"""F1-VRAM-EXP-V4.2 — escribe `evaluacion_f1/PRERREGISTRO_F1_VRAM_EXP_v4_2.json`.

    python -B evaluacion_f1/prerregistrar_vram_exp_v4_2.py

V4.1 corrige tres defectos de V4 encontrados al preparar sus puertas (guardián independiente del fondo animado,
puertas ligadas al código y aborto si una tarea no corre con E2). V4.2 añade el aislamiento de las pruebas: ninguna prueba puede llegar al Wallpaper Engine real (una mutación de F21 lo\nconsiguió en las primeras puertas de V4.1). No toca V1–V4.1: los incluye por su SHA-256.
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
datos = {"version": "4.2", "variante": V.VARIANTE, "base": "prerregistros V4 y V4.1 (conservados) + correcciones de sus puertas",
         "fecha_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
         "estado": "PRERREGISTRADO, NO EJECUTADO (la evaluación F1 completa NO está autorizada)",
         "cambios_sobre_v4": [
             "guardián independiente (lab_vram/guardian_fondo.py, lanzado por WMI) que reanuda Wallpaper Engine si "
             "Equipo IA termina de golpe; sin guardián no se detiene el fondo",
             "comparar exige un puertas.json con el MISMO código y prerregistro (huella_codigo)",
             "una tarea que no corre con E2 aborta TODA la evaluación (antes solo se marcaba)",
             "puertas G1–G10 propias de V4.1 (G8 tope de VRAM real, G9 fallo de arranque real, G10 equivalencia)",
             "V4.2: la prueba de puertas ligadas sustituye FondoAnimado por uno que falla: ninguna prueba toca el fondo real"],
         "llama_e2": V.E2,
         "limites": {"vram_tope_MiB": V.VRAM_TOPE, "vram_otras_max_MiB": V.VRAM_OTRAS_MAX,
                     "pico_e2_medido_MiB": V.PICO_E2_MEDIDO, "crecimiento_ajeno_max_MiB": V.CRECIMIENTO_AJENO_MAX,
                     "margen_MiB": V.MARGEN, "variacion_otras_max_MiB": V.VARIACION_OTRAS_MAX,
                     "uso_gpu_max_pct": V.UTILIZACION_GPU_MAX, "inactividad_min_s": V.INACTIVIDAD_MIN_S},
         "sin_cambios": "tareas, oráculos, prompts, configuraciones, orden, temperaturas, semillas, regla de decisión, "
                        "STOP, monitor de memoria, propiedad de procesos y reintentos por terceros: los de V3",
         "sha256": {a: hashlib.sha256((RAIZ / a).read_bytes()).hexdigest() for a in V.ARCHIVOS_V4}}
V.PRERREGISTRO_V4.write_text(json.dumps(datos, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
for a, h in datos["sha256"].items():
    print(h, a)
