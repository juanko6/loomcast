<script lang="ts">
  import Button from "../primitives/Button.svelte";
  import Chip from "../primitives/Chip.svelte";
  import type { Idea } from "@/lib/proyectos";

  let {
    ideas,
    busy = false,
    onaprobar,
    ondescartar,
    onrestaurar,
    onabrirproyecto,
    onmas,
  }: {
    ideas: Idea[];
    busy?: boolean;
    onaprobar: (id: number) => void;
    ondescartar: (id: number) => void;
    onrestaurar: (id: number) => void;
    onabrirproyecto: (pid: number) => void;
    onmas: () => void;
  } = $props();
</script>

{#if !ideas.length}
  <p class="text-sm text-dim">Generando ideas con el LLM… aparecerán aquí.</p>
{:else}
  <div class="space-y-3">
    <p class="text-sm text-dim">Aprueba las buenas y descarta el resto.</p>

    <div class="grid gap-3 lg:grid-cols-2">
      {#each ideas as i (i.id)}
        <article
          class={`space-y-2 rounded-xl border bg-surface-2 p-4 transition-opacity
            ${i.estado === "aprobada" ? "border-ok/40" : "border-line"}
            ${i.estado === "descartada" ? "opacity-45" : ""}`}
        >
          <h3 class="text-base font-semibold text-balance">{i.titulo}</h3>
          <p class="text-sm text-accent italic">“{i.gancho}”</p>
          <p class="text-sm text-dim">{i.resumen}</p>
          <div class="flex flex-wrap gap-2 pt-1">
            {#if i.proyecto_id}
              <Chip tone="ok">proyecto creado</Chip>
              <Button size="sm" onclick={() => onabrirproyecto(i.proyecto_id!)}>Ver proyecto →</Button>
            {:else}
              <Button size="sm" disabled={busy} onclick={() => onaprobar(i.id)}>
                Aprobar y crear proyecto
              </Button>
              {#if i.estado !== "descartada"}
                <Button size="sm" variant="ghost" onclick={() => ondescartar(i.id)}>Descartar</Button>
              {:else}
                <Button size="sm" variant="secondary" onclick={() => onrestaurar(i.id)}>Restaurar</Button>
              {/if}
            {/if}
          </div>
        </article>
      {/each}
    </div>

    <Button variant="secondary" size="sm" disabled={busy} onclick={onmas}>
      Generar más ideas
    </Button>
  </div>
{/if}
