"""Continuidad de una serie: el hilo, el contexto del guion y el canon.

Tres piezas, y las tres son texto:

- `generar_hilo` escribe hacia dónde va la serie desde la premisa: la pregunta,
  el destino, lo que la serie no es y un tramo por episodio. Es la única que
  mira **hacia delante**, y sin ella las otras dos solo pueden evitar
  contradicciones, no desvíos.

- `contexto_continuidad` es lo que se le añade al LLM al escribir el guion de un
  episodio: quién es el reparto fijo (con las claves con las que ya está en el
  proyecto, porque son los marcadores que el casting y las escenas usarán), qué
  pasó en el episodio anterior y qué sitio ocupa este en el hilo. **Para un
  proyecto suelto devuelve cadena vacía**, y entonces la petición del guion es
  byte a byte la de siempre.

- `generar_resumen_episodio` escribe el canon: qué pasó de verdad en el
  episodio, que es lo que leerá el siguiente. El hilo no puede hacer este
  trabajo —se escribió antes de que existiera un solo guion, así que no sabe que
  la llave llegó en un sobre ni a quién se lo contó Ana—, y el canon no puede
  hacer el del hilo. Se guarda en el proyecto y es editable como el guion o los
  metadatos: una serie que depende de un resumen que nadie puede corregir deriva
  en tres capítulos.

**Cuándo se escribe el canon**: al aprobar el guion, no al armar el vídeo. La
historia queda cerrada cuando está escrita; ni la voz ni las imágenes ni el i2v
añaden un hecho. Esperar al render metía el render en el camino de la historia y
hacía imposible escribir la temporada entera antes de producirla (y en un lote,
con la parada de revisión del guion puesta, hacía algo peor: el episodio
siguiente entraba en la línea y escribía su guion sin canon del anterior). Lo
pide `autopiloto._que_falta` justo después del guion, y por eso el canon lleva
la versión de la que salió: si el guion se edita, el canon de la versión vieja
miente, y lo que miente aquí es canon en el capítulo siguiente.

El resumen **no toca el estado del proyecto**: `avanzar_estado` describe la
producción de un vídeo (IDEA → … → FINAL) y cerrar el episodio no es una etapa
más de ese vídeo, es lo que le pasa a la serie cuando ese vídeo ya está.
"""
import json

from ...clients import llm
from ...config import PROMPTS_DIR
from ...db import get_session
from ...repositories import guiones as guiones_repo
from ...repositories import hilos as hilos_repo
from ...repositories import ideas as ideas_repo
from ...repositories import metadatos as metadatos_repo
from ...repositories import personajes as personajes_repo
from ...repositories import plantillas as plantillas_repo
from ...repositories import proyectos as proyectos_repo
from ...repositories import reparto as reparto_repo
from ...repositories import series as series_repo
from ...schemas import HiloLLM, ResumenEpisodioLLM


def _titulo(s, proyecto) -> str:
    """Cómo se llama el episodio: su título de publicación si ya lo tiene, y si
    no el de la idea con la que nació."""
    meta = metadatos_repo.ultimo(s, proyecto.id)
    if meta:
        titulo = json.loads(meta.contenido)["youtube"]["titulo"]
        if titulo:
            return titulo
    idea = ideas_repo.obtener(s, proyecto.idea_id)
    return idea.titulo if idea else proyecto.slug


# Con cuánto de un tramo futuro basta para que el guion de hoy no se lo coma.
# Va en corto a propósito: aquí no se cuenta un capítulo, se marca una frontera,
# y un tramo escrito largo (el LLM los escribe en párrafos si le dejas) metía
# cinco capítulos enteros en el prompt de uno. Además, cuanto más detalle tiene
# delante de lo que viene, más tienta adelantarlo.
TRAMO_EN_CORTO = 160


def _en_corto(texto: str | None) -> str:
    """La primera frase de un tramo, recortada. Es lo que basta para vetarlo."""
    frase = (texto or "").strip().split(". ")[0].strip()
    if len(frase) <= TRAMO_EN_CORTO:
        return frase
    return frase[:TRAMO_EN_CORTO].rsplit(" ", 1)[0] + "…"


