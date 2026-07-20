"""Etapas 0–3: ideas, guion y metadatos (todas contra llama.cpp)."""
import json

from .. import llm, plantillas
from ..db import get_session
from ..models import Guion, Idea, Metadatos, Proyecto, Tema

N_IDEAS = 8

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
        tema = s.get(Tema, tema_id)
        if tema is None:
            raise ValueError(f"Tema {tema_id} no existe")
        pl = plantillas.cargar(tema.plantilla)
        system = pl["prompts"]["ideas"].replace("{n_ideas}", str(N_IDEAS))
        ideas = llm.chat_json(system, f"Tema: {tema.texto}", SCHEMA_IDEAS)
        if not isinstance(ideas, list) or not ideas:
            raise llm.LLMError(f"Se esperaba una lista de ideas: {ideas!r:.200}")
        for i in ideas:
            s.add(Idea(
                tema_id=tema_id,
                titulo=str(i.get("titulo", ""))[:200],
                gancho=str(i.get("gancho", "")),
                resumen=str(i.get("resumen", "")),
            ))
        s.commit()
        return f"{len(ideas)} ideas generadas"


def generar_guion(proyecto_id: int) -> str:
    with get_session() as s:
        p = s.get(Proyecto, proyecto_id)
        if p is None:
            raise ValueError(f"Proyecto {proyecto_id} no existe")
        idea = s.get(Idea, p.idea_id)
        pl = plantillas.cargar(p.plantilla)
        duracion = pl["ritmo"]["duracion_objetivo_s"]
        # Español narrado ágil ≈ 2.2–2.7 palabras/segundo
        system = (
            pl["prompts"]["guion"]
            .replace("{duracion}", str(duracion))
            .replace("{min_palabras}", str(round(duracion * 2.2)))
            .replace("{max_palabras}", str(round(duracion * 2.7)))
        )
        user = (
            f"Idea del video:\n- Título: {idea.titulo}\n"
            f"- Gancho propuesto: {idea.gancho}\n- Resumen: {idea.resumen}"
        )
        guion = llm.chat_json(system, user, SCHEMA_GUION)
        if not isinstance(guion, dict) or not guion.get("frases"):
            raise llm.LLMError(f"Guion inválido: {guion!r:.200}")
        version = 1 + len(
            s.query(Guion).filter(Guion.proyecto_id == proyecto_id).all()
        )
        s.add(Guion(
            proyecto_id=proyecto_id,
            version=version,
            contenido=json.dumps(guion, ensure_ascii=False),
        ))
        if p.estado == "IDEA":
            p.estado = "GUION"
        s.commit()
        return f"Guion v{version} generado"


def generar_metadatos(proyecto_id: int) -> str:
    with get_session() as s:
        p = s.get(Proyecto, proyecto_id)
        if p is None:
            raise ValueError(f"Proyecto {proyecto_id} no existe")
        ultimo = (
            s.query(Guion)
            .filter(Guion.proyecto_id == proyecto_id)
            .order_by(Guion.version.desc())
            .first()
        )
        if ultimo is None:
            raise ValueError("El proyecto no tiene guion todavía")
        g = json.loads(ultimo.contenido)
        texto = " ".join([g["gancho"], *g["frases"], g["cta"]])
        pl = plantillas.cargar(p.plantilla)
        meta = llm.chat_json(
            pl["prompts"]["metadatos"], f"Guion del video:\n{texto}", SCHEMA_METADATOS
        )
        if not isinstance(meta, dict) or "youtube" not in meta:
            raise llm.LLMError(f"Metadatos inválidos: {meta!r:.200}")
        version = 1 + len(
            s.query(Metadatos).filter(Metadatos.proyecto_id == proyecto_id).all()
        )
        s.add(Metadatos(
            proyecto_id=proyecto_id,
            version=version,
            contenido=json.dumps(meta, ensure_ascii=False),
        ))
        if p.estado == "GUION":
            p.estado = "METADATOS"
        s.commit()
        return f"Metadatos v{version} generados"
