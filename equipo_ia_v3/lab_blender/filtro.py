"""Filtro estático para scripts de Blender escritos por cerebros (laboratorio). No ejecuta nada: solo lee el texto.

    python -B -X utf8 lab_blender/filtro.py SCRIPT.py

Un script pasa solo si TODO lo que usa está en una lista de permitidos (lista blanca): módulos, funciones integradas y grupos
de operadores de Blender. Lo que no se puede comprobar leyendo el código (acceso a atributos por texto, alias de `bpy.ops`,
clases, decoradores) se rechaza. El filtro reduce mucho el riesgo, pero NO es un aislamiento perfecto: el ejecutor añade
límites de tiempo y memoria, Blender arranca de fábrica, sin scripts automáticos y sin red, y solo trabaja sobre copias.
El mismo filtro se vuelve a pasar DENTRO de Blender justo antes de ejecutar.
"""
from __future__ import annotations

import ast
import re
import sys

MAX_BYTES = 60_000
MAX_LINEAS = 1500
MAX_NODOS = 40_000

MODULOS = {"bpy", "bmesh", "mathutils", "math", "random"}
DESDE = {"mathutils", "math", "random"}                      # «from X import y» solo de estos (nunca «from bpy import …»)
INTEGRADAS = {
    "abs", "all", "any", "bool", "callable", "chr", "dict", "divmod", "enumerate", "filter", "float", "format",
    "frozenset", "hasattr", "int", "isinstance", "iter", "len", "list", "map", "max", "min", "next", "ord", "pow", "print",
    "range", "repr", "reversed", "round", "set", "slice", "sorted", "str", "sum", "tuple", "zip",
    "ArithmeticError", "AssertionError", "AttributeError", "Exception", "IndexError", "KeyError", "LookupError",
    "NameError", "NotImplementedError", "ReferenceError", "RuntimeError", "StopIteration", "TypeError", "ValueError",
    "ZeroDivisionError"}
# grupos de bpy.ops permitidos (crear y editar geometría, objetos, materiales, huesos y animación)
OPS = {"mesh", "object", "transform", "material", "curve", "surface", "armature", "pose", "anim", "collection", "uv",
       "geometry", "constraint"}
OP_PROHIBIDO = re.compile(r"bake|external|import|export|load|save|cache|script|python|link_|append|asset|library|"
                          r"image|sound|movie|volume|simulation|quadriflow", re.I)
# atributos que no se tocan (da igual sobre qué objeto): archivos, código, preferencias, registro de clases, red
ATRIBUTOS = {
    "app", "utils", "types", "props", "msgbus", "path", "preferences", "window_manager", "libraries", "texts", "load",
    "save", "save_render", "save_as", "write", "pack", "unpack", "pack_all", "unpack_all", "reload", "as_module",
    "as_string", "from_string", "driver_add", "driver_remove", "driver_namespace", "driver", "drivers", "expression",
    "handlers", "timers", "register_class", "unregister_class", "execfile", "user_resource", "system_resource",
    "script_paths", "filepath_from_user", "movieclips", "sounds", "fonts", "cache_files", "workspaces", "screens",
    "addons", "open_mainfile", "save_mainfile", "quit_blender", "sequence_editor", "sequence_editor_create",
    "freestyle_settings"}
# los ajustes de render (scene.render.fps, resolución…) sí se pueden tocar: el ejecutor fija la ruta y renderiza él
RUTA = re.compile(r"filepath|directory|filename|blendfile|relative_path|cache_dir|disk_cache|use_external", re.I)
# marcos de ejecución, generadores y código: por ahí se llega a los módulos reales de quien ejecuta el script
INTROSPECCION = re.compile(r"^(?:gi|cr|ag|tb)_|^f_(?:back|globals|locals|builtins|code|trace|lineno|lasti)$|"
                           r"^co_(?:code|consts|names|varnames|filename|name|cellvars|freevars|qualname)$|^func_|"
                           r"^with_traceback$")
