"""Flujo de IDENTIDAD (tanda 5): que el cerebro no conteste con el dato de una función parecida.

Medido en la tanda 4: con preguntas parafraseadas, los 17 fallos fueron el dato de una función VECINA que sí estaba
en el contexto. El cerebro no inventaba números: confundía de qué función se hablaba. Pasos:

1. Claves: las de la pregunta que ya existen en los nombres del proyecto, más las que proponga el cerebro y existan
   (lector tolerante, comprobación sin IA).
2. Candidatos (sin IA): TODAS las funciones y constantes cuyo nombre contiene alguna clave, ordenadas por cuántas
   contiene. Solo nombres: caben decenas en poco contexto.
3. Elección: el cerebro elige la que corresponde a la descripción o «NINGUNA». Solo vale un nombre de la lista.
4. Código exacto: Contexto Ligero `bundle --require` de la elegida (con lo que llama), o la línea de la constante.
5. Respuesta citando «FUNCION_USADA»; comprobación sin IA: la función citada es la elegida o una que esta llama, y
   el valor está escrito literalmente en su código. Si no, la respuesta se descarta («NO_ENCONTRADO»).

Límite conocido: si el cerebro ELIGE una vecina, el valor de la vecina sí está en su código y pasa la comprobación
literal. Lo único que frena esa confusión es el paso 3; por eso se mide aparte («elegida correcta»).
"""
from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from pathlib import Path

import expansion as X

MAX_CANDIDATOS = 60
ELEGIR = (
    "Te doy una descripción y una lista de nombres de funciones y constantes de un proyecto de Python en español "
    "(formato «modulo.nombre»). Elige el ÚNICO nombre que corresponde EXACTAMENTE a lo descrito: compara el verbo, "
    "el objeto y el matiz (por ejemplo «hacia el extranjero» = internacional, no nacional). Si ninguno corresponde de "
    "verdad, elige NINGUNA: es mejor que equivocarse. Contesta con una línea «ELEGIDA: modulo.nombre» (o «ELEGIDA: "
    "NINGUNA») y termina con «RESPUESTA: LISTO».")
ELEGIR_JAVA = ELEGIR.replace("funciones y constantes de un proyecto de Python", "métodos y constantes de un proyecto de Java").replace("«modulo.nombre»", "«Clase.nombre»")
CITAR = ("Antes de la última línea, escribe una línea «FUNCION_USADA: nombre» con el nombre de la función o constante "
         "de la que sacas el dato.")


def catalogo(paquete: Path, prefijo: str) -> list:
    """Funciones y constantes de módulo del paquete: nombre, tipo, módulo, ruta (desde la raíz del índice) y palabras."""
    out = []
    for f in sorted(Path(paquete).glob("*.py")):
        arbol = ast.parse(f.read_text(encoding="utf-8"))
        for n in arbol.body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                out.append({"nombre": n.name, "tipo": "def", "modulo": f.stem, "ruta": f"{prefijo}/{f.name}",
                            "linea": n.lineno, "fin": n.end_lineno})
            elif isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
                out.append({"nombre": n.targets[0].id, "tipo": "const", "modulo": f.stem, "ruta": f"{prefijo}/{f.name}",
                            "linea": n.lineno, "fin": n.end_lineno})
    for e in out:
        e["palabras"] = {X._norm(p) for p in e["nombre"].split("_") if len(p) >= 3}
    return out


def palabras_java(nombre: str) -> set:
    """calcularRecargoUrgente / LIMITE_LOTE_URGENTE -> {calcular, recargo, urgente} / {limite, lote, urgente}"""
    trozos = re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+", nombre)
    return {X._norm(p) for p in trozos if len(p) >= 3 and not p.isdigit()}


def catalogo_java(paquete: Path, prefijo: str) -> list:
    """Métodos y constantes de los .java del paquete, con el analizador de Java de Contexto Ligero (sin compilador)."""
    import sys as _sys
    cl = Path(__file__).resolve().parents[2] / "fuentes" / "contexto_ligero_v35"
    if str(cl) not in _sys.path:
        _sys.path.insert(0, str(cl))
    from contexto_core.index import _java_metadata
    out = []
    for f in sorted(Path(paquete).glob("*.java")):
        for s in _java_metadata(f.read_bytes())[0]:
            if s.get("kind") not in ("FunctionDef", "Assign") or "#" in s["name"]:
                continue
            simple = s["name"].split(".")[-1]
            if simple == f.stem:                          # constructor
                continue
            out.append({"nombre": simple, "simbolo": s["name"], "tipo": "def" if s["kind"] == "FunctionDef" else
                        "const", "modulo": f.stem, "ruta": f"{prefijo}/{f.name}", "linea": s["line"], "fin": s["end"],
                        "palabras": palabras_java(simple)})
    return out


