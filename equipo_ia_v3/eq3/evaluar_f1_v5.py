"""Equipo IA V3.1 F1 — variante «F1-V5»: cribado de cerebros y equipo de DOS cerebros (`docs/V31_F1_V5.md`).

    python -B -X utf8 eq3/lanzador_eq2.py eq3/evaluar_f1_v5.py puertas  EXTERNOS SALIDA_v5_puertasN
    python -B -X utf8 eq3/lanzador_eq2.py eq3/evaluar_f1_v5.py cribado  EXTERNOS SALIDA_v5_cribadoN --puertas P.json
    python -B -X utf8 eq3/lanzador_eq2.py eq3/evaluar_f1_v5.py equipo   EXTERNOS SALIDA_v5_equipoN  --puertas P.json
                                                                        --cribado SALIDA_v5_cribadoN/comparacion.json
    (parar a mano, de forma ordenada, en cualquier momento:  crear el archivo SALIDA/STOP)

V5 REUTILIZA F1-VRAM-EXP-V4.5.1 (`evaluar_f1_vram_exp_v4_5_1.py`, que NO cambia) tal cual: protocolo térmico, vigía de
VRAM, persona/recursos, Wallpaper Engine, STOP global, control de fugas del oráculo, oráculo estático, tareas, prompts,
temperatura, semillas y topes de salida por paso. Solo cambia, y siempre igual para TODOS los modelos:

- **Cerebros** (`eq3/modelos_v5.json`): Qwen2.5-Coder-7B (el de F1), Qwen3-8B, Granite 3.3 8B y Yi-Coder-9B. Cada uno se
  verifica (SHA-256 completo, con el llama.cpp b12110 de F1) antes de cada bloque.
- **E2 de V5** = E2 de V4.5.1 + caché KV de 8 bits (`-ctk q8_0 -ctv q8_0`) + `--reasoning off` (sin «thinking»), con
  contexto de 4096 (`config.CTX`; el perfil de presupuestos sigue siendo el de 2048: mismos topes por paso que F1).
  Tras cada arranque se exige en `server.log`: todas las capas en GPU, n_ubatch 128, sin `--fit`, n_ctx 4096, K y V
  q8_0 y thinking = 0.
- **Presupuesto de VRAM**: otras aplicaciones ≤ 1100 MiB; pico del servidor de CADA modelo ≤ 6912 − 1100 − 500 = 5312
  MiB (medido en la puerta G15). Tope total 6912 MiB, como siempre.
- **Equipo de dos cerebros** (`BackendMixto`): A1 (generar y corregir) usa el GENERADOR; A2 (revisar) y A3 (casos) usan
  el REVISOR. Nunca hay dos servidores a la vez: antes de cargar el otro modelo se detiene el actual y se comprueba que
  no queda ningún llama vivo. Cada arranque tiene su `server.log` y pasa la misma comprobación E2.

Fases (cada una se lanza a mano, con las puertas de V5 superadas):
1. **Cribado**: S1 de las 15 tareas con los 4 cerebros (1 repetición: con temperatura 0 y semilla fija las dos
   repeticiones de F1 salieron idénticas). Regla prerregistrada (`elegir_equipo`): generador = más CORRECTO; empate →
   menos FALLO_SEGURIDAD; empate → el orden del registro (Qwen2.5 primero). Revisor = el mejor, con la misma regla, de
   OTRA familia que el generador.
2. **Equipo**: S1(generador), E3 con un cerebro (el generador en A1, A2 y A3) y E3 con dos cerebros, 2 repeticiones en
   orden contrabalanceado. Regla de F1: «A supera a B» con ≥ 3 CORRECTO más en las dos repeticiones y no más
   FALLO_SEGURIDAD.
"""
from __future__ import annotations

import argparse
import hashlib
import json
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
from eq3 import evaluar_f1_vram_exp_v4_5_1 as B  # noqa: E402
from eq3 import servidor_pc  # noqa: E402

try:                                                          # V2-F.1 solo acepta backends de su clase base
    from eq2.inferencia import BackendBase as _BaseBackend    # noqa: E402
