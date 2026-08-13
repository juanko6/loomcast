from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..schemas import (
    EscenasIn,
    GuionIn,
    ModosEscenasIn,
    PersonajeNuevoIn,
    PersonajesIn,
    RegenerarClipIn,
    RegenerarImagenIn,
    VideoIn,
    VozGenerarIn,
    VozSeleccionIn,
)
from ..services import proyectos as proyectos_service

router = APIRouter(prefix="/api/proyectos", tags=["proyectos"])


@router.get("")
def listar():
    return proyectos_service.listar()


@router.get("/{pid}")
def detalle(pid: int):
    try:
        return proyectos_service.detalle(pid)
    except proyectos_service.ProyectoNoExiste:
        raise HTTPException(404, "Proyecto no existe")


@router.put("/{pid}/guion")
def editar_guion(pid: int, body: GuionIn):
    try:
        return {"version": proyectos_service.editar_guion(pid, body.model_dump())}
    except proyectos_service.ProyectoNoExiste:
        raise HTTPException(404, "Proyecto no existe")


@router.post("/{pid}/guion/regenerar")
def regenerar_guion(pid: int):
    return {"job_id": proyectos_service.encolar_etapa(pid, "generar_guion")}


@router.post("/{pid}/metadatos")
def generar_metadatos(pid: int):
    return {"job_id": proyectos_service.encolar_etapa(pid, "generar_metadatos")}


@router.put("/{pid}/voz")
def seleccionar_voz(pid: int, body: VozSeleccionIn):
    try:
        proyectos_service.seleccionar_voz(pid, body.voz)
        return {"ok": True}
    except proyectos_service.ProyectoNoExiste:
        raise HTTPException(404, "Proyecto no existe")
    except proyectos_service.VozNoDisponible:
        raise HTTPException(400, "Voz no disponible")


@router.post("/{pid}/voz")
def generar_voz(pid: int, body: VozGenerarIn | None = None):
    modo = body.modo if body else "clon"
    instruct = body.instruct if body else None
    return {"job_id": proyectos_service.encolar_etapa(
        pid, "generar_voz", modo=modo, instruct=instruct)}


@router.post("/{pid}/subtitulos")
def regenerar_subtitulos(pid: int):
    return {"job_id": proyectos_service.encolar_etapa(pid, "generar_subtitulos")}


@router.post("/{pid}/casting")
def generar_casting(pid: int):
    return {"job_id": proyectos_service.encolar_etapa(pid, "generar_casting")}


@router.put("/{pid}/casting")
def editar_casting(pid: int, body: PersonajesIn):
    try:
        cambios = {
            x.clave: {"nombre": x.nombre, "ficha": x.ficha} for x in body.personajes
        }
        return {"actualizados": proyectos_service.editar_personajes(pid, cambios)}
    except proyectos_service.ProyectoNoExiste:
        raise HTTPException(404, "Proyecto no existe")


@router.post("/{pid}/personajes")
def anadir_personaje(pid: int, body: PersonajeNuevoIn):
    try:
        clave = proyectos_service.anadir_personaje(
            pid, body.clave, body.nombre, body.ficha
        )
        return {"clave": clave}
    except proyectos_service.ProyectoNoExiste:
        raise HTTPException(404, "Proyecto no existe")
    except proyectos_service.PersonajeRepetido:
        raise HTTPException(409, "Ya hay un personaje con esa clave")
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/{pid}/personajes/{clave}")
def borrar_personaje(pid: int, clave: str):
    try:
        proyectos_service.borrar_personaje(pid, clave)
        return {"borrado": clave}
    except proyectos_service.ProyectoNoExiste:
        raise HTTPException(404, "Proyecto no existe")
    except proyectos_service.PersonajeNoExiste:
        raise HTTPException(404, "El proyecto no tiene ese personaje")


@router.post("/{pid}/personajes/{clave}/retrato")
def generar_retrato(pid: int, clave: str, body: RegenerarImagenIn):
    try:
        proyectos_service.ruta_retrato(pid, clave)  # valida que el personaje existe
    except proyectos_service.ProyectoNoExiste:
        raise HTTPException(404, "Proyecto no existe")
    except proyectos_service.PersonajeNoExiste:
        raise HTTPException(404, "El proyecto no tiene ese personaje")
    return {
        "job_id": proyectos_service.encolar_etapa(
            pid, "generar_retrato", clave=clave, nuevo_seed=body.nuevo_seed
        )
    }


@router.get("/{pid}/personajes/{clave}/retrato")
def retrato(pid: int, clave: str):
    try:
        ruta = proyectos_service.ruta_retrato(pid, clave)
    except proyectos_service.ProyectoNoExiste:
        raise HTTPException(404, "Proyecto no existe")
    except proyectos_service.PersonajeNoExiste:
        raise HTTPException(404, "El proyecto no tiene ese personaje")
    if not ruta.exists():
        raise HTTPException(404, "Retrato no generado")
    return FileResponse(ruta, media_type="image/png")


@router.post("/{pid}/escenas")
def generar_escenas(pid: int):
    return {"job_id": proyectos_service.encolar_etapa(pid, "generar_escenas")}


