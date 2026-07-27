<script lang="ts">
  // Navegación por pasos del pipeline. Sustituye el muro vertical del front
  // antiguo: solo se ve el paso activo, y el estado de cada paso (hecho /
  // disponible / bloqueado) se lee de un vistazo.
  import type { Paso } from "@/lib/proyectos";

  let {
    pasos,
    activo,
    onselect,
  }: { pasos: Paso[]; activo: string; onselect: (id: string) => void } = $props();
</script>

<nav class="flex items-center gap-1 overflow-x-auto border-b border-line px-6 py-3" aria-label="Pasos del proyecto">
  {#each pasos as p, i (p.id)}
    {#if i > 0}
      <span class="h-px w-4 shrink-0 bg-line" aria-hidden="true"></span>
    {/if}
    <button
      type="button"
      disabled={p.bloqueado}
      aria-current={activo === p.id ? "step" : undefined}
      onclick={() => onselect(p.id)}
      title={p.bloqueado ? "Completa los pasos anteriores" : p.label}
      class={`flex shrink-0 items-center gap-2 rounded-lg px-3 py-1.5 text-sm transition-colors
        ${activo === p.id
          ? "bg-accent-soft text-text"
          : p.bloqueado
            ? "cursor-default text-muted opacity-55"
            : "text-dim hover:bg-surface-2 hover:text-text"}`}
    >
      <span
        class={`grid size-5 shrink-0 place-items-center rounded-full text-[11px] font-semibold
          ${p.hecho
            ? "bg-ok text-bg"
            : activo === p.id
              ? "bg-accent text-on-accent"
              : "bg-surface-3 text-dim"}`}
      >
        {#if p.hecho}✓{:else}{i + 1}{/if}
      </span>
      <span class="font-medium whitespace-nowrap">{p.label}</span>
    </button>
  {/each}
</nav>
