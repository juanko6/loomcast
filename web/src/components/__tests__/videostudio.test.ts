import { render, screen, waitFor, within } from "@testing-library/svelte";
import userEvent from "@testing-library/user-event";
import { get } from "svelte/store";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/proyectos", async (o) => {
  const real = await o<typeof import("@/lib/proyectos")>();
  const falsas = Object.fromEntries(
    Object.entries(real).filter(([, v]) => typeof v === "function").map(([k]) => [k, vi.fn()]),
  );
  return { ...real, ...falsas };
});
vi.mock("@/lib/api", async (o) => ({ ...(await o<typeof import("@/lib/api")>()), api: vi.fn().mockResolvedValue([]) }));

import * as API from "@/lib/proyectos";
import type { ProyectoDetalle } from "@/lib/proyectos";
import { currentTrack } from "@/lib/player";
import { jobs, jobsDrenados, seleccionPendiente } from "@/lib/stores";
import type { Job } from "@/lib/types";
import VideoStudio from "../videos/VideoStudio.svelte";

const m = vi.mocked(API);

const proyecto = (extra: Partial<ProyectoDetalle> = {}): ProyectoDetalle => ({
  id: 1, slug: "demo", estado: "GUION", plantilla: "curiosidades", voz: null, voz_instruct: "",
  idea: { titulo: "Mi proyecto", gancho: "g", resumen: "r" },
  guion: { gancho: "Hola", frases: ["Uno"], cta: "Fin" }, guion_version: 1, metadatos: null,
  voz_disponible: false, voz_version: 0, subtitulos: null, escenas: [], personajes: [],
  imagenes_completas: false, video_disponible: false, versiones: [], jobs_activos: 0, job_activo: null,
  musica: null, musica_mezclar: false, ...extra,
});

beforeEach(() => {
  m.listarPlantillas.mockResolvedValue(["curiosidades", "drama"]);
  m.listarVoces.mockResolvedValue([]);
  m.listarReparto.mockResolvedValue([]);
  m.listarTemas.mockResolvedValue([{ id: 1, texto: "misterios del mar", n_ideas: 3, n_aprobadas: 1 }]);
  m.listarProyectos.mockResolvedValue([{ id: 1, titulo: "Mi proyecto", slug: "demo", estado: "GUION" }]);
  m.ideasDeTema.mockResolvedValue([
    { id: 5, titulo: "Idea A", gancho: "g", resumen: "r", estado: "propuesta", proyecto_id: null }]);
  m.detalleProyecto.mockResolvedValue(proyecto());
  m.crearTema.mockResolvedValue({ tema_id: 9 });
  m.proyectoDesdeIdea.mockResolvedValue({ proyecto_id: 1 });
  m.cambiarEstadoIdea.mockResolvedValue(undefined);
  m.masIdeas.mockResolvedValue({ job_id: 1 });
  m.borrarProyecto.mockResolvedValue({ slug: "demo", archivos: 3 });
  m.borrarTema.mockResolvedValue({ ideas: 3 });
  m.guardarGuion.mockResolvedValue({ version: 2 });
  m.regenerarGuion.mockResolvedValue({ job_id: 1 });
  currentTrack.set(null);
  seleccionPendiente.set(null);
  jobs.set([]);
  jobsDrenados.set(0);
  vi.stubGlobal("confirm", vi.fn().mockReturnValue(true));
});

const montar = async () => {
  const r = render(VideoStudio);
  await screen.findByText("misterios del mar");
  return r;
};

describe("carga inicial", () => {
  it("lista temas (con aprobadas/ideas) y proyectos (con estado)", async () => {
    await montar();
    expect(screen.getByText("1/3 aprobadas")).toBeInTheDocument();
    expect(await screen.findByText("Mi proyecto")).toBeInTheDocument();
    expect(screen.getByText("GUION")).toBeInTheDocument();
  });

  it("sin temas ni proyectos muestra los avisos", async () => {
    m.listarTemas.mockResolvedValue([]);
    m.listarProyectos.mockResolvedValue([]);
    render(VideoStudio);
    expect(await screen.findByText("Sin temas aún.")).toBeInTheDocument();
    expect(screen.getByText("Sin proyectos aún.")).toBeInTheDocument();
  });

  it("ofrece las plantillas y elige la primera", async () => {
    await montar();
    const sel = screen.getByLabelText("Plantilla") as HTMLSelectElement;
    expect([...sel.options].map((o) => o.value)).toEqual(["curiosidades", "drama"]);
    expect(sel.value).toBe("curiosidades");
  });

  it("sin vista elegida invita a crear o elegir un tema", async () => {
    await montar();
    expect(screen.getByText(/Crea un tema para empezar/)).toBeInTheDocument();
  });

  it("si la carga falla muestra el error", async () => {
    m.listarPlantillas.mockRejectedValue(new Error("HTTP 500"));
    render(VideoStudio);
    expect(await screen.findByText("HTTP 500")).toBeInTheDocument();
  });
});

