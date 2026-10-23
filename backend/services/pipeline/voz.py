"""Etapa 4 — VOZ: sintetiza la narración por tramos y aplica atempo.

Un guion se parte en **tramos** (ver `guiones_repo.tramos`): el narrador lleva
la historia y, si la plantilla usa el formato de líneas atribuidas, cada
personaje del reparto dice las suyas con su propia voz del banco. Los tramos se
sintetizan por separado y se unen con un silencio corto; después atempo →
voz.wav / voz.mp3.

Los formatos de guion de siempre (frases y narración continua) devuelven **un
solo tramo** con el texto completo, así que para ellos esta etapa hace la misma
llamada única que antes: la voz por personaje no cambia lo que ya sale bien. Y
los tramos contiguos que acaban en la misma voz se unen (`_unir_misma_voz`), con
lo que un guion de líneas cuyo reparto todavía no tiene voces también vuelve a
ser una sola llamada.

Dos modos de narración:

- "clon" (por defecto): clona la voz elegida del banco con el modelo Base
  (generate_voice_clone). Reproduce el timbre del ref pero sin control de
  emoción; requiere proyecto.voz.
- "design": narra con VoiceDesign usando el `instruct` de la plantilla como
  guía de entrega (tono, ritmo, intención). No usa el banco; la voz la diseña
  el modelo desde la descripción. Experimental (más expresivo, identidad menos
  estable entre vídeos).

**Los tramos se agrupan por modelo y el modelo se carga una vez por grupo**, no
una vez por tramo: en esta máquina cargar Qwen3-TTS cuesta más que sintetizar un
tramo corto y el modelo no cabe dos veces en la memoria unificada. Como mucho se
cargan dos (VoiceDesign para el narrador en modo expresivo y Base para los
clones), uno después del otro.
"""
import json

import numpy as np

from ... import parada, procesos
from ...clients import tts
from ...config import PROYECTOS_DIR
from ...db import get_session
from ...models import avanzar_estado
from ...repositories import guiones as guiones_repo
from ...repositories import personajes as personajes_repo
from ...repositories import plantillas as plantillas_repo
from ...repositories import proyectos as proyectos_repo
from ...repositories import voces as voces_repo
from .. import progreso
from . import crear_voz

# Silencio entre tramos: el aire que deja una persona al pasar de narrar a que
# hable otro. Sin él los dos tramos se pegan y suena a corte de edición.
#
# No llega a PAUSA_CORTE_S (0,5 s en subtitulos.py) a propósito, y no hace
# falta: cada tramo acaba en punto, interrogación o puntos suspensivos, así que
# el bloque de subtítulos ya corta ahí por puntuación. Alargarlo hasta forzar el
# corte por pausa solo metería segundos de silencio en un vídeo de 45.
PAUSA_S = 0.3


def _voces_del_reparto(s, proyecto_id: int) -> dict[str, tuple[str, str]]:
    """{CLAVE: (slug, ref_text)} de los personajes con voz del banco utilizable.

    Un personaje cuya voz todavía se está generando, falló o perdió su clip no
    entra: sus líneas las dirá la voz del narrador, que es peor que su voz pero
    mucho mejor que un hueco en la narración.
    """
    out = {}
    for x in personajes_repo.por_proyecto(s, proyecto_id):
        if not x.voz:
            continue
        v = voces_repo.por_slug(s, x.voz)
        if v is None or v.estado != "lista" or not voces_repo.ruta_ref(v.slug).exists():
            continue
        out[x.clave] = (v.slug, v.ref_text)
    return out


def _olvidar(proyecto_id: int, sueltas: list[tuple[str, int]]) -> None:
    """Borra del banco las voces que se quedaron a medias y desasigna al dueño.

    Una voz a medio escribir (falló, o se paró la etapa) no puede quedarse
    pegada al personaje: `_voces_del_reparto` la descartaría por no estar lista
    —así que sus líneas las diría el narrador igual— pero el hueco ya no
    estaría vacío y la siguiente pasada no volvería a intentarlo. Mejor dejarlo
    como estaba y que la próxima vez se le escriba de nuevo.
    """
    if not sueltas:
        return
    with get_session() as s:
        porclave = {x.clave: x for x in personajes_repo.por_proyecto(s, proyecto_id)}
        for clave, voz_id in sueltas:
            personaje = porclave.get(clave)
            if personaje is not None:
                personaje.voz = ""
            fila = voces_repo.obtener(s, voz_id)
            if fila is not None:
                voces_repo.borrar(s, fila)
        s.commit()


