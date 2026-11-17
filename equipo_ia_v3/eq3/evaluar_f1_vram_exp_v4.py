"""Equipo IA V3.1 F1 — variante EXPERIMENTAL «F1-VRAM-EXP-V4» (`docs/V31_F1_VRAM_EXP_V4.md`).

    python -B -X utf8 eq3/lanzador_eq2.py eq3/evaluar_f1_vram_exp_v4.py sondear  [SEGUNDOS]
    python -B -X utf8 eq3/lanzador_eq2.py eq3/evaluar_f1_vram_exp_v4.py comparar EXTERNOS SALIDA_NUEVA --puertas P.json

NO modifica la estable (`evaluar_f1.py`, V2) ni F1-VRAM-EXP (`evaluar_f1_vram_exp.py`, V3): las reutiliza. Cambios:

- **E2**: llama-server con `--fit off -ngl all -fa on -ub 128 -b 512` (y `-lv 4`, solo registro), pasado como prefijo de
  `comando` de `ServidorLlama`: V2-F.1 no cambia. Tras CADA arranque se lee `server.log` y se exige la configuración
  efectiva (29/29 capas en GPU, n_ubatch 128, sin ajuste de `--fit`); si no, la tarea es de infraestructura y se aborta.
- **Presupuesto** de VRAM ajena = 6912 − 4420 (pico MEDIDO de E2) − 500 (margen = 2 × 251, el mayor crecimiento de la VRAM
  ajena compatible con el intento 1) = **1992 MiB**. Tope total: 6912 MiB, como V3.
- **Persona ≠ carga gráfica**: cuenta como persona la entrada en los últimos 10 min, otra sesión, la consola en otra
  sesión, pantalla completa D3D, presentación, o «ocupada» con una ventana que NO sea el escritorio. El uso de la GPU y
  el fondo animado NO cuentan como persona (son recursos, se comprueban aparte).
- **Wallpaper Engine** (autorizado solo él): con el PC libre se DETIENE (`-control stop`, libera 159 MiB medidos); se
  RESTAURA (`-control play`) al terminar, al abortar, ante un error o si aparece una persona. Nunca se cierra ni se fuerza.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
from eq3 import evaluar_f1 as EV  # noqa: E402
from eq3 import evaluar_f1_vram_exp as X  # noqa: E402
from eq3 import servidor_pc  # noqa: E402

VARIANTE = "F1-VRAM-EXP-V4.2"       # V4.1: guardián, puertas ligadas, aborto si no es E2; V4.2: pruebas aisladas
E2 = ["--fit", "off", "-ngl", "all", "-fa", "on", "-ub", "128", "-b", "512", "-lv", "4"]
VRAM_TOPE = X.VRAM_TOPE_EXP                                   # 6912, sin cambios
PICO_E2_MEDIDO = 4420                                         # laboratorio 2026-11-12, 2 cargas × 3 repeticiones
CRECIMIENTO_AJENO_MAX = 251                                   # 6231 − 4528 − 1452 (intento 1; cota superior)
MARGEN = 500                                                  # ≈ 2 × CRECIMIENTO_AJENO_MAX, redondeado
VRAM_OTRAS_MAX = VRAM_TOPE - PICO_E2_MEDIDO - MARGEN          # 1992
VARIACION_OTRAS_MAX = X.VARIACION_OTRAS_MAX                   # 200
UTILIZACION_GPU_MAX = X.UTILIZACION_GPU_MAX                   # 40 %, medido con el fondo animado ya detenido
INACTIVIDAD_MIN_S = X.INACTIVIDAD_MIN_S                       # 600
ESCRITORIO = ("Progman", "WorkerW")                           # ventanas del escritorio (y del fondo animado)
PRERREGISTRO_V4 = RAIZ / "evaluacion_f1" / "PRERREGISTRO_F1_VRAM_EXP_v4_2.json"     # V4 y V4.1 se conservan


# --- persona (independiente de la GPU) -----------------------------------------------------------------------------
def primer_plano():
    """{clase, pantalla_completa} de la ventana en primer plano, o None."""
    import ctypes
    from ctypes import wintypes
    try:
        u = ctypes.WinDLL("user32")
        h = u.GetForegroundWindow()
        if not h:
            return {"clase": "", "pantalla_completa": False}
        r, cls = wintypes.RECT(), ctypes.create_unicode_buffer(256)
        u.GetWindowRect(h, ctypes.byref(r))
        u.GetClassNameW(h, cls, 256)
        completa = r.right - r.left >= u.GetSystemMetrics(0) and r.bottom - r.top >= u.GetSystemMetrics(1)
        return {"clase": cls.value, "pantalla_completa": bool(completa)}
    except (OSError, AttributeError):
        return None


def persona(act=X.actividad, plano=primer_plano, inactividad_min=INACTIVIDAD_MIN_S) -> dict:
    """¿Hay (o puede haber) alguien usando el PC? Falla CERRADO. No mira la GPU."""
    a = act()
    motivos = [m for m in a["motivos"] if m != "aplicacion_ocupada"]
    if "aplicacion_ocupada" in a["motivos"]:
        p = plano()
        if p is None:
            motivos.append("primer_plano_no_medible")
        elif p["clase"] not in ESCRITORIO:
            motivos.append(f"aplicacion_ocupada_{p['clase']}")
    if a["inactividad_s"] is None:
        motivos.append("inactividad_no_medible")
    elif a["inactividad_s"] < inactividad_min:
        motivos.append(f"entrada_reciente_{round(a['inactividad_s'])}s")
    return {"hay": bool(motivos), "motivos": motivos, "inactividad_s": a["inactividad_s"]}


def condiciones(ventana_s, medir=servidor_pc.vram_mib, util=X.utilizacion_gpu, quien=persona,
                intervalo=X.INTERVALO_SONDEO_S, dormir=time.sleep) -> dict:
    """Persona (aparte) + recursos: VRAM ajena ≤ 1992 y estable, uso de GPU ≤ 40 %."""
    vram, uso, p = [], [], None
    for k in range(max(1, int(ventana_s / intervalo))):
        if k:
            dormir(intervalo)
        v = medir()
        vram.append(v and v["usada"])
        uso.append(util())
        q = quien()
        p = q if p is None or q["hay"] else p
    recursos = []
    if None in vram:
        recursos.append("vram_no_medible")
    elif max(vram) > VRAM_OTRAS_MAX:
        recursos.append(f"vram_otras_{max(vram)}MiB")
    elif max(vram) - min(vram) > VARIACION_OTRAS_MAX:
        recursos.append(f"vram_inestable_{min(vram)}-{max(vram)}MiB")
    if None in uso:
        recursos.append("uso_gpu_no_medible")
    elif max(uso) > UTILIZACION_GPU_MAX:
        recursos.append(f"uso_gpu_{max(uso)}pct")
    return {"ok": not p["hay"] and not recursos, "persona": p, "recursos": recursos,
            "motivos": p["motivos"] + recursos, "vram_MiB": vram, "uso_gpu_pct": uso,
            "fecha": time.strftime("%Y-%m-%dT%H:%M:%S")}


def actividad_vigia(act=X.actividad, plano=primer_plano) -> dict:
    """Para `VigiaExp` (durante una tarea): las mismas señales que `persona`, sin la ventana de 10 min (el vigía ya
    compara la última entrada con el inicio de la tarea)."""
    p = persona(act, plano, inactividad_min=0)
    a = act()
    return {"inactividad_s": a["inactividad_s"], "sesiones": a["sesiones"], "notificacion": a["notificacion"],
            "motivos": [m for m in p["motivos"] if not m.startswith("entrada_reciente")]}


# --- Wallpaper Engine (solo él; reversible) ---------------------------------------------------------------------------
class FondoAnimado:
    """Detiene / restaura Wallpaper Engine con `lab_vram.wallpaper.Control`. Sin él abierto, no hace nada.
    V4.1: antes de detenerlo escribe `marca` y lanza un GUARDIÁN independiente (`lab_vram/guardian_fondo.py`) que lo
    reanuda si este proceso termina de golpe; sin guardián, no se detiene (fallo cerrado)."""

    def __init__(self, control=None, marca=None, guardian=None):
        from lab_vram import wallpaper
        self.c, self.registro = control or wallpaper.Control(), []
        self.marca = Path(marca).resolve() if marca else None
        self.lanzar_guardian, self.guardian = guardian or wallpaper.lanzar_guardian, None
        self.c.capturar()

    def anotar(self, **k):
        self.registro.append({"t": time.strftime("%H:%M:%S")} | k)

    def liberar(self) -> bool:
        if not self.c.inicial["abierto"] or self.c.estado == "detenido":
            return True
        if self.marca is None:
            self.anotar(accion="stop", ok=False, motivo="sin marca no hay guardián: no se detiene")
            return False
        if self.guardian is None:
            self.marca.parent.mkdir(parents=True, exist_ok=True)
            self.marca.write_text(str(os.getpid()), encoding="utf-8")
            self.guardian = self.lanzar_guardian(os.getpid(), self.marca, self.c._exe())
            self.anotar(accion="guardian", resultado=self.guardian)
            if not self.guardian or self.guardian.get("rc") != 0 or not self.guardian.get("pid"):
                self.marca.unlink(missing_ok=True)
                self.guardian = None
                self.anotar(accion="stop", ok=False, motivo="el guardián no arrancó: no se detiene")
                return False
        ok = self.c.control("stop")
        self.anotar(accion="stop", ok=ok)
        return ok

    def restaurar(self) -> bool:
        r = self.c.restaurar()
        if r["ok"] and self.marca is not None:
            self.marca.unlink(missing_ok=True)            # el guardián lo ve y se retira sin actuar
            self.guardian = None
        self.anotar(accion="restaurar", ok=r["ok"])
        return r["ok"]


# --- E2 y su configuración efectiva -----------------------------------------------------------------------------------
def fabrica_e2(verificacion: dict, puerto=None):
    def crear():
        return servidor_pc.crear_backend(verificacion, puerto=puerto, comando=[verificacion["ejecutable"]] + E2,
                                         srv_kw=dict(max_carga_s=240))
    return crear


def configuracion_efectiva(log: str) -> dict:
    """Lo que llama.cpp dice que ha hecho: capas en GPU, n_ubatch, flash_attn y si `--fit` ajustó algo."""
    capas = re.findall(r"offloaded (\d+)/(\d+) layers to GPU", log)
    ub = re.findall(r"n_ubatch\s+=\s+(\d+)", log)
    fa = re.findall(r"flash_attn\s+=\s+(\w+)", log)
    out = {"capas_gpu": f"{capas[-1][0]}/{capas[-1][1]}" if capas else None, "n_ubatch": int(ub[-1]) if ub else None,
           "flash_attn": fa[-1] if fa else None, "fit_ajusto": "fitting params" in log}
    out["ok"] = (bool(capas) and capas[-1][0] == capas[-1][1] and out["n_ubatch"] == 128
                 and not out["fit_ajusto"])
    return out


def comprobar_logs(carpeta: Path) -> dict:
    logs = sorted(carpeta.rglob("server.log"))
    efectivas = [configuracion_efectiva(p.read_text(encoding="utf-8", errors="replace")) for p in logs]
    return {"logs": len(logs), "efectivas": efectivas, "ok": bool(efectivas) and all(e["ok"] for e in efectivas)}


def ejecutar_tarea_e2(configuracion, tarea, oraculo, oraculos, carpeta: Path, fabrica, vigia) -> dict:
    """`EV.ejecutar_tarea` + comprobación de la configuración efectiva de llama.cpp (fallo cerrado)."""
    fila = EV.ejecutar_tarea(configuracion, tarea, oraculo, oraculos, carpeta, fabrica, vigia)
    ef = fila["llama_efectiva"] = comprobar_logs(carpeta)
    sin_e2 = (ef["logs"] and not ef["ok"]) or (not ef["logs"] and not fila.get("infraestructura"))
    if sin_e2:                                            # V4.1: es un fallo sistemático → se aborta TODO
        fila["infraestructura"] = "configuracion_llama_no_e2"
        carpeta.mkdir(parents=True, exist_ok=True)
        (carpeta / "fila_no_e2.json").write_text(json.dumps(fila, ensure_ascii=False, indent=1, default=str),
                                                 encoding="utf-8")
        raise EV.Abortada(f"la tarea {tarea.get('id')} ({configuracion}) no corrió con E2: {ef['efectivas']}")
    return fila


# --- prerregistro V4 -------------------------------------------------------------------------------------------------
ARCHIVOS_V4 = ["evaluacion_f1/PRERREGISTRO_F1.json", "evaluacion_f1/PRERREGISTRO_F1_v1.json",
               "evaluacion_f1/PRERREGISTRO_F1_VRAM_EXP_v3.json", "evaluacion_f1/PRERREGISTRO_F1_VRAM_EXP_v4.json",
               "eq3/evaluar_f1_vram_exp_v4.py", "lab_vram/wallpaper.py", "lab_vram/guardian_fondo.py",
               "pruebas/test_eq3_evaluar_f1_vram_exp_v4.py", "pruebas/test_lab_wallpaper.py",
               "v3/mutaciones/v31_f1_vram_exp_v4.json", "v3/mutaciones/v31_lab_wallpaper.json",
               "evaluacion_f1/prerregistrar_vram_exp_v4.py", "evaluacion_f1/prerregistrar_vram_exp_v4_1.py",
               "evaluacion_f1/PRERREGISTRO_F1_VRAM_EXP_v4_1.json", "evaluacion_f1/prerregistrar_vram_exp_v4_2.py",
               "docs/V31_F1_VRAM_EXP_V4.md"]


def huella_codigo() -> dict:
    return X.huella_codigo() | {a: hashlib.sha256((RAIZ / a).read_bytes()).hexdigest() if (RAIZ / a).is_file()
                                else None for a in ("eq3/evaluar_f1_vram_exp_v4.py", "lab_vram/wallpaper.py",
                                                    "lab_vram/guardian_fondo.py",
                                                    "evaluacion_f1/PRERREGISTRO_F1_VRAM_EXP_v4_2.json")}


def comprobar_v4() -> list:
    if not PRERREGISTRO_V4.is_file():
        return ["falta PRERREGISTRO_F1_VRAM_EXP_v4.json"]
    pre = json.loads(PRERREGISTRO_V4.read_text(encoding="utf-8"))
    dif = [rel for rel, h in pre["sha256"].items()
           if not (RAIZ / rel).is_file() or hashlib.sha256((RAIZ / rel).read_bytes()).hexdigest() != h]
    if pre.get("variante") != VARIANTE or pre.get("limites", {}).get("vram_tope_MiB") != VRAM_TOPE \
            or pre.get("limites", {}).get("vram_otras_max_MiB") != VRAM_OTRAS_MAX or pre.get("llama_e2") != E2:
        dif.append("variante, límites o E2 del prerregistro V4")
    return dif + [f"V3:{d}" for d in X.comprobar_v3()]


# --- comparación V4 --------------------------------------------------------------------------------------------------
@contextmanager
def fondo_gestionado(fondo):
    """Restaura SIEMPRE Wallpaper Engine al salir (fin, aborto, error o STOP)."""
    try:
        yield fondo
    finally:
        if fondo is not None:
            fondo.restaurar()


def esperar_v4(fondo, cond=condiciones, ventana_s=X.VENTANA_TAREA_S, max_espera_s=X.MAX_ESPERA_S,
               dormir=time.sleep, reloj=time.monotonic) -> dict:
    """Antes de cada tarea. Si hay alguien: se le devuelve el fondo animado y se espera; con el PC libre se vuelve a
    detener el fondo y se comprueban los recursos."""
    t0, intentos = reloj(), 0
    while True:
        intentos += 1
        q = persona()
        if q["hay"]:
            if fondo is not None and fondo.c.estado != "normal":
                fondo.restaurar()
            c = {"ok": False, "persona": q, "recursos": [], "motivos": q["motivos"]}
        else:
            if fondo is not None and not fondo.liberar():
                c = {"ok": False, "persona": q, "recursos": ["fondo_no_detenido"], "motivos": ["fondo_no_detenido"]}
            else:
                c = cond(ventana_s)
        if c["ok"] or reloj() - t0 >= max_espera_s:
            return c | {"intentos": intentos, "esperado_s": round(reloj() - t0, 1)}
        dormir(X.ESPERA_REINTENTO_S)


def comparar(externos: Path, salida: Path, puertas_json: Path, repeticiones=(1, 2), solo_tareas=None) -> dict:
    from eq3 import majflt_windows
    if "vram_exp_v4" not in str(salida).lower():
        raise EV.Abortada("los resultados de F1-VRAM-EXP-V4 van en una carpeta con «vram_exp_v4» en el nombre")
    pu = json.loads(puertas_json.read_text(encoding="utf-8"))
    if pu.get("variante") != VARIANTE or not pu.get("ok"):
        raise EV.Abortada("las puertas de F1-VRAM-EXP-V4.1 no pasaron")
    if comprobar_v4():
        raise EV.Abortada(f"prerregistros V1–V4.1 no intactos: {comprobar_v4()[:5]}")
    if pu.get("codigo") != huella_codigo():               # V4.1: las puertas valen solo para ESTE código y prerregistro
        raise EV.Abortada("el código o el prerregistro cambiaron desde las puertas")
    salida.mkdir(parents=True)
    tareas, oraculos = EV.E.cargar()
    ids = [t for t in tareas if not solo_tareas or t in solo_tareas]
    res = {"variante": VARIANTE, "inicio": time.strftime("%Y-%m-%dT%H:%M:%S"), "llama_e2": E2,
           "limites": {"vram_tope_MiB": VRAM_TOPE, "vram_otras_max_MiB": VRAM_OTRAS_MAX},
           "majflt": majflt_windows.activar(salida), "filas": [], "bloques": []}
    EV.preparar_contexto()
    guardar = lambda: (salida / "comparacion.json").write_text(json.dumps(res, ensure_ascii=False, indent=1,
                                                                          default=str), encoding="utf-8")
    with fondo_gestionado(FondoAnimado(marca=salida / "fondo_detenido.marca")) as fondo:
        inicio = esperar_v4(fondo, ventana_s=X.VENTANA_INICIO_S, max_espera_s=0)
        res["condiciones_inicio"] = inicio
        if not inicio["ok"]:
            raise EV.Abortada(f"no se inicia: {inicio['motivos']}")
        X.ejecutar_bucle(res, salida, tareas, oraculos, ids, repeticiones, ejecutar=ejecutar_tarea_e2,
                         fabrica=fabrica_e2, g2_fn=lambda: _g2(externos), esperar=lambda: esperar_v4(fondo),
                         vigia_fn=lambda: X.VigiaExp(act=actividad_vigia), guardar=guardar)
        res["fondo_animado"] = fondo.registro
    res["fondo_restaurado"] = fondo.registro[-1] if fondo.registro else None
    res["analisis"] = EV.analizar(res["filas"])
    res["fin"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    guardar()
    return res


def _g2(externos: Path) -> tuple:
    ver = servidor_pc.verificar_externos(externos)
    v = servidor_pc.vram_mib()
    ok = ver["ok"] and v is not None and v["usada"] <= VRAM_OTRAS_MAX
    return {"ok": ok, "vram_otras_MiB": v and v["usada"], "maximo_otras_MiB": VRAM_OTRAS_MAX,
            "externos_ok": ver["ok"]}, ver


# --- pruebas reales CORTAS de seguridad (sin la evaluación F1) -----------------------------------------------------
@contextmanager
def _fabrica_e2_en_ev():
    """G3/G4 de la estable (`EV._interrupcion_real`) con E2, solo en ESTE proceso; se deshace al salir."""
    original = EV.fabrica_real
    EV.fabrica_real = fabrica_e2
    try:
        yield
    finally:
        EV.fabrica_real = original


def prompt_largo(funciones=40) -> str:
    """≈ 1800 tokens (casi todo el contexto de 2048) para medir el pico de VRAM de E2 en el peor caso."""
    return "Revisa este módulo y explica qué hace cada función:\n\n" + "\n".join(
        f"def paso_{i}(datos):\n    total = 0\n    for x in datos:\n        if x % {i + 2} == 0:\n"
        f"            total += x * {i}\n    return total\n" for i in range(funciones))


def pico_e2(ver, carpeta: Path) -> dict:
    from eq2 import rutas
    raiz = carpeta / "equipo_f2"
    raiz.mkdir(parents=True)
    lab = rutas.Laboratorio(raiz, raiz / "p")
    lab.crear_base()
    lab.crear_dir("runs", "P")
    base = (servidor_pc.vram_mib() or {}).get("usada")
    vig = X.VigiaExp(act=actividad_vigia, intervalo=0.5).iniciar()
    be = fabrica_e2(ver)()
    out = {"vram_antes_MiB": base}
    try:
        be.iniciar({"lab": lab, "run_id": "P", "parar": vig.parar})
        t0 = time.monotonic()
        be.completar([{"role": "user", "content": prompt_largo()}], 120, 240)
        out["segundos"] = round(time.monotonic() - t0, 2)
    except Exception as e:                                         # se registra; el cierre va en finally
        out["error"] = f"{type(e).__name__}: {getattr(e, 'motivo', e)}"
    finally:
        d = be.detener()
        v = vig.detener()
    ok_p = [p for p in be.peticiones if p.get("status") == 200]
    m = (ok_p[-1].get("metricas") or {}) if ok_p else {}
    out.update(vigia=v, cierre_limpio=d["limpio"], tokens_prompt=m.get("prompt_n"), tokens_generados=m.get("predicted_n"),
               gen_tps=round(m["predicted_n"] / m["predicted_ms"] * 1000, 2) if m.get("predicted_ms") else None,
               qwen_pico_MiB=(v["maxima_MiB"] - base) if v["maxima_MiB"] and base else None,
               llama_efectiva=comprobar_logs(carpeta), llama_despues=servidor_pc.procesos_llama())
    return out


def pruebas_reales(externos: Path, salida: Path) -> dict:
    if "vram_exp_v4" not in str(salida).lower():
        raise EV.Abortada("las evidencias de V4 van en una carpeta con «vram_exp_v4» en el nombre")
    salida.mkdir(parents=True)
    res = {"variante": VARIANTE, "inicio": time.strftime("%Y-%m-%dT%H:%M:%S"), "llama_e2": E2}
    guardar = lambda: (salida / "pruebas_reales.json").write_text(json.dumps(res, ensure_ascii=False, indent=1,
                                                                             default=str), encoding="utf-8")
    ver = servidor_pc.verificar_externos(externos)
    if not ver["ok"]:
        raise EV.Abortada(f"externos no verificados: {ver['problemas'][:3]}")
    with fondo_gestionado(FondoAnimado(marca=salida / "fondo_detenido.marca")) as fondo:
        c = esperar_v4(fondo, ventana_s=20, max_espera_s=0)
        res["condiciones"] = c
        guardar()
        if c["ok"]:
            EV.preparar_contexto()
            res["pico_e2"] = pico_e2(ver, salida / "pico")
            guardar()
            with _fabrica_e2_en_ev():
                for nombre, modo in (("G3", "stop"), ("G4", "memoria")):
                    if persona()["hay"]:
                        res[nombre] = {"ok": False, "motivo": "persona: no se ejecuta"}
                        break
                    r = EV._interrupcion_real(ver, salida / nombre, modo)
                    r["llama_efectiva"] = comprobar_logs(salida / nombre)
                    res[nombre] = r
                    guardar()
        res["fondo_antes_de_restaurar"] = list(fondo.registro)
    res["fondo"] = fondo.registro
    res["fin"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    guardar()
    return res


# --- puertas V4.1 ------------------------------------------------------------------------------------------------------
def _lab(carpeta: Path, run_id: str):
    from eq2 import rutas
    raiz = carpeta / "equipo_f2"
    raiz.mkdir(parents=True)
    lab = rutas.Laboratorio(raiz, raiz / run_id)
    lab.crear_base()
    lab.crear_dir("runs", run_id)
    return lab


def _liberada(base, t1, limite=20) -> tuple:
    v = None
    while time.monotonic() - t1 < limite:
        v = servidor_pc.vram_mib()
        if v and base is not None and v["usada"] <= base + 64:
            break
        time.sleep(0.5)
    return round(time.monotonic() - t1, 2), v and v["usada"]


def corte_vram_real(ver, carpeta: Path) -> dict:
    """G8: a mitad de una generación con Qwen real, el tope del vigía pasa a ser MÁS ESTRICTO que la VRAM real (nunca se
    sube nada): el vigía debe cortar la petición y el servidor propio debe cerrarse y liberar la VRAM."""
    from eq2 import inferencia
    lab = _lab(carpeta, "V")
    llama_antes, base = servidor_pc.procesos_llama(), (servidor_pc.vram_mib() or {}).get("usada")
    vig = X.VigiaExp(act=actividad_vigia, intervalo=0.5).iniciar()
    be, marca, out = fabrica_e2(ver)(), {}, {"vram_antes_MiB": base, "llama_antes": llama_antes}
    try:
        be.iniciar({"lab": lab, "run_id": "V", "parar": vig.parar})
        cargado = (servidor_pc.vram_mib() or {}).get("usada")
        out.update(vram_cargado_MiB=cargado, pid_servidor=be.srv.pid(), pid_propio=os.getpid(),
                   padre_del_servidor=EV._pid_padre(be.srv.pid()))

        def apretar():
            time.sleep(4.0)
            marca["t"] = time.monotonic()
            vig.tope = (cargado or 0) - 200                      # MÁS estricto que lo que ya se usa
        threading.Thread(target=apretar, daemon=True).start()
        try:
            be.completar([{"role": "user", "content": "Escribe un ensayo muy largo sobre la historia de la "
                                                      "computación, sin resumir."}], 800, 240)
            out["interrumpida"] = False
        except inferencia.ErrorInferencia as e:
            out["interrumpida"], out["motivo"] = True, e.motivo
        out["segundos_hasta_interrupcion"] = round(time.monotonic() - marca["t"], 2) if "t" in marca else None
    finally:
        t1 = time.monotonic()
        d = be.detener()
        out["cierre"] = {"segundos": round(time.monotonic() - t1, 2), "limpio": d["limpio"]}
        out["segundos_hasta_liberar_vram"], out["vram_despues_MiB"] = _liberada(base, t1)
        out["vigia"] = vig.detener()
        out["llama_despues"] = servidor_pc.procesos_llama()
    out["llama_efectiva"] = comprobar_logs(carpeta)
    out["ok"] = bool(out.get("interrumpida") and str(out["vigia"]["excedida"]).startswith("vram_excedida")
                     and out["segundos_hasta_interrupcion"] is not None and out["segundos_hasta_interrupcion"] <= 6
                     and out["cierre"]["limpio"] and out["padre_del_servidor"] == out["pid_propio"]
                     and out["llama_despues"] == llama_antes and out["vram_despues_MiB"] is not None
                     and base is not None and out["vram_despues_MiB"] <= base + 64 and out["llama_efectiva"]["ok"])
    return out


def fallo_arranque_real(ver, carpeta: Path) -> dict:
    """G9: un arranque que falla (opción inexistente al final de E2) debe dar ErrorInferencia, sin dejar procesos llama,
    con el puerto libre y la VRAM igual. No carga el modelo."""
    from eq2 import inferencia, servidor
    lab = _lab(carpeta, "F")
    llama_antes, base = servidor_pc.procesos_llama(), (servidor_pc.vram_mib() or {}).get("usada")
    import subprocess
    ayuda = (lambda r: r.stdout + r.stderr)(subprocess.run([ver["ejecutable"], "--help"], capture_output=True,
                                                           text=True, timeout=60))
    # la ayuda REAL (sin la opción mala) para que las comprobaciones previas pasen y falle el ARRANQUE del proceso
    be = servidor_pc.crear_backend(ver, comando=[ver["ejecutable"]] + E2 + ["--opcion-inexistente-eq3"],
                                   srv_kw=dict(max_carga_s=60, ayuda_fn=lambda: ayuda))
    out = {"llama_antes": llama_antes, "vram_antes_MiB": base}
    try:
        be.iniciar({"lab": lab, "run_id": "F", "parar": lambda: None})
        out["arranco"] = True
    except inferencia.ErrorInferencia as e:
        out["arranco"], out["motivo"] = False, e.motivo
    finally:
        if be.estado != "detenido":
            be.detener()
    time.sleep(1.0)
    out.update(llama_despues=servidor_pc.procesos_llama(), puerto_libre=servidor.puerto_libre(be.srv.puerto),
               servidor_terminado=be.srv.proc is None or be.srv.proc.poll() is not None,
               vram_despues_MiB=(servidor_pc.vram_mib() or {}).get("usada"))
    out["ok"] = bool(out["arranco"] is False and out["llama_despues"] == llama_antes and out["puerto_libre"]
                     and out["servidor_terminado"] and out["vram_despues_MiB"] is not None and base is not None
                     and out["vram_despues_MiB"] <= base + 64)
    return out


def _unittest(patron: str, carpeta: Path) -> dict:
    from eq3 import plataforma
    carpeta.mkdir(parents=True, exist_ok=True)
    r = plataforma.ejecutar([sys.executable, "-B", "-m", "unittest", "discover", "-s", "pruebas", "-t", "pruebas",
                             "-p", patron], cwd=RAIZ, env=plataforma.entorno_hijo(carpeta), timeout=1800)
    ult = [l for l in (r.stdout + r.stderr).splitlines() if l.startswith(("Ran ", "OK", "FAILED"))]
    return {"rc": r.returncode, "resultado": ult[-2:]}


def g10_equivalencia(carpeta: Path) -> dict:
    """G10: S1, S1×3 y E3 en condiciones equivalentes. Estático: el mismo ejecutor, la misma fábrica E2, el mismo vigía y
    el orden contrabalanceado; REAL con el servidor falso de V2-F.1: mismo prompt (SHA-256) para S1, cada muestra de
    S1×3 y el primer paso de E3, temperaturas y semillas (pruebas de la estable)."""
    llamadas = []

    def ejecutar(c, tarea, oraculo, oraculos, carpeta_t, be, vigia):
        llamadas.append((c, be, type(vigia).__name__, vigia.tope))
        return {"evaluacion": {"categoria": "CORRECTO", "calidad": "CORRECTO", "seguridad": "seguro", "motivo": ""},
                "segundos_total": 0, "metricas": {"tokens_prompt": 0, "tokens_generados": 0}}
    res = {"filas": [], "bloques": []}
    X.ejecutar_bucle(res, carpeta / "vram_exp_v4_equivalencia", {"T01": {"id": "T01"}}, {"T01": {}}, ["T01"], (1, 2),
                     ejecutar=ejecutar, fabrica=lambda ver: ("E2", tuple(E2)),
                     esperar=lambda: {"ok": True, "motivos": [], "esperado_s": 0},
                     vigia_fn=lambda: X.VigiaExp(act=lambda: {"inactividad_s": 1e9, "sesiones": {}, "notificacion": 5,
                                                              "motivos": []}, medir=lambda: {"usada": 1000}))
    import inspect
    configs = [l[0] for l in llamadas]
    fuente = inspect.getsource(comparar)
    estatico = {"orden": configs, "orden_ok": configs == list(EV.ORDEN[1] + EV.ORDEN[2]),
                "comparar_usa_e2_para_todas": "ejecutar=ejecutar_tarea_e2" in fuente and "fabrica=fabrica_e2" in fuente
                and "vigia_fn=lambda: X.VigiaExp(act=actividad_vigia)" in fuente,
                "misma_fabrica": len({l[1] for l in llamadas}) == 1, "mismo_vigia": len({(l[2], l[3]) for l in llamadas}) == 1,
                "temperatura_s1x3": EV.TEMPERATURA_S1X3, "semillas_s1x3": EV.SEMILLAS_S1X3, "max_iter_e3": EV.MAX_ITER_E3,
                "ctx": EV.CTX}
    real = _unittest("test_eq3_evaluar_f1.py", carpeta / "estable")
    return {"estatico": estatico, "pruebas_estable_mismo_prompt": real,
            "ok": estatico["orden_ok"] and estatico["misma_fabrica"] and estatico["mismo_vigia"]
            and estatico["comparar_usa_e2_para_todas"] and real["rc"] == 0}


def g5(carpeta: Path) -> dict:
    """G5: F15–F20 + V-SRV (como V3) y F21–F22 (V4.1)."""
    from eq3 import plataforma
    out = X.g5(carpeta)
    for fase, spec in (("F21", "v31_f1_vram_exp_v4"), ("F22", "v31_lab_wallpaper")):
        tmp = carpeta / fase
        tmp.mkdir(parents=True)
        r = plataforma.ejecutar([sys.executable, "-B", "v3/mutacion.py", f"v3/mutaciones/{spec}.json"], cwd=RAIZ,
                                env=plataforma.entorno_hijo(tmp), timeout=3600)
        ultima = [l for l in r.stdout.splitlines() if "FIN MUTACI" in l][-1:] or [r.stderr[-200:]]
        out[fase] = {"rc": r.returncode, "resultado": ultima[0].strip()}
        out["ok"] = out["ok"] and r.returncode == 0
    return out


def puertas(externos: Path, salida: Path, con_g5=True) -> dict:
    """G1 integridad, G2 externos y VRAM ajena, G3 STOP, G4 RAM, G5 mutaciones, G6 persona y recursos, G7 fondo animado,
    G8 tope de VRAM, G9 fallo de arranque, G10 equivalencia. Las de Qwen real, SOLO si G1, G2 y G6 pasan."""
    from eq3 import majflt_windows
    if "vram_exp_v4" not in str(salida).lower():
        raise EV.Abortada("las puertas de V4.1 van en una carpeta con «vram_exp_v4» en el nombre")
    salida.mkdir(parents=True)
    res = {"variante": VARIANTE, "inicio": time.strftime("%Y-%m-%dT%H:%M:%S"), "codigo": huella_codigo(),
           "llama_e2": E2, "limites": {"vram_tope_MiB": VRAM_TOPE, "vram_otras_max_MiB": VRAM_OTRAS_MAX}}
    guardar = lambda: (salida / "puertas.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str),
                                                           encoding="utf-8")
    dif, g1e = comprobar_v4(), EV.g1()
    res["G1"] = {"ok": not dif and g1e["ok"], "diferencias_v1_v4": dif, "v2_y_fugas": {k: g1e[k] for k in (
        "ok", "diferencias_prerregistro", "fugas_en_enunciados")}, "compat_v2f1": _unittest("test_eq3_servidor_pc.py",
                                                                                           salida / "compat")}
    res["G1"]["ok"] = res["G1"]["ok"] and res["G1"]["compat_v2f1"]["rc"] == 0
    guardar()
    res["G10"] = g10_equivalencia(salida / "G10")
    guardar()
    res["G5"] = g5(salida / "G5") if con_g5 else {"ok": False, "motivo": "no ejecutada"}
    guardar()
    llama_inicio = servidor_pc.procesos_llama()
    with fondo_gestionado(FondoAnimado(marca=salida / "fondo_detenido.marca")) as fondo:
        res["G6"] = esperar_v4(fondo, ventana_s=X.VENTANA_INICIO_S, max_espera_s=0)
        res["G7_detencion"] = {"registro": list(fondo.registro), "vram_wallpaper_MiB": _vram_fondo()}
        res["G2"], ver = _g2(externos)
        guardar()
        res["majflt"] = majflt_windows.activar(salida)
        EV.preparar_contexto()
        previas = res["G1"]["ok"] and res["G2"]["ok"] and res["G6"]["ok"]
        pruebas = [("G3", lambda: EV._interrupcion_real(ver, salida / "G3", "stop")),
                   ("G4", lambda: EV._interrupcion_real(ver, salida / "G4", "memoria")),
                   ("G8", lambda: corte_vram_real(ver, salida / "G8")),
                   ("G9", lambda: fallo_arranque_real(ver, salida / "G9"))]
        with _fabrica_e2_en_ev():
            for nombre, prueba in pruebas:
                if not previas:
                    res[nombre] = {"ok": False, "motivo": "no se ejecuta: G1, G2 o G6 no pasaron"}
                    continue
                q = persona()
                if q["hay"]:
                    res[nombre] = {"ok": False, "motivo": f"persona: {q['motivos']}"}
                    previas = False
                    continue
                r = prueba()
                if nombre in ("G3", "G4"):
                    r["llama_efectiva"] = comprobar_logs(salida / nombre)
                    r["ok"] = r["ok"] and r["llama_efectiva"]["ok"]
                res[nombre] = r
                guardar()
    time.sleep(3.0)
    procs = []
    try:
        from lab_vram import wallpaper
        procs = wallpaper.procesos()
    except Exception:
        pass
    inicial = fondo.c.inicial["procesos"]
    res["G7"] = {"registro": fondo.registro, "procesos_antes": inicial, "procesos_despues": procs,
                 "vram_wallpaper_MiB_despues": _vram_fondo(),
                 "marca_retirada": not (salida / "fondo_detenido.marca").exists()}
    res["G7"]["ok"] = bool(fondo.registro and fondo.registro[-1].get("accion") == "restaurar"
                           and fondo.registro[-1].get("ok") and res["G7"]["marca_retirada"]
                           and [p["pid"] for p in procs] == [p["pid"] for p in inicial]
                           and (not inicial or any(v > 0 for v in res["G7"]["vram_wallpaper_MiB_despues"].values())))
    res["llama_al_final"] = servidor_pc.procesos_llama()
    res["procesos_liberados"] = res["llama_al_final"] == llama_inicio
    res["ok"] = all(res[g]["ok"] for g in ("G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9", "G10")) \
        and res["procesos_liberados"]
    res["fin"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    guardar()
    return res


def _vram_fondo() -> dict:
    try:
        from lab_vram import wallpaper
        return wallpaper.vram_por_proceso({p["pid"] for p in wallpaper.procesos()})
    except Exception:
        return {}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("orden", choices=("sondear", "comparar", "pruebas_reales", "puertas"))
    ap.add_argument("--sin-g5", action="store_true")
    ap.add_argument("externos", nargs="?")
    ap.add_argument("salida", type=Path, nargs="?")
    ap.add_argument("--puertas", type=Path)
    a = ap.parse_args(argv)
    if a.orden == "sondear":
        print(json.dumps(condiciones(float(a.externos or 10)), ensure_ascii=False, default=str))
        return 0
    servidor_pc.preparar_proceso()
    try:
        if a.orden == "puertas":
            r = puertas(Path(a.externos), a.salida, con_g5=not a.sin_g5)
            print(json.dumps({g: r[g].get("ok") for g in ("G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9", "G10")}
                             | {"procesos_liberados": r["procesos_liberados"], "ok": r["ok"]}))
            return 0 if r["ok"] else 1
        if a.orden == "pruebas_reales":
            r = pruebas_reales(Path(a.externos), a.salida)
            resumen = {k: (r.get(k) or {}).get("ok") for k in ("G3", "G4")}
            p = r.get("pico_e2") or {}
            print(json.dumps(resumen | {"condiciones": r["condiciones"]["ok"], "qwen_pico_MiB": p.get("qwen_pico_MiB"),
                                        "tokens_prompt": p.get("tokens_prompt"), "gen_tps": p.get("gen_tps"),
                                        "efectiva": (p.get("llama_efectiva") or {}).get("ok"),
                                        "fondo": r["fondo"][-1:]}, ensure_ascii=False, default=str))
            return 0
        r = comparar(Path(a.externos), a.salida, a.puertas)
        return 0 if r.get("abortada") is None else 1
    except EV.Abortada as e:
        print(f"ABORTADA: {e}")
        return 2
    except EV.FugaDeOraculo as e:
        print(f"ABORTADA POR FUGA DEL ORÁCULO: {e}")
        return 3


if __name__ == "__main__":
    sys.exit(main())
