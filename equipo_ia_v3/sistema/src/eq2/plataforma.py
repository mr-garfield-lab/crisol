"""V2-D: detección de plataforma y capacidades, para preparar la migración a Windows 11.

Solo LEE el entorno (variables, existencia de rutas, herramientas en PATH). No escribe nada.
Componentes que hoy dependen de Linux/Android y deberán tener equivalente en Windows:
  * monitor.py / vigilancia.py: /proc/meminfo, /proc/<pid>/status  -> en Windows: psutil o WMI.
  * servidor.llama_activo: recorre /proc                             -> en Windows: lista de procesos.
  * servidor.wake_lock: termux-wake-lock                             -> en Windows: no aplica.
  * señales SIGTERM/SIGKILL                                          -> en Windows: TerminateProcess.
  * rutas: O_NOFOLLOW y TMPDIR                                       -> en Windows: %TEMP% y reparse points.
"""
from __future__ import annotations

import os
import shutil
import signal
import sys


def nombre(env=None) -> str:
    env = os.environ if env is None else env
    if os.name == "nt" or sys.platform.startswith("win"):
        return "windows"
    if "com.termux" in env.get("PREFIX", "") or os.path.isdir("/data/data/com.termux"):
        return "android_termux"
    if sys.platform.startswith("linux"):
        return "linux"
    return "otro"


def capacidades() -> dict:
    return {
        "plataforma": nombre(),
        "proc": os.path.isdir("/proc/self"),
        "o_nofollow": hasattr(os, "O_NOFOLLOW"),
        "sigkill": hasattr(signal, "SIGKILL"),
        "termux_wake_lock": shutil.which("termux-wake-lock") is not None,
        "tmpdir_definido": bool(os.environ.get("TMPDIR")),
        # Aislamiento REAL para un ejecutor futuro: aquí no se detecta ninguno. Un directorio no
        # es un sandbox; proot tampoco es una barrera de seguridad.
        "aislamiento_real": None,
    }


def problemas_para_esta_version() -> list:
    """Qué impediría ejecutar V2-D tal cual en esta plataforma (informativo)."""
    c = capacidades()
    p = []
    if not c["proc"]:
        p.append("sin /proc: el monitor de memoria y la detección de llama-server no funcionan")
    if not c["o_nofollow"]:
        p.append("sin O_NOFOLLOW: rutas.py no puede impedir seguir enlaces")
    if not c["tmpdir_definido"]:
        p.append("TMPDIR no está definido")
    return p


# --- V2-E: proveedores de plataforma ---------------------------------------------------------
class NoSoportado(RuntimeError):
    pass


class ProveedorPlataforma:
    nombre = "base"

    def mem_disponible_kb(self):
        raise NoSoportado("mem_disponible_kb")

    def bateria(self):
        raise NoSoportado("bateria")

    def proceso_llama_activo(self):
        raise NoSoportado("proceso_llama_activo")


class ProveedorLinux(ProveedorPlataforma):
    """Linux y Android/Termux: /proc y /sys (lectura)."""
    nombre = "linux"

    def mem_disponible_kb(self):
        from .vigilancia import leer_mem_available
        return leer_mem_available()

    def bateria(self):
        from .vigilancia import leer_bateria
        return leer_bateria()

    def proceso_llama_activo(self):
        from .servidor import llama_activo
        return llama_activo()


class ProveedorWindows(ProveedorPlataforma):
    """Pendiente (psutil o WMI); ver MIGRACION_WINDOWS.md. Todas las operaciones lanzan NoSoportado."""
    nombre = "windows"


def proveedor(env=None) -> ProveedorPlataforma:
    return ProveedorWindows() if nombre(env) == "windows" else ProveedorLinux()


# ============================ V2-E.5: adaptadores de plataforma (FASE 1) ============================
"""Fase 1 (V2-E.5): separar lo que depende del sistema operativo SIN cambiar el núcleo.

Responsabilidades del adaptador (una sola interfaz; el núcleo no se duplica):
  rutas      raiz_temporal(env)      dónde vive el laboratorio ($TMPDIR en Linux/Termux)
  procesos   pid_vivo(pid), proceso_llama_activo()
  recursos   mem_disponible_kb(), bateria()            (delegan en el ProveedorPlataforma)
  servidor   comando_servidor(), wake_lock_disponible()
  entorno    entorno()                                  (solo LECTURA de variables relevantes)
`estado` dice lo que está COMPROBADO, no lo que se espera:
  android_termux  pruebas ejecutadas por el usuario en el dispositivo (última constancia: V2-E.1)
  linux           pruebas ejecutadas en la sandbox Linux de desarrollo (no en un escritorio Linux)
  windows         SOLO DISEÑO: toda operación del sistema lanza NoSoportado
En esta fase el único punto del núcleo que pasa por el adaptador es la comprobación de si el pid de
un candado sigue vivo (antes: /proc a mano). En Linux y Termux el resultado es idéntico.
"""
import re as _re
from pathlib import Path as _Path

ESTADOS_VERIFICACION = {
    "android_termux": "probado por el usuario en el dispositivo (última constancia: V2-E.1); V2-E.2+ pendiente",
    "linux": "probado en la sandbox Linux de desarrollo; no probado en un escritorio Linux real",
    "windows": "solo diseño: no se ha ejecutado nada en Windows 10/11",
}


