"""Etapa 5 — SUBTITULOS: Whisper con timestamps por palabra → SRT.

Genera palabras.json (timestamps crudos, insumo de la etapa de escenas) y
subtitulos.srt con bloques cortos estilo shorts (máx N palabras, cortando
en puntuación fuerte o pausas largas).
"""
import json

from ...clients import stt
from ...config import PROYECTOS_DIR
from ...db import get_session
from ...repositories import plantillas as plantillas_repo
from ...repositories import proyectos as proyectos_repo
from ...models import avanzar_estado

PAUSA_CORTE_S = 0.5
FIN_FUERTE = ".?!…"


def _fmt_srt(t: float) -> str:
    ms = round(t * 1000)
    h, resto = divmod(ms, 3_600_000)
    m, resto = divmod(resto, 60_000)
    s, ms = divmod(resto, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _bloques(palabras: list[dict], max_palabras: int) -> list[dict]:
    bloques, actual = [], []
    for i, w in enumerate(palabras):
        actual.append(w)
        texto = w["word"].strip()
        gap_sig = (
            i + 1 < len(palabras)
            and palabras[i + 1]["start"] - w["end"] > PAUSA_CORTE_S
        )
        if (
            len(actual) >= max_palabras
            or (texto and texto[-1] in FIN_FUERTE)
            or gap_sig
        ):
            bloques.append(actual)
            actual = []
    if actual:
        bloques.append(actual)
    return [
        {
            "start": b[0]["start"],
            "end": b[-1]["end"],
            "texto": " ".join(w["word"].strip() for w in b),
        }
        for b in bloques
    ]


def generar_subtitulos(proyecto_id: int) -> str:
    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        if p is None:
            raise ValueError(f"Proyecto {proyecto_id} no existe")
        slug, plantilla = p.slug, p.plantilla

    base_dir = PROYECTOS_DIR / slug
    voz = base_dir / "voz.wav"
    if not voz.exists():
        raise ValueError("No hay voz.wav; genera la voz primero")

    palabras = stt.transcribir(voz, palabras=True)["palabras"]
    if not palabras:
        raise ValueError("Whisper no devolvió palabras")

    with open(base_dir / "palabras.json", "w") as f:
        json.dump(palabras, f, ensure_ascii=False, indent=1)

    pl = plantillas_repo.cargar(plantilla)
    max_palabras = pl["subtitulos"].get("max_palabras_por_bloque", 3)
    bloques = _bloques(palabras, max_palabras)

    srt = "\n".join(
        f"{n}\n{_fmt_srt(b['start'])} --> {_fmt_srt(b['end'])}\n{b['texto']}\n"
        for n, b in enumerate(bloques, 1)
    )
    (base_dir / "subtitulos.srt").write_text(srt)

    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        avanzar_estado(p, "SUBTITULOS")
        s.commit()
    return f"{len(bloques)} bloques de subtítulos ({len(palabras)} palabras)"
