<script lang="ts">
  import Field from "../primitives/Field.svelte";
  import Segmented from "../primitives/Segmented.svelte";
  import Button from "../primitives/Button.svelte";
  import Icon from "../primitives/Icon.svelte";
  import { TAMANOS } from "@/lib/galeria";
  import type { TipoGaleria } from "@/lib/types";

  let {
    busy = false,
    oncreateGenerar,
    oncreateEditar,
    oncreateFondo,
  }: {
    busy?: boolean;
    oncreateGenerar: (p: { idea: string; width: number; height: number }) => void;
    oncreateEditar: (p: { idea: string; file: File }) => void;
    oncreateFondo: (p: { file: File }) => void;
  } = $props();

  let tipo = $state<TipoGaleria>("generar");
  let idea = $state("");
  let tamano = $state(`${TAMANOS[0].w}x${TAMANOS[0].h}`);
  let customW = $state(1024);
  let customH = $state(1024);
  let file = $state<File | null>(null);
  let previewUrl = $state<string | null>(null);

  const esCustom = $derived(tamano === "custom");
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
  const puedeCrear = $derived(
    tipo === "generar"
      ? !!idea.trim()
      : tipo === "editar"
        ? !!idea.trim() && !!file
        : !!file,
  );

  function crear() {
    if (tipo === "generar") {
      const [w, h] = tamanoElegido();
      oncreateGenerar({ idea: idea.trim(), width: w, height: h });
    } else if (tipo === "editar" && file) {
      oncreateEditar({ idea: idea.trim(), file });
    } else if (tipo === "quitarfondo" && file) {
      oncreateFondo({ file });
    }
  }

  const ideaLabel = $derived(
    tipo === "editar" ? "¿Qué cambios o efectos quieres aplicar?" : "¿Qué imagen quieres?",
  );
  const ideaPlaceholder = $derived(
    tipo === "editar"
      ? "Ej: cambia el cielo a un atardecer dramático y añade niebla"
      : "Ej: un faro solitario en un acantilado bajo una tormenta eléctrica",
  );
  const ctaLabel = $derived(
    tipo === "quitarfondo" ? "Quitar fondo" : tipo === "editar" ? "Subir y mejorar prompt" : "Crear",
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
      ]}
      value={tipo}
      onchange={(v) => (tipo = v as TipoGaleria)}
    />

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
      <Field
        label={ideaLabel}
        hint="Después puedes escribir el prompt a mano o pedirle al LLM que lo mejore."
      >
        <textarea class="control" rows="3" bind:value={idea} placeholder={ideaPlaceholder}></textarea>
      </Field>
    {/if}

    {#if tipo === "generar"}
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
    {/if}
  </div>

  <div class="border-t border-line bg-surface p-4">
    <Button class="w-full" disabled={busy || !puedeCrear} onclick={crear}>{ctaLabel}</Button>
  </div>
</div>
