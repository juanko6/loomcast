"""Álbum de música: mismo sonido, distinta intención en cada pista.

Tres etapas, las dos primeras con el LLM y en jobs seguidos para no cargar el
llama-server dos veces:
  1. planificar_album — el ADN (género, banda, firma de producción) y el
     tracklist: por pista, su intención, papel, lead, forma, tempo y tonalidad.
     Crea las filas `Musica` del álbum.
  2. escribir_album — el brief de cada pista con el prompt de instrumental de
     siempre, más la intención de esa pista y las reglas del álbum. El guion
     viene medido en compases y de él sale la duración. La firma de producción
     se pega literal al final de cada descripción.
  Entre la 2 y la síntesis el usuario revisa el álbum y lo lanza.
  3. generar_portada_album — una portada para todo el disco, tras la última
     pista.

La síntesis de cada pista es el `generar_musica` de siempre, con la semilla del
álbum: la variación entre pistas sale de la intención, nunca del azar.
"""
import random
import re
import shutil

from ...clients import comfy, llm
from ...config import MUSICA_DIR, MUSICA_PORTADA_PX
from ...db import get_session
from ...repositories import albumes as albumes_repo
from ...repositories import musica as musica_repo
from ...repositories import proyectos as proyectos_repo
from ...schemas import AlbumPlanLLM, MusicaPromptLLM
from .. import musica_compases as compases
from .. import progreso
from ..musica_combos import normalizar_bpm, normalizar_keyscale, normalizar_timesig
from . import musica as musica_pipeline

# Duración que acepta una pista (ver services/musica.py: DUR_MIN, DUR_MAX).
DUR_MIN, DUR_MAX = 5, 600
# Intentos de planificar un álbum cuyo tracklist no pasa las reglas.
INTENTOS_PLAN = 2
# Instrumentos de la base rítmica: nunca llevan la melodía de una pista. Con el
# contrabajo de lead la pista salía en bucle (la 129, 90 % de repetición): tiene
# que llevar el pulso y cantar a la vez, y acaba siendo un walking que gira.
_RITMICOS = re.compile(
    r"\b(?:double bass|upright bass|contrabass|bass(?! clarinet| flute| trombone| saxophone)"
    r"|bajo|contrabajo|drums?|drum kit|percussion|bater[ií]a|percusi[oó]n|cajon|caj[oó]n"
    r"|congas?|bongos?|kick|snare|hi-?hats?|cymbals?)\b",
    re.I,
)
_MELODICOS = re.compile(
    r"\b(?:sax\w*|trumpet|trompeta|trombone|tromb[oó]n|horn|clarinet\w*|flute|flauta"
    r"|guitar\w*|guitarra|piano|rhodes|keys|organ|[oó]rgano|vibraphone|vibes|marimba"
    r"|violin\w*|viol[ií]n|viola|cello|chelo|strings|cuerdas|harp|arpa|harmonica|accordion"
    r"|acorde[oó]n|synth\w*|sintetizador|oboe|bassoon|mandolin|banjo|ukulele|sitar|kalimba"
    r"|bass clarinet|bass flute|melodica)\b",
    re.I,
)


def _lead_ritmico(lead: str) -> bool:
    """El lead nombra solo base rítmica (un diálogo saxo y contrabajo vale)."""
    return bool(_RITMICOS.search(lead or "")) and not _MELODICOS.search(lead or "")


def _fallos_plan(r, desde_pista: bool) -> list[str]:
    # Si la banda no tiene ningún instrumento melódico no hay a quién darle la
    # melodía: no se exige.
    if not any(_MELODICOS.search(b) for b in r.banda):
        return []
    return [
        f"track {i} «{p.titulo}» is led by «{p.lead}», a rhythm-section instrument: "
        "give the melody to a melodic member of the band and keep that one for a "
        "short featured moment inside the track"
        for i, p in enumerate(r.pistas, start=1)
        if not (i == 1 and desde_pista) and _lead_ritmico(p.lead)
    ]


