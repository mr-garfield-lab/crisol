"""Equipo IA V3.1 F1 — llama-server REAL en el PC con el ciclo de vida de V2-F.1 (que no se modifica).

V2-F.1 (`sistema/src/eq2/servidor.py` y `backend_llama.py`) lanza, vigila y detiene el servidor: comprobaciones
previas (modelo, memoria, proceso llama ya activo, puerto, flags), solo 127.0.0.1, monitor de memoria, STOP, y al
final detiene ÚNICAMENTE el proceso que lanzó y comprueba que el puerto quedó libre y que el modelo no cambió. Este
módulo solo aporta, por los puntos de inyección que V2-F.1 ya ofrece, lo que en el PC es distinto del Samsung S23:

- **Qué ejecutable y qué modelo.** Los de una carpeta de «externos» cuyo contenido coincide, archivo por archivo, con
  el registro `eq3/externos_f1.json` (SHA-256). Si un archivo falta, sobra o no coincide, NO se lanza nada.
- **Detector de un llama ya activo.** V2-F.1 lo busca en `/proc`, que en Windows no existe: sin un detector propio,
  la comprobación «ya hay un proceso llama; no se inicia ni se mata nada» quedaría ciega. Si los procesos no se
  pueden listar, falla cerrado (no se lanza nada).
- **Hilos del PC** y la ruta del modelo (`config.HILOS`, `config.MODELO_PARTES`, en este proceso; ningún archivo de
  `sistema/` cambia).

Este módulo no lanza, no cierra y no mata procesos: eso lo hace V2-F.1. Nunca pasa opciones nuevas al servidor: la
orden es la de `ServidorLlama.construir_argv` (-m, --host 127.0.0.1, --port, -c, -t, -np 1, --no-ui).
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
REGISTRO = Path(__file__).with_name("externos_f1.json")
HILOS_PC = 6
PREFIJO_LLAMA = "llama"
SIN_LISTA = "no_se_pueden_listar_procesos"


class ExternosNoVerificados(RuntimeError):
    """Los componentes externos no coinciden con el registro: no se construye ningún backend."""


def sha256_archivo(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def cargar_registro(ruta: Path | None = None) -> dict:
    return json.loads((ruta or REGISTRO).read_text(encoding="utf-8"))


def verificar_externos(carpeta, registro: dict | None = None) -> dict:
    """Comprueba TODOS los archivos de la carpeta de llama.cpp y el modelo contra el registro. Devuelve
    {ok, problemas, archivos, segundos, ejecutable, modelo, huellas}; `huellas` (tamaño y fecha de cada archivo
    verificado) permite a `sin_cambios` detectar después cualquier cambio sin repetir los SHA-256."""
    reg = registro or cargar_registro()
    carpeta = Path(carpeta)
    t0 = time.monotonic()
    problemas, huellas = [], {}
    base = carpeta / reg["llama"]["carpeta"]
    esperados = reg["llama"]["archivos"]
    if not base.is_dir():
        problemas.append(f"falta la carpeta {reg['llama']['carpeta']}")
        presentes = set()
    else:
        presentes = {p.relative_to(base).as_posix() for p in base.rglob("*") if p.is_file()}
        for n in sorted(presentes - set(esperados)):
            problemas.append(f"archivo no registrado: {n}")
    comprobar = [(base / n, d, n) for n, d in esperados.items()]
    modelo = carpeta.joinpath(*reg["modelo"]["archivo"].split("/"))
    comprobar.append((modelo, reg["modelo"], reg["modelo"]["archivo"]))
    for p, d, nombre in comprobar:
        if not p.is_file() or p.is_symlink():
            problemas.append(f"falta: {nombre}")
            continue
        st = p.stat()
        if st.st_size != d["bytes"]:
            problemas.append(f"tamaño distinto: {nombre}")
            continue
        if sha256_archivo(p) != d["sha256"]:
            problemas.append(f"SHA-256 distinto: {nombre}")
            continue
        huellas[str(p)] = [st.st_size, st.st_mtime_ns]
    return {"ok": not problemas, "problemas": problemas, "archivos": len(comprobar),
            "segundos": round(time.monotonic() - t0, 1), "ejecutable": str(base / reg["llama"]["ejecutable"]),
            "modelo": str(modelo), "version": reg["llama"]["version"], "huellas": huellas}


def sin_cambios(verificacion: dict) -> list:
    """Archivos verificados cuyo tamaño o fecha han cambiado (o que ya no existen) desde `verificar_externos`."""
    cambiados = []
    for ruta, (tam, fecha) in verificacion["huellas"].items():
        try:
            st = os.stat(ruta)
        except OSError:
            cambiados.append(ruta)
            continue
        if [st.st_size, st.st_mtime_ns] != [tam, fecha]:
            cambiados.append(ruta)
    return cambiados


# --- detector de un llama ya activo ----------------------------------------------------------------------------------
def listar_procesos_windows():
    """[(pid, nombre de imagen)] de todos los procesos (instantánea Toolhelp, solo lectura), o None si falla."""
    import ctypes
    from ctypes import wintypes

    class Entrada(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                    ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                    ("szExeFile", ctypes.c_wchar * 260)]
    try:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    except (AttributeError, OSError):
        return None
    k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    k32.Process32FirstW.argtypes = k32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entrada)]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    h = k32.CreateToolhelp32Snapshot(0x2, 0)                     # TH32CS_SNAPPROCESS
    if h in (None, wintypes.HANDLE(-1).value):
        return None
    try:
        e = Entrada()
        e.dwSize = ctypes.sizeof(e)
        if not k32.Process32FirstW(h, ctypes.byref(e)):
            return None
        procesos = []
        while True:
            procesos.append((int(e.th32ProcessID), e.szExeFile))
            if not k32.Process32NextW(h, ctypes.byref(e)):
                break
        return procesos
    finally:
        k32.CloseHandle(h)


def procesos_llama(listar=listar_procesos_windows):
    """[(pid, nombre)] de los procesos cuyo nombre empieza por «llama» (como `servidor.llama_activo` de V2-F.1), o
    None si no se pueden listar."""
    procesos = listar()
    if not procesos:                                             # None o lista vacía: una lista vacía no es creíble
        return None
    return [(pid, n) for pid, n in procesos if n.lower().startswith(PREFIJO_LLAMA)]


def detector_llama(listar=listar_procesos_windows):
    """Para `ServidorLlama(detector_llama=…)`: pid (texto) de un llama activo, o None. FALLA CERRADO: si los procesos
    no se pueden listar devuelve un valor no vacío, y V2-F.1 no lanza nada. Fuera de Windows, el detector de V2-F.1."""
    if os.name != "nt":
        from eq2 import servidor
        return servidor.llama_activo()
    activos = procesos_llama(listar)
    if activos is None:
        return SIN_LISTA
    return str(activos[0][0]) if activos else None


# --- perfil del PC y backend --------------------------------------------------------------------------------------
def aplicar_perfil_pc(modelo, hilos: int = HILOS_PC) -> dict:
    """Fija EN ESTE PROCESO la ruta del modelo y los hilos que usará V2-F.1. Devuelve lo que había, para el informe."""
    from eq2 import config
    antes = {"MODELO_PARTES": list(config.MODELO_PARTES), "HILOS": config.HILOS}
    config.MODELO_PARTES = (str(Path(modelo)),)       # una ruta absoluta: `Path.home().joinpath(abs)` es esa ruta
    config.HILOS = int(hilos)
    return {"antes": antes, "ahora": {"MODELO_PARTES": [str(Path(modelo))], "HILOS": config.HILOS}}


def crear_backend(verificacion: dict, puerto=None, comando=None, detector=detector_llama, **kw):
    """`BackendLlama` de V2-F.1 sobre los externos YA verificados. Se niega (ExternosNoVerificados) si la
    verificación no es correcta o si algún archivo cambió después. `comando` solo lo usan las pruebas (servidor falso)."""
    if verificacion.get("ok") is not True or not verificacion.get("huellas"):
        raise ExternosNoVerificados("; ".join(verificacion.get("problemas") or ["sin verificación"])[:500])
    cambiados = sin_cambios(verificacion)
    if cambiados:
        raise ExternosNoVerificados(f"{len(cambiados)} archivos cambiaron tras la verificación: "
                                    + "; ".join(Path(c).name for c in cambiados[:5]))
    from eq2 import backend_llama, config, servidor
    aplicar_perfil_pc(verificacion["modelo"], kw.pop("hilos", HILOS_PC))
    srv_kw = kw.pop("srv_kw", {})
    srv = servidor.ServidorLlama(puerto or config.PUERTO, comando=comando or [verificacion["ejecutable"]],
                                 detector_llama=detector, **srv_kw)
    kw.setdefault("usar_wake_lock", False)            # termux-wake-lock no existe en el PC
    return backend_llama.BackendLlama(srv, **kw)


# --- VRAM (solo lectura) ----------------------------------------------------------------------------------------
def vram_mib(ejecutar=subprocess.run):
    """{usada, total, procesos: {pid: MiB}} según nvidia-smi, o None si no está o falla. Solo consulta."""
    try:
        r = ejecutar(["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
                     capture_output=True, text=True, timeout=15)
        if r.returncode != 0:
            return None
        usada, total = (int(x) for x in r.stdout.strip().splitlines()[0].split(","))
        out = {"usada": usada, "total": total, "procesos": {}}
        r = ejecutar(["nvidia-smi", "--query-compute-apps=pid,used_memory", "--format=csv,noheader,nounits"],
                     capture_output=True, text=True, timeout=15)
        if r.returncode == 0:
            for linea in r.stdout.strip().splitlines():
                pid, _, mem = linea.partition(",")
                if pid.strip().isdigit() and mem.strip().isdigit():
                    out["procesos"][int(pid)] = int(mem)
        return out
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return None


def preparar_proceso() -> None:
    """Deja este proceso listo para usar V2-F.1 en Windows: `sistema/src` en la ruta y los ajustes del lanzador
    (memoria real, «servidor_muerto», escritura con «\\n»); en Linux/Termux el lanzador no cambia nada de eso."""
    src = str(RAIZ / "sistema" / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    if subprocess.Popen.__name__ == "PopenAdaptado":      # este proceso ya se lanzó con eq3/lanzador_eq2.py: instalarlo
        return                                            # otra vez (como otro módulo) duplicaría sus ajustes
    from eq3 import lanzador_eq2
    lanzador_eq2.instalar()
