<script lang="ts">
  // Área de trabajo: cabecera compartida + el estudio del modo activo. Los
  // modos ya portados llenan el cuerpo a sangre; los pendientes muestran un
  // placeholder.
  import { modo, jobs } from "@/lib/stores";
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

  // La cola procesa de uno en uno, así que el único job con progreso es el que
  // está corriendo ahora.
  let prog = $derived($jobs.find((j) => j.progreso)?.progreso ?? null);

  function reloj(s: number): string {
    if (s < 60) return `${s}s`;
    const m = Math.round(s / 60);
    return m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${m % 60} min`;
  }

  // Lo que se lee en el chip: la posición dentro del lote y lo que queda. Si la
  // etapa no va por lotes (voz, guion, armado) no hay nada que contar y se
  // enseña el tiempo que lleva, que al menos distingue "va lento" de "se colgó".
  let texto = $derived.by(() => {
    const cola = `${$jobs.length} en cola`;
    const partes = [prog?.fase || cola];
    if (prog?.eta_s != null) partes.push(`~${reloj(prog.eta_s)}`);
    else if (prog) partes.push(reloj(prog.transcurrido_s));
    // El recuento solo se repite si la fase le quitó el sitio y además hay
    // más de un trabajo esperando.
    if (prog?.fase && $jobs.length > 1) partes.push(cola);
    return partes.join(" · ");
  });
</script>

<section class="flex min-w-0 flex-1 flex-col overflow-hidden">
  <header class="flex items-center justify-between gap-4 border-b border-line px-7 py-4">
    <div class="min-w-0">
      <h1 class="text-lg font-semibold tracking-tight">{info.t}</h1>
      <p class="truncate text-sm text-dim">{info.sub}</p>
    </div>
    {#if $jobs.length}
      <!-- El propio chip es la barra: se rellena por detrás del texto, así el
           avance y lo que se está haciendo ocupan un solo elemento. -->
      <span
        class="relative inline-flex shrink-0 items-center gap-2 overflow-hidden rounded-full bg-accent-soft px-3 py-1.5 text-xs font-medium text-accent"
        title="Trabajos en cola (se procesan de uno en uno)"
        {...prog?.pct != null
          ? {
              role: "progressbar",
              "aria-valuenow": prog.pct,
              "aria-valuemin": 0,
              "aria-valuemax": 100,
            }
          : {}}
      >
        {#if prog?.pct != null}
          <span
            class="absolute inset-y-0 left-0 bg-accent/30 transition-[width] duration-700 ease-out"
            style="width: {prog.pct}%"
            aria-hidden="true"
          ></span>
        {/if}
        <span class="relative size-1.5 animate-pulse rounded-full bg-accent"></span>
        <span class="relative">{texto}</span>
      </span>
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
