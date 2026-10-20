<script lang="ts">
  // Cierre del episodio: en qué quedó, para el guion del siguiente.
  //
  // Vive en el paso del vídeo final porque ahí es donde se cierra un capítulo,
  // y porque el resumen lo escribe la cola sola al terminar el montaje: quien
  // acaba de armar el episodio se lo encuentra aquí ya escrito. Es editable
  // porque es lo que el episodio siguiente dará por cierto, y un detalle
  // inventado que nadie corrige se vuelve canon de la serie.
  import Button from "../primitives/Button.svelte";
  import Chip from "../primitives/Chip.svelte";
  import type { ProyectoDetalle } from "@/lib/proyectos";

  let {
    p,
    busy = false,
    onguardar,
    ongenerar,
  }: {
    p: ProyectoDetalle;
    busy?: boolean;
    onguardar: (resumen: string) => void;
    ongenerar: () => void;
  } = $props();

  // El texto guardado es la fuente; al cambiar por fuera (lo acaba de escribir
  // el LLM) se recarga el editor, salvo que haya cambios a medio escribir.
  let texto = $state(p.resumen_episodio);
  let guardado = $state(p.resumen_episodio);
  $effect(() => {
    if (p.resumen_episodio !== guardado) {
      if (texto === guardado) texto = p.resumen_episodio;
      guardado = p.resumen_episodio;
    }
  });
  const sucio = $derived(texto.trim() !== guardado.trim());
</script>

<section class="space-y-2 rounded-xl border border-line bg-surface-2 p-4">
  <div class="flex flex-wrap items-center gap-2">
    <h3 class="text-sm font-semibold">Cierre del episodio {p.serie?.episodio}</h3>
    {#if guardado.trim()}
      <Chip tone="ok">cerrado</Chip>
    {:else}
      <Chip tone="warn">sin cerrar</Chip>
    {/if}
  </div>
  <p class="text-xs text-dim">
    Qué pasó en este capítulo, cómo acabó y qué queda abierto. Es lo que entra como contexto en el
    guion del episodio siguiente, así que corrige aquí lo que el LLM haya entendido mal.
  </p>

  <textarea
    class="control"
    rows="5"
    bind:value={texto}
    placeholder="Se escribe solo al armar el vídeo del episodio. También puedes escribirlo a mano."
    aria-label="Resumen del episodio"
  ></textarea>

  <div class="flex flex-wrap items-center gap-2">
    <Button size="sm" disabled={busy || !sucio} onclick={() => onguardar(texto.trim())}>
      Guardar resumen
    </Button>
    <Button size="sm" variant="secondary" disabled={busy} onclick={ongenerar}>
      {guardado.trim() ? "Reescribir con el LLM" : "Escribir con el LLM"}
    </Button>
  </div>

  {#if p.serie?.anterior}
    <details class="pt-1">
      <summary class="cursor-pointer text-xs text-dim">
        Lo que venía del episodio {p.serie.anterior.episodio}
      </summary>
      <p class="mt-1 text-xs text-muted">
        {p.serie.anterior.resumen || "No se cerró: este episodio no pudo continuarlo."}
      </p>
    </details>
  {/if}
</section>
