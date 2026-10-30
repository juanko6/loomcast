import { render, screen } from "@testing-library/svelte";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import Button from "../primitives/Button.svelte";
import Chip from "../primitives/Chip.svelte";
import CopyField from "../primitives/CopyField.svelte";
import Field from "../primitives/Field.svelte";
import Icon from "../primitives/Icon.svelte";
import IconButton from "../primitives/IconButton.svelte";
import Segmented from "../primitives/Segmented.svelte";
import StatusDot from "../primitives/StatusDot.svelte";
import Thumbnail from "../primitives/Thumbnail.svelte";
import Viewer from "../primitives/Viewer.svelte";
import { icons } from "@/lib/icons";
import { texto } from "./helpers";

describe("Button", () => {
  it("muestra su contenido y dispara onclick", async () => {
    const onclick = vi.fn();
    render(Button, { children: texto("Guardar"), onclick });
    await userEvent.click(screen.getByRole("button", { name: "Guardar" }));
    expect(onclick).toHaveBeenCalledTimes(1);
  });

  it("deshabilitado no dispara onclick", async () => {
    const onclick = vi.fn();
    render(Button, { children: texto("Guardar"), onclick, disabled: true });
    const b = screen.getByRole("button");
    expect(b).toBeDisabled();
    await userEvent.click(b);
    expect(onclick).not.toHaveBeenCalled();
  });

  it("por defecto es type=button (no envía formularios por accidente)", () => {
    render(Button, { children: texto("x") });
    expect(screen.getByRole("button")).toHaveAttribute("type", "button");
  });

  it.each([
    ["primary", "bg-accent"], ["secondary", "bg-surface-3"],
    ["ghost", "bg-transparent"], ["danger", "text-danger"],
  ] as const)("variante %s", (variant, clase) => {
    render(Button, { children: texto("x"), variant });
    expect(screen.getByRole("button").className).toContain(clase);
  });

  it("tamaño sm y clases extra", () => {
    render(Button, { children: texto("x"), size: "sm", class: "mi-clase", title: "ayuda" });
    const b = screen.getByRole("button");
    expect(b.className).toContain("text-xs");
    expect(b.className).toContain("mi-clase");
    expect(b).toHaveAttribute("title", "ayuda");
  });
});

describe("Chip", () => {
  it("renderiza el texto con tono neutro por defecto", () => {
    render(Chip, { children: texto("final") });
    expect(screen.getByText("final").parentElement!.className).toContain("bg-surface-3");
  });

  it.each([["accent", "text-accent"], ["ok", "text-ok"], ["warn", "text-warn"], ["danger", "text-danger"]] as const)(
    "tono %s", (tone, clase) => {
      render(Chip, { children: texto("x"), tone });
      expect(screen.getByText("x").parentElement!.className).toContain(clase);
    });
});

describe("StatusDot", () => {
  it("lleva texto además de color (accesibilidad)", () => {
    render(StatusDot, { estado: "on", label: "LLM", title: "cargado" });
    const el = screen.getByText("LLM");
    expect(el).toBeInTheDocument();
    expect(el).toHaveAttribute("title", "cargado");
    expect(el.className).toContain("text-ok");
  });

  it.each([["on", "text-ok"], ["off", "text-danger"], ["espera", "text-warn"]] as const)(
    "estado %s", (estado, clase) => {
      render(StatusDot, { estado, label: "X" });
      expect(screen.getByText("X").className).toContain(clase);
    });

  it("sin estado se considera apagado", () => {
    render(StatusDot, { label: "Comfy" });
    expect(screen.getByText("Comfy").className).toContain("text-danger");
  });
});

describe("Field", () => {
  it("asocia la etiqueta con su control (clic en la etiqueta da foco)", async () => {
    render(Field, { label: "Gancho", children: createInput() });
    await userEvent.click(screen.getByText("Gancho"));
    expect(screen.getByLabelText("Gancho")).toHaveFocus();
  });

  it("muestra la ayuda solo si se pasa", () => {
    const { unmount } = render(Field, { label: "A", hint: "Ayuda", children: createInput() });
    expect(screen.getByText("Ayuda")).toBeInTheDocument();
    unmount();
    render(Field, { label: "A", children: createInput() });
    expect(screen.queryByText("Ayuda")).toBeNull();
  });

  it("sin etiqueta no pinta el span de etiqueta", () => {
    const { container } = render(Field, { children: createInput() });
    expect(container.querySelectorAll("label > span")).toHaveLength(0);
  });
});

