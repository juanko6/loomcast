"""Cortar en caliente el job que está corriendo.

Un job pendiente se cancela en la BD y el worker lo salta cuando le llega el
turno; eso no necesita nada de aquí. El que ya está corriendo es el difícil: el
hilo de la cola está bloqueado dentro del handler y hay que alcanzarlo desde el
hilo HTTP. Se corta por todas las vías por las que una etapa puede estar
esperando, porque cerrar solo una lo dejaría vivo:

  1. **ComfyUI** (imágenes, upscale, clips i2v, música): el trabajo corre dentro
     de ComfyUI y aquí solo se sondea su `/history`. Se le pide `/interrupt`, con
     lo que el prompt sube como fallido y la etapa sale.
  2. **Procesos externos** (ffmpeg, ESRGAN, RIFE): todos pasan por
     `backend/procesos.py`, que guarda el que está en marcha; se le manda
     SIGTERM y, si no muere, SIGKILL.
  3. **La bandera** (`backend/parada.py`), que miran los bucles por lotes entre
     elemento y elemento, el cliente del LLM entre trozos de la respuesta y el
     de Whisper entre segmentos. Es lo que corta las etapas que no hablan con
     ComfyUI ni lanzan un proceso: ideas, guion, metadatos, prompts de escena y
     subtítulos.

Lo único que no se puede cortar por dentro es **una** síntesis de voz
(Qwen3-TTS): es una sola llamada a PyTorch sin puntos de control. Lo que sí se
puede, desde la voz por personaje, es cortar **entre tramos**: la narración se
sintetiza tramo a tramo (el narrador y las líneas de cada personaje), así que
una parada pierde como mucho el tramo que estuviera sonando. Con los formatos de
guion de frases y de narración continua el guion es un solo tramo, y entonces
ese "como mucho" es toda la narración. Por eso `SIN_CORTE` sigue aquí pero habla
del tramo y no de la etapa: la UI tiene que avisar de lo que de verdad pasa, sin
prometer un corte que no hay ni asustar con uno más caro del que es (ver
`SIN_CORTE` abajo y web/.../BotonParar).
"""
from .. import parada, procesos
from ..clients import comfy

# Etapas con un trozo de trabajo que es una sola llamada bloqueante y no se
# puede partir: la parada las alcanza antes de empezar, entre trozos o al
# terminar, no a mitad de uno. Lo que dice cada entrada es **ese trozo**, porque
# es lo que se paga al pulsar parar, y es lo que enseña la UI y el log del job.
SIN_CORTE = {
    # La narración va por tramos y se corta entre ellos; lo que no se puede
    # cortar es el tramo en curso (con los guiones de un solo tramo, que son los
    # de las plantillas de hoy, ese tramo es la narración entera).
    "generar_voz": "el tramo de narración que se esté sintetizando",
    "crear_voz": "la síntesis de la voz",
    "clonar_voz": "la transcripción del clip de referencia",
}


def pedir(job_id: int) -> bool:
    """Pide parar ese job. Devuelve si era el que estaba corriendo.

    Si no lo era, no hay nada que cortar: o ya terminó, o está esperando turno y
    basta con su estado en la BD.
    """
    if not parada.marcar(job_id):
        return False
    # Fuera del lock de la bandera: las dos llamadas hablan por red o esperan a
    # un proceso, y el worker tiene que poder leerla mientras tanto.
    comfy.interrumpir()
    procesos.terminar_actual()
    return True
