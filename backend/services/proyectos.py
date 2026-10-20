"""Lógica de negocio de proyectos: detalle, edición de guion, estados."""
import json
import random
import shutil
from datetime import datetime

from ..config import I2V_MOTOR, I2V_MOTORES, PROYECTOS_DIR
from ..db import get_session
from ..models import avanzar_estado
from ..repositories import escenas as escenas_repo
from ..repositories import guiones as guiones_repo
from ..repositories import ideas as ideas_repo
from ..repositories import jobs as jobs_repo
from ..repositories import metadatos as metadatos_repo
from ..repositories import musica as musica_repo
from ..repositories import personajes as personajes_repo
from ..repositories import plantillas as plantillas_repo
from ..repositories import proyectos as proyectos_repo
from ..repositories import series as series_repo
from ..repositories import voces as voces_repo
from ..repositories import autopilotos as autopilotos_repo
from ..services import autopiloto as autopiloto_service
from ..services import voces as voces_service
from ..services.pipeline import casting
from ..services.pipeline import escenas as escenas_pipeline
from ..services.pipeline import musica as musica_pipeline
from ..services.pipeline import retratos
from ..workers import queue

TIPOS_JOB_PROYECTO = [
    "generar_guion", "generar_metadatos", "generar_voz", "generar_subtitulos",
    "generar_casting", "generar_retrato",
    "generar_escenas", "generar_imagenes", "generar_upscale", "generar_clips",
    "generar_i2v", "armar_video", "armar_estatico",
    "regenerar_imagen", "regenerar_clip", "generar_clips_mixto",
    "generar_musica_proyecto", "generar_resumen_episodio",
]

# Jobs de la cola que trabajan sobre una pista de música (su ref_id es el id de
# la pista, no del proyecto): lo que hace falta para saber si la música del
# proyecto está en marcha.
TIPOS_JOB_MUSICA = [
    "generar_musica_proyecto", "generar_musica", "generar_portada_musica",
    "mejorar_prompt_musica",
]

# El estado del proyecto NO retrocede, pero editar escenas invalida imágenes
# ya generadas; la UI lo maneja mostrando el botón de regenerar imágenes.


class ProyectoNoExiste(LookupError):
    pass


class VozNoDisponible(ValueError):
    pass


class PersonajeNoExiste(LookupError):
    pass


class MusicaNoExiste(LookupError):
    pass


class SinFicha(ValueError):
    pass


def listar() -> list[dict]:
    with get_session() as s:
        out = []
        for p in proyectos_repo.listar(s):
            idea = ideas_repo.obtener(s, p.idea_id)
            serie = series_repo.obtener(s, p.serie_id) if p.serie_id else None
            auto = autopilotos_repo.vivo_de_proyecto(s, p.id)
            out.append({
                "id": p.id, "slug": p.slug, "estado": p.estado,
                "plantilla": p.plantilla, "titulo": idea.titulo if idea else "",
                # Estado de su autopiloto si tiene uno en marcha (corriendo,
                # esperando una revisión o esperando turno en su lote), o None.
                # El listado es desde donde se ve que de diez vídeos tres están
                # esperando que alguien lea su guion.
                "autopiloto": auto.estado if auto else None,
                # Nombre de la serie y número de episodio, o None: el listado
                # distingue un episodio de un vídeo suelto de un vistazo.
                "serie": serie.nombre if serie else None,
                "episodio": p.episodio,
            })
        return out


def _escena_dict(e, base_dir, en_cola=None) -> dict:
    img = base_dir / "imagenes" / f"{e.orden:02d}.png"
    clip = base_dir / "clips" / f"{e.orden:02d}.mp4"
    tiene_img, tiene_clip = img.exists(), clip.exists()
    return {
        "orden": e.orden, "t_inicio": e.t_inicio, "t_fin": e.t_fin,
        "texto": e.texto, "prompt": e.prompt,
        "prompt_movimiento": e.prompt_movimiento or "",
        "imagen": tiene_img,
        "clip": tiene_clip,
        "modo": e.modo or "",
        "clip_modo": e.clip_modo or "",
        # Quién sale en la escena: si tienen retrato, es la que se generará a
        # partir de sus caras en vez de solo desde el texto.
        "personajes": [c for c in (e.personajes or "").split(",") if c],
        "imagen_s": e.imagen_s or 0,
        "clip_s": e.clip_s or 0,
        # El clip se hizo con la imagen anterior si esta se regeneró después.
        # Se deduce de las fechas de los archivos, sin marcas que mantener.
        "clip_viejo": (
            tiene_img and tiene_clip
            and img.stat().st_mtime > clip.stat().st_mtime
        ),
        # 'imagen' | 'clip' si esta escena tiene una regeneración esperando en
        # la cola; None si no.
        "en_cola": (en_cola or {}).get(e.orden),
    }


