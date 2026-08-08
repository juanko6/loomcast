<script lang="ts">
  import Chip from "../primitives/Chip.svelte";
  import Button from "../primitives/Button.svelte";
  import Icon from "../primitives/Icon.svelte";
  import { media } from "@/lib/api";
  import type { GaleriaDetalle } from "@/lib/galeria";

  let {
    detail,
    busy = false,
    previewSel = null,
    verGrid = false,
    bust = 0,
    onpreviews,
    onmejorar,
    onpick,
    onfinal,
    onreelegir,
  }: {
    detail: GaleriaDetalle | null;
    busy?: boolean;
    previewSel?: number | null;
    verGrid?: boolean;
    bust?: number;
    onpreviews: (prompt: string) => void;
    onmejorar: () => void;
    onpick: (i: number) => void;
    onfinal: () => void;
    onreelegir: () => void;
  } = $props();

  // Borrador local del prompt, re-sincronizado al cambiar de imagen o cuando el
  // LLM lo reescribe (el padre refresca `detail`).
  let prompt = $state("");
  $effect(() => {
    prompt = detail?.prompt ?? "";
  });

  const esFondo = $derived(detail?.tipo === "quitarfondo");
  const tieneOrigen = $derived(detail?.tipo === "editar" || detail?.tipo === "quitarfondo");
  const mostrarGrid = $derived(
    !!detail && detail.seeds.length > 0 && (detail.estado === "previews" || (detail.estado === "final" && verGrid)),
  );
  const mostrarFinal = $derived(!!detail && detail.estado === "final" && !verGrid);
</script>

<aside class="flex h-full w-[420px] min-w-0 shrink-0 flex-col border-l border-line bg-surface">
  <header class="flex items-center gap-2 border-b border-line px-5 py-4">
    <h2 class="text-sm font-semibold">Trabajo</h2>
    {#if detail && !esFondo && detail.motor_nombre}
      <span class="ml-auto rounded-full border border-line px-2 py-0.5 text-xs text-dim">
        {detail.motor_nombre}
      </span>
    {/if}
  </header>

  <div class="min-h-0 flex-1 space-y-4 overflow-y-auto p-5">
    {#if !detail}
      <p class="mt-10 text-center text-sm text-dim">
        Selecciona una imagen o crea una nueva para empezar.
      </p>
    {:else}
      {#if busy}
        <div class="flex items-center gap-3 rounded-lg border border-line bg-surface-2 px-4 py-3 text-dim">
          <span class="size-5 shrink-0 animate-spin rounded-full border-2 border-line border-t-accent"></span>
          <p class="text-sm">{esFondo ? "Quitando el fondo…" : "Trabajando… (un job en curso)"}</p>
        </div>
      {/if}

      {#if tieneOrigen}
        <div class="space-y-1.5">
          <p class="text-xs font-medium tracking-wide text-muted">Imagen de origen</p>
          <img src={media(`/galeria/${detail.id}/fuente`)} alt="origen" class="max-h-48 rounded-lg" />
        </div>
      {/if}

      {#if esFondo}
        {#if detail.estado === "final"}
          <div class="space-y-2">
            <p class="text-xs font-medium tracking-wide text-muted">Resultado (fondo transparente)</p>
            <div class="checker overflow-hidden rounded-lg">
              <img src={`${media(`/galeria/${detail.id}/final`)}?v=${bust}`} alt="resultado" class="block max-w-full" />
            </div>
            <a
              href={media(`/galeria/${detail.id}/final`)}
              download={`loomcast_${detail.id}.png`}
              class="inline-flex items-center gap-2 rounded-md border border-line bg-surface-2 px-3 py-2 text-sm text-text transition hover:border-accent"
            >
              <Icon name="download" size={16} /> Descargar PNG
            </a>
          </div>
        {/if}
      {:else}
        <!-- generar / editar: prompt (mejorar es opcional) -> previews -> final -->
        <div class="space-y-2">
          <p class="text-xs font-medium tracking-wide text-muted">Prompt (inglés, editable)</p>
          <textarea
            class="control"
            rows="4"
            bind:value={prompt}
            placeholder="Escribe el prompt en inglés, o pulsa «Mejorar prompt con el LLM»."
          ></textarea>
          <div class="flex flex-wrap items-center gap-2">
            <Button size="sm" variant="secondary" disabled={busy} onclick={onmejorar}>
              Mejorar prompt con el LLM
            </Button>
            <Button size="sm" disabled={busy || !prompt.trim()} onclick={() => onpreviews(prompt)}>
              {detail.seeds.length ? "Regenerar 4 previews" : "Generar 4 previews"}
            </Button>
            {#if detail.tipo === "generar"}
              <span class="text-xs text-muted">{detail.width}×{detail.height}</span>
            {/if}
          </div>
        </div>

        {#if mostrarGrid}
          <div class="space-y-2">
            <p class="text-xs font-medium tracking-wide text-muted">Elige la mejor (se ampliará a máxima resolución)</p>
            <div class="grid grid-cols-2 gap-2">
              {#each detail.seeds as _, i (i)}
                <button
                  type="button"
                  onclick={() => onpick(i)}
                  class={`overflow-hidden rounded-lg border-2 transition
                    ${previewSel === i ? "border-accent" : "border-line hover:border-dim"}`}
                >
                  <img
                    src={`${media(`/galeria/${detail.id}/preview/${i}`)}?v=${bust}`}
                    alt={`preview ${i + 1}`}
                    class="aspect-square w-full object-cover"
                  />
                </button>
              {/each}
            </div>
            <Button disabled={previewSel === null || busy} onclick={onfinal}>
              Generar máxima resolución
            </Button>
          </div>
        {/if}

        {#if mostrarFinal}
          <div class="space-y-2">
            <p class="text-xs font-medium tracking-wide text-muted">Imagen final</p>
            <img src={`${media(`/galeria/${detail.id}/final`)}?v=${bust}`} alt="final" class="max-w-full rounded-lg" />
            <div class="flex items-center gap-2">
              <a
                href={media(`/galeria/${detail.id}/final`)}
                download={`loomcast_${detail.id}.png`}
                class="inline-flex items-center gap-2 rounded-md border border-line bg-surface-2 px-3 py-2 text-sm text-text transition hover:border-accent"
              >
                <Icon name="download" size={16} /> Descargar PNG
              </a>
              <Button size="sm" variant="secondary" onclick={onreelegir}>Elegir otra preview</Button>
            </div>
          </div>
        {/if}
      {/if}
    {/if}
  </div>
</aside>