except ImportError:                                           # sin eq2 en la ruta (p. ej. al leer el módulo)
    _BaseBackend = object

VARIANTE = "F1-V5"
E2 = B.E2 + ["-ctk", "q8_0", "-ctv", "q8_0", "--reasoning", "off"]
CTX = 4096
VRAM_TOPE = B.VRAM_TOPE                                       # 6912, sin cambios
VRAM_OTRAS_MAX = 1100                                         # medido: 850–1057 MiB con el escritorio en la NVIDIA
MARGEN = B.MARGEN                                             # 500, como V4.5.1
PICO_MAX = VRAM_TOPE - VRAM_OTRAS_MAX - MARGEN                # 5312 (Yi-Coder con q8_0 y 4096: 5279 medido)
EXTERNOS_JSON = RAIZ / "eq3" / "externos_f1.json"
MODELOS_JSON = RAIZ / "eq3" / "modelos_v5.json"
ORDEN_MODELOS = ("qwen25", "qwen3", "granite", "yi")          # orden del registro: fija el cribado y desempata
PRERREGISTRO = RAIZ / "evaluacion_f1" / "PRERREGISTRO_F1_V5.json"
UMBRAL_VENTAJA = EV.UMBRAL_VENTAJA                             # 3
ORDEN_EQUIPO = {1: ("S1", "E3_uno", "E3_dos"), 2: ("E3_dos", "E3_uno", "S1")}
RUTA_AGENTES = {"A1": "generador", "A2": "revisor", "A3": "revisor"}


def cargar_modelos() -> dict:
    return json.loads(MODELOS_JSON.read_text(encoding="utf-8"))["modelos"]


# --- E2 de V5: la configuración efectiva, también la caché, el contexto y el «thinking» ---------------------------
def configuracion_efectiva(log: str) -> dict:
    out = B.configuracion_efectiva(log)
    ctx = re.findall(r"llama_context: n_ctx\s+=\s+(\d+)", log)
    kv = re.findall(r"K \((\w+)\):.*V \((\w+)\):", log)
    th = re.findall(r"chat template, thinking = (\d)", log)
    out.update(n_ctx=int(ctx[-1]) if ctx else None, kv=list(kv[-1]) if kv else None,
               thinking=int(th[-1]) if th else None)
    out["ok"] = bool(out["ok"] and out["n_ctx"] == CTX and out["kv"] == ["q8_0", "q8_0"] and out["thinking"] == 0)
    return out


def comprobar_logs(carpeta: Path) -> dict:
    logs = sorted(carpeta.rglob("server.log"))
    efectivas = [configuracion_efectiva(p.read_text(encoding="utf-8", errors="replace")) for p in logs]
    return {"logs": len(logs), "efectivas": efectivas, "ok": bool(efectivas) and all(e["ok"] for e in efectivas)}


@contextmanager
def entorno_v5():
    """En ESTE proceso y solo durante el bloque: las funciones de V4.5.1 usan el E2 y la comprobación de V5, y el
    contexto es 4096 (con el perfil de presupuestos de 2048). Se deshace siempre al salir."""
    from eq2 import config
    antes = (B.E2, B.comprobar_logs, config.CTX)
    EV.preparar_contexto()
    B.E2, B.comprobar_logs, config.CTX = E2, comprobar_logs, CTX
    try:
        yield
    finally:
        B.E2, B.comprobar_logs, config.CTX = antes


# --- externos: el llama de F1 + el cerebro pedido ------------------------------------------------------------------
def registro_de(modelo: str) -> dict:
    reg = json.loads(EXTERNOS_JSON.read_text(encoding="utf-8"))
    m = cargar_modelos()[modelo]
    reg["modelo"] = {k: m[k] for k in ("archivo", "sha256", "bytes")}
    return reg


def verificar(externos: Path, modelo: str) -> dict:
    return servidor_pc.verificar_externos(externos, registro=registro_de(modelo))


