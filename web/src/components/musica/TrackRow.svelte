<script lang="ts">
  import Chip from "../primitives/Chip.svelte";
  import Thumbnail from "../primitives/Thumbnail.svelte";
  import IconButton from "../primitives/IconButton.svelte";
  import Icon from "../primitives/Icon.svelte";
  import { media } from "@/lib/api";
  import { portadaUrl } from "@/lib/musica";
  import { currentTrack, isPlaying, playTrack } from "@/lib/player";
  import type { MusicaResumen } from "@/lib/types";

  let {
    track,
    active = false,
    onselect,
    ondelete,
  }: {
    track: MusicaResumen;
    active?: boolean;
    onselect: () => void;
    ondelete: () => void;
  } = $props();

  const tipoLabel = $derived(track.tipo === "cancion" ? "Canción" : "Instrumental");
  // Solo las pistas ya generadas tienen audio que reproducir.
  const reproducible = $derived(track.estado === "generada");
  const sonando = $derived($currentTrack?.id === track.id && $isPlaying);

  const cover = $derived(track.tiene_portada ? portadaUrl(track.id) : null);

  function reproducir() {
    playTrack({
      id: track.id,
      tipo: track.tipo,
      idea: track.idea,
      seed: null,
      duracion_s: 0,
      src: media(`/musica/${track.id}/audio`),
      cover,
    });
  }

  // TODO(feature): compartir y like requieren backend; por ahora son stubs.
  function proximamente() {}
</script>

<div
  class={`group relative flex items-center gap-3 rounded-lg border px-3 py-2.5 transition-colors
    ${active
      ? "border-accent/40 bg-accent-soft"
      : "border-line-soft bg-surface-2 hover:border-line hover:bg-surface-3"}`}
>
  {#if reproducible}
    <Thumbnail src={cover} alt="" icon="music" size={48} playing={sonando} onplay={reproducir} />
  {:else}
    <Thumbnail src={cover} alt="" icon="music" size={48} />
  {/if}

  <button type="button" onclick={onselect} class="flex min-w-0 flex-1 flex-col items-start gap-1 text-left">
    <span class="w-full truncate text-sm font-medium text-text">
      {track.idea?.trim() || "(pista sin título)"}
    </span>
    <span class="flex items-center gap-1.5">
      <Chip tone="accent">{tipoLabel}</Chip>
      <Chip>{track.estado}</Chip>
    </span>
  </button>

  <!-- Acciones: aparecen al pasar por encima (o si la pista suena) -->
  <div
    class={`flex shrink-0 items-center gap-0.5 transition-opacity
      ${sonando ? "opacity-100" : "opacity-0 group-hover:opacity-100 focus-within:opacity-100"}`}
  >
    <IconButton name="heart" label="Me gusta" size={16} soon onclick={proximamente} />
    <IconButton name="share" label="Compartir" size={16} soon onclick={proximamente} />
    {#if reproducible}
      <a
        href={media(`/musica/${track.id}/audio`)}
        download={`loomcast_musica_${track.id}`}
        title="Descargar"
        aria-label="Descargar"
        onclick={(e) => e.stopPropagation()}
        class="inline-grid place-items-center rounded-md p-2 text-dim transition-colors hover:bg-surface-3 hover:text-text"
      >
        <Icon name="download" size={16} />
      </a>
    {/if}
    <IconButton
      name="x"
      label="Borrar pista"
      size={16}
      onclick={ondelete}
      class="hover:bg-danger-soft hover:text-danger"
    />
  </div>
</div>
