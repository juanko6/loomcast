<script lang="ts">
  import Icon from "./Icon.svelte";

  // Un texto listo para pegar en otro sitio, con su botón de copiar. El texto
  // va en un <textarea readonly> y no en un <p>: así se selecciona con el
  // teclado, se puede copiar a mano si el portapapeles del navegador no está
  // disponible, y lo que se ve es exactamente lo que se copia.
  let {
    label,
    text,
    hint = "",
    rows = 2,
  }: { label: string; text: string; hint?: string; rows?: number } = $props();

  let campo = $state<HTMLTextAreaElement | null>(null);
  let copiado = $state(false);
  let temporizador: ReturnType<typeof setTimeout> | undefined;

  async function copiar() {
    let hecho = false;
    try {
      await navigator.clipboard.writeText(text);
      hecho = true;
    } catch {
      // El portapapeles moderno pide permiso y no siempre lo hay (un webview,
      // un navegador con el permiso denegado). El camino viejo no lo pide:
      // copia lo que esté seleccionado.
      campo?.select();
      try {
        hecho = document.execCommand("copy");
      } catch {
        hecho = false;
      }
    }
    // Si tampoco se pudo, el texto se queda seleccionado y no se dice que se
    // copió: lo que no pasó no se anuncia.
    if (!hecho) return;
    copiado = true;
    clearTimeout(temporizador);
    temporizador = setTimeout(() => (copiado = false), 1600);
  }
</script>

<div class="space-y-1">
  <div class="flex items-center gap-2">
    <span class="text-xs font-medium tracking-wide text-dim">{label}</span>
    <button
      type="button"
      onclick={copiar}
      aria-label={`Copiar ${label.toLowerCase()}`}
      title={`Copiar ${label.toLowerCase()}`}
      class={`ml-auto inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs transition-colors
        ${copiado ? "text-ok" : "text-dim hover:bg-surface-3 hover:text-text"}`}
    >
      <Icon name={copiado ? "check" : "copy"} size={14} />
      {copiado ? "Copiado" : "Copiar"}
    </button>
  </div>
  <textarea
    bind:this={campo}
    class="control font-sans text-sm"
    {rows}
    readonly
    aria-label={label}
    value={text}
  ></textarea>
  {#if hint}
    <p class="text-xs text-muted">{hint}</p>
  {/if}
</div>
