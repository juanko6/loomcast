import { render, screen, within } from "@testing-library/svelte";
import userEvent from "@testing-library/user-event";
import { get } from "svelte/store";
import { beforeEach, describe, expect, it, vi } from "vitest";

// El backend responde a /salud con su forma real: un `{}` rompería el semáforo.
const SALUD = { comfy: true, llm_estado: { estado: "activo", nombre: "Qwen" } };
vi.mock("@/lib/api", async (o) => ({
  ...(await o<typeof import("@/lib/api")>()),
  api: vi.fn(async (ruta: string) => (ruta === "/salud" ? SALUD : {})),
}));

import { api } from "@/lib/api";
import { modeloActivo, modelos, modo, salud } from "@/lib/stores";
import Rail from "../shell/Rail.svelte";
import SystemStatus from "../shell/SystemStatus.svelte";
import Stepper from "../videos/Stepper.svelte";

beforeEach(() => {
  modo.set("videos");
  salud.set(null);
  modelos.set([]);
  modeloActivo.set("");
});

describe("Rail", () => {
  it("lista los cuatro modos del estudio", () => {
    render(Rail);
    const nav = screen.getByRole("navigation", { name: "Navegación del estudio" });
    for (const m of ["Vídeos", "Imágenes", "Música", "Biblioteca"]) {
      expect(within(nav).getByText(m)).toBeInTheDocument();
    }
  });

  it("marca el modo actual con aria-current y cambia de modo al pulsar", async () => {
    render(Rail);
    const boton = (t: string) => screen.getByText(t).closest("button")!;
    expect(boton("Vídeos")).toHaveAttribute("aria-current", "page");
    expect(boton("Música")).not.toHaveAttribute("aria-current");

    await userEvent.click(boton("Música"));

    expect(get(modo)).toBe("musica");
    expect(boton("Música")).toHaveAttribute("aria-current", "page");
    expect(boton("Vídeos")).not.toHaveAttribute("aria-current");
  });

  it("incluye el estado del sistema al pie", () => {
    render(Rail);
    expect(screen.getByText("LLM")).toBeInTheDocument();
    expect(screen.getByText("Comfy")).toBeInTheDocument();
  });
});

describe("SystemStatus", () => {
  const estadoLlm = (estado: string) => ({ comfy: true, llm_estado: { estado, nombre: "Qwen" } }) as never;

  it("sin datos de salud muestra ambos semáforos apagados", () => {
    render(SystemStatus);
    expect(screen.getByText("LLM").className).toContain("text-danger");
    expect(screen.getByText("Comfy").className).toContain("text-danger");
    expect(screen.getByText("LLM")).toHaveAttribute("title", "llama-server");
  });

  it.each([
    ["activo", "text-ok", "levantado por ti"],
    ["cargado", "text-ok", "cargado en memoria"],
    ["en_espera", "text-warn", "se carga solo"],
    ["caido", "text-danger", "no responde"],
  ])("LLM %s", (estado, clase, detalle) => {
    salud.set(estadoLlm(estado));
    render(SystemStatus);
    const llm = screen.getByText("LLM");
    expect(llm.className).toContain(clase);
    expect(llm.getAttribute("title")).toContain("Qwen");
    expect(llm.getAttribute("title")).toContain(detalle);
  });

  it("Comfy refleja si responde", () => {
    salud.set({ comfy: false, llm_estado: { estado: "activo", nombre: "x" } } as never);
    render(SystemStatus);
    expect(screen.getByText("Comfy").className).toContain("text-danger");
  });

  it("el selector de modelo solo aparece con más de un modelo", () => {
    modelos.set([{ id: "a", nombre: "A" }]);
    const { unmount } = render(SystemStatus);
    expect(screen.queryByTitle("Modelo de texto")).toBeNull();
    unmount();

    modelos.set([{ id: "a", nombre: "A" }, { id: "b", nombre: "B" }]);
    modeloActivo.set("b");
    render(SystemStatus);
    const sel = screen.getByTitle("Modelo de texto") as HTMLSelectElement;
    expect(sel.value).toBe("b");
    expect([...sel.options].map((o) => o.text)).toEqual(["A", "B"]);
  });

  it("elegir un modelo avisa al backend", async () => {
    modelos.set([{ id: "a", nombre: "A" }, { id: "b", nombre: "B" }]);
    modeloActivo.set("a");
    render(SystemStatus);
    await userEvent.selectOptions(screen.getByTitle("Modelo de texto"), "b");
    expect(api).toHaveBeenCalledWith("/llm/modelo", { method: "POST", body: { id: "b" } });
    expect(get(modeloActivo)).toBe("b");
  });
});

describe("Stepper", () => {
  const pasos = [
    { id: "guion", label: "Guion", hecho: true, bloqueado: false },
    { id: "voz", label: "Voz", hecho: false, bloqueado: false },
    { id: "video", label: "Vídeo final", hecho: false, bloqueado: true },
  ];

  it("un paso hecho muestra ✓ y los demás su número", () => {
    render(Stepper, { pasos, activo: "voz", onselect: vi.fn() });
    expect(screen.getByText("Guion").previousElementSibling).toHaveTextContent("✓");
    expect(screen.getByText("Voz").previousElementSibling).toHaveTextContent("2");
    expect(screen.getByText("Vídeo final").previousElementSibling).toHaveTextContent("3");
  });

  it("marca el paso activo con aria-current=step", () => {
    render(Stepper, { pasos, activo: "voz", onselect: vi.fn() });
    expect(screen.getByRole("button", { name: /Voz/ })).toHaveAttribute("aria-current", "step");
    expect(screen.getByRole("button", { name: /Guion/ })).not.toHaveAttribute("aria-current");
  });

  it("pulsar un paso disponible lo selecciona", async () => {
    const onselect = vi.fn();
    render(Stepper, { pasos, activo: "voz", onselect });
    await userEvent.click(screen.getByRole("button", { name: /Guion/ }));
    expect(onselect).toHaveBeenCalledWith("guion");
  });

  it("un paso bloqueado está deshabilitado y no se puede seleccionar", async () => {
    const onselect = vi.fn();
    render(Stepper, { pasos, activo: "voz", onselect });
    const b = screen.getByRole("button", { name: /Vídeo final/ });
    expect(b).toBeDisabled();
    expect(b).toHaveAttribute("title", "Completa los pasos anteriores");
    await userEvent.click(b);
    expect(onselect).not.toHaveBeenCalled();
  });

  it("sin pasos no pinta botones ni separadores", () => {
    const { container } = render(Stepper, { pasos: [], activo: "", onselect: vi.fn() });
    expect(screen.queryAllByRole("button")).toHaveLength(0);
    expect(container.querySelectorAll("[aria-hidden]")).toHaveLength(0);
  });

  it("pone un separador entre pasos, no antes del primero", () => {
    const { container } = render(Stepper, { pasos, activo: "voz", onselect: vi.fn() });
    expect(container.querySelectorAll("nav > span[aria-hidden]")).toHaveLength(2);
  });
});
