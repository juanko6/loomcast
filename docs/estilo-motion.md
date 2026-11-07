# Estilo motion — ingeniería inversa de la referencia

> **Qué es esto.** El encargo fue «quiero que los vídeos queden como los de
> [@Stupy_Doo](https://www.youtube.com/@Stupy_Doo)». Esto es lo que se vio al
> mirarlo con calma, qué de eso sabe hacer Loomcast hoy, qué habría que
> construir y qué decisión hay que tomar antes de escribir una línea.
> Fecha: 31 oct 2026.
>
> Las capturas de referencia **no están en el repo** a propósito: son fotogramas
> de un canal ajeno y esto es un repositorio público. Lo que se versiona es la
> descripción del lenguaje, que es lo que se puede reconstruir.

## 1. El canal

| | |
|---|---|
| Canal | Stupy Doo (`@Stupy_Doo`), 162 K suscriptores, 139 vídeos |
| Se presenta como | «desarrollador de Inteligencia artificial que en el fondo quiere ser youtuber» |
| Lo nuevo | «Más carriles nunca reducen el tráfico…» (8:09, 9,6 K) y «La abeja de miel no se está extinguiendo» (4:47, 24 K), los dos de hace nueve días |
| Lo viejo | mods de Terraria y tutoriales de Sony Vegas, de hace diez años |

El canal **pivotó hace poco**. Lo que te gusta es lo nuevo: divulgación de datos
en horizontal, de cuatro a ocho minutos, con tesis, fuentes citadas y
contraargumento. El de los carriles cita a Duranton y Turner, al Instituto Cato,
a Greenshields (1934), a Wardrop y la paradoja de Braess. El de las abejas
desmonta un bulo con series históricas de colmenas.

## 2. El hallazgo que cambia el plan

**No hay un solo fotograma generado por IA.** Ni difusión, ni i2v, ni stock. Es
todo vectorial y simulado: dibujado por código y animado por código.

Eso es exactamente el modo `motion` que se midió esta semana, y descarta de
plano los otros dos caminos para este estilo. También quiere decir que la pieza
que falta de la Fase 6 —el QA de caras con ArcFace— no pinta nada aquí: en este
estilo no hay caras que mantener.

## 3. El inventario del lenguaje

Lo que en el flujo que te inspiró llaman «el contact»: la gramática, no la obra.

| Capa | Qué hace |
|---|---|
| **Escenario** | Una simulación vista desde arriba (una ciudad en rejilla con coches que circulan) o un escenario lateral (colmenas en fila, un camión cruzando). Fondo casi negro con textura sutil. |
| **Objetos** | Vectores planos de dos o tres tintas: coches rojos de seis píxeles, colmenas naranjas, flores blancas y violetas, un camión blanco. Nada de detalle: silueta y color. |
| **Cámara** | Paneos lentos y zooms sobre la simulación, rotaciones isométricas, y travelling lateral cuando algo se desplaza. La cámara es la que narra. |
| **Anotación** | Círculos sobre un objeto con línea de guía hasta una etiqueta, llaves, tramas rayadas sobre una zona, nodos A y B unidos por aristas. Dibujado como si fuera a mano sobre la escena. |
| **Etiquetas** | Píldoras: oscura con texto blanco para afirmaciones, azul con monoespaciada para citar a una persona, contorno amarillo para cifras, papel blanco rotado para notas. |
| **Cifras** | Numeral enorme en azul (`26`, `14`, `4.000`) con la unidad en minúscula pequeña al lado. |
| **Rótulo de lugar** | «Nueva York» en negrita blanca con el año debajo en monoespaciada pequeña. |
| **Gráficas** | Ejes dibujados a mano que se trazan solos, puntos que van cayendo uno a uno y una anotación en lima señalando la conclusión («casi no bajó»). |
| **Dos mundos** | El oscuro de la simulación y uno **crema de papel** para lo histórico y lo académico: recorte de periódico, tira de película, cita con año. |
| **Subtítulos** | Quemados, blancos, en caja translúcida, abajo. |
| **Paleta** | Negro `#0a0a0c`, azul fuerte, rojo de los coches, lima para los remates, crema para el mundo papel. |
| **Tipografía** | Una grotesca negrita para las afirmaciones y una **monoespaciada** para datos, años y citas. Ese contraste es media identidad del canal. |

Si hubiera que resumirlo en una frase: **una simulación que se deja anotar**.

## 4. Qué tiene Loomcast y qué le falta

Esta tabla es del 31 oct, cuando no había nada escrito. Se deja como estaba y
se le añade la columna de lo que pasó después, porque la mitad del valor de
este documento es saber qué se creía al empezar.

| Pieza | Estado el 31 oct | Cómo acabó |
|---|---|---|
| Render de HTML+GSAP a MP4 | ✅ medido: 55 s de vídeo en 31 s | se cambió por Pillow (§12) |
| Sincronía palabra a palabra | ✅ `palabras.json` ya lo da | sin tocar |
| Voz, música, cola, parada, autopiloto, lotes | ✅ sin cambios | sin cambios, confirmado |
| Fichas de escena escritas por el LLM | 🟡 probado: acierta estructura y énfasis, no condensa (ver abajo) | ✅ condensa el revisor, no el modelo (§11) |
| Capa de anotación (píldoras, guías, cifras) | ⬜ es el kit, trabajo nuevo | ✅ seis bloques (§10) |
| Simulación del escenario | ⬜ lo gordo: un canvas con sembrado determinista | ✅ una ciudad sembrada (§9) |
| Gráficas que se trazan | ⬜ el registro de HyperFrames trae nueve bloques de gráficas | ✅ una, escrita a mano |
| Formato horizontal y guion largo | ⬜ **no existe**: ver el choque de abajo | ⬜ sigue sin existir |

## 5. El choque que hay que decidir

Loomcast hace **vertical de 50 segundos con gancho y CTA**. La referencia es
**horizontal de 4 a 8 minutos con tesis, datos y contraargumento**. No es el
mismo producto, y la diferencia no está en el motor de render sino en el guion.

Dos caminos:

**(a) Traer el lenguaje al corto vertical.** La gramática de arriba funciona
igual en 9:16: simulación arriba, cifra enorme, anotaciones, cierre. No toca
nada del pipeline salvo el kit. Es una plantilla más, al lado de
`curiosidades`.

**(b) Añadir el formato largo.** Cambia el guion (de 130 palabras a 1.200), los
metadatos, la duración objetivo, el troceado de escenas, el armado en 16:9 y,
sobre todo, **obliga a que lo que se cuenta sea verdad**.

Recomendación: **(a) primero**. Un corto vertical con este lenguaje se puede
tener funcionando sin tocar el pipeline, y es la prueba de si el kit aguanta
antes de rehacer el guion.

## 6. El problema que este estilo trae consigo

Este género **se sostiene sobre datos verificables**. El vídeo de los carriles
cita un estudio con autores y años, da la cifra del presupuesto de una autopista
y menciona a quien le lleva la contraria. Un modelo local de 35B escribiendo eso
se inventará nombres, años y cifras con total aplomo, igual que se inventó dos
palabras que no estaban en el segmento.

Para `curiosidades` eso es un defecto tolerable. Para divulgación con fuentes es
una mentira publicada con tu cara. Si se va por este camino, el guion necesita
otra cosa: o datos que entren **a mano** en el proyecto (una tabla, tres fuentes
con su enlace) y el LLM solo los redacte, o búsqueda con citación. Es la decisión
más importante de todas y no es técnica.

## 7. Otros creadores que mirar

Estos salen del vecindario que YouTube pone junto al vídeo de los carriles — es
decir, contra quién compite de verdad, no una lista de nadie:

| Canal | Lo que vale la pena robarle |
|---|---|
| **CienciaX** — «Cómo Valencia movió un río entero» (331 K) | Historia de ingeniería local contada con mapas; el mismo truco de rótulo de lugar y año |
| **Science Time** — bomba de 100 Mt sobre Nueva York en 3D (2,9 M) | Escalas imposibles en 3D sobre una ciudad real; el radio que crece es un bloque reutilizable |
| **OBF** — «¿Qué país rico se declarará en bancarrota primero?» (8,3 M) | Economía con gráficas animadas; el que mejor convierte datos en tensión |
| **Los Ecomonos** — «Stellantis… explicado con plátanos» (376 K) | Metáfora física para una cifra: el recurso más barato que existe |
| **Coordenada Crítica** — colapso de la AMOC (210 K) | Mapas de proceso y escenarios; mucha anotación sobre mapa |
| **Oliver Nabani**, **Península por Dentro**, **Así Se Explica** | El mismo nicho con menos producción: ahí se ve qué parte del éxito es el montaje y qué parte el tema |
| **QuantumFracture** (1 M) | La referencia veterana en español: animación propia y guion muy trabajado |

Y los de fuera que explican de dónde viene todo esto:

- **Primer** (Justin Helps) — simulaciones de agentes programadas, en Blender y Python. Es el abuelo directo de lo que hace Stupy Doo: evolución, votaciones, economías explicadas con bichitos que se mueven en una rejilla. Si hay un canal que mirar para entender cómo se escribe una simulación narrativa, es ese.
- **3Blue1Brown** y su librería **Manim** — animación matemática generada por código Python. Alternativa real a HyperFrames si el estilo se fuera hacia lo matemático: Loomcast ya es Python. Más limitado para diseño, imbatible para fórmulas y geometría.
- **Kurzgesagt** — el vector plano llevado al extremo; de ahí sale la idea de «objetos de dos tintas sobre fondo oscuro».
- **Vox** (sección Darknet / Missing Chapter) — la capa de anotación sobre imagen: círculos, flechas, subrayados. Media gramática de Stupy Doo viene de aquí.
- **Johnny Harris** — mapa + línea de tiempo + tono personal; el montaje más imitado del momento.

## 8. Lo que yo haría, en orden

1. **Un bloque de simulación y nada más.** Un canvas con una rejilla de ciudad sembrada por semilla y coches que circulan, y la cámara encima. Si eso sale bonito y determinista, el estilo entero es alcanzable; si no, no hay kit que lo salve.
2. **La capa de anotación como bloques sueltos**: píldora, cifra enorme, círculo con guía, rótulo de lugar y año. Son CSS y SVG, y son lo que hace que una simulación parezca un vídeo explicativo.
3. **Una plantilla `explica` en vertical** que use las dos cosas, con su `escena.md` devolviendo fichas de composición. Con eso ya hay vídeo de punta a punta sin tocar el pipeline.
4. Y solo entonces, decidir si se va al formato largo — que es rehacer el guion, no el render.

Lo que no haría: copiar la paleta. El azul es suyo; el acento de Loomcast es
`#6d5efc` sobre `#0d0f14` y ya está decidido en la marca. Se copia la gramática,
no el color.

## 9. Paso 1, hecho — el bloque de simulación

Escrito y renderizado el 1 nov 2026 en el banco de pruebas: `sim-ciudad.html`,
6 s en vertical a 30 fps. Lo que se describe aquí es ese prototipo en HTML;
llegó a vivir portado a Pillow en el repositorio y se borró cinco pasos más
tarde (§13), así que esto es el acta de un banco de pruebas, no de código que
exista.

**Qué hace.** Una semilla (`20261101`) y de ahí sale todo: los anchos de calle
—unas pocas son avenidas, y una avenida no es una calle con más pintura sino con
más carriles—, qué manzanas son parque, cuáles plaza y cuáles edificios, cómo se
parten esos edificios y cuánto cantean. Unos mil coches circulan por los
carriles, y la cámara arranca con la ciudad entera cabiendo justa en el encuadre
y se mete hasta un cruce de avenidas, con tres grados de giro al final.

**Lo que mejor ha salido.** Los coches no se simulan uno a uno: su sitio es una
cuenta del reloj, posición de partida más velocidad por tiempo, y encima una
onda que viaja hacia atrás. Los atascos nacen solos de ahí, se amontonan donde
la onda frena y se estiran donde la suelta, igual que en una autovía de verdad.
Sale gratis y es exacto en cualquier fotograma, que es justo lo que pide un
render que va dando saltos por la línea de tiempo.

**El coste.** 180 cuadros de 1080×1920 en **5,0 s** — menos que lo que dura el
vídeo. Ken Burns tarda media hora y el i2v hora y cuarto.

**El susto, y lo que hay que apuntar.** Dos renders seguidos de lo mismo daban
ficheros distintos. No era la simulación: los fotogramas diferían en 48–55 dB de
PSNR, o sea solo en el antialias. Es el rasterizador por GPU de Chrome, que en
este Mac no repite. Con `--no-browser-gpu` los dos renders salen con el **mismo
md5, bit a bit**, y no cuesta un segundo más porque el dibujo es barato. Para
motion, el render va siempre por software.

**Lo que no hace, y no conviene olvidar.** Los coches se ignoran entre sí: no
hay semáforos ni cedas, y en un cruce se solapan. Para dos segundos de plano
general no se nota, pero esto es decorado, no un modelo: sirve para ilustrar una
idea, nunca para sostenerla.

**Veredicto.** El paso 1 pasa: sale bonito y sale determinista. El estilo es
alcanzable, y lo siguiente es la capa de anotación.

## 10. Paso 2, hecho — la capa de anotación

Escrito y renderizado el 1 nov 2026, también en el banco: `anotacion.html`, 8 s
en vertical, con la ciudad del paso 1 debajo. En el repositorio es
`_motion_bloques.py` (§12).

**Los seis bloques.** Rótulo de lugar y año (negrita blanca, año en
monoespaciada); cifra enorme con la unidad pequeña debajo, contando sola hasta
su valor; píldora anclada en dos sabores —oscura con texto blanco para afirmar,
contorno lima con monoespaciada para una cifra—, las dos con su punto en el
sitio al que señalan; nodos A y B unidos por una ruta que va **por las calles**,
con dos codos, dibujándose sola; círculo sobre el cruce con línea de guía hasta
su etiqueta; y una gráfica que se traza con la punta avanzando y un remate en
lima diciendo qué mirar.

**Lo que había que resolver, y es la pieza del día: el ancla.** Una anotación no
se coloca en la pantalla, se engancha a un sitio del mundo, y la pantalla es
donde ese sitio cae en cada fotograma. El módulo de la ciudad expone
`proyectar(cam, x, y)`, que hace la misma cuenta que el dibujo —incluido el
recorte de cámara contra los bordes—, y la capa de anotación recoloca sus piezas
con ella en cada fotograma. Por eso el círculo sigue pegado al cruce mientras la
cámara entra y gira, y la ruta sigue encima de sus calles. Una anotación cuyo
anclaje se sale del encuadre no se difumina: se va del todo.

**La ciudad ya es un módulo.** `assets/ciudad.js`, compartido por las dos
composiciones. Sacarlo del primer fichero dio un render **idéntico bit a bit** al
de antes, que es la forma barata de comprobar que la extracción fue fiel.

**El coste.** 240 cuadros de 1080×1920 en **5,0 s**, y el mismo md5 dos veces
seguidas. La anotación sale gratis: lo que cuesta es la ciudad.

**Lo que hay que llevarse al paso 3.** Los bloques se estorban. La cifra enorme
y el nodo A se peleaban por la esquina de arriba; la etiqueta del círculo y la
gráfica, por la banda de abajo. Se arregla en el plano de rodaje —uno se va
antes de que entre el otro—, pero eso quiere decir que **una ficha de
composición tiene que declarar en qué banda de la pantalla se pone** (arriba,
centro, abajo) y que el montador no puede dejar dos bloques en la misma banda a
la vez. No es un detalle de estilo: es una restricción del formato de la ficha.

Y una cosa de oficio: sobre una ciudad casi negra, un panel oscuro no existe.
Todas las cajas llevan un filo de luz al 16–22 % y una sombra larga, o el texto
flota sin caja.

## 11. Paso 3, hecho — la plantilla `explica`

Escrita y probada el 1 nov 2026. Ya está en `plantillas/explica/`; lo que
quedaba para poder meterla ahí es la §12.

**Qué hay.** La plantilla entera: `plantilla.json` (que valida contra
`backend/schemas/plantilla.py` tal cual, con un campo nuevo `montaje: "motion"`
que pasa por el `extra="allow"`) y sus ocho prompts. Los de siempre adaptados al
nicho, y dos reescritos de arriba abajo:

- **`storyboard.md`** ya no reparte encuadres de cámara entre fotos: reparte
  **bloques de anotación** y **movimientos de cámara**, los dos de una lista
  cerrada, uno por segmento y en orden. Decide de una vez cuál es el plano que
  afirma, cuál el que cuenta, cuál el que señala un sitio y cuál el que traza la
  curva.
- **`escena.md`** ya no escribe un prompt para un modelo de imagen: escribe la
  **ficha de composición**, o sea las palabras que se ven literalmente en
  pantalla. `{bloque, banda, texto, apoyo, enfasis}`. Seis bloques (ROTULO,
  TITULAR, CIFRA, PILDORA, CIRCULO, GRAFICA), tres bandas y cinco movimientos.

Y el montador: la ficha más los tiempos del segmento se convierten en una
composición por escena, que se renderiza a `clips/NN.mp4` como cualquier otro
modo. El reloj del tráfico no se reinicia en cada clip — cada composición
arranca en el `t_inicio` de su segmento —, así que los coches siguen donde
estaban y el corte entre escenas no se nota.

**Probado de punta a punta** con un guion de verdad de la base (`el-codigo-que-
nadie-puede-borrar`, 48,8 s, 11 escenas) y el 35B local: storyboard 10,3 s +
once fichas 13,4 s + render 54,6 s (4,9 s por clip) = **79,7 s** para 48,8 s de
vídeo. Ken Burns tarda media hora y el i2v hora y cuarto.

**El hallazgo del día: la reparación va en el storyboard, no en la ficha.** El
modelo incumple su propia regla de no repetir bloque —cuatro TITULAR seguidos al
final de un vídeo—, así que hay que arreglarlo. Lo arreglé primero sobre las
fichas ya escritas y salió peor de dos maneras: cambiar todos los repetidos al
mismo bloque dejó el vídeo haciendo pimpón entre dos, y cambiar el bloque
**después** de escribir el texto metió una frase entera dentro de una píldora,
que es una etiqueta de tres palabras. Movido delante —se repara el plano, y la
ficha se escribe ya sabiendo en qué bloque va— la misma tanda bajó de 4 bandas
repetidas a 1 y de 3 bloques mal a 1. La regla general: **repara lo que decide
la forma antes de pedir el contenido**.

**La mentira, cortada por construcción.** Una CIFRA solo existe si el guion trae
un número: el revisor del storyboard la degrada a TITULAR cuando el guion no
tiene dígitos, antes de que nadie se lo pida al modelo, y el revisor de fichas
vuelve a comprobarlo contra los números del guion. En esta tanda las dos
cuentas salieron a cero, pero porque el storyboard no pidió ninguna CIFRA: es
el bloque menos probado de los seis, y conviene decirlo.

**Y una de oficio, otra vez la misma.** Cortar una tarjeta a N palabras a ciegas
la deja colgando: «un fantasma digital **en**». Se arregla soltando los enlaces
del final, exactamente como ya hacía `escenas._breve` con las fichas del
reparto. Era el mismo problema y tenía la misma solución a veinte líneas de
distancia.

### La decisión que quedaba, y cómo se resolvió

Quedaba una: con qué se dibuja. El banco usó el CLI de HyperFrames, que para
probar fue perfecto —trajo el contrato, el lint y la prueba de determinismo— y
para producción tenía dos pegas: mete Node y npm en la instalación de un
proyecto que es Python + ComfyUI con lanzador propio, y es una caja negra
respecto a lo que Loomcast ya tiene montado (`parada.comprobar`,
`progreso.lote`, el presupuesto de memoria, `procesos.ejecutar`). La
alternativa que se barajó —un Chromium por Playwright— quitaba Node pero
dejaba un navegador dentro.

Se midió la tercera: **dibujarlo con Pillow**, que ya está instalado. La ciudad
es geometría y rectángulos, o sea exactamente lo que una librería de dibujo
hace. Salió más rápido que el navegador, sin dependencias nuevas, y de regalo
se llevó por delante el problema de determinismo: no hay rasterizador de GPU
que pueda cambiar de opinión entre dos renders. El antialias que el navegador
daba solo se consigue dibujando a 2x y bajando con `reduce(2)`, que es la media
exacta de cada cuadrado de cuatro píxeles.

## 12. Paso 4, hecho — el modo en el repositorio

El 1 nov 2026 aterrizó, y es un **modo de vídeo más**, no una categoría aparte.
Lo decide la plantilla con un campo: `"montaje": "motion"`. La razón es que
comparte todo el ciclo de vida —idea, guion, voz, subtítulos, música, armado,
publicación— y produce el mismo mp4 vertical. Una pestaña propia habría
duplicado ese camino entero para cambiar una etapa de once.

| Pieza | Dónde |
| --- | --- |
| El lienzo: medidas, paleta, curvas y proyección | `backend/services/pipeline/_motion_lienzo.py` |
| La composición de cada escena | `backend/services/pipeline/_motion_escena.py` |
| Los seis bloques de anotación | `backend/services/pipeline/_motion_bloques.py` |
| La revisión de planos y de fichas | `backend/services/pipeline/_motion_ficha.py` |
| La etapa que dibuja los clips | `backend/services/pipeline/motion.py` |
| La rama de la etapa de escenas | `escenas.py` |
| La plantilla | `plantillas/explica/` |

(La ciudad duró un día como columna vertebral del modo: la sustituyó la
composición por escena del paso 5, abajo. `_motion_ciudad.py` se borró con sus
trece tests el mismo día; lo que se cuenta de ella en este documento es
historia, no código que exista.)

Tres cosas que se aprendieron al aterrizarlo:

**El modo no se elige, lo impone la plantilla.** Ni en el paso de vídeo ni al
lanzar un lote. Una plantilla de motion con el modo Ken Burns se quedaría
esperando imágenes que nadie va a generar, y una plantilla de imágenes en modo
motion pediría clips sin ficha. Así que `generar_video` y
`autopiloto._modo_real` lo resuelven desde la plantilla, y la UI esconde el
selector. Lo que no se puede elegir mal no se elige.

**Los fotogramas no pasan por el disco.** Dibujar 2.926 PNG de 1080x1920 para
que ffmpeg los vuelva a leer es trabajo de sobra: se le dan crudos por stdin.
Eso hizo falta `procesos.ejecutar_alimentado`, porque `ejecutar` manda stdin a
`/dev/null` a propósito (un SIGTTIN heredado de la terminal congela el backend
entero, que ya pasó una vez). La tubería es nuestra, así que ese motivo se
cumple igual.

**Lo que se corrige en la UI tiene que cambiar el vídeo.** El texto de la ficha
viaja en `escena.prompt`, donde las demás plantillas llevan el prompt visual, y
es de ahí de donde lo lee el dibujo —no de la copia que quedó dentro del JSON—.
Si no, editar una tarjeta en la pantalla de escenas no haría nada y no habría
forma de saberlo hasta ver el vídeo.

Lo que **no** se hizo, a propósito: la cifra sigue siendo el bloque menos
probado (el guardián de honestidad la degrada a titular en cuanto el guion no
trae ese número, que es casi siempre), y el único formato es el vertical.

## 13. Paso 5 — la ciudad se cae y cada escena dibuja lo suyo

El primer vídeo de verdad dejó claro lo que el paso 1 había escondido: **el
fondo era siempre el mismo**. La ciudad era un banco de pruebas excelente —
probó que el estilo se alcanzaba por código y que repetía bit a bit— y se
quedó de columna vertebral por inercia. El prompt del storyboard llegaba a
decir, literalmente, que si el mecanismo no iba de tráfico se eligiera la
ciudad igual y se explicara «en sus términos». Un vídeo sobre la jerarquía de
caché acababa siendo coches.

Lo que sustituye a la ciudad no es otra ciudad: es que **cada escena declara lo
que se dibuja en ella**, sobre negro, y puede continuar la anterior o empezar
de cero.

**El vocabulario es cerrado y la colocación es del código.** Cinco tipos de
pieza, siete estados, ocho animaciones, tres costes de vínculo. El modelo dice
qué hay y qué conecta con qué; el reparto por filas y los huecos los calcula
`_motion_escena`. La tentación era dejarle colocar —o darle un DSL de dibujo
con rectángulos y flechas— y habría sido un error: con coordenadas del modelo,
la mitad de los vídeos salen con las cajas pisándose y eso no se puede revisar
a ojo en un lote.

**Lo lento tiene que tardar.** Fue la petición más clara: una tortuga no, pero
que la RAM sea lenta sí. Un vínculo `largo` abre el hueco en pantalla *y* hace
que el paquete tarde 2,1 s en cruzarlo; `caliente` respira en naranja. El
estado no decora el dibujo, es el dibujo.

**Las escenas dejan de durar todas lo mismo.** Era la otra petición, y chocaba
con un hecho: la voz ya está grabada. Se resolvió cortando por frases —que ya
traen sus tiempos de `palabras.json`— y dejando que el storyboard diga cuántas
van juntas en cada toma. Así una escena dura 3,1 s y la siguiente 10,5 s, y la
suma sigue siendo exactamente el audio. El modelo no dice segundos nunca.

**Del storyboard se usa el tamaño del grupo, no los índices.** Los índices los
baila —se salta una frase, repite otra— y entonces quedan frases sin escena.
El tamaño, en cambio, es lo que de verdad quiso decir.

| Pieza nueva | Dónde |
| --- | --- |
| El lienzo común: medidas, paleta, curvas, proyección | `_motion_lienzo.py` |
| La composición: colocación, piezas, estados, animaciones | `_motion_escena.py` |
| El corte por frases y su reparto en escenas | `_motion_frases.py` |
| El repaso del dibujo | `_motion_ficha.py::revisar_dibujo` |

Dos cosas que se vieron solo al renderizar:

**El titular se comía el esquema.** Sobre la ciudad bastaba la viñeta, porque
la ciudad es textura. Un esquema no: son cajas con sus propias etiquetas, y un
titular cruzado por un banco de memoria no deja leer ninguno de los dos. Se
añadió un plato detrás del texto que funde lo que hay con el fondo en vez de
tapar.

**El modelo dibuja estrellas donde hay cadenas.** Escribe `cpu→l1 corto`,
`cpu→l2 medio`, `cpu→ram largo`: no está mal visto de cerca —el procesador
habla con las tres— pero se dibuja como una fila con las tres al mismo lado, y
ahí se pierde justo la distancia que el vídeo estaba explicando. Pedirlo en el
prompt no sirvió: lo siguió haciendo. Se endereza en el repaso, y solo cuando
salen tres o más de la misma pieza con costes distintos; tres al mismo coste
son alternativas de verdad y se quedan.

## 14. Paso 6 — la segunda referencia, y el titular pasa a ser la capa que manda

El 2 nov 2026 entró una referencia nueva: los shorts de
[@FaztTech](https://www.youtube.com/@FaztTech), y con ellos
[un vídeo de @iadeguardia](https://vt.tiktok.com/ZSgoP1V3q/) sobre cómo se le
piden las cosas a HyperFrames. Se miraron los cinco últimos shorts fotograma a
fotograma. No sustituyen a Stupy Doo: lo que traen es el nicho —divulgación
técnica, no de datos— y, sobre todo, un hallazgo que no se veía en la primera
referencia.

**Lo que hacen y aquí no se hacía.** El marco es fijo en todos: fondo casi
negro con rejilla, subtítulos **arriba**, pequeños y literales, una chapa de
versalitas debajo diciendo por qué parte del vídeo vamos, y abajo un titular
grande que **cambia cada dos o tres segundos**, con una palabra en el color de
acento. En medio, un escenario que cambia por latido: un esquema, una réplica
de terminal con el comando tecleándose, un navegador con su dirección, una
lista numerada, un ordinal gigante.

**El hueco que eso destapó.** Loomcast tenía una tarjeta por escena, y una
escena dura hasta nueve segundos (§13). O sea: durante el plano en el que se
explica lo importante, la pantalla estaba quieta. El titular pasa a ser una
capa propia, **uno por frase**, con los tiempos que `palabras.json` ya daba y
que `_motion_frases` ahora reparte dentro de cada escena. No es un efecto: es
la capa que sostiene el vídeo, y las demás se ordenan alrededor de ella.

**Y eso reordenó el resto.** `TITULAR` deja de ser uno de los seis bloques —era
«the workhorse», el que se ponía cuando no había nada mejor— y aparece `NADA`,
que es el caso **más común** del lenguaje que se está copiando: esquema,
titular y chapa ya cuentan la toma. Entraron `LISTA` y `ORDINAL`, que son lo
que sostiene un vídeo que promete tres cosas y luego las dice. La chapa se fue
al storyboard, porque decir por qué parte vamos es una cuenta del vídeo entero
y una escena sola no la sabe.

**Las dos piezas nuevas traen algo real a la pantalla.** `terminal` y
`navegador` se dibujan con Pillow como todo lo demás, y lo que llevan dentro
—el comando, la dirección— tiene que estar en el guion. El navegador **no
finge una captura**: dibuja el esqueleto de una página. Fingir el sitio exige
una imagen que nadie ha visto; un esqueleto dice lo mismo sin afirmar nada.
(La idea de que esos iconos y logos los acabe generando el motor de imágenes
del propio Loomcast está anotada y no hecha.)

**La receta del TikTok, traducida.** El vídeo tacha «hazme un vídeo bonito» y
lo cambia por **guion exacto + datos reales + referencia visual**. Las tres
están ahora al principio de `storyboard.md` y de `escena.md`, y la tercera era
la que faltaba: el prompt pedía «qué se dibuja» en abstracto, que es
exactamente lo que el vídeo tacha. Ahora cada plano nombra lo que se ve de una
lista cerrada o no se puede construir.

**Lo que se vio solo al dibujar.** Dos cosas, y las dos de encuadre:

- *El esquema se metía debajo del titular.* El aire se reservaba solo si el
  bloque caía en esa banda, y el titular está en **todas** las escenas. Ahora
  el encuadre vive siempre entre lo que ocupan los subtítulos y la chapa
  arriba (`AIRE_CHAPA`) y lo que ocupa el titular abajo (`AIRE_TITULAR`).
- *Acercarse sacaba del cuadro aquello a lo que te acercabas.* `cerca` era
  `z * 1.45`, relativo al encuadre, y en una escena de una sola pieza el
  encuadre ya era la pieza: con una ventana —ancha y con texto dentro— el
  comando se leía a medias siempre. Ahora el zoom se topa a lo que deja la
  pieza enmarcada dentro del cuadro.
- *Y el titular salía desalineado, que es lo que se vio de lejos.* Eran dos
  cosas a la vez, heredadas de cuando la tarjeta era una por escena y nadie la
  miraba dos veces. La primera: cada palabra se dibujaba restándole **su**
  desplazamiento de medida, y eso alinea los topes de tinta, no las bases —una
  palabra sin astas ni mayúsculas se sube por encima de sus vecinas—. La
  segunda: las palabras entraban cada una con su propio salto, así que durante
  el tercio de segundo de la entrada la frase estaba a cuatro alturas
  distintas, que es justo cuando se empieza a leer. Ahora la línea entera
  comparte la referencia vertical de la línea, el titular entra de una pieza y
  lo que se escalona es encenderse. De paso, el hueco entre palabras se mide
  en la fuente en vez de ser veinte píxeles fijos: con uno inventado, la línea
  se centraba por una medida y se dibujaba con otra.

| Pieza | Dónde |
| --- | --- |
| Las tres capas de texto: titular, chapa y bloque | `_motion_bloques.py` |
| El reloj de cada frase dentro de su escena | `_motion_frases.py::_reloj` |
| Terminal y navegador, y el tecleo | `_motion_escena.py` |
| Los titulares, las filas y los bloques que se apagan sin datos | `_motion_ficha.py` |
| Los subtítulos arriba y pequeños | `_subtitulos_render.py`, `armado.py`, `plantillas/explica/plantilla.json` |

Lo que **no** se hizo, a propósito: el formato sigue siendo el vertical de unos
50 segundos explicando un mecanismo, no el short de 90 a 140 segundos en
formato lista que hace Fazt; no hay logos, capturas ni ningún recurso que no
dibuje el código; y la paleta sigue siendo la de la marca y no una por vídeo.

## Apéndice — lo medido el 31 oct 2026

Banco de pruebas con HyperFrames 0.8.225 en el M3 Max (Node 26.8.1, ffmpeg 9.0.2):

| Prueba | Tiempo |
|---|---|
| 5 s vertical @ 30 fps (150 cuadros) | 6,1 s |
| 5 s vertical @ 60 fps (300 cuadros) | 6,3 s |
| **55 s vertical @ 60 fps (3.300 cuadros)** | **31,0 s** |
| 3 escenas sueltas de 4 s @ 60 fps | 17,4 s en total |
| Escena con personaje recortado (PNG de 1.280 px) | 7,5 s |
| Escena con personaje vectorial animado (SVG + GSAP) | 8,0 s |
| Recorte de un retrato del reparto con rembg | 15,6 s el primero, 0,2 s el siguiente |
| **Simulación de ciudad, 6 s @ 30 fps (180 cuadros, ~1.000 coches)** | **5,0 s** |
| La misma, dos veces con GPU | distintas (PSNR 48–55 dB, solo antialias) |
| La misma, dos veces con `--no-browser-gpu` | idénticas, mismo md5, 5,0 s |
| **Ciudad + capa de anotación, 8 s @ 30 fps (240 cuadros)** | **5,0 s**, mismo md5 dos veces |
| **Vídeo `explica` entero: 11 escenas, 48,8 s** | **79,7 s** (storyboard 10,3 · fichas 13,4 · render 54,6) |
| La misma ciudad dibujada con Pillow, sin navegador, 1x | 3 ms/cuadro → **5 s** por vídeo de 50 s |
| Íd. a 2x con `reduce(2)` (el antialias que el navegador da solo) | 10 ms/cuadro → **15 s** por vídeo de 50 s |

### Lo medido el 1 nov 2026, ya dentro de Loomcast

El mismo vídeo (`el-codigo-que-nadie-puede-borrar`, 48,8 s de narración, 11
escenas) de punta a punta con el modo motion del repositorio, sin navegador:

| Etapa | Tiempo |
| --- | --- |
| Escenas: storyboard + 11 fichas (Qwen3.6 35B A3B, MLX) | 25,3 s |
| **Clips: 2.926 cuadros a 60 fps, dibujados y codificados** | **73,8 s** (25 ms/cuadro) |
| Armado: concatenar, rasterizar subtítulos y pegar la voz | 43,2 s |
| **Total** | **142,3 s** para 50,9 s de vídeo |

Los 25 ms por cuadro son el coste real: los 10 ms que se midieron en el banco
eran la ciudad sola, sin la capa de anotación, sin la viñeta y sin ffmpeg. Aun
así, el banco renderizaba a 30 fps; a los 60 fps que usa el resto del pipeline
el navegador habría pedido unos 110 s para lo mismo.

De las 11 fichas salieron 10 correcciones, que **no** son 10 escenas rotas sino
10 arreglos sueltos: 5 bloques repetidos, 2 bandas repetidas, 1 ficha que no
respetó su bloque, 1 texto largo y 1 énfasis que no estaba en el texto. El
reparto de planos del modelo era bueno; lo que no cumple nunca es su propia
regla de no repetir.

Para comparar, de la propia base de datos (`escenas` con `clip_s > 0`, 13,6
escenas de media por proyecto): Ken Burns ~30 min por vídeo, i2v ~76 min.

Y la prueba del LLM (Qwen3.6 35B A3B en MLX, 13 escenas de un guion real):
18,1 s en escribir las trece fichas; 13 de 13 con el bloque bien elegido y el
énfasis bien puesto; 11 de 13 sin condensar el texto; 2 con palabras que no
estaban en el segmento. Pidiéndole índices en vez de texto desaparecen los dos
problemas pero aparece otro: 2 de 13 apuntan a palabras que no existen.
Conclusión: texto libre, validación dura y reparación, nunca confianza.
