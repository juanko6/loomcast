<script lang="ts">
  import { onMount } from "svelte";
  import Field from "../primitives/Field.svelte";
  import Segmented from "../primitives/Segmented.svelte";
  import Button from "../primitives/Button.svelte";
  import Icon from "../primitives/Icon.svelte";
  import StylePicker from "./StylePicker.svelte";
  import { media } from "@/lib/api";
  import {
    N_PREVIEWS_DEFECTO,
    N_PREVIEWS_MAX,
    TAMANO_ANIMADA,
    TAMANOS,
    listarMotores,
    rutaEjemploEstilo,
    type EstiloImagen,
    type MotorImagen,
    type NuevaImagen,
  } from "@/lib/galeria";
  import type { TipoGaleria } from "@/lib/types";

  let {
    busy = false,
    estilos = [],
    oncreateGenerar,
    oncreateEditar,
    oncreateFondo,
    oncreateAnimada,
  }: {
    busy?: boolean;
    estilos?: EstiloImagen[];
    oncreateGenerar: (p: NuevaImagen & { motor: string }) => void;
    oncreateEditar: (p: { idea: string; file: File; motor: string }) => void;
    oncreateFondo: (p: { file: File }) => void;
    oncreateAnimada: (p: NuevaImagen) => void;
  } = $props();

  // Estilo y cuántas previews: los dos se recuerdan en este navegador, porque
  // lo normal es hacer varias seguidas con el mismo look. El acceso a
  // localStorage puede fallar (ventana privada, datos bloqueados).
  const CLAVE_N = "loomcast.galeria.nPreviews";
  const CLAVE_ESTILO = "loomcast.galeria.estilo";
  function leer(clave: string): string | null {
    try {
      return localStorage.getItem(clave);
    } catch {
      return null;
    }
  }
  function guardar(clave: string, v: string) {
    try {
      localStorage.setItem(clave, v);
    } catch {
      /* sin almacenamiento: se olvida al recargar, nada más */
    }
  }
  const nGuardado = Number(leer(CLAVE_N));
  let nPreviews = $state(
    nGuardado >= 1 && nGuardado <= N_PREVIEWS_MAX ? nGuardado : N_PREVIEWS_DEFECTO,
  );
  let estilo = $state(leer(CLAVE_ESTILO) ?? "");
  let detalles = $state("");
  let eligiendoEstilo = $state(false);
  $effect(() => guardar(CLAVE_N, String(nPreviews)));
  $effect(() => guardar(CLAVE_ESTILO, estilo));
  // Un estilo recordado que ya no existe (se borró la carpeta) vuelve a libre.
  $effect(() => {
    if (estilos.length && estilo && !estilos.some((e) => e.id === estilo)) estilo = "";
  });
  const estiloElegido = $derived(estilos.find((e) => e.id === estilo) ?? null);

  let tipo = $state<TipoGaleria>("generar");
  let motores = $state<MotorImagen[]>([]);
  // Motor elegido por modo: cambiar de Generar a Editar no debe perder la
  // elección del otro, y cada modo tiene su propio motor por defecto.
  let motorPorModo = $state<Record<string, string>>({ generar: "", editar: "" });

  // Motores que saben hacer el modo activo. Quitar fondo no pasa por ComfyUI,
  // la animada usa el del estilo (o Z-Image), y con un estilo elegido el motor
  // es el suyo: el que mejor lo dibuja.
  const motoresDelModo = $derived.by(() => {
    if (tipo === "quitarfondo" || tipo === "animada") return [];
    if (tipo === "generar" && estilo) return [];
    const modo = tipo;
    return motores.filter((m) => m.modos.includes(modo));
  });
  const motorElegido = $derived(motorPorModo[tipo] ?? "");

  onMount(async () => {
    motores = await listarMotores();
    for (const modo of ["generar", "editar"] as const) {
      motorPorModo[modo] =
        motores.find((m) => m.defecto_en.includes(modo))?.id ??
        motores.find((m) => m.modos.includes(modo))?.id ??
        "";
    }
  });
  let idea = $state("");
  let tamano = $state(`${TAMANOS[0].w}x${TAMANOS[0].h}`);
  let customW = $state(1024);
  let customH = $state(1024);
  let file = $state<File | null>(null);
  let previewUrl = $state<string | null>(null);

  const esCustom = $derived(tamano === "custom");

  // La animada va a YouTube: arranca en horizontal. Al volver a Generar se
  // recupera el vertical, salvo que se hubiera elegido otro tamaño a mano.
  const TAMANO_INICIAL = `${TAMANOS[0].w}x${TAMANOS[0].h}`;
  function elegirTipo(v: string) {
    const nuevo = v as TipoGaleria;
    if (nuevo === "animada" && tamano === TAMANO_INICIAL) tamano = TAMANO_ANIMADA;
    else if (tipo === "animada" && nuevo !== "animada" && tamano === TAMANO_ANIMADA)
      tamano = TAMANO_INICIAL;
    tipo = nuevo;
  }
  function tamanoElegido(): [number, number] {
    if (esCustom) return [customW || 1024, customH || 1024];
    const [w, h] = tamano.split("x").map(Number);
    return [w, h];
  }

  function elegirArchivo(e: Event) {
    const f = (e.target as HTMLInputElement).files?.[0] ?? null;
    file = f;
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = f ? URL.createObjectURL(f) : null;
  }

  const usaArchivo = $derived(tipo === "editar" || tipo === "quitarfondo");
  // Generar y animada piden lo mismo para empezar: una idea y un tamaño.
  const conTamano = $derived(tipo === "generar" || tipo === "animada");
  const puedeCrear = $derived(
    conTamano
      ? !!idea.trim()
      : tipo === "editar"
        ? !!idea.trim() && !!file
        : !!file,
  );

  function nueva(): NuevaImagen {
    const [width, height] = tamanoElegido();
    return { idea: idea.trim(), detalles: detalles.trim(), estilo, n_previews: nPreviews, width, height };
  }

  function crear() {
    if (tipo === "generar") {
      // Con estilo, el motor lo pone el estilo (el backend lo resuelve).
      oncreateGenerar({ ...nueva(), motor: estilo ? "" : motorElegido });
    } else if (tipo === "animada") {
      oncreateAnimada(nueva());
    } else if (tipo === "editar" && file) {
      oncreateEditar({ idea: idea.trim(), file, motor: motorElegido });
    } else if (tipo === "quitarfondo" && file) {
      oncreateFondo({ file });
    }
  }

  const ideaLabel = $derived(
    tipo === "editar" ? "¿Qué cambios o efectos quieres aplicar?" : "Título",
  );
  const ideaPlaceholder = $derived(
    tipo === "editar"
      ? "Ej: cambia el cielo a un atardecer dramático y añade niebla"
      : tipo === "animada"
        ? "Ej: Morning Groove – jazz hip hop para empezar el día"
        : "Ej: un faro solitario en un acantilado bajo una tormenta eléctrica",
  );
  const ideaHint = $derived(
    tipo === "editar"
      ? "Después puedes escribir el prompt a mano o pedirle al LLM que lo mejore."
      : tipo === "animada"
        ? "Lo que quieres ver, o el título del vídeo. Al crear, el LLM escribe la escena y salen las previews; apruebas una y luego eliges cómo se mueve (10–15 s en bucle)."
        : "Lo que quieres ver, o el título del vídeo. Al crear, el LLM escribe la escena y salen las previews directamente.",
  );
  const ctaLabel = $derived(
    tipo === "quitarfondo" ? "Quitar fondo" : tipo === "editar" ? "Subir imagen" : "Crear",
  );