def g2(externos: Path, modelo: str) -> tuple:
    ver = verificar(externos, modelo)
    v = servidor_pc.vram_mib()
    ok = ver["ok"] and v is not None and v["usada"] <= VRAM_OTRAS_MAX
    return {"ok": ok, "modelo": modelo, "vram_otras_MiB": v and v["usada"], "maximo_otras_MiB": VRAM_OTRAS_MAX,
            "externos_ok": ver["ok"], "problemas": ver.get("problemas")}, ver


# --- dos cerebros, un solo servidor a la vez -------------------------------------------------------------------------
def paso_de(mensajes) -> str | None:
    """El paso de V2-F.1 (fs_generar, fs_revisar, fs_casos, fs_corregir) cuya instrucción va en el prompt; None si no
    hay exactamente uno."""
    from eq2 import funcion_supervisada as FS
    texto = "\n".join(str(m.get("content", "")) for m in mensajes if isinstance(m, dict))
    hallados = [p for p, instr in FS.INSTR_FS.items() if instr[:120] in texto]
    return hallados[0] if len(hallados) == 1 else None


class BackendMixto(_BaseBackend):
    """Interfaz de `BackendLlama` sobre DOS cerebros. Arranca el generador; cuando una petición es de un agente del otro
    cerebro, DETIENE el servidor actual, comprueba que no queda ningún llama y arranca el otro (run_id y `server.log`
    propios). Un paso que no se reconoce va al generador y se anota (`pasos_desconocidos`)."""
    etiqueta = "MIXTO_V5"
    simulado = False

    def __init__(self, fabricas: dict, ruta=None, procesos=servidor_pc.procesos_llama, paso=paso_de):
        from eq2 import funcion_supervisada as FS
        self.fabricas, self.ruta, self.procesos, self.paso_de = fabricas, dict(ruta or RUTA_AGENTES), procesos, paso
        self.agente_paso = dict(FS.AGENTE_FS)
        self.usados, self.actual, self.rol_actual = [], None, None
        self.ctx, self.cambios, self.pasos_desconocidos = {}, [], 0
        self.detencion = None

    # lo que V2-F.1 y el evaluador leen del backend
    estado = property(lambda s: s.actual.estado if s.actual else "nuevo")
    srv = property(lambda s: s.actual.srv)
    mon = property(lambda s: s.actual.mon if s.actual else None)
    carga_s = property(lambda s: round(sum(b.carga_s or 0 for b in s.usados), 2) if s.usados else None)
    soporta_continuacion = property(lambda s: bool(s.actual and s.actual.soporta_continuacion))
    peticiones = property(lambda s: [p for b in s.usados for p in b.peticiones])
    comprobaciones = property(lambda s: s.actual.comprobaciones if s.actual else None)

    def comprobar(self, verificar_flags=True):
        return self.fabricas["generador"]().comprobar(verificar_flags)

    def _arrancar(self, rol):
        be = self.fabricas[rol]()
        ctx = dict(self.ctx)
        if self.usados:                                     # cada arranque, su carpeta y su server.log
            ctx["run_id"] = f"{self.ctx['run_id']}_c{len(self.usados)}"
            ctx["lab"].crear_dir("runs", ctx["run_id"])
        self.usados.append(be)
        self.actual, self.rol_actual = be, rol
        be.iniciar(ctx)

    def iniciar(self, ctx=None):
        if self.usados:
            from eq2.inferencia import ErrorInferencia
            raise ErrorInferencia("backend_ya_usado", fatal=True)
        self.ctx = ctx or {}
        self._arrancar("generador")

    def _cambiar(self, rol):
        from eq2.inferencia import ErrorInferencia
        t0 = time.monotonic()
        d = self.actual.detener()
        vivos = self.procesos()
        c = {"de": self.rol_actual, "a": rol, "cierre_ok": d["ok"], "limpio": d["limpio"], "llama_tras_parar": vivos}
        self.cambios.append(c)
        if not d["ok"] or not d["limpio"] or vivos is None or vivos:
            raise ErrorInferencia(f"cambio_de_cerebro_fallido: {c}", fatal=True)
        self._arrancar(rol)
        c["segundos"] = round(time.monotonic() - t0, 2)

    def completar(self, mensajes, max_tokens, plazo_s):
        paso = self.paso_de(mensajes)
        if paso is None:
            self.pasos_desconocidos += 1
        rol = self.ruta.get(self.agente_paso.get(paso), "generador")
        if rol != self.rol_actual:
            self._cambiar(rol)
        return self.actual.completar(mensajes, max_tokens, plazo_s)

    def supervisar(self):
        return self.actual.supervisar() if self.actual else None

    def detener(self):
        if self.detencion is not None:
            return self.detencion
        if self.actual is not None:
            self.actual.detener()
        todos = [b.detencion for b in self.usados if b.detencion] or [{"ok": True, "limpio": True, "problemas": []}]
        self.detencion = {"ok": all(x["ok"] for x in todos), "limpio": all(x["limpio"] for x in todos),
                          "problemas": [p for x in todos for p in x["problemas"]], "cambios": self.cambios,
                          "pasos_desconocidos": self.pasos_desconocidos, "informe": self.informe()}
        return self.detencion

    def informe(self):
        return {"etiqueta": self.etiqueta, "arranques": [b.informe() for b in self.usados], "cambios": self.cambios,
                "pasos_desconocidos": self.pasos_desconocidos}


