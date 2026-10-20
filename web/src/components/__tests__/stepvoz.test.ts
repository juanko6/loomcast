import { render, screen, within } from "@testing-library/svelte";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Personaje, ProyectoDetalle, Voz } from "@/lib/proyectos";
import StepVoz from "../videos/steps/StepVoz.svelte";

const proy = (extra: Partial<ProyectoDetalle> = {}): ProyectoDetalle => ({
  id: 1, slug: "demo", estado: "GUION", plantilla: "curiosidades", voz: null, voz_instruct: "Voz grave y pausada",
  idea: null, guion: null, guion_version: 1, metadatos: null, voz_disponible: false, voz_version: 3,
  subtitulos: null, escenas: [], personajes: [], imagenes_completas: false, video_disponible: false,
  versiones: [], jobs_activos: 0, job_activo: null, musica: null, musica_mezclar: false,
  serie: null, resumen_episodio: "", ...extra,
});
const voz = (slug: string, extra: Partial<Voz> = {}): Voz =>
  ({ slug, nombre: slug.toUpperCase(), instruct: `descripción de ${slug}`, estado: "lista", disponible: true, ...extra });

const props = () => ({
  onselectvoz: vi.fn(), ongenerar: vi.fn(), oncrearvoz: vi.fn(), onclonarvoz: vi.fn(), onborrarvoz: vi.fn(),
  onvozpersonaje: vi.fn(), oncrearvozpersonaje: vi.fn(),
});
const personaje = (extra: Partial<Personaje> = {}): Personaje =>
  ({ clave: "ANA", nombre: "Ana", ficha: "a tall woman", tipo: "persona", retrato: false, ...extra });

beforeEach(() => {
  vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: vi.fn(() => "blob:audio"), revokeObjectURL: vi.fn() }));
  vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
});

