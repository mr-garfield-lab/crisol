"""Ejecutor de scripts de Blender escritos por cerebros (laboratorio): filtro, Blender sin ventana, límites y evidencia.

    python -B -X utf8 lab_blender/ejecutor.py SCRIPT.py SALIDA [--base ARCHIVO.blend] [--fotogramas 1 40] [--video]
                                                             [--motor BLENDER_EEVEE] [--tiempo 120]

Qué hace, en orden:
  1. Pasa el filtro (lab_blender/filtro.py). Si no pasa, NO se lanza Blender: estado RECHAZADO.
  2. Crea la carpeta SALIDA (tiene que ser nueva) y, si hay --base, trabaja sobre una COPIA del .blend (comprueba que el
     original no cambia).
  3. Lanza Blender sin ventana, de fábrica, sin scripts automáticos y sin red, con dentro_blender.py.
  4. Vigila tiempo y memoria; si se pasa, termina ESE proceso (el que lanzó él) y lo anota. Un archivo SALIDA/STOP lo para.
  5. Escribe SALIDA/resultado.json con el estado y los hechos de la escena.

Estados: OK, RECHAZADO, ERROR_SCRIPT, LIMITE, TIEMPO, MEMORIA, PARADO, FALLO_BLENDER.
No decide si el resultado es bueno: eso lo hará un verificador sin IA sobre los hechos. El filtro no es un aislamiento
perfecto (ver LEEME.md): por eso están los límites y solo se trabaja con copias.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import filtro  # noqa: E402

TIEMPO_S = 120
MEMORIA_MB = 6000
LIMITES = {"objetos": 3000, "vertices": 3_000_000}
SONDEO_S = 0.5
MAX_BASE_MB = 2000


def blender_exe() -> Path | None:
    """El Blender instalado (no se instala nada): variable BLENDER_EXE o la versión más alta de Blender Foundation."""
    if os.environ.get("BLENDER_EXE"):
        p = Path(os.environ["BLENDER_EXE"])
        return p if p.is_file() else None
    if os.name != "nt":
        en_ruta = shutil.which("blender")
        return Path(en_ruta) if en_ruta else None
    raiz = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Blender Foundation"
    candidatos = sorted(raiz.glob("Blender */blender.exe"), key=lambda p: [int(x) if x.isdigit() else 0
                                                                           for x in p.parent.name.replace("Blender ", "").split(".")])
    return candidatos[-1] if candidatos else None


def huella(p: Path) -> dict:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for trozo in iter(lambda: f.read(1 << 20), b""):
            h.update(trozo)
    st = p.stat()
    return {"bytes": st.st_size, "mtime_ns": st.st_mtime_ns, "sha256": h.hexdigest()}


def memoria_mb(proc) -> float | None:
    """Memoria del proceso en MB (Windows: memoria privada; Linux: VmRSS de /proc). None si no se puede medir."""
    if os.name != "nt":
        try:
            for linea in Path(f"/proc/{proc.pid}/status").read_text(encoding="ascii", errors="replace").splitlines():
                if linea.startswith("VmRSS:"):
                    return int(linea.split()[1]) / 1024
        except (OSError, ValueError, IndexError):
            pass
        return None
    import ctypes
    from ctypes import wintypes

    class Contadores(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD), ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t), ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t), ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t)]
    c = Contadores()
    c.cb = ctypes.sizeof(c)
    try:
        f = ctypes.WinDLL("psapi").GetProcessMemoryInfo
        f.argtypes = [wintypes.HANDLE, ctypes.POINTER(Contadores), wintypes.DWORD]
        if not f(int(proc._handle), ctypes.byref(c), c.cb):
            return None
    except (OSError, AttributeError, ValueError):
        return None
    return max(c.PagefileUsage, c.WorkingSetSize) / (1 << 20)


def _escribir(ruta: Path, datos: dict):
    tmp = ruta.with_name(ruta.name + ".tmp")
    tmp.write_text(json.dumps(datos, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    os.replace(tmp, ruta)


def _cola(p: Path, n=1500) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")[-n:]
    except OSError:
        return ""


def ejecutar(texto: str, salida, base=None, escena: str = "vacia", render: dict | None = None, tiempo_s: float = TIEMPO_S,
             memoria_max_mb: float = MEMORIA_MB, limites: dict | None = None, muestras: int = 5, exe=None,
             reloj=time.monotonic, dormir=time.sleep) -> dict:
    """Filtra y ejecuta `texto` en Blender. Devuelve el resultado (y lo escribe en salida/resultado.json)."""
    salida = Path(salida).resolve()
    res = {"modo": "REAL", "estado": None, "inicio": time.strftime("%Y-%m-%dT%H:%M:%S"), "salida": str(salida),
           "sha256_script": hashlib.sha256(texto.encode("utf-8", errors="replace")).hexdigest(),
           "limites": {"tiempo_s": tiempo_s, "memoria_mb": memoria_max_mb, **(limites or LIMITES)}}
    if salida.exists():
        raise FileExistsError(f"{salida} ya existe: cada ejecución va en una carpeta nueva")
    salida.mkdir(parents=True)
    final = lambda: (_escribir(salida / "resultado.json", res), res)[1]
    (salida / "script_cerebro.py").write_text(texto, encoding="utf-8", newline="\n")
    motivos = filtro.revisar(texto)
    res["filtro"] = {"pasa": not motivos, "motivos": motivos}
    if motivos:
        res |= {"estado": "RECHAZADO", "blender_lanzado": False}
        return final()
    exe = Path(exe) if exe else blender_exe()
    if not exe or not exe.is_file():
        res |= {"estado": "FALLO_BLENDER", "blender_lanzado": False, "error": "no encuentro blender.exe (no se instala nada)"}
        return final()
    cfg = {"script": str(salida / "script_cerebro.py"), "sha256": res["sha256_script"], "salida": str(salida), "lab": str(AQUI),
           "escena": escena, "render": render, "limites": limites or LIMITES, "muestras": muestras, "base": None}
    antes = None
    if base:
        base = Path(base).resolve()
        if not base.is_file() or base.suffix.lower() != ".blend":
            res |= {"estado": "FALLO_BLENDER", "blender_lanzado": False, "error": f"la base no es un .blend: {base}"}
            return final()
        if base.stat().st_size > MAX_BASE_MB * (1 << 20):
            res |= {"estado": "FALLO_BLENDER", "blender_lanzado": False, "error": f"la base pesa más de {MAX_BASE_MB} MB"}
            return final()
        antes = huella(base)
        shutil.copyfile(base, salida / "entrada.blend")       # se trabaja SIEMPRE sobre la copia
        cfg["base"] = str(salida / "entrada.blend")
        res["base"] = {"original": str(base), "huella": antes}
    _escribir(salida / "config.json", cfg)
    orden = [str(exe), "-b", "--factory-startup", "-Y", "--offline-mode", "-noaudio", "--python-exit-code", "3",
             "-P", str(AQUI / "dentro_blender.py"), "--", str(salida / "config.json")]
    entorno = {k: v for k, v in os.environ.items() if not k.upper().startswith(("PYTHON", "BLENDER_"))}
    res["orden"] = orden
    t0 = reloj()
    motivo, pico = None, 0.0
    with open(salida / "blender.salida.txt", "wb") as so, open(salida / "blender.errores.txt", "wb") as se:
        proc = subprocess.Popen(orden, cwd=str(salida), env=entorno, stdin=subprocess.DEVNULL, stdout=so, stderr=se)
        res["blender_lanzado"] = True
        try:
            while proc.poll() is None:
                m = memoria_mb(proc)
                pico = max(pico, m or 0.0)
                if reloj() - t0 > tiempo_s:
                    motivo = "TIEMPO"
                elif m is not None and m > memoria_max_mb:
                    motivo = "MEMORIA"
                elif (salida / "STOP").exists():
                    motivo = "PARADO"
                if motivo:
                    proc.kill()                              # solo el proceso que lanzó este ejecutor
                    break
                dormir(SONDEO_S)
        finally:
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=30)
    res |= {"segundos": round(reloj() - t0, 2), "codigo_de_salida": proc.returncode, "memoria_pico_mb": round(pico)}
    if antes is not None:
        res["base"]["intacta"] = huella(Path(res["base"]["original"])) == antes
    informe = None
    try:
        informe = json.loads((salida / "informe.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    res["informe"] = informe
    if motivo:
        res["estado"] = motivo
        res["fase_al_cortar"] = (informe or {}).get("fase")
    elif not informe or informe.get("fase") != "fin":
        if informe and informe.get("fase") == "rechazado_dentro":
            res |= {"estado": "RECHAZADO", "filtro": {"pasa": False, "motivos": informe.get("motivos", [])}}
        else:
            res |= {"estado": "FALLO_BLENDER", "fase": (informe or {}).get("fase"),
                    "error": _cola(salida / "blender.errores.txt") or _cola(salida / "blender.salida.txt")}
    elif not informe["script"]["ok"]:
        res["estado"] = "ERROR_SCRIPT"
    elif informe["escena"]["limites_superados"]:
        res["estado"] = "LIMITE"
    else:
        res["estado"] = "OK"
    if antes is not None and not res["base"]["intacta"]:
        res["estado"] = "FALLO_BLENDER"
        res["error"] = "el .blend ORIGINAL cambió durante la ejecución: se para y se conserva la evidencia"
    return final()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("script")
    ap.add_argument("salida")
    ap.add_argument("--base")
    ap.add_argument("--escena", choices=("vacia", "fabrica"), default="vacia")
    ap.add_argument("--fotogramas", nargs="*", type=int, default=[])
    ap.add_argument("--video", action="store_true")
    ap.add_argument("--motor", choices=("BLENDER_WORKBENCH", "BLENDER_EEVEE"), default="BLENDER_WORKBENCH")
    ap.add_argument("--resolucion", nargs=2, type=int, default=[640, 360])
    ap.add_argument("--tiempo", type=float, default=TIEMPO_S)
    a = ap.parse_args(argv)
    render = None
    if a.fotogramas or a.video:
        render = {"motor": a.motor, "fotogramas": a.fotogramas, "video": a.video, "resolucion": a.resolucion}
    r = ejecutar(Path(a.script).read_text(encoding="utf-8"), a.salida, base=a.base, escena=a.escena, render=render,
                 tiempo_s=a.tiempo)
    print(json.dumps({k: v for k, v in r.items() if k not in ("informe", "orden")}, ensure_ascii=False, indent=1))
    esc = (r.get("informe") or {}).get("escena") or {}
    if esc:
        print(f"objetos: {esc.get('n_objetos')}  por tipo: {esc.get('por_tipo')}  se mueven: {esc.get('objetos_que_se_mueven')}")
    return 0 if r["estado"] == "OK" else 1


if __name__ == "__main__":
    sys.exit(main())
