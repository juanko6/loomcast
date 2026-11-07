"""Encuentra los vídeos de mezclas de música (jazz, soul, groove…) que más
funcionan en YouTube y extrae de sus descripciones el estilo o prompt que usan.

Uso:
  export YOUTUBE_API_KEY=...        # clave de la YouTube Data API v3
  ./.venv/bin/python scripts/referencias_youtube.py descubrir [--consultas N] [--por-canal N]
  ./.venv/bin/python scripts/referencias_youtube.py extraer --top 50

Entradas (las crea `descubrir` con valores de ejemplo si no existen):
  referencias/youtube/consultas.txt   una búsqueda por línea
  referencias/youtube/canales.txt     handles semilla (@groovenest) o IDs UC…

Salidas, en referencias/youtube/ (fuera de git):
  videos.jsonl       todos los vídeos que pasan los filtros, con métricas
  ranking.csv        lo mismo ordenado por puntuación, para revisar a mano
  descartes.csv      lo que se quedó fuera y por qué
  fichas.jsonl       lo que el LLM sacó de cada vídeo (incremental)
  biblioteca.json    fichas agrupadas por plantilla, ordenadas por visitas
  informe.md         géneros, instrumentos y tempos que concentran visitas

Solo usa la API oficial. Cada respuesta se guarda en cache/, así que repetir
una ejecución no gasta cuota.
"""
import argparse
import csv
import hashlib
import json
import os
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.services import referencias_youtube as ry  # noqa: E402

DIR = ROOT / "referencias" / "youtube"
CACHE = DIR / "cache"
API = "https://www.googleapis.com/youtube/v3"
COSTE = {"search": 100}  # el resto de endpoints cuesta 1 unidad

CONSULTAS_EJEMPLO = """\
smooth jazz cafe music
jazz relaxing music for work and study
soul groove playlist
neo soul chill mix
funk groove instrumental mix
bossa nova cafe music
lofi jazz hip hop mix
late night jazz lounge
jazz saxophone relaxing music
música jazz para estudiar
"""
CANALES_EJEMPLO = """\
# Canales semilla: handle con @ o ID que empieza por UC. Uno por línea.
@GrooveNest
@ViraJazz
@JOYROOVE
@SoulLuxe
"""


class SinCuota(RuntimeError):
    pass


class YouTube:
    def __init__(self, clave: str, cuota: int):
        self.clave = clave
        self.cuota = cuota
        self.gastado = 0
        self.http = httpx.Client(timeout=30)
        CACHE.mkdir(parents=True, exist_ok=True)

    def get(self, recurso: str, **params) -> dict:
        clave_cache = hashlib.sha256(
            json.dumps([recurso, sorted(params.items())]).encode()
        ).hexdigest()[:24]
        f = CACHE / f"{recurso}-{clave_cache}.json"
        if f.exists():
            return json.loads(f.read_text())
        coste = COSTE.get(recurso, 1)
        if self.gastado + coste > self.cuota:
            raise SinCuota(f"Se acaba la cuota de esta ejecución ({self.gastado}/{self.cuota})")
        r = self.http.get(f"{API}/{recurso}", params=params | {"key": self.clave})
        self.gastado += coste
        if r.status_code >= 400:
            raise RuntimeError(f"{recurso} → {r.status_code}: {r.text[:400]}")
        datos = r.json()
        f.write_text(json.dumps(datos))
        return datos


def _leer_lista(ruta: Path, ejemplo: str) -> list[str]:
    if not ruta.exists():
        ruta.write_text(ejemplo)
        print(f"Creado {ruta.relative_to(ROOT)} con valores de ejemplo")
    return [l.strip() for l in ruta.read_text().splitlines()
            if l.strip() and not l.lstrip().startswith("#")]


def _trozos(xs: list, n: int = 50):
    for i in range(0, len(xs), n):
        yield xs[i:i + n]


def buscar(yt: YouTube, consulta: str, desde: str | None) -> tuple[set[str], set[str]]:
    """Una página de 50 resultados ordenados por visitas → (videos, canales)."""
    params = dict(part="snippet", q=consulta, type="video", videoCategoryId="10",
                  order="viewCount", videoDuration="long", maxResults=50)
    if desde:
        params["publishedAfter"] = desde
    datos = yt.get("search", **params)
    vids = {i["id"]["videoId"] for i in datos.get("items", [])}
    canales = {i["snippet"]["channelId"] for i in datos.get("items", [])}
    return vids, canales


def resolver_canal(yt: YouTube, ref: str) -> str | None:
    if ref.startswith("UC"):
        return ref
    datos = yt.get("channels", part="id", forHandle=ref.lstrip("@"))
    items = datos.get("items", [])
    if not items:
        print(f"  ! no encuentro el canal {ref}")
        return None
    return items[0]["id"]


