import { render, screen, within } from "@testing-library/svelte";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { Escena, Personaje, ProyectoDetalle } from "@/lib/proyectos";
import StepEscenas from "../videos/steps/StepEscenas.svelte";

const escena = (orden: number, extra: Partial<Escena> = {}): Escena => ({
  orden, texto: `texto ${orden}`, prompt: `prompt ${orden}`, prompt_movimiento: `mov ${orden}`,
  t_inicio: orden * 4, t_fin: orden * 4 + 4, imagen: true, imagen_s: null, clip: false, clip_s: null,
  clip_modo: null, clip_viejo: false, modo: null, en_cola: null, personajes: [], ...extra,
});
const personaje = (clave: string, extra: Partial<Personaje> = {}): Personaje =>
  ({ clave, nombre: `Nombre ${clave}`, ficha: `ficha de ${clave}`, retrato: false, ...extra });

const proy = (extra: Partial<ProyectoDetalle> = {}): ProyectoDetalle => ({
  id: 1, slug: "demo", estado: "ESCENAS", plantilla: "curiosidades", voz: null, voz_instruct: "", idea: null,
  guion: null, guion_version: 1, metadatos: null, voz_disponible: true, voz_version: 0, subtitulos: "x",
  escenas: [escena(0), escena(1), escena(2)], personajes: [], imagenes_completas: false,
  video_disponible: false, versiones: [], jobs_activos: 0, job_activo: null,
  musica: null, musica_mezclar: false, ...extra,
});

const acciones = () => ({
  ongenerar: vi.fn(), onguardar: vi.fn(), ongenerarcasting: vi.fn(), onguardarcasting: vi.fn(),
  ongenerarretrato: vi.fn(), onanadirpersonaje: vi.fn(), onborrarpersonaje: vi.fn(),
  ongenerarimagenes: vi.fn(), onregenimagen: vi.fn(), onregenclip: vi.fn(), onfijarmodos: vi.fn(), onver: vi.fn(),
});
const montar = (p: ProyectoDetalle, a = acciones(), extra = {}) => ({ ...render(StepEscenas, { p, ...a, ...extra }), a });

