<script lang="ts">
  import Button from "../primitives/Button.svelte";
  import Chip from "../primitives/Chip.svelte";
  import AutopilotoForm from "./AutopilotoForm.svelte";
  import type { Idea, Voz } from "@/lib/proyectos";
  import type { OpcionesAutopiloto } from "@/lib/autopiloto";

  let {
    ideas,
    voces = [],
    busy = false,
    onaprobar,
    ondescartar,
    onrestaurar,
    onabrirproyecto,
    onmas,
    onlote,
  }: {
    ideas: Idea[];
    voces?: Voz[];
    busy?: boolean;
    onaprobar: (id: number) => void;
    ondescartar: (id: number) => void;
    onrestaurar: (id: number) => void;
    onabrirproyecto: (pid: number) => void;
    onmas: () => void;
    // Produce de una tirada todas las ideas de este tema. Si no se pasa, el
    // bloque del lote no aparece (la vista se usa también sin él).
    onlote?: (o: OpcionesAutopiloto) => void;
  } = $props();

  const aprobadas = $derived(ideas.filter((i) => i.estado === "aprobada").length);
  const sinProyecto = $derived(ideas.filter((i) => !i.proyecto_id).length);
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

    <!-- El lote va al pie y detrás de un desplegable: la decisión normal es
         aprobar una idea y trabajarla, y producir ocho de golpe es la que se
         toma cuando la plantilla ya está afinada. -->
    {#if onlote}
      <details class="rounded-xl border border-line bg-surface-2 p-3">
        <summary class="cursor-pointer text-sm font-semibold">
          Producir en lote ({aprobadas}
          {aprobadas === 1 ? "idea aprobada" : "ideas aprobadas"})
        </summary>
        <div class="mt-3 space-y-3">
          <p class="text-xs text-dim">
            Un proyecto por idea, cada uno en automático y encolados uno detrás de otro:
            la cola es de un solo hilo porque las etapas se pelean por la GPU, así que se
            producen de uno en uno. Un vídeo que falle no tira los demás.
          </p>
          <AutopilotoForm
            {voces}
            {busy}
            etiqueta="Producir el lote"
            onlanzar={onlote}
          />
          {#if !sinProyecto}
            <p class="text-xs text-muted">
              Todas estas ideas ya tienen proyecto: el lote los retomará donde estén.
            </p>
          {/if}
        </div>
      </details>
    {/if}
  </div>
{/if}