def claves_de_pregunta(pregunta: str, voc: set) -> list:
    return sorted({p for p in (X._norm(w) for w in re.findall(r"[A-Za-zÁÉÍÓÚáéíóúñÑüÜ_]+", pregunta)) if p in voc
                   and len(p) >= 4})


def candidatos(cat: list, claves: list, modulo_nombrado: str | None = None) -> list:
    cl = set(claves)
    puntuados = []
    for e in cat:
        n = len(e["palabras"] & cl) + (2 if modulo_nombrado and e["modulo"] == modulo_nombrado else 0)
        if n:
            puntuados.append((-n, e["modulo"], e["nombre"], e))
    puntuados.sort(key=lambda x: x[:3])
    return [x[3] for x in puntuados[:MAX_CANDIDATOS]]


def leer_eleccion(texto: str, cands: list):
    m = re.findall(r"ELEGIDA:\s*`?([\w.]+)`?", texto or "")
    if not m:
        return None, "sin_eleccion"
    elegido = m[-1]
    if elegido.upper() == "NINGUNA":
        return None, "ninguna"
    for e in cands:
        if elegido in (f"{e['modulo']}.{e['nombre']}", e["nombre"]):
            return e, "ok"
    return None, "fuera_de_la_lista"                         # un nombre que no estaba: no se acepta


def codigo_exacto(e: dict, raiz: Path, db: Path, cl_script: Path) -> str:
    if e["tipo"] == "const":
        lineas = (Path(raiz) / e["ruta"]).read_text(encoding="utf-8").splitlines()
        return f"# ===== {e['ruta']} =====\n" + "\n".join(lineas[e["linea"] - 1:e["fin"]])
    r = subprocess.run([sys.executable, "-B", "-X", "utf8", str(cl_script), "--db", str(db), "bundle", str(raiz),
                        e["nombre"], "--require", f"{e['ruta']}::{e.get('simbolo', e['nombre'])}", "--budget", "2600",
                        "--allow-partial", "--json"], capture_output=True, text=True, encoding="utf-8")
    if r.returncode:
        lineas = (Path(raiz) / e["ruta"]).read_text(encoding="utf-8").splitlines()
        return f"# ===== {e['ruta']} =====\n" + "\n".join(lineas[e["linea"] - 1:e["fin"]])
    return json.loads(r.stdout)["text"]


def _cuerpo(ctx: str, nombre: str) -> str | None:
    m = re.search(rf"def {re.escape(nombre)}\(.*?(?=\ndef |\n# =====|\n```|\Z)", ctx, re.S)
    if m:
        return m.group(0)
    m = re.search(rf"\b{re.escape(nombre)}\s*\([^;{{}}]*\)[^;{{}}]*\{{", ctx)      # método Java: hasta su llave
    if m:
        nivel, k = 0, m.end() - 1
        while k < len(ctx):
            nivel += {"{": 1, "}": -1}.get(ctx[k], 0)
            if nivel == 0:
                return ctx[m.start():k + 1]
            k += 1
        return ctx[m.start():]
    m = re.search(rf"^\s*(?:L\d+:\s*)?(?:[\w<>\[\],.\s]*\s)?{re.escape(nombre)}\s*=.*$", ctx, re.M)
    return m.group(0) if m else None


def comprobar(texto: str, valor, elegido: dict, ctx: str) -> tuple:
    """(válida, motivo). La función citada debe ser la elegida o una que esta llama, y el valor estar en su código."""
    if valor is None or "NO_ENCONTRADO" in str(valor).upper().replace(" ", "_"):
        return True, "no_encontrado"
    citadas = re.findall(r"FUNCION_USADA:\s*`?([\w.]+)`?", texto or "")
    if not citadas:
        return False, "sin_cita"
    usada = citadas[-1].split(".")[-1]
    propio = _cuerpo(ctx, elegido["nombre"]) or ""
    if usada != elegido["nombre"] and not re.search(rf"\b{re.escape(usada)}\(", propio):
        return False, "cita_otra_funcion"
    cuerpo = _cuerpo(ctx, usada)
    num = re.search(r"-?\d+", str(valor))
    if not cuerpo or not num or not re.search(rf"(?<![\d.]){re.escape(num.group())}(?![\d.])", cuerpo):
        return False, "valor_no_esta_en_la_funcion_citada"
    return True, "verificada"
