// La UI del autopiloto: el formulario con el que se lanza, la tira que cuenta
// qué está haciendo dentro del proyecto, y lo que la cabecera dice de un lote.
import { render, screen, waitFor, within } from "@testing-library/svelte";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api", async (o) => ({
  ...(await o<typeof import("@/lib/api")>()),
  api: vi.fn().mockResolvedValue([]),
}));

import { api } from "@/lib/api";
import type { Autopiloto, Lote } from "@/lib/autopiloto";
import type { ProyectoDetalle, Voz } from "@/lib/proyectos";
import type { Job } from "@/lib/types";
import { jobs, lotes, modo } from "@/lib/stores";
import AutopilotoForm from "../videos/AutopilotoForm.svelte";
import AutopilotoPanel from "../videos/AutopilotoPanel.svelte";
import IdeasView from "../videos/IdeasView.svelte";
import BotonParar from "../shell/BotonParar.svelte";
import ColaPanel from "../shell/ColaPanel.svelte";
import Workspace from "../shell/Workspace.svelte";

const apiMock = vi.mocked(api);

const voces: Voz[] = [
  { slug: "ana", nombre: "Ana", instruct: "", estado: "lista", disponible: true },
  { slug: "a-medias", nombre: "A medias", instruct: "", estado: "generando", disponible: false },
];

const auto = (extra: Partial<Autopiloto> = {}): Autopiloto => ({
  id: 1, proyecto_id: 7, lote_id: null, estado: "corriendo", modo_video: "kenburns",
  motor: "", paradas: ["idea", "guion", "escenas"], etapa: "", motivo: "", parada: "",
  ...extra,
});

const proyecto = (extra: Partial<ProyectoDetalle> = {}): ProyectoDetalle =>
  ({
    id: 7, slug: "demo", estado: "IDEA", plantilla: "curiosidades", serie: null,
    resumen_episodio: "", voz: "ana", voz_instruct: "",
    idea: { titulo: "Una idea", gancho: "g", resumen: "r" },
    guion: null, guion_version: 0, metadatos: null, voz_disponible: false,
    voz_version: 0, subtitulos: null, escenas: [], personajes: [],
    imagenes_completas: false, musica: null, musica_mezclar: false,
    video_disponible: false, versiones: [], jobs_activos: 0, job_activo: null,
    autopiloto: null, ...extra,
  }) as ProyectoDetalle;

const lote = (extra: Partial<Lote> = {}): Lote => ({
  id: 1, tema_id: 2, tema: "el espacio", total: 4, pendientes: 2, esperando: 0,
  hechos: 1, errores: 0, parados: 0,
  actual: { proyecto_id: 9, titulo: "Un vídeo", etapa: "generar_voz", posicion: 2 },
  proyectos: [], ...extra,
});

const job = (id: number, extra: Partial<Job> = {}): Job =>
  ({ id, tipo: "generar_imagenes", estado: "pendiente", intentos: 0,
     sin_corte: null, progreso: null, ...extra });

beforeEach(() => {
  apiMock.mockClear();
  apiMock.mockResolvedValue([]);
  jobs.set([]);
  lotes.set([]);
  modo.set("videos");
  vi.spyOn(window, "confirm").mockReturnValue(true);
});

