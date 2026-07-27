<script lang="ts">
  import Button from "../../primitives/Button.svelte";
  import Chip from "../../primitives/Chip.svelte";
  import type { ProyectoDetalle } from "@/lib/proyectos";

  let {
    p,
    busy = false,
    ongenerar,
  }: { p: ProyectoDetalle; busy?: boolean; ongenerar: () => void } = $props();

  const m = $derived(p.metadatos);
</script>

<div class="max-w-3xl space-y-4">
  <Button disabled={busy} onclick={ongenerar}>
    {m ? "Regenerar metadatos" : "Generar título, descripción y etiquetas"}
  </Button>

  {#if !m}
    <p class="text-sm text-dim">
      Genera los metadatos cuando la narración esté lista: el LLM los escribe a partir del guion.
    </p>
  {:else}
    <section class="space-y-2 rounded-xl border border-line bg-surface-2 p-4">
      <h3 class="text-sm font-semibold">YouTube</h3>
      <p class="font-medium">{m.youtube.titulo}</p>
      <pre class="whitespace-pre-wrap font-sans text-sm leading-relaxed text-dim">{m.youtube.descripcion}</pre>
      <div class="flex flex-wrap gap-1.5 pt-1">
        {#each m.youtube.etiquetas as e (e)}
          <Chip>{e}</Chip>
        {/each}
      </div>
    </section>

    <section class="space-y-2 rounded-xl border border-line bg-surface-2 p-4">
      <h3 class="text-sm font-semibold">TikTok</h3>
      <pre class="whitespace-pre-wrap font-sans text-sm leading-relaxed text-dim">{m.tiktok.descripcion}</pre>
    </section>
  {/if}
</div>
