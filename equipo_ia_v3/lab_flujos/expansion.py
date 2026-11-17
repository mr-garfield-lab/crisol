"""Expansión de consulta VERIFICADA (tanda 4 del banco de flujos).

El problema medido: Contexto Ligero busca por coincidencia de texto. Con preguntas parafraseadas («la función que
corrige los kilos de los envíos rápidos» en vez de `ajustar_peso_express`) no encontró la función correcta en
ninguna de 25 preguntas.

La idea: antes de buscar, el cerebro propone palabras clave como las escribiría un programador en un nombre de
función. El cerebro puede proponer cualquier cosa, pero solo se usan las que EXISTEN de verdad en el vocabulario de
nombres del proyecto (comprobación sin IA). Así gana sinónimos sin poder meter en la búsqueda un nombre inventado.
"""
from __future__ import annotations

import ast
import re
import unicodedata
from pathlib import Path

MAX_CLAVES = 10
INSTRUCCION = (
    "Vas a buscar en el código de un proyecto de Python escrito en español. Propón palabras clave tal como aparecerían "
    "DENTRO de nombres de funciones, clases o constantes: verbos en infinitivo (calcular, validar…), sustantivos en "
    "singular, sin tildes ni artículos, y sinónimos técnicos habituales (por ejemplo, para «kilos» propón «peso»; para "
    "«hacia el extranjero», «internacional»). Hasta 10, una por línea, con el formato «CLAVE: palabra». No contestes "
    "la pregunta. Termina con la línea «RESPUESTA: LISTO».")


def _norm(p: str) -> str:
    p = unicodedata.normalize("NFKD", p.casefold())
    return "".join(c for c in p if not unicodedata.combining(c))


def vocabulario(raiz: Path) -> set:
    """Las palabras que aparecen en los nombres de funciones, clases y constantes del proyecto (sin IA)."""
    voc = set()
    for f in sorted(Path(raiz).glob("*.py")):
        for n in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            nombre = getattr(n, "name", None)
            if isinstance(n, ast.Assign):
                nombre = next((t.id for t in n.targets if isinstance(t, ast.Name)), None)
            if isinstance(nombre, str):
                voc.update(_norm(x) for x in nombre.split("_") if len(x) >= 3)
        voc.update(_norm(x) for x in f.stem.split("_") if len(x) >= 3 and not x.isdigit())
    return voc


def mensajes_expansion(pregunta: str, lenguaje: str = "python") -> list:
    instr = INSTRUCCION if lenguaje == "python" else INSTRUCCION.replace("proyecto de Python", "proyecto de Java")
    return [{"role": "system", "content": instr},
            {"role": "user", "content": f"PREGUNTA QUE HAY QUE RESPONDER LUEGO: {pregunta}"}]


def claves(texto: str, voc: set) -> dict:
    """Separa lo propuesto en verificado (existe en el vocabulario) y descartado (no existe)."""
    dichas = []
    # Tolerante (tanda 5): ministral3 escribió «EXTRANJERO: internacional» en vez de «CLAVE: internacional». Se
    # toma lo que va DESPUÉS de los dos puntos en cualquier línea «ALGO: …», y también líneas sueltas «- palabra».
    lineas = re.findall(r"^[\s*\-•\d.)]*[^:\n]{1,40}:\s*([^\n]+)$", texto or "", re.M)
    lineas += re.findall(r"^\s*[-•*]\s*([^\s:]+)\s*$", texto or "", re.M)
    for c in lineas:
        if "LISTO" in c.upper():
            continue
        for parte in re.split(r"[\s_,;/]+", _norm(c.strip().strip("`*«»\"'."))):
            if len(parte) >= 3 and parte not in dichas:
                dichas.append(parte)
    dichas = dichas[:MAX_CLAVES * 2]
    return {"dichas": dichas, "verificadas": [d for d in dichas if d in voc][:MAX_CLAVES],
            "descartadas": [d for d in dichas if d not in voc]}
