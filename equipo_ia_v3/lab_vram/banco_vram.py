"""Equipo IA V3.1 — LABORATORIO de VRAM (experimental, aislado). NO forma parte de V2-F.1 ni de la configuración estable.

    python -B -X utf8 lab_vram/banco_vram.py EXTERNOS SALIDA_NUEVA CONFIG [CONFIG ...] [--reps 3]
    python -B -X utf8 lab_vram/banco_vram.py --lista

Mide, para cada configuración de `llama-server` (las opciones por defecto del PC más las de CONFIGURACIONES), la VRAM
(nvidia-smi y los búferes que declara llama.cpp), la RAM, los tokens/s de prompt y de generación, el tiempo hasta el
primer token, el uso de CPU y GPU, los fallos de página duros y la liberación de recursos tras un corte (STOP).

Protecciones (todas fallan cerradas):
- externos verificados por SHA-256 (`servidor_pc.verificar_externos`) y ningún proceso llama previo;
- antes de CADA configuración: nadie usando el PC (≥ 10 min sin teclado/ratón, ninguna otra sesión, sin pantalla
  completa D3D ni presentación) y VRAM ajena ≤ 6912 − 4780 − 300; si no, espera (máx. 30 min) u omite;
- durante la prueba, un vigía cada 0,5 s: VRAM total > 6912 MiB o entrada de teclado/ratón ⇒ se termina el servidor
  PROPIO (el `Popen` lanzado aquí, nunca otro proceso) y se registra;
- un solo modelo cargado a la vez; nada generado se ejecuta (solo se mide la velocidad y se guarda el SHA-256 del texto).
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import http.client
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
from eq3 import evaluar_f1_vram_exp as X  # noqa: E402
from eq3 import majflt_windows, servidor_pc  # noqa: E402

TOPE_MIB = X.VRAM_TOPE_EXP                      # 6912: el límite experimental autorizado; aquí NO se cambia
OTRAS_MAX_MIB = X.VRAM_OTRAS_MAX_EXP            # 1832
INACTIVIDAD_MIN_S = 600
ESPERA_MAX_S = 1800
VIGIA_S = 0.5
CTX, HILOS = 2048, 6
BASE = ["-c", str(CTX), "-t", str(HILOS), "-np", "1", "--no-ui"]       # lo que pasa V2-F.1 (`construir_argv`)
CAPAS = 28                                      # Qwen2.5-7B: 28 bloques (blk.0 … blk.27)
REF_TOKS = 41.0                                 # referencia aproximada del humo de F1

E = ["--fit", "off", "-ngl", "all", "-fa", "on", "-ub", "128", "-b", "512"]
CONFIGURACIONES = {
    "A0_estable": [],                                                       # tal como lo lanza V2-F.1 hoy
    "A1_todo_gpu": ["--fit", "off", "-ngl", "all", "-fa", "on"],
    "E1_ub256": ["--fit", "off", "-ngl", "all", "-fa", "on", "-ub", "256", "-b", "512"],
    "E2_ub128": E,
    "E3_ub128_kvq8": E + ["-ctk", "q8_0", "-ctv", "q8_0"],
    "E4_ub128_kv_ram": E + ["-nkvo"],
    "B2_cpu2": E + ["-ot", r"blk\.(0|1)\.=CPU"],
    "C4_cpu4": E + ["-ot", r"blk\.([0-3])\.=CPU"],
    "C6_cpu6": E + ["-ot", r"blk\.([0-5])\.=CPU"],
    "F1_salida_cpu": E + ["-ot", r"output\.weight=CPU"],
    "F2_ffn_cpu4": E + ["-ncffn", "4"],
}
# Vega 7 (Vulkan1) con la carpeta de LABORATORIO CUDA+Vulkan (`--lab`): los mismos bloques que B2/C4/C6, pero en la Vega
EV_ = ["--fit", "off", "-ngl", "all", "-fa", "on", "-ub", "128", "-b", "512", "-dev", "CUDA0,Vulkan1", "-ts", "1,0"]
CONFIGURACIONES_LAB = {
    "V0_vulkan_rtx": ["--fit", "off", "-ngl", "all", "-fa", "on", "-ub", "128", "-b", "512", "-dev", "Vulkan0"],
    "V2_vega2": EV_ + ["-ot", r"blk\.(0|1)\.=Vulkan1"],
    "V4_vega4": EV_ + ["-ot", r"blk\.([0-3])\.=Vulkan1"],
    "V6_vega6": EV_ + ["-ot", r"blk\.([0-5])\.=Vulkan1"],
    "VS_salida_vega": EV_ + ["-ot", r"output\.weight=Vulkan1"],
}
RAM_MIN_MIB = 2048                             # memoria disponible del sistema: por debajo, se termina el servidor propio


# --- mediciones del sistema (solo consulta) --------------------------------------------------------------------------
class _MemEx(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong)] + \
               [(n, ctypes.c_ulonglong) for n in ("total", "disponible", "pag_total", "pag_disp", "virt_total",
                                                   "virt_disp", "ext")]


def memoria_sistema() -> dict:
    m = _MemEx()
    m.dwLength = ctypes.sizeof(m)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return {"disponible_MiB": m.disponible // 2**20, "total_MiB": m.total // 2**20,
            "compromiso_disp_MiB": m.pag_disp // 2**20}


class _PMC(ctypes.Structure):
    _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong)] + \
               [(n, ctypes.c_size_t) for n in ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                                               "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
                                               "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage",
                                               "PrivateUsage")]


def memoria_proceso(proc) -> dict | None:
    """Memoria y tiempo de CPU del proceso PROPIO (`proc` es el Popen lanzado aquí)."""
    try:
        h = int(proc._handle)
        c = _PMC()
        c.cb = ctypes.sizeof(c)
        if not ctypes.windll.psapi.GetProcessMemoryInfo(h, ctypes.byref(c), c.cb):
            return None
        t = [ctypes.c_ulonglong() for _ in range(4)]
        ctypes.windll.kernel32.GetProcessTimes(h, *[ctypes.byref(x) for x in t])
        duros = majflt_windows.contadores_fallos(proc.pid)
        return {"ws_MiB": c.WorkingSetSize // 2**20, "ws_pico_MiB": c.PeakWorkingSetSize // 2**20,
                "privada_MiB": c.PrivateUsage // 2**20, "fallos_pagina": c.PageFaultCount,
                "fallos_duros": duros[0] if duros else None,
                "cpu_s": (t[2].value + t[3].value) / 1e7}
    except (OSError, AttributeError, ValueError):
        return None


def gpu() -> dict | None:
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,utilization.gpu", "--format=csv,noheader,nounits"],
                           capture_output=True, text=True, timeout=10)
        usada, uso = (int(x) for x in r.stdout.strip().splitlines()[0].split(","))
        return {"vram_MiB": usada, "uso_pct": uso}
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return None


def pc_libre(inactividad_min=INACTIVIDAD_MIN_S, act=X.actividad, medir=gpu) -> dict:
    """Criterio del LABORATORIO (pruebas cortas): nadie usando el PC y margen de VRAM. Distinto del de la evaluación F1:
    el uso de la GPU (Wallpaper Engine ≈ 30 %) y «aplicación ocupada» se registran pero no bloquean."""
    a, g = act(), medir()
    motivos = [m for m in a["motivos"] if m not in ("aplicacion_ocupada", "notificacion_no_medible")]
    if a["inactividad_s"] is not None and a["inactividad_s"] < inactividad_min:
        motivos.append(f"entrada_reciente_{round(a['inactividad_s'])}s")
    if g is None:
        motivos.append("gpu_no_medible")
    elif g["vram_MiB"] > OTRAS_MAX_MIB:
        motivos.append(f"vram_otras_{g['vram_MiB']}MiB")
    return {"ok": not motivos, "motivos": motivos, "actividad": a, "gpu": g}


# --- servidor propio ------------------------------------------------------------------------------------------------
def puerto_libre() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


BUFER = re.compile(r"(\w+) (model|KV|compute|output|RS) buffer size =\s+([\d.]+) MiB")
CAPAS_GPU = re.compile(r"offloaded (\d+)/(\d+) layers to GPU")


def bufers(log: str) -> dict:
    """Búferes que declara llama.cpp al cargar: {"CUDA0 model": MiB, …} y capas en GPU."""
    out = {}
    for disp, tipo, mib in BUFER.findall(log):
        out[f"{disp} {tipo}"] = round(out.get(f"{disp} {tipo}", 0) + float(mib), 2)
    c = CAPAS_GPU.findall(log)
    out["capas_gpu"] = f"{c[-1][0]}/{c[-1][1]}" if c else None
    out["cuda_total_MiB"] = round(sum(v for k, v in out.items() if re.match(r"CUDA\d+ ", k) and isinstance(v, float)),
                                  1)
    out["vulkan1_total_MiB"] = round(sum(v for k, v in out.items() if k.startswith("Vulkan1 ")
                                         and isinstance(v, float)), 1)
    return out


class Vigia:
    """Cada `intervalo` s: VRAM total > tope o entrada de teclado/ratón posterior al inicio ⇒ termina SOLO `proc`."""

    def __init__(self, proc, tope=TOPE_MIB, medir=gpu, act=X.actividad, intervalo=VIGIA_S, reloj=time.monotonic,
                 ram=lambda: memoria_sistema()["disponible_MiB"]):
        self.proc, self.tope, self.medir, self.act, self.intervalo, self.reloj = proc, tope, medir, act, intervalo, reloj
        self.ram, self.ram_min = ram, None
        self.t0, self.motivo, self.muestras, self._fin = reloj(), None, [], threading.Event()
        self.t_motivo = None

    def paso(self):
        g = self.medir()
        if g:
            self.muestras.append((round(self.reloj() - self.t0, 2), g["vram_MiB"], g["uso_pct"]))
        a = self.act()
        r = self.ram()
        self.ram_min = r if self.ram_min is None or (r is not None and r < self.ram_min) else self.ram_min
        motivo = None
        if g is None:
            motivo = "vram_no_medible"
        elif g["vram_MiB"] > self.tope:
            motivo = f"vram_excedida_{g['vram_MiB']}MiB"
        elif r is None or r < RAM_MIN_MIB:
            motivo = f"ram_disponible_baja_{r}MiB"
        elif a["inactividad_s"] is None or a["inactividad_s"] < self.reloj() - self.t0:
            motivo = "actividad_de_terceros"
        elif [m for m in a["motivos"] if m not in ("aplicacion_ocupada", "notificacion_no_medible")]:
            motivo = "actividad_de_terceros_" + "+".join(a["motivos"])
        if motivo and self.motivo is None:
            self.motivo, self.t_motivo = motivo, self.reloj()
            if self.proc.poll() is None:
                self.proc.terminate()                    # el servidor PROPIO; ningún otro proceso

    def iniciar(self):
        def bucle():
            while not self._fin.is_set() and self.proc.poll() is None:
                self.paso()
                self._fin.wait(self.intervalo)
        threading.Thread(target=bucle, daemon=True, name="lab-vram-vigia").start()
        return self

    def detener(self):
        self._fin.set()

    def pico(self, desde=0.0):
        v = [m[1] for m in self.muestras if m[0] >= desde]
        return max(v) if v else None


def lanzar(exe, modelo, extra, log: Path, puerto: int):
    orden = [exe, "-m", modelo, "--host", "127.0.0.1", "--port", str(puerto)] + BASE + list(extra) + \
        ["-lv", "4"]                                     # solo más registro: los búferes y las capas de la carga
    f = open(log, "wb")
    proc = subprocess.Popen(orden, stdout=f, stderr=subprocess.STDOUT, cwd=str(Path(exe).parent),
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return proc, orden, f


def esperar_listo(proc, puerto, limite=240) -> float | None:
    t0 = time.monotonic()
    while time.monotonic() - t0 < limite and proc.poll() is None:
        try:
            c = http.client.HTTPConnection("127.0.0.1", puerto, timeout=2)
            c.request("GET", "/health")
            if c.getresponse().status == 200:
                return round(time.monotonic() - t0, 2)
        except OSError:
            pass
        time.sleep(0.25)
    return None


def prompt_fijo() -> str:
    """≈ 1000 tokens de entrada (como un primer paso de E3) y una petición de código; siempre el mismo texto."""
    fuente = "\n".join(f"def paso_{i}(datos):\n    total = 0\n    for x in datos:\n        if x % {i + 2} == 0:\n"
                       f"            total += x * {i}\n    return total\n" for i in range(28))
    return ("<|im_start|>system\nEres un programador cuidadoso.<|im_end|>\n<|im_start|>user\nRevisa este módulo y "
            "escribe una versión mejorada y comentada de todas las funciones, una por una:\n\n" + fuente +
            "<|im_end|>\n<|im_start|>assistant\n")


def completar(puerto, prompt, n, cortar_tras_s=None, timeout=300) -> dict:
    """POST /completion en streaming. Mide el primer token; con `cortar_tras_s` cierra la conexión (STOP)."""
    cuerpo = json.dumps({"prompt": prompt, "n_predict": n, "temperature": 0, "seed": 1, "cache_prompt": False,
                         "stream": True, "ignore_eos": True}).encode()
    c = http.client.HTTPConnection("127.0.0.1", puerto, timeout=timeout)
    t0 = time.monotonic()
    c.request("POST", "/completion", body=cuerpo, headers={"Content-Type": "application/json"})
    r = c.getresponse()
    primero, texto, timings, cortada = None, [], None, False
    for linea in r:
        if not linea.startswith(b"data: "):
            continue
        d = json.loads(linea[6:])
        if d.get("content") and primero is None:
            primero = time.monotonic() - t0
        texto.append(d.get("content", ""))
        if d.get("stop"):
            timings = d.get("timings")
            break
        if cortar_tras_s is not None and primero is not None and time.monotonic() - t0 > cortar_tras_s:
            cortada = True
            break
    c.close()
    t = "".join(texto)
    return {"ttft_s": round(primero, 3) if primero else None, "total_s": round(time.monotonic() - t0, 3),
            "timings": timings, "texto_sha256": hashlib.sha256(t.encode()).hexdigest()[:16], "caracteres": len(t),
            "cortada": cortada}


def cerrar(proc, f, vram_base, vig=None) -> dict:
    t0 = time.monotonic()
    if proc.poll() is None:
        proc.terminate()                                 # V2-F.1 hace lo mismo en Windows (TerminateProcess)
    try:
        proc.wait(15)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(10)
    t_salida = time.monotonic() - t0
    if vig:
        vig.detener()
    f.close()
    v = None
    while time.monotonic() - t0 < 20:
        v = gpu()
        if v and vram_base is not None and v["vram_MiB"] <= vram_base + 64:
            break
        time.sleep(0.25)
    return {"salida_s": round(t_salida, 2), "vram_liberada_s": round(time.monotonic() - t0, 2),
            "vram_despues_MiB": v and v["vram_MiB"], "codigo_salida": proc.returncode}


def verificar_lab(carpeta: Path, manifiesto: Path) -> list:
    """Problemas de la carpeta de LABORATORIO CUDA+Vulkan frente a su manifiesto SHA-256 ([] = intacta)."""
    m = json.loads(manifiesto.read_text(encoding="utf-8"))["sha256"]
    presentes = {p.name for p in carpeta.iterdir()}
    problemas = [f"sobra: {n}" for n in sorted(presentes - set(m))] + [f"falta: {n}" for n in sorted(set(m) - presentes)]
    for n, h in m.items():
        if n in presentes and hashlib.sha256((carpeta / n).read_bytes()).hexdigest() != h:
            problemas.append(f"distinto: {n}")
    return problemas


def medir_config(nombre, ver, carpeta: Path, reps: int, libre=pc_libre, dormir=time.sleep) -> dict:
    extra = (CONFIGURACIONES | CONFIGURACIONES_LAB)[nombre]
    res = {"config": nombre, "extra": extra, "inicio": time.strftime("%Y-%m-%dT%H:%M:%S")}
    t_esp = time.monotonic()
    while True:
        cond = libre()
        if cond["ok"] or time.monotonic() - t_esp > ESPERA_MAX_S:
            break
        dormir(30)
    res["condiciones"] = cond
    if not cond["ok"]:
        res["omitida"] = f"PC en uso o sin margen: {cond['motivos']}"
        return res
    if servidor_pc.procesos_llama() != []:
        res["omitida"] = "hay un proceso llama ajeno (o no se pueden listar): no se lanza nada"
        return res
    base = gpu()
    if base is None:
        res["omitida"] = "VRAM no medible: no se lanza nada"
        return res
    res.update(vram_otras_MiB=base["vram_MiB"], uso_gpu_otras_pct=base["uso_pct"], ram_antes=memoria_sistema())
    puerto = puerto_libre()
    log = carpeta / f"{nombre}.log"
    proc, orden, f = lanzar(ver["ejecutable"], ver["modelo"], extra, log, puerto)
    res["orden"] = [Path(orden[0]).name, "-m", Path(orden[2]).name] + orden[3:]
    vig = Vigia(proc).iniciar()
    try:
        res["carga_s"] = esperar_listo(proc, puerto)
        if res["carga_s"] is None:
            res["fallo"] = vig.motivo or f"no arrancó (código {proc.poll()})"
            return res
        time.sleep(1.0)
        g = gpu()
        res["vram_cargado_MiB"] = g and g["vram_MiB"]
        res["vram_qwen_cargado_MiB"] = g and g["vram_MiB"] - base["vram_MiB"]
        res["bufers"] = bufers(log.read_text(encoding="utf-8", errors="replace"))
        prompt = prompt_fijo()
        completar(puerto, prompt, 16)                                            # calentamiento (no se mide)
        res["corridas"] = []
        for i in range(reps):
            if vig.motivo:
                break
            t_ini = vig.reloj() - vig.t0
            m0 = memoria_proceso(proc)
            r = completar(puerto, prompt, 256)
            m1 = memoria_proceso(proc)
            usos = [u for (t, _, u) in vig.muestras if t >= t_ini]
            tm = r["timings"] or {}
            r.update(prompt_n=tm.get("prompt_n"), prompt_tps=round(tm.get("prompt_per_second") or 0, 1),
                     gen_n=tm.get("predicted_n"), gen_tps=round(tm.get("predicted_per_second") or 0, 2),
                     vram_pico_MiB=vig.pico(t_ini), uso_gpu_medio_pct=round(sum(usos) / len(usos)) if usos else None,
                     cpu_pct=round(100 * (m1["cpu_s"] - m0["cpu_s"]) / r["total_s"] / os.cpu_count(), 1)
                     if m0 and m1 else None,
                     fallos_duros=(m1["fallos_duros"] - m0["fallos_duros"]) if m0 and m1 and m0["fallos_duros"]
                     is not None and m1["fallos_duros"] is not None else None,
                     proceso=m1, ram_sistema=memoria_sistema())
            r.pop("timings", None)
            res["corridas"].append(r)
        if not vig.motivo:                                                       # STOP: cortar a mitad y cerrar
            r = completar(puerto, prompt, 800, cortar_tras_s=3.0)
            res["stop"] = {"cortada": r["cortada"], "segundos_peticion": r["total_s"]}
    except (OSError, ValueError, http.client.HTTPException) as e:
        res["fallo"] = f"{type(e).__name__}: {e}"
    finally:
        res["cierre"] = cerrar(proc, f, base["vram_MiB"], vig)
        res["vigia"] = {"motivo": vig.motivo, "pico_MiB": vig.pico(), "muestras": len(vig.muestras),
                        "ram_min": vig.ram_min}
        res["llama_despues"] = servidor_pc.procesos_llama()
    return res


def resumir(res: dict) -> dict:
    c = res.get("corridas") or []
    if not c:
        return {"config": res["config"], "sin_datos": res.get("omitida") or res.get("fallo") or res["vigia"]}
    g = [x["gen_tps"] for x in c]
    p = [x["prompt_tps"] for x in c]
    media = sum(g) / len(g)
    return {"config": res["config"], "capas_gpu": res["bufers"]["capas_gpu"],
            "cuda_bufers_MiB": res["bufers"]["cuda_total_MiB"], "vram_qwen_cargado_MiB": res["vram_qwen_cargado_MiB"],
            "vram_qwen_pico_MiB": max(x["vram_pico_MiB"] or 0 for x in c) - res["vram_otras_MiB"],
            "gen_tps_media": round(media, 2), "gen_tps_min_max": [min(g), max(g)],
            "gen_vs_41_pct": round(100 * (media / REF_TOKS - 1), 1), "prompt_tps_media": round(sum(p) / len(p), 1),
            "ttft_s_media": round(sum(x["ttft_s"] or 0 for x in c) / len(c), 3),
            "total_s_media": round(sum(x["total_s"] for x in c) / len(c), 2),
            "ws_MiB": c[-1]["proceso"] and c[-1]["proceso"]["ws_MiB"],
            "privada_MiB": c[-1]["proceso"] and c[-1]["proceso"]["privada_MiB"],
            "ram_disponible_min_MiB": min(x["ram_sistema"]["disponible_MiB"] for x in c),
            "fallos_duros": [x["fallos_duros"] for x in c], "cpu_pct": [x["cpu_pct"] for x in c],
            "uso_gpu_pct": [x["uso_gpu_medio_pct"] for x in c], "textos": sorted({x["texto_sha256"] for x in c}),
            "vega_bufers_MiB": res["bufers"]["vulkan1_total_MiB"], "ram_disponible_min_vigia_MiB": res["vigia"]["ram_min"],
            "stop": res.get("stop"), "cierre": res["cierre"], "vigia": res["vigia"]["motivo"]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("externos", nargs="?", type=Path)
    ap.add_argument("salida", nargs="?", type=Path)
    ap.add_argument("configs", nargs="*")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--lista", action="store_true")
    ap.add_argument("--lab", type=Path, help="carpeta CUDA+Vulkan de laboratorio (para las configuraciones V*)")
    ap.add_argument("--manifiesto", type=Path, help="SHA-256 de cada archivo de la carpeta --lab")
    a = ap.parse_args(argv)
    if a.lista:
        print(json.dumps(CONFIGURACIONES | CONFIGURACIONES_LAB, indent=1))
        return 0
    validas = CONFIGURACIONES_LAB if a.lab else CONFIGURACIONES
    desconocidas = [c for c in a.configs if c not in validas]
    if desconocidas or not a.configs:
        print(f"configuraciones desconocidas, ninguna o sin la carpeta adecuada: {desconocidas}")
        return 2
    if "lab_vram" not in str(a.salida).lower():
        print("la salida debe estar en una carpeta con «lab_vram» en el nombre (evidencias separadas)")
        return 2
    ver = servidor_pc.verificar_externos(a.externos)          # el modelo (y la carpeta CUDA estable) por SHA-256
    if not ver["ok"]:
        print(f"externos NO verificados: {ver['problemas'][:5]}")
        return 2
    if a.lab:
        problemas = verificar_lab(a.lab, a.manifiesto) if a.manifiesto else ["falta --manifiesto"]
        if problemas:
            print(f"carpeta de laboratorio NO verificada: {problemas[:5]}")
            return 2
        ver = ver | {"ejecutable": str(a.lab / "llama-server.exe"), "version": ver["version"] + " + ggml-vulkan.dll"}
    a.salida.mkdir(parents=True)
    todo = {"inicio": time.strftime("%Y-%m-%dT%H:%M:%S"), "version": ver["version"], "tope_MiB": TOPE_MIB,
            "resultados": [], "resumen": []}
    for nombre in a.configs:
        r = medir_config(nombre, ver, a.salida, a.reps)
        todo["resultados"].append(r)
        todo["resumen"].append(resumir(r))
        print(json.dumps(todo["resumen"][-1], ensure_ascii=False), flush=True)
        (a.salida / "banco.json").write_text(json.dumps(todo, ensure_ascii=False, indent=1, default=str),
                                             encoding="utf-8")
        if r["vigia"]["motivo"] if "vigia" in r else False:
            if str(r["vigia"]["motivo"]).startswith("vram_excedida"):
                print("ABORTADO: VRAM por encima del tope")
                break
    todo["fin"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    (a.salida / "banco.json").write_text(json.dumps(todo, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
