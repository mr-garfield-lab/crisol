"""V2-E: gestión SEGURA de los archivos de un proyecto generado por A1.

* Rutas RELATIVAS validadas componente a componente (sin absolutas, sin '..', sin '\\', sin ':',
  sin ocultos, sin nombres reservados de Windows, profundidad y longitud limitadas).
* Enlaces simbólicos rechazados en cualquier componente (rutas.Laboratorio).
* Cada versión va a una carpeta NUEVA (runs/<run>/proyecto/v<n>/): nunca se sobrescribe; las
  versiones anteriores se conservan para comparar y recuperar.
* Escrituras atómicas sin sobrescritura (rutas.escribir_atomico) y manifiesto con SHA-256.
* Límites de cantidad de archivos, tamaño por archivo y tamaño total.
Nada de lo que se escribe aquí se ejecuta.
"""
from __future__ import annotations

import hashlib
import json
import re

from . import archivos, config, rutas

_COMP = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_-]{0,47}")
_ARCH = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_-]{0,47}\.[a-z]{1,4}")
MAX_LONGITUD_RUTA = 120


class LimiteSuperado(ValueError):
    pass


def partes_ruta(ruta) -> tuple | None:
    """Componentes de una ruta relativa VÁLIDA, o None si no es aceptable."""
    if not isinstance(ruta, str) or not ruta or len(ruta) > MAX_LONGITUD_RUTA:
        return None
    if any(c in ruta for c in ("\\", ":", "\x00", "~")) or ruta.startswith("/"):
        return None
    partes = tuple(ruta.split("/"))
    if len(partes) > config.MOTOR_MAX_PROFUNDIDAD:
        return None
    *dirs, nombre = partes
    for d in dirs:
        if not _COMP.fullmatch(d) or d.lower() in archivos.RESERVADOS:
            return None
    if not _ARCH.fullmatch(nombre):
        return None
    base, ext = nombre.rsplit(".", 1)
    if ("." + ext) not in config.EJECUTOR_EXTENSIONES or base.lower() in archivos.RESERVADOS:
        return None
    return partes


def ruta_valida(ruta) -> bool:
    return partes_ruta(ruta) is not None


def extraer(texto, presupuesto) -> dict:
    """Archivos de la salida de A1, con rutas y límites del presupuesto."""
    return archivos.extraer(texto, validador=ruta_valida, max_archivos=presupuesto.max_archivos,
                            max_bytes=presupuesto.max_bytes_archivo,
                            max_total=presupuesto.max_bytes_total)


def huella_conjunto(lista) -> str:
    h = hashlib.sha256()
    for a in sorted(lista, key=lambda a: a["nombre"]):
        h.update(a["nombre"].encode("utf-8") + b"\0" + a["sha256"].encode("ascii") + b"\n")
    return h.hexdigest()


class Proyecto:
    """Versiones de la solución dentro del laboratorio."""

    def __init__(self, lab: rutas.Laboratorio, run_id: str, presupuesto):
        self.lab, self.presupuesto = lab, presupuesto
        self.partes = ("runs", run_id, "proyecto")
        lab.crear_dir(*self.partes)
        self.versiones = []          # manifiestos (solo versiones COMPLETAS)
        self.contenidos = []         # {ruta: contenido} por versión (en memoria)
        # V2-E.1: el número de versión se consume al crear su carpeta. Si una versión falla a
        # mitad (p. ej. error de E/S), queda en disco SIN manifiesto.json (= incompleta) y la
        # siguiente usa el número siguiente: un fallo ya no bloquea las versiones posteriores.
        self._proximo = 1
        self.incompletas = []

    def guardar_version(self, lista) -> dict:
        if not lista:
            raise LimiteSuperado("versión vacía")
        if len(lista) > self.presupuesto.max_archivos:
            raise LimiteSuperado("demasiados archivos")
        total = sum(a["bytes"] for a in lista)
        if total > self.presupuesto.max_bytes_total:
            raise LimiteSuperado("tamaño total superado")
        for a in lista:
            if partes_ruta(a["nombre"]) is None:
                raise rutas.RutaInsegura(f"ruta no permitida: {a['nombre'][:60]!r}")
            if a["bytes"] > self.presupuesto.max_bytes_archivo:
                raise LimiteSuperado(f"archivo demasiado grande: {a['nombre']}")
        n = self._proximo
        vdir = self.partes + (f"v{n}",)
        self.lab.crear_dir_exclusivo(*vdir)                  # FileExistsError si ya existiera
        self._proximo += 1
        self.incompletas.append(n)                           # hasta que se escriba el manifiesto
        atomico = True
        for a in lista:
            *dirs, nombre = partes_ruta(a["nombre"])
            if dirs:
                self.lab.crear_dir(*vdir, *dirs)
            _, at = self.lab.escribir_atomico(vdir + tuple(dirs) + (nombre,), a["contenido"])
            atomico = atomico and at
        man = {"version": n, "archivos": [{"ruta": a["nombre"], "bytes": a["bytes"], "sha256": a["sha256"]}
                                          for a in sorted(lista, key=lambda a: a["nombre"])],
               "bytes_total": total, "sha256_conjunto": huella_conjunto(lista), "atomico": atomico}
        self.lab.escribir_atomico(vdir + ("manifiesto.json",), json.dumps(man, ensure_ascii=False, indent=2))
        self.incompletas.remove(n)
        self.versiones.append(man)
        self.contenidos.append({a["nombre"]: a["contenido"] for a in lista})
        return man

    @staticmethod
    def diferencias(a: dict, b: dict) -> dict:
        ha = {f["ruta"]: f["sha256"] for f in a["archivos"]}
        hb = {f["ruta"]: f["sha256"] for f in b["archivos"]}
        return {"añadidos": sorted(set(hb) - set(ha)), "eliminados": sorted(set(ha) - set(hb)),
                "modificados": sorted(r for r in set(ha) & set(hb) if ha[r] != hb[r]),
                "iguales": sorted(r for r in set(ha) & set(hb) if ha[r] == hb[r])}

    def repetida(self, lista) -> bool:
        """True si el conjunto es idéntico a la última versión guardada (sin progreso)."""
        return bool(self.versiones) and self.versiones[-1]["sha256_conjunto"] == huella_conjunto(lista)

    def texto_version(self, n=None, max_chars=6000) -> str:
        c = self.contenidos[(n or len(self.contenidos)) - 1] if self.contenidos else {}
        t = "\n".join(f"ARCHIVO: {r}\n```\n{x}```" for r, x in sorted(c.items()))
        return t[:max_chars]
