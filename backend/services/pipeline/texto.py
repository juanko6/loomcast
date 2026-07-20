"""Etapas 0–3: ideas, guion y metadatos (todas contra llama.cpp)."""
import json

from ...clients import llm
from ...db import get_session
from ...repositories import guiones as guiones_repo
from ...repositories import ideas as ideas_repo
from ...repositories import metadatos as metadatos_repo
from ...repositories import plantillas as plantillas_repo
from ...repositories import proyectos as proyectos_repo
from ...repositories import temas as temas_repo
from ...models import avanzar_estado

N_IDEAS = 8
# Español narrado ágil ≈ 2.2–2.7 palabras/segundo
PALABRAS_POR_SEGUNDO = (2.2, 2.7)

SCHEMA_IDEAS = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "titulo": {"type": "string"},
            "gancho": {"type": "string"},
            "resumen": {"type": "string"},
        },
        "required": ["titulo", "gancho", "resumen"],
    },
}

SCHEMA_GUION = {
    "type": "object",
    "properties": {
        "gancho": {"type": "string"},
        "frases": {"type": "array", "items": {"type": "string"}},
        "cta": {"type": "string"},
    },
    "required": ["gancho", "frases", "cta"],
}

SCHEMA_METADATOS = {
    "type": "object",
    "properties": {
        "youtube": {
            "type": "object",
            "properties": {
                "titulo": {"type": "string"},
                "descripcion": {"type": "string"},
                "etiquetas": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["titulo", "descripcion", "etiquetas"],
        },
        "tiktok": {
            "type": "object",
            "properties": {"descripcion": {"type": "string"}},
            "required": ["descripcion"],
        },
    },
    "required": ["youtube", "tiktok"],
}


def generar_ideas(tema_id: int) -> str:
    with get_session() as s:
        tema = temas_repo.obtener(s, tema_id)
        if tema is None:
            raise ValueError(f"Tema {tema_id} no existe")
        texto_tema, plantilla = tema.texto, tema.plantilla

    pl = plantillas_repo.cargar(plantilla)
    system = pl["prompts"]["ideas"].replace("{n_ideas}", str(N_IDEAS))
    ideas = llm.chat_json(system, f"Tema: {texto_tema}", SCHEMA_IDEAS)
    if not isinstance(ideas, list) or not ideas:
        raise llm.LLMError(f"Se esperaba una lista de ideas: {ideas!r:.200}")

    with get_session() as s:
        for i in ideas:
            ideas_repo.crear(
                s, tema_id,
                titulo=str(i.get("titulo", ""))[:200],
                gancho=str(i.get("gancho", "")),
                resumen=str(i.get("resumen", "")),
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
    guion = llm.chat_json(system, user, SCHEMA_GUION)
    if not isinstance(guion, dict) or not guion.get("frases"):
        raise llm.LLMError(f"Guion inválido: {guion!r:.200}")

    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        g = guiones_repo.crear(s, proyecto_id, guion)
        avanzar_estado(p, "GUION")
        s.commit()
        return f"Guion v{g.version} generado"


def generar_metadatos(proyecto_id: int) -> str:
    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        if p is None:
            raise ValueError(f"Proyecto {proyecto_id} no existe")
        ultimo = guiones_repo.ultimo(s, proyecto_id)
        if ultimo is None:
            raise ValueError("El proyecto no tiene guion todavía")
        plantilla = p.plantilla
        g = json.loads(ultimo.contenido)

    texto = " ".join([g["gancho"], *g["frases"], g["cta"]])
    pl = plantillas_repo.cargar(plantilla)
    meta = llm.chat_json(
        pl["prompts"]["metadatos"], f"Guion del video:\n{texto}", SCHEMA_METADATOS
    )
    if not isinstance(meta, dict) or "youtube" not in meta:
        raise llm.LLMError(f"Metadatos inválidos: {meta!r:.200}")

    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        m = metadatos_repo.crear(s, proyecto_id, meta)
        avanzar_estado(p, "METADATOS")
        s.commit()
        return f"Metadatos v{m.version} generados"
