from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..schemas import AlbumEditarIn, AlbumNuevoIn, AlbumOrdenIn, AlbumPistaIn
from ..services import albumes as albumes_service
from ..services.pipeline import album as album_pipeline

router = APIRouter(prefix="/api/albumes", tags=["albumes"])


def _llamar(f, *args, **kw):
    try:
        return f(*args, **kw)
    except albumes_service.AlbumNoExiste:
        raise HTTPException(404, "Álbum o pista no existe")
    except albumes_service.AlbumInvalido as e:
        raise HTTPException(400, str(e))


@router.get("")
def listar():
    return albumes_service.listar()


@router.post("")
def crear(body: AlbumNuevoIn):
    if body.musica_id is not None:
        return _llamar(albumes_service.crear_desde_pista, body.musica_id, body.num_pistas)
    return _llamar(albumes_service.crear_desde_idea, body.idea, body.num_pistas)


@router.get("/{album_id}")
def detalle(album_id: int):
    return _llamar(albumes_service.detalle, album_id)


@router.put("/{album_id}")
def editar(album_id: int, body: AlbumEditarIn):
    _llamar(albumes_service.editar, album_id, body.titulo, body.firma)
    return {"ok": True}


@router.delete("/{album_id}")
def borrar(album_id: int):
    return _llamar(albumes_service.borrar, album_id)


@router.post("/{album_id}/replanificar")
def replanificar(album_id: int):
    return {"job_id": _llamar(albumes_service.replanificar, album_id)}


@router.post("/{album_id}/producir")
def producir(album_id: int):
    return _llamar(albumes_service.producir, album_id)


@router.put("/{album_id}/orden")
def ordenar(album_id: int, body: AlbumOrdenIn):
    _llamar(albumes_service.ordenar, album_id, body.ids)
    return {"ok": True}


@router.put("/{album_id}/pistas/{musica_id}")
def editar_pista(album_id: int, musica_id: int, body: AlbumPistaIn):
    _llamar(
        albumes_service.editar_pista, album_id, musica_id,
        body.titulo, body.intencion, body.bpm, body.keyscale, body.timesig,
    )
    return {"ok": True}


@router.post("/{album_id}/pistas/{musica_id}/reescribir")
def reescribir_pista(album_id: int, musica_id: int):
    return {"job_id": _llamar(albumes_service.reescribir_pista, album_id, musica_id)}


@router.delete("/{album_id}/pistas/{musica_id}")
def quitar_pista(album_id: int, musica_id: int):
    _llamar(albumes_service.quitar_pista, album_id, musica_id)
    return {"ok": True}


@router.get("/{album_id}/portada")
def portada(album_id: int):
    ruta = album_pipeline.ruta_portada(album_id)
    if ruta is None:
        raise HTTPException(404, "El álbum aún no tiene portada")
    return FileResponse(ruta, media_type="image/png")
