<script lang="ts">
  // Área de trabajo: cabecera compartida + el estudio del modo activo. La
  // cabecera lleva el estado de la cola y la parada (ColaPanel), que así están
  // en el mismo sitio en las cuatro secciones.
  import { modo, jobs, lotes } from "@/lib/stores";
  import ColaPanel from "./ColaPanel.svelte";
  import BotonParar from "./BotonParar.svelte";
  import MusicStudio from "../musica/MusicStudio.svelte";
  import ImageStudio from "../imagenes/ImageStudio.svelte";
  import VideoStudio from "../videos/VideoStudio.svelte";
  import LibraryStudio from "../biblioteca/LibraryStudio.svelte";
  import type { StudioMode } from "@/lib/types";

  const titulos: Record<StudioMode, { t: string; sub: string }> = {
    videos: { t: "Vídeos", sub: "Del tema a la idea, guion, voz, escenas y montaje final" },
    imagenes: { t: "Imágenes", sub: "Generar desde texto, editar o quitar el fondo" },
    musica: { t: "Música", sub: "Pistas instrumentales o canciones con letra" },
    biblioteca: { t: "Biblioteca", sub: "Todo lo que has creado, en un sitio" },
  };

  let info = $derived(titulos[$modo]);
  // La cabecera también aparece con un lote vivo y la cola momentáneamente
  // vacía: eso es lo que pasa cuando todos sus vídeos están esperando revisión,
  // y es justo cuando hay que poder verlo y pararlo.
  let hayQueContar = $derived($jobs.length > 0 || $lotes.length > 0);
</script>

<section class="flex min-w-0 flex-1 flex-col overflow-hidden">
  <header class="flex items-center justify-between gap-4 border-b border-line px-7 py-4">
    <div class="min-w-0">
      <h1 class="text-lg font-semibold tracking-tight">{info.t}</h1>
      <p class="truncate text-sm text-dim">{info.sub}</p>
    </div>
    {#if hayQueContar}
      <div class="flex shrink-0 items-center gap-2">
        <ColaPanel />
        <BotonParar />
      </div>
    {/if}
  </header>

  {#if $modo === "videos"}
    <VideoStudio />
  {:else if $modo === "imagenes"}
    <ImageStudio />
  {:else if $modo === "musica"}
    <MusicStudio />
  {:else}
    <LibraryStudio />
  {/if}
</section>
