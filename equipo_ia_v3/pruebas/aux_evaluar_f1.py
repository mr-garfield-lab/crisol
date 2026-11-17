"""Auxiliar de test_eq3_evaluar_f1.py (no es un módulo de pruebas: unittest no lo descubre).

    python -B [eq3/lanzador_eq2.py] pruebas/aux_evaluar_f1.py ESCENARIO CARPETA_TMP

Ejecuta `eq3.evaluar_f1.ejecutar_tarea` con el ciclo de vida REAL de V2-F.1 contra su servidor FALSO (procesos, sockets
y archivos reales; el modelo es simulado). Imprime un JSON en la última línea.
"""
import copy
import json
import socket
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "pruebas"))
from eq3 import servidor_pc  # noqa: E402

servidor_pc.preparar_proceso()
from eq2 import config  # noqa: E402
from eq3 import evaluar_f1 as EV  # noqa: E402
from aux_servidor_pc import AYUDA, FAKE, externos  # noqa: E402


def puerto():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def fabrica(ver, pausa=0.0):
    def crear():
        return servidor_pc.crear_backend(
            ver, puerto=puerto(), comando=[sys.executable, "-B", str(FAKE), "--fake-modo", "normal", "--fake-carga",
                                           "0.2", "--fake-pausa", str(pausa)],
            detector=lambda: None, intervalo_monitor=0.05, espera_monitor=1,
            srv_kw=dict(ayuda_fn=lambda: AYUDA, gracia_term=3, gracia_kill=3, max_carga_s=20, sondeo_s=0.05))
    return crear


def resumen(f):
    return {"respuesta": f["respuesta"], "evaluacion": f["evaluacion"], "infraestructura": f.get("infraestructura"),
            "servidor_terminado": f["servidor_terminado"], "prompt": f["prompt_primer_paso_sha256"],
            "peticiones": f["metricas"]["peticiones"], "llamadas": f["metricas"]["llamadas"],
            "tokens_generados": f["metricas"]["tokens_generados"], "segundos_total": f["segundos_total"],
            "cierre": f["cierre"], "e3": f.get("e3"), "votos": f.get("votos"), "elegida": f.get("elegida"),
            "muestras": len(f["muestras"])}


def main(escenario, tmp):
    t = Path(tmp)
    config.MIN_MODELO_BYTES = 1
    EV.preparar_contexto()
    ext, reg = externos(t)
    ver = servidor_pc.verificar_externos(ext, reg)
    tareas, oraculos = EV.E.cargar()
    out = {"escenario": escenario}
    if escenario == "prompts":
        for c in ("S1", "E3", "S1x3"):
            vig = EV.Vigia(medir=lambda: {"usada": 1000, "total": 8192, "procesos": {}}, intervalo=0.05).iniciar()
            try:
                out[c] = resumen(EV.ejecutar_tarea(c, tareas["T01"], oraculos["T01"], oraculos, t / c, fabrica(ver), vig))
            finally:
                out[c]["vram"] = vig.detener()
        out["config_tras"] = [config.TEMPERATURA, config.SEMILLA]
        out["carpetas"] = sorted(p.name for p in t.iterdir())
    elif escenario in ("fuga_S1", "fuga_E3"):
        malos = copy.deepcopy(oraculos)
        malos["T01"]["trampa"] = "No escribas pruebas"          # está en las instrucciones de A1 de V2-F.1
        vig = EV.Vigia(medir=lambda: None, intervalo=0.05).iniciar()
        try:
            EV.ejecutar_tarea(escenario[5:], tareas["T01"], oraculos["T01"], malos, t / "x", fabrica(ver), vig)
            out["fuga"] = None
        except EV.FugaDeOraculo as e:
            out["fuga"] = str(e)
        finally:
            vig.detener()
        out["llama_falsos_vivos"] = [p for p in servidor_pc.procesos_llama(lambda: [(0, "x")]) or []]
    elif escenario in ("vram_S1", "vram_E3"):
        vig = EV.Vigia(medir=lambda: {"usada": 7000, "total": 8192, "procesos": {}}, intervalo=0.05).iniciar()
        try:
            out["fila"] = resumen(EV.ejecutar_tarea(escenario[5:], tareas["T01"], oraculos["T01"], oraculos, t / "v",
                                                    fabrica(ver, pausa=20.0), vig))
        finally:
            out["vram"] = vig.detener()
    return out


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1], sys.argv[2]), ensure_ascii=False, default=str))
