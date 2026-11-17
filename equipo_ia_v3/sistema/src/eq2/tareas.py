"""V2-E.7: TAREAS «LAB-NNN» del equipo (importar, ejecutar, estado, exportar).

Reutiliza el motor de V2-E (motor.Motor): A2 planifica y ESCRIBE LAS PRUEBAS, A1 escribe el código y lo
corrige, A3 revisa; el EJECUTOR RESTRINGIDO ejecuta las pruebas de verdad (solo con --autorizo-pruebas) y,
al final, A3 AUDITA la evidencia en modo lectura: recibe un resumen, no puede escribir nada, y su texto se
guarda aparte. La conclusión «verificado» la decide el CÓDIGO (pruebas reales con nonce válido), nunca un
agente.

Todo vive en $TMPDIR/equipo_f2/lab_v2e7/tareas/<ID>/ y nada se sobrescribe ni se borra:
  tarea_original.json   bytes recibidos, tal cual          tarea.json   normalizada + SHA-256 del original
  eventos.jsonl         historial (solo añadir)             ejecuciones/E<nnn>/   una carpeta por ejecución:
      runs/<run>/motor/{eventos.jsonl, informe.json}, runs/<run>/proyecto/v<n>/ (archivos y su manifiesto)
      pruebas/P<nnn>/{espacio/, comando en registro.json, salida.txt, errores.txt, informe_unittest.txt}
      auditoria/{determinista.json, A3_auditoria.txt}       MANIFIESTO_SHA256.txt (de la ejecución)
Exportar crea exportaciones/EQUIPO_IA_<ID>_ENTREGA[_vN].zip con todo lo anterior, un LEEME y un manifiesto
SHA-256 comprobable con `sha256sum -c`.
"""
from __future__ import annotations

import hashlib
import json
import re
import zipfile
from pathlib import Path

from . import VERSION, archivos, config, ejecutor_restringido, memoria, motor, plataforma, rutas

# V2-F: tareas de código con el motor V2-F (por defecto) o el de V2-E.7 («motor»: «v2e», para comparar), debate por
# evidencias («tipo»: «debate_codigo»), casos-oráculo del usuario («casos»), propiedades declaradas
# («propiedades») y política ante información que falta («politica_falta»).
MOTORES = ("v2f", "v2e")

ID_RX = re.compile(r"^LAB-[0-9]{3,6}$")
CLAVES = {"id", "titulo", "instrucciones", "max_iteraciones", "notas",
          "tipo", "resultado_esperado",                              # V2-E.7-r2: tareas «modlab_pz»
          "motor", "casos", "propiedades", "politica_falta",          # V2-F
          "funcion"}                                                  # V2-F.1: nombre de la función (funcion_supervisada)
TIPOS = ("codigo", "modlab_pz", "debate_codigo",                     # V2-F: debate_codigo
         "funcion_supervisada")                                      # V2-F.1
ESPERADOS = ("todos_ok", "fallo_detectado")
MAX_SOLICITUDES_PZ = 3
SOLICITUD_RX = re.compile(r"^\s*SOLICITO:\s*([a-z_]+)\s+([A-Za-z0-9_.\-]+)\s*$", re.M)
MAX_JSON = 64_000


class ErrorTarea(ValueError):
    pass


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


