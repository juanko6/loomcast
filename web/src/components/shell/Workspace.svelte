<script lang="ts">
  // Área de trabajo: cabecera compartida + el estudio del modo activo. Los
  // modos ya portados llenan el cuerpo a sangre; los pendientes muestran un
  // placeholder.
  import { modo, jobs } from "@/lib/stores";
  import MusicStudio from "../musica/MusicStudio.svelte";
  import type { StudioMode } from "@/lib/types";

  const titulos: Record<StudioMode, { t: string; sub: string }> = {
    videos: { t: "Vídeos", sub: "Del tema a la idea, guion, voz, escenas y montaje final" },
    imagenes: { t: "Imágenes", sub: "Generar desde texto, editar o quitar el fondo" },
    musica: { t: "Música", sub: "Pistas instrumentales o canciones con letra" },
    biblioteca: { t: "Biblioteca", sub: "Todo lo que has creado, en un sitio" },
  };

  let info = $derived(titulos[$modo]);
  const portados: StudioMode[] = ["musica"];
</script>

<section class="flex min-w-0 flex-1 flex-col overflow-hidden">
  <header class="flex items-center justify-between gap-4 border-b border-line px-7 py-4">
    <div class="min-w-0">
      <h1 class="text-lg font-semibold tracking-tight">{info.t}</h1>
      <p class="truncate text-sm text-dim">{info.sub}</p>
    </div>
    {#if $jobs.length}
      <span
        class="inline-flex items-center gap-2 rounded-full bg-accent-soft px-3 py-1.5 text-xs font-medium text-accent"
        title="Trabajos en cola (se procesan de uno en uno)"
      >
        <span class="size-1.5 animate-pulse rounded-full bg-accent"></span>
        {$jobs.length} en cola
      </span>
    {/if}
  </header>

  {#if $modo === "musica"}
    <MusicStudio />
  {:else if portados.includes($modo)}
    <!-- reservado para futuros modos ya portados -->
  {:else}
    <div class="min-h-0 flex-1 overflow-y-auto px-7 py-6">
      <div class="grid h-full min-h-[60vh] place-items-center rounded-xl border border-dashed border-line text-center">
        <div class="max-w-sm px-6">
          <p class="text-sm text-dim">
            El modo <b class="text-text">{info.t}</b> se está portando a la nueva
            arquitectura. La estructura (rail, workspace, tokens) ya está viva.
          </p>
        </div>
      </div>
    </div>
  {/if}
</section>
