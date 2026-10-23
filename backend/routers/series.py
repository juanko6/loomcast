from fastapi import APIRouter, HTTPException

from ..schemas import (
    EpisodioNuevoIn,
    HiloIn,
    SerieAjusteIn,
    SerieIn,
    SerieMiembroIn,
)
from ..services import series as series_service

router = APIRouter(prefix="/api/series", tags=["series"])

# El reparto fijo se maneja desde aquí y no desde /api/reparto: lo que se guarda
# es una lista de a quién traer, que es de la serie. El reparto propio sigue
# siendo el almacén y no sabe en qué series sale cada uno.


@router.get("")
def listar():
    return series_service.listar()


@router.post("")
def crear(body: SerieIn):
    """Crea la serie y, si trae premisa, encola el hilo con el que se guiará."""
    try:
        return series_service.crear(
            body.nombre, body.plantilla, body.premisa, body.episodios
        )
    except series_service.PlantillaInvalida as e:
        raise HTTPException(400, f"Plantilla desconocida: {e}")
    except series_service.SlugOcupado as e:
        raise HTTPException(409, f"Ya hay una serie con ese nombre: {e}")


@router.put("/{serie_id}")
def ajustar(serie_id: int, body: SerieAjusteIn):
    """Cambia de qué va la serie y cuántos episodios se quieren.

    No reescribe el hilo: eso es `POST /{serie_id}/hilo`, porque en una serie a
    medias replanifica los capítulos que todavía no se han escrito.
    """
    try:
        return series_service.ajustar(serie_id, body.premisa, body.episodios)
    except series_service.SerieNoExiste:
        raise HTTPException(404, "Serie no existe")


@router.post("/{serie_id}/hilo")
def escribir_hilo(serie_id: int):
    """Escribe el hilo, o replanifica los tramos que quedan por rodar."""
    try:
        return series_service.escribir_hilo(serie_id)
    except series_service.SerieNoExiste:
        raise HTTPException(404, "Serie no existe")
    except series_service.SinPremisa:
        raise HTTPException(
            400,
            "La serie no dice de qué va: escribe su premisa y el hilo sale de "
            "ahí. Desde el nombre a secas no hay historia que planificar.",
        )


@router.put("/{serie_id}/hilo")
def editar_hilo(serie_id: int, body: HiloIn):
    """Guarda el hilo corregido a mano como una versión más."""
    try:
        return series_service.editar_hilo(serie_id, body.model_dump())
    except series_service.SerieNoExiste:
        raise HTTPException(404, "Serie no existe")


@router.get("/{serie_id}")
def detalle(serie_id: int):
    try:
        return series_service.detalle(serie_id)
    except series_service.SerieNoExiste:
        raise HTTPException(404, "Serie no existe")


@router.post("/{serie_id}/miembros")
def anadir_miembro(serie_id: int, body: SerieMiembroIn):
    """Añade a alguien del reparto propio al reparto fijo de la serie.

    Entra en los episodios siguientes, no en los que ya existen: un capítulo
    escrito no gana un personaje por detrás.
    """
    try:
        return series_service.anadir_miembro(serie_id, body.reparto_slug)
    except series_service.SerieNoExiste:
        raise HTTPException(404, "Serie no existe")
    except series_service.MiembroNoExiste:
        raise HTTPException(404, "Ese miembro no está en el reparto propio")
    except series_service.MiembroRepetido:
        raise HTTPException(409, "Ya sale en todos los episodios de esta serie")


@router.delete("/{serie_id}/miembros/{reparto_slug}")
def quitar_miembro(serie_id: int, reparto_slug: str):
    try:
        return series_service.quitar_miembro(serie_id, reparto_slug)
    except series_service.SerieNoExiste:
        raise HTTPException(404, "Serie no existe")
    except series_service.MiembroNoExiste:
        raise HTTPException(404, "Ese miembro no está en el reparto de la serie")


@router.post("/{serie_id}/episodios")
def crear_episodio(serie_id: int, body: EpisodioNuevoIn | None = None):
    """Crea el episodio siguiente y encola su guion.

    Hereda la plantilla de la serie, se numera solo, se le trae el reparto fijo
    con su ficha y su cara, y el guion sale con el resumen del episodio
    anterior como contexto.
    """
    try:
        return series_service.crear_episodio(
            serie_id, body.apunte if body else ""
        )
    except series_service.SerieNoExiste:
        raise HTTPException(404, "Serie no existe")


@router.delete("/{serie_id}")
def borrar(serie_id: int):
    """Disuelve la serie. Sus episodios se quedan como vídeos sueltos."""
    try:
        return series_service.borrar(serie_id)
    except series_service.SerieNoExiste:
        raise HTTPException(404, "Serie no existe")