@router.put("/{pid}/escenas")
def editar_escenas(pid: int, body: EscenasIn):
    try:
        prompts = {
            e.orden: (
                {"prompt": e.prompt}
                if e.prompt_movimiento is None
                else {"prompt": e.prompt, "prompt_movimiento": e.prompt_movimiento}
            )
            for e in body.escenas
        }
        return {"actualizadas": proyectos_service.editar_prompts_escenas(pid, prompts)}
    except proyectos_service.ProyectoNoExiste:
        raise HTTPException(404, "Proyecto no existe")


@router.post("/{pid}/imagenes")
def generar_imagenes(pid: int):
    return {"job_id": proyectos_service.encolar_etapa(pid, "generar_imagenes")}


@router.post("/{pid}/escenas/{orden}/imagen")
def regenerar_imagen(pid: int, orden: int, body: RegenerarImagenIn):
    """Regenera la imagen de una sola escena."""
    return {"job_id": proyectos_service.encolar_etapa(
        pid, "regenerar_imagen", orden=orden, nuevo_seed=body.nuevo_seed)}


@router.post("/{pid}/escenas/{orden}/clip")
def regenerar_clip(pid: int, orden: int, body: RegenerarClipIn):
    """Regenera el clip de una sola escena en el modo indicado."""
    return {"job_id": proyectos_service.encolar_etapa(
        pid, "regenerar_clip", orden=orden, modo=body.modo)}


@router.put("/{pid}/escenas/modos")
def fijar_modos(pid: int, body: ModosEscenasIn):
    """Fija el modo de animación de cada escena, que respeta 'generar video'."""
    try:
        modos = {e.orden: e.modo for e in body.escenas}
        return {"actualizadas": proyectos_service.fijar_modo_escenas(pid, modos)}
    except proyectos_service.ProyectoNoExiste:
        raise HTTPException(404, "Proyecto no existe")


@router.post("/{pid}/video")
def generar_video(pid: int, body: VideoIn):
    """Genera el video en el modo pedido: 'estatico' (rápido) o 'kenburns'
    (con movimiento: cadena upscale → clips → armado)."""
    try:
        return {"job_id": proyectos_service.generar_video(pid, body.modo)}
    except proyectos_service.ModoVideoInvalido:
        raise HTTPException(400, "Modo de video inválido")


@router.get("/{pid}/versiones")
def listar_versiones(pid: int):
    """Montajes anteriores del video final, del más reciente al más antiguo."""
    try:
        return proyectos_service.listar_versiones(pid)
    except proyectos_service.ProyectoNoExiste:
        raise HTTPException(404, "Proyecto no existe")


@router.get("/{pid}/versiones/{nombre}")
def ver_version(pid: int, nombre: str):
    if not proyectos_service._nombre_version_valido(nombre):
        raise HTTPException(400, "Nombre de versión inválido")
    return _archivo(pid, ("versiones", nombre), "video/mp4", "Versión no existe")


@router.delete("/{pid}/versiones/{nombre}")
def borrar_version(pid: int, nombre: str):
    try:
        proyectos_service.borrar_version(pid, nombre)
        return {"borrada": nombre}
    except proyectos_service.ProyectoNoExiste:
        raise HTTPException(404, "Proyecto no existe")
    except proyectos_service.VersionNoExiste:
        raise HTTPException(404, "Versión no existe")


@router.delete("/{pid}/video")
def borrar_video(pid: int, con_versiones: bool = False):
    """Borra el video final; con `con_versiones` también los archivados."""
    try:
        return proyectos_service.borrar_video(pid, con_versiones)
    except proyectos_service.ProyectoNoExiste:
        raise HTTPException(404, "Proyecto no existe")


@router.delete("/{pid}")
def borrar_proyecto(pid: int):
    """Borra el proyecto entero: filas en la base y carpeta en disco."""
    try:
        return proyectos_service.borrar_proyecto(pid)
    except proyectos_service.ProyectoNoExiste:
        raise HTTPException(404, "Proyecto no existe")
    except proyectos_service.ProyectoOcupado:
        raise HTTPException(409, "El proyecto tiene trabajo en curso; espera a "
                                 "que termine antes de borrarlo")


def _archivo(pid: int, partes: tuple[str, ...], media_type: str, detalle: str):
    try:
        ruta = proyectos_service.ruta_archivo(pid, *partes)
    except proyectos_service.ProyectoNoExiste:
        raise HTTPException(404, "Proyecto no existe")
    if not ruta.exists():
        raise HTTPException(404, detalle)
    return FileResponse(ruta, media_type=media_type)


@router.get("/{pid}/audio")
def audio(pid: int):
    return _archivo(pid, ("voz.mp3",), "audio/mpeg", "Aún no hay voz generada")


@router.get("/{pid}/imagenes/{orden}")
def imagen(pid: int, orden: int):
    return _archivo(
        pid, ("imagenes", f"{orden:02d}.png"), "image/png", "Imagen no generada"
    )


@router.get("/{pid}/clips/{orden}")
def clip(pid: int, orden: int):
    """Clip de una escena, para previsualizarlo sin armar el video entero."""
    return _archivo(
        pid, ("clips", f"{orden:02d}.mp4"), "video/mp4", "Clip no generado"
    )


@router.get("/{pid}/video")
def video(pid: int):
    return _archivo(pid, ("final.mp4",), "video/mp4", "Aún no hay video final")
