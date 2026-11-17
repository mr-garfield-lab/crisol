"""Detector de hardware y selector de perfil de Equipo IA. Propone; nunca impone ni cambia nada.

    py -B -X utf8 perfiles/equipo_perfil.py detectar              [--json]
    py -B -X utf8 perfiles/equipo_perfil.py modelos               [--json]
    py -B -X utf8 perfiles/equipo_perfil.py añadir_modelo RUTA.gguf [--alias NOMBRE]
    py -B -X utf8 perfiles/equipo_perfil.py recomendar [--modelo ALIAS|RUTA] [--ctx N] [--ngl N] [--json]
    py -B -X utf8 perfiles/equipo_perfil.py informe               (texto SIN datos personales para pegar en cualquier IA)

Cooperativo: con --json, cualquier asistente (Claude, Gemini, GPT…) puede leer la salida y proponer el siguiente paso.
El usuario elige el modelo (los registra él con añadir_modelo); el perfil solo dice cuántas capas caben en la GPU, qué
contexto se puede usar y qué topes de memoria se aplican. Si el usuario fuerza --ngl o --ctx, se valida y se avisa;
nunca se permite pasar del tope de VRAM.

Medido de verdad (2026-11): RTX 3050 8 GB, Ryzen 5 5600GT, 32 GB. El resto de equipos: ESTIMADO.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import gguf_meta as G  # noqa: E402

REGISTRO = AQUI / "modelos_usuario.json"
RESERVA_MIB = 1024             # VRAM que nunca se usa (Windows, picos); en 8 GB deja el tope en 7168, el que se midió
RESERVA_FRACCION = 0.125       # en tarjetas grandes se reserva el 12,5 %
SOBRECOSTE_MIB = 500           # buffers de cálculo y contexto CUDA (medido con gemma12: ~467 MiB)
MARGEN_MIB = 350               # margen ante subidas de otros programas (el mismo que el reparto de capas medido)
RAM_LIBRE_MIN_MIB = 2048       # lo que se deja a Windows al poner capas en la RAM
# RAM que ocupa el proceso del modelo. Medido 2026-11-17 con gemma24 (16,2 GiB, 10 de 30 capas en GPU, archivo mapeado):
# 13,2 GB al arrancar y hasta 17,7 GB durante una tanda larga (Windows deja en RAM todo lo que lee del archivo, también
# las capas que ya están en la GPU). Con carga parcial se cuenta el archivo ENTERO. Antes no se contaba y el freno de
# memoria del núcleo saltó dos veces con otros programas abiertos.
RAM_EXTRA_FRACCION = 0.15      # modelo entero en la GPU: buffers y parte del archivo (sin medir aún: estimado)
RAM_EXTRA_FIJO_MIB = 512
RAM_MARGEN_ARRANQUE_MIB = 4096  # lo que debe quedar libre al arrancar (otros programas crecen; el núcleo corta a 300 MB)


def ram_necesaria(peso_mib: float, en_ram_mib: float) -> int:
    """RAM que ocupará el proceso del modelo. Con capas en la RAM (carga parcial): el archivo entero + 512 MiB, porque
    Windows acaba reteniéndolo todo. Entero en la GPU: 15 % del peso + 512 MiB (estimado)."""
    if en_ram_mib > 0:
        return int(peso_mib + RAM_EXTRA_FIJO_MIB)
    return int(RAM_EXTRA_FRACCION * peso_mib + RAM_EXTRA_FIJO_MIB)


def esperar_ram(necesaria_mib: int, parar=lambda: False, leer=None, max_s: float = 1800, dormir=time.sleep,
                cada_s: float = 30) -> dict:
    """Espera a que haya RAM libre suficiente para arrancar (necesaria + margen), como la puerta de VRAM. No cierra
    nada: si no llega a tiempo, devuelve ok=False y quien llama decide (los laboratorios paran con un motivo claro)."""
    leer = leer or (lambda: _ram_mib().get("libre"))
    falta, esperado = necesaria_mib + RAM_MARGEN_ARRANQUE_MIB, 0.0
    while True:
        libre = leer()
        if libre is None or libre >= falta:
            return {"ok": True, "libre_mib": libre, "necesaria_mib": falta, "esperado_s": esperado}
        if parar() or esperado >= max_s:
            return {"ok": False, "libre_mib": libre, "necesaria_mib": falta, "esperado_s": esperado}
        dormir(cada_s)
        esperado += cada_s
CONTEXTOS = (4096, 8192, 16384, 32768)
MEDIDO = {"gpu": "NVIDIA GeForce RTX 3050", "vram_mib": 8192, "ctx": 4096}
# modelos medidos de verdad en esa tarjeta (SHA-256 → ¿iba entero en la GPU?)
MODELOS_MEDIDOS = {"509287f78cb4d4cf6b3843734733b914b2c158e43e22a7f4bf5e963800894d3c": True,    # qwen25
                   "33e7a72cf5e6e2cfc2f2847075acc013d68bba023e35310cef86b5cf8fdca761": True,    # ministral3
                   "90fd44e29e0d7cffeb0fd00dc73cfdab9ed0b0e95306ecf7821ea634c940c370": False}   # gemma12 (38–39 capas)


# --- detección -------------------------------------------------------------------------------------------------------
def _ram_mib() -> dict:
    try:
        if os.name == "nt":
            class M(ctypes.Structure):
                _fields_ = [("l", ctypes.c_ulong), ("carga", ctypes.c_ulong), ("total", ctypes.c_ulonglong),
                            ("libre", ctypes.c_ulonglong), ("a", ctypes.c_ulonglong), ("b", ctypes.c_ulonglong),
                            ("c", ctypes.c_ulonglong), ("d", ctypes.c_ulonglong), ("e", ctypes.c_ulonglong)]
            m = M()
            m.l = ctypes.sizeof(M)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return {"total": m.total // 2 ** 20, "libre": m.libre // 2 ** 20}
        if Path("/proc/meminfo").is_file():
            d = dict(re.findall(r"^(\w+):\s+(\d+) kB", Path("/proc/meminfo").read_text(), re.M))
            return {"total": int(d["MemTotal"]) // 1024, "libre": int(d.get("MemAvailable", d["MemFree"])) // 1024}
    except Exception:
        pass
    return {"total": None, "libre": None}


def _cpu() -> str:
    try:
        if os.name == "nt":
            import winreg
            k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
            return winreg.QueryValueEx(k, "ProcessorNameString")[0].strip()
        if Path("/proc/cpuinfo").is_file():
            m = re.search(r"model name\s*:\s*(.+)", Path("/proc/cpuinfo").read_text())
            return m.group(1).strip() if m else platform.processor()
    except Exception:
        pass
    return platform.processor() or "desconocido"


def _gpus() -> list:
    """GPUs NVIDIA con nvidia-smi. Otras marcas: no soportadas todavía (se informa, no se adivina)."""
    try:
        o = subprocess.run(["nvidia-smi", "--query-gpu=index,name,memory.total,memory.used,driver_version",
                            "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=15)
        if o.returncode != 0:
            return []
        out = []
        for l in o.stdout.strip().splitlines():
            i, nombre, total, usada, driver = [x.strip() for x in l.split(",")]
            out.append({"indice": int(i), "nombre": nombre, "vram_mib": int(total), "vram_usada_mib": int(usada),
                        "driver": driver, "marca": "NVIDIA"})
        return out
    except (OSError, subprocess.SubprocessError, ValueError):
        return []


def _limites_termicos(indice: int) -> dict:
    """Temperaturas que declara el propio driver: objetivo, máxima de trabajo y de frenado (°C)."""
    try:
        o = subprocess.run(["nvidia-smi", "-q", "-d", "TEMPERATURE", "-i", str(indice)], capture_output=True, text=True,
                           timeout=15).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    buscar = lambda rx: (int(m.group(1)) if (m := re.search(rx + r"\s*:\s*(\d+) C", o)) else None)
    return {"objetivo_C": buscar(r"GPU Target Temperature Specification"), "max_trabajo_C": buscar(r"GPU Max Operating Temp"),
            "frenado_C": buscar(r"GPU Slowdown Temp"), "apagado_C": buscar(r"GPU Shutdown Temp")}


def detectar() -> dict:
    gpus = _gpus()
    for g in gpus:
        g["limites"] = _limites_termicos(g["indice"])
    return {"fecha": time.strftime("%Y-%m-%dT%H:%M:%S"), "so": f"{platform.system()} {platform.release()}",
            "cpu": _cpu(), "hilos": os.cpu_count(), "ram_mib": _ram_mib(), "gpus": gpus,
            "nota": "Solo se detectan GPUs NVIDIA (nvidia-smi). AMD, Intel y Apple: sin soporte medido todavía."}


# Frenos del PC de origen (RTX 3050, objetivo 83 °C): enfriar desde 74 °C hasta 66 °C antes de cada petición.
# En otro equipo se calculan con la MISMA distancia al objetivo que declare su driver; sin dato, se usan estos.
FRENO_ORIGEN = {"enfriar_desde_C": 74, "enfriar_hasta_C": 66, "objetivo_C": 83}


def frenos(gpu: dict | None, tope_mib: int | None, vram_modelo_mib: float | None) -> dict:
    """Frenos adaptados al hardware del usuario (no los del PC de origen copiados):
    - térmicos: objetivo − 9 °C para empezar a enfriar y objetivo − 17 °C para seguir, nunca por encima de
      max_trabajo − 10;
    - VRAM: el tope (total − reserva) y la VRAM máxima que pueden usar OTROS programas antes de arrancar
      (tope − lo que ocupará el modelo − margen), igual que la puerta del PC de origen pero con sus números."""
    if not gpu:
        return {"termico": None, "nota": "sin GPU: no hay frenos de GPU; vigila la temperatura del procesador"}
    lim = gpu.get("limites") or {}
    obj = lim.get("objetivo_C")
    if obj:
        desde = obj - (FRENO_ORIGEN["objetivo_C"] - FRENO_ORIGEN["enfriar_desde_C"])
        if lim.get("max_trabajo_C"):
            desde = min(desde, lim["max_trabajo_C"] - 10)
        hasta = desde - (FRENO_ORIGEN["enfriar_desde_C"] - FRENO_ORIGEN["enfriar_hasta_C"])
        origen = "calculado con los límites de tu driver"
    else:
        desde, hasta, origen = FRENO_ORIGEN["enfriar_desde_C"], FRENO_ORIGEN["enfriar_hasta_C"], \
            "tu driver no da la temperatura objetivo: se usan los del PC de origen (conservadores)"
    otras_max = int(tope_mib - vram_modelo_mib - MARGEN_MIB) if tope_mib and vram_modelo_mib is not None else None
    return {"termico": {"enfriar_desde_C": desde, "enfriar_hasta_C": hasta, "origen": origen},
            "vram": {"tope_mib": tope_mib, "otros_programas_max_mib": otras_max}}


# --- modelos del usuario ---------------------------------------------------------------------------------------------
def _registro() -> dict:
    return json.loads(REGISTRO.read_text(encoding="utf-8")) if REGISTRO.is_file() else {"modelos": {}}


def sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with Path(ruta).open("rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def añadir_modelo(ruta, alias=None, registro=None) -> dict:
    """Registra un GGUF elegido por el usuario: huella SHA-256, tamaño y metadatos (para reproducir y para el perfil)."""
    ruta = Path(ruta).resolve()
    meta = G.leer(ruta)
    alias = alias or re.sub(r"[^a-z0-9]+", "_", ruta.stem.lower()).strip("_")[:32]
    reg_f = Path(registro or REGISTRO)
    reg = json.loads(reg_f.read_text(encoding="utf-8")) if reg_f.is_file() else {"modelos": {}}
    reg["modelos"][alias] = {"ruta": str(ruta), "sha256": sha256(ruta), "bytes": meta["bytes"],
                             "meta": {k: v for k, v in meta.items() if k not in ("archivo", "bytes")}}
    reg_f.write_text(json.dumps(reg, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    return {"alias": alias, **reg["modelos"][alias]}


def _modelo(nombre):
    reg = _registro()["modelos"]
    if nombre in reg:
        return {"alias": nombre, **reg[nombre], "meta": {**reg[nombre]["meta"], "bytes": reg[nombre]["bytes"]}}
    p = Path(nombre)
    if p.is_file():
        m = G.leer(p)
        return {"alias": p.stem, "ruta": str(p), "bytes": m["bytes"], "meta": m}
    raise SystemExit(f"no conozco el modelo «{nombre}»: regístralo con añadir_modelo RUTA.gguf")


# --- perfil ------------------------------------------------------------------------------------------------------------
def tope_vram(vram_mib: int) -> int:
    return int(vram_mib - max(RESERVA_MIB, vram_mib * RESERVA_FRACCION))


def recomendar(hw: dict, modelo: dict, ctx=None, ngl=None) -> dict:
    """Capas en GPU, contexto y topes. Con `ctx`/`ngl` del usuario: se validan y se avisa; nunca se pasa del tope."""
    meta = {**modelo["meta"], "bytes": modelo["bytes"]}
    capas = meta.get("capas") or 0
    peso_mib = modelo["bytes"] / 2 ** 20
    por_capa = peso_mib / max(1, capas)
    avisos, r = [], {"modelo": modelo["alias"], "capas_modelo": capas, "peso_mib": round(peso_mib)}
    gpu = max(hw["gpus"], key=lambda g: g["vram_mib"]) if hw["gpus"] else None
    ram_libre = (hw["ram_mib"] or {}).get("libre")
    ctx_max_modelo = meta.get("contexto_entrenado") or 4096
    if not gpu:
        ctx_ok = ctx or 4096
        r.update(gpu=None, ngl=0, ctx=ctx_ok, modo="solo procesador", estimado=True, frenos=frenos(None, None, None))
        avisos.append("sin GPU NVIDIA: irá MUY lento (estimado 1–5 tokens/s según el procesador)")
        if ram_libre is not None and peso_mib + G.kv_mib(meta, ctx_ok) + RAM_LIBRE_MIN_MIB > ram_libre:
            avisos.append("no cabe en la RAM libre: elige un modelo más pequeño o una cuantización menor")
            r["cabe"] = False
        else:
            r["cabe"] = True
        return {**r, "avisos": avisos}
    tope = tope_vram(gpu["vram_mib"])
    otras = gpu["vram_usada_mib"]
    disponible = tope - otras - SOBRECOSTE_MIB - MARGEN_MIB

    def capas_para(c):
        return int((disponible - G.kv_mib(meta, c)) // por_capa)

    if ctx is None:                                   # el mayor contexto con el que el modelo cabe ENTERO; si no, 4096
        ctx = 4096
        for c in CONTEXTOS:
            if c <= ctx_max_modelo and capas_para(c) >= capas:
                ctx = c
    elif ctx > ctx_max_modelo:
        avisos.append(f"el modelo se entrenó con {ctx_max_modelo} de contexto; {ctx} puede dar respuestas peores")
    cabe = capas_para(ctx)
    if ngl is None:
        ngl = max(0, min(capas, cabe))
    elif ngl > cabe:
        avisos.append(f"pediste {ngl} capas en la GPU, pero solo caben {max(cabe, 0)} bajo el tope de {tope} MiB: "
                      f"se usan {max(cabe, 0)}")
        ngl = max(0, min(capas, cabe))
    en_ram = (capas - ngl) * por_capa
    entero = ngl >= capas
    if not entero:
        avisos.append(f"{capas - ngl} de {capas} capas irán a la RAM: más lento (en la RTX 3050 medida, gemma12 con "
                      f"38 de 48 capas iba a 13–15 tokens/s)")
        if ngl < capas * 0.5:
            avisos.append("menos de la mitad cabe en la GPU: considera un modelo más pequeño o una cuantización menor")
    ram = ram_necesaria(peso_mib, en_ram)
    if ram_libre is not None and ram + RAM_MARGEN_ARRANQUE_MIB > ram_libre:
        avisos.append(f"necesita ~{ram} MiB de RAM y hay {ram_libre} libres (más {RAM_MARGEN_ARRANQUE_MIB} de margen): "
                      "cierra programas antes de arrancarlo; los laboratorios esperan a que haya RAM libre")
    usada = otras + ngl * por_capa + G.kv_mib(meta, ctx) + SOBRECOSTE_MIB
    # medido = la tarjeta Y la configuración que se probaron de verdad (contexto 4096); lo demás es estimación
    medido = (gpu["nombre"] == MEDIDO["gpu"] and gpu["vram_mib"] == MEDIDO["vram_mib"] and ctx == MEDIDO["ctx"]
              and MODELOS_MEDIDOS.get(modelo.get("sha256")) == entero)   # y el mismo modelo, en la misma forma
    r.update(gpu=gpu["nombre"], vram_mib=gpu["vram_mib"], vram_otras_mib=otras, tope_vram_mib=tope, ctx=ctx,
             ngl=ngl, entero=entero, kv_mib=round(G.kv_mib(meta, ctx), 1), en_ram_mib=round(en_ram),
             ram_necesaria_mib=ram,
             vram_prevista_mib=round(usada), modo="GPU entera" if entero else "GPU + RAM (carga parcial)",
             estimado=not medido, args_llama=["-ngl", "all" if entero else str(ngl), "-c", str(ctx),
                                              "-ctk", "q8_0", "-ctv", "q8_0", "-fa", "on"])
    if not medido:
        avisos.append("perfil ESTIMADO: solo está medida la RTX 3050 de 8 GB con contexto 4096; mide tu equipo y "
                      "compártelo")
    r["frenos"] = frenos(gpu, tope, usada - otras)
    r["frenos"]["ram"] = {"necesaria_mib": ram, "libre_para_arrancar_mib": ram + RAM_MARGEN_ARRANQUE_MIB}
    return {**r, "avisos": avisos}


# --- informe para cualquier asistente ----------------------------------------------------------------------------------
def informe(hw: dict, recomendaciones: list) -> str:
    """Texto sin rutas, usuario ni nombre del equipo: se puede pegar en cualquier IA para pedir ayuda."""
    L = ["# Equipo IA — informe de hardware (sin datos personales)", "",
         f"- Sistema: {hw['so']}; CPU: {hw['cpu']} ({hw['hilos']} hilos); RAM: {hw['ram_mib']['total']} MiB "
         f"({hw['ram_mib']['libre']} libres)"]
    if hw["gpus"]:
        for g in hw["gpus"]:
            L.append(f"- GPU {g['indice']}: {g['nombre']}, {g['vram_mib']} MiB ({g['vram_usada_mib']} en uso), "
                     f"driver {g['driver']}")
    else:
        L.append("- GPU: ninguna NVIDIA detectada")
    for r in recomendaciones:
        L += ["", f"## Modelo {r['modelo']} ({r['peso_mib']} MiB, {r['capas_modelo']} capas)",
              f"- Perfil: {r['modo']}; contexto {r['ctx']}; capas en GPU {r['ngl']}"
              + (f"; VRAM prevista {r['vram_prevista_mib']} de tope {r['tope_vram_mib']} MiB" if r.get("gpu") else ""),
              f"- ¿Medido o estimado?: {'ESTIMADO' if r['estimado'] else 'medido'}"]
        L += [f"- Aviso: {a}" for a in r["avisos"]]
    L += ["", "Pregunta sugerida al asistente: «Con este hardware, ¿qué modelo y perfil me recomiendas para Equipo IA y "
          "por qué? No me pidas cambiar topes de seguridad.»"]
    texto = "\n".join(L)
    usuario = os.environ.get("USERNAME") or os.environ.get("USER")
    for secreto in filter(None, {usuario, platform.node()}):        # por si algún nombre se colara
        texto = texto.replace(secreto, "<oculto>")
    return texto


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("orden", choices=("detectar", "modelos", "añadir_modelo", "recomendar", "informe"))
    ap.add_argument("ruta", nargs="?")
    ap.add_argument("--alias")
    ap.add_argument("--modelo", action="append")
    ap.add_argument("--ctx", type=int)
    ap.add_argument("--ngl", type=int)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    salida = None
    if a.orden == "detectar":
        salida = detectar()
    elif a.orden == "modelos":
        salida = {k: {"sha256": v["sha256"][:16] + "…", "mib": v["bytes"] // 2 ** 20, "capas": v["meta"].get("capas"),
                      "arquitectura": v["meta"].get("arquitectura")} for k, v in _registro()["modelos"].items()}
    elif a.orden == "añadir_modelo":
        if not a.ruta:
            raise SystemExit("falta la ruta del .gguf")
        r = añadir_modelo(a.ruta, a.alias)
        salida = {"alias": r["alias"], "sha256": r["sha256"], "capas": r["meta"]["capas"]}
    else:
        hw = detectar()
        nombres = a.modelo or list(_registro()["modelos"])
        if not nombres:
            raise SystemExit("no hay modelos registrados: usa añadir_modelo RUTA.gguf")
        recs = [recomendar(hw, _modelo(n), a.ctx, a.ngl) for n in nombres]
        if a.orden == "informe":
            print(informe(hw, recs))
            return 0
        salida = recs if len(recs) > 1 else recs[0]
    if a.json or a.orden != "recomendar":
        print(json.dumps(salida, ensure_ascii=False, indent=1))
    else:
        for r in (salida if isinstance(salida, list) else [salida]):
            print(f"{r['modelo']}: {r['modo']}, contexto {r['ctx']}, capas en GPU {r['ngl']}/{r['capas_modelo']}"
                  + (f", VRAM prevista {r['vram_prevista_mib']}/{r['tope_vram_mib']} MiB" if r.get("gpu") else "")
                  + (" [ESTIMADO]" if r["estimado"] else " [medido]"))
            for x in r["avisos"]:
                print("  aviso:", x)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