def _serie_dict(s, p) -> dict | None:
    """De qué serie es episodio este proyecto, o None si es un vídeo suelto.

    Lleva el número del episodio anterior y su resumen porque es lo que el
    usuario necesita ver al escribir este: es el contexto que el LLM ya está
    usando, y si está mal es ahí donde se corrige.
    """
    if p.serie_id is None:
        return None
    serie = series_repo.obtener(s, p.serie_id)
    if serie is None:
        return None
    previo = series_repo.anterior(s, p.serie_id, p.episodio)
    return {
        "id": serie.id,
        "nombre": serie.nombre,
        "slug": serie.slug,
        "episodio": p.episodio,
        "anterior": (
            {"episodio": previo.episodio,
             "resumen": (previo.resumen_episodio or "").strip()}
            if previo else None
        ),
    }


def _musica_dict(s, p) -> dict | None:
    """La pista del proyecto, tal como la ve el paso de Música.

    Es una fila de `musicas` como cualquier otra de la biblioteca: lo que la
    hace del proyecto es que este la apunte. Por eso aquí no se duplica nada,
    se lee de allí.
    """
    if p.musica_id is None:
        return None
    m = musica_repo.obtener(s, p.musica_id)
    if m is None:
        # La pista se borró desde la sección de Música; el proyecto se queda
        # sin ella en la siguiente escritura (ver desvincular_musica).
        return None
    ocupado = any(
        j.ref_id == m.id and j.tipo in TIPOS_JOB_MUSICA
        for j in jobs_repo.activos(s)
    )
    return {
        "id": m.id,
        "idea": m.idea,
        "tags": m.tags,
        "lyrics": m.lyrics,
        "duracion_s": m.duracion_s,
        "bpm": m.bpm,
        "keyscale": m.keyscale,
        "estado": m.estado,
        "tiene_audio": musica_pipeline.ruta_audio(m.id) is not None,
        "tiene_portada": musica_pipeline.ruta_portada(m.id) is not None,
        "ocupado": ocupado,
    }


