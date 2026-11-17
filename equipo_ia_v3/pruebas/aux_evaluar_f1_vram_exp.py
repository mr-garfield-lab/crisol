"""Auxiliar de test_eq3_evaluar_f1_vram_exp.py (no es un módulo de pruebas: unittest no lo descubre).

    python -B [eq3/lanzador_eq2.py] pruebas/aux_evaluar_f1_vram_exp.py ESCENARIO CARPETA_TMP

Ejecuta `eq3.evaluar_f1.ejecutar_tarea` con el vigía EXPERIMENTAL (`VigiaExp`) y el ciclo de vida REAL de V2-F.1 contra
su servidor FALSO. La VRAM y la actividad de terceros son simuladas. Imprime un JSON en la última línea.
"""
import json
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "pruebas"))
from eq3 import servidor_pc  # noqa: E402

servidor_pc.preparar_proceso()
from eq2 import config  # noqa: E402
from eq3 import evaluar_f1 as EV  # noqa: E402
from eq3 import evaluar_f1_vram_exp as X  # noqa: E402
from aux_evaluar_f1 import fabrica, resumen  # noqa: E402
from aux_servidor_pc import externos  # noqa: E402


def main(escenario, tmp):
    t = Path(tmp)
    config.MIN_MODELO_BYTES = 1
    EV.preparar_contexto()
    ext, reg = externos(t)
    ver = servidor_pc.verificar_externos(ext, reg)
    tareas, oraculos = EV.E.cargar()
    nombre, c = escenario.split("_")
    libre = {"inactividad_s": 10_000.0, "sesiones": {}, "notificacion": 5, "motivos": []}
    act = lambda: libre
    if nombre == "terceros":
        t0 = time.monotonic()
        act = lambda: libre | {"inactividad_s": 10_000.0 if time.monotonic() - t0 < 1.0 else 0.0}
    mib = {"vram6900": 6900, "vram6913": 6913}.get(nombre, 4000)
    vig = X.VigiaExp(medir=lambda: {"usada": mib, "total": 8192, "procesos": {}}, intervalo=0.05, act=act).iniciar()
    out = {"escenario": escenario}
    try:
        out["fila"] = resumen(EV.ejecutar_tarea(c, tareas["T01"], oraculos["T01"], oraculos, t / "v",
                                                fabrica(ver, pausa=0.0 if nombre == "vram6900" else 20.0), vig))
    finally:
        out["vram"] = vig.detener()
    return out


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1], sys.argv[2]), ensure_ascii=False, default=str))
