<script lang="ts">
  import { onMount } from "svelte";
  import ImageRow from "./ImageRow.svelte";
  import ImageConfig from "./ImageConfig.svelte";
  import ImageDetail from "./ImageDetail.svelte";
  import Button from "../primitives/Button.svelte";
  import { jobsDrenados, refrescarJobs, seleccionPendiente } from "@/lib/stores";
  import { currentTrack } from "@/lib/player";
  import {
    listarGaleria,
    detalleGaleria,
    crearGenerar,
    crearEditar,
    crearQuitarFondo,
    editarPrompt,
    mejorarPrompt,
    lanzarPreviews,
    lanzarFinal,
    borrarGaleria,
    type GaleriaDetalle,
  } from "@/lib/galeria";
  import type { GaleriaResumen } from "@/lib/types";

  let items = $state<GaleriaResumen[]>([]);
  let selectedId = $state<number | null>(null);
  let detail = $state<GaleriaDetalle | null>(null);
  let previewSel = $state<number | null>(null);
  let verGrid = $state(false);
  let bust = $state(0);
  let error = $state("");

  const busy = $derived(detail?.ocupado ?? false);
  const reservaPlayer = $derived($currentTrack ? "padding-bottom:88px" : "");

  async function refreshList() {
    try {
      items = await listarGaleria();
    } catch (e) {
      error = (e as Error).message;
    }
  }

  async function loadDetail(id: number) {
    try {
      detail = await detalleGaleria(id);
    } catch (e) {
      error = (e as Error).message;
    }
  }

  function select(id: number) {
    error = "";
    selectedId = id;
    detail = null;
    previewSel = null;
    verGrid = false;
    loadDetail(id);
  }

  function newImage() {
    error = "";
    selectedId = null;
    detail = null;
    previewSel = null;
    verGrid = false;
  }

  async function crearY(promesa: Promise<{ id: number }>) {
    try {
      const { id } = await promesa;
      await refreshList();
      select(id);
      refrescarJobs();
    } catch (e) {
      error = (e as Error).message;
    }
  }

  // Al crear NO se mejora el prompt automáticamente: el paso del LLM es opcional
  // (el usuario lo pulsa en el panel de trabajo si lo quiere).
  const handleGenerar = (p: { idea: string; width: number; height: number }) =>
    crearY(crearGenerar(p));
  const handleEditar = (p: { idea: string; file: File }) =>
    crearY(crearEditar(p.idea, p.file));
  const handleFondo = (p: { file: File }) => crearY(crearQuitarFondo(p.file));

  async function onmejorar() {
    if (selectedId == null) return;
    try {
      await mejorarPrompt(selectedId);
      refrescarJobs();
      loadDetail(selectedId);
    } catch (e) {
      error = (e as Error).message;
    }
  }

  async function onpreviews(prompt: string) {
    if (selectedId == null) return;
    try {
      await editarPrompt(selectedId, prompt);
      await lanzarPreviews(selectedId);
      previewSel = null;
      verGrid = false;
      refrescarJobs();
      loadDetail(selectedId);
    } catch (e) {
      error = (e as Error).message;
    }
  }

  function onpick(i: number) {
    previewSel = i;
  }

  async function onfinal() {
    if (selectedId == null || previewSel == null) return;
    try {
      await lanzarFinal(selectedId, previewSel);
      verGrid = false;
      refrescarJobs();
      loadDetail(selectedId);
    } catch (e) {
      error = (e as Error).message;
    }
  }

  function onreelegir() {
    verGrid = true;
  }

  async function handleDelete(id: number, idea: string) {
    if (!confirm(`¿Borrar la imagen «${idea.slice(0, 40)}»?\n\nSe pierden las previews y la final. No se puede deshacer.`))
      return;
    try {
      await borrarGaleria(id);
      if (selectedId === id) newImage();
      refreshList();
    } catch (e) {
      error = (e as Error).message;
    }
  }

  let ultimoDrenaje = 0;
  $effect(() => {
    const n = $jobsDrenados;
    if (n !== ultimoDrenaje) {
      ultimoDrenaje = n;
      refreshList();
      if (selectedId != null) loadDetail(selectedId);
      bust = n;
    }
  });

  // Salto desde la Biblioteca: abre la imagen pedida y consume la señal.
  $effect(() => {
    const sel = $seleccionPendiente;
    if (sel?.modo === "imagenes") {
      seleccionPendiente.set(null);
      select(sel.id);
    }
  });

  onMount(refreshList);
</script>

<div class="flex min-h-0 flex-1">
  <!-- Config (izquierda) -->
  <div class="flex w-[360px] min-w-0 shrink-0 flex-col border-r border-line bg-surface" style={reservaPlayer}>
    <ImageConfig {busy} oncreateGenerar={handleGenerar} oncreateEditar={handleEditar} oncreateFondo={handleFondo} />
  </div>

  <!-- Lista (centro) -->
  <div class="flex min-w-0 flex-1 flex-col">
    <div class="flex items-center justify-between gap-3 border-b border-line px-5 py-3">
      <span class="text-xs font-medium tracking-wide text-muted">
        {items.length} {items.length === 1 ? "imagen" : "imágenes"}
      </span>
      <Button size="sm" variant={selectedId === null ? "secondary" : "primary"} onclick={newImage}>
        + Nueva imagen
      </Button>
    </div>
    <div class="min-h-0 flex-1 space-y-2 overflow-y-auto p-4" style={reservaPlayer}>
      {#if error}
        <div class="rounded-md border border-danger/30 bg-danger-soft px-3 py-2 text-sm text-danger">{error}</div>
      {/if}
      {#each items as it (it.id)}
        <ImageRow
          item={it}
          active={it.id === selectedId}
          onselect={() => select(it.id)}
          ondelete={() => handleDelete(it.id, it.idea)}
        />
      {:else}
        <p class="mt-10 text-center text-sm text-muted">
          Sin imágenes aún. Crea la primera con el panel de la izquierda.
        </p>
      {/each}
    </div>
  </div>

  <!-- Trabajo (derecha) -->
  <ImageDetail {detail} {busy} {previewSel} {verGrid} {bust} {onpreviews} {onmejorar} {onpick} {onfinal} {onreelegir} />
</div>
