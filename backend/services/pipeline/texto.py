"""Etapas 0–3: ideas, guion y metadatos (todas contra llama.cpp)."""
import json

from ...clients import llm
from ...db import get_session
from ...models import avanzar_estado
from ...repositories import guiones as guiones_repo
from ...repositories import ideas as ideas_repo
from ...repositories import metadatos as metadatos_repo
from ...repositories import plantillas as plantillas_repo
from ...repositories import proyectos as proyectos_repo
from ...repositories import temas as temas_repo
from ...schemas import (
    DescripcionLLM,
    EtiquetasLLM,
    GuionLLM,
    GuionNarracionLLM,
    IdeasLLM,
    TituloLLM,
)

N_IDEAS = 8
# Español narrado ágil ≈ 2.2–2.7 palabras/segundo
PALABRAS_POR_SEGUNDO = (2.2, 2.7)


def generar_ideas(tema_id: int) -> str:
    with get_session() as s:
        tema = temas_repo.obtener(s, tema_id)
        if tema is None:
            raise ValueError(f"Tema {tema_id} no existe")
        texto_tema, plantilla = tema.texto, tema.plantilla

    pl = plantillas_repo.cargar(plantilla)
    system = pl["prompts"]["ideas"].replace("{n_ideas}", str(N_IDEAS))
    ideas = llm.chat(system, f"Tema: {texto_tema}", IdeasLLM).root

    with get_session() as s:
        for i in ideas:
            ideas_repo.crear(
                s, tema_id, titulo=i.titulo, gancho=i.gancho, resumen=i.resumen
            )
        s.commit()
    return f"{len(ideas)} ideas generadas"


def generar_guion(proyecto_id: int) -> str:
    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        if p is None:
            raise ValueError(f"Proyecto {proyecto_id} no existe")
        idea = ideas_repo.obtener(s, p.idea_id)
        plantilla = p.plantilla
        datos_idea = (idea.titulo, idea.gancho, idea.resumen)

    pl = plantillas_repo.cargar(plantilla)
    duracion = pl["ritmo"]["duracion_objetivo_s"]
    system = (
        pl["prompts"]["guion"]
        .replace("{duracion}", str(duracion))
        .replace("{min_palabras}", str(round(duracion * PALABRAS_POR_SEGUNDO[0])))
        .replace("{max_palabras}", str(round(duracion * PALABRAS_POR_SEGUNDO[1])))
    )
    titulo, gancho, resumen = datos_idea
    user = (
        f"Idea del video:\n- Título: {titulo}\n"
        f"- Gancho propuesto: {gancho}\n- Resumen: {resumen}"
    )
    # La plantilla elige el formato: narración continua o lista de frases.
    esquema = GuionNarracionLLM if pl.get("formato_guion") == "narracion" else GuionLLM
    guion = llm.chat(system, user, esquema)

    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        g = guiones_repo.crear(s, proyecto_id, guion.model_dump())
        avanzar_estado(p, "GUION")
        s.commit()
        return f"Guion v{g.version} generado"


def generar_metadatos(proyecto_id: int) -> str:
    """Tres llamadas especializadas encadenadas: título → descripción →
    etiquetas/TikTok (la descripción necesita el título ya elegido)."""
    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        if p is None:
            raise ValueError(f"Proyecto {proyecto_id} no existe")
        ultimo = guiones_repo.ultimo(s, proyecto_id)
        if ultimo is None:
            raise ValueError("El proyecto no tiene guion todavía")
        plantilla = p.plantilla
        g = json.loads(ultimo.contenido)

    texto = guiones_repo.texto_narrado(g)
    pl = plantillas_repo.cargar(plantilla)
    prompts = pl["prompts"]

    titulo = llm.chat(
        prompts["titulo"], f"Guion del video:\n{texto}", TituloLLM
    ).titulo
    descripcion = llm.chat(
        prompts["descripcion"],
        f"Título: {titulo}\n\nGuion del video:\n{texto}",
        DescripcionLLM,
    ).descripcion
    redes = llm.chat(
        prompts["etiquetas"],
        f"Título: {titulo}\n\nGuion del video:\n{texto}",
        EtiquetasLLM,
    )

    meta = {
        "youtube": {
            "titulo": titulo,
            "descripcion": descripcion,
            "etiquetas": redes.etiquetas,
        },
        "tiktok": {"descripcion": redes.tiktok},
    }
    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        m = metadatos_repo.crear(s, proyecto_id, meta)
        avanzar_estado(p, "METADATOS")
        s.commit()
        return f"Metadatos v{m.version} generados (título, descripción y etiquetas)"