def detalle(pid: int) -> dict:
    with get_session() as s:
        p = proyectos_repo.obtener(s, pid)
        if p is None:
            raise ProyectoNoExiste(pid)
        idea = ideas_repo.obtener(s, p.idea_id)
        guion = guiones_repo.ultimo(s, pid)
        meta = metadatos_repo.ultimo(s, pid)
        activos = jobs_repo.activos_de_proyecto(s, pid, TIPOS_JOB_PROYECTO)
        job_activo = jobs_repo.tipo_activo_de_proyecto(s, pid, TIPOS_JOB_PROYECTO)
        base_dir = PROYECTOS_DIR / p.slug
        srt = base_dir / "subtitulos.srt"
        en_cola = jobs_repo.escenas_en_cola(s, pid)
        ultimo_auto = autopilotos_repo.ultimo_de_proyecto(s, pid)
        escenas = [_escena_dict(e, base_dir, en_cola)
                   for e in escenas_repo.por_proyecto(s, pid)]
        personajes = [
            {
                "clave": x.clave,
                "nombre": x.nombre,
                "ficha": x.ficha,
                "tipo": x.tipo or "persona",
                # Slug del miembro del reparto propio del que se trajo ("" si
                # nació aquí): la UI ofrece actualizarlo allí en vez de volver a
                # promoverlo, y avisa de que esa cara sobrevive al regenerar.
                "reparto_slug": x.reparto_slug or "",
                # Slug de la voz del banco con la que dice sus líneas ("" = sus
                # líneas las narra la voz del proyecto). El estado de esa voz lo
                # resuelve la UI contra /api/voces, que ya tiene.
                "voz": x.voz or "",
                "retrato": retratos.ruta_retrato(p.slug, x.clave).exists(),
            }
            for x in personajes_repo.por_proyecto(s, pid)
        ]
        todas_imagenes = bool(escenas) and all(e["imagen"] for e in escenas)
        voz_mp3 = base_dir / "voz.mp3"
        guion_dict = json.loads(guion.contenido) if guion else None
        # Instruct por defecto del modo expresivo: el que sugirió el guion para
        # esta historia y, si no lo hay, el de la plantilla.
        voz_instruct = (guion_dict or {}).get("voz_instruct") or ""
        if not voz_instruct:
            try:
                voz_instruct = plantillas_repo.cargar(p.plantilla)["voz"]["instruct"]
            except Exception:
                voz_instruct = ""
        return {
            "id": p.id, "slug": p.slug, "estado": p.estado,
            "plantilla": p.plantilla, "voz": p.voz, "voz_instruct": voz_instruct,
            # None = vídeo suelto. Con serie, la UI dice de qué episodio se
            # trata y abre el paso de cerrarlo.
            "serie": _serie_dict(s, p),
            "resumen_episodio": p.resumen_episodio or "",
            "idea": {"titulo": idea.titulo, "gancho": idea.gancho,
                     "resumen": idea.resumen} if idea else None,
            "guion": guion_dict,
            "guion_version": guion.version if guion else 0,
            "metadatos": json.loads(meta.contenido) if meta else None,
            "voz_disponible": voz_mp3.exists(),
            # mtime del mp3: version real del archivo para que el player de la
            # UI re-descargue tras cada regeneración (el bust por guion_version
            # no cambiaba al regenerar solo la voz y el navegador se quedaba
            # con la narración antigua en caché).
            "voz_version": int(voz_mp3.stat().st_mtime) if voz_mp3.exists() else 0,
            "subtitulos": srt.read_text() if srt.exists() else None,
            "escenas": escenas,
            "personajes": personajes,
            "imagenes_completas": todas_imagenes,
            "musica": _musica_dict(s, p),
            "musica_mezclar": p.musica_mezclar,
            "video_disponible": (base_dir / "final.mp4").exists(),
            "versiones": _versiones(base_dir),
            "jobs_activos": activos,
            "job_activo": job_activo,
            # Su última tirada automática (o None si nunca tuvo una). Va la
            # última y no solo la viva porque cómo acabó la anterior —un fallo,
            # una parada— es justo lo que hay que leer antes de relanzarla.
            "autopiloto": (
                autopiloto_service.a_dict(ultimo_auto) if ultimo_auto else None
            ),
        }


def editar_guion(pid: int, contenido: dict) -> int:
    with get_session() as s:
        p = proyectos_repo.obtener(s, pid)
        if p is None:
            raise ProyectoNoExiste(pid)
        # Las claves de las líneas atribuidas se normalizan como las del
        # reparto: lo que se teclea en el editor tiene que casar con la clave
        # del personaje o la línea se quedaría sin su voz.
        contenido = guiones_repo.normalizar_lineas(contenido)
        # El editor de la UI manda gancho/narración/cta (o frases), sin
        # voz_instruct; conserva el que sugirió el guion para no perderlo.
        if not contenido.get("voz_instruct"):
            previo = guiones_repo.ultimo(s, pid)
            heredado = json.loads(previo.contenido).get("voz_instruct") if previo else None
            if heredado:
                contenido = {**contenido, "voz_instruct": heredado}
        g = guiones_repo.crear(s, pid, contenido)
        avanzar_estado(p, "GUION")
        s.commit()
        return g.version


class NoEsEpisodio(ValueError):
    pass


def editar_resumen_episodio(pid: int, texto: str) -> str:
    """Corrige a mano en qué quedó el episodio.

    El resumen lo escribe el LLM al cerrar el episodio, pero es lo que el guion
    del siguiente va a dar por cierto: si se queda sin revisar, un detalle
    inventado se vuelve canon de la serie. Por eso se edita como el guion.
    """
    with get_session() as s:
        p = proyectos_repo.obtener(s, pid)
        if p is None:
            raise ProyectoNoExiste(pid)
        if p.serie_id is None:
            raise NoEsEpisodio(pid)
        p.resumen_episodio = texto.strip()
        s.commit()
        return p.resumen_episodio


