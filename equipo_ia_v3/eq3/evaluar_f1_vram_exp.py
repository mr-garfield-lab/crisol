"""Equipo IA V3.1 F1 — variante EXPERIMENTAL «F1-VRAM-EXP» del ejecutor (`docs/V31_F1_VRAM_EXP.md`).

    python -B -X utf8 eq3/lanzador_eq2.py eq3/evaluar_f1_vram_exp.py sondear  [SEGUNDOS]
    python -B -X utf8 eq3/lanzador_eq2.py eq3/evaluar_f1_vram_exp.py puertas  EXTERNOS SALIDA_NUEVA
    python -B -X utf8 eq3/lanzador_eq2.py eq3/evaluar_f1_vram_exp.py comparar EXTERNOS SALIDA_NUEVA --puertas PUERTAS.json

La configuración ESTABLE (`eq3/evaluar_f1.py`, tope 6144 MiB, prerregistro V2) no se toca: este módulo la REUTILIZA
(mismas tareas, oráculos, prompts, `ejecutar_tarea`, análisis y regla) y solo cambia, de forma separada y reversible
(basta con no usar este archivo):

- **Tope de VRAM total 6912 MiB** (autorizado por el usuario) en lugar de 6144. Si se supera, se detiene la tarea en
  curso (STOP de V2-F.1 / corte de la petición) y se ABORTA TODA la evaluación experimental; solo se cierra el servidor
  que lanzó Equipo IA (`ejecutar_tarea` → `be.detener()`), nunca otro proceso.
- **VRAM de otras aplicaciones ≤ 1832 MiB** antes de cada tarea (6912 − 4780 de pico medido de Qwen − 300 de margen;
  la estable usaba 1500 con el tope 6144) y **estable** (variación ≤ 200 MiB y uso de la GPU ≤ 40 % en la ventana).
- **Terceros**: no empieza (ni sigue con la tarea siguiente) si hay otra sesión de Windows activa, una aplicación a
  pantalla completa o en presentación, o entrada de teclado/ratón en los últimos 10 minutos; espera hasta 1 h y, si
  persiste, aborta. Si aparece entrada o una sesión ajena A MITAD de una tarea, la tarea se detiene, se espera y se
  REPITE desde cero (máximo 2 interrupciones por tarea; los intentos interrumpidos se registran y no se puntúan).
- Las salidas deben estar en una carpeta cuyo nombre contenga «vram_exp»: los resultados quedan separados de los del
  límite estable. Todo lo demás (STOP, monitor de memoria, propiedad del proceso, fugas del oráculo) es lo de siempre.

Nada se ejecuta: el código de los agentes solo lo analiza `eq3.evaluacion_f1` (AST y literal_eval).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
from eq3 import evaluar_f1 as EV  # noqa: E402
from eq3 import servidor_pc  # noqa: E402

VARIANTE = "F1-VRAM-EXP"
VRAM_TOPE_EXP = 6912
PICO_QWEN_MEDIDO = 4780          # máximo observado en el intento 1 (S1, generación con ctx 2048)
MARGEN_VRAM = 300
VRAM_OTRAS_MAX_EXP = VRAM_TOPE_EXP - PICO_QWEN_MEDIDO - MARGEN_VRAM          # 1832
VARIACION_OTRAS_MAX = 200        # MiB entre el mínimo y el máximo de la ventana
UTILIZACION_GPU_MAX = 40         # % de uso de la GPU (otras aplicaciones) en la ventana
INACTIVIDAD_MIN_S = 600          # sin teclado ni ratón en la sesión propia
VENTANA_INICIO_S, VENTANA_TAREA_S, INTERVALO_SONDEO_S = 60, 10, 2.0
ESPERA_REINTENTO_S, MAX_ESPERA_S = 30, 3600
MAX_INTERRUPCIONES = 2
PRERREGISTRO_V3 = RAIZ / "evaluacion_f1" / "PRERREGISTRO_F1_VRAM_EXP_v3.json"
NOTIFICACION_OCUPADA = {2: "aplicacion_ocupada", 3: "pantalla_completa_d3d", 4: "modo_presentacion"}


# --- actividad de terceros (solo consulta: no toca ninguna aplicación) ---------------------------------------------
def _windows():
    import ctypes
    from ctypes import wintypes
    return ctypes, wintypes


def inactividad_s():
    """Segundos sin teclado ni ratón en la sesión de este proceso (GetLastInputInfo), o None si no se puede saber."""
    if os.name != "nt":
        return None
    ctypes, wintypes = _windows()

    class Ultima(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]
    u = Ultima()
    u.cbSize = ctypes.sizeof(u)
    if not ctypes.WinDLL("user32").GetLastInputInfo(ctypes.byref(u)):
        return None
    ahora = ctypes.WinDLL("kernel32").GetTickCount() & 0xFFFFFFFF
    return ((ahora - u.dwTime) & 0xFFFFFFFF) / 1000.0


def sesiones():
    """{propia, consola, activas_ajenas: [ids]} con WTSEnumerateSessions, o None si no se puede saber."""
    if os.name != "nt":
        return None
    ctypes, wintypes = _windows()

    class Info(ctypes.Structure):
        _fields_ = [("SessionId", wintypes.DWORD), ("pWinStationName", wintypes.LPWSTR), ("State", ctypes.c_int)]
    k32, wts = ctypes.WinDLL("kernel32"), ctypes.WinDLL("wtsapi32")
    propia = wintypes.DWORD()
    if not k32.ProcessIdToSessionId(k32.GetCurrentProcessId(), ctypes.byref(propia)):
        return None
    p, n = ctypes.POINTER(Info)(), wintypes.DWORD()
    if not wts.WTSEnumerateSessionsW(None, 0, 1, ctypes.byref(p), ctypes.byref(n)):
        return None
    try:
        activas = [p[i].SessionId for i in range(n.value) if p[i].State == 0]          # WTSActive
    finally:
        wts.WTSFreeMemory(p)
    return {"propia": propia.value, "consola": k32.WTSGetActiveConsoleSessionId() & 0xFFFFFFFF,
            "activas_ajenas": [s for s in activas if s != propia.value]}


def notificacion():
    """SHQueryUserNotificationState (2 ocupada, 3 juego/pantalla completa D3D, 4 presentación…), o None."""
    if os.name != "nt":
        return None
    ctypes, _ = _windows()
    estado = ctypes.c_int()
    try:
        return estado.value if ctypes.WinDLL("shell32").SHQueryUserNotificationState(ctypes.byref(estado)) == 0 \
            else None
    except (AttributeError, OSError):
        return None


def utilizacion_gpu(ejecutar=subprocess.run):
    """% de uso de la GPU según nvidia-smi, o None. Solo consulta."""
    try:
        r = ejecutar(["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                     capture_output=True, text=True, timeout=15)
        return int(r.stdout.strip().splitlines()[0]) if r.returncode == 0 else None
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return None


def actividad(inactividad=inactividad_s, sesiones_fn=sesiones, notificacion_fn=notificacion) -> dict:
    """Instantánea de uso del PC por terceros. Falla CERRADO: lo que no se puede medir cuenta como ocupado."""
    s, n, i = sesiones_fn(), notificacion_fn(), inactividad()
    motivos = []
    if s is None:
        motivos.append("sesiones_no_medibles")
    else:
        if s["activas_ajenas"]:
            motivos.append(f"otra_sesion_activa_{s['activas_ajenas']}")
        if s["consola"] != s["propia"]:
            motivos.append(f"consola_en_otra_sesion_{s['consola']}")
    if n is None:
        motivos.append("notificacion_no_medible")
    elif n in NOTIFICACION_OCUPADA:
        motivos.append(NOTIFICACION_OCUPADA[n])
    if i is None:
        motivos.append("inactividad_no_medible")
    return {"inactividad_s": i, "sesiones": s, "notificacion": n, "motivos": motivos}


def condiciones(ventana_s, medir=servidor_pc.vram_mib, util=utilizacion_gpu, act=actividad,
                intervalo=INTERVALO_SONDEO_S, dormir=time.sleep, inactividad_min=INACTIVIDAD_MIN_S) -> dict:
    """¿Se puede lanzar Qwen sin molestar? Muestrea VRAM, uso de GPU y actividad durante `ventana_s` (sin Equipo IA
    cargado, la VRAM usada es la de las otras aplicaciones)."""
    vram, uso, fotos = [], [], []
    for k in range(max(1, int(ventana_s / intervalo))):
        if k:
            dormir(intervalo)
        v = medir()
        vram.append(v and v["usada"])
        uso.append(util())
        fotos.append(act())
    motivos = sorted({m for f in fotos for m in f["motivos"]})
    inact = [f["inactividad_s"] for f in fotos if f["inactividad_s"] is not None]
    if inact and min(inact) < inactividad_min:
        motivos.append(f"entrada_reciente_{round(min(inact))}s")
    if None in vram:
        motivos.append("vram_no_medible")
    elif max(vram) > VRAM_OTRAS_MAX_EXP:
        motivos.append(f"vram_otras_{max(vram)}MiB")
    elif max(vram) - min(vram) > VARIACION_OTRAS_MAX:
        motivos.append(f"vram_inestable_{min(vram)}-{max(vram)}MiB")
    if None in uso:
        motivos.append("uso_gpu_no_medible")
    elif max(uso) > UTILIZACION_GPU_MAX:
        motivos.append(f"uso_gpu_{max(uso)}pct")
    return {"ok": not motivos, "motivos": motivos, "ventana_s": ventana_s, "vram_MiB": vram, "uso_gpu_pct": uso,
            "inactividad_min_s": min(inact) if inact else None, "ultima": fotos[-1],
            "fecha": time.strftime("%Y-%m-%dT%H:%M:%S")}


def esperar_libre(cond=condiciones, ventana_s=VENTANA_TAREA_S, max_espera_s=MAX_ESPERA_S, dormir=time.sleep,
                  reloj=time.monotonic) -> dict:
    """Repite `cond` cada ESPERA_REINTENTO_S hasta que el PC esté libre o se agote `max_espera_s` (no molesta: solo mira)."""
    t0, intentos = reloj(), 0
    while True:
        c = cond(ventana_s)
        intentos += 1
        if c["ok"] or reloj() - t0 >= max_espera_s:
            return c | {"intentos": intentos, "esperado_s": round(reloj() - t0, 1)}
        dormir(ESPERA_REINTENTO_S)


class VigiaExp(EV.Vigia):
    """El vigía estable con el tope EXPERIMENTAL y, además, terceros: entrada de teclado/ratón POSTERIOR al inicio de la
    tarea, otra sesión activa o una aplicación a pantalla completa cortan la tarea (motivo «actividad_de_terceros_…»)."""

    def __init__(self, medir=servidor_pc.vram_mib, intervalo=EV.INTERVALO_VRAM_S, tope=VRAM_TOPE_EXP, act=actividad,
                 reloj=time.monotonic):
        super().__init__(medir=medir, intervalo=intervalo, tope=tope)
        self.act, self.reloj, self.t0, self.actividad_detectada = act, reloj, reloj(), None

    def _muestrear(self):
        super()._muestrear()
        if self.excedida is not None:
            return
        a = self.act()
        motivos = list(a["motivos"])
        if a["inactividad_s"] is not None and a["inactividad_s"] < self.reloj() - self.t0:
            motivos.append("entrada_durante_la_tarea")
        if motivos and self.excedida is None:
            self.actividad_detectada = a | {"motivos": motivos}
            self.excedida = "actividad_de_terceros_" + "+".join(motivos)
            for accion in list(self.acciones):
                try:
                    accion()
                except Exception:
                    pass

    def detener(self):
        return super().detener() | {"tope_MiB": self.tope, "actividad": self.actividad_detectada}


def por_vram(motivo) -> bool:
    return bool(motivo) and str(motivo).startswith("vram_excedida")


def por_terceros(motivo) -> bool:
    return bool(motivo) and str(motivo).startswith("actividad_de_terceros")


# --- prerregistro V3 y puertas ---------------------------------------------------------------------------------------
ARCHIVOS_V3 = ["evaluacion_f1/PRERREGISTRO_F1.json", "eq3/evaluar_f1_vram_exp.py",
               "pruebas/test_eq3_evaluar_f1_vram_exp.py", "pruebas/aux_evaluar_f1_vram_exp.py",
               "v3/mutaciones/v31_f1_vram_exp.json", "evaluacion_f1/prerregistrar_vram_exp.py",
               "docs/V31_F1_VRAM_EXP.md"]


def comprobar_v3() -> list:
    """Diferencias con el prerregistro V3 (incluye el V2 completo por su SHA-256); [] = intacto."""
    if not PRERREGISTRO_V3.is_file():
        return ["falta PRERREGISTRO_F1_VRAM_EXP_v3.json"]
    pre = json.loads(PRERREGISTRO_V3.read_text(encoding="utf-8"))
    dif = [rel for rel, h in pre["sha256"].items()
           if not (RAIZ / rel).is_file() or hashlib.sha256((RAIZ / rel).read_bytes()).hexdigest() != h]
    if pre.get("variante") != VARIANTE or pre.get("limites", {}).get("vram_tope_MiB") != VRAM_TOPE_EXP:
        dif.append("variante o límites del prerregistro V3")
    return dif + [f"V2:{d}" for d in EV.E.comprobar_prerregistro()]


def huella_codigo() -> dict:
    return EV.huella_codigo() | {a: hashlib.sha256((RAIZ / a).read_bytes()).hexdigest()
                                 for a in ("eq3/evaluar_f1_vram_exp.py", "evaluacion_f1/PRERREGISTRO_F1_VRAM_EXP_v3.json")}


def g1() -> dict:
    r = EV.g1()
    dif = comprobar_v3()
    return r | {"ok": r["ok"] and not dif, "diferencias_v3": dif,
                "prerregistro_v3": json.loads(PRERREGISTRO_V3.read_text(encoding="utf-8"))
                if PRERREGISTRO_V3.is_file() else None}


def g2(externos: Path) -> tuple:
    ver = servidor_pc.verificar_externos(externos)
    v = servidor_pc.vram_mib()
    ok = ver["ok"] and v is not None and v["usada"] <= VRAM_OTRAS_MAX_EXP
    return {"ok": ok, "externos": {k: ver[k] for k in ("ok", "problemas", "archivos", "segundos", "version")},
            "vram_otras_MiB": v and v["usada"], "maximo_otras_MiB": VRAM_OTRAS_MAX_EXP}, ver


def g5(carpeta: Path) -> dict:
    from eq3 import plataforma
    out = EV.g5(carpeta)
    for fase, spec in (("F19", "v31_f1_ejecutor"), ("F20", "v31_f1_vram_exp")):
        tmp = carpeta / fase
        tmp.mkdir(parents=True)
        r = plataforma.ejecutar([sys.executable, "-B", "v3/mutacion.py", f"v3/mutaciones/{spec}.json"], cwd=RAIZ,
                                env=plataforma.entorno_hijo(tmp), timeout=3600)
        ultima = [l for l in r.stdout.splitlines() if "FIN MUTACI" in l][-1:] or [r.stderr[-200:]]
        out[fase] = {"rc": r.returncode, "resultado": ultima[0].strip()}
        out["ok"] = out["ok"] and r.returncode == 0
    return out


def separada(salida: Path) -> None:
    if "vram_exp" not in str(salida).lower():
        raise EV.Abortada("los resultados de F1-VRAM-EXP van en una carpeta con «vram_exp» en el nombre, separados "
                          "de los del límite estable")


def puertas(externos: Path, salida: Path, cond=condiciones) -> dict:
    """G1 (V2 y V3 intactos), G2 (externos y VRAM ajena ≤ 1832), G6 (PC libre de terceros), G3/G4 con Qwen real SOLO
    si G1, G2 y G6 pasan, y G5 (F15–F20 + V-SRV)."""
    from eq3 import majflt_windows
    separada(salida)
    salida.mkdir(parents=True)
    res = {"variante": VARIANTE, "inicio": time.strftime("%Y-%m-%dT%H:%M:%S"), "codigo": huella_codigo()}
    guardar = lambda: (salida / "puertas.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str),
                                                           encoding="utf-8")
    res["G1"] = g1()
    guardar()
    res["G2"], ver = g2(externos)
    res["G6"] = cond(VENTANA_INICIO_S)
    guardar()
    res["majflt"] = majflt_windows.activar(salida)
    EV.preparar_contexto()
    for nombre, modo in (("G3", "stop"), ("G4", "memoria")):
        previas = res["G1"]["ok"] and res["G2"]["ok"] and res["G6"]["ok"]
        if previas and nombre == "G4":
            previas = cond(VENTANA_TAREA_S)["ok"]
        res[nombre] = EV._interrupcion_real(ver, salida / nombre, modo) if previas else \
            {"ok": False, "motivo": "no se ejecuta: G1, G2 o G6 (terceros) no pasaron"}
        guardar()
    res["G5"] = g5(salida / "G5")
    res["ok"] = all(res[g]["ok"] for g in ("G1", "G2", "G3", "G4", "G5", "G6"))
    res["fin"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    guardar()
    return res


# --- comparación experimental ----------------------------------------------------------------------------------------
def _fila_no_concluyente(c, tid, motivo) -> dict:
    return {"configuracion": c, "tarea": tid, "infraestructura": motivo,
            "evaluacion": {"categoria": "NO_CONCLUYENTE", "calidad": "NO_CONCLUYENTE", "seguridad": "sin_respuesta",
                           "motivo": motivo}, "segundos_total": 0, "metricas": {"tokens_prompt": 0, "tokens_generados": 0}}


def ejecutar_bucle(res, salida, tareas, oraculos, ids, repeticiones, ejecutar=EV.ejecutar_tarea, fabrica=None,
                   g2_fn=None, esperar=esperar_libre, vigia_fn=VigiaExp, guardar=lambda: None) -> dict:
    """Bloques y tareas en el orden prerregistrado. Antes de cada tarea espera a que el PC esté libre; una tarea cortada
    por terceros se repite desde cero (≤ MAX_INTERRUPCIONES); la VRAM por encima del tope aborta TODO lo que queda."""
    abortada = None
    for rep in repeticiones:
        for c in EV.ORDEN[rep]:
            bloque = {"repeticion": rep, "configuracion": c}
            res["bloques"].append(bloque)
            ver = None
            if abortada is None:
                ok2, ver = g2_fn() if g2_fn else ({"ok": True}, None)
                bloque["G2"] = ok2
                if not ok2["ok"]:
                    espera = esperar()
                    bloque["espera_G2"] = espera
                    ok2, ver = g2_fn() if g2_fn else ({"ok": True}, None)
                    if not (espera["ok"] and ok2["ok"]):
                        abortada = "G2 no pasa al empezar el bloque"
            for tid in ids:
                carpeta = salida / f"r{rep}" / c / tid
                interrumpidos = []
                if abortada is not None:
                    fila = _fila_no_concluyente(c, tid, f"evaluacion_abortada: {abortada}")
                else:
                    while True:
                        espera = esperar()
                        if not espera["ok"]:
                            abortada = f"terceros_o_gpu_tras_{espera['esperado_s']}s: {espera['motivos']}"
                            fila = _fila_no_concluyente(c, tid, f"evaluacion_abortada: {abortada}")
                            break
                        vigia = vigia_fn().iniciar()
                        intento = carpeta / f"intento{len(interrumpidos) + 1}"
                        try:
                            fila = ejecutar(c, tareas[tid], oraculos[tid], oraculos, intento, fabrica(ver), vigia)
                        finally:
                            vram = vigia.detener()
                        fila["vram"], fila["espera_previa"] = vram, espera
                        if por_vram(vigia.excedida):
                            abortada = vigia.excedida
                            break
                        if por_terceros(vigia.excedida) and len(interrumpidos) < MAX_INTERRUPCIONES:
                            interrumpidos.append({"intento": intento.name, "motivo": vigia.excedida, "vram": vram,
                                                  "segundos_total": fila.get("segundos_total"),
                                                  "servidor_terminado": fila.get("servidor_terminado")})
                            continue
                        break
                fila["repeticion"], fila["intentos_interrumpidos"] = rep, interrumpidos
                carpeta.mkdir(parents=True, exist_ok=True)
                (carpeta / "fila.json").write_text(json.dumps(fila, ensure_ascii=False, indent=1, default=str),
                                                   encoding="utf-8")
                ev = fila["evaluacion"]
                res["filas"].append({"repeticion": rep, "configuracion": c, "tarea": tid, "categoria": ev["categoria"],
                                     "calidad": ev["calidad"], "seguridad": ev["seguridad"], "motivo": ev["motivo"],
                                     "segundos_total": fila["segundos_total"],
                                     "tokens_prompt": fila["metricas"]["tokens_prompt"],
                                     "tokens_generados": fila["metricas"]["tokens_generados"],
                                     "infraestructura": fila.get("infraestructura"),
                                     "interrupciones_por_terceros": len(interrumpidos),
                                     "prompt_primer_paso_sha256": fila.get("prompt_primer_paso_sha256")})
                guardar()
    res["abortada"] = abortada
    res["valida"] = abortada is None           # una evaluación abortada se conserva como evidencia, no se interpreta
    return res


def comparar(externos: Path, salida: Path, puertas_json: Path, repeticiones=(1, 2), solo_tareas=None) -> dict:
    from eq3 import majflt_windows
    separada(salida)
    pu = json.loads(puertas_json.read_text(encoding="utf-8"))
    g1_ahora = g1()
    if pu.get("variante") != VARIANTE or not pu.get("ok"):
        raise EV.Abortada("las puertas de F1-VRAM-EXP (G1–G6) no pasaron")
    if not g1_ahora["ok"] or pu["G1"]["prerregistro_v3"] != g1_ahora["prerregistro_v3"]:
        raise EV.Abortada("el prerregistro V2/V3 cambió o no está intacto desde las puertas")
    if pu["codigo"] != huella_codigo():
        raise EV.Abortada("el código del ejecutor o de los adaptadores cambió desde las puertas")
    inicio = condiciones(VENTANA_INICIO_S)
    if not inicio["ok"]:
        raise EV.Abortada(f"no se inicia: el PC está en uso o la GPU no está estable: {inicio['motivos']}")
    salida.mkdir(parents=True)
    tareas, oraculos = EV.E.cargar()
    ids = [t for t in tareas if not solo_tareas or t in solo_tareas]
    res = {"variante": VARIANTE, "inicio": time.strftime("%Y-%m-%dT%H:%M:%S"), "prerregistro": g1_ahora["prerregistro"],
           "prerregistro_v3": g1_ahora["prerregistro_v3"], "puertas": str(puertas_json.name), "condiciones_inicio": inicio,
           "limites": {"vram_tope_MiB": VRAM_TOPE_EXP, "vram_otras_max_MiB": VRAM_OTRAS_MAX_EXP},
           "majflt": majflt_windows.activar(salida), "filas": [], "bloques": []}
    EV.preparar_contexto()
    guardar = lambda: (salida / "comparacion.json").write_text(json.dumps(res, ensure_ascii=False, indent=1,
                                                                          default=str), encoding="utf-8")
    ejecutar_bucle(res, salida, tareas, oraculos, ids, repeticiones, fabrica=EV.fabrica_real,
                   g2_fn=lambda: g2(externos), guardar=guardar)
    res["analisis"] = EV.analizar(res["filas"])
    res["fin"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    guardar()
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("orden", choices=("sondear", "puertas", "comparar"))
    ap.add_argument("externos", nargs="?")
    ap.add_argument("salida", type=Path, nargs="?")
    ap.add_argument("--puertas", type=Path)
    a = ap.parse_args(argv)
    if a.orden == "sondear":
        print(json.dumps(condiciones(float(a.externos or VENTANA_INICIO_S)), ensure_ascii=False, default=str))
        return 0
    servidor_pc.preparar_proceso()
    try:
        if a.orden == "puertas":
            r = puertas(Path(a.externos), a.salida)
            print(json.dumps({g: r[g].get("ok") for g in ("G1", "G2", "G3", "G4", "G5", "G6")} | {"ok": r["ok"]}))
            return 0 if r["ok"] else 1
        if not a.puertas:
            print("falta --puertas")
            return 2
        r = comparar(Path(a.externos), a.salida, a.puertas)
        print(json.dumps({"abortada": r["abortada"], "comparaciones": r["analisis"]["comparaciones"]},
                         ensure_ascii=False, default=str)[:2000])
        return 0 if r["abortada"] is None else 1
    except EV.Abortada as e:
        print(f"ABORTADA: {e}")
        return 2
    except EV.FugaDeOraculo as e:
        print(f"ABORTADA POR FUGA DEL ORÁCULO: {e}")
        return 3


if __name__ == "__main__":
    sys.exit(main())
