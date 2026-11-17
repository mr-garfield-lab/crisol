"""F1-VRAM-EXP-V4.3 — escribe `evaluacion_f1/PRERREGISTRO_F1_VRAM_EXP_v4_3.json`.

    python -B evaluacion_f1/prerregistrar_vram_exp_v4_3.py

V4.3 corrige el falso positivo del control de fugas del oráculo que abortó la primera F1 con V4.2 (E3/T10: A1 acertó y
su código llegó a A2). Es un módulo NUEVO (`eq3/evaluar_f1_vram_exp_v4_3.py`); V4.2 y V1–V4.2 se conservan y se
incluyen por su SHA-256, junto con las evidencias de la ejecución abortada.
"""
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
from eq3 import evaluar_f1_vram_exp_v4_3 as V  # noqa: E402

if V.PRERREGISTRO_V4.is_file():
    raise SystemExit(f"ya existe {V.PRERREGISTRO_V4.name}: no se sobrescribe")
datos = {"version": "4.3", "variante": V.VARIANTE,
         "base": "prerregistro V4.2 (conservado) + corrección del control de fugas tras la F1 abortada",
         "fecha_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
         "estado": "PRERREGISTRADO, NO EJECUTADO (la evaluación F1 completa NO está autorizada)",
         "motivo": "F1 con V4.2 abortada en r1/E3/T10 por FugaDeOraculo ['T10.esperado']: falso positivo (el literal lo "
                   "escribió A1 y el controlador lo retransmitió a A2); 39/90 filas, ejecución no válida",
         "cambios_sobre_v4_2": [
             "fugas_con_procedencia: un texto del oráculo deja de ser fuga SOLO en E3, dentro de un bloque de relevo "
             f"({', '.join(sorted(V.FUENTES_RELEVO))}), con la línea copiada literalmente (o ≥ {V.CONTEXTO_MIN} "
             "caracteres de contexto) de una respuesta devuelta por el servidor de ESA tarea, sin exposición previa y "
             "para TODAS las apariciones de la etiqueta; en otro caso, como la estable (fallo cerrado)",
             "S1 y S1×3: control idéntico al de la estable (nunca se exime nada)",
             "relevos eximidos anotados en metricas.peticiones[n].relevos_verificados (etiqueta, fuente, SHA-256 "
             "de la respuesta de origen)",
             "comparar anota una fuga en comparacion.json (abortada, valida=false) antes de abortar",
             "puertas: G5 añade F23 (36 mutaciones); G10 añade test_eq3_procedencia_v4_3 (flujo real de V2-F.1 con un "
             "modelo simulado que acierta, en S1, S1×3 y E3)"],
         "procedencia": {"fuentes_relevo": sorted(V.FUENTES_RELEVO), "contexto_min": V.CONTEXTO_MIN,
                         "solo_configuracion": "E3"},
         "llama_e2": V.E2,
         "limites": {"vram_tope_MiB": V.VRAM_TOPE, "vram_otras_max_MiB": V.VRAM_OTRAS_MAX,
                     "pico_e2_medido_MiB": V.PICO_E2_MEDIDO, "crecimiento_ajeno_max_MiB": V.CRECIMIENTO_AJENO_MAX,
                     "margen_MiB": V.MARGEN, "variacion_otras_max_MiB": V.VARIACION_OTRAS_MAX,
                     "uso_gpu_max_pct": V.UTILIZACION_GPU_MAX, "inactividad_min_s": V.INACTIVIDAD_MIN_S},
         "sin_cambios": "tareas, oráculos, prompts, configuraciones, orden, temperaturas, semillas, regla de decisión, "
                        "E2, límites de VRAM, STOP, monitor de memoria, persona, fondo animado, propiedad de procesos y "
                        "reintentos por terceros: los de V4.2",
         "sha256": {a: hashlib.sha256((RAIZ / a).read_bytes()).hexdigest() for a in V.ARCHIVOS_V4}}
V.PRERREGISTRO_V4.write_text(json.dumps(datos, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
for a, h in datos["sha256"].items():
    print(h, a)
