import { render, screen } from "@testing-library/svelte";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { MusicaProyecto, ProyectoDetalle } from "@/lib/proyectos";
import StepMusica from "../videos/steps/StepMusica.svelte";

const listarMusica = vi.fn();
vi.mock("@/lib/musica", () => ({ listarMusica: () => listarMusica() }));

const proy = (extra: Partial<ProyectoDetalle> = {}): ProyectoDetalle => ({
  id: 7, slug: "demo", estado: "VOZ", plantilla: "curiosidades", voz: null, voz_instruct: "",
  idea: null, guion: { gancho: "g", cta: "c" }, guion_version: 1, metadatos: null,
  voz_disponible: true, voz_version: 0, subtitulos: null, escenas: [], personajes: [],
  imagenes_completas: false, musica: null, musica_mezclar: false,
  publicacion: null, disco: { total_mb: 0, liberable_mb: 0 }, liberado: false, video_disponible: false,
  serie: null, resumen_episodio: "",
  versiones: [], jobs_activos: 0, job_activo: null, ...extra,
});

const pista = (extra: Partial<MusicaProyecto> = {}): MusicaProyecto => ({
  id: 3, idea: "Banda sonora de «La fosa»", tags: "dark hybrid orchestral", lyrics: "[Intro]",
  duracion_s: 45, bpm: 88, keyscale: "E minor", estado: "generada", tiene_audio: true,
  tiene_portada: false, ocupado: false, ...extra,
});

const props = () => ({ ongenerar: vi.fn(), onfijar: vi.fn() });

beforeEach(() => {
  listarMusica.mockResolvedValue([]);
});

describe("generar", () => {
  it("sin música ofrece generarla y no enseña reproductor", () => {
    const { container } = render(StepMusica, { p: proy(), ...props() });
    expect(screen.getByRole("button", { name: "Generar la música" })).toBeEnabled();
    expect(container.querySelector("audio")).toBeNull();
  });

  it("con pista hecha el botón pasa a rehacerla", async () => {
    const a = props();
    render(StepMusica, { p: proy({ musica: pista() }), ...a });
    await userEvent.click(screen.getByRole("button", { name: "Rehacer la música" }));
    expect(a.ongenerar).toHaveBeenCalled();
  });

  it("mientras la pista está en la cola no se puede volver a pedir", () => {
    render(StepMusica, { p: proy({ musica: pista({ ocupado: true }) }), ...props() });
    expect(screen.getByRole("button", { name: "Rehacer la música" })).toBeDisabled();
    expect(screen.getByText("Componiendo la pista…")).toBeInTheDocument();
  });
});

describe("la pista suelta", () => {
  it("se escucha y se descarga sola, con el nombre del proyecto", () => {
    const { container } = render(StepMusica, { p: proy({ musica: pista() }), bust: 42, ...props() });
    expect(container.querySelector("audio")).toHaveAttribute("src", "/api/musica/3/audio?v=42");
    const enlace = screen.getByRole("link", { name: /Descargar la pista sola/ });
    expect(enlace).toHaveAttribute("download", "demo-musica");
    expect(enlace).toHaveAttribute("href", "/api/musica/3/audio?v=42");
  });

  it("enseña duración, tempo y tonalidad, y avisa si aún no hay audio", () => {
    const { container } = render(StepMusica, {
      p: proy({ musica: pista({ tiene_audio: false }) }), ...props(),
    });
    expect(screen.getByText(/45s · 88 BPM · E minor/)).toBeInTheDocument();
    expect(screen.getByText("sin audio todavía")).toBeInTheDocument();
    expect(container.querySelector("audio")).toBeNull();
  });
});

describe("mezclar en el vídeo", () => {
  it("activarla manda la pista y el interruptor", async () => {
    const a = props();
    render(StepMusica, { p: proy({ musica: pista() }), ...a });
    await userEvent.click(screen.getByRole("checkbox"));
    expect(a.onfijar).toHaveBeenCalledWith(3, true);
  });

  it("no se puede mezclar una pista sin audio", () => {
    render(StepMusica, { p: proy({ musica: pista({ tiene_audio: false }) }), ...props() });
    expect(screen.getByRole("checkbox")).toBeDisabled();
  });
});

describe("reutilizar una pista de la biblioteca", () => {
  it("lista solo las generadas y manda la elegida", async () => {
    listarMusica.mockResolvedValue([
      { id: 1, idea: "una hecha", tipo: "instrumental", estado: "generada", tiene_portada: false },
      { id: 2, idea: "a medias", tipo: "instrumental", estado: "nueva", tiene_portada: false },
    ]);
    const a = props();
    render(StepMusica, { p: proy(), ...a });
    const sel = await screen.findByLabelText(/O usar una pista que ya tengas/);
    expect([...(sel as HTMLSelectElement).options].map((o) => o.text)).toEqual([
      "— sin música —", "una hecha",
    ]);
    await userEvent.selectOptions(sel, "1");
    expect(a.onfijar).toHaveBeenCalledWith(1, false);
  });

  it("soltar la pista apaga también la mezcla", async () => {
    listarMusica.mockResolvedValue([
      { id: 3, idea: "la del proyecto", tipo: "instrumental", estado: "generada", tiene_portada: false },
    ]);
    const a = props();
    render(StepMusica, { p: proy({ musica: pista(), musica_mezclar: true }), ...a });
    const sel = await screen.findByLabelText(/O usar una pista que ya tengas/);
    await userEvent.selectOptions(sel, "");
    expect(a.onfijar).toHaveBeenCalledWith(null, false);
  });

  it("sin pistas generadas no hay selector", () => {
    render(StepMusica, { p: proy(), ...props() });
    expect(screen.queryByLabelText(/O usar una pista que ya tengas/)).toBeNull();
  });
});
