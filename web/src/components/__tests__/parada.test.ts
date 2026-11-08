import { render, screen, waitFor, within } from "@testing-library/svelte";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api", async (o) => ({
  ...(await o<typeof import("@/lib/api")>()),
  api: vi.fn().mockResolvedValue([]),
}));

import { api } from "@/lib/api";
import type { Job, JobHistorial, ProgresoJob } from "@/lib/types";
import type { ProyectoDetalle } from "@/lib/proyectos";
import { jobs, modo } from "@/lib/stores";
import BotonParar from "../shell/BotonParar.svelte";
import ColaPanel from "../shell/ColaPanel.svelte";
import Workspace from "../shell/Workspace.svelte";
import ProjectView from "../videos/ProjectView.svelte";
import MusicStudio from "../musica/MusicStudio.svelte";
import ImageStudio from "../imagenes/ImageStudio.svelte";

const apiMock = vi.mocked(api);

const job = (id: number, extra: Partial<Job> = {}): Job =>
  ({ id, tipo: "generar_imagenes", ref_id: 1, estado: "pendiente", intentos: 0, sin_corte: null,
     progreso: null, ...extra });
const progreso = (extra: Partial<ProgresoJob> = {}): ProgresoJob =>
  ({ job_id: 1, transcurrido_s: 30, fase: "imagen 2 de 4", hecho: 1, total: 4, pct: 25, eta_s: 60, ...extra });
const hecho = (id: number, extra: Partial<JobHistorial> = {}): JobHistorial =>
  ({ ...job(id), estado: "ok", intentos: 1, log: "listo", ...extra });

beforeEach(() => {
  apiMock.mockClear();
  apiMock.mockResolvedValue([]);
  jobs.set([]);
  modo.set("biblioteca");
  vi.spyOn(window, "confirm").mockReturnValue(true);
});

