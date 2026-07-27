<script lang="ts">
  // Rail izquierdo persistente: marca + navegación entre los modos del estudio
  // + estado del sistema al pie. Es el nivel superior de navegación (IA nueva:
  // Loomcast pasa de "app de storytelling" a "estudio multimedia").
  import SystemStatus from "./SystemStatus.svelte";
  import { modo } from "@/lib/stores";
  import type { StudioMode } from "@/lib/types";

  const items: { id: StudioMode; label: string; icon: string; desc: string }[] = [
    { id: "videos", label: "Vídeos", icon: "clapper", desc: "Del tema al vídeo final" },
    { id: "imagenes", label: "Imágenes", icon: "image", desc: "Generar, editar, fondo" },
    { id: "musica", label: "Música", icon: "music", desc: "Instrumental o canción" },
    { id: "biblioteca", label: "Biblioteca", icon: "library", desc: "Todo lo creado" },
  ];

  // Iconos SVG inline (stroke) — sin dependencias, coherentes de grosor.
  const paths: Record<string, string> = {
    clapper:
      "M3 8h18M3 8l1.5-4h15L21 8M3 8v11a1 1 0 0 0 1 1h16a1 1 0 0 0 1-1V8M7 4l-1 4M12 4l-1 4M17 4l-1 4",
    image:
      "M4 5h16a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1ZM3 16l5-5 4 4 3-3 6 6M9 10a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3Z",
    music: "M9 18V6l11-2v12M9 18a3 3 0 1 1-6 0 3 3 0 0 1 6 0Zm11-2a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z",
    library: "M4 5h4v14H4zM10 5h4v14h-4zM17 5.5l3.5 1-3 12.5-3.5-1z",
  };
</script>

<nav
  class="flex h-full w-[248px] shrink-0 flex-col border-r border-line bg-surface px-3 py-4"
  aria-label="Navegación del estudio"
>
  <!-- Marca -->
  <div class="flex items-center gap-2.5 px-2 pb-5">
    <span class="grid size-8 place-items-center rounded-lg bg-accent-soft text-accent">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"
           stroke-linecap="round" stroke-linejoin="round" class="size-5">
        <path d={paths.clapper} />
      </svg>
    </span>
    <span class="text-[17px] font-semibold tracking-tight">Loomcast</span>
  </div>

  <!-- Modos principales -->
  <ul class="flex flex-col gap-1">
    {#each items as it (it.id)}
      <li>
        <button
          type="button"
          aria-current={$modo === it.id ? "page" : undefined}
          onclick={() => modo.set(it.id)}
          class={`group flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left transition-colors
            ${$modo === it.id
              ? "bg-accent-soft text-text"
              : "text-dim hover:bg-surface-2 hover:text-text"}`}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"
               stroke-linecap="round" stroke-linejoin="round"
               class={`size-5 shrink-0 ${$modo === it.id ? "text-accent" : ""}`}>
            <path d={paths[it.icon]} />
          </svg>
          <span class="flex flex-col leading-tight">
            <span class="text-sm font-medium">{it.label}</span>
            <span class="text-xs text-muted">{it.desc}</span>
          </span>
        </button>
      </li>
    {/each}
  </ul>

  <div class="mt-auto pt-4">
    <div class="mb-3 border-t border-line-soft"></div>
    <SystemStatus />
  </div>
</nav>
