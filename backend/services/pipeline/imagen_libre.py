"""Galería de imágenes independiente del pipeline de video.

Tres etapas:
  1. mejorar_prompt  — el LLM convierte la idea/petición en un prompt en inglés.
     Con un estilo de `estilos/`, solo escribe la escena (qué se dibuja); el
     estilo (cómo) se le pega tal cual al generar.
  2. generar_previews — N imágenes a resolución nativa con distinta seed.
  3. generar_final    — ESRGAN x4 sobre la preview elegida (máxima resolución).

Generar y animada encadenan 1 → 2 al crear (`y_previews`); lo demás lo dispara
el usuario desde la UI.

El modo (`tipo`) decide la etapa 1 (qué prompt de sistema) y la etapa 2 (generar
desde texto o editar la imagen subida); el `motor` guardado en la entrada decide
con qué modelo de [imagen.motores] se hace esa etapa 2.
"""
import random

from ...clients import comfy, llm
from ...config import GALERIA_DIR, PROMPTS_DIR
from ...db import get_session
from ...repositories import galeria as galeria_repo
from ...schemas import ImagenLibrePromptLLM
from ... import estilos, parada
from .. import progreso

def carpeta(imagen_id: int):
    return GALERIA_DIR / str(imagen_id)


def ruta_fuente(imagen_id: int):
    return carpeta(imagen_id) / "fuente.png"


def ruta_preview(imagen_id: int, indice: int):
    return carpeta(imagen_id) / f"preview_{indice}.png"


def ruta_final(imagen_id: int):
    return carpeta(imagen_id) / "final.png"


