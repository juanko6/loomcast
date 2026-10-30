<script lang="ts">
  import Button from "../../primitives/Button.svelte";
  import Icon from "../../primitives/Icon.svelte";
  import { media } from "@/lib/api";
  import { onMount } from "svelte";
  import {
    MODOS_VIDEO,
    ETAPA_VIDEO,
    listarMotoresI2V,
    type MotorI2V,
    type ProyectoDetalle,
  } from "@/lib/proyectos";

  let {
    p,
    busy = false,
    bust = 0,
    ongenerar,
    onborrarvideo,
    onborrarversion,
    onborrarproyecto,
    onver,
  }: {
    p: ProyectoDetalle;
    busy?: boolean;
    bust?: number;
    ongenerar: (modo: string, motor: string) => void;
    onborrarvideo: () => void;
    onborrarversion: (nombre: string) => void;
    onborrarproyecto: () => void;
    onver: (html: string, pie: string) => void;
  } = $props();

  let modo = $state("kenburns");
  // Motores i2v de config.toml. Solo se piden una vez y solo importan cuando el
  // modo elegido anima con i2v.
  let motores = $state<MotorI2V[]>([]);
  let motor = $state("");
  const conI2V = $derived(modo === "i2v" || modo === "mixto");

  onMount(async () => {
    // Si la lista no llega, el selector no aparece y se genera con el motor de
    // config.toml: quedarse sin elegir motor no puede tumbar el paso entero.
    try {
      motores = await listarMotoresI2V();
      motor = motores.find((m) => m.defecto)?.id ?? motores[0]?.id ?? "";
    } catch {
      motores = [];
    }
  });
  const etapa = $derived(p.job_activo ? ETAPA_VIDEO[p.job_activo] : null);
  const totalMb = $derived(p.versiones.reduce((a, v) => a + v.mb, 0).toFixed(0));
</script>

<div class="max-w-3xl space-y-5">
  {#if p.liberado}
    <p class="rounded-xl border border-warn/30 bg-warn-soft px-3 py-2 text-sm text-warn">
      Este vídeo se publicó y su material se liberó: en disco solo queda el montaje final. Para
      rehacerlo hay que volver a generar la voz, las escenas y las imágenes desde sus pasos.
    </p>
  {/if}

  <fieldset class="space-y-2">
    <legend class="mb-2 text-xs font-medium tracking-wide text-dim">Modo de generación</legend>
    {#each MODOS_VIDEO as m (m.id)}
      <label
        class={`flex cursor-pointer gap-3 rounded-xl border p-3 transition-colors
          ${modo === m.id ? "border-accent bg-accent-soft" : "border-line bg-surface-2 hover:border-dim"}`}
      >
        <input type="radio" name="modo-video" value={m.id} bind:group={modo} class="mt-1" />
        <span>
          <span class="block text-sm font-medium">{m.nombre}</span>
          <span class="block text-xs text-dim">{m.desc}</span>
        </span>
      </label>
    {/each}
  </fieldset>

  {#if conI2V && motores.length > 1}
    <label class="block space-y-1">
      <span class="text-xs font-medium tracking-wide text-dim">Motor de movimiento</span>
      <select class="control" bind:value={motor}>
        {#each motores as m (m.id)}
          <option value={m.id}>{m.nombre} · {m.frames} cuadros</option>
        {/each}
      </select>
      <span class="block text-xs text-dim">
        Las escenas que ya tengan clip hecho con otro motor se vuelven a generar.
      </span>
    </label>
  {/if}

  <div class="flex flex-wrap items-center gap-3">
    <!-- Liberado no hay con qué armar: las imágenes y la narración ya no
         están, y el botón solo serviría para encolar un job que falla. -->
    <Button
      disabled={busy || p.liberado}
      title={p.liberado ? "Su material se liberó: no hay imágenes con las que armarlo" : undefined}
      onclick={() => ongenerar(modo, conI2V ? motor : "")}
    >
      {p.video_disponible ? "Rehacer vídeo" : "Generar vídeo"}
    </Button>
    {#if etapa}
      <span class="flex items-center gap-2 text-sm text-dim">
        <span class="size-4 animate-spin rounded-full border-2 border-line border-t-accent"></span>
        {etapa}
      </span>
    {/if}
  </div>

  <p class="text-xs text-dim">
    {#if p.musica_mezclar && p.musica}
      La pista «{p.musica.idea}» se mezclará por debajo de la narración.
    {:else if p.musica?.tiene_audio}
      Hay música generada, pero no se mezclará: actívalo en el paso de Música.
    {:else}
      El vídeo sale con voz y subtítulos. Para añadir música, pasa por el paso de Música.
    {/if}
  </p>

  {#if p.video_disponible}
    <div class="space-y-2">
      <video
        src={`${media(`/proyectos/${p.id}/video`)}?v=${bust}`}
        controls
        class="w-64 rounded-xl"
      ></video>
      <div class="flex flex-wrap gap-2">
        <Button
          size="sm"
          variant="secondary"
          onclick={() =>
            onver(
              `<video src="${media(`/proyectos/${p.id}/video`)}?v=${bust}" controls autoplay playsinline></video>`,
              "Vídeo final",
            )}
        >
          Ver en grande
        </Button>
        <a
          href={`${media(`/proyectos/${p.id}/video`)}?v=${bust}`}
          download={`${p.slug}.mp4`}
          class="inline-flex items-center gap-2 rounded-md border border-line bg-surface-2 px-3 py-1.5 text-xs text-text transition hover:border-accent"
        >
          <Icon name="download" size={14} /> Descargar
        </a>
        <Button size="sm" variant="danger" onclick={onborrarvideo}>Borrar vídeo</Button>
      </div>
    </div>
  {/if}

  {#if p.versiones.length}
    <details class="rounded-xl border border-line bg-surface-2 p-3">
      <summary class="cursor-pointer text-sm text-dim">
        Montajes anteriores ({p.versiones.length} · {totalMb} MB)
      </summary>
      <div class="mt-2 space-y-1">
        {#each p.versiones as v (v.nombre)}
          <div class="flex items-center gap-2 border-b border-line-soft py-1.5 last:border-0">
            <span class="flex-1 text-xs tabular-nums text-muted">{v.fecha} · {v.mb} MB</span>
            <Button
              size="sm"
              variant="ghost"
              onclick={() =>
                onver(
                  `<video src="${media(`/proyectos/${p.id}/versiones/${v.nombre}`)}" controls autoplay playsinline></video>`,
                  v.nombre,
                )}
            >
              Ver
            </Button>
            <a
              href={media(`/proyectos/${p.id}/versiones/${v.nombre}`)}
              download={v.nombre}
              class="rounded-md p-1.5 text-dim transition hover:bg-surface-3 hover:text-text"
              title="Descargar"
              aria-label="Descargar versión"
            >
              <Icon name="download" size={14} />
            </a>
            <Button size="sm" variant="ghost" onclick={() => onborrarversion(v.nombre)}>✕</Button>
          </div>
        {/each}
      </div>
    </details>
  {/if}

  <div class="flex items-center gap-3 border-t border-line pt-4">
    <Button variant="danger" size="sm" disabled={busy} onclick={onborrarproyecto}>
      Borrar proyecto entero
    </Button>
    <span class="text-xs text-muted">
      Borra el guion, la voz, las imágenes, los clips y los vídeos.
    </span>
  </div>
</div>