</script>

<div class="flex h-full flex-col">
  <div class="min-h-0 flex-1 space-y-4 overflow-y-auto p-5">
    <h2 class="text-sm font-semibold text-text">Nueva imagen</h2>
    <Segmented
      options={[
        { value: "generar", label: "Generar" },
        { value: "editar", label: "Editar" },
        { value: "quitarfondo", label: "Quitar fondo" },
        { value: "animada", label: "Animada" },
      ]}
      value={tipo}
      onchange={elegirTipo}
    />

    {#if motoresDelModo.length > 1}
      <Field label="Modelo">
        <select class="control" value={motorElegido} onchange={(e) => (motorPorModo[tipo] = e.currentTarget.value)}>
          {#each motoresDelModo as m (m.id)}
            <option value={m.id}>{m.nombre}</option>
          {/each}
        </select>
      </Field>
    {/if}

    {#if usaArchivo}
      <Field label="Imagen de origen">
        <label
          class="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border
                 border-dashed border-line bg-surface-2 p-4 text-center transition hover:border-accent"
        >
          {#if previewUrl}
            <img src={previewUrl} alt="origen" class="max-h-40 rounded-md object-contain" />
            <span class="text-xs text-dim">Cambiar imagen</span>
          {:else}
            <Icon name="image" size={28} class="text-muted" />
            <span class="text-xs text-dim">Haz clic para elegir una imagen</span>
          {/if}
          <input type="file" accept="image/*" class="hidden" onchange={elegirArchivo} />
        </label>
      </Field>
    {/if}

    {#if tipo !== "quitarfondo"}
      <Field label={ideaLabel} hint={ideaHint}>
        <textarea class="control" rows="3" bind:value={idea} placeholder={ideaPlaceholder}></textarea>
      </Field>
    {/if}

    {#if conTamano}
      <Field label="Detalles (opcional)" hint="Mandan sobre lo que el LLM deduzca del título.">
        <textarea
          class="control"
          rows="2"
          bind:value={detalles}
          placeholder="Ej: un gato naranja en vez de una persona, fondo verde menta"
        ></textarea>
      </Field>

      <div class="flex flex-col gap-1.5">
        <span class="text-xs font-medium tracking-wide text-dim">Estilo</span>
        <button
          type="button"
          onclick={() => (eligiendoEstilo = true)}
          class="flex items-center gap-3 rounded-lg border border-line bg-surface-2 p-2 text-left transition hover:border-accent"
        >
          {#if estiloElegido && estiloElegido.ejemplos > 0}
            <img
              src={media(rutaEjemploEstilo(estiloElegido.id, 0))}
              alt=""
              class="h-10 w-16 shrink-0 rounded object-cover"
            />
          {:else}
            <span class="flex h-10 w-16 shrink-0 items-center justify-center rounded bg-surface text-[10px] text-muted">
              {estiloElegido ? "sin ejemplo" : "libre"}
            </span>
          {/if}
          <span class="min-w-0 flex-1">
            <span class="block truncate text-sm text-text">{estiloElegido?.nombre ?? "Libre"}</span>
            <span class="block truncate text-xs text-dim">
              {estiloElegido?.descripcion ?? "El LLM elige el estilo."}
            </span>
          </span>
          <span class="text-xs text-accent">Cambiar</span>
        </button>
      </div>
    {/if}

    {#if conTamano}
      <Field label="Tamaño">
        <select class="control" bind:value={tamano}>
          {#each TAMANOS as t (t.label)}
            <option value={`${t.w}x${t.h}`}>{t.label} · {t.w}×{t.h}</option>
          {/each}
          <option value="custom">Personalizado…</option>
        </select>
      </Field>
      {#if esCustom}
        <div class="flex gap-2">
          <Field label="Ancho">
            <input class="control" type="number" min="256" max="1536" step="64" bind:value={customW} />
          </Field>
          <Field label="Alto">
            <input class="control" type="number" min="256" max="1536" step="64" bind:value={customH} />
          </Field>
        </div>
        <p class="text-xs text-muted">Se redondea a múltiplos de 64 (entre 256 y 1536).</p>
      {/if}
      <Field label="Previews">
        <select class="control" bind:value={nPreviews}>
          {#each Array.from({ length: N_PREVIEWS_MAX }, (_, i) => i + 1) as n (n)}
            <option value={n}>{n} {n === 1 ? "preview" : "previews"}</option>
          {/each}
        </select>
      </Field>
    {/if}
  </div>

  <div class="border-t border-line bg-surface p-4">
    <Button class="w-full" disabled={busy || !puedeCrear} onclick={crear}>{ctaLabel}</Button>
  </div>
</div>

{#if eligiendoEstilo}
  <StylePicker
    {estilos}
    value={estilo}
    onpick={(id) => {
      estilo = id;
      eligiendoEstilo = false;
    }}
    onclose={() => (eligiendoEstilo = false)}
  />
{/if}
