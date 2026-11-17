"""Laboratorio V4.3: lanza `comparar` de F1-VRAM-EXP-V4.3 SIN cambiarlo, con comprobaciones previas y vigilancia térmica.

    python -B -X utf8 lab_vram/f1_v4_3_supervisado.py EXTERNOS SALIDA_NUEVA PUERTAS.json

- Antes de empezar: prerregistros V1–V4.3 intactos, puertas del MISMO código, RAM disponible ≥ 6144 MiB y las
  condiciones de V4.3 (persona, VRAM ajena ≤ 1992, GPU); E2 lo comprueba `comparar` en cada arranque. Si algo falla,
  no se inicia.
- Durante: lee la temperatura de la GPU con `nvidia-smi` (solo lectura; nunca toca potencia ni ventiladores). Anomalía
  = ≥ 90 °C, ≥ 87 °C en dos lecturas seguidas o freno térmico activo. Entonces interrumpe el hilo principal
  (KeyboardInterrupt): los `finally` de V2-F.1 y V4.3 cierran el servidor propio y restauran Wallpaper Engine.
- Todo queda junto a SALIDA (`SALIDA_supervision.json`, `SALIDA_termica.jsonl`): `comparar` exige una carpeta nueva.
"""
import _thread
import ctypes
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
from eq3 import evaluar_f1_vram_exp_v4_3 as V  # noqa: E402

RAM_MIN_MIB = 6144
TEMP_CORTE, TEMP_AVISO, INTERVALO_S = 90, 87, 5.0


def ram_disponible_mib():
    class M(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong)] + [
            (n, ctypes.c_ulonglong) for n in ("tot", "disp", "totpf", "disppf", "totv", "dispv", "ext")]
    m = M()
    m.dwLength = ctypes.sizeof(M)
    return m.disp // 2**20 if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)) else None


def leer_gpu():
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=temperature.gpu,clocks_throttle_reasons.hw_thermal_slowdown,"
                            "clocks_throttle_reasons.sw_thermal_slowdown,utilization.gpu,memory.used",
                            "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=10)
        t, hw, sw, u, m = [x.strip() for x in r.stdout.strip().splitlines()[0].split(",")]
        return {"temp_C": int(t), "freno_termico": "Active" in (hw, sw), "uso_pct": int(u), "vram_MiB": int(m)}
    except Exception as e:                                      # sensor no disponible: se anota, no se inventa
        return {"error": f"{type(e).__name__}: {e}"}


def anomalia(lectura, previa):
    t = lectura.get("temp_C")
    if lectura.get("freno_termico"):
        return "freno_termico_activo"
    if t is not None and t >= TEMP_CORTE:
        return f"temperatura_{t}C"
    if t is not None and t >= TEMP_AVISO and (previa or {}).get("temp_C", 0) >= TEMP_AVISO:
        return f"temperatura_sostenida_{previa['temp_C']}-{t}C"
    return None


class VigiaTermico(threading.Thread):
    def __init__(self, registro: Path, leer=leer_gpu, interrumpir=_thread.interrupt_main, intervalo=INTERVALO_S):
        super().__init__(daemon=True)
        self.registro, self.leer, self.interrumpir, self.intervalo = registro, leer, interrumpir, intervalo
        self.motivo, self.maxima, self.sin_sensor, self._fin = None, None, 0, threading.Event()

    def run(self):
        previa = None
        while not self._fin.is_set():
            lec = self.leer() | {"t": time.strftime("%H:%M:%S")}
            with self.registro.open("a", encoding="utf-8") as f:
                f.write(json.dumps(lec) + "\n")
            if "temp_C" in lec:
                self.maxima = max(self.maxima or 0, lec["temp_C"])
            else:
                self.sin_sensor += 1
            m = anomalia(lec, previa)
            if m:
                self.motivo = m
                self.interrumpir()
                return
            previa = lec
            self._fin.wait(self.intervalo)

    def detener(self):
        self._fin.set()


def comprobaciones_previas(puertas: Path) -> dict:
    pu = json.loads(puertas.read_text(encoding="utf-8"))
    c = V.condiciones(V.X.VENTANA_INICIO_S)
    out = {"prerregistros": V.comprobar_v4(), "puertas_ok": pu.get("ok") is True and pu.get("variante") == V.VARIANTE,
           "puertas_mismo_codigo": pu.get("codigo") == V.huella_codigo(), "ram_disponible_MiB": ram_disponible_mib(),
           "condiciones_con_fondo_activo": c, "gpu": leer_gpu(), "e2": V.E2}
    out["ok"] = (not out["prerregistros"] and out["puertas_ok"] and out["puertas_mismo_codigo"]
                 and (out["ram_disponible_MiB"] or 0) >= RAM_MIN_MIB and not c["persona"]["hay"]
                 and "temp_C" in out["gpu"] and anomalia(out["gpu"], None) is None)
    return out                     # la VRAM ajena y la GPU con el fondo DETENIDO las exige `comparar` al empezar


def main(externos, salida, puertas) -> int:
    salida, puertas = Path(salida), Path(puertas)
    sup = salida.parent / f"{salida.name}_supervision.json"
    estado = {"inicio": time.strftime("%Y-%m-%dT%H:%M:%S"), "variante": V.VARIANTE}
    guardar = lambda: sup.write_text(json.dumps(estado, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    salida.parent.mkdir(parents=True, exist_ok=True)
    estado["previas"] = comprobaciones_previas(puertas)
    guardar()
    if not estado["previas"]["ok"]:
        print("NO SE INICIA:", json.dumps(estado["previas"], ensure_ascii=False, default=str)[:1500])
        return 4
    V.servidor_pc.preparar_proceso()
    vt = VigiaTermico(salida.parent / f"{salida.name}_termica.jsonl")
    vt.start()
    rc = 0
    try:
        r = V.comparar(Path(externos), salida, puertas)
        estado["resultado"] = {"abortada": r.get("abortada"), "valida": r.get("valida"), "filas": len(r["filas"])}
        rc = 0 if r.get("abortada") is None else 1
    except KeyboardInterrupt:
        estado["detenida"] = f"anomalia_termica: {vt.motivo}" if vt.motivo else "interrupcion_externa"
        rc = 5
    except V.EV.Abortada as e:
        estado["detenida"] = f"abortada: {e}"
        rc = 2
    except V.EV.FugaDeOraculo as e:
        estado["detenida"] = f"fuga_del_oraculo: {e}"
        rc = 3
    finally:
        vt.detener()
        estado.update(fin=time.strftime("%Y-%m-%dT%H:%M:%S"), temp_maxima_C=vt.maxima, lecturas_sin_sensor=vt.sin_sensor,
                      llama_al_final=V.servidor_pc.procesos_llama(), codigo_salida=rc)
        guardar()
    print(json.dumps({k: estado.get(k) for k in ("resultado", "detenida", "temp_maxima_C", "codigo_salida")},
                     ensure_ascii=False, default=str))
    return rc


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:4]))