describe("crear tema", () => {
  it("'Generar ideas' está bloqueado sin texto", async () => {
    await montar();
    expect(screen.getByRole("button", { name: "Generar ideas" })).toBeDisabled();
    await userEvent.type(screen.getByPlaceholderText(/misterios del océano/), "   ");
    expect(screen.getByRole("button", { name: "Generar ideas" })).toBeDisabled();
  });

  it("crea el tema con su plantilla, limpia el formulario y abre sus ideas", async () => {
    await montar();
    await userEvent.type(screen.getByPlaceholderText(/misterios del océano/), "  los volcanes ");
    await userEvent.selectOptions(screen.getByLabelText("Plantilla"), "drama");
    await userEvent.click(screen.getByRole("button", { name: "Generar ideas" }));

    await waitFor(() => expect(m.crearTema).toHaveBeenCalledWith("los volcanes", "drama"));
    await waitFor(() => expect(m.ideasDeTema).toHaveBeenCalledWith(9));
    expect((screen.getByPlaceholderText(/misterios del océano/) as HTMLTextAreaElement).value).toBe("");
  });

  it("si falla muestra el error y conserva el texto", async () => {
    m.crearTema.mockRejectedValue(new Error("HTTP 400"));
    await montar();
    await userEvent.type(screen.getByPlaceholderText(/misterios del océano/), "algo");
    await userEvent.click(screen.getByRole("button", { name: "Generar ideas" }));
    expect(await screen.findByText("HTTP 400")).toBeInTheDocument();
    expect((screen.getByPlaceholderText(/misterios del océano/) as HTMLTextAreaElement).value).toBe("algo");
  });
});

describe("ideas de un tema", () => {
  const abrirTema = async () => {
    await montar();
    await userEvent.click(screen.getByText("misterios del mar"));
    await screen.findByText("Idea A");
  };

  it("pulsar un tema muestra sus ideas", async () => {
    await abrirTema();
    expect(m.ideasDeTema).toHaveBeenCalledWith(1);
  });

  it("aprobar crea el proyecto y salta a él", async () => {
    await abrirTema();
    await userEvent.click(screen.getByRole("button", { name: "Aprobar y crear proyecto" }));
    await waitFor(() => expect(m.proyectoDesdeIdea).toHaveBeenCalledWith(5));
    await waitFor(() => expect(m.detalleProyecto).toHaveBeenCalledWith(1));
    expect(await screen.findByRole("heading", { name: "Mi proyecto" })).toBeInTheDocument();
  });

  it("descartar y restaurar cambian el estado de la idea", async () => {
    await abrirTema();
    // La vista se recarga tras cambiar el estado: el backend ya devolverá la idea descartada.
    m.ideasDeTema.mockResolvedValue([{ id: 5, titulo: "Idea A", gancho: "g", resumen: "r", estado: "descartada", proyecto_id: null }]);
    await userEvent.click(screen.getByRole("button", { name: "Descartar" }));
    await waitFor(() => expect(m.cambiarEstadoIdea).toHaveBeenCalledWith(5, "descartada"));
    await userEvent.click(await screen.findByRole("button", { name: "Restaurar" }));
    await waitFor(() => expect(m.cambiarEstadoIdea).toHaveBeenCalledWith(5, "propuesta"));
  });

  it("'Generar más ideas' lo pide para el tema abierto", async () => {
    await abrirTema();
    await userEvent.click(screen.getByRole("button", { name: "Generar más ideas" }));
    await waitFor(() => expect(m.masIdeas).toHaveBeenCalledWith(1));
  });

  it("si aprobar falla muestra el error y no abre proyecto", async () => {
    m.proyectoDesdeIdea.mockRejectedValue(new Error("HTTP 404"));
    await abrirTema();
    await userEvent.click(screen.getByRole("button", { name: "Aprobar y crear proyecto" }));
    expect(await screen.findByText("HTTP 404")).toBeInTheDocument();
    expect(m.detalleProyecto).not.toHaveBeenCalled();
  });

  it("una idea con proyecto permite abrirlo", async () => {
    m.ideasDeTema.mockResolvedValue([{ id: 5, titulo: "Idea A", gancho: "g", resumen: "r", estado: "aprobada", proyecto_id: 1 }]);
    await abrirTema();
    await userEvent.click(screen.getByRole("button", { name: /Ver proyecto/ }));
    await waitFor(() => expect(m.detalleProyecto).toHaveBeenCalledWith(1));
  });
});

