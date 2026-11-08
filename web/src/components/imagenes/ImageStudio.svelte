<script lang="ts">
  import { onMount } from "svelte";
  import ImageRow from "./ImageRow.svelte";
  import ImageConfig from "./ImageConfig.svelte";
  import ImageDetail from "./ImageDetail.svelte";
  import Button from "../primitives/Button.svelte";
  import BotonParar from "../shell/BotonParar.svelte";
  import { jobs, jobsDrenados, refrescarJobs, seleccionPendiente } from "@/lib/stores";
  import { currentTrack } from "@/lib/player";
  import {
    listarGaleria,
    detalleGaleria,
    crearGenerar,
    crearEditar,
    crearQuitarFondo,
    crearAnimada,
    cambiarEstilo,
    listarEstilos,
    type EstiloImagen,
    type NuevaImagen,
    guardarMovimiento,
    mejorarMovimiento,
    animar,
    escalar,
    type Escala,
    editarPrompt,
    mejorarPrompt,
    lanzarPreviews,
    lanzarFinal,
    borrarGaleria,
    type GaleriaDetalle,
  } from "@/lib/galeria";
  import type { GaleriaResumen } from "@/lib/types";

  let items = $state<GaleriaResumen[]>([]);
  // Los estilos de `estilos/`: los usan el formulario y el panel de trabajo.
  let estilos = $state<EstiloImagen[]>([]);
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

  async function cargarEstilos() {
    try {
      estilos = await listarEstilos();
    } catch {
      // Sin estilos se puede crear igual, en libre.
      estilos = [];
    }
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

  // Generar y animada: crear ya encola la escena y las previews (el backend
  // las encadena). Editar sigue con su paso de prompt opcional.
  const handleGenerar = (p: NuevaImagen & { motor: string }) => crearY(crearGenerar(p));
  const handleEditar = (p: { idea: string; file: File; motor: string }) =>
    crearY(crearEditar(p.idea, p.file, p.motor));
  const handleFondo = (p: { file: File }) => crearY(crearQuitarFondo(p.file));
  const handleAnimada = (p: NuevaImagen) => crearY(crearAnimada(p));

  // Pasos de la animada tras aprobar la preview. El movimiento se guarda antes
  // de pedir nada: tanto el LLM como el render leen el que está en la base.
  async function pasoAnimada(trabajo: () => Promise<unknown>) {
    if (selectedId == null) return;
    try {
      await trabajo();
      refrescarJobs();
      loadDetail(selectedId);
    } catch (e) {
      error = (e as Error).message;
    }
  }
  const onmejorarmov = (prompt: string, duracion: number) =>
    pasoAnimada(async () => {
      await guardarMovimiento(selectedId!, prompt, duracion);
      await mejorarMovimiento(selectedId!);
    });
  const onanimar = (prompt: string, duracion: number) =>
    pasoAnimada(async () => {
      await guardarMovimiento(selectedId!, prompt, duracion);
      await animar(selectedId!);
    });
  const onescalar = (escala: Escala) => pasoAnimada(() => escalar(selectedId!, escala));

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

  async function onpreviews(prompt: string, nPreviews: number) {
    if (selectedId == null) return;
    try {
      await editarPrompt(selectedId, prompt);
      await lanzarPreviews(selectedId, { n_previews: nPreviews });
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
      const { job_id } = await lanzarFinal(selectedId, previewSel);
      // En una animada aprobar es inmediato (sin job que drene): la imagen
      // aprobada cambia ya y hay que forzar que se vuelva a pedir.
      if (job_id == null) bust = Date.now();
      verGrid = false;
      refrescarJobs();
      loadDetail(selectedId);
    } catch (e) {
      error = (e as Error).message;
    }
  }

  async function oncambiarestilo(estilo: string) {
    if (selectedId == null) return;
    try {
      await cambiarEstilo(selectedId, estilo);
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

  // Una tirada de previews de la imagen abierta: cada vez que su progreso
  // avanza ha salido una preview más, y se recarga el detalle para enseñarla
  // en su hueco sin esperar a que termine la tirada entera.
  let pasoTirada = "";
  $effect(() => {
    const t = $jobs.find(
      (j) => j.tipo === "generar_previews_imagen" && j.ref_id === selectedId && j.estado === "corriendo",
    );
    const paso = t ? `${t.id}:${t.progreso?.hecho ?? 0}` : "";
    if (paso !== pasoTirada) {
      pasoTirada = paso;
      if (paso && selectedId != null) loadDetail(selectedId);
    }
  });

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

  onMount(() => {
    refreshList();
    cargarEstilos();
  });
</script>

<div class="flex min-h-0 flex-1">
  <!-- Config (izquierda) -->
  <div class="flex w-[360px] min-w-0 shrink-0 flex-col border-r border-line bg-surface" style={reservaPlayer}>
    <ImageConfig {busy} {estilos} oncreateGenerar={handleGenerar} oncreateEditar={handleEditar} oncreateFondo={handleFondo} oncreateAnimada={handleAnimada} />
  </div>

  <!-- Lista (centro) -->
  <div class="flex min-w-0 flex-1 flex-col">
    <div class="flex items-center justify-between gap-3 border-b border-line px-5 py-3">
      <span class="text-xs font-medium tracking-wide text-muted">
        {items.length} {items.length === 1 ? "imagen" : "imágenes"}
      </span>
      <div class="flex items-center gap-2">
        <BotonParar />
        <Button size="sm" variant={selectedId === null ? "secondary" : "primary"} onclick={newImage}>
          + Nueva imagen
        </Button>
      </div>
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
  <ImageDetail {detail} {busy} {previewSel} {verGrid} {bust} {estilos} {oncambiarestilo} {onpreviews} {onmejorar} {onpick} {onfinal} {onreelegir} {onmejorarmov} {onanimar} {onescalar} />
</div>
