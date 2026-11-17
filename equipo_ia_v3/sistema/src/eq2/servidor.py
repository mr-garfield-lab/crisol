"""Gestión del proceso hijo llama-server (único módulo autorizado a usar subprocess).

Mecanismos copiados y adaptados de prueba3.py (revisada y ejecutada con éxito).
Reglas: escucha SOLO en config.HOST; un único hijo por ejecución; se detiene
únicamente ese hijo (terminate -> espera -> kill del propio hijo); nunca pkill;
el entorno del hijo no hereda variables que parezcan credenciales; no lee ni
modifica nada del proyecto existente salvo la lectura del modelo (modelo.py).
LIMITACIÓN: si Android mata a este proceso con SIGKILL, el hijo podría seguir
vivo; la siguiente ejecución lo detecta (llama_activo) y NO lo mata.
"""
from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
import time

from . import cliente_http, config, modelo, vigilancia
from .inferencia import ErrorInferencia

_FLAGS_NECESARIOS = ("--host", "--port", "--ctx-size", "--threads", "--parallel", "--no-ui")
_ERR_LOG = re.compile(r"\b(error|failed|abort|assert|out of memory|killed)\b", re.I)


def entorno(base=None):
    """Entorno del hijo sin variables que parezcan credenciales."""
    base = os.environ if base is None else base
    return {k: v for k, v in base.items()
            if not re.search(config.ENV_SENSIBLE, k, re.I)}


def llama_activo(proc_dir="/proc"):
    """pid (str) de un proceso cuyo nombre empiece por 'llama', o None. Solo lee /proc."""
    try:
        for nombre in os.listdir(proc_dir):
            if nombre.isdigit():
                try:
                    with open(f"{proc_dir}/{nombre}/comm") as f:
                        if f.read().startswith("llama"):
                            return nombre
                except OSError:
                    pass
    except OSError:
        return None
    return None


def puerto_libre(puerto: int) -> bool:
    """Libre = se puede enlazar (con SO_REUSEADDR, para ignorar TIME_WAIT) Y nadie acepta conexiones."""
    s = socket.socket()
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((config.HOST, puerto))
    except OSError:
        return False
    finally:
        s.close()
    c = socket.socket()
    c.settimeout(0.5)
    try:
        c.connect((config.HOST, puerto))
        return False            # alguien escucha
    except OSError:
        return True
    finally:
        c.close()


def _ejecutar_simple(argv, timeout):
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout)


def wake_lock(ejecutar=_ejecutar_simple, liberar=False):
    """termux-wake-lock / termux-wake-unlock. Devuelve 'ok' o 'fallo ...' (nunca lanza)."""
    try:
        ejecutar(["termux-wake-unlock" if liberar else "termux-wake-lock"], 10)
        return "ok"
    except Exception as e:
        return f"fallo {type(e).__name__}"


