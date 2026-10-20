// Los clientes de galeria/musica/proyectos son envoltorios finos sobre `api`:
// lo que importa es que cada uno pegue a la ruta, método y cuerpo que espera el
// backend (los routers de FastAPI). Se comprueba contra un `api` simulado.
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../api", async (original) => ({
  ...(await original<typeof import("../api")>()),
  api: vi.fn().mockResolvedValue({}),
  apiForm: vi.fn().mockResolvedValue({}),
}));

import { api, apiForm } from "../api";
import * as galeria from "../galeria";
import * as musica from "../musica";
import * as p from "../proyectos";
import * as series from "../series";
import { icons, filledIcons } from "../icons";

const apiMock = vi.mocked(api);
const formMock = vi.mocked(apiForm);

beforeEach(() => {
  apiMock.mockResolvedValue({});
  formMock.mockResolvedValue({});
});

const ultima = () => apiMock.mock.calls.at(-1)!;

describe("galería", () => {
  it.each([
    ["listarGaleria", () => galeria.listarGaleria(), "/galeria", undefined],
    ["detalleGaleria", () => galeria.detalleGaleria(4), "/galeria/4", undefined],
    ["listarMotores", () => galeria.listarMotores(), "/galeria/motores", undefined],
    ["mejorarPrompt", () => galeria.mejorarPrompt(4), "/galeria/4/mejorar", { method: "POST" }],
    ["editarPrompt", () => galeria.editarPrompt(4, "a fox"), "/galeria/4/prompt", { method: "PUT", body: { prompt: "a fox" } }],
    ["lanzarFinal", () => galeria.lanzarFinal(4, 2), "/galeria/4/final", { method: "POST", body: { indice: 2 } }],
    ["borrarGaleria", () => galeria.borrarGaleria(4), "/galeria/4", { method: "DELETE" }],
    ["crearGenerar", () => galeria.crearGenerar({ idea: "x", width: 768, height: 1344, motor: "zimage" }), "/galeria",
      { method: "POST", body: { idea: "x", width: 768, height: 1344, motor: "zimage" } }],
  ])("%s", async (_n, llamar, ruta, opts) => {
    await llamar();
    expect(ultima()).toEqual(opts === undefined ? [ruta] : [ruta, opts]);
  });

  it("lanzarPreviews manda el tamaño solo si vienen los dos lados", async () => {
    await galeria.lanzarPreviews(1, 512, 768);
    expect(ultima()[1]).toMatchObject({ body: { width: 512, height: 768 } });
    await galeria.lanzarPreviews(1, 512);
    expect(ultima()[1]).toMatchObject({ body: {} });
    await galeria.lanzarPreviews(1);
    expect(ultima()[1]).toMatchObject({ body: {} });
    await galeria.lanzarPreviews(1, 0, 0);
    expect(ultima()[1]).toMatchObject({ body: {} });
  });

  it("crearEditar sube idea, imagen y motor como multipart", async () => {
    const f = new File(["x"], "a.png", { type: "image/png" });
    await galeria.crearEditar("ponle gafas", f, "qwen");
    const [ruta, fd] = formMock.mock.calls[0];
    expect(ruta).toBe("/galeria/editar");
    expect(fd.get("idea")).toBe("ponle gafas");
    expect(fd.get("motor")).toBe("qwen");
    expect((fd.get("imagen") as File).name).toBe("a.png");
  });

  it("crearQuitarFondo sube solo la imagen", async () => {
    await galeria.crearQuitarFondo(new File(["x"], "b.png"));
    const [ruta, fd] = formMock.mock.calls[0];
    expect(ruta).toBe("/galeria/quitarfondo");
    expect([...fd.keys()]).toEqual(["imagen"]);
  });

  it("los tamaños predefinidos son múltiplos de 64 y están en rango del backend", () => {
    for (const t of galeria.TAMANOS) {
      expect(t.w % 64).toBe(0);
      expect(t.h % 64).toBe(0);
      expect(Math.min(t.w, t.h)).toBeGreaterThanOrEqual(256);
      expect(Math.max(t.w, t.h)).toBeLessThanOrEqual(1536);
    }
    expect(galeria.TAMANOS[0]).toMatchObject({ w: 768, h: 1344 }); // el 9:16 por defecto
  });
});