def seleccionar_voz(pid: int, voz_slug: str) -> None:
    with get_session() as s:
        p = proyectos_repo.obtener(s, pid)
        if p is None:
            raise ProyectoNoExiste(pid)
        if voces_repo.por_slug(s, voz_slug) is None:
            raise VozNoDisponible(voz_slug)
        p.voz = voz_slug
        s.commit()


class VozPersonajeNoDisponible(ValueError):
    pass


def _personaje(s, pid: int, clave: str):
    p = proyectos_repo.obtener(s, pid)
    if p is None:
        raise ProyectoNoExiste(pid)
    x = next(
        (x for x in personajes_repo.por_proyecto(s, pid) if x.clave == clave), None
    )
    if x is None:
        raise PersonajeNoExiste(clave)
    return p, x


def asignar_voz_personaje(pid: int, clave: str, voz_slug: str) -> None:
    """Elige con qué voz del banco dice sus líneas un personaje del reparto.

    Vacío lo deja sin voz propia: sus líneas las narra la voz del proyecto, que
    es lo que pasaba antes de que esto existiera.
    """
    with get_session() as s:
        _, personaje = _personaje(s, pid, clave)
        if voz_slug and voces_repo.por_slug(s, voz_slug) is None:
            raise VozPersonajeNoDisponible(voz_slug)
        personaje.voz = voz_slug
        s.commit()


def generar_voz_personaje(pid: int, clave: str) -> dict:
    """Le crea una voz en el banco desde su propia ficha y se la asigna.

    La ficha es de donde ya sale su retrato, así que es de donde sale también su
    voz: dice la edad aparente, el género y el aire del personaje, que es lo que
    decide el timbre. La voz nace en el banco como cualquier otra —se escucha,
    se reutiliza y se borra desde el mismo sitio—, y queda asignada en cuanto se
    encola, de modo que la UI dice ya de quién es aunque todavía se esté
    sintetizando.
    """
    with get_session() as s:
        _, personaje = _personaje(s, pid, clave)
        if not (personaje.ficha or "").strip():
            raise SinFicha(clave)
        nombre = (personaje.nombre or clave).strip()
        instruct = voces_service.instruct_desde_ficha(
            nombre, personaje.ficha, personaje.tipo or "persona"
        )

    creada = voces_service.crear_para_personaje(nombre, instruct)

    with get_session() as s:
        _, personaje = _personaje(s, pid, clave)
        personaje.voz = creada["slug"]
        s.commit()
    return creada


def fijar_musica(pid: int, musica_id: int | None, mezclar: bool) -> None:
    """Engancha una pista al proyecto y decide si el armado la mezcla.

    Sirve para las dos cosas que el usuario puede querer: reutilizar una pista
    que ya está en la biblioteca, y activar o desactivar la mezcla sin tocar la
    pista. Sin pista no hay mezcla que activar.
    """
    with get_session() as s:
        p = proyectos_repo.obtener(s, pid)
        if p is None:
            raise ProyectoNoExiste(pid)
        if musica_id is not None and musica_repo.obtener(s, musica_id) is None:
            raise MusicaNoExiste(musica_id)
        p.musica_id = musica_id
        p.musica_mezclar = bool(mezclar) and musica_id is not None
        s.commit()


def ruta_retrato(pid: int, clave: str):
    """Ruta del retrato de un personaje, validando la clave contra el reparto.

    La clave llega en la URL, así que no puede componer una ruta sin más: se
    comprueba que sea uno de los personajes del proyecto.
    """
    with get_session() as s:
        p = proyectos_repo.obtener(s, pid)
        if p is None:
            raise ProyectoNoExiste(pid)
        if not any(x.clave == clave for x in personajes_repo.por_proyecto(s, pid)):
            raise PersonajeNoExiste(clave)
        return retratos.ruta_retrato(p.slug, clave)


class PersonajeRepetido(ValueError):
    pass