# Intentos de escribir una pista cuyo guion no pasa las reglas. Cada intento le
# cuenta al LLM qué falló: repetir la misma petición daría el mismo texto.
INTENTOS_PISTA = 3


def carpeta(album_id: int):
    return MUSICA_DIR / "albumes" / str(album_id)


def ruta_portada(album_id: int):
    p = carpeta(album_id) / "portada.png"
    return p if p.exists() else None


# ---------------------------------------------------------------------------
# 1. Plan
# ---------------------------------------------------------------------------

def _mensaje_plan(a, origen, usados: tuple[list[str], list[str]] = ([], [])) -> str:
    return _mensaje_origen(a, origen) + _no_repetir(*usados)


def _no_repetir(discos: list[str], temas: list[str]) -> str:
    if not discos and not temas:
        return ""
    out = "\n\nThese titles already exist in the user's library. Do NOT reuse any of them, nor a near copy:"
    if discos:
        out += "\nAlbums: " + "; ".join(sorted(set(discos)))
    if temas:
        out += "\nTracks: " + "; ".join(sorted(set(temas)))
    return out


def _titulo_libre(titulo: str, discos: list[str]) -> str:
    """Si aun así repite el título de otro álbum, se numera: dos discos con el
    mismo nombre no se distinguen en la lista."""
    usados = {d.strip().lower() for d in discos}
    if titulo.lower() not in usados:
        return titulo
    n = 2
    while f"{titulo} {n}".lower() in usados:
        n += 1
    return f"{titulo} {n}"


def _titulos_repetidos(r, temas: list[str], desde_pista: bool) -> list[str]:
    usados = {x.strip().lower() for x in temas}
    return [
        p.titulo.strip() for i, p in enumerate(r.pistas, start=1)
        if not (i == 1 and desde_pista) and p.titulo.strip().lower() in usados
    ]


def _mensaje_origen(a, origen) -> str:
    if origen is not None:
        return (
            "FROM A TRACK. This is track 1 of the album, the one the user loved.\n\n"
            f"Its description:\n{origen.tags or ''}\n\n"
            f"Its section skeleton:\n{origen.lyrics or '(none)'}\n\n"
            f"Tempo {origen.bpm} bpm, key {origen.keyscale}, time signature "
            f"{origen.timesig}.\n"
            f"What the user asked for it: {origen.idea}\n\n"
            f"Plan an album of {a.num_pistas} tracks in total, this one included "
            "as the first entry."
        )
    return (
        f"FROM AN IDEA.\n{a.idea}\n\n"
        f"Plan an album of {a.num_pistas} tracks."
    )


