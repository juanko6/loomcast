import { render, screen, waitFor } from "@testing-library/svelte";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/proyectos", async (o) => {
  const real = await o<typeof import("@/lib/proyectos")>();
  const falsas = Object.fromEntries(
    Object.entries(real).filter(([, v]) => typeof v === "function").map(([k]) => [k, vi.fn()]),
  );
  return { ...real, ...falsas };
});
vi.mock("@/lib/series", async (o) => {
  const real = await o<typeof import("@/lib/series")>();
  const falsas = Object.fromEntries(
    Object.entries(real).filter(([, v]) => typeof v === "function").map(([k]) => [k, vi.fn()]),
  );
  return { ...real, ...falsas };
});
vi.mock("@/lib/api", async (o) => ({
  ...(await o<typeof import("@/lib/api")>()),
  api: vi.fn().mockResolvedValue([]),
}));

import * as API from "@/lib/proyectos";
import type { MiembroReparto, ProyectoDetalle } from "@/lib/proyectos";
import * as SeriesAPI from "@/lib/series";
import type { EpisodioResumen, SerieDetalle } from "@/lib/series";
import { currentTrack } from "@/lib/player";
import { jobs, jobsDrenados, seleccionPendiente } from "@/lib/stores";
import ResumenEpisodio from "../videos/ResumenEpisodio.svelte";
import SerieView from "../videos/SerieView.svelte";
import VideoStudio from "../videos/VideoStudio.svelte";

const m = vi.mocked(API);
const ms = vi.mocked(SeriesAPI);

const miembro = (extra: Partial<MiembroReparto> = {}): MiembroReparto => ({
  slug: "ana-narradora", nombre: "Ana narradora", clave: "ANA",
  ficha: "a tall woman with red hair", tipo: "persona", voz: "voz-ana",
  retrato: true, ...extra,
});

const episodio = (n: number, extra: Partial<EpisodioResumen> = {}): EpisodioResumen => ({
  proyecto_id: 100 + n, episodio: n, titulo: `Episodio ${n}`, slug: `ep-${n}`,
  estado: "FINAL", resumen: "Alicia encontró la llave.", ocupado: false, ...extra,
});

const serie = (extra: Partial<SerieDetalle> = {}): SerieDetalle => ({
  id: 7, slug: "la-casa-de-alicia", nombre: "La casa de Alicia", plantilla: "serie",
  tema_id: 3, n_episodios: 1, n_miembros: 1,
  miembros: [miembro()], episodios: [episodio(1)], ...extra,
});

const proyecto = (extra: Partial<ProyectoDetalle> = {}): ProyectoDetalle => ({
  id: 101, slug: "ep-1", estado: "FINAL", plantilla: "serie", voz: null, voz_instruct: "",
  serie: { id: 7, nombre: "La casa de Alicia", slug: "la-casa-de-alicia", episodio: 2,
           anterior: { episodio: 1, resumen: "Alicia encontró la llave." } },
  resumen_episodio: "",
  idea: { titulo: "Episodio 2", gancho: "g", resumen: "r" },
  guion: { gancho: "Hola", frases: ["Uno"], cta: "Fin" }, guion_version: 1, metadatos: null,
  voz_disponible: false, voz_version: 0, subtitulos: null, escenas: [], personajes: [],
  imagenes_completas: false, video_disponible: false, versiones: [], jobs_activos: 0,
  job_activo: null, musica: null, musica_mezclar: false, ...extra,
});

// --- SerieView --------------------------------------------------------------

