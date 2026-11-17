#!/usr/bin/env python3
"""Validación ESTÁTICA de src/eq2: no importa ni ejecuta el código analizado.

Uso:  python3 -B -I validar_estatico.py
Sale con código 0 si todo pasa, 1 si algo falla. Solo lee archivos.
"""
import ast
import hashlib
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
SRC = RAIZ / "src" / "eq2"

IMPORTS_PROHIBIDOS = {"subprocess", "socket", "ssl", "urllib", "http", "requests", "ctypes",
                      "pickle", "marshal", "shelve", "multiprocessing", "pty", "telnetlib",
                      "ftplib", "smtplib", "asyncio", "importlib",
                      # V2-D: módulos que permiten ejecutar código arbitrario
                      "runpy", "code", "codeop", "pdb", "imp", "zipimport"}
# Excepciones por módulo (el resto de módulos no puede importarlos):
IMPORTS_PERMITIDOS = {"servidor.py": {"subprocess", "socket"}, "cliente_http.py": {"socket"},
                      # V2-E.7: el ejecutor restringido lanza SOLO el corredor de pruebas (lista blanca + límites)
                      "ejecutor_restringido.py": {"subprocess"}}
LLAMADAS_RED = {"connect", "bind", "create_connection"}
LLAMADAS_PROHIBIDAS = {"eval", "exec", "compile", "__import__", "input", "breakpoint"}
ATRIBUTOS_PROHIBIDOS = {("os", n) for n in (
    "system", "popen", "kill", "killpg", "unlink", "rename", "fork",
    "execv", "execve", "execvp", "execl", "execlp", "spawnl", "spawnv", "chmod", "chown",
    "symlink")} | {("shutil", "rmtree"), ("shutil", "move"), ("shutil", "copy"),
                           ("shutil", "copytree"), ("signal", "alarm")}
METODOS_ESCRITURA = {"write_text", "write_bytes", "touch", "unlink", "mkdir", "rmdir",
                     "symlink_to", "hardlink_to"}
# Solo rutas.py puede crear/escribir/borrar archivos o carpetas (con confinamiento).
# V2-E: os.replace y os.link pasan de prohibidos a «solo rutas.py» (escrituras atómicas).
ATRIBUTOS_SOLO_RUTAS = {("os", n) for n in ("open", "mkdir", "makedirs", "rmdir", "fdopen",
                                           "remove", "replace", "link")}
MODULOS_QUE_PUEDEN_ESCRIBIR = {"rutas.py"}


def _es_config_host(nodo) -> bool:
    return (isinstance(nodo, ast.Attribute) and nodo.attr == "HOST"
            and isinstance(nodo.value, ast.Name) and nodo.value.id == "config")


