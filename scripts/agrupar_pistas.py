"""Reparte las pistas del lote de referencias de YouTube en carpetas de 20.

Cada carpeta es de una sola familia de género y va a ser una mezcla de 1 hora
(20 × 180 s). Dentro de una familia, las pistas más parecidas se mandan a
carpetas distintas, para que una mezcla no repita dos veces la misma canción.

    ./.venv/bin/python scripts/agrupar_pistas.py            # crea las carpetas
    ./.venv/bin/python scripts/agrupar_pistas.py --simular  # solo el informe

La similitud sale del texto del brief (los tags que recibió ACE-Step: género,
instrumentos, ambiente, mezcla) más el BPM y la tonalidad. Las carpetas llevan
una copia del audio de `musica/<id>/musica.flac` (unos 4 GB en total).
"""
import argparse
import json
import random
import shutil
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

RAIZ = Path(__file__).resolve().parent.parent
REF = RAIZ / "referencias" / "youtube"
SALIDA = REF / "carpetas"
POR_CARPETA = 20
# Lo que sobra de una familia se reparte entre sus carpetas hasta este tope
# (25 × 3 min = 75 min): mejor una mezcla algo más larga que pistas sueltas.
MAX_CARPETA = 25

# Orden importante: la primera regla que casa gana. Se mira género + subgénero
# de la ficha de YouTube, que es lo que pidió la pista.
FAMILIAS = [
    ("Bossa nova", ("bossa",)),
    ("Lofi y jazzhop", ("lofi", "lo-fi", "jazzhop", "jazz hop", "hip hop", "hiphop", "chillhop")),
    ("House y lounge", ("house", "garage", "techno", "lounge", "chillstep")),
    ("RnB, soul y funk", ("r&b", "rnb", "soul", "funk", "city pop", "groove", "afrobeat", "oldies")),
    ("Calma: ambient, piano y clasica", ("ambient", "classical", "new age", "focus", "study music",
                                         "children", "acoustic guitar", "adagio", "instrumental")),
    ("Jazz noir", ("noir", "dark jazz", "doom")),
]
FAMILIA_POR_DEFECTO = "Jazz cafe"


# Del subgénero solo se fían estas: «jazz / bossa nova» es bossa y «jazz / noir
# jazz» es noir, pero «smooth jazz / lounge jazz» o «… / saxophone instrumental»
# siguen siendo jazz de cafetería.
POR_SUBGENERO = ("Bossa nova", "Jazz noir")
# Dos briefs casi idénticos (el LLM respondió lo mismo a dos ideas gemelas) son
# casi la misma canción: nunca en la misma carpeta.
GEMELAS = 0.95


def familia(genero: str, subgenero: str) -> str:
    g, sub = genero.lower(), subgenero.lower()
    for nombre, claves in FAMILIAS:
        if any(c in g for c in claves):
            return nombre
    for nombre, claves in FAMILIAS:
        if nombre in POR_SUBGENERO and any(c in sub for c in claves):
            return nombre
    return FAMILIA_POR_DEFECTO


def cargar() -> list[dict]:
    fichas = {}
    for linea in open(REF / "fichas.jsonl"):
        f = json.loads(linea)
        fichas[f["video"]["id"]] = f
    pistas = json.load(open(REF / "pistas.json"))
    db = sqlite3.connect(RAIZ / "loomcast.db")
    db.row_factory = sqlite3.Row
    salida = []
    for vid, mid in pistas.items():
        m = db.execute("select * from musicas where id=?", (mid,)).fetchone()
        audio = RAIZ / "musica" / str(mid) / "musica.flac"
        if m is None or m["estado"] != "generada" or not audio.exists():
            print(f"  · pista {mid} sin audio, se queda fuera", file=sys.stderr)
            continue
        ref = fichas[vid]["ref"]
        salida.append({
            "id": mid, "video": vid, "audio": audio,
            "canal": fichas[vid]["video"]["canal"],
            "genero": ref["genero"], "subgenero": ref["subgenero"],
            "familia": familia(ref["genero"], ref["subgenero"]),
            "tags": m["tags"] or "", "bpm": m["bpm"], "tono": m["keyscale"],
        })
    return salida


def similitudes(pistas: list[dict]) -> np.ndarray:
    """Matriz de parecido 0–1 entre pistas: texto del brief, tempo y tono."""
    tfidf = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), sublinear_tf=True)
    x = tfidf.fit_transform([p["tags"] for p in pistas])
    texto = (x @ x.T).toarray()
    bpm = np.array([p["bpm"] for p in pistas], dtype=float)
    tempo = np.clip(1 - np.abs(bpm[:, None] - bpm[None, :]) / 30, 0, 1)
    tono = np.array([[a["tono"] == b["tono"] for b in pistas] for a in pistas], dtype=float)
    return 0.7 * texto + 0.2 * tempo + 0.1 * tono


def coste(grupo: list[int], s: np.ndarray) -> float:
    # Al cubo: dos casi gemelas pesan mucho más que varias medio parecidas.
    sub = s[np.ix_(grupo, grupo)]
    return float((np.triu(sub, 1) ** 3).sum())


