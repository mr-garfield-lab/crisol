"""Equipo IA V3.1 F1 — EJECUTOR de la evaluación prerregistrada S1 / S1×3 / E3 (`docs/V31_F1_PLAN_EVALUACION.md`).

    python -B -X utf8 eq3/lanzador_eq2.py eq3/evaluar_f1.py puertas  EXTERNOS SALIDA_NUEVA
    python -B -X utf8 eq3/lanzador_eq2.py eq3/evaluar_f1.py comparar EXTERNOS SALIDA_NUEVA --puertas PUERTAS.json

`puertas` comprueba G1–G5 y escribe `puertas.json`; `comparar` se niega a empezar si el prerregistro no está intacto o si
las puertas no pasaron con el MISMO prerregistro, los mismos externos y el mismo código.

Qué garantiza:
- **Mismas tareas** (`evaluacion_f1/tareas_f1.json`) para las tres configuraciones; los oráculos no entran en ningún
  prompt: CADA petición al modelo pasa por `proteger_backend`, que aborta TODA la evaluación (`FugaDeOraculo`,
  derivada de BaseException para que ningún `except Exception` de V2-F.1 la oculte) si un texto del oráculo aparece.
- **Mismo prompt** para S1, para cada muestra de S1×3 y para el primer paso de E3 (`AgentesFuncionLLM.generar_fs` con el
  plan de trabajo, los casos y las experiencias que calcula `FuncionSupervisada`), comprobado y registrado.
- **Un servidor y un laboratorio NUEVOS por tarea**, configuración y repetición (sin memoria compartida).
- **S1×3**: temperatura 0,7 y semillas 11, 42 y 2026 SOLO durante sus tres peticiones (se restauran 0 y 1); votación por
  mayoría de la respuesta normalizada, SIN acceso al oráculo.
- **E3**: `tareas.Tareas.ejecutar` de V2-F.1 tal cual (función supervisada, `max_iteraciones` 2).
- **Nada se ejecuta**: el código de los agentes solo lo analiza `eq3.evaluacion_f1` (AST y literal_eval).
- **VRAM**: se muestrea cada 2 s; si la total supera 6144 MiB, la tarea en curso se detiene (STOP de V2-F.1) y el resto
  del bloque no se ejecuta (NO_CONCLUYENTE por infraestructura).
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import os
import sys
import threading
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
from eq3 import evaluacion_f1 as E  # noqa: E402
from eq3 import servidor_pc  # noqa: E402

CONFIGURACIONES = ("S1", "S1x3", "E3")
ORDEN = {1: ("S1", "S1x3", "E3"), 2: ("E3", "S1x3", "S1")}
TEMPERATURA_S1X3 = 0.7
SEMILLAS_S1X3 = (11, 42, 2026)
MAX_ITER_E3 = 2
CTX = 2048
VRAM_OTRAS_MAX = 1500
VRAM_TOPE = 6144
INTERVALO_VRAM_S = 2.0
UMBRAL_VENTAJA = 3              # «A supera a B»: ≥ 3 CORRECTO más en LAS DOS repeticiones y no más FALLO_SEGURIDAD
MAX_CAMBIOS_ESTABLE = 2         # > 2 tareas que cambian de categoría entre repeticiones = configuración inestable
TAREAS_PRINCIPALES = tuple(f"T{i:02d}" for i in range(1, 14))


class FugaDeOraculo(BaseException):
    """Un texto de los oráculos iba a enviarse al modelo: se aborta TODA la evaluación."""


class Abortada(RuntimeError):
    """La evaluación no puede continuar (prerregistro, puertas o externos)."""


# --- protecciones --------------------------------------------------------------------------------------------------
def proteger_backend(be, oraculos: dict, registro: list):
    """Envuelve `be.completar`: comprueba fugas en CADA petición y anota temperatura, semilla y SHA-256 del prompt."""
    from eq2 import config
    original = be.completar

    def completar(mensajes, max_tokens, plazo_s):
        texto = "\n".join(str(m.get("content", "")) for m in mensajes if isinstance(m, dict))
        fugas = E.fugas_de_oraculo(texto, oraculos)
        if fugas:
            registro.append({"fuga": fugas})
            raise FugaDeOraculo(f"texto del oráculo en un prompt: {fugas}")
        registro.append({"sha256": hashlib.sha256(texto.encode("utf-8")).hexdigest(), "caracteres": len(texto),
                         "temperatura": config.TEMPERATURA, "semilla": config.SEMILLA, "max_tokens": max_tokens})
        return original(mensajes, max_tokens, plazo_s)
    be.completar = completar
    return be


class Vigia:
    """Muestrea la VRAM cada `intervalo` s. Si la total supera el tope, `parar()` devuelve un motivo (V2-F.1 corta la
    petición) y se ejecutan las acciones registradas (p. ej. crear el archivo STOP de una tarea E3)."""

    def __init__(self, medir=servidor_pc.vram_mib, intervalo=INTERVALO_VRAM_S, tope=VRAM_TOPE):
        self.medir, self.intervalo, self.tope = medir, intervalo, tope
        self.excedida, self.maxima, self.muestras, self.sin_medida = None, None, [], 0
        self.acciones, self._fin, self._hilo = [], threading.Event(), None

    def _muestrear(self):
        v = self.medir()
        if v is None:
            self.sin_medida += 1
            return
        self.muestras.append(v["usada"])
        self.maxima = max(self.maxima or 0, v["usada"])
        if v["usada"] > self.tope and self.excedida is None:
            self.excedida = f"vram_excedida_{v['usada']}MiB"
            for a in list(self.acciones):
                try:
                    a()
                except Exception:
                    pass

    def agregar_accion(self, accion):
        """Registra una acción para cuando se supere el tope; si YA se superó, la ejecuta en el acto."""
        self.acciones.append(accion)
        if self.excedida is not None:
            accion()

    def iniciar(self):
        def bucle():
            while not self._fin.is_set():
                self._muestrear()
                self._fin.wait(self.intervalo)
        self._hilo = threading.Thread(target=bucle, daemon=True, name="eq3-vigia-vram")
        self._hilo.start()
        return self

    def detener(self):
        self._fin.set()
        if self._hilo:
            self._hilo.join(10)
        return {"maxima_MiB": self.maxima, "media_MiB": round(sum(self.muestras) / len(self.muestras)) if self.muestras
                else None, "muestras": len(self.muestras), "sin_medida": self.sin_medida, "excedida": self.excedida}

    def parar(self):
        return self.excedida


# --- respuestas ----------------------------------------------------------------------------------------------------
def codigo_de(texto: str) -> str:
    """Los .py (no de pruebas) que entrega A1, como los toma V2-F.1 (`proyecto.extraer` + el filtro de `_version`)."""
    from eq2 import funcion_supervisada as FS, proyecto
    ex = proyecto.extraer(texto or "", FS.PRESUPUESTO.acotado())
    return "\n\n".join(a["contenido"] for a in ex["archivos"]
                       if a["nombre"].endswith(".py") and not a["nombre"].rsplit("/", 1)[-1].startswith("test"))


def es_rechazo(texto: str, codigo: str) -> bool:
    """¿Se negó o pidió información? Regla de V2-F.1 (FALTA sin SUPUESTO con la política «preguntar»), o respondió
    texto sin ningún código. NUNCA mira el oráculo."""
    from eq2 import planificacion
    if planificacion.decision_informacion(planificacion.analizar(texto or ""), "preguntar")["accion"] == "preguntar":
        return True
    return not codigo.strip() and bool((texto or "").strip())


def clave_de_voto(tarea: dict, codigo: str, rechazo: bool) -> str:
    """Respuesta normalizada para la votación de S1×3 (sin oráculo): el literal devuelto, o el AST de la función."""
    if not codigo.strip():
        return "RECHAZO" if rechazo else "SIN_RESPUESTA"
    try:
        arbol = ast.parse(codigo)
    except (SyntaxError, ValueError):
        return "SINTAXIS:" + hashlib.sha256(codigo.encode()).hexdigest()[:16]
    f = E._funcion(arbol, tarea["funcion"])
    if f is None:
        return "SIN_FUNCION:" + hashlib.sha256(ast.dump(arbol).encode()).hexdigest()[:16]
    ok, v = E._literal(f)
    if ok:
        return "LITERAL:" + repr(E._a_listas(v))
    return "AST:" + hashlib.sha256(ast.dump(f, annotate_fields=False).encode()).hexdigest()[:16]


def votar(tarea: dict, muestras: list) -> int:
    """Índice de la muestra elegida: la clave más votada; en empate, la primera con código analizable; si no, la de la
    primera semilla. No usa el oráculo."""
    claves = [clave_de_voto(tarea, m["codigo"], m["rechazo"]) for m in muestras]
    cuenta = {c: claves.count(c) for c in claves}
    mejor = max(cuenta.values())
    empatadas = [i for i, c in enumerate(claves) if cuenta[c] == mejor]
    if len({claves[i] for i in empatadas}) > 1:
        analizables = [i for i in empatadas if claves[i].startswith(("LITERAL:", "AST:"))]
        return (analizables or empatadas)[0]
    return empatadas[0]


# --- prompts idénticos al primer paso de E3 ----------------------------------------------------------------------
def entradas_primer_paso(tarea: dict, lab) -> dict:
    """orden, casos y experiencias EXACTAMENTE como los calcula `FuncionSupervisada` para su paso fs_generar."""
    from eq2 import casos as C, experiencias, funcion_supervisada as FS, interfaces_codex
    fs = FS.FuncionSupervisada.__new__(FS.FuncionSupervisada)
    fs.max_iter, fs.propiedades = MAX_ITER_E3, ()
    oraculo_v2f = C.casos_del_usuario(None) + C.con_ids(C.ejemplos_del_enunciado(tarea["instrucciones"]), "E")
    mem = experiencias.MemoriaEquipo(lab)
    try:
        exp = interfaces_codex.Componentes(memoria=mem).memoria(
            "A1", f"{tarea['instrucciones']} {tarea['funcion'] or ''} funcion", n=2)["texto"]
    finally:
        mem.cerrar()
    return {"orden": fs._orden_trabajo(tarea["funcion"]), "casos": FS.FuncionSupervisada._casos_txt(oraculo_v2f),
            "experiencias": exp}


# --- una tarea ---------------------------------------------------------------------------------------------------
def _metricas(be, agentes, registro) -> dict:
    p = [x for x in be.peticiones if x.get("status") == 200]
    suma = lambda k: sum((x.get("metricas") or {}).get(k) or 0 for x in p)
    vmhwm = [max(v for v in (x.get("memoria_kB") or {}).get("VmHWM", [None]) if v is not None) for x in p
             if any(v is not None for v in (x.get("memoria_kB") or {}).get("VmHWM", [None]))]
    mon = be.mon.resumen() if be.mon else {}
    return {"llamadas": len(be.peticiones), "llamadas_ok": len(p),
            "tokens_prompt": suma("prompt_n"), "tokens_cache": suma("cache_n"), "tokens_generados": suma("predicted_n"),
            "prompt_ms": round(suma("prompt_ms"), 1), "generacion_ms": round(suma("predicted_ms"), 1),
            "no_concluyentes_medicion": [x.get("motivos_no_concluyente") for x in p if not x.get("concluyente")],
            "majflt_windows": [(x.get("delta_fallos") or {}).get("majflt") for x in p],
            "servidor_VmHWM_kB_max": max(vmhwm) if vmhwm else None,
            "MemAvailable_min_kB": mon.get("min_MemAvailable_kB"), "carga_s": be.carga_s,
            "fallos_peticion": [x.get("fallo") for x in be.peticiones if x.get("fallo")],
            "recortes_prompt": [{"paso": q["paso"], "omitidos": q["omitidos"], "recortados": q["recortados"]}
                                for q in getattr(agentes, "prompts", []) if q.get("omitidos") or q.get("recortados")],
            "peticiones": registro}


def ejecutar_tarea(configuracion, tarea, oraculo, oraculos, carpeta: Path, fabrica, vigia) -> dict:
    """Ejecuta UNA tarea con UNA configuración en un laboratorio y un servidor nuevos. Devuelve el registro completo."""
    from eq2 import config, funcion_supervisada as FS, inferencia, rutas, tareas as TS
    t0 = time.monotonic()
    raiz = carpeta / "equipo_f2"
    raiz.mkdir(parents=True)
    reg = {"configuracion": configuracion, "tarea": tarea["id"], "inicio": time.strftime("%Y-%m-%dT%H:%M:%S")}
    registro = []
    be = proteger_backend(fabrica(), oraculos, registro)
    agentes = FS.AgentesFuncionLLM(be)
    muestras, cierre = [], None
    try:
        if configuracion in ("S1", "S1x3"):
            lab = rutas.Laboratorio(raiz, raiz / config.CARPETA_ACTUAL)
            lab.crear_base()
            lab.crear_dir("runs", "R")
            ent = entradas_primer_paso(tarea, lab)
            planes = [(config.TEMPERATURA, config.SEMILLA)] if configuracion == "S1" else \
                [(TEMPERATURA_S1X3, s) for s in SEMILLAS_S1X3]
            try:
                be.iniciar({"lab": lab, "run_id": "R", "parar": vigia.parar})
            except inferencia.ErrorInferencia as e:          # p. ej. VRAM ya excedida o STOP: no se pide nada
                planes, reg["arranque"] = [], e.motivo
                muestras.append({"temperatura": None, "semilla": None, "texto": "", "codigo": "", "rechazo": False,
                                 "error": e.motivo})
            t_orig, s_orig = config.TEMPERATURA, config.SEMILLA
            try:
                for temp, semilla in planes:
                    config.TEMPERATURA, config.SEMILLA = temp, semilla
                    try:
                        texto = agentes.generar_fs(tarea["instrucciones"], **ent) or ""
                        err = None
                    except inferencia.ErrorInferencia as e:
                        texto, err = "", e.motivo
                    cod = codigo_de(texto)
                    muestras.append({"temperatura": temp, "semilla": semilla, "texto": texto, "codigo": cod,
                                     "rechazo": err is None and es_rechazo(texto, cod), "error": err})
            finally:
                config.TEMPERATURA, config.SEMILLA = t_orig, s_orig
            elegida = 0 if configuracion == "S1" else votar(tarea, muestras)
            final = muestras[elegida]
            reg.update(elegida=elegida, votos=[clave_de_voto(tarea, m["codigo"], m["rechazo"]) for m in muestras])
            reg["respuesta"] = {"codigo": final["codigo"], "rechazo": final["rechazo"], "error": final["error"]}
        else:
            ts = TS.Tareas(raiz=raiz)
            spec = carpeta / "tarea.json"
            spec.write_text(json.dumps({"id": "LAB-001", "titulo": tarea["id"], "instrucciones": tarea["instrucciones"],
                                        "tipo": "funcion_supervisada", "funcion": tarea["funcion"],
                                        "max_iteraciones": MAX_ITER_E3}, ensure_ascii=False), encoding="utf-8")
            tid = ts.importar(spec)["id"]
            stop = ts.lab.ruta("tareas", tid, "STOP")
            vigia.agregar_accion(lambda: stop.write_text("vram", encoding="utf-8"))
            try:
                res = ts.ejecutar(tid, agentes, backend=be, autorizo_pruebas=False)
            finally:
                vigia.acciones.clear()
            base = ts.lab.ruta("tareas", tid, *res["informe"].split("/")).parent
            inf = json.loads((base / "informe.json").read_text(encoding="utf-8"))
            vr = inf.get("version_recomendada") or {}
            cod = "\n\n".join(p.read_text(encoding="utf-8") for p in sorted((base / vr["carpeta"]).glob("**/*.py"))
                              ) if vr.get("carpeta") else ""
            borrador = next(iter(sorted((base / "agentes").glob("*_A1_fs_generar.txt"))), None)
            texto_borrador = borrador.read_text(encoding="utf-8") if borrador else ""
            completada = inf.get("estado_final") == "completada"
            reg["e3"] = {k: inf.get(k) for k in ("estado_final", "resultado", "motivo", "aceptada", "reservas",
                                                 "preguntas", "llamadas")}
            reg["e3"]["pasos"] = (inf.get("limites") or {}).get("pasos")
            reg["respuesta"] = {"codigo": cod, "error": None if completada else inf.get("motivo"),
                                "rechazo": completada and not cod.strip() and (
                                    inf.get("resultado") == "informacion_insuficiente" or bool(texto_borrador.strip()))}
            cb = codigo_de(texto_borrador)
            muestras.append({"texto": texto_borrador, "codigo": cb, "rechazo": es_rechazo(texto_borrador, cb),
                             "error": None, "borrador_e3": True})
    finally:
        if be.estado != "detenido":
            t1 = time.monotonic()
            d = be.detener()
            cierre = {"segundos": round(time.monotonic() - t1, 2), "limpio": d["limpio"], "problemas": d["problemas"]}
    det = be.detencion or {}
    reg["cierre"] = cierre or {"limpio": det.get("limpio"), "problemas": det.get("problemas"), "por": "V2-F.1"}
    reg["servidor_terminado"] = be.srv.proc is None or be.srv.proc.poll() is not None
    reg["metricas"] = _metricas(be, agentes, registro)
    reg["prompt_primer_paso_sha256"] = (hashlib.sha256((agentes.prompts[0]["sistema"] + "\n" + agentes.prompts[0]
                                        ["usuario"]).encode("utf-8")).hexdigest() if agentes.prompts else None)
    reg["muestras"] = [{k: m[k] for k in m if k != "texto"} | {"texto_sha256": hashlib.sha256(
        (m["texto"] or "").encode()).hexdigest(), "texto": (m["texto"] or "")[:4000]} for m in muestras]
    r = reg["respuesta"]
    reg["evaluacion"] = E.evaluar(tarea, oraculo, r["codigo"], rechazo=bool(r["rechazo"]))
    reg["evaluacion_muestras"] = [E.evaluar(tarea, oraculo, m["codigo"], rechazo=m["rechazo"]) for m in muestras]
    if vigia.excedida or (r.get("error") and not r["codigo"]):
        reg["infraestructura"] = vigia.excedida or r["error"]
    reg["segundos_total"] = round(time.monotonic() - t0, 2)
    return reg


# --- análisis (reglas prerregistradas) ----------------------------------------------------------------------------
def signos_exacto(a_gana: int, b_gana: int) -> float | None:
    """p bilateral del test de signos exacto sobre las tareas discordantes (SOLO contexto, no decide)."""
    n = a_gana + b_gana
    if n == 0:
        return None
    k = min(a_gana, b_gana)
    p = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return round(min(1.0, 2 * p), 4)


def analizar(filas: list) -> dict:
    """Tablas y decisiones según el prerregistro. `filas`: [{repeticion, configuracion, tarea, categoria, seguridad,
    segundos_total, tokens_prompt, tokens_generados}]."""
    res = {"por_configuracion": {}, "comparaciones": {}, "estabilidad": {}}
    def de(c, rep):
        return {f["tarea"]: f for f in filas if f["configuracion"] == c and f["repeticion"] == rep}
    for c in CONFIGURACIONES:
        res["por_configuracion"][c] = {}
        for rep in (1, 2):
            fs = [f for f in de(c, rep).values() if f["tarea"] in TAREAS_PRINCIPALES]
            cuenta = {k: sum(1 for f in fs if f["categoria"] == k) for k in E.CATEGORIAS}
            seg = sum(f["segundos_total"] for f in fs)
            res["por_configuracion"][c][rep] = {
                "tareas": len(fs), **cuenta,
                "seguridad": {s: sum(1 for f in fs if f["seguridad"] == s) for s in E.SEGURIDADES},
                "segundos_total": round(seg, 1),
                "segundos_por_correcta": round(seg / cuenta["CORRECTO"], 1) if cuenta["CORRECTO"] else None,
                "tokens_prompt": sum(f["tokens_prompt"] for f in fs),
                "tokens_generados": sum(f["tokens_generados"] for f in fs)}
        r1, r2 = de(c, 1), de(c, 2)
        cambios = [t for t in TAREAS_PRINCIPALES if t in r1 and t in r2 and r1[t]["categoria"] != r2[t]["categoria"]]
        res["estabilidad"][c] = {"cambios": cambios, "inestable": len(cambios) > MAX_CAMBIOS_ESTABLE}
    for a, b in (("E3", "S1x3"), ("E3", "S1"), ("S1x3", "S1")):
        reps = {}
        for rep in (1, 2):
            fa, fb = de(a, rep), de(b, rep)
            ok = lambda f, t: f.get(t, {}).get("categoria") == "CORRECTO"
            solo_a = [t for t in TAREAS_PRINCIPALES if ok(fa, t) and not ok(fb, t)]
            solo_b = [t for t in TAREAS_PRINCIPALES if ok(fb, t) and not ok(fa, t)]
            pa, pb = res["por_configuracion"][a][rep], res["por_configuracion"][b][rep]
            reps[rep] = {"diferencia_correctas": pa["CORRECTO"] - pb["CORRECTO"], "solo_" + a: solo_a,
                         "solo_" + b: solo_b, "signos_p_contexto": signos_exacto(len(solo_a), len(solo_b)),
                         "mas_fallos_seguridad_" + a: pa["FALLO_SEGURIDAD"] > pb["FALLO_SEGURIDAD"]}
        supera = all(reps[r]["diferencia_correctas"] >= UMBRAL_VENTAJA and not reps[r]["mas_fallos_seguridad_" + a]
                     for r in (1, 2))
        inestable = res["estabilidad"][a]["inestable"] or res["estabilidad"][b]["inestable"]
        res["comparaciones"][f"{a}_vs_{b}"] = {
            "repeticiones": reps,
            "dictamen": ("NO SOSTENIBLE: configuración inestable entre repeticiones" if inestable else
                         f"{a} supera a {b} según la regla operativa prerregistrada" if supera else
                         "sin diferencia demostrable con esta muestra"),
            "nota": "regla OPERATIVA fijada de antemano; no demuestra superioridad estadística"}
    e3 = res["comparaciones"]["E3_vs_S1x3"]["dictamen"]
    res["recomendacion"] = ("mantener el equipo A1/A2/A3 (ver tiempo por respuesta correcta)" if e3.startswith("E3 supera")
                            else "simplificar el equipo (menos agentes o roles con herramientas distintas), no ampliarlo")
    return res


# --- puertas --------------------------------------------------------------------------------------------------------
def huella_codigo() -> dict:
    archivos = ["eq3/evaluar_f1.py", "eq3/evaluacion_f1.py", "eq3/servidor_pc.py", "eq3/majflt_windows.py",
                "eq3/lanzador_eq2.py", "eq3/externos_f1.json"]
    return {a: hashlib.sha256((RAIZ / a).read_bytes()).hexdigest() for a in archivos}


def fabrica_real(verificacion: dict, puerto=None):
    def crear():
        return servidor_pc.crear_backend(verificacion, puerto=puerto, srv_kw=dict(max_carga_s=240))
    return crear


def g1() -> dict:
    dif = E.comprobar_prerregistro()
    tareas, oraculos = E.cargar()
    fugas = {tid: E.fugas_de_oraculo(t["instrucciones"], oraculos) for tid, t in tareas.items()}
    fugas = {k: v for k, v in fugas.items() if v}
    return {"ok": not dif and not fugas, "diferencias_prerregistro": dif, "fugas_en_enunciados": fugas,
            "prerregistro": json.loads((E.CARPETA / "PRERREGISTRO_F1.json").read_text(encoding="utf-8"))}


def g2(externos: Path) -> tuple:
    ver = servidor_pc.verificar_externos(externos)
    v = servidor_pc.vram_mib()
    ok = ver["ok"] and v is not None and v["usada"] <= VRAM_OTRAS_MAX
    return {"ok": ok, "externos": {k: ver[k] for k in ("ok", "problemas", "archivos", "segundos", "version")},
            "vram_otras_MiB": v and v["usada"], "maximo_otras_MiB": VRAM_OTRAS_MAX}, ver


def _pid_padre(pid: int):
    import ctypes
    from ctypes import wintypes
    if os.name != "nt":
        try:
            return int(open(f"/proc/{pid}/stat").read().rsplit(")", 1)[1].split()[1])
        except (OSError, ValueError, IndexError):
            return None

    class Entrada(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                    ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_wchar * 260)]
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    k32.Process32FirstW.argtypes = k32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entrada)]
    h = k32.CreateToolhelp32Snapshot(0x2, 0)
    try:
        e = Entrada()
        e.dwSize = ctypes.sizeof(e)
        ok = k32.Process32FirstW(h, ctypes.byref(e))
        while ok:
            if e.th32ProcessID == pid:
                return int(e.th32ParentProcessID)
            ok = k32.Process32NextW(h, ctypes.byref(e))
    finally:
        k32.CloseHandle(h)
    return None


def _interrupcion_real(ver, carpeta: Path, modo: str) -> dict:
    """G3 (modo «stop»: archivo STOP) o G4 (modo «memoria»: umbral del monitor MÁS ESTRICTO, por encima de la memoria
    disponible real) a mitad de una generación larga con Qwen real. Mide la interrupción, el cierre y la VRAM."""
    from eq2 import inferencia, rutas, servidor
    raiz = carpeta / "equipo_f2"
    raiz.mkdir(parents=True)
    lab = rutas.Laboratorio(raiz, raiz / modo)
    lab.crear_base()
    lab.crear_dir("runs", "G")
    llama_antes = servidor_pc.procesos_llama()
    vram0 = servidor_pc.vram_mib()
    be = fabrica_real(ver)()
    marca = {}
    parar = (lambda: "stop_usuario" if lab.existe("STOP") else None)
    out = {"modo": modo, "llama_antes": llama_antes, "vram_antes_MiB": vram0 and vram0["usada"]}
    try:
        be.iniciar({"lab": lab, "run_id": "G", "parar": parar})
        pid = be.srv.pid()
        out.update(pid_servidor=pid, padre_del_servidor=_pid_padre(pid), pid_propio=os.getpid(),
                   carga_s=be.carga_s, vram_cargado_MiB=(servidor_pc.vram_mib() or {}).get("usada"))

        def disparar():
            time.sleep(4.0)                                       # la generación ya está en marcha
            marca["t"] = time.monotonic()
            if modo == "stop":
                lab.crear_exclusivo(("STOP",), "G3")
            else:
                disp = be.mon.ultima["MemAvailable"] if be.mon and be.mon.ultima else None
                marca["mem_disponible_kB"] = disp
                be.mon.umbral_kb = (disp or 0) + 1_000_000        # MÁS estricto que la memoria real disponible
        hilo = threading.Thread(target=disparar, daemon=True)
        hilo.start()
        t0 = time.monotonic()
        try:
            be.completar([{"role": "user", "content": "Escribe un ensayo muy largo y detallado sobre la historia de la "
                                                      "computación, sin resumir y sin terminar pronto."}], 800, 240)
            out["interrumpida"] = False
        except inferencia.ErrorInferencia as e:
            out["interrumpida"], out["motivo"] = True, e.motivo
        t_fin = time.monotonic()
        hilo.join(10)
        out["segundos_peticion"] = round(t_fin - t0, 2)
        out["segundos_hasta_interrupcion"] = round(t_fin - marca["t"], 2) if "t" in marca else None
        out["mem_disponible_kB_al_disparar"] = marca.get("mem_disponible_kB")
    finally:
        t1 = time.monotonic()
        d = be.detener()
        out["cierre"] = {"segundos": round(time.monotonic() - t1, 2), "limpio": d["limpio"], "problemas": d["problemas"],
                         "pasos": d["pasos"]}
        out["servidor_terminado"] = be.srv.proc is None or be.srv.proc.poll() is not None
        out["puerto_libre"] = servidor.puerto_libre(be.srv.puerto)
        t2 = time.monotonic()
        vram = None
        while time.monotonic() - t2 < 20:
            vram = servidor_pc.vram_mib()
            if vram and vram0 and vram["usada"] <= vram0["usada"] + 64:
                break
            time.sleep(0.5)
        out["segundos_hasta_liberar_vram"] = round(time.monotonic() - t1, 2)
        out["vram_despues_MiB"] = vram and vram["usada"]
        out["llama_despues"] = servidor_pc.procesos_llama()
        out["monitor"] = be.mon.resumen() if be.mon else None
    esperado = "stop_usuario" if modo == "stop" else "presion_memoria"
    out["ok"] = bool(out.get("interrumpida") and esperado in str(out.get("motivo"))
                     and out["segundos_hasta_interrupcion"] is not None
                     and out["segundos_hasta_interrupcion"] <= (5 if modo == "stop" else 15)
                     and out["servidor_terminado"] and out["puerto_libre"]
                     and out["padre_del_servidor"] == out["pid_propio"]
                     and out["llama_despues"] == out["llama_antes"]
                     and out["vram_despues_MiB"] is not None and out["vram_antes_MiB"] is not None
                     and out["vram_despues_MiB"] <= out["vram_antes_MiB"] + 64)
    return out


def g5(carpeta: Path) -> dict:
    from eq3 import plataforma
    out, ok = {}, True
    for fase, spec in (("F15", "v31_f1_inestables"), ("F16", "v31_f1_servidor"), ("F17", "v31_f1_majflt"),
                       ("F18", "v31_f1_oraculos")):
        tmp = carpeta / fase
        tmp.mkdir(parents=True)
        r = plataforma.ejecutar([sys.executable, "-B", "v3/mutacion.py", f"v3/mutaciones/{spec}.json"], cwd=RAIZ,
                                env=plataforma.entorno_hijo(tmp), timeout=3600)
        ultima = [l for l in r.stdout.splitlines() if "FIN MUTACI" in l][-1:] or [r.stderr[-200:]]
        out[fase] = {"rc": r.returncode, "resultado": ultima[0].strip()}
        ok = ok and r.returncode == 0
    tmp = carpeta / "V-SRV"
    r = plataforma.ejecutar([sys.executable, "-B", "evidencias/v31_f1/externos/compat_v2f1_clases.py",
                             str(carpeta / "compat.json"), str(tmp)], cwd=RAIZ, env=plataforma.entorno_hijo(carpeta),
                            timeout=3600)
    comp = json.loads((carpeta / "compat.json").read_text(encoding="utf-8")) if (carpeta / "compat.json").is_file() else {}
    out["V-SRV"] = {"rc": r.returncode, "mismas_firmas_que_la_linea_base": comp.get("mismas_firmas_que_la_linea_base")}
    out["ok"] = ok and comp.get("mismas_firmas_que_la_linea_base") is True
    return out


def puertas(externos: Path, salida: Path) -> dict:
    from eq3 import majflt_windows
    salida.mkdir(parents=True)
    res = {"inicio": time.strftime("%Y-%m-%dT%H:%M:%S"), "codigo": huella_codigo()}
    guardar = lambda: (salida / "puertas.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str),
                                                           encoding="utf-8")
    res["G1"] = g1()
    guardar()
    res["G2"], ver = g2(externos)
    guardar()
    res["majflt"] = majflt_windows.activar(salida)
    preparar_contexto()
    for nombre, modo in (("G3", "stop"), ("G4", "memoria")):
        if res["G1"]["ok"] and res["G2"]["ok"]:
            res[nombre] = _interrupcion_real(ver, salida / nombre, modo)
        else:
            res[nombre] = {"ok": False, "motivo": "no se ejecuta: G1 o G2 no pasaron"}
        guardar()
    res["G5"] = g5(salida / "G5")
    res["ok"] = all(res[g]["ok"] for g in ("G1", "G2", "G3", "G4", "G5"))
    res["fin"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    guardar()
    return res


def preparar_contexto():
    from eq2 import config, perfiles_contexto
    config.CTX = CTX
    perfiles_contexto.aplicar(perfiles_contexto.perfil_de_ctx(CTX))


# --- comparación ----------------------------------------------------------------------------------------------------
def comparar(externos: Path, salida: Path, puertas_json: Path, repeticiones=(1, 2), solo_tareas=None) -> dict:
    from eq3 import majflt_windows
    pu = json.loads(puertas_json.read_text(encoding="utf-8"))
    g1_ahora = g1()
    if not pu.get("ok"):
        raise Abortada("las puertas G1–G5 no pasaron")
    if not g1_ahora["ok"] or pu["G1"]["prerregistro"]["sha256"] != g1_ahora["prerregistro"]["sha256"]:
        raise Abortada("el prerregistro cambió o no está intacto desde las puertas")
    if pu["codigo"] != huella_codigo():
        raise Abortada("el código del ejecutor o de los adaptadores cambió desde las puertas")
    salida.mkdir(parents=True)
    tareas, oraculos = E.cargar()
    ids = [t for t in tareas if not solo_tareas or t in solo_tareas]
    res = {"inicio": time.strftime("%Y-%m-%dT%H:%M:%S"), "prerregistro": g1_ahora["prerregistro"],
           "puertas": str(puertas_json.name), "majflt": majflt_windows.activar(salida), "filas": [], "bloques": []}
    preparar_contexto()
    guardar = lambda: (salida / "comparacion.json").write_text(json.dumps(res, ensure_ascii=False, indent=1,
                                                                          default=str), encoding="utf-8")
    for rep in repeticiones:
        for c in ORDEN[rep]:
            ok2, ver = g2(externos)
            bloque = {"repeticion": rep, "configuracion": c, "G2": ok2}
            res["bloques"].append(bloque)
            if not ok2["ok"]:
                bloque["abortado"] = "G2 no pasa al empezar el bloque"
                guardar()
                continue
            vigia = Vigia().iniciar()
            try:
                for tid in ids:
                    carpeta = salida / f"r{rep}" / c / tid
                    if vigia.excedida:
                        fila = {"configuracion": c, "tarea": tid, "infraestructura": "bloque_abortado_vram",
                                "evaluacion": {"categoria": "NO_CONCLUYENTE", "calidad": "NO_CONCLUYENTE",
                                               "seguridad": "sin_respuesta", "motivo": "bloque abortado por VRAM"},
                                "segundos_total": 0, "metricas": {"tokens_prompt": 0, "tokens_generados": 0}}
                    else:
                        fila = ejecutar_tarea(c, tareas[tid], oraculos[tid], oraculos, carpeta,
                                              fabrica_real(ver), vigia)
                    fila["repeticion"] = rep
                    (carpeta.parent / f"{tid}.json").write_text(json.dumps(fila, ensure_ascii=False, indent=1,
                                                                           default=str), encoding="utf-8")
                    res["filas"].append({"repeticion": rep, "configuracion": c, "tarea": tid,
                                         "categoria": fila["evaluacion"]["categoria"],
                                         "calidad": fila["evaluacion"]["calidad"],
                                         "seguridad": fila["evaluacion"]["seguridad"],
                                         "motivo": fila["evaluacion"]["motivo"],
                                         "segundos_total": fila["segundos_total"],
                                         "tokens_prompt": fila["metricas"]["tokens_prompt"],
                                         "tokens_generados": fila["metricas"]["tokens_generados"],
                                         "infraestructura": fila.get("infraestructura"),
                                         "prompt_primer_paso_sha256": fila.get("prompt_primer_paso_sha256")})
                    guardar()
            finally:
                bloque["vram"] = vigia.detener()
                guardar()
    res["analisis"] = analizar(res["filas"])
    res["fin"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    guardar()
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("orden", choices=("puertas", "comparar"))
    ap.add_argument("externos", type=Path)
    ap.add_argument("salida", type=Path)
    ap.add_argument("--puertas", type=Path)
    a = ap.parse_args(argv)
    servidor_pc.preparar_proceso()
    try:
        if a.orden == "puertas":
            r = puertas(a.externos, a.salida)
            print(json.dumps({g: r[g].get("ok") for g in ("G1", "G2", "G3", "G4", "G5")} | {"ok": r["ok"]}))
            return 0 if r["ok"] else 1
        if not a.puertas:
            print("falta --puertas")
            return 2
        r = comparar(a.externos, a.salida, a.puertas)
        print(json.dumps(r["analisis"]["comparaciones"], ensure_ascii=False, default=str)[:2000])
        return 0
    except Abortada as e:
        print(f"ABORTADA: {e}")
        return 2
    except FugaDeOraculo as e:
        print(f"ABORTADA POR FUGA DEL ORÁCULO: {e}")
        return 3


if __name__ == "__main__":
    sys.exit(main())
