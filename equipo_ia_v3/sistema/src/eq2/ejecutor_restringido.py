"""V2-E.7: EJECUTOR RESTRINGIDO de pruebas Python, la capacidad MÍNIMA para que A2 ejecute pruebas de verdad.

Por qué no basta el Modo B: en Termux sin root no hay sandbox real (aislamiento.SinAislamiento). Este
ejecutor NO lo sustituye ni activa config.MODO_B_HABILITADO. Su alcance es más estrecho: código de
cómputo puro que pasa una LISTA BLANCA, ejecutado en capas:

  1. Lista blanca AST (antes de ejecutar nada): solo módulos de cálculo de la biblioteca estándar y
     módulos locales del propio espacio; sin open/exec/eval/getattr..., sin atributos que empiecen por
     '_' (salvo self._x y __init__/__name__), sin atributos con nombre de módulo peligroso (os, sys,
     subprocess...), sin reasignar atributos ajenos, sin `from x import *` ni imports relativos.
  2. Proceso hijo `python3 -I -S -B corredor_pruebas.py` en una COPIA del espacio, con entorno mínimo,
     sesión propia y límites del núcleo, y un gancho de auditoría que bloquea escritura fuera del espacio,
     red, subprocesos, ctypes y señales (ver corredor_pruebas.py).
  3. Tiempo límite de pared: el ejecutor termina a SU PROPIO hijo (Popen.kill), nunca a otro proceso.
  4. Resultados solo con el «nonce» de la ejecución; salidas completas, códigos de retorno y huellas
     SHA-256 guardados sin sobrescribir (pruebas/P<nnn>/).
Requiere la autorización explícita del usuario por ejecución (`equipo.py tarea ejecutar ... --autorizo-pruebas`):
sin ella devuelve «no_disponible». Ningún texto de agente ni JSON de tarea puede concederla.
Límite honesto: un proceso del mismo usuario no está aislado del resto de sus archivos a nivel del sistema
operativo; la protección es la lista blanca + el gancho de auditoría, no el núcleo.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path

from . import config, rutas
from .ejecutor import EjecutorBase, Resultado

CORREDOR = Path(__file__).resolve().parent / "corredor_pruebas.py"
MAX_SALIDA = 2_000_000                        # bytes guardados de stdout y de stderr (cada uno)
MODULOS_PERMITIDOS = {"unittest", "math", "cmath", "string", "re", "itertools", "functools", "collections",
                      "dataclasses", "typing", "fractions", "decimal", "statistics", "heapq", "bisect",
                      "copy", "operator", "enum", "json", "datetime", "random", "textwrap", "numbers", "abc"}
SUBMODULOS_PROHIBIDOS = {"unittest.mock"}
NOMBRES_PROHIBIDOS = {"open", "exec", "eval", "compile", "__import__", "globals", "locals", "vars", "getattr",
                      "setattr", "delattr", "input", "breakpoint", "help", "exit", "quit", "memoryview",
                      "__builtins__", "__loader__", "__spec__", "__file__"}
DUNDER_PERMITIDOS = {"__init__", "__name__", "__main__"}
ATRIBUTOS_PROHIBIDOS = {"os", "sys", "io", "subprocess", "socket", "shutil", "builtins", "importlib", "ctypes",
                        "signal", "posix", "nt", "gc", "inspect", "marshal", "pickle", "types", "threading",
                        "multiprocessing", "pathlib", "tempfile", "glob", "code", "codeop", "runpy", "mmap",
                        "fcntl", "resource", "pty", "urllib", "http", "platform", "sysconfig", "linecache",
                        "tokenize", "warnings", "weakref", "atexit", "faulthandler", "tracemalloc", "site",
                        "loader", "mock", "case", "suite", "runner", "main", "util", "result", "signals"}
PROPIOS = {"self", "cls"}


def validar(archivos: dict) -> list:
    """Problemas de la lista blanca para {ruta: contenido}. Lista vacía = se puede ejecutar."""
    locales = {Path(r).stem for r in archivos if r.endswith(".py")}
    prob = []
    for ruta, txt in sorted(archivos.items()):
        if not ruta.endswith(".py"):
            continue
        if "/" in ruta or "\\" in ruta:
            prob.append(f"{ruta}: solo se ejecutan archivos en la raíz del espacio")
            continue
        try:
            arbol = ast.parse(txt, filename=ruta)
        except (SyntaxError, ValueError, RecursionError, MemoryError) as e:
            prob.append(f"{ruta}: sintaxis: {type(e).__name__}: {str(e)[:120]}")
            continue
        for n in ast.walk(arbol):
            linea = f"{ruta}:{getattr(n, 'lineno', '?')}"
            if isinstance(n, ast.Import):
                for a in n.names:
                    raiz = a.name.split(".")[0]
                    if a.name in SUBMODULOS_PROHIBIDOS or (raiz not in MODULOS_PERMITIDOS and raiz not in locales):
                        prob.append(f"{linea}: import no permitido: {a.name}")
            elif isinstance(n, ast.ImportFrom):
                raiz = (n.module or "").split(".")[0]
                if n.level or not n.module or n.module in SUBMODULOS_PROHIBIDOS or \
                        (raiz not in MODULOS_PERMITIDOS and raiz not in locales):
                    prob.append(f"{linea}: import no permitido: from {'.' * n.level}{n.module or ''}")
                if any(a.name == "*" for a in n.names):
                    prob.append(f"{linea}: `from ... import *` no permitido")
                for a in n.names:
                    if a.name.startswith("_") or a.name in ATRIBUTOS_PROHIBIDOS:
                        prob.append(f"{linea}: nombre importado no permitido: {a.name}")
            elif isinstance(n, ast.Name):
                if n.id in NOMBRES_PROHIBIDOS or (n.id.startswith("__") and n.id not in DUNDER_PERMITIDOS):
                    prob.append(f"{linea}: nombre no permitido: {n.id}")
            elif isinstance(n, ast.Attribute):
                propio = isinstance(n.value, ast.Name) and n.value.id in PROPIOS
                if n.attr.startswith("__") and n.attr not in DUNDER_PERMITIDOS:
                    prob.append(f"{linea}: atributo no permitido: {n.attr}")
                elif n.attr.startswith("_") and not propio:
                    prob.append(f"{linea}: atributo privado ajeno no permitido: {n.attr}")
                elif n.attr in ATRIBUTOS_PROHIBIDOS:
                    prob.append(f"{linea}: atributo no permitido: {n.attr}")
            elif isinstance(n, (ast.Assign, ast.AugAssign, ast.AnnAssign, ast.Delete)):
                destinos = n.targets if isinstance(n, (ast.Assign, ast.Delete)) else [n.target]
                for d in destinos:
                    for x in ast.walk(d):
                        if isinstance(x, ast.Attribute) and not (
                                isinstance(x.value, ast.Name) and x.value.id in PROPIOS):
                            prob.append(f"{linea}: no se pueden modificar atributos ajenos")
                            break
    return list(dict.fromkeys(prob))


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


class EjecutorRestringido(EjecutorBase):
    nombre = "restringido_local"
    simulado = False
    aislamiento = "proceso_restringido_sin_sandbox"

    def __init__(self, lab: rutas.Laboratorio, partes_base=(), autorizado: bool = False,
                 seg: int = None, mem_mb: int = None, ahora=None, python: str = None):
        self.lab, self.partes_base = lab, tuple(partes_base)
        self.autorizado = autorizado is True
        self.seg = int(seg or config.EJECUTOR_SEG_POR_EJECUCION)
        self.mem_mb = int(mem_mb or max(config.EJECUTOR_MEM_MB, 384))
        self.ahora = ahora or (lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))
        self.python = python or sys.executable
        self.ejecuciones = []

    def _siguiente(self):
        self.lab.crear_dir(*self.partes_base, "pruebas")
        n = 1
        while os.path.lexists(str(self.lab.ruta(*self.partes_base, "pruebas", f"P{n:03d}"))):
            n += 1
        partes = self.partes_base + ("pruebas", f"P{n:03d}")
        self.lab.crear_dir_exclusivo(*partes)
        return partes

    def _ejecutar(self, espacio, herramienta, politica):
        if herramienta != "pruebas_python":
            return Resultado("rechazado", False, salida=f"herramienta no soportada: {herramienta}")
        if not self.autorizado:
            return Resultado("no_disponible", False,
                             salida="ejecución de pruebas no autorizada (falta --autorizo-pruebas)")
        archivos = dict(getattr(espacio, "archivos", {}) or {})
        prob = validar(archivos)
        partes = self._siguiente()
        reg = {"herramienta": herramienta, "solicitada_por": "A2", "inicio": self.ahora(),
               "archivos": {r: sha256(t.encode("utf-8")) for r, t in sorted(archivos.items())}}
        if not any(r.split("/")[-1].startswith("test") and r.endswith(".py") for r in archivos):
            prob.append("no hay ningún archivo test*.py que ejecutar")
        if prob:
            reg.update(estado="rechazado_por_politica", problemas=prob, fin=self.ahora())
            self.lab.crear_exclusivo(partes + ("registro.json",), json.dumps(reg, ensure_ascii=False, indent=1))
            self.ejecuciones.append(reg)
            return Resultado("fallos", False, salida="código rechazado por la lista blanca: " + "; ".join(prob)[:900],
                             tipo="estatico", detalle={"errores": prob[:20], "rechazado_por_politica": True,
                                                       "carpeta": "/".join(partes[len(self.partes_base):])})
        self.lab.crear_dir(*partes, "espacio")
        for r, t in sorted(archivos.items()):
            self.lab.crear_exclusivo(partes + ("espacio", r), t)
        ruta_esp = str(self.lab.ruta(*partes, "espacio"))
        comando = [self.python, "-I", "-S", "-B", str(CORREDOR), ruta_esp, str(self.seg), str(self.mem_mb)]
        entorno = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "PYTHONHASHSEED": "0", "HOME": ruta_esp,
                   "TMPDIR": ruta_esp}
        reg["comando"] = comando
        nonce = secrets.token_hex(16)
        t0 = time.monotonic()
        excedido = False
        proc = subprocess.Popen(comando, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                cwd=ruta_esp, env=entorno, start_new_session=True, close_fds=True)
        try:
            out, err = proc.communicate(nonce.encode("ascii"), timeout=self.seg + 5)
        except subprocess.TimeoutExpired:
            excedido = True
            proc.kill()                                 # SOLO el hijo propio, por su objeto Popen
            out, err = proc.communicate()
        dur = round(time.monotonic() - t0, 3)
        datos, nonce_ok = None, False
        for linea in reversed(out.decode("utf-8", "replace").splitlines()):
            if linea.startswith("EQ2RES "):
                _, n, js = (linea.split(" ", 2) + ["", ""])[:3]
                if n != nonce:                           # línea falsificada por el código probado: se ignora
                    continue
                try:
                    datos, nonce_ok = json.loads(js), True
                except ValueError:
                    pass
                break
        self.lab.crear_exclusivo(partes + ("salida.txt",), out[:MAX_SALIDA].decode("utf-8", "replace"))
        self.lab.crear_exclusivo(partes + ("errores.txt",), err[:MAX_SALIDA].decode("utf-8", "replace"))
        despues = {}
        for r in sorted(archivos):
            p = self.lab.ruta(*partes, "espacio", r)
            despues[r] = sha256(p.read_bytes()) if p.is_file() else None
        reg.update(fin=self.ahora(), duracion_s=dur, codigo_retorno=proc.returncode, tiempo_excedido=excedido,
                   nonce_valido=nonce_ok, salida_sha256=sha256(out), errores_sha256=sha256(err),
                   salida_truncada=len(out) > MAX_SALIDA, errores_truncados=len(err) > MAX_SALIDA,
                   archivos_modificados_por_las_pruebas=sorted(r for r in archivos if despues[r] != reg["archivos"][r]),
                   resultado=datos and {k: datos[k] for k in ("total", "fallos", "errores", "omitidas", "pruebas",
                                                             "errores_carga", "limites")})
        if datos is not None:
            self.lab.crear_exclusivo(partes + ("informe_unittest.txt",), datos.get("texto", ""))
        if datos is None:
            estado = "error"
        elif proc.returncode == 0 and datos["total"] > 0 and datos["fallos"] == 0 and datos["errores"] == 0 \
                and not excedido:
            estado = "ok"
        else:
            estado = "fallos"
        reg["estado"] = estado
        self.lab.crear_exclusivo(partes + ("registro.json",), json.dumps(reg, ensure_ascii=False, indent=1))
        self.ejecuciones.append(reg)
        pruebas = (datos or {}).get("pruebas", {})
        malas = sorted(k for k, v in pruebas.items() if v != "ok")
        resumen = (f"{(datos or {}).get('total', 0)} pruebas, {len(malas)} sin pasar, código {proc.returncode}"
                   + (", TIEMPO EXCEDIDO" if excedido else "") + ("" if nonce_ok else ", SIN RESULTADO VÁLIDO"))
        errores = (datos or {}).get("errores_carga", []) + \
            [l for l in ((datos or {}).get("texto", "") + err.decode("utf-8", "replace")).splitlines()
             if l.startswith(("AssertionError", "Error", "FAIL", "ERROR")) or "Error:" in l][:15]
        return Resultado(estado, False, pruebas_total=(datos or {}).get("total", 0), pruebas_fallidas=len(malas),
                         salida=resumen, duracion_s=dur, tipo="real",
                         detalle={"pruebas": {k: ("ok" if v == "ok" else "fallo") for k, v in pruebas.items()},
                                  "pruebas_detectadas": sorted(pruebas), "errores": errores[:15],
                                  "codigo_retorno": proc.returncode, "nonce_valido": nonce_ok,
                                  "carpeta": "/".join(partes[len(self.partes_base):]),
                                  "aislamiento": self.aislamiento})
