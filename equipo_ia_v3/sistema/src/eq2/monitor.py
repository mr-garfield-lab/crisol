"""Hilo monitor de memoria y del proceso hijo, con latido y supervisión desde el hilo principal.

Copiado y adaptado de los mecanismos revisados de prueba3.py (sin importarlo).
LIMITACIÓN: si la lectura de /proc se bloquea dentro del hilo, el latido deja de
actualizarse y el hilo NO puede abortar por sí mismo; solo `supervisar()`, llamada
desde el hilo principal en los bucles de espera, lo detecta (latido > 3*intervalo+5 s).
Si el hilo principal también se bloquea no hay una tercera capa.
Las medidas ilegibles NO aparecen en la muestra (nunca se rellenan con 0).
"""
from __future__ import annotations

import threading
import time
from collections import deque

from . import config


def leer_kv(ruta, claves):
    out = {}
    try:
        with open(ruta) as f:
            for linea in f:
                k, _, v = linea.partition(":")
                if k in claves:
                    out[k] = int(v.split()[0])
    except (OSError, ValueError, IndexError):
        pass
    return out


def leer_fallos(pid, proc_dir="/proc"):
    """minflt y majflt: campos 10 y 12 de /proc/PID/stat; se parte tras el último ')'."""
    try:
        with open(f"{proc_dir}/{int(pid)}/stat") as f:
            t = f.read()
        r = t[t.rindex(")") + 2:].split()
        return {"minflt": int(r[7]), "majflt": int(r[9])}
    except (OSError, ValueError, IndexError):
        return {}


def muestra_proceso(pid=None, proc_dir="/proc"):
    m = {"t": time.time()}
    m.update(leer_kv(f"{proc_dir}/meminfo", {"MemAvailable", "SwapFree"}))
    if pid:
        m.update(leer_kv(f"{proc_dir}/{int(pid)}/status", {"VmRSS", "VmHWM", "RssAnon", "RssFile"}))
        m.update(leer_fallos(pid, proc_dir))
    return m


class Monitor:
    def __init__(self, pid_fn, vivo_fn, lector=muestra_proceso,
                 intervalo=config.INTERVALO_MONITOR, umbral_kb=config.UMBRAL_MEM_KB,
                 consecutivas=config.MUESTRAS_BAJAS_CONSECUTIVAS, reloj=time.monotonic,
                 margen_latido=5.0):
        self.pid_fn, self.vivo_fn, self.lector = pid_fn, vivo_fn, lector
        self.intervalo, self.umbral_kb, self.consecutivas = intervalo, umbral_kb, consecutivas
        self.reloj, self.margen_latido = reloj, margen_latido
        self.abortar, self.fin, self._lock = threading.Event(), threading.Event(), threading.Lock()
        self.motivo = None
        self.latido = reloj()
        self.hilo = None
        self.n_muestras = 0
        self.min_mem = None
        self.ausentes = {k: 0 for k in config.CRITICAS}
        self.ultima = None
        self.historial = deque(maxlen=500)

    def _abortar_con(self, motivo):
        with self._lock:
            if not self.abortar.is_set():
                self.motivo = motivo
                self.abortar.set()

    def _registrar(self, m):
        with self._lock:
            self.n_muestras += 1
            self.ultima = m
            self.historial.append(m)
            mem = m.get("MemAvailable")
            if mem is not None and (self.min_mem is None or mem < self.min_mem):
                self.min_mem = mem
            for k in config.CRITICAS:
                if k not in m:
                    self.ausentes[k] += 1

    def muestra_ahora(self):
        """Muestra tomada por el llamante (antes/después de una petición)."""
        m = self.lector(self.pid_fn())
        self._registrar(m)
        return m

    def iniciar(self):
        self.latido = self.reloj()
        self.hilo = threading.Thread(target=self._bucle, daemon=True, name="eq2-monitor")
        self.hilo.start()

    def _bucle(self):
        bajas = ciegas = 0
        try:
            while not self.fin.is_set():
                self.latido = self.reloj()
                m = self.lector(self.pid_fn())
                self._registrar(m)
                if not self.vivo_fn():
                    self._abortar_con("servidor_muerto")
                    return
                mem = m.get("MemAvailable")
                ciegas = ciegas + 1 if mem is None else 0
                if ciegas >= self.consecutivas:
                    self._abortar_con("sin_medicion_MemAvailable")
                    return
                bajas = bajas + 1 if (mem is not None and mem < self.umbral_kb) else 0
                if bajas >= self.consecutivas:
                    self._abortar_con(f"presion_memoria_{mem}kB")
                    return
                self.fin.wait(self.intervalo)
        except Exception as e:
            self._abortar_con("monitor_fallo_" + type(e).__name__)

    def supervisar(self):
        """Segunda capa: la llama el HILO PRINCIPAL. Devuelve un motivo o None."""
        if self.abortar.is_set():
            return self.motivo
        if self.hilo is not None and not self.fin.is_set():
            if not self.hilo.is_alive():
                self._abortar_con("monitor_detenido")
            elif self.reloj() - self.latido > 3 * self.intervalo + self.margen_latido:
                self._abortar_con("monitor_sin_latido")
        return self.motivo if self.abortar.is_set() else None

    def detener(self, timeout=5):
        self.fin.set()
        if self.hilo is None:
            return "sin_monitor"
        self.hilo.join(timeout)
        return "NO_TERMINA_monitor" if self.hilo.is_alive() else "ok"

    def resumen(self):
        with self._lock:
            return {"muestras": self.n_muestras, "min_MemAvailable_kB": self.min_mem,
                    "criticas_ausentes": dict(self.ausentes), "motivo_aborto": self.motivo,
                    "ultima_muestra": dict(self.ultima) if self.ultima else None}
