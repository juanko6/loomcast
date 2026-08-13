# Marca Loomcast — direcciones para el símbolo

> **Estado (12 ago 2026):** ya hay decisión. El original vivo es
> `brand loomcast v1.ai` (5 mesas de trabajo: logotipo, favicon en positivo,
> favicon pequeño y favicon en negativo sobre círculo). Tipografía: **Nexa
> Light**, todo en minúscula, con las dos «o» tangentes atravesadas por el hilo
> que sale por la derecha. Lo que sigue es el razonamiento que llevó hasta ahí;
> los SVG de este directorio son bocetos, no los originales.
>
> **Dónde vive cada cosa**
>
> | fichero | qué es |
> |---|---|
> | `brand loomcast v1.ai` | el original. Todo lo demás sale de aquí. |
> | `exportado/logotipo.svg` | el logotipo en curvas, `fill="currentColor"`. |
> | `exportado/marca.svg` | solo el símbolo (las dos «o» y el hilo), en curvas. |
> | `web/public/favicon.svg` | favicon: círculo en el acento con la marca en negativo. |
> | `web/public/apple-touch-icon.png` | el mismo, 180 px. |
> | `web/src/components/shell/Logotipo.svelte` | el logotipo incrustado, el que se ve en el rail. |
>
> Para regenerar los exportados desde el `.ai` (es PDF por dentro):
> `pdftocairo -svg -f <mesa> -l <mesa> "brand loomcast v1.ai" salida.svg`, y
> luego dejar un solo `<path>` con `fill="currentColor"`.

El nombre regala dos cosas: **loom** (telar: hilos que se cruzan hasta formar una
tela) y **cast** (emitir). Y regala una tercera, gráfica: la **doble o**. Las
cuatro direcciones de abajo salen de ahí — todas son monolínea, todas caben en
un cuadrado y todas se leen a 16 px.

Bocetos: [`direcciones.svg`](direcciones.svg).

Paleta del estudio (ya definida en `web/src/styles/global.css`): tinta
`#e7e9f0` sobre `#0d0f14`, acento `#6d5efc`. El símbolo se dibuja a una sola
tinta; el acento es opcional y nunca imprescindible.

---

## 01 · Trenza — la referencia que trajiste

*(Colección de logos monoline de Freepik; el recurso es de ellos, la idea de
usarla para las dos «o» es tuya.)*

Dos aros de líneas paralelas que se entrelazan como eslabones. Es la más directa
de las cuatro: dice «tejido» y «unión» sin explicar nada.

- **A favor:** el entrelazado es el gesto de la marca; funciona en negativo, en
  bordado, en una pegatina. Y las dos «o» del wordmark salen gratis.
- **En contra:** el monolínea de 4 hilos es el estilo más visto de la década, y
  a 16 px los hilos se empastan. Habría que hacer una versión de 2 hilos para
  favicon.
- **Ojo:** dos aros enlazados ya son la marca de mucha gente (y el símbolo de
  «enlace» en toda interfaz). Hay que empujarlo hacia el telar para que no se
  quede en «cadena».

## 02 · Urdimbre y trama

Las dos «o» son aros concéntricos y un haz de tres hilos horizontales los
atraviesa: se hunde bajo el aro al entrar y sale por encima al otro lado. El
telar literal.

- **A favor:** es la que más habla de *loom* y la única que no se confunde con
  otra cosa. El haz horizontal da una versión apaisada perfecta para cabecera, y
  el hilo que continúa fuera del símbolo sugiere que el material sigue.
- **En contra:** necesita aire; comprimida pierde el cruce. Es la más difícil de
  reducir a favicon (probablemente haya que quedarse con un solo aro).

## 03 · Señal que se emite

La «o» izquierda es un aro cerrado con un punto en el centro — lo que guardas.
La derecha se abre por su lado derecho y se prolonga en ondas: lo que sale.

- **A favor:** cuenta el producto entero en un gesto — material dentro, difusión
  fuera — y es la única con dirección de lectura (izquierda → derecha). Las
  ondas dan una animación obvia para la carga o el render.
- **En contra:** el vocabulario de ondas es el de wifi, podcast y radio; se
  parecerá a algo. Y las dos «o» dejan de ser gemelas, así que el símbolo pesa
  más que el wordmark.

## 04 · Obturador

Las dos «o» son el mismo diafragma en dos estados: cerrado a la izquierda,
abierto a la derecha. Entrada y salida.

- **A favor:** dice «imagen en movimiento» sin dibujar una cámara ni un
  triángulo de play. Los dos estados son un sistema, no un dibujo: sirven de
  iconos de estado, de spinner y de transición entre modos.
- **En contra:** es la más «app de foto» de las cuatro y la que menos tiene que
  ver con tejer; el aspa cerrada se ensucia en tamaños pequeños.

---

## Cómo decidir

Si la marca tiene que hablar de **cómo se hace** (muchas piezas cosidas en una),
son la 01 o la 02. Si tiene que hablar de **qué sale** (algo que se emite,
imagen en movimiento), son la 03 o la 04.

---

# Recomendación: la 02, refinada

Boceto: [`recomendacion.svg`](recomendacion.svg).

Lo que hace Loomcast es **coser pistas separadas en una pieza**. El pipeline de
vídeo son cinco pasos que generan material por separado —guion, narración,
subtítulos, imágenes, clips, música— y un montaje final que los junta. Las tres
áreas (Vídeos, Imágenes, Música) son independientes y alimentan lo mismo. Eso es
un telar, literalmente: hilos que entran por su lado y salen hechos tela.

El refinado consiste en darle dirección de lectura: **tres hilos entran por la
izquierda, atraviesan los dos aros y salen por la derecha convertidos en uno
solo**. Tres porque son tres las pistas que se montan (voz, imagen, música) y
tres las áreas de la app. Todo a una tinta: en color acento la salida parecía
una flecha de «enviar», que es justo lo que la app no hace.

## Por qué las otras tres se caen

- **01 (trenza).** Es la segunda mejor y la que mejor reduce, pero dice «unión»
  sin decir de qué; y dos aros enlazados son el icono universal de «enlace».
  Queda como reserva: si la 02 se complica, la 01 con dos hilos es un buen plan B.
- **03 (emisión).** La descarto por una razón de producto: Loomcast es 100 %
  local y nada sale de la máquina. Una marca que dibuja ondas propagándose
  promete difusión, que es precisamente lo que el proyecto no hace.
- **04 (obturador).** Habla de capturar, y aquí no se captura nada: se fabrica.
  Además la acerca visualmente a una app de foto.

## Reducción (probada, no supuesta)

El símbolo completo no sobrevive a 16 px: tres hilos de un píxel se empastan, y
un aro con un hilo horizontal centrado se lee como el icono de «prohibido» (⊖).
Lo que sí aguanta —comprobado a 64, 32 y 16— es **los dos aros más el hilo que
sale**: sigue siendo la misma historia y a 16 px todavía se distingue de un «oo»
cualquiera.

## Siguientes pasos

1. Dibujarla en curvas definitivas (ahora son arcos calculados a mano) y fijar la
   rejilla: radios, separación entre hilos y grosor único.
2. Wordmark: elegir la grotesca y comprobar que las dos «o» del logotipo aguantan
   el peso del símbolo al lado.
3. Probar el símbolo en la cabecera real de `web/` y el icono en la pestaña.
4. Versión animada para la cola de jobs: los hilos avanzan y se unen al terminar
   el montaje.