def anadir_personaje(pid: int, clave: str, nombre: str, ficha: str) -> str:
    """Mete un personaje al reparto a mano.

    Hace falta porque el casting se deja gente: alguien que sale en varias
    escenas sin nombre ni diálogo ("el escritor del sótano") puede no entrar, y
    entonces cada escena se lo inventa distinto. Ojo: los prompts ya escritos no
    lo mencionan, así que después hay que regenerarlos o editarlos.
    """
    clave = personajes_repo.normalizar_clave(clave)
    if not clave:
        raise ValueError(
            "La clave solo admite letras, dígitos y guion bajo, y no puede "
            "quedar vacía: es el marcador con el que se le nombra en los prompts."
        )
    with get_session() as s:
        p = proyectos_repo.obtener(s, pid)
        if p is None:
            raise ProyectoNoExiste(pid)
        if personajes_repo.existe(s, pid, clave):
            raise PersonajeRepetido(clave)
        personajes_repo.crear(
            s, pid, clave, nombre.strip(), ficha.strip(),
            random.randint(0, 2**31 - 1),
            # Persona salvo que la ficha diga que ahí no hay nadie: el tipo no
            # se pide por la API, se deduce de lo que se escribe.
            casting.normalizar_tipo("persona", ficha),
        )
        s.commit()
    return clave


def borrar_personaje(pid: int, clave: str) -> None:
    """Saca a alguien del reparto y se lleva su retrato.

    Las escenas que lo tuvieran marcado se quedan con una clave que ya no
    existe; como quién sale se resuelve contra el reparto vivo, esas escenas
    pasan a generarse desde el texto sin más.
    """
    with get_session() as s:
        p = proyectos_repo.obtener(s, pid)
        if p is None:
            raise ProyectoNoExiste(pid)
        if not personajes_repo.existe(s, pid, clave):
            raise PersonajeNoExiste(clave)
        slug = p.slug
        personajes_repo.borrar(s, pid, clave)
        s.commit()
    retrato = retratos.ruta_retrato(slug, clave)
    if retrato.exists():
        retrato.unlink()


def editar_personajes(pid: int, cambios: dict[str, dict]) -> int:
    with get_session() as s:
        p = proyectos_repo.obtener(s, pid)
        if p is None:
            raise ProyectoNoExiste(pid)
        n = personajes_repo.actualizar(s, pid, cambios)
        s.commit()
        return n


def editar_prompts_escenas(pid: int, prompts: dict[int, dict]) -> int:
    with get_session() as s:
        p = proyectos_repo.obtener(s, pid)
        if p is None:
            raise ProyectoNoExiste(pid)
        # Quién sale en cada escena se relee del prompt guardado: si lo editas
        # para meter o quitar a alguien, lo que decidió el LLM al generarlo deja
        # de valer, y de esto depende que la escena use la cara del personaje.
        fichas = personajes_repo.fichas(s, pid)
        if fichas:
            for campos in prompts.values():
                if "prompt" in campos:
                    campos["personajes"] = ",".join(
                        escenas_pipeline.detectar_personajes(campos["prompt"], fichas)
                    )
        n = escenas_repo.actualizar_prompts(s, pid, prompts)
        s.commit()
        return n


def _versiones_dir(slug: str):
    return PROYECTOS_DIR / slug / "versiones"


def _versiones(base_dir) -> list[dict]:
    """Montajes anteriores archivados, del más reciente al más antiguo."""
    d = base_dir / "versiones"
    if not d.exists():
        return []
    out = []
    for f in sorted(d.glob("final_*.mp4"), reverse=True):
        st = f.stat()
        out.append({
            "nombre": f.name,
            "mb": round(st.st_size / 1e6, 1),
            "fecha": datetime.fromtimestamp(st.st_mtime).strftime("%d/%m %H:%M"),
        })
    return out


def _nombre_version_valido(nombre: str) -> bool:
    """Solo nombres del propio archivador: evita que un nombre con '..' o con
    separadores saque el borrado fuera de la carpeta de versiones."""
    return (
        nombre.startswith("final_")
        and nombre.endswith(".mp4")
        and "/" not in nombre
        and "\\" not in nombre
        and ".." not in nombre
    )


