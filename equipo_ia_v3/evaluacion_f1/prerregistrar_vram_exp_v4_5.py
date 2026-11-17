"""F1-VRAM-EXP-V4.5 — escribe `evaluacion_f1/PRERREGISTRO_F1_VRAM_EXP_v4_5.json`.

    python -B evaluacion_f1/prerregistrar_vram_exp_v4_5.py

V4.5 añade a V4.4 la convivencia con un PC compartido (origen de los eventos térmicos, esperas de hasta 4 h, STOP
global, tiempos de espera humana) tras la F1 con V4.4 invalidada por un freno térmico ocurrido con Qwen cerrado y un
juego usando la GPU. La F1 se repetirá DESDE CERO (90 ejecuciones). V4.4 y V1–V4.4 se conservan por su SHA-256.
"""
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
from eq3 import evaluar_f1_vram_exp_v4_5 as V  # noqa: E402
from eq3 import termica_v4_5 as TM  # noqa: E402

if V.PRERREGISTRO_V4.is_file():
    raise SystemExit(f"ya existe {V.PRERREGISTRO_V4.name}: no se sobrescribe")
datos = {"version": "4.5", "variante": V.VARIANTE,
         "base": "prerregistro V4.4 (conservado) + convivencia con un PC compartido",
         "fecha_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
         "estado": "PRERREGISTRADO ANTES DE LAS PUERTAS; F1 autorizada por el usuario SOLO si todas las puertas pasan",
         "motivo": "F1 con V4.4: protocolo térmico correcto con carga propia (máx. 81 °C, 0 frenos); tras 44 filas, con "
                   "Qwen cerrado y un juego usando la GPU, freno térmico de hardware a 74 °C (crítico en V4.4)",
         "repeticion": "90 ejecuciones desde cero; las filas de V4.2 (39), V4.3 (31) y V4.4 (44) NO se reutilizan",
         "cambios_sobre_v4_4": [
             "origen de cada evento térmico: propio (tarea en curso o cualquier llama vivo) o incierto → crítico como en "
             "V4.4; externo verificado (sin tarea y sin ningún llama) → interferencia anotada, no crítica, y la "
             "evaluación espera REPOSO_EXTERNO_S sin eventos externos; externo ≥ T_EXTERNA_MAX → inseguro (aborta); "
             "fallo de supervisión → crítico siempre",
             "espera máxima por persona, recursos o interferencia: MAX_ESPERA_PERSONA_S (4 h); sin generar y con Qwen "
             "cerrado; cada pausa registrada (inicio, duración, motivos)",
             "STOP global: archivo SALIDA/STOP corta la generación o la espera y aborta de forma ordenada",
             "Wallpaper Engine se PAUSA (ORDEN_FONDO = pause) en vez de detenerse (decisión del usuario): sigue visible, "
             "GPU 31 % → 6 % medido; restauración con play y guardián sin cambios",
             "tiempos por separado: generacion_s, enfriamiento_s, espera_humana_s, trabajo_s, total_s; intentos "
             "interrumpidos por fila",
             "puertas: G5 añade F25; G10 añade test_eq3_compartido_v4_5; G13 interferencia externa en reposo real; "
             "G14 STOP global real"],
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
                        "decisión, E2, límites de VRAM y RAM, límites térmicos y enfriamiento a 60 °C, persona, fondo "
                        "animado, propiedad de procesos y control de fugas con procedencia: los de V4.4",
         "sha256": {a: hashlib.sha256((RAIZ / a).read_bytes()).hexdigest() for a in V.ARCHIVOS_V4}}
V.PRERREGISTRO_V4.write_text(json.dumps(datos, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
for a, h in datos["sha256"].items():
    print(h, a)