describe("borrados", () => {
  it("borrar un tema pide confirmación y no borra si se cancela", async () => {
    vi.stubGlobal("confirm", vi.fn().mockReturnValue(false));
    await montar();
    await userEvent.click(screen.getByRole("button", { name: "Borrar tema" }));
    expect(m.borrarTema).not.toHaveBeenCalled();
  });

  it("borrar el tema abierto cierra la vista y refresca las listas", async () => {
    await montar();
    await userEvent.click(screen.getByText("misterios del mar"));
    await screen.findByText("Idea A");
    m.listarTemas.mockClear();
    await userEvent.click(screen.getByRole("button", { name: "Borrar tema" }));
    await waitFor(() => expect(m.borrarTema).toHaveBeenCalledWith(1));
    expect(await screen.findByText(/Crea un tema para empezar/)).toBeInTheDocument();
    expect(m.listarTemas).toHaveBeenCalled();
  });

  it("un tema con proyectos: el error del backend (409) se muestra", async () => {
    m.borrarTema.mockRejectedValue(new Error("Hay proyectos creados desde este tema"));
    await montar();
    await userEvent.click(screen.getByRole("button", { name: "Borrar tema" }));
    expect(await screen.findByText(/Hay proyectos creados/)).toBeInTheDocument();
  });

  it("borrar un proyecto exige DOBLE confirmación", async () => {
    const confirmar = vi.fn().mockReturnValueOnce(true).mockReturnValueOnce(false);
    vi.stubGlobal("confirm", confirmar);
    await montar();
    await userEvent.click(await screen.findByRole("button", { name: "Borrar proyecto" }));
    expect(confirmar).toHaveBeenCalledTimes(2);
    expect(m.borrarProyecto).not.toHaveBeenCalled();
  });

  it("confirmado dos veces, borra y cierra el proyecto si era el abierto", async () => {
    await montar();
    await userEvent.click(await screen.findByText("Mi proyecto"));
    await screen.findByRole("heading", { name: "Mi proyecto" });
    await userEvent.click(screen.getByRole("button", { name: "Borrar proyecto" }));
    await waitFor(() => expect(m.borrarProyecto).toHaveBeenCalledWith(1));
    expect(await screen.findByText(/Crea un tema para empezar/)).toBeInTheDocument();
  });
});

describe("proyecto abierto", () => {
  const abrirProyecto = async () => {
    await montar();
    await userEvent.click(await screen.findByText("Mi proyecto"));
    await screen.findByRole("heading", { name: "Mi proyecto" });
  };

  it("mientras carga el detalle muestra un indicador", async () => {
    m.detalleProyecto.mockReturnValue(new Promise(() => {}));
    await montar();
    const { container } = { container: document.body };
    await userEvent.click(await screen.findByText("Mi proyecto"));
    expect(container.querySelector(".animate-spin")).not.toBeNull();
  });

  it("si el detalle falla muestra el error", async () => {
    m.detalleProyecto.mockRejectedValue(new Error("HTTP 404"));
    await montar();
    await userEvent.click(await screen.findByText("Mi proyecto"));
    expect(await screen.findByText("HTTP 404")).toBeInTheDocument();
  });

  it("guardar el guion llama a la API y recarga el proyecto y las listas", async () => {
    await abrirProyecto();
    await userEvent.click(screen.getByRole("button", { name: /Guion/ }));
    m.detalleProyecto.mockClear();
    m.listarProyectos.mockClear();
    await userEvent.click(screen.getByRole("button", { name: "Guardar guion" }));
    await waitFor(() => expect(m.guardarGuion).toHaveBeenCalledWith(1, { gancho: "Hola", frases: ["Uno"], cta: "Fin" }));
    await waitFor(() => expect(m.detalleProyecto).toHaveBeenCalledWith(1));
    await waitFor(() => expect(m.listarProyectos).toHaveBeenCalled());
  });

  it("si una acción falla muestra el error", async () => {
    m.regenerarGuion.mockRejectedValue(new Error("HTTP 500"));
    await abrirProyecto();
    await userEvent.click(screen.getByRole("button", { name: /Guion/ }));
    await userEvent.click(screen.getByRole("button", { name: "Regenerar con el LLM" }));
    expect(await screen.findByText("HTTP 500")).toBeInTheDocument();
  });

  it("con trabajo en curso el proyecto lo indica y bloquea las acciones", async () => {
    m.detalleProyecto.mockResolvedValue(proyecto({ jobs_activos: 1, job_activo: "generar_guion" }));
    await abrirProyecto();
    expect(screen.getByText("Escribiendo el guion…")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Guion/ }));
    expect(screen.getByRole("button", { name: "Regenerar con el LLM" })).toBeDisabled();
  });
});

