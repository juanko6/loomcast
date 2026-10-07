import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { tiraH } from "../tira";

function tira(ancho = 300, contenido = 1000) {
  const nodo = document.createElement("div");
  Object.defineProperty(nodo, "clientWidth", { value: ancho, configurable: true });
  Object.defineProperty(nodo, "scrollWidth", { value: contenido, configurable: true });
  nodo.setPointerCapture = vi.fn();
  nodo.releasePointerCapture = vi.fn();
  nodo.hasPointerCapture = vi.fn().mockReturnValue(true);
  document.body.append(nodo);
  const accion = tiraH(nodo);
  return { nodo, accion };
}

function puntero(tipo: string, x: number, init: PointerEventInit = {}) {
  return new PointerEvent(tipo, { clientX: x, button: 0, pointerId: 1, bubbles: true, cancelable: true, ...init });
}

let activas: { destroy(): void }[] = [];
beforeEach(() => {
  activas = [];
});
afterEach(() => {
  activas.forEach((a) => a.destroy());
  document.body.innerHTML = "";
  vi.useRealTimers();
});
const montar = (...a: Parameters<typeof tira>) => {
  const t = tira(...a);
  activas.push(t.accion);
  return t;
};

describe("arrastrar", () => {
  it("mover el puntero con el botón pulsado desplaza la tira en sentido contrario", () => {
    const { nodo } = montar();
    nodo.scrollLeft = 100;
    nodo.dispatchEvent(puntero("pointerdown", 200));
    nodo.dispatchEvent(puntero("pointermove", 150));
    expect(nodo.scrollLeft).toBe(150); // 100 - (150 - 200)
    nodo.dispatchEvent(puntero("pointermove", 260));
    expect(nodo.scrollLeft).toBe(40);  // 100 - 60
  });

  it("captura el puntero una sola vez al empezar a arrastrar", () => {
    const { nodo } = montar();
    nodo.dispatchEvent(puntero("pointerdown", 200));
    nodo.dispatchEvent(puntero("pointermove", 180));
    nodo.dispatchEvent(puntero("pointermove", 160));
    expect(nodo.setPointerCapture).toHaveBeenCalledTimes(1);
  });

  it("un movimiento por debajo del umbral sigue siendo un clic: no desplaza ni captura", () => {
    const { nodo } = montar();
    nodo.dispatchEvent(puntero("pointerdown", 200));
    nodo.dispatchEvent(puntero("pointermove", 197));
    expect(nodo.scrollLeft).toBe(0);
    expect(nodo.setPointerCapture).not.toHaveBeenCalled();
  });

  it("mover sin haber pulsado no hace nada", () => {
    const { nodo } = montar();
    nodo.dispatchEvent(puntero("pointermove", 50));
    expect(nodo.scrollLeft).toBe(0);
  });

  it("ignora los botones que no son el izquierdo", () => {
    const { nodo } = montar();
    nodo.dispatchEvent(puntero("pointerdown", 200, { button: 2 }));
    nodo.dispatchEvent(puntero("pointermove", 100));
    expect(nodo.scrollLeft).toBe(0);
  });

  it("al soltar deja de arrastrar y libera el puntero", () => {
    const { nodo } = montar();
    nodo.dispatchEvent(puntero("pointerdown", 200));
    nodo.dispatchEvent(puntero("pointermove", 150));
    nodo.dispatchEvent(puntero("pointerup", 150));
    expect(nodo.releasePointerCapture).toHaveBeenCalledWith(1);
    nodo.scrollLeft = 0;
    nodo.dispatchEvent(puntero("pointermove", 10));
    expect(nodo.scrollLeft).toBe(0);
  });

  it("pointercancel termina el gesto igual que pointerup", () => {
    const { nodo } = montar();
    nodo.dispatchEvent(puntero("pointerdown", 200));
    nodo.dispatchEvent(puntero("pointermove", 150));
    nodo.dispatchEvent(puntero("pointercancel", 150));
    expect(nodo.releasePointerCapture).toHaveBeenCalled();
  });
});

