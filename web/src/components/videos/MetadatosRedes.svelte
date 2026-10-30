<script lang="ts">
  import CopyField from "../primitives/CopyField.svelte";
  import { etiquetasEnHashtags, etiquetasEnLinea } from "@/lib/metadatos";
  import type { Metadatos } from "@/lib/proyectos";

  // Los textos del vídeo en la forma en la que se pegan en cada red. Lo usan el
  // paso de Metadatos (donde se escriben) y el de Publicación (donde se suben),
  // que son dos momentos del mismo texto.
  let { m }: { m: Metadatos } = $props();

  const enLinea = $derived(etiquetasEnLinea(m.youtube.etiquetas));
  const enHashtags = $derived(etiquetasEnHashtags(m.youtube.etiquetas));
</script>

<section class="space-y-3 rounded-xl border border-line bg-surface-2 p-4">
  <h3 class="text-sm font-semibold">YouTube</h3>
  <CopyField
    label="Título"
    text={m.youtube.titulo}
    hint={`${m.youtube.titulo.length} caracteres`}
  />
  <CopyField label="Descripción" text={m.youtube.descripcion} rows={7} />
  <CopyField
    label="Etiquetas"
    text={enLinea}
    rows={3}
    hint="Separadas por comas, como las pide la caja de etiquetas de YouTube."
  />
  <CopyField
    label="Etiquetas como hashtags"
    text={enHashtags}
    rows={2}
    hint="Para pegarlas dentro del título o de la descripción."
  />
</section>

<section class="space-y-3 rounded-xl border border-line bg-surface-2 p-4">
  <h3 class="text-sm font-semibold">TikTok</h3>
  <CopyField label="Descripción" text={m.tiktok.descripcion} rows={4} />
</section>
