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
