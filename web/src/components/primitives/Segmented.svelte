<script lang="ts">
  // Conmutador segmentado (ej. Instrumental / Canción, o Generar / Editar).
  // Genérico sobre el tipo del valor.
  type Opt = { value: string; label: string; icon?: string };
  let {
    options,
    value,
    onchange,
  }: { options: Opt[]; value: string; onchange: (v: string) => void } = $props();
</script>

<div class="flex gap-1 rounded-lg bg-surface p-1" role="tablist">
  {#each options as opt (opt.value)}
    <button
      type="button"
      role="tab"
      aria-selected={value === opt.value}
      onclick={() => onchange(opt.value)}
      class={`flex flex-1 items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium
        transition-colors ${
          value === opt.value
            ? "bg-accent text-on-accent"
            : "text-dim hover:bg-surface-2 hover:text-text"
        }`}
    >
      {#if opt.icon}<span aria-hidden="true">{opt.icon}</span>{/if}
      {opt.label}
    </button>
  {/each}
</div>
