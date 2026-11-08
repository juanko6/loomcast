import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { get } from "svelte/store";

vi.mock("../api", () => ({ api: vi.fn() }));

import { api } from "../api";
import * as s from "../stores";

const apiMock = vi.mocked(api);

beforeEach(async () => {
  vi.useFakeTimers();
  s.detenerPolling();
  s.salud.set(null);
  s.modo.set("videos");
  s.seleccionPendiente.set(null);
  // El contador de jobs previos es estado de módulo: se rearma con una lista
  // vacía (esto puede contar como "drenado", por eso se pone a 0 después).
  apiMock.mockResolvedValueOnce([]);
  await s.refrescarJobs();
  s.jobs.set([]);
  s.jobsDrenados.set(0);
});

afterEach(() => {
  s.detenerPolling();
  vi.useRealTimers();
});

const job = (id: number) =>
  ({ id, tipo: "generar_voz", ref_id: 1, estado: "corriendo", intentos: 1, sin_corte: null, progreso: null });

describe("navegación", () => {
  it("abrirEn fija la selección pendiente y cambia de modo", () => {
    s.abrirEn("musica", 7);
    expect(get(s.modo)).toBe("musica");
    expect(get(s.seleccionPendiente)).toEqual({ modo: "musica", id: 7 });
  });
});

describe("salud y modelos", () => {
  it("refrescarSalud guarda la respuesta", async () => {
    apiMock.mockResolvedValueOnce({ comfy: true, llm_estado: { estado: "activo", nombre: "x" } });
    await s.refrescarSalud();
    expect(get(s.salud)?.comfy).toBe(true);
    expect(apiMock).toHaveBeenLastCalledWith("/salud");
  });

  it("si el backend cae, conserva el último estado conocido y no lanza", async () => {
    s.salud.set({ comfy: true, llm_estado: { estado: "activo", nombre: "x" } });
    apiMock.mockRejectedValueOnce(new Error("caído"));
    await expect(s.refrescarSalud()).resolves.toBeUndefined();
    expect(get(s.salud)?.comfy).toBe(true);
  });

  it("cargarModelos rellena la lista y el activo", async () => {
    apiMock.mockResolvedValueOnce({ activo: "b", modelos: [{ id: "a", nombre: "A" }, { id: "b", nombre: "B" }] });
    await s.cargarModelos();
    expect(get(s.modelos)).toHaveLength(2);
    expect(get(s.modeloActivo)).toBe("b");
  });

  it("cargarModelos propaga el error (lo captura App)", async () => {
    apiMock.mockRejectedValueOnce(new Error("sin red"));
    await expect(s.cargarModelos()).rejects.toThrow("sin red");
  });

  it("cambiarModelo avisa al backend, actualiza el activo y refresca la salud", async () => {
    apiMock.mockResolvedValue({ comfy: false, llm_estado: { estado: "caido", nombre: "x" } });
    await s.cambiarModelo("c");
    expect(apiMock).toHaveBeenCalledWith("/llm/modelo", { method: "POST", body: { id: "c" } });
    expect(get(s.modeloActivo)).toBe("c");
    expect(apiMock).toHaveBeenCalledWith("/salud");
  });

  it("cambiarModelo no cambia el activo si el backend lo rechaza", async () => {
    s.modeloActivo.set("a");
    apiMock.mockRejectedValueOnce(new Error("404"));
    await expect(s.cambiarModelo("zzz")).rejects.toThrow();
    expect(get(s.modeloActivo)).toBe("a");
  });
});

describe("cola de jobs", () => {
  it("guarda la lista y detecta cuándo se drena", async () => {
    apiMock.mockResolvedValueOnce([job(1), job(2)]);
    await s.refrescarJobs();
    expect(get(s.jobs)).toHaveLength(2);
    expect(get(s.jobsDrenados)).toBe(0);

    apiMock.mockResolvedValueOnce([job(2)]);
    await s.refrescarJobs();
    expect(get(s.jobsDrenados)).toBe(1);
  });

  it("no cuenta como drenado que la cola crezca o se quede igual", async () => {
    apiMock.mockResolvedValueOnce([job(1)]);
    await s.refrescarJobs();
    apiMock.mockResolvedValueOnce([job(1), job(2)]);
    await s.refrescarJobs();
    apiMock.mockResolvedValueOnce([job(1), job(2)]);
    await s.refrescarJobs();
    expect(get(s.jobsDrenados)).toBe(0);
  });

  it("de vacío a vacío no dispara el refresco de las vistas", async () => {
    apiMock.mockResolvedValue([]);
    await s.refrescarJobs();
    await s.refrescarJobs();
    expect(get(s.jobsDrenados)).toBe(0);
  });

  it("un fallo puntual del polling se ignora y mantiene la lista", async () => {
    apiMock.mockResolvedValueOnce([job(1)]);
    await s.refrescarJobs();
    apiMock.mockRejectedValueOnce(new Error("timeout"));
    await s.refrescarJobs();
    expect(get(s.jobs)).toHaveLength(1);
    expect(s.hayCola()).toBe(true);
  });

  it("hayCola refleja si hay jobs", async () => {
    expect(s.hayCola()).toBe(false);
    s.jobs.set([job(1)]);
    expect(s.hayCola()).toBe(true);
  });
});

