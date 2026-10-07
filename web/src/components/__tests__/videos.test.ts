import { render, screen, waitFor } from "@testing-library/svelte";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { Idea, ProyectoDetalle } from "@/lib/proyectos";
import IdeasView from "../videos/IdeasView.svelte";
import ProjectView from "../videos/ProjectView.svelte";
import StepGuion from "../videos/steps/StepGuion.svelte";
import StepMetadatos from "../videos/steps/StepMetadatos.svelte";

function proyecto(extra: Partial<ProyectoDetalle> = {}): ProyectoDetalle {
  return {
    id: 1, slug: "demo", estado: "IDEA", plantilla: "curiosidades", voz: null, voz_instruct: "",
    idea: { titulo: "Un título", gancho: "g", resumen: "r" },
    guion: null, guion_version: 0, metadatos: null, voz_disponible: false, voz_version: 0,
    subtitulos: null, escenas: [], personajes: [], imagenes_completas: false,
    video_disponible: false, versiones: [], jobs_activos: 0, job_activo: null, ...extra,
  };
}

const GUION_FRASES = { gancho: "Hola", frases: ["Uno", "Dos"], cta: "Suscríbete" };
const GUION_NARRACION = { gancho: "Hola", narracion: "Érase una vez", cta: "Fin" };