def _bloque_hilo(hilo: dict | None, numero: int) -> str:
    """Hacia dónde va la serie, para quien escribe el guion de este episodio.

    Cadena vacía si la serie no tiene hilo: entonces la continuidad es la de
    antes, solo hacia atrás, y el prompt queda igual que estaba.

    El destino y los tramos que vienen después se le dan a propósito, aunque
    suene a espóiler: el guion los necesita para **no** tocarlos. Un capítulo
    que se desvía casi nunca contradice el pasado, se adelanta al futuro.
    """
    if not hilo:
        return ""
    mapa = hilos_repo.tramos(hilo)
    total = len(mapa)
    partes = ["HACIA DÓNDE VA LA SERIE. Esto es el plan: cúmplelo, no lo cuentes."]
    if hilo.get("premisa"):
        partes.append(f"De qué va: {hilo['premisa']}")
    if hilo.get("pregunta"):
        partes.append(f"La pregunta de la serie: {hilo['pregunta']}")
    if hilo.get("destino"):
        partes.append(
            f"Cómo acaba la serie: {hilo['destino']}\n"
            "Lo sabes para no contradecirlo y para no adelantarlo. Esto solo lo "
            "cuenta el último episodio."
        )
    fuera = [x for x in (hilo.get("fuera") or []) if x]
    if fuera:
        partes.append(
            "Esta serie NUNCA (si tu episodio hace alguna de estas cosas, se "
            "ha ido de la serie):\n" + "\n".join(f"- {x}" for x in fuera)
        )

    tramo = hilos_repo.tramo(hilo, numero)
    if tramo is None:
        partes.append(
            f"TU SITIO EN EL MAPA: el hilo planificaba {total} episodios y este "
            f"es el {numero}, así que se sale del mapa. No hay tramo que "
            "cumplir: cuenta algo que no desmienta nada de lo anterior y no "
            "vuelvas a abrir la pregunta de la serie, que ya está respondida."
        )
        return "\n\n".join(partes)

    sitio = [f"TU SITIO EN EL MAPA: episodio {numero} de {total}"]
    if tramo.get("titulo"):
        sitio.append(f"Tramo: {tramo['titulo']}")
    if tramo.get("pasa"):
        sitio.append(f"Lo que pasa en este episodio: {tramo['pasa']}")
    if tramo.get("cambia"):
        sitio.append(
            f"Lo que tiene que haber cambiado al terminarlo: {tramo['cambia']}"
        )
    partes.append("\n".join(sitio))

    siguientes = [
        f"- EP {t.get('numero')} · {t.get('titulo') or ''}: {_en_corto(t.get('pasa'))}"
        for t in mapa if (t.get("numero") or 0) > numero
    ]
    if siguientes:
        partes.append(
            "Lo que todavía NO puede pasar, porque es de los capítulos que "
            "vienen detrás:\n" + "\n".join(siguientes)
        )
    if hilos_repo.es_final(hilo, numero):
        partes.append(
            "ESTE ES EL ÚLTIMO EPISODIO Y AQUÍ SÍ SE CIERRA: responde la "
            "pregunta de la serie y llega al destino. No dejes un filo abierto "
            "ni invites al capítulo siguiente, porque no hay siguiente."
        )
    return "\n\n".join(partes)


def contexto_continuidad(proyecto_id: int) -> str:
    """Lo que el guion de este episodio tiene que saber de los anteriores.

    Cadena vacía si el proyecto no es un episodio: es lo que mantiene intacta la
    etapa de guion de los vídeos sueltos.
    """
    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        if p is None or p.serie_id is None:
            return ""
        serie = series_repo.obtener(s, p.serie_id)
        if serie is None:
            return ""
        # El reparto se lee del proyecto y no de la serie: aquí hacen falta las
        # claves con las que entraron de verdad, que pueden no ser las que
        # propone el reparto propio si alguna estaba ocupada ({ANA_2}).
        fijos = [
            f"- {{{x.clave}}} {x.nombre or x.clave}"
            + (f": {x.ficha}" if x.ficha else "")
            for x in personajes_repo.por_proyecto(s, proyecto_id)
            if x.reparto_slug
        ]
        hilo = hilos_repo.contenido(s, p.serie_id)
        previo = series_repo.anterior(s, p.serie_id, p.episodio)
        resumen_previo, numero_previo, titulo_previo = "", 0, ""
        if previo is not None:
            resumen_previo = (previo.resumen_episodio or "").strip()
            numero_previo = previo.episodio
            titulo_previo = _titulo(s, previo)
        nombre, numero = serie.nombre, p.episodio

    partes = [f"CONTINUIDAD DE LA SERIE «{nombre}» — episodio {numero}"]
    if fijos:
        partes.append(
            "Reparto fijo de la serie. Son los mismos de siempre y el "
            "espectador ya los conoce: no los vuelvas a presentar, y cuando "
            "hablen atribuye la línea con su clave tal cual está escrita aquí.\n"
            + "\n".join(fijos)
        )
    if resumen_previo:
        partes.append(
            f"En el episodio anterior ({numero_previo}"
            f"{f' — «{titulo_previo}»' if titulo_previo else ''}) pasó esto:\n"
            f"{resumen_previo}\n\n"
            "Este episodio continúa desde ahí: recoge lo que quedó abierto sin "
            "resumir el anterior (quien llega nuevo tiene que entenderlo igual, "
            "con una frase, no con un repaso)."
        )
    elif numero > 1:
        partes.append(
            "No hay resumen del episodio anterior, así que no te inventes lo "
            "que pasó: cuenta algo que funcione por sí solo con este reparto."
        )
    else:
        partes.append(
            "Es el primer episodio: planta la situación y deja algo abierto "
            "para el siguiente."
        )
    # Y lo que mira hacia delante, detrás de lo que mira hacia atrás: primero
    # qué no puedes contradecir, después a dónde tienes que llevarlo.
    hacia_delante = _bloque_hilo(hilo, numero)
    if hacia_delante:
        partes.append(hacia_delante)
    return "\n\n".join(partes)