describe("música", () => {
  it("rutas y métodos", async () => {
    await musica.listarMusica();
    expect(ultima()).toEqual(["/musica"]);
    await musica.detalleMusica(3);
    expect(ultima()).toEqual(["/musica/3"]);
    await musica.mejorarMusica(3);
    expect(ultima()).toEqual(["/musica/3/mejorar", { method: "POST" }]);
    await musica.borrarMusica(3);
    expect(ultima()).toEqual(["/musica/3", { method: "DELETE" }]);
    await musica.crearMusica({ tipo: "cancion", idea: "x", duracion_s: 30, bpm: 90 });
    expect(ultima()).toEqual(["/musica", { method: "POST", body: { tipo: "cancion", idea: "x", duracion_s: 30, bpm: 90 } }]);
    await musica.editarMusica(3, { tags: "t" });
    expect(ultima()).toEqual(["/musica/3", { method: "PUT", body: { tags: "t" } }]);
    await musica.generarMusica(3, { seed: null });
    expect(ultima()).toEqual(["/musica/3/generar", { method: "POST", body: { seed: null } }]);
  });

  it("portadaUrl apunta a la portada de la pista", () => {
    expect(musica.portadaUrl(9)).toBe("/api/musica/9/portada");
  });

  it("los combos coinciden con los del backend (musica_combos.py)", () => {
    expect(musica.RAICES).toHaveLength(17);
    expect(musica.KEYSCALES).toHaveLength(34);
    expect(musica.KEYSCALES[0]).toBe("C major");
    expect(musica.KEYSCALES.at(-1)).toBe("B minor");
    expect(new Set(musica.KEYSCALES).size).toBe(34);
    expect([...musica.TIMESIGS]).toEqual(["2", "3", "4", "6"]);
    expect(musica.IDIOMAS.map((i) => i.value)).toContain("es");
    expect(new Set(musica.IDIOMAS.map((i) => i.value)).size).toBe(musica.IDIOMAS.length);
  });
});

describe("series", () => {
  it.each([
    ["listarSeries", () => series.listarSeries(), "/series", undefined],
    ["detalleSerie", () => series.detalleSerie(7), "/series/7", undefined],
    ["crearSerie", () => series.crearSerie("La casa", "serie"), "/series",
      { method: "POST", body: { nombre: "La casa", plantilla: "serie" } }],
    ["borrarSerie", () => series.borrarSerie(7), "/series/7", { method: "DELETE" }],
    ["anadirMiembroSerie", () => series.anadirMiembroSerie(7, "ana"), "/series/7/miembros",
      { method: "POST", body: { reparto_slug: "ana" } }],
    ["quitarMiembroSerie", () => series.quitarMiembroSerie(7, "ana"),
      "/series/7/miembros/ana", { method: "DELETE" }],
    ["crearEpisodio con apunte", () => series.crearEpisodio(7, "Ana vuelve"),
      "/series/7/episodios", { method: "POST", body: { apunte: "Ana vuelve" } }],
    // Sin apunte el cuerpo va vacío: el episodio lo propone el LLM desde el
    // resumen del anterior.
    ["crearEpisodio sin apunte", () => series.crearEpisodio(7), "/series/7/episodios",
      { method: "POST", body: { apunte: "" } }],
  ])("%s", async (_n, llamar, ruta, opts) => {
    await llamar();
    expect(ultima()).toEqual(opts === undefined ? [ruta] : [ruta, opts]);
  });
});

