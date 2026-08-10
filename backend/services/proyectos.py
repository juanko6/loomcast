"""Lógica de negocio de proyectos: detalle, edición de guion, estados."""
import json
import shutil
from datetime import datetime

from ..config import PROYECTOS_DIR
from ..db import get_session
from ..models import avanzar_estado
from ..repositories import escenas as escenas_repo
from ..repositories import guiones as guiones_repo
from ..repositories import ideas as ideas_repo
from ..repositories import jobs as jobs_repo
from ..repositories import metadatos as metadatos_repo
from ..repositories import personajes as personajes_repo
from ..repositories import plantillas as plantillas_repo
from ..repositories import proyectos as proyectos_repo
from ..repositories import voces as voces_repo
from ..workers import queue

TIPOS_JOB_PROYECTO = [
    "generar_guion", "generar_metadatos", "generar_voz", "generar_subtitulos",
    "generar_casting",
    "generar_escenas", "generar_imagenes", "generar_upscale", "generar_clips",
    "generar_i2v", "armar_video", "armar_estatico",
    "regenerar_imagen", "regenerar_clip", "generar_clips_mixto",
]

# El estado del proyecto NO retrocede, pero editar escenas invalida imágenes
# ya generadas; la UI lo maneja mostrando el botón de regenerar imágenes.


class ProyectoNoExiste(LookupError):
    pass


class VozNoDisponible(ValueError):
    pass


def listar() -> list[dict]:
    with get_session() as s:
        out = []
        for p in proyectos_repo.listar(s):
            idea = ideas_repo.obtener(s, p.idea_id)
            out.append({
                "id": p.id, "slug": p.slug, "estado": p.estado,
                "plantilla": p.plantilla, "titulo": idea.titulo if idea else "",
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
        escenas = [_escena_dict(e, base_dir, en_cola)
                   for e in escenas_repo.por_proyecto(s, pid)]
        personajes = [
            {"clave": x.clave, "nombre": x.nombre, "ficha": x.ficha}
            for x in personajes_repo.por_proyecto(s, pid)
        ]
        todas_imagenes = bool(escenas) and all(e["imagen"] for e in escenas)
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
            "idea": {"titulo": idea.titulo, "gancho": idea.gancho,
                     "resumen": idea.resumen} if idea else None,
            "guion": guion_dict,
            "guion_version": guion.version if guion else 0,
            "metadatos": json.loads(meta.contenido) if meta else None,
            "voz_disponible": (base_dir / "voz.mp3").exists(),
            "subtitulos": srt.read_text() if srt.exists() else None,
            "escenas": escenas,
            "personajes": personajes,
            "imagenes_completas": todas_imagenes,
            "video_disponible": (base_dir / "final.mp4").exists(),
            "versiones": _versiones(base_dir),
            "jobs_activos": activos,
            "job_activo": job_activo,
        }


def editar_guion(pid: int, contenido: dict) -> int:
    with get_session() as s:
        p = proyectos_repo.obtener(s, pid)
        if p is None:
            raise ProyectoNoExiste(pid)
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


def seleccionar_voz(pid: int, voz_slug: str) -> None:
    with get_session() as s:
        p = proyectos_repo.obtener(s, pid)
        if p is None:
            raise ProyectoNoExiste(pid)
        if voces_repo.por_slug(s, voz_slug) is None:
            raise VozNoDisponible(voz_slug)
        p.voz = voz_slug
        s.commit()


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


# Modo de video → job con el que arranca. El estático es un solo job; el de
# movimiento (Ken Burns) es una cadena upscale → clips → armado.
MODOS_VIDEO = {
    "estatico": "armar_estatico",
    "kenburns": "generar_upscale",
    "i2v": "generar_i2v",
    # Respeta el modo elegido en cada escena: el video puede mezclarlos.
    "mixto": "generar_clips_mixto",
}


class ModoVideoInvalido(ValueError):
    pass


def generar_video(pid: int, modo: str) -> int:
    if modo not in MODOS_VIDEO:
        raise ModoVideoInvalido(modo)
    return queue.encolar(MODOS_VIDEO[modo], pid)