describe("el clic que sigue a un arrastre", () => {
  const clic = () => new MouseEvent("click", { bubbles: true, cancelable: true });

  it("se traga el primer clic tras arrastrar para no abrir lo que quedó bajo el puntero", () => {
    vi.useFakeTimers();
    const { nodo } = montar();
    const hijo = nodo.appendChild(document.createElement("button"));
    const alClic = vi.fn();
    hijo.addEventListener("click", alClic);

    nodo.dispatchEvent(puntero("pointerdown", 200));
    nodo.dispatchEvent(puntero("pointermove", 100));
    nodo.dispatchEvent(puntero("pointerup", 100));
    hijo.dispatchEvent(clic());
    expect(alClic).not.toHaveBeenCalled();

    // El vigilante se retira en el siguiente ciclo: el clic siguiente ya pasa.
    vi.runAllTimers();
    hijo.dispatchEvent(clic());
    expect(alClic).toHaveBeenCalledTimes(1);
  });

  it("un clic sin arrastre pasa tal cual", () => {
    const { nodo } = montar();
    const hijo = nodo.appendChild(document.createElement("button"));
    const alClic = vi.fn();
    hijo.addEventListener("click", alClic);
    nodo.dispatchEvent(puntero("pointerdown", 200));
    nodo.dispatchEvent(puntero("pointermove", 198));
    nodo.dispatchEvent(puntero("pointerup", 198));
    hijo.dispatchEvent(clic());
    expect(alClic).toHaveBeenCalledTimes(1);
  });
});

describe("rueda", () => {
  const rueda = (init: WheelEventInit) => new WheelEvent("wheel", { bubbles: true, cancelable: true, ...init });

  it("la rueda vertical desplaza en horizontal y evita el scroll de la página", () => {
    const { nodo } = montar();
    const e = rueda({ deltaY: 80 });
    nodo.dispatchEvent(e);
    expect(nodo.scrollLeft).toBe(80);
    expect(e.defaultPrevented).toBe(true);
  });

  it.each([
    ["con Shift (el navegador ya desplaza en horizontal)", { deltaY: 50, shiftKey: true }],
    ["con deltaX propio (trackpad)", { deltaY: 50, deltaX: 10 }],
    ["sin movimiento vertical", { deltaY: 0 }],
  ])("no interviene %s", (_, init) => {
    const { nodo } = montar();
    const e = rueda(init);
    nodo.dispatchEvent(e);
    expect(nodo.scrollLeft).toBe(0);
    expect(e.defaultPrevented).toBe(false);
  });

  it("si el contenido cabe, deja que la página se desplace con normalidad", () => {
    const { nodo } = montar(300, 300);
    const e = rueda({ deltaY: 80 });
    nodo.dispatchEvent(e);
    expect(nodo.scrollLeft).toBe(0);
    expect(e.defaultPrevented).toBe(false);
  });
});

describe("imágenes y limpieza", () => {
  it("impide el arrastre nativo de las miniaturas", () => {
    const { nodo } = montar();
    const e = new Event("dragstart", { bubbles: true, cancelable: true });
    nodo.dispatchEvent(e);
    expect(e.defaultPrevented).toBe(true);
  });

  it("destroy quita todos los listeners", () => {
    const { nodo, accion } = montar();
    accion.destroy();
    nodo.dispatchEvent(puntero("pointerdown", 200));
    nodo.dispatchEvent(puntero("pointermove", 100));
    expect(nodo.scrollLeft).toBe(0);
    const e = new WheelEvent("wheel", { deltaY: 50, cancelable: true });
    nodo.dispatchEvent(e);
    expect(e.defaultPrevented).toBe(false);
    const d = new Event("dragstart", { cancelable: true });
    nodo.dispatchEvent(d);
    expect(d.defaultPrevented).toBe(false);
  });
});
