"""F1-V5.1 — escribe `evaluacion_f1/PRERREGISTRO_F1_V5_1.json`.

    python -B evaluacion_f1/prerregistrar_v5_1.py

V5.1 = V5 (sin modificar) + eco verificado de la continuación (falso positivo de T08) + seis cerebros + descanso al empezar cada
bloque (`docs/V31_F1_V5_1.md`). Se prerregistra ANTES de las puertas; ninguna fase se lanza sin aprobación del usuario.
"""
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
from eq3 import evaluar_f1_v5 as V5  # noqa: E402
from eq3 import evaluar_f1_v5_1 as V  # noqa: E402

if V.PRERREGISTRO.is_file():
    raise SystemExit(f"ya existe {V.PRERREGISTRO.name}: no se sobrescribe")
datos = {"version": "5.1", "variante": V.VARIANTE,
         "base": "F1-V5 (código, prerregistro y evidencia conservados sin cambios)",
         "fecha_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
         "estado": "PRERREGISTRADO ANTES DE LAS PUERTAS; autorizado por el usuario (2026-11-13) preparar la versión completa; "
                   "el cribado y el equipo se lanzan SOLO con su aprobación",
         "motivo": "equipo1 de V5 se abortó en T08 (E3 qwen3+yi) por un falso positivo del control de fugas: la continuación "
                   "(prefill) reenvía la respuesta cortada del propio modelo como mensaje «assistant»; diagnóstico "
                   "reproducido en evidencias/v31_f1_v5/diagnostico_t08",
         "cambios_sobre_v5": [
             "control de fugas: un mensaje «assistant» que repite byte a byte (SHA-256) una respuesta de ESTE servidor en ESTA "
             "tarea no cuenta como texto del evaluador; se anota (ecos_verificados); todo lo demás, igual (fallo cerrado)",
             "seis cerebros: los de V5 + Gemma 4 E4B y Ministral 3 8B (aptos en el banco de capacidad); cribado S1 de las 15 "
             "tareas con los seis, con la regla de V5",
             "descanso al empezar cada bloque: ≥ 60 s y ≤ 55 °C sin freno de software (máx. 300 s; si no, se anota); ningún "
             "límite térmico cambia",
             "puerta G17: regresión real del caso T08 (E3 qwen3 + yi)"],
         "cerebros": json.loads(V.MODELOS_JSON.read_text(encoding="utf-8"))["modelos"],
         "orden_cribado": list(V.ORDEN_MODELOS),
         "descanso_bloque": {"descanso_s": V.DESCANSO_BLOQUE_S, "objetivo_C": V.T_INICIO_BLOQUE,
                             "max_s": V.MAX_ESPERA_BLOQUE_S},
         "llama_e2": V5.E2, "ctx": V5.CTX,
         "limites": {"vram_tope_MiB": V5.VRAM_TOPE, "vram_otras_max_MiB": V5.VRAM_OTRAS_MAX,
                     "pico_max_MiB": V5.PICO_MAX, "margen_MiB": V5.MARGEN},
         "ruta_agentes": V5.RUTA_AGENTES, "orden_equipo": V5.ORDEN_EQUIPO,
         "reglas": {
             "cribado": "S1, 15 tareas, 1 repetición, 6 cerebros. Generador = más CORRECTO; empate → menos FALLO_SEGURIDAD; "
                        "empate → orden del registro. Revisor = el mejor de OTRA familia con la misma regla. Solo cuentan los "
                        "cerebros con todas sus filas y sin fallos de infraestructura.",
             "equipo": "S1(generador), E3 con un cerebro y E3 con dos, 2 repeticiones contrabalanceadas. H1: E3 dos supera a "
                       "S1; H2: E3 dos supera a E3 uno.",
             "supera": f"≥ {V5.UMBRAL_VENTAJA} CORRECTO más en TODAS las repeticiones y no más FALLO_SEGURIDAD (la de F1)"},
         "politica_interrupcion": "una fase abortada (STOP, térmica crítica, externo inseguro, VRAM, fuga, cambio de cerebro "
                                  "fallido o > 4 h de espera) NO es válida, se conserva y NO se reinicia sola; una tarea cortada "
                                  "por terceros se repite desde cero (≤ 2)",
         "sin_cambios": "tareas, oráculos, prompts, temperatura, semillas, topes de salida por paso, protocolo térmico y sus "
                        "límites, vigía de VRAM, persona y recursos, fondo animado, STOP global, E2 de V5 y control de fugas "
                        "con procedencia: los de V5 y V4.5.1",
         "sha256": {a: hashlib.sha256((RAIZ / a).read_bytes()).hexdigest() for a in V.ARCHIVOS_V5_1}}
V.PRERREGISTRO.write_text(json.dumps(datos, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
for a, h in datos["sha256"].items():
    print(h, a)