def falta_resumen(s, p) -> bool:
    """Si a ese episodio le falta el canon, o el que tiene es de otro guion.

    Lo segundo es la mitad nueva: el resumen se escribe del guion aprobado, así
    que un guion editado deja un canon que cuenta una versión que ya no existe.
    Lo consulta el autopiloto justo después del guion (`_que_falta`), y es lo
    que hace que el episodio siguiente nazca con continuidad sin que nadie se
    acuerde de pedirla.

    Toma la sesión en vez de abrir la suya porque quien más lo llama ya está
    dentro de una.
    """
    if p is None or p.serie_id is None:
        return False
    if not (p.resumen_episodio or "").strip():
        return True
    g = guiones_repo.ultimo(s, p.id)
    return g is not None and g.version != p.resumen_version


def resumen_pendiente(proyecto_id: int) -> bool:
    """Como `falta_resumen`, pero con su propia sesión y por id."""
    with get_session() as s:
        return falta_resumen(s, proyectos_repo.obtener(s, proyecto_id))


def generar_resumen_episodio(proyecto_id: int) -> str:
    """Escribe en qué quedó este episodio, para el guion del siguiente."""
    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        if p is None:
            raise ValueError(f"Proyecto {proyecto_id} no existe")
        if p.serie_id is None:
            raise ValueError(
                "Este proyecto no es un episodio de ninguna serie: el resumen "
                "solo sirve para dar continuidad al episodio siguiente."
            )
        guion_row = guiones_repo.ultimo(s, proyecto_id)
        if guion_row is None:
            raise ValueError("El episodio no tiene guion todavía")
        serie = series_repo.obtener(s, p.serie_id)
        nombre = serie.nombre if serie else ""
        numero, titulo = p.episodio, _titulo(s, p)
        version = guion_row.version
        # El tramo que el hilo le había asignado: es lo que convierte el resumen
        # en detector de deriva. Sin hilo es None y el resumen es el de antes.
        tramo = hilos_repo.tramo(hilos_repo.contenido(s, p.serie_id), numero)
        previo = series_repo.anterior(s, p.serie_id, numero)
        # El resumen anterior entra también: así el que se escribe ahora
        # arrastra los hilos que siguen abiertos desde antes en vez de contar
        # solo este capítulo y perder la mitad de la historia en el camino.
        antes = (previo.resumen_episodio or "").strip() if previo else ""

    guion_texto = guiones_repo.texto_narrado(json.loads(guion_row.contenido))
    plan = ""
    if tramo:
        plan = "El tramo que el hilo le había asignado a este episodio:\n"
        if tramo.get("pasa"):
            plan += f"- Lo que tenía que pasar: {tramo['pasa']}\n"
        if tramo.get("cambia"):
            plan += f"- Lo que tenía que cambiar: {tramo['cambia']}\n"
        plan += "\n"
    user = (
        f"Serie: «{nombre}»\n"
        f"Episodio {numero}: {titulo}\n\n"
        + (f"Resumen del episodio anterior:\n{antes}\n\n" if antes else "")
        + plan
        + f"Guion narrado de este episodio:\n```\n{guion_texto}\n```"
    )
    sistema = (PROMPTS_DIR / "resumen_episodio.md").read_text()
    r = llm.chat(sistema, user, ResumenEpisodioLLM)

    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        p.resumen_episodio = r.resumen.strip()
        # De qué versión del guion salió: con esto se sabe que el canon dejó de
        # valer en cuanto alguien edite el guion.
        p.resumen_version = version
        # Sin tramo no hay desvío posible, diga lo que diga el LLM: no se le
        # dio ningún plan contra el que comparar.
        p.tramo_desvio = r.tramo_desvio.strip() if tramo else ""
        desvio = p.tramo_desvio
        s.commit()
    if desvio:
        return (
            f"Resumen del episodio {numero} escrito, y se salió de su tramo: "
            f"{desvio}"
        )
    return f"Resumen del episodio {numero} escrito ({len(r.resumen)} caracteres)"


