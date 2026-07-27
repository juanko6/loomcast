<script lang="ts">
  // Estado del sistema en el pie del rail: semáforo LLM, semáforo ComfyUI y
  // selector de modelo de texto. Se apoya en los stores globales.
  import StatusDot from "../primitives/StatusDot.svelte";
  import { salud, modelos, modeloActivo, cambiarModelo } from "@/lib/stores";
  import type { LlmEstado } from "@/lib/types";

  const LLM: Record<LlmEstado, { estado: "on" | "off" | "espera"; detalle: string }> = {
    activo: { estado: "on", detalle: "levantado por ti, fuera de Loomcast" },
    cargado: { estado: "on", detalle: "cargado en memoria" },
    en_espera: { estado: "espera", detalle: "descargado; se carga solo al generar texto" },
    caido: { estado: "off", detalle: "no responde en su url" },
  };

  let llm = $derived($salud ? LLM[$salud.llm_estado.estado] : null);
</script>

<div class="flex flex-col gap-2">
  {#if $modelos.length > 1}
    <select
      class="w-full rounded-md border border-line bg-surface-2 px-2.5 py-1.5 text-xs text-dim
             hover:text-text focus:outline-none"
      value={$modeloActivo}
      title="Modelo de texto"
      onchange={(e) => cambiarModelo((e.currentTarget as HTMLSelectElement).value)}
    >
      {#each $modelos as m (m.id)}
        <option value={m.id}>{m.nombre}</option>
      {/each}
    </select>
  {/if}

  <div class="flex flex-wrap gap-1.5">
    <StatusDot
      estado={llm?.estado ?? "off"}
      label="LLM"
      title={$salud ? `${$salud.llm_estado.nombre} — ${llm?.detalle}` : "llama-server"}
    />
    <StatusDot
      estado={$salud?.comfy ? "on" : "off"}
      label="Comfy"
      title="ComfyUI"
    />
  </div>
</div>