class ServidorLlama:
    def __init__(self, puerto=config.PUERTO, comando=None, detector_llama=llama_activo,
                 ayuda_fn=None, lector_mem=vigilancia.leer_mem_available,
                 gracia_term=config.GRACIA_TERM_S, gracia_kill=config.GRACIA_KILL_S,
                 max_carga_s=config.MAX_CARGA_S, sondeo_s=config.INTERVALO_SONDEO_S):
        if not (isinstance(puerto, int) and 1024 <= puerto <= 65535):
            raise ValueError("puerto fuera de rango")
        self.puerto = puerto
        self.comando = list(comando) if comando else ["llama-server"]
        self.detector_llama, self.ayuda_fn, self.lector_mem = detector_llama, ayuda_fn, lector_mem
        self.gracia_term, self.gracia_kill = gracia_term, gracia_kill
        self.max_carga_s, self.sondeo_s = max_carga_s, sondeo_s
        self.proc = None
        self.log = None
        self.lab = None
        self.run_id = None
        self.argv = None
        self.pos_log = 0
        self.comprobado = False
        self.huella_inicial = None

    # --- comprobaciones previas (no arrancan el servidor) -------------------
    def comprobaciones(self, verificar_flags=True) -> dict:
        problemas = []
        out = {"puerto": self.puerto, "host": config.HOST, "soporta_prefill": None}
        h = modelo.huella_modelo()
        out["modelo"] = h
        problemas += modelo.problemas_modelo(h)
        self.huella_inicial = h
        mem = self.lector_mem()
        out["mem_available_kb"] = mem
        if mem is None:
            problemas.append("no se puede leer MemAvailable: no habría vigilancia de memoria")
        pid = self.detector_llama()
        out["llama_activo_pid"] = pid
        if pid:
            problemas.append(f"ya hay un proceso llama (pid {pid}); no se inicia ni se mata nada")
        out["puerto_libre"] = puerto_libre(self.puerto)
        if not out["puerto_libre"]:
            problemas.append("puerto ocupado")
        exe = self.comando[0]
        ruta = exe if os.path.isabs(exe) else shutil.which(exe)
        out["binario"] = ruta
        if not ruta or not os.path.exists(ruta):
            problemas.append(f"no se encuentra el ejecutable {exe!r}")
        elif verificar_flags:
            try:
                ayuda = (self.ayuda_fn() if self.ayuda_fn else
                         (lambda r: r.stdout + r.stderr)(_ejecutar_simple(self.comando + ["--help"], 30)))
            except Exception as e:
                ayuda = ""
                problemas.append(f"no se pudo leer --help: {type(e).__name__}")
            falta = [f for f in _FLAGS_NECESARIOS
                     if not re.search(r"(?<![\w-])" + re.escape(f) + r"(?![\w-])", ayuda)]
            out["flags_faltantes"] = falta
            # V2-D: la continuación de respuestas (prefill del último mensaje 'assistant') existe en
            # las versiones de llama-server que ofrecen --no-prefill-assistant (activo por defecto).
            # Es una INDICACIÓN: el comportamiento real se verifica en el dispositivo.
            out["soporta_prefill"] = bool(re.search(r"(?<![\w-])--no-prefill-assistant(?![\w-])", ayuda))
            if falta and ayuda:
                problemas.append(f"flags no disponibles en esta versión: {falta}")
        out["problemas"] = problemas
        out["ok"] = not problemas
        self.comprobado = out["ok"]
        return out

    # --- arranque ------------------------------------------------------------
    def construir_argv(self):
        # mmap activado = comportamiento por defecto: sin --no-mmap, --mlock ni --cache-ram.
        return self.comando + ["-m", str(config.ruta_modelo()), "--host", config.HOST,
                               "--port", str(self.puerto), "-c", str(config.CTX),
                               "-t", str(config.HILOS), "-np", str(config.NP), "--no-ui"]

    def lanzar(self, lab, run_id):
        if self.proc is not None:
            raise ErrorInferencia("servidor_ya_lanzado", fatal=True)
        if not self.comprobado:
            raise ErrorInferencia("comprobaciones_no_superadas", fatal=True)
        self.lab, self.run_id = lab, run_id
        self.argv = self.construir_argv()
        self.log = lab.abrir_binario_exclusivo(("runs", run_id, "server.log"))
        try:
            self.proc = subprocess.Popen(
                self.argv, stdout=self.log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                env=entorno(), cwd=str(lab.ruta("runs", run_id)))
        except BaseException:
            self.cerrar_log()          # no dejar el registro abierto si no hay proceso
            raise
        return self.proc.pid

    def vivo(self):
        return self.proc is not None and self.proc.poll() is None

    def pid(self):
        return self.proc.pid if self.proc is not None else None

    def esperar_listo(self, deberia_parar=lambda: None, supervisar=lambda: None):
        """Sondea GET /health hasta 200. Devuelve los segundos de carga o lanza ErrorInferencia."""
        t = time.monotonic()
        while True:
            m = supervisar() or deberia_parar()
            if m:
                raise ErrorInferencia(f"abortado_durante_carga:{m}", fatal=True)
            if self.proc.poll() is not None:
                raise ErrorInferencia(f"servidor_murio_al_arrancar_rc_{self.proc.returncode}", fatal=True)
            if time.monotonic() - t > self.max_carga_s:
                raise ErrorInferencia("timeout_carga", fatal=True)
            try:
                r = cliente_http.peticion(self.puerto, "GET", "/health", None, 3.0, deberia_parar)
                if r.status == 200:
                    return round(time.monotonic() - t, 2)
            except cliente_http.ErrorHTTP as e:
                if e.motivo in ("senal", "stop_usuario") or e.motivo.startswith("presion"):
                    raise ErrorInferencia(f"abortado_durante_carga:{e.motivo}", fatal=True)
            fin = time.monotonic() + self.sondeo_s
            while time.monotonic() < fin and self.proc.poll() is None:
                time.sleep(min(0.1, self.sondeo_s))

    def murio_pronto(self, espera=0.5):
        """True si el hijo termina en `espera` s (se usa tras un error de comunicación)."""
        if self.proc is None:
            return False
        try:
            self.proc.wait(espera)
            return True
        except subprocess.TimeoutExpired:
            return False

    def log_nuevo(self):
        """Líneas de error nuevas del registro (posiciones en BYTES)."""
        if self.lab is None:
            return []
        datos, self.pos_log = self.lab.leer_desde(("runs", self.run_id, "server.log"), self.pos_log)
        if datos is None:
            return ["log_ilegible"]
        txt = datos.decode("utf-8", "replace")
        return [l[:200] for l in txt.splitlines() if _ERR_LOG.search(l)][:5]

    # --- parada: SOLO el hijo propio ------------------------------------------
    def detener(self):
        if self.proc is None:
            return "sin_servidor"
        if self.proc.poll() is not None:
            return f"ya_terminado_rc_{self.proc.returncode}"
        try:
            self.proc.terminate()
        except ProcessLookupError:
            pass
        try:
            self.proc.wait(self.gracia_term)
            return "SIGTERM_ok"
        except subprocess.TimeoutExpired:
            pass
        try:
            self.proc.kill()
        except ProcessLookupError:
            pass
        try:
            self.proc.wait(self.gracia_kill)
            return "SIGKILL_usado"
        except subprocess.TimeoutExpired:
            return f"NO_TERMINA_revisar_pid_{self.proc.pid}"

    def cerrar_log(self):
        if self.log is not None:
            self.log.close()
        return "ok"

    def esperar_puerto_libre(self, timeout=3.0):
        fin = time.monotonic() + timeout
        while True:
            if puerto_libre(self.puerto):
                return True
            if time.monotonic() > fin:
                return False
            time.sleep(0.1)