# --- el hilo: hacia dónde va la serie ---------------------------------------

def _cuantos_episodios(pedidos: int, rodados: int, previo: dict | None) -> str:
    """El bloque CUÁNTOS EPISODIOS del prompt, según quién decide el número.

    Tres casos y uno es el que importa: cuando el usuario no ha puesto número,
    el LLM lo decide y además dice por qué. Que lo decida él no es un atajo —es
    lo que convierte "¿cuántos capítulos?" en una pregunta con respuesta antes
    de escribir el primero.
    """
    if rodados:
        total = len(hilos_repo.tramos(previo))
        faltan = max(total - rodados, 1)
        return (
            f"La serie se planificó con {total} tramos y {rodados} ya están "
            f"rodados. Escribe solo los que faltan: {faltan} si siguen "
            "valiendo, o los que de verdad hagan falta ahora para llegar al "
            "destino desde donde la historia se ha quedado. En "
            "`episodios_recomendados` di el total de la serie, contando los "
            "rodados."
        )
    if pedidos > 0:
        return (
            f"El usuario quiere **{pedidos} episodios**: escribe exactamente "
            f"{pedidos} tramos. Di de todos modos en "
            "`episodios_recomendados` cuántos recomendarías tú y por qué, que "
            "para eso te lo pregunta."
        )
    return (
        "El usuario no ha decidido cuántos: **decídelo tú** y escribe un tramo "
        "por episodio."
    )


def _bloque_rodado(rodados: list[dict], previo: dict | None) -> str:
    """Los tramos que ya pasaron y lo que de verdad pasó en ellos.

    Lo segundo es lo que hace útil replanificar: el tramo decía una cosa y el
    capítulo acabó haciendo otra, y es desde esa otra desde donde hay que seguir
    —no desde el plan que no se cumplió—.
    """
    partes = ["LO QUE YA ESTÁ RODADO (no escribas estos tramos otra vez)"]
    for ep in rodados:
        tramo = hilos_repo.tramo(previo, ep["episodio"]) or {}
        linea = [f"- Episodio {ep['episodio']}: {ep['titulo']}"]
        if tramo.get("pasa"):
            linea.append(f"  Su tramo decía: {tramo['pasa']}")
        if ep["resumen"]:
            linea.append(f"  Lo que pasó de verdad: {ep['resumen']}")
        if ep["desvio"]:
            linea.append(f"  Se desvió: {ep['desvio']}")
        partes.append("\n".join(linea))
    return "\n".join(partes)


