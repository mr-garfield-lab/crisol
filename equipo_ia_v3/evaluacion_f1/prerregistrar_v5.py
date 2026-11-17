"""F1-V5 — escribe `evaluacion_f1/PRERREGISTRO_F1_V5.json`.

    python -B evaluacion_f1/prerregistrar_v5.py

V5 = V4.5.1 (sin modificar) + 4 cerebros, E2 con caché KV de 8 bits y sin «thinking», contexto 4096 y un equipo de dos
cerebros (`docs/V31_F1_V5.md`). Se prerregistra ANTES de las puertas; ninguna fase se lanza sin aprobación del usuario.
"""
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
from eq3 import evaluar_f1_v5 as V  # noqa: E402

if V.PRERREGISTRO.is_file():
    raise SystemExit(f"ya existe {V.PRERREGISTRO.name}: no se sobrescribe")
datos = {"version": "5", "variante": V.VARIANTE,
         "base": "F1-VRAM-EXP-V4.5.1 (código, prerregistro y resultados conservados sin cambios)",
         "fecha_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
         "estado": "PRERREGISTRADO ANTES DE LAS PUERTAS; autorizado por el usuario (2026-11-13) preparar V5 y sus "
                   "puertas; el cribado y el equipo se lanzan SOLO con su aprobación",
         "motivo": "F1 V4.5.1: sin diferencia demostrable entre S1, S1×3 y E3 con un solo cerebro; los revisores del "
                   "mismo modelo no corrigieron ningún error",
         "cerebros": V.cargar_modelos(), "orden_cribado": list(V.ORDEN_MODELOS),
         "llama_e2": V.E2, "ctx": V.CTX,
         "limites": {"vram_tope_MiB": V.VRAM_TOPE, "vram_otras_max_MiB": V.VRAM_OTRAS_MAX, "pico_max_MiB": V.PICO_MAX,
                     "margen_MiB": V.MARGEN},
         "ruta_agentes": V.RUTA_AGENTES, "orden_equipo": V.ORDEN_EQUIPO,
         "reglas": {
             "cribado": "S1, 15 tareas, 1 repetición. Generador = más CORRECTO; empate → menos FALLO_SEGURIDAD; empate → "
                        "orden del registro. Revisor = el mejor de OTRA familia con la misma regla. Solo cuentan los "
                        "cerebros con todas sus filas y sin fallos de infraestructura.",
             "equipo": "S1(generador), E3 con un cerebro y E3 con dos, 2 repeticiones contrabalanceadas. H1: E3 dos "
                       "supera a S1; H2: E3 dos supera a E3 uno.",
             "supera": f"≥ {V.UMBRAL_VENTAJA} CORRECTO más en TODAS las repeticiones y no más FALLO_SEGURIDAD (la de F1)"},
         "politica_interrupcion": "una fase abortada (STOP, térmica crítica, externo inseguro, VRAM, fuga, cambio de "
                                  "cerebro fallido o > 4 h de espera) NO es válida, se conserva y NO se reinicia sola; una "
                                  "tarea cortada por terceros se repite desde cero (≤ 2)",
         "sin_cambios": "tareas, oráculos, prompts, temperatura, semillas, topes de salida por paso, protocolo térmico, "
                        "vigía de VRAM, persona y recursos, fondo animado, STOP global y control de fugas: los de V4.5.1",
         "sha256": {a: hashlib.sha256((RAIZ / a).read_bytes()).hexdigest() for a in V.ARCHIVOS_V5}}
V.PRERREGISTRO.write_text(json.dumps(datos, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
for a, h in datos["sha256"].items():
    print(h, a)