describe("SerieView", () => {
  const props = () => ({
    onnuevoepisodio: vi.fn(), onabrirepisodio: vi.fn(), onanadirmiembro: vi.fn(),
    onquitarmiembro: vi.fn(), onideas: vi.fn(), onborrarserie: vi.fn(),
  });

  it("muestra el reparto fijo con su clave y su voz", () => {
    render(SerieView, { s: serie(), ...props() });
    expect(screen.getByRole("heading", { name: "La casa de Alicia" })).toBeInTheDocument();
    expect(screen.getByText("Ana narradora")).toBeInTheDocument();
    expect(screen.getByText("{ANA} · voz voz-ana")).toBeInTheDocument();
  });

  it("sin reparto fijo explica de dónde sale", () => {
    render(SerieView, { s: serie({ miembros: [], n_miembros: 0 }), ...props() });
    expect(screen.getByText(/Promueve a un personaje al reparto propio/)).toBeInTheDocument();
  });

  it("el siguiente episodio es el último más uno y dice a quién continúa", () => {
    render(SerieView, { s: serie({ episodios: [episodio(1), episodio(2)] }), ...props() });
    expect(screen.getByRole("heading", { name: "Episodio 3" })).toBeInTheDocument();
    expect(screen.getByText(/Continúa el episodio 2/)).toBeInTheDocument();
  });

  it("avisa cuando el anterior no está cerrado: este no podrá continuarlo", () => {
    render(SerieView, { s: serie({ episodios: [episodio(1, { resumen: "" })] }), ...props() });
    expect(screen.getByText(/no está cerrado todavía/)).toBeInTheDocument();
  });

  it("en una serie vacía dice que el primero planta la situación", () => {
    render(SerieView, { s: serie({ episodios: [], n_episodios: 0 }), ...props() });
    expect(screen.getByRole("heading", { name: "Episodio 1" })).toBeInTheDocument();
    expect(screen.getByText(/planta la situación/)).toBeInTheDocument();
    expect(screen.getByText("Ningún episodio todavía.")).toBeInTheDocument();
  });

  it("el apunte es opcional: sin escribir nada crea el episodio", async () => {
    const p = props();
    render(SerieView, { s: serie(), ...p });
    await userEvent.click(screen.getByRole("button", { name: "Nuevo episodio" }));
    expect(p.onnuevoepisodio).toHaveBeenCalledWith("");
  });

  it("manda el apunte recortado y limpia el campo", async () => {
    const p = props();
    render(SerieView, { s: serie(), ...p });
    const campo = screen.getByPlaceholderText("Qué pasa en este capítulo");
    await userEvent.type(campo, "  Ana encuentra la llave  ");
    await userEvent.click(screen.getByRole("button", { name: "Nuevo episodio" }));
    expect(p.onnuevoepisodio).toHaveBeenCalledWith("Ana encuentra la llave");
    expect((campo as HTMLInputElement).value).toBe("");
  });

  it("solo ofrece añadir a quien no sale ya en la serie", async () => {
    const p = props();
    const reparto = [miembro(), miembro({ slug: "vecino", nombre: "El vecino", clave: "VECINO" })];
    render(SerieView, { s: serie(), reparto, ...p });
    const sel = screen.getByLabelText("Añadir del reparto propio") as HTMLSelectElement;
    expect([...sel.options].map((o) => o.value)).toEqual(["", "vecino"]);

    await userEvent.selectOptions(sel, "vecino");
    await userEvent.click(screen.getByRole("button", { name: "Añadir" }));
    expect(p.onanadirmiembro).toHaveBeenCalledWith("vecino");
    expect(sel.value).toBe("");
  });

  it("sin nadie disponible no aparece el selector", () => {
    render(SerieView, { s: serie(), reparto: [miembro()], ...props() });
    expect(screen.queryByLabelText("Añadir del reparto propio")).not.toBeInTheDocument();
  });

  it("marca los episodios cerrados y abre el que se pulsa", async () => {
    const p = props();
    render(SerieView, {
      s: serie({ episodios: [episodio(1), episodio(2, { resumen: "", ocupado: true })] }),
      ...p,
    });
    expect(screen.getAllByText("cerrado")).toHaveLength(1);
    expect(screen.getByText("en marcha")).toBeInTheDocument();
    await userEvent.click(screen.getByLabelText(/Abrir episodio 1/));
    expect(p.onabrirepisodio).toHaveBeenCalledWith(101);
  });

  it("quitar a alguien del reparto fijo y disolver la serie avisan de lo que pasa", async () => {
    const p = props();
    render(SerieView, { s: serie(), ...p });
    await userEvent.click(screen.getByLabelText("Quitar a Ana narradora de la serie"));
    expect(p.onquitarmiembro).toHaveBeenCalledWith("ana-narradora", "Ana narradora");
    expect(screen.getByText(/se quedan como vídeos sueltos/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Disolver la serie" }));
    expect(p.onborrarserie).toHaveBeenCalled();
  });
});

// --- ResumenEpisodio --------------------------------------------------------

describe("ResumenEpisodio", () => {
  const props = () => ({ onguardar: vi.fn(), ongenerar: vi.fn() });

  it("un episodio sin cerrar lo dice y ofrece escribirlo con el LLM", () => {
    render(ResumenEpisodio, { p: proyecto(), ...props() });
    expect(screen.getByRole("heading", { name: "Cierre del episodio 2" })).toBeInTheDocument();
    expect(screen.getByText("sin cerrar")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Escribir con el LLM" })).toBeInTheDocument();
  });

  it("con resumen guardado se marca cerrado y el botón pasa a reescribir", () => {
    render(ResumenEpisodio, { p: proyecto({ resumen_episodio: "Pasó esto." }), ...props() });
    expect(screen.getByText("cerrado")).toBeInTheDocument();
    expect((screen.getByLabelText("Resumen del episodio") as HTMLTextAreaElement).value).toBe(
      "Pasó esto.",
    );
    expect(screen.getByRole("button", { name: "Reescribir con el LLM" })).toBeInTheDocument();
  });

  it("guardar está bloqueado hasta que el texto cambia, y manda el texto recortado", async () => {
    const p = props();
    render(ResumenEpisodio, { p: proyecto({ resumen_episodio: "Pasó esto." }), ...p });
    const guardar = screen.getByRole("button", { name: "Guardar resumen" });
    expect(guardar).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Resumen del episodio"), "  Y luego aquello. ");
    expect(guardar).toBeEnabled();
    await userEvent.click(guardar);
    expect(p.onguardar).toHaveBeenCalledWith("Pasó esto.  Y luego aquello.");
  });

  it("enseña lo que venía del episodio anterior", () => {
    render(ResumenEpisodio, { p: proyecto(), ...props() });
    expect(screen.getByText("Lo que venía del episodio 1")).toBeInTheDocument();
    expect(screen.getByText("Alicia encontró la llave.")).toBeInTheDocument();
  });
});

// --- VideoStudio: el área de series -----------------------------------------

describe("series en el estudio de vídeos", () => {
  beforeEach(() => {
    m.listarPlantillas.mockResolvedValue(["curiosidades", "serie"]);
    m.listarVoces.mockResolvedValue([]);
    m.listarReparto.mockResolvedValue([miembro()]);
    m.listarTemas.mockResolvedValue([]);
    m.listarProyectos.mockResolvedValue([
      { id: 101, titulo: "Episodio 1", slug: "ep-1", estado: "FINAL",
        serie: "La casa de Alicia", episodio: 1 },
      { id: 9, titulo: "Un vídeo suelto", slug: "suelto", estado: "GUION",
        serie: null, episodio: 0 },
    ]);
    m.detalleProyecto.mockResolvedValue(proyecto());
    m.masIdeas.mockResolvedValue({ job_id: 1 });
    m.ideasDeTema.mockResolvedValue([]);
    ms.listarSeries.mockResolvedValue([
      { id: 7, slug: "la-casa-de-alicia", nombre: "La casa de Alicia", plantilla: "serie",
        tema_id: 3, n_episodios: 2, n_miembros: 1 },
    ]);
    ms.detalleSerie.mockResolvedValue(serie());
    ms.crearSerie.mockResolvedValue({
      id: 7, slug: "la-casa-de-alicia", nombre: "La casa de Alicia", plantilla: "serie",
      tema_id: 3, n_episodios: 0, n_miembros: 0,
    });
    ms.crearEpisodio.mockResolvedValue({
      proyecto_id: 101, episodio: 2, idea_id: 44, job_id: 1, reparto_traido: ["ANA"],
    });
    ms.anadirMiembroSerie.mockResolvedValue({ slug: "ana-narradora" });
    ms.quitarMiembroSerie.mockResolvedValue({ slug: "ana-narradora" });
    ms.borrarSerie.mockResolvedValue({ episodios_sueltos: 2 });
    currentTrack.set(null);
    seleccionPendiente.set(null);
    jobs.set([]);
    jobsDrenados.set(0);
    vi.stubGlobal("confirm", vi.fn().mockReturnValue(true));
  });

  const montar = async () => {
    const r = render(VideoStudio);
    await screen.findByText("La casa de Alicia");
    return r;
  };

  const abrirSerie = async () => {
    await montar();
    await userEvent.click(screen.getByText("La casa de Alicia"));
    await screen.findByRole("heading", { name: "La casa de Alicia" });
  };

  it("lista las series con sus episodios y sus fijos", async () => {
    await montar();
    expect(screen.getByText("2 episodios · 1 fijos")).toBeInTheDocument();
  });

  it("marca en el listado de proyectos cuáles son episodios", async () => {
    await montar();
    expect(await screen.findByText("EP 1")).toBeInTheDocument();
    expect(screen.getByText("Un vídeo suelto")).toBeInTheDocument();
  });

  it("crear una serie la abre y limpia el formulario", async () => {
    await montar();
    const nombre = screen.getByLabelText("Nombre de la serie");
    await userEvent.type(nombre, "  La casa de Alicia ");
    await userEvent.selectOptions(screen.getByLabelText("Plantilla de la serie"), "serie");
    await userEvent.click(screen.getByRole("button", { name: "Crear serie" }));

    await waitFor(() =>
      expect(ms.crearSerie).toHaveBeenCalledWith("La casa de Alicia", "serie"));
    await waitFor(() => expect(ms.detalleSerie).toHaveBeenCalledWith(7));
    expect((nombre as HTMLInputElement).value).toBe("");
  });

  it("'Crear serie' está bloqueado sin nombre", async () => {
    await montar();
    expect(screen.getByRole("button", { name: "Crear serie" })).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Nombre de la serie"), "   ");
    expect(screen.getByRole("button", { name: "Crear serie" })).toBeDisabled();
  });

  it("nuevo episodio lo crea y abre el proyecto, que es donde se sigue", async () => {
    await abrirSerie();
    await userEvent.click(screen.getByRole("button", { name: "Nuevo episodio" }));
    await waitFor(() => expect(ms.crearEpisodio).toHaveBeenCalledWith(7, ""));
    await waitFor(() => expect(m.detalleProyecto).toHaveBeenCalledWith(101));
    expect(await screen.findByRole("heading", { name: "Episodio 2" })).toBeInTheDocument();
  });

  it("el episodio abierto lleva la serie en la cabecera", async () => {
    await abrirSerie();
    await userEvent.click(screen.getByLabelText(/Abrir episodio 1/));
    expect(await screen.findByText("La casa de Alicia · EP 2")).toBeInTheDocument();
  });

  it("pedir ideas de episodio usa el tema de la serie y abre ese tema", async () => {
    await abrirSerie();
    await userEvent.click(screen.getByRole("button", { name: "Pedir ideas de episodio" }));
    await waitFor(() => expect(m.masIdeas).toHaveBeenCalledWith(3));
    await waitFor(() => expect(m.ideasDeTema).toHaveBeenCalledWith(3));
  });

  it("añadir y quitar del reparto fijo recargan la serie", async () => {
    m.listarReparto.mockResolvedValue([
      miembro(), miembro({ slug: "vecino", nombre: "El vecino", clave: "VECINO" }),
    ]);
    await abrirSerie();
    await userEvent.selectOptions(screen.getByLabelText("Añadir del reparto propio"), "vecino");
    await userEvent.click(screen.getByRole("button", { name: "Añadir" }));
    await waitFor(() => expect(ms.anadirMiembroSerie).toHaveBeenCalledWith(7, "vecino"));

    await userEvent.click(screen.getByLabelText("Quitar a Ana narradora de la serie"));
    await waitFor(() =>
      expect(ms.quitarMiembroSerie).toHaveBeenCalledWith(7, "ana-narradora"));
  });

  it("quitar del reparto fijo se puede cancelar", async () => {
    vi.stubGlobal("confirm", vi.fn().mockReturnValue(false));
    await abrirSerie();
    await userEvent.click(screen.getByLabelText("Quitar a Ana narradora de la serie"));
    expect(ms.quitarMiembroSerie).not.toHaveBeenCalled();
  });

  it("disolver la serie cierra la vista y refresca las listas", async () => {
    await abrirSerie();
    await userEvent.click(screen.getByRole("button", { name: "Disolver la serie" }));
    await waitFor(() => expect(ms.borrarSerie).toHaveBeenCalledWith(7));
    expect(await screen.findByText(/Crea un tema para empezar/)).toBeInTheDocument();
  });

  it("un error del backend al crear el episodio se muestra y no abre nada", async () => {
    ms.crearEpisodio.mockRejectedValue(new Error("HTTP 404"));
    await abrirSerie();
    await userEvent.click(screen.getByRole("button", { name: "Nuevo episodio" }));
    expect(await screen.findByText("HTTP 404")).toBeInTheDocument();
    expect(m.detalleProyecto).not.toHaveBeenCalled();
  });

  it("guardar y reescribir el resumen del episodio abierto", async () => {
    // El paso del vídeo final solo se abre con las imágenes hechas.
    m.detalleProyecto.mockResolvedValue(proyecto({
      resumen_episodio: "Pasó esto.", imagenes_completas: true, video_disponible: false,
    }));
    m.editarResumen.mockResolvedValue({ resumen: "Otra cosa." });
    m.generarResumen.mockResolvedValue({ job_id: 2 });
    await abrirSerie();
    await userEvent.click(screen.getByLabelText(/Abrir episodio 1/));
    await screen.findByRole("heading", { name: "Episodio 2" });
    // El paso del vídeo final es el que cierra el episodio.
    await userEvent.click(screen.getByRole("button", { name: /Vídeo final/ }));

    const caja = await screen.findByLabelText("Resumen del episodio");
    await userEvent.type(caja, " Y luego aquello.");
    await userEvent.click(screen.getByRole("button", { name: "Guardar resumen" }));
    await waitFor(() =>
      expect(m.editarResumen).toHaveBeenCalledWith(101, "Pasó esto. Y luego aquello."));

    await userEvent.click(screen.getByRole("button", { name: "Reescribir con el LLM" }));
    await waitFor(() => expect(m.generarResumen).toHaveBeenCalledWith(101));
  });

  it("un vídeo suelto no tiene nada que cerrar", async () => {
    m.detalleProyecto.mockResolvedValue(proyecto({
      id: 9, serie: null, imagenes_completas: true,
      idea: { titulo: "Un vídeo suelto", gancho: "", resumen: "" },
    }));
    await montar();
    await userEvent.click(screen.getByText("Un vídeo suelto"));
    await screen.findByRole("heading", { name: "Un vídeo suelto" });
    await userEvent.click(screen.getByRole("button", { name: /Vídeo final/ }));
    expect(screen.queryByLabelText("Resumen del episodio")).not.toBeInTheDocument();
    expect(screen.queryByText(/· EP /)).not.toBeInTheDocument();
  });
});
