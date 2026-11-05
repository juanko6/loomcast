import { render, screen, waitFor, within } from "@testing-library/svelte";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/musica", async (o) => {
  const real = await o<typeof import("@/lib/musica")>();
  return {
    ...real,
    listarMusica: vi.fn(), detalleMusica: vi.fn(), crearMusica: vi.fn(), editarMusica: vi.fn(),
    mejorarMusica: vi.fn(), generarMusica: vi.fn(), borrarMusica: vi.fn(),
  };
});
vi.mock("@/lib/api", async (o) => ({ ...(await o<typeof import("@/lib/api")>()), api: vi.fn().mockResolvedValue([]) }));

import * as m from "@/lib/musica";
import type { MusicaDetalle } from "@/lib/musica";
import { currentTrack } from "@/lib/player";
import { jobs, jobsDrenados, seleccionPendiente } from "@/lib/stores";
import MusicConfig from "../musica/MusicConfig.svelte";
import MusicStudio from "../musica/MusicStudio.svelte";

const detalle = (extra: Partial<MusicaDetalle> = {}): MusicaDetalle => ({
  id: 4, tipo: "instrumental", idea: "lofi triste", tags: "warm lofi piano", lyrics: "[Intro]", duracion_s: 60,
  seed: null, estado: "nueva", tiene_audio: false, tiene_portada: false, ocupado: false,
  bpm: 90, keyscale: "A minor", timesig: "3", idioma: "en", ...extra,
});
const resumen = (id: number, idea: string, extra = {}) =>
  ({ id, idea, tipo: "instrumental" as const, estado: "nueva", tiene_portada: false, ...extra });

