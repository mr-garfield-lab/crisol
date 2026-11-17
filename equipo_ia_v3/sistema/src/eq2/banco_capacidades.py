"""V2-F: BANCO COMPARATIVO de capacidades — un agente frente al equipo, mismas tareas, ORÁCULOS OCULTOS.

Modos (todos sobre las mismas tareas de bancos/capacidades_v1 y el mismo backend):
  individual             A1 resuelve en UNA llamada (el mismo prompt que su propuesta en el debate).
  individual_autoprueba  A1 propone código y sus casos; el controlador ejecuta esos casos y los ejemplos del
                         enunciado; si algo falla, A1 repara UNA vez con la evidencia (2 llamadas como mucho).
  equipo_debate          debate por evidencias (debate.py): 6–7 llamadas.
  equipo_motor           motor V2-F (motor_v2f.py): plan, código, pruebas de A2, revisión y contraejemplos de A3…
Calidad: la solución final de cada modo se ejecuta contra los ORÁCULOS OCULTOS (bancos/.../oraculos.json), que
nunca entran en un prompt. Además se mide: llamadas, tokens (medidos con Qwen; ESTIMADOS len/3 en simulación),
tiempo de pared, proyección de tiempo en el S23, errores (formato, casos rechazados, afirmaciones sin evidencia) y
CERTEZA: un modo «afirma» éxito cuando su conclusión es cumple_oraculo/consistente/verificado/autoprueba_ok; si el
oráculo oculto la contradice es una FALSA CERTEZA.

Modo SIMULADO (`BackendGuion` + `PoliticaSimulada`): los agentes reciben los MISMOS prompts que recibiría Qwen y
responden con variantes de código y casos de bancos/.../simulacion.json según PARÁMETROS documentados (probabilidad
de acierto, correlación entre agentes, de reparar con evidencia, de insistir…). La ejecución de las pruebas es REAL.
Lo que demuestra: que el protocolo, las métricas y la evaluación oculta funcionan y son reproducibles (misma semilla
=> mismo resultado). Lo que NO demuestra: que el equipo supere al individuo con Qwen; eso depende de los parámetros
del guion y solo lo mide el modo REAL en el S23.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path

from . import (VERSION, archivos, casos as C, config, contexto, debate, ejecutor_restringido, herramientas, motor,
               motor_v2f, rutas)
from .inferencia import BackendBase, Respuesta

MODOS = ("individual", "individual_autoprueba", "equipo_debate", "equipo_motor")
AFIRMA_EXITO = {"individual_autoprueba": ("autoprueba_ok",),
                "equipo_debate": debate.DECISIONES_EXITO,
                "equipo_motor": ("criterios_verificados", "verificado_con_reservas")}
# Velocidades MEDIDAS en el Galaxy S23 con Qwen2.5-Coder-3B Q4_K_M (prueba3, escenarios A y B: generación 8,1–10,5 tok/s,
# procesamiento de entrada 3,2–13,6 tok/s). Solo sirven para PROYECTAR el tiempo; no son medidas de esta ejecución.
VELOCIDAD_S23 = {"generacion_tok_s": 9.3, "entrada_tok_s": 10.5}
SEMILLAS_FIJAS = (11, 42, 2026)
MAX_JSON = 1_000_000


class BancoInvalido(ValueError):
    pass


def _sha(b) -> str:
    return hashlib.sha256(b if isinstance(b, bytes) else str(b).encode("utf-8")).hexdigest()


def cargar(carpeta: Path) -> dict:
    """Lee el banco (solo lectura). Comprueba formato y que oráculos y tareas casan."""
    def leer(n):
        p = carpeta / n
        if p.is_symlink() or not p.is_file() or p.stat().st_size > MAX_JSON:
            raise BancoInvalido(f"{n}: no es un archivo normal o es demasiado grande")
        return p.read_bytes()
    bt, bo, bs = leer("tareas.json"), leer("oraculos.json"), leer("simulacion.json")
    t, o, s = json.loads(bt), json.loads(bo), json.loads(bs)
    ids = [x["id"] for x in t["tareas"]]
    if sorted(ids) != sorted(o["oraculos"]) or sorted(ids) != sorted(s["tareas"]):
        raise BancoInvalido("tareas, oráculos y simulación no tienen las mismas tareas")
    for x in t["tareas"]:
        if len(x["instrucciones"]) > config.MAX_TAREA_CHARS:
            raise BancoInvalido(f"{x['id']}: instrucciones demasiado largas")
    oraculos = {k: [C.parsear_expresion(e, "usuario", f"O{i}") for i, e in enumerate(v, 1)]
                for k, v in o["oraculos"].items()}
    return {"nombre": t["banco"], "tareas": t["tareas"], "oraculos": oraculos, "simulacion": s,
            "sha256": _sha(bt + b"\0" + bo), "sha256_simulacion": _sha(bs)}


# --- backend y política SIMULADOS -------------------------------------------------------------------------------
_PASOS = sorted(list(debate.INSTR_DEBATE.items()) + list(motor_v2f.INSTR_V2F.items()), key=lambda kv: -len(kv[1]))


def identificar(mensajes) -> tuple:
    """(paso, agente) a partir del prompt REAL: el texto del usuario empieza por la instrucción del paso y el
    sistema dice «Eres A<n>»."""
    sistema = mensajes[0]["content"] if mensajes else ""
    usuario = mensajes[-1]["content"] if mensajes else ""
    m = re.search(r"Eres (A[123]),", sistema)
    agente = m.group(1) if m else None
    cand = [p for p, instr in _PASOS if usuario.startswith(instr)]
    por_agente = [p for p in cand if agente and p.endswith("_" + agente.lower())]
    return ((por_agente or cand or ["desconocido"])[0], agente)


class BackendGuion(BackendBase):
    """Backend SIMULADO del banco: recibe los prompts reales y responde con la política. Tokens ESTIMADOS (len/3)."""
    etiqueta = "SIMULADO_BANCO"
    simulado = True

    def __init__(self, politica):
        self.politica = politica
        self.prompts = []                                # para comprobar que ningún oráculo oculto llega al modelo

    def completar(self, mensajes, max_tokens, plazo_s):
        paso, agente = identificar(mensajes)
        texto = self.politica.responder(paso, agente, mensajes[-1]["content"]) or ""
        self.prompts.append({"paso": paso, "agente": agente, "texto": "\n".join(m["content"] for m in mensajes)})
        tp = contexto.estimar_tokens(self.prompts[-1]["texto"]) + 2 * config.TOKENS_POR_MENSAJE
        return Respuesta(texto=texto, tokens_prompt=tp, tokens_gen=min(max_tokens, contexto.estimar_tokens(texto)),
                         finish_reason="stop")


class PoliticaSimulada:
    """Comportamiento PARAMETRIZADO de A1/A2/A3 para una tarea. Determinista: u(...) sale de SHA-256(semilla, tarea,
    modo, claves). Los textos imitan el formato pedido; NO son salidas de Qwen."""

    def __init__(self, sim: dict, tarea: dict, semilla: int, modo: str, parametros: dict):
        self.sim, self.tarea, self.semilla, self.modo, self.p = sim, tarea, semilla, modo, dict(parametros)
        self.funcion = tarea["funcion"]
        self.variantes = sim["variantes"]
        self.pool_ok = [c["caso"] for c in sim["casos_agentes"] if c["correcto"]]
        self.pool_mal = [c["caso"] for c in sim["casos_agentes"] if not c["correcto"]]
        self.ejemplos = {c.clave() for c in C.ejemplos_del_enunciado(tarea["instrucciones"])}
        self.var, self._elegidas, self.escritos = {}, {}, {}
        self.pruebas_a2, self.revisiones_a3, self.intentos = {}, 0, {}

    def u(self, *claves) -> float:
        h = _sha("|".join(map(str, (self.semilla, self.tarea["id"], self.modo) + claves)))
        return int(h[:12], 16) / float(16 ** 12)

    def correcto(self, clave) -> bool:
        return clave in self.pool_ok or clave in self.ejemplos

    def elegir_variante(self, agente) -> str:
        if agente in self._elegidas:
            return self._elegidas[agente]
        if agente != "A1" and self.u("correlacion", agente) < self.p["correlacion"]:
            v = self.elegir_variante("A1")
        elif self.u("acierto", agente) < self.p["p_acierto"]:
            v = "correcta"
        else:
            malas = sorted(x for x in self.variantes if x != "correcta")
            v = malas[int(self.u("defecto", agente) * len(malas)) % len(malas)]
        self._elegidas[agente] = v
        return v

    def casos(self, agente, k, etapa) -> list:
        out = []
        for i in range(k):
            fuente = self.pool_mal if (self.pool_mal and self.u("err", agente, etapa, i) < self.p["p_caso_erroneo"]) \
                else self.pool_ok
            libres = [c for c in fuente if c not in out] or [c for c in self.pool_ok if c not in out]
            if not libres:
                break
            out.append(libres[int(self.u("pick", agente, etapa, i) * len(libres)) % len(libres)])
        self.escritos.setdefault(agente, []).extend(out)
        return out

    def _codigo(self, agente, extra="") -> str:
        v = self.var.get(agente) or self.elegir_variante(agente)
        self.var[agente] = v
        return f"ARCHIVO: solucion.py\n```python\n{self.variantes[v]['codigo']}```\n{extra}FIN"

    def _reparar_si(self, agente, fallidas, clave_u) -> None:
        # cada intento es independiente (p_reparar por intento): volver a intentarlo con evidencia puede salir bien
        self.intentos[agente] = self.intentos.get(agente, 0) + 1
        if self.var.get(agente) != "correcta" and any(self.correcto(c) for c in fallidas) \
                and self.u("reparar", agente, clave_u, self.intentos[agente]) < self.p["p_reparar"]:
            self.var[agente] = "correcta"

    # --- respuestas ---------------------------------------------------------------------------------------
    def responder(self, paso, agente, usuario) -> str:
        if paso.startswith("propuesta_"):
            self.var[agente] = self.elegir_variante(agente)
            cs = self.casos(agente, 2, "prop")
            return self._codigo(agente, "".join(f"CASO: {c}\n" for c in cs))
        if paso.startswith("cuestionar_"):
            return self._cuestionar(agente, usuario)
        if paso.startswith("reparar_"):
            fallidas = re.findall(r"^[A-Za-z0-9_-]+: (.+?) -> ", usuario, re.MULTILINE)
            self._reparar_si(agente, fallidas, "debate")
            return self._codigo(agente, "CAMBIOS: corrijo los casos que fallaban\n")
        return getattr(self, "_m_" + paso, lambda a, u: "")(agente, usuario)

    def _cuestionar(self, agente, usuario) -> str:
        casos_ev = re.findall(r"^(\S+) \[(\w+)\] (.+)$", usuario, re.MULTILINE)
        filas = re.findall(r"^(P[1-3]r?) \((A[1-3])\): cumple (\d+)/(\d+)", usuario, re.MULTILINE)
        lineas = []
        propia = debate.CAND[agente]
        if filas:
            mejor = max(int(k) for _, _, k, _ in filas)
            mejores = sorted(p for p, _, k, _ in filas if int(k) == mejor)
            pos = propia if (propia in mejores or self.u("terco", agente) < self.p["p_terco"]) else mejores[0]
            lineas.append(f"POSICION: {pos} | MOTIVO: {'cumple más casos' if pos in mejores else 'prefiero la mía'}")
        fallan_todas = {cid for cid, _, _ in casos_ev
                        if filas and all(re.search(rf"(?:falla |; ){re.escape(cid)}->", l) for l in
                                         re.findall(r"^P[1-3]r? \(A[1-3]\): cumple.*$", usuario, re.MULTILINE))}
        for cid, fuente, clave in casos_ev:
            if fuente == agente and clave in self.pool_mal and cid in fallan_todas \
                    and self.u("retira_propio", cid) < self.p["p_retira"]:
                lineas.append(f"IMPUGNO: {cid} | retiro mi caso: todas las implementaciones lo contradicen")
            elif fuente in ("A1", "A2", "A3") and fuente != agente:
                if clave in self.pool_mal and self.u("impugna_mal", agente, cid) < self.p["p_impugna_erroneo"]:
                    lineas.append(f"IMPUGNO: {cid} | no corresponde a lo que pide la tarea")
                elif clave in self.pool_ok and self.u("impugna_ok", agente, cid) < self.p["p_impugna_correcto"]:
                    lineas.append(f"IMPUGNO: {cid} | creo que el resultado esperado es otro")
        if agente == "A3":
            presentes = {c for _, _, c in casos_ev}
            nuevos = [c for c in self.pool_ok if c not in presentes]
            if nuevos and self.u("nuevo_caso") < 0.8:
                lineas.append(f"CASO: {nuevos[int(self.u('cual') * len(nuevos)) % len(nuevos)]}")
        return "\n".join(lineas)

    # --- pasos del motor V2-F ---------------------------------------------------------------------------------
    def _m_planificar(self, agente, usuario):
        cs = self.casos("A2", 3, "plan")
        self.pruebas_a2 = {f"C{i}": c for i, c in enumerate(cs, 1)}
        ids = ",".join(self.pruebas_a2)
        crit = "\n".join(f"CRITERIO: {k} | {c} | PRUEBA: {C.nombre_prueba(k)}" for k, c in self.pruebas_a2.items())
        return (f"SUBTAREA: S1 | implementar {self.funcion} | CRITERIOS: {ids} | DEPENDE: - | PRIORIDAD: alta\n"
                f"ARCHIVOS: solucion.py, test_solucion.py\n{crit}")

    def _modulo_pruebas(self):
        casos = [C.parsear_expresion(c, "A2", k) for k, c in self.pruebas_a2.items()]
        g = C.generar_modulo(casos, {self.funcion: "solucion"})
        return f"ARCHIVO: test_solucion.py\n```python\n{g['texto']}```\nFIN"

    def _m_pruebas(self, agente, usuario):
        return self._modulo_pruebas()

    def _m_generar(self, agente, usuario):
        self.var["A1"] = self.elegir_variante("A1")
        return self._codigo("A1")

    def _m_revisar(self, agente, usuario):
        self.revisiones_a3 += 1
        imp = re.findall(r"^- (A3v\d+-\d+): (.+?) \(al ejecutarlo", usuario, re.MULTILINE)
        if imp:
            mantener = [c for cid, c in imp if not (c in self.pool_mal and self.u("retira", cid) < self.p["p_retira"])]
            if mantener:
                return "".join(f"OBJECION: mantengo el caso | EVIDENCIA: `{c}`\nCASO: {c}\n" for c in mantener)
            return "SIN OBJECIONES: retiro los casos impugnados"
        if self.revisiones_a3 == 1:
            cs = self.casos("A3", 2, "rev")
            return "SIN OBJECIONES: propongo casos para comprobarlo\n" + "".join(f"CASO: {c}\n" for c in cs)
        return "SIN OBJECIONES: revisé la nueva versión"

    def _m_evaluar(self, agente, usuario):
        ids = sorted(set(re.findall(r"test_caso_(c\d+)", usuario)))
        claves = [self.pruebas_a2[i.upper()] for i in ids if i.upper() in self.pruebas_a2]
        return "DIAGNOSTICO: fallan los casos: " + "; ".join(claves) if claves else "DIAGNOSTICO: revisa los casos que fallan"

    def _m_corregir(self, agente, usuario):
        fallidas = []
        for linea in re.findall(r"fallan los casos: (.+)$", usuario, re.MULTILINE)[-1:]:
            fallidas += [x.strip() for x in linea.split(";") if x.strip()]
        a3 = re.findall(r"^- (A3v\d+-\d+) FALLA: (.+?) -> ", usuario, re.MULTILINE)
        fallidas += [c for _, c in a3]
        self._reparar_si("A1", fallidas, f"motor{len(fallidas)}")
        extra = ""
        if self.var.get("A1") == "correcta":
            for cid, c in a3:
                if c in self.pool_mal and self.u("rebate", cid) < self.p["p_impugna_erroneo"]:
                    extra += f"REBATIDA: CASO {cid} | según la tarea el resultado correcto es otro\n"
            for k, c in sorted(self.pruebas_a2.items()):
                if c in fallidas and c in self.pool_mal and self.u("rebate_prueba", k) < self.p["p_impugna_erroneo"]:
                    extra += f"REBATIDA: {C.nombre_prueba(k)} | la prueba espera un resultado que la tarea no pide\n"
        return extra + self._codigo("A1", "CAMBIOS: corrijo lo que fallaba\n")

    def _m_replanificar(self, agente, usuario):
        cambios = []
        for k, c in list(self.pruebas_a2.items()):
            if c in self.pool_mal and self.u("corrige_prueba", k) < self.p["p_corrige_prueba"]:
                libres = [x for x in self.pool_ok if x not in self.pruebas_a2.values()]
                if libres:
                    self.pruebas_a2[k] = libres[int(self.u("sustituta", k) * len(libres)) % len(libres)]
                    cambios.append(k)
        crit = "".join(f"CRITERIO: {k} | {self.pruebas_a2[k]} | PRUEBA: {C.nombre_prueba(k)}\n" for k in cambios)
        return crit + self._modulo_pruebas()

    def _m_auditar(self, agente, usuario):
        return "AUDITORIA: conforme\nOBSERVACION: revisé la evidencia registrada"


# --- ejecución de un modo -------------------------------------------------------------------------------------
def _codigo_de(texto) -> dict:
    ex = archivos.extraer(texto or "", max_archivos=3)
    return {f["nombre"]: f["contenido"] for f in ex["archivos"]
            if f["nombre"].endswith(".py") and not f["nombre"].startswith("test")}


def _metricas(agentes) -> dict:
    llam = list(getattr(agentes, "metricas", []) or [])
    num = lambda k: [x.get(k) for x in llam if isinstance(x.get(k), (int, float))]
    tp, tg = sum(num("tokens_prompt")), sum(num("tokens_gen"))
    return {"llamadas": len(llam), "tokens_prompt": tp, "tokens_gen": tg, "tiempo_modelo_s": round(sum(num("pared_s")), 3),
            "proyeccion_s23_s": round(tg / VELOCIDAD_S23["generacion_tok_s"] + tp / VELOCIDAD_S23["entrada_tok_s"], 1)}


class Banco:
    """Ejecuta modos × tareas sobre un backend ya preparado (simulado: uno por tarea y modo; real: el mismo
    llama-server para todo). Escribe en lab/<partes>/ (registro, artefactos y evaluaciones)."""

    def __init__(self, lab, partes, banco: dict, autorizado: bool, crear_backend, simulado: bool, semilla=None,
                 parametros=None, memoria_por_modo=None, parar=None, supervisar=None):
        self.lab, self.partes, self.banco = lab, tuple(partes), banco
        self.crear_backend, self.simulado, self.semilla = crear_backend, simulado, semilla
        self.parametros = dict(parametros or banco["simulacion"]["parametros"])
        self.parametros.pop("explicacion", None)
        self.memoria_por_modo = memoria_por_modo or (lambda modo: None)
        self.parar = parar or (lambda: None)
        self.supervisar = supervisar or (lambda: None)
        self.lab.crear_dir(*self.partes)
        self.eval = herramientas.Despachador(lab, self.partes + ("evaluacion",), autorizado=autorizado, contexto="banco")
        if not self.eval.permitido:
            raise PermissionError("el banco necesita --autorizo-pruebas: sin ejecutar no se puede medir la calidad")
        self.filas = []

    def _parada(self):
        m = self.parar() or self.supervisar()
        if m:
            raise InterruptedError(str(m))

    def ejecutar(self, modos=MODOS, tareas=None) -> list:
        sel = [t for t in self.banco["tareas"] if not tareas or t["id"] in tareas]
        for t in sel:
            for modo in modos:
                self._parada()
                self.filas.append(self._uno(t, modo))
        return self.filas

    def _uno(self, t, modo) -> dict:
        ident = f"{t['id']}__{modo}" + (f"__s{self.semilla}" if self.semilla is not None else "")
        partes = self.partes + ("runs", ident)
        self.lab.crear_dir(*partes)
        backend = self.crear_backend(t, modo)
        t0 = time.monotonic()
        fila = {"tarea": t["id"], "modo": modo, "semilla": self.semilla, "conclusion": None, "error": None,
                "errores": {}, "afirmaciones_sin_evidencia": 0}
        final = {}
        try:
            final, extra = getattr(self, "_modo_" + modo)(t, partes, backend, fila)
        except InterruptedError:
            raise
        except Exception as e:                                       # un fallo del sistema se registra y cuenta
            fila["error"] = f"{type(e).__name__}: {e}"[:300]
            extra, final = None, {}
        fila["tiempo_pared_s"] = round(time.monotonic() - t0, 3)
        fila.update(_metricas(extra) if extra is not None else {"llamadas": 0, "tokens_prompt": 0, "tokens_gen": 0,
                                                               "tiempo_modelo_s": 0.0, "proyeccion_s23_s": 0.0})
        fila["tokens_medidos"] = not self.simulado
        fila.update(self._evaluar_oculto(t, final, partes))
        fila["afirma_exito"] = fila["conclusion"] in AFIRMA_EXITO.get(modo, ())
        fila["falsa_certeza"] = fila["afirma_exito"] and not fila["correcta"]
        fila["acierto_con_aval"] = fila["afirma_exito"] and fila["correcta"]
        fila["abstencion"] = not final
        self.lab.anexar(self.partes + ("por_ejecucion.jsonl",), json.dumps(fila, ensure_ascii=False, default=str) + "\n")
        return fila

    def _evaluar_oculto(self, t, final, partes) -> dict:
        ora = self.banco["oraculos"][t["id"]]
        if not final:
            return {"calidad": 0.0, "correcta": False, "oraculo_pasa": 0, "oraculo_total": len(ora),
                    "solucion_sha256": None}
        r = self.eval.ejecutar_casos(final, ora, agente="evaluador", etiqueta=f"oculto_{t['id']}")
        ok = sum(1 for v in r["por_caso"].values() if v["estado"] == "pasa")
        self.lab.crear_dir(*partes, "solucion_final")
        for n, x in sorted(final.items()):
            self.lab.crear_exclusivo(partes + ("solucion_final", n), x)
        return {"calidad": round(ok / len(ora), 4), "correcta": ok == len(ora), "oraculo_pasa": ok,
                "oraculo_total": len(ora), "solucion_sha256": _sha(json.dumps(final, sort_keys=True)),
                "evaluacion_carpeta": r.get("carpeta")}

    # --- modos ----------------------------------------------------------------------------------------------
    def _modo_individual(self, t, partes, backend, fila):
        ag = debate.AgentesDebateLLM(backend)
        txt = ag.proponer("A1", t["instrucciones"]) or ""
        self.lab.crear_exclusivo(partes + ("A1_respuesta.txt",), txt)
        cod = _codigo_de(txt)
        if not cod:
            fila["errores"]["formato"] = 1
        fila["conclusion"] = "sin_conclusion"
        return cod, ag

    def _modo_individual_autoprueba(self, t, partes, backend, fila):
        ag = debate.AgentesDebateLLM(backend)
        desp = herramientas.Despachador(self.lab, partes, autorizado=self.eval.permitido, contexto="banco")
        txt = ag.proponer("A1", t["instrucciones"]) or ""
        self.lab.crear_exclusivo(partes + ("A1_respuesta.txt",), txt)
        cod = _codigo_de(txt)
        cs = C.casos_de_texto(txt, "A1", prefijo="A1", maximo=debate.MAX_CASOS_PROPUESTA)
        fila["errores"]["casos_rechazados"] = len(cs["rechazados"])
        casos = C.con_ids(C.ejemplos_del_enunciado(t["instrucciones"]), "E") + cs["casos"]
        if not cod:
            fila["errores"]["formato"] = 1
            fila["conclusion"] = "sin_codigo"
            return cod, ag
        r = desp.ejecutar_casos(cod, casos, agente="A1", etiqueta="autoprueba")
        fallos = [c for c in casos if r["por_caso"][c.id]["estado"] != "pasa"]
        if fallos:
            ev = "\n".join(f"{c.id}: {c.clave()} -> {(r['por_caso'][c.id]['obtenido'] or '?')[:100]}" for c in fallos)
            txt2 = ag.reparar("A1", t["instrucciones"], "\n".join(f"ARCHIVO: {n}\n```\n{x}```"
                                                                  for n, x in sorted(cod.items())), ev) or ""
            self.lab.crear_exclusivo(partes + ("A1_reparacion.txt",), txt2)
            cod2 = _codigo_de(txt2)
            if cod2:
                cod = cod2
                r = desp.ejecutar_casos(cod, casos, agente="A1", etiqueta="autoprueba2")
                fallos = [c for c in casos if r["por_caso"][c.id]["estado"] != "pasa"]
            else:
                fila["errores"]["formato"] = fila["errores"].get("formato", 0) + 1
        fila["conclusion"] = "autoprueba_ok" if not fallos else "autoprueba_fallida"
        return cod, ag

    def _modo_equipo_debate(self, t, partes, backend, fila):
        ag = debate.AgentesDebateLLM(backend)
        desp = herramientas.Despachador(self.lab, partes + ("debate",), autorizado=self.eval.permitido,
                                        contexto="debate")
        res = debate.Debate(self.lab, partes + ("debate",), ag, desp, memoria=self.memoria_por_modo("equipo_debate")) \
            .ejecutar(t["instrucciones"])
        fila["conclusion"] = res["decision"]
        fila["mayoria_contra_evidencia"] = res["adjudicacion"].get("mayoria_contra_evidencia")
        fila["diversidad_baja"] = res["independencia"]["diversidad_baja"]
        fila["errores"]["casos_rechazados"] = len(res["casos_rechazados"])
        fila["errores"]["propuestas_invalidas"] = sum(1 for c in res["candidatas"].values() if not c["valida"])
        el = res["elegida"]
        cod = {}
        if el:
            for n in res["candidatas"][el]["archivos"]:
                cod[n] = self.lab.leer_texto(partes + ("debate", "solucion_final", n), 200_000) or ""
        return cod, ag

    def _modo_equipo_motor(self, t, partes, backend, fila):
        ag = motor_v2f.AgentesMotorLLMV2F(backend)
        base = self.lab.ruta(*partes, "motor")
        lab_m = rutas.Laboratorio(self.lab.raiz, base)
        lab_m.crear_base()
        ej = ejecutor_restringido.EjecutorRestringido(lab_m, (), autorizado=self.eval.permitido)
        m = motor_v2f.MotorV2F(base, ag, ej, raiz_laboratorio=self.lab.raiz, pruebas_por_a2=True,
                               memoria=self.memoria_por_modo("equipo_motor"), politica_falta="asumir_y_marcar",
                               presupuesto=motor.Presupuesto(max_iteraciones_correccion=2))
        inf = m.ejecutar(t["instrucciones"])
        fila["conclusion"] = inf["estado_final"]
        v = inf.get("v2f") or {}
        fila["afirmaciones_sin_evidencia"] = len(v.get("afirmaciones_sin_evidencia") or [])
        fila["errores"]["casos_rechazados"] = len(v.get("casos_rechazados") or [])
        fila["llamadas_evitadas"] = v.get("llamadas_evitadas", 0)
        cod = {}
        if m.proy and m.proy.contenidos:
            cod = {r: x for r, x in m.proy.contenidos[-1].items() if not r.rsplit("/", 1)[-1].startswith("test")}
        return cod, ag


# --- resumen y comparación ---------------------------------------------------------------------------------------
def resumir(filas: list) -> dict:
    por_modo = {}
    for f in filas:
        d = por_modo.setdefault(f["modo"], {"ejecuciones": 0, "correctas": 0, "calidad_suma": 0.0, "falsas_certezas": 0,
                                            "aciertos_con_aval": 0, "abstenciones": 0, "errores_sistema": 0,
                                            "llamadas": 0, "tokens_prompt": 0, "tokens_gen": 0, "tiempo_pared_s": 0.0,
                                            "tiempo_modelo_s": 0.0, "proyeccion_s23_s": 0.0, "afirmaciones_sin_evidencia": 0,
                                            "casos_rechazados": 0, "formato": 0, "mayoria_contra_evidencia": 0})
        d["ejecuciones"] += 1
        d["correctas"] += int(f["correcta"])
        d["calidad_suma"] += f["calidad"]
        d["falsas_certezas"] += int(f["falsa_certeza"])
        d["aciertos_con_aval"] += int(f["acierto_con_aval"])
        d["abstenciones"] += int(f["abstencion"])
        d["errores_sistema"] += int(bool(f["error"]))
        for k in ("llamadas", "tokens_prompt", "tokens_gen", "tiempo_pared_s", "tiempo_modelo_s", "proyeccion_s23_s",
                  "afirmaciones_sin_evidencia"):
            d[k] = round(d[k] + (f.get(k) or 0), 3)
        d["casos_rechazados"] += (f.get("errores") or {}).get("casos_rechazados", 0)
        d["formato"] += (f.get("errores") or {}).get("formato", 0)
        d["mayoria_contra_evidencia"] += int(bool(f.get("mayoria_contra_evidencia")))
    for d in por_modo.values():
        n = d["ejecuciones"] or 1
        d["calidad_media"] = round(d.pop("calidad_suma") / n, 4)
        d["tasa_correctas"] = round(d["correctas"] / n, 4)
        d["llamadas_media"] = round(d["llamadas"] / n, 2)
    return por_modo


def comparar_modos(por_modo: dict, referencia="individual") -> dict:
    """Diferencias de cada modo frente a la referencia (calidad, aciertos, coste). Ninguna cifra se oculta."""
    if referencia not in por_modo:
        return {}
    r = por_modo[referencia]
    out = {}
    for m, d in por_modo.items():
        if m == referencia:
            continue
        cociente = lambda k: round(d[k] / r[k], 2) if r[k] else None
        out[m] = {"delta_tasa_correctas": round(d["tasa_correctas"] - r["tasa_correctas"], 4),
                  "delta_calidad_media": round(d["calidad_media"] - r["calidad_media"], 4),
                  "delta_falsas_certezas": d["falsas_certezas"] - r["falsas_certezas"],
                  "x_llamadas": cociente("llamadas"), "x_tokens": cociente("tokens_prompt"),
                  "x_proyeccion_s23": cociente("proyeccion_s23_s")}
    return out


def informe(banco: dict, filas: list, contexto_ej: dict) -> dict:
    por_modo = resumir(filas)
    semillas = sorted({f["semilla"] for f in filas if f["semilla"] is not None})
    decisiones = json.dumps([[f["tarea"], f["modo"], f["semilla"], f["conclusion"], f["solucion_sha256"], f["correcta"]]
                             for f in filas], sort_keys=True)
    return {"version": VERSION, "banco": banco["nombre"], "banco_sha256": banco["sha256"],
            "simulacion_sha256": banco["sha256_simulacion"] if contexto_ej.get("simulado") else None,
            "contexto": contexto_ej, "semillas": semillas, "por_modo": por_modo,
            "frente_a_individual": comparar_modos(por_modo, "individual"),
            "frente_a_individual_autoprueba": comparar_modos(por_modo, "individual_autoprueba"),
            "huella_decisiones": _sha(decisiones), "filas": filas,
            "velocidad_s23_supuesta": VELOCIDAD_S23,
            "notas": ([
                "MODO SIMULADO: las respuestas de los agentes salen de una POLÍTICA PARAMETRIZADA (simulacion.json), no "
                "de Qwen. La ejecución de pruebas y la evaluación oculta son REALES. Las diferencias entre modos dependen "
                "de los parámetros: esto valida el banco y el protocolo, NO demuestra que el equipo supere al individuo.",
                "Tokens ESTIMADOS (len/3) sobre los prompts reales; la proyección al S23 usa velocidades medidas en "
                "prueba3, no medidas de esta ejecución."] if contexto_ej.get("simulado") else [
                "MODO REAL: Qwen local; tokens medidos por llama-server; el tiempo incluye la inferencia."]) + [
                "Calidad = fracción de casos del ORÁCULO OCULTO que cumple la solución final; ningún oráculo entra en "
                "un prompt.", "Falsa certeza = el modo afirma éxito y el oráculo oculto lo contradice.",
                "Abstención = el modo no entrega solución (p. ej. el debate sin candidata válida): no es un acierto ni "
                "una falsa certeza."]}


def texto_md(inf: dict) -> str:
    l = [f"# Banco de capacidades — {inf['banco']} ({inf['version']})", "",
         f"Modo: **{'SIMULADO' if inf['contexto'].get('simulado') else 'QWEN REAL'}** · banco SHA-256 "
         f"`{inf['banco_sha256'][:16]}` · semillas {inf['semillas'] or '—'} · huella de decisiones "
         f"`{inf['huella_decisiones'][:16]}`", ""]
    l += [f"> {n}" for n in inf["notas"]] + [""]
    l += ["| Modo | Ejec. | Correctas | Calidad media | Falsas certezas | Aciertos con aval | Abstenciones | "
          "Llamadas (media) | Tokens entrada | Tokens salida | Proyección S23 (s) | Errores sistema |",
          "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for m in MODOS:
        d = inf["por_modo"].get(m)
        if d:
            l.append(f"| {m} | {d['ejecuciones']} | {d['correctas']} ({d['tasa_correctas']:.0%}) | {d['calidad_media']:.3f} | "
                     f"{d['falsas_certezas']} | {d['aciertos_con_aval']} | {d['abstenciones']} | {d['llamadas_media']} | "
                     f"{d['tokens_prompt']} | {d['tokens_gen']} | {d['proyeccion_s23_s']} | {d['errores_sistema']} |")
    for ref in ("individual", "individual_autoprueba"):
        c = inf[f"frente_a_{ref}"]
        if c:
            l += ["", f"## Frente a «{ref}»", "", "| Modo | Δ tasa correctas | Δ calidad | Δ falsas certezas | × llamadas | "
                  "× tokens | × tiempo S23 |", "|---|---:|---:|---:|---:|---:|---:|"]
            for m, x in c.items():
                l.append(f"| {m} | {x['delta_tasa_correctas']:+.3f} | {x['delta_calidad_media']:+.3f} | "
                         f"{x['delta_falsas_certezas']:+d} | {x['x_llamadas']} | {x['x_tokens']} | {x['x_proyeccion_s23']} |")
    l += ["", "## Por tarea", "", "| Tarea | Modo | Semilla | Conclusión | Calidad | Correcta | Llamadas | Error |",
          "|---|---|---:|---|---:|---|---:|---|"]
    for f in inf["filas"]:
        l.append(f"| {f['tarea']} | {f['modo']} | {f['semilla'] if f['semilla'] is not None else '—'} | {f['conclusion']} | "
                 f"{f['calidad']:.2f} | {'sí' if f['correcta'] else 'no'} | {f['llamadas']} | {f['error'] or ''} |")
    return "\n".join(l) + "\n"


def comparar_informes(a: dict, b: dict) -> dict:
    avisos = []
    if a.get("banco_sha256") != b.get("banco_sha256"):
        avisos.append("los bancos NO son el mismo (SHA-256 distinto): la comparación no es equivalente")
    if bool(a["contexto"].get("simulado")) != bool(b["contexto"].get("simulado")):
        avisos.append("uno es SIMULADO y el otro REAL: no son comparables como medida del modelo")
    if a["contexto"].get("ctx") != b["contexto"].get("ctx"):
        avisos.append("contexto distinto")
    out = {}
    for m in MODOS:
        x, y = a["por_modo"].get(m), b["por_modo"].get(m)
        if x and y:
            out[m] = {k: (x[k], y[k]) for k in ("tasa_correctas", "calidad_media", "falsas_certezas", "llamadas_media",
                                                "tokens_prompt", "proyeccion_s23_s")}
    return {"modos": out, "avisos": avisos}
