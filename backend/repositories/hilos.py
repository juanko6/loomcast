"""El hilo de una serie: versionado como el guion, y leído por tramo.

Las funciones que no tocan la base (`tramo`, `es_final`, `normalizar`) trabajan
sobre el dict del contenido y viven aquí al lado de las que lo leen: el tramo de
un episodio es "el que lleva su número", y eso lo necesitan el guion, las ideas
y el resumen por igual. Tenerlo tres veces escrito es tenerlo tres veces mal.
"""
import json

from sqlalchemy.orm import Session

from ..models import Hilo


def ultimo(s: Session, serie_id: int) -> Hilo | None:
    return (
        s.query(Hilo)
        .filter(Hilo.serie_id == serie_id)
        .order_by(Hilo.version.desc())
        .first()
    )


def crear(s: Session, serie_id: int, contenido: dict) -> Hilo:
    """Crea la siguiente versión del hilo (el versionado es automático).

    Las versiones se quedan: replanificar lo que falta no borra el plan con el
    que se empezó, y en una serie a medias eso es lo único que explica por qué
    el episodio 3 hacía lo que hacía.
    """
    previo = ultimo(s, serie_id)
    h = Hilo(
        serie_id=serie_id,
        version=(previo.version + 1) if previo else 1,
        contenido=json.dumps(normalizar(contenido), ensure_ascii=False),
    )
    s.add(h)
    return h


def contenido(s: Session, serie_id: int) -> dict | None:
    """El hilo vigente de la serie, o None si no tiene (serie sin hilo).

    None es un caso normal, no un error: las series de antes del hilo y las que
    se crean sin premisa siguen funcionando con la continuidad hacia atrás de
    siempre, y todo lo que lee de aquí tiene que seguir dando el prompt de
    antes cuando no hay nada.
    """
    h = ultimo(s, serie_id)
    return json.loads(h.contenido) if h else None


def normalizar(datos: dict) -> dict:
    """Renumera los tramos por su posición y recorta lo que venga de más.

    El número del tramo no es un dato del LLM ni del editor: es el episodio al
    que le toca. Si llega descolocado (el LLM escribe 1,2,2,4 de vez en cuando,
    y al borrar un tramo a mano quedan huecos), un episodio se quedaría sin
    tramo o con el de otro, que es peor que no tener hilo.
    """
    vivos = [
        t for t in (datos.get("tramos") or [])
        if (t.get("titulo") or t.get("pasa") or t.get("cambia") or "").strip()
    ]
    return {**datos,
            "tramos": [{**t, "numero": i} for i, t in enumerate(vivos, start=1)]}


def tramos(contenido: dict | None) -> list[dict]:
    return list((contenido or {}).get("tramos") or [])


def tramo(contenido: dict | None, numero: int) -> dict | None:
    """El tramo que le toca a ese episodio, o None si se sale del mapa.

    Un episodio más allá del último tramo devuelve None a propósito: la serie
    llegó a su destino y lo que venga detrás ya no está planificado. Eso se le
    dice al LLM tal cual en vez de inventarle un tramo que nadie escribió.
    """
    for t in tramos(contenido):
        if t.get("numero") == numero:
            return t
    return None


def es_final(contenido: dict | None, numero: int) -> bool:
    """Si ese episodio es el último del hilo: el que sí cierra la serie."""
    mapa = tramos(contenido)
    return bool(mapa) and numero == mapa[-1].get("numero")


def borrar_de_serie(s: Session, serie_id: int) -> int:
    """Borra el hilo al disolver la serie.

    Aquí sí se borra, al contrario que los episodios: un hilo sin serie no es
    nada reutilizable (es el plan de *esta* historia), mientras que un episodio
    suelto sigue siendo un vídeo con su guion y su narración.
    """
    return s.query(Hilo).filter(Hilo.serie_id == serie_id).delete()