import { createRawSnippet } from "svelte";
function createInput() {
  return createRawSnippet(() => ({ render: () => `<input />` }));
}

describe("Segmented", () => {
  const opciones = [
    { value: "a", label: "Alfa" },
    { value: "b", label: "Beta", icon: "★" },
  ];

  it("marca como seleccionada solo la opción activa", () => {
    render(Segmented, { options: opciones, value: "b", onchange: vi.fn() });
    expect(screen.getByRole("tab", { name: "Alfa" })).toHaveAttribute("aria-selected", "false");
    expect(screen.getByRole("tab", { name: /Beta/ })).toHaveAttribute("aria-selected", "true");
  });

  it("emite el valor de la opción pulsada", async () => {
    const onchange = vi.fn();
    render(Segmented, { options: opciones, value: "a", onchange });
    await userEvent.click(screen.getByRole("tab", { name: /Beta/ }));
    expect(onchange).toHaveBeenCalledWith("b");
  });

  it("pulsar la ya activa vuelve a emitir (el padre decide)", async () => {
    const onchange = vi.fn();
    render(Segmented, { options: opciones, value: "a", onchange });
    await userEvent.click(screen.getByRole("tab", { name: "Alfa" }));
    expect(onchange).toHaveBeenCalledWith("a");
  });

  it("dibuja el icono opcional", () => {
    render(Segmented, { options: opciones, value: "a", onchange: vi.fn() });
    expect(screen.getByText("★")).toHaveAttribute("aria-hidden", "true");
  });

  it("sin opciones no revienta", () => {
    render(Segmented, { options: [], value: "", onchange: vi.fn() });
    expect(screen.queryAllByRole("tab")).toHaveLength(0);
  });
});

describe("Icon", () => {
  it("dibuja el path del registro, de trazo", () => {
    const { container } = render(Icon, { name: "trash", size: 24 });
    const svg = container.querySelector("svg")!;
    expect(svg.querySelector("path")).toHaveAttribute("d", icons.trash);
    expect(svg).toHaveAttribute("width", "24");
    expect(svg).toHaveAttribute("fill", "none");
    expect(svg).toHaveAttribute("aria-hidden", "true");
  });

  it("los iconos rellenos (play) usan fill y no stroke", () => {
    const svg = render(Icon, { name: "play" }).container.querySelector("svg")!;
    expect(svg).toHaveAttribute("fill", "currentColor");
    expect(svg).toHaveAttribute("stroke", "none");
  });
});

describe("IconButton", () => {
  it("es accesible por su etiqueta y dispara onclick", async () => {
    const onclick = vi.fn();
    render(IconButton, { name: "x", label: "Cerrar", onclick });
    await userEvent.click(screen.getByRole("button", { name: "Cerrar" }));
    expect(onclick).toHaveBeenCalled();
  });

  it("'soon' lo marca como próximamente en el tooltip", () => {
    render(IconButton, { name: "heart", label: "Me gusta", soon: true });
    expect(screen.getByRole("button")).toHaveAttribute("title", "Me gusta · Próximamente");
  });

  it("sin 'soon' el tooltip es la etiqueta", () => {
    render(IconButton, { name: "heart", label: "Me gusta" });
    expect(screen.getByRole("button")).toHaveAttribute("title", "Me gusta");
  });

  it("'active' lo tiñe con el acento y 'disabled' lo bloquea", async () => {
    const onclick = vi.fn();
    render(IconButton, { name: "heart", label: "L", active: true, disabled: true, onclick });
    const b = screen.getByRole("button");
    expect(b.className).toContain("text-accent");
    await userEvent.click(b);
    expect(onclick).not.toHaveBeenCalled();
  });
});