describe("BotonParar", () => {
  it("sin nada en la cola no se pinta: no hay nada que parar", () => {
    render(BotonParar);
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("parar pide confirmación y, si se acepta, vacía la cola y corta lo que corre", async () => {
    jobs.set([job(1, { estado: "corriendo" }), job(2), job(3)]);
    render(BotonParar);

    await userEvent.click(screen.getByRole("button", { name: "Parar" }));

    expect(apiMock).toHaveBeenCalledWith("/jobs/parar", {
      method: "POST",
      body: { corriendo: true, pendientes: true },
    });
  });

  it("el aviso dice cuántos trabajos se descartan y qué se conserva", async () => {
    jobs.set([job(1, { estado: "corriendo" }), job(2), job(3)]);
    render(BotonParar);

    await userEvent.click(screen.getByRole("button", { name: "Parar" }));

    const aviso = vi.mocked(window.confirm).mock.calls[0][0] as string;
    expect(aviso).toContain("se descartan los 2 trabajos");
    expect(aviso).toContain("Se conserva todo lo ya terminado");
    expect(aviso).toContain("hay que repetirlo");
  });

  it("si se cancela la confirmación no se para nada", async () => {
    vi.mocked(window.confirm).mockReturnValue(false);
    jobs.set([job(1, { estado: "corriendo" })]);
    render(BotonParar);

    await userEvent.click(screen.getByRole("button", { name: "Parar" }));

    expect(apiMock).not.toHaveBeenCalled();
  });

  it("en modo 'solo lo actual' deja la cola esperando", async () => {
    jobs.set([job(1, { estado: "corriendo" }), job(2)]);
    render(BotonParar, { soloCorriendo: true, etiqueta: "Detener lo actual" });

    await userEvent.click(screen.getByRole("button", { name: "Detener lo actual" }));

    expect(apiMock).toHaveBeenCalledWith("/jobs/parar", {
      method: "POST",
      body: { corriendo: true, pendientes: false },
    });
    const aviso = vi.mocked(window.confirm).mock.calls[0][0] as string;
    expect(aviso).toContain("1 trabajos que esperan en la cola siguen esperando");
  });

  it("si la etapa en curso no se puede cortar a mitad, el aviso lo dice", async () => {
    jobs.set([job(1, { estado: "corriendo", tipo: "generar_voz", sin_corte: "la síntesis de la narración" })]);
    render(BotonParar);
    expect(screen.getByRole("button", { name: "Parar" })).toHaveAttribute(
      "title",
      "la síntesis de la narración no se puede cortar a mitad: se para en cuanto termine",
    );

    await userEvent.click(screen.getByRole("button", { name: "Parar" }));

    const aviso = vi.mocked(window.confirm).mock.calls[0][0] as string;
    expect(aviso).toContain("la síntesis de la narración ya está en marcha y no se puede cortar");
    expect(aviso).toContain("Se para en cuanto termine");
  });

  it("un fallo del backend se dice en vez de quedarse en silencio", async () => {
    apiMock.mockRejectedValueOnce(new Error("backend caído"));
    jobs.set([job(1, { estado: "corriendo" })]);
    render(BotonParar);

    await userEvent.click(screen.getByRole("button", { name: "Parar" }));

    expect(await screen.findByText("backend caído")).toBeInTheDocument();
  });
});

describe("ColaPanel", () => {
  const abrir = () => userEvent.click(screen.getByTitle(/Trabajos en cola/));

  it("el chip abre el panel y pide el historial", async () => {
    jobs.set([job(1, { estado: "corriendo", progreso: progreso() })]);
    render(ColaPanel);
    expect(screen.queryByRole("region", { name: "Cola de trabajos" })).toBeNull();

    await abrir();

    expect(apiMock).toHaveBeenCalledWith("/jobs/historial?limite=8");
    const panel = screen.getByRole("region", { name: "Cola de trabajos" });
    expect(panel).toHaveTextContent("Imágenes de escena");
    expect(panel).toHaveTextContent("imagen 2 de 4");
  });

  it("enseña lo que espera y los dos modos de parada", async () => {
    jobs.set([job(1, { estado: "corriendo" }), job(2, { tipo: "armar_video" })]);
    render(ColaPanel);

    await abrir();

    const panel = screen.getByRole("region", { name: "Cola de trabajos" });
    expect(panel).toHaveTextContent("1 esperando: Montaje final");
    expect(within(panel).getByRole("button", { name: "Detener lo actual" })).toBeInTheDocument();
    expect(within(panel).getByRole("button", { name: "Parar todo y vaciar la cola" })).toBeInTheDocument();
  });

  it("el panel avisa de la etapa que no se corta a mitad", async () => {
    jobs.set([job(1, { estado: "corriendo", tipo: "generar_voz", sin_corte: "la síntesis de la narración" })]);
    render(ColaPanel);

    await abrir();

    expect(screen.getByRole("region", { name: "Cola de trabajos" })).toHaveTextContent(
      "la síntesis de la narración no se puede cortar a mitad",
    );
  });

  it("avisa de que un job va por su segundo intento", async () => {
    jobs.set([job(1, { estado: "corriendo", intentos: 2 })]);
    render(ColaPanel);

    await abrir();

    expect(screen.getByRole("region", { name: "Cola de trabajos" })).toHaveTextContent("intento 2");
  });

  it("el historial distingue parado de error y cuenta los intentos", async () => {
    apiMock.mockResolvedValue([
      hecho(9, { tipo: "generar_i2v", estado: "cancelado", log: "Parado desde la interfaz" }),
      hecho(8, { tipo: "generar_clips", estado: "error", intentos: 3, log: "Falló 3 veces" }),
      hecho(7, { tipo: "generar_musica" }),
    ]);
    jobs.set([job(1, { estado: "corriendo" })]);
    render(ColaPanel);

    await abrir();

    const panel = await screen.findByRole("region", { name: "Cola de trabajos" });
    const fila = (texto: string) =>
      within(panel).getByText(texto).parentElement as HTMLElement;
    expect(fila("Clips animados (i2v)")).toHaveTextContent("Parado");
    expect(fila("Clips Ken Burns")).toHaveTextContent("Error");
    expect(fila("Clips Ken Burns")).toHaveTextContent("3 intentos");
    expect(fila("Pista de música")).toHaveTextContent("Hecho");
    // "Parado" no se pinta como un error: pararlo fue una decisión.
    expect(within(fila("Clips animados (i2v)")).getByText("Parado").className).toContain("text-warn");
    expect(within(fila("Clips Ken Burns")).getByText("Error").className).toContain("text-danger");
  });

  it("si el historial falla, el panel sigue sirviendo para parar", async () => {
    apiMock.mockRejectedValue(new Error("sin historial"));
    jobs.set([job(1, { estado: "corriendo" })]);
    render(ColaPanel);

    await abrir();

    const panel = screen.getByRole("region", { name: "Cola de trabajos" });
    expect(within(panel).getByRole("button", { name: "Detener lo actual" })).toBeInTheDocument();
  });

  it("se cierra al pulsar fuera", async () => {
    jobs.set([job(1, { estado: "corriendo" })]);
    render(ColaPanel);
    await abrir();

    await userEvent.click(screen.getByRole("button", { name: "Cerrar el panel de la cola" }));

    expect(screen.queryByRole("region", { name: "Cola de trabajos" })).toBeNull();
  });
});

describe("dónde aparece la parada", () => {
  it("la cabecera la lleva junto al chip de la cola, en cualquier sección", async () => {
    jobs.set([job(1, { estado: "corriendo" })]);
    for (const m of ["videos", "imagenes", "musica"] as const) {
      modo.set(m);
      const { unmount } = render(Workspace);
      // Acotado a la cabecera: Música e Imágenes llevan además el suyo en la
      // barra de su lista.
      const cabecera = screen.getByTitle(/Trabajos en cola/).closest("header")!;
      expect(within(cabecera).getByRole("button", { name: "Parar" })).toBeInTheDocument();
      unmount();
    }
  });

  it("Música la lleva en la barra de la lista", async () => {
    jobs.set([job(1, { estado: "corriendo", tipo: "generar_musica" })]);
    render(MusicStudio);
    await waitFor(() => expect(screen.getByRole("button", { name: "Parar" })).toBeInTheDocument());
  });

  it("Imágenes la lleva en la barra de la lista", async () => {
    jobs.set([job(1, { estado: "corriendo", tipo: "generar_previews_imagen" })]);
    render(ImageStudio);
    await waitFor(() => expect(screen.getByRole("button", { name: "Parar" })).toBeInTheDocument());
  });

  it("Vídeos la lleva junto a la etapa en curso del proyecto", () => {
    jobs.set([job(1, { estado: "corriendo" })]);
    const p = {
      id: 1, slug: "demo", estado: "ESCENAS", plantilla: "curiosidades", voz: null, voz_instruct: "",
      idea: { titulo: "Un título", gancho: "g", resumen: "r" },
      guion: null, guion_version: 0, metadatos: null, voz_disponible: false, voz_version: 0,
      subtitulos: null, escenas: [], personajes: [], imagenes_completas: false,
      video_disponible: false, versiones: [], jobs_activos: 1, job_activo: "generar_imagenes",
      musica: null, musica_mezclar: false,
      publicacion: null, disco: { total_mb: 0, liberable_mb: 0 }, liberado: false, serie: null, resumen_episodio: "",
    } as ProyectoDetalle;

    render(ProjectView, { p, voces: [], acciones: new Proxy({}, { get: () => vi.fn() }) as never, onver: vi.fn() });

    expect(screen.getByText("Generando las imágenes…")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Parar" })).toBeInTheDocument();
  });

  it("sin cola, ninguna sección la pinta", () => {
    modo.set("videos");
    render(Workspace);
    expect(screen.queryByRole("button", { name: "Parar" })).toBeNull();
  });
});