def _escribir_voces_que_faltan(
    proyecto_id: int, claves: set[str], voces_reparto: dict[str, tuple[str, str]]
) -> tuple[dict[str, tuple[str, str]], list[str]]:
    """Le escribe su voz a cada personaje que habla y todavía no tiene ninguna.

    Es lo que hace que un guion de líneas se oiga a varias voces sin tener que
    pulsar nada. La voz sale de la **ficha** del personaje, que es de donde sale
    también su retrato: dice la edad aparente, el género y el aire, que es lo
    que decide el timbre. Nace en el banco como cualquier otra —se escucha, se
    reutiliza y se borra desde el mismo sitio— y queda asignada, así que
    regenerar la narración no vuelve a escribirla.

    Quien no tenga ficha, o ya tenga voz aunque esté a medias, se queda como
    está: sus líneas las dirá el narrador, que es peor que su voz pero mucho
    mejor que un hueco.

    El VoiceDesign se carga **una vez para todas**: lo caro es cargarlo, no
    sintetizar ocho segundos, y en esta máquina no caben dos.

    Devuelve las recién escritas ({CLAVE: (slug, ref_text)}) y lo que haya que
    contar en el log.
    """
    # El import va aquí dentro: `services/voces` encola jobs, o sea importa la
    # cola, que es quien importa esta etapa. A nivel de módulo el ciclo sería
    # real.
    from .. import voces as voces_service

    pendientes: list[tuple[str, int, str]] = []
    with get_session() as s:
        for x in personajes_repo.por_proyecto(s, proyecto_id):
            if x.clave not in claves or x.clave in voces_reparto:
                continue
            if x.voz:
                # Tiene voz y no está entre las utilizables: o se está
                # generando todavía —cosa de otro job, y se respeta— o falló.
                # Una que falló no suena y además tapa el hueco, así que se
                # borra y se le escribe otra.
                fila = voces_repo.por_slug(s, x.voz)
                if fila is not None and fila.estado != "error":
                    continue
                if fila is not None:
                    voces_repo.borrar(s, fila)
                x.voz = ""
            if not (x.ficha or "").strip():
                continue
            nombre = (x.nombre or x.clave).strip()
            creada = voces_service.registrar_para_personaje(
                nombre,
                voces_service.instruct_desde_ficha(
                    nombre, x.ficha, x.tipo or "persona"
                ),
            )
            x.voz = creada["slug"]
            pendientes.append((x.clave, creada["voz_id"], creada["slug"]))
        s.commit()
    if not pendientes:
        return {}, []

    nuevas: dict[str, tuple[str, str]] = {}
    avisos: list[str] = []
    progreso.lote(0, len(pendientes), "voz del reparto")
    # La carga va dentro del try: si es ella la que falla, las filas recién
    # creadas también hay que recogerlas.
    modelo = None
    try:
        modelo = tts.cargar_modelo(tts.MODELO_DESIGN)
        for clave, voz_id, slug in pendientes:
            parada.comprobar(f"antes de escribirle la voz a {clave}")
            try:
                crear_voz.sintetizar_ref(modelo, voz_id)
            except parada.Parado:
                raise
            except Exception as e:
                avisos.append(f"{clave}: {e}")
                continue
            with get_session() as s:
                nuevas[clave] = (slug, voces_repo.obtener(s, voz_id).ref_text)
            progreso.lote(len(nuevas) + len(avisos), len(pendientes), "voz del reparto")
    finally:
        # `modelo = None` antes de liberar, como en el bucle de abajo.
        modelo = None
        tts.liberar()
        _olvidar(proyecto_id, [(c, i) for c, i, _ in pendientes if c not in nuevas])
    return nuevas, avisos


def _etiqueta(claves: list[str]) -> str:
    """Cómo se nombra un tramo en el log: su dueño, o los que se unieron."""
    return "+".join(dict.fromkeys(c or "narrador" for c in claves))


def _unir_misma_voz(crudos, plan):
    """Une los tramos contiguos que acaban en la misma voz.

    Hace falta porque un personaje sin voz propia dice sus líneas con la del
    narrador: partir ahí no cambiaría el timbre, solo cortaría la prosodia y
    pagaría otra llamada al modelo. Pasa entero la primera vez que se genera la
    voz de un guion con líneas, porque el reparto se fija en un paso posterior y
    todavía no hay nadie: ese caso vuelve así a ser la llamada única de siempre.

    Devuelve [(claves, texto, asignación)] en orden.
    """
    tramos: list[tuple[list[str], str, tuple[str, str]]] = []
    for (clave, texto), asignacion in zip(crudos, plan):
        if tramos and tramos[-1][2] == asignacion:
            claves, previo, _ = tramos[-1]
            tramos[-1] = (claves + [clave], f"{previo} {texto}", asignacion)
        else:
            tramos.append(([clave], texto, asignacion))
    return tramos


