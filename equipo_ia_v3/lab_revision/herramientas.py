"""Herramientas SIN IA del banco de revisión: dicen si un código compila y en qué línea falla.

- Python: `ast.parse` (sintaxis e indentación) y, si compila, un analizador estático propio: nombres que no existen en
  ningún ámbito (incluido un módulo usado sin `import`) y llamadas a funciones del mismo archivo con un número de
  argumentos que no encaja. No ejecuta nada.
- Java: `javac` de verdad (JDK externo). Archivos en UTF-8 SIN BOM (javac rechaza el BOM) y `-encoding UTF-8`.
  `javac` informa por fases: con un error de sintaxis no muestra los de nombres o tipos.

Límites honestos: el analizador de Python no ve tipos, atributos de objetos ni llamadas a funciones de otros módulos;
nada de esto detecta errores de lógica (harían falta ejecutar pruebas).
"""
from __future__ import annotations

import ast
import builtins
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

_BUILTINS = set(dir(builtins))
_AMBITOS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ListComp, ast.SetComp, ast.DictComp,
            ast.GeneratorExp)


def _guardados(nodo) -> set:
    """Nombres que el ámbito define: parámetros, asignaciones, bucles, with, imports, defs internas, global/nonlocal."""
    out = set()
    args = getattr(nodo, "args", None)
    if isinstance(args, ast.arguments):
        for a in args.posonlyargs + args.args + args.kwonlyargs:
            out.add(a.arg)
        for a in (args.vararg, args.kwarg):
            if a:
                out.add(a.arg)
    pila = list(ast.iter_child_nodes(nodo))
    while pila:
        n = pila.pop()
        if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            out.add(n.id)
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(n.name)
            for d in n.decorator_list:
                pila.append(d)
            continue                                       # su cuerpo es otro ámbito
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for a in n.names:
                out.add((a.asname or a.name).split(".")[0])
        elif isinstance(n, (ast.Global, ast.Nonlocal)):
            out.update(n.names)
        elif isinstance(n, ast.ExceptHandler) and n.name:
            out.add(n.name)
        elif isinstance(n, (ast.Lambda, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            continue
        pila.extend(ast.iter_child_nodes(n))
    return out


def revisar_python(codigo: str) -> list:
    try:
        arbol = ast.parse(codigo)
    except SyntaxError as e:
        return [{"linea": e.lineno, "clase": "sintaxis", "mensaje": e.msg}]
    padre = {}
    for n in ast.walk(arbol):
        for h in ast.iter_child_nodes(n):
            padre[h] = n
    modulo = _guardados(arbol)
    cache = {}

    def disponibles(n) -> set:
        nombres, x = set(modulo) | _BUILTINS, padre.get(n)
        while x is not None:
            if isinstance(x, _AMBITOS):
                if x not in cache:
                    cache[x] = _guardados(x)
                    if isinstance(x, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
                        cache[x] |= {t.id for g in x.generators for t in ast.walk(g.target) if isinstance(t, ast.Name)}
                nombres |= cache[x]
            x = padre.get(x)
        return nombres

    errores, vistos = [], set()
    for n in ast.walk(arbol):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and n.id not in disponibles(n):
            if (n.lineno, n.id) not in vistos:
                vistos.add((n.lineno, n.id))
                errores.append({"linea": n.lineno, "clase": "nombre", "mensaje": f"el nombre '{n.id}' no existe"})
    funciones = {n.name: n for n in arbol.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    for n in ast.walk(arbol):
        if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in funciones):
            continue
        if any(isinstance(a, ast.Starred) for a in n.args) or any(k.arg is None for k in n.keywords):
            continue
        a = funciones[n.func.id].args
        posicionales = [x.arg for x in a.posonlyargs + a.args]
        obligatorios = len(posicionales) - len(a.defaults)
        dados = len(n.args) + sum(1 for k in n.keywords if k.arg in posicionales)
        if (not a.vararg and len(n.args) > len(posicionales)) or dados < obligatorios:
            errores.append({"linea": n.lineno, "clase": "argumentos",
                            "mensaje": f"'{n.func.id}' recibe {len(n.args) + len(n.keywords)} argumentos y espera "
                                       f"{obligatorios}" + (f"–{len(posicionales)}" if a.defaults else "")})
    return sorted(errores, key=lambda e: e["linea"])


def javac() -> str | None:
    """El compilador: EQUIPO_JAVAC, el JDK portátil de externos/ o el del PATH."""
    if os.environ.get("EQUIPO_JAVAC") and Path(os.environ["EQUIPO_JAVAC"]).is_file():
        return os.environ["EQUIPO_JAVAC"]
    for raiz in Path(__file__).resolve().parents:
        cand = sorted((raiz / "externos" / "jdk_temurin_21").glob("jdk-*/bin/javac*"))
        if cand:
            return str(cand[0])
    return shutil.which("javac")


_JAVAC_LINEA = re.compile(r"^.*?\.java:(\d+): error: (.*)$")


def _clase_java(msg: str) -> str:
    m = msg.lower()
    if "expected" in m or "illegal start" in m or "reached end of file" in m or "not a statement" in m:
        return "sintaxis"
    if "incompatible types" in m or "lossy conversion" in m:
        return "tipos"
    if "cannot be applied" in m or "no suitable method" in m or "actual and formal argument" in m:
        return "argumentos"
    if "cannot find symbol" in m:
        return "simbolo"
    return "otro"


def revisar_java(codigo: str, archivo: str) -> list:
    exe = javac()
    if not exe:
        raise RuntimeError("no hay javac: instala un JDK o define EQUIPO_JAVAC (ver lab_flujos/JDK_EXTERNO.md)")
    with tempfile.TemporaryDirectory(prefix="revision_java_") as d:
        f = Path(d) / archivo
        f.write_bytes(codigo.encode("utf-8"))              # sin BOM
        r = subprocess.run([exe, "-encoding", "UTF-8", "-Xmaxerrs", "100", "-d", str(Path(d) / "out"), str(f)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    errores = []
    for l in (r.stdout + r.stderr).splitlines():
        m = _JAVAC_LINEA.match(l)
        if m:
            errores.append({"linea": int(m.group(1)), "clase": _clase_java(m.group(2)), "mensaje": m.group(2).strip()})
    if r.returncode and not errores:
        errores.append({"linea": None, "clase": "otro", "mensaje": (r.stdout + r.stderr).strip()[:200]})
    return errores


def revisar(lenguaje: str, codigo: str, archivo: str) -> list:
    return revisar_python(codigo) if lenguaje == "python" else revisar_java(codigo, archivo)
