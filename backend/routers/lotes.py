"""Lotes: varias ideas de un tema produciéndose una detrás de otra."""
from fastapi import APIRouter, HTTPException

from ..schemas import LoteIn
from ..services import autopiloto as autopiloto_service

router = APIRouter(prefix="/api/lotes", tags=["lotes"])


@router.get("")
def listar(limite: int = 10):
    """Los últimos lotes: en qué proyecto va cada uno, en qué etapa y cuántos
    quedan. Es lo que alimenta el panel de la cola."""
    return autopiloto_service.listar_lotes(max(1, min(limite, 50)))


@router.post("")
def lanzar(body: LoteIn):
    try:
        return autopiloto_service.lanzar_lote(
            body.tema_id, body.modo, body.motor, body.voz, body.paradas,
            narracion=body.narracion,
        )
    except autopiloto_service.TemaNoExiste:
        raise HTTPException(404, "Tema no existe")
    except autopiloto_service.SinIdeas:
        raise HTTPException(
            400,
            "Este tema no tiene ninguna idea que producir. Aprueba las que "
            "quieras, o desactiva la parada de revisión de ideas para producir "
            "también las propuestas.",
        )
    except autopiloto_service.SinVoz:
        raise HTTPException(
            400, "Elige la voz con la que narrar antes de lanzar el lote: la "
                 "narración se clona de una voz del banco. O lanza con "
                 "narración expresiva, y cada historia se narra con el estilo "
                 "que el guion trae para ella."
        )
    except autopiloto_service.ModoVideoInvalido:
        raise HTTPException(400, "Modo de video inválido")
    except autopiloto_service.NarracionInvalida as e:
        raise HTTPException(400, f"Modo de narración desconocido: {e}")
    except autopiloto_service.ParadaInvalida as e:
        raise HTTPException(400, f"Parada de revisión desconocida: {e}")


@router.get("/{lote_id}")
def ver(lote_id: int):
    try:
        return autopiloto_service.ver_lote(lote_id)
    except autopiloto_service.LoteNoExiste:
        raise HTTPException(404, "Lote no existe")
