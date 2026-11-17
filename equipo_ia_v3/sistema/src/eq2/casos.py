"""V2-F: CASOS LITERALES ejecutables. Base común del debate por evidencias, de los contraejemplos de A3 y del
banco comparativo.

Formato (una línea por caso; el texto de un agente es NO CONFIABLE):
    CASO: nombre(<literales>) == <literal>
    CASO: nombre(<literales>) lanza <Excepcion>
    CASO K3: ...                       (identificador opcional; lo asigna el controlador)

Por qué solo literales: el texto del agente NUNCA se convierte en código. Del caso solo se aceptan un
identificador de función y valores que `ast.literal_eval` puede leer (números, cadenas, listas, tuplas,
diccionarios, conjuntos, booleanos, None). La prueba que se ejecuta la escribe el CONTROLADOR con `repr()` de
esos valores ya leídos, así que una cadena del agente no puede inyectar instrucciones en el archivo de prueba.

Fuentes de un caso (deciden su peso en la adjudicación, ver debate.py):
    usuario     escrito por el usuario en la tarea (campo «casos»): ORÁCULO
    enunciado   ejemplo literal del texto de la tarea («f(x) == y» o «f(x) -> y»): ORÁCULO
    propiedad   comprobación genérica declarada por el usuario (no_muta_argumentos, determinista)
    A1/A2/A3    propuesto por un agente: HIPÓTESIS hasta que la evidencia lo resuelva
Módulo puro: no escribe archivos ni ejecuta nada (la ejecución la hace herramientas.py con el ejecutor
restringido).
"""
from __future__ import annotations

import ast
import keyword
import re
from dataclasses import dataclass, field

MAX_CASOS = 12                       # por fuente y llamada
MAX_CHARS_CASO = 500
MAX_REPR = 400
FUENTES = ("usuario", "enunciado", "propiedad", "A1", "A2", "A3")
FUENTES_ORACULO = ("usuario", "enunciado", "propiedad")
EXCEPCIONES = ("ValueError", "TypeError", "KeyError", "IndexError", "ZeroDivisionError", "LookupError",
               "ArithmeticError", "RuntimeError", "OverflowError")
PROPIEDADES = ("no_muta_argumentos", "determinista")
_NOMBRES_RESERVADOS = {"print", "open", "exec", "eval", "compile", "input", "getattr", "setattr", "delattr",
                       "globals", "locals", "vars", "help", "exit", "quit", "breakpoint", "memoryview",
                       "type", "object", "super", "repr", "isinstance", "len", "range", "copy"}
_LINEA = re.compile(r"^[ \t]*[-*]?[ \t]*(?:\*\*)?CASO(?:[ \t]+([A-Za-z0-9_-]{1,12}))?(?:\*\*)?[ \t]*:[ \t]*(.+?)[ \t]*$",
                    re.IGNORECASE | re.MULTILINE)
_LANZA = re.compile(r"^(.*\))\s*(?:lanza|raises)\s+([A-Za-z]{3,30})\s*\.?\s*$", re.IGNORECASE)
_FLECHA = re.compile(r"\s*(?:==|->|=>|→)\s*")
_NOMBRE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,40}")


class CasoInvalido(ValueError):
    """El caso no cumple el formato literal (motivo en el mensaje)."""


@dataclass(frozen=True)
class Caso:
    id: str
    funcion: str
    args: tuple
    kwargs: tuple                      # ((clave, valor), ...) ordenado: hashable e inmutable
    esperado: object = None
    excepcion: str | None = None
    fuente: str = "A1"
    texto: str = ""
    extra: dict = field(default_factory=dict, compare=False, hash=False)

    @property
    def es_oraculo(self) -> bool:
        return self.fuente in FUENTES_ORACULO

    def llamada(self) -> str:
        partes = [repr(a) for a in self.args] + [f"{k}={v!r}" for k, v in self.kwargs]
        return f"{self.funcion}({', '.join(partes)})"

    def clave(self) -> str:
        """Forma canónica (para deduplicar y comparar casos de fuentes distintas)."""
        return self.llamada() + (f" lanza {self.excepcion}" if self.excepcion else f" == {self.esperado!r}")

    def entrada(self) -> str:
        return self.llamada()

    def a_dict(self) -> dict:
        return {"id": self.id, "funcion": self.funcion, "caso": self.clave(), "fuente": self.fuente,
                "oraculo": self.es_oraculo, "texto_original": self.texto[:200]}


def _literal(nodo, que):
    try:
        v = ast.literal_eval(nodo)
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError) as e:
        raise CasoInvalido(f"{que} no es un literal: {type(e).__name__}")
    if len(repr(v)) > MAX_REPR:
        raise CasoInvalido(f"{que} demasiado grande")
    return v


