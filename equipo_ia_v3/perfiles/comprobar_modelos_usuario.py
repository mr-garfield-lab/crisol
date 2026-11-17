"""Comprobaciones SIN GPU: los laboratorios aceptan los modelos que registra el usuario con `añadir_modelo`.

    py -B -X utf8 perfiles/comprobar_modelos_usuario.py

Usa un registro y un GGUF falsos en una carpeta temporal; no toca perfiles/modelos_usuario.json.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
for p in (str(AQUI), str(RAIZ), str(RAIZ / "lab_flujos")):
    if p not in sys.path:
        sys.path.insert(0, p)
import comprobar_perfiles as CP  # noqa: E402
import equipo_perfil as P  # noqa: E402

RES = []


def ok(nombre, cond, detalle=""):
    RES.append(bool(cond))
    print(f"[{'PASA' if cond else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else ""))


def main():
    import banco_flujos as BF
    from eq3 import evaluar_f1_v5 as V
    from lab_vram import banco_capacidad as BC
    LB = BF._banco_blender()
    tmp = Path(tempfile.mkdtemp(prefix="modusr_"))
    externos = tmp / "externos"
    (externos / "modelos").mkdir(parents=True)
    dentro = CP.gguf_falso(externos / "modelos" / "mio-14b.gguf", capas=40, relleno_mib=8)
    fuera = CP.gguf_falso(tmp / "otra_carpeta" / "lejos.gguf" if (tmp / "otra_carpeta").mkdir() is None else None,
                          capas=24, relleno_mib=4)
    reg = tmp / "modelos_usuario.json"
    P.añadir_modelo(dentro, "mio14b", registro=reg)
    P.añadir_modelo(fuera, "lejos", registro=reg)
    falso_qwen = json.loads(reg.read_text(encoding="utf-8"))
    falso_qwen["modelos"]["qwen25"] = {**falso_qwen["modelos"]["mio14b"], "sha256": "0" * 64}
    reg.write_text(json.dumps(falso_qwen), encoding="utf-8")
    LB.MODELOS_USUARIO = reg
    original = LB._con_cerebros_lab(BC, V, V.B, externos)
    try:
        r = BC.registro("mio14b")["modelo"]
        ok("modelo del usuario dentro de externos: ruta relativa, SHA-256 y bytes de su registro",
           r["archivo"] == "modelos/mio-14b.gguf" and r["sha256"] == P.sha256(dentro) and r["bytes"] == dentro.stat().st_size,
           r["archivo"])
        ok("el armazón resuelve esa ruta al archivo real (como verificar_externos)",
           externos.joinpath(*r["archivo"].split("/")).resolve() == dentro.resolve())
        r2 = BC.registro("lejos")["modelo"]
        ok("modelo fuera de externos (misma unidad): ruta con «..» que llega al archivo",
           r2["archivo"].startswith("../") and externos.joinpath(*r2["archivo"].split("/")).resolve() == fuera.resolve(),
           r2["archivo"])
        rq = BC.registro("qwen25")["modelo"]
        ok("los nombres del proyecto tienen prioridad: «qwen25» del usuario no sustituye al oficial",
           rq["sha256"] != "0" * 64 and rq["sha256"].startswith("509287"))
        ok("es_solo_del_usuario: sí para el suyo; no para qwen25 ni gemma12",
           LB.es_solo_del_usuario("mio14b", original) and not LB.es_solo_del_usuario("qwen25", original)
           and not LB.es_solo_del_usuario("gemma12", original))
        try:
            BC.registro("no_existe")
            ok("un nombre desconocido sigue fallando (KeyError)", False)
        except KeyError:
            ok("un nombre desconocido sigue fallando (KeyError)", True)
        if os.name == "nt":
            otra = "D:\\" if not str(externos).upper().startswith("D:") else "C:\\"
            try:
                LB._ruta_desde(externos, otra + "modelo.gguf")
                ok("modelo en otra unidad: se rechaza con un mensaje claro", False)
            except SystemExit as e:
                ok("modelo en otra unidad: se rechaza con un mensaje claro", "otra unidad" in str(e))
        perfil = LB._perfil_usuario(externos, BC.registro("mio14b"), V.CTX)
        ok("el perfil por hardware se calcula para el modelo del usuario (tope y capas)",
           perfil["tope_vram_mib"] > 0 and perfil["capas_modelo"] == 40 and "frenos" in perfil)
    finally:
        BC.registro = original
    print(f"\n{sum(RES)}/{len(RES)} comprobaciones pasan")
    return 0 if all(RES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
