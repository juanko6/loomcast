import { fireEvent, render, screen, waitFor, within } from "@testing-library/svelte";
import userEvent from "@testing-library/user-event";
import { get } from "svelte/store";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/galeria", async (o) => {
  const real = await o<typeof import("@/lib/galeria")>();
  return {
    ...real,
    listarGaleria: vi.fn(), detalleGaleria: vi.fn(), listarMotores: vi.fn(), crearGenerar: vi.fn(),
    crearEditar: vi.fn(), crearQuitarFondo: vi.fn(), editarPrompt: vi.fn(), mejorarPrompt: vi.fn(),
    lanzarPreviews: vi.fn(), lanzarFinal: vi.fn(), borrarGaleria: vi.fn(),
    crearAnimada: vi.fn(), guardarMovimiento: vi.fn(), mejorarMovimiento: vi.fn(), animar: vi.fn(),
    escalar: vi.fn(), listarEstilos: vi.fn(), cambiarEstilo: vi.fn(),
  };
});
vi.mock("@/lib/api", async (o) => ({ ...(await o<typeof import("@/lib/api")>()), api: vi.fn().mockResolvedValue([]) }));

import * as g from "@/lib/galeria";
import type { EstiloImagen, GaleriaDetalle, MotorImagen } from "@/lib/galeria";
import { currentTrack } from "@/lib/player";
import { jobs, jobsDrenados, seleccionPendiente } from "@/lib/stores";
import ImageConfig from "../imagenes/ImageConfig.svelte";
import ImageStudio from "../imagenes/ImageStudio.svelte";

const MOTORES: MotorImagen[] = [
  { id: "zimage", nombre: "Z-Image Turbo", modos: ["generar"], defecto_en: ["generar"] },
  { id: "qwen", nombre: "Qwen-Image-Edit", modos: ["editar"], defecto_en: ["editar"] },
  { id: "flux2klein", nombre: "FLUX.2 Klein", modos: ["generar", "editar"], defecto_en: [] },
];
const ESTILOS: EstiloImagen[] = [
  { id: "tinta", nombre: "Tinta y serigrafía", descripcion: "Línea de tinta y grano", motor: "flux2klein", ejemplos: 2 },
  { id: "plano", nombre: "Color plano", descripcion: "Un color de fondo", motor: "", ejemplos: 0 },
];
const NUEVA = { detalles: "", estilo: "", n_previews: 4 };
const titulo = () => screen.getByLabelText(/^Título/);
const fireInput = (el: HTMLInputElement, v: string) => fireEvent.input(el, { target: { value: v } });
const archivo = () => new File(["x"], "foto.png", { type: "image/png" });

beforeEach(() => {
  vi.mocked(g.listarMotores).mockResolvedValue(MOTORES);
  vi.mocked(g.listarEstilos).mockResolvedValue(ESTILOS);
  localStorage.clear();
  vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: vi.fn(() => "blob:previa"), revokeObjectURL: vi.fn() }));
});

