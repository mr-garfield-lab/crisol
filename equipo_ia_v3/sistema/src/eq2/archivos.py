"""V2-D: extracción de los archivos que propone A1. Solo TEXTO: nunca se ejecuta nada.

Formato pedido al modelo (una o varias veces):
    ARCHIVO: nombre.py
    ```python
    ...contenido...
    ```
Reglas: nombre simple (sin carpetas, sin '..', sin ocultos), extensión de una lista cerrada,
tamaño y número de archivos limitados, sin duplicados, sin bytes nulos. Lo que no cumple se
RECHAZA con un motivo; no se corrige en silencio.
"""
from __future__ import annotations

import hashlib
import re

from . import config

NOMBRE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,39}\.[a-z]{1,4}")
_CABECERA = re.compile(r"^\s*[-*]?\s*ARCHIVO\s*:\s*(\S+)\s*$", re.IGNORECASE)
_FENCE = re.compile(r"^\s*```")
RESERVADOS = {"con", "prn", "aux", "nul", "com1", "lpt1"}   # nombres prohibidos en Windows


def nombre_valido(nombre) -> bool:
    if not isinstance(nombre, str) or not NOMBRE.fullmatch(nombre):
        return False
    base, ext = nombre.rsplit(".", 1)
    return ("." + ext) in config.EJECUTOR_EXTENSIONES and base.lower() not in RESERVADOS


def extraer(texto, validador=None, max_archivos=None, max_bytes=None, max_total=None) -> dict:
    """{archivos: [{nombre, contenido, bytes, sha256}], problemas: [str]}.

    V2-E: validador/límites configurables (por defecto, los de V2-D)."""
    validador = validador or nombre_valido
    max_archivos = config.EJECUTOR_MAX_ARCHIVOS if max_archivos is None else max_archivos
    max_bytes = config.EJECUTOR_MAX_BYTES_ARCHIVO if max_bytes is None else max_bytes
    total = 0
    archivos, problemas, vistos = [], [], set()
    if not isinstance(texto, str):
        return {"archivos": [], "problemas": ["sin_texto"]}
    lineas = texto.split("\n")
    i = 0
    while i < len(lineas):
        m = _CABECERA.match(lineas[i])
        if not m:
            i += 1
            continue
        nombre = m.group(1).strip("`'\"")
        j = i + 1
        while j < len(lineas) and not lineas[j].strip():
            j += 1
        if j >= len(lineas) or not _FENCE.match(lineas[j]):
            problemas.append(f"sin_bloque_de_codigo:{nombre[:40]}")
            i += 1
            continue
        k = j + 1
        while k < len(lineas) and not _FENCE.match(lineas[k]):
            k += 1
        if k >= len(lineas):
            problemas.append(f"bloque_sin_cerrar:{nombre[:40]}")
            break
        contenido = "\n".join(lineas[j + 1:k]) + "\n"
        i = k + 1
        if not validador(nombre):
            problemas.append(f"nombre_invalido:{nombre[:40]}")
            continue
        if nombre.lower() in vistos:
            problemas.append(f"duplicado:{nombre}")
            continue
        if "\x00" in contenido:
            problemas.append(f"byte_nulo:{nombre}")
            continue
        datos = contenido.encode("utf-8")
        if len(datos) > max_bytes:
            problemas.append(f"demasiado_grande:{nombre}:{len(datos)}")
            continue
        if len(archivos) >= max_archivos:
            problemas.append(f"demasiados_archivos:{nombre}")
            continue
        if max_total is not None and total + len(datos) > max_total:
            problemas.append(f"tamano_total_superado:{nombre}")
            continue
        total += len(datos)
        vistos.add(nombre.lower())
        archivos.append({"nombre": nombre, "contenido": contenido, "bytes": len(datos),
                         "sha256": hashlib.sha256(datos).hexdigest()})
    if not archivos and not problemas:
        problemas.append("ningun_archivo")
    return {"archivos": archivos, "problemas": problemas}
