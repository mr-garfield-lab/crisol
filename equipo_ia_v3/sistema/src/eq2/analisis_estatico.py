"""V2-E: comprobaciones ESTÁTICAS del código generado. NO se ejecuta nada.

Se usa ast.parse (construye el árbol sintáctico; no crea ni ejecuta código objeto) con límites
de tamaño y captura de RecursionError/MemoryError. Detecta:
  * errores de sintaxis;
  * archivos de prueba sin funciones test_* y pruebas sin aserciones;
  * `from modulo import nombre` local con un nombre que el módulo no define, o módulos inexistentes;
  * imports y llamadas de RIESGO (os, subprocess, socket, eval, exec, open...) -> avisos.
Un resultado estático NO es una prueba: nunca verifica criterios de aceptación.
"""
from __future__ import annotations

import ast
import sys
import time

from . import config
from .ejecutor import EjecutorBase, Resultado

MODULOS_RIESGO = {"os", "subprocess", "socket", "shutil", "ctypes", "importlib", "pickle", "marshal",
                  "multiprocessing", "signal", "urllib", "http", "requests", "asyncio", "sys", "pty",
                  "runpy", "code", "threading", "tempfile", "pathlib", "glob"}
LLAMADAS_RIESGO = {"eval", "exec", "compile", "__import__", "open", "input", "breakpoint"}
STDLIB = set(getattr(sys, "stdlib_module_names", ())) | {"unittest", "typing", "dataclasses"}


def _parsear(ruta, contenido):
    if len(contenido.encode("utf-8")) > config.MOTOR_MAX_BYTES_ARCHIVO:
        return None, {"tipo": "demasiado_grande", "archivo": ruta}
    try:
        return ast.parse(contenido, filename=ruta), None
    except SyntaxError as e:
        return None, {"tipo": "sintaxis", "archivo": ruta, "linea": e.lineno,
                      "mensaje": str(e.msg)[:160]}
    except (ValueError, RecursionError, MemoryError) as e:
        return None, {"tipo": "no_analizable", "archivo": ruta, "mensaje": type(e).__name__}


def _nombres_definidos(arbol):
    n = set()
    for x in arbol.body:
        if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            n.add(x.name)
        elif isinstance(x, ast.Assign):
            n |= {t.id for t in x.targets if isinstance(t, ast.Name)}
        elif isinstance(x, (ast.AnnAssign,)) and isinstance(x.target, ast.Name):
            n.add(x.target.id)
        elif isinstance(x, (ast.Import, ast.ImportFrom)):
            n |= {(a.asname or a.name).split(".")[0] for a in x.names}
    return n


def analizar(archivos_: dict) -> dict:
    """archivos_: {ruta: contenido}. Devuelve {errores, avisos, pruebas_detectadas, modulos}."""
    errores, avisos, pruebas, arboles = [], [], [], {}
    for ruta, cont in sorted(archivos_.items()):
        if not ruta.endswith(".py"):
            continue
        arbol, err = _parsear(ruta, cont)
        if err:
            errores.append(err)
            continue
        arboles[ruta] = arbol
    modulos = {r[:-3].replace("/", "."): a for r, a in arboles.items()}
    for ruta, arbol in arboles.items():
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Import):
                for a in nodo.names:
                    if a.name.split(".")[0] in MODULOS_RIESGO:
                        avisos.append({"tipo": "import_riesgo", "archivo": ruta, "modulo": a.name})
            elif isinstance(nodo, ast.ImportFrom) and nodo.level == 0 and nodo.module:
                raiz = nodo.module.split(".")[0]
                if raiz in MODULOS_RIESGO:
                    avisos.append({"tipo": "import_riesgo", "archivo": ruta, "modulo": nodo.module})
                if nodo.module in modulos:
                    definidos = _nombres_definidos(modulos[nodo.module])
                    for a in nodo.names:
                        if a.name != "*" and a.name not in definidos:
                            errores.append({"tipo": "nombre_no_definido", "archivo": ruta,
                                            "modulo": nodo.module, "nombre": a.name})
                elif raiz not in STDLIB and raiz not in {m.split(".")[0] for m in modulos}:
                    errores.append({"tipo": "modulo_inexistente", "archivo": ruta, "modulo": nodo.module})
            elif isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Name) \
                    and nodo.func.id in LLAMADAS_RIESGO:
                avisos.append({"tipo": "llamada_riesgo", "archivo": ruta, "llamada": nodo.func.id})
        nombre = ruta.rsplit("/", 1)[-1]
        if nombre.startswith("test_"):
            tests = [x for x in arbol.body if isinstance(x, ast.FunctionDef) and x.name.startswith("test_")]
            for c in arbol.body:
                if isinstance(c, ast.ClassDef):
                    tests += [x for x in c.body if isinstance(x, ast.FunctionDef) and x.name.startswith("test_")]
            if not tests:
                errores.append({"tipo": "pruebas_ausentes", "archivo": ruta})
            for t in tests:
                pruebas.append(t.name)
                tiene = any(isinstance(n, ast.Assert) or (isinstance(n, ast.Call) and isinstance(
                    n.func, ast.Attribute) and n.func.attr.startswith("assert")) for n in ast.walk(t))
                if not tiene:
                    avisos.append({"tipo": "prueba_sin_aserciones", "archivo": ruta, "prueba": t.name})
    if not any(r.rsplit("/", 1)[-1].startswith("test_") for r in archivos_):
        errores.append({"tipo": "sin_archivo_de_pruebas"})
    return {"errores": errores, "avisos": avisos, "pruebas_detectadas": sorted(set(pruebas)),
            "modulos": sorted(modulos)}


class EjecutorEstatico(EjecutorBase):
    """No ejecuta: analiza. Resultado tipo 'estatico'; pruebas_total = 0 (nada se ejecutó)."""
    nombre = "analisis_estatico"
    simulado = False
    aislamiento = "no_aplica"

    def _ejecutar(self, espacio, herramienta, politica):
        t0 = time.monotonic()
        a = analizar(dict(espacio.archivos))
        return Resultado("fallos" if a["errores"] else "ok", False, pruebas_total=0,
                         pruebas_fallidas=0, tipo="estatico", duracion_s=round(time.monotonic() - t0, 3),
                         salida="; ".join(f"{e['tipo']}:{e.get('archivo', '')}:{e.get('linea', e.get('nombre', ''))}"
                                          for e in a["errores"])[:1500],
                         detalle=a)
