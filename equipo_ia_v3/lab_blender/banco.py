"""Banco de Blender (laboratorio): un cerebro escribe el script, Blender lo ejecuta, un verificador SIN IA lo mide y el
cerebro corrige con lo medido. Hasta INTENTOS intentos por tarea.

    python -B -X utf8 lab_blender/banco.py validar  SALIDA_BLENDER                       (sin cerebros ni GPU)
    python -B -X utf8 eq3/lanzador_eq2.py lab_blender/banco.py ejecutar EXTERNOS EVIDENCIA SALIDA_BLENDER
                                             [--modelos qwen25 yi] [--tareas T01 T02 …] [--reanudar]
    python -B -X utf8 lab_blender/banco.py estado  EVIDENCIA
    python -B -X utf8 lab_blender/banco.py informe EVIDENCIA
    python -B -X utf8 lab_blender/banco.py videos  EVIDENCIA SALIDA_BLENDER              (sin cerebros; usa la GPU un poco)

`validar` ejecuta las soluciones de referencia (de Claude) y comprueba que cada tarea se puede resolver y que el verificador
distingue unas de otras; también crea los .blend de partida. `ejecutar` usa la misma seguridad que el resto del laboratorio
(PC libre, VRAM, térmica, STOP, reanudación) y NO renderiza: mientras el cerebro ocupa la GPU, Blender solo mide. `videos`
renderiza después, con el cerebro ya descargado, el último script de cada tarea.
Quien decide si una tarea está aprobada es el verificador, nunca un cerebro. La velocidad no decide nada.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
for p in (str(RAIZ), str(AQUI)):
    if p not in sys.path:
        sys.path.insert(0, p)
import ejecutor as EJ  # noqa: E402
import tareas as T  # noqa: E402
import verificador as VF  # noqa: E402

MODELOS = ("qwen25", "yi")                                    # los dos «coder»; de dos en dos (usuario, 2026-11-13)
CEREBROS_LAB = AQUI / "cerebros_extra.json"                  # cerebros solo de este banco (gemma12, 2026-11-15)


def cerebro_lab(modelo: str) -> dict | None:
    """El registro de un cerebro propio del banco de Blender (archivo, SHA-256, bytes y capas en GPU), o None."""
    if not CEREBROS_LAB.is_file():
        return None
    return json.loads(CEREBROS_LAB.read_text(encoding="utf-8"))["modelos"].get(modelo)


MODELOS_USUARIO = RAIZ / "perfiles" / "modelos_usuario.json"   # los que registra cada persona con añadir_modelo


def modelo_usuario(alias: str) -> dict | None:
    """Un modelo registrado por el usuario (perfiles/equipo_perfil.py añadir_modelo): ruta, SHA-256 y bytes."""
    if not MODELOS_USUARIO.is_file():
        return None
    return json.loads(MODELOS_USUARIO.read_text(encoding="utf-8"))["modelos"].get(alias)


def es_solo_del_usuario(modelo: str, original) -> bool:
    """True si el modelo NO está en ningún registro del proyecto y sí en el del usuario (sus topes no están medidos)."""
    if cerebro_lab(modelo) is not None or modelo_usuario(modelo) is None:
        return False
    try:
        original(modelo)
        return False
    except KeyError:
        return True


def _ruta_desde(externos, ruta: str) -> str:
    """La ruta del modelo relativa a la carpeta de externos (como la esperan los registros), con «/»."""
    import os
    if externos is None:
        raise SystemExit("un modelo registrado por el usuario necesita la carpeta de externos")
    try:
        return os.path.relpath(ruta, externos).replace("\\", "/")
    except ValueError:                                   # otra unidad en Windows
        raise SystemExit(f"el modelo está en otra unidad que la carpeta de externos ({externos}): muévelo a "
                         "externos/modelos/ y vuelve a registrarlo con añadir_modelo")


def _perfil_usuario(externos, registro: dict, ctx: int) -> dict:
    """Perfil por hardware (perfiles/) para un modelo del usuario: tope de VRAM y capas calculados para su equipo."""
    sys.path.insert(0, str(RAIZ / "perfiles"))
    import equipo_perfil as PERF
    import gguf_meta as GM
    ruta = Path(externos) / registro["modelo"]["archivo"]
    return PERF.recomendar(PERF.detectar(), {"alias": ruta.stem, "bytes": ruta.stat().st_size, "meta": GM.leer(ruta)},
                           ctx=ctx)


def _con_cerebros_lab(BC, V, B, externos=None):
    """Hace que BC.g2 conozca, además de los registros protegidos de F1 (que no se tocan): los cerebros de
    `cerebros_extra.json` y, desde 2026-11-17, los que cada usuario registra con `añadir_modelo`. En todos se sigue
    exigiendo la huella SHA-256 y el tamaño exactos; los nombres del proyecto tienen prioridad sobre los del usuario."""
    original = BC.registro

    def registro(modelo):
        m = cerebro_lab(modelo)
        if m is None:
            try:
                return original(modelo)
            except KeyError:
                u = modelo_usuario(modelo)
                if u is None:
                    raise
                m = {"archivo": _ruta_desde(externos, u["ruta"]), "sha256": u["sha256"], "bytes": u["bytes"]}
        reg = json.loads(V.EXTERNOS_JSON.read_text(encoding="utf-8"))
        reg["modelo"] = {k: m[k] for k in ("archivo", "sha256", "bytes")}
        return reg
    BC.registro = registro
    return original


def ngl_para(m: dict, otras_MiB, tope_MiB: int) -> int:
    """Capas en la GPU para un cerebro que no cabe entero: las que caben bajo el tope de VRAM con la VRAM que ya
    usan las demás aplicaciones (medida en G2), con margen; nunca menos que «ngl» (lo medido con 1992 MiB ajenos)."""
    a = m.get("ngl_auto")
    if not a or otras_MiB is None:
        return m["ngl"]
    cabe = int((tope_MiB - otras_MiB - a["margen_MiB"] - a["fijo_MiB"]) // a["por_capa_MiB"])
    return max(m["ngl"], min(a["capas"], cabe))


def _e2_de(modelo, V, ngl=None):
    """El E2 de V5; con «ngl», solo esas capas en la GPU (el resto en la RAM)."""
    e2 = list(V.E2)
    if ngl:
        e2[e2.index("-ngl") + 1] = str(ngl)
    return e2


def _e2_ok(modelo, V, carpeta, ngl=None):
    """Como V.comprobar_logs, pero con «ngl» acepta exactamente esas capas en la GPU."""
    m = {"ngl": ngl}
    if not ngl:
        return V.comprobar_logs(carpeta)
    logs = sorted(Path(carpeta).rglob("server.log"))
    ef = []
    for p in logs:
        e = V.B.configuracion_efectiva(p.read_text(encoding="utf-8", errors="replace"))
        e["ok"] = (e["capas_gpu"] is not None and e["capas_gpu"].split("/")[0] == str(m["ngl"])
                   and e["n_ubatch"] == 128 and not e["fit_ajusto"])
        ef.append(e)
    return {"logs": len(logs), "efectivas": ef, "ok": bool(ef) and all(e["ok"] for e in ef), "ngl": m["ngl"]}
INTENTOS = 3
TOKENS = 800                                                 # tope del backend de V2-F.1 (sistema/, no se toca)
MAX_SCRIPT_PROMPT = 3800                                     # caracteres del script anterior que vuelven al cerebro
MAX_REINTENTOS = 3
TIEMPO_BLENDER_S = 90
SUPERCONJUNTOS = {("T08", "T05"), ("B01", "T05")}            # la solución de la primera también cumple la segunda
MANUAL = ""  # tanda 5: manual de recetas, se añade a SISTEMA con --manual
SISTEMA = (
    "Escribes scripts de Python para Blender 5.2 que se ejecutan sin ventana. Reglas:\n"
    "- Responde SOLO con un bloque ```python … ``` con el script completo, sin explicaciones.\n"
    "- Solo puedes importar bpy, bmesh, mathutils, math y random. Prohibido: archivos, render, clases, bpy.app, bpy.utils, "
    "bpy.types y cualquier ruta de archivo.\n"
    "- Usa bpy.ops de forma directa (bpy.ops.mesh.…, bpy.ops.object.…); no lo guardes en variables.\n"
    "- La escena empieza VACÍA (sin cubo, cámara ni luz) salvo que la tarea diga otra cosa. No añadas cámara, luz ni suelo.\n"
    "- Unidades en metros, Z hacia arriba. Las medidas «a × b × c» son en X, Y, Z. Usa exactamente los nombres pedidos.\n"
    "- Caja: bpy.ops.mesh.primitive_cube_add(size=1, location=(x, y, z)); ob = bpy.context.active_object; ob.name = \"…\"; "
    "ob.scale = (a, b, c).\n"
    "- Hijo: bpy.context.view_layer.update(); hijo.parent = padre; hijo.matrix_parent_inverse = padre.matrix_world.inverted().\n"
    "- Color de render: m = bpy.data.materials.new(\"Nombre\"); m.use_nodes = True; "
    "m.node_tree.nodes[\"Principled BSDF\"].inputs[\"Base Color\"].default_value = (r, g, b, 1.0); ob.data.materials.append(m).\n"
    "- Animación: ob.keyframe_insert(data_path=\"location\", frame=N) (o \"rotation_euler\"); la escena se ajusta con "
    "bpy.context.scene.frame_start y frame_end.")
BLOQUE = re.compile(r"```(?:python|py)?[ \t]*\r?\n(.*?)```", re.S | re.I)


def escribir(ruta: Path, datos):
    import os
    ruta = Path(ruta)
    tmp = ruta.with_name(ruta.name + ".tmp")
    tmp.write_text(datos if isinstance(datos, str) else json.dumps(datos, ensure_ascii=False, indent=1, default=str),
                   encoding="utf-8", newline="\n")
    os.replace(tmp, ruta)


def extraer_script(texto: str) -> str:
    """El primer bloque ```python``` de la respuesta; si no hay bloque, la respuesta entera."""
    m = BLOQUE.search(texto or "")
    if m:
        return m.group(1).strip() + "\n"
    t = (texto or "").strip()
    if t.startswith("```"):                                  # bloque abierto y sin cerrar (respuesta cortada)
        t = t.split("\n", 1)[1] if "\n" in t else ""
    return t + "\n"


def mensajes(tarea: dict, previo: dict | None = None) -> list:
    """Primer intento: la tarea. Siguientes: la tarea, el script anterior y lo que midió el verificador."""
    u = f"TAREA:\n{tarea['enunciado']}"
    if previo:
        s = previo["script"]
        if len(s) > MAX_SCRIPT_PROMPT:
            s = s[:MAX_SCRIPT_PROMPT] + "\n# …[script recortado]\n"
        u += (f"\n\nTu script anterior:\n```python\n{s}```\n\nResultado al ejecutarlo en Blender:\n{previo['feedback']}\n\n"
              "Corrige el script y devuélvelo completo.")
    return [{"role": "system", "content": SISTEMA + MANUAL}, {"role": "user", "content": u}]


def base_de(tarea: dict, salida_blender: Path) -> Path | None:
    return Path(salida_blender) / "bases" / f"{tarea['base']}.blend" if tarea.get("base") else None


def probar(id_tarea: str, script: str, carpeta: Path, salida_blender: Path, render: dict | None = None) -> tuple:
    """Ejecuta un script para una tarea y lo verifica. Devuelve (resultado del ejecutor, veredicto del verificador)."""
    tarea = T.TAREAS[id_tarea]
    r = EJ.ejecutar(script, carpeta, base=base_de(tarea, salida_blender), muestras=tarea.get("muestras", 5), render=render,
                    tiempo_s=TIEMPO_BLENDER_S if not render else 300)
    return r, VF.verificar(tarea, r)


# --- validación con las soluciones de referencia (sin cerebros) -----------------------------------------------------------
def validar(salida_blender: Path) -> dict:
    import shutil
    salida_blender = Path(salida_blender)
    zona = salida_blender / f"validacion_{int(time.time())}"
    (salida_blender / "bases").mkdir(parents=True, exist_ok=True)
    res = {"inicio": time.strftime("%Y-%m-%dT%H:%M:%S"), "modo": "REAL", "referencias": {}, "vacio": {}, "cruces": [],
           "fallos": []}
    for nombre, tarea_ref in T.BASES.items():                # los .blend de partida salen de una referencia
        destino = salida_blender / "bases" / f"{nombre}.blend"
        if not destino.exists():
            r, v = probar(tarea_ref, T.REFERENCIAS[tarea_ref], zona / f"base_{nombre}", salida_blender)
            if not v["aprobado"]:
                raise SystemExit(f"la referencia {tarea_ref} no pasa su propia tarea: {v['texto']}")
            shutil.copyfile(zona / f"base_{nombre}" / "resultado.blend", destino)
        res.setdefault("bases", {})[nombre] = EJ.huella(destino)
    resultados = {}
    for id_ in T.TAREAS:
        r, v = probar(id_, T.REFERENCIAS[id_], zona / f"ref_{id_}", salida_blender)
        resultados[id_] = r
        res["referencias"][id_] = {"aprobado": v["aprobado"], "cumplidas": v.get("cumplidas"), "total": v.get("total"),
                                   "estado": r["estado"], "segundos": r.get("segundos"), "texto": v["texto"]}
        if not v["aprobado"]:
            res["fallos"].append(f"la referencia de {id_} no pasa: {v['texto']}")
        r0, v0 = probar(id_, "import bpy\n", zona / f"vacio_{id_}", salida_blender)
        res["vacio"][id_] = {"aprobado": v0["aprobado"], "cumplidas": v0.get("cumplidas"), "total": v0.get("total")}
        if v0["aprobado"]:
            res["fallos"].append(f"{id_} se aprueba con un script vacío")
    for a, ra in resultados.items():                         # la solución de una tarea no debe aprobar otra
        for b, tb in T.TAREAS.items():
            if a != b:
                v = VF.verificar(tb, ra)
                if v["aprobado"]:
                    esperado = (a, b) in SUPERCONJUNTOS
                    res["cruces"].append({"solucion_de": a, "aprueba": b, "esperado": esperado})
                    if not esperado:
                        res["fallos"].append(f"la solución de {a} aprueba también {b}")
    res["ok"] = not res["fallos"]
    res["fin"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    return res


# --- bucle con un cerebro -------------------------------------------------------------------------------------------------
def leer_filas(evidencia: Path) -> list:
    f = Path(evidencia) / "peticiones.jsonl"
    out = []
    if f.is_file():
        for l in f.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(l))
            except json.JSONDecodeError:                     # última línea cortada: ese intento se repite
                break
    return out


def pendientes(modelo: str, ids: list, evidencia: Path) -> list:
    filas = [f for f in leer_filas(evidencia) if f["modelo"] == modelo]
    out = []
    for id_ in ids:
        de_la_tarea = [f for f in filas if f["tarea"] == id_]
        if not any(f["aprobado"] for f in de_la_tarea) and len(de_la_tarea) < INTENTOS:
            out.append(id_)
    return out


def correr_modelo(modelo: str, ids: list, evidencia: Path, salida_blender: Path, completar, parar=lambda: False,
                  reloj=time.monotonic, probar_fn=probar) -> str:
    """Recorre las tareas pendientes; «completo» o «parado». Reanuda desde peticiones.jsonl (el intento a medias se repite)."""
    evidencia = Path(evidencia)
    for id_ in ids:
        hechas = [f for f in leer_filas(evidencia) if f["modelo"] == modelo and f["tarea"] == id_]
        while not any(f["aprobado"] for f in hechas) and len(hechas) < INTENTOS:
            if parar():
                escribir(evidencia / "estado.json", {"modelo": modelo, "tarea": id_, "intento": len(hechas) + 1, "parado": True,
                                                     "fecha": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                                     "reanudar": "la misma orden con --reanudar"})
                return "parado"
            intento = len(hechas) + 1
            t0 = reloj()
            texto, tokens, fin = completar(mensajes(T.TAREAS[id_], hechas[-1] if hechas else None), TOKENS)
            t_gen = round(reloj() - t0, 2)
            script = extraer_script(texto)
            carpeta = Path(salida_blender) / modelo / f"{id_}_i{intento}_{int(time.time())}"
            r, v = probar_fn(id_, script, carpeta, salida_blender)
            fila = {"modelo": modelo, "tarea": id_, "intento": intento, "texto": texto, "script": script, "tokens": tokens,
                    "finish_reason": fin, "segundos_cerebro": t_gen, "segundos_blender": r.get("segundos"),
                    "estado": r["estado"], "aprobado": v["aprobado"], "cumplidas": v.get("cumplidas", 0),
                    "total": v.get("total", len(T.TAREAS[id_]["comprobaciones"])), "feedback": v["texto"],
                    "motivos_filtro": (r.get("filtro") or {}).get("motivos", []), "carpeta": str(carpeta),
                    "base_intacta": (r.get("base") or {}).get("intacta"), "fecha": time.strftime("%Y-%m-%dT%H:%M:%S")}
            with (evidencia / "peticiones.jsonl").open("a", encoding="utf-8", newline="\n") as fh:
                fh.write(json.dumps(fila, ensure_ascii=False) + "\n")
            hechas.append(fila)
            escribir(evidencia / "estado.json", {"modelo": modelo, "tarea": id_, "intento": intento, "parado": False,
                                                 "fecha": fila["fecha"]})
            if fila["base_intacta"] is False:
                raise RuntimeError("un .blend de partida cambió: se para y se conserva la evidencia")
    return "completo"


# «permitir_uso» (usuario, 2026-11-15: «relaja el guardia»): el PC se usa a la vez, así que NO se mira si hay una
# persona (teclado/ratón, aplicación en primer plano). Se mantienen la VRAM ajena ≤ 1992 MiB, el uso de GPU ≤ 40 %, el
# tope de VRAM durante la tarea, la térmica y el STOP.
SIN_PERSONA = lambda *a, **k: {"hay": False, "motivos": [], "inactividad_s": None}
ENFRIAR_DESDE_C, ENFRIAR_HASTA_C = 74, 66          # con el PC en uso: pausa entre llamadas (la térmica no cambia)
SIN_ACTIVIDAD = lambda:{"inactividad_s": 1e9, "sesiones": {}, "notificacion": None, "motivos": []}


def _esperar_sin_persona(fondo, cond, ventana_s, max_espera_s, dormir, reloj):
    """`esperar_v4` sin su propia consulta de persona (que no pasa por `cond`): fondo detenido y recursos."""
    if fondo is not None and not fondo.liberar():
        return {"ok": False, "recursos": ["fondo_no_detenido"], "motivos": ["fondo_no_detenido"], "intentos": 1,
                "esperado_s": 0.0}
    return cond(ventana_s) | {"intentos": 1, "esperado_s": 0.0}


def ejecutar(externos: Path, evidencia: Path, salida_blender: Path, modelos=MODELOS, ids=None, reanudar=False,
             correr=None, pendientes_fn=None, permitir_uso=False) -> dict:
    from eq3 import evaluar_f1 as EV
    from eq3 import evaluar_f1_v5 as V
    from eq3 import evaluar_f1_vram_exp as X
    from eq3 import servidor_pc
    from lab_vram import banco_capacidad as BC
    B = V.B
    reg_original = _con_cerebros_lab(BC, V, B, externos)
    evidencia, salida_blender = Path(evidencia), Path(salida_blender)
    ids = list(ids or T.TAREAS)
    if evidencia.exists() and not reanudar:
        raise SystemExit(f"{evidencia} ya existe: usa --reanudar para continuar, o elige otra carpeta")
    for id_ in ids:
        b = base_de(T.TAREAS[id_], salida_blender)
        if b and not b.is_file():
            raise SystemExit(f"falta {b}: ejecuta antes la orden «validar»")
    if not EJ.blender_exe():
        raise SystemExit("no encuentro Blender (no se instala nada)")
    evidencia.mkdir(parents=True, exist_ok=True)
    res = {"inicio": time.strftime("%Y-%m-%dT%H:%M:%S"), "modo": "REAL", "modelos": list(modelos), "tareas": ids,
           "intentos": INTENTOS, "tokens": TOKENS, "llama_e2": V.E2, "ctx": V.CTX, "bloques": [], "pausas": [],
           "reanudada": bool(reanudar), "salida_blender": str(salida_blender), "permitir_uso": bool(permitir_uso)}
    cond = (lambda v: B.condiciones(v, quien=SIN_PERSONA)) if permitir_uso else B.condiciones
    act = SIN_ACTIVIDAD if permitir_uso else B.actividad_vigia
    guardar = lambda: escribir(evidencia / "banco.json", res)
    B._STOP_GLOBAL = evidencia / "STOP"
    termica = B.nueva_termica(evidencia / "termica.jsonl")
    with V.entorno_v5(), B.termica_activa(termica.iniciar()), \
            B.fondo_gestionado(B.FondoAnimado(marca=evidencia / "fondo_detenido.marca")) as fondo:
        try:
            for modelo in modelos:
                arranque, reintentos = 0, 0
                while (pendientes_fn or pendientes)(modelo, ids, evidencia):
                    espera = (B.esperar_v45(fondo, pausas=res["pausas"], cond=cond, base=_esperar_sin_persona)
                              if permitir_uso else B.esperar_v45(fondo, pausas=res["pausas"]))
                    if not espera["ok"]:
                        raise EV.Abortada(f"no se puede seguir: {espera['motivos']}")
                    ok2, ver = BC.g2(externos, modelo)
                    if permitir_uso and not ok2["ok"] and not ok2.get("problemas") \
                            and (ok2.get("vram_otras_MiB") or 1e9) <= B.VRAM_OTRAS_MAX:
                        # con el PC en uso, el mismo tope de VRAM ajena que la puerta (1992 MiB, no 1100); los SHA-256
                        # de llama.cpp y del cerebro se siguen exigiendo
                        ok2 = ok2 | {"ok": True, "tope_vram_otras_MiB": B.VRAM_OTRAS_MAX}
                    res.setdefault("g2", []).append(ok2)
                    if not ok2["ok"]:
                        raise EV.Abortada(f"G2 de {modelo}: {ok2}")
                    arranque += 1
                    carpeta = evidencia / modelo / f"arranque{arranque}_{int(time.time())}"
                    lab = B._lab(carpeta, "B")
                    registro = []
                    m_lab = cerebro_lab(modelo) or {}
                    tope = m_lab.get("tope_MiB") or V.VRAM_TOPE   # gemma12: un poco más (usuario, 2026-11-15)
                    bloque_ngl = ngl_para(m_lab, ok2.get("vram_otras_MiB"), tope) if m_lab.get("ngl") else None
                    if es_solo_del_usuario(modelo, reg_original):  # modelo del usuario: topes de SU equipo
                        perfil = _perfil_usuario(externos, BC.registro(modelo), V.CTX)
                        tope = perfil["tope_vram_mib"]
                        bloque_ngl = None if perfil["entero"] else perfil["ngl"]
                        sys.path.insert(0, str(RAIZ / "perfiles"))
                        import equipo_perfil as PERF
                        espera_ram = PERF.esperar_ram(perfil["frenos"]["ram"]["necesaria_mib"], B.stop_global)
                        res.setdefault("esperas_ram", []).append({"modelo": modelo, **espera_ram})
                        if not espera_ram["ok"]:                # puerta de RAM: sin RAM libre no se carga
                            raise EV.Abortada(f"{modelo}: no hay RAM libre para cargarlo (hay {espera_ram['libre_mib']}"
                                              f" MiB, hacen falta {espera_ram['necesaria_mib']}): cierra programas")
                    B.E2 = _e2_de(modelo, V, bloque_ngl)  # dentro de entorno_v5: se deshace al salir
                    vigia = B.VigiaTermica(act=act, tope=tope).iniciar()
                    be = B.proteger_backend_v44(B.fabrica_e2(ver)(), {}, registro, "S1", termica)
                    bloque = {"modelo": modelo, "arranque": arranque, "tope_vram_MiB": tope,
                              **({"ngl": bloque_ngl} if bloque_ngl else {})}
                    res["bloques"].append(bloque)
                    B._EN_TAREA += 1
                    try:
                        be.iniciar({"lab": lab, "run_id": "B", "parar": vigia.parar})

                        def completar(msgs, max_tokens):
                            if permitir_uso:                 # con el PC en uso: enfriar antes de pedir, no rozar el freno
                                t0 = time.monotonic()
                                while ((termica.ultima or {}).get("temp_C") or 0) >= ENFRIAR_DESDE_C \
                                        and time.monotonic() - t0 < 600 and not B.stop_global():
                                    time.sleep(5)
                                    while ((termica.ultima or {}).get("temp_C") or 0) > ENFRIAR_HASTA_C \
                                            and time.monotonic() - t0 < 600 and not B.stop_global():
                                        time.sleep(5)
                                if time.monotonic() - t0 > 1:
                                    res.setdefault("enfriamientos_s", []).append(round(time.monotonic() - t0, 1))
                            r = be.completar(msgs, max_tokens, 300)
                            return (getattr(r, "texto", "") or "", getattr(r, "tokens_gen", None),
                                    getattr(r, "finish_reason", None))
                        bloque["fin"] = (correr or correr_modelo)(modelo, ids, evidencia, salida_blender, completar,
                                                                   parar=B.stop_global)
                    except Exception as e:                   # corte del vigía, térmica, STOP o fallo del servidor
                        bloque["corte"] = f"{type(e).__name__}: {getattr(e, 'motivo', e)}"
                    finally:
                        B._EN_TAREA -= 1
                        d = be.detener()
                        bloque["vigia"] = vigia.detener()
                        bloque["cierre_limpio"] = d["limpio"]
                        bloque["e2"] = _e2_ok(modelo, V, carpeta, bloque_ngl)
                        guardar()
                    if B.stop_global() or termica.critico:
                        raise EV.Abortada(f"stop o térmica crítica: {termica.critico}; punto en estado.json")
                    if not bloque["e2"]["ok"] or not d["limpio"]:
                        raise EV.Abortada(f"{modelo}: arranque sin E2 de V5 o cierre sucio")
                    if (pendientes_fn or pendientes)(modelo, ids, evidencia):
                        if X.por_vram(bloque["vigia"].get("excedida")) or reintentos >= MAX_REINTENTOS:
                            raise EV.Abortada(f"{modelo}: {bloque.get('corte')} (reintentos {reintentos})")
                        reintentos += 1
        except (EV.Abortada, KeyboardInterrupt) as e:
            res["abortada"] = f"{type(e).__name__}: {e}"
        finally:
            termica.detener()
            B._STOP_GLOBAL = None
            res["termica"] = termica.resumen()
            res["llama_al_final"] = servidor_pc.procesos_llama()
            res["fin"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            BC.registro = reg_original
            guardar()
    try:                                                     # el formato de filas de banco.py (otros bancos tienen su informe)
        res["analisis"] = analizar(leer_filas(evidencia))
    except (KeyError, TypeError) as e:
        res["analisis"] = {"no_aplica": f"{type(e).__name__}: {e}"}
    guardar()
    return res


# --- análisis e informe ---------------------------------------------------------------------------------------------------
def analizar(filas: list) -> dict:
    out = {}
    for m in dict.fromkeys(f["modelo"] for f in filas):
        fm = [f for f in filas if f["modelo"] == m]
        por = {}
        for f in fm:
            por.setdefault(f["tarea"], []).append(f)
        tareas = {}
        for id_, fs in por.items():
            ultimo = fs[-1]
            tareas[id_] = {"aprobada": any(f["aprobado"] for f in fs), "intentos": len(fs),
                           "aprobada_en": next((f["intento"] for f in fs if f["aprobado"]), None),
                           "estados": [f["estado"] for f in fs], "ultimo": f"{ultimo['cumplidas']}/{ultimo['total']}",
                           "mejora": [f"{f['cumplidas']}/{f['total']}" for f in fs],
                           "mejor_fraccion": max((f["cumplidas"] / f["total"] if f["total"] else 0.0) for f in fs)}
        peligro = [f for f in fm if f["estado"] == "RECHAZADO"]
        out[m] = {"tareas": tareas, "n_tareas": len(por),
                  "aprobadas_a_la_primera": sum(t["aprobada_en"] == 1 for t in tareas.values()),
                  "aprobadas": sum(t["aprobada"] for t in tareas.values()),
                  "puntuacion_parcial": round(sum(t["mejor_fraccion"] for t in tareas.values()), 2),
                  "aprobadas_gracias_a_corregir": sum((t["aprobada_en"] or 0) > 1 for t in tareas.values()),
                  "intentos": len(fm), "por_estado": {e: sum(f["estado"] == e for f in fm) for e in
                                                      dict.fromkeys(f["estado"] for f in fm)},
                  "rechazos_del_filtro": [{"tarea": f["tarea"], "intento": f["intento"], "motivos": f["motivos_filtro"][:3]}
                                          for f in peligro],
                  "cortes_por_tope": sum(f.get("finish_reason") == "length" for f in fm),
                  "bases_intactas": all(f.get("base_intacta") is not False for f in fm),
                  "segundos_cerebro_mediana": sorted(f["segundos_cerebro"] for f in fm)[len(fm) // 2] if fm else None}
    return out


def estado(evidencia: Path) -> dict:
    evidencia = Path(evidencia)
    filas = leer_filas(evidencia)
    b = {}
    try:
        b = json.loads((evidencia / "banco.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    return {"carpeta": str(evidencia), "intentos_hechos": len(filas),
            "por_modelo": {m: {"tareas_vistas": len({f["tarea"] for f in filas if f["modelo"] == m}),
                               "aprobadas": len({f["tarea"] for f in filas if f["modelo"] == m and f["aprobado"]})}
                           for m in dict.fromkeys(f["modelo"] for f in filas)},
            "stop_pedido": (evidencia / "STOP").exists(), "terminada": bool(b.get("fin")), "abortada": b.get("abortada"),
            "fin": b.get("fin")}


def informe(evidencia: Path) -> str:
    evidencia = Path(evidencia)
    filas = leer_filas(evidencia)
    an = analizar(filas)
    e = estado(evidencia)
    L = ["# Banco de Blender: informe", "", f"Carpeta: `{evidencia}`", "",
         f"Estado: {'terminada' if e['terminada'] else 'sin terminar'}; intentos {e['intentos_hechos']}" +
         (f"; abortada: {e['abortada']}" if e["abortada"] else ""), "",
         "Aprueba el verificador sin IA (medidas de la escena), no un cerebro. Hasta "
         f"{INTENTOS} intentos por tarea: tras cada fallo el cerebro recibe lo medido y corrige.", ""]
    ids = list(dict.fromkeys(f["tarea"] for f in filas))
    L += ["| tarea | " + " | ".join(an) + " |", "|---|" + "---|" * len(an)]
    for id_ in ids:
        celdas = []
        for m in an:
            t = an[m]["tareas"].get(id_)
            celdas.append("–" if not t else (f"✔ al intento {t['aprobada_en']}" if t["aprobada"] else
                                             f"✘ ({' → '.join(t['mejora'])}; {t['estados'][-1]})"))
        L.append(f"| {id_} | " + " | ".join(celdas) + " |")
    for m, d in an.items():
        L += ["", f"## {m}", "",
              f"- aprobadas: {d['aprobadas']}/{d['n_tareas']} (a la primera {d['aprobadas_a_la_primera']}; gracias a corregir "
              f"{d['aprobadas_gracias_a_corregir']})",
              f"- puntuación parcial: {d['puntuacion_parcial']}/{d['n_tareas']} (suma, por tarea, de la mejor fracción de "
              "comprobaciones cumplidas; no cambia el aprobado)",
              f"- intentos: {d['intentos']}; por estado: {d['por_estado']}; respuestas cortadas por longitud: {d['cortes_por_tope']}",
              f"- scripts rechazados por el filtro de seguridad: {len(d['rechazos_del_filtro'])}" +
              ("".join(f"\n  - {r['tarea']} intento {r['intento']}: {'; '.join(r['motivos'])}" for r in d["rechazos_del_filtro"][:8])),
              f"- los .blend de partida quedaron intactos: {'sí' if d['bases_intactas'] else 'NO'}",
              f"- mediana de segundos del cerebro por intento: {d['segundos_cerebro_mediana']} (no decide nada)"]
    L += ["", "Tareas: " + "; ".join(f"{i} = {T.TAREAS[i]['enunciado'][:70]}…" for i in ids), ""]
    texto = "\n".join(L)
    escribir(evidencia / "INFORME.md", texto)
    escribir(evidencia / "analisis.json", an)
    return texto


def videos(evidencia: Path, salida_blender: Path, resolucion=(960, 540)) -> dict:
    """Con los cerebros ya descargados: renderiza el último script ejecutable de cada tarea (vídeo si es animada)."""
    filas, out = leer_filas(evidencia), {}
    destino = Path(salida_blender) / f"videos_{Path(evidencia).name}"
    ultimos = {}
    for f in filas:
        if f["estado"] in ("OK",):
            ultimos[(f["modelo"], f["tarea"])] = f
    for (m, id_), f in ultimos.items():
        carpeta = destino / m / f"{id_}_{'aprobada' if f['aprobado'] else 'fallida'}"
        if carpeta.exists():
            continue
        animada = T.TAREAS[id_].get("animada")
        render = {"motor": "BLENDER_EEVEE", "resolucion": list(resolucion), "video": bool(animada),
                  "fotogramas": [] if animada else [1]}
        r, v = probar(id_, f["script"], carpeta, salida_blender, render=render)
        out[f"{m}/{id_}"] = {"estado": r["estado"], "aprobado": v["aprobado"],
                             "archivos": ((r.get("informe") or {}).get("render") or {}).get("archivos"), "carpeta": str(carpeta)}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("orden", choices=("validar", "ejecutar", "estado", "informe", "videos"))
    ap.add_argument("rutas", nargs="+")
    ap.add_argument("--modelos", nargs="+", default=list(MODELOS))
    ap.add_argument("--tareas", nargs="+")
    ap.add_argument("--reanudar", action="store_true")
    ap.add_argument("--tokens", type=int, default=None, help="tope de tokens por respuesta (800 por defecto; la tanda 4 usa 1200)")
    ap.add_argument("--manual", default=None, help="archivo de manual de recetas que se añade al prompt del sistema")
    a = ap.parse_args(argv)
    if a.orden == "validar":
        r = validar(Path(a.rutas[0]))
        if len(a.rutas) > 1:
            escribir(Path(a.rutas[1]), r)
        print(json.dumps({k: r[k] for k in ("ok", "fallos", "cruces")}, ensure_ascii=False, indent=1))
        for id_, x in r["referencias"].items():
            print(id_, "referencia", "APRUEBA" if x["aprobado"] else "FALLA", f"{x['cumplidas']}/{x['total']}",
                  "| vacío:", f"{r['vacio'][id_]['cumplidas']}/{r['vacio'][id_]['total']}", "" if x["aprobado"] else x["texto"])
        return 0 if r["ok"] else 1
    if a.orden == "estado":
        print(json.dumps(estado(Path(a.rutas[0])), ensure_ascii=False, indent=1))
        return 0
    if a.orden == "informe":
        print(informe(Path(a.rutas[0])))
        return 0
    if a.orden == "videos":
        print(json.dumps(videos(Path(a.rutas[0]), Path(a.rutas[1])), ensure_ascii=False, indent=1))
        return 0
    global TOKENS
    global MANUAL
    if a.manual:
        MANUAL = '\n\nMANUAL DE REFERENCIA:\n' + Path(a.manual).read_text(encoding='utf-8')
    TOKENS = a.tokens or TOKENS
    r = ejecutar(Path(a.rutas[0]), Path(a.rutas[1]), Path(a.rutas[2]), tuple(a.modelos), a.tareas, a.reanudar)
    print(json.dumps({k: r.get(k) for k in ("inicio", "fin", "abortada", "llama_al_final")}, ensure_ascii=False, indent=1))
    return 0 if not r.get("abortada") else 1


if __name__ == "__main__":
    sys.exit(main())