def generar_hilo(serie_id: int) -> str:
    """Escribe hacia dónde va la serie, desde la premisa que puso el usuario.

    Dos usos y un solo camino, como en el resto de la app: la primera vez el
    hilo sale de la premisa, y con capítulos ya rodados **replanifica lo que
    falta** sin tocar sus tramos. Los rodados no se los pide al LLM —se copian
    del hilo anterior— porque pedir "cópiame estos y cambia el resto" es pedirle
    que no se equivoque en lo único que no se puede equivocar.

    Lo hecho no se toca, igual que con el reparto fijo: un capítulo ya escrito
    no cambia de sitio en el mapa porque el mapa se haya redibujado.
    """
    with get_session() as s:
        serie = series_repo.obtener(s, serie_id)
        if serie is None:
            raise ValueError(f"Serie {serie_id} no existe")
        premisa = (serie.premisa or "").strip()
        if not premisa:
            raise ValueError(
                "La serie no tiene premisa, y el hilo sale de ella: escribirlo "
                "desde el nombre a secas es justo lo que hacía que cada "
                "capítulo fuera de otra cosa."
            )
        nombre, plantilla = serie.nombre, serie.plantilla
        pedidos = serie.episodios_objetivo or 0
        previo = hilos_repo.contenido(s, serie_id)
        # Quiénes son ya los de la serie. Si hay alguien, el hilo no ficha a
        # nadie más: se le dan y los escribe en los tramos.
        fijos = [
            {"clave": x.clave, "nombre": x.nombre, "ficha": x.ficha}
            for x in (
                reparto_repo.por_slug(s, m.reparto_slug)
                for m in series_repo.miembros(s, serie_id)
            )
            if x is not None
        ]
        rodados = [
            {
                "episodio": p.episodio,
                "titulo": _titulo(s, p),
                "resumen": (p.resumen_episodio or "").strip(),
                "desvio": (p.tramo_desvio or "").strip(),
            }
            for p in series_repo.episodios(s, serie_id)
        ]
    # Se replanifica solo si hay capítulos Y un hilo del que copiar sus tramos.
    # Una serie con episodios pero sin hilo (las de antes, o una a la que se le
    # escribe el hilo a mitad) planifica de cero: no hay mapa que respetar, y
    # sus capítulos entran como contexto igual porque el prompt los recibe.
    tramos_fijos = (
        hilos_repo.tramos(previo)[:len(rodados)] if (rodados and previo) else []
    )

    sistema = (PROMPTS_DIR / "hilo.md").read_text().replace(
        "{episodios}", _cuantos_episodios(pedidos, len(tramos_fijos), previo)
    )
    pl = plantillas_repo.cargar(plantilla)
    user = (
        f"Serie: «{nombre}»\n"
        f"Tipo de serie: {pl.get('descripcion') or plantilla}\n\n"
        f"Premisa del usuario:\n{premisa}"
    )
    if fijos:
        user = (
            f"{user}\n\nREPARTO FIJO DE LA SERIE. Son sus personajes y no se "
            "tocan: devuélvelos tal cual en `reparto` y escribe los tramos con "
            "ellos.\n"
            + "\n".join(
                f"- {{{x['clave']}}} {x['nombre']}: {x['ficha']}" for x in fijos
            )
        )
    if tramos_fijos:
        user = f"{user}\n\n{_bloque_rodado(rodados[:len(tramos_fijos)], previo)}"
    h = llm.chat(sistema, user, HiloLLM)

    contenido = h.model_dump()
    contenido["tramos"] = tramos_fijos + contenido["tramos"]
    # El reparto NO se guarda en el hilo: se convierte en el reparto fijo de la
    # serie, que es donde vive el reparto de verdad (con su cara, su voz y su
    # viaje a cada episodio). Guardarlo en los dos sitios sería tener dos
    # versiones del mismo personaje esperando a no coincidir.
    propuesto = contenido.pop("reparto", [])
    with get_session() as s:
        fila = hilos_repo.crear(s, serie_id, contenido)
        s.commit()
        version, n = fila.version, len(json.loads(fila.contenido)["tramos"])

    # Fuera de la transacción: escribe filas del reparto propio y abre su
    # sesión, igual que `traer_reparto_fijo` al crear un episodio.
    from ...services import reparto as reparto_service

    fichados = reparto_service.fichar_para_serie(serie_id, propuesto)
    if tramos_fijos:
        return (
            f"Hilo v{version} replanificado: {len(tramos_fijos)} tramos rodados "
            f"intactos y {n - len(tramos_fijos)} por delante"
        )
    quienes = ", ".join(x["clave"] for x in fichados)
    return (
        f"Hilo v{version} escrito, {n} episodios"
        + (f" y {len(fichados)} fichados ({quienes})" if fichados else "")
    )


def contexto_episodio_siguiente(serie_id: int) -> tuple[int, str] | None:
    """Qué número y qué contexto lleva el episodio que viene de esta serie.

    `None` si la serie no tiene hilo, y eso decide de qué manera se le piden las
    ideas: sin hilo se le piden ocho ideas de episodio a ciegas, que es lo que
    se hacía siempre y lo que produce la deriva —ocho capítulos escritos de una
    vez sin saber qué pasó en ninguno—; con hilo se le piden tres maneras del
    **mismo** episodio, el que toca, con su tramo delante.
    """
    with get_session() as s:
        serie = series_repo.obtener(s, serie_id)
        if serie is None:
            return None
        hilo = hilos_repo.contenido(s, serie_id)
        if not hilo:
            return None
        nombre = serie.nombre
        numero = series_repo.siguiente_numero(s, serie_id)
        previo = series_repo.anterior(s, serie_id, numero)
        resumen_previo = (previo.resumen_episodio or "").strip() if previo else ""
        numero_previo = previo.episodio if previo else 0

    partes = [f"Serie: «{nombre}». Vas a proponer el episodio {numero}."]
    if resumen_previo:
        partes.append(
            f"En el episodio anterior ({numero_previo}) pasó esto:\n"
            f"{resumen_previo}"
        )
    elif numero > 1:
        partes.append(
            "El episodio anterior todavía no tiene resumen, así que no des por "
            "hecho nada de lo que pasó en él más allá de su tramo."
        )
    partes.append(_bloque_hilo(hilo, numero))
    return numero, "\n\n".join(partes)
