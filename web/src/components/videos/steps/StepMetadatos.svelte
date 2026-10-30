<script lang="ts">
  import Button from "../../primitives/Button.svelte";
  import MetadatosRedes from "../MetadatosRedes.svelte";
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
    <MetadatosRedes {m} />
  {/if}
</div>