def planificar_album(album_id: int) -> str:
    with get_session() as s:
        a = albumes_repo.obtener(s, album_id)
        if a is None:
            raise ValueError(f"Álbum {album_id} no existe")
        origen = (
            musica_repo.obtener(s, a.origen_musica_id) if a.origen_musica_id else None
        )
        usados = albumes_repo.titulos_usados(s, album_id)
        mensaje = _mensaje_plan(a, origen, usados)
        n = a.num_pistas

    sistema = musica_pipeline.leer_prompt("musica_album.md")
    desde_pista = origen is not None
    pedido = mensaje
    for _ in range(INTENTOS_PLAN):
        r = llm.chat(sistema, pedido, AlbumPlanLLM)
        fallos = _fallos_plan(r, desde_pista)
        repetidos = _titulos_repetidos(r, usados[1], desde_pista)
        if not fallos and not repetidos:
            break
        avisos = fallos + [
            f"the track title «{t}» already exists in the library: invent a new one"
            for t in repetidos
        ]
        pedido = (
            f"{mensaje}\n\nYour previous plan was rejected:\n- " + "\n- ".join(avisos)
            + "\nPlan the album again following the rules."
        )
    # Que la melodía la lleve la base rítmica sí tumba el plan; un título
    # repetido no: se numera abajo.
    if fallos:
        raise ValueError("El plan del álbum da la melodía a la base rítmica: " + "; ".join(fallos))
    # Menos pistas de las pedidas no se rellena en silencio: el usuario pidió un
    # número y un álbum cojo se nota tarde.
    if len(r.pistas) < n:
        raise ValueError(
            f"El LLM planificó {len(r.pistas)} pistas y se pidieron {n}"
        )
    plan = r.pistas[:n]

    with get_session() as s:
        a = albumes_repo.obtener(s, album_id)
        a.titulo = _titulo_libre(r.titulo.strip(), usados[0])
        a.genero = r.genero.strip()
        a.banda = "\n".join(b.strip() for b in r.banda if b.strip())
        a.firma = r.firma.strip()
        a.arco = r.arco.strip()
        a.portada = r.portada.strip() or None
        # Replanificar tira las pistas nuevas que hubiera (nunca la de origen).
        for m in albumes_repo.pistas(s, album_id):
            if m.id != a.origen_musica_id:
                proyectos_repo.desvincular_musica(s, m.id)
                musica_repo.borrar(s, m)
        for i, p in enumerate(plan, start=1):
            if i == 1 and a.origen_musica_id:
                m = musica_repo.obtener(s, a.origen_musica_id)
                # La de origen conserva su tempo, tonalidad y audio: ya existe.
                m.album_id, m.pista_n = album_id, 1
                m.titulo = p.titulo.strip()
                m.intencion = _intencion(p)
                continue
            m = musica_repo.crear(
                s, "instrumental", p.titulo.strip(), None, None, 30,
                normalizar_bpm(p.bpm), normalizar_keyscale(p.keyscale),
                normalizar_timesig(p.timesig), "en",
            )
            m.album_id, m.pista_n = album_id, i
            m.titulo = _titulo_libre(p.titulo.strip(), usados[1])
            m.intencion = _intencion(p)
            m.seed = a.seed
        a.estado = "planificando"
        s.commit()
    return f"Álbum planificado: {len(plan)} pistas"


def _intencion(p) -> str:
    """La ficha de la pista en texto, que es lo que el usuario edita en la
    revisión y lo que lee el LLM al escribir el brief."""
    partes = [p.intencion.strip()]
    if p.papel:
        partes.append(f"Papel: {p.papel.strip()}")
    if p.lead:
        partes.append(f"Lead: {p.lead.strip()}")
    if p.forma:
        partes.append(f"Forma: {p.forma.strip()}")
    partes.append(f"Energía: {max(1, min(5, p.energia))}/5")
    return "\n".join(partes)


# ---------------------------------------------------------------------------
# 2. Briefs
# ---------------------------------------------------------------------------

def _mensaje_pista(a, m, total: int) -> str:
    banda = "; ".join(b for b in a.banda.splitlines() if b.strip())
    return (
        "ALBUM TRACK. This track belongs to an album: follow ALBUM TRACKS.\n\n"
        f"Album genre: {a.genero}\n"
        f"The band (the only instruments allowed): {banda}\n"
        f"The album's journey: {a.arco}\n\n"
        f"Track {m.pista_n} of {total}: {m.titulo}\n"
        f"Intention (may be in Spanish):\n{m.intencion}\n\n"
        f"Fixed: {m.bpm} bpm, key {m.keyscale}, time signature {m.timesig}.\n"
        "The bass and the drums keep time and never carry the melody: give them "
        "at most one short featured moment (a bass solo, a drum break, a bass "
        "phrase answering the lead), in one section.\n"
        "Duration: yours to choose. Write the bars this intention needs, "
        "no more and no less, and compose its ending.\n\n"
        # Sin esto el LLM cumple las reglas del brief suelto (agudos, estéreo,
        # producción) y las escribe otra vez con sus palabras, que acaban
        # contradiciendo la firma: en la primera prueba real puso la guitarra
        # en el centro y la firma pone ahí el saxo.
        "Do NOT write anything about the mix, panning, stereo image, top end, "
        "recording, microphones, room or production in your paragraph: this "
        "album's fixed signature is appended right after it and already covers "
        f"all of that:\n{a.firma}"
    )


