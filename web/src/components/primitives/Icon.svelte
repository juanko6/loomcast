<script lang="ts">
  import { icons, filledIcons, type IconName } from "@/lib/icons";
  let {
    name,
    size = 18,
    class: extra = "",
  }: { name: IconName; size?: number; class?: string } = $props();

  const filled = $derived(filledIcons.includes(name));
</script>

<svg
  viewBox="0 0 24 24"
  width={size}
  height={size}
  fill={filled ? "currentColor" : "none"}
  stroke={filled ? "none" : "currentColor"}
  stroke-width="1.7"
  stroke-linecap="round"
  stroke-linejoin="round"
  class={extra}
  aria-hidden="true"
>
  <path d={icons[name]} />
</svg>