def nombre_funcion_valido(nombre) -> bool:
    return (isinstance(nombre, str) and bool(_NOMBRE.fullmatch(nombre)) and not nombre.startswith("_")
            and not keyword.iskeyword(nombre) and nombre not in _NOMBRES_RESERVADOS and not nombre.startswith("test"))


def parsear_expresion(expr: str, fuente="A1", ident="") -> Caso:
    """Un caso a partir de «f(args) == valor», «f(args) -> valor» o «f(args) lanza Excepcion»."""
    if not isinstance(expr, str) or not expr.strip():
        raise CasoInvalido("caso vacío")
    if len(expr) > MAX_CHARS_CASO:
        raise CasoInvalido("caso demasiado largo")
    if fuente not in FUENTES:
        raise CasoInvalido("fuente desconocida")
    t = expr.strip().strip("`").strip()
    exc = None
    m = _LANZA.match(t)
    if m:
        t, exc = m.group(1).strip(), m.group(2)
        if exc not in EXCEPCIONES:
            raise CasoInvalido(f"excepción no admitida: {exc[:30]} (admitidas: {', '.join(EXCEPCIONES)})")
        izq_txt, der_txt = t, None
    else:
        # separar por el PRIMER operador fuera de paréntesis/corchetes/comillas
        izq_txt, der_txt = _partir(t)
        if der_txt is None:
            raise CasoInvalido("falta «== valor», «-> valor» o «lanza Excepcion»")
        der_txt = der_txt.strip().rstrip(".,;").strip()
    try:
        llamada = ast.parse(izq_txt.strip(), mode="eval").body
    except (SyntaxError, ValueError, MemoryError, RecursionError):
        raise CasoInvalido("la llamada no es una expresión válida")
    if not isinstance(llamada, ast.Call) or not isinstance(llamada.func, ast.Name):
        raise CasoInvalido("la parte izquierda debe ser una llamada «funcion(...)»")
    nombre = llamada.func.id
    if not nombre_funcion_valido(nombre):
        raise CasoInvalido(f"nombre de función no admitido: {nombre[:40]}")
    if any(isinstance(a, ast.Starred) for a in llamada.args) or any(k.arg is None for k in llamada.keywords):
        raise CasoInvalido("no se admiten *args ni **kwargs")
    args = tuple(_literal(a, "argumento") for a in llamada.args)
    kw = []
    for k in llamada.keywords:
        if not _NOMBRE.fullmatch(k.arg) or k.arg.startswith("_"):
            raise CasoInvalido("nombre de argumento no admitido")
        kw.append((k.arg, _literal(k.value, "argumento")))
    esperado = None
    if exc is None:
        try:
            nodo = ast.parse(der_txt, mode="eval").body
        except (SyntaxError, ValueError, MemoryError, RecursionError):
            raise CasoInvalido("el valor esperado no es un literal")
        esperado = _literal(nodo, "valor esperado")
    return Caso(ident or "", nombre, args, tuple(sorted(kw)), esperado, exc, fuente, expr.strip()[:MAX_CHARS_CASO])


def _partir(t: str):
    """(izquierda, derecha) por el primer ==, ->, => o → que esté fuera de agrupaciones y cadenas."""
    prof, comilla, i = 0, None, 0
    while i < len(t):
        c = t[i]
        if comilla:
            if c == "\\":
                i += 2
                continue
            if c == comilla:
                comilla = None
        elif c in "'\"":
            comilla = c
        elif c in "([{":
            prof += 1
        elif c in ")]}":
            prof -= 1
        elif prof == 0:
            for op in ("==", "->", "=>", "→"):
                if t.startswith(op, i):
                    return t[:i], t[i + len(op):]
        i += 1
    return t, None


def casos_de_texto(texto, fuente, prefijo=None, maximo=MAX_CASOS) -> dict:
    """Líneas «CASO: …» de un texto de agente. {casos: [Caso], rechazados: [{linea, motivo}]}.
    Los inválidos se informan; nunca se corrigen en silencio. Duplicados (forma canónica) se descartan."""
    prefijo = prefijo or fuente
    casos, rechazados, vistos = [], [], set()
    for m in _LINEA.finditer(texto or ""):
        linea = m.group(2)
        if len(casos) >= maximo:
            rechazados.append({"linea": linea[:120], "motivo": f"más de {maximo} casos"})
            continue
        try:
            c = parsear_expresion(linea, fuente, f"{prefijo}-{len(casos) + 1}")
        except CasoInvalido as e:
            rechazados.append({"linea": linea[:120], "motivo": str(e)})
            continue
        if c.clave() in vistos:
            rechazados.append({"linea": linea[:120], "motivo": "duplicado"})
            continue
        vistos.add(c.clave())
        casos.append(c)
    return {"casos": casos, "rechazados": rechazados}


