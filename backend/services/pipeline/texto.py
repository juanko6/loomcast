"""Etapas 0–3: ideas, guion y metadatos (todas contra llama.cpp)."""
import json

from ...clients import llm
from ...config import PROMPTS_DIR
from ...db import get_session
from ...models import avanzar_estado
from ...repositories import guiones as guiones_repo
from ...repositories import ideas as ideas_repo
from ...repositories import metadatos as metadatos_repo
from ...repositories import plantillas as plantillas_repo
from ...repositories import proyectos as proyectos_repo
from ...repositories import series as series_repo
from ...repositories import temas as temas_repo
from ...schemas import (
    DescripcionLLM,
    EtiquetasLLM,
    GuionLineasLLM,
    GuionLLM,
    GuionNarracionLLM,
    IdeasLLM,
    TituloLLM,
)
from . import series as series_pipeline

N_IDEAS = 8
# Cuántas maneras del MISMO episodio se proponen cuando la serie tiene hilo.
# Son tres y no ocho porque con el tramo escrito ya no hay ocho decisiones que
# tomar: hay una, cómo se rueda este capítulo, y de eso se eligen variantes.
# Pedir ocho era lo que convertía las ideas de una serie en ocho capítulos
# sueltos escritos a la vez sin saber qué había pasado en ninguno.
N_IDEAS_EPISODIO = 3
# Qué esquema de guion pide cada `formato_guion` de la plantilla. Lo que no esté
# aquí (incluida una plantilla que no declare el campo) va a GuionLLM, que es el
# formato de frases de siempre.
ESQUEMA_GUION = {
    "narracion": GuionNarracionLLM,
    "lineas": GuionLineasLLM,
}
# Español narrado ágil ≈ 2.2–2.7 palabras/segundo
PALABRAS_POR_SEGUNDO = (2.2, 2.7)


def generar_ideas(tema_id: int) -> str:
    """Ideas del tema, o maneras de rodar el episodio que viene si es una serie.

    Son dos peticiones distintas con un solo camino, que es el que ya había: las
    ideas de episodio son ideas del tema de la serie. Lo que cambia con el hilo
    es qué se pide. Sin hilo (un tema normal, o una serie sin planificar) van
    ocho ideas desde el texto del tema, como siempre. Con hilo van tres maneras
    del episodio que toca, con su tramo y el canon del anterior delante: el
    número del capítulo deja de ser una casualidad de en qué orden se aprobaron.
    """
    with get_session() as s:
        tema = temas_repo.obtener(s, tema_id)
        if tema is None:
            raise ValueError(f"Tema {tema_id} no existe")
        texto_tema, plantilla = tema.texto, tema.plantilla
        serie = series_repo.por_tema(s, tema_id)
        serie_id = serie.id if serie else None

    episodio = (
        series_pipeline.contexto_episodio_siguiente(serie_id)
        if serie_id is not None else None
    )
    if episodio is None:
        pl = plantillas_repo.cargar(plantilla)
        system = pl["prompts"]["ideas"].replace("{n_ideas}", str(N_IDEAS))
        user = f"Tema: {texto_tema}"
        numero = 0
    else:
        numero, user = episodio
        # El prompt de las maneras es global, como el del resumen y el del
        # hilo: no es del nicho, es de cómo funciona una serie. Así vale para
        # una serie con cualquier plantilla sin tener que escribirlo en todas.
        system = (PROMPTS_DIR / "ideas_episodio.md").read_text().replace(
            "{n_ideas}", str(N_IDEAS_EPISODIO)
        )
    ideas = llm.chat(system, user, IdeasLLM).root

    with get_session() as s:
        for i in ideas:
            # Con hilo las tres son el mismo capítulo, y verlas en la lista sin
            # su número es verlas como tres episodios distintos.
            titulo = i.titulo if not numero else f"Episodio {numero}: {i.titulo}"
            ideas_repo.crear(
                s, tema_id, titulo=titulo, gancho=i.gancho, resumen=i.resumen
            )
        s.commit()
    if numero:
        return f"{len(ideas)} maneras de rodar el episodio {numero}"
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
    # Si el proyecto es un episodio, detrás de la idea va la continuidad: el
    # reparto fijo de la serie y qué pasó en el episodio anterior. Para un vídeo
    # suelto es cadena vacía y la petición es byte a byte la de siempre.
    continuidad = series_pipeline.contexto_continuidad(proyecto_id)
    if continuidad:
        user = f"{user}\n\n{continuidad}"
    # La plantilla elige el formato: frases, narración continua o líneas
    # atribuidas a un personaje.
    esquema = ESQUEMA_GUION.get(pl.get("formato_guion"), GuionLLM)
    guion = llm.chat(system, user, esquema)
    # Las claves que escribió al atribuir las líneas pasan por el normalizador
    # del reparto: son los marcadores con los que el casting lo encontrará.
    contenido = guiones_repo.normalizar_lineas(guion.model_dump())

    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        g = guiones_repo.crear(s, proyecto_id, contenido)
        avanzar_estado(p, "GUION")
        if p.serie_id is not None:
            # Este episodio acaba de escribirse con el canon que hay ahora, así
            # que su continuidad está al día; los que vengan DETRÁS, si ya
            # existen, se escribieron con el canon anterior a esto.
            p.continuidad_rota = False
            series_repo.marcar_continuidad_rota(s, p.serie_id, p.episodio)
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
