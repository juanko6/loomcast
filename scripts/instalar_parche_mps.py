#!/usr/bin/env python3
"""Enlaza el parche de torch.multinomial en el ComfyUI de esta máquina.

Crea un symlink en ComfyUI/custom_nodes/ que apunta a scripts/comfy_parche_mps/,
así que el código vive versionado en Loomcast y ComfyUI solo lo carga. Al ir en
custom_nodes/, `comfy update` no lo pisa.

    python scripts/instalar_parche_mps.py [--comfy RUTA] [--quitar]

Hay que reiniciar ComfyUI después. Para comprobar que está activo, busca en su
arranque la línea "[loomcast] Parche de torch.multinomial en MPS activo".
"""
import argparse
import sys
from pathlib import Path

ORIGEN = Path(__file__).resolve().parent / "comfy_parche_mps"
COMFY_POR_DEFECTO = Path.home() / "Documents" / "ComfyUI" / "ComfyUI"
NOMBRE = "loomcast_parche_mps"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--comfy", type=Path, default=COMFY_POR_DEFECTO,
                   help=f"Raíz de ComfyUI (por defecto {COMFY_POR_DEFECTO})")
    p.add_argument("--quitar", action="store_true", help="Desinstala el parche")
    args = p.parse_args()

    custom_nodes = args.comfy / "custom_nodes"
    if not custom_nodes.is_dir():
        print(f"No encuentro {custom_nodes}. Pasa la ruta con --comfy.", file=sys.stderr)
        return 1

    destino = custom_nodes / NOMBRE

    if args.quitar:
        if destino.is_symlink() or destino.exists():
            destino.unlink()
            print(f"Parche quitado de {destino}. Reinicia ComfyUI.")
        else:
            print("No estaba instalado.")
        return 0

    if destino.is_symlink():
        if destino.resolve() == ORIGEN:
            print(f"Ya estaba instalado y apunta bien ({destino}).")
            return 0
        destino.unlink()
    elif destino.exists():
        print(f"{destino} existe y no es un enlace nuestro; no lo toco.", file=sys.stderr)
        return 1

    destino.symlink_to(ORIGEN, target_is_directory=True)
    print(f"Enlazado {destino} -> {ORIGEN}")
    print("Reinicia ComfyUI. Con el parche puedes poner [musica].lm_device = \"default\".")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
