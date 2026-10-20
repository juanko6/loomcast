from fastapi import APIRouter, HTTPException

from ..schemas import EpisodioNuevoIn, SerieIn, SerieMiembroIn
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
    try:
        return series_service.crear(body.nombre, body.plantilla)
    except series_service.PlantillaInvalida as e:
        raise HTTPException(400, f"Plantilla desconocida: {e}")
    except series_service.SlugOcupado as e:
        raise HTTPException(409, f"Ya hay una serie con ese nombre: {e}")


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
