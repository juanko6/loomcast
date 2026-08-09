<script lang="ts">
  import Chip from "../primitives/Chip.svelte";
  import Icon from "../primitives/Icon.svelte";
  import { media } from "@/lib/api";
  import { currentTrack, isPlaying, playTrack } from "@/lib/player";
  import type { MusicaDetalle } from "@/lib/musica";

  let {
    detail,
    busy = false,
  }: { detail: MusicaDetalle | null; busy?: boolean } = $props();

  const tipoLabel = $derived(detail?.tipo === "cancion" ? "Canción" : "Instrumental");
  const sonando = $derived($currentTrack?.id === detail?.id && $isPlaying);

  function reproducir() {
    if (!detail) return;
    playTrack({
      id: detail.id,
      tipo: detail.tipo,
      idea: detail.idea,
      seed: detail.seed,
      duracion_s: detail.duracion_s,
      src: media(`/musica/${detail.id}/audio`),
    });
  }
</script>

<aside class="flex h-full w-[340px] min-w-0 shrink-0 flex-col border-l border-line bg-surface">
  <header class="flex items-center gap-2 border-b border-line px-5 py-4">
    <h2 class="text-sm font-semibold">Resultado</h2>
  </header>

  <div class="min-h-0 flex-1 overflow-y-auto p-5">
    {#if !detail}
      <p class="mt-10 text-center text-sm text-dim">
        Selecciona una pista o crea una nueva para empezar.
      </p>
    {:else if busy}
      <div class="mt-10 flex flex-col items-center gap-3 text-dim">
        <span class="size-6 animate-spin rounded-full border-2 border-line border-t-accent"></span>
        <p class="text-sm">Generando música…</p>
      </div>
    {:else if detail.tiene_audio}
      <div class="space-y-4">
        <div class="flex flex-wrap items-center gap-1.5">
          <Chip tone="accent">{tipoLabel}</Chip>
          {#if detail.seed != null}<Chip>seed {detail.seed}</Chip>{/if}
          <Chip>{detail.duracion_s}s</Chip>
          <Chip>{detail.bpm} BPM</Chip>
          <Chip>{detail.keyscale}</Chip>
          <Chip>{detail.timesig}/4</Chip>
        </div>

        <div class="flex items-center gap-2">
          <button
            type="button"
            onclick={reproducir}
            class="inline-flex items-center gap-2 rounded-md bg-accent px-4 py-2 text-sm font-medium
                   text-on-accent transition hover:bg-accent-hover"
          >
            <Icon name={sonando ? "pause" : "play"} size={16} />
            {sonando ? "Pausar" : "Reproducir"}
          </button>
          <a
            href={media(`/musica/${detail.id}/audio`)}
            download={`loomcast_musica_${detail.id}`}
            title="Descargar"
            aria-label="Descargar"
            class="inline-grid place-items-center rounded-md border border-line bg-surface-2 p-2.5
                   text-dim transition hover:border-accent hover:text-text"
          >
            <Icon name="download" size={16} />
          </a>
        </div>

        {#if detail.tags}
          <div class="space-y-1.5">
            <p class="text-xs font-medium tracking-wide text-muted">Estilo</p>
            <p class="text-sm leading-relaxed text-dim">{detail.tags}</p>
          </div>
        {/if}
        {#if detail.tipo === "cancion" && detail.lyrics}
          <div class="space-y-1.5">
            <p class="text-xs font-medium tracking-wide text-muted">Letra</p>
            <pre class="whitespace-pre-wrap font-sans text-sm leading-relaxed text-dim">{detail.lyrics}</pre>
          </div>
        {/if}
      </div>
    {:else}
      <div class="mt-10 flex flex-col items-center gap-2 text-center text-dim">
        <Icon name="music" size={40} class="text-muted" />
        <p class="text-sm">Aún no hay audio.</p>
        <p class="text-xs text-muted">Ajusta el estilo y pulsa «Generar música».</p>
      </div>
    {/if}
  </div>
</aside>
