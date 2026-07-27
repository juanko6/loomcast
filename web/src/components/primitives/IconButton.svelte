<script lang="ts">
  import Icon from "./Icon.svelte";
  import type { IconName } from "@/lib/icons";

  // Botón de icono cuadrado. `active` lo tiñe con el acento (p. ej. like dado).
  // `soon` lo marca como funcionalidad futura (tooltip + estilo tenue).
  let {
    name,
    label,
    size = 18,
    active = false,
    soon = false,
    disabled = false,
    onclick,
    class: extra = "",
  }: {
    name: IconName;
    label: string;
    size?: number;
    active?: boolean;
    soon?: boolean;
    disabled?: boolean;
    onclick?: (e: MouseEvent) => void;
    class?: string;
  } = $props();
</script>

<button
  type="button"
  title={soon ? `${label} · Próximamente` : label}
  aria-label={label}
  {disabled}
  onclick={onclick}
  class={`inline-grid place-items-center rounded-md p-2 transition-colors
    ${active ? "text-accent" : "text-dim hover:bg-surface-3 hover:text-text"}
    ${soon ? "opacity-55" : ""} disabled:cursor-default disabled:opacity-40 ${extra}`}
>
  <Icon {name} {size} />
</button>