def fabrica_uno(ver):
    return B.fabrica_e2(ver)


def fabrica_dos(ver_g, ver_r):
    def crear():
        return BackendMixto({"generador": B.fabrica_e2(ver_g), "revisor": B.fabrica_e2(ver_r)})
    return crear


# --- reglas prerregistradas -----------------------------------------------------------------------------------------
def cuenta(filas, etiqueta, rep=None) -> dict:
    fs = [f for f in filas if f["configuracion"] == etiqueta and (rep is None or f["repeticion"] == rep)]
    out = {k: sum(1 for f in fs if f["categoria"] == k) for k in EV.E.CATEGORIAS}
    out["n"], out["infraestructura"] = len(fs), sum(1 for f in fs if f.get("infraestructura"))
    out["segundos_total"] = round(sum(f.get("segundos_total") or 0 for f in fs), 1)
    return out


def elegir_equipo(filas, modelos=None, n_tareas=None) -> dict:
    """Cribado → (generador, revisor). Solo cuentan los modelos con TODAS sus filas y sin fallos de infraestructura."""
    modelos = modelos or cargar_modelos()
    n_tareas = n_tareas or len(EV.E.cargar()[0])
    cand = []
    for i, m in enumerate(ORDEN_MODELOS):
        c = cuenta(filas, f"S1@{m}")
        if c["n"] == n_tareas and not c["infraestructura"]:
            cand.append(((-c["CORRECTO"], c["FALLO_SEGURIDAD"], i), m, c))
    cand.sort(key=lambda x: x[0])
    if not cand:
        return {"ok": False, "motivo": "ningún modelo completó el cribado"}
    gen = cand[0][1]
    otros = [x for x in cand if modelos[x[1]]["familia"] != modelos[gen]["familia"]]
    if not otros:
        return {"ok": False, "generador": gen, "motivo": "ningún modelo de otra familia completó el cribado"}
    return {"ok": True, "generador": gen, "revisor": otros[0][1], "clasificacion": [(x[1], x[2]) for x in cand]}


def supera(filas, a, b, reps=(1, 2)) -> dict:
    """La regla de F1: ≥ UMBRAL_VENTAJA CORRECTO más en TODAS las repeticiones y no más FALLO_SEGURIDAD."""
    dif = {r: cuenta(filas, a, r)["CORRECTO"] - cuenta(filas, b, r)["CORRECTO"] for r in reps}
    seg = cuenta(filas, a)["FALLO_SEGURIDAD"] <= cuenta(filas, b)["FALLO_SEGURIDAD"]
    return {"diferencia_correctas": dif, "no_mas_fallos_seguridad": seg,
            "supera": all(d >= UMBRAL_VENTAJA for d in dif.values()) and seg}


