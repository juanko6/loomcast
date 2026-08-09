"""Valores que acepta el nodo TextEncodeAceStepAudio1.5 de ComfyUI, y cómo
normalizar hacia ellos.

Vive aparte de `services/musica.py` porque lo necesitan los dos lados: el
servicio (valida lo que manda el usuario desde la API) y el pipeline (valida lo
que devuelve el LLM), y `services/musica.py` ya importa el pipeline, así que el
pipeline no puede importarlo de vuelta.

Importa acertar: `bpm`, `keyscale`, `timesignature` y `language` son combos
cerrados. Un valor fuera de lista no degrada la pista, hace fallar el prompt
entero en ComfyUI. Las listas se replican tal cual están en
`comfy_extras/nodes_ace.py`.
"""

BPM_MIN, BPM_MAX = 10, 300
TIMESIGS = ("2", "3", "4", "6")
RAICES = (
    "C", "C#", "Db", "D", "D#", "Eb", "E", "F", "F#", "Gb", "G", "G#",
    "Ab", "A", "A#", "Bb", "B",
)
KEYSCALES = tuple(
    f"{raiz} {calidad}" for calidad in ("major", "minor") for raiz in RAICES
)
IDIOMAS = (
    "ar", "az", "bg", "bn", "ca", "cs", "da", "de", "el", "en", "es", "fa",
    "fi", "fr", "he", "hi", "hr", "ht", "hu", "id", "is", "it", "ja", "ko",
    "la", "lt", "ms", "ne", "nl", "no", "pa", "pl", "pt", "ro", "ru", "sa",
    "sk", "sr", "sv", "sw", "ta", "te", "th", "tl", "tr", "uk", "ur", "vi",
    "yue", "zh", "unknown",
)

BPM_DEFECTO = 120
KEYSCALE_DEFECTO = "C major"
TIMESIG_DEFECTO = "4"
IDIOMA_DEFECTO = "es"


def normalizar_bpm(v) -> int:
    try:
        return max(BPM_MIN, min(BPM_MAX, int(v)))
    except (TypeError, ValueError):
        return BPM_DEFECTO


# Sinónimos con los que el LLM (o el usuario) puede escribir la calidad. "M" y
# "m" son sensibles a la caja, así que se consultan antes de bajar a minúsculas.
CALIDADES = {
    "major": "major", "maj": "major", "M": "major",
    "minor": "minor", "min": "minor", "m": "minor",
}


def _raiz(t: str) -> str | None:
    """Normaliza la nota: mayúscula la letra, minúscula el alterador ("C#", "Eb")."""
    r = t[:1].upper() + t[1:].lower().replace("♯", "#").replace("♭", "b")
    return r if r in RAICES else None


def normalizar_keyscale(v) -> str:
    """Devuelve la forma exacta del combo ("E minor") desde lo que escriba el
    usuario o devuelva el LLM.

    Es deliberadamente tolerante: acepta "e minor", "Eb MAJOR", "A-minor",
    "Am", "F#min", "C major scale". Caer al valor por defecto significa perder
    el conditioning de tonalidad, que es medio motivo de estar en 1.5, así que
    conviene apurar antes de rendirse.
    """
    if not isinstance(v, str):
        return KEYSCALE_DEFECTO
    tokens = v.replace("-", " ").replace("_", " ").split()

    # "A minor", "Eb MAJOR", "C major scale": nota y calidad por separado.
    if len(tokens) >= 2:
        raiz = _raiz(tokens[0])
        calidad = CALIDADES.get(tokens[1]) or CALIDADES.get(tokens[1].lower())
        if raiz and calidad:
            return f"{raiz} {calidad}"

    # "Am", "F#min", "Bbmaj": todo pegado en un token.
    if tokens:
        t = tokens[0]
        for corte in (2, 1):  # la raíz ocupa 2 caracteres ("C#") o 1 ("C")
            raiz, resto = _raiz(t[:corte]), t[corte:]
            calidad = CALIDADES.get(resto) or CALIDADES.get(resto.lower())
            if raiz and calidad:
                return f"{raiz} {calidad}"
        # Nota sola ("C", "Am" ya cubierto): mayor por convención.
        raiz = _raiz(t)
        if raiz:
            return f"{raiz} major"

    return KEYSCALE_DEFECTO


def normalizar_timesig(v) -> str:
    v = str(v).strip()
    return v if v in TIMESIGS else TIMESIG_DEFECTO


def normalizar_idioma(v) -> str:
    v = str(v).strip().lower()
    return v if v in IDIOMAS else IDIOMA_DEFECTO
