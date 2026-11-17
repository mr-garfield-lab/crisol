"""Equipo IA V3.1 F1 — variante «F1-V5.1» (`docs/V31_F1_V5_1.md`): V5 + corrección del falso positivo de T08 + 6 cerebros.

    python -B -X utf8 eq3/lanzador_eq2.py eq3/evaluar_f1_v5_1.py puertas  EXTERNOS SALIDA_v5_1_puertasN
    python -B -X utf8 eq3/lanzador_eq2.py eq3/evaluar_f1_v5_1.py cribado  EXTERNOS SALIDA_v5_1_cribadoN --puertas P.json
    python -B -X utf8 eq3/lanzador_eq2.py eq3/evaluar_f1_v5_1.py equipo   EXTERNOS SALIDA_v5_1_equipoN  --puertas P.json
                                                                          --cribado SALIDA_v5_1_cribadoN/comparacion.json
    (parar a mano, de forma ordenada, en cualquier momento:  crear el archivo SALIDA/STOP)

V5.1 REUTILIZA F1-V5 (`evaluar_f1_v5.py`, que NO cambia) y, con él, F1-VRAM-EXP-V4.5.1 sin tocarlos. Cambia TRES cosas:

1. **Control de fugas y continuación** (el aborto de T08 en equipo1, diagnosticado en `evidencias/v31_f1_v5/diagnostico_t08`).
   Cuando una respuesta se corta por el tope de tokens, V2-F.1 la continúa reenviando el prompt MÁS un mensaje
   «assistant» con esa misma respuesta (prefill). El control de V4.3 miraba ese eco como si fuera texto del evaluador y,
   si la respuesta del propio modelo contenía el literal del oráculo, abortaba. `proteger_backend_v51` excluye del texto
   comprobado SOLO un mensaje «assistant» cuyo contenido es, byte a byte (SHA-256), una respuesta que ESTE servidor
   devolvió en ESTA tarea; lo anota (`ecos_verificados`). Cualquier otro mensaje, y cualquier eco modificado, se comprueba
   exactamente como antes (fallo cerrado). El resto de la lógica (`fugas_con_procedencia`) no cambia.
2. **Seis cerebros** (`eq3/modelos_v5_1.json`): los 4 de V5 + Gemma 4 E4B y Ministral 3 8B (aptos en el banco de capacidad).
   Cribado S1 de las 15 tareas con los 6, con la misma regla prerregistrada de V5 (`elegir_equipo`).
3. **Descanso al empezar cada bloque** (cerebro/configuración): al menos 60 s y hasta ≤ 55 °C y sin freno de software
   (máx. 300 s; si no se alcanza, se anota y sigue el protocolo normal). NO cambia ningún límite térmico: 60 °C antes de
   cada petición, crítico a 88 °C, freno de software ≥ 20 s, STOP y atribución de origen son los de V4.5.1.

Todo lo demás (E2 de V5: caché q8_0, contexto 4096, `--reasoning off`; límites de VRAM; tareas; prompts; temperatura;
semillas; oráculo estático; reglas de decisión) es el de V5. Las fases se lanzan a mano y solo con las puertas superadas.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from contextlib import contextmanager
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
from eq3 import evaluar_f1 as EV  # noqa: E402
from eq3 import evaluar_f1_v5 as V  # noqa: E402
from eq3 import evaluar_f1_vram_exp as X  # noqa: E402
from eq3 import servidor_pc  # noqa: E402

B = V.B
VARIANTE = "F1-V5.1"
MODELOS_JSON = RAIZ / "eq3" / "modelos_v5_1.json"
ORDEN_MODELOS = ("qwen25", "qwen3", "granite", "yi", "gemma4", "ministral3")
PRERREGISTRO = RAIZ / "evaluacion_f1" / "PRERREGISTRO_F1_V5_1.json"
DESCANSO_BLOQUE_S = 60              # descanso mínimo al empezar un bloque
T_INICIO_BLOQUE = 55                # °C: objetivo antes de la primera petición de un bloque
MAX_ESPERA_BLOQUE_S = 300           # si no se alcanza, se anota y sigue el protocolo normal (60 °C antes de cada petición)
PUERTAS = V.PUERTAS + ("G17",)


# --- 1. el eco de la continuación (prefill) ----------------------------------------------------------------------------
def proteger_backend_v51(be, oraculos: dict, registro: list, configuracion=None):
    """`B.proteger_backend_v43` + el eco verificado: un mensaje «assistant» que repite BYTE A BYTE una respuesta que este
    servidor devolvió en esta tarea no cuenta como texto del evaluador. Todo lo demás se comprueba igual."""
    from eq2 import config
    original, respuestas, estado = be.completar, [], {"expuesto": False}

    def completar(mensajes, max_tokens, plazo_s):
        propias = {r["sha256"] for r in respuestas}
        visibles, ecos = [], []
        for m in mensajes:
            if isinstance(m, dict) and m.get("role") == "assistant" and isinstance(m.get("content"), str):
                h = hashlib.sha256(m["content"].encode("utf-8")).hexdigest()
                if h in propias:
                    ecos.append(h)
                    continue
            visibles.append(m)
        completo = "\n".join(str(m.get("content", "")) for m in mensajes if isinstance(m, dict))
        texto = "\n".join(str(m.get("content", "")) for m in visibles if isinstance(m, dict))
        fugas, relevos = B.fugas_con_procedencia(texto, oraculos, [] if estado["expuesto"] else respuestas,
                                                 configuracion)
        if fugas:
            estado["expuesto"] = True
            registro.append({"fuga": fugas})
            raise EV.FugaDeOraculo(f"texto del oráculo en un prompt: {fugas}")
        entrada = {"sha256": hashlib.sha256(completo.encode("utf-8")).hexdigest(), "caracteres": len(completo),
                   "temperatura": config.TEMPERATURA, "semilla": config.SEMILLA, "max_tokens": max_tokens}
        if relevos:
            entrada["relevos_verificados"] = relevos
        if ecos:
            entrada["ecos_verificados"] = ecos
        registro.append(entrada)
        r = original(mensajes, max_tokens, plazo_s)
        salida = getattr(r, "texto", r)
        if isinstance(salida, str):
            respuestas.append({"norm": B._norm(salida), "sha256": hashlib.sha256(salida.encode("utf-8")).hexdigest()})
        return r
    be.completar = completar
    return be


# --- 3. descanso al empezar un bloque ---------------------------------------------------------------------------------
def descanso_inicio_bloque(termica, descanso_s=DESCANSO_BLOQUE_S, objetivo=T_INICIO_BLOQUE, max_s=MAX_ESPERA_BLOQUE_S,
                           dormir=time.sleep, reloj=time.monotonic) -> dict:
    """Espera `descanso_s` y luego hasta `objetivo` °C sin freno de software (máx. `max_s` en total). No marca nada como
    crítico: si no se alcanza, lo anota y el protocolo normal (≤ 60 °C antes de cada petición) sigue mandando."""
    t0 = reloj()
    dormir(descanso_s)
    while True:
        lec = termica.muestrear()
        temp = lec.get("temp_C")
        alcanzado = temp is not None and temp <= objetivo and not lec.get("freno_sw_termico")
        parada = termica.motivo_parada()
        if alcanzado or parada or reloj() - t0 >= max_s:
            return {"ok": bool(alcanzado), "esperado_s": round(reloj() - t0, 1), "temp_C": temp, "objetivo_C": objetivo,
                    "parada": parada}
        dormir(termica.intervalo)


# --- entorno -------------------------------------------------------------------------------------------------------
@contextmanager
def entorno_v5_1():
    """En ESTE proceso y solo durante el bloque: V5 usa los 6 cerebros y V4.5.1 usa el control de fugas con eco
    verificado (además de lo que ya hace `V.entorno_v5`). Se deshace siempre al salir."""
    antes = (V.MODELOS_JSON, V.ORDEN_MODELOS, B.proteger_backend_v43)
    V.MODELOS_JSON, V.ORDEN_MODELOS, B.proteger_backend_v43 = MODELOS_JSON, ORDEN_MODELOS, proteger_backend_v51
    try:
        with V.entorno_v5():
            yield
    finally:
        V.MODELOS_JSON, V.ORDEN_MODELOS, B.proteger_backend_v43 = antes


# --- prerregistro -----------------------------------------------------------------------------------------------------
ARCHIVOS_V5_1 = [
    "eq3/evaluar_f1_v5_1.py", "eq3/modelos_v5_1.json", "pruebas/test_eq3_evaluar_f1_v5_1.py",
    "v3/mutaciones/v31_f1_v5_1.json", "evaluacion_f1/prerregistrar_v5_1.py", "docs/V31_F1_V5_1.md",
    # V5 conservada: código, pruebas, mutaciones, prerregistro y la evidencia que motiva V5.1
    "eq3/evaluar_f1_v5.py", "eq3/modelos_v5.json", "pruebas/test_eq3_evaluar_f1_v5.py", "v3/mutaciones/v31_f1_v5.json",
    "evaluacion_f1/prerregistrar_v5.py", "evaluacion_f1/PRERREGISTRO_F1_V5.json", "docs/V31_F1_V5.md",
    "evidencias/v31_f1_v5/puertas2/puertas.json", "evidencias/v31_f1_v5/cribado1/comparacion.json",
    "evidencias/v31_f1_v5/equipo1/comparacion.json", "evidencias/v31_f1_v5/diagnostico_t08/diagnostico.json",
    "evidencias/v31_f1_v5/diagnostico_t08/diario_control_fugas.json", "evidencias/v31_f1_v5/banco1/analisis.json",
    "lab_vram/banco_modelos_extra.json", "evaluacion_f1/PRERREGISTRO_BANCO_CAPACIDAD_V5.json",
    # V4.5.1 (la base de V5) sigue protegida por el prerregistro de V5
    "evaluacion_f1/PRERREGISTRO_F1_VRAM_EXP_v4_5_1.json", "eq3/evaluar_f1_vram_exp_v4_5_1.py", "eq3/termica_v4_5.py",
    "eq3/externos_f1.json", "eq3/servidor_pc.py"]


def huella_codigo() -> dict:
    return V.huella_codigo() | {a: hashlib.sha256((RAIZ / a).read_bytes()).hexdigest() if (RAIZ / a).is_file()
                                else None for a in ("eq3/evaluar_f1_v5_1.py", "eq3/modelos_v5_1.json",
                                                    "evaluacion_f1/PRERREGISTRO_F1_V5_1.json")}


def comprobar_v5_1() -> list:
    if not PRERREGISTRO.is_file():
        return ["falta PRERREGISTRO_F1_V5_1.json"]
    pre = json.loads(PRERREGISTRO.read_text(encoding="utf-8"))
    dif = [rel for rel, h in pre["sha256"].items()
           if not (RAIZ / rel).is_file() or hashlib.sha256((RAIZ / rel).read_bytes()).hexdigest() != h]
    lim = pre.get("limites", {})
    if pre.get("variante") != VARIANTE or pre.get("llama_e2") != V.E2 or pre.get("ctx") != V.CTX \
            or lim.get("vram_tope_MiB") != V.VRAM_TOPE or lim.get("vram_otras_max_MiB") != V.VRAM_OTRAS_MAX \
            or lim.get("pico_max_MiB") != V.PICO_MAX or pre.get("orden_cribado") != list(ORDEN_MODELOS) \
            or pre.get("descanso_bloque") != {"descanso_s": DESCANSO_BLOQUE_S, "objetivo_C": T_INICIO_BLOQUE,
                                              "max_s": MAX_ESPERA_BLOQUE_S}:
        dif.append("variante, E2, contexto, límites, orden del cribado o descanso del prerregistro V5.1")
    return dif + [f"V5:{d}" for d in V.comprobar_v5()]


# --- bucle de V5.1: el de V5 con el descanso al empezar cada bloque -----------------------------------------------------
def ejecutar_bloques(res, salida, tareas, oraculos, ids, bloques, ejecutar, g2_fn, esperar, vigia_fn, descanso,
                     guardar=lambda: None):
    abortada = None
    for rep, etiqueta, base, crear_fabrica, modelos in bloques:
        bloque = {"repeticion": rep, "configuracion": etiqueta, "modelos": modelos, "G2": {}}
        res["bloques"].append(bloque)
        vers = {}
        if abortada is None:
            for rol, m in modelos.items():
                ok2, vers[rol] = g2_fn(m)
                bloque["G2"][rol] = ok2
                if not ok2["ok"]:
                    espera = esperar()
                    bloque.setdefault("espera_G2", {})[rol] = espera
                    ok2, vers[rol] = g2_fn(m)
                    bloque["G2"][rol] = ok2
                    if not (espera["ok"] and ok2["ok"]):
                        abortada = f"G2 no pasa al empezar el bloque {etiqueta} ({m})"
                        break
            if abortada is None:
                bloque["descanso"] = descanso()
        for tid in ids:
            carpeta = salida / f"r{rep}" / etiqueta.replace("@", "_").replace("+", "_") / tid
            interrumpidos = []
            if abortada is not None:
                fila = X._fila_no_concluyente(base, tid, f"evaluacion_abortada: {abortada}")
            else:
                while True:
                    espera = esperar()
                    if not espera["ok"]:
                        abortada = f"terceros_o_gpu_tras_{espera['esperado_s']}s: {espera['motivos']}"
                        fila = X._fila_no_concluyente(base, tid, f"evaluacion_abortada: {abortada}")
                        break
                    vigia = vigia_fn().iniciar()
                    intento = carpeta / f"intento{len(interrumpidos) + 1}"
                    try:
                        fila = ejecutar(base, tareas[tid], oraculos[tid], oraculos, intento, crear_fabrica(vers), vigia)
                    finally:
                        vram = vigia.detener()
                    fila["vram"], fila["espera_previa"] = vram, espera
                    if X.por_vram(vigia.excedida):
                        abortada = vigia.excedida
                        break
                    if X.por_terceros(vigia.excedida) and len(interrumpidos) < X.MAX_INTERRUPCIONES:
                        interrumpidos.append({"intento": intento.name, "motivo": vigia.excedida, "vram": vram})
                        continue
                    break
            fila["repeticion"], fila["intentos_interrumpidos"] = rep, interrumpidos
            fila["bloque_v5_1"], fila["modelos"] = etiqueta, modelos
            carpeta.mkdir(parents=True, exist_ok=True)
            (carpeta / "fila.json").write_text(json.dumps(fila, ensure_ascii=False, indent=1, default=str),
                                               encoding="utf-8")
            ev, met = fila["evaluacion"], fila.get("metricas") or {}
            res["filas"].append({"repeticion": rep, "configuracion": etiqueta, "base": base, "tarea": tid,
                                 "modelos": modelos, "categoria": ev["categoria"], "calidad": ev["calidad"],
                                 "seguridad": ev["seguridad"], "motivo": ev["motivo"],
                                 "segundos_total": fila.get("segundos_total"), "tokens_prompt": met.get("tokens_prompt"),
                                 "tokens_generados": met.get("tokens_generados"),
                                 "infraestructura": fila.get("infraestructura"),
                                 "interrupciones_por_terceros": len(interrumpidos),
                                 "prompt_primer_paso_sha256": fila.get("prompt_primer_paso_sha256")})
            guardar()
    res["abortada_en_bucle"] = abortada
    return res


def evaluar(fase: str, externos: Path, salida: Path, puertas_json: Path, cribado_json: Path | None = None) -> dict:
    from eq3 import majflt_windows
    if "v5_1" not in str(salida).lower():
        raise EV.Abortada("los resultados de V5.1 van en una carpeta con «v5_1» en la ruta")
    pu = json.loads(puertas_json.read_text(encoding="utf-8"))
    if pu.get("variante") != VARIANTE or not pu.get("ok"):
        raise EV.Abortada("las puertas de F1-V5.1 no pasaron")
    if comprobar_v5_1():
        raise EV.Abortada(f"prerregistros V1–V5.1 no intactos: {comprobar_v5_1()[:5]}")
    if pu.get("codigo") != huella_codigo():
        raise EV.Abortada("el código o el prerregistro cambiaron desde las puertas")
    with entorno_v5_1():
        if fase == "cribado":
            bloques, eleccion = V.bloques_cribado(), None
        else:
            cr = json.loads(cribado_json.read_text(encoding="utf-8"))
            if cr.get("variante") != VARIANTE or cr.get("fase") != "cribado" or not cr.get("valida"):
                raise EV.Abortada("el cribado indicado no es un cribado V5.1 válido")
            eleccion = V.elegir_equipo(cr["filas"])
            if not eleccion["ok"]:
                raise EV.Abortada(f"sin equipo: {eleccion['motivo']}")
            bloques = V.bloques_equipo(eleccion["generador"], eleccion["revisor"])
        salida.mkdir(parents=True)
        tareas, oraculos = EV.E.cargar()
        res = {"variante": VARIANTE, "fase": fase, "inicio": time.strftime("%Y-%m-%dT%H:%M:%S"), "llama_e2": V.E2,
               "ctx": V.CTX, "limites": {"vram_tope_MiB": V.VRAM_TOPE, "vram_otras_max_MiB": V.VRAM_OTRAS_MAX,
                                         "pico_max_MiB": V.PICO_MAX},
               "eleccion": eleccion, "majflt": majflt_windows.activar(salida), "filas": [], "bloques": [], "pausas": []}
        guardar = lambda: (salida / "comparacion.json").write_text(json.dumps(res, ensure_ascii=False, indent=1,
                                                                              default=str), encoding="utf-8")
        B._STOP_GLOBAL = salida / "STOP"
        termica = B.nueva_termica(salida / "termica.jsonl")
        with B.termica_activa(termica.iniciar()), \
                B.fondo_gestionado(B.FondoAnimado(marca=salida / "fondo_detenido.marca")) as fondo:
            try:
                inicio = B.esperar_v4(fondo, ventana_s=X.VENTANA_INICIO_S, max_espera_s=0)
                res["condiciones_inicio"], res["termica_inicio"] = inicio, termica.enfriar()
                if not inicio["ok"] or not res["termica_inicio"]["ok"]:
                    raise EV.Abortada(f"no se inicia: {inicio['motivos']} {res['termica_inicio']}")
                ejecutar_bloques(res, salida, tareas, oraculos, list(tareas), bloques, ejecutar=B.ejecutar_tarea_e2,
                                 g2_fn=lambda m: V.g2(externos, m),
                                 esperar=lambda: B.esperar_v45(fondo, pausas=res["pausas"]),
                                 vigia_fn=lambda: B.VigiaTermica(act=B.actividad_vigia),
                                 descanso=lambda: descanso_inicio_bloque(termica), guardar=guardar)
            except (EV.FugaDeOraculo, EV.Abortada, KeyboardInterrupt) as e:
                res["abortada"], res["valida"] = f"{type(e).__name__}: {e}", False
                res["fondo_animado"], res["termica"] = fondo.registro, termica.resumen()
                guardar()
                raise
            finally:
                termica.detener()
                B._STOP_GLOBAL = None
            res["fondo_animado"] = fondo.registro
        res["termica"], res["tiempos"] = termica.resumen(), B._tiempos(salida)
        res["valida"] = res.get("abortada_en_bucle") is None and not any(f["infraestructura"] for f in res["filas"])
        res["analisis"] = V.analizar(res["filas"])
        if fase == "cribado":
            res["analisis"]["eleccion"] = V.elegir_equipo(res["filas"])
            res["analisis"]["frente_a_qwen25"] = {m: V.supera(res["filas"], f"S1@{m}", "S1@qwen25", reps=(1,))
                                                  for m in ORDEN_MODELOS[1:]}
        else:
            g, r = eleccion["generador"], eleccion["revisor"]
            dos, uno, s1 = f"E3@{g}+{r}", f"E3@{g}", f"S1@{g}"
            res["analisis"]["hipotesis"] = {"H1_dos_supera_a_S1": V.supera(res["filas"], dos, s1),
                                            "H2_dos_supera_a_uno": V.supera(res["filas"], dos, uno),
                                            "uno_supera_a_S1": V.supera(res["filas"], uno, s1)}
        res["fin"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        guardar()
        return res


# --- puertas ---------------------------------------------------------------------------------------------------------
def regresion_t08(ver_g, ver_r, carpeta: Path) -> dict:
    """G17: el caso REAL que abortó equipo1 (T08, E3 con Qwen3 + Yi-Coder, temperatura 0): ya no debe abortar por fuga y
    debe haber pasado por una continuación con eco verificado. Es una puerta, no una fila de resultados."""
    tareas, oraculos = EV.E.cargar()
    carpeta.mkdir(parents=True)
    B._STOP_GLOBAL = carpeta / "STOP"
    termica = B.nueva_termica(carpeta / "termica.jsonl")
    out = {"tarea": "T08", "cerebros": {"generador": "qwen3", "revisor": "yi"}}
    try:
        with B.termica_activa(termica.iniciar()):
            vigia = B.VigiaTermica(act=B.actividad_vigia).iniciar()
            try:
                fila = B.ejecutar_tarea_e2("E3", tareas["T08"], oraculos["T08"], oraculos, carpeta / "T08",
                                           V.fabrica_dos(ver_g, ver_r), vigia)
                peticiones = (fila.get("metricas") or {}).get("peticiones") or []
                out.update(categoria=fila["evaluacion"]["categoria"], infraestructura=fila.get("infraestructura"),
                           ecos_verificados=sum(len(p.get("ecos_verificados", [])) for p in peticiones),
                           peticiones=len(peticiones))
            finally:
                out["vigia"] = vigia.detener()
    except EV.FugaDeOraculo as e:
        out["fuga"] = str(e)
    except EV.Abortada as e:
        out["abortada"] = str(e)
    finally:
        termica.detener()
        B._STOP_GLOBAL = None
        out["llama_despues"] = servidor_pc.procesos_llama()
    out["ok"] = bool("fuga" not in out and "abortada" not in out and not out.get("infraestructura")
                     and out.get("ecos_verificados", 0) >= 1 and not out["llama_despues"]
                     and out.get("vigia", {}).get("excedida") is None)
    return out


def g5(carpeta: Path) -> dict:
    """G5: batería de mutaciones de V5.1 (F28). Las de V1–V5 siguen valiendo porque su código no cambia (G1)."""
    from eq3 import plataforma
    tmp = carpeta / "F28"
    tmp.mkdir(parents=True)
    r = plataforma.ejecutar([sys.executable, "-B", "v3/mutacion.py", "v3/mutaciones/v31_f1_v5_1.json"], cwd=RAIZ,
                            env=plataforma.entorno_hijo(tmp), timeout=3600)
    ultima = [l for l in r.stdout.splitlines() if "FIN MUTACI" in l][-1:] or [r.stderr[-200:]]
    return {"F28": {"rc": r.returncode, "resultado": ultima[0].strip()}, "ok": r.returncode == 0}


def puertas(externos: Path, salida: Path, con_g5=True) -> dict:
    """Las 16 de V5 (con los 6 cerebros en G2 y G15) + G17, la regresión real de T08."""
    from eq3 import majflt_windows
    if "v5_1" not in str(salida).lower():
        raise EV.Abortada("las puertas de V5.1 van en una carpeta con «v5_1» en la ruta")
    salida.mkdir(parents=True)
    res = {"variante": VARIANTE, "inicio": time.strftime("%Y-%m-%dT%H:%M:%S"), "codigo": huella_codigo(),
           "llama_e2": V.E2, "ctx": V.CTX, "limites": {"vram_tope_MiB": V.VRAM_TOPE,
                                                        "vram_otras_max_MiB": V.VRAM_OTRAS_MAX,
                                                        "pico_max_MiB": V.PICO_MAX}}
    guardar = lambda: (salida / "puertas.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str),
                                                           encoding="utf-8")
    dif, g1e = comprobar_v5_1(), EV.g1()
    res["G1"] = {"ok": not dif and g1e["ok"], "diferencias": dif, "v2_y_fugas": {k: g1e[k] for k in (
        "ok", "diferencias_prerregistro", "fugas_en_enunciados")}}
    guardar()
    t51 = B._unittest("test_eq3_evaluar_f1_v5_1.py", salida / "G10" / "v5_1")
    t5 = B._unittest("test_eq3_evaluar_f1_v5.py", salida / "G10" / "v5")
    t451 = B._unittest("test_eq3_*_v4_5_1.py", salida / "G10" / "v4_5_1")
    res["G10"] = {"v5_1": t51, "v5": t5, "v4_5_1": t451, "ok": t51["rc"] == 0 and t5["rc"] == 0 and t451["rc"] == 0}
    guardar()
    res["G5"] = g5(salida / "G5") if con_g5 else {"ok": False, "motivo": "no ejecutada"}
    guardar()
    res["G11"] = B.sensores_reales(salida / "G11")
    res["G13"] = B.interferencia_externa_real(salida / "G13")
    guardar()
    llama_inicio = servidor_pc.procesos_llama()
    with entorno_v5_1(), B.fondo_gestionado(B.FondoAnimado(marca=salida / "fondo_detenido.marca")) as fondo:
        res["G6"] = B.esperar_v4(fondo, ventana_s=X.VENTANA_INICIO_S, max_espera_s=0)
        res["G7_detencion"] = {"registro": list(fondo.registro), "vram_wallpaper_MiB": B._vram_fondo()}
        res["G2"], vers = {"ok": True, "modelos": {}}, {}
        for m in ORDEN_MODELOS:
            r2, vers[m] = V.g2(externos, m)
            res["G2"]["modelos"][m] = r2
            res["G2"]["ok"] = res["G2"]["ok"] and r2["ok"]
        guardar()
        res["majflt"] = majflt_windows.activar(salida)
        previas = all(res[g]["ok"] for g in ("G1", "G2", "G6", "G11", "G13"))
        yi = vers.get("yi")
        pruebas = [("G15", lambda: {m: V.pico(vers[m], salida / "G15" / m, m) for m in ORDEN_MODELOS}),
                   ("G16", lambda: V.cambio_real(vers.get("qwen25"), vers.get("granite"), salida / "G16")),
                   ("G17", lambda: regresion_t08(vers.get("qwen3"), yi, salida / "G17")),
                   ("G3", lambda: EV._interrupcion_real(yi, salida / "G3", "stop")),
                   ("G4", lambda: EV._interrupcion_real(yi, salida / "G4", "memoria")),
                   ("G8", lambda: B.corte_vram_real(yi, salida / "G8")),
                   ("G9", lambda: B.fallo_arranque_real(yi, salida / "G9")),
                   ("G12", lambda: B.corte_termico_real(yi, salida / "G12")),
                   ("G14", lambda: B.stop_global_real(yi, salida / "G14"))]
        with B._fabrica_e2_en_ev():
            for nombre, prueba in pruebas:
                if not previas:
                    res[nombre] = {"ok": False, "motivo": "no se ejecuta: G1, G2, G6, G11 o G13 no pasaron"}
                    continue
                q = B.persona()
                if q["hay"]:
                    res[nombre] = {"ok": False, "motivo": f"persona: {q['motivos']}"}
                    previas = False
                    continue
                r = prueba()
                if nombre == "G15":
                    r = {"modelos": r, "ok": all(x["ok"] for x in r.values())}
                if nombre in ("G3", "G4"):
                    r["llama_efectiva"] = V.comprobar_logs(salida / nombre)
                    r["ok"] = r["ok"] and r["llama_efectiva"]["ok"]
                res[nombre] = r
                guardar()
                time.sleep(20)                                # pausa entre cargas: pruebas ligeras
    time.sleep(3.0)
    procs = []
    try:
        from lab_vram import wallpaper
        procs = wallpaper.procesos()
    except Exception:
        pass
    inicial = fondo.c.inicial["procesos"]
    res["G7"] = {"registro": fondo.registro, "procesos_antes": inicial, "procesos_despues": procs,
                 "vram_wallpaper_MiB_despues": B._vram_fondo(),
                 "marca_retirada": not (salida / "fondo_detenido.marca").exists()}
    res["G7"]["ok"] = bool(fondo.registro and fondo.registro[-1].get("accion") == "restaurar"
                           and fondo.registro[-1].get("ok") and res["G7"]["marca_retirada"]
                           and [p["pid"] for p in procs] == [p["pid"] for p in inicial])
    res["llama_al_final"] = servidor_pc.procesos_llama()
    res["procesos_liberados"] = res["llama_al_final"] == llama_inicio
    res["ok"] = all(res[g]["ok"] for g in PUERTAS) and res["procesos_liberados"]
    res["fin"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    guardar()
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("orden", choices=("puertas", "cribado", "equipo"))
    ap.add_argument("externos")
    ap.add_argument("salida", type=Path)
    ap.add_argument("--puertas", type=Path)
    ap.add_argument("--cribado", type=Path)
    ap.add_argument("--sin-g5", action="store_true")
    a = ap.parse_args(argv)
    servidor_pc.preparar_proceso()
    try:
        if a.orden == "puertas":
            r = puertas(Path(a.externos), a.salida, con_g5=not a.sin_g5)
            print(json.dumps({g: r[g].get("ok") for g in PUERTAS} | {"procesos_liberados": r["procesos_liberados"],
                                                                     "ok": r["ok"]}))
            return 0 if r["ok"] else 1
        r = evaluar(a.orden, Path(a.externos), a.salida, a.puertas, a.cribado)
        print(json.dumps({"valida": r["valida"], "analisis": r["analisis"]}, ensure_ascii=False, default=str)[:4000])
        return 0 if r["valida"] else 1
    except EV.Abortada as e:
        print(f"ABORTADA: {e}")
        return 2
    except EV.FugaDeOraculo as e:
        print(f"ABORTADA POR FUGA DEL ORÁCULO: {e}")
        return 3


if __name__ == "__main__":
    sys.exit(main())
