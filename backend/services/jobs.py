"""Cara HTTP de la cola: ver qué hay, cancelar uno y parar la generación.

Cancelar tiene dos mitades muy distintas:

  - **Pendiente**: basta con dejarlo cancelado en la BD. El worker mira el
    estado antes de ejecutarlo y lo salta cuando le llega el turno, así que no
    hace falta sacarlo de la cola en memoria (y no se saca a propósito: hurgar
    en la `Queue` desde el hilo HTTP mientras el worker tira de ella es pedir
    una carrera por nada).
  - **Corriendo**: además hay que cortarle el trabajo de verdad, que es lo que
    hace `cancelacion.pedir`: ComfyUI, el proceso externo y la bandera que miran
    los bucles por lotes, el cliente del LLM entre trozos y el de Whisper entre
    segmentos.
"""
from ..db import get_session
from ..repositories import jobs as jobs_repo
from . import autopiloto, cancelacion, progreso

MOTIVO = "Parado desde la interfaz"


class JobNoExiste(LookupError):
    pass


def _progreso_de(job_id: int) -> dict | None:
    """El progreso del job solo si es el que está corriendo ahora mismo: la
    cola procesa de uno en uno, así que los demás no tienen ninguno."""
    p = progreso.snapshot()
    return p if p and p["job_id"] == job_id else None


def _a_dict(j, con_log: bool = False) -> dict:
    # `sin_corte` nombra lo que no se puede cortar a mitad (la síntesis de voz),
    # y es null en todo lo demás. Lo decide el backend y no la UI para que el
    # botón de parada no prometa lo que esta etapa no puede hacer.
    d = {"id": j.id, "tipo": j.tipo, "ref_id": j.ref_id, "estado": j.estado,
         "intentos": j.intentos, "sin_corte": cancelacion.SIN_CORTE.get(j.tipo),
         "progreso": _progreso_de(j.id)}
    if con_log:
        d["log"] = j.log
    return d


def ver(job_id: int) -> dict:
    with get_session() as s:
        j = jobs_repo.obtener(s, job_id)
        if j is None:
            raise JobNoExiste(job_id)
        return _a_dict(j, con_log=True)


def activos() -> list[dict]:
    with get_session() as s:
        return [_a_dict(j) for j in jobs_repo.activos(s)]


def historial(limite: int = 20) -> list[dict]:
    """Los últimos jobs terminados, con su log: es donde se ve que uno acabó en
    error tras varios intentos y que otro se paró a mano."""
    with get_session() as s:
        return [_a_dict(j, con_log=True) for j in jobs_repo.historial(s, limite)]


def cancelar(job_id: int) -> dict:
    """Cancela un job. Devuelve su estado y si hubo que cortar algo en caliente.

    Un job ya terminado no se toca: su resultado es el que es, y marcarlo
    cancelado a posteriori sería mentir sobre lo que pasó.
    """
    with get_session() as s:
        j = jobs_repo.obtener(s, job_id)
        if j is None:
            raise JobNoExiste(job_id)
        if j.estado not in jobs_repo.ACTIVOS:
            return {"id": job_id, "estado": j.estado, "cortado": False}
        corria = j.estado == "corriendo"
        jobs_repo.cancelar(s, j, MOTIVO)
        s.commit()
    return {"id": job_id, "estado": "cancelado",
            "cortado": cancelacion.pedir(job_id) if corria else False}


def parar(corriendo: bool = True, pendientes: bool = True) -> dict:
    """Para la generación: lo que se está haciendo, lo que espera, o las dos.

    Con `corriendo=False` se vacía la cola pero se deja acabar la etapa en
    curso: sirve para "que termine esta y pare", sin tirar minutos de GPU ya
    invertidos.

    Vaciar la cola apaga además **todos los autopilotos**, y se hace antes de
    cancelar nada: un autopiloto encola la etapa siguiente en cuanto la anterior
    termina, así que dejarlo encendido convertiría la parada en un juego de
    quién llega primero —se vacía la cola y él la vuelve a llenar—. Apagándolo
    primero, el worker viene a preguntar qué toca y se encuentra con que ya no
    hay a quién seguir. Los que esperaban revisión también se apagan: el botón
    dice parar. Relanzar uno es un clic y retoma el proyecto donde esté.

    "Detener lo actual" (`pendientes=False`) no los apaga: ahí se corta una
    etapa, no la línea de producción. El autopiloto de ese proyecto se detiene
    de todos modos —su etapa sube como cancelada y el worker se lo dice—, y el
    lote sigue con el proyecto siguiente.
    """
    autopilotos = autopiloto.parar_todos(MOTIVO) if pendientes else 0
    with get_session() as s:
        activos_ahora = jobs_repo.activos(s)
        en_curso = [j for j in activos_ahora if j.estado == "corriendo"]
        esperando = [j for j in activos_ahora if j.estado == "pendiente"]
        objetivo = (en_curso if corriendo else []) + (esperando if pendientes else [])
        for j in objetivo:
            jobs_repo.cancelar(s, j, MOTIVO)
        ids_en_curso = [j.id for j in en_curso]
        s.commit()
    cortados = sum(cancelacion.pedir(i) for i in ids_en_curso) if corriendo else 0
    return {
        "corriendo": len(ids_en_curso) if corriendo else 0,
        "pendientes": len(esperando) if pendientes else 0,
        "cortado": bool(cortados),
        # Cuántas tiradas automáticas se apagaron: es lo que la UI necesita para
        # no decir "se paró" cuando además se ha cancelado un lote entero.
        "autopilotos": autopilotos,
    }
