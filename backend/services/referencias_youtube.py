"""Referencias de música sacadas de YouTube: qué vídeos de este nicho funcionan
y qué estilo (o prompt) declaran en la descripción.

Aquí vive la lógica pura —parsear duraciones, filtrar, puntuar, agrupar
plantillas repetidas— para poder probarla sin red. Las llamadas a la YouTube
Data API v3 y al LLM las hace `scripts/referencias_youtube.py`.

Los datos que se recogen son material de consulta personal: viven en
`/referencias/youtube/`, que está en .gitignore.
"""
import re
import unicodedata
from datetime import datetime, timezone

from pydantic import BaseModel, Field

# Una mezcla de estos canales dura de 1 a 3 horas. Por debajo de esto suele ser
# un single, un short o un vídeo de artista, que es otro tipo de contenido.
DURACION_MIN_S = 20 * 60

_ISO_DUR = re.compile(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$")

# Señales de que el vídeo es de un sello o artista real, no de un canal de
# mezclas generadas. Es una heurística: se revisa a mano en el ranking.
_ARTISTA_REAL = re.compile(
    r"official (music )?video|official audio|\(official\)|full album|live (at|in|from)\b|"
    r"\bvevo\b|remaster",
    re.IGNORECASE,
)
# Recopilatorios de canciones reales: «90s R&B Mix», «Throwback…», o un título
# que enumera artistas («… | Usher, Keith Sweat, Maxwell»). Suben mucho en el
# ranking por visitas, pero no son mezclas generadas y no tienen estilo que copiar.
_RECOPILATORIO = re.compile(
    r"\b(19)?[5-9]0'?s\b|\b20[01]0'?s\b|throwback|old school|greatest hits|best of\b",
    re.IGNORECASE,
)
_LISTA_DE_ARTISTAS = re.compile(r"\|\s*[A-Z][^|,]{1,25},\s*[A-Z][^|,]{1,25},\s*[A-Z]")
# El canal declara que la música está hecha con IA. No filtra (muchos no lo dicen),
# pero es la mejor señal de que ese vídeo es el tipo de contenido que se busca.
_DECLARA_IA = re.compile(
    r"\bsuno\b|\budio\b|ai[- ](generated|assisted|music|created)|generated (with|by|using) ai|"
    r"artificial intelligence|\bIA\b|inteligencia artificial",
    re.IGNORECASE,
)


def duracion_s(iso: str | None) -> int:
    """`PT1H2M3S` → 3723. Cero si no se entiende (vídeo en directo, p. ej.)."""
    if not iso:
        return 0
    m = _ISO_DUR.match(iso)
    if not m:
        return 0
    d, h, mi, s = (int(x) if x else 0 for x in m.groups())
    return ((d * 24 + h) * 60 + mi) * 60 + s


def _fecha(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def dias_desde(publicado: str, ahora: datetime | None = None) -> float:
    """Días desde la publicación, con un mínimo de 1 para no dividir por casi cero."""
    ahora = ahora or datetime.now(timezone.utc)
    return max(1.0, (ahora - _fecha(publicado)).total_seconds() / 86400)


def motivo_descarte(video: dict) -> str | None:
    """Por qué un vídeo no entra en el ranking, o None si entra.

    `video` es la forma aplanada que guarda el script (ver `aplanar`).
    """
    if video.get("en_directo"):
        return "directo"
    if video["duracion_s"] < DURACION_MIN_S:
        return "corto"
    if video["canal"].endswith(" - Topic"):
        return "canal Topic"
    if _ARTISTA_REAL.search(video["titulo"]):
        return "artista real"
    if _RECOPILATORIO.search(video["titulo"]) or _LISTA_DE_ARTISTAS.search(video["titulo"]):
        return "recopilatorio"
    return None


def aplanar(item: dict, suscriptores: dict[str, int]) -> dict:
    """Un recurso de `videos.list` (snippet, statistics, contentDetails) → dict plano."""
    sn, st, cd = item["snippet"], item.get("statistics", {}), item.get("contentDetails", {})
    canal_id = sn["channelId"]
    return {
        "id": item["id"],
        "titulo": sn["title"],
        "descripcion": sn.get("description", ""),
        "tags": sn.get("tags", []),
        "canal": sn["channelTitle"],
        "canal_id": canal_id,
        "publicado": sn["publishedAt"],
        "en_directo": sn.get("liveBroadcastContent", "none") != "none",
        "duracion_s": duracion_s(cd.get("duration")),
        "visitas": int(st.get("viewCount", 0)),
        "likes": int(st.get("likeCount", 0)),
        "suscriptores": suscriptores.get(canal_id, 0),
        "declara_ia": bool(_DECLARA_IA.search(sn.get("description", ""))),
    }


def metricas(video: dict, ahora: datetime | None = None) -> dict:
    """Las tres medidas del ranking.

    - visitas: el éxito absoluto (favorece lo viejo y los canales grandes).
    - visitas_dia: la tendencia; corrige que lo viejo acumula más.
    - ratio_canal: visitas / suscriptores. Un vídeo que supera con mucho a su
      canal funcionó por el contenido y no por el tamaño del canal.
    """
    dias = dias_desde(video["publicado"], ahora)
    subs = video["suscriptores"]
    return {
        "visitas": video["visitas"],
        "visitas_dia": round(video["visitas"] / dias, 1),
        "ratio_canal": round(video["visitas"] / subs, 3) if subs else 0.0,
    }


def puntuar(videos: list[dict], ahora: datetime | None = None) -> list[dict]:
    """Ordena por la media de los percentiles de las tres métricas.

    Se usan percentiles y no valores crudos porque las tres viven en escalas
    sin relación (millones de visitas contra un ratio de 0,5), y así ninguna
    se come a las otras.
    """
    if not videos:
        return []
    filas = [v | metricas(v, ahora) for v in videos]
    n = len(filas)
    claves = ("visitas", "visitas_dia", "ratio_canal")
    for c in claves:
        orden = sorted(range(n), key=lambda i: filas[i][c])
        for pos, i in enumerate(orden):
            filas[i][f"p_{c}"] = pos / (n - 1) if n > 1 else 1.0
    for f in filas:
        f["puntuacion"] = round(sum(f[f"p_{c}"] for c in claves) / len(claves), 4)
    return sorted(filas, key=lambda f: f["puntuacion"], reverse=True)


# --- Extracción ---------------------------------------------------------------


class ReferenciaLLM(BaseModel):
    """Lo que el LLM saca de un título + descripción."""

    prompt_original: str = Field(
        "", description="El prompt de generación tal cual aparece en la descripción, o vacío"
    )
    genero: str
    subgenero: str = ""
    instrumentos: list[str] = []
    bpm: int | None = None
    tonalidad: str = ""
    ambiente: str = ""
    uso: str = ""
    idea_semilla: str


def normalizar_plantilla(texto: str) -> str:
    """Clave para agrupar el mismo prompt repetido en cientos de vídeos.

    Los canales cambian números, emojis y el orden de algún adjetivo entre un
    vídeo y otro; esto se queda con las palabras, ordenadas y sin acentos.
    """
    t = unicodedata.normalize("NFKD", texto.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    palabras = re.findall(r"[a-z]{3,}", t)
    return " ".join(sorted(set(palabras)))


def agrupar(fichas: list[dict]) -> list[dict]:
    """Junta las fichas que son la misma plantilla y suma sus visitas.

    Cada ficha trae `video` (el dict plano) y `ref` (un ReferenciaLLM en dict).
    Si no hay prompt original, la clave es género + instrumentos: dos vídeos
    del mismo canal con el mismo estilo cuentan como una sola referencia.
    """
    grupos: dict[tuple, dict] = {}
    for f in fichas:
        ref, video = f["ref"], f["video"]
        if ref["prompt_original"].strip():
            clave = ("prompt", normalizar_plantilla(ref["prompt_original"]))
        else:
            estilo = " ".join([ref["genero"], ref["subgenero"], *ref["instrumentos"]])
            clave = ("estilo", video["canal_id"], normalizar_plantilla(estilo))
        g = grupos.get(clave)
        if g is None:
            grupos[clave] = {
                **ref,
                "videos": 1,
                "visitas": video["visitas"],
                "canales": [video["canal"]],
                "ejemplo": {"id": video["id"], "titulo": video["titulo"],
                            "visitas": video["visitas"]},
            }
            continue
        g["videos"] += 1
        g["visitas"] += video["visitas"]
        if video["canal"] not in g["canales"]:
            g["canales"].append(video["canal"])
        if video["visitas"] > g["ejemplo"]["visitas"]:
            g["ejemplo"] = {"id": video["id"], "titulo": video["titulo"],
                            "visitas": video["visitas"]}
    return sorted(grupos.values(), key=lambda g: g["visitas"], reverse=True)
