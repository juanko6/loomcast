<script lang="ts">
  import type { Snippet } from "svelte";

  type Variant = "primary" | "secondary" | "ghost" | "danger";
  type Size = "sm" | "md";

  let {
    variant = "primary",
    size = "md",
    type = "button",
    disabled = false,
    title,
    onclick,
    children,
    class: extra = "",
  }: {
    variant?: Variant;
    size?: Size;
    type?: "button" | "submit" | "reset";
    disabled?: boolean;
    title?: string;
    onclick?: (e: MouseEvent) => void;
    children: Snippet;
    class?: string;
  } = $props();

  const base =
    "inline-flex items-center justify-center gap-2 font-medium rounded-md " +
    "transition-[filter,background-color,border-color] cursor-pointer select-none " +
    "disabled:opacity-45 disabled:cursor-default whitespace-nowrap";

  const variants: Record<Variant, string> = {
    primary: "bg-accent text-on-accent hover:bg-accent-hover",
    secondary: "bg-surface-3 text-text hover:brightness-115 border border-line",
    ghost: "bg-transparent text-dim hover:text-text hover:bg-surface-2",
    danger: "bg-danger-soft text-danger hover:brightness-115 border border-danger/30",
  };

  const sizes: Record<Size, string> = {
    sm: "text-xs px-2.5 py-1.5",
    md: "text-sm px-3.5 py-2",
  };
</script>

<button
  {type}
  {title}
  {disabled}
  {onclick}
  class={`${base} ${variants[variant]} ${sizes[size]} ${extra}`}
>
  {@render children()}
</button>