class AdaptadorPlataforma:
    nombre = "base"
    estado = "sin_definir"

    def __init__(self, proc_dir="/proc"):
        self.proc_dir = proc_dir
        self.recursos = ProveedorPlataforma()

    def raiz_temporal(self, env=None):
        raise NoSoportado("raiz_temporal")

    def pid_vivo(self, pid) -> bool:
        raise NoSoportado("pid_vivo")

    def proceso_llama_activo(self):
        return self.recursos.proceso_llama_activo()

    def mem_disponible_kb(self):
        return self.recursos.mem_disponible_kb()

    def bateria(self):
        return self.recursos.bateria()

    def comando_servidor(self) -> list:
        return ["llama-server"]

    def wake_lock_disponible(self) -> bool:
        return False

    def entorno(self, env=None) -> dict:
        env = os.environ if env is None else env
        return {k: env.get(k) for k in ("TMPDIR", "TEMP", "TMP", "PREFIX", "HOME", "USERPROFILE")
                if env.get(k) is not None}

    def informe(self) -> dict:
        def probar(f):
            try:
                return f()
            except NoSoportado:
                return "no_soportado"
        return {"adaptador": self.nombre, "estado": self.estado,
                "verificacion": ESTADOS_VERIFICACION.get(self.nombre, "sin datos"),
                "raiz_temporal": probar(self.raiz_temporal), "mem_disponible_kB": probar(self.mem_disponible_kb),
                "comando_servidor": self.comando_servidor(), "wake_lock_disponible": self.wake_lock_disponible()}


class AdaptadorLinux(AdaptadorPlataforma):
    nombre = "linux"
    estado = "probado_en_sandbox"

    def __init__(self, proc_dir="/proc"):
        super().__init__(proc_dir)
        self.recursos = ProveedorLinux()

    def raiz_temporal(self, env=None):
        env = os.environ if env is None else env
        t = env.get("TMPDIR")
        return t if t and os.path.isabs(t) else None          # igual que rutas.raiz_laboratorio

    def pid_vivo(self, pid) -> bool:
        p = str(pid)
        return p.isdigit() and os.path.exists(f"{self.proc_dir}/{p}")   # idéntico a la versión anterior

    def proceso_llama_activo(self):
        from .servidor import llama_activo
        return llama_activo(self.proc_dir)


class AdaptadorTermux(AdaptadorLinux):
    nombre = "android_termux"
    estado = "probado_por_el_usuario_hasta_V2-E.1"

    def wake_lock_disponible(self) -> bool:
        return shutil.which("termux-wake-lock") is not None


class AdaptadorWindows(AdaptadorPlataforma):
    """SOLO DISEÑO (fase 3). Todo lo que tocaría el sistema lanza NoSoportado: así nunca se toma una
    decisión con un dato falso (p. ej. dar por muerto un proceso porque no existe /proc)."""
    nombre = "windows"
    estado = "solo_diseno"

    def __init__(self, proc_dir=None):
        super().__init__(proc_dir)
        self.recursos = ProveedorWindows()

    def raiz_temporal(self, env=None):
        raise NoSoportado("raiz_temporal (diseño: %TEMP% o %TMP%; rutas.py aún exige TMPDIR)")

    def comando_servidor(self) -> list:
        return ["llama-server.exe"]


def adaptador(env=None, proc_dir="/proc") -> AdaptadorPlataforma:
    n = nombre(env)
    if n == "windows":
        return AdaptadorWindows()
    if n == "android_termux":
        return AdaptadorTermux(proc_dir)
    return AdaptadorLinux(proc_dir)


# --- auditoría estática de dependencias de plataforma (solo LEE el código fuente) ----------------
CATEGORIAS = {
    "rutas": [r"TMPDIR", r"O_NOFOLLOW", r"\bos\.link\b", r"/data/data", r"\bPREFIX\b"],
    "procesos": [r"/proc/\{?pid", r"\bos\.getpid\(\)", r"\.terminate\(\)", r"\.kill\(\)", r"SIGKILL"],
    "recursos": [r"/proc/meminfo", r"/proc/self", r"/sys/class/power_supply", r"proc_dir"],
    "servidor": [r"termux-wake-(?:un)?lock", r"llama-server", r"127\.0\.0\.1"],
    "senales": [r"signal\.SIG(?:INT|TERM)", r"signal\.signal\("],
}


def auditar_dependencias(raiz=None) -> dict:
    """{categoria: {archivo: [lineas]}} de usos dependientes del sistema operativo en src/eq2 y los
    ejecutables. Determinista; no ejecuta ni importa nada."""
    raiz = _Path(raiz) if raiz else _Path(__file__).resolve().parent.parent.parent
    archivos = sorted((raiz / "src" / "eq2").glob("*.py")) + [raiz / n for n in ("ejecutar_v2.py", "supervisar.py")
                                                              if (raiz / n).is_file()]
    out = {c: {} for c in CATEGORIAS}
    for f in archivos:
        if f.name == "plataforma.py":
            continue
        for n, linea in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            s = linea.strip()
            if not s or s.startswith("#"):
                continue
            for c, pats in CATEGORIAS.items():
                if any(_re.search(p, linea) for p in pats):
                    out[c].setdefault(f.name, []).append(n)
    return out
