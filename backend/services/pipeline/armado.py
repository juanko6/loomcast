"""Etapa 11 (versión estática) — ARMADO: video final con ffmpeg + Pillow.

El ffmpeg de brew viene sin libass/freetype (sin filtros de subtítulos), así
que los subtítulos se componen con Pillow: la línea de tiempo se corta en
cada frontera de escena o de bloque de subtítulo, se estampa el texto sobre
la imagen de la escena activa (1080x1920) y se concatenan los stills con sus
duraciones. Luego ffmpeg solo codifica: concat + voz → final.mp4.
"""
import re
import subprocess
from pathlib import Path

from ...config import PROYECTOS_DIR
from ...db import get_session
from ...models import avanzar_estado
from ...repositories import escenas as escenas_repo
from ...repositories import plantillas as plantillas_repo
from ...repositories import proyectos as proyectos_repo

ANCHO, ALTO = 1080, 1920
TAM_FUENTE = 88
MARGEN_INFERIOR = 420
ANCHO_MAX_TEXTO = 980

DIRS_FUENTES = [
    Path.home() / "Library/Fonts",
    Path("/System/Library/Fonts/Supplemental"),
    Path("/Library/Fonts"),
]


def _srt_a_bloques(srt: Path) -> list[dict]:
    def a_seg(t: str) -> float:
        h, m, resto = t.split(":")
        s, ms = resto.split(",")
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000

    bloques = re.findall(
        r"(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n(.+?)(?:\n\n|\n?$)",
        srt.read_text(),
        re.DOTALL,
    )
    return [
        {"start": a_seg(i), "end": a_seg(f), "texto": " ".join(t.split())}
        for i, f, t in bloques
    ]


def _buscar_fuente(nombre: str) -> Path | None:
    """Busca un archivo de fuente cuyo nombre normalizado contenga el pedido."""
    objetivo = re.sub(r"[^a-z0-9]", "", nombre.lower())
    candidatos = []
    for d in DIRS_FUENTES:
        if d.exists():
            candidatos += [p for p in d.iterdir() if p.suffix in (".ttf", ".otf")]
    for p in candidatos:
        if re.sub(r"[^a-z0-9]", "", p.stem.lower()) == objetivo:
            return p
    for p in candidatos:
        if objetivo in re.sub(r"[^a-z0-9]", "", p.stem.lower()):
            return p
    for respaldo in ("Arial Bold.ttf", "Helvetica.ttc"):
        p = Path("/System/Library/Fonts/Supplemental") / respaldo
        if p.exists():
            return p
    return None


