"""F1-VRAM-EXP-V4 — escribe `evaluacion_f1/PRERREGISTRO_F1_VRAM_EXP_v4.json` (prerregistro V4, variante experimental).

    python -B evaluacion_f1/prerregistrar_vram_exp_v4.py

No toca V1, V2 ni V3: los incluye por su SHA-256 (V3 ya incluye todo V2), junto con los archivos de V4. Se niega a
sobrescribir un V4 existente.
"""
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
from eq3 import evaluar_f1_vram_exp_v4 as V  # noqa: E402

if V.PRERREGISTRO_V4.is_file():
    raise SystemExit(f"ya existe {V.PRERREGISTRO_V4.name}: no se sobrescribe")
datos = {"version": 4, "variante": V.VARIANTE, "base": "prerregistro V3 (F1-VRAM-EXP) sin cambios, que incluye V2 y V1",
         "fecha_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
         "estado": "PRERREGISTRADO, NO EJECUTADO (la evaluación F1 completa NO está autorizada)",
         "llama_e2": V.E2,
         "limites": {"vram_tope_MiB": V.VRAM_TOPE, "vram_otras_max_MiB": V.VRAM_OTRAS_MAX,
                     "pico_e2_medido_MiB": V.PICO_E2_MEDIDO, "crecimiento_ajeno_max_MiB": V.CRECIMIENTO_AJENO_MAX,
                     "margen_MiB": V.MARGEN, "variacion_otras_max_MiB": V.VARIACION_OTRAS_MAX,
                     "uso_gpu_max_pct": V.UTILIZACION_GPU_MAX, "inactividad_min_s": V.INACTIVIDAD_MIN_S},
         "fondo_animado": "Wallpaper Engine: -control stop con el PC libre; -control play al terminar, abortar, fallar o "
                          "si aparece una persona; nunca se cierra ni se fuerza",
         "sin_cambios": "tareas, oráculos, prompts, configuraciones, orden, temperaturas, semillas, regla de decisión, "
                        "STOP, monitor de memoria, propiedad de procesos y reintentos por terceros: los de V3",
         "sha256": {a: hashlib.sha256((RAIZ / a).read_bytes()).hexdigest() for a in V.ARCHIVOS_V4}}
V.PRERREGISTRO_V4.write_text(json.dumps(datos, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
for a, h in datos["sha256"].items():
    print(h, a)