class Tareas:
    def __init__(self, raiz=None, ahora=memoria.ahora_iso):
        self.raiz = Path(raiz) if raiz is not None else rutas.raiz_laboratorio()
        self.base = self.raiz / config.CARPETA_ACTUAL
        self.lab = rutas.Laboratorio(self.raiz, self.base)
        self.lab.crear_base()
        self.lab.crear_dir("tareas")
        self.ahora = ahora

    # --- utilidades -----------------------------------------------------------------------------------
    def _ids(self):
        return sorted(p.name for p in self.lab.ruta("tareas").iterdir() if ID_RX.match(p.name))

    def _comprobar_id(self, tid):
        if not isinstance(tid, str) or not ID_RX.match(tid):
            raise ErrorTarea(f"identificador inválido: {tid!r} (formato LAB-001)")
        if not self.lab.existe("tareas", tid):
            raise ErrorTarea(f"no existe la tarea {tid}")
        return tid

    def evento(self, tid, tipo, **datos):
        linea = json.dumps({"ts": self.ahora(), "tipo": tipo, **datos}, ensure_ascii=False, default=str)
        self.lab.anexar(("tareas", tid, "eventos.jsonl"), linea + "\n")

    def eventos(self, tid):
        txt = self.lab.leer_texto(("tareas", tid, "eventos.jsonl"), 5_000_000) or ""
        return [json.loads(l) for l in txt.splitlines() if l.strip()]

    def resolver(self, tid):
        if tid == "ultima":
            ids = self._ids()
            if not ids:
                raise ErrorTarea("no hay tareas")
            return max(ids, key=lambda t: (self.eventos(t)[-1]["ts"] if self.eventos(t) else "", t))
        return self._comprobar_id(tid)

    # --- importar -----------------------------------------------------------------------------------
    def importar(self, ruta) -> dict:
        p = Path(ruta)
        datos = p.read_bytes()[:MAX_JSON + 1]
        if len(datos) > MAX_JSON:
            raise ErrorTarea(f"el JSON supera {MAX_JSON} bytes")
        try:
            texto = datos.decode("utf-8")
            d = json.loads(texto)
        except (UnicodeDecodeError, ValueError) as e:
            raise ErrorTarea(f"JSON inválido: {e}")
        if not isinstance(d, dict):
            raise ErrorTarea("la tarea debe ser un objeto JSON")
        extra = set(d) - CLAVES
        if extra:
            raise ErrorTarea(f"claves desconocidas: {sorted(extra)} (permitidas: {sorted(CLAVES)})")
        instr = d.get("instrucciones")
        if not isinstance(instr, str) or not instr.strip():
            raise ErrorTarea("falta «instrucciones» (texto)")
        if len(instr) > config.MAX_TAREA_CHARS:
            raise ErrorTarea(f"«instrucciones» supera {config.MAX_TAREA_CHARS} caracteres (límite del contexto)")
        mi = d.get("max_iteraciones", 2)
        if not isinstance(mi, int) or not 0 <= mi <= config.EJECUTOR_MAX_ITERACIONES:
            raise ErrorTarea(f"max_iteraciones debe ser un entero entre 0 y {config.EJECUTOR_MAX_ITERACIONES}")
        tipo, esperado = d.get("tipo", "codigo"), d.get("resultado_esperado", "todos_ok")
        if tipo not in TIPOS or esperado not in ESPERADOS:
            raise ErrorTarea(f"tipo debe ser uno de {TIPOS} y resultado_esperado uno de {ESPERADOS}")
        mot = d.get("motor", "v2f")
        if mot not in MOTORES:
            raise ErrorTarea(f"motor debe ser uno de {MOTORES}")
        pol = d.get("politica_falta", "preguntar")
        from . import casos as C, planificacion
        if pol not in planificacion.POLITICAS_FALTA:
            raise ErrorTarea(f"politica_falta debe ser una de {planificacion.POLITICAS_FALTA}")
        props = d.get("propiedades", [])
        if not isinstance(props, list) or any(x not in C.PROPIEDADES for x in props) or len(set(props)) != len(props):
            raise ErrorTarea(f"propiedades debe ser una lista sin repetir de {C.PROPIEDADES}")
        try:
            casos_u = C.casos_del_usuario(d.get("casos"))
        except C.CasoInvalido as e:
            raise ErrorTarea(f"casos: {e}")
        if (casos_u or props) and tipo == "modlab_pz":
            raise ErrorTarea("casos y propiedades no se usan en tareas modlab_pz")
        fun = d.get("funcion")                                              # V2-F.1
        if fun is not None and (tipo != "funcion_supervisada" or not C.nombre_funcion_valido(fun)):
            raise ErrorTarea("«funcion» solo se usa en tareas funcion_supervisada y debe ser un nombre de función válido")
        tid = d.get("id")
        if tid is None:
            nums = [int(t[4:]) for t in self._ids()]
            tid = f"LAB-{(max(nums) + 1) if nums else 1:03d}"
        if not isinstance(tid, str) or not ID_RX.match(tid):
            raise ErrorTarea(f"identificador inválido: {tid!r} (formato LAB-001)")
        try:
            self.lab.crear_dir_exclusivo("tareas", tid)
        except FileExistsError:
            raise ErrorTarea(f"la tarea {tid} ya existe: no se sobrescribe (usa otro id)")
        self.lab.crear_exclusivo(("tareas", tid, "tarea_original.json"), texto)
        norm = {"id": tid, "titulo": str(d.get("titulo") or "")[:200], "instrucciones": instr,
                "max_iteraciones": mi, "notas": str(d.get("notas") or "")[:2000],
                "tipo": tipo, "resultado_esperado": esperado,
                "motor": mot, "politica_falta": pol, "propiedades": props,
                "casos": [c.texto for c in casos_u],
                "original_sha256": sha256(datos), "origen": p.name, "importada": self.ahora(), "version": VERSION}
        if tipo == "funcion_supervisada":                                   # V2-F.1 (las demás tareas no cambian)
            norm["funcion"] = fun
        self.lab.crear_exclusivo(("tareas", tid, "tarea.json"), json.dumps(norm, ensure_ascii=False, indent=1))
        self.lab.crear_dir("tareas", tid, "ejecuciones")
        self.evento(tid, "importada", original_sha256=norm["original_sha256"], origen=p.name)
        return norm

    def tarea(self, tid):
        return json.loads(self.lab.leer_texto(("tareas", tid, "tarea.json"), MAX_JSON * 2))

    # --- ejecutar -----------------------------------------------------------------------------------
    def ejecutar(self, tid, agentes: motor.AgentesMotor, backend=None, autorizo_pruebas=False,
                 instalar_senales=True, componentes_codex=None) -> dict:
        """componentes_codex (V2-F.1, solo funcion_supervisada): {"recuperador"|"selector"|"diagnostico": objeto} que
        cumple interfaces_codex; sus salidas se validan y nunca afectan a permisos ni a la autorización."""
        tid = self._comprobar_id(tid)
        t = self.tarea(tid)
        n = 1
        while self.lab.existe("tareas", tid, "ejecuciones", f"E{n:03d}"):
            n += 1
        eid = f"E{n:03d}"
        partes = ("tareas", tid, "ejecuciones", eid)
        self.lab.crear_dir_exclusivo(*partes)
        base = self.lab.ruta(*partes)
        lab_ej = rutas.Laboratorio(self.raiz, base)
        self.evento(tid, "ejecucion_iniciada", ejecucion=eid, autorizo_pruebas=autorizo_pruebas is True,
                    backend=getattr(backend, "etiqueta", None) or type(agentes).__name__)
        if t.get("tipo") == "modlab_pz":                          # V2-E.7-r2
            return self._ejecutar_pz(tid, eid, base, lab_ej, t, agentes, backend, autorizo_pruebas is True)
        if t.get("tipo") == "debate_codigo":                      # V2-F
            return self._ejecutar_debate(tid, eid, base, lab_ej, t, agentes, backend, autorizo_pruebas is True)
        if t.get("tipo") == "funcion_supervisada":                # V2-F.1: ejecución dinámica BLOQUEADA
            return self._ejecutar_funcion(tid, eid, base, lab_ej, t, agentes, backend, autorizo_pruebas is True,
                                          componentes_codex)
        ej = ejecutor_restringido.EjecutorRestringido(lab_ej, (), autorizado=autorizo_pruebas is True,
                                                       ahora=self.ahora)
        comunes = dict(presupuesto=motor.Presupuesto(max_iteraciones_correccion=t["max_iteraciones"]),
                       backend=backend, raiz_laboratorio=self.raiz, instalar_senales=instalar_senales,
                       proveedor=plataforma.proveedor(), pruebas_por_a2=True,
                       al_finalizar=lambda mo, inf, llm: self._auditar(lab_ej, inf, ej, agentes, t["instrucciones"], llm))
        mem = None
        if t.get("motor", "v2e") == "v2f":                       # V2-F (las tareas de V2-E.7 conservan su motor)
            from . import experiencias, motor_v2f
            try:
                mem = experiencias.MemoriaEquipo(self.lab)
            except Exception as e:                               # la memoria es auxiliar: se informa y se sigue
                self.evento(tid, "memoria_no_disponible", ejecucion=eid, motivo=f"{type(e).__name__}: {e}"[:200])
            m = motor_v2f.MotorV2F(base, agentes, ej, memoria=mem, politica_falta=t.get("politica_falta", "preguntar"),
                                   tarea_ref=f"{tid}/{eid}", **comunes)
        else:
            m = motor.Motor(base, agentes, ej, **comunes)
        try:
            inf = m.ejecutar(t["instrucciones"])
        except FileExistsError:
            self.evento(tid, "ejecucion_rechazada", ejecucion=eid, motivo="candado existente")
            raise ErrorTarea("candado existente: otra ejecución en curso o candado obsoleto")
        except BaseException as e:
            self.evento(tid, "ejecucion_interrumpida", ejecucion=eid, motivo=f"{type(e).__name__}: {e}"[:300])
            raise
        finally:
            if mem is not None:
                mem.cerrar()
        aud = m.auditoria or {"conclusion": "no_verificado",
                              "A3": {"veredicto": "no_realizada", "error": "la auditoría no se completó"}}
        man = self._manifiesto(lab_ej, base)
        res = {"tarea": tid, "ejecucion": eid, "estado_final": inf["estado_final"], "motivo": inf.get("motivo"),
               "resultado": aud["conclusion"], "pruebas_reales_ejecutadas": inf["pruebas_reales_ejecutadas"],
               "ejecuciones_de_pruebas": len(ej.ejecuciones), "auditoria_A3": aud["A3"]["veredicto"],
               "run_id": inf["run_id"], "manifiesto_sha256": man}
        if "v2f" in inf:                                                         # V2-F
            v = inf["v2f"]
            res.update(motor="v2f", reservas=v.get("reservas"), preguntas=v.get("preguntas"),
                       llamadas_evitadas=v.get("llamadas_evitadas"),
                       experiencias_guardadas=(v.get("memoria") or {}).get("guardadas"))
        self.evento(tid, "ejecucion_terminada", **res)
        return res

    # --- V2-E.7-r2: tareas PZ ModLab (A1 escenario, A2 solicita, herramientas de lista blanca, A3 audita) ----
    def _ejecutar_pz(self, tid, eid, base, lab_ej, t, agentes, backend, autorizado):
        from . import modlab_pz_adaptador as pz
        instr = t["instrucciones"]
        lab_ej.crear_dir_exclusivo("lock")
        reg = lambda tipo, **d: lab_ej.anexar(("eventos.jsonl",), json.dumps(
            {"ts": self.ahora(), "tipo": tipo, **d}, ensure_ascii=False, default=str) + "\n")
        parada = lambda: "stop_usuario" if lab_ej.existe("STOP") or self.lab.existe("tareas", tid, "STOP") else None
        herramientas, escenario, estado, a3 = [], {}, "completada", {"veredicto": "no_realizada", "error": None}
        try:
            if backend is not None:
                lab_ej.crear_dir("runs", eid)                    # el backend guarda runs/<id>/server.log
                backend.iniciar({"lab": lab_ej, "run_id": eid, "parar": parada})
            reg("inicio", version=VERSION, clase="modlab_pz", autorizado=autorizado)
            for paso in ("A1", "A2"):
                if parada():
                    raise InterruptedError(parada())
                if paso == "A1":
                    txt = agentes.paso_libre("pz_escenario", instr) or ""
                    lab_ej.crear_dir("agentes")
                    lab_ej.crear_exclusivo(("agentes", "A1_escenario.txt"), txt)
                    ex = archivos.extraer(txt)
                    lab_ej.crear_dir("escenario")
                    for f in ex["archivos"]:
                        if f["nombre"].endswith((".json", ".lua")) and "/" not in f["nombre"]:
                            lab_ej.crear_exclusivo(("escenario", f["nombre"]), f["contenido"])
                            escenario[f["nombre"]] = sha256(f["contenido"].encode("utf-8"))
                    reg("A1_escenario", archivos=escenario, problemas=ex["problemas"])
                else:
                    txt = agentes.paso_libre("pz_solicitar", instr, archivos="\n".join(sorted(escenario)) or "(ninguno)") or ""
                    lab_ej.crear_exclusivo(("agentes", "A2_solicitudes.txt"), txt)
                    for i, (op, nombre) in enumerate(SOLICITUD_RX.findall(txt)[:MAX_SOLICITUDES_PZ], 1):
                        h = {"n": i, "solicitada_por": "A2", "operacion": op, "archivo": nombre, "inicio": self.ahora()}
                        partes = ("herramientas", f"H{i:03d}")
                        lab_ej.crear_dir("herramientas")
                        lab_ej.crear_dir_exclusivo(*partes)
                        if not autorizado:
                            h["estado"] = "no_autorizada"
                        elif op not in pz.EXTENSION:
                            h["estado"] = "rechazada_por_contrato"
                        elif nombre not in escenario:
                            h["estado"] = "rechazada_archivo_desconocido"
                        else:
                            try:
                                res = pz.ejecutar(op, lab_ej.ruta("escenario", nombre))
                                txt_res = json.dumps(res, ensure_ascii=False, indent=1)
                                lab_ej.crear_exclusivo(partes + ("resultado.json",), txt_res)
                                h.update(estado="ejecutada", resultado_sha256=sha256(txt_res.encode("utf-8")),
                                         entrada_sha256=escenario[nombre], todos_ok=res.get("todos_ok"))
                            except Exception as e:           # error de la herramienta: se guarda, no se oculta
                                h.update(estado="error", error=f"{type(e).__name__}: {e}"[:500])
                        h["fin"] = self.ahora()
                        lab_ej.crear_exclusivo(partes + ("registro.json",), json.dumps(h, ensure_ascii=False, indent=1))
                        herramientas.append(h)
                        reg("herramienta", **{k: h.get(k) for k in ("n", "operacion", "archivo", "estado", "todos_ok")})
            sims = [h for h in herramientas if h["operacion"] == "simular_escenario" and h["estado"] == "ejecutada"]
            obtenido = None if not sims else ("todos_ok" if all(h["todos_ok"] for h in sims) else "fallo_detectado")
            conclusion = "sin_pruebas" if obtenido is None else (
                "esperado_confirmado" if obtenido == t["resultado_esperado"] else "no_confirmado")
            det = {"conclusion": conclusion, "esperado": t["resultado_esperado"], "obtenido": obtenido,
                   "regla": "solo cuentan simulaciones EJECUTADAS por la herramienta; un error de la herramienta no es "
                            "un fallo detectado; no certifica compatibilidad con Project Zomboid",
                   "herramientas": herramientas, "escenario": escenario}
            lab_ej.crear_dir("auditoria")
            lab_ej.crear_exclusivo(("auditoria", "determinista.json"), json.dumps(det, ensure_ascii=False, indent=1))
            # V2-E.7-r3: A3 recibe la evidencia VERIFICADA en disco (pasos, inventario, rechazos), no un resumen mínimo
            from . import evidencia_pz
            ev = evidencia_pz.construir(lab_ej, t, herramientas, det)
            evid = ev["texto"]
            lab_ej.crear_exclusivo(("auditoria", "evidencia_verificada.json"),
                                   json.dumps(ev["datos"], ensure_ascii=False, indent=1, default=str))
            try:
                if parada():
                    raise RuntimeError("parada solicitada: A3 no se consulta")
                texto = agentes.paso_libre("pz_auditar", instr, evidencia=evid) or ""
                m = re.search(r"AUDITORIA:\s*(conforme|no_conforme|evidencia_insuficiente)", texto, re.I)
                a3 = {"veredicto": m.group(1).lower() if m else "sin_veredicto", "error": None,
                      "cita_pasos": bool(re.search(r"\bpaso\s*\d+", texto, re.I))}
            except Exception as e:
                texto, a3 = "", {"veredicto": "no_realizada", "error": f"{type(e).__name__}: {e}"[:300]}
            lab_ej.crear_exclusivo(("auditoria", "A3_auditoria.txt"),
                                   f"# Auditoría de A3 (no cambia la conclusión)\n# veredicto: {a3['veredicto']}  "
                                   f"error: {a3['error']}  cita_pasos: {a3.get('cita_pasos')}\n\n" + texto)
            lab_ej.crear_exclusivo(("auditoria", "A3_evidencia_recibida.txt"), evid)
        except InterruptedError as e:
            estado, conclusion = "detenida", "sin_pruebas"
            reg("detenida", motivo=str(e))
        except Exception as e:
            estado, conclusion = "error", "sin_pruebas"
            reg("error", detalle=f"{type(e).__name__}: {e}"[:500])
        finally:
            if backend is not None:
                try:
                    reg("backend_detenido", informe=backend.detener())
                except Exception as e:
                    reg("backend_detener_fallo", detalle=type(e).__name__)
            lab_ej.quitar_candado()
        man = self._manifiesto(lab_ej, base)
        res = {"tarea": tid, "ejecucion": eid, "clase": "modlab_pz", "estado_final": estado, "resultado": conclusion,
               "herramientas_ejecutadas": sum(h["estado"] == "ejecutada" for h in herramientas),
               "auditoria_A3": a3["veredicto"], "manifiesto_sha256": man,
               "advertencia": "simulación declarativa propia; no certifica compatibilidad con Project Zomboid"}
        self.evento(tid, "ejecucion_terminada", **res)
        return res

    # --- V2-F: debate por evidencias (A1, A2 y A3 proponen; la ejecución cruzada y el código deciden) ------------
    def _ejecutar_debate(self, tid, eid, base, lab_ej, t, agentes, backend, autorizado):
        from . import casos as C, debate, experiencias, herramientas
        lab_ej.crear_dir_exclusivo("lock")
        parada = lambda: "stop_usuario" if lab_ej.existe("STOP") or self.lab.existe("tareas", tid, "STOP") else None
        estado, res_d, mem = "completada", None, None
        try:
            try:
                mem = experiencias.MemoriaEquipo(self.lab)
            except Exception as e:
                self.evento(tid, "memoria_no_disponible", ejecucion=eid, motivo=f"{type(e).__name__}: {e}"[:200])
            if backend is not None:
                lab_ej.crear_dir("runs", eid)
                backend.iniciar({"lab": lab_ej, "run_id": eid, "parar": parada})
            desp = herramientas.Despachador(lab_ej, ("debate",), autorizado=autorizado, ahora=self.ahora,
                                            contexto="debate")
            d = debate.Debate(lab_ej, ("debate",), agentes, desp, memoria=mem, parar=parada,
                              supervisar=(backend.supervisar if backend is not None else None), ahora=self.ahora,
                              tarea_ref=f"{tid}/{eid}")
            res_d = d.ejecutar(t["instrucciones"], C.casos_del_usuario(t.get("casos") or None),
                               tuple(t.get("propiedades") or ()))
        except InterruptedError as e:
            estado = "detenida"
            lab_ej.anexar(("eventos.jsonl",), json.dumps({"ts": self.ahora(), "tipo": "detenida", "motivo": str(e)},
                                                         ensure_ascii=False) + "\n")
        except Exception as e:
            estado = "error"
            lab_ej.anexar(("eventos.jsonl",), json.dumps({"ts": self.ahora(), "tipo": "error",
                                                          "detalle": f"{type(e).__name__}: {e}"[:500]},
                                                         ensure_ascii=False) + "\n")
        finally:
            if backend is not None:
                try:
                    lab_ej.anexar(("eventos.jsonl",), json.dumps({"ts": self.ahora(), "tipo": "backend_detenido",
                                                                  "informe": backend.detener()}, ensure_ascii=False,
                                                                 default=str) + "\n")
                except Exception as e:
                    lab_ej.anexar(("eventos.jsonl",), json.dumps({"ts": self.ahora(), "tipo": "backend_detener_fallo",
                                                                  "detalle": type(e).__name__}) + "\n")
            if mem is not None:
                mem.cerrar()
            lab_ej.quitar_candado()
        man = self._manifiesto(lab_ej, base)
        res = {"tarea": tid, "ejecucion": eid, "clase": "debate_codigo", "estado_final": estado,
               "resultado": (res_d or {}).get("decision", "sin_pruebas" if estado != "error" else "error"),
               "elegida": (res_d or {}).get("elegida"), "motivo": (res_d or {}).get("motivo"),
               "mayoria_contra_evidencia": ((res_d or {}).get("adjudicacion") or {}).get("mayoria_contra_evidencia"),
               "llamadas": (res_d or {}).get("llamadas"), "manifiesto_sha256": man,
               "nota": "«cumple_oraculo» exige casos del usuario o del enunciado (oráculo) cumplidos al EJECUTAR y "
                       "ninguna disputa abierta; no es una demostración matemática"}
        self.evento(tid, "ejecucion_terminada", **res)
        return res

    # --- V2-F.1: función supervisada (A1 escribe, A2 revisa, A3 propone casos y evalúa; sin ejecutar nada) -----------
    def _ejecutar_funcion(self, tid, eid, base, lab_ej, t, agentes, backend, autorizado, componentes_codex=None):
        from . import experiencias, funcion_supervisada as FS, interfaces_codex
        lab_ej.crear_dir_exclusivo("lock")
        parada = lambda: "stop_usuario" if lab_ej.existe("STOP") or self.lab.existe("tareas", tid, "STOP") else None
        mem, inf = None, None
        try:
            try:
                mem = experiencias.MemoriaEquipo(self.lab)
            except Exception as e:                               # la memoria es auxiliar: se informa y se sigue
                self.evento(tid, "memoria_no_disponible", ejecucion=eid, motivo=f"{type(e).__name__}: {e}"[:200])
            if backend is not None:
                lab_ej.crear_dir("runs", eid)                    # el backend guarda runs/<id>/server.log
            try:
                extra = dict(componentes_codex or {})
                if set(extra) - {"recuperador", "selector", "diagnostico"}:
                    raise ValueError(f"componentes desconocidos: {sorted(set(extra) - {'recuperador', 'selector', 'diagnostico'})}")
                comp = interfaces_codex.Componentes(**extra, memoria=mem, tarea_ref=f"{tid}/{eid}")
                fs = FS.FuncionSupervisada(lab_ej, ("funcion",), agentes, t, eid, memoria=mem, parar=parada,
                                           componentes=comp,
                                           supervisar=(backend.supervisar if backend is not None else None),
                                           ahora=self.ahora, tarea_ref=f"{tid}/{eid}", autorizo_pruebas=autorizado,
                                           backend=backend)
            except Exception as e:                               # no se pudo ni preparar: queda registrado
                self.evento(tid, "ejecucion_interrumpida", ejecucion=eid, motivo=f"{type(e).__name__}: {e}"[:300])
                raise
            inf = fs.ejecutar(iniciar=(lambda: backend.iniciar({"lab": lab_ej, "run_id": eid, "parar": parada}))
                              if backend is not None else None)
        finally:
            if backend is not None:
                try:
                    lab_ej.anexar(("eventos.jsonl",), json.dumps({"ts": self.ahora(), "tipo": "backend_detenido",
                                                                  "informe": backend.detener()}, ensure_ascii=False,
                                                                 default=str) + "\n")
                except Exception as e:
                    lab_ej.anexar(("eventos.jsonl",), json.dumps({"ts": self.ahora(), "tipo": "backend_detener_fallo",
                                                                  "detalle": type(e).__name__}) + "\n")
            if mem is not None:
                mem.cerrar()
            lab_ej.quitar_candado()
        man = self._manifiesto(lab_ej, base)
        inf = inf or {}
        res = {"tarea": tid, "ejecucion": eid, "clase": "funcion_supervisada", "estado_final": inf.get("estado_final"),
               "resultado": inf.get("resultado"), "motivo": inf.get("motivo"),
               "version_recomendada": inf.get("version_recomendada"),
               "ejecucion_dinamica": "bloqueada", "autorizo_pruebas_ignorado": autorizado,
               "backend": (inf.get("backend") or {}).get("etiqueta"), "simulado": (inf.get("backend") or {}).get("simulado"),
               "pasos": (inf.get("limites") or {}).get("pasos"), "llamadas": inf.get("llamadas"),
               "informe": f"ejecuciones/{eid}/funcion/informe.md", "manifiesto_sha256": man,
               "nota": "sin ejecución no hay verificación: «aceptada_sin_ejecucion» no es «verificado»"}
        self.evento(tid, "ejecucion_terminada", **res)
        return res

    def _auditar(self, lab_ej, inf, ej, agentes, instrucciones, permitir_llm=True):
        """Auditoría determinista (el código) + auditoría de A3 (texto, solo lectura). Archivos nuevos."""
        lab_ej.crear_dir("auditoria")
        pruebas = []
        for reg in ej.ejecuciones:
            pruebas.append({k: reg.get(k) for k in ("estado", "codigo_retorno", "nonce_valido", "tiempo_excedido",
                                                     "duracion_s", "salida_sha256", "resultado", "problemas",
                                                     "archivos_modificados_por_las_pruebas")})
        # las versiones del proyecto deben seguir coincidiendo con su manifiesto
        integridad = []
        for v in inf.get("versiones") or []:
            for f in v.get("archivos", []):
                rel = f.get("ruta")
                cand = [p for p in lab_ej.base.glob(f"runs/*/proyecto/v{v.get('version')}/{rel}")]
                ok = bool(cand) and sha256(cand[0].read_bytes()) == f.get("sha256")
                integridad.append({"version": v.get("version"), "archivo": rel, "sha256": f.get("sha256"), "coincide": ok})
        ult = pruebas[-1] if pruebas else {}
        verificado = (inf.get("resultado") == "verificado" and inf.get("estado_final") == "criterios_verificados"
                      and ult.get("estado") == "ok" and ult.get("nonce_valido") is True
                      and all(x["coincide"] for x in integridad))
        # V2-F: todo pasa, pero hay reservas (criterio retirado, prueba debilitada, disputa, supuesto sin respuesta)
        con_reservas = (inf.get("resultado") == "verificado_con_reservas"
                        and inf.get("estado_final") == "verificado_con_reservas"
                        and ult.get("estado") == "ok" and ult.get("nonce_valido") is True
                        and all(x["coincide"] for x in integridad))
        det = {"conclusion": "verificado" if verificado else "verificado_con_reservas" if con_reservas else "no_verificado",
               "reservas": (inf.get("v2f") or {}).get("reservas") or [],
               "regla": "verificado solo si el motor terminó en criterios_verificados con pruebas REALES, la última "
                        "ejecución de pruebas fue ok con nonce válido y los archivos coinciden con su manifiesto",
               "estado_final_motor": inf.get("estado_final"), "resultado_motor": inf.get("resultado"),
               "criterios": inf.get("criterios"), "ejecuciones_de_pruebas": pruebas, "integridad_archivos": integridad}
        lab_ej.crear_exclusivo(("auditoria", "determinista.json"), json.dumps(det, ensure_ascii=False, indent=1, default=str))
        evid = json.dumps({"conclusion_del_codigo": det["conclusion"], "estado_final": det["estado_final_motor"],
                           "criterios": [{k: c.get(k) for k in ("id", "descripcion", "prueba", "estado")}
                                         for c in (inf.get("criterios") or [])],
                           "pruebas": [{k: p.get(k) for k in ("estado", "codigo_retorno", "nonce_valido")} |
                                       {"resultado": (p.get("resultado") or {}).get("pruebas")} for p in pruebas[-2:]],
                           "archivos_ultima_version": [x["archivo"] for x in integridad
                                                       if x["version"] == len(inf.get("versiones") or [])]},
                          ensure_ascii=False)[:2500]
        try:
            if not permitir_llm:
                raise RuntimeError("parada solicitada: A3 no se consulta (solo auditoría determinista)")
            texto = agentes.auditar(instrucciones, evid) or ""
            m = re.search(r"AUDITORIA:\s*(conforme|no_conforme)", texto, re.I)
            a3 = {"veredicto": m.group(1).lower() if m else "sin_veredicto", "error": None}
        except Exception as e:                       # una auditoría fallida se registra; no se inventa
            texto, a3 = "", {"veredicto": "no_realizada", "error": f"{type(e).__name__}: {e}"[:300]}
        lab_ej.crear_exclusivo(("auditoria", "A3_auditoria.txt"),
                               "# Auditoría de A3 (texto del modelo; NO cambia la conclusión del código)\n"
                               f"# veredicto: {a3['veredicto']}  error: {a3['error']}\n\n" + texto)
        lab_ej.crear_exclusivo(("auditoria", "A3_evidencia_recibida.json"), evid)
        return {"conclusion": det["conclusion"], "A3": a3}

    def _manifiesto(self, lab_ej, base: Path) -> str:
        lineas = [f"{sha256(p.read_bytes())}  {p.relative_to(base).as_posix()}"
                  for p in sorted(base.rglob("*")) if p.is_file() and not p.is_symlink()]
        txt = "\n".join(lineas) + "\n"
        lab_ej.crear_exclusivo(("MANIFIESTO_SHA256.txt",), txt)
        return sha256(txt.encode("utf-8"))

    # --- estado -------------------------------------------------------------------------------------
    def estado(self, tid) -> dict:
        tid = self.resolver(tid)
        ev = self.eventos(tid)
        ejecs = []
        for e in ev:
            if e["tipo"] == "ejecucion_terminada":
                ejecs.append({k: e.get(k) for k in ("ejecucion", "estado_final", "resultado", "auditoria_A3",
                                                    "pruebas_reales_ejecutadas", "ts")})
        abiertas = [e["ejecucion"] for e in ev if e["tipo"] == "ejecucion_iniciada"
                    and not any(x["tipo"] in ("ejecucion_terminada", "ejecucion_interrumpida", "ejecucion_rechazada")
                                and x.get("ejecucion") == e["ejecucion"] for x in ev)]
        t = self.tarea(tid)
        return {"tarea": tid, "titulo": t["titulo"], "importada": t["importada"],
                "estado": ("en_ejecucion_o_interrumpida" if abiertas else
                           ("terminada" if ejecs else "importada")),
                "ejecuciones": ejecs, "sin_terminar": abiertas, "eventos": len(ev),
                "ultimo_evento": ev[-1] if ev else None}

    # --- exportar -----------------------------------------------------------------------------------
    def exportar(self, tid) -> Path:
        tid = self.resolver(tid)
        self.lab.crear_dir("exportaciones")
        nombre, n = f"EQUIPO_IA_{tid}_ENTREGA.zip", 1
        while self.lab.existe("exportaciones", nombre):
            n += 1
            nombre = f"EQUIPO_IA_{tid}_ENTREGA_v{n}.zip"
        origen = self.lab.ruta("tareas", tid)
        raiz_zip = nombre[:-4]
        archivos = [p for p in sorted(origen.rglob("*")) if p.is_file() and not p.is_symlink()]
        est = self.estado(tid)
        leeme = (f"Entrega de la tarea {tid} de Equipo IA ({VERSION}).\n"
                 f"Estado: {est['estado']}. Ejecuciones: {json.dumps(est['ejecuciones'], ensure_ascii=False)}\n\n"
                 "Contenido: tarea_original.json (instrucciones tal cual), tarea.json, eventos.jsonl (historial),\n"
                 "ejecuciones/E<nnn>/ (runs/: eventos e informe del motor y versiones del código;\n"
                 "pruebas/P<nnn>/: espacio ejecutado, registro.json con comando, código de retorno, tiempos y huellas,\n"
                 "salida.txt, errores.txt, informe_unittest.txt; auditoria/: determinista.json y A3_auditoria.txt).\n"
                 "Comprobar: unzip el ZIP, cd a la carpeta y `sha256sum -c MANIFIESTO_SHA256.txt`.\n"
                 "«verificado» solo lo decide el código con pruebas reales; el texto de A3 es una opinión.\n")
        contenido = {}
        for p in archivos:
            contenido["tarea/" + p.relative_to(origen).as_posix()] = p.read_bytes()
        contenido["LEEME.txt"] = leeme.encode("utf-8")
        man = "".join(f"{sha256(b)}  {r}\n" for r, b in sorted(contenido.items()))
        contenido["MANIFIESTO_SHA256.txt"] = man.encode("utf-8")
        with self.lab.abrir_binario_exclusivo(("exportaciones", nombre)) as f:
            with zipfile.ZipFile(f, "w", zipfile.ZIP_DEFLATED) as z:
                for r, b in sorted(contenido.items()):
                    zi = zipfile.ZipInfo(f"{raiz_zip}/{r}", date_time=(2026, 1, 1, 0, 0, 0))
                    zi.compress_type = zipfile.ZIP_DEFLATED
                    zi.external_attr = 0o644 << 16
                    z.writestr(zi, b)
        ruta = self.lab.ruta("exportaciones", nombre)
        self.evento(tid, "exportada", archivo=nombre, sha256=sha256(ruta.read_bytes()), archivos=len(contenido))
        return ruta


def agentes_para(tarea: dict, backend):
    """V2-F: los agentes adecuados al tipo de tarea, sobre el backend dado (Qwen real o simulado)."""
    if tarea.get("tipo") == "debate_codigo":
        from . import debate
        return debate.AgentesDebateLLM(backend)
    if tarea.get("tipo") == "funcion_supervisada":                           # V2-F.1
        from . import funcion_supervisada
        return funcion_supervisada.AgentesFuncionLLM(backend)
    if tarea.get("tipo", "codigo") == "codigo" and tarea.get("motor", "v2e") == "v2f":
        from . import motor_v2f
        return motor_v2f.AgentesMotorLLMV2F(backend)
    return motor.AgentesMotorLLM(backend)