def casos_del_usuario(lista, maximo=MAX_CASOS) -> list:
    """Casos del campo «casos» de una tarea (lista de cadenas). Un caso inválido del usuario es un ERROR de la
    tarea (se lanza CasoInvalido con su posición), no se ignora."""
    if lista is None:
        return []
    if not isinstance(lista, list) or len(lista) > maximo:
        raise CasoInvalido(f"«casos» debe ser una lista de como máximo {maximo} cadenas")
    out, vistos = [], set()
    for i, s in enumerate(lista, 1):
        try:
            c = parsear_expresion(s, "usuario", f"U{i}")
        except CasoInvalido as e:
            raise CasoInvalido(f"caso {i}: {e}")
        if c.clave() not in vistos:
            vistos.add(c.clave())
            out.append(c)
    return out


_INICIO_LLAMADA = re.compile(r"(?<![A-Za-z0-9_.])([A-Za-z_][A-Za-z0-9_]{0,40})\(")


def ejemplos_del_enunciado(texto, maximo=MAX_CASOS) -> list:
    """Ejemplos literales del ENUNCIADO: «f(args) == valor», «f(args) -> valor» o «f(args) lanza X», cada uno
    terminado en fin de línea o «;». Lo que no se pueda leer como literal se ignora (el enunciado no es código)."""
    out, vistos = [], set()
    for linea in (texto or "").replace(";", "\n").split("\n"):
        for m in _INICIO_LLAMADA.finditer(linea):
            if len(out) >= maximo:
                return out
            ini = m.start(1)
            fin = _cierre(linea, m.end() - 1)
            if fin is None:
                continue
            resto = linea[fin + 1:]
            mo = re.match(r"\s*(==|->|=>|→|lanza\s|raises\s)", resto, re.IGNORECASE)
            if not mo:
                continue
            candidato = linea[ini:].strip()
            # el valor llega hasta el final de la línea; se recorta lo que sigue a un punto final
            for corte in _cortes(candidato):
                try:
                    c = parsear_expresion(corte, "enunciado", f"E{len(out) + 1}")
                except CasoInvalido:
                    continue
                if c.clave() not in vistos:
                    vistos.add(c.clave())
                    out.append(c)
                break
    return out


def _cierre(linea, abre):
    prof, comilla, i = 0, None, abre
    while i < len(linea):
        c = linea[i]
        if comilla:
            if c == "\\":
                i += 2
                continue
            if c == comilla:
                comilla = None
        elif c in "'\"":
            comilla = c
        elif c in "([{":
            prof += 1
        elif c in ")]}":
            prof -= 1
            if prof == 0:
                return i
        i += 1
    return None


def _cortes(candidato):
    yield candidato
    for sep in (". ", ", y ", " y ", ", "):
        k = candidato.rfind(sep)
        while k > 0:
            yield candidato[:k]
            k = candidato.rfind(sep, 0, k)


def con_ids(casos, prefijo) -> list:
    """Reasigna identificadores estables (prefijo-1, prefijo-2...) conservando el orden."""
    return [Caso(f"{prefijo}-{i}", c.funcion, c.args, c.kwargs, c.esperado, c.excepcion, c.fuente, c.texto, c.extra)
            for i, c in enumerate(casos, 1)]


# --- generación de pruebas (texto que escribe el CONTROLADOR) ---------------------------------------------------
def nombre_prueba(caso_id: str, prefijo="test_caso") -> str:
    return f"{prefijo}_" + re.sub(r"[^A-Za-z0-9]", "_", caso_id).lower()


def _args_txt(c: Caso) -> str:
    partes = [repr(a) for a in c.args] + [f"{k}={v!r}" for k, v in c.kwargs]
    return ", ".join(partes)


