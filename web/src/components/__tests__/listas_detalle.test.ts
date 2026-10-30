import { render, screen } from "@testing-library/svelte";
import userEvent from "@testing-library/user-event";
import { get } from "svelte/store";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { GaleriaDetalle } from "@/lib/galeria";
import type { MusicaDetalle } from "@/lib/musica";
import { currentTrack, isPlaying, registerAudio } from "@/lib/player";
import * as proyectosApi from "@/lib/proyectos";
import type { ProyectoDetalle } from "@/lib/proyectos";
import ImageDetail from "../imagenes/ImageDetail.svelte";
import ImageRow from "../imagenes/ImageRow.svelte";
import TrackDetail from "../musica/TrackDetail.svelte";
import TrackRow from "../musica/TrackRow.svelte";
import StepVideo from "../videos/steps/StepVideo.svelte";

beforeEach(() => {
  currentTrack.set(null);
  isPlaying.set(false);
  registerAudio(null);
});

// --- música ------------------------------------------------------------------

describe("TrackRow", () => {
  const pista = (extra = {}) => ({ id: 4, idea: "lofi nocturno", tipo: "instrumental" as const, estado: "generada", tiene_portada: false, ...extra });
  const props = () => ({ onselect: vi.fn(), ondelete: vi.fn() });

  it("muestra título, tipo y estado", () => {
    render(TrackRow, { track: pista({ tipo: "cancion" }), ...props() });
    expect(screen.getByText("lofi nocturno")).toBeInTheDocument();
    expect(screen.getByText("Canción")).toBeInTheDocument();
    expect(screen.getByText("generada")).toBeInTheDocument();
  });

  it.each(["", "   "])("una idea vacía (%j) se rotula como pista sin título", (idea) => {
    render(TrackRow, { track: pista({ idea }), ...props() });
    expect(screen.getByText("(pista sin título)")).toBeInTheDocument();
  });

  it("pulsar el título la selecciona; la papelera la borra", async () => {
    const p = props();
    render(TrackRow, { track: pista(), ...p });
    await userEvent.click(screen.getByText("lofi nocturno"));
    expect(p.onselect).toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Borrar pista" }));
    expect(p.ondelete).toHaveBeenCalled();
  });

  it("una pista generada se puede reproducir (con su portada) y descargar", async () => {
    render(TrackRow, { track: pista({ tiene_portada: true }), ...props() });
    await userEvent.click(screen.getByRole("button", { name: "Reproducir" }));
    expect(get(currentTrack)).toMatchObject({ id: 4, src: "/api/musica/4/audio", cover: "/api/musica/4/portada" });
    expect(screen.getByRole("link", { name: "Descargar" })).toHaveAttribute("href", "/api/musica/4/audio");
  });

  it("una pista sin generar no ofrece reproducir ni descargar", () => {
    render(TrackRow, { track: pista({ estado: "nueva" }), ...props() });
    expect(screen.queryByRole("button", { name: "Reproducir" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Descargar" })).toBeNull();
  });

  it("sin portada no pide la imagen", () => {
    const { container } = render(TrackRow, { track: pista(), ...props() });
    expect(container.querySelector("img")).toBeNull();
  });

  it("se marca como activa y refleja que está sonando", () => {
    currentTrack.set({ id: 4, tipo: "instrumental", idea: "x", seed: null, duracion_s: 1, src: "/a", cover: null });
    isPlaying.set(true);
    const { container } = render(TrackRow, { track: pista(), active: true, ...props() });
    expect(container.firstElementChild!.className).toContain("bg-accent-soft");
    expect(screen.getByRole("button", { name: "Pausar" })).toBeInTheDocument();
  });
});

describe("TrackDetail", () => {
  const detalle = (extra: Partial<MusicaDetalle> = {}): MusicaDetalle => ({
    id: 4, tipo: "cancion", idea: "x", tags: "pop brillante", lyrics: "[Verse]\nla la", duracion_s: 30, seed: 42,
    estado: "generada", tiene_audio: true, tiene_portada: true, ocupado: false,
    bpm: 100, keyscale: "A minor", timesig: "4", idioma: "es", ...extra,
  });

  it("sin pista seleccionada invita a elegir una", () => {
    render(TrackDetail, { detail: null });
    expect(screen.getByText(/Selecciona una pista/)).toBeInTheDocument();
  });

  it("mientras trabaja muestra el progreso y nada más", () => {
    render(TrackDetail, { detail: detalle(), busy: true });
    expect(screen.getByText("Generando música…")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reproducir" })).toBeNull();
  });

  it("sin audio explica cómo generarlo", () => {
    render(TrackDetail, { detail: detalle({ tiene_audio: false }) });
    expect(screen.getByText("Aún no hay audio.")).toBeInTheDocument();
  });

  it("con audio muestra los datos musicales, estilo y letra", () => {
    render(TrackDetail, { detail: detalle() });
    for (const t of ["Canción", "seed 42", "30s", "100 BPM", "A minor", "4/4", "pop brillante"]) {
      expect(screen.getByText(t)).toBeInTheDocument();
    }
    expect(screen.getByAltText("Portada de la pista")).toHaveAttribute("src", "/api/musica/4/portada");
    expect(screen.getByText(/la la/)).toBeInTheDocument();
  });

  it("una pista instrumental no muestra la letra aunque exista", () => {
    render(TrackDetail, { detail: detalle({ tipo: "instrumental" }) });
    expect(screen.queryByText("Letra")).toBeNull();
  });

  it("sin seed ni portada omite esos elementos", () => {
    const { container } = render(TrackDetail, { detail: detalle({ seed: null, tiene_portada: false }) });
    expect(screen.queryByText(/^seed/)).toBeNull();
    expect(container.querySelector("img")).toBeNull();
  });

  it("reproducir carga la pista en el player", async () => {
    render(TrackDetail, { detail: detalle() });
    await userEvent.click(screen.getByRole("button", { name: /Reproducir/ }));
    expect(get(currentTrack)).toMatchObject({ id: 4, seed: 42, duracion_s: 30, src: "/api/musica/4/audio" });
    expect(screen.getByRole("link", { name: "Descargar" })).toHaveAttribute("download", "loomcast_musica_4");
  });
});

// --- imágenes ------------------------------------------------------------------

describe("ImageRow", () => {
  const item = (extra = {}) => ({ id: 2, idea: "un zorro", tipo: "generar" as const, estado: "nueva", ...extra });

  it.each([
    ["generar", "Generar"], ["editar", "Editar"], ["quitarfondo", "Fondo"],
  ] as const)("rotula el tipo %s", (tipo, texto) => {
    render(ImageRow, { item: item({ tipo }), onselect: vi.fn(), ondelete: vi.fn() });
    expect(screen.getByText(texto)).toBeInTheDocument();
  });

  it("idea vacía → '(imagen)'", () => {
    render(ImageRow, { item: item({ idea: "  " }), onselect: vi.fn(), ondelete: vi.fn() });
    expect(screen.getByText("(imagen)")).toBeInTheDocument();
  });

  it.each([
    ["generar", "nueva", null],
    ["generar", "previews", null],
    ["editar", "nueva", "/api/galeria/2/fuente"],
    ["quitarfondo", "nueva", "/api/galeria/2/fuente"],
    ["generar", "final", "/api/galeria/2/final"],
    ["editar", "final", "/api/galeria/2/final"],
  ] as const)("miniatura de %s en estado %s", (tipo, estado, esperada) => {
    const { container } = render(ImageRow, { item: item({ tipo, estado }), onselect: vi.fn(), ondelete: vi.fn() });
    const img = container.querySelector("img");
    expect(img?.getAttribute("src") ?? null).toBe(esperada);
  });

  it("seleccionar y borrar", async () => {
    const onselect = vi.fn(), ondelete = vi.fn();
    render(ImageRow, { item: item(), onselect, ondelete });
    await userEvent.click(screen.getByText("un zorro"));
    await userEvent.click(screen.getByRole("button", { name: "Borrar imagen" }));
    expect(onselect).toHaveBeenCalled();
    expect(ondelete).toHaveBeenCalled();
  });
});

describe("ImageDetail", () => {
  const detalle = (extra: Partial<GaleriaDetalle> = {}): GaleriaDetalle => ({
    id: 2, tipo: "generar", motor: "zimage", motor_nombre: "Z-Image Turbo", idea: "zorro", prompt: "a red fox",
    width: 768, height: 1344, estado: "nueva", seeds: [], seed_elegido: null, ocupado: false, ...extra,
  });
  const props = () => ({ onpreviews: vi.fn(), onmejorar: vi.fn(), onpick: vi.fn(), onfinal: vi.fn(), onreelegir: vi.fn() });

  it("sin imagen invita a elegir una", () => {
    render(ImageDetail, { detail: null, ...props() });
    expect(screen.getByText(/Selecciona una imagen/)).toBeInTheDocument();
  });

  it("muestra el motor, el prompt editable y el tamaño (solo al generar)", () => {
    render(ImageDetail, { detail: detalle(), ...props() });
    expect(screen.getByText("Z-Image Turbo")).toBeInTheDocument();
    expect((screen.getByRole("textbox") as HTMLTextAreaElement).value).toBe("a red fox");
    expect(screen.getByText("768×1344")).toBeInTheDocument();
  });

  it("al editar muestra la imagen de origen y no el tamaño", () => {
    render(ImageDetail, { detail: detalle({ tipo: "editar" }), ...props() });
    expect(screen.getByAltText("origen")).toHaveAttribute("src", "/api/galeria/2/fuente");
    expect(screen.queryByText("768×1344")).toBeNull();
  });

  it("generar previews envía el prompt editado; sin prompt está bloqueado", async () => {
    const p = props();
    render(ImageDetail, { detail: detalle({ prompt: null }), ...p });
    const boton = screen.getByRole("button", { name: "Generar 4 previews" });
    expect(boton).toBeDisabled();
    await userEvent.type(screen.getByRole("textbox"), "  a blue fox ");
    expect(boton).toBeEnabled();
    await userEvent.click(boton);
    expect(p.onpreviews).toHaveBeenCalledWith("  a blue fox ");
  });

  it("con previews cambia a 'Regenerar' y muestra la cuadrícula para elegir", async () => {
    const p = props();
    render(ImageDetail, { detail: detalle({ estado: "previews", seeds: [1, 2, 3, 4] }), ...p });
    expect(screen.getByRole("button", { name: "Regenerar 4 previews" })).toBeInTheDocument();
    await userEvent.click(screen.getByAltText("preview 3"));
    expect(p.onpick).toHaveBeenCalledWith(2);
  });

  it("'máxima resolución' exige elegir una preview", async () => {
    const p = props();
    const { rerender } = render(ImageDetail, { detail: detalle({ estado: "previews", seeds: [1, 2] }), previewSel: null, ...p });
    expect(screen.getByRole("button", { name: "Generar máxima resolución" })).toBeDisabled();
    await rerender({ detail: detalle({ estado: "previews", seeds: [1, 2] }), previewSel: 1, ...p });
    await userEvent.click(screen.getByRole("button", { name: "Generar máxima resolución" }));
    expect(p.onfinal).toHaveBeenCalled();
  });

  it("'busy' bloquea las acciones y lo indica", () => {
    render(ImageDetail, { detail: detalle({ estado: "previews", seeds: [1] }), busy: true, previewSel: 0, ...props() });
    expect(screen.getByText(/Trabajando/)).toBeInTheDocument();
    for (const n of ["Mejorar prompt con el LLM", "Generar máxima resolución"]) {
      expect(screen.getByRole("button", { name: n })).toBeDisabled();
    }
  });

  it("en estado final muestra la imagen final con descarga y permite volver a elegir", async () => {
    const p = props();
    render(ImageDetail, { detail: detalle({ estado: "final", seeds: [1, 2] }), ...p });
    expect(screen.getByAltText("final")).toBeInTheDocument();
    expect(screen.queryByAltText("preview 1")).toBeNull();
    expect(screen.getByRole("link", { name: /Descargar PNG/ })).toHaveAttribute("download", "loomcast_2.png");
    await userEvent.click(screen.getByRole("button", { name: "Elegir otra preview" }));
    expect(p.onreelegir).toHaveBeenCalled();
  });

  it("final + verGrid muestra la cuadrícula en vez de la imagen final", () => {
    render(ImageDetail, { detail: detalle({ estado: "final", seeds: [1, 2] }), verGrid: true, ...props() });
    expect(screen.getByAltText("preview 1")).toBeInTheDocument();
    expect(screen.queryByAltText("final")).toBeNull();
  });

  it("quitar fondo: sin prompt ni previews; muestra el resultado solo al terminar", () => {
    const { rerender } = render(ImageDetail, { detail: detalle({ tipo: "quitarfondo", motor_nombre: "" }), busy: true, ...props() });
    expect(screen.getByText("Quitando el fondo…")).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(screen.queryByAltText("resultado")).toBeNull();
    rerender({ detail: detalle({ tipo: "quitarfondo", estado: "final" }), ...props() });
  });

  it("quitar fondo terminado ofrece el PNG transparente", () => {
    render(ImageDetail, { detail: detalle({ tipo: "quitarfondo", estado: "final" }), ...props() });
    expect(screen.getByAltText("resultado")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Descargar PNG/ })).toBeInTheDocument();
  });

  it("al cambiar de imagen el borrador del prompt se resincroniza", async () => {
    const { rerender } = render(ImageDetail, { detail: detalle(), ...props() });
    await userEvent.type(screen.getByRole("textbox"), " extra");
    await rerender({ detail: detalle({ id: 3, prompt: "otro prompt" }), ...props() });
    expect((screen.getByRole("textbox") as HTMLTextAreaElement).value).toBe("otro prompt");
  });
});

// --- vídeo final ----------------------------------------------------------------

describe("StepVideo", () => {
  const proy = (extra: Partial<ProyectoDetalle> = {}): ProyectoDetalle => ({
    id: 1, slug: "demo", estado: "IMAGENES", plantilla: "curiosidades", voz: null, voz_instruct: "", idea: null,
    guion: null, guion_version: 0, metadatos: null, voz_disponible: true, voz_version: 0, subtitulos: "x",
    escenas: [], personajes: [], imagenes_completas: true, video_disponible: false, versiones: [],
    jobs_activos: 0, job_activo: null, musica: null, musica_mezclar: false,
    publicacion: null, disco: { total_mb: 0, liberable_mb: 0 }, liberado: false,
    serie: null, resumen_episodio: "", ...extra,
  });
  const acciones = () => ({ ongenerar: vi.fn(), onborrarvideo: vi.fn(), onborrarversion: vi.fn(), onborrarproyecto: vi.fn(), onver: vi.fn() });

  it("por defecto elige Ken Burns y genera con ese modo", async () => {
    const a = acciones();
    render(StepVideo, { p: proy(), ...a });
    expect(screen.getByRole("radio", { name: /Ken Burns/ })).toBeChecked();
    await userEvent.click(screen.getByRole("button", { name: "Generar vídeo" }));
    expect(a.ongenerar).toHaveBeenCalledWith("kenburns", "");
  });

  it("liberado no se puede rehacer: avisa y no deja encolar un job que falla", () => {
    render(StepVideo, { p: proy({ video_disponible: true, liberado: true }), ...acciones() });
    expect(screen.getByText(/su material se liberó/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Rehacer vídeo" })).toBeDisabled();
  });

  it("se puede cambiar de modo antes de generar", async () => {
    const a = acciones();
    render(StepVideo, { p: proy(), ...a });
    await userEvent.click(screen.getByRole("radio", { name: /Estático/ }));
    await userEvent.click(screen.getByRole("button", { name: "Generar vídeo" }));
    expect(a.ongenerar).toHaveBeenCalledWith("estatico", "");
  });

  it("en i2v aparece el selector de motor y se genera con el elegido", async () => {
    const motores = [
      { id: "ltx25", nombre: "LTX-2.5", frames: 25, fps_origen: 24, defecto: true },
      { id: "hunyuan", nombre: "HunyuanVideo 1.5", frames: 21, fps_origen: 24, defecto: false },
    ];
    vi.spyOn(proyectosApi, "listarMotoresI2V").mockResolvedValue(motores);
    const a = acciones();
    render(StepVideo, { p: proy(), ...a });
    await vi.waitFor(() => expect(proyectosApi.listarMotoresI2V).toHaveBeenCalled());

    // Con un modo que no anima por IA el selector no pinta nada.
    expect(screen.queryByRole("combobox")).toBeNull();

    await userEvent.click(screen.getByRole("radio", { name: /Image-to-video/ }));
    const selector = screen.getByRole("combobox");
    await userEvent.selectOptions(selector, "hunyuan");
    await userEvent.click(screen.getByRole("button", { name: "Generar vídeo" }));
    expect(a.ongenerar).toHaveBeenCalledWith("i2v", "hunyuan");
  });

  it("si los motores no llegan, el paso sigue generando sin motor", async () => {
    vi.spyOn(proyectosApi, "listarMotoresI2V").mockRejectedValue(new Error("sin backend"));
    const a = acciones();
    render(StepVideo, { p: proy(), ...a });
    await userEvent.click(screen.getByRole("radio", { name: /Image-to-video/ }));
    expect(screen.queryByRole("combobox")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Generar vídeo" }));
    expect(a.ongenerar).toHaveBeenCalledWith("i2v", "");
  });

  it("ofrece los cuatro modos", () => {
    render(StepVideo, { p: proy(), ...acciones() });
    expect(screen.getAllByRole("radio")).toHaveLength(4);
  });

  it("sin vídeo no hay reproductor; con vídeo sí, y el botón pasa a 'Rehacer'", () => {
    const { container, unmount } = render(StepVideo, { p: proy(), ...acciones() });
    expect(container.querySelector("video")).toBeNull();
    unmount();
    const r = render(StepVideo, { p: proy({ video_disponible: true }), bust: 7, ...acciones() });
    expect(r.container.querySelector("video")).toHaveAttribute("src", "/api/proyectos/1/video?v=7");
    expect(screen.getByRole("button", { name: "Rehacer vídeo" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Descargar/ })).toHaveAttribute("download", "demo.mp4");
  });

  it("'Ver en grande' abre el visor con el vídeo (cache-bust incluido)", async () => {
    const a = acciones();
    render(StepVideo, { p: proy({ video_disponible: true }), bust: 3, ...a });
    await userEvent.click(screen.getByRole("button", { name: "Ver en grande" }));
    expect(a.onver).toHaveBeenCalledWith(expect.stringContaining('src="/api/proyectos/1/video?v=3"'), "Vídeo final");
  });

  it("'busy' bloquea generar y borrar el proyecto, y muestra la etapa", () => {
    render(StepVideo, { p: proy({ job_activo: "armar_video", jobs_activos: 1 }), busy: true, ...acciones() });
    expect(screen.getByRole("button", { name: "Generar vídeo" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Borrar proyecto entero" })).toBeDisabled();
    expect(screen.getByText(/Armando el vídeo final/)).toBeInTheDocument();
  });

  it("borrar el vídeo y el proyecto delegan en el padre", async () => {
    const a = acciones();
    render(StepVideo, { p: proy({ video_disponible: true }), ...a });
    await userEvent.click(screen.getByRole("button", { name: "Borrar vídeo" }));
    await userEvent.click(screen.getByRole("button", { name: "Borrar proyecto entero" }));
    expect(a.onborrarvideo).toHaveBeenCalled();
    expect(a.onborrarproyecto).toHaveBeenCalled();
  });

  it("lista los montajes anteriores con su tamaño total y permite verlos o borrarlos", async () => {
    const a = acciones();
    const versiones = [
      { nombre: "final_1.mp4", fecha: "01/01 10:00", mb: 10.4 },
      { nombre: "final_2.mp4", fecha: "02/01 10:00", mb: 20.2 },
    ];
    render(StepVideo, { p: proy({ versiones }), ...a });
    expect(screen.getByText(/Montajes anteriores \(2 · 31 MB\)/)).toBeInTheDocument();

    await userEvent.click(screen.getAllByRole("button", { name: "Ver" })[1]);
    expect(a.onver).toHaveBeenCalledWith(expect.stringContaining("versiones/final_2.mp4"), "final_2.mp4");
    await userEvent.click(screen.getAllByRole("button", { name: "✕" })[0]);
    expect(a.onborrarversion).toHaveBeenCalledWith("final_1.mp4");
  });

  it("sin versiones no hay sección de montajes anteriores", () => {
    render(StepVideo, { p: proy(), ...acciones() });
    expect(screen.queryByText(/Montajes anteriores/)).toBeNull();
  });
});
