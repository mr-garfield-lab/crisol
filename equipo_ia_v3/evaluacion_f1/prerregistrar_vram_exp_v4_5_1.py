"""F1-VRAM-EXP-V4.5.1 — escribe `evaluacion_f1/PRERREGISTRO_F1_VRAM_EXP_v4_5_1.json`.

    python -B evaluacion_f1/prerregistrar_vram_exp_v4_5_1.py

V4.5.1 = V4.5 + UNA corrección en la puerta G12 (la `Termica` de la prueba se creaba sin `propio_activo`). Las puertas de
V4.5 (2026-11-13) dieron 13/14: G12 falló por esa causa, comprobada con su evidencia (`verificacion_causa_g12.json`). V4.5 y
su prerregistro NO se modifican; la F1 se hará con V4.5.1 DESDE CERO (90 ejecuciones).
"""
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
from eq3 import evaluar_f1_vram_exp_v4_5_1 as V  # noqa: E402
from eq3 import termica_v4_5 as TM  # noqa: E402

if V.PRERREGISTRO_V4.is_file():
    raise SystemExit(f"ya existe {V.PRERREGISTRO_V4.name}: no se sobrescribe")
datos = {"version": "4.5.1", "variante": V.VARIANTE,
         "base": "prerregistro V4.5 (conservado, sin cambios) + corrección de la puerta G12",
         "fecha_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
         "estado": "PRERREGISTRADO ANTES DE LAS PUERTAS; F1 autorizada por el usuario (2026-11-13) SOLO si las 14 puertas "
                   "pasan; ante un fallo crítico o pérdida de integridad se detiene y se conserva la evidencia",
         "motivo": "las puertas de V4.5 (evidencias/v31_f1_vram_exp_v4_5/puertas2) dieron 13/14: G12 falló porque su "
                   "Termica no recibía `propio_activo` (origen incierto por defecto) aunque su servidor llama estaba vivo; "
                   "el corte fue correcto (0,56 s, cierre limpio, VRAM liberada) y la temperatura máxima real fue 66 °C",
         "verificacion_de_la_causa": "evidencias/v31_f1_vram_exp_v4_5_1/verificacion_causa_g12.json: la lógica de atribución "
                                     "de V4.5 se comporta como está diseñada (propio / externo / incierto); el defecto era "
                                     "del escenario simulado de G12",
         "repeticion": "90 ejecuciones desde cero; las filas de V4.2 (39), V4.3 (31) y V4.4 (44) NO se reutilizan",
         "cambios_sobre_v4_5": [
             "G12: la Termica se crea con `termica_g12` (origen REAL `propio_activo`, función de V4.5 sin cambios); el "
             "criterio de G12 sigue siendo exacto: crítico == «freno_termico_hardware», corte ≤ 3 s, cierre limpio y VRAM "
             "liberada; se anota además `origen_atribuido`",
             "G10 añade test_eq3_g12_v4_5_1 (atribución propio / externo / incierto con la misma lógica de V4.5, caso "
             "negativo de origen incierto, y código de V4.5.1 idéntico al de V4.5 salvo corte_termico_real, g10 y g5)",
             "G5 añade F26 (mutaciones de V4.5.1); las demás baterías (F15–F25) se repiten",
             "nombres de versión y lista de archivos protegidos (V4.5 y su evidencia se conservan por SHA-256)"],
         "politica_interrupcion": "una F1 abortada (STOP, térmica crítica, externo inseguro, fallo de supervisión, "
                                  "VRAM, fuga o > 4 h de espera) NO es válida, se conserva como evidencia y NO se "
                                  "reinicia automáticamente; una tarea cortada por terceros se repite desde cero (≤ 2)",
         "termica": {"t_reanudar_C": TM.T_REANUDAR, "max_enfriar_s": TM.MAX_ENFRIAR_S, "t_critica_C": TM.T_CRITICA,
                     "max_freno_sw_s": TM.MAX_FRENO_SW_S, "max_fallos_lectura": TM.MAX_FALLOS_LECTURA,
                     "t_externa_max_C": TM.T_EXTERNA_MAX, "reposo_externo_s": TM.REPOSO_EXTERNO_S,
                     "intervalo_s": TM.INTERVALO_S,
                     "nunca": "potencia, frecuencias, ventiladores ni límites de hardware"},
         "espera_max_persona_s": V.MAX_ESPERA_PERSONA_S,
         "llama_e2": V.E2,
         "limites": {"vram_tope_MiB": V.VRAM_TOPE, "vram_otras_max_MiB": V.VRAM_OTRAS_MAX,
                     "pico_e2_medido_MiB": V.PICO_E2_MEDIDO, "margen_MiB": V.MARGEN,
                     "variacion_otras_max_MiB": V.VARIACION_OTRAS_MAX, "uso_gpu_max_pct": V.UTILIZACION_GPU_MAX,
                     "inactividad_min_s": V.INACTIVIDAD_MIN_S},
         "sin_cambios": "tareas, oráculos, prompts, configuraciones, orden, temperaturas de muestreo, semillas, regla de "
                        "decisión, E2, límites de VRAM y RAM, límites térmicos y enfriamiento a 60 °C, lógica de atribución "
                        "(eq3/termica_v4_5.py, el mismo archivo), STOP global, pausas de hasta 4 h, persona, fondo "
                        "animado (pausa), propiedad de procesos y control de fugas con procedencia: los de V4.5",
         "sha256": {a: hashlib.sha256((RAIZ / a).read_bytes()).hexdigest() for a in V.ARCHIVOS_V4}}
V.PRERREGISTRO_V4.write_text(json.dumps(datos, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
for a, h in datos["sha256"].items():
    print(h, a)