describe("MusicConfig", () => {
  const props = () => ({ oncreate: vi.fn(), onsuggest: vi.fn(), ongenerate: vi.fn() });

  describe("pista nueva", () => {
    it("pide la idea y tiene 'Crear pista' bloqueado mientras esté vacía", async () => {
      render(MusicConfig, { detail: null, ...props() });
      const crear = screen.getByRole("button", { name: "Crear pista" });
      expect(crear).toBeDisabled();
      await userEvent.type(screen.getByRole("textbox"), "   ");
      expect(crear).toBeDisabled();           // solo espacios no cuenta
      await userEvent.type(screen.getByRole("textbox"), "jazz");
      expect(crear).toBeEnabled();
    });

    it("crea con tipo, idea recortada y duración", async () => {
      const p = props();
      render(MusicConfig, { detail: null, ...p });
      await userEvent.click(screen.getByRole("tab", { name: "Canción" }));
      await userEvent.type(screen.getByRole("textbox"), "  una balada  ");
      const dur = screen.getByLabelText("Duración (segundos)");
      await userEvent.clear(dur);
      await userEvent.type(dur, "45");
      await userEvent.click(screen.getByRole("button", { name: "Crear pista" }));
      expect(p.oncreate).toHaveBeenCalledWith({ tipo: "cancion", idea: "una balada", duracion_s: 45 });
    });

    it("la pregunta cambia según el tipo y no muestra los campos de edición", async () => {
      render(MusicConfig, { detail: null, ...props() });
      expect(screen.getByText("¿Qué música quieres?")).toBeInTheDocument();
      await userEvent.click(screen.getByRole("tab", { name: "Canción" }));
      expect(screen.getByText("¿De qué va la canción?")).toBeInTheDocument();
      expect(screen.queryByLabelText("Tempo (BPM)")).toBeNull();
    });
  });

  describe("pista existente", () => {
    it("rellena el borrador con los datos de la pista", () => {
      render(MusicConfig, { detail: detalle(), ...props() });
      expect(screen.getByText("lofi triste")).toBeInTheDocument();
      expect((screen.getByLabelText(/Descripción de estilo/) as HTMLTextAreaElement).value).toBe("warm lofi piano");
      expect((screen.getByLabelText(/^Estructura/) as HTMLTextAreaElement).value).toBe("[Intro]");
      expect((screen.getByLabelText("Tempo (BPM)") as HTMLInputElement).value).toBe("90");
      expect((screen.getByLabelText("Tonalidad") as HTMLSelectElement).value).toBe("A minor");
      expect((screen.getByLabelText("Compás") as HTMLSelectElement).value).toBe("3");
    });

    it("una canción muestra 'Letra' e idioma; un instrumental, 'Estructura' y sin idioma", () => {
      const { unmount } = render(MusicConfig, { detail: detalle({ tipo: "cancion", idioma: "fr" }), ...props() });
      expect(screen.getByLabelText(/^Letra/)).toBeInTheDocument();
      expect((screen.getByLabelText("Idioma de la letra") as HTMLSelectElement).value).toBe("fr");
      unmount();
      render(MusicConfig, { detail: detalle(), ...props() });
      expect(screen.getByLabelText(/^Estructura/)).toBeInTheDocument();
      expect(screen.queryByLabelText("Idioma de la letra")).toBeNull();
    });

    it("sin título muestra '(pista sin título)'", () => {
      render(MusicConfig, { detail: detalle({ idea: "" }), ...props() });
      expect(screen.getByText("(pista sin título)")).toBeInTheDocument();
    });

    it("'Generar música' manda los campos editados; con audio pasa a 'Regenerar'", async () => {
      const p = props();
      const { rerender } = render(MusicConfig, { detail: detalle(), ...p });
      await userEvent.type(screen.getByLabelText(/Descripción de estilo/), " y bajo");
      await userEvent.click(screen.getByRole("button", { name: "Generar música" }));
      expect(p.ongenerate).toHaveBeenCalledWith({
        tags: "warm lofi piano y bajo", lyrics: "[Intro]", duracion_s: 60,
        bpm: 90, keyscale: "A minor", timesig: "3", idioma: "en",
      });
      await rerender({ detail: detalle({ tiene_audio: true }), ...p });
      expect(screen.getByRole("button", { name: "Regenerar (otra distinta)" })).toBeInTheDocument();
    });

    it("sin descripción de estilo no se puede generar", () => {
      render(MusicConfig, { detail: detalle({ tags: "   " }), ...props() });
      expect(screen.getByRole("button", { name: "Generar música" })).toBeDisabled();
    });

    it("'Sugerir con LLM' manda el borrador (el padre lo guarda antes)", async () => {
      const p = props();
      render(MusicConfig, { detail: detalle(), ...p });
      await userEvent.click(screen.getByRole("button", { name: "Sugerir con LLM" }));
      expect(p.onsuggest).toHaveBeenCalledWith(expect.objectContaining({ tags: "warm lofi piano", bpm: 90 }));
    });

    it("'busy' bloquea sugerir y generar", () => {
      render(MusicConfig, { detail: detalle(), busy: true, ...props() });
      expect(screen.getByRole("button", { name: "Sugerir con LLM" })).toBeDisabled();
      expect(screen.getByRole("button", { name: "Generar música" })).toBeDisabled();
    });

    it("al cambiar de pista (o tras sugerir) el borrador se resincroniza", async () => {
      const p = props();
      const { rerender } = render(MusicConfig, { detail: detalle(), ...p });
      await userEvent.type(screen.getByLabelText(/Descripción de estilo/), " editado");
      await rerender({ detail: detalle({ id: 5, tags: "sugerido por el LLM" }), ...p });
      await waitFor(() => expect((screen.getByLabelText(/Descripción de estilo/) as HTMLTextAreaElement).value).toBe("sugerido por el LLM"));
    });

    it("los combos ofrecen exactamente los valores del backend", () => {
      render(MusicConfig, { detail: detalle({ tipo: "cancion" }), ...props() });
      const opts = (n: string) => within(screen.getByLabelText(n)).getAllByRole("option").map((o) => (o as HTMLOptionElement).value);
      expect(opts("Compás")).toEqual(["2", "3", "4", "6"]);
      expect(opts("Tonalidad")).toEqual(m.KEYSCALES);
      expect(opts("Idioma de la letra")).toEqual(m.IDIOMAS.map((i) => i.value));
    });
  });
});