describe("AutopilotoForm", () => {
  it("arranca con las tres paradas puestas: es lo que ya hace el flujo a mano", async () => {
    const onlanzar = vi.fn();
    render(AutopilotoForm, { props: { voces, onlanzar } });

    for (const n of ["Elegir las ideas", "Revisar el guion", "Revisar los prompts de escena"]) {
      expect(screen.getByLabelText(new RegExp(n)) as HTMLInputElement).toBeChecked();
    }

    await userEvent.click(screen.getByRole("button", { name: "Lanzar autopiloto" }));

    expect(onlanzar).toHaveBeenCalledWith({
      modo: "kenburns", motor: "", voz: "", paradas: ["idea", "guion", "escenas"],
    });
  });

  it("quitar las tres es producción sin manos, y se dice", async () => {
    const onlanzar = vi.fn();
    render(AutopilotoForm, { props: { voces, onlanzar } });

    for (const n of ["Elegir las ideas", "Revisar el guion", "Revisar los prompts de escena"]) {
      await userEvent.click(screen.getByLabelText(new RegExp(n)));
    }

    expect(screen.getByText(/sin preguntar nada/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Lanzar autopiloto" }));
    expect(onlanzar).toHaveBeenCalledWith(
      expect.objectContaining({ paradas: [] }),
    );
  });

  it("solo ofrece voces listas, y la que ya tiene el proyecto viene elegida", () => {
    render(AutopilotoForm, { props: { voces, vozActual: "ana", onlanzar: vi.fn() } });
    const select = screen.getByLabelText("Voz de la narración") as HTMLSelectElement;

    expect(select.value).toBe("ana");
    expect(within(select).queryByText("A medias")).toBeNull();
    expect(within(select).getByText("Ana")).toBeInTheDocument();
  });

  it("el motor solo se pregunta en los modos que animan con i2v", async () => {
    apiMock.mockResolvedValue([
      { id: "ltx25", nombre: "LTX 2.5", frames: 97, fps_origen: 24, defecto: true },
      { id: "hunyuan", nombre: "Hunyuan", frames: 65, fps_origen: 24, defecto: false },
    ]);
    render(AutopilotoForm, { props: { voces, onlanzar: vi.fn() } });
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith("/proyectos/motores-i2v"));

    expect(screen.queryByLabelText("Motor de movimiento")).toBeNull();

    await userEvent.selectOptions(screen.getByLabelText("Modo de montaje"), "i2v");

    expect(screen.getByLabelText("Motor de movimiento")).toBeInTheDocument();
  });

  it("el modo y el motor elegidos llegan a quien lanza", async () => {
    apiMock.mockResolvedValue([
      { id: "ltx25", nombre: "LTX 2.5", frames: 97, fps_origen: 24, defecto: true },
      { id: "hunyuan", nombre: "Hunyuan", frames: 65, fps_origen: 24, defecto: false },
    ]);
    const onlanzar = vi.fn();
    render(AutopilotoForm, { props: { voces, onlanzar } });
    await waitFor(() => expect(apiMock).toHaveBeenCalled());

    await userEvent.selectOptions(screen.getByLabelText("Modo de montaje"), "i2v");
    await userEvent.selectOptions(screen.getByLabelText("Motor de movimiento"), "hunyuan");
    await userEvent.selectOptions(screen.getByLabelText("Voz de la narración"), "ana");
    await userEvent.click(screen.getByRole("button", { name: "Lanzar autopiloto" }));

    expect(onlanzar).toHaveBeenCalledWith(
      expect.objectContaining({ modo: "i2v", motor: "hunyuan", voz: "ana" }),
    );
  });
});

describe("AutopilotoPanel", () => {
  const acciones = () => ({
    onlanzar: vi.fn(), oncontinuar: vi.fn(), ondetener: vi.fn(),
  });

  it("sin tirada en marcha solo ofrece lanzarla, con el formulario cerrado", async () => {
    render(AutopilotoPanel, { props: { p: proyecto(), voces, ...acciones() } });

    expect(screen.queryByLabelText("Modo de montaje")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Lanzar…" }));
    expect(screen.getByLabelText("Modo de montaje")).toBeInTheDocument();
  });

  it("corriendo dice en qué etapa va y deja detenerlo", () => {
    const props = { p: proyecto({ autopiloto: auto({ etapa: "generar_voz" }) }), voces, ...acciones() };
    render(AutopilotoPanel, { props });

    expect(screen.getByText("En automático")).toBeInTheDocument();
    expect(screen.getByText("Generando la narración…")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Detener autopiloto" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Visto, continuar" })).toBeNull();
  });

  it("parado en una revisión dice por qué y ofrece continuar", async () => {
    const acc = acciones();
    render(AutopilotoPanel, {
      props: {
        p: proyecto({
          autopiloto: auto({
            estado: "esperando", etapa: "generar_guion", parada: "guion",
            motivo: "Esperando que revises el guion",
          }),
        }),
        voces, ...acc,
      },
    });

    expect(screen.getByText("Esperando tu revisión")).toBeInTheDocument();
    expect(screen.getByText("Esperando que revises el guion")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Visto, continuar" }));

    expect(acc.oncontinuar).toHaveBeenCalled();
  });

  it("un fallo deja escrito el motivo y permite relanzarlo", () => {
    render(AutopilotoPanel, {
      props: {
        p: proyecto({
          autopiloto: auto({ estado: "error", motivo: "Falló «armar_video»: ffmpeg se quejó" }),
        }),
        voces, ...acciones(),
      },
    });

    expect(screen.getByText(/ffmpeg se quejó/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Volver a lanzarlo" })).toBeInTheDocument();
  });

  it("si es parte de un lote avisa de que los demás siguen su turno", () => {
    render(AutopilotoPanel, {
      props: { p: proyecto({ autopiloto: auto({ lote_id: 3 }) }), voces, ...acciones() },
    });

    expect(screen.getByText(/los demás siguen su turno/)).toBeInTheDocument();
  });

  it("lanzar desde el panel cierra el formulario y pasa las opciones", async () => {
    const acc = acciones();
    render(AutopilotoPanel, { props: { p: proyecto(), voces, ...acc } });
    await userEvent.click(screen.getByRole("button", { name: "Lanzar…" }));

    await userEvent.click(screen.getByRole("button", { name: "Lanzar autopiloto" }));

    expect(acc.onlanzar).toHaveBeenCalledWith(
      expect.objectContaining({ modo: "kenburns" }),
    );
    expect(screen.queryByLabelText("Modo de montaje")).toBeNull();
  });
});

describe("el lote desde las ideas", () => {
  const ideas = [
    { id: 1, titulo: "A", gancho: "g", resumen: "r", estado: "aprobada", proyecto_id: null },
    { id: 2, titulo: "B", gancho: "g", resumen: "r", estado: "propuesta", proyecto_id: null },
  ];

  it("cuenta cuántas ideas aprobadas entrarían", () => {
    render(IdeasView, {
      props: {
        ideas, voces, onaprobar: vi.fn(), ondescartar: vi.fn(), onrestaurar: vi.fn(),
        onabrirproyecto: vi.fn(), onmas: vi.fn(), onlote: vi.fn(),
      },
    });

    expect(screen.getByText(/Producir en lote \(1 idea aprobada\)/)).toBeInTheDocument();
  });

  it("sin manejador de lote no se ofrece: la vista también se usa sin él", () => {
    render(IdeasView, {
      props: {
        ideas, voces, onaprobar: vi.fn(), ondescartar: vi.fn(), onrestaurar: vi.fn(),
        onabrirproyecto: vi.fn(), onmas: vi.fn(),
      },
    });

    expect(screen.queryByText(/Producir en lote/)).toBeNull();
  });

  it("produce el lote con las opciones elegidas", async () => {
    const onlote = vi.fn();
    render(IdeasView, {
      props: {
        ideas, voces, onaprobar: vi.fn(), ondescartar: vi.fn(), onrestaurar: vi.fn(),
        onabrirproyecto: vi.fn(), onmas: vi.fn(), onlote,
      },
    });

    await userEvent.click(screen.getByRole("button", { name: "Producir el lote" }));

    expect(onlote).toHaveBeenCalledWith(
      expect.objectContaining({ paradas: ["idea", "guion", "escenas"] }),
    );
  });
});

describe("la cabecera con un lote en marcha", () => {
  it("el chip cuenta por qué vídeo va", () => {
    jobs.set([job(1, { estado: "corriendo" })]);
    lotes.set([lote()]);
    render(ColaPanel);

    expect(screen.getByRole("button", { name: /vídeo 2 de 4/ })).toBeInTheDocument();
  });

  it("con la cola vacía y el lote esperando revisión lo dice en vez de '0 en cola'", () => {
    lotes.set([lote({ actual: null, pendientes: 0, esperando: 3 })]);
    render(ColaPanel);

    expect(screen.getByRole("button", { name: /3 esperando revisión/ })).toBeInTheDocument();
    expect(screen.queryByText(/0 en cola/)).toBeNull();
  });

  it("el panel dice en qué proyecto va, en qué etapa y cuántos quedan", async () => {
    jobs.set([job(1, { estado: "corriendo" })]);
    lotes.set([lote({ esperando: 1, errores: 1 })]);
    render(ColaPanel);

    await userEvent.click(screen.getByRole("button", { name: /en cola|vídeo/ }));

    const panel = screen.getByRole("region", { name: "Cola de trabajos" });
    expect(within(panel).getByText(/el espacio/)).toBeInTheDocument();
    expect(within(panel).getByText(/1 de 4 hechos/)).toBeInTheDocument();
    expect(within(panel).getByText(/Un vídeo/)).toBeInTheDocument();
    expect(within(panel).getByText(/Generando la narración…/)).toBeInTheDocument();
    expect(
      within(panel).getByText(/2 por empezar, 1 esperando revisión, 1 con fallo/),
    ).toBeInTheDocument();
  });

  it("la cabecera aparece con un lote vivo aunque la cola esté vacía", () => {
    lotes.set([lote({ actual: null, pendientes: 2 })]);
    render(Workspace);

    expect(screen.getByRole("button", { name: /lote/ })).toBeInTheDocument();
  });
});

describe("parar con un lote en marcha", () => {
  it("el aviso dice cuántos autopilotos se apagan y qué se conserva", async () => {
    jobs.set([job(1, { estado: "corriendo" })]);
    lotes.set([lote({ pendientes: 2, esperando: 1 })]);
    render(BotonParar);

    await userEvent.click(screen.getByRole("button", { name: "Parar" }));

    const aviso = vi.mocked(window.confirm).mock.calls[0][0] as string;
    expect(aviso).toContain("el autopiloto de 4 vídeos");
    expect(aviso).toContain("los retoma donde estén");
  });

  it("detener lo actual avisa de que el lote sigue con el siguiente", async () => {
    jobs.set([job(1, { estado: "corriendo" })]);
    lotes.set([lote()]);
    render(BotonParar, { props: { soloCorriendo: true, etiqueta: "Detener lo actual" } });

    await userEvent.click(screen.getByRole("button", { name: "Detener lo actual" }));

    const aviso = vi.mocked(window.confirm).mock.calls[0][0] as string;
    expect(aviso).toContain("El lote sigue su curso");
  });

  it("con la cola vacía pero un lote vivo todavía se puede parar todo", () => {
    lotes.set([lote({ actual: null, pendientes: 2 })]);
    render(BotonParar);

    expect(screen.getByRole("button", { name: "Parar" })).toBeInTheDocument();
  });
});