def generar_modulo(casos, modulos: dict, propiedades=(), prefijo="test_caso") -> dict:
    """Texto de un archivo de pruebas para `casos`. `modulos`: {funcion: modulo} (el módulo que la define en el
    espacio). Devuelve {texto, pruebas: {nombre_prueba: {caso, tipo}}, omitidos: [{caso, motivo}]}.
    Propiedades admitidas: no_muta_argumentos, determinista (se aplican a las ENTRADAS de los casos)."""
    for p in propiedades:
        if p not in PROPIEDADES:
            raise CasoInvalido(f"propiedad desconocida: {p}")
    imports, cuerpos, pruebas, omitidos = set(), [], {}, []
    necesita_copy = "no_muta_argumentos" in propiedades
    for c in casos:
        mod = modulos.get(c.funcion)
        if not mod:
            omitidos.append({"caso": c.id, "motivo": f"ninguna versión define {c.funcion}()"})
            continue
        if not (_NOMBRE.fullmatch(mod) and not mod.startswith("_")):
            omitidos.append({"caso": c.id, "motivo": "módulo no válido"})
            continue
        imports.add(f"from {mod} import {c.funcion}")
        n = nombre_prueba(c.id, prefijo)
        if c.excepcion:
            cuerpos.append(
                f"def {n}():\n"
                f"    try:\n"
                f"        obtenido = {c.funcion}({_args_txt(c)})\n"
                f"    except {c.excepcion}:\n"
                f"        return\n"
                f"    except Exception as e:\n"
                f"        raise AssertionError('OBTENIDO=excepcion ' + repr(e)[:200])\n"
                f"    raise AssertionError('OBTENIDO=' + repr(obtenido)[:300])\n")
        else:
            cuerpos.append(
                f"def {n}():\n"
                f"    obtenido = {c.funcion}({_args_txt(c)})\n"
                f"    assert obtenido == {c.esperado!r}, 'OBTENIDO=' + repr(obtenido)[:300]\n")
        pruebas[n] = {"caso": c.id, "tipo": "caso"}
        mutables = [a for a in list(c.args) + [v for _, v in c.kwargs] if isinstance(a, (list, dict, set))]
        if "no_muta_argumentos" in propiedades and mutables:
            np_ = nombre_prueba(c.id, prefijo + "_no_muta")
            cuerpos.append(
                f"def {np_}():\n"
                f"    args = [{', '.join(repr(a) for a in c.args)}]\n"
                f"    kwargs = {dict(c.kwargs)!r}\n"
                f"    antes = copy.deepcopy([args, kwargs])\n"
                f"    try:\n"
                f"        {c.funcion}(*args, **kwargs)\n"
                f"    except Exception:\n"
                f"        pass\n"
                f"    assert [args, kwargs] == antes, 'OBTENIDO=modifico los argumentos: ' + repr([args, kwargs])[:300]\n")
            pruebas[np_] = {"caso": c.id, "tipo": "no_muta_argumentos"}
        if "determinista" in propiedades and not c.excepcion:
            nd = nombre_prueba(c.id, prefijo + "_determinista")
            cuerpos.append(
                f"def {nd}():\n"
                f"    a = {c.funcion}({_args_txt(c)})\n"
                f"    b = {c.funcion}({_args_txt(c)})\n"
                f"    assert a == b, 'OBTENIDO=resultados distintos: ' + repr([a, b])[:300]\n")
            pruebas[nd] = {"caso": c.id, "tipo": "determinista"}
    cab = ["# Archivo GENERADO por el controlador de Equipo IA (V2-F) a partir de casos literales.",
           "# No lo escribe ningún agente: los valores son repr() de literales ya validados."]
    if necesita_copy:
        cab.append("import copy")
    texto = "\n".join(cab + sorted(imports)) + "\n\n\n" + "\n\n".join(cuerpos)
    return {"texto": texto, "pruebas": pruebas, "omitidos": omitidos}


def funciones_definidas(archivos: dict) -> dict:
    """{funcion: modulo} de las funciones de nivel superior de los archivos .py (no test*) del espacio. Si dos
    módulos definen la misma función, se marca como ambigua (no se usa)."""
    out, ambiguas = {}, set()
    for ruta, txt in sorted((archivos or {}).items()):
        nombre = ruta.rsplit("/", 1)[-1]
        if "/" in ruta or not nombre.endswith(".py") or nombre.startswith("test"):
            continue
        try:
            arbol = ast.parse(txt)
        except (SyntaxError, ValueError, MemoryError, RecursionError):
            continue
        for n in arbol.body:
            if isinstance(n, ast.FunctionDef):
                if n.name in out and out[n.name] != nombre[:-3]:
                    ambiguas.add(n.name)
                out[n.name] = nombre[:-3]
    for a in ambiguas:
        out.pop(a, None)
    return out


_BLOQUE = re.compile(r"^(?:FAIL|ERROR):\s*(.*)$", re.MULTILINE)


def obtenidos_de_informe(texto: str) -> dict:
    """{nombre_prueba: 'OBTENIDO=...'} a partir del informe de unittest del corredor (solo las que fallan)."""
    out = {}
    t = texto or ""
    pos = [m.start() for m in _BLOQUE.finditer(t)] + [len(t)]
    for a, b in zip(pos, pos[1:]):
        bloque = t[a:b]
        cab = bloque.split("\n", 2)[:2]
        m = re.search(r"\b(test_[A-Za-z0-9_]+)\b", " ".join(cab))
        if not m:
            continue
        o = re.findall(r"(?:AssertionError|Error):\s*(OBTENIDO=.*)", bloque)
        out[m.group(1)] = (o[-1] if o else "OBTENIDO=desconocido (error sin valor)")[:320]
    return out