describe("IdeasView", () => {
  const idea = (extra: Partial<Idea> = {}): Idea => ({
    id: 1, titulo: "Idea uno", gancho: "Un gancho", resumen: "Un resumen", estado: "propuesta",
    proyecto_id: null, ...extra,
  });
  const props = () => ({
    onaprobar: vi.fn(), ondescartar: vi.fn(), onrestaurar: vi.fn(), onabrirproyecto: vi.fn(), onmas: vi.fn(),
  });

  it("sin ideas avisa de que se están generando", () => {
    render(IdeasView, { ideas: [], ...props() });
    expect(screen.getByText(/Generando ideas/)).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("una idea propuesta se puede aprobar o descartar", async () => {
    const p = props();
    render(IdeasView, { ideas: [idea({ id: 7 })], ...p });
    await userEvent.click(screen.getByRole("button", { name: "Aprobar y crear proyecto" }));
    await userEvent.click(screen.getByRole("button", { name: "Descartar" }));
    expect(p.onaprobar).toHaveBeenCalledWith(7);
    expect(p.ondescartar).toHaveBeenCalledWith(7);
  });

  it("una idea descartada se puede restaurar y se ve atenuada", async () => {
    const p = props();
    const { container } = render(IdeasView, { ideas: [idea({ id: 3, estado: "descartada" })], ...p });
    expect(screen.queryByRole("button", { name: "Descartar" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Restaurar" }));
    expect(p.onrestaurar).toHaveBeenCalledWith(3);
    expect(container.querySelector("article")!.className).toContain("opacity-45");
  });

  it("una idea con proyecto ofrece abrirlo y ya no se puede aprobar", async () => {
    const p = props();
    render(IdeasView, { ideas: [idea({ proyecto_id: 9, estado: "aprobada" })], ...p });
    expect(screen.getByText("proyecto creado")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Aprobar/ })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: /Ver proyecto/ }));
    expect(p.onabrirproyecto).toHaveBeenCalledWith(9);
  });

  it("'busy' bloquea aprobar y pedir más ideas", () => {
    render(IdeasView, { ideas: [idea()], busy: true, ...props() });
    expect(screen.getByRole("button", { name: "Aprobar y crear proyecto" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Generar más ideas" })).toBeDisabled();
  });

  it("'Generar más ideas' lo pide", async () => {
    const p = props();
    render(IdeasView, { ideas: [idea()], ...p });
    await userEvent.click(screen.getByRole("button", { name: "Generar más ideas" }));
    expect(p.onmas).toHaveBeenCalled();
  });
});

describe("StepGuion", () => {
  it("sin guion avisa de que se está escribiendo", () => {
    render(StepGuion, { p: proyecto(), onsave: vi.fn(), onregen: vi.fn() });
    expect(screen.getByText(/Escribiendo el guion/)).toBeInTheDocument();
  });

  it("formato frases: muestra una caja por frase y guarda las editadas, sin las vacías", async () => {
    const onsave = vi.fn();
    render(StepGuion, { p: proyecto({ guion: GUION_FRASES, guion_version: 3 }), onsave, onregen: vi.fn() });

    const campos = screen.getAllByRole("textbox") as HTMLInputElement[];
    expect(campos.map((c) => c.value)).toEqual(["Hola", "Uno", "Dos", "Suscríbete"]);
    expect(screen.getByText("Versión 3")).toBeInTheDocument();

    await userEvent.clear(campos[2]);                       // vacía la segunda frase
    await userEvent.type(campos[1], " editada");
    await userEvent.click(screen.getByRole("button", { name: "Guardar guion" }));

    expect(onsave).toHaveBeenCalledWith({ gancho: "Hola", frases: ["Uno editada"], cta: "Suscríbete" });
  });

  it("recorta los espacios de las frases al guardar", async () => {
    const onsave = vi.fn();
    render(StepGuion, { p: proyecto({ guion: { ...GUION_FRASES, frases: ["  Uno  "] } }), onsave, onregen: vi.fn() });
    await userEvent.click(screen.getByRole("button", { name: "Guardar guion" }));
    expect(onsave.mock.calls[0][0].frases).toEqual(["Uno"]);
  });

  it("se pueden añadir y quitar frases", async () => {
    const onsave = vi.fn();
    render(StepGuion, { p: proyecto({ guion: GUION_FRASES }), onsave, onregen: vi.fn() });
    await userEvent.click(screen.getByRole("button", { name: "+ Añadir frase" }));
    expect(screen.getAllByRole("textbox")).toHaveLength(5);
    await userEvent.click(screen.getAllByTitle("Quitar frase")[0]);
    await userEvent.click(screen.getByRole("button", { name: "Guardar guion" }));
    expect(onsave.mock.calls[0][0].frases).toEqual(["Dos"]);   // la nueva vacía no se guarda
  });

  it("formato narración: un único cuerpo y se guarda sin frases", async () => {
    const onsave = vi.fn();
    render(StepGuion, { p: proyecto({ guion: GUION_NARRACION }), onsave, onregen: vi.fn() });
    expect(screen.queryByRole("button", { name: "+ Añadir frase" })).toBeNull();
    const cuerpo = screen.getByLabelText("Narración") as HTMLTextAreaElement;
    expect(cuerpo.value).toBe("Érase una vez");
    await userEvent.type(cuerpo, "!");
    await userEvent.click(screen.getByRole("button", { name: "Guardar guion" }));
    expect(onsave).toHaveBeenCalledWith({ gancho: "Hola", narracion: "Érase una vez!", cta: "Fin" });
  });

  it("regenerar avisa y 'busy' lo bloquea", async () => {
    const onregen = vi.fn();
    const { rerender } = render(StepGuion, { p: proyecto({ guion: GUION_FRASES }), onregen, onsave: vi.fn() });
    await userEvent.click(screen.getByRole("button", { name: "Regenerar con el LLM" }));
    expect(onregen).toHaveBeenCalled();
    await rerender({ p: proyecto({ guion: GUION_FRASES }), busy: true, onregen, onsave: vi.fn() });
    expect(screen.getByRole("button", { name: "Regenerar con el LLM" })).toBeDisabled();
  });

  it("si el LLM reescribe el guion, el borrador se resincroniza", async () => {
    const { rerender } = render(StepGuion, { p: proyecto({ guion: GUION_FRASES }), onsave: vi.fn(), onregen: vi.fn() });
    await rerender({ p: proyecto({ guion: { ...GUION_FRASES, gancho: "Nuevo gancho" }, guion_version: 2 }), onsave: vi.fn(), onregen: vi.fn() });
    await waitFor(() => expect((screen.getAllByRole("textbox")[0] as HTMLInputElement).value).toBe("Nuevo gancho"));
  });
});

describe("StepMetadatos", () => {
  const meta = {
    youtube: { titulo: "Título YT", descripcion: "Descripción larga", etiquetas: ["a", "b"] },
    tiktok: { descripcion: "Texto TikTok" },
  };

  it("sin metadatos ofrece generarlos y lo explica", async () => {
    const ongenerar = vi.fn();
    render(StepMetadatos, { p: proyecto(), ongenerar });
    expect(screen.getByText(/Genera los metadatos cuando la narración/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Generar título, descripción y etiquetas/ }));
    expect(ongenerar).toHaveBeenCalled();
  });

  it("con metadatos los muestra y el botón pasa a regenerar", () => {
    render(StepMetadatos, { p: proyecto({ metadatos: meta }), ongenerar: vi.fn() });
    expect(screen.getByText("Título YT")).toBeInTheDocument();
    expect(screen.getByText("Descripción larga")).toBeInTheDocument();
    expect(screen.getByText("Texto TikTok")).toBeInTheDocument();
    expect(screen.getByText("a")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Regenerar metadatos" })).toBeInTheDocument();
  });

  it("'busy' bloquea la generación", () => {
    render(StepMetadatos, { p: proyecto(), busy: true, ongenerar: vi.fn() });
    expect(screen.getByRole("button")).toBeDisabled();
  });
});

describe("ProjectView: qué paso se muestra", () => {
  const acciones = new Proxy({}, { get: () => vi.fn() }) as Record<string, any>;
  const montar = (p: ProyectoDetalle) => render(ProjectView, { p, voces: [], acciones, onver: vi.fn() });
  const activo = () => screen.getByRole("button", { current: "step" }).textContent!.replace(/^\s*\S+\s*/, "").trim();

  it("proyecto nuevo: empieza en Guion y el resto está bloqueado", () => {
    montar(proyecto());
    expect(activo()).toBe("Guion");
    for (const n of ["Voz", "Metadatos", "Escenas e imágenes", "Vídeo final"]) {
      expect(screen.getByRole("button", { name: new RegExp(n) })).toBeDisabled();
    }
  });

  it("con guion se desbloquea Voz y pasa a ser el paso sugerido", () => {
    montar(proyecto({ guion: GUION_FRASES }));
    expect(screen.getByRole("button", { name: /Voz/ })).toBeEnabled();
    expect(activo()).toBe("Voz");
    expect(screen.getByRole("button", { name: /Metadatos/ })).toBeDisabled();
  });

  it("con la voz hecha se desbloquea Metadatos", () => {
    montar(proyecto({ guion: GUION_FRASES, voz_disponible: true }));
    expect(screen.getByRole("button", { name: /Metadatos/ })).toBeEnabled();
    expect(activo()).toBe("Metadatos");
  });

  it("Escenas se desbloquea con los subtítulos, y Vídeo con las imágenes completas", () => {
    montar(proyecto({ guion: GUION_FRASES, voz_disponible: true, subtitulos: "1\n...", metadatos: {} as never }));
    expect(screen.getByRole("button", { name: /Escenas/ })).toBeEnabled();
    expect(screen.getByRole("button", { name: /Vídeo final/ })).toBeDisabled();
  });

  it("con todo hecho, el sugerido es el último paso", () => {
    montar(proyecto({
      guion: GUION_FRASES, voz_disponible: true, subtitulos: "x", metadatos: {} as never,
      imagenes_completas: true, video_disponible: true,
    }));
    expect(activo()).toBe("Vídeo final");
  });

  it("el usuario puede elegir un paso desbloqueado, y no uno bloqueado", async () => {
    montar(proyecto({ guion: GUION_FRASES }));
    await userEvent.click(screen.getByRole("button", { name: /Guion/ }));
    expect(activo()).toBe("Guion");
    await userEvent.click(screen.getByRole("button", { name: /Vídeo final/ }));
    expect(activo()).toBe("Guion");   // el bloqueado no responde
  });

  it("si el paso elegido se vuelve a bloquear, cae al sugerido", async () => {
    const { rerender } = render(ProjectView, { p: proyecto({ guion: GUION_FRASES, voz_disponible: true }), voces: [], acciones, onver: vi.fn() });
    await userEvent.click(screen.getByRole("button", { name: /Metadatos/ }));
    expect(activo()).toBe("Metadatos");
    await rerender({ p: proyecto({ guion: null }), voces: [], acciones, onver: vi.fn() });
    expect(activo()).toBe("Guion");
  });

  it("muestra el título de la idea (o el slug), el estado y la etapa en curso", () => {
    const { unmount } = montar(proyecto({ estado: "VOZ", job_activo: "generar_voz", jobs_activos: 1 }));
    expect(screen.getByRole("heading", { name: "Un título" })).toBeInTheDocument();
    expect(screen.getByText("VOZ")).toBeInTheDocument();
    expect(screen.getByText("Generando la narración…")).toBeInTheDocument();
    unmount();
    montar(proyecto({ idea: null }));
    expect(screen.getByRole("heading", { name: "demo" })).toBeInTheDocument();
    expect(screen.queryByText("Generando la narración…")).toBeNull();
  });

  it("con un job activo desconocido no muestra etapa (ni revienta)", () => {
    montar(proyecto({ job_activo: "tipo_nuevo", jobs_activos: 1 }));
    expect(screen.getByRole("heading")).toBeInTheDocument();
  });

  it("guardar el guion delega en la acción inyectada", async () => {
    const guardarGuion = vi.fn();
    render(ProjectView, {
      p: proyecto({ guion: GUION_FRASES }), voces: [], onver: vi.fn(),
      acciones: { ...acciones, guardarGuion },
    });
    await userEvent.click(screen.getByRole("button", { name: /Guion/ }));
    await userEvent.click(screen.getByRole("button", { name: "Guardar guion" }));
    expect(guardarGuion).toHaveBeenCalledWith({ gancho: "Hola", frases: ["Uno", "Dos"], cta: "Suscríbete" });
  });
});
