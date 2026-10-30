import { describe, expect, it } from "vitest";

import { comoHashtag, etiquetasEnHashtags, etiquetasEnLinea } from "../metadatos";
import { enlaceYoutube, fechaEnEspanol } from "../proyectos";

describe("etiquetas", () => {
  it("en línea van separadas por comas, como las pide YouTube", () => {
    expect(etiquetasEnLinea(["mar", "curiosidades del mar"])).toBe("mar, curiosidades del mar");
  });

  it("en línea ignora las vacías y recorta los espacios", () => {
    expect(etiquetasEnLinea([" mar ", "", "  "])).toBe("mar");
  });

  it("como hashtag pierde los espacios y la puntuación, pero no las tildes", () => {
    expect(comoHashtag("curiosidades del mar")).toBe("#curiosidadesdelmar");
    expect(comoHashtag("¿sabías que?")).toBe("#sabíasque");
    expect(comoHashtag("año 2026")).toBe("#año2026");
  });

  it("una etiqueta sin letras ni números no da hashtag", () => {
    expect(comoHashtag("—")).toBe("");
    expect(etiquetasEnHashtags(["mar", "···", "sol"])).toBe("#mar #sol");
  });

  it("sin etiquetas, las dos formas salen vacías", () => {
    expect(etiquetasEnLinea([])).toBe("");
    expect(etiquetasEnHashtags([])).toBe("");
  });
});

describe("enlaceYoutube", () => {
  it("un enlace entero se queda como está", () => {
    expect(enlaceYoutube("https://youtu.be/abc123")).toBe("https://youtu.be/abc123");
    expect(enlaceYoutube("http://youtube.com/watch?v=abc")).toBe("http://youtube.com/watch?v=abc");
  });

  it("un id suelto se convierte en enlace", () => {
    expect(enlaceYoutube("abc123")).toBe("https://youtu.be/abc123");
    expect(enlaceYoutube("  abc123  ")).toBe("https://youtu.be/abc123");
  });

  it("sin nada apuntado no hay enlace", () => {
    expect(enlaceYoutube("")).toBe("");
    expect(enlaceYoutube("   ")).toBe("");
  });
});

describe("fechaEnEspanol", () => {
  it("la ISO corta se lee en día/mes/año", () => {
    expect(fechaEnEspanol("2026-10-29")).toBe("29/10/2026");
  });

  it("lo que no es una ISO se deja como está", () => {
    expect(fechaEnEspanol("")).toBe("");
    expect(fechaEnEspanol("ayer")).toBe("ayer");
  });
});
