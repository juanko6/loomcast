// El cliente del autopiloto es un envoltorio fino sobre `api`: lo que importa es
// que pegue a la ruta, método y cuerpo que esperan los routers, y que las
// etiquetas de estado digan lo que pasa sin asustar cuando no hay nada roto.
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../api", async (original) => ({
  ...(await original<typeof import("../api")>()),
  api: vi.fn().mockResolvedValue({}),
}));

import { api } from "../api";
import * as a from "../autopiloto";

const apiMock = vi.mocked(api);
const ultima = () => apiMock.mock.calls.at(-1)!;

beforeEach(() => {
  apiMock.mockClear();
  apiMock.mockResolvedValue({});
});

const lote = (extra: Partial<a.Lote> = {}): a.Lote => ({
  id: 1, tema_id: 2, tema: "el espacio", total: 3, pendientes: 0, esperando: 0,
  hechos: 0, errores: 0, parados: 0, actual: null, proyectos: [], ...extra,
});

describe("llamadas", () => {
  it("lanzar un autopiloto manda modo, motor, voz y paradas", async () => {
    await a.lanzarAutopiloto(7, { modo: "i2v", motor: "ltx25", voz: "ana", paradas: [] });

    expect(ultima()).toEqual([
      "/proyectos/7/autopiloto",
      { method: "POST", body: { modo: "i2v", motor: "ltx25", voz: "ana", paradas: [] } },
    ]);
  });

  it("continuar y detener pegan al proyecto", async () => {
    await a.continuarAutopiloto(7);
    expect(ultima()).toEqual(["/proyectos/7/autopiloto/continuar", { method: "POST" }]);

    await a.detenerAutopiloto(7);
    expect(ultima()).toEqual(["/proyectos/7/autopiloto", { method: "DELETE" }]);
  });

  it("lanzar un lote lleva el tema dentro del cuerpo", async () => {
    await a.lanzarLote(3, { modo: "estatico", voz: "ana", paradas: ["guion"] });

    expect(ultima()).toEqual([
      "/lotes",
      { method: "POST", body: { tema_id: 3, modo: "estatico", voz: "ana", paradas: ["guion"] } },
    ]);
  });

  it("listar lotes", async () => {
    await a.listarLotes();
    expect(ultima()).toEqual(["/lotes"]);
  });
});

describe("paradas", () => {
  it("son las tres del flujo a mano y vienen puestas por defecto", () => {
    expect(a.PARADAS.map((p) => p.id)).toEqual(["idea", "guion", "escenas"]);
    expect(a.PARADAS_DEFECTO).toEqual(["idea", "guion", "escenas"]);
  });

  it("cada una dice qué se revisa, no cómo se llama la clave", () => {
    for (const p of a.PARADAS) {
      expect(p.nombre).toBeTruthy();
      expect(p.desc.length).toBeGreaterThan(20);
    }
  });
});

describe("estados", () => {
  it("esperando una revisión es un aviso, no un error", () => {
    expect(a.estadoAutopiloto("esperando").clase).toBe("text-warn");
    expect(a.estadoAutopiloto("error").clase).toBe("text-danger");
    expect(a.estadoAutopiloto("hecho").clase).toBe("text-ok");
  });

  it("un estado que no conoce se enseña tal cual en vez de desaparecer", () => {
    expect(a.estadoAutopiloto("raro")).toEqual({ texto: "raro", clase: "text-dim" });
  });

  it.each([
    ["pendiente", true],
    ["corriendo", true],
    ["esperando", true],
    ["hecho", false],
    ["error", false],
    ["parado", false],
  ])("viva(%s) = %s", (estado, esperado) => {
    expect(a.viva({ estado } as a.Autopiloto)).toBe(esperado);
  });

  it("sin autopiloto no hay tirada viva", () => {
    expect(a.viva(null)).toBe(false);
  });
});

describe("lotes vivos", () => {
  it("vive mientras quede algo por empezar o algo produciendo", () => {
    expect(a.loteVivo(lote({ pendientes: 2 }))).toBe(true);
    expect(
      a.loteVivo(lote({ actual: { proyecto_id: 1, titulo: "x", etapa: "", posicion: 1 } })),
    ).toBe(true);
  });

  it("un lote con todo revisado o acabado ya no cuenta en la cabecera", () => {
    expect(a.loteVivo(lote({ hechos: 3 }))).toBe(false);
    // Los que esperan revisión no mantienen la línea ocupada, pero tampoco se
    // pierden: siguen en el listado de proyectos marcados para revisar.
    expect(a.loteVivo(lote({ esperando: 3 }))).toBe(false);
  });
});
