"""Estilos de imagen: cómo se dibuja, separado de qué se dibuja.

Cada estilo es una carpeta `estilos/<id>/` con un `estilo.toml` y unas cuantas
imágenes de ejemplo (`ejemplo_*.webp|png|jpg`) que la UI enseña para elegir.

El estilo no lo reescribe el LLM. Su `cabecera` y su `cola` van pegadas tal cual
al principio y al final del prompt, con la escena en medio (`componer`): si el
LLM las parafrasea, las diluye, y el motor de imagen (Z-Image va a cfg 1, sin
negativo) dibuja lo que más pesa en el prompt. La `guia_escena` sí se le da al
LLM: le dice qué tipo de escena encaja con el estilo (fondo plano o escena
completa, dónde dejar aire para el título), no cómo se dibuja.

Por eso un estilo **nunca** fija sujeto ni color de fondo concreto: eso es la
escena, y la escena es del usuario (título, detalles y el texto editable).

Se leen del disco en cada llamada: son pocos archivos pequeños y así un estilo
recién retocado vale sin reiniciar el backend.
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from .config import IMAGEN_MOTORES, ROOT

# Lo mira `cargar` en cada llamada; los tests lo apuntan a una carpeta temporal.
ESTILOS_DIR: Path = ROOT / "estilos"
EXTENSIONES_EJEMPLO = (".webp", ".png", ".jpg", ".jpeg")


class EstiloNoExiste(LookupError):
    pass


@dataclass(frozen=True)
class Estilo:
    id: str
    nombre: str
    descripcion: str
    cabecera: str
    cola: str
    guia_escena: str
    # Id de [imagen.motores] que mejor lo dibuja; "" = el motor por defecto.
    motor: str
    orden: int
    ejemplos: tuple[Path, ...]


def _ejemplos(carpeta: Path) -> tuple[Path, ...]:
    return tuple(sorted(
        p for p in carpeta.glob("ejemplo_*")
        if p.suffix.lower() in EXTENSIONES_EJEMPLO
    ))


def _leer(carpeta: Path) -> Estilo:
    datos = tomllib.loads((carpeta / "estilo.toml").read_text())
    faltan = [k for k in ("nombre", "cabecera") if not str(datos.get(k, "")).strip()]
    if faltan:
        raise ValueError(f"Estilo '{carpeta.name}': faltan {faltan} en estilo.toml")
    motor = str(datos.get("motor", "")).strip()
    if motor and (motor not in IMAGEN_MOTORES or "generar" not in IMAGEN_MOTORES[motor].modos):
        raise ValueError(
            f"Estilo '{carpeta.name}': el motor '{motor}' no existe o no sabe generar"
        )
    return Estilo(
        id=carpeta.name,
        nombre=str(datos["nombre"]).strip(),
        descripcion=str(datos.get("descripcion", "")).strip(),
        cabecera=" ".join(str(datos["cabecera"]).split()),
        cola=" ".join(str(datos.get("cola", "")).split()),
        guia_escena=str(datos.get("guia_escena", "")).strip(),
        motor=motor,
        orden=int(datos.get("orden", 100)),
        ejemplos=_ejemplos(carpeta),
    )


def listar() -> list[Estilo]:
    if not ESTILOS_DIR.is_dir():
        return []
    carpetas = [c for c in ESTILOS_DIR.iterdir() if (c / "estilo.toml").is_file()]
    return sorted((_leer(c) for c in carpetas), key=lambda e: (e.orden, e.nombre))


def obtener(estilo_id: str) -> Estilo:
    carpeta = ESTILOS_DIR / estilo_id
    # El id llega de la API: nada de rutas que se salgan de la carpeta.
    if not estilo_id or "/" in estilo_id or estilo_id.startswith(".") \
            or not (carpeta / "estilo.toml").is_file():
        raise EstiloNoExiste(estilo_id)
    return _leer(carpeta)


def componer(estilo: Estilo, escena: str) -> str:
    """El prompt que recibe el motor: el estilo abre y cierra, la escena en medio."""
    partes = [estilo.cabecera, escena.strip().rstrip("."), estilo.cola]
    return ". ".join(p.rstrip(". ") for p in partes if p.strip()) + "."


def a_dict(estilo: Estilo) -> dict:
    return {
        "id": estilo.id,
        "nombre": estilo.nombre,
        "descripcion": estilo.descripcion,
        "motor": estilo.motor,
        "ejemplos": len(estilo.ejemplos),
    }
