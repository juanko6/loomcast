<script lang="ts">
  import Field from "../../primitives/Field.svelte";
  import Button from "../../primitives/Button.svelte";
  import type { ProyectoDetalle, Guion } from "@/lib/proyectos";

  let {
    p,
    busy = false,
    onsave,
    onregen,
  }: {
    p: ProyectoDetalle;
    busy?: boolean;
    onsave: (g: Guion) => void;
    onregen: () => void;
  } = $props();

  // Borrador local del guion, re-sincronizado cuando cambia el proyecto o el
  // LLM lo reescribe.
  let gancho = $state("");
  let narracion = $state("");
  let cta = $state("");
  let frases = $state<string[]>([]);

  // Dos formatos de guion según la plantilla: narración continua (drama) o
  // lista de frases (curiosidades).
  const esNarracion = $derived(p.guion?.narracion != null);

  $effect(() => {
    const g = p.guion;
    gancho = g?.gancho ?? "";
    narracion = g?.narracion ?? "";
    cta = g?.cta ?? "";
    frases = [...(g?.frases ?? [])];
  });

  function guardar() {
    onsave(
      esNarracion
        ? { gancho, narracion, cta }
        : { gancho, frases: frases.map((f) => f.trim()).filter(Boolean), cta },
    );
  }
</script>

{#if !p.guion}
  <p class="text-sm text-dim">Escribiendo el guion con el LLM…</p>
{:else}
  <div class="max-w-3xl space-y-4">
    <Field label="Gancho">
      <input class="control" bind:value={gancho} />
    </Field>

    {#if esNarracion}
      <Field label="Narración">
        <textarea class="control" rows="12" bind:value={narracion}></textarea>
      </Field>
    {:else}
      <Field label="Frases">
        <div class="space-y-2">
          {#each frases as _, i (i)}
            <div class="flex gap-2">
              <input class="control" bind:value={frases[i]} />
              <Button
                variant="ghost"
                size="sm"
                title="Quitar frase"
                onclick={() => (frases = frases.filter((_, j) => j !== i))}
              >
                ✕
              </Button>
            </div>
          {/each}
        </div>
      </Field>
      <Button variant="secondary" size="sm" onclick={() => (frases = [...frases, ""])}>
        + Añadir frase
      </Button>
    {/if}

    <Field label="CTA (cierre)">
      <input class="control" bind:value={cta} />
    </Field>

    <div class="flex flex-wrap gap-2 pt-1">
      <Button onclick={guardar}>Guardar guion</Button>
      <Button variant="secondary" disabled={busy} onclick={onregen}>
        Regenerar con el LLM
      </Button>
      <span class="self-center text-xs text-muted">Versión {p.guion_version}</span>
    </div>
  </div>
{/if}