def subidas(yt: YouTube, canal_ids: list[str], por_canal: int) -> set[str]:
    vids: set[str] = set()
    listas = {}
    for lote in _trozos(canal_ids):
        datos = yt.get("channels", part="contentDetails", id=",".join(lote), maxResults=50)
        for i in datos.get("items", []):
            listas[i["id"]] = i["contentDetails"]["relatedPlaylists"]["uploads"]
    for canal, lista in listas.items():
        token, n = None, 0
        while n < por_canal:
            params = dict(part="contentDetails", playlistId=lista, maxResults=50)
            if token:
                params["pageToken"] = token
            try:
                datos = yt.get("playlistItems", **params)
            except RuntimeError as e:
                # Un canal sin vídeos públicos no tiene lista de subidas: 404.
                if "404" not in str(e):
                    raise
                print(f"  ! {canal}: sin lista de subidas, lo salto")
                break
            for i in datos.get("items", []):
                vids.add(i["contentDetails"]["videoId"])
                n += 1
            token = datos.get("nextPageToken")
            if not token:
                break
    return vids


def detalles(yt: YouTube, video_ids: list[str]) -> list[dict]:
    items = []
    for lote in _trozos(video_ids):
        datos = yt.get("videos", part="snippet,statistics,contentDetails", id=",".join(lote))
        items.extend(datos.get("items", []))
    canales = sorted({i["snippet"]["channelId"] for i in items})
    subs = {}
    for lote in _trozos(canales):
        datos = yt.get("channels", part="statistics", id=",".join(lote))
        for c in datos.get("items", []):
            subs[c["id"]] = int(c["statistics"].get("subscriberCount", 0))
    return [ry.aplanar(i, subs) for i in items]


def cmd_descubrir(a) -> None:
    clave = os.environ.get("YOUTUBE_API_KEY")
    if not clave:
        sys.exit("Falta YOUTUBE_API_KEY (YouTube Data API v3).")
    DIR.mkdir(parents=True, exist_ok=True)
    consultas = _leer_lista(DIR / "consultas.txt", CONSULTAS_EJEMPLO)[: a.consultas]
    semillas = _leer_lista(DIR / "canales.txt", CANALES_EJEMPLO)
    yt = YouTube(clave, a.cuota)
    reciente = (datetime.now(timezone.utc) - timedelta(days=a.reciente_dias)).strftime(
        "%Y-%m-%dT00:00:00Z")  # al día: si cambiara cada segundo, la caché no serviría

    vids: set[str] = set()
    canales: Counter = Counter()
    try:
        for q in consultas:
            for desde in (None, reciente):
                v, c = buscar(yt, q, desde)
                vids |= v
                canales.update(c)
                print(f"  «{q}»{' (reciente)' if desde else ''}: {len(v)} vídeos")
        semillas_ids = [x for x in (resolver_canal(yt, s) for s in semillas) if x]
        # Los canales que salen en varias búsquedas son los que dominan el nicho:
        # de esos (y de los semilla) se recorren también las subidas.
        frecuentes = [c for c, n in canales.most_common() if n >= a.min_apariciones]
        recorrer = list(dict.fromkeys(semillas_ids + frecuentes))[: a.max_canales]
        print(f"Recorriendo las subidas de {len(recorrer)} canales…")
        vids |= subidas(yt, recorrer, a.por_canal)
    except SinCuota as e:
        print(f"  ! {e}: sigo con lo recogido")

    print(f"Pidiendo métricas de {len(vids)} vídeos…")
    todos = detalles(yt, sorted(vids))
    dentro, fuera = [], []
    for v in todos:
        motivo = ry.motivo_descarte(v)
        (fuera if motivo else dentro).append(v | {"motivo": motivo})
    ranking = ry.puntuar(dentro)

    with open(DIR / "videos.jsonl", "w") as f:
        for v in ranking:
            f.write(json.dumps(v, ensure_ascii=False) + "\n")
    columnas = ["puntuacion", "visitas", "visitas_dia", "ratio_canal", "declara_ia", "duracion_s",
                "publicado", "canal", "suscriptores", "titulo", "id"]
    with open(DIR / "ranking.csv", "w", newline="") as f:
        w = csv.DictWriter(f, columnas, extrasaction="ignore")
        w.writeheader()
        w.writerows(ranking)
    with open(DIR / "descartes.csv", "w", newline="") as f:
        w = csv.DictWriter(f, ["motivo", "visitas", "canal", "titulo", "id"],
                           extrasaction="ignore")
        w.writeheader()
        w.writerows(sorted(fuera, key=lambda v: -v["visitas"]))

    print(f"\n{len(ranking)} vídeos en el ranking, {len(fuera)} descartados. "
          f"Cuota gastada: {yt.gastado} unidades.")
    for v in ranking[:15]:
        print(f"  {v['puntuacion']:.2f}  {v['visitas']:>11,}  {v['canal'][:22]:<22}  "
              f"{v['titulo'][:70]}")