def problemas_de(ruta: Path):
    fuente = ruta.read_text(encoding="utf-8")
    arbol = ast.parse(fuente, filename=str(ruta))
    pr = []
    nombre = ruta.name
    permitidos = IMPORTS_PERMITIDOS.get(nombre, set())
    if "equipo-ia" in fuente and nombre != "config.py":
        pr.append("menciona 'equipo-ia' fuera de config.py")
    for nodo in ast.walk(arbol):
        # V2-E.1: el módulo que escribe (rutas.py) no puede capturar errores de forma indiscriminada.
        if nombre in MODULOS_QUE_PUEDEN_ESCRIBIR and isinstance(nodo, ast.ExceptHandler):
            tipos = []
            if nodo.type is None:
                tipos = ["(desnudo)"]
            else:
                for t in (nodo.type.elts if isinstance(nodo.type, ast.Tuple) else [nodo.type]):
                    if isinstance(t, ast.Name) and t.id in ("Exception", "BaseException"):
                        tipos.append(t.id)
            if tipos:
                pr.append(f"línea {nodo.lineno}: except {tipos[0]} prohibido en {nombre}")
        if isinstance(nodo, ast.Import):
            for a in nodo.names:
                if a.name.split(".")[0] in IMPORTS_PROHIBIDOS - permitidos:
                    pr.append(f"línea {nodo.lineno}: import prohibido {a.name}")
        elif isinstance(nodo, ast.ImportFrom):
            if (nodo.module or "").split(".")[0] in IMPORTS_PROHIBIDOS - permitidos:
                pr.append(f"línea {nodo.lineno}: import prohibido {nodo.module}")
        elif isinstance(nodo, ast.Call):
            f = nodo.func
            for kw in nodo.keywords:
                if kw.arg == "shell" and not (isinstance(kw.value, ast.Constant) and kw.value.value is False):
                    pr.append(f"línea {nodo.lineno}: shell=... prohibido")
            nombre_llamada = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
            if nombre_llamada in LLAMADAS_RED and nombre in IMPORTS_PERMITIDOS:
                a0 = nodo.args[0] if nodo.args else None
                if not (isinstance(a0, ast.Tuple) and a0.elts and _es_config_host(a0.elts[0])):
                    pr.append(f"línea {nodo.lineno}: {nombre_llamada}() debe usar (config.HOST, puerto)")
            if isinstance(f, ast.Name) and f.id in LLAMADAS_PROHIBIDAS:
                pr.append(f"línea {nodo.lineno}: llamada prohibida {f.id}()")
            if isinstance(f, ast.Attribute):
                if isinstance(f.value, ast.Name) and (f.value.id, f.attr) in ATRIBUTOS_PROHIBIDOS:
                    pr.append(f"línea {nodo.lineno}: llamada prohibida {f.value.id}.{f.attr}()")
                if isinstance(f.value, ast.Name) and (f.value.id, f.attr) in ATRIBUTOS_SOLO_RUTAS \
                        and nombre not in MODULOS_QUE_PUEDEN_ESCRIBIR:
                    pr.append(f"línea {nodo.lineno}: {f.value.id}.{f.attr}() solo permitido en rutas.py")
                if f.attr in METODOS_ESCRITURA and nombre not in MODULOS_QUE_PUEDEN_ESCRIBIR:
                    pr.append(f"línea {nodo.lineno}: escritura de archivo en {nombre}")
                if f.attr in ("execute", "executescript", "executemany"):
                    if not nodo.args:
                        pr.append(f"línea {nodo.lineno}: {f.attr}() sin argumentos")
                    else:
                        a0 = nodo.args[0]
                        if not (isinstance(a0, ast.Constant) and isinstance(a0.value, str)
                                or isinstance(a0, ast.Name)):
                            pr.append(f"línea {nodo.lineno}: SQL no literal en {f.attr}() "
                                      f"({type(a0).__name__})")
            if isinstance(f, ast.Name) and f.id == "open":
                modo = None
                if len(nodo.args) > 1 and isinstance(nodo.args[1], ast.Constant):
                    modo = nodo.args[1].value
                for kw in nodo.keywords:
                    if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                        modo = kw.value.value
                if modo is not None and any(c in str(modo) for c in "wax+") \
                        and nombre not in MODULOS_QUE_PUEDEN_ESCRIBIR:
                    pr.append(f"línea {nodo.lineno}: open() de escritura en {nombre}")
                if modo is not None and "w" in str(modo):
                    pr.append(f"línea {nodo.lineno}: open(...,'w') sobrescribe; usar 'x' o 'a'")
    return pr


def main() -> int:
    archivos = sorted(SRC.glob("*.py")) + [p for p in [RAIZ / "ejecutar_v2.py",
                                                       RAIZ / "comparar_metricas.py",
                                                       RAIZ / "supervisar.py",
                                                       RAIZ / "auditar.py",
                                                       RAIZ / "aprender.py",     # V2-E.6
                                                       RAIZ / "retos.py",        # V2-E.6
                                                       RAIZ / "equipo.py",       # V2-E.7
                                                       RAIZ / "banco.py"] if p.exists()]   # V2-F
    if not archivos:
        print("No se encontraron módulos en", SRC)
        return 1
    fallos = 0
    print(f"{'archivo':<18}{'líneas':>7}  {'sha256 (12)':<14} resultado")
    for a in archivos:
        try:
            pr = problemas_de(a)
        except SyntaxError as e:
            pr = [f"error de sintaxis: {e}"]
        datos = a.read_bytes()
        print(f"{a.name:<18}{datos.count(b'\n'):>7}  {hashlib.sha256(datos).hexdigest()[:12]:<14} "
              f"{'OK' if not pr else 'FALLA'}")
        for p in pr:
            print("    -", p)
        fallos += len(pr)
    print("TOTAL problemas:", fallos)
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
