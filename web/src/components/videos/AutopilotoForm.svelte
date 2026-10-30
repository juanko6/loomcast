<script lang="ts">
  // Con qué se lanza una tirada automática: el modo de montaje, el motor, la
  // voz y qué paradas de revisión se respetan.
  //
  // Es el mismo formulario para un proyecto y para un lote, porque son las
  // mismas decisiones. Las dos primeras se piden aquí y no se adivinan: el modo
  // de montaje ya se elige a mano en el paso de vídeo, y sin voz la narración no
  // se puede generar.
  //
  // De la voz hay dos respuestas, y en un lote la que importa es la segunda:
  // una voz del banco se clona igual en los diez vídeos (y una de hombre
  // elegida a mano narrando la historia de una mujer canta en los diez), o la
  // narración expresiva, que la escribe VoiceDesign con el estilo que el LLM
  // sacó de cada guion. Por eso, cuando no hay ninguna elegida, lo que viene
  // puesto es la expresiva: el hueco de antes no se podía lanzar.
  import { onMount } from "svelte";
  import Button from "../primitives/Button.svelte";
  import Field from "../primitives/Field.svelte";
  import { MODOS_VIDEO, listarMotoresI2V, type MotorI2V, type Voz } from "@/lib/proyectos";
  import {
    PARADAS,
    PARADAS_DEFECTO,
    VOZ_EXPRESIVA,
    type OpcionesAutopiloto,
  } from "@/lib/autopiloto";

  let {
    voces = [],
    vozActual = null,
    busy = false,
    etiqueta = "Lanzar autopiloto",
    onlanzar,
  }: {
    voces?: Voz[];
    // La que ya tenga el proyecto elegida, para no volver a pedirla.
    vozActual?: string | null;
    busy?: boolean;
    etiqueta?: string;
    onlanzar: (o: OpcionesAutopiloto) => void;
  } = $props();

  let modo = $state("kenburns");
  let motor = $state("");
  let motores = $state<MotorI2V[]>([]);
  let voz = $state(vozActual ?? VOZ_EXPRESIVA);
  // Se arranca con las tres puestas, que es lo que hace el flujo a mano.
  let activas = $state<string[]>([...PARADAS_DEFECTO]);

  const conI2V = $derived(modo === "i2v" || modo === "mixto");
  const disponibles = $derived(voces.filter((v) => v.disponible));
  const expresiva = $derived(voz === VOZ_EXPRESIVA);

  onMount(async () => {
    try {
      motores = await listarMotoresI2V();
      motor = motores.find((m) => m.defecto)?.id ?? motores[0]?.id ?? "";
    } catch {
      motores = [];
    }
  });

  function alternar(id: string) {
    activas = activas.includes(id) ? activas.filter((x) => x !== id) : [...activas, id];
  }

  function lanzar() {
    onlanzar({
      modo,
      motor: conI2V ? motor : "",
      narracion: expresiva ? "design" : "clon",
      // Con la expresiva no hay voz del banco que mandar: la del proyecto se
      // queda como esté, porque lo que narra es el estilo del guion.
      voz: expresiva ? "" : voz,
      // Se mandan siempre, incluso vacías: una lista vacía es "producción sin
      // manos" y no es lo mismo que no decir nada (eso serían las de
      // config.toml).
      paradas: activas,
    });
  }
</script>

<div class="space-y-4">
  <div class="grid gap-3 sm:grid-cols-2">
    <Field label="Modo de montaje">
      <select class="control" bind:value={modo}>
        {#each MODOS_VIDEO as m (m.id)}
          <option value={m.id}>{m.nombre}</option>
        {/each}
      </select>
    </Field>

    <Field label="Voz de la narración">
      <select class="control" bind:value={voz}>
        <option value={VOZ_EXPRESIVA}>Narración expresiva (del guion)</option>
        <option value="">
          {vozActual ? "La que ya tiene elegida" : "— elige una voz del banco —"}
        </option>
        {#each disponibles as v (v.slug)}
          <option value={v.slug}>{v.nombre}</option>
        {/each}
      </select>
    </Field>
  </div>

  <p class="text-xs text-muted">
    {#if expresiva}
      Cada vídeo lo narra VoiceDesign con el estilo que el LLM escribió para su
      guion, así que la voz la pone la historia y no se elige a mano. Las voces del
      reparto siguen saliendo de la ficha de cada personaje.
    {:else}
      Se clona esa voz del banco, la misma en todo lo que produzca esta tirada,
      también si la historia pide otra.
    {/if}
  </p>

  {#if conI2V && motores.length > 1}
    <Field label="Motor de movimiento">
      <select class="control" bind:value={motor}>
        {#each motores as m (m.id)}
          <option value={m.id}>{m.nombre} · {m.frames} cuadros</option>
        {/each}
      </select>
    </Field>
  {/if}

  <fieldset class="space-y-2">
    <legend class="mb-1 text-xs font-medium tracking-wide text-dim">
      Paradas de revisión
    </legend>
    {#each PARADAS as p (p.id)}
      <label class="flex cursor-pointer items-start gap-2.5">
        <input
          type="checkbox"
          class="mt-0.5"
          checked={activas.includes(p.id)}
          onchange={() => alternar(p.id)}
        />
        <span>
          <span class="block text-sm">{p.nombre}</span>
          <span class="block text-xs text-dim">{p.desc}</span>
        </span>
      </label>
    {/each}
    <p class="text-xs text-muted">
      {activas.length
        ? "El autopiloto llega hasta la siguiente parada, deja el proyecto esperando y lo dice."
        : "Sin paradas: de aquí al vídeo final sin preguntar nada."}
    </p>
  </fieldset>

  <Button disabled={busy} onclick={lanzar}>{etiqueta}</Button>
</div>
