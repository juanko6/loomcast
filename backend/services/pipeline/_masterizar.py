"""Masterizado de las pistas de música con ffmpeg.

ACE-Step entrega el audio crudo y con dos defectos medidos sobre las 25 pistas
que ya había en la biblioteca:

1. **El volumen baila y los picos van pegados al techo.** Cada pista sale a un
   nivel distinto; las primeras generaciones salían a ~-17 LUFS con picos reales
   de 0,0 a 0,1 dBTP, es decir, distorsionando.

2. **La imagen estéreo se rompe en una pista de cada dos.** En 7 de las 16 de la
   sección de Música el canal lateral (la diferencia L-R) estaba al mismo nivel
   que el central (la suma L+R) o por encima, cuando en una mezcla sana el
   central saca al lateral entre 3 y 12 dB. En la peor —la 22, un folk
   acústico— el lateral iba 0,9 dB POR ENCIMA, con la correlación L/R en -0,10.
   Eso no es "estéreo ancho": son dos canales descorrelacionados, y al sumarse a
   mono —móvil, portátil, media ruta de reproducción de YouTube— se cancelan.
   La pista 34 perdía 5,8 dB al sumarse.

Tres pasos, los dos primeros estándar de emisión:

  - **corrección medio/lado** baja el canal lateral hasta que el central vuelve
    a mandar. Es lo primero porque cambia los picos, y lo que loudnorm mida
    después tiene que ser ya el audio corregido.
  - **loudnorm** lleva el volumen percibido (LUFS, la unidad de EBU R128) a un
    valor fijo, para que todas las pistas suenen igual de altas entre sí.
  - **limitador de pico real** (el `TP` de loudnorm) impide que los picos lleguen
    al techo, que es lo que produce el crujido.

loudnorm se hace en DOS PASADAS a propósito: la primera mide la pista y la
segunda aplica la corrección con esas medidas. En una sola pasada trabaja a
ciegas, comprime de más y aplasta la dinámica, que es justo lo que no queremos
en música.

No toca la mezcla más allá de eso: no separa instrumentos ni reequilibra nada, y
**no inventa agudos**. Las pistas apagadas (la 21 mide -58 dB en la banda de
8-16 kHz frente a los -17,8 dB de la 12) lo están porque el modelo devolvió un
arreglo sin brillo, y lo que no está no se puede ecualizar: eso se arregla en el
brief del LLM, en `prompts/musica_*.md`, no aquí.
"""
import json
from pathlib import Path

from ... import procesos
from ...config import (
    MUSICA_LUFS,
    MUSICA_MEDIO_LADO_MIN,
    MUSICA_MEDIO_LADO_OBJETIVO,
    MUSICA_TRUE_PEAK,
)


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


def _medir_medio_lado(origen: Path) -> float | None:
    """dB que el canal central (L+R) le saca al lateral (L-R).

    `stereotools=mode=lr>ms` reescribe los dos canales como medio y lado, y
    astats da el RMS de cada uno: la diferencia es lo que buscamos. Los dos
    salen con la misma escala, así que la RESTA es exacta aunque el valor
    absoluto no sea el de la mezcla original.

    None si no se pudo medir; quien llama decide entonces no tocar el estéreo,
    que es lo conservador.
    """
    r = _correr(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(origen),
         "-af", "stereotools=mode=lr>ms,"
                "astats=metadata=1:reset=0:measure_overall=none:measure_perchannel=RMS_level",
         "-f", "null", "-"],
    )
    niveles = []
    for linea in r.stderr.splitlines():
        if "RMS level dB" in linea:
            try:
                niveles.append(float(linea.rsplit(":", 1)[1]))
            except ValueError:
                return None
    # Exactamente dos canales: medio y lado, en ese orden.
    if len(niveles) != 2:
        return None
    medio, lado = niveles
    return medio - lado


def _slev(origen: Path) -> tuple[float | None, float | None]:
    """Ganancia del canal lateral que hace falta, y el medio/lado medido.

    Devuelve (None, medido) cuando la pista ya está sana: no se toca, porque
    estrechar un estéreo que ya estaba bien es empeorarlo.
    """
    medido = _medir_medio_lado(origen)
    if medido is None or medido >= MUSICA_MEDIO_LADO_MIN:
        return None, medido
    # Lo que falta para llegar al objetivo, en veces de amplitud. El filtro
    # acota slev a [0.015625, 64]; se acota aquí también para no pasarle un
    # valor que rechace y tumbe la pasada entera.
    g = 10 ** ((medido - MUSICA_MEDIO_LADO_OBJETIVO) / 20)
    return max(0.015625, min(64.0, g)), medido


def _cadena(slev: float | None, loudnorm: str) -> str:
    """El filtro completo: primero el estéreo, luego el volumen."""
    pasos = []
    if slev is not None:
        pasos.append(f"stereotools=slev={slev:.6f}")
    pasos.append(loudnorm)
    return ",".join(pasos)


def _medir(origen: Path, slev: float | None) -> dict:
    """Primera pasada de loudnorm: mide y escupe las medidas en JSON por
    stderr. Mide SOBRE el estéreo ya corregido, porque bajar el lateral cambia
    los picos y el volumen percibido."""
    r = _correr(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(origen),
         "-af", _cadena(slev, f"loudnorm=I={MUSICA_LUFS}:TP={MUSICA_TRUE_PEAK}:"
                              "LRA=11:print_format=json"),
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
    slev, medio_lado = _slev(origen)
    m = _medir(origen, slev)
    medido = (
        f"measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
        f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:"
        f"offset={m['target_offset']}"
    )
    r = _correr(
        ["ffmpeg", "-hide_banner", "-nostats", "-y", "-i", str(origen),
         "-af", _cadena(slev, f"loudnorm=I={MUSICA_LUFS}:TP={MUSICA_TRUE_PEAK}:"
                              f"LRA=11:{medido}:linear=true"),
         # loudnorm trabaja por dentro a 192 kHz y en coma flotante. Sin estos
         # dos, el FLAC sale a 192 kHz y 24 bits: el doble de tamaño y ninguna
         # ventaja para una pista que acabará mezclada y recodificada. ffmpeg
         # aplica dither al bajar de bits.
         "-ar", "48000", "-sample_fmt", "s16", str(destino)],
    )
    if r.returncode != 0 or not destino.exists():
        raise MasterizarError(f"ffmpeg falló masterizando: {r.stderr[-300:]}")
    return {
        "lufs": float(m["input_i"]),
        "pico_dbtp": float(m["input_tp"]),
        "medio_lado": medio_lado,
        "estereo_corregido": slev is not None,
    }
