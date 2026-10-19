<script lang="ts">
  import { onMount } from "svelte";
  import TrackRow from "./TrackRow.svelte";
  import MusicConfig from "./MusicConfig.svelte";
  import TrackDetail from "./TrackDetail.svelte";
  import Button from "../primitives/Button.svelte";
  import BotonParar from "../shell/BotonParar.svelte";
  import { jobsDrenados, refrescarJobs, seleccionPendiente } from "@/lib/stores";
  import { currentTrack } from "@/lib/player";
  import {
    listarMusica,
    detalleMusica,
    crearMusica,
    editarMusica,
    mejorarMusica,
    generarMusica,
    borrarMusica,
    type Musical,
    type MusicaDetalle,
  } from "@/lib/musica";

  import type { MusicaResumen, TipoMusica } from "@/lib/types";

  type Campos = { tags: string; lyrics: string; duracion_s: number } & Musical;

  let tracks = $state<MusicaResumen[]>([]);
  let selectedId = $state<number | null>(null);
  let detail = $state<MusicaDetalle | null>(null);
  let error = $state("");

  const busy = $derived(detail?.ocupado ?? false);
  // Reserva de espacio abajo para que la isla flotante del player no tape el
  // contenido (ni la barra de acción del config).
  const reservaPlayer = $derived($currentTrack ? "padding-bottom:88px" : "");

  async function refreshList() {
    try {
      tracks = await listarMusica();
    } catch (e) {
      error = (e as Error).message;
    }
  }

  async function loadDetail(id: number) {
    try {
      detail = await detalleMusica(id);
    } catch (e) {
      error = (e as Error).message;
    }
  }

  function selectTrack(id: number) {
    error = "";
    selectedId = id;
    detail = null;
    loadDetail(id);
  }

  function newTrack() {
    error = "";
    selectedId = null;
    detail = null;
  }

  async function handleCreate(p: { tipo: TipoMusica; idea: string; duracion_s: number }) {
    try {
      const { id } = await crearMusica(p);
      await refreshList();
      selectTrack(id);
    } catch (e) {
      error = (e as Error).message;
    }
  }

  async function handleSuggest(p: Campos) {
    if (selectedId == null) return;
    try {
      // Guarda el borrador antes de que el LLM reescriba descripción/letra.
      await editarMusica(selectedId, p);
      await mejorarMusica(selectedId);
      refrescarJobs();
      loadDetail(selectedId);
    } catch (e) {
      error = (e as Error).message;
    }
  }

  async function handleGenerate(p: Campos) {
    if (selectedId == null) return;
    try {
      // seed null = pista nueva (el backend elige una aleatoria distinta).
      await generarMusica(selectedId, { ...p, seed: null });
      refrescarJobs();
      loadDetail(selectedId);
    } catch (e) {
      error = (e as Error).message;
    }
  }

  async function handleDelete(id: number, idea: string) {
    if (!confirm(`¿Borrar la pista «${idea.slice(0, 40)}»?\n\nSe pierde el audio generado. No se puede deshacer.`))
      return;
    try {
      await borrarMusica(id);
      if (selectedId === id) newTrack();
      refreshList();
    } catch (e) {
      error = (e as Error).message;
    }
  }

  // Cuando un job termina: refresca la lista (cambia el estado) y, si hay pista
  // abierta, recarga su detalle y fuerza recargar el audio.
  let ultimoDrenaje = 0;
  $effect(() => {
    const n = $jobsDrenados;
    if (n !== ultimoDrenaje) {
      ultimoDrenaje = n;
      refreshList();
      if (selectedId != null) loadDetail(selectedId);
    }
  });

  // Salto desde la Biblioteca: abre la pista pedida y consume la señal.
  $effect(() => {
    const sel = $seleccionPendiente;
    if (sel?.modo === "musica") {
      seleccionPendiente.set(null);
      selectTrack(sel.id);
    }
  });

  onMount(refreshList);
</script>

<div class="flex min-h-0 flex-1">
  <!-- Config (izquierda) -->
  <div class="flex w-[360px] min-w-0 shrink-0 flex-col border-r border-line bg-surface" style={reservaPlayer}>
    <MusicConfig
      {detail}
      {busy}
      oncreate={handleCreate}
      onsuggest={handleSuggest}
      ongenerate={handleGenerate}
    />
  </div>

  <!-- Lista de pistas (centro) -->
  <div class="flex min-w-0 flex-1 flex-col">
    <div class="flex items-center justify-between gap-3 border-b border-line px-5 py-3">
      <span class="text-xs font-medium tracking-wide text-muted">
        {tracks.length} {tracks.length === 1 ? "pista" : "pistas"}
      </span>
      <div class="flex items-center gap-2">
        <!-- Generar una pista son minutos de GPU: el botón de parada va donde
             se está mirando mientras trabaja, no solo en la cabecera. -->
        <BotonParar />
        <Button size="sm" variant={selectedId === null ? "secondary" : "primary"} onclick={newTrack}>
          + Nueva pista
        </Button>
      </div>
    </div>
    <div class="min-h-0 flex-1 space-y-2 overflow-y-auto p-4" style={reservaPlayer}>
      {#if error}
        <div class="rounded-md border border-danger/30 bg-danger-soft px-3 py-2 text-sm text-danger">
          {error}
        </div>
      {/if}
      {#each tracks as t (t.id)}
        <TrackRow
          track={t}
          active={t.id === selectedId}
          onselect={() => selectTrack(t.id)}
          ondelete={() => handleDelete(t.id, t.idea)}
        />
      {:else}
        <p class="mt-10 text-center text-sm text-muted">
          Sin pistas aún. Crea la primera con el panel de la izquierda.
        </p>
      {/each}
    </div>
  </div>

  <!-- Detalle (derecha): metadatos + play/descarga; el audio suena en el player global -->
  <TrackDetail {detail} {busy} />
</div>