def _llm():
    """El LLM de Loomcast: el que ya escuche, o lo arranca el runtime."""
    from backend.clients import llm
    from backend.services import llm_runtime
    modelo = llm_runtime.activo()
    llm.configurar(modelo)
    arrancado = False
    if not llm.ping(modelo.url):
        print(f"Arrancando «{modelo.nombre}»…")
        llm_runtime.asegurar()
        arrancado = True
    return llm, llm_runtime, arrancado


def cmd_extraer(a) -> None:
    fuente = DIR / "videos.jsonl"
    if not fuente.exists():
        sys.exit("Primero: descubrir")
    videos = [json.loads(l) for l in fuente.read_text().splitlines()][: a.top]
    salida = DIR / "fichas.jsonl"
    hechas = {}
    if salida.exists():
        for l in salida.read_text().splitlines():
            f = json.loads(l)
            hechas[f["video"]["id"]] = f
    pendientes = [v for v in videos if v["id"] not in hechas]
    print(f"{len(videos)} vídeos: {len(hechas)} ya extraídos, {len(pendientes)} pendientes")

    if pendientes and not a.solo_informe:
        llm, runtime, arrancado = _llm()
        sistema = (ROOT / "prompts" / "musica_referencia.md").read_text()
        try:
            with open(salida, "a") as out:
                for n, v in enumerate(pendientes, 1):
                    usuario = (f"TITLE: {v['titulo']}\nCHANNEL: {v['canal']}\n"
                               f"TAGS: {', '.join(v['tags'][:30])}\n\n"
                               f"DESCRIPTION:\n{v['descripcion'][:6000]}")
                    try:
                        ref = llm.chat(sistema, usuario, ry.ReferenciaLLM)
                    except httpx.TransportError as e:
                        # El servidor ya no está (p. ej. se reinició Loomcast y lo
                        # tiró). Seguir solo llenaría el log de errores: se para,
                        # y lo hecho queda en fichas.jsonl para retomar.
                        print(f"  ! el LLM dejó de responder ({e}); paro en {n - 1}/"
                              f"{len(pendientes)}. Vuelve a lanzar extraer para seguir.")
                        break
                    except llm.LLMError as e:
                        print(f"  ! {v['id']}: {e}")
                        continue
                    ficha = {"video": {k: v[k] for k in
                                       ("id", "titulo", "canal", "canal_id", "visitas",
                                        "visitas_dia", "puntuacion")},
                             "ref": ref.model_dump()}
                    out.write(json.dumps(ficha, ensure_ascii=False) + "\n")
                    out.flush()
                    hechas[v["id"]] = ficha
                    marca = "prompt" if ref.prompt_original else "estilo"
                    print(f"  [{n}/{len(pendientes)}] {marca:6} {ref.genero:<16} "
                          f"{v['titulo'][:60]}")
        finally:
            if arrancado:
                runtime.liberar("referencias extraídas")

    fichas = [hechas[v["id"]] for v in videos if v["id"] in hechas]
    biblioteca = ry.agrupar(fichas)
    (DIR / "biblioteca.json").write_text(json.dumps(biblioteca, ensure_ascii=False, indent=2))
    (DIR / "informe.md").write_text(_informe(fichas, biblioteca))
    con_prompt = sum(1 for f in fichas if f["ref"]["prompt_original"])
    print(f"\n{len(fichas)} fichas ({con_prompt} con prompt publicado) → "
          f"{len(biblioteca)} referencias distintas en biblioteca.json")


