import { describe, expect, it, vi } from "vitest";

vi.mock("../proyectos", () => ({ listarProyectos: vi.fn() }));
vi.mock("../galeria", () => ({ listarGaleria: vi.fn() }));
vi.mock("../musica", () => ({ listarMusica: vi.fn() }));

import { FILTROS, cargarBiblioteca } from "../biblioteca";
import { listarGaleria } from "../galeria";
import { listarMusica } from "../musica";
import { listarProyectos } from "../proyectos";

function datos({ proyectos = [], imagenes = [], musica = [] }: Record<string, unknown[]> = {}) {
  vi.mocked(listarProyectos).mockResolvedValue(proyectos as never);
  vi.mocked(listarGaleria).mockResolvedValue(imagenes as never);
  vi.mocked(listarMusica).mockResolvedValue(musica as never);
}

describe("cargarBiblioteca", () => {
  it("sin nada creado devuelve una lista vacía", async () => {
    datos();
    expect(await cargarBiblioteca()).toEqual([]);
  });

  it("agrupa vídeos, imágenes y música en ese orden", async () => {
    datos({
      proyectos: [{ id: 1, titulo: "V", slug: "v", estado: "GUION" }],
      imagenes: [{ id: 2, idea: "I", tipo: "generar", estado: "nueva" }],
      musica: [{ id: 3, idea: "M", tipo: "cancion", estado: "nueva", tiene_portada: false }],
    });
    const items = await cargarBiblioteca();
    expect(items.map((i) => [i.kind, i.id, i.destino])).toEqual([
      ["video", 1, "videos"], ["imagen", 2, "imagenes"], ["musica", 3, "musica"]]);
  });

  describe("vídeos", () => {
    it("usan la escena 0 como miniatura y el título (o el slug si no hay)", async () => {
      datos({ proyectos: [
        { id: 1, titulo: "Con título", slug: "con-titulo", estado: "GUION" },
        { id: 2, titulo: "", slug: "solo-slug", estado: "GUION" }] });
      const [a, b] = await cargarBiblioteca();
      expect(a.thumb).toBe("/api/proyectos/1/imagenes/0");
      expect([a.titulo, b.titulo]).toEqual(["Con título", "solo-slug"]);
    });

    // Regresión: el backend manda el estado del proyecto en MAYÚSCULAS ("FINAL")
    // y la biblioteca comparaba con "final", así que nunca ofrecía el vídeo.
    it("solo ofrecen el vídeo cuando el estado es FINAL (como lo manda el backend)", async () => {
      datos({ proyectos: [
        { id: 1, titulo: "a", slug: "a", estado: "FINAL" },
        { id: 2, titulo: "b", slug: "b", estado: "GUION" }] });
      const [a, b] = await cargarBiblioteca();
      expect(a.src).toBe("/api/proyectos/1/video");
      expect(b.src).toBeNull();
    });
  });

  describe("imágenes", () => {
    it("rotulan el tipo y usan la final como miniatura cuando existe, y si no la fuente", async () => {
      datos({ imagenes: [
        { id: 1, idea: "gato", tipo: "generar", estado: "final" },
        { id: 2, idea: "perro", tipo: "editar", estado: "previews" },
        { id: 3, idea: "", tipo: "quitarfondo", estado: "nueva" },
        { id: 4, idea: "x", tipo: "otro_tipo", estado: "nueva" }] });
      const [a, b, c, d] = await cargarBiblioteca();
      expect([a.subtipo, b.subtipo, c.subtipo, d.subtipo]).toEqual(
        ["Generar", "Editar", "Quitar fondo", "otro_tipo"]);
      expect([a.thumb, a.src]).toEqual(["/api/galeria/1/final", "/api/galeria/1/final"]);
      expect([b.thumb, b.src]).toEqual(["/api/galeria/2/fuente", null]);
      expect(c.titulo).toBe("(imagen)");
    });
  });

  describe("música", () => {
    it("rotula el tipo, no tiene miniatura y ofrece el audio solo si está generada", async () => {
      datos({ musica: [
        { id: 1, idea: "lofi", tipo: "instrumental", estado: "generada", tiene_portada: true },
        { id: 2, idea: "", tipo: "cancion", estado: "nueva", tiene_portada: false },
        { id: 3, idea: "x", tipo: "raro", estado: "nueva", tiene_portada: false }] });
      const [a, b, c] = await cargarBiblioteca();
      expect([a.subtipo, b.subtipo, c.subtipo]).toEqual(["Instrumental", "Canción", "raro"]);
      expect(a.src).toBe("/api/musica/1/audio");
      expect(b.src).toBeNull();
      expect(a.thumb).toBeNull();
      expect(b.titulo).toBe("(pista)");
    });
  });

  it("consulta las tres listas en paralelo", async () => {
    datos();
    await cargarBiblioteca();
    expect(listarProyectos).toHaveBeenCalledTimes(1);
    expect(listarGaleria).toHaveBeenCalledTimes(1);
    expect(listarMusica).toHaveBeenCalledTimes(1);
  });

  it("si una de las listas falla, falla toda la carga", async () => {
    datos();
    vi.mocked(listarMusica).mockRejectedValue(new Error("500"));
    await expect(cargarBiblioteca()).rejects.toThrow("500");
  });
});

describe("FILTROS", () => {
  it("empieza por 'todo' y cubre los tres tipos", () => {
    expect(FILTROS.map((f) => f.id)).toEqual(["todo", "video", "imagen", "musica"]);
  });
});