describe("parar la generación", () => {
  it("cancelar un job avisa al backend y refresca la cola", async () => {
    apiMock.mockClear();     // el beforeEach ya ha consultado la cola una vez
    apiMock.mockResolvedValueOnce(undefined).mockResolvedValueOnce([]);
    s.jobs.set([job(4)]);

    await s.cancelarJob(4);

    expect(apiMock.mock.calls.map((c) => c[0])).toEqual(["/jobs/4/cancelar", "/jobs"]);
    expect(get(s.jobs)).toEqual([]);
  });

  it("parar sin opciones se lleva lo que corre y lo que espera", async () => {
    apiMock.mockClear();
    apiMock.mockResolvedValue([]);

    await s.pararCola();

    expect(apiMock).toHaveBeenCalledWith("/jobs/parar", {
      method: "POST",
      body: { corriendo: true, pendientes: true },
    });
  });

  it("se puede parar solo lo que corre, o solo vaciar la cola", async () => {
    apiMock.mockClear();
    apiMock.mockResolvedValue([]);

    await s.pararCola({ pendientes: false });
    await s.pararCola({ corriendo: false });

    const cuerpos = apiMock.mock.calls
      .filter((c) => c[0] === "/jobs/parar")
      .map((c) => (c[1] as { body: unknown }).body);
    expect(cuerpos).toEqual([
      { corriendo: true, pendientes: false },
      { corriendo: false, pendientes: true },
    ]);
  });

  it("el historial se pide acotado", async () => {
    apiMock.mockClear();
    apiMock.mockResolvedValueOnce([]);
    await s.historialJobs(3);
    expect(apiMock).toHaveBeenCalledWith("/jobs/historial?limite=3");
  });
});

describe("polling", () => {
  const llamadasA = (ruta: string) => apiMock.mock.calls.filter((c) => c[0] === ruta).length;

  beforeEach(() => {
    apiMock.mockReset();
    apiMock.mockImplementation(async (ruta) => (ruta === "/jobs" ? [] : ({} as never)));
  });

  it("arranca consultando salud y cola al instante", async () => {
    s.iniciarPolling();
    await vi.advanceTimersByTimeAsync(0);
    expect(llamadasA("/salud")).toBe(1);
    expect(llamadasA("/jobs")).toBe(1);
  });

  it("en reposo consulta la cola cada 2,5 s y la salud cada 15 s", async () => {
    s.iniciarPolling();
    await vi.advanceTimersByTimeAsync(15_000);
    expect(llamadasA("/salud")).toBe(1 + 1);
    // 1 inicial + una cada 2,5 s durante 15 s
    expect(llamadasA("/jobs")).toBe(1 + 6);
  });

  it("con trabajo en marcha consulta la cola cada segundo", async () => {
    apiMock.mockImplementation(async (ruta) => (ruta === "/jobs" ? [job(1)] : ({} as never)));
    s.iniciarPolling();
    await vi.advanceTimersByTimeAsync(5_000);
    expect(llamadasA("/jobs")).toBe(1 + 5);
  });

  it("detenerPolling para ambos ciclos", async () => {
    s.iniciarPolling();
    await vi.advanceTimersByTimeAsync(0);
    s.detenerPolling();
    apiMock.mockClear();
    await vi.advanceTimersByTimeAsync(60_000);
    expect(apiMock).not.toHaveBeenCalled();
  });

  it("rearrancar no deja dos cadenas consultando a la vez", async () => {
    s.iniciarPolling();
    s.iniciarPolling();
    s.iniciarPolling();
    await vi.advanceTimersByTimeAsync(0);
    apiMock.mockClear();
    await vi.advanceTimersByTimeAsync(5_000);
    expect(llamadasA("/jobs")).toBe(2); // una sola cadena: a los 2,5 s y a los 5 s
  });

  it("parar mientras una petición está en vuelo no reprograma el ciclo", async () => {
    let resolver!: (v: never[]) => void;
    apiMock.mockImplementation(
      (ruta) => (ruta === "/jobs" ? new Promise<never[]>((r) => (resolver = r)) : Promise.resolve({})) as never,
    );
    s.iniciarPolling();
    await vi.advanceTimersByTimeAsync(0);
    s.detenerPolling();
    resolver([]);
    await vi.advanceTimersByTimeAsync(30_000);
    expect(llamadasA("/jobs")).toBe(1);
  });
});