describe("ImageConfig", () => {
  const props = () => ({
    oncreateGenerar: vi.fn(), oncreateEditar: vi.fn(), oncreateFondo: vi.fn(), oncreateAnimada: vi.fn(),
  });
  const montar = async (p = props(), extra = {}) => {
    const r = render(ImageConfig, { ...p, ...extra });
    await waitFor(() => expect(g.listarMotores).toHaveBeenCalled());
    return { ...r, p };
  };

  it("generar: 'Crear' bloqueado sin título, y manda tamaño, motor por defecto, libre y 4 previews", async () => {
    const { p } = await montar();
    const crear = screen.getByRole("button", { name: "Crear" });
    expect(crear).toBeDisabled();
    await userEvent.type(titulo(), "  un faro  ");
    await userEvent.click(crear);
    expect(p.oncreateGenerar).toHaveBeenCalledWith({ ...NUEVA, idea: "un faro", width: 768, height: 1344, motor: "zimage" });
  });

  it("un tamaño predefinido distinto se envía tal cual", async () => {
    const { p } = await montar();
    await userEvent.type(titulo(), "x");
    await userEvent.selectOptions(screen.getByLabelText("Tamaño"), "1024x1024");
    await userEvent.click(screen.getByRole("button", { name: "Crear" }));
    expect(p.oncreateGenerar).toHaveBeenCalledWith(expect.objectContaining({ width: 1024, height: 1024 }));
  });

  it("tamaño personalizado: aparecen ancho y alto, y se envían", async () => {
    const { p } = await montar();
    await userEvent.type(titulo(), "x");
    await userEvent.selectOptions(screen.getByLabelText("Tamaño"), "custom");
    const ancho = screen.getByLabelText("Ancho"), alto = screen.getByLabelText("Alto");
    await userEvent.clear(ancho); await userEvent.type(ancho, "640");
    await userEvent.clear(alto); await userEvent.type(alto, "896");
    expect(screen.getByText(/múltiplos de 64/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Crear" }));
    expect(p.oncreateGenerar).toHaveBeenCalledWith(expect.objectContaining({ width: 640, height: 896 }));
  });

  it("personalizado con los campos vacíos cae a 1024×1024", async () => {
    const { p } = await montar();
    await userEvent.type(titulo(), "x");
    await userEvent.selectOptions(screen.getByLabelText("Tamaño"), "custom");
    await userEvent.clear(screen.getByLabelText("Ancho"));
    await userEvent.clear(screen.getByLabelText("Alto"));
    await userEvent.click(screen.getByRole("button", { name: "Crear" }));
    expect(p.oncreateGenerar).toHaveBeenCalledWith(expect.objectContaining({ width: 1024, height: 1024 }));
  });

  it("el selector de modelo solo ofrece los que saben el modo, y recuerda la elección de cada modo", async () => {
    await montar();
    const opciones = () => within(screen.getByLabelText("Modelo")).getAllByRole("option").map((o) => o.textContent);
    expect(opciones()).toEqual(["Z-Image Turbo", "FLUX.2 Klein"]);
    await userEvent.selectOptions(screen.getByLabelText("Modelo"), "flux2klein");

    await userEvent.click(screen.getByRole("tab", { name: "Editar" }));
    expect(opciones()).toEqual(["Qwen-Image-Edit", "FLUX.2 Klein"]);
    expect((screen.getByLabelText("Modelo") as HTMLSelectElement).value).toBe("qwen");   // el suyo, no el de Generar

    await userEvent.click(screen.getByRole("tab", { name: "Generar" }));
    expect((screen.getByLabelText("Modelo") as HTMLSelectElement).value).toBe("flux2klein");
  });

  it("con un solo modelo para el modo no se muestra el selector", async () => {
    vi.mocked(g.listarMotores).mockResolvedValue([MOTORES[0]]);
    await montar();
    expect(screen.queryByLabelText("Modelo")).toBeNull();
  });

  it("el motor elegido viaja en la creación", async () => {
    const { p } = await montar();
    await userEvent.selectOptions(screen.getByLabelText("Modelo"), "flux2klein");
    await userEvent.type(titulo(), "x");
    await userEvent.click(screen.getByRole("button", { name: "Crear" }));
    expect(p.oncreateGenerar).toHaveBeenCalledWith(expect.objectContaining({ motor: "flux2klein" }));
  });

  it("editar: exige idea Y imagen, muestra la vista previa y envía ambas", async () => {
    const { p, container } = await montar();
    await userEvent.click(screen.getByRole("tab", { name: "Editar" }));
    const crear = screen.getByRole("button", { name: "Subir imagen" });
    expect(crear).toBeDisabled();

    await userEvent.type(screen.getByLabelText(/quieres aplicar/), "  ponle gafas ");
    expect(crear).toBeDisabled();          // falta la imagen
    const f = archivo();
    await userEvent.upload(container.querySelector('input[type="file"]')!, f);
    expect(await screen.findByAltText("origen")).toHaveAttribute("src", "blob:previa");
    expect(screen.getByText("Cambiar imagen")).toBeInTheDocument();
    expect(crear).toBeEnabled();

    await userEvent.click(crear);
    expect(p.oncreateEditar).toHaveBeenCalledWith({ idea: "ponle gafas", file: f, motor: "qwen" });
  });

  it("cambiar de imagen libera la URL de la anterior", async () => {
    const { container } = await montar();
    await userEvent.click(screen.getByRole("tab", { name: "Editar" }));
    const input = container.querySelector('input[type="file"]')!;
    await userEvent.upload(input, archivo());
    await userEvent.upload(input, new File(["y"], "otra.png", { type: "image/png" }));
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:previa");
  });

  it("quitar fondo: sin campo de idea; basta con la imagen", async () => {
    const { p, container } = await montar();
    await userEvent.click(screen.getByRole("tab", { name: "Quitar fondo" }));
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(screen.queryByLabelText("Modelo")).toBeNull();   // no pasa por ComfyUI
    const boton = screen.getByRole("button", { name: "Quitar fondo", hidden: false });
    expect(boton).toBeDisabled();
    const f = archivo();
    await userEvent.upload(container.querySelector('input[type="file"]')!, f);
    await userEvent.click(boton);
    expect(p.oncreateFondo).toHaveBeenCalledWith({ file: f });
  });

  it("'busy' bloquea la creación", async () => {
    await montar(props(), { busy: true });
    await userEvent.type(titulo(), "x");
    expect(screen.getByRole("button", { name: "Crear" })).toBeDisabled();
  });

  it("animada: título y tamaño, sin selector de modelo, y lo manda a su creación", async () => {
    const { p } = await montar();
    await userEvent.click(screen.getByRole("tab", { name: "Animada" }));
    expect(screen.getByText(/10–15 s en bucle/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Modelo")).toBeNull();
    const crear = screen.getByRole("button", { name: "Crear" });
    expect(crear).toBeDisabled();
    // Arranca en horizontal (YouTube).
    expect((screen.getByLabelText("Tamaño") as HTMLSelectElement).value).toBe("1344x768");
    await userEvent.type(titulo(), " un gato groovy ");
    await userEvent.click(crear);
    expect(p.oncreateAnimada).toHaveBeenCalledWith({ ...NUEVA, idea: "un gato groovy", width: 1344, height: 768 });
    expect(p.oncreateGenerar).not.toHaveBeenCalled();
  });

  it("animada respeta un tamaño elegido a mano, y al salir vuelve al vertical", async () => {
    await montar();
    const tam = () => (screen.getByLabelText("Tamaño") as HTMLSelectElement).value;
    await userEvent.click(screen.getByRole("tab", { name: "Animada" }));
    await userEvent.click(screen.getByRole("tab", { name: "Generar" }));
    expect(tam()).toBe("768x1344");
    await userEvent.selectOptions(screen.getByLabelText("Tamaño"), "1024x1024");
    await userEvent.click(screen.getByRole("tab", { name: "Animada" }));
    expect(tam()).toBe("1024x1024");
  });

  it("las etiquetas cambian según el modo", async () => {
    await montar();
    expect(screen.getByText("Título")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "Editar" }));
    expect(screen.getByText("¿Qué cambios o efectos quieres aplicar?")).toBeInTheDocument();
  });
});

describe("ImageConfig: estilo, detalles y previews", () => {
  const props = () => ({
    oncreateGenerar: vi.fn(), oncreateEditar: vi.fn(), oncreateFondo: vi.fn(), oncreateAnimada: vi.fn(),
  });
  const montar = async () => {
    const p = props();
    render(ImageConfig, { ...p, estilos: ESTILOS });
    await waitFor(() => expect(g.listarMotores).toHaveBeenCalled());
    return p;
  };

  it("arranca en libre y la galería enseña Libre, cada estilo y sus ejemplos", async () => {
    await montar();
    expect(screen.getByText("El LLM elige el estilo.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Cambiar/ }));
    const dialogo = screen.getByRole("dialog", { name: "Elegir estilo" });
    const tarjetas = within(dialogo).getAllByRole("button", { pressed: false }).concat(
      within(dialogo).getAllByRole("button", { pressed: true }));
    expect(tarjetas).toHaveLength(3);
    expect(within(dialogo).getByAltText("Tinta y serigrafía, ejemplo 2")).toHaveAttribute(
      "src", "/api/galeria/estilos/tinta/ejemplo/1");
    expect(within(dialogo).getByText("Sin ejemplos todavía")).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("con estilo: se ve en el formulario, se esconde el modelo y viaja con detalles y previews", async () => {
    const p = await montar();
    expect(screen.getByLabelText("Modelo")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Cambiar/ }));
    await userEvent.click(screen.getByRole("button", { name: /Tinta y serigrafía/ }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByText("Línea de tinta y grano")).toBeInTheDocument();
    expect(screen.queryByLabelText("Modelo")).toBeNull();   // el motor es el del estilo
    await userEvent.type(titulo(), "Morning Bossa");
    await userEvent.type(screen.getByLabelText(/^Detalles/), " un gato ");
    await userEvent.selectOptions(screen.getByLabelText("Previews"), "6");
    await userEvent.click(screen.getByRole("button", { name: "Crear" }));
    expect(p.oncreateGenerar).toHaveBeenCalledWith({
      idea: "Morning Bossa", detalles: "un gato", estilo: "tinta", n_previews: 6,
      width: 768, height: 1344, motor: "",
    });
  });

  it("recuerda el estilo y las previews, y olvida un estilo que ya no existe", async () => {
    localStorage.setItem("loomcast.galeria.estilo", "tinta");
    localStorage.setItem("loomcast.galeria.nPreviews", "7");
    const { unmount } = render(ImageConfig, { ...props(), estilos: ESTILOS });
    expect(screen.getByText("Tinta y serigrafía")).toBeInTheDocument();
    expect((screen.getByLabelText("Previews") as HTMLSelectElement).value).toBe("7");
    unmount();
    localStorage.setItem("loomcast.galeria.nPreviews", "99");
    render(ImageConfig, { ...props(), estilos: [ESTILOS[1]] });
    expect(screen.getByText("El LLM elige el estilo.")).toBeInTheDocument();
    expect((screen.getByLabelText("Previews") as HTMLSelectElement).value).toBe("4");
  });
});

describe("ImageStudio", () => {
  const detalle = (extra: Partial<GaleriaDetalle> = {}): GaleriaDetalle => ({
    id: 2, tipo: "generar", motor: "zimage", motor_nombre: "Z-Image", idea: "zorro", prompt: "a fox",
    detalles: "", estilo: "", n_previews: 4,
    width: 768, height: 1344, estado: "nueva", seeds: [], seed_elegido: null,
    prompt_movimiento: "", duracion_s: 12, seed_video: null, escala: null, videos: [],
    ocupado: false, generando_previews: false, ...extra,
  });
  const animada = (extra: Partial<GaleriaDetalle> = {}) =>
    detalle({ tipo: "animada", estado: "final", seeds: [1, 2, 3, 4], seed_elegido: 1, ...extra });
  const resumen = (id: number, idea: string) => ({ id, idea, tipo: "generar" as const, estado: "nueva" });

  beforeEach(() => {
    vi.mocked(g.listarGaleria).mockResolvedValue([resumen(2, "zorro"), resumen(3, "gato")]);
    vi.mocked(g.detalleGaleria).mockResolvedValue(detalle());
    vi.mocked(g.crearGenerar).mockResolvedValue({ id: 8, job_id: 1 });
    vi.mocked(g.cambiarEstilo).mockResolvedValue({ ok: true });
    vi.mocked(g.crearEditar).mockResolvedValue({ id: 8 });
    vi.mocked(g.crearQuitarFondo).mockResolvedValue({ id: 8, job_id: 1 });
    vi.mocked(g.editarPrompt).mockResolvedValue({ ok: true });
    vi.mocked(g.mejorarPrompt).mockResolvedValue({ job_id: 1 });
    vi.mocked(g.lanzarPreviews).mockResolvedValue({ job_id: 2 });
    vi.mocked(g.lanzarFinal).mockResolvedValue({ job_id: 3 });
    vi.mocked(g.borrarGaleria).mockResolvedValue({ borrada: 2, archivos: 0 });
    vi.mocked(g.crearAnimada).mockResolvedValue({ id: 9, job_id: 1 });
    vi.mocked(g.guardarMovimiento).mockResolvedValue({ ok: true });
    vi.mocked(g.mejorarMovimiento).mockResolvedValue({ job_id: 4 });
    vi.mocked(g.animar).mockResolvedValue({ job_id: 5 });
    vi.mocked(g.escalar).mockResolvedValue({ job_id: 6 });
    currentTrack.set(null);
    seleccionPendiente.set(null);
    jobsDrenados.set(0);
    jobs.set([]);
    vi.stubGlobal("confirm", vi.fn().mockReturnValue(true));
  });

  const abrir = async () => {
    render(ImageStudio);
    await userEvent.click(await screen.findByText("zorro"));
    await screen.findByText("Trabajo");
    await screen.findByDisplayValue("a fox");
  };

  it("carga la lista y cuenta (singular/plural)", async () => {
    render(ImageStudio);
    expect(await screen.findByText("zorro")).toBeInTheDocument();
    expect(screen.getByText("2 imágenes")).toBeInTheDocument();
  });

  it("lista vacía y error de carga", async () => {
    vi.mocked(g.listarGaleria).mockResolvedValue([]);
    const { unmount } = render(ImageStudio);
    expect(await screen.findByText(/Sin imágenes aún/)).toBeInTheDocument();
    unmount();
    vi.mocked(g.listarGaleria).mockRejectedValue(new Error("HTTP 500"));
    render(ImageStudio);
    expect(await screen.findByText("HTTP 500")).toBeInTheDocument();
  });

  it("crear (generar) crea, refresca y abre la imagen nueva", async () => {
    render(ImageStudio);
    await screen.findByText("zorro");
    await userEvent.type(screen.getAllByRole("textbox")[0], "un faro");
    await waitFor(() => expect(screen.getByRole("button", { name: "Crear" })).toBeEnabled());
    await userEvent.click(screen.getByRole("button", { name: "Crear" }));
    await waitFor(() => expect(g.crearGenerar).toHaveBeenCalledWith(expect.objectContaining({ idea: "un faro", width: 768 })));
    await waitFor(() => expect(g.detalleGaleria).toHaveBeenCalledWith(8));
  });

  it("si crear falla muestra el error", async () => {
    vi.mocked(g.crearGenerar).mockRejectedValue(new Error("HTTP 400"));
    render(ImageStudio);
    await screen.findByText("zorro");
    await userEvent.type(screen.getAllByRole("textbox")[0], "x");
    await userEvent.click(screen.getByRole("button", { name: "Crear" }));
    expect(await screen.findByText("HTTP 400")).toBeInTheDocument();
  });

  it("generar previews guarda la escena editada antes de lanzarlas, con las que se pidan", async () => {
    await abrir();
    const caja = screen.getByDisplayValue("a fox");
    await userEvent.clear(caja);
    await userEvent.type(caja, "a blue fox");
    await userEvent.selectOptions(screen.getByLabelText("Cuántas previews"), "3");
    await userEvent.click(screen.getByRole("button", { name: "Generar previews" }));
    await waitFor(() => expect(g.lanzarPreviews).toHaveBeenCalledWith(2, { n_previews: 3 }));
    expect(g.editarPrompt).toHaveBeenCalledWith(2, "a blue fox");
    expect(vi.mocked(g.editarPrompt).mock.invocationCallOrder[0]).toBeLessThan(vi.mocked(g.lanzarPreviews).mock.invocationCallOrder[0]);
  });

  it("reescribir la escena con el LLM la pide para la imagen abierta", async () => {
    await abrir();
    await userEvent.click(screen.getByRole("button", { name: "Reescribir con el LLM" }));
    await waitFor(() => expect(g.mejorarPrompt).toHaveBeenCalledWith(2));
  });

  it("con estilo: título, detalles, la escena plegada si ya hay previews, y se puede cambiar el estilo", async () => {
    vi.mocked(g.detalleGaleria).mockResolvedValue(
      detalle({ estilo: "tinta", detalles: "un gato", estado: "previews", seeds: [1, 2] }));
    await abrir();
    expect(screen.getByText("un gato")).toBeInTheDocument();
    const escena = screen.getByText("Escena (inglés, editable)").closest("details")!;
    expect(escena.open).toBe(false);
    expect(screen.getByText(/el estilo «Tinta y serigrafía» se añade/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Regenerar previews" })).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Estilo"), "plano");
    await waitFor(() => expect(g.cambiarEstilo).toHaveBeenCalledWith(2, "plano"));
  });

  it("mientras el LLM escribe la escena lo dice", async () => {
    vi.mocked(g.detalleGaleria).mockResolvedValue(detalle({ prompt: null, ocupado: true }));
    render(ImageStudio);
    await userEvent.click(await screen.findByText("zorro"));
    expect(await screen.findByText("Escribiendo la escena…")).toBeInTheDocument();
  });

  it("editar conserva su prompt con «Mejorar prompt con el LLM»", async () => {
    vi.mocked(g.detalleGaleria).mockResolvedValue(detalle({ tipo: "editar" }));
    await abrir();
    expect(screen.getByRole("button", { name: "Mejorar prompt con el LLM" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Estilo")).toBeNull();
  });

  it("flujo completo: elegir una preview y generar la final", async () => {
    vi.mocked(g.detalleGaleria).mockResolvedValue(detalle({ estado: "previews", seeds: [1, 2, 3, 4] }));
    await abrir();
    const final = await screen.findByRole("button", { name: "Generar máxima resolución" });
    expect(final).toBeDisabled();           // hay que elegir primero
    await userEvent.click(screen.getByAltText("preview 2"));
    expect(final).toBeEnabled();
    await userEvent.click(final);
    await waitFor(() => expect(g.lanzarFinal).toHaveBeenCalledWith(2, 1));
  });

  it("si lanzar la final falla muestra el error", async () => {
    vi.mocked(g.detalleGaleria).mockResolvedValue(detalle({ estado: "previews", seeds: [1, 2] }));
    vi.mocked(g.lanzarFinal).mockRejectedValue(new Error("HTTP 409"));
    await abrir();
    await userEvent.click(await screen.findByAltText("preview 1"));
    await userEvent.click(screen.getByRole("button", { name: "Generar máxima resolución" }));
    expect(await screen.findByText("HTTP 409")).toBeInTheDocument();
  });

  it("'Elegir otra preview' desde la final vuelve a mostrar la cuadrícula", async () => {
    vi.mocked(g.detalleGaleria).mockResolvedValue(detalle({ estado: "final", seeds: [1, 2] }));
    await abrir();
    expect(await screen.findByAltText("final")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Elegir otra preview" }));
    expect(await screen.findByAltText("preview 1")).toBeInTheDocument();
  });

  it("borrar pide confirmación y, si era la abierta, la cierra", async () => {
    await abrir();
    vi.stubGlobal("confirm", vi.fn().mockReturnValue(false));
    await userEvent.click(screen.getAllByRole("button", { name: "Borrar imagen" })[0]);
    expect(g.borrarGaleria).not.toHaveBeenCalled();

    vi.stubGlobal("confirm", vi.fn().mockReturnValue(true));
    await userEvent.click(screen.getAllByRole("button", { name: "Borrar imagen" })[0]);
    await waitFor(() => expect(g.borrarGaleria).toHaveBeenCalledWith(2));
    expect(await screen.findByText(/Selecciona una imagen/)).toBeInTheDocument();
  });

  it("al terminar un job refresca lista y detalle", async () => {
    await abrir();
    vi.mocked(g.listarGaleria).mockClear();
    vi.mocked(g.detalleGaleria).mockClear();
    jobsDrenados.update((n) => n + 1);
    await waitFor(() => expect(g.listarGaleria).toHaveBeenCalled());
    await waitFor(() => expect(g.detalleGaleria).toHaveBeenCalledWith(2));
  });

  it("cada preview que sale de la tirada de la imagen abierta recarga el detalle", async () => {
    await abrir();
    const tirada = (hecho: number, ref_id = 2) => ({
      id: 50, tipo: "generar_previews_imagen", estado: "corriendo", ref_id, intentos: 0, sin_corte: null,
      progreso: { job_id: 50, transcurrido_s: 1, fase: "", hecho, total: 4, pct: null, eta_s: null },
    });
    vi.mocked(g.detalleGaleria).mockClear();
    jobs.set([tirada(0)]);
    await waitFor(() => expect(g.detalleGaleria).toHaveBeenCalledTimes(1));
    jobs.set([tirada(0)]);                 // el mismo paso no recarga otra vez
    jobs.set([tirada(1)]);
    await waitFor(() => expect(g.detalleGaleria).toHaveBeenCalledTimes(2));
    jobs.set([tirada(2, 3)]);              // la tirada de otra imagen no toca esta
    await new Promise((r) => setTimeout(r, 20));
    expect(g.detalleGaleria).toHaveBeenCalledTimes(2);
  });

  it("un salto desde la Biblioteca abre esa imagen y consume la señal", async () => {
    seleccionPendiente.set({ modo: "imagenes", id: 3 });
    render(ImageStudio);
    await waitFor(() => expect(g.detalleGaleria).toHaveBeenCalledWith(3));
    expect(get(seleccionPendiente)).toBeNull();
  });

  it("una señal de otro modo no se consume", async () => {
    seleccionPendiente.set({ modo: "musica", id: 3 });
    render(ImageStudio);
    await screen.findByText("zorro");
    expect(get(seleccionPendiente)).toEqual({ modo: "musica", id: 3 });
  });

  it("una imagen ocupada bloquea las acciones del detalle", async () => {
    vi.mocked(g.detalleGaleria).mockResolvedValue(detalle({ ocupado: true }));
    await abrir();
    expect(screen.getByRole("button", { name: "Reescribir con el LLM" })).toBeDisabled();
  });

  it("'+ Nueva imagen' cierra la imagen abierta", async () => {
    await abrir();
    await userEvent.click(screen.getByRole("button", { name: "+ Nueva imagen" }));
    expect(await screen.findByText(/Selecciona una imagen/)).toBeInTheDocument();
  });

  describe("animada", () => {
    it("crear una animada la abre", async () => {
      render(ImageStudio);
      await screen.findByText("zorro");
      await userEvent.click(screen.getByRole("tab", { name: "Animada" }));
      await userEvent.type(screen.getAllByRole("textbox")[0], "un gato groovy");
      await userEvent.click(screen.getByRole("button", { name: "Crear" }));
      await waitFor(() => expect(g.crearAnimada).toHaveBeenCalledWith({ ...NUEVA, idea: "un gato groovy", width: 1344, height: 768 }));
      await waitFor(() => expect(g.detalleGaleria).toHaveBeenCalledWith(9));
    });

    it("en las previews se aprueba una para animar, no se amplía", async () => {
      vi.mocked(g.detalleGaleria).mockResolvedValue(animada({ estado: "previews", seed_elegido: null }));
      vi.mocked(g.lanzarFinal).mockResolvedValue({ job_id: null });
      await abrir();
      expect(screen.getByText("Elige la que quieres animar")).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Generar máxima resolución" })).toBeNull();
      await userEvent.click(screen.getByAltText("preview 3"));
      await userEvent.click(screen.getByRole("button", { name: "Aprobar esta imagen" }));
      await waitFor(() => expect(g.lanzarFinal).toHaveBeenCalledWith(2, 2));
    });

    it("aprobada: escribe el movimiento y anima guardándolo antes", async () => {
      vi.mocked(g.detalleGaleria).mockResolvedValue(animada());
      await abrir();
      expect(screen.getByAltText("imagen aprobada")).toBeInTheDocument();
      const animar = screen.getByRole("button", { name: "Animar" });
      const mejorar = screen.getByRole("button", { name: "Mejorar con IA" });
      expect(animar).toBeDisabled();
      expect(mejorar).toBeDisabled();
      await userEvent.type(screen.getByLabelText("Prompt de movimiento"), "se balancea y da un sorbo");
      const dur = screen.getByRole("slider") as HTMLInputElement;
      expect(dur.min).toBe("10");
      expect(dur.max).toBe("15");
      await fireInput(dur, "14");
      await userEvent.click(animar);
      await waitFor(() => expect(g.animar).toHaveBeenCalledWith(2));
      expect(g.guardarMovimiento).toHaveBeenCalledWith(2, "se balancea y da un sorbo", 14);
      expect(vi.mocked(g.guardarMovimiento).mock.invocationCallOrder[0]).toBeLessThan(
        vi.mocked(g.animar).mock.invocationCallOrder[0],
      );
    });

    it("«Mejorar con IA» guarda el texto y pide pulirlo", async () => {
      vi.mocked(g.detalleGaleria).mockResolvedValue(animada({ estado: "movimiento", prompt_movimiento: "que baile", duracion_s: 11 }));
      await abrir();
      expect(screen.getByDisplayValue("que baile")).toBeInTheDocument();
      await userEvent.click(screen.getByRole("button", { name: "Mejorar con IA" }));
      await waitFor(() => expect(g.mejorarMovimiento).toHaveBeenCalledWith(2));
      expect(g.guardarMovimiento).toHaveBeenCalledWith(2, "que baile", 11);
    });

    it("con vídeo: bucle mudo en loop, descarga y escalado de lo que falta", async () => {
      vi.mocked(g.detalleGaleria).mockResolvedValue(
        animada({ estado: "escalada", prompt_movimiento: "x", videos: ["base", "2k"], escala: "2k" }),
      );
      await abrir();
      const video = document.querySelector("video")!;
      expect(video.loop).toBe(true);
      expect(video.muted).toBe(true);
      expect(video.getAttribute("src")).toMatch(/^\/api\/galeria\/2\/video\?v=/);
      expect(screen.getByText("Descargar MP4").closest("a")).toHaveAttribute("href", "/api/galeria/2/video");
      expect(screen.getByText("MP4 2K").closest("a")).toHaveAttribute("href", "/api/galeria/2/video?escala=2k");
      expect(screen.queryByRole("button", { name: "Escalar a 2K" })).toBeNull();
      await userEvent.click(screen.getByRole("button", { name: "Escalar a Full HD" }));
      await waitFor(() => expect(g.escalar).toHaveBeenCalledWith(2, "1080p"));
      expect(screen.getByRole("button", { name: "Volver a animar" })).toBeEnabled();
      await userEvent.click(screen.getByRole("button", { name: "Escalar a 4K" }));
      await waitFor(() => expect(g.escalar).toHaveBeenCalledWith(2, "4k"));
    });

    it("ocupada bloquea animar y escalar", async () => {
      vi.mocked(g.detalleGaleria).mockResolvedValue(
        animada({ estado: "animada", prompt_movimiento: "x", videos: ["base"], ocupado: true }),
      );
      await abrir();
      expect(screen.getByRole("button", { name: "Volver a animar" })).toBeDisabled();
      expect(screen.getByRole("button", { name: "Escalar a 4K" })).toBeDisabled();
    });

    it("si animar falla muestra el error", async () => {
      vi.mocked(g.detalleGaleria).mockResolvedValue(animada({ prompt_movimiento: "x" }));
      vi.mocked(g.animar).mockRejectedValue(new Error("HTTP 409"));
      await abrir();
      await userEvent.click(screen.getByRole("button", { name: "Animar" }));
      expect(await screen.findByText("HTTP 409")).toBeInTheDocument();
    });
  });
});