def armar_video(proyecto_id: int) -> str:
    import soundfile as sf
    from PIL import Image, ImageDraw, ImageFont

    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        if p is None:
            raise ValueError(f"Proyecto {proyecto_id} no existe")
        escenas = [
            {"orden": e.orden, "t_inicio": e.t_inicio, "t_fin": e.t_fin}
            for e in escenas_repo.por_proyecto(s, proyecto_id)
        ]
        slug, plantilla = p.slug, p.plantilla

    base = PROYECTOS_DIR / slug
    if not escenas:
        raise ValueError("No hay escenas")
    faltantes = [
        e["orden"] for e in escenas
        if not (base / "imagenes" / f"{e['orden']:02d}.png").exists()
    ]
    if faltantes:
        raise ValueError(f"Faltan imágenes de las escenas {faltantes}")
    if not (base / "voz.wav").exists() or not (base / "subtitulos.srt").exists():
        raise ValueError("Faltan voz.wav o subtitulos.srt")

    pl = plantillas_repo.cargar(plantilla)
    sub_cfg = pl["subtitulos"]
    fuente_path = _buscar_fuente(sub_cfg.get("fuente", "Arial Bold"))
    if fuente_path is None:
        raise RuntimeError("No se encontró ninguna fuente para los subtítulos")

    bloques = _srt_a_bloques(base / "subtitulos.srt")
    dur_audio = sf.info(base / "voz.wav").duration

    # Cortes de la línea de tiempo: fronteras de escena y de subtítulo
    cortes = {0.0, dur_audio}
    for e in escenas:
        cortes.update((e["t_inicio"], e["t_fin"]))
    for b in bloques:
        cortes.update((b["start"], b["end"]))
    cortes = sorted(t for t in cortes if 0 <= t <= dur_audio)

    def escena_en(t: float) -> dict:
        for e in escenas:
            if e["t_inicio"] <= t < e["t_fin"]:
                return e
        return escenas[-1]

    def bloque_en(t: float) -> str | None:
        for b in bloques:
            if b["start"] <= t < b["end"]:
                return b["texto"]
        return None

    # Fondos 1080x1920 por escena (recorte centrado), cacheados
    armado_dir = base / "armado"
    armado_dir.mkdir(exist_ok=True)
    fondos: dict[int, Image.Image] = {}

    def fondo(orden: int) -> Image.Image:
        if orden not in fondos:
            img = Image.open(base / "imagenes" / f"{orden:02d}.png").convert("RGB")
            escala = max(ANCHO / img.width, ALTO / img.height)
            img = img.resize((round(img.width * escala), round(img.height * escala)))
            x = (img.width - ANCHO) // 2
            y = (img.height - ALTO) // 2
            fondos[orden] = img.crop((x, y, x + ANCHO, y + ALTO))
        return fondos[orden]

    color = sub_cfg.get("color", "#FFFFFF")
    borde = sub_cfg.get("borde", "#000000")

    def estampar(img: Image.Image, texto: str) -> Image.Image:
        img = img.copy()
        draw = ImageDraw.Draw(img)
        tam = TAM_FUENTE
        while tam > 40:
            font = ImageFont.truetype(str(fuente_path), tam)
            caja = draw.textbbox((0, 0), texto, font=font, stroke_width=6)
            if caja[2] - caja[0] <= ANCHO_MAX_TEXTO:
                break
            tam -= 6
        x = (ANCHO - (caja[2] - caja[0])) // 2 - caja[0]
        y = ALTO - MARGEN_INFERIOR - (caja[3] - caja[1])
        draw.text(
            (x, y), texto, font=font, fill=color,
            stroke_width=6, stroke_fill=borde,
        )
        return img

    # Un still por tramo; se reutiliza si (escena, texto) se repite
    lineas = []
    stills: dict[tuple[int, str | None], str] = {}
    for i in range(len(cortes) - 1):
        t0, t1 = cortes[i], cortes[i + 1]
        if t1 - t0 < 0.01:
            continue
        e = escena_en(t0)
        texto = bloque_en(t0 + 0.005)
        clave = (e["orden"], texto)
        if clave not in stills:
            nombre = f"{len(stills):03d}.png"
            img = fondo(e["orden"])
            if texto:
                img = estampar(img, texto)
            img.save(armado_dir / nombre)
            stills[clave] = nombre
        lineas.append(f"file 'armado/{stills[clave]}'")
        lineas.append(f"duration {t1 - t0:.3f}")
    lineas.append(f"file 'armado/{stills[clave]}'")
    (base / "escenas_concat.txt").write_text("\n".join(lineas) + "\n")

    resultado = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y",
         "-f", "concat", "-safe", "0", "-i", "escenas_concat.txt",
         "-i", "voz.wav",
         "-vf", "fps=30",
         "-c:v", "libx264", "-preset", "medium", "-crf", "18",
         "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "192k",
         "-shortest", "final.mp4"],
        cwd=base,
        capture_output=True,
        text=True,
    )
    if resultado.returncode != 0:
        raise RuntimeError(f"ffmpeg falló: {resultado.stderr[-800:]}")

    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        avanzar_estado(p, "FINAL")
        s.commit()
    return (
        f"Video final armado: {len(escenas)} escenas, {len(stills)} cuadros "
        f"compuestos, {dur_audio:.1f}s → final.mp4"
    )
