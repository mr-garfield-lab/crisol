"""Identificador PARCIAL del modelo. SOLO LECTURA: nunca se abre para escribir.

Lee tamaño, fecha, marca GGUF y el SHA-256 del primer y último MiB (no el archivo
entero, para no precalentar la caché de páginas). No prueba identidad completa.
"""
from __future__ import annotations

import hashlib
import os

from . import config


def huella_modelo(ruta=None) -> dict:
    ruta = config.ruta_modelo() if ruta is None else ruta
    out = {"ruta": str(ruta)}
    try:
        if os.path.islink(str(ruta)):
            out["error"] = "el modelo es un enlace simbólico (no permitido)"
            return out
        st = os.stat(str(ruta))
        out.update(size=st.st_size, mtime_ns=st.st_mtime_ns)
        with open(str(ruta), "rb") as f:
            cab = f.read(1 << 20)
            f.seek(max(0, st.st_size - (1 << 20)))
            cola = f.read(1 << 20)
        out.update(magic=cab[:4].decode("ascii", "replace"),
                   sha256_primer_MiB=hashlib.sha256(cab).hexdigest(),
                   sha256_ultimo_MiB=hashlib.sha256(cola).hexdigest(),
                   nota="parcial: tamaño, fecha y 2 MiB; no prueba identidad completa")
    except (OSError, ValueError) as e:
        out["error"] = repr(e)
    return out


def problemas_modelo(h: dict) -> list:
    """Lista vacía si el modelo es utilizable."""
    if "error" in h:
        return [f"modelo: {h['error']}"]
    p = []
    if h.get("size", 0) < config.MIN_MODELO_BYTES:
        p.append(f"modelo demasiado pequeño ({h.get('size')} B < {config.MIN_MODELO_BYTES})")
    if h.get("magic") != "GGUF":
        p.append(f"el archivo no empieza por la marca GGUF ({h.get('magic')!r})")
    return p


def mismo_modelo(h0: dict, h1: dict):
    """True/False, o 'no_comprobable' si alguna huella falló."""
    if not h0 or not h1 or "error" in h0 or "error" in h1:
        return "no_comprobable"
    return h0 == h1