CLAVES_RUTA = {"path", "files", "file", "dirname", "library", "check_existing"}
CLAVES_OK = {"data_path"}                                   # keyframe_insert(data_path=…) es animación, no un archivo
CADENA_SOSPECHOSA = re.compile(r"__|\\\\|^[A-Za-z]:[\\/]|^/(?:etc|usr|home|tmp|var)/|\.\.[\\/]")
# modificadores que escriben cachés en disco al avanzar fotogramas
CADENAS_PROHIBIDAS = {"FLUID", "OCEAN", "DYNAMIC_PAINT", "MESH_SEQUENCE_CACHE"}
NODOS_PROHIBIDOS = (ast.ClassDef, ast.AsyncFunctionDef, ast.AsyncFor, ast.AsyncWith, ast.Await)


def _padres(arbol) -> dict:
    """id(nodo) -> nodo padre."""
    return {id(h): n for n in ast.walk(arbol) for h in ast.iter_child_nodes(n)}


def _linea(motivo: str) -> int:
    m = re.match(r"línea (\d+)", motivo)
    return int(m.group(1)) if m else 0


def revisar(texto: str) -> list:
    """Motivos de rechazo (lista vacía = el script pasa). Cada motivo lleva la línea."""
    M = []
    crudo = texto.encode("utf-8", errors="replace")
    if len(crudo) > MAX_BYTES:
        return [f"el script mide {len(crudo)} bytes (máximo {MAX_BYTES})"]
    if "\x00" in texto:
        return ["el script contiene bytes nulos"]
    if texto.count("\n") + 1 > MAX_LINEAS:
        return [f"el script tiene más de {MAX_LINEAS} líneas"]
    try:
        arbol = ast.parse(texto, filename="script_cerebro.py", mode="exec")
    except (SyntaxError, ValueError, RecursionError, MemoryError) as e:
        return [f"no es Python válido: {type(e).__name__}: {e}"]
    nodos, padres = list(ast.walk(arbol)), _padres(arbol)
    if len(nodos) > MAX_NODOS:
        return [f"el script es demasiado complejo ({len(nodos)} nodos; máximo {MAX_NODOS})"]
    no = lambda nodo, motivo: M.append(f"línea {getattr(nodo, 'lineno', '?')}: {motivo}")

    # 1) importaciones y alias de módulo
    alias = {}                                              # nombre local -> módulo
    for n in nodos:
        if isinstance(n, ast.Import):
            for a in n.names:
                if a.name not in MODULOS:
                    no(n, f"importa «{a.name}» (solo se permite {', '.join(sorted(MODULOS))})")
                else:
                    alias[a.asname or a.name] = a.name
        elif isinstance(n, ast.ImportFrom):
            if n.level or n.module not in DESDE:
                no(n, f"«from {n.module or '.'} import …» no está permitido (solo desde {', '.join(sorted(DESDE))})")
            elif any(a.name == "*" for a in n.names):
                no(n, "«import *» no está permitido")

    # 2) nombres ligados por el propio script
    ligados = set(alias)
    for n in nodos:
        if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            ligados.add(n.id)
            if n.id in alias:
                no(n, f"reasigna el módulo «{n.id}»")
        elif isinstance(n, (ast.FunctionDef, ast.Lambda)):
            ar = n.args
            for a in ar.posonlyargs + ar.args + ar.kwonlyargs + [x for x in (ar.vararg, ar.kwarg) if x]:
                ligados.add(a.arg)
                if a.arg in alias:
                    no(n, f"usa el nombre de módulo «{a.arg}» como parámetro")
            if isinstance(n, ast.FunctionDef):
                ligados.add(n.name)
                if n.name in alias:
                    no(n, f"define una función con el nombre de módulo «{n.name}»")
                if n.decorator_list:
                    no(n, "usa decoradores")
        elif isinstance(n, ast.ImportFrom):
            for a in n.names:
                ligados.add(a.asname or a.name)
                if (a.asname or a.name) in alias:
                    no(n, f"reasigna el módulo «{a.asname or a.name}»")
        elif isinstance(n, ast.ExceptHandler) and n.name:
            ligados.add(n.name)
        elif isinstance(n, (ast.Global, ast.Nonlocal)):
            ligados.update(n.names)
        elif isinstance(n, ast.MatchAs) and n.name:
            ligados.add(n.name)
        elif isinstance(n, (ast.MatchStar, ast.MatchMapping)):
            nombre = getattr(n, "name", None) or getattr(n, "rest", None)
            if nombre:
                ligados.add(nombre)

    # 3) cada nodo
    for n in nodos:
        if isinstance(n, NODOS_PROHIBIDOS):
            no(n, f"usa {type(n).__name__} (clases y código asíncrono no están permitidos)")
        elif isinstance(n, ast.Name):
            if n.id.startswith("__") and not (n.id == "__name__" and isinstance(n.ctx, ast.Load)):
                no(n, f"usa el nombre interno «{n.id}»")
            elif isinstance(n.ctx, ast.Load) and n.id not in ligados and n.id not in INTEGRADAS and n.id != "__name__":
                no(n, f"usa «{n.id}», que no está en la lista de funciones permitidas")
        elif isinstance(n, ast.Attribute):
            if n.attr.startswith("_"):
                no(n, f"accede al atributo interno «{n.attr}»")
            elif n.attr in ATRIBUTOS:
                no(n, f"usa «.{n.attr}», que no está permitido")
            elif INTROSPECCION.search(n.attr):
                no(n, f"usa «.{n.attr}» (acceso a los marcos de ejecución)")
            elif isinstance(n.ctx, (ast.Store, ast.Del)) and RUTA.search(n.attr):
                no(n, f"escribe en «.{n.attr}» (rutas de archivo)")
            elif isinstance(n.ctx, (ast.Store, ast.Del)) and isinstance(n.value, ast.Name) and n.value.id in alias:
                no(n, f"modifica el módulo «{n.value.id}» (cambiaría las funciones con las que se mide el resultado)")
            elif n.attr == "ops":
                base = alias.get(n.value.id) if isinstance(n.value, ast.Name) else None
                padre = padres.get(id(n))
                if base == "bmesh":
                    pass                                    # bmesh.ops trabaja solo en memoria
                elif base != "bpy":
                    no(n, "usa «.ops» sobre algo que no es directamente el módulo bpy")
                elif not (isinstance(padre, ast.Attribute) and padre.value is n):
                    no(n, "guarda o pasa «bpy.ops» en vez de llamar a un operador directamente")
                elif padre.attr not in OPS:
                    no(n, f"usa bpy.ops.{padre.attr} (grupos permitidos: {', '.join(sorted(OPS))})")
                else:
                    op = padres.get(id(padre))
                    if not (isinstance(op, ast.Attribute) and op.value is padre):
                        no(n, f"guarda o pasa «bpy.ops.{padre.attr}» en vez de llamar a un operador directamente")
                    elif OP_PROHIBIDO.search(op.attr):
                        no(n, f"usa el operador bpy.ops.{padre.attr}.{op.attr}, que no está permitido")
        elif isinstance(n, ast.Call):
            for k in n.keywords:
                if k.arg is None:
                    no(n, "pasa argumentos con ** (no se puede comprobar qué claves lleva)")
                elif k.arg not in CLAVES_OK and (RUTA.search(k.arg) or k.arg in CLAVES_RUTA):
                    no(n, f"pasa el argumento «{k.arg}» (rutas de archivo)")
        elif isinstance(n, ast.Constant) and isinstance(n.value, str):
            if n.value == "__main__":
                pass                                        # «if __name__ == "__main__":» es habitual e inofensivo
            elif CADENA_SOSPECHOSA.search(n.value):
                no(n, "contiene un texto con «__», «..» o una ruta absoluta")
            elif n.value.strip().upper() in CADENAS_PROHIBIDAS:
                no(n, f"usa «{n.value}» (simulaciones y cachés que escriben en disco)")
        elif isinstance(n, ast.Constant) and isinstance(n.value, bytes):
            no(n, "contiene un literal de bytes")
    return sorted(set(M), key=lambda m: (_linea(m), m))


def pasa(texto: str) -> bool:
    return not revisar(texto)


if __name__ == "__main__":
    motivos = revisar(open(sys.argv[1], encoding="utf-8").read())
    print("PASA" if not motivos else "RECHAZADO\n" + "\n".join(motivos))
    sys.exit(1 if motivos else 0)
