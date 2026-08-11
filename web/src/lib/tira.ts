// Acción de Svelte para tiras horizontales: arrastrar con el ratón y rueda.
//
// Un contenedor con overflow-x solo se desplaza de forma nativa con el trackpad
// (dos dedos), las flechas del teclado o arrastrando la barra. Con ratón no hay
// forma: la rueda vertical no lo mueve y el clic sostenido tampoco. Esto añade
// las dos cosas que uno espera.
//
// Va emparejada con la clase `.tira-h` de global.css, que dibuja la barra y
// pone el cursor de agarre.

export function tiraH(nodo: HTMLElement) {
  let arrastrando = false;
  let inicioX = 0;
  let inicioScroll = 0;
  let recorrido = 0;

  // Umbral por debajo del cual el gesto sigue siendo un clic y no un arrastre;
  // sin él, el temblor de la mano al pulsar impediría seleccionar nada.
  const UMBRAL = 4;

  function abajo(e: PointerEvent) {
    if (e.button !== 0) return;
    arrastrando = true;
    recorrido = 0;
    inicioX = e.clientX;
    inicioScroll = nodo.scrollLeft;
  }

  function mover(e: PointerEvent) {
    if (!arrastrando) return;
    const dx = e.clientX - inicioX;
    if (Math.abs(dx) <= UMBRAL) return;
    // Capturar el puntero deja seguir arrastrando aunque el ratón se salga de
    // la tira, que es lo natural al empujar hasta el borde.
    if (!recorrido && nodo.setPointerCapture) nodo.setPointerCapture(e.pointerId);
    recorrido = Math.abs(dx);
    nodo.scrollLeft = inicioScroll - dx;
    e.preventDefault();
  }

  function arriba(e: PointerEvent) {
    if (recorrido > UMBRAL) {
      // El navegador dispara un `click` al soltar. Si el gesto fue un arrastre,
      // ese clic abriría la escena que quedó bajo el puntero, así que se traga
      // el primero y se quita el vigilante en el siguiente ciclo.
      const tragar = (ev: Event) => {
        ev.stopPropagation();
        ev.preventDefault();
      };
      nodo.addEventListener("click", tragar, true);
      setTimeout(() => nodo.removeEventListener("click", tragar, true));
    }
    arrastrando = false;
    if (nodo.hasPointerCapture?.(e.pointerId)) nodo.releasePointerCapture(e.pointerId);
  }

  // Rueda vertical → desplazamiento horizontal, que es lo único que tiene un
  // ratón normal. Con Shift el navegador ya desplaza en horizontal, y un
  // trackpad manda deltaX propio: en ambos casos no hay que tocar nada.
  function rueda(e: WheelEvent) {
    if (e.shiftKey || e.deltaX !== 0 || e.deltaY === 0) return;
    if (nodo.scrollWidth <= nodo.clientWidth) return;
    nodo.scrollLeft += e.deltaY;
    e.preventDefault();
  }

  // Las miniaturas son <img>, y arrastrar una imagen es un gesto nativo del
  // navegador que se comería el arrastre de la tira.
  function noArrastrarImagen(e: DragEvent) {
    e.preventDefault();
  }

  nodo.addEventListener("pointerdown", abajo);
  nodo.addEventListener("pointermove", mover);
  nodo.addEventListener("pointerup", arriba);
  nodo.addEventListener("pointercancel", arriba);
  nodo.addEventListener("wheel", rueda, { passive: false });
  nodo.addEventListener("dragstart", noArrastrarImagen);

  return {
    destroy() {
      nodo.removeEventListener("pointerdown", abajo);
      nodo.removeEventListener("pointermove", mover);
      nodo.removeEventListener("pointerup", arriba);
      nodo.removeEventListener("pointercancel", arriba);
      nodo.removeEventListener("wheel", rueda);
      nodo.removeEventListener("dragstart", noArrastrarImagen);
    },
  };
}
