import { describe, expect, it } from "vitest";

import { nombreJob, resultadoJob } from "../jobs";

describe("nombres de los jobs", () => {
  it("traduce el tipo de la cola a lo que el usuario pidió", () => {
    expect(nombreJob("generar_previews_imagen")).toBe("Previews de imagen");
    expect(nombreJob("armar_video")).toBe("Montaje final");
  });

  it("un tipo nuevo se enseña tal cual en vez de desaparecer", () => {
    expect(nombreJob("generar_lo_que_venga")).toBe("generar_lo_que_venga");
  });
});

describe("resultado de un job", () => {
  it("parado no se pinta como un error", () => {
    expect(resultadoJob("cancelado")).toEqual({ texto: "Parado", clase: "text-warn" });
    expect(resultadoJob("error")).toEqual({ texto: "Error", clase: "text-danger" });
  });

  it("un estado desconocido no rompe la fila", () => {
    expect(resultadoJob("raro").texto).toBe("raro");
  });
});