def repartir(n: int, k: int, s: np.ndarray, semilla: int = 0) -> list[list[int]]:
    """Anticlustering: k grupos de tamaño parejo con el menor parecido interno.

    Arranca repartiendo por turnos según un orden de vecinos (las parecidas
    quedan contiguas y caen en carpetas distintas) y luego prueba intercambios
    entre carpetas mientras alguno baje el coste.
    """
    if k == 1:
        return [list(range(n))]
    # Orden voraz por vecino más cercano.
    restantes = set(range(n))
    orden = [0]
    restantes.remove(0)
    while restantes:
        ult = orden[-1]
        sig = max(restantes, key=lambda j: s[ult, j])
        orden.append(sig)
        restantes.remove(sig)
    grupos = [[] for _ in range(k)]
    for pos, i in enumerate(orden):
        grupos[pos % k].append(i)

    rng = random.Random(semilla)
    mejoro = True
    while mejoro:
        mejoro = False
        pares = [(a, b) for a in range(k) for b in range(a + 1, k)]
        rng.shuffle(pares)
        for a, b in pares:
            for ia in range(len(grupos[a])):
                for ib in range(len(grupos[b])):
                    ga, gb = grupos[a], grupos[b]
                    antes = coste(ga, s) + coste(gb, s)
                    ga[ia], gb[ib] = gb[ib], ga[ia]
                    if coste(ga, s) + coste(gb, s) < antes - 1e-9:
                        mejoro = True
                    else:
                        ga[ia], gb[ib] = gb[ib], ga[ia]
    return grupos


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--simular", action="store_true")
    args = ap.parse_args()

    pistas = cargar()
    por_familia = defaultdict(list)
    for p in pistas:
        por_familia[p["familia"]].append(p)

    carpetas = []  # (nombre, familia, [pistas], parecido_max)
    for fam, lista in sorted(por_familia.items(), key=lambda kv: -len(kv[1])):
        lista.sort(key=lambda p: p["id"])
        n = len(lista)
        # Redondeo: 54 pistas dan 3 carpetas de 18 (faltan 6 para completarlas)
        # mejor que 2 de 20 y 14 sueltas; 29 dan 1 de 20 y 9 en reserva.
        k = max(1, round(n / POR_CARPETA))
        s = similitudes(lista)
        np.fill_diagonal(s, 0)
        grupos = repartir(n, k, s)
        # Si sobran pistas (n no es múltiplo de 20), las carpetas pasan de 20:
        # se recortan las que más se parecen a otra de su carpeta y van a reserva.
        reserva = []
        for g in grupos:
            while len(g) > POR_CARPETA:
                peor = max(g, key=lambda i: s[i, g].max())
                g.remove(peor)
                reserva.append(peor)
        # Gemelas que el reparto no pudo separar (tres iguales en dos carpetas):
        # una sale a reserva y entra, si la hay, una de reserva que no sea gemela.
        for g in grupos:
            while True:
                par = next(((i, j) for i in g for j in g if i < j and s[i, j] >= GEMELAS), None)
                if par is None:
                    break
                g.remove(par[1])
                candidatas = [r for r in reserva if s[r, g].max() < GEMELAS]
                if candidatas:
                    mejor = min(candidatas, key=lambda r: s[r, g].max())
                    reserva.remove(mejor)
                    g.append(mejor)
                reserva.append(par[1])
        # Las que sobraron vuelven a la carpeta de su familia donde menos se
        # parecen a nada, sin pasar del tope. Una gemela que no cabe en ningún
        # sitio sin su gemela se queda fuera.
        fuera = []
        for r in sorted(reserva, key=lambda r: lista[r]["id"]):
            sitios = [g for g in grupos if len(g) < MAX_CARPETA and s[r, g].max() < GEMELAS]
            if sitios:
                min(sitios, key=lambda g: (s[r, g].max(), len(g))).append(r)
            else:
                fuera.append(r)
        reserva = fuera
        for n_c, g in enumerate(grupos, 1):
            maxi = max((s[i, j] for i in g for j in g if i < j), default=0)
            carpetas.append((f"{fam} {n_c:02d}", fam, [lista[i] for i in g], maxi))
        for i in reserva:
            print(f"  · pista {lista[i]['id']} fuera: es gemela de otra en cada carpeta")
        print(f"{fam}: {n} pistas → {k} carpeta(s) de {', '.join(str(len(g)) for g in grupos)}")

    if args.simular:
        return
    if SALIDA.exists():
        shutil.rmtree(SALIDA)
    resumen = []
    for nombre, fam, lista, maxi in carpetas:
        d = SALIDA / nombre
        d.mkdir(parents=True)
        for n_p, p in enumerate(lista, 1):
            shutil.copy2(p["audio"], d / f"{n_p:02d} - pista {p['id']}.flac")
        resumen.append({
            "carpeta": nombre, "familia": fam,
            "parecido_max": round(maxi, 3),
            "pistas": [{k: p[k] for k in ("id", "genero", "subgenero", "bpm", "tono", "canal", "tags")}
                       for p in lista],
        })
    (SALIDA / "carpetas.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=2))
    print(f"\n{len(carpetas)} carpetas en {SALIDA}")


if __name__ == "__main__":
    main()