describe("sin escenas", () => {
  it("ofrece generar los prompts y lo explica", async () => {
    const { a } = montar(proy({ escenas: [] }));
    expect(screen.getByText(/El LLM propone un prompt visual/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Generar prompts de escenas" }));
    expect(a.ongenerar).toHaveBeenCalled();
  });

  it("'busy' bloquea la generación", () => {
    montar(proy({ escenas: [] }), acciones(), { busy: true });
    expect(screen.getByRole("button", { name: "Generar prompts de escenas" })).toBeDisabled();
  });
});

describe("tira y detalle de escenas", () => {
  it("muestra una miniatura por escena y abre la primera", () => {
    montar(proy());
    for (const n of [1, 2, 3]) expect(screen.getAllByAltText(`escena ${n}`).length).toBeGreaterThan(0);
    expect((screen.getByPlaceholderText("Prompt visual (imagen)") as HTMLTextAreaElement).value).toBe("prompt 0");
    expect(screen.getByText("#1")).toBeInTheDocument();
    expect(screen.getByText("0.0–4.0s")).toBeInTheDocument();
  });

  it("pulsar otra escena abre su detalle", async () => {
    montar(proy());
    await userEvent.click(screen.getByTitle("Escena 3: texto 2"));
    expect((screen.getByPlaceholderText("Prompt visual (imagen)") as HTMLTextAreaElement).value).toBe("prompt 2");
    expect(screen.getByText("#3")).toBeInTheDocument();
    expect(screen.getByTitle("Escena 3: texto 2")).toHaveAttribute("aria-current", "true");
  });

  it("las miniaturas llevan el cache-bust", () => {
    montar(proy(), acciones(), { bust: 42 });
    expect(screen.getAllByAltText("escena 1")[0]).toHaveAttribute("src", "/api/proyectos/1/imagenes/0?v=42");
  });

  it("una escena sin imagen muestra un hueco y 'sin imagen'", () => {
    montar(proy({ escenas: [escena(0, { imagen: false })] }));
    expect(screen.getAllByText("sin imagen")).toHaveLength(2);   // aviso de la tira + hueco del detalle
    expect(screen.queryByAltText("escena 1")).toBeNull();
  });

  it.each([
    [{ en_cola: "imagen" }, "en cola"],
    [{ imagen: false }, "sin imagen"],
    [{ clip_viejo: true }, "clip viejo"],
  ])("el aviso de la tira para %j es '%s'", (extra, aviso) => {
    montar(proy({ escenas: [escena(0, extra)] }));
    expect(screen.getAllByText(aviso).length).toBeGreaterThan(0);
  });

  it("en cola tiene prioridad sobre los demás avisos; sin nada no hay aviso", () => {
    const { unmount } = montar(proy({ escenas: [escena(0, { en_cola: "clip", imagen: false })] }));
    expect(screen.queryByText("sin imagen", { selector: "span.absolute" })).toBeNull();
    expect(screen.getByText("en cola", { selector: "span.absolute" })).toBeInTheDocument();
    unmount();
    montar(proy({ escenas: [escena(0)] }));
    expect(screen.queryByText(/en cola|sin imagen|clip viejo/, { selector: "span.absolute" })).toBeNull();
  });

  it("marca las escenas con personajes (con contador si hay más de uno)", () => {
    montar(proy({ escenas: [escena(0, { personajes: ["ANA"] }), escena(1, { personajes: ["ANA", "LUIS"] })] }));
    expect(screen.getByTitle("Sale ANA")).toHaveTextContent("◍");
    expect(screen.getByTitle("Sale ANA, LUIS")).toHaveTextContent("2◍");
  });

  it("si regeneran las escenas y la elegida desaparece, vuelve a la primera", async () => {
    const a = acciones();
    const { rerender } = render(StepEscenas, { p: proy(), ...a });
    await userEvent.click(screen.getByTitle("Escena 3: texto 2"));
    await rerender({ p: proy({ escenas: [escena(0, { prompt: "nuevo 0" })] }), ...a });
    expect((await screen.findByPlaceholderText("Prompt visual (imagen)") as HTMLTextAreaElement).value).toBe("nuevo 0");
  });

  it("detalle: etiquetas de cola, clip desactualizado y tiempos de render", () => {
    montar(proy({ escenas: [escena(0, { en_cola: "imagen", clip_viejo: true, imagen_s: 12.5, clip: true, clip_modo: "i2v", clip_s: 30 })] }));
    expect(screen.getByText("⏳ imagen en cola")).toBeInTheDocument();
    expect(screen.getByText("clip desactualizado")).toBeInTheDocument();
    // Regresión: Svelte se comía el espacio antes del "·" ("clip i2v· 30s").
    expect(screen.getByText(/img 12.5s/).textContent).toBe("img 12.5s · clip i2v · 30s");
  });

  it("un clip sin modo registrado lo dice", () => {
    montar(proy({ escenas: [escena(0, { clip: true, clip_modo: null })] }));
    expect(screen.getByText(/modo sin registrar/)).toBeInTheDocument();
  });
});

describe("edición de prompts", () => {
  it("guardar manda todas las escenas, recortadas, y el prompt de movimiento vacío como null", async () => {
    const { a } = montar(proy({ escenas: [escena(0, { prompt_movimiento: null }), escena(1)] }));
    const visual = screen.getByPlaceholderText("Prompt visual (imagen)");
    await userEvent.clear(visual);
    await userEvent.type(visual, "  nuevo visual  ");
    await userEvent.click(screen.getByRole("button", { name: "Guardar prompts" }));
    expect(a.onguardar).toHaveBeenCalledWith([
      { orden: 0, prompt: "nuevo visual", prompt_movimiento: null },
      { orden: 1, prompt: "prompt 1", prompt_movimiento: "mov 1" },
    ]);
  });

  it("lo editado en una escena se conserva al cambiar a otra", async () => {
    const { a } = montar(proy());
    await userEvent.type(screen.getByPlaceholderText("Prompt de movimiento (solo modo i2v)"), " extra");
    await userEvent.click(screen.getByTitle("Escena 2: texto 1"));
    await userEvent.click(screen.getByTitle("Escena 1: texto 0"));
    await userEvent.click(screen.getByRole("button", { name: "Guardar prompts" }));
    expect(a.onguardar.mock.calls[0][0][0].prompt_movimiento).toBe("mov 0 extra");
  });

  it("'Generar imágenes' envía los prompts editados; con imágenes completas dice 'Regenerar'", async () => {
    const a = acciones();
    const { rerender } = render(StepEscenas, { p: proy(), ...a });
    await userEvent.click(screen.getByRole("button", { name: "Generar imágenes" }));
    expect(a.ongenerarimagenes).toHaveBeenCalledWith([
      { orden: 0, prompt: "prompt 0", prompt_movimiento: "mov 0" },
      { orden: 1, prompt: "prompt 1", prompt_movimiento: "mov 1" },
      { orden: 2, prompt: "prompt 2", prompt_movimiento: "mov 2" },
    ]);
    await rerender({ p: proy({ imagenes_completas: true }), ...a });
    expect(screen.getByRole("button", { name: "Regenerar imágenes" })).toBeInTheDocument();
  });

  it("'busy' bloquea regenerar prompts e imágenes pero no guardar", () => {
    montar(proy(), acciones(), { busy: true });
    expect(screen.getByRole("button", { name: "Regenerar prompts" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Generar imágenes" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Guardar prompts" })).toBeEnabled();
  });

  it("'Regenerar prompts' lo pide", async () => {
    const { a } = montar(proy());
    await userEvent.click(screen.getByRole("button", { name: "Regenerar prompts" }));
    expect(a.ongenerar).toHaveBeenCalled();
  });
});

describe("acciones por escena", () => {
  it("'Otra imagen' usa seed nuevo y 'Mismo seed' lo conserva", async () => {
    const { a } = montar(proy());
    await userEvent.click(screen.getByRole("button", { name: "Otra imagen" }));
    await userEvent.click(screen.getByRole("button", { name: "Mismo seed" }));
    expect(a.onregenimagen.mock.calls).toEqual([[0, true], [0, false]]);
  });

  it("una escena en cola no admite nuevas regeneraciones", () => {
    montar(proy({ escenas: [escena(0, { en_cola: "imagen" })] }));
    for (const n of ["Otra imagen", "Mismo seed", "Clip"]) {
      expect(screen.getByRole("button", { name: n })).toBeDisabled();
    }
  });

  it("'Clip' exige imagen y regenera con el modo elegido", async () => {
    const { a, unmount } = montar(proy({ escenas: [escena(0, { imagen: false })] }));
    expect(screen.getByRole("button", { name: "Clip" })).toBeDisabled();
    unmount();
    const m = montar(proy({ escenas: [escena(0, { modo: "i2v" })] }));
    expect((screen.getByRole("combobox", { name: "" }) as HTMLSelectElement).value).toBe("i2v");
    await userEvent.click(screen.getByRole("button", { name: "Clip" }));
    expect(m.a.onregenclip).toHaveBeenCalledWith(0, "i2v");
    expect(a.onregenclip).not.toHaveBeenCalled();
  });

  it("cambiar el modo de la escena lo fija al momento", async () => {
    const { a } = montar(proy());
    const modoEscena = screen.getAllByRole("combobox").find((s) => (s as HTMLSelectElement).value === "kenburns")!;
    await userEvent.selectOptions(modoEscena, "estatico");
    expect(a.onfijarmodos).toHaveBeenCalledWith([{ orden: 0, modo: "estatico" }]);
    await userEvent.click(screen.getByRole("button", { name: "Clip" }));
    expect(a.onregenclip).toHaveBeenCalledWith(0, "estatico");
  });

  it("por defecto el modo de una escena es Ken Burns", () => {
    montar(proy());
    expect(screen.getAllByRole("combobox").some((s) => (s as HTMLSelectElement).value === "kenburns")).toBe(true);
  });

  it("'Modo de todas' fija el modo en todas las escenas de una vez y se queda en '— elegir —'", async () => {
    const { a } = montar(proy());
    const todas = screen.getByLabelText("Modo de todas") as HTMLSelectElement;
    await userEvent.selectOptions(todas, "i2v");
    expect(a.onfijarmodos).toHaveBeenCalledWith([
      { orden: 0, modo: "i2v" }, { orden: 1, modo: "i2v" }, { orden: 2, modo: "i2v" }]);
    expect(todas.value).toBe("");
  });

  it("'Modo de todas' sin elegir nada no hace nada", async () => {
    const { a } = montar(proy());
    await userEvent.selectOptions(screen.getByLabelText("Modo de todas"), "");
    expect(a.onfijarmodos).not.toHaveBeenCalled();
  });

  it("'Ver clip' solo aparece si hay clip y lo abre en el visor", async () => {
    const { a, unmount } = montar(proy());
    expect(screen.queryByRole("button", { name: "Ver clip" })).toBeNull();
    unmount();
    const m = montar(proy({ escenas: [escena(1, { clip: true, clip_modo: "kenburns" })] }), acciones(), { bust: 5 });
    await userEvent.click(screen.getByRole("button", { name: "Ver clip" }));
    expect(m.a.onver).toHaveBeenCalledWith(expect.stringContaining('/api/proyectos/1/clips/1?v=5'), "Escena 2 · clip Ken Burns");
    expect(a.onver).not.toHaveBeenCalled();
  });

  it("pulsar la imagen del detalle la abre en grande", async () => {
    const { a } = montar(proy());
    await userEvent.click(screen.getAllByAltText("escena 1")[1].closest("button")!);
    expect(a.onver).toHaveBeenCalledWith(expect.stringContaining('src="/api/proyectos/1/imagenes/0?v=0"'), "Escena 1 · imagen");
  });
});

describe("reparto", () => {
  it("sin reparto y sin escenas ofrece 'Generar reparto'", async () => {
    const { a } = montar(proy({ escenas: [] }));
    await userEvent.click(screen.getByRole("button", { name: "Generar reparto" }));
    expect(a.ongenerarcasting).toHaveBeenCalled();
  });

  it("sin reparto pero con escenas lo dice y cambia el botón", () => {
    montar(proy());
    expect(screen.getByRole("button", { name: "Buscar reparto en el guion" })).toBeInTheDocument();
    expect(screen.getByText(/no tiene reparto fijado/)).toBeInTheDocument();
  });

  it("con reparto muestra cada personaje con su clave, nombre y ficha editable", () => {
    montar(proy({ personajes: [personaje("ANA"), personaje("LUIS")] }));
    expect(screen.getByText("{ANA}")).toBeInTheDocument();
    expect(screen.getByText("Nombre LUIS")).toBeInTheDocument();
    expect(screen.getByDisplayValue("ficha de ANA")).toBeInTheDocument();
    expect(screen.getByText(/Los prompts ya escritos no cambian solos/)).toBeInTheDocument();
  });

  it("guardar el reparto manda las fichas editadas y recortadas", async () => {
    const { a } = montar(proy({ personajes: [personaje("ANA")] }));
    const ficha = screen.getByDisplayValue("ficha de ANA");
    await userEvent.clear(ficha);
    await userEvent.type(ficha, "  una mujer alta  ");
    await userEvent.click(screen.getByRole("button", { name: "Guardar reparto" }));
    expect(a.onguardarcasting).toHaveBeenCalledWith([
      { clave: "ANA", nombre: "Nombre ANA", ficha: "una mujer alta" },
    ]);
  });

  it("un objeto del reparto se marca en su tarjeta y no se elige a mano", () => {
    // Lo decide el casting: aquí solo se enseña, para que se entienda por qué
    // su referencia se genera sin pedirle cara.
    montar(proy({ personajes: [personaje("BARCO", { tipo: "objeto" })] }));
    expect(screen.getByText("objeto")).toBeInTheDocument();
    expect(screen.queryByLabelText("Qué es BARCO")).toBeNull();
  });

  it("una persona no lleva etiqueta de objeto", () => {
    montar(proy({ personajes: [personaje("ANA", { tipo: "persona" })] }));
    expect(screen.queryByText("objeto")).toBeNull();
  });

  it("los botones del retrato hablan de cara solo cuando hay cara", () => {
    montar(proy({ personajes: [personaje("MAPA", { tipo: "objeto", retrato: true })] }));
    expect(screen.getByRole("button", { name: "Otro" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Igual" })).toBeInTheDocument();
  });

  it("regenerar el reparto lo pide (y respeta 'busy')", async () => {
    const a = acciones();
    const { rerender } = render(StepEscenas, { p: proy({ personajes: [personaje("ANA")] }), ...a });
    await userEvent.click(screen.getByRole("button", { name: "Regenerar reparto" }));
    expect(a.ongenerarcasting).toHaveBeenCalled();
    await rerender({ p: proy({ personajes: [personaje("ANA")] }), busy: true, ...a });
    expect(screen.getByRole("button", { name: "Regenerar reparto" })).toBeDisabled();
  });

  it("sacar a un personaje del reparto lo pide por clave", async () => {
    const { a } = montar(proy({ personajes: [personaje("ANA")] }));
    await userEvent.click(screen.getByRole("button", { name: "Sacar a ANA del reparto" }));
    expect(a.onborrarpersonaje).toHaveBeenCalledWith("ANA");
  });

  describe("retratos", () => {
    it("sin retrato: hueco y botón 'Retrato' (cara nueva)", async () => {
      const { a } = montar(proy({ personajes: [personaje("ANA")] }));
      expect(screen.getByText("sin retrato")).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Misma cara" })).toBeNull();
      await userEvent.click(screen.getByRole("button", { name: "Retrato" }));
      expect(a.ongenerarretrato).toHaveBeenCalledWith("ANA", false);
    });

    it("con retrato: 'Otra cara' (seed nuevo), 'Misma cara' y vista ampliada", async () => {
      const { a } = montar(proy({ personajes: [personaje("ANA", { retrato: true })] }), acciones(), { bust: 3 });
      await userEvent.click(screen.getByRole("button", { name: "Otra cara" }));
      await userEvent.click(screen.getByRole("button", { name: "Misma cara" }));
      expect(a.ongenerarretrato.mock.calls).toEqual([["ANA", true], ["ANA", false]]);

      await userEvent.click(screen.getByAltText("retrato de ANA").closest("button")!);
      expect(a.onver).toHaveBeenCalledWith(
        expect.stringContaining("/api/proyectos/1/personajes/ANA/retrato?v=3"), "Nombre ANA · retrato de referencia");
    });

    it("'busy' bloquea generar retratos", () => {
      montar(proy({ personajes: [personaje("ANA")] }), acciones(), { busy: true });
      expect(screen.getByRole("button", { name: "Retrato" })).toBeDisabled();
    });
  });

  describe("resumen de caras", () => {
    it("cuenta las escenas que saldrán de retratos y las que tienen personaje sin retrato", () => {
      montar(proy({
        personajes: [personaje("ANA", { retrato: true }), personaje("LUIS")],
        escenas: [escena(0, { personajes: ["ANA"] }), escena(1, { personajes: ["LUIS"] }), escena(2)],
      }));
      expect(screen.getByText(/1 de 3 saldrán de las caras del reparto/)).toBeInTheDocument();
      expect(screen.getByText(/1 con personaje pero sin retrato/)).toBeInTheDocument();
    });

    it("sin personajes en las escenas no muestra el resumen", () => {
      montar(proy());
      expect(screen.queryByText(/saldrán de las caras/)).toBeNull();
      expect(screen.queryByText(/sin retrato/)).toBeNull();
    });

    it("una escena con dos personajes, uno retratado, cuenta como retratada", () => {
      montar(proy({
        personajes: [personaje("ANA", { retrato: true }), personaje("LUIS")],
        escenas: [escena(0, { personajes: ["ANA", "LUIS"] })],
      }));
      expect(screen.getByText(/1 de 1 saldrán/)).toBeInTheDocument();
      expect(screen.queryByText(/pero sin retrato/)).toBeNull();
    });
  });

  describe("añadir a mano", () => {
    it("el formulario se abre y se cierra", async () => {
      montar(proy());
      expect(screen.queryByPlaceholderText("ESCRITOR")).toBeNull();
      await userEvent.click(screen.getByRole("button", { name: "Añadir personaje" }));
      expect(screen.getByPlaceholderText("ESCRITOR")).toBeInTheDocument();
      await userEvent.click(screen.getByRole("button", { name: "Cancelar" }));
      expect(screen.queryByPlaceholderText("ESCRITOR")).toBeNull();
    });

    it("'Añadir al reparto' exige clave y ficha (solo espacios no valen)", async () => {
      montar(proy());
      await userEvent.click(screen.getByRole("button", { name: "Añadir personaje" }));
      const anadir = screen.getByRole("button", { name: "Añadir al reparto" });
      expect(anadir).toBeDisabled();
      await userEvent.type(screen.getByPlaceholderText("ESCRITOR"), "   ");
      await userEvent.type(screen.getByPlaceholderText(/Descripción física en inglés, como/), "   ");
      expect(anadir).toBeDisabled();
    });

    it("envía clave, nombre y ficha recortados, y cierra y limpia el formulario", async () => {
      const { a } = montar(proy());
      await userEvent.click(screen.getByRole("button", { name: "Añadir personaje" }));
      await userEvent.type(screen.getByPlaceholderText("ESCRITOR"), " ESCRITOR ");
      await userEvent.type(screen.getByPlaceholderText("cómo lo llama el guion"), " el del sótano ");
      await userEvent.type(screen.getByPlaceholderText(/Descripción física en inglés, como/), " a gaunt man ");
      await userEvent.click(screen.getByRole("button", { name: "Añadir al reparto" }));
      expect(a.onanadirpersonaje).toHaveBeenCalledWith("ESCRITOR", "el del sótano", "a gaunt man");
      expect(screen.queryByPlaceholderText("ESCRITOR")).toBeNull();
      await userEvent.click(screen.getByRole("button", { name: "Añadir personaje" }));
      expect((screen.getByPlaceholderText("ESCRITOR") as HTMLInputElement).value).toBe("");
    });

    it("también se puede añadir con un reparto ya hecho", async () => {
      montar(proy({ personajes: [personaje("ANA")] }));
      await userEvent.click(screen.getByRole("button", { name: "Añadir personaje" }));
      expect(screen.getByPlaceholderText("ESCRITOR")).toBeInTheDocument();
    });
  });
});
