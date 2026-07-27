<script lang="ts">
  import type { Snippet } from "svelte";
  // Etiqueta compacta para estados/tipos. `tone` mapea a la semántica; por
  // defecto es neutra.
  type Tone = "neutral" | "accent" | "ok" | "warn" | "danger";
  let {
    tone = "neutral",
    children,
  }: { tone?: Tone; children: Snippet } = $props();

  const tones: Record<Tone, string> = {
    neutral: "bg-surface-3 text-dim",
    accent: "bg-accent-soft text-accent",
    ok: "bg-ok-soft text-ok",
    warn: "bg-warn-soft text-warn",
    danger: "bg-danger-soft text-danger",
  };
</script>

<span
  class={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${tones[tone]}`}
>
  {@render children()}
</span>
