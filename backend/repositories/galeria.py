import json

from sqlalchemy.orm import Session

from ..models import ImagenLibre


def crear(s: Session, tipo: str, idea: str, width: int, height: int) -> ImagenLibre:
    img = ImagenLibre(tipo=tipo, idea=idea, width=width, height=height)
    s.add(img)
    return img


def obtener(s: Session, imagen_id: int) -> ImagenLibre | None:
    return s.get(ImagenLibre, imagen_id)


def listar(s: Session) -> list[ImagenLibre]:
    return s.query(ImagenLibre).order_by(ImagenLibre.id.desc()).all()


def guardar_prompt(s: Session, img: ImagenLibre, prompt: str) -> None:
    img.prompt = prompt
    img.estado = "mejorada"


def guardar_tamano(s: Session, img: ImagenLibre, width: int, height: int) -> None:
    img.width = width
    img.height = height


def guardar_previews(s: Session, img: ImagenLibre, seeds: list[int]) -> None:
    img.seeds = json.dumps(seeds)
    img.estado = "previews"


def set_estado(s: Session, img: ImagenLibre, estado: str) -> None:
    img.estado = estado


def set_seed_elegido(s: Session, img: ImagenLibre, indice: int) -> None:
    img.seed_elegido = indice
    img.estado = "final"


def borrar(s: Session, img: ImagenLibre) -> None:
    s.delete(img)
