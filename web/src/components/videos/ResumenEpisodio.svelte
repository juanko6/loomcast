<script lang="ts">
  // El canon del episodio: qué pasó de verdad, para el guion del siguiente.
  //
  // Vive en el paso del **guion** y no en el del vídeo final, porque es ahí
  // donde la historia queda cerrada: ni la voz ni las imágenes ni el i2v añaden
  // un hecho, y esperar al montaje metía el render en el camino de la historia
  // (y dejaba al episodio siguiente sin continuidad hasta entonces). La cola lo
  // escribe sola en cuanto el guion está aprobado, así que quien acaba de
  // aprobarlo se lo encuentra aquí ya escrito.
  //
  // Es editable porque es lo que el episodio siguiente dará por cierto, y un
  // detalle inventado que nadie corrige se vuelve canon de la serie. Y aquí
  // también se ve el tramo que le tocaba: sin él, "este capítulo se fue del
  // tema" no es una frase que se pueda comprobar.
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
  const tramo = $derived(p.serie?.tramo ?? null);
  // El canon salió de otra versión del guion: lo que cuenta ya no es lo que el
  // episodio dice, y lo que miente aquí se vuelve canon en el siguiente.
  const caducado = $derived(
    !!guardado.trim() &&
      !!p.serie &&
      p.guion_version > 0 &&
      p.serie.resumen_version !== p.guion_version,
  );
</script>

<section class="space-y-2 rounded-xl border border-line bg-surface-2 p-4">
  <div class="flex flex-wrap items-center gap-2">
    <h3 class="text-sm font-semibold">Canon del episodio {p.serie?.episodio}</h3>
    {#if guardado.trim()}
      <Chip tone="ok">cerrado</Chip>
    {:else}
      <Chip tone="warn">sin cerrar</Chip>
    {/if}
    {#if caducado}
      <Chip tone="warn">de la v{p.serie?.resumen_version} del guion</Chip>
    {/if}
    {#if p.serie?.continuidad_rota}
      <Chip tone="warn">un episodio anterior cambió</Chip>
    {/if}
  </div>
  <p class="text-xs text-dim">
    Qué pasó en este capítulo, cómo acabó y qué queda abierto. Es lo que entra como contexto en el
    guion del episodio siguiente, así que corrige aquí lo que el LLM haya entendido mal.
  </p>
  {#if caducado}
    <p class="text-xs text-warn">
      El guion va por la v{p.guion_version} y este canon salió de la v{p.serie?.resumen_version}:
      cuenta una versión que ya no existe. Reescríbelo antes de sacar el episodio siguiente.
    </p>
  {/if}
  {#if p.serie?.continuidad_rota}
    <p class="text-xs text-warn">
      Este episodio se escribió con el canon de antes: después se reescribió el guion de un
      capítulo anterior o se corrigió su resumen. No se ha rehecho nada —lo escrito no se toca—,
      así que decide tú si vuelves a generar su guion.
    </p>
  {/if}

  {#if tramo}
    <div class="rounded-lg bg-surface p-3 text-xs">
      <p class="font-semibold">
        Su tramo del hilo: {tramo.titulo}
        {#if p.serie?.es_final}<span class="text-accent"> · cierra la serie</span>{/if}
      </p>
      <p class="mt-1 text-dim">Tenía que pasar: {tramo.pasa}</p>
      <p class="text-dim">Tenía que cambiar: {tramo.cambia}</p>
      {#if p.serie?.desvio}
        <p class="mt-1 text-warn">Se desvió: {p.serie.desvio}</p>
      {:else if guardado.trim()}
        <p class="mt-1 text-ok">Cumplió su tramo.</p>
      {/if}
    </div>
  {/if}

  <textarea
    class="control"
    rows="5"
    bind:value={texto}
    placeholder="Se escribe solo en cuanto el guion está aprobado. También puedes escribirlo a mano."
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
