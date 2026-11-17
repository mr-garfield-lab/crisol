"""Orquestador: único componente que toca SQLite y el sistema de archivos.

Flujo de 7 llamadas por tarea, estrictamente secuenciales. La salida del modelo
es texto no confiable: se limpia, se guarda y se muestra; jamás se ejecuta.

V2-C: los votos se evalúan con votos.evaluar_voto (un voto truncado o no verificable nunca
cuenta: 1 reintento dirigido y, si persiste, abstención obligatoria); se registra la
terminación de TODAS las fases; el consenso y la fiabilidad del procedimiento son dos
indicadores separados; un fallo de infraestructura detiene la sesión (antes en la subclase
de V2-B, ahora aquí).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import (VERSION, config, criticas, desbordes, integridad, memoria, metricas, perfiles_contexto,
               personalidad, plataforma, prompts, protocolo, rutas, sanea, votos)
from . import aprendizaje, independencia, roles  # V2-E.6
from .contexto import ContextoExcedido, estimar_tokens
from .inferencia import BackendBase, ErrorInferencia, parada_de
from .vigilancia import Vigilante


class SesionAbortada(Exception):
    def __init__(self, motivo):
        super().__init__(motivo)
        self.motivo = motivo


class TareaAbortada(Exception):
    def __init__(self, motivo):
        super().__init__(motivo)
        self.motivo = motivo


class SesionActiva(Exception):
    """Ya existe un candado. `obsoleto=True` si su pid no figura en /proc (no se borra solo)."""

    def __init__(self, mensaje, pid=None, obsoleto=False):
        super().__init__(mensaje)
        self.pid, self.obsoleto = pid, obsoleto


LIMITACIONES = (
    "TIMEOUT: el orquestador solo comprueba el plazo DESPUÉS de que el backend devuelva. "
    "Con un backend simulado no se puede interrumpir una llamada bloqueada. El plazo efectivo "
    "y la supervisión independiente los aplica BackendLlama (cliente_http: recv corto + plazo "
    "total + parada + monitor con latido), pero esa ruta NO se ha probado con el modelo real.",
    "TOKENS: " + config.ESTIMACION_TOKENS + ".",
    "TOCTOU: entre comprobar una ruta y usarla hay una ventana que solo otro proceso con "
    "permisos sobre el laboratorio podría aprovechar.",
    "Un SIGKILL deja el candado 'lock/' sin liberar; se detecta pero no se borra solo.",
    "SIGKILL del supervisor: el hijo llama-server podría seguir vivo (RAM y puerto ocupados); "
    "la siguiente ejecución lo detecta (proceso llama*) y se niega a arrancar, pero NO lo mata.",
    "Si la lectura de /proc se bloquea dentro del hilo monitor, solo la supervisión del hilo "
    "principal lo detecta; si el hilo principal también se bloquea no hay una tercera capa.",
    "V2-D CONTINUACIÓN: depende del prefill de llama-server (indicado por --no-prefill-assistant en "
    "--help); el comportamiento real no se ha verificado en el dispositivo.",
    "V2-D VOTACIÓN: si la propuesta final no está completa o no cabe entera para los votantes, NO se "
    "vota (resultado no_votada). Con ctx 1024 esto limita la longitud útil de la réplica.",
)


@dataclass
class _Turno:
    estado: str
    texto: str
    turno_id: int
    finish_reason: str | None = None
    terminacion: str | None = None
    evaluacion: dict | None = None
    recortados: tuple = ()
    omitidos: tuple = ()
    # V2-D
    bruto: str = ""                  # texto SIN limpiar (solo para continuar; nunca se ejecuta)
    mensajes: tuple = ()
    tokens_est: int | None = None
    tokens_prompt: int | None = None
    tokens_gen: int | None = None
    max_gen: int | None = None
    integridad: dict | None = None
    compresion: dict | None = None


class Orquestador:
    def __init__(self, base, backend, vigilante=None, reloj=time.monotonic,
                 ahora=memoria.ahora_iso, instalar_senales=False, raiz_laboratorio=None,
                 solicitar_evidencia=False):
        """`base` debe estar dentro del laboratorio autorizado ($TMPDIR/equipo_f2 por defecto).

        `raiz_laboratorio` solo se pasa explícito en pruebas.
        V2-E.5: `solicitar_evidencia=True` permite UNA llamada de aclaración por tarea (A3 cita la
        evidencia de sus objeciones o las retira); el tope de llamadas sube exactamente en 1.
        """
        if not isinstance(backend, BackendBase):
            raise TypeError("backend inválido")
        raiz = raiz_laboratorio if raiz_laboratorio is not None else rutas.raiz_laboratorio()
        self.lab = rutas.Laboratorio(raiz, base)     # RutaInsegura (ValueError) si no cumple
        self.base = self.lab.base
        self.backend = backend
        self.vig = vigilante or Vigilante()
        self.reloj, self.ahora = reloj, ahora
        self.instalar_senales = instalar_senales
        self.solicitar_evidencia = bool(solicitar_evidencia)
        self.max_llamadas_tarea = config.MAX_LLAMADAS_TAREA + (config.LLAMADAS_ACLARACION if self.solicitar_evidencia
                                                                else 0)
        self._parar = False
        self._errores_cierre = []
        self._reset_estado()

    def _reset_estado(self):
        self.sdb = None
        self.mem = {}
        self.apr = {}                          # V2-E.6: aprendizaje con evidencia (aprendizaje/<ag>.db)
        self.sid = None
        self.run_id = None
        self._t_sesion0 = 0.0
        self._t_tarea0 = 0.0
        self._llamadas_tarea = 0
        self._llamadas_total = 0
        self._tokens_tarea = 0                 # V2-E.6: generación pedida acumulada (límites estrictos)
        self._tokens_sesion = 0
        self._orden = 0
        self._tarea_interrumpida = None
        self.calibracion = []
        self.metricas = []               # V2-D: una fila por llamada al backend

    # --- control -----------------------------------------------------------
    def solicitar_parada(self):
        self._parar = True

    def _ev(self, tipo, detalle=""):
        try:
            if self.sdb is not None:
                self.sdb.evento(self.sid, tipo, detalle)
        except Exception as e:
            self._errores_cierre.append(f"evento_db:{type(e).__name__}")
        try:
            if self.run_id is not None:
                linea = json.dumps({"ts": self.ahora(), "tipo": tipo,
                                    "detalle": sanea.limpiar(detalle, 500)},
                                   ensure_ascii=False)
                self.lab.anexar(("runs", self.run_id, "eventos.jsonl"), linea + "\n")
        except (OSError, ValueError) as e:
            self._errores_cierre.append(f"evento_jsonl:{type(e).__name__}")

    def _motivo_parada(self):
        """Motivo de parada solicitada (para el backend), o None. No lanza.
        V2-E.5-r3: la primera parada detectada se RETIENE (aunque luego se borre STOP)."""
        m = "senal" if self._parar else ("stop_usuario" if os.path.lexists(str(self.base / "STOP")) else None)
        if m and getattr(self, "_parada_vista", None) is None:
            self._parada_vista = m
        return m

    def _chequear(self):
        m = self._motivo_parada()
        if m:
            raise SesionAbortada(m)
        ahora = self.reloj()
        if ahora - self._t_sesion0 > config.SEG_POR_SESION:
            raise SesionAbortada("tiempo_sesion")
        if ahora - self._t_tarea0 > config.SEG_POR_TAREA:
            raise TareaAbortada("tiempo_tarea")
        if self._llamadas_tarea >= self.max_llamadas_tarea:
            raise TareaAbortada("limite_llamadas")
        mb = self.backend.supervisar()
        if mb:
            raise SesionAbortada("backend_" + str(mb))
        motivo = self.vig.verificar()
        if self.vig.historial:
            try:
                self.sdb.registrar_muestra(self.sid, self.vig.historial[-1])
            except Exception as e:
                self._errores_cierre.append(f"muestra:{type(e).__name__}")
        if motivo:
            raise SesionAbortada(motivo)

    # --- una llamada -------------------------------------------------------
    def _invocar(self, tid, orden, fase, agente, mensajes, max_gen, tipo, tokens_est=None):
        """Una llamada al backend (la ÚNICA vía). Cuenta la llamada, aplica el plazo y registra
        métricas. Devuelve (resp, fallo, fatal, ini, fin, pared_s)."""
        # V2-E.6: límites ESTRICTOS de tokens de salida pedidos por tarea y por sesión (según el perfil).
        if self._tokens_sesion + max_gen > perfiles_contexto.tokens_sesion():
            self._ev("limite_tokens", f"sesion: {self._tokens_sesion} + {max_gen}")
            raise SesionAbortada("limite_tokens_sesion")
        if self._tokens_tarea + max_gen > perfiles_contexto.tokens_tarea():
            self._ev("limite_tokens", f"tarea: {self._tokens_tarea} + {max_gen}")
            raise TareaAbortada("limite_tokens_tarea")
        self._tokens_tarea += max_gen
        self._tokens_sesion += max_gen
        self._llamadas_tarea += 1
        self._llamadas_total += 1
        ini = self.ahora()
        c0 = self.reloj()
        resp, fallo, fatal = None, None, None
        try:
            resp = self.backend.completar(list(mensajes), max_gen, config.SEG_POR_LLAMADA)
            if not hasattr(resp, "texto"):
                fallo = "respuesta_sin_texto"
        except Exception as e:
            if isinstance(e, ErrorInferencia):
                fallo = e.motivo
                fatal = e.motivo if e.fatal else None
            else:
                fallo = type(e).__name__
        pared = round(self.reloj() - c0, 3)
        if fallo is None and pared > config.SEG_POR_LLAMADA:
            fallo = "plazo_superado"
        g = (lambda k: getattr(resp, k, None)) if fallo is None else (lambda k: None)
        self.metricas.append({"tarea_id": tid, "orden": orden, "fase": fase, "agente": agente,
                              "tipo": tipo, "max_tokens": max_gen, "tokens_est": tokens_est,
                              "tokens_prompt": g("tokens_prompt"), "tokens_gen": g("tokens_gen"),
                              "ms_prompt": g("ms_prompt"), "ms_gen": g("ms_gen"), "pared_s": pared,
                              "cache_n": g("cache_n"),
                              "finish_reason": g("finish_reason"), "fallo": fallo})
        return resp, fallo, fatal, ini, self.ahora(), pared

    def _registrar_fallo(self, tid, orden, fase, agente, fallo, fatal, sha, ini, fin, tipo, max_gen,
                         pared):
        turno_id = self.sdb.registrar_turno(tid, orden, fase, agente, "fallido",
                                            sanea.limpiar(fallo, 100), sha, None, ini, fin,
                                            terminacion=None,
                                            motivo=sanea.limpiar("fallo:" + fallo, 100),
                                            tipo=tipo, max_tokens=max_gen, pared_s=pared)
        self._ev("llamada_fallida", f"{fase}/{agente} ({tipo}): {fallo}")
        if fatal:
            m = sanea.limpiar(fatal, 80)
            raise SesionAbortada(m if m in ("senal", "stop_usuario") else "backend_" + m)
        return turno_id

    @staticmethod
    def _clasificar(fase, bruto, fr):
        """(texto_limpio, estado, terminacion, motivo, evaluacion_voto, integridad)."""
        completo = sanea.limpiar(bruto, 10 ** 6)
        texto = completo[:config.MAX_TURNO_CHARS]
        recortado = len(completo) > config.MAX_TURNO_CHARS
        if fase == "voto":
            ev = votos.evaluar_voto(texto, fr)
            if recortado and ev["estado"] == "valido":
                ev = dict(ev, estado="truncado", postura=None, motivo="voto_truncado")
            return (texto, "ok" if ev["estado"] == "valido" else "invalido",
                    votos.terminacion(fr) if not recortado else "truncada", ev["motivo"], ev, None)
        integ = integridad.evaluar(fase, texto, fr, recortado)
        mapa = {"finish_length": "respuesta_truncada",
                "finish_reason_desconocido": "terminacion_no_verificable"}
        motivos = [mapa.get(m, m) for m in integ["motivos"]]
        if not texto:
            return texto, "invalido", integ["terminacion"], "respuesta_vacia", None, integ
        return (texto, "ok", integ["terminacion"], ";".join(motivos) or None, None, integ)

    def _llamar(self, tid, fase, agente, enunciado, hist, recordatorio=False,
                truncados=(), tipo="normal") -> _Turno:
        self._chequear()
        memorias = []
        if fase in ("analisis", "propuesta"):
            # V2-E.6: memorias con METADATOS. Primero el aprendizaje con evidencia (verificados delante),
            # dejando un hueco para la memoria de r3 si la hay; nunca solo el texto.
            try:
                r3 = [aprendizaje.de_memoria_r3(m) for m in self.mem[agente].buscar(enunciado)]
            except Exception as e:
                r3 = []
                self._ev("memoria_lectura_fallida", type(e).__name__)
            apr = []
            if agente in self.apr:
                try:
                    apr = self.apr[agente].recuperar(enunciado, config.MEMORIAS_POR_PROMPT - (1 if r3 else 0),
                                                     tarea_ref=tid)
                except Exception as e:
                    self._ev("aprendizaje_lectura_fallida", type(e).__name__)
            memorias = (apr + r3)[:config.MEMORIAS_POR_PROMPT]
        self._orden += 1
        orden = self._orden
        try:
            prompt = prompts.construir(fase, agente, enunciado, hist, memorias,
                                       recordatorio=recordatorio, truncados=truncados)
        except ContextoExcedido as e:
            self.sdb.registrar_turno(tid, orden, fase, agente, "omitido",
                                     sanea.limpiar(str(e), 200), None, tipo=tipo)
            self._ev("contexto_excedido", f"{fase}/{agente}")
            raise TareaAbortada("contexto_excedido")
        mensajes = tuple(prompt.mensajes())
        resp, fallo, fatal, ini, fin, pared = self._invocar(
            tid, orden, fase, agente, mensajes, prompt.max_gen, tipo, prompt.tokens_est)
        if fallo is not None:
            turno_id = self._registrar_fallo(tid, orden, fase, agente, fallo, fatal, prompt.sha256(),
                                             ini, fin, tipo, prompt.max_gen, pared)
            return _Turno("fallido", "", turno_id)
        real = getattr(resp, "tokens_prompt", None)
        if real is not None:
            self.calibracion.append({"fase": fase, "agente": agente, "tokens_est": prompt.tokens_est,
                                     "tokens_real": real, "max_gen": prompt.max_gen})
            self._ev("calibracion_tokens", f"est={prompt.tokens_est} real={real}")
            if real + prompt.max_gen > config.CTX:
                self._ev("contexto_real_excedido",
                         f"real={real} + max_gen={prompt.max_gen} > ctx={config.CTX}")
        bruto = resp.texto if isinstance(resp.texto, str) else ""
        fr = getattr(resp, "finish_reason", None)
        fr = fr if isinstance(fr, str) else None
        texto, estado, term, motivo, ev, integ = self._clasificar(fase, bruto, fr)
        turno_id = self.sdb.registrar_turno(tid, orden, fase, agente, estado, texto,
                                            prompt.sha256(), resp, ini, fin,
                                            terminacion=term, motivo=motivo, tipo=tipo,
                                            max_tokens=prompt.max_gen, pared_s=pared)
        if term != "completa":
            self._ev("respuesta_" + term, f"{fase}/{agente} finish_reason={fr} motivo={motivo}")
        return _Turno(estado, texto, turno_id, fr, term, ev,
                      tuple(prompt.recortados), tuple(prompt.omitidos),
                      bruto[:8000], mensajes, prompt.tokens_est, real,
                      getattr(resp, "tokens_gen", None), prompt.max_gen, integ, dict(prompt.compresion))

    def _continuar(self, tid, fase, agente, t: _Turno):
        """V2-D: UNA continuación de una respuesta cortada (prefill del mensaje 'assistant').

        Devuelve (_Turno unido | None, motivo). Nunca duplica: integridad.unir quita ecos y
        solapes y rechaza reinicios y duplicados. Se vuelve a verificar la integridad."""
        if not getattr(self.backend, "soporta_continuacion", False):
            return None, "backend_sin_continuacion"
        if self._llamadas_tarea >= self.max_llamadas_tarea:
            return None, "limite_llamadas"
        usado = (t.tokens_prompt if t.tokens_prompt is not None else (t.tokens_est or 0)) \
            + (t.tokens_gen if t.tokens_gen is not None else estimar_tokens(t.bruto))
        espacio = config.CTX - usado - config.MARGEN_CONTINUACION
        max_c = min(config.MAX_TOKENS_CONTINUACION, espacio)
        if max_c < config.MIN_TOKENS_CONTINUACION:
            self._ev("continuacion_sin_espacio", f"{fase}/{agente}: usado~{usado} ctx={config.CTX}")
            return None, "sin_espacio_para_continuar"
        self._chequear()
        self._orden += 1
        orden = self._orden
        mensajes = tuple(t.mensajes) + ({"role": "assistant", "content": t.bruto},)
        resp, fallo, fatal, ini, fin, pared = self._invocar(tid, orden, fase, agente, mensajes,
                                                            max_c, "continuacion")
        if fallo is not None:
            self._registrar_fallo(tid, orden, fase, agente, fallo, fatal, None, ini, fin,
                                  "continuacion", max_c, pared)
            raise TareaAbortada("inferencia_fallida")
        cont = resp.texto if isinstance(resp.texto, str) else None
        fr = getattr(resp, "finish_reason", None)
        fr = fr if isinstance(fr, str) else None
        u = integridad.unir(t.bruto, cont)
        frag = sanea.limpiar(cont or "", config.MAX_TURNO_CHARS)
        if not u["ok"]:
            self.sdb.registrar_turno(tid, orden, fase, agente, "invalido", frag, None, resp, ini, fin,
                                     terminacion=votos.terminacion(fr),
                                     motivo="continuacion_" + u["problema"], tipo="continuacion",
                                     max_tokens=max_c, pared_s=pared)
            self._ev("continuacion_rechazada", f"{fase}/{agente}: {u['problema']}")
            return None, "continuacion_" + u["problema"]
        texto, estado, term, motivo, _ev, integ = self._clasificar(fase, u["texto"], fr)
        turno_id = self.sdb.registrar_turno(tid, orden, fase, agente, estado, frag, None, resp,
                                            ini, fin, terminacion=term, motivo=motivo,
                                            tipo="continuacion", max_tokens=max_c, pared_s=pared)
        self._ev("continuacion", f"{fase}/{agente}: +{u['añadido']} chars, terminacion={term}")
        gen = (t.tokens_gen or 0) + (getattr(resp, "tokens_gen", None) or estimar_tokens(cont or ""))
        return _Turno(estado, texto, turno_id, fr, term, None, t.recortados, t.omitidos,
                      u["texto"][:8000], t.mensajes, t.tokens_est, t.tokens_prompt, gen,
                      t.max_gen, integ, t.compresion), None

    def _votar(self, tid, agente, enunciado, hist, truncados=()) -> dict:
        """Voto con evaluación estricta. Devuelve el voto FINAL ya decidido.

        valido -> cuenta. truncado / no_verificable / invalido -> 1 reintento con recordatorio
        dirigido; si persiste -> abstención OBLIGATORIA con motivo. Un fallo de inferencia
        (no fatal) aborta la TAREA como fallo de infraestructura (antes se convertía en
        abstención y la tarea seguía: defecto corregido en V2-C).
        """
        recordatorio = False
        intentos, ultimo, motivos = 0, None, []
        recortada = False
        for _intento in range(1 + config.MAX_REINTENTOS_VOTO):
            t = self._llamar(tid, "voto", agente, enunciado, hist, recordatorio=recordatorio,
                             truncados=truncados,
                             tipo="normal" if recordatorio is False else "reintento_voto")
            intentos += 1
            ultimo = t
            if t.estado == "fallido":
                raise TareaAbortada("inferencia_fallida")
            ev = t.evaluacion or {"estado": "invalido", "motivo": "voto_sin_evaluar"}
            recortada = ("propuesta_final" in t.recortados or "propuesta_final" in t.omitidos)
            if ev["estado"] == "valido":
                return {"postura": ev["postura"], "razon": ev["razon"], "turno_id": t.turno_id,
                        "estado_voto": "valido", "motivo": None, "intentos": intentos,
                        "finish_reason": t.finish_reason, "advertencias": list(ev["advertencias"]),
                        "evaluacion": ev, "intentos_fallidos": motivos, "propuesta_recortada": recortada}
            motivos.append(ev.get("motivo") or ev["estado"])
            recordatorio = {"truncado": "truncado", "no_verificable": "no_verificable"}.get(
                ev["estado"], {"razon_obligatoria": "razon",
                               "razon_demasiado_larga": "razon_larga"}.get(ev.get("motivo"), "formato"))
        motivo = motivos[-1] if motivos else "voto_sin_evaluar"
        self._ev("abstencion_forzada", f"{agente}: {motivo} tras {intentos} intentos ({motivos})")
        return {"postura": "abstencion", "razon": "", "turno_id": ultimo.turno_id,
                "estado_voto": "abstencion_forzada", "motivo": motivo, "intentos": intentos,
                "finish_reason": ultimo.finish_reason, "advertencias": [],
                "evaluacion": ultimo.evaluacion, "intentos_fallidos": motivos,
                "propuesta_recortada": recortada}

    # --- una tarea ---------------------------------------------------------
    def _fase_completa(self, tid, fase, agente, enunciado, hist, truncados, avisos, extra):
        """V2-D: una fase no-voto con hasta MAX_CONTINUACIONES_POR_FASE continuaciones.

        Devuelve el _Turno final (unido si hubo continuación). `avisos`/`extra` acumulan
        advertencias y motivos de fiabilidad reducida."""
        t = self._llamar(tid, fase, agente, enunciado, hist, truncados=truncados)
        if t.estado != "ok":
            raise TareaAbortada("inferencia_fallida" if t.estado == "fallido" else "respuesta_vacia")
        n = 0
        while (t.integridad and integridad.necesita_continuacion(fase, t.integridad)
               and n < config.MAX_CONTINUACIONES_POR_FASE):
            n += 1
            nuevo, motivo = self._continuar(tid, fase, agente, t)
            if nuevo is None:
                avisos.append(f"continuacion_no_realizada:{fase}:{motivo}")
                break
            t = nuevo
            avisos.append(f"continuacion:{fase}:{t.terminacion}")
        for a in (t.integridad or {}).get("avisos", []):
            avisos.append(f"{a}:{fase}")
        for b, c in (t.compresion or {}).items():
            if not c.get("completo", True):
                extra.append(f"contexto_esencial_perdido:{fase}:{b}")
            elif c.get("lineas_descartadas") or c.get("lineas_partidas"):
                avisos.append(f"contexto_comprimido:{fase}:{b}")
        for b in t.recortados:
            avisos.append(f"bloque_recortado:{fase}:{b}")
        for b in t.omitidos:
            extra.append(f"bloque_omitido:{fase}:{b}")
        return t

    def _integridad_para_votar(self, enunciado, hist, terminaciones, truncados):
        """V2-D: la propuesta final debe estar COMPLETA y caber ENTERA en el prompt de cada
        votante. Devuelve la lista de motivos que impiden votar (vacía = se puede votar)."""
        motivos = []
        if not hist.get("replica"):
            motivos.append("sin_propuesta_final")
        t = terminaciones.get("replica")
        if t != "completa":
            motivos.append(f"propuesta_final_{t or 'ausente'}")
        if not motivos:
            for ag in config.AGENTES:
                try:
                    p = prompts.construir("voto", ag, enunciado, hist, [], truncados=truncados)
                except ContextoExcedido:
                    motivos.append(f"propuesta_final_no_cabe_para_votante:{ag}")
                    continue
                if "propuesta_final" in p.recortados or "propuesta_final" in p.omitidos:
                    motivos.append(f"propuesta_final_no_cabe_para_votante:{ag}")
        return motivos

    def _tarea(self, enunciado) -> dict:
        """V2-E: añade la duración de la tarea (tiempo de pared) al resultado."""
        t0 = self.reloj()
        try:
            r = self._tarea_interna(enunciado)
        except SesionAbortada:
            if self._tarea_interrumpida is not None:
                self._tarea_interrumpida["duracion_s"] = round(self.reloj() - t0, 3)
            raise
        r["duracion_s"] = round(self.reloj() - t0, 3)
        return r

    def _tarea_interna(self, enunciado) -> dict:
        tid = self.sdb.crear_tarea(self.sid, enunciado)
        self.sdb.estado_tarea(tid, "en_deliberacion")
        self._t_tarea0 = self.reloj()
        self._llamadas_tarea = 0
        self._tokens_tarea = 0
        self._orden = 0
        hist, vt, terminaciones, truncados = {}, {}, {}, set()
        avisos, extra = [], []
        aclaracion = None
        try:
            for _orden, fase, agente in config.PLAN:
                if fase != "voto":
                    t = self._fase_completa(tid, fase, agente, enunciado, hist,
                                            tuple(sorted(truncados)), avisos, extra)
                    hist[fase] = (integridad.quitar_marca_fin(t.texto)
                                  if fase in config.FASES_CON_MARCA_FIN else t.texto)
                    terminaciones[fase] = t.terminacion
                    if t.terminacion != "completa":
                        truncados.add(fase)
                    if fase == "revision" and self.solicitar_evidencia:          # V2-E.5 (opcional)
                        aclaracion = self._aclarar(tid, enunciado, hist, tuple(sorted(truncados)), avisos)
                    continue
                if not vt:
                    bloqueo = self._integridad_para_votar(enunciado, hist, terminaciones,
                                                          tuple(sorted(truncados)))
                    if bloqueo:
                        return self._no_votar(tid, enunciado, hist, terminaciones, bloqueo,
                                              avisos, extra, aclaracion)
                vt[agente] = self._votar(tid, agente, enunciado, hist,
                                         truncados=tuple(sorted(truncados)))
        except TareaAbortada as e:
            self.sdb.estado_tarea(tid, "abortada")
            self._ev("tarea_abortada", e.motivo)
            return {"tarea_id": tid, "estado": "abortada", "motivo": e.motivo,
                    "llamadas": self._llamadas_tarea, "terminaciones": terminaciones}
        except SesionAbortada as e:
            self.sdb.estado_tarea(tid, "abortada")
            self._tarea_interrumpida = {"tarea_id": tid, "estado": "abortada",
                                        "motivo": e.motivo, "llamadas": self._llamadas_tarea,
                                        "terminaciones": terminaciones}
            raise

        votos_ = {ag: (vt[ag]["postura"], vt[ag]["razon"]) for ag in config.AGENTES}
        estados = {ag: vt[ag]["estado_voto"] for ag in config.AGENTES}
        for ag in config.AGENTES:
            v = vt[ag]
            self.sdb.registrar_voto(tid, ag, v["turno_id"], v["postura"], v["razon"],
                                    estado_voto=v["estado_voto"], motivo=v["motivo"],
                                    intentos=v["intentos"], finish_reason=v["finish_reason"],
                                    advertencias_json=json.dumps(v["advertencias"],
                                                                 ensure_ascii=False))
        cuenta = protocolo.contar(votos_, estados)
        res = cuenta["resultado"]
        if cuenta["sesgo_autoria"]:
            self._ev("sesgo_autoria", cuenta["nota_sesgo"])
        adv = [f"{ag}:{a}" for ag in config.AGENTES for a in vt[ag]["advertencias"]]
        adv += votos.senales_calidad(hist, {ag: vt[ag]["evaluacion"] or {} for ag in config.AGENTES})
        adv += avisos
        extra = list(extra) + [f"propuesta_final_recortada_para_votante:{ag}"
                               for ag in config.AGENTES if vt[ag]["propuesta_recortada"]]
        # V2-E.5: críticas fundamentadas o no, contradicciones e incertidumbre (determinista).
        crit = criticas.evaluar_deliberacion(hist, {ag: vt[ag]["evaluacion"] or {} for ag in config.AGENTES},
                                             enunciado)
        crit["aclaracion"] = aclaracion
        adv += [f"critica:{c}" for c in crit["contradicciones"]]
        adv += [f"posible_critica_falsa:objecion_{n}" for n in crit["posibles_criticas_falsas"]]
        # V2-E.6: independencia de la revisión y de los votos (advertencias; no cambian el recuento)
        ind = independencia.analizar(hist, votos_, estados)
        adv += [f"independencia:{t}" for t in ind["tipos"]]
        if ind["tipos"]:
            self._ev("independencia", ", ".join(ind["tipos"]))
        if res in ("aprobada", "aprobada_con_cambios"):
            extra += [f"critica:{c}" for c in crit["contradicciones"]
                      if c.startswith("replica_acepta_pero_no_aplica") or "_aprueba_con_objecion_fundamentada_pendiente" in c]
        self._ev("criticas", json.dumps({k: crit[k] for k in ("conteo", "contradicciones", "problemas_no_resueltos")},
                                        ensure_ascii=False)[:900])
        if protocolo.depende_del_autor(votos_, estados):
            extra.append("decision_depende_del_voto_del_autor")
            self._ev("sesgo_autoria_decisivo", "sin el voto de A1 el resultado cambiaría")
        forzadas = {ag: vt[ag]["motivo"] for ag in config.AGENTES
                    if vt[ag]["estado_voto"] == "abstencion_forzada"}
        fia = protocolo.fiabilidad(cuenta, terminaciones, forzadas, adv, motivos_extra=extra)
        fia["criticas"] = crit                                   # V2-E.5: se guarda con la conclusión
        fia["independencia"] = ind                               # V2-E.6
        fia["consenso_no_es_correccion"] = True
        self._ev("fiabilidad", f"{fia['nivel']}: {fia['motivos']}")

        posturas = "\n".join(
            f"- {ag}: {votos_[ag][0]}"
            + (f" [ABSTENCIÓN OBLIGATORIA: {vt[ag]['motivo']}]" if estados[ag] != "valido"
               else f" ({votos_[ag][1]})") for ag in config.AGENTES)
        if res in ("aprobada", "aprobada_con_cambios"):
            final = hist.get("replica", "")
            if cuenta["cambios_pendientes"]:
                final += "\n\nCAMBIOS PENDIENTES:\n" + "\n".join(
                    "- " + c for c in cuenta["cambios_pendientes"])
        else:
            final = "POSTURAS (sin decisión del equipo; decide el usuario):\n" + posturas
        if fia["propuesta_estado"] != "completa":
            final = ("ADVERTENCIA: PROPUESTA FINAL " + fia["propuesta_estado"].upper()
                     + " (la réplica no terminó normalmente). NO es una conclusión fiable; "
                     "el recuento se conserva solo como registro.\n\n" + final)
        self.sdb.registrar_conclusion(
            tid, res, json.dumps(cuenta, ensure_ascii=False), final,
            propuesta_estado=fia["propuesta_estado"], fiabilidad=fia["nivel"],
            fiabilidad_json=json.dumps(fia, ensure_ascii=False))
        self.sdb.estado_tarea(tid, "sin_consenso" if res == "sin_consenso" else "decidida")
        self._escribir_propuesta(tid, res, final, fia)

        for ag in config.AGENTES:
            v = vt[ag]
            try:
                self.mem[ag].agregar(
                    "hipotesis",
                    f"Tarea {tid} «{enunciado[:120]}»: resultado {res} (fiabilidad "
                    f"{fia['nivel']}); mi voto {v['postura']}"
                    + (f" [obligatorio: {v['motivo']}]" if v["estado_voto"] != "valido" else "")
                    + f". Razón (sin verificar): {v['razon']}",
                    sesion_ref=self.sid, turno_ref=v["turno_id"])
                self.mem[ag].registrar_decision(tid, v["turno_id"], v["postura"], v["razon"])
            except (memoria.MemoriaLlena, ValueError) as e:
                self._ev("memoria_no_guardada", f"{ag}: {type(e).__name__}")
        self._aprender_de_tarea(tid, enunciado, res, fia, vt)
        return {"tarea_id": tid, "estado": "completa", "resultado": res,
                "conteo": cuenta["conteo"], "llamadas": self._llamadas_tarea,
                "cambios_pendientes": cuenta["cambios_pendientes"],
                "sesgo_autoria": cuenta["sesgo_autoria"], "fiabilidad": fia,
                "criticas": crit, "consenso_no_es_correccion": True, "independencia": ind,
                "terminaciones": terminaciones,
                "votos": {ag: {k: vt[ag][k] for k in ("postura", "estado_voto", "motivo",
                                                      "intentos", "intentos_fallidos",
                                                      "finish_reason", "advertencias")}
                          for ag in config.AGENTES}}

    def _aprender_de_tarea(self, tid, enunciado, res, fia, vt):
        """V2-E.6: lo que queda en el aprendizaje de cada agente tras una tarea. NO solo votos:
          * un HECHO OBSERVADO (lo que registró el sistema: resultado, fiabilidad y motivos), redactado para no
            confundir consenso con corrección; V2-E.6-r2: queda «sin_verificar» (antes se daba por verificado);
          * su VOTO como hipótesis de confianza baja (un voto nunca verifica nada)."""
        if not self.apr:
            return
        motivos = ", ".join((fia.get("motivos") or [])[:3]) or "ninguno"
        hecho = (f"Hecho observado (consenso, no una verificación de la solución): la tarea {tid} terminó con "
                 f"resultado {res} y fiabilidad {fia['nivel']} (motivos: {motivos[:90]}); enunciado «{enunciado[:80]}».")
        for ag in config.AGENTES:
            a = self.apr.get(ag)
            if a is None:
                continue
            try:
                # V2-E.6-r2: el hecho observado queda «sin_verificar» (un registro no es una prueba ejecutada)
                a.recordar("hecho", hecho, "observado", fuente_ref=f"sesion.db/conclusiones/tarea={tid}",
                           tarea_ref=tid, sesion_ref=self.sid, ambito=enunciado[:150], estado="sin_verificar")
                v = vt.get(ag) or {}
                rv = a.recordar("hipotesis", f"Mi voto en la tarea {tid}: {v.get('postura')} — {str(v.get('razon') or '')[:150]} "
                           "(opinión, sin verificar)", "voto", fuente_ref=f"votos/tarea={tid}", tarea_ref=tid,
                           turno_ref=v.get("turno_id"), sesion_ref=self.sid, ambito=enunciado[:150])
                if rv.get("cuarentena"):
                    self._ev("aprendizaje_cuarentena", f"{ag}: {rv['id']}: {rv['cuarentena'][:150]}")
            except (aprendizaje.RecuerdoRechazado, ValueError, sqlite3.DatabaseError) as e:
                self._ev("aprendizaje_no_guardado", f"{ag}: {type(e).__name__}: {str(e)[:120]}")

    def _aclarar(self, tid, enunciado, hist, truncados, avisos):
        """V2-E.5: UNA petición de evidencia a A3 para las objeciones sin evidencia o con una cita que no
        existe. Responde citando o RETIRANDO; no puede añadir objeciones. Un fallo no aborta la tarea:
        se conserva la revisión original y se anota."""
        pend = criticas.objeciones_a_aclarar(hist.get("revision", ""), hist.get("propuesta", ""), enunciado)
        info = {"pedidas": [o["n"] for o in pend], "realizada": False}
        if not pend:
            return info
        if self._llamadas_tarea >= self.max_llamadas_tarea:
            info["motivo"] = "limite_llamadas"
            return info
        t = self._llamar(tid, "aclaracion", "A3", enunciado,
                         dict(hist, aclarar=criticas.texto_para_aclarar(pend)), truncados=truncados)
        if t.estado != "ok":
            avisos.append(f"aclaracion_no_valida:{t.estado}")
            self._ev("aclaracion_fallida", t.estado)
            info["motivo"] = t.estado
            return info
        if t.terminacion != "completa":
            avisos.append(f"aclaracion_{t.terminacion}")
        nueva, r = criticas.fusionar_aclaracion(hist.get("revision", ""), t.texto, info["pedidas"])
        hist["revision"] = nueva
        info.update(r, realizada=True, terminacion=t.terminacion)
        self._ev("aclaracion", json.dumps(info, ensure_ascii=False)[:400])
        return info

    def _no_votar(self, tid, enunciado, hist, terminaciones, bloqueo, avisos, extra, aclaracion=None) -> dict:
        """V2-D: la propuesta final no es íntegra -> NO se vota (nadie puede aprobarla).
        Resultado 'no_votada', fiabilidad 'no_valida'. La base lo garantiza con CHECK."""
        term = terminaciones.get("replica")
        propuesta = ("completa" if term == "completa" else
                     "incompleta" if term == "truncada" else "no_verificable")
        fia = {"nivel": "no_valida", "impide_conclusion": True, "propuesta_estado": propuesta,
               "motivos": ["no_votada"] + list(bloqueo) + list(extra), "advertencias": list(avisos)}
        crit = criticas.evaluar_deliberacion(hist, {}, enunciado)              # V2-E.5
        crit["aclaracion"] = aclaracion
        fia["criticas"], fia["consenso_no_es_correccion"] = crit, True
        fia["independencia"] = independencia.analizar(hist)                 # V2-E.6 (sin votos)
        self._ev("votacion_omitida", ", ".join(bloqueo))
        final = ("ADVERTENCIA: NO SE VOTÓ. La propuesta final no está completa o no cabe entera "
                 "para los votantes (" + ", ".join(bloqueo) + "). NO es una conclusión.\n\n"
                 + (hist.get("replica") or hist.get("propuesta") or ""))
        self.sdb.registrar_conclusion(tid, "no_votada", "{}", final, propuesta_estado=propuesta,
                                      fiabilidad="no_valida",
                                      fiabilidad_json=json.dumps(fia, ensure_ascii=False))
        self.sdb.estado_tarea(tid, "propuesta_incompleta")
        self._escribir_propuesta(tid, "no_votada", final, fia)
        try:
            self.mem["A1"].agregar(
                "hipotesis", f"Tarea {tid} «{enunciado[:120]}»: mi propuesta final no se pudo "
                f"votar ({', '.join(bloqueo)[:150]}). Sin verificar.", sesion_ref=self.sid)
        except (memoria.MemoriaLlena, ValueError) as e:
            self._ev("memoria_no_guardada", f"A1: {type(e).__name__}")
        return {"tarea_id": tid, "estado": "completa", "resultado": "no_votada", "conteo": {},
                "llamadas": self._llamadas_tarea, "cambios_pendientes": [], "sesgo_autoria": False,
                "fiabilidad": fia, "terminaciones": terminaciones, "votos": {},
                "criticas": crit, "consenso_no_es_correccion": True, "independencia": fia["independencia"]}

    def _escribir_propuesta(self, tid, res, texto, fia=None):
        """Archivo de texto plano con nombre FIJO. Nunca se ejecuta."""
        cab = (f"ORIGEN: {self.backend.etiqueta}\nRESULTADO: {res}\n"
               "ESTADO: hipótesis, no verificada por el usuario\n"
               "CONSENSO: el acuerdo de los agentes NO demuestra que la propuesta sea correcta "
               "(no se ha ejecutado ni probado)\n")
        if fia is not None:
            cab += (f"FIABILIDAD: {fia['nivel']}\nPROPUESTA_FINAL: {fia['propuesta_estado']}\n"
                    f"MOTIVOS: {', '.join(fia['motivos']) or 'ninguno'}\n")
            cr = fia.get("criticas") or {}
            if cr:
                cab += (f"CRITICAS: {cr['conteo']}\n"
                        f"CONTRADICCIONES: {', '.join(cr['contradicciones']) or 'ninguna'}\n"
                        f"NO_RESUELTO: {'; '.join(cr['problemas_no_resueltos']) or 'nada señalado con cita'}\n"
                        f"INCERTIDUMBRE: {', '.join(cr['incertidumbre']) or 'ninguna señalada'}\n")
        cab += "---\n"
        self.lab.crear_exclusivo(("runs", self.run_id, "propuestas", f"tarea_{int(tid)}.txt"),
                                 cab + texto + "\n")

    # --- sesión ------------------------------------------------------------
    def _validar_tareas(self, tareas):
        if not tareas or len(tareas) > config.MAX_TAREAS_SESION:
            raise ValueError(f"se requieren 1..{config.MAX_TAREAS_SESION} tareas")
        limpias = []
        for t in tareas:
            c = sanea.limpiar(t, config.MAX_TAREA_CHARS + 1)
            if not c or len(c) > config.MAX_TAREA_CHARS:
                raise ValueError(f"tarea vacía o de más de {config.MAX_TAREA_CHARS} caracteres")
            limpias.append(c)
        return limpias

    def run(self, tareas) -> dict:
        """Deliberación completa de 7 llamadas por tarea."""
        limpias = self._validar_tareas(tareas)
        return self._sesion(limpias, "deliberacion", self._trabajo_deliberacion)

    # --- V2-E.6: reanudación EXPLÍCITA ---------------------------------------------------------------
    _RUN_ID = re.compile(r"^\d{8}_\d{6}_\d{6}_\d{1,10}$")

    def pendientes_de(self, run_id) -> dict:
        """Qué tareas de una ejecución anterior NO terminaron. Solo lee (runs/<run_id>/tareas.json y
        summary.json). Las tareas se procesan en orden, así que la i-ésima entrada de «tareas» del resumen
        corresponde a la i-ésima tarea pedida. Sin summary.json (corte brusco) todas cuentan como pendientes."""
        if not isinstance(run_id, str) or not self._RUN_ID.match(run_id):
            raise ValueError("run_id no válido")
        bruto = self.lab.leer_texto(("runs", run_id, "tareas.json"), 400_000)
        if bruto is None:
            raise FileNotFoundError(f"runs/{run_id}/tareas.json no existe (¿ejecución anterior a V2-E.6?)")
        reg = json.loads(bruto)
        tareas = list(reg.get("tareas") or [])
        if [hashlib.sha256(t.encode("utf-8")).hexdigest() for t in tareas] != reg.get("sha256"):
            raise ValueError("tareas.json no coincide con sus huellas: no se reanuda")
        resumen = json.loads(self.lab.leer_texto(("runs", run_id, "summary.json"), 4_000_000) or "null")
        hechas = []
        if isinstance(resumen, dict):
            for i, t in enumerate(resumen.get("tareas") or []):
                if i < len(tareas) and t.get("estado") == "completa":
                    hechas.append(i)
        return {"run_id": run_id, "modo": reg.get("modo"), "total": len(tareas), "completas": hechas,
                "pendientes": [t for i, t in enumerate(tareas) if i not in hechas],
                "indices_pendientes": [i for i in range(len(tareas)) if i not in hechas],
                "estado_anterior": (resumen or {}).get("estado") if isinstance(resumen, dict) else "sin_resumen",
                "motivo_anterior": (resumen or {}).get("motivo_fin") if isinstance(resumen, dict) else None,
                "sesion_anterior": (resumen or {}).get("sesion_id") if isinstance(resumen, dict) else None}

    def run_reanudacion(self, run_id) -> dict:
        """Reanuda EXPLÍCITAMENTE (nunca de forma automática) las tareas pendientes de `run_id` en una
        sesión NUEVA. La ejecución anterior y sus evidencias no se modifican."""
        pend = self.pendientes_de(run_id)
        if pend["modo"] != "deliberacion":
            raise ValueError("solo se reanudan deliberaciones")
        if not pend["pendientes"]:
            return {"estado": "nada_que_reanudar", "reanuda": pend}
        self._reanuda = {k: pend[k] for k in ("run_id", "total", "completas", "indices_pendientes", "estado_anterior",
                                             "motivo_anterior", "sesion_anterior")}
        try:
            res = self.run_deliberacion(pend["pendientes"])
        finally:
            self._reanuda = None
        res["reanuda"] = {k: pend[k] for k in ("run_id", "total", "completas", "indices_pendientes", "estado_anterior",
                                              "motivo_anterior", "sesion_anterior")}
        return res

    def run_una_llamada(self, tarea, fase="analisis", agente="A2") -> dict:
        """V2-A: UNA sola llamada (no una deliberación). Usa las mismas bases SQLite y límites."""
        limpias = self._validar_tareas([tarea])
        if fase not in config.MAX_TOKENS or fase == "voto" or agente not in config.AGENTES:
            raise ValueError("fase o agente no válidos para una llamada única")
        return self._sesion(limpias, "una_llamada",
                            lambda resumen, ls: self._trabajo_una_llamada(resumen, ls[0], fase, agente))

    def _trabajo_deliberacion(self, resumen, limpias):
        for enun in limpias:
            t = self._tarea(enun)
            resumen["tareas"].append(t)
            resumen["tareas_no_iniciadas"] -= 1
            if t.get("estado") == "abortada" and t.get("motivo") in config.MOTIVOS_TAREA_INFRAESTRUCTURA:
                self._ev("parada_por_infraestructura", str(t.get("motivo")))
                raise SesionAbortada("infraestructura_" + str(t["motivo"]))

    def run_eleccion_personalidad(self, registro, agentes=config.AGENTES, autorizado=False) -> dict:
        """V2-E.5-r2 (OPCIONAL): elección inicial de personalidad. Usa la MISMA sesión, candado,
        vigilancia, plazos y backend que una deliberación; las llamadas son secuenciales con el único
        servidor. Como máximo PERSONALIDAD_MAX_INTENTOS_AGENTE llamadas por agente. Ninguna
        deliberación ni tarea llama a este método."""
        if not (config.PERSONALIDAD_ELECCION_HABILITADA or autorizado):
            raise personalidad.EleccionDeshabilitada("la elección de personalidad está desactivada")
        tope = len(agentes) * config.PERSONALIDAD_MAX_INTENTOS_AGENTE
        if tope > self.max_llamadas_tarea:
            raise ValueError("demasiados agentes para el límite de llamadas")
        return self._sesion([], "eleccion_personalidad",
                            lambda resumen, _l: self._trabajo_personalidad(resumen, registro, agentes, autorizado))

    def _trabajo_personalidad(self, resumen, registro, agentes, autorizado):
        self._t_tarea0 = self.reloj()
        self._llamadas_tarea = 0
        self._tokens_tarea = 0
        self._orden = 0
        simulado = bool(self.backend.simulado)
        modelo = None if simulado else f"{self.backend.etiqueta}:{config.MODELO_PARTES[-1]}"

        def llamar(agente, mensajes, max_tokens):
            self._chequear()                         # parada, tiempo, límite, backend y recursos
            self._orden += 1
            resp, fallo, fatal, _i, _f, _p = self._invocar(None, self._orden, "personalidad", agente,
                                                           tuple(mensajes), max_tokens, "personalidad")
            if fatal:
                m = sanea.limpiar(fatal, 80)
                raise SesionAbortada(m if m in ("senal", "stop_usuario") else "backend_" + m)
            if fallo is not None:
                self._ev("llamada_fallida", f"personalidad/{agente}: {fallo}")
                return None, fallo
            return (resp.texto if isinstance(resp.texto, str) else None), None
        r = personalidad.ElectorPersonalidad(registro).elegir(llamar, simulado=simulado, modelo=modelo,
                                                              agentes=agentes, autorizado=autorizado)
        self._ev("personalidad", json.dumps({ag: v["estado"] for ag, v in r["agentes"].items()}))
        resumen["personalidad"] = r

    def run_deliberacion(self, tareas) -> dict:
        """run(tareas) + desbordes + conclusión válida + texto final (NO CONFIABLE)."""
        res = self.run(tareas)
        res["desbordes"] = desbordes.analizar(res)
        mon = ((res.get("backend_informe") or {}).get("informe") or {}).get("monitor") or {}
        res.setdefault("metricas", {})["memoria_min_kB"] = mon.get("min_MemAvailable_kB")
        res["metricas"]["carga_s"] = ((res.get("backend_informe") or {}).get("informe") or {}).get("carga_s")
        run_id = res.get("run_id")
        tareas_r = res.get("tareas", [])
        niveles = [((t.get("fiabilidad") or {}).get("nivel") or "no_valida") for t in tareas_r]
        res["fiabilidad_global"] = (max(niveles, key=protocolo.ORDEN_NIVEL.index)
                                    if niveles else "no_valida")
        res["conclusion_valida"] = bool(
            tareas_r and res.get("resultado_global") == "completo"
            and all(t.get("estado") == "completa" for t in tareas_r)
            and not any((t.get("fiabilidad") or {}).get("impide_conclusion", True) for t in tareas_r)
            and not res["desbordes"].get("hay_desbordamiento"))
        for t in tareas_r:
            tid = t.get("tarea_id")
            if run_id is None or tid is None or t.get("estado") != "completa":
                continue
            try:
                t["texto_final_no_confiable"] = self.lab.leer_texto(
                    ("runs", run_id, "propuestas", f"tarea_{int(tid)}.txt"), 8000)
            except (OSError, ValueError) as e:
                t["texto_final_no_confiable"] = None
                self._errores_cierre.append("leer_propuesta:" + type(e).__name__)
        if run_id is not None:
            informe = {"run_id": run_id, "version": VERSION,
                       "resultado_global": res.get("resultado_global"),
                       "conclusion_valida": res["conclusion_valida"],
                       "fiabilidad_global": res["fiabilidad_global"],
                       "estado": res.get("estado"), "motivo_fin": res.get("motivo_fin"),
                       "llamadas_total": res.get("llamadas_total"), "desbordes": res["desbordes"],
                       "tareas": [{k: v for k, v in t.items() if k != "texto_final_no_confiable"}
                                  for t in tareas_r]}
            try:
                self.lab.crear_exclusivo(("runs", run_id, "informe_deliberacion.json"),
                                         json.dumps(informe, ensure_ascii=False, indent=2, default=str))
            except (OSError, ValueError) as e:
                res["informe_escrito"] = False
                res.setdefault("errores_cierre", []).append("informe:" + type(e).__name__)
                res["resultado_global"] = "incompleto"
                res["conclusion_valida"] = False
        return res

    def _trabajo_una_llamada(self, resumen, enun, fase, agente):
        tid = self.sdb.crear_tarea(self.sid, enun)
        self.sdb.estado_tarea(tid, "en_deliberacion")
        self._t_tarea0 = self.reloj()
        self._llamadas_tarea = 0
        self._tokens_tarea = 0
        self._orden = 0
        try:
            t = self._llamar(tid, fase, agente, enun, {})
            if t.estado != "ok":
                raise TareaAbortada("inferencia_fallida" if t.estado == "fallido" else "respuesta_vacia")
        except TareaAbortada as e:
            self.sdb.estado_tarea(tid, "abortada")
            self._ev("tarea_abortada", e.motivo)
            resumen["tareas"].append({"tarea_id": tid, "estado": "abortada", "motivo": e.motivo,
                                      "llamadas": self._llamadas_tarea})
            resumen["tareas_no_iniciadas"] -= 1
            return
        except SesionAbortada as e:
            self.sdb.estado_tarea(tid, "abortada")
            self._tarea_interrumpida = {"tarea_id": tid, "estado": "abortada",
                                        "motivo": e.motivo, "llamadas": self._llamadas_tarea}
            raise
        self.sdb.estado_tarea(tid, "analisis_unico")
        self._escribir_propuesta(tid, "analisis_unico", t.texto)
        try:
            self.mem[agente].agregar(
                "hipotesis",
                f"Llamada única ({fase}) sobre «{enun[:120]}». Respuesta sin verificar: {t.texto[:200]}",
                sesion_ref=self.sid, turno_ref=t.turno_id)
        except (memoria.MemoriaLlena, ValueError) as e:
            self._ev("memoria_no_guardada", f"{agente}: {type(e).__name__}")
        resumen["tareas"].append({"tarea_id": tid, "estado": "completa", "resultado": "analisis_unico",
                                  "agente": agente, "fase": fase, "llamadas": self._llamadas_tarea,
                                  "turno_id": t.turno_id, "chars_respuesta": len(t.texto),
                                  "respuesta_texto_no_confiable": t.texto})
        resumen["tareas_no_iniciadas"] -= 1

    def _sesion(self, limpias, modo, trabajo) -> dict:
        self._reset_estado()
        self._errores_cierre = []
        self._parar = False
        self._parada_vista = None
        # V2-C: comprobar el esquema EN SOLO LECTURA antes de escribir nada en la carpeta
        # (candado, copias, runs): una carpeta de una versión anterior no se toca.
        esq = memoria.esquema_sesion_de(self.base / "datos" / "sesion.db")
        if esq is not None and esq != memoria.ESQUEMA_SESION:
            raise memoria.EsquemaIncompatible(
                f"sesion.db tiene esquema {esq}, se esperaba {memoria.ESQUEMA_SESION}; "
                "no se migra ni se modifica: usa una carpeta nueva")
        self.lab.crear_base()
        for d in ("datos", "copias", "runs"):
            self.lab.crear_dir(d)
        try:
            self.lab.crear_dir_exclusivo("lock")
        except FileExistsError:
            pid = (self.lab.leer_texto(("lock", "pid"), 32) or "").strip()
            # V2-E.5: a través del adaptador de plataforma (en Linux/Termux, el mismo /proc de antes).
            try:
                viva = plataforma.adaptador().pid_vivo(pid)
            except plataforma.NoSoportado:
                viva = None                       # sin forma de comprobarlo: nunca se sugiere borrarlo
            raise SesionActiva(
                f"candado existente: lock/ (pid={pid or 'desconocido'}, "
                + ("proceso vivo" if viva else "no se puede comprobar si el proceso vive en esta plataforma"
                   if viva is None else "candado OBSOLETO: bórralo a mano si nada lo usa")
                + ")", pid=pid or None, obsoleto=viva is False)
        try:
            self.lab.crear_exclusivo(("lock", "pid"), str(os.getpid()))
        except Exception:
            self.lab.quitar_candado()
            raise

        run_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f") + f"_{os.getpid()}"
        resumen = {"version": VERSION, "modo": modo, "run_id": run_id,
                   "backend": self.backend.etiqueta,
                   "simulado": bool(self.backend.simulado), "tareas": [],
                   "tareas_no_iniciadas": len(limpias), "estado": "abortada",
                   "motivo_fin": "no_iniciada", "errores_cierre": [],
                   "sesiones_recuperadas": [], "limitaciones": list(LIMITACIONES),
                   "estimacion_tokens": config.ESTIMACION_TOKENS,
                   "tareas_sha256": [hashlib.sha256(t.encode("utf-8")).hexdigest() for t in limpias],
                   "config": {"ctx": config.CTX, "max_tokens": dict(config.MAX_TOKENS),
                              "perfil_contexto": config.PERFIL_CONTEXTO,
                              "tokens_tarea_max": perfiles_contexto.tokens_tarea(),
                              "tokens_sesion_max": perfiles_contexto.tokens_sesion(),
                              "max_llamadas_tarea": self.max_llamadas_tarea,
                              "solicitar_evidencia": self.solicitar_evidencia,
                              "max_continuaciones_por_fase": config.MAX_CONTINUACIONES_POR_FASE,
                              "continuacion_permitida": bool(getattr(
                                  self.backend, "permitir_continuacion", False))}}
        previos = {}
        if self.instalar_senales and threading.current_thread() is threading.main_thread():
            for sg in (signal.SIGINT, signal.SIGTERM):
                previos[sg] = signal.signal(sg, lambda *_: self.solicitar_parada())
        try:
            self.lab.crear_dir("runs", run_id, "propuestas")
            self.run_id = run_id
            # V2-E.6: las tareas pedidas quedan registradas para una reanudación EXPLÍCITA posterior
            self.lab.crear_exclusivo(("runs", run_id, "tareas.json"), json.dumps(
                {"modo": modo, "tareas": limpias, "sha256": resumen["tareas_sha256"]}, ensure_ascii=False))
            if getattr(self, "_reanuda", None):
                resumen["reanuda"] = dict(self._reanuda)
            resumen["roles"] = roles.persistir(self.lab)                     # V2-E.6: criterios persistentes
            for nombre in ("sesion", "a1", "a2", "a3"):
                p = self.lab.ruta("datos", f"{nombre}.db")
                if os.path.lexists(str(p)):
                    memoria.respaldar(p, self.lab.ruta("copias"), etiqueta=run_id)
            self.sdb = memoria.SesionDB(self.lab.ruta("datos", "sesion.db"), self.ahora)
            for ag in config.AGENTES:
                self.mem[ag] = memoria.MemoriaAgente(
                    self.lab.ruta("datos", f"{ag.lower()}.db"), ag, self.ahora)
            if config.APRENDIZAJE_HABILITADO:                                   # V2-E.6
                self.lab.crear_dir("aprendizaje")
                for ag in config.AGENTES:
                    p = self.lab.ruta("aprendizaje", f"{ag.lower()}.db")
                    if os.path.lexists(str(p)):
                        memoria.respaldar(p, self.lab.ruta("copias"), etiqueta="apr_" + run_id)
                    self.apr[ag] = aprendizaje.AprendizajeAgente(p, ag, self.ahora)
            for obj in [self.sdb] + list(self.mem.values()) + list(self.apr.values()):
                if not obj.quick_check():
                    raise SesionAbortada("db_corrupta")
            resumen["sesiones_recuperadas"] = self.sdb.recuperar_interrumpidas()
            try:
                src = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
            except OSError:
                src = None
            self.sid = self.sdb.crear_sesion(
                src, self.backend.etiqueta,
                json.dumps({"ctx": config.CTX, "max_tokens": config.MAX_TOKENS, "modo": modo,
                            "simulado": bool(self.backend.simulado),
                            "estimacion_tokens": config.ESTIMACION_TOKENS}))
            resumen["sesion_id"] = self.sid
            self._t_sesion0 = self.reloj()
            self._ev("inicio", f"backend={self.backend.etiqueta} modo={modo}")
            if resumen.get("reanuda"):
                self._ev("reanudacion", f"de run {resumen['reanuda']['run_id']} (sesión "
                         f"{resumen['reanuda']['sesion_anterior']}): tareas {resumen['reanuda']['indices_pendientes']}")
            if resumen["sesiones_recuperadas"]:
                self._ev("sesiones_recuperadas",
                         "interrumpidas, no reanudadas: " + str(resumen["sesiones_recuperadas"]))
            try:
                self.backend.iniciar({"lab": self.lab, "run_id": run_id,
                                      "parar": self._motivo_parada})
            except SesionAbortada:
                raise
            except Exception as e:
                m = sanea.limpiar(getattr(e, "motivo", None) or type(e).__name__, 120)
                pm = self._motivo_parada() or self._parada_vista
                # V2-E.5-r3: la parada pedida solo «manda» si es lo que interrumpió el arranque. Un fallo
                # distinto (el servidor murió, faltan comprobaciones...) se informa aunque haya STOP.
                if pm and isinstance(e, ErrorInferencia) and parada_de(e.motivo):
                    raise SesionAbortada(pm)
                if pm:
                    resumen["parada"] = {"solicitada": True, "motivo": pm, "fallo_independiente": m,
                                         "clasificacion": "fallo_independiente_durante_parada"}
                    self._ev("fallo_independiente_durante_parada", m)
                raise SesionAbortada("backend_no_inicia:" + m)
            trabajo(resumen, limpias)
            hubo_abortada = any(t["estado"] == "abortada" for t in resumen["tareas"])
            resumen["estado"] = "abortada" if hubo_abortada else "completa"
            resumen["motivo_fin"] = "tarea_abortada" if hubo_abortada else "fin_normal"
        except SesionAbortada as e:
            resumen["estado"] = ("interrumpida" if e.motivo in ("stop_usuario", "senal")
                                 else "abortada")
            resumen["motivo_fin"] = e.motivo
            if self._tarea_interrumpida is not None:
                resumen["tareas"].append(self._tarea_interrumpida)
            resumen["tareas_no_iniciadas"] = max(
                0, len(limpias) - len(resumen["tareas"]))
            self._ev("sesion_abortada", e.motivo)
        except KeyboardInterrupt:
            resumen["estado"] = "interrumpida"
            resumen["motivo_fin"] = "ctrl_c"
            self._ev("sesion_abortada", "ctrl_c")
        except Exception as e:      # defecto inesperado: se informa, no se oculta
            resumen["estado"] = "abortada"
            resumen["motivo_fin"] = "error_interno:" + type(e).__name__
            self._ev("error_interno", f"{type(e).__name__}: {e}")
        finally:
            self._cerrar(resumen, previos)
        return resumen

    def _paso(self, nombre, fn):
        try:
            fn()
        except Exception as e:
            self._errores_cierre.append(f"{nombre}:{type(e).__name__}")

    def _cerrar(self, resumen, previos):
        # 1) lo más importante: detener el backend (servidor hijo) pase lo que pase
        informe = {}

        def detener_backend():
            informe.update(self.backend.detener() or {})
        self._paso("backend_detener", detener_backend)
        resumen["backend_informe"] = informe
        if informe and informe.get("limpio") is False:
            self._errores_cierre.append("backend_limpieza:" + ",".join(informe.get("problemas", [])))
        resumen["calibracion_tokens"] = list(self.calibracion)
        resumen["metricas"] = metricas.agregar(self.metricas)
        resumen["metricas"]["llamadas"] = list(self.metricas)
        if self.sdb is not None and self.sid is not None:
            self._paso("cerrar_sesion", lambda: self.sdb.cerrar_sesion(
                self.sid, resumen["estado"], resumen["motivo_fin"]))
        if self.apr:                                                         # V2-E.6
            aud = {}
            for a, obj in self.apr.items():
                self._paso("auditar_aprendizaje_" + a, lambda a=a, obj=obj: aud.__setitem__(a, obj.auditar()))
            resumen["aprendizaje"] = aud
            if any(not x.get("ok") for x in aud.values()):
                self._errores_cierre.append("aprendizaje_auditoria")
        for nombre, obj in ([("sesion", self.sdb)] + [(a, m) for a, m in self.mem.items()]
                            + [("apr_" + a, m) for a, m in self.apr.items()]):
            if obj is not None:
                self._paso("cerrar_db_" + nombre, obj.cerrar)
        self._paso("liberar_lock", self.lab.quitar_candado)
        for s, h in previos.items():
            self._paso("restaurar_senal", lambda s=s, h=h: signal.signal(s, h))
        resumen["llamadas_total"] = self._llamadas_total
        resumen["tokens_pedidos_sesion"] = self._tokens_sesion                 # V2-E.6
        resumen["errores_cierre"] = list(self._errores_cierre)
        limpio = (resumen["estado"] == "completa" and not self._errores_cierre)
        resumen["resultado_global"] = "completo" if limpio else "incompleto"
        if "parada" not in resumen:                                         # V2-E.5-r3
            if not self._parada_vista:
                resumen["parada"] = {"solicitada": False, "clasificacion": "sin_parada"}
            else:
                fallos = list(self._errores_cierre)
                if resumen["estado"] != "interrumpida":
                    fallos.insert(0, f"{resumen['estado']}:{resumen['motivo_fin']}")
                resumen["parada"] = {
                    "solicitada": True, "motivo": self._parada_vista, "fallos_independientes": fallos,
                    "clasificacion": ("fallo_independiente_durante_parada" if resumen["estado"] != "interrumpida"
                                      else "parada_con_fallo_de_limpieza" if fallos else "parada_limpia")}
        pets = ((informe.get("informe") or {}).get("peticiones")) or []
        noconc = [p.get("n") for p in pets if p.get("concluyente") is False]
        if noconc:
            resumen["peticiones_no_concluyentes"] = noconc
            if limpio:
                resumen["resultado_global"] = "completo_no_concluyente"
        if self.backend.simulado:
            resumen["nota"] = "BACKEND SIMULADO: no son medidas ni salidas del modelo real."
        if self.run_id is not None:
            try:
                resumen["summary_escrito"] = True
                self.lab.crear_exclusivo(("runs", self.run_id, "summary.json"),
                                         json.dumps(resumen, ensure_ascii=False, indent=2,
                                                    default=str))
            except (OSError, ValueError) as e:
                resumen["summary_escrito"] = False
                resumen["errores_cierre"].append("summary:" + type(e).__name__)
                resumen["resultado_global"] = "incompleto"