def _por_modelo(plan: list[tuple[str, str]]) -> list[tuple[str, list[int]]]:
    """Agrupa los índices de los tramos por el modelo que los sintetiza.

    Conserva el orden de primera aparición para que el log y la carga sean
    deterministas; el audio se recompone después por índice, así que agrupar no
    reordena nada de lo que se oye.
    """
    grupos: dict[str, list[int]] = {}
    for i, (tipo, _) in enumerate(plan):
        repo = tts.MODELO_DESIGN if tipo == "design" else tts.MODELO_BASE
        grupos.setdefault(repo, []).append(i)
    return list(grupos.items())


def _unir(pistas: list[np.ndarray], sr: int) -> np.ndarray:
    """Concatena los tramos con PAUSA_S de silencio entre ellos.

    Con un solo tramo devuelve el audio tal cual, sin añadirle nada: es el caso
    de los dos formatos de guion que ya estaban, y su salida tiene que ser la
    de siempre.
    """
    if len(pistas) == 1:
        return pistas[0]
    silencio = np.zeros(int(sr * PAUSA_S), dtype=np.float32)
    trozos: list[np.ndarray] = []
    for i, pista in enumerate(pistas):
        if i:
            trozos.append(silencio)
        trozos.append(pista)
    return np.concatenate(trozos)


