"""Tanda de prueba de los estilos y copia de sus ejemplos.

Habla con un Loomcast en marcha por su API, así que la cola reparte la memoria
como siempre (el LLM escribe todas las escenas seguidas y luego ComfyUI hace
todas las previews, sin cargar uno encima del otro).

    # Una imagen de generar por estilo y motor, con el mismo título:
    python scripts/ejemplos_estilos.py lanzar "Morning Bossa Nova – café jazz"
    python scripts/ejemplos_estilos.py lanzar "..." --motores zimage flux2klein --previews 4

    # Qué salió (ids, estilo, motor, estado), para mirar las previews en la UI:
    python scripts/ejemplos_estilos.py estado 20 21 22

    # Copiar una preview como ejemplo de su estilo (estilos/<id>/ejemplo_N.webp):
    python scripts/ejemplos_estilos.py copiar 20 2
"""
import argparse
import json
import sys
import urllib.request
from pathlib import Path

from PIL import Image

RAIZ = Path(__file__).resolve().parent.parent
API = "http://127.0.0.1:8700/api"
# Lado largo de los ejemplos: los enseña una tarjeta de 300 px, no hace falta más.
LADO_EJEMPLO = 640


def _api(ruta: str, cuerpo: dict | None = None, metodo: str | None = None):
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    req = urllib.request.Request(
        API + ruta, data=datos, method=metodo or ("POST" if datos else "GET"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as r:
        return json.load(r)


def lanzar(titulo: str, motores: list[str], previews: int, ancho: int, alto: int,
           estilos: list[str] | None) -> None:
    disponibles = [e["id"] for e in _api("/galeria/estilos")]
    elegidos = estilos or disponibles
    faltan = set(elegidos) - set(disponibles)
    if faltan:
        sys.exit(f"Estilos que no existen: {sorted(faltan)}")
    # Por motor y luego por estilo: así ComfyUI carga cada motor una sola vez.
    for motor in motores:
        for estilo in elegidos:
            r = _api("/galeria", {"idea": titulo, "estilo": estilo, "motor": motor,
                                  "n_previews": previews, "width": ancho, "height": alto})
            print(f"{r['id']:>5}  {motor:<12} {estilo}")


def estado(ids: list[int]) -> None:
    for i in ids:
        d = _api(f"/galeria/{i}")
        print(f"{i:>5}  {d['motor']:<12} {d['estilo']:<20} {d['estado']:<9} {len(d['seeds'])} previews")
        if d["prompt"]:
            print(f"       {d['prompt']}")


def copiar(imagen_id: int, indice: int) -> None:
    d = _api(f"/galeria/{imagen_id}")
    if not d["estilo"]:
        sys.exit(f"La imagen {imagen_id} no tiene estilo")
    origen = RAIZ / "galeria" / str(imagen_id) / f"preview_{indice}.png"
    if not origen.exists():
        sys.exit(f"No existe {origen}")
    carpeta = RAIZ / "estilos" / d["estilo"]
    n = len(list(carpeta.glob("ejemplo_*"))) + 1
    destino = carpeta / f"ejemplo_{n}.webp"
    with Image.open(origen) as im:
        im.thumbnail((LADO_EJEMPLO, LADO_EJEMPLO))
        im.convert("RGB").save(destino, "WEBP", quality=82)
    print(f"{destino.relative_to(RAIZ)}  ({d['motor']})")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="orden", required=True)
    l = sub.add_parser("lanzar")
    l.add_argument("titulo")
    l.add_argument("--motores", nargs="+", default=["zimage", "flux2klein"])
    l.add_argument("--estilos", nargs="+")
    l.add_argument("--previews", type=int, default=4)
    l.add_argument("--ancho", type=int, default=1344)
    l.add_argument("--alto", type=int, default=768)
    e = sub.add_parser("estado")
    e.add_argument("ids", type=int, nargs="+")
    c = sub.add_parser("copiar")
    c.add_argument("imagen_id", type=int)
    c.add_argument("indice", type=int)
    a = p.parse_args()
    if a.orden == "lanzar":
        lanzar(a.titulo, a.motores, a.previews, a.ancho, a.alto, a.estilos)
    elif a.orden == "estado":
        estado(a.ids)
    else:
        copiar(a.imagen_id, a.indice)


if __name__ == "__main__":
    main()