def listar_versiones(pid: int) -> list[dict]:
    """Montajes anteriores, del más reciente al más antiguo."""
    with get_session() as s:
        p = proyectos_repo.obtener(s, pid)
        if p is None:
            raise ProyectoNoExiste(pid)
        slug = p.slug
    return _versiones(PROYECTOS_DIR / slug)


class VersionNoExiste(LookupError):
    pass


def borrar_version(pid: int, nombre: str) -> None:
    if not _nombre_version_valido(nombre):
        raise VersionNoExiste(nombre)
    with get_session() as s:
        p = proyectos_repo.obtener(s, pid)
        if p is None:
            raise ProyectoNoExiste(pid)
        slug = p.slug
    f = _versiones_dir(slug) / nombre
    if not f.exists():
        raise VersionNoExiste(nombre)
    f.unlink()


def borrar_video(pid: int, con_versiones: bool = False) -> dict:
    """Borra el video final y, si se pide, también los montajes archivados."""
    with get_session() as s:
        p = proyectos_repo.obtener(s, pid)
        if p is None:
            raise ProyectoNoExiste(pid)
        slug = p.slug
    base = PROYECTOS_DIR / slug
    borrados = 0
    final = base / "final.mp4"
    if final.exists():
        final.unlink()
        borrados += 1
    versiones = 0
    if con_versiones and _versiones_dir(slug).exists():
        for f in _versiones_dir(slug).glob("final_*.mp4"):
            f.unlink()
            versiones += 1
    return {"final": borrados, "versiones": versiones}


def borrar_proyecto(pid: int) -> dict:
    """Borra el proyecto: sus filas en la base y su carpeta en disco."""
    with get_session() as s:
        p = proyectos_repo.obtener(s, pid)
        if p is None:
            raise ProyectoNoExiste(pid)
        slug = p.slug
        activos = jobs_repo.activos_de_proyecto(s, pid, TIPOS_JOB_PROYECTO)
        if activos:
            raise ProyectoOcupado(pid)
        proyectos_repo.borrar(s, pid)
        s.commit()

    carpeta = PROYECTOS_DIR / slug
    archivos = 0
    if carpeta.exists():
        archivos = sum(1 for _ in carpeta.rglob("*") if _.is_file())
        shutil.rmtree(carpeta)
    return {"slug": slug, "archivos": archivos}


class ProyectoOcupado(RuntimeError):
    pass


def ruta_archivo(pid: int, *partes: str):
    with get_session() as s:
        p = proyectos_repo.obtener(s, pid)
        if p is None:
            raise ProyectoNoExiste(pid)
        return PROYECTOS_DIR.joinpath(p.slug, *partes)


def encolar_etapa(pid: int, tipo: str, **params) -> int:
    return queue.encolar(tipo, pid, **params)


def fijar_modo_escenas(pid: int, modos: dict[int, str]) -> int:
    """Guarda con qué modo debe animarse cada escena. `generar_video` lo respeta,
    de modo que un mismo video puede mezclar estático, Ken Burns e i2v."""
    with get_session() as s:
        p = proyectos_repo.obtener(s, pid)
        if p is None:
            raise ProyectoNoExiste(pid)
        n = 0
        for e in escenas_repo.por_proyecto(s, pid):
            if e.orden in modos:
                e.modo = modos[e.orden]
                n += 1
        s.commit()
        return n


class ModoVideoInvalido(ValueError):
    pass


def generar_video(pid: int, modo: str, motor: str = "") -> int:
    if modo not in queue.MODOS_VIDEO:
        raise ModoVideoInvalido(modo)
    # El motor solo llega a los modos que animan con i2v; a los demás les
    # sobraría como kwarg y el handler lo rechazaría.
    extra = {"motor": motor} if motor and modo in ("i2v", "mixto") else {}
    return queue.encolar(queue.MODOS_VIDEO[modo], pid, **extra)


def motores_i2v() -> list[dict]:
    """Motores de [i2v.motores] para el selector de la UI, con el que viene
    preseleccionado marcado."""
    return [
        {"id": m.id, "nombre": m.nombre, "frames": m.frames,
         "fps_origen": m.fps_origen, "defecto": m.id == I2V_MOTOR}
        for m in I2V_MOTORES.values()
    ]
