"""Mezcla de la música del proyecto por debajo de la narración, con ducking.

La usan los dos armados (estático y movimiento). Si el proyecto no tiene la
mezcla activada, no se toca nada de la cadena de audio de siempre: la voz se
mapea directa, como antes.

El ducking es `sidechaincompress`: la cama se comprime usando la VOZ como señal
de control, así que baja sola cuando se habla y vuelve a subir en los silencios.
Un `volume` fijo no sirve: o la música tapa la narración, o no se oye nunca.
"""
from pathlib import Path

from ...config import VIDEO_MUSICA_DB, VIDEO_MUSICA_FADE_S
from ...db import get_session
from ...repositories import musica as musica_repo
from ...repositories import proyectos as proyectos_repo
from . import musica as musica_pipeline

# Parámetros del ducking. Verificados a oído sobre narración en español:
#  - umbral bajo, porque la voz ya viene normalizada y no queremos que el
#    compresor espere a los picos;
#  - ataque corto para que la cama se aparte antes de la primera sílaba;
#  - release largo para que suba despacio entre frases y no "respire".
UMBRAL = 0.02
RATIO = 6
ATAQUE_MS = 20
RELEASE_MS = 400


class MusicaNoLista(ValueError):
    pass


def pista_a_mezclar(proyecto_id: int) -> Path | None:
    """Ruta de la pista que hay que mezclar, o None si este proyecto no mezcla.

    Si la mezcla está marcada pero la pista no existe o no tiene audio, falla en
    vez de armar un video en silencio: el usuario pidió música y un vídeo sin
    ella pasaría desapercibido hasta publicarlo.
    """
    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        if p is None or not p.musica_mezclar:
            return None
        if p.musica_id is None:
            raise MusicaNoLista(
                "La mezcla de música está activada pero el proyecto no tiene "
                "pista: genérala en el paso de Música o desactiva la mezcla"
            )
        m = musica_repo.obtener(s, p.musica_id)
        musica_id = p.musica_id
    if m is None:
        raise MusicaNoLista(
            f"La pista #{musica_id} del proyecto ya no existe; elige otra en el "
            "paso de Música o desactiva la mezcla"
        )
    ruta = musica_pipeline.ruta_audio(musica_id)
    if ruta is None:
        raise MusicaNoLista(
            f"La pista #{musica_id} aún no tiene audio generado: termina de "
            "generarla antes de armar el video con música"
        )
    return ruta


def cadena(idx_voz: int, idx_musica: int, dur_video: float, dur_musica: float) -> str:
    """Filtro de audio que deja la mezcla en [aout].

    - La cama se alarga con silencio (`apad`) si es más corta que el video, para
      que la mezcla no se corte antes de tiempo.
    - El fade de salida se coloca donde acaba la música de verdad, no al final
      del video: si la pista es más corta, el fade iría sobre el silencio y la
      música cortaría en seco.
    """
    fade = max(0.1, VIDEO_MUSICA_FADE_S)
    fin_musica = min(dur_musica, dur_video) if dur_musica else dur_video
    salida = max(0.0, fin_musica - fade)
    return ";".join([
        f"[{idx_musica}:a]apad,volume={VIDEO_MUSICA_DB:.1f}dB"
        f",afade=t=in:st=0:d={fade:.2f}"
        f",afade=t=out:st={salida:.3f}:d={fade:.2f}[cama]",
        f"[{idx_voz}:a]apad,asplit=2[vozmix][vozctrl]",
        f"[cama][vozctrl]sidechaincompress=threshold={UMBRAL}:ratio={RATIO}"
        f":attack={ATAQUE_MS}:release={RELEASE_MS}[camaduck]",
        # normalize=0: amix divide por el número de entradas si se le deja, y
        # eso bajaría la narración 6 dB solo por añadir música.
        "[vozmix][camaduck]amix=inputs=2:normalize=0[aout]",
    ])