describe("elegir y generar", () => {
  it("solo ofrece las voces disponibles y selecciona la del proyecto", () => {
    render(StepVoz, { p: proy({ voz: "ana" }), voces: [voz("ana"), voz("luis", { disponible: false })], ...props() });
    const sel = screen.getByLabelText("Voz del banco") as HTMLSelectElement;
    expect([...sel.options].map((o) => o.value)).toEqual(["", "ana"]);
    expect(sel.value).toBe("ana");
  });

  it("elegir una voz avisa con su slug", async () => {
    const p = props();
    render(StepVoz, { p: proy(), voces: [voz("ana"), voz("luis")], ...p });
    await userEvent.selectOptions(screen.getByLabelText("Voz del banco"), "luis");
    expect(p.onselectvoz).toHaveBeenCalledWith("luis");
  });

  it("con voz elegida muestra su descripción y un reproductor de la referencia", () => {
    const { container } = render(StepVoz, { p: proy({ voz: "ana" }), voces: [voz("ana")], ...props() });
    expect(screen.getByText("descripción de ana")).toBeInTheDocument();
    expect(container.querySelector("audio")).toHaveAttribute("src", "/api/voces/ana/audio");
  });

  it("una voz del proyecto que ya no está disponible no muestra reproductor", () => {
    const { container } = render(StepVoz, { p: proy({ voz: "fantasma" }), voces: [voz("ana")], ...props() });
    expect(container.querySelector("audio")).toBeNull();
  });

  it("'Generar narración' exige una voz y genera en modo clon", async () => {
    const p = props();
    const { rerender } = render(StepVoz, { p: proy(), voces: [voz("ana")], ...p });
    expect(screen.getByRole("button", { name: "Generar narración" })).toBeDisabled();
    await rerender({ p: proy({ voz: "ana" }), voces: [voz("ana")], ...p });
    await userEvent.click(screen.getByRole("button", { name: "Generar narración" }));
    expect(p.ongenerar).toHaveBeenCalledWith("clon", "");
  });

  it("la narración expresiva no necesita voz y manda el estilo (editable)", async () => {
    const p = props();
    render(StepVoz, { p: proy(), voces: [], ...p });
    const estilo = screen.getByLabelText(/Estilo de la narración expresiva/) as HTMLTextAreaElement;
    expect(estilo.value).toBe("Voz grave y pausada");
    await userEvent.clear(estilo);
    await userEvent.type(estilo, "susurrando");
    await userEvent.click(screen.getByRole("button", { name: "Narración expresiva" }));
    expect(p.ongenerar).toHaveBeenCalledWith("design", "susurrando");
  });

  it("'busy' bloquea las dos formas de generar", () => {
    render(StepVoz, { p: proy({ voz: "ana" }), voces: [voz("ana")], busy: true, ...props() });
    expect(screen.getByRole("button", { name: "Generar narración" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Narración expresiva" })).toBeDisabled();
  });

  it("con narración hecha el botón dice 'Regenerar' y se ve el reproductor con su versión (cache-bust)", () => {
    const { container } = render(StepVoz, { p: proy({ voz: "ana", voz_disponible: true, voz_version: 7 }), voces: [voz("ana")], ...props() });
    expect(screen.getByRole("button", { name: "Regenerar narración" })).toBeInTheDocument();
    const reproductores = [...container.querySelectorAll("audio")].map((a) => a.getAttribute("src"));
    expect(reproductores).toContain("/api/proyectos/1/audio?v=7");
  });

  it("sin narración no hay reproductor de narración; sin subtítulos no hay SRT", () => {
    render(StepVoz, { p: proy(), voces: [], ...props() });
    expect(screen.queryByText("Narración generada")).toBeNull();
    expect(screen.queryByText("Ver subtítulos (.srt)")).toBeNull();
  });

  it("los subtítulos se pueden desplegar", () => {
    render(StepVoz, { p: proy({ subtitulos: "1\n00:00:00,000 --> 00:00:01,000\nhola" }), voces: [], ...props() });
    expect(screen.getByText("Ver subtítulos (.srt)")).toBeInTheDocument();
    expect(screen.getByText(/00:00:00,000 --> 00:00:01,000/)).toBeInTheDocument();
  });

  it("si cambia el instruct del proyecto (otro guion) el borrador se actualiza", async () => {
    const p = props();
    const { rerender } = render(StepVoz, { p: proy(), voces: [], ...p });
    await rerender({ p: proy({ voz_instruct: "Tono épico" }), voces: [], ...p });
    expect((screen.getByLabelText(/Estilo de la narración/) as HTMLTextAreaElement).value).toBe("Tono épico");
  });
});

describe("banco de voces", () => {
  const abrir = async () => {
    await userEvent.click(screen.getByText(/Banco de voces/));
  };

  it("cuenta todas las voces, también las no disponibles, y marca su estado", async () => {
    render(StepVoz, { p: proy(), voces: [voz("ana"), voz("luis", { estado: "generando", disponible: false })], ...props() });
    expect(screen.getByText("Banco de voces (2)")).toBeInTheDocument();
    await abrir();
    expect(screen.getByText("(generando)")).toBeInTheDocument();
    expect(screen.queryByText("(lista)")).toBeNull();
  });

  it("borrar una voz avisa con su slug y nombre", async () => {
    const p = props();
    render(StepVoz, { p: proy(), voces: [voz("ana")], ...p });
    await abrir();
    await userEvent.click(screen.getByRole("button", { name: "Borrar voz" }));
    expect(p.onborrarvoz).toHaveBeenCalledWith("ana", "ANA");
  });

  it("describir: 'Crear voz' exige nombre Y descripción, y los recorta", async () => {
    const p = props();
    render(StepVoz, { p: proy(), voces: [], ...p });
    await abrir();
    const crear = screen.getByRole("button", { name: "Crear voz (VoiceDesign)" });
    expect(crear).toBeDisabled();
    await userEvent.type(screen.getByPlaceholderText(/Nombre/), "  Narrador  ");
    expect(crear).toBeDisabled();
    await userEvent.type(screen.getByPlaceholderText(/Describe cómo suena/), " grave ");
    expect(crear).toBeEnabled();
    await userEvent.click(crear);
    expect(p.oncrearvoz).toHaveBeenCalledWith("Narrador", "grave");
  });

  it("solo espacios no cuentan como nombre ni descripción", async () => {
    render(StepVoz, { p: proy(), voces: [], ...props() });
    await abrir();
    await userEvent.type(screen.getByPlaceholderText(/Nombre/), "   ");
    await userEvent.type(screen.getByPlaceholderText(/Describe cómo suena/), "   ");
    expect(screen.getByRole("button", { name: "Crear voz (VoiceDesign)" })).toBeDisabled();
  });

  describe("clonar de un audio", () => {
    const abrirClon = async (p = props()) => {
      const r = render(StepVoz, { p: proy(), voces: [], ...p });
      await abrir();
      await userEvent.click(screen.getByRole("tab", { name: "Clonar de un audio" }));
      return { ...r, p };
    };
    const subir = (container: HTMLElement, nombre = "voz.wav") =>
      userEvent.upload(container.querySelector('input[type="file"]')!, new File(["x"], nombre, { type: "audio/wav" }));

    it("cambia el formulario y exige nombre y archivo", async () => {
      const { container } = await abrirClon();
      expect(screen.queryByPlaceholderText(/Describe cómo suena/)).toBeNull();
      const clonar = screen.getByRole("button", { name: "Clonar voz del fragmento" });
      expect(clonar).toBeDisabled();
      await userEvent.type(screen.getByPlaceholderText(/Nombre/), "Mi voz");
      expect(clonar).toBeDisabled();
      await subir(container);
      expect(clonar).toBeEnabled();
    });

    it("al subir el audio aparece el recorte con el máximo por defecto (15 s)", async () => {
      const { container } = await abrirClon();
      await subir(container);
      expect(await screen.findByText(/Fragmento a clonar: 0.0s → 15.0s \(15.0s\)/)).toBeInTheDocument();
      expect(screen.getByText(/Máximo 15s/)).toBeInTheDocument();
      expect(container.querySelector("audio[src='blob:audio']")).not.toBeNull();
    });

    it("al cargar los metadatos el fin se acota a la duración si el audio es corto", async () => {
      const { container } = await abrirClon();
      await subir(container);
      const audio = container.querySelector("audio[src='blob:audio']") as HTMLAudioElement;
      Object.defineProperty(audio, "duration", { value: 6, configurable: true });
      audio.dispatchEvent(new Event("loadedmetadata"));
      expect(await screen.findByText(/0.0s → 6.0s \(6.0s\)/)).toBeInTheDocument();
    });

    it("'Inicio aquí' y 'Fin aquí' toman la posición del reproductor y respetan el tope", async () => {
      const { container } = await abrirClon();
      await subir(container);
      const audio = container.querySelector("audio[src='blob:audio']") as HTMLAudioElement;
      Object.defineProperty(audio, "duration", { value: 60, configurable: true });
      Object.defineProperty(audio, "currentTime", { value: 10, writable: true, configurable: true });
      audio.dispatchEvent(new Event("loadedmetadata"));

      await userEvent.click(screen.getByRole("button", { name: "Inicio aquí" }));
      expect(await screen.findByText(/10.0s → 15.0s \(5.0s\)/)).toBeInTheDocument();

      audio.currentTime = 18;
      await userEvent.click(screen.getByRole("button", { name: "Fin aquí" }));
      expect(await screen.findByText(/10.0s → 18.0s \(8.0s\)/)).toBeInTheDocument();

      audio.currentTime = 50;           // más allá del tope de 15 s
      await userEvent.click(screen.getByRole("button", { name: "Fin aquí" }));
      expect(await screen.findByText(/10.0s → 25.0s/)).toBeInTheDocument();

      audio.currentTime = 10.1;         // un fin demasiado pegado al inicio se separa 0,5 s
      await userEvent.click(screen.getByRole("button", { name: "Fin aquí" }));
      expect(await screen.findByText(/10.0s → 10.5s/)).toBeInTheDocument();
    });

    it("si el inicio pasa del fin, el fin se recoloca 15 s después (sin salirse del audio)", async () => {
      const { container } = await abrirClon();
      await subir(container);
      const audio = container.querySelector("audio[src='blob:audio']") as HTMLAudioElement;
      Object.defineProperty(audio, "duration", { value: 40, configurable: true });
      Object.defineProperty(audio, "currentTime", { value: 20, writable: true, configurable: true });
      audio.dispatchEvent(new Event("loadedmetadata"));
      await userEvent.click(screen.getByRole("button", { name: "Inicio aquí" }));
      expect(await screen.findByText(/20.0s → 35.0s \(15.0s\)/)).toBeInTheDocument();
      audio.currentTime = 38;
      await userEvent.click(screen.getByRole("button", { name: "Inicio aquí" }));
      expect(await screen.findByText(/38.0s → 40.0s \(2.0s\)/)).toBeInTheDocument();
    });

    it("'Oír selección' salta al inicio y reproduce", async () => {
      const { container } = await abrirClon();
      await subir(container);
      const audio = container.querySelector("audio[src='blob:audio']") as HTMLAudioElement;
      Object.defineProperty(audio, "duration", { value: 60, configurable: true });
      Object.defineProperty(audio, "currentTime", { value: 12, writable: true, configurable: true });
      audio.dispatchEvent(new Event("loadedmetadata"));
      await userEvent.click(screen.getByRole("button", { name: "Inicio aquí" }));
      audio.currentTime = 0;
      await userEvent.click(screen.getByRole("button", { name: "Oír selección" }));
      expect(audio.currentTime).toBe(12);
      expect(HTMLMediaElement.prototype.play).toHaveBeenCalled();
    });

    it("la reproducción se detiene al llegar al fin del fragmento", async () => {
      const { container } = await abrirClon();
      await subir(container);
      const audio = container.querySelector("audio[src='blob:audio']") as HTMLAudioElement;
      Object.defineProperty(audio, "duration", { value: 60, configurable: true });
      Object.defineProperty(audio, "currentTime", { value: 15.5, writable: true, configurable: true });
      Object.defineProperty(audio, "paused", { value: false, configurable: true });
      audio.dispatchEvent(new Event("loadedmetadata"));
      audio.dispatchEvent(new Event("timeupdate"));
      expect(HTMLMediaElement.prototype.pause).toHaveBeenCalled();
    });

    it("clonar envía nombre recortado, archivo y fragmento", async () => {
      const { container, p } = await abrirClon();
      await userEvent.type(screen.getByPlaceholderText(/Nombre/), " Mi voz ");
      await subir(container, "origen.wav");
      await userEvent.click(screen.getByRole("button", { name: "Clonar voz del fragmento" }));
      const [nombre, archivo, inicio, fin] = p.onclonarvoz.mock.calls[0];
      expect(nombre).toBe("Mi voz");
      expect(archivo.name).toBe("origen.wav");
      expect([inicio, fin]).toEqual([0, 15]);
    });

    it("cambiar de archivo libera la URL anterior y reinicia el recorte", async () => {
      const { container } = await abrirClon();
      await subir(container);
      await subir(container, "otra.wav");
      expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:audio");
      expect(await screen.findByText(/0.0s → 15.0s/)).toBeInTheDocument();
    });
  });
});

describe("voces del reparto", () => {
  it("sin reparto y sin líneas atribuidas no estorba", () => {
    render(StepVoz, { p: proy(), voces: [voz("ana")], ...props() });
    expect(screen.queryByText("Voces del reparto")).toBeNull();
  });

  it("cada personaje elige su voz del banco, y sin elegir la dice el narrador", async () => {
    const p = props();
    render(StepVoz, {
      p: proy({ personajes: [personaje(), personaje({ clave: "LUIS", nombre: "Luis", voz: "luis-voz" })] }),
      voces: [voz("ana"), voz("luis-voz")],
      ...p,
    });

    const deAna = screen.getByLabelText("Voz de ANA") as HTMLSelectElement;
    expect(deAna.value).toBe("");
    expect([...deAna.options].map((o) => o.value)).toEqual(["", "ana", "luis-voz"]);
    expect((screen.getByLabelText("Voz de LUIS") as HTMLSelectElement).value).toBe("luis-voz");

    await userEvent.selectOptions(deAna, "ana");
    expect(p.onvozpersonaje).toHaveBeenCalledWith("ANA", "ana");
  });

  it("quitarle la voz lo devuelve a la del narrador", async () => {
    const p = props();
    render(StepVoz, {
      p: proy({ personajes: [personaje({ voz: "ana" })] }), voces: [voz("ana")], ...p,
    });
    await userEvent.selectOptions(screen.getByLabelText("Voz de ANA"), "");
    expect(p.onvozpersonaje).toHaveBeenCalledWith("ANA", "");
  });

  it("quien no tiene voz la puede crear desde su ficha; sin ficha no", () => {
    const p = props();
    const { rerender } = render(StepVoz, {
      p: proy({ personajes: [personaje()] }), voces: [], ...p,
    });
    expect(screen.getByRole("button", { name: "Crear desde su ficha" })).toBeEnabled();

    rerender({ p: proy({ personajes: [personaje({ ficha: "  " })] }), voces: [], ...p });
    expect(screen.getByRole("button", { name: "Crear desde su ficha" })).toBeDisabled();
  });

  it("crear su voz avisa con su clave", async () => {
    const p = props();
    render(StepVoz, { p: proy({ personajes: [personaje()] }), voces: [], ...p });
    await userEvent.click(screen.getByRole("button", { name: "Crear desde su ficha" }));
    expect(p.oncrearvozpersonaje).toHaveBeenCalledWith("ANA");
  });

  it("una voz recién encolada sigue siendo la suya aunque no esté lista", () => {
    render(StepVoz, {
      p: proy({ personajes: [personaje({ voz: "ana" })] }),
      voces: [voz("ana", { estado: "generando", disponible: false })],
      ...props(),
    });
    // Si el selector no la ofreciera, caería en "la del narrador" y parecería
    // que la asignación se perdió.
    const select = screen.getByLabelText("Voz de ANA") as HTMLSelectElement;
    expect(select.value).toBe("ana");
    // En su fila, no en la del banco de voces de abajo (que también lo dice).
    expect(within(select.closest("div")!).getByText("(generando)")).toBeInTheDocument();
    // Y ya no se ofrece crearla otra vez.
    expect(screen.queryByRole("button", { name: "Crear desde su ficha" })).toBeNull();
  });

  it("un guion con líneas y el reparto sin fijar avisa de dónde se fija", () => {
    render(StepVoz, {
      p: proy({ guion: { gancho: "H", cta: "F", lineas: [{ personaje: "ANA", texto: "yo" }] } }),
      voces: [],
      ...props(),
    });
    expect(screen.getByText("Voces del reparto")).toBeInTheDocument();
    expect(screen.getByText(/el reparto todavía no está fijado/)).toBeInTheDocument();
  });
});