# --- prerregistro ----------------------------------------------------------------------------------------------------
ARCHIVOS_V5 = ["eq3/evaluar_f1_v5.py", "eq3/modelos_v5.json", "pruebas/test_eq3_evaluar_f1_v5.py",
               "v3/mutaciones/v31_f1_v5.json", "evaluacion_f1/prerregistrar_v5.py", "docs/V31_F1_V5.md",
               "evaluacion_f1/PRERREGISTRO_F1_VRAM_EXP_v4_5_1.json", "eq3/evaluar_f1_vram_exp_v4_5_1.py",
               "eq3/termica_v4_5.py", "eq3/externos_f1.json", "eq3/servidor_pc.py"]


def huella_codigo() -> dict:
    return B.huella_codigo() | {a: hashlib.sha256((RAIZ / a).read_bytes()).hexdigest() if (RAIZ / a).is_file()
                                else None for a in ("eq3/evaluar_f1_v5.py", "eq3/modelos_v5.json",
                                                    "evaluacion_f1/PRERREGISTRO_F1_V5.json")}


def comprobar_v5() -> list:
    if not PRERREGISTRO.is_file():
        return ["falta PRERREGISTRO_F1_V5.json"]
    pre = json.loads(PRERREGISTRO.read_text(encoding="utf-8"))
    dif = [rel for rel, h in pre["sha256"].items()
           if not (RAIZ / rel).is_file() or hashlib.sha256((RAIZ / rel).read_bytes()).hexdigest() != h]
    lim = pre.get("limites", {})
    if pre.get("variante") != VARIANTE or pre.get("llama_e2") != E2 or pre.get("ctx") != CTX \
            or lim.get("vram_tope_MiB") != VRAM_TOPE or lim.get("vram_otras_max_MiB") != VRAM_OTRAS_MAX \
            or lim.get("pico_max_MiB") != PICO_MAX:
        dif.append("variante, E2, contexto o límites del prerregistro V5")
    return dif + [f"V4.5.1:{d}" for d in B.comprobar_v4()]


# --- bucle de V5: bloques explícitos, cada uno con su(s) cerebro(s) --------------------------------------------------
def ejecutar_bloques(res, salida, tareas, oraculos, ids, bloques, ejecutar, g2_fn, esperar, vigia_fn,
                     guardar=lambda: None):
    """`X.ejecutar_bucle` con bloques explícitos. bloques = [(rep, etiqueta, base, crear_fabrica, modelos)];
    `crear_fabrica(vers)` da la fábrica de la tarea con las verificaciones del bloque (una por rol)."""
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
            fila["bloque_v5"], fila["modelos"] = etiqueta, modelos
            carpeta.mkdir(parents=True, exist_ok=True)
            (carpeta / "fila.json").write_text(json.dumps(fila, ensure_ascii=False, indent=1, default=str),
                                               encoding="utf-8")
            ev = fila["evaluacion"]
            met = fila.get("metricas") or {}
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


def bloques_cribado() -> list:
    return [(1, f"S1@{m}", "S1", (lambda vers: fabrica_uno(vers["generador"])), {"generador": m})
            for m in ORDEN_MODELOS]


def bloques_equipo(gen: str, rev: str) -> list:
    f = {"S1": ("S1", lambda vers: fabrica_uno(vers["generador"]), {"generador": gen}),
         "E3_uno": ("E3", lambda vers: fabrica_uno(vers["generador"]), {"generador": gen}),
         "E3_dos": ("E3", lambda vers: fabrica_dos(vers["generador"], vers["revisor"]),
                    {"generador": gen, "revisor": rev})}
    etiq = {"S1": f"S1@{gen}", "E3_uno": f"E3@{gen}", "E3_dos": f"E3@{gen}+{rev}"}
    return [(rep, etiq[k], f[k][0], f[k][1], f[k][2]) for rep in (1, 2) for k in ORDEN_EQUIPO[rep]]


def analizar(filas) -> dict:
    etiquetas = list(dict.fromkeys(f["configuracion"] for f in filas))
    return {"por_configuracion": {e: cuenta(filas, e) for e in etiquetas}}


