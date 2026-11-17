"""F1-VRAM-EXP — escribe `evaluacion_f1/PRERREGISTRO_F1_VRAM_EXP_v3.json` (prerregistro V3 de la variante experimental).

    python -B evaluacion_f1/prerregistrar_vram_exp.py

No toca el prerregistro V2 (`PRERREGISTRO_F1.json`) ni el V1: los incluye por su SHA-256, junto con los archivos que
V2 ya protegía, y añade los de la variante. Se niega a sobrescribir un V3 existente.
"""
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
from eq3 import evaluar_f1_vram_exp as X  # noqa: E402

DESTINO = X.PRERREGISTRO_V3
if DESTINO.is_file():
    raise SystemExit(f"ya existe {DESTINO.name}: no se sobrescribe")
v2 = json.loads((RAIZ / "evaluacion_f1" / "PRERREGISTRO_F1.json").read_text(encoding="utf-8"))
archivos = list(v2["sha256"]) + ["evaluacion_f1/PRERREGISTRO_F1_v1.json"] + X.ARCHIVOS_V3
datos = {"version": 3, "variante": X.VARIANTE, "base": f"prerregistro V{v2['version']} (sin cambios)",
         "fecha_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
         "estado": "PRERREGISTRADO, NO EJECUTADO",
         "limites": {"vram_tope_MiB": X.VRAM_TOPE_EXP, "vram_otras_max_MiB": X.VRAM_OTRAS_MAX_EXP,
                     "pico_qwen_medido_MiB": X.PICO_QWEN_MEDIDO, "margen_MiB": X.MARGEN_VRAM,
                     "variacion_otras_max_MiB": X.VARIACION_OTRAS_MAX, "uso_gpu_max_pct": X.UTILIZACION_GPU_MAX,
                     "inactividad_min_s": X.INACTIVIDAD_MIN_S, "ventana_inicio_s": X.VENTANA_INICIO_S,
                     "ventana_tarea_s": X.VENTANA_TAREA_S, "max_espera_s": X.MAX_ESPERA_S,
                     "max_interrupciones_por_tarea": X.MAX_INTERRUPCIONES},
         "sin_cambios": "tareas, oráculos, prompts, configuraciones, orden, temperaturas, semillas, regla de decisión, "
                        "STOP, monitor de memoria y propiedad de procesos: los del prerregistro V2",
         "sha256": {a: hashlib.sha256((RAIZ / a).read_bytes()).hexdigest() for a in dict.fromkeys(archivos)}}
DESTINO.write_text(json.dumps(datos, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
for a, h in datos["sha256"].items():
    print(h, a)
