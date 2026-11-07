<script lang="ts">
  import { onMount } from "svelte";
  import TrackRow from "./TrackRow.svelte";
  import MusicConfig from "./MusicConfig.svelte";
  import TrackDetail from "./TrackDetail.svelte";
  import AlbumConfig from "./AlbumConfig.svelte";
  import AlbumView from "./AlbumView.svelte";
  import Segmented from "../primitives/Segmented.svelte";
  import Chip from "../primitives/Chip.svelte";
  import Thumbnail from "../primitives/Thumbnail.svelte";
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

  import {
    listarAlbumes,
    detalleAlbum,
    crearAlbum,
    editarAlbum,
    borrarAlbum,
    replanificarAlbum,
    producirAlbum,
    ordenarAlbum,
    editarPista,
    reescribirPista,
    quitarPista,
    portadaAlbumUrl,
    type AlbumResumen,
    type AlbumDetalle,
    type CambiosPista,
    type PistaAlbum,
  } from "@/lib/albumes";
  import type { MusicaResumen, TipoMusica } from "@/lib/types";

  type Campos = { tags: string; lyrics: string; duracion_s: number } & Musical;

  let tracks = $state<MusicaResumen[]>([]);
  let selectedId = $state<number | null>(null);
  let detail = $state<MusicaDetalle | null>(null);
  let error = $state("");

  // Pistas sueltas o álbumes. Las pistas de un álbum no salen en la lista de
  // sueltas: viven en su tracklist.
  let vista = $state<"pistas" | "albumes">("pistas");
  let albumes = $state<AlbumResumen[]>([]);
  let albumId = $state<number | null>(null);
  let album = $state<AlbumDetalle | null>(null);
  const sueltas = $derived(tracks.filter((t) => t.album_id == null));

  const busy = $derived(detail?.ocupado ?? false);
  // Reserva de espacio abajo para que la isla flotante del player no tape el
  // contenido (ni la barra de acción del config).
  const reservaPlayer = $derived($currentTrack ? "padding-bottom:88px" : "");

  async function refreshList() {
    try {
      tracks = await listarMusica();
      albumes = await listarAlbumes();
      if (albumId != null) album = await detalleAlbum(albumId);
    } catch (e) {
      error = (e as Error).message;
    }
  }

  async function intentar(f: () => Promise<unknown>) {
    error = "";
    try {
      await f();
      refrescarJobs();
      await refreshList();
      if (selectedId != null) loadDetail(selectedId);
    } catch (e) {
      error = (e as Error).message;
    }
  }

  async function abrirAlbum(id: number) {
    vista = "albumes";
    albumId = id;
    newTrack();
    try {
      album = await detalleAlbum(id);
    } catch (e) {
      error = (e as Error).message;
    }
  }

  function cerrarAlbum() {
    albumId = null;
    album = null;
    newTrack();
  }

  async function handleCrearAlbum(p: { idea?: string; musica_id?: number; num_pistas: number }) {
    try {
      const { id } = await crearAlbum(p);
      refrescarJobs();
      await refreshList();
      abrirAlbum(id);
    } catch (e) {
      error = (e as Error).message;
    }
  }

  function moverPista(id: number, delta: number) {
    if (!album) return;
    const ids = album.pistas.map((p) => p.id);
    const i = ids.indexOf(id);
    const j = i + delta;
    if (i < 0 || j < 0 || j >= ids.length) return;
    [ids[i], ids[j]] = [ids[j], ids[i]];
    intentar(() => ordenarAlbum(album!.id, ids));
  }

  function quitar(p: PistaAlbum) {
    if (!album) return;
    const msg = p.origen
      ? `¿Sacar «${p.titulo}» del álbum? Vuelve a ser una pista suelta.`
      : `¿Quitar «${p.titulo}» del álbum?\n\nSe borra la pista y su audio.`;
    if (!confirm(msg)) return;
    if (selectedId === p.id) newTrack();
    intentar(() => quitarPista(album!.id, p.id));
  }

  function borrarElAlbum() {
    if (!album) return;
    if (!confirm(`¿Borrar el álbum «${album.titulo || album.idea}» y sus pistas?\n\nLa pista de origen se conserva. No se puede deshacer.`))
      return;
    const id = album.id;
    cerrarAlbum();
    intentar(() => borrarAlbum(id));
  }

  function replanificar() {
    if (!album) return;
    if (!confirm("¿Replanificar? Se tiran las pistas nuevas y el LLM propone otro tracklist.")) return;
    intentar(() => replanificarAlbum(album!.id));
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
    {#if vista === "albumes"}
      <AlbumConfig
        {album}
        oncreate={(p) => handleCrearAlbum(p)}
        onsave={(p) => album && intentar(() => editarAlbum(album!.id, p))}
        onproduce={() => album && intentar(() => producirAlbum(album!.id))}
        onreplan={replanificar}
        ondelete={borrarElAlbum}
      />
    {:else}
      <MusicConfig
        {detail}
        {busy}
        oncreate={handleCreate}
        onsuggest={handleSuggest}
        ongenerate={handleGenerate}
      />
    {/if}
  </div>

  <!-- Lista de pistas (centro) -->
  <div class="flex min-w-0 flex-1 flex-col">
    <div class="flex items-center justify-between gap-3 border-b border-line px-5 py-3">
      <div class="flex items-center gap-3">
        <div class="w-56">
          <Segmented
            options={[
              { value: "pistas", label: "Pistas" },
              { value: "albumes", label: "Álbumes" },
            ]}
            value={vista}
            onchange={(v) => {
              vista = v as "pistas" | "albumes";
              cerrarAlbum();
            }}
          />
        </div>
        {#if vista === "albumes" && album}
          <button type="button" class="text-xs text-muted hover:text-text" onclick={cerrarAlbum}>
            ← Álbumes
          </button>
        {:else}
          <span class="text-xs font-medium tracking-wide text-muted">
            {#if vista === "pistas"}
              {sueltas.length} {sueltas.length === 1 ? "pista" : "pistas"}
            {:else}
              {albumes.length} {albumes.length === 1 ? "álbum" : "álbumes"}
            {/if}
          </span>
        {/if}
      </div>
      <div class="flex items-center gap-2">
        <!-- Generar una pista son minutos de GPU: el botón de parada va donde
             se está mirando mientras trabaja, no solo en la cabecera. -->
        <BotonParar />
        {#if vista === "pistas"}
          <Button size="sm" variant={selectedId === null ? "secondary" : "primary"} onclick={newTrack}>
            + Nueva pista
          </Button>
        {:else}
          <Button size="sm" variant={album === null ? "secondary" : "primary"} onclick={cerrarAlbum}>
            + Nuevo álbum
          </Button>
        {/if}
      </div>
    </div>
    <div class="min-h-0 flex-1 space-y-2 overflow-y-auto p-4" style={reservaPlayer}>
      {#if error}
        <div class="rounded-md border border-danger/30 bg-danger-soft px-3 py-2 text-sm text-danger">
          {error}
        </div>
      {/if}
      {#if vista === "pistas"}
        {#each sueltas as t (t.id)}
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
      {:else if album}
        <AlbumView
          {album}
          {selectedId}
          onselect={(id) => {
            selectedId = id;
            loadDetail(id);
          }}
          onedit={(id, c: CambiosPista) => intentar(() => editarPista(album!.id, id, c))}
          onrewrite={(id) => intentar(() => reescribirPista(album!.id, id))}
          onmove={moverPista}
          onremove={quitar}
        />
      {:else}
        {#each albumes as a (a.id)}
          <button
            type="button"
            onclick={() => abrirAlbum(a.id)}
            class="flex w-full items-center gap-3 rounded-lg border border-line-soft bg-surface-2 px-3 py-2.5
                   text-left transition-colors hover:border-line hover:bg-surface-3"
          >
            <Thumbnail src={a.tiene_portada ? portadaAlbumUrl(a.id) : null} alt="" icon="music" size={48} />
            <span class="flex min-w-0 flex-1 flex-col gap-1">
              <span class="truncate text-sm font-medium text-text">{a.titulo}</span>
              <span class="flex items-center gap-1.5">
                <Chip tone="accent">{a.estado}</Chip>
                <Chip>{a.generadas}/{a.num_pistas} pistas</Chip>
                {#if a.ocupado}
                  <span class="size-3.5 animate-spin rounded-full border-2 border-line border-t-accent"></span>
                {/if}
              </span>
            </span>
          </button>
        {:else}
          <p class="mt-10 text-center text-sm text-muted">
            Sin álbumes aún. Planifica uno desde una idea, o desde una pista que te guste.
          </p>
        {/each}
      {/if}
    </div>
  </div>

  <!-- Detalle (derecha): metadatos + play/descarga; el audio suena en el player global -->
  <TrackDetail
    {detail}
    {busy}
    oncreatealbum={(num_pistas) => detail && handleCrearAlbum({ musica_id: detail.id, num_pistas })}
  />
</div>