def cmd_pistas(a) -> None:
    """Manda las ideas semilla al flujo de música de Loomcast, en orden de ranking.

    Cada idea entra como una pista instrumental: el LLM escribe su brief y luego
    ACE-Step la sintetiza, todo en la cola del backend (que tiene que estar
    corriendo). `pistas.json` apunta qué pista salió de cada vídeo, así que
    relanzar solo manda las que falten.
    """
    fichas = DIR / "fichas.jsonl"
    if not fichas.exists():
        sys.exit("Primero: extraer")
    orden = {json.loads(l)["id"]: n for n, l in
             enumerate((DIR / "videos.jsonl").read_text().splitlines())}
    todas = sorted((json.loads(l) for l in fichas.read_text().splitlines()),
                   key=lambda f: orden.get(f["video"]["id"], 1e9))
    registro = DIR / "pistas.json"
    hechas = json.loads(registro.read_text()) if registro.exists() else {}
    pendientes = [f for f in todas if f["video"]["id"] not in hechas][: a.limite]
    print(f"{len(todas)} fichas: {len(hechas)} ya mandadas, {len(pendientes)} a mandar")
    if not pendientes:
        return
    try:
        r = httpx.post(f"{a.api}/api/musica/lote", timeout=60, json={
            "ideas": [f["ref"]["idea_semilla"] for f in pendientes],
            "duracion_s": a.duracion})
    except httpx.TransportError as e:
        sys.exit(f"No responde el backend en {a.api} ({e}). ¿Está Loomcast levantado?")
    if r.status_code >= 400:
        sys.exit(f"El backend respondió {r.status_code}: {r.text[:300]}")
    ids = r.json()["ids"]
    # El backend descarta ideas vacías; las fichas siempre traen una, pero si
    # no cuadra es mejor no apuntar nada que apuntar mal.
    if len(ids) != len(pendientes):
        sys.exit(f"Se crearon {len(ids)} pistas para {len(pendientes)} ideas: revisa la biblioteca")
    for f, mid in zip(pendientes, ids):
        hechas[f["video"]["id"]] = mid
    registro.write_text(json.dumps(hechas, indent=1))
    print(f"Creadas {len(ids)} pistas ({ids[0]}–{ids[-1]}) de {a.duracion} s. "
          "Primero salen todos los briefs y luego las síntesis; se ve en la cola de Loomcast.")


def _informe(fichas: list[dict], biblioteca: list[dict]) -> str:
    def suma(clave_fn) -> list[tuple[str, int, int]]:
        visitas, n = Counter(), Counter()
        for f in fichas:
            for k in clave_fn(f["ref"]):
                if k:
                    visitas[k] += f["video"]["visitas"]
                    n[k] += 1
        return [(k, visitas[k], n[k]) for k, _ in visitas.most_common(15)]

    def tabla(titulo, filas):
        out = [f"## {titulo}\n", "| | visitas | vídeos |", "|---|---:|---:|"]
        out += [f"| {k} | {v:,} | {n} |" for k, v, n in filas]
        return "\n".join(out) + "\n"

    bpm = lambda r: [f"{(r['bpm'] // 10) * 10}–{(r['bpm'] // 10) * 10 + 9}"] if r["bpm"] else []
    con_prompt = sum(1 for f in fichas if f["ref"]["prompt_original"])
    partes = [
        "# Referencias de YouTube\n",
        f"{len(fichas)} vídeos analizados, {con_prompt} publican su prompt; "
        f"{len(biblioteca)} referencias distintas.\n",
        tabla("Géneros", suma(lambda r: [r["subgenero"] or r["genero"]])),
        tabla("Instrumentos", suma(lambda r: [i.lower() for i in r["instrumentos"]])),
        tabla("Tempo (BPM declarado)", suma(bpm)),
        tabla("Ambiente (por palabra)", suma(lambda r: [p.strip().lower() for p in r["ambiente"].split(",")])),
        "## Las 10 referencias con más visitas\n",
    ]
    for g in biblioteca[:10]:
        partes.append(f"- **{g['visitas']:,}** ({g['videos']} vídeos, {', '.join(g['canales'][:3])}): "
                      f"{g['idea_semilla']}")
        if g["prompt_original"]:
            partes.append(f"  - prompt: `{g['prompt_original'][:300]}`")
    return "\n".join(partes) + "\n"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("descubrir", help="buscar vídeos y hacer el ranking")
    d.add_argument("--consultas", type=int, default=40,
                   help="cuántas líneas de consultas.txt usar (cada una cuesta 200 unidades)")
    d.add_argument("--reciente-dias", type=int, default=365)
    d.add_argument("--min-apariciones", type=int, default=2,
                   help="un canal entra a recorrer subidas si sale en tantas búsquedas")
    d.add_argument("--max-canales", type=int, default=60)
    d.add_argument("--por-canal", type=int, default=200)
    d.add_argument("--cuota", type=int, default=9000, help="tope de unidades por ejecución")
    d.set_defaults(fn=cmd_descubrir)
    e = sub.add_parser("extraer", help="sacar el estilo de los mejores con el LLM")
    e.add_argument("--top", type=int, default=300)
    e.add_argument("--solo-informe", action="store_true",
                   help="rehacer biblioteca e informe con las fichas que ya hay, sin LLM")
    e.set_defaults(fn=cmd_extraer)
    pi = sub.add_parser("pistas", help="crear las pistas en Loomcast a partir de las fichas")
    pi.add_argument("--limite", type=int, default=300, help="cuántas mandar en esta tanda")
    pi.add_argument("--duracion", type=int, default=180, help="segundos por pista")
    pi.add_argument("--api", default="http://127.0.0.1:8700")
    pi.set_defaults(fn=cmd_pistas)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
