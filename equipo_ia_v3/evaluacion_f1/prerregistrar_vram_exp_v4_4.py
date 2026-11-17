"""F1-VRAM-EXP-V4.4 — escribe `evaluacion_f1/PRERREGISTRO_F1_VRAM_EXP_v4_4.json`.

    python -B evaluacion_f1/prerregistrar_vram_exp_v4_4.py

V4.4 añade a V4.3 un protocolo térmico (enfriar antes de cada petición, igual en S1, S1×3 y E3; vigilancia durante la
generación; tiempos de enfriamiento, generación y trabajo por separado) tras la F1 con V4.3 detenida por un freno térmico
(31/90). La F1 se repetirá DESDE CERO (90 ejecuciones). V4.3, V4.2 y V1–V4.3 se conservan y se incluyen por su SHA-256.
"""
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
from eq3 import evaluar_f1_vram_exp_v4_4 as V  # noqa: E402
from eq3 import termica_v4_4 as TM  # noqa: E402

if V.PRERREGISTRO_V4.is_file():
    raise SystemExit(f"ya existe {V.PRERREGISTRO_V4.name}: no se sobrescribe")
datos = {"version": "4.4", "variante": V.VARIANTE,
         "base": "prerregistro V4.3 (conservado) + protocolo térmico tras la F1 detenida por temperatura",
         "fecha_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
         "estado": "PRERREGISTRADO, NO EJECUTADO (la evaluación F1 completa NO está autorizada)",
         "motivo": "F1 con V4.3 detenida en r1/E3/T02 por freno térmico a 84 °C (59→84 °C en 26 s); 31/90 filas, no "
                   "válida. Decisión del usuario: repetir las 90 desde cero con un protocolo térmico uniforme",
         "repeticion": "las 90 ejecuciones desde cero; las filas de V4.2 (39) y V4.3 (31) NO se reutilizan",
         "cambios_sobre_v4_3": [
             "antes de CADA petición al modelo (S1, S1×3 y E3 por igual): esperar a ≤ T_REANUDAR y sin freno térmico de "
             "software, como mucho MAX_ENFRIAR_S; si no, aborto seguro sin enviar nada",
             "hilo térmico (nvidia-smi, solo lectura, cada INTERVALO_S) durante toda la evaluación; el vigía de cada tarea "
             "lo consulta en cada parar() y corta la petición en curso (también en E3, con su STOP)",
             "parada inmediata: freno térmico de hardware o cualquier freno de hardware, ≥ T_CRITICA, freno térmico de "
             "software continuo ≥ MAX_FRENO_SW_S, MAX_FALLOS_LECTURA lecturas sin temperatura o hilo muerto; un corte "
             "térmico aborta TODA la evaluación (anotado en comparacion.json)",
             "registro por separado de frenos (hw térmico, sw térmico, hw, hw de potencia), temperatura, relojes, "
             "ventilador, pstate, uso, VRAM y potencia (null si el sensor no la da)",
             "tiempos por separado: enfriamiento_s, generacion_s, trabajo_s (= total − enfriamiento), total_s, pico_C",
             "puertas: G5 añade F24; G10 añade test_eq3_termica_v4_4; G11 sensores reales; G12 corte térmico real"],
         "termica": {"t_reanudar_C": TM.T_REANUDAR, "max_enfriar_s": TM.MAX_ENFRIAR_S, "t_aviso_C": TM.T_AVISO,
                     "t_critica_C": TM.T_CRITICA, "max_freno_sw_s": TM.MAX_FRENO_SW_S,
                     "max_fallos_lectura": TM.MAX_FALLOS_LECTURA, "intervalo_s": TM.INTERVALO_S,
                     "campos_nvidia_smi": list(TM.CAMPOS),
                     "tarjeta": "NVIDIA GeForce RTX 3050, 8192 MiB, 115 W; objetivo 83 °C, máx. operación 92 °C, "
                                "freno hw 94 °C, apagado 97 °C (nvidia-smi -q)",
                     "nunca": "potencia, frecuencias, ventiladores ni límites de hardware"},
         "procedencia": {"fuentes_relevo": sorted(V.FUENTES_RELEVO), "contexto_min": V.CONTEXTO_MIN,
                         "solo_configuracion": "E3"},
         "llama_e2": V.E2,
         "limites": {"vram_tope_MiB": V.VRAM_TOPE, "vram_otras_max_MiB": V.VRAM_OTRAS_MAX,
                     "pico_e2_medido_MiB": V.PICO_E2_MEDIDO, "crecimiento_ajeno_max_MiB": V.CRECIMIENTO_AJENO_MAX,
                     "margen_MiB": V.MARGEN, "variacion_otras_max_MiB": V.VARIACION_OTRAS_MAX,
                     "uso_gpu_max_pct": V.UTILIZACION_GPU_MAX, "inactividad_min_s": V.INACTIVIDAD_MIN_S},
         "sin_cambios": "tareas, oráculos, prompts, configuraciones, orden, temperaturas de muestreo, semillas, regla de "
                        "decisión, E2, límites de VRAM y RAM, STOP, persona, fondo animado, propiedad de procesos, "
                        "reintentos por terceros y control de fugas con procedencia: los de V4.3",
         "sha256": {a: hashlib.sha256((RAIZ / a).read_bytes()).hexdigest() for a in V.ARCHIVOS_V4}}
V.PRERREGISTRO_V4.write_text(json.dumps(datos, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
for a, h in datos["sha256"].items():
    print(h, a)
