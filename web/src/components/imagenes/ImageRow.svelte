<script lang="ts">
  import Chip from "../primitives/Chip.svelte";
  import Thumbnail from "../primitives/Thumbnail.svelte";
  import IconButton from "../primitives/IconButton.svelte";
  import { media } from "@/lib/api";
  import type { GaleriaResumen } from "@/lib/types";

  let {
    item,
    active = false,
    onselect,
    ondelete,
  }: {
    item: GaleriaResumen;
    active?: boolean;
    onselect: () => void;
    ondelete: () => void;
  } = $props();

  const TIPO: Record<string, string> = {
    generar: "Generar",
    editar: "Editar",
    quitarfondo: "Fondo",
  };

  // Miniatura: la final si ya está; si no, el origen (editar/fondo); si no, nada.
  const thumb = $derived(
    item.estado === "final"
      ? media(`/galeria/${item.id}/final`)
      : item.tipo === "editar" || item.tipo === "quitarfondo"
        ? media(`/galeria/${item.id}/fuente`)
        : null,
  );
</script>

<div
  class={`group relative flex items-center gap-3 rounded-lg border px-3 py-2.5 transition-colors
    ${active
      ? "border-accent/40 bg-accent-soft"
      : "border-line-soft bg-surface-2 hover:border-line hover:bg-surface-3"}`}
>
  <Thumbnail icon="image" size={48} src={thumb} alt={item.idea} />

  <button type="button" onclick={onselect} class="flex min-w-0 flex-1 flex-col items-start gap-1 text-left">
    <span class="w-full truncate text-sm font-medium text-text">
      {item.idea?.trim() || "(imagen)"}
    </span>
    <span class="flex items-center gap-1.5">
      <Chip tone="accent">{TIPO[item.tipo] ?? item.tipo}</Chip>
      <Chip>{item.estado}</Chip>
    </span>
  </button>

  <div class="shrink-0 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
    <IconButton
      name="x"
      label="Borrar imagen"
      size={16}
      onclick={ondelete}
      class="hover:bg-danger-soft hover:text-danger"
    />
  </div>
</div>
