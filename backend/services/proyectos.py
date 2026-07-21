"""Lógica de negocio de proyectos: detalle, edición de guion, estados."""
import json

from ..config import PROYECTOS_DIR
from ..db import get_session
from ..models import avanzar_estado
from ..repositories import escenas as escenas_repo
from ..repositories import guiones as guiones_repo
from ..repositories import ideas as ideas_repo
from ..repositories import jobs as jobs_repo
from ..repositories import metadatos as metadatos_repo
from ..repositories import proyectos as proyectos_repo
from ..repositories import voces as voces_repo
from ..workers import queue

TIPOS_JOB_PROYECTO = [
    "generar_guion", "generar_metadatos", "generar_voz", "generar_subtitulos",
    "generar_escenas", "generar_imagenes", "generar_upscale", "generar_clips",
    "generar_i2v", "armar_video", "armar_estatico",
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
        escenas = [
            {
                "orden": e.orden, "t_inicio": e.t_inicio, "t_fin": e.t_fin,
                "texto": e.texto, "prompt": e.prompt,
                "imagen": (base_dir / "imagenes" / f"{e.orden:02d}.png").exists(),
            }
            for e in escenas_repo.por_proyecto(s, pid)
        ]
        todas_imagenes = bool(escenas) and all(e["imagen"] for e in escenas)
        return {
            "id": p.id, "slug": p.slug, "estado": p.estado,
            "plantilla": p.plantilla, "voz": p.voz,
            "idea": {"titulo": idea.titulo, "gancho": idea.gancho,
                     "resumen": idea.resumen} if idea else None,
            "guion": json.loads(guion.contenido) if guion else None,
            "guion_version": guion.version if guion else 0,
            "metadatos": json.loads(meta.contenido) if meta else None,
            "voz_disponible": (base_dir / "voz.mp3").exists(),
            "subtitulos": srt.read_text() if srt.exists() else None,
            "escenas": escenas,
            "imagenes_completas": todas_imagenes,
            "video_disponible": (base_dir / "final.mp4").exists(),
            "jobs_activos": activos,
            "job_activo": job_activo,
        }


def editar_guion(pid: int, contenido: dict) -> int:
    with get_session() as s:
        p = proyectos_repo.obtener(s, pid)
        if p is None:
            raise ProyectoNoExiste(pid)
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


def editar_prompts_escenas(pid: int, prompts: dict[int, str]) -> int:
    with get_session() as s:
        p = proyectos_repo.obtener(s, pid)
        if p is None:
            raise ProyectoNoExiste(pid)
        n = escenas_repo.actualizar_prompts(s, pid, prompts)
        s.commit()
        return n


def ruta_archivo(pid: int, *partes: str):
    with get_session() as s:
        p = proyectos_repo.obtener(s, pid)
        if p is None:
            raise ProyectoNoExiste(pid)
        return PROYECTOS_DIR.joinpath(p.slug, *partes)


def encolar_etapa(pid: int, tipo: str) -> int:
    return queue.encolar(tipo, pid)


# Modo de video → job con el que arranca. El estático es un solo job; el de
# movimiento (Ken Burns) es una cadena upscale → clips → armado.
MODOS_VIDEO = {
    "estatico": "armar_estatico",
    "kenburns": "generar_upscale",
    "i2v": "generar_i2v",
}


class ModoVideoInvalido(ValueError):
    pass


def generar_video(pid: int, modo: str) -> int:
    if modo not in MODOS_VIDEO:
        raise ModoVideoInvalido(modo)
    return queue.encolar(MODOS_VIDEO[modo], pid)
