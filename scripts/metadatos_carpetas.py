"""Escribe `metadatos.md` (en inglés, listo para YouTube) en cada carpeta de mezcla.

Lee el reparto de `referencias/youtube/carpetas/carpetas.json` (lo hace
`agrupar_pistas.py`) y los textos de `referencias/youtube/metadatos.json`
(título, gancho, nombres de pista, tags por familia). Los capítulos salen de la
duración real de cada audio, en el orden de los archivos de la carpeta.

    ./.venv/bin/python scripts/metadatos_carpetas.py

Ojo: `agrupar_pistas.py` borra y rehace las carpetas, así que este script va
siempre después.
"""
import json
import sys
from pathlib import Path

import soundfile as sf

RAIZ = Path(__file__).resolve().parent.parent
REF = RAIZ / "referencias" / "youtube"
CARPETAS = REF / "carpetas"

# YouTube: tags hasta 500 caracteres en total, descripción hasta 5000.
MAX_TAGS = 500
MAX_DESCRIPCION = 5000


def reloj(seg: float) -> str:
    s = int(round(seg))
    h, m, s = s // 3600, s % 3600 // 60, s % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def duracion_texto(seg: float) -> str:
    m = int(round(seg / 60))
    if m < 60:
        return f"{m} minutes"
    h, m = divmod(m, 60)
    return f"{h} hour" + (f" {m} minutes" if m else "")


def tags_que_caben(tags: list[str]) -> list[str]:
    salida, total = [], 0
    for t in tags:
        coste = len(t) + (2 if salida else 0)
        if total + coste > MAX_TAGS:
            break
        salida.append(t)
        total += coste
    return salida


def render(meta: dict, fam: dict, archivos: list[Path]) -> tuple[str, str]:
    inicios, total = [], 0.0
    for archivo in archivos:
        inicios.append(total)
        total += sf.info(str(archivo)).duration
    capitulos = [f"{reloj(t)} {nombre}" for t, nombre in zip(inicios, meta["tracks"])]

    descripcion = "\n".join([
        meta["hook"],
        "",
        f"⏱ {duracion_texto(total)} · {len(archivos)} original instrumentals",
        "",
        "✨ Perfect for:",
        *[f"• {p}" for p in fam["perfect_for"]],
        "",
        "🎵 Tracklist",
        *capitulos,
        "",
        "🔔 Subscribe and turn on notifications for a new mix every week.",
        "💬 Tell us in the comments where you're listening from and which track is your favorite.",
        "",
        "All music in this mix is original and was created with the help of AI tools.",
        "",
        " ".join(fam["hashtags"]),
    ])
    tags = tags_que_caben(fam["tags"])

    md = "\n".join([
        f"# {meta['title']}",
        "",
        "## Title",
        "",
        meta["title"],
        "",
        "### Alternative titles (A/B test)",
        "",
        *[f"- {a}" for a in meta["alt_titles"]],
        "",
        "## Thumbnail text",
        "",
        meta["thumbnail_text"],
        "",
        "## Description",
        "",
        "```",
        descripcion,
        "```",
        "",
        "## Tags",
        "",
        "```",
        ", ".join(tags),
        "```",
        "",
    ])
    return md, descripcion


def main() -> None:
    reparto = json.loads((CARPETAS / "carpetas.json").read_text())
    textos = json.loads((REF / "metadatos.json").read_text())
    fallos = 0
    for c in reparto:
        nombre = c["carpeta"]
        meta = textos["carpetas"].get(nombre)
        d = CARPETAS / nombre
        archivos = sorted(d.glob("[0-9][0-9] - *.flac"))
        if meta is None or len(meta["tracks"]) != len(archivos):
            print(f"  ✗ {nombre}: {len(archivos)} pistas y "
                  f"{0 if meta is None else len(meta['tracks'])} nombres", file=sys.stderr)
            fallos += 1
            continue
        md, descripcion = render(meta, textos["_familias"][c["familia"]], archivos)
        if len(descripcion) > MAX_DESCRIPCION:
            print(f"  ✗ {nombre}: descripción de {len(descripcion)} caracteres", file=sys.stderr)
            fallos += 1
            continue
        (d / "metadatos.md").write_text(md)
        print(f"  ✓ {nombre}: {len(archivos)} pistas, descripción de {len(descripcion)} caracteres")
    sys.exit(1 if fallos else 0)


if __name__ == "__main__":
    main()