describe("proyectos", () => {
  it("temas e ideas", async () => {
    await p.crearTema("el espacio", "drama");
    expect(ultima()).toEqual(["/temas", { method: "POST", body: { texto: "el espacio", plantilla: "drama" } }]);
    await p.masIdeas(2);
    expect(ultima()).toEqual(["/temas/2/ideas", { method: "POST" }]);
    await p.borrarTema(2);
    expect(ultima()).toEqual(["/temas/2", { method: "DELETE" }]);
    await p.cambiarEstadoIdea(5, "aprobada");
    expect(ultima()).toEqual(["/ideas/5/estado", { method: "POST", body: { estado: "aprobada" } }]);
    await p.proyectoDesdeIdea(5);
    expect(ultima()).toEqual(["/ideas/5/proyecto", { method: "POST" }]);
  });

  it("etapas del proyecto", async () => {
    await p.regenerarGuion(1);
    expect(ultima()[0]).toBe("/proyectos/1/guion/regenerar");
    await p.generarMetadatos(1);
    expect(ultima()[0]).toBe("/proyectos/1/metadatos");
    await p.generarCasting(1);
    expect(ultima()[0]).toBe("/proyectos/1/casting");
    await p.generarEscenas(1);
    expect(ultima()[0]).toBe("/proyectos/1/escenas");
    await p.generarImagenes(1);
    expect(ultima()[0]).toBe("/proyectos/1/imagenes");
    await p.guardarGuion(1, { gancho: "g", cta: "c" });
    expect(ultima()).toEqual(["/proyectos/1/guion", { method: "PUT", body: { gancho: "g", cta: "c" } }]);
    await p.seleccionarVoz(1, "ana");
    expect(ultima()).toEqual(["/proyectos/1/voz", { method: "PUT", body: { voz: "ana" } }]);
    await p.generarVoz(1, "design", "grave");
    expect(ultima()).toEqual(["/proyectos/1/voz", { method: "POST", body: { modo: "design", instruct: "grave" } }]);
    // Cierre del episodio: editarlo a mano y pedir que lo reescriba el LLM.
    await p.editarResumen(1, "Pasó esto.");
    expect(ultima()).toEqual(["/proyectos/1/resumen", { method: "PUT", body: { resumen: "Pasó esto." } }]);
    await p.generarResumen(1);
    expect(ultima()).toEqual(["/proyectos/1/resumen", { method: "POST" }]);
  });

  it("personajes y retratos", async () => {
    await p.anadirPersonaje(1, "ANA", "Ana", "ficha");
    expect(ultima()).toEqual(["/proyectos/1/personajes", { method: "POST", body: { clave: "ANA", nombre: "Ana", ficha: "ficha" } }]);
    await p.borrarPersonaje(1, "ANA");
    expect(ultima()).toEqual(["/proyectos/1/personajes/ANA", { method: "DELETE" }]);
    await p.generarRetrato(1, "ANA", false);
    expect(ultima()).toEqual(["/proyectos/1/personajes/ANA/retrato", { method: "POST", body: { nuevo_seed: false } }]);
    await p.guardarCasting(1, [{ clave: "ANA", nombre: "A", ficha: "f", retrato: true }]);
    expect(ultima()[1]).toMatchObject({ method: "PUT" });
  });

  it("escenas, imágenes y clips", async () => {
    await p.guardarEscenas(1, [{ orden: 0, prompt: "p", prompt_movimiento: null }]);
    expect(ultima()).toEqual(["/proyectos/1/escenas", { method: "PUT", body: { escenas: [{ orden: 0, prompt: "p", prompt_movimiento: null }] } }]);
    await p.fijarModos(1, [{ orden: 0, modo: "i2v" }]);
    expect(ultima()[0]).toBe("/proyectos/1/escenas/modos");
    await p.regenerarImagen(1, 3, true);
    expect(ultima()).toEqual(["/proyectos/1/escenas/3/imagen", { method: "POST", body: { nuevo_seed: true } }]);
    await p.regenerarClip(1, 3, "kenburns");
    expect(ultima()).toEqual(["/proyectos/1/escenas/3/clip", { method: "POST", body: { modo: "kenburns" } }]);
  });

  it("vídeo y versiones", async () => {
    await p.generarVideo(1, "estatico");
    expect(ultima()).toEqual([
      "/proyectos/1/video",
      { method: "POST", body: { modo: "estatico", motor: "" } },
    ]);
    await p.generarVideo(1, "i2v", "hunyuan");
    expect(ultima()).toEqual([
      "/proyectos/1/video",
      { method: "POST", body: { modo: "i2v", motor: "hunyuan" } },
    ]);
    await p.borrarVideo(1, true);
    expect(ultima()).toEqual(["/proyectos/1/video?con_versiones=true", { method: "DELETE" }]);
    await p.borrarVideo(1, false);
    expect(ultima()[0]).toBe("/proyectos/1/video?con_versiones=false");
    await p.borrarVersion(1, "final_1.mp4");
    expect(ultima()).toEqual(["/proyectos/1/versiones/final_1.mp4", { method: "DELETE" }]);
    await p.borrarProyecto(1);
    expect(ultima()).toEqual(["/proyectos/1", { method: "DELETE" }]);
  });

  it("voces", async () => {
    await p.listarVoces();
    expect(ultima()).toEqual(["/voces"]);
    await p.crearVoz("Ana", "cálida");
    expect(ultima()).toEqual(["/voces", { method: "POST", body: { nombre: "Ana", instruct: "cálida" } }]);
    await p.borrarVoz("ana");
    expect(ultima()).toEqual(["/voces/ana", { method: "DELETE" }]);
    await p.listarPlantillas();
    expect(ultima()).toEqual(["/plantillas"]);
  });

  it("clonarVoz incluye el recorte solo si se indica (0 cuenta como indicado)", async () => {
    const audio = new File(["x"], "v.wav");
    await p.clonarVoz("Ana", audio, "cálida");
    expect([...formMock.mock.calls[0][1].keys()].sort()).toEqual(["audio", "descripcion", "nombre"]);
    await p.clonarVoz("Ana", audio, "", 0, 8.5);
    const fd = formMock.mock.calls[1][1];
    expect(fd.get("inicio")).toBe("0");
    expect(fd.get("fin")).toBe("8.5");
    expect(formMock.mock.calls[1][0]).toBe("/voces/clonar");
  });

  it("reparto propio: listar, promover, traer, actualizar y borrar", async () => {
    await p.listarReparto();
    expect(ultima()).toEqual(["/reparto"]);
    await p.promoverAlReparto(3, "ANA", "Ana narradora");
    expect(ultima()).toEqual(["/reparto", {
      method: "POST", body: { proyecto_id: 3, clave: "ANA", nombre: "Ana narradora" }}]);
    await p.traerDelReparto("ana-narradora", 3);
    expect(ultima()).toEqual(["/reparto/ana-narradora/traer", {
      method: "POST", body: { proyecto_id: 3 }}]);
    await p.actualizarEnReparto("ana-narradora", 3, "ANA");
    expect(ultima()).toEqual(["/reparto/ana-narradora", {
      method: "PUT", body: { proyecto_id: 3, clave: "ANA" }}]);
    await p.borrarDelReparto("ana-narradora");
    expect(ultima()).toEqual(["/reparto/ana-narradora", { method: "DELETE" }]);
  });

  it("cada modo de vídeo tiene nombre legible y etapa", () => {
    const ids = p.MODOS_VIDEO.map((m) => m.id);
    expect(ids).toEqual(["estatico", "kenburns", "i2v", "mixto"]);
    for (const m of p.MODOS_VIDEO) expect(m.nombre && m.desc).toBeTruthy();
    for (const id of ["estatico", "kenburns", "i2v"]) expect(p.NOMBRE_MODO[id]).toBeTruthy();
  });

  it("ETAPA_VIDEO cubre todos los jobs de proyecto del backend", () => {
    // Tipos de job que aparecen como `job_activo` (backend/services/proyectos.py).
    const jobs = [
      "generar_guion", "generar_metadatos", "generar_voz", "generar_subtitulos",
      "generar_casting", "generar_retrato", "generar_escenas", "generar_imagenes",
      "generar_upscale", "generar_clips", "generar_i2v", "armar_video", "armar_estatico",
      "regenerar_imagen", "regenerar_clip", "generar_clips_mixto",
    ];
    expect(jobs.filter((j) => !(j in p.ETAPA_VIDEO))).toEqual([]);
  });
});

describe("icons", () => {
  it("todos los iconos rellenos existen en el registro", () => {
    for (const nombre of filledIcons) expect(icons).toHaveProperty(nombre);
  });

  it("cada icono es un path SVG no vacío", () => {
    for (const [nombre, d] of Object.entries(icons)) {
      expect(d, nombre).toMatch(/^M/);
    }
  });
});
