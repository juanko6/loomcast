<script lang="ts">
  // Galería de estilos: una tarjeta por estilo con sus ejemplos, para elegir a
  // ojo cómo se va a dibujar. «Libre» deja que el LLM elija el estilo.
  import { onMount } from "svelte";
  import { media } from "@/lib/api";
  import { rutaEjemploEstilo, type EstiloImagen } from "@/lib/galeria";

  let {
    estilos,
    value,
    onpick,
    onclose,
  }: {
    estilos: EstiloImagen[];
    value: string;
    onpick: (id: string) => void;
    onclose: () => void;
  } = $props();

  // Tres ejemplos bastan para reconocer un estilo sin llenar la tarjeta.
  const MAX_EJEMPLOS = 3;

  function teclas(e: KeyboardEvent) {
    if (e.key === "Escape") onclose();
  }

  let dialogo: HTMLDivElement;
  onMount(() => dialogo?.focus());
</script>

<svelte:window onkeydown={teclas} />

<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-6" onclick={onclose}>
  <div
    bind:this={dialogo}
    role="dialog"
    aria-modal="true"
    aria-label="Elegir estilo"
    tabindex="-1"
    class="flex max-h-full w-full max-w-5xl flex-col overflow-hidden rounded-xl border border-line bg-surface outline-none"
    onclick={(e) => e.stopPropagation()}
  >
    <header class="flex items-center justify-between border-b border-line px-5 py-4">
      <div>
        <h2 class="text-sm font-semibold">Elige un estilo</h2>
        <p class="text-xs text-dim">El estilo decide cómo se dibuja; qué se dibuja lo dicen tu título y tus detalles.</p>
      </div>
      <button type="button" class="text-sm text-dim hover:text-text" onclick={onclose}>Cerrar</button>
    </header>

    <div class="grid min-h-0 grid-cols-1 gap-3 overflow-y-auto p-5 sm:grid-cols-2 lg:grid-cols-3">
      <button
        type="button"
        aria-pressed={value === ""}
        onclick={() => onpick("")}
        class={`flex flex-col gap-2 rounded-lg border-2 p-3 text-left transition
          ${value === "" ? "border-accent" : "border-line hover:border-dim"}`}
      >
        <div class="flex aspect-[16/9] items-center justify-center rounded-md bg-surface-2 text-xs text-muted">
          El LLM elige
        </div>
        <span class="text-sm font-medium">Libre</span>
        <span class="text-xs text-dim">Sin estilo fijo: el LLM escribe el prompt entero a partir del título.</span>
      </button>

      {#each estilos as e (e.id)}
        <button
          type="button"
          aria-pressed={value === e.id}
          onclick={() => onpick(e.id)}
          class={`flex flex-col gap-2 rounded-lg border-2 p-3 text-left transition
            ${value === e.id ? "border-accent" : "border-line hover:border-dim"}`}
        >
          {#if e.ejemplos > 0}
            {@const n = Math.min(e.ejemplos, MAX_EJEMPLOS)}
            <div
              class="grid aspect-[16/9] gap-1 overflow-hidden rounded-md"
              style={`grid-template-columns: repeat(${n}, minmax(0, 1fr))`}
            >
              {#each Array.from({ length: n }, (_, i) => i) as i (i)}
                <img
                  src={media(rutaEjemploEstilo(e.id, i))}
                  alt={`${e.nombre}, ejemplo ${i + 1}`}
                  loading="lazy"
                  class="h-full w-full object-cover"
                />
              {/each}
            </div>
          {:else}
            <div class="flex aspect-[16/9] items-center justify-center rounded-md bg-surface-2 text-xs text-muted">
              Sin ejemplos todavía
            </div>
          {/if}
          <span class="text-sm font-medium">{e.nombre}</span>
          <span class="text-xs text-dim">{e.descripcion}</span>
        </button>
      {/each}
    </div>
  </div>
</div>