describe("refrescos automáticos", () => {
  const abrirProyecto = async () => {
    await montar();
    await userEvent.click(await screen.findByText("Mi proyecto"));
    await screen.findByRole("heading", { name: "Mi proyecto" });
  };
  const job = (hecho: number): Job => ({ id: 1, tipo: "generar_imagenes", estado: "corriendo",
    progreso: { job_id: 1, transcurrido_s: 1, fase: "imagen", hecho, total: 5, pct: 0, eta_s: null } });

  it("al terminar un job recarga listas, vista y voces", async () => {
    await abrirProyecto();
    [m.listarTemas, m.listarProyectos, m.detalleProyecto, m.listarVoces].forEach((f) => f.mockClear());
    jobsDrenados.update((n) => n + 1);
    await waitFor(() => expect(m.listarTemas).toHaveBeenCalled());
    await waitFor(() => expect(m.detalleProyecto).toHaveBeenCalledWith(1));
    await waitFor(() => expect(m.listarVoces).toHaveBeenCalled());
  });

  it("mientras corre un lote recarga cada vez que avanza, no en el primer elemento", async () => {
    await abrirProyecto();
    m.detalleProyecto.mockClear();

    jobs.set([job(0)]);                 // primer elemento: aún no hay nada nuevo
    await new Promise((r) => setTimeout(r, 20));
    expect(m.detalleProyecto).not.toHaveBeenCalled();

    jobs.set([job(1)]);                 // ya hay una imagen hecha
    await waitFor(() => expect(m.detalleProyecto).toHaveBeenCalledTimes(1));
    jobs.set([job(1)]);                 // misma cifra: no vuelve a pedir
    await new Promise((r) => setTimeout(r, 20));
    expect(m.detalleProyecto).toHaveBeenCalledTimes(1);
    jobs.set([job(2)]);
    await waitFor(() => expect(m.detalleProyecto).toHaveBeenCalledTimes(2));
  });

  it("un salto desde la Biblioteca abre ese proyecto y consume la señal", async () => {
    seleccionPendiente.set({ modo: "videos", id: 1 });
    render(VideoStudio);
    await waitFor(() => expect(m.detalleProyecto).toHaveBeenCalledWith(1));
    expect(get(seleccionPendiente)).toBeNull();
  });

  it("una señal de otro modo se deja", async () => {
    seleccionPendiente.set({ modo: "musica", id: 1 });
    await montar();
    expect(get(seleccionPendiente)).toEqual({ modo: "musica", id: 1 });
  });

  it("con una pista en el player reserva sitio abajo", async () => {
    currentTrack.set({ id: 1, tipo: "instrumental", idea: "x", seed: null, duracion_s: 1, src: "/a", cover: null });
    const { container } = await montar();
    expect(container.querySelectorAll('[style*="padding-bottom: 88px"]').length).toBeGreaterThan(0);
  });

  it("el listado de proyectos y temas se puede recorrer con su panel", async () => {
    await montar();
    const panel = screen.getByText("Proyectos").parentElement!;
    expect(within(panel).getByText("Mi proyecto")).toBeInTheDocument();
  });
});

