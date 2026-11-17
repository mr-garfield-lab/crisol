"""Saneado de texto no confiable y análisis estricto de votos.

La salida del modelo es TEXTO NO CONFIABLE: nunca se ejecuta, nunca se usa
como ruta, SQL ni comando. Aquí solo se limpia, se acota y se envuelve.
"""
from __future__ import annotations

import re
import unicodedata

DELIM_ABRE = "<<<DATOS_NO_CONFIABLES"
DELIM_CIERRA = "DATOS_NO_CONFIABLES>>>"
_ETIQUETA = re.compile(r"[a-z0-9_]{1,24}")
_VOTO = re.compile(
    r"^VOTO:\s*(aprobar_con_cambios|aprobar|rechazar|abstencion)\s*$",
    re.IGNORECASE)
_RAZON = re.compile(r"^RAZON:\s*(.*)$", re.IGNORECASE)


def limpiar(texto, max_chars: int) -> str:
    """Normaliza, quita controles/invisibles, neutraliza delimitadores y acota."""
    if not isinstance(texto, str):
        return ""
    t = unicodedata.normalize("NFC", texto).replace("\r\n", "\n").replace("\r", "\n")
    salida = []
    for ch in t:
        if ch == "\n":
            salida.append(ch)
        elif ch == "\t":
            salida.append(" ")
        else:
            cat = unicodedata.category(ch)
            if cat in ("Cc", "Cf", "Cs", "Co", "Cn"):
                continue
            salida.append(ch)
    t = "".join(salida)
    t = t.replace("<<<", "‹‹‹").replace(">>>", "›››")
    t = re.sub(r"[ ]{2,}", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t).strip()
    return t[:max(0, int(max_chars))]


def limpiar_codigo(texto, max_chars: int) -> str:
    """V2-E.6: como `limpiar` pero CONSERVA espacios e indentación (código y parches como TEXTO; la
    indentación es significativa). Sigue quitando controles/invisibles y neutralizando delimitadores."""
    if not isinstance(texto, str):
        return ""
    t = unicodedata.normalize("NFC", texto).replace("\r\n", "\n").replace("\r", "\n")
    t = "".join(ch if ch == "\n" else "    " if ch == "\t" else ch for ch in t
                if ch in "\n\t" or unicodedata.category(ch) not in ("Cc", "Cf", "Cs", "Co", "Cn"))
    t = t.replace("<<<", "‹‹‹").replace(">>>", "›››")
    t = "\n".join(l.rstrip() for l in t.split("\n")).strip("\n")
    return t[:max(0, int(max_chars))]


def envolver(etiqueta: str, texto, max_chars: int) -> str:
    """Envuelve texto entre delimitadores marcados como datos no confiables."""
    if not isinstance(etiqueta, str) or not _ETIQUETA.fullmatch(etiqueta):
        raise ValueError("etiqueta inválida")
    cuerpo = limpiar(texto, max_chars)
    return f"{DELIM_ABRE} fuente={etiqueta}\n{cuerpo}\n{DELIM_CIERRA}"


def envolver_codigo(etiqueta: str, texto, max_chars: int) -> str:
    """V2-F.1: como `envolver` pero CONSERVA la indentación (limpiar_codigo). `envolver` colapsa los espacios
    repetidos, así que un bloque de Python llegaba al modelo con todos los niveles de indentación reducidos a uno."""
    if not isinstance(etiqueta, str) or not _ETIQUETA.fullmatch(etiqueta):
        raise ValueError("etiqueta inválida")
    cuerpo = limpiar_codigo(texto, max_chars)
    return f"{DELIM_ABRE} fuente={etiqueta}\n{cuerpo}\n{DELIM_CIERRA}"


def parsear_voto(texto):
    """Devuelve (postura, razon) o None si el formato no es EXACTO.

    Formato permitido (líneas en blanco ignoradas):
        VOTO: <aprobar|aprobar_con_cambios|rechazar|abstencion>
        RAZON: <una línea>          <- opcional
    Cualquier otra línea (texto previo o posterior, segunda línea VOTO, RAZON
    antes del voto, vallas de código, viñetas, continuaciones) invalida todo.
    """
    if not isinstance(texto, str):
        return None
    lineas = [l.strip() for l in texto.replace("\r", "\n").split("\n") if l.strip()]
    if not 1 <= len(lineas) <= 2:
        return None
    m = _VOTO.match(lineas[0])
    if not m:
        return None
    razon = ""
    if len(lineas) == 2:
        r = _RAZON.match(lineas[1])
        if not r:
            return None
        razon = r.group(1)
    return m.group(1).lower(), limpiar(razon, 200)
