"""Comprobaciones SIN GPU del detector y del selector de perfil (hardware falso y un GGUF falso hecho aquí).

    py -B -X utf8 perfiles/comprobar_perfiles.py [carpeta con modelos .gguf reales, opcional]

Con la carpeta de modelos, además compara la caché KV calculada con la medida en llama-server (RTX 3050).
"""
from __future__ import annotations

import json
import os
import platform
import struct
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import equipo_perfil as P  # noqa: E402
import gguf_meta as G  # noqa: E402

RES = []


def ok(nombre, cond, detalle=""):
    RES.append(bool(cond))
    print(f"[{'PASA' if cond else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else ""))


def _s(t):
    b = t.encode()
    return struct.pack("<Q", len(b)) + b


def gguf_falso(ruta, capas=32, cabezas=32, kv=8, emb=4096, ctx=32768, relleno_mib=4000):
    """Un GGUF v3 mínimo con los metadatos que usa el perfil; el peso se simula con un archivo disperso."""
    pares = [("general.architecture", 8, "llama"), ("general.name", 8, "Falso 7B"),
             ("llama.block_count", 4, capas), ("llama.attention.head_count", 4, cabezas),
             ("llama.attention.head_count_kv", 4, kv), ("llama.embedding_length", 4, emb),
             ("llama.context_length", 4, ctx)]
    with open(ruta, "wb") as f:
        f.write(b"GGUF" + struct.pack("<I", 3) + struct.pack("<Q", 0) + struct.pack("<Q", len(pares)))
        for k, t, v in pares:
            f.write(_s(k) + struct.pack("<I", t) + (_s(v) if t == 8 else struct.pack("<I", v)))
        f.seek(relleno_mib * 2 ** 20)
        f.write(b"\0")
    return ruta


def hw(vram=None, usada=800, ram=32000, libre=16000, nombre="NVIDIA GeForce RTX 4060 Ti"):
    return {"so": "Windows 11", "cpu": "CPU falsa", "hilos": 12, "ram_mib": {"total": ram, "libre": libre},
            "gpus": [] if vram is None else [{"indice": 0, "nombre": nombre, "vram_mib": vram, "vram_usada_mib": usada,
                                              "driver": "1.0", "marca": "NVIDIA"}]}


def main(modelos_reales=None):
    tmp = Path(tempfile.mkdtemp(prefix="perfil_"))
    f = gguf_falso(tmp / "falso-7b.gguf")
    m = G.leer(f)
    ok("lee un GGUF v3: arquitectura, capas, cabezas KV y contexto", (m["arquitectura"], m["capas"], m["cabezas_kv"],
                                                                      m["contexto_entrenado"]) == ("llama", 32, 8, 32768))
    ok("KV a 4096 = capas × cabezas_kv × (dk+dv) × 4096 × 1,0625 bytes",
       abs(G.kv_mib(m, 4096) - 32 * 8 * 256 * 4096 * 1.0625 / 2 ** 20) < 0.01, str(round(G.kv_mib(m, 4096), 1)))
    (tmp / "no.gguf").write_bytes(b"XXXX")
    try:
        G.leer(tmp / "no.gguf")
        ok("un archivo que no es GGUF se rechaza", False)
    except G.ErrorGGUF:
        ok("un archivo que no es GGUF se rechaza", True)
    reg = tmp / "modelos_usuario.json"
    r = P.añadir_modelo(f, "falso", registro=reg)
    ok("añadir_modelo guarda SHA-256, bytes y capas", len(r["sha256"]) == 64 and r["meta"]["capas"] == 32
       and json.loads(reg.read_text(encoding="utf-8"))["modelos"]["falso"]["bytes"] == f.stat().st_size)
    mod = {"alias": "falso", "bytes": f.stat().st_size, "meta": m}
    ok("tope de VRAM: 8 GB → 7168 (el medido); 24 GB → 21504 (reserva 12,5 %)",
       P.tope_vram(8192) == 7168 and P.tope_vram(24576) == 21504)
    sin = P.recomendar(hw(None), mod)
    ok("sin GPU: solo procesador, 0 capas, aviso de lentitud", sin["ngl"] == 0 and sin["modo"] == "solo procesador"
       and any("lento" in a for a in sin["avisos"]))
    poca = P.recomendar(hw(None, libre=3000), mod)
    ok("sin GPU y sin RAM libre suficiente: «no cabe»", poca["cabe"] is False)
    r8 = P.recomendar(hw(8192, nombre="NVIDIA GeForce RTX 3050"), mod)
    ok("8 GB (la medida), modelo de 4 GB: entero, contexto 4096 o más, «medido» solo con 4096",
       r8["entero"] and (r8["estimado"] == (r8["ctx"] != 4096)), f"ctx {r8['ctx']}")
    r16 = P.recomendar(hw(16384), mod)
    ok("16 GB: entero y con más contexto que en 8 GB; marcado ESTIMADO", r16["entero"] and r16["ctx"] >= r8["ctx"]
       and r16["estimado"] and any("ESTIMADO" in a for a in r16["avisos"]))
    grande = {"alias": "grande", "bytes": 14000 * 2 ** 20, "meta": {**m, "capas": 48}}
    r8g = P.recomendar(hw(8192), grande)
    ok("modelo de 14 GB en 8 GB: carga parcial, menos de la mitad → aviso de modelo más pequeño",
       not r8g["entero"] and r8g["ngl"] < 24 and any("más pequeño" in a for a in r8g["avisos"]))
    ok("la VRAM prevista nunca pasa del tope", all(x["vram_prevista_mib"] <= x["tope_vram_mib"] for x in (r8, r16, r8g)))
    forz = P.recomendar(hw(8192), grande, ngl=48)
    ok("si el usuario fuerza más capas de las que caben: se recortan y se avisa", forz["ngl"] == r8g["ngl"]
       and any("solo caben" in a for a in forz["avisos"]))
    ctxl = P.recomendar(hw(16384), mod, ctx=65536)
    ok("contexto mayor que el entrenado: se avisa", any("se entrenó" in a for a in ctxl["avisos"]))
    otras = P.recomendar(hw(8192, usada=3000), grande)
    ok("si otros programas usan más VRAM, caben menos capas", otras["ngl"] < r8g["ngl"])
    txt = P.informe(hw(8192), [r8, r8g])
    usuario = os.environ.get("USERNAME") or os.environ.get("USER") or "zzz"
    ok("el informe no lleva rutas, usuario ni nombre del equipo",
       "\\" not in txt and "/" not in txt.replace("tokens/s", "") and usuario not in txt and platform.node() not in txt)
    g3050 = {"limites": {"objetivo_C": 83, "max_trabajo_C": 92}}
    f3050 = P.frenos(g3050, 7168, 5000)
    ok("frenos térmicos con los límites de la RTX 3050 (objetivo 83 °C) = los del PC de origen, 74/66 °C",
       (f3050["termico"]["enfriar_desde_C"], f3050["termico"]["enfriar_hasta_C"]) == (74, 66))
    fcal = P.frenos({"limites": {"objetivo_C": 87, "max_trabajo_C": 93}}, 21504, 9000)
    ok("tarjeta con objetivo 87 °C: frenos 78/70 °C (misma distancia), no los 74/66 copiados",
       (fcal["termico"]["enfriar_desde_C"], fcal["termico"]["enfriar_hasta_C"]) == (78, 70))
    fmax = P.frenos({"limites": {"objetivo_C": 90, "max_trabajo_C": 85}}, 7168, 5000)
    ok("nunca a menos de 10 °C de la máxima de trabajo", fmax["termico"]["enfriar_desde_C"] == 75)
    fnd = P.frenos({"limites": {}}, 7168, 5000)
    ok("sin datos del driver: los frenos conservadores del PC de origen", fnd["termico"]["enfriar_desde_C"] == 74
       and "conservadores" in fnd["termico"]["origen"])
    ok("VRAM de otros programas permitida = tope − modelo − margen (8 GB, modelo de 5000 MiB: 1818)",
       f3050["vram"]["otros_programas_max_mib"] == 7168 - 5000 - P.MARGEN_MIB)
    ok("la recomendación incluye sus frenos", "frenos" in r16 and r16["frenos"]["vram"]["tope_mib"] == P.tope_vram(16384))
    real = P.detectar()
    ok("detectar() devuelve un JSON válido en este equipo", json.loads(json.dumps(real))["cpu"] is not None)
    if modelos_reales:
        medidos = {"qwen2.5-coder-7b-instruct-q4_k_m.gguf": 119.0, "Ministral-3-8B-Instruct-2512-Q4_K_M.gguf": 289.0,
                   "gemma-4-12B-it-qat-UD-Q4_K_XL.gguf": 246.5}
        for nombre, mib in medidos.items():
            p = Path(modelos_reales) / nombre
            if p.is_file():
                k = G.kv_mib(G.leer(p), 4096)
                ok(f"KV calculada = medida en llama-server: {nombre[:24]}", abs(k - mib) < 1, f"{k:.1f} vs {mib}")
        p = Path(modelos_reales) / "gemma-4-12B-it-qat-UD-Q4_K_XL.gguf"
        if p.is_file():
            g = P.recomendar(hw(8192, usada=792, nombre="NVIDIA GeForce RTX 3050"),
                             {"alias": "gemma12", "bytes": p.stat().st_size, "meta": G.leer(p)})
            ok("gemma12 en la RTX 3050: 37–40 capas (medido en la práctica: 37–39)", 37 <= g["ngl"] <= 40, str(g["ngl"]))
    print(f"\n{sum(RES)}/{len(RES)} comprobaciones pasan")
    return 0 if all(RES) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else None))