def _tamano(imagen) -> tuple[int, int]:
    """Ancho y alto de la imagen subida, redondeados a múltiplo de 8 como
    quieren los latentes."""
    from PIL import Image

    with Image.open(imagen) as im:
        w, h = im.size
    return max(8, w // 8 * 8), max(8, h // 8 * 8)


SISTEMA = {
    "editar": "imagen_editar.md",
    # Respeta el tema del usuario y solo añade lo que ayuda a animarlo:
    # composición estable, aire alrededor, nada cortado por el borde.
    "animada": "animada_imagen.md",
}


def _sistema(tipo: str) -> str:
    return (PROMPTS_DIR / SISTEMA.get(tipo, "imagen_generar.md")).read_text()


def _peticion(tipo: str, idea: str, detalles: str, estilo: str) -> tuple[str, str]:
    """Prompt de sistema y mensaje para el LLM.

    Con estilo, el LLM escribe solo la escena y recibe la guía del estilo (qué
    escena le encaja), nunca su cabecera: si la viera la repetiría a su manera.
    Libre, es el camino de siempre, con los detalles añadidos a la idea."""
    if estilo:
        e = estilos.obtener(estilo)
        partes = [f"TITLE: {idea}"]
        if detalles:
            partes.append(f"DETAILS (they override the title): {detalles}")
        if e.guia_escena:
            partes.append(f"STYLE GUIDE: {e.guia_escena}")
        if tipo == "animada":
            partes.append("This still image will be animated into a short loop.")
        return (PROMPTS_DIR / "imagen_escena.md").read_text(), "\n\n".join(partes)
    mensaje = f"{idea}\n\nDetalles: {detalles}" if detalles else idea
    return _sistema(tipo), mensaje


def mejorar_prompt(imagen_id: int, y_previews: bool = False) -> str:
    """`y_previews` no se usa aquí: es la marca con la que la cola encadena
    las previews al acabar (ver `queue._encadenado`)."""
    with get_session() as s:
        img = galeria_repo.obtener(s, imagen_id)
        if img is None:
            raise ValueError(f"Imagen {imagen_id} no existe")
        tipo, idea = img.tipo, img.idea
        detalles, estilo = img.detalles or "", img.estilo or ""

    if tipo == "editar" and not ruta_fuente(imagen_id).exists():
        raise ValueError("No hay imagen de origen; súbela antes de mejorar el prompt")

    sistema, mensaje = _peticion(tipo, idea, detalles, estilo)
    # La escena es un párrafo y se pide como texto: el JSON lo saltaba el
    # modelo con algunos estilos (ver `llm.texto`). Libre sigue con su contrato.
    if estilo:
        prompt = llm.texto(sistema, mensaje)
    else:
        prompt = llm.chat(sistema, mensaje, ImagenLibrePromptLLM).prompt

    with get_session() as s:
        img = galeria_repo.obtener(s, imagen_id)
        galeria_repo.guardar_prompt(s, img, prompt)
        s.commit()
    return "Prompt mejorado"


def generar_previews(imagen_id: int) -> str:
    with get_session() as s:
        img = galeria_repo.obtener(s, imagen_id)
        if img is None:
            raise ValueError(f"Imagen {imagen_id} no existe")
        if not img.prompt:
            raise ValueError("La imagen no tiene prompt todavía")
        tipo, prompt, width, height = img.tipo, img.prompt, img.width, img.height
        motor = img.motor or None
        n = img.n_previews or 4
        estilo = img.estilo or ""

    if estilo and tipo != "editar":
        prompt = estilos.componer(estilos.obtener(estilo), prompt)

    carpeta(imagen_id).mkdir(parents=True, exist_ok=True)
    # La tirada anterior se va entera, archivos y semillas a la vez: la UI
    # dibuja la rejilla con las semillas, y si quedaran las viejas pediría
    # imágenes que ya no están.
    for vieja in carpeta(imagen_id).glob("preview_*.png"):
        vieja.unlink()
    with get_session() as s:
        galeria_repo.empezar_previews(s, galeria_repo.obtener(s, imagen_id))
        s.commit()
    seeds = [random.randint(0, 2**31 - 1) for _ in range(n)]
    try:
        for i, seed in enumerate(seeds):
            parada.comprobar(f"quedaban {n - i} previews")
            progreso.lote(i, n, "preview")
            destino = ruta_preview(imagen_id, i)
            if tipo == "editar":
                # Editar aquí es retocar la imagen que subió el usuario, así que
                # la salida conserva su tamaño. Antes lo heredaba del propio
                # workflow; ahora el tamaño se pide explícito (lo necesita el
                # pipeline de vídeo, donde la referencia no tiene la forma del
                # resultado), y hay que decírselo.
                w, h = _tamano(ruta_fuente(imagen_id))
                comfy.editar_imagen(
                    ruta_fuente(imagen_id), prompt, seed, destino, motor, w, h
                )
            else:
                comfy.generar_imagen(prompt, seed, destino, width, height, motor)
            # Cada una se apunta en cuanto existe: la UI la enseña ya, en su
            # hueco, mientras salen las demás.
            with get_session() as s:
                galeria_repo.anadir_preview(s, galeria_repo.obtener(s, imagen_id), seed)
                s.commit()
    finally:
        comfy.liberar_memoria()

    with get_session() as s:
        img = galeria_repo.obtener(s, imagen_id)
        galeria_repo.guardar_previews(s, img, seeds)
        s.commit()
    return f"{n} previews generadas"


def generar_final(imagen_id: int, indice: int) -> str:
    with get_session() as s:
        img = galeria_repo.obtener(s, imagen_id)
        if img is None:
            raise ValueError(f"Imagen {imagen_id} no existe")

    origen = ruta_preview(imagen_id, indice)
    if not origen.exists():
        raise ValueError(f"No existe la preview {indice}")

    try:
        comfy.upscale_imagen(origen, ruta_final(imagen_id))
    finally:
        comfy.liberar_memoria()

    with get_session() as s:
        img = galeria_repo.obtener(s, imagen_id)
        galeria_repo.set_seed_elegido(s, img, indice)
        s.commit()
    return f"Imagen final ampliada (preview {indice + 1})"