describe("reparto propio", () => {
  // El paso de escenas, que es donde vive el reparto, pide subtítulos hechos.
  const conReparto = (extra: Partial<ProyectoDetalle> = {}) =>
    proyecto({
      estado: "ESCENAS", voz_disponible: true, subtitulos: "1\nhola",
      metadatos: { youtube: { titulo: "t", descripcion: "d", etiquetas: [] },
                   tiktok: { descripcion: "d" } },
      personajes: [{ clave: "ANA", nombre: "Ana", ficha: "a tall woman", tipo: "persona",
                     retrato: false }],
      ...extra,
    });

  const abrir = async (p = conReparto()) => {
    m.detalleProyecto.mockResolvedValue(p);
    await montar();
    await userEvent.click(await screen.findByText("Mi proyecto"));
    await screen.findByText("Reparto");
  };

  it("traer a alguien lo mete en el proyecto abierto y recarga el detalle", async () => {
    m.listarReparto.mockResolvedValue([
      { slug: "ana-narradora", nombre: "Ana narradora", clave: "ANA", ficha: "f",
        tipo: "persona", retrato: true }]);
    m.traerDelReparto.mockResolvedValue({ clave: "ANA_2", renombrado: false, retrato: true });
    await abrir();
    m.detalleProyecto.mockClear();

    await userEvent.click(screen.getByRole("button", { name: "Traer" }));

    await waitFor(() => expect(m.traerDelReparto).toHaveBeenCalledWith("ana-narradora", 1));
    await waitFor(() => expect(m.detalleProyecto).toHaveBeenCalledWith(1));
  });

  it("si su clave estaba ocupada, avisa con la clave que sí entró", async () => {
    const avisar = vi.fn();
    vi.stubGlobal("alert", avisar);
    m.listarReparto.mockResolvedValue([
      { slug: "ana-narradora", nombre: "Ana narradora", clave: "ANA", ficha: "f",
        tipo: "persona", retrato: false }]);
    m.traerDelReparto.mockResolvedValue({ clave: "ANA_2", renombrado: true, retrato: false });
    await abrir();

    await userEvent.click(screen.getByRole("button", { name: "Traer" }));

    await waitFor(() => expect(avisar).toHaveBeenCalledWith(expect.stringContaining("{ANA_2}")));
  });

  it("guardar en el reparto pregunta el nombre y lo manda", async () => {
    vi.stubGlobal("prompt", vi.fn().mockReturnValue("  Ana narradora  "));
    m.promoverAlReparto.mockResolvedValue({ slug: "ana-narradora", nombre: "Ana narradora", retrato: true });
    await abrir();
    m.listarReparto.mockClear();

    await userEvent.click(screen.getByRole("button", { name: "Guardar en el reparto" }));

    await waitFor(() => expect(m.promoverAlReparto).toHaveBeenCalledWith(1, "ANA", "Ana narradora"));
    await waitFor(() => expect(m.listarReparto).toHaveBeenCalled());
  });

  it("cancelar el nombre no guarda nada", async () => {
    vi.stubGlobal("prompt", vi.fn().mockReturnValue(null));
    await abrir();
    await userEvent.click(screen.getByRole("button", { name: "Guardar en el reparto" }));
    expect(m.promoverAlReparto).not.toHaveBeenCalled();
  });

  it("actualizar en el reparto pide confirmación y dice que los vídeos hechos no cambian", async () => {
    const confirmar = vi.fn().mockReturnValue(true);
    vi.stubGlobal("confirm", confirmar);
    m.actualizarEnReparto.mockResolvedValue({ slug: "ana-narradora", nombre: "Ana", retrato: true });
    await abrir(conReparto({
      personajes: [{ clave: "ANA", nombre: "Ana", ficha: "a tall woman", tipo: "persona",
                     retrato: true, reparto_slug: "ana-narradora" }],
    }));

    await userEvent.click(screen.getByRole("button", { name: "Actualizar en el reparto" }));

    expect(confirmar).toHaveBeenCalledWith(expect.stringContaining("NO cambian"));
    await waitFor(() => expect(m.actualizarEnReparto).toHaveBeenCalledWith("ana-narradora", 1, "ANA"));
  });

  it("borrar del reparto pide confirmación y refresca el listado", async () => {
    m.listarReparto.mockResolvedValue([
      { slug: "ana-narradora", nombre: "Ana narradora", clave: "ANA", ficha: "f",
        tipo: "persona", retrato: false }]);
    m.borrarDelReparto.mockResolvedValue({ slug: "ana-narradora", personajes_desvinculados: 2 });
    await abrir();
    m.listarReparto.mockClear();

    await userEvent.click(
      screen.getByRole("button", { name: "Borrar a Ana narradora del reparto propio" }));

    await waitFor(() => expect(m.borrarDelReparto).toHaveBeenCalledWith("ana-narradora"));
    await waitFor(() => expect(m.listarReparto).toHaveBeenCalled());
  });

  it("si traer falla, el error se ve", async () => {
    m.listarReparto.mockResolvedValue([
      { slug: "ana-narradora", nombre: "Ana narradora", clave: "ANA", ficha: "f",
        tipo: "persona", retrato: false }]);
    m.traerDelReparto.mockRejectedValue(new Error("HTTP 404"));
    await abrir();
    await userEvent.click(screen.getByRole("button", { name: "Traer" }));
    expect(await screen.findByText("HTTP 404")).toBeInTheDocument();
  });
});
