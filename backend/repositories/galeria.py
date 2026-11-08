import json

from sqlalchemy.orm import Session

from ..models import ImagenLibre


def crear(
    s: Session, tipo: str, idea: str, width: int, height: int, motor: str = "",
    *, detalles: str = "", estilo: str = "", n_previews: int = 4,
) -> ImagenLibre:
    img = ImagenLibre(tipo=tipo, idea=idea, width=width, height=height, motor=motor,
                      detalles=detalles, estilo=estilo, n_previews=n_previews)
    s.add(img)
    return img


def obtener(s: Session, imagen_id: int) -> ImagenLibre | None:
    return s.get(ImagenLibre, imagen_id)


def listar(s: Session) -> list[ImagenLibre]:
    return s.query(ImagenLibre).order_by(ImagenLibre.id.desc()).all()


def guardar_prompt(s: Session, img: ImagenLibre, prompt: str) -> None:
    """Guarda el prompt (o la escena) que escribió el LLM. Solo avanza una
    entrada recién creada: reescribirlo más tarde no la devuelve atrás. Antes
    sí, y la UI dejaba de enseñar las previews (y en una animada aprobada, la
    imagen, el movimiento y el vídeo) aunque seguían en disco; ahora se ven
    hasta que se regeneran, que es cuando se sustituyen."""
    img.prompt = prompt
    if img.estado == "nueva":
        img.estado = "mejorada"


def guardar_tamano(s: Session, img: ImagenLibre, width: int, height: int) -> None:
    img.width = width
    img.height = height


def empezar_previews(s: Session, img: ImagenLibre) -> None:
    """Una tirada nueva: las semillas se vacían y se van apuntando según sale
    cada preview (`anadir_preview`), para que la UI las enseñe sin esperar a
    la última."""
    img.seeds = "[]"


def anadir_preview(s: Session, img: ImagenLibre, seed: int) -> None:
    img.seeds = json.dumps([*json.loads(img.seeds or "[]"), seed])


def guardar_previews(s: Session, img: ImagenLibre, seeds: list[int]) -> None:
    img.seeds = json.dumps(seeds)
    img.estado = "previews"


def set_estado(s: Session, img: ImagenLibre, estado: str) -> None:
    img.estado = estado


def set_seed_elegido(s: Session, img: ImagenLibre, indice: int) -> None:
    img.seed_elegido = indice
    img.estado = "final"


def guardar_movimiento(s: Session, img: ImagenLibre, prompt: str, duracion_s: int) -> None:
    img.prompt_movimiento = prompt
    img.duracion_s = duracion_s
    img.estado = "movimiento"


def guardar_video(s: Session, img: ImagenLibre, seed: int) -> None:
    img.seed_video = seed
    img.escala = None
    img.estado = "animada"


def guardar_escala(s: Session, img: ImagenLibre, escala: str) -> None:
    img.escala = escala
    img.estado = "escalada"


def borrar(s: Session, img: ImagenLibre) -> None:
    s.delete(img)
