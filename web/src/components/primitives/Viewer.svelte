<script lang="ts">
  // Visor a pantalla completa para ver una imagen o un clip en grande.
  // El contenido llega como HTML ya construido por quien lo abre.
  let {
    html = null,
    pie = "",
    onclose,
  }: { html?: string | null; pie?: string; onclose: () => void } = $props();

  function onkeydown(e: KeyboardEvent) {
    if (e.key === "Escape") onclose();
  }
</script>

<svelte:window on:keydown={onkeydown} />

{#if html}
  <!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
  <div
    class="fixed inset-0 z-50 flex flex-col items-center justify-center gap-3 bg-black/88 p-6"
    onclick={onclose}
  >
    <button
      type="button"
      onclick={onclose}
      aria-label="Cerrar (Esc)"
      class="absolute top-4 right-5 rounded-md bg-surface px-3 py-1.5 text-sm text-text transition hover:bg-surface-3"
    >
      ✕
    </button>
    <!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
    <div class="viewer-media max-h-[82vh] max-w-[min(92vw,520px)]" onclick={(e) => e.stopPropagation()}>
      {@html html}
    </div>
    {#if pie}<p class="text-center text-sm text-dim">{pie}</p>{/if}
  </div>
{/if}

<style>
  .viewer-media :global(img),
  .viewer-media :global(video) {
    display: block;
    max-width: 100%;
    max-height: 82vh;
    border-radius: 10px;
  }
</style>