def generar_voz(proyecto_id: int, modo: str = "clon", instruct: str | None = None) -> str:
    import soundfile as sf

    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        if p is None:
            raise ValueError(f"Proyecto {proyecto_id} no existe")
        guion_row = guiones_repo.ultimo(s, proyecto_id)
        if guion_row is None:
            raise ValueError("El proyecto no tiene guion todavía")
        slug, plantilla = p.slug, p.plantilla
        voz_slug = ref_text = None
        if modo != "design":  # modo clon: necesita una voz del banco lista
            if not p.voz:
                raise ValueError("Selecciona una voz del banco antes de generar la voz")
            voz = voces_repo.por_slug(s, p.voz)
            if voz is None or voz.estado != "lista":
                raise ValueError(f"La voz '{p.voz}' no está disponible")
            voz_slug, ref_text = voz.slug, voz.ref_text
        voces_reparto = _voces_del_reparto(s, proyecto_id)

    g = json.loads(guion_row.contenido)
    crudos = guiones_repo.tramos(g)
    if not crudos:
        raise ValueError("El guion no tiene nada que narrar")

    # Quien habla y todavía no tiene voz la recibe ahora, escrita desde su
    # ficha. Es lo que convierte un guion de líneas en varias voces sin tener
    # que pulsar nada; antes de esto el episodio entero salía con la del
    # narrador, porque nadie le había elegido voz a nadie.
    nuevas, avisos_voces = _escribir_voces_que_faltan(
        proyecto_id, {clave for clave, _ in crudos if clave}, voces_reparto
    )
    voces_reparto = {**voces_reparto, **nuevas}

    pl = plantillas_repo.cargar(plantilla)
    ritmo, language = pl["ritmo"], pl["voz"]["language"]

    base_dir = PROYECTOS_DIR / slug
    base_dir.mkdir(parents=True, exist_ok=True)

    # Las referencias de clonado que se van a usar, comprobadas antes de cargar
    # nada: un ref que falta es un error de la etapa, no media carga de modelo.
    refs: dict[str, tuple[object, str]] = {}
    if voz_slug:
        ref_path = voces_repo.ruta_ref(voz_slug)
        if not ref_path.exists():
            raise ValueError(f"Falta el clip de referencia de la voz '{voz_slug}'")
        refs[voz_slug] = (ref_path, ref_text)
    for slug_voz, texto_ref in voces_reparto.values():
        refs[slug_voz] = (voces_repo.ruta_ref(slug_voz), texto_ref)

    if modo == "design":
        # Prioridad: instruct de la UI > el que sugirió el guion para esta
        # historia > el de la plantilla (fallback).
        instruct = (
            (instruct or "").strip()
            or (g.get("voz_instruct") or "").strip()
            or pl["voz"]["instruct"]
        )
        narrador: tuple[str, str] = ("design", instruct)
        etiqueta = "diseñada (VoiceDesign, estilo de la plantilla)"
    else:
        narrador = ("clon", voz_slug)
        etiqueta = f"clon '{voz_slug}'"

    # Quién dice cada tramo. Un personaje sin voz utilizable cae en la del
    # narrador: la narración entera importa más que el timbre de una línea.
    tramos = _unir_misma_voz(crudos, [
        ("clon", voces_reparto[clave][0]) if clave in voces_reparto else narrador
        for clave, _ in crudos
    ])
    plan = [asignacion for _, _, asignacion in tramos]

    # Último punto donde esta etapa se puede cortar si el guion es de un solo
    # tramo: la síntesis de uno es una sola llamada a PyTorch sin puntos de
    # control. Con varios tramos se corta además entre tramo y tramo (ver
    # SIN_CORTE en services/cancelacion.py).
    parada.comprobar("antes de sintetizar la voz")

    pistas: dict[int, np.ndarray] = {}
    fallos: list[str] = []
    sr = None
    progreso.lote(0, len(tramos), "tramo")
    for repo, indices in _por_modelo(plan):
        modelo = tts.cargar_modelo(repo)
        try:
            clones: dict[str, object] = {}
            for i in indices:
                parada.comprobar(f"quedaban {len(tramos) - len(pistas)} tramos")
                texto = tramos[i][1]
                try:
                    tipo, dato = plan[i]
                    if tipo == "design":
                        wavs, sr = modelo.generate_voice_design(
                            text=texto,
                            language=language,
                            instruct=dato,
                            max_new_tokens=tts.tope_tokens(texto),
                        )
                    else:
                        if dato not in clones:
                            ruta, texto_ref = refs[dato]
                            ref, ref_sr = sf.read(ruta, dtype="float32")
                            clones[dato] = modelo.create_voice_clone_prompt(
                                ref_audio=(ref, ref_sr), ref_text=texto_ref
                            )
                        wavs, sr = modelo.generate_voice_clone(
                            text=texto,
                            language=language,
                            voice_clone_prompt=clones[dato],
                            max_new_tokens=tts.tope_tokens(texto),
                        )
                    pistas[i] = np.asarray(wavs[0], dtype=np.float32)
                except parada.Parado:
                    raise
                except Exception as e:
                    # Un tramo que falla no tira la narración entera: con el
                    # formato de líneas son muchas llamadas al modelo y perder
                    # las veinte buenas por la mala es el peor resultado
                    # posible. El tramo se queda fuera del audio, el log dice
                    # cuál y los subtítulos salen de lo que de verdad se oye.
                    fallos.append(f"tramo {i + 1} ({_etiqueta(tramos[i][0])}): {e}")
                progreso.lote(len(pistas) + len(fallos), len(tramos), "tramo")
        finally:
            # `modelo = None` y no `tts.liberar(modelo)`: la referencia que hay
            # que soltar es esta, la del que llama (ver `tts.liberar`).
            modelo = None
            tts.liberar()

    if not pistas:
        raise ValueError(
            "No se pudo sintetizar ningún tramo de la narración: "
            + "; ".join(fallos)
        )

    sf.write(base_dir / "voz_raw.wav", _unir([pistas[i] for i in sorted(pistas)], sr), sr)

    atempo = ritmo.get("atempo", 1.0)
    procesos.ejecutar(
        ["ffmpeg", "-loglevel", "error", "-y", "-i", str(base_dir / "voz_raw.wav"),
         "-filter:a", f"atempo={atempo}", str(base_dir / "voz.wav")],
        timeout=procesos.CORTO_S, que="ffmpeg (atempo)", check=True,
    )
    procesos.ejecutar(
        ["ffmpeg", "-loglevel", "error", "-y", "-i", str(base_dir / "voz.wav"),
         "-b:a", "192k", str(base_dir / "voz.mp3")],
        timeout=procesos.CORTO_S, que="ffmpeg (mp3)", check=True,
    )

    dur = sf.info(base_dir / "voz.wav").duration
    with get_session() as s:
        p = proyectos_repo.obtener(s, proyecto_id)
        avanzar_estado(p, "VOZ")
        s.commit()

    log = f"Voz {etiqueta}: {dur:.1f}s (atempo {atempo})"
    if len(tramos) > 1:
        propias = sorted({c for c, _ in crudos if c in voces_reparto})
        log += f", {len(pistas)} de {len(tramos)} tramos"
        if propias:
            log += f"; con voz propia: {', '.join(propias)}"
    if nuevas:
        log += f"\nVoz escrita desde su ficha para: {', '.join(sorted(nuevas))}"
    if avisos_voces:
        log += ("\n\nPersonajes a los que no se les pudo escribir la voz "
                "(los narra la voz del proyecto):\n" + "\n".join(avisos_voces))
    if fallos:
        log += "\n\nTramos que fallaron y no están en el audio:\n" + "\n".join(fallos)
    return log
