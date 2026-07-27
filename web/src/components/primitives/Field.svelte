<script lang="ts">
  import type { Snippet } from "svelte";
  // Envoltorio label + control + ayuda opcional. El <label> envuelve al control
  // (asociación implícita) para dar foco al hacer clic en la etiqueta y cumplir
  // accesibilidad. Da ritmo vertical consistente a los formularios.
  let {
    label,
    hint,
    children,
  }: { label?: string; hint?: string; children: Snippet } = $props();
</script>

<label class="flex flex-col gap-1.5">
  {#if label}
    <span class="text-xs font-medium tracking-wide text-dim">{label}</span>
  {/if}
  {@render children()}
  {#if hint}
    <span class="text-xs text-muted">{hint}</span>
  {/if}
</label>