describe("MusicStudio", () => {
  beforeEach(() => {
    vi.mocked(m.listarMusica).mockResolvedValue([resumen(4, "lofi triste"), resumen(5, "rock duro")]);
    vi.mocked(m.detalleMusica).mockResolvedValue(detalle());
    vi.mocked(m.crearMusica).mockResolvedValue({ id: 9 });
    vi.mocked(m.editarMusica).mockResolvedValue({ ok: true });
    vi.mocked(m.mejorarMusica).mockResolvedValue({ job_id: 1 });
    vi.mocked(m.generarMusica).mockResolvedValue({ job_id: 2 });
    vi.mocked(m.borrarMusica).mockResolvedValue({ borrada: 4, archivos: 0 });
    currentTrack.set(null);
    seleccionPendiente.set(null);
    jobs.set([]);
    jobsDrenados.set(0);
    vi.stubGlobal("confirm", vi.fn().mockReturnValue(true));
  });

  it("carga la lista al montar y cuenta las pistas (singular/plural)", async () => {
    render(MusicStudio);
    expect(await screen.findByText("lofi triste")).toBeInTheDocument();
    expect(screen.getByText("2 pistas")).toBeInTheDocument();
  });

  it("lista vacía: mensaje y '0 pistas'", async () => {
    vi.mocked(m.listarMusica).mockResolvedValue([]);
    render(MusicStudio);
    expect(await screen.findByText(/Sin pistas aún/)).toBeInTheDocument();
    expect(screen.getByText("0 pistas")).toBeInTheDocument();
  });

  it("una sola pista usa el singular", async () => {
    vi.mocked(m.listarMusica).mockResolvedValue([resumen(4, "x")]);
    render(MusicStudio);
    expect(await screen.findByText("1 pista")).toBeInTheDocument();
  });

  it("si la lista falla muestra el error", async () => {
    vi.mocked(m.listarMusica).mockRejectedValue(new Error("HTTP 500"));
    render(MusicStudio);
    expect(await screen.findByText("HTTP 500")).toBeInTheDocument();
  });

  it("seleccionar una pista carga su detalle y la abre en el editor", async () => {
    render(MusicStudio);
    await userEvent.click(await screen.findByText("lofi triste"));
    expect(m.detalleMusica).toHaveBeenCalledWith(4);
    expect(await screen.findByText("Editando pista")).toBeInTheDocument();
  });

  it("'+ Nueva pista' vuelve al formulario de creación", async () => {
    render(MusicStudio);
    await userEvent.click(await screen.findByText("lofi triste"));
    await screen.findByText("Editando pista");
    await userEvent.click(screen.getByRole("button", { name: "+ Nueva pista" }));
    expect(await screen.findByRole("button", { name: "Crear pista" })).toBeInTheDocument();
  });

  it("crear una pista la crea, refresca la lista y la selecciona", async () => {
    vi.mocked(m.detalleMusica).mockResolvedValue(detalle({ id: 9, idea: "nueva idea" }));
    render(MusicStudio);
    await screen.findByText("lofi triste");
    await userEvent.type(screen.getByRole("textbox"), "nueva idea");
    await userEvent.click(screen.getByRole("button", { name: "Crear pista" }));
    await waitFor(() => expect(m.crearMusica).toHaveBeenCalledWith({ tipo: "instrumental", idea: "nueva idea", duracion_s: 180 }));
    await waitFor(() => expect(m.detalleMusica).toHaveBeenCalledWith(9));
    expect(vi.mocked(m.listarMusica).mock.calls.length).toBeGreaterThanOrEqual(2);
  });

  it("si crear falla muestra el error y no selecciona nada", async () => {
    vi.mocked(m.crearMusica).mockRejectedValue(new Error("HTTP 400"));
    render(MusicStudio);
    await screen.findByText("lofi triste");
    await userEvent.type(screen.getByRole("textbox"), "x");
    await userEvent.click(screen.getByRole("button", { name: "Crear pista" }));
    expect(await screen.findByText("HTTP 400")).toBeInTheDocument();
    expect(m.detalleMusica).not.toHaveBeenCalled();
  });

  it("'Sugerir con LLM' guarda el borrador, pide la mejora y recarga el detalle", async () => {
    render(MusicStudio);
    await userEvent.click(await screen.findByText("lofi triste"));
    await userEvent.click(await screen.findByRole("button", { name: "Sugerir con LLM" }));
    await waitFor(() => expect(m.mejorarMusica).toHaveBeenCalledWith(4));
    // Primero se guarda el borrador, después se pide la sugerencia.
    expect(vi.mocked(m.editarMusica).mock.invocationCallOrder[0]).toBeLessThan(vi.mocked(m.mejorarMusica).mock.invocationCallOrder[0]);
    expect(m.editarMusica).toHaveBeenCalledWith(4, expect.objectContaining({ tags: "warm lofi piano" }));
  });

  it("'Generar música' pide una pista nueva (seed null) con los campos del formulario", async () => {
    render(MusicStudio);
    await userEvent.click(await screen.findByText("lofi triste"));
    await userEvent.click(await screen.findByRole("button", { name: "Generar música" }));
    await waitFor(() => expect(m.generarMusica).toHaveBeenCalledWith(4, expect.objectContaining({ seed: null, tags: "warm lofi piano", bpm: 90 })));
  });

  it("si generar falla muestra el error", async () => {
    vi.mocked(m.generarMusica).mockRejectedValue(new Error("HTTP 500"));
    render(MusicStudio);
    await userEvent.click(await screen.findByText("lofi triste"));
    await userEvent.click(await screen.findByRole("button", { name: "Generar música" }));
    expect(await screen.findByText("HTTP 500")).toBeInTheDocument();
  });

  it("borrar pide confirmación; si se cancela no borra", async () => {
    vi.stubGlobal("confirm", vi.fn().mockReturnValue(false));
    render(MusicStudio);
    await screen.findByText("lofi triste");
    await userEvent.click(screen.getAllByRole("button", { name: "Borrar pista" })[0]);
    expect(m.borrarMusica).not.toHaveBeenCalled();
  });

  it("borrar la pista abierta la cierra y refresca la lista", async () => {
    render(MusicStudio);
    await userEvent.click(await screen.findByText("lofi triste"));
    await screen.findByText("Editando pista");
    vi.mocked(m.listarMusica).mockClear();
    await userEvent.click(screen.getAllByRole("button", { name: "Borrar pista" })[0]);
    await waitFor(() => expect(m.borrarMusica).toHaveBeenCalledWith(4));
    expect(await screen.findByRole("button", { name: "Crear pista" })).toBeInTheDocument();
    await waitFor(() => expect(m.listarMusica).toHaveBeenCalled());
  });

  it("borrar otra pista no cierra la abierta", async () => {
    render(MusicStudio);
    await userEvent.click(await screen.findByText("lofi triste"));
    await screen.findByText("Editando pista");
    await userEvent.click(screen.getAllByRole("button", { name: "Borrar pista" })[1]);
    await waitFor(() => expect(m.borrarMusica).toHaveBeenCalledWith(5));
    expect(screen.getByText("Editando pista")).toBeInTheDocument();
  });

  it("cuando termina un job refresca la lista y el detalle abierto", async () => {
    render(MusicStudio);
    await userEvent.click(await screen.findByText("lofi triste"));
    await screen.findByText("Editando pista");
    vi.mocked(m.listarMusica).mockClear();
    vi.mocked(m.detalleMusica).mockClear();
    jobsDrenados.update((n) => n + 1);
    await waitFor(() => expect(m.listarMusica).toHaveBeenCalled());
    await waitFor(() => expect(m.detalleMusica).toHaveBeenCalledWith(4));
  });

  it("un salto desde la Biblioteca abre esa pista y consume la señal", async () => {
    seleccionPendiente.set({ modo: "musica", id: 5 });
    render(MusicStudio);
    await waitFor(() => expect(m.detalleMusica).toHaveBeenCalledWith(5));
    await waitFor(() => expect(seleccionPendiente).toBeDefined());
    const { get } = await import("svelte/store");
    expect(get(seleccionPendiente)).toBeNull();
  });

  it("una señal pendiente de otro modo no se toca", async () => {
    seleccionPendiente.set({ modo: "imagenes", id: 5 });
    render(MusicStudio);
    await screen.findByText("lofi triste");
    const { get } = await import("svelte/store");
    expect(get(seleccionPendiente)).toEqual({ modo: "imagenes", id: 5 });
    expect(m.detalleMusica).not.toHaveBeenCalled();
  });

  it("con una pista en el player reserva sitio abajo para la isla", async () => {
    currentTrack.set({ id: 1, tipo: "instrumental", idea: "x", seed: null, duracion_s: 1, src: "/a", cover: null });
    const { container } = render(MusicStudio);
    await screen.findByText("lofi triste");
    expect(container.querySelector('[style*="padding-bottom: 88px"]')).not.toBeNull();
  });

  it("una pista ocupada (job en curso) muestra 'Generando música…' en el detalle", async () => {
    vi.mocked(m.detalleMusica).mockResolvedValue(detalle({ ocupado: true }));
    render(MusicStudio);
    await userEvent.click(await screen.findByText("lofi triste"));
    expect(await screen.findByText("Generando música…")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Generar música" })).toBeDisabled();
  });
});
