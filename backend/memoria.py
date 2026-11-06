"""Cuánta memoria unificada hay disponible, sin preguntarle a nadie.

Hasta ahora esto se medía con `/system_stats` de ComfyUI, que para MPS devuelve
la memoria disponible del sistema. Funciona, pero ata la medición a que ComfyUI
esté escuchando, y hace falta justo cuando puede no estarlo: al soltar un modelo
para que quepa el siguiente.

**`available` y no "libre".** En macOS la memoria *libre* (`Pages free` de
`vm_stat`) no dice si cabe un modelo: el 2026-10-20, con un episodio de serie a
medias, `vm_stat` daba 1,0 GiB libres y 25,5 GiB ocupados por el compresor,
mientras que `available` daba 39,2 GiB — y los 39 son los reales, porque la
memoria inactiva y la comprimida se reclaman en cuanto alguien pide. Es también
la cifra que usa ComfyUI por debajo, así que medir aquí no cambia el criterio,
solo quita la dependencia.
"""


def disponible_gb() -> float | None:
    """GiB de memoria que el sistema puede dar ahora. None si no se puede medir.

    Nunca lanza: quien la usa está decidiendo si arrancar un modelo o esperar, y
    quedarse sin medición no puede ser peor que no mirar.
    """
    try:
        import psutil

        return psutil.virtual_memory().available / (1024**3)
    except Exception:
        return None


def swapouts_gb() -> float | None:
    """GiB que el kernel ha mandado al swap desde que arrancó el equipo. None si
    no se puede medir.

    Es un contador acumulado, así que lo que vale es la **diferencia** entre dos
    lecturas: cuánta memoria mandó al disco la etapa que corrió en medio. Es la
    única cifra que distingue «ha ido justo» de «ha estado paginando cuatro
    minutos», y no se ve en la memoria disponible, que al terminar vuelve a
    parecer sana.

    Se lee `Swapouts` de `vm_stat` por dos motivos. Uno: `Pageouts` **no es el
    swap** —cuenta también las escrituras de archivos mapeados, que son
    normales— y medido en este equipo da 276 MiB frente a los 123 GiB de
    `Swapouts`. Dos: `psutil.swap_memory().sout`, que es lo que habría a mano,
    devuelve en macOS justo el Pageouts, o sea el número equivocado.
    """
    try:
        import subprocess

        salida = subprocess.run(
            ["vm_stat"], capture_output=True, text=True, timeout=5
        ).stdout
    except Exception:
        return None
    pagina, swapouts = 4096, None
    for linea in salida.splitlines():
        if "page size of" in linea:
            pagina = int(linea.split("page size of")[1].split()[0])
        elif linea.startswith("Swapouts:"):
            swapouts = int(linea.split(":")[1].strip().rstrip("."))
    if swapouts is None:
        return None
    return swapouts * pagina / (1024**3)