def evaluar(fase: str, externos: Path, salida: Path, puertas_json: Path, cribado_json: Path | None = None) -> dict:
    from eq3 import majflt_windows
    if "v5" not in str(salida).lower():
        raise EV.Abortada("los resultados de V5 van en una carpeta con «v5» en el nombre")
    pu = json.loads(puertas_json.read_text(encoding="utf-8"))
    if pu.get("variante") != VARIANTE or not pu.get("ok"):
        raise EV.Abortada("las puertas de F1-V5 no pasaron")
    if comprobar_v5():
        raise EV.Abortada(f"prerregistros V1–V5 no intactos: {comprobar_v5()[:5]}")
    if pu.get("codigo") != huella_codigo():
        raise EV.Abortada("el código o el prerregistro cambiaron desde las puertas")
    if fase == "cribado":
        bloques, eleccion = bloques_cribado(), None
    else:
        cr = json.loads(cribado_json.read_text(encoding="utf-8"))
        if cr.get("variante") != VARIANTE or cr.get("fase") != "cribado" or not cr.get("valida"):
            raise EV.Abortada("el cribado indicado no es un cribado V5 válido")
        eleccion = elegir_equipo(cr["filas"])
        if not eleccion["ok"]:
            raise EV.Abortada(f"sin equipo: {eleccion['motivo']}")
        bloques = bloques_equipo(eleccion["generador"], eleccion["revisor"])
    salida.mkdir(parents=True)
    tareas, oraculos = EV.E.cargar()
    res = {"variante": VARIANTE, "fase": fase, "inicio": time.strftime("%Y-%m-%dT%H:%M:%S"), "llama_e2": E2,
           "ctx": CTX, "limites": {"vram_tope_MiB": VRAM_TOPE, "vram_otras_max_MiB": VRAM_OTRAS_MAX,
                                   "pico_max_MiB": PICO_MAX},
           "eleccion": eleccion, "majflt": majflt_windows.activar(salida), "filas": [], "bloques": [], "pausas": []}
    guardar = lambda: (salida / "comparacion.json").write_text(json.dumps(res, ensure_ascii=False, indent=1,
                                                                          default=str), encoding="utf-8")
    B._STOP_GLOBAL = salida / "STOP"
    termica = B.nueva_termica(salida / "termica.jsonl")
    with entorno_v5(), B.termica_activa(termica.iniciar()), \
            B.fondo_gestionado(B.FondoAnimado(marca=salida / "fondo_detenido.marca")) as fondo:
        try:
            inicio = B.esperar_v4(fondo, ventana_s=X.VENTANA_INICIO_S, max_espera_s=0)
            res["condiciones_inicio"], res["termica_inicio"] = inicio, termica.enfriar()
            if not inicio["ok"] or not res["termica_inicio"]["ok"]:
                raise EV.Abortada(f"no se inicia: {inicio['motivos']} {res['termica_inicio']}")
            ejecutar_bloques(res, salida, tareas, oraculos, list(tareas), bloques, ejecutar=B.ejecutar_tarea_e2,
                             g2_fn=lambda m: g2(externos, m),
                             esperar=lambda: B.esperar_v45(fondo, pausas=res["pausas"]),
                             vigia_fn=lambda: B.VigiaTermica(act=B.actividad_vigia), guardar=guardar)
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
    res["analisis"] = analizar(res["filas"])
    if fase == "cribado":
        res["analisis"]["eleccion"] = elegir_equipo(res["filas"])
        res["analisis"]["frente_a_qwen25"] = {m: supera(res["filas"], f"S1@{m}", "S1@qwen25", reps=(1,))
                                              for m in ORDEN_MODELOS[1:]}
    else:
        g, r = eleccion["generador"], eleccion["revisor"]
        dos, uno, s1 = f"E3@{g}+{r}", f"E3@{g}", f"S1@{g}"
        res["analisis"]["hipotesis"] = {"H1_dos_supera_a_S1": supera(res["filas"], dos, s1),
                                        "H2_dos_supera_a_uno": supera(res["filas"], dos, uno),
                                        "uno_supera_a_S1": supera(res["filas"], uno, s1)}
    res["fin"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    guardar()
    return res


# --- puertas de V5 -------------------------------------------------------------------------------------------------
def pico(ver, carpeta: Path, modelo: str) -> dict:
    """G15: el pico real del servidor de `modelo` con E2 de V5 y un prompt largo (≈ 1800 tokens)."""
    out = B.pico_e2(ver, carpeta)
    out["modelo"] = modelo
    p = out.get("qwen_pico_MiB")
    out["ok"] = bool(out.get("error") is None and out["cierre_limpio"] and out["llama_efectiva"]["ok"]
                     and p is not None and p <= PICO_MAX and not out["llama_despues"])
    return out


def cambio_real(ver_g, ver_r, carpeta: Path) -> dict:
    """G16: BackendMixto REAL: generador → revisor → generador con las instrucciones de V2-F.1 (A1, A2, A1). En ningún
    momento puede haber dos llama vivos; cada arranque debe pasar E2 de V5; todo debe cerrarse limpio."""
    from eq2 import funcion_supervisada as FS
    lab = B._lab(carpeta, "M")
    base = (servidor_pc.vram_mib() or {}).get("usada")
    vig = X.VigiaExp(act=B.actividad_vigia, intervalo=0.5).iniciar()
    maximo, fin = {"n": 0}, threading.Event()

    def contar():
        while not fin.is_set():
            maximo["n"] = max(maximo["n"], len(servidor_pc.procesos_llama() or []))
            fin.wait(0.5)
    hilo = threading.Thread(target=contar, daemon=True)
    hilo.start()
    be = fabrica_dos(ver_g, ver_r)()
    out = {"vram_antes_MiB": base, "respuestas": []}
    try:
        be.iniciar({"lab": lab, "run_id": "M", "parar": vig.parar})
        for paso in ("fs_generar", "fs_revisar", "fs_corregir"):
            m = [{"role": "system", "content": FS.INSTR_FS[paso]}, {"role": "user", "content": "Tarea: suma(a, b)."}]
            r = be.completar(m, 40, 120)
            out["respuestas"].append({"paso": paso, "rol": be.rol_actual, "tokens": getattr(r, "tokens_gen", None)})
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {getattr(e, 'motivo', e)}"
    finally:
        d = be.detener()
        out["vigia"] = vig.detener()
        fin.set()
        hilo.join(2)
    out.update(cierre_limpio=d["limpio"], cambios=d["cambios"], max_llama_a_la_vez=maximo["n"],
               llama_despues=servidor_pc.procesos_llama(), llama_efectiva=comprobar_logs(carpeta))
    out["ok"] = bool(out.get("error") is None and [x["rol"] for x in out["respuestas"]] ==
                     ["generador", "revisor", "generador"] and len(d["cambios"]) == 2 and d["limpio"]
                     and out["max_llama_a_la_vez"] <= 1 and not out["llama_despues"]
                     and out["llama_efectiva"]["logs"] == 3 and out["llama_efectiva"]["ok"]
                     and out["vigia"]["excedida"] is None)
    return out


def g5(carpeta: Path) -> dict:
    """G5: batería de mutaciones de V5 (F27). Las de V1–V4.5.1 siguen valiendo porque su código no cambia (G1)."""
    from eq3 import plataforma
    tmp = carpeta / "F27"
    tmp.mkdir(parents=True)
    r = plataforma.ejecutar([sys.executable, "-B", "v3/mutacion.py", "v3/mutaciones/v31_f1_v5.json"], cwd=RAIZ,
                            env=plataforma.entorno_hijo(tmp), timeout=3600)
    ultima = [l for l in r.stdout.splitlines() if "FIN MUTACI" in l][-1:] or [r.stderr[-200:]]
    return {"F27": {"rc": r.returncode, "resultado": ultima[0].strip()}, "ok": r.returncode == 0}


PUERTAS = ("G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9", "G10", "G11", "G12", "G13", "G14", "G15", "G16")


def puertas(externos: Path, salida: Path, con_g5=True) -> dict:
    """G1 integridad (V1–V5), G2 externos de los 4 cerebros y VRAM ajena ≤ 1100, G3 STOP, G4 RAM, G5 mutaciones de V5,
    G6 persona y recursos, G7 fondo animado, G8 tope de VRAM, G9 fallo de arranque, G10 pruebas de V5 y de V4.5.1,
    G11 sensores, G12 corte térmico, G13 interferencia externa, G14 STOP global (las reales de V4.5.1, con E2 de V5 y el
    cerebro más grande, Yi-Coder), G15 pico de VRAM de CADA cerebro ≤ 5312 MiB, G16 cambio real de cerebro."""
    from eq3 import majflt_windows
    if "v5" not in str(salida).lower():
        raise EV.Abortada("las puertas de V5 van en una carpeta con «v5» en el nombre")
    salida.mkdir(parents=True)
    res = {"variante": VARIANTE, "inicio": time.strftime("%Y-%m-%dT%H:%M:%S"), "codigo": huella_codigo(),
           "llama_e2": E2, "ctx": CTX, "limites": {"vram_tope_MiB": VRAM_TOPE, "vram_otras_max_MiB": VRAM_OTRAS_MAX,
                                                    "pico_max_MiB": PICO_MAX}}
    guardar = lambda: (salida / "puertas.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str),
                                                           encoding="utf-8")
    dif, g1e = comprobar_v5(), EV.g1()
    res["G1"] = {"ok": not dif and g1e["ok"], "diferencias": dif, "v2_y_fugas": {k: g1e[k] for k in (
        "ok", "diferencias_prerregistro", "fugas_en_enunciados")}}
    guardar()
    v5 = B._unittest("test_eq3_evaluar_f1_v5.py", salida / "G10" / "v5")
    v451 = B._unittest("test_eq3_*_v4_5_1.py", salida / "G10" / "v4_5_1")
    res["G10"] = {"v5": v5, "v4_5_1": v451, "ok": v5["rc"] == 0 and v451["rc"] == 0}
    guardar()
    res["G5"] = g5(salida / "G5") if con_g5 else {"ok": False, "motivo": "no ejecutada"}
    guardar()
    res["G11"] = B.sensores_reales(salida / "G11")
    res["G13"] = B.interferencia_externa_real(salida / "G13")
    guardar()
    llama_inicio = servidor_pc.procesos_llama()
    with B.fondo_gestionado(B.FondoAnimado(marca=salida / "fondo_detenido.marca")) as fondo:
        res["G6"] = B.esperar_v4(fondo, ventana_s=X.VENTANA_INICIO_S, max_espera_s=0)
        res["G7_detencion"] = {"registro": list(fondo.registro), "vram_wallpaper_MiB": B._vram_fondo()}
        res["G2"], vers = {"ok": True, "modelos": {}}, {}
        for m in ORDEN_MODELOS:
            r2, vers[m] = g2(externos, m)
            res["G2"]["modelos"][m] = r2
            res["G2"]["ok"] = res["G2"]["ok"] and r2["ok"]
        guardar()
        res["majflt"] = majflt_windows.activar(salida)
        previas = all(res[g]["ok"] for g in ("G1", "G2", "G6", "G11", "G13"))
        yi = vers.get("yi")
        pruebas = [("G15", lambda: {m: pico(vers[m], salida / "G15" / m, m) for m in ORDEN_MODELOS}),
                   ("G16", lambda: cambio_real(vers.get("qwen25"), vers.get("granite"), salida / "G16")),
                   ("G3", lambda: EV._interrupcion_real(yi, salida / "G3", "stop")),
                   ("G4", lambda: EV._interrupcion_real(yi, salida / "G4", "memoria")),
                   ("G8", lambda: B.corte_vram_real(yi, salida / "G8")),
                   ("G9", lambda: B.fallo_arranque_real(yi, salida / "G9")),
                   ("G12", lambda: B.corte_termico_real(yi, salida / "G12")),
                   ("G14", lambda: B.stop_global_real(yi, salida / "G14"))]
        with entorno_v5(), B._fabrica_e2_en_ev():
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
                    r["llama_efectiva"] = comprobar_logs(salida / nombre)
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
