<script lang="ts">
  import Chip from "../primitives/Chip.svelte";
  import Icon from "../primitives/Icon.svelte";
  import { currentTrack, isPlaying, playTrack } from "@/lib/player";
  import type { LibItem } from "@/lib/biblioteca";
  import { escaparHtml as esc } from "@/lib/html";
  import type { TipoMusica } from "@/lib/types";

  let {
    item,
    onopen,
    onview,
  }: {
    item: LibItem;
    onopen: () => void;
    onview: (html: string, pie: string) => void;
  } = $props();

  // Si la miniatura no existe todavía (p. ej. un proyecto sin imágenes), se
  // oculta y queda el icono de fondo.
  let sinThumb = $state(false);

  const sonando = $derived(
    item.kind === "musica" && $currentTrack?.id === item.id && $isPlaying,
  );

  const icono = $derived(
    item.kind === "musica" ? "music" : item.kind === "video" ? "clapper" : "image",
  );

  function accionPrincipal() {
    if (item.kind === "musica" && item.src) {
      playTrack({
        id: item.id,
        tipo: (item.subtipo === "Canción" ? "cancion" : "instrumental") as TipoMusica,
        idea: item.titulo,
        seed: null,
        duracion_s: 0,
        src: item.src,
      });
    } else if (item.kind === "video" && item.src) {
      onview(`<video src="${esc(item.src)}" controls autoplay playsinline></video>`, item.titulo);
    } else if (item.kind === "imagen" && item.video) {
      onview(
        `<video src="${esc(item.video)}" controls autoplay loop muted playsinline></video>`,
        item.titulo,
      );
    } else if (item.kind === "imagen" && item.src) {
      onview(`<img src="${esc(item.src)}" alt="${esc(item.titulo)}">`, item.titulo);
    } else {
      onopen();
    }
  }

  const reproducible = $derived(!!item.src);
</script>

<article
  class="group flex flex-col overflow-hidden rounded-xl border border-line bg-surface-2 transition-colors hover:border-dim"
>
  <!-- Portada -->
  <button
    type="button"
    onclick={accionPrincipal}
    class="relative block aspect-video w-full overflow-hidden bg-surface-3"
    aria-label={reproducible ? `Abrir ${item.titulo}` : item.titulo}
  >
    {#if item.video}
      <!-- El bucle es la portada: se ve tal cual empalma. -->
      <video
        src={item.video}
        poster={item.thumb ?? undefined}
        autoplay
        loop
        muted
        playsinline
        class="size-full object-cover"
      ></video>
    {:else if item.thumb && !sinThumb}
      <img
        src={item.thumb}
        alt=""
        loading="lazy"
        onerror={() => (sinThumb = true)}
        class="size-full object-cover"
      />
    {:else}
      <span class="grid size-full place-items-center text-muted">
        <Icon name={icono} size={28} />
      </span>
    {/if}

    {#if reproducible}
      <span
        class={`absolute inset-0 grid place-items-center bg-black/40 text-white transition-opacity
          ${sonando ? "opacity-100" : "opacity-0 group-hover:opacity-100"}`}
      >
        <span class="grid size-10 place-items-center rounded-full bg-accent text-on-accent">
          <Icon name={sonando ? "pause" : "play"} size={16} />
        </span>
      </span>
    {/if}
  </button>

  <!-- Datos -->
  <div class="flex min-w-0 flex-1 flex-col gap-2 p-3">
    <p class="line-clamp-2 text-sm font-medium break-words">{item.titulo}</p>
    <div class="mt-auto flex flex-wrap items-center gap-1.5">
      {#if item.subtipo}<Chip tone="accent">{item.subtipo}</Chip>{/if}
      <!-- Un vídeo subido está en FINAL por definición: la marca dice más que
           el estado, así que ocupa su sitio. -->
      {#if item.publicado_en}
        <Chip tone="ok">subido</Chip>
      {:else}
        <Chip>{item.estado}</Chip>
      {/if}
      <button
        type="button"
        onclick={onopen}
        class="ml-auto rounded-md px-2 py-1 text-xs text-dim transition hover:bg-surface-3 hover:text-text"
      >
        Abrir →
      </button>
    </div>
  </div>
</article>