describe("Thumbnail", () => {
  // Regresión: Thumbnail le pasaba `icon` a Icon, que espera `name`; el icono de
  // respaldo salía en blanco en las listas de música e imágenes.
  it("sin imagen muestra el icono de respaldo", () => {
    const { container } = render(Thumbnail, { icon: "image", size: 40 });
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("svg path")).toHaveAttribute("d", icons.image);
  });

  it("con imagen la muestra con su alt", () => {
    render(Thumbnail, { src: "/x.png", alt: "portada" });
    expect(screen.getByAltText("portada")).toHaveAttribute("src", "/x.png");
  });

  it("con onplay es un botón que alterna su etiqueta según suene", async () => {
    const onplay = vi.fn();
    const { rerender } = render(Thumbnail, { onplay, playing: false });
    await userEvent.click(screen.getByRole("button", { name: "Reproducir" }));
    expect(onplay).toHaveBeenCalled();
    await rerender({ onplay, playing: true });
    expect(screen.getByRole("button", { name: "Pausar" })).toBeInTheDocument();
  });

  it("sin onplay no es un botón", () => {
    render(Thumbnail, { src: "/x.png" });
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("el tamaño se aplica al contenedor", () => {
    const { container } = render(Thumbnail, { size: 64 });
    expect((container.firstElementChild as HTMLElement).style.width).toBe("64px");
  });
});

describe("Viewer", () => {
  it("sin contenido no pinta nada", () => {
    const { container } = render(Viewer, { html: null, onclose: vi.fn() });
    expect(container.querySelector(".viewer-media")).toBeNull();
  });

  it("muestra el HTML recibido y el pie", () => {
    render(Viewer, { html: '<img src="/a.png" alt="foto">', pie: "Mi foto", onclose: vi.fn() });
    expect(screen.getByAltText("foto")).toBeInTheDocument();
    expect(screen.getByText("Mi foto")).toBeInTheDocument();
  });

  it("se cierra con el botón, con Escape y al pulsar el fondo, pero no al pulsar el contenido", async () => {
    const onclose = vi.fn();
    const { container } = render(Viewer, { html: '<img src="/a.png" alt="foto">', onclose });

    await userEvent.click(screen.getByAltText("foto"));
    expect(onclose).not.toHaveBeenCalled();

    // (el clic del botón sube hasta el fondo, que también cierra: onclose llega a sonar dos veces)
    await userEvent.click(screen.getByRole("button", { name: /Cerrar/ }));
    expect(onclose).toHaveBeenCalled();
    onclose.mockClear();

    await userEvent.click(container.querySelector(".fixed")!);
    expect(onclose).toHaveBeenCalledTimes(1);

    await userEvent.keyboard("{Escape}");
    expect(onclose).toHaveBeenCalledTimes(2);

    await userEvent.keyboard("a");
    expect(onclose).toHaveBeenCalledTimes(2);
  });
});

describe("CopyField", () => {
  // jsdom no trae portapapeles: se pone uno y se mira qué se le pidió escribir.
  function conPortapapeles(escribir = vi.fn().mockResolvedValue(undefined)) {
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText: escribir },
      configurable: true,
    });
    return escribir;
  }

  it("muestra el texto en un campo de solo lectura", () => {
    render(CopyField, { label: "Título", text: "Un título", hint: "9 caracteres" });
    const campo = screen.getByLabelText("Título") as HTMLTextAreaElement;
    expect(campo.value).toBe("Un título");
    expect(campo).toHaveAttribute("readonly");
    expect(screen.getByText("9 caracteres")).toBeInTheDocument();
  });

  it("copia el texto y lo dice", async () => {
    const escribir = conPortapapeles();
    render(CopyField, { label: "Etiquetas", text: "a, b" });
    await userEvent.click(screen.getByRole("button", { name: "Copiar etiquetas" }));
    expect(escribir).toHaveBeenCalledWith("a, b");
    expect(await screen.findByText("Copiado")).toBeInTheDocument();
  });

  it("si el portapapeles pide permiso y no lo hay, copia por el camino viejo", async () => {
    conPortapapeles(vi.fn().mockRejectedValue(new Error("sin permiso")));
    const viejo = vi.fn().mockReturnValue(true);
    Object.defineProperty(document, "execCommand", { value: viejo, configurable: true });
    render(CopyField, { label: "Título", text: "Un título" });
    await userEvent.click(screen.getByRole("button", { name: "Copiar título" }));
    expect(viejo).toHaveBeenCalledWith("copy");
    expect(await screen.findByText("Copiado")).toBeInTheDocument();
  });

  it("si el portapapeles falla, deja el texto seleccionado para copiarlo a mano", async () => {
    conPortapapeles(vi.fn().mockRejectedValue(new Error("sin permiso")));
    Object.defineProperty(document, "execCommand", {
      value: () => { throw new Error("tampoco"); },
      configurable: true,
    });
    render(CopyField, { label: "Título", text: "Un título" });
    const campo = screen.getByLabelText("Título") as HTMLTextAreaElement;
    await userEvent.click(screen.getByRole("button", { name: "Copiar título" }));
    expect(campo.selectionStart).toBe(0);
    expect(campo.selectionEnd).toBe("Un título".length);
    expect(screen.queryByText("Copiado")).toBeNull();
  });
});