def _escribir_pista(a, m, total: int) -> tuple[str, str, int]:
    """(tags, lyrics, duracion_s) de una pista. Lanza ValueError si el guion
    no pasa las reglas tras `INTENTOS_PISTA` intentos."""
    sistema = musica_pipeline.leer_prompt("musica_instrumental.md")
    base = _mensaje_pista(a, m, total)
    mensaje = base
    for _ in range(INTENTOS_PISTA):
        r = llm.chat(sistema, mensaje, MusicaPromptLLM)
        fallos = compases.problemas(r.lyrics, m.bpm, m.timesig)
        if not fallos:
            break
        mensaje = (
            f"{base}\n\nYour previous section skeleton was rejected:\n- "
            + "\n- ".join(fallos)
            + "\nWrite it again following THE SECTION SKELETON."
        )
    else:
        raise ValueError(
            f"La pista {m.pista_n} «{m.titulo}» no dio un guion válido: "
            + "; ".join(fallos)
        )
    tags = f"{r.tags.strip()} {a.firma.strip()}".strip()
    dur = compases.duracion_desde_guion(r.lyrics, m.bpm, m.timesig)
    return tags, r.lyrics.strip(), max(DUR_MIN, min(DUR_MAX, dur))


def escribir_album(album_id: int) -> str:
    """El brief de cada pista que aún no lo tiene. Es reanudable: si falla a
    mitad, el reintento sigue por donde iba."""
    with get_session() as s:
        a = albumes_repo.obtener(s, album_id)
        if a is None:
            raise ValueError(f"Álbum {album_id} no existe")
        todas = albumes_repo.pistas(s, album_id)
        total = len(todas)
        pendientes = [m.id for m in todas if not m.tags and m.id != a.origen_musica_id]

    for i, mid in enumerate(pendientes):
        progreso.lote(i, len(pendientes), "pista")
        _escribir_y_guardar(album_id, mid, total)
    progreso.lote(len(pendientes), len(pendientes), "pista")

    with get_session() as s:
        a = albumes_repo.obtener(s, album_id)
        a.estado = "revision"
        s.commit()
    return f"Briefs escritos: {len(pendientes)} pistas"


def _escribir_y_guardar(album_id: int, musica_id: int, total: int) -> None:
    with get_session() as s:
        a = albumes_repo.obtener(s, album_id)
        m = musica_repo.obtener(s, musica_id)
        tags, lyrics, dur = _escribir_pista(a, m, total)
        musica_repo.guardar_campos(s, m, tags, lyrics, dur)
        s.commit()


def escribir_pista_album(musica_id: int) -> str:
    """Reescribe el brief de una sola pista, tras editar su intención."""
    with get_session() as s:
        m = musica_repo.obtener(s, musica_id)
        if m is None or m.album_id is None:
            raise ValueError(f"La pista {musica_id} no es de un álbum")
        album_id = m.album_id
        total = len(albumes_repo.pistas(s, album_id))
    _escribir_y_guardar(album_id, musica_id, total)
    return "Brief de la pista reescrito"


# ---------------------------------------------------------------------------
# 3. Portada
# ---------------------------------------------------------------------------

def generar_portada_album(album_id: int) -> str:
    """Una portada para todo el disco, copiada a cada pista para que la lista,
    el player y la biblioteca la enseñen sin saber nada de álbumes."""
    with get_session() as s:
        a = albumes_repo.obtener(s, album_id)
        if a is None:
            raise ValueError(f"Álbum {album_id} no existe")
        prompt = a.portada
        ids = [m.id for m in albumes_repo.pistas(s, album_id)]
    if not prompt:
        return "Sin prompt de portada: nada que generar"

    car = carpeta(album_id)
    car.mkdir(parents=True, exist_ok=True)
    try:
        comfy.generar_imagen(
            prompt, random.randint(0, 2**31 - 1), car / "portada.png",
            MUSICA_PORTADA_PX, MUSICA_PORTADA_PX,
        )
    finally:
        comfy.liberar_memoria()
    for mid in ids:
        destino = musica_pipeline.carpeta(mid)
        destino.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(car / "portada.png", destino / "portada.png")
    return f"Portada del álbum generada y puesta en {len(ids)} pistas"
