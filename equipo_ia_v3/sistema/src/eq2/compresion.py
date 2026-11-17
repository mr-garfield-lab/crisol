"""V2-D: compresión EXTRACTIVA y determinista del historial (no la hace el modelo).

Se conservan íntegras las líneas ESENCIALES; las demás se descartan en orden inverso de
prioridad (se quitan primero las del medio) y cada hueco se marca con «[…]». Nunca se corta una
línea por la mitad. Si las esenciales no caben, se informa (`completo=False`): nunca en silencio.

Esencial:
  * todo bloque de código ``` (incluidas las vallas);
  * líneas OBJECION / EVIDENCIA / FALTA / ACEPTADA / REBATIDA / SIN OBJECIONES;
  * casos de prueba: líneas con 'assert', 'entrada', 'salida', 'caso de prueba', '->', '=>'.
"""
from __future__ import annotations

import re
import unicodedata

HUECO = "[…]"
_FENCE = re.compile(r"^\s*```")
_CLAVE = re.compile(
    r"^\s*[-*]?\s*(objecion|evidencia|falta|aceptada|rebatida|sin objeciones|caso de prueba|"
    r"prueba|entrada|salida|requisito)\b|\bassert\b|->|=>", re.IGNORECASE)


def _plano(t: str) -> str:
    t = unicodedata.normalize("NFKD", t)
    return "".join(c for c in t if not unicodedata.combining(c))


def esenciales(lineas) -> list:
    """Lista de booleanos: True si la línea es esencial."""
    marca, dentro = [], False
    for l in lineas:
        if _FENCE.match(l):
            marca.append(True)
            dentro = not dentro
            continue
        marca.append(dentro or bool(_CLAVE.search(_plano(l))))
    return marca


def comprimir(texto, cap: int) -> dict:
    """{texto, comprimido, completo, lineas_descartadas, esenciales_descartadas, chars_original}."""
    texto = texto if isinstance(texto, str) else ""
    base = {"texto": texto, "comprimido": False, "completo": True, "lineas_descartadas": 0,
            "esenciales_descartadas": 0, "chars_original": len(texto), "chars_conservados": len(texto),
            "lineas_partidas": 0, "esenciales_no_caben": False}
    if len(texto) <= cap:
        return base
    lineas = texto.split("\n")
    es = esenciales(lineas)
    n = len(lineas)
    keep = [es[i] for i in range(n)]
    partidas = 0

    def coste(k):
        total, hueco = 0, False
        for i in range(n):
            if k[i]:
                total += len(lineas[i]) + 1
                hueco = False
            elif not hueco:
                total += len(HUECO) + 1
                hueco = True
        return total

    if coste(keep) > cap:
        # Ni siquiera las esenciales caben: se conservan las primeras que quepan, ENTERAS.
        keep = [False] * n
        for i in range(n):
            if es[i]:
                keep[i] = True
                if coste(keep) > cap:
                    keep[i] = False
                    break
        comp = True
    else:
        # Añadir líneas no esenciales: primero las del principio y las del final.
        orden = sorted((i for i in range(n) if not es[i]),
                       key=lambda i: min(i, n - 1 - i))
        for i in orden:
            keep[i] = True
            if coste(keep) > cap:
                keep[i] = False
        comp = False
        # Si sobra espacio, la primera línea descartada entra como PREFIJO (con «…»), para que
        # un texto de una sola línea larga no quede reducido a «[…]».
        resto = cap - coste(keep)
        primera = next((i for i in range(n) if not keep[i]), None)
        if primera is not None and resto > 40:
            lineas = list(lineas)
            lineas[primera] = lineas[primera][:resto - len(HUECO) - 3].rstrip() + "…"
            keep[primera] = True
            partidas = 1
            if coste(keep) > cap:
                keep[primera] = False
                partidas = 0
    salida, hueco = [], False
    for i in range(n):
        if keep[i]:
            salida.append(lineas[i])
            hueco = False
        elif not hueco:
            salida.append(HUECO)
            hueco = True
    perdidas_es = sum(1 for i in range(n) if es[i] and not keep[i])
    conservado = sum(len(lineas[i]) for i in range(n) if keep[i])
    return {"texto": "\n".join(salida), "comprimido": True, "completo": perdidas_es == 0,
            "lineas_descartadas": sum(1 for i in range(n) if not keep[i]),
            "esenciales_descartadas": perdidas_es, "chars_original": len(texto),
            "chars_conservados": conservado, "lineas_partidas": partidas,
            "esenciales_no_caben": comp}
