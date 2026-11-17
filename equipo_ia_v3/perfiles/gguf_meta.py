"""Lee la cabecera de un archivo GGUF (llama.cpp) sin dependencias: arquitectura, capas, contexto entrenado y lo que
hace falta para estimar la memoria de la caché KV. Solo lee; nunca carga el modelo.

Formato (GGUF v2/v3): 'GGUF', versión u32, nº de tensores u64, nº de pares clave-valor u64 y los pares.
"""
from __future__ import annotations

import struct
from pathlib import Path

_FIJOS = {0: "<B", 1: "<b", 2: "<H", 3: "<h", 4: "<I", 5: "<i", 6: "<f", 7: "<?", 10: "<Q", 11: "<q", 12: "<d"}


class ErrorGGUF(ValueError):
    pass


def _leer(f, fmt):
    n = struct.calcsize(fmt)
    b = f.read(n)
    if len(b) != n:
        raise ErrorGGUF("archivo GGUF cortado")
    return struct.unpack(fmt, b)[0]


def _cadena(f):
    n = _leer(f, "<Q")
    if n > 1 << 24:
        raise ErrorGGUF("cadena demasiado larga: ¿es un GGUF?")
    return f.read(n).decode("utf-8", errors="replace")


def _valor(f, tipo, guardar=True):
    if tipo in _FIJOS:
        return _leer(f, _FIJOS[tipo])
    if tipo == 8:
        return _cadena(f)
    if tipo == 9:                                   # lista: se guardan solo las cortas (el vocabulario se salta)
        sub, n = _leer(f, "<I"), _leer(f, "<Q")
        corta = guardar and n <= 64
        out = [_valor(f, sub, corta) for _ in range(n)]
        return out if corta else f"<lista de {n}>"
    raise ErrorGGUF(f"tipo de valor desconocido: {tipo}")


def leer(ruta) -> dict:
    """Metadatos útiles del modelo. Lanza ErrorGGUF si no es un GGUF válido."""
    ruta = Path(ruta)
    with ruta.open("rb") as f:
        if f.read(4) != b"GGUF":
            raise ErrorGGUF(f"{ruta.name} no es un archivo GGUF")
        version = _leer(f, "<I")
        if version not in (2, 3):
            raise ErrorGGUF(f"versión GGUF no soportada: {version}")
        n_tensores, n_kv = _leer(f, "<Q"), _leer(f, "<Q")
        kv = {}
        for _ in range(n_kv):
            k = _cadena(f)
            kv[k] = _valor(f, _leer(f, "<I"))
    arq = kv.get("general.architecture", "")
    g = lambda c, d=None: kv.get(f"{arq}.{c}", d)
    capas = g("block_count")
    cabezas = g("attention.head_count")
    if isinstance(cabezas, list):
        cabezas = max(cabezas)
    cabezas_kv = g("attention.head_count_kv", cabezas)   # puede ser una lista (un valor por capa)
    emb = g("embedding_length")
    dim_k = g("attention.key_length") or (emb // cabezas if emb and cabezas else None)
    dim_v = g("attention.value_length") or dim_k
    return {"archivo": ruta.name, "bytes": ruta.stat().st_size, "version_gguf": version, "tensores": n_tensores,
            "arquitectura": arq, "nombre": kv.get("general.name"), "capas": capas,
            "contexto_entrenado": g("context_length"), "embedding": emb, "cabezas": cabezas, "cabezas_kv": cabezas_kv,
            "dim_k": dim_k, "dim_v": dim_v, "ventana_deslizante": g("attention.sliding_window"),
            "patron_ventana": g("attention.sliding_window_pattern"),
            "dim_k_ventana": g("attention.key_length_swa"), "dim_v_ventana": g("attention.value_length_swa"),
            "licencia": kv.get("general.license"), "cuantizacion": kv.get("general.file_type")}


def kv_mib(meta: dict, ctx: int, bytes_por_valor: float = 1.0625, extra_ventana: int = 256) -> float:
    """Caché KV estimada (MiB) a `ctx` tokens, K y V en q8_0 (≈ 1,0625 bytes por valor), capa a capa:
    - cabezas KV por capa si el modelo las da en lista;
    - capas con ventana deslizante: solo guardan ventana + `extra_ventana` posiciones, con sus propias dimensiones.
    Comprobado con gemma12 (gemma4): 212,5 + 34 MiB a 4096, igual que el registro de llama-server."""
    n = meta.get("capas")
    if not n or not meta.get("cabezas_kv") or not meta.get("dim_k"):
        return 0.0
    ckv = meta["cabezas_kv"] if isinstance(meta["cabezas_kv"], list) else [meta["cabezas_kv"]] * n
    patron = meta.get("patron_ventana") if isinstance(meta.get("patron_ventana"), list) else None
    ventana = meta.get("ventana_deslizante")
    total = 0.0
    for i in range(n):
        desliza = bool(ventana) and (patron[i] if patron and i < len(patron) else False)
        if desliza:
            dims = (meta.get("dim_k_ventana") or meta["dim_k"]) + (meta.get("dim_v_ventana") or meta["dim_v"])
            celdas = min(ctx, ventana + extra_ventana)
        else:
            dims, celdas = meta["dim_k"] + meta["dim_v"], ctx
        total += ckv[i % len(ckv)] * dims * celdas * bytes_por_valor
    return total / 2 ** 20
