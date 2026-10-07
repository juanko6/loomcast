import { render, screen, waitFor, within } from "@testing-library/svelte";
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
  };
});
vi.mock("@/lib/api", async (o) => ({ ...(await o<typeof import("@/lib/api")>()), api: vi.fn().mockResolvedValue([]) }));

import * as g from "@/lib/galeria";
import type { GaleriaDetalle, MotorImagen } from "@/lib/galeria";
import { currentTrack } from "@/lib/player";
import { jobsDrenados, seleccionPendiente } from "@/lib/stores";
import ImageConfig from "../imagenes/ImageConfig.svelte";
import ImageStudio from "../imagenes/ImageStudio.svelte";

const MOTORES: MotorImagen[] = [
  { id: "zimage", nombre: "Z-Image Turbo", modos: ["generar"], defecto_en: ["generar"] },
  { id: "qwen", nombre: "Qwen-Image-Edit", modos: ["editar"], defecto_en: ["editar"] },
  { id: "flux2klein", nombre: "FLUX.2 Klein", modos: ["generar", "editar"], defecto_en: [] },
];
const archivo = () => new File(["x"], "foto.png", { type: "image/png" });

beforeEach(() => {
  vi.mocked(g.listarMotores).mockResolvedValue(MOTORES);
  vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: vi.fn(() => "blob:previa"), revokeObjectURL: vi.fn() }));
});

describe("ImageConfig", () => {
  const props = () => ({ oncreateGenerar: vi.fn(), oncreateEditar: vi.fn(), oncreateFondo: vi.fn() });
  const montar = async (p = props(), extra = {}) => {
    const r = render(ImageConfig, { ...p, ...extra });
    await waitFor(() => expect(g.listarMotores).toHaveBeenCalled());
    return { ...r, p };
  };

  it("generar: 'Crear' bloqueado sin idea, y manda tamaño y motor por defecto", async () => {
    const { p } = await montar();
    const crear = screen.getByRole("button", { name: "Crear" });
    expect(crear).toBeDisabled();
    await userEvent.type(screen.getByRole("textbox"), "  un faro  ");
    await userEvent.click(crear);
    expect(p.oncreateGenerar).toHaveBeenCalledWith({ idea: "un faro", width: 768, height: 1344, motor: "zimage" });
  });

  it("un tamaño predefinido distinto se envía tal cual", async () => {
    const { p } = await montar();
    await userEvent.type(screen.getByRole("textbox"), "x");
    await userEvent.selectOptions(screen.getByLabelText("Tamaño"), "1024x1024");
    await userEvent.click(screen.getByRole("button", { name: "Crear" }));
    expect(p.oncreateGenerar).toHaveBeenCalledWith(expect.objectContaining({ width: 1024, height: 1024 }));
  });

  it("tamaño personalizado: aparecen ancho y alto, y se envían", async () => {
    const { p } = await montar();
    await userEvent.type(screen.getByRole("textbox"), "x");
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
    await userEvent.type(screen.getByRole("textbox"), "x");
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
    await userEvent.type(screen.getByRole("textbox"), "x");
    await userEvent.click(screen.getByRole("button", { name: "Crear" }));
    expect(p.oncreateGenerar).toHaveBeenCalledWith(expect.objectContaining({ motor: "flux2klein" }));
  });

  it("editar: exige idea Y imagen, muestra la vista previa y envía ambas", async () => {
    const { p, container } = await montar();
    await userEvent.click(screen.getByRole("tab", { name: "Editar" }));
    const crear = screen.getByRole("button", { name: "Subir imagen" });
    expect(crear).toBeDisabled();

    await userEvent.type(screen.getByRole("textbox"), "  ponle gafas ");
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
    await userEvent.type(screen.getByRole("textbox"), "x");
    expect(screen.getByRole("button", { name: "Crear" })).toBeDisabled();
  });

  it("las etiquetas cambian según el modo", async () => {
    await montar();
    expect(screen.getByText("¿Qué imagen quieres?")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "Editar" }));
    expect(screen.getByText("¿Qué cambios o efectos quieres aplicar?")).toBeInTheDocument();
  });
});

describe("ImageStudio", () => {
  const detalle = (extra: Partial<GaleriaDetalle> = {}): GaleriaDetalle => ({
    id: 2, tipo: "generar", motor: "zimage", motor_nombre: "Z-Image", idea: "zorro", prompt: "a fox",
    width: 768, height: 1344, estado: "nueva", seeds: [], seed_elegido: null, ocupado: false, ...extra,
  });
  const resumen = (id: number, idea: string) => ({ id, idea, tipo: "generar" as const, estado: "nueva" });

  beforeEach(() => {
    vi.mocked(g.listarGaleria).mockResolvedValue([resumen(2, "zorro"), resumen(3, "gato")]);
    vi.mocked(g.detalleGaleria).mockResolvedValue(detalle());
    vi.mocked(g.crearGenerar).mockResolvedValue({ id: 8 });
    vi.mocked(g.crearEditar).mockResolvedValue({ id: 8 });
    vi.mocked(g.crearQuitarFondo).mockResolvedValue({ id: 8, job_id: 1 });
    vi.mocked(g.editarPrompt).mockResolvedValue({ ok: true });
    vi.mocked(g.mejorarPrompt).mockResolvedValue({ job_id: 1 });
    vi.mocked(g.lanzarPreviews).mockResolvedValue({ job_id: 2 });
    vi.mocked(g.lanzarFinal).mockResolvedValue({ job_id: 3 });
    vi.mocked(g.borrarGaleria).mockResolvedValue({ borrada: 2, archivos: 0 });
    currentTrack.set(null);
    seleccionPendiente.set(null);
    jobsDrenados.set(0);
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

  it("generar previews guarda el prompt editado antes de lanzarlas", async () => {
    await abrir();
    const caja = screen.getByDisplayValue("a fox");
    await userEvent.clear(caja);
    await userEvent.type(caja, "a blue fox");
    await userEvent.click(screen.getByRole("button", { name: "Generar 4 previews" }));
    await waitFor(() => expect(g.lanzarPreviews).toHaveBeenCalledWith(2));
    expect(g.editarPrompt).toHaveBeenCalledWith(2, "a blue fox");
    expect(vi.mocked(g.editarPrompt).mock.invocationCallOrder[0]).toBeLessThan(vi.mocked(g.lanzarPreviews).mock.invocationCallOrder[0]);
  });

  it("mejorar el prompt con el LLM lo pide para la imagen abierta", async () => {
    await abrir();
    await userEvent.click(screen.getByRole("button", { name: "Mejorar prompt con el LLM" }));
    await waitFor(() => expect(g.mejorarPrompt).toHaveBeenCalledWith(2));
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
    expect(screen.getByRole("button", { name: "Mejorar prompt con el LLM" })).toBeDisabled();
  });

  it("'+ Nueva imagen' cierra la imagen abierta", async () => {
    await abrir();
    await userEvent.click(screen.getByRole("button", { name: "+ Nueva imagen" }));
    expect(await screen.findByText(/Selecciona una imagen/)).toBeInTheDocument();
  });
});
