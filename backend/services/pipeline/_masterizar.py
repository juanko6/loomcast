"""Masterizado de las pistas de música con ffmpeg.

ACE-Step entrega el audio crudo: cada pista sale a un volumen distinto y con los
picos pegados al techo digital. Medido sobre las primeras generaciones, salían a
~-17 LUFS con picos reales de 0,0 a 0,1 dBTP, es decir, distorsionando.

Dos pasos, los dos estándar de emisión:

  - **loudnorm** lleva el volumen percibido (LUFS, la unidad de EBU R128) a un
    valor fijo, para que todas las pistas suenen igual de altas entre sí.
  - **limitador de pico real** (el `TP` de loudnorm) impide que los picos lleguen
    al techo, que es lo que produce el crujido.

Se hace en DOS PASADAS a propósito: la primera mide la pista y la segunda aplica
la corrección con esas medidas. En una sola pasada loudnorm trabaja a ciegas,
comprime de más y aplasta la dinámica, que es justo lo que no queremos en música.

No toca la mezcla: no separa instrumentos ni reequilibra nada. Si un arreglo
suena embarullado, eso viene del modelo y se arregla en el prompt.
"""
import json
from pathlib import Path

from ... import procesos
from ...config import MUSICA_LUFS, MUSICA_TRUE_PEAK


class MasterizarError(RuntimeError):
    pass


def _correr(cmd: list[str]):
    """ffmpeg con tope; un cuelgue se reporta como MasterizarError para que la
    pista se entregue sin masterizar en vez de dejar el job colgado."""
    try:
        return procesos.ejecutar(cmd, timeout=procesos.MASTERIZADO_S,
                                 que="ffmpeg (masterizado)", capture_output=True, text=True)
    except procesos.ProcesoTimeout as e:
        raise MasterizarError(str(e)) from e


def _medir(origen: Path) -> dict:
    """Primera pasada: loudnorm mide y escupe las medidas en JSON por stderr."""
    r = _correr(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(origen),
         "-af", f"loudnorm=I={MUSICA_LUFS}:TP={MUSICA_TRUE_PEAK}:LRA=11:print_format=json",
         "-f", "null", "-"],
    )
    # El JSON va al final de stderr, entre el log de ffmpeg y la línea de
    # resumen que ffmpeg imprime después: hay que acotarlo por los dos lados.
    inicio, fin = r.stderr.rfind("{"), r.stderr.rfind("}")
    if inicio == -1 or fin < inicio:
        raise MasterizarError(f"ffmpeg no devolvió medidas de loudnorm: {r.stderr[-300:]}")
    try:
        return json.loads(r.stderr[inicio:fin + 1])
    except json.JSONDecodeError as e:
        raise MasterizarError(f"medidas de loudnorm ilegibles: {e}") from e


def masterizar(origen: Path, destino: Path) -> dict:
    """Normaliza `origen` y escribe `destino`. Devuelve las medidas de la pista
    cruda, para poder decir de dónde venía."""
    m = _medir(origen)
    medido = (
        f"measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
        f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:"
        f"offset={m['target_offset']}"
    )
    r = _correr(
        ["ffmpeg", "-hide_banner", "-nostats", "-y", "-i", str(origen),
         "-af", f"loudnorm=I={MUSICA_LUFS}:TP={MUSICA_TRUE_PEAK}:LRA=11:{medido}:linear=true",
         # loudnorm trabaja por dentro a 192 kHz y en coma flotante. Sin estos
         # dos, el FLAC sale a 192 kHz y 24 bits: el doble de tamaño y ninguna
         # ventaja para una pista que acabará mezclada y recodificada. ffmpeg
         # aplica dither al bajar de bits.
         "-ar", "48000", "-sample_fmt", "s16", str(destino)],
    )
    if r.returncode != 0 or not destino.exists():
        raise MasterizarError(f"ffmpeg falló masterizando: {r.stderr[-300:]}")
    return {"lufs": float(m["input_i"]), "pico_dbtp": float(m["input_tp"])}
