<script lang="ts">
  import Icon from "./Icon.svelte";
  import type { IconName } from "@/lib/icons";

  // Miniatura cuadrada. Hoy muestra un placeholder con icono; cuando exista la
  // feature de portada IA, se le pasará `src`. Si se pasa `onplay`, se vuelve un
  // botón con overlay de play/pause (patrón Mureka).
  let {
    src = null,
    alt = "",
    icon = "music" as IconName,
    size = 48,
    playing = false,
    onplay,
  }: {
    src?: string | null;
    alt?: string;
    icon?: IconName;
    size?: number;
    playing?: boolean;
    onplay?: () => void;
  } = $props();
</script>

{#if onplay}
  <button
    type="button"
    onclick={onplay}
    aria-label={playing ? "Pausar" : "Reproducir"}
    style={`width:${size}px;height:${size}px`}
    class="group/thumb relative shrink-0 overflow-hidden rounded-lg bg-surface-3"
  >
    {#if src}
      <img {src} {alt} class="size-full object-cover" />
    {:else}
      <span class="grid size-full place-items-center text-muted">
        <Icon {icon} size={Math.round(size * 0.42)} />
      </span>
    {/if}
    <!-- Overlay de play/pause: siempre visible si suena, al hover si no -->
    <span
      class={`absolute inset-0 grid place-items-center bg-black/45 text-white transition-opacity
        ${playing ? "opacity-100" : "opacity-0 group-hover/thumb:opacity-100"}`}
    >
      <Icon name={playing ? "pause" : "play"} size={Math.round(size * 0.34)} />
    </span>
  </button>
{:else}
  <span
    style={`width:${size}px;height:${size}px`}
    class="grid shrink-0 place-items-center overflow-hidden rounded-lg bg-surface-3 text-muted"
  >
    {#if src}
      <img {src} {alt} class="size-full object-cover" />
    {:else}
      <Icon {icon} size={Math.round(size * 0.42)} />
    {/if}
  </span>
{/if}
