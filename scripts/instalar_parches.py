#!/usr/bin/env python3
"""Enlaza los parches de Loomcast en el ComfyUI de esta máquina.

Crea un symlink por paquete en ComfyUI/custom_nodes/, así que el código vive
versionado en Loomcast y ComfyUI solo lo carga. Al ir en custom_nodes/,
`comfy update` no lo pisa.

    python scripts/instalar_parches.py [--comfy RUTA] [--quitar]

Los parches son:

  comfy_parche_mps    los agujeros de PyTorch en Metal: el torch.multinomial
                      que tumba las pistas largas de ACE-Step y el escalado
                      `area` que impedía usar Qwen-Image-Edit con referencias.
  comfy_parche_gguf   los parámetros sueltos que el GGUF de LTX-2.5 trae
                      cuantizados por error, y sin los cuales no carga.

Hay que reiniciar ComfyUI después. Para comprobar que están activos, busca en
su arranque las líneas que empiezan por "[loomcast] Parche".
"""
import argparse
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
COMFY_POR_DEFECTO = Path.home() / "Documents" / "ComfyUI" / "ComfyUI"
# origen en scripts/ -> nombre del enlace en custom_nodes/
PARCHES = {
    "comfy_parche_mps": "loomcast_parche_mps",
    "comfy_parche_gguf": "loomcast_parche_gguf",
}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--comfy", type=Path, default=COMFY_POR_DEFECTO,
                   help=f"Raíz de ComfyUI (por defecto {COMFY_POR_DEFECTO})")
    p.add_argument("--quitar", action="store_true", help="Desinstala los parches")
    args = p.parse_args()

    custom_nodes = args.comfy / "custom_nodes"
    if not custom_nodes.is_dir():
        print(f"No encuentro {custom_nodes}. Pasa la ruta con --comfy.", file=sys.stderr)
        return 1

    fallos = 0
    for carpeta, nombre in PARCHES.items():
        origen, destino = SCRIPTS / carpeta, custom_nodes / nombre

        if args.quitar:
            if destino.is_symlink() or destino.exists():
                destino.unlink()
                print(f"Quitado {destino}")
            else:
                print(f"{nombre} no estaba instalado.")
            continue

        if destino.is_symlink():
            if destino.resolve() == origen:
                print(f"{nombre}: ya estaba y apunta bien.")
                continue
            destino.unlink()
        elif destino.exists():
            print(f"{destino} existe y no es un enlace nuestro; no lo toco.", file=sys.stderr)
            fallos += 1
            continue

        destino.symlink_to(origen, target_is_directory=True)
        print(f"Enlazado {destino} -> {origen}")

    print("Reinicia ComfyUI." if not args.quitar else "Reinicia ComfyUI para que dejen de cargarse.")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main())
