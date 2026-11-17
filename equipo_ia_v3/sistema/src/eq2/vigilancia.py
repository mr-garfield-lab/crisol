"""Vigilancia de memoria y batería con lectores inyectables.

En V0-V1 se vigila entre llamadas desde el hilo principal. El hilo monitor con
latido (heartbeat) de prueba3 se copiará en V2, cuando exista un servidor al
que supervisar. Las medidas no disponibles se guardan como None, nunca como 0.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from . import config


def parsear_meminfo(texto: str):
    """Devuelve MemAvailable en kB, o None si no aparece o es ilegible."""
    for linea in texto.splitlines():
        if linea.startswith("MemAvailable:"):
            partes = linea.split()
            if len(partes) >= 2 and partes[1].isdigit():
                return int(partes[1])
    return None


def leer_mem_available(ruta: str = "/proc/meminfo"):
    try:
        return parsear_meminfo(Path(ruta).read_text())
    except OSError:
        return None


def leer_bateria(base: str = "/sys/class/power_supply/battery"):
    """(porcentaje|None, cargando|None). Cualquier fallo -> (None, None)."""
    try:
        b = Path(base)
        pct = int((b / "capacity").read_text().strip())
        estado = (b / "status").read_text().strip().lower()
        return pct, estado in ("charging", "full")
    except (OSError, ValueError):
        return None, None


@dataclass
class Muestra:
    ts: float
    mem_kb: int | None
    bateria_pct: int | None
    cargando: bool | None


class Vigilante:
    def __init__(self, lector_mem=leer_mem_available, lector_bat=leer_bateria,
                 umbral_kb: int = config.UMBRAL_MEM_KB,
                 consecutivas: int = config.MUESTRAS_BAJAS_CONSECUTIVAS,
                 fallos_max: int = config.FALLOS_MONITOR_MAX,
                 bateria_min: int = config.BATERIA_MIN_PCT, reloj=time.time):
        self.lector_mem, self.lector_bat = lector_mem, lector_bat
        self.umbral_kb, self.consecutivas = umbral_kb, consecutivas
        self.fallos_max, self.bateria_min, self.reloj = fallos_max, bateria_min, reloj
        self._bajas = 0
        self._fallos = 0
        self.historial: list[Muestra] = []

    def muestrear(self) -> Muestra:
        try:
            mem = self.lector_mem()
        except Exception:        # un lector defectuoso no debe tumbar el proceso
            mem = None
        try:
            pct, carg = self.lector_bat()
        except Exception:
            pct, carg = None, None
        m = Muestra(self.reloj(), mem, pct, carg)
        self.historial.append(m)
        return m

    def verificar(self):
        """Toma una muestra. Devuelve None si todo va bien o un motivo de parada."""
        m = self.muestrear()
        if m.mem_kb is None:
            self._fallos += 1
            if self._fallos >= self.fallos_max:
                return "monitor_falla"
        else:
            self._fallos = 0
            if m.mem_kb < self.umbral_kb:
                self._bajas += 1
                if self._bajas >= self.consecutivas:
                    return "memoria_baja"
            else:
                self._bajas = 0
        if (m.bateria_pct is not None and m.cargando is False
                and m.bateria_pct < self.bateria_min):
            return "bateria_baja"
        return None
