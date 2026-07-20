"""Siembra el banco con 6 voces de arranque vía la API (crea + espera).

Uso: ./.venv/bin/python scripts/sembrar_voces.py
Requiere el backend corriendo en localhost:8700 y Qwen3-TTS disponible.
"""
import sys
import time

import httpx

API = "http://127.0.0.1:8700"

VOCES = [
    {
        "nombre": "Narrador Documental",
        "instruct": (
            "Voz masculina grave de narrador de documental en español, tono "
            "misterioso y envolvente, ritmo ágil con energía, dicción clara."
        ),
    },
    {
        "nombre": "Divulgadora Enérgica",
        "instruct": (
            "Voz femenina joven en español, enérgica y entusiasta, ritmo rápido "
            "y dinámico, ideal para datos sorprendentes y curiosidades virales."
        ),
    },
    {
        "nombre": "Misterio Susurrante",
        "instruct": (
            "Voz masculina profunda y pausada en español, tono íntimo y "
            "conspirativo, casi susurrado, crea suspenso e intriga."
        ),
    },
    {
        "nombre": "Presentadora Cercana",
        "instruct": (
            "Voz femenina cálida y cercana en español, natural y conversacional, "
            "ritmo medio, como si le contara un secreto a un amigo."
        ),
    },
    {
        "nombre": "Locutor Épico",
        "instruct": (
            "Voz masculina potente y teatral en español, tono épico y dramático, "
            "proyección de tráiler de cine, transmite asombro y grandeza."
        ),
    },
    {
        "nombre": "Joven Viral",
        "instruct": (
            "Voz juvenil andrógina en español neutro, desenfadada y moderna, "
            "ritmo rápido con inflexiones de creador de contenido de TikTok."
        ),
    },
]


def main() -> None:
    with httpx.Client(base_url=API, timeout=30) as c:
        existentes = {v["nombre"] for v in c.get("/api/voces").json()}
        jobs = []
        for v in VOCES:
            if v["nombre"] in existentes:
                print(f"= ya existe: {v['nombre']}")
                continue
            r = c.post("/api/voces", json=v)
            r.raise_for_status()
            data = r.json()
            jobs.append((v["nombre"], data["job_id"]))
            print(f"+ encolada: {v['nombre']} (job {data['job_id']})")

        print("\nGenerando (VoiceDesign, ~25s c/u)...")
        for nombre, job_id in jobs:
            while True:
                estado = c.get(f"/api/jobs/{job_id}").json()["estado"]
                if estado in ("ok", "error"):
                    break
                time.sleep(5)
            print(f"  {'✓' if estado == 'ok' else '✗'} {nombre}: {estado}")

    listas = [v for v in httpx.get(f"{API}/api/voces").json() if v["disponible"]]
    print(f"\nVoces disponibles en el banco: {len(listas)}")


if __name__ == "__main__":
    sys.exit(main())
