"""BackendLlama: cliente de llama-server local (127.0.0.1) con plazo efectivo y supervisión.

Una petición a la vez (-np 1, llamadas secuenciales). La salida del modelo es TEXTO
NO CONFIABLE: aquí solo se extrae y se mide; nunca se interpreta como orden.
Parámetros de muestreo (temperature 0, seed 1, cache_prompt true) copiados de prueba3.py.
"""
from __future__ import annotations

import json
import re

from . import cliente_http, config, modelo, sanea, servidor as srv
from .inferencia import BackendBase, ErrorInferencia, Respuesta
from .monitor import Monitor

_ESPECIALES = re.compile(r"<\|im_(start|end)\|>|<\|endoftext\|>|</s>|<s>")


def _entero(x):
    return x if isinstance(x, int) and not isinstance(x, bool) and x >= 0 else None


def _numero(x):
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) and x >= 0 else None


class BackendLlama(BackendBase):
    etiqueta = "QWEN_LOCAL"
    simulado = False

    def __init__(self, servidor, usar_wake_lock=False, ejecutar_wake=srv._ejecutar_simple,
                 intervalo_monitor=config.INTERVALO_MONITOR, lector_muestra=None,
                 margen_latido=5.0, espera_monitor=5, permitir_continuacion=True):
        self.srv = servidor
        self.usar_wake_lock = usar_wake_lock
        self.ejecutar_wake = ejecutar_wake
        self.intervalo_monitor = intervalo_monitor
        self.lector_muestra = lector_muestra
        self.margen_latido, self.espera_monitor = margen_latido, espera_monitor
        self.mon = None
        self.ctx = {}
        self.estado = "nuevo"          # nuevo -> iniciando -> listo -> detenido
        self.comprobaciones = None
        self.carga_s = None
        self.wake = None
        self.peticiones = []
        self.puerto_libre_antes = None
        self.detencion = None
        self.n_en_curso = 0
        # V2-D: continuación de respuestas cortadas (prefill). Solo si la versión la anuncia.
        self.permitir_continuacion = permitir_continuacion
        self.soporta_continuacion = False

    # --- comprobaciones sin arrancar nada -------------------------------------
    def comprobar(self, verificar_flags=True):
        return self.srv.comprobaciones(verificar_flags)

    # --- ciclo de vida -----------------------------------------------------------
    def iniciar(self, ctx=None):
        if self.estado != "nuevo":
            raise ErrorInferencia("backend_ya_usado", fatal=True)
        self.ctx = ctx or {}
        self.estado = "iniciando"
        previo = self._deberia_parar()                 # STOP/señal antes de lanzar nada
        if previo:
            raise ErrorInferencia("parada_antes_de_lanzar:" + previo, fatal=True)
        self.comprobaciones = self.srv.comprobaciones(True)
        self.puerto_libre_antes = self.comprobaciones.get("puerto_libre")
        if not self.comprobaciones["ok"]:
            raise ErrorInferencia("comprobaciones_fallidas:" + "; ".join(
                self.comprobaciones["problemas"])[:300], fatal=True)
        self.soporta_continuacion = bool(self.permitir_continuacion
                                         and self.comprobaciones.get("soporta_prefill") is True)
        if self.usar_wake_lock:
            self.wake = srv.wake_lock(self.ejecutar_wake)
        self.srv.lanzar(self.ctx["lab"], self.ctx["run_id"])
        kw = {} if self.lector_muestra is None else {"lector": self.lector_muestra}
        self.mon = Monitor(self.srv.pid, self.srv.vivo, intervalo=self.intervalo_monitor,
                           margen_latido=self.margen_latido, **kw)
        self.mon.iniciar()
        self.carga_s = self.srv.esperar_listo(self._deberia_parar, self.mon.supervisar)
        self.estado = "listo"

    def _deberia_parar(self):
        """Motivo por el que hay que abandonar la operación en curso, o None."""
        parar = self.ctx.get("parar")
        m = parar() if parar else None
        if m:
            return m
        if self.mon is not None:
            m = self.mon.supervisar()
            if m:
                return m
        if self.srv.proc is not None and not self.srv.vivo():
            return "servidor_muerto"
        return None

    def supervisar(self):
        if self.estado != "listo":
            return None
        if self.mon is not None:
            return self.mon.supervisar()
        return None

    # --- una petición -------------------------------------------------------------
    def completar(self, mensajes, max_tokens, plazo_s):
        if self.estado != "listo":
            raise ErrorInferencia("backend_no_listo", fatal=True)
        if self.n_en_curso:
            raise ErrorInferencia("peticion_concurrente", fatal=True)
        if not (isinstance(max_tokens, int) and 1 <= max_tokens <= config.TOPE_MAX_TOKENS):
            raise ErrorInferencia("max_tokens_fuera_de_rango", fatal=False)
        if (not isinstance(mensajes, list) or not mensajes or not all(
                isinstance(m, dict) and m.get("role") in ("system", "user", "assistant")
                and isinstance(m.get("content"), str) for m in mensajes)):
            raise ErrorInferencia("mensajes_invalidos", fatal=False)
        cuerpo = json.dumps({"messages": mensajes, "max_tokens": max_tokens,
                             "temperature": config.TEMPERATURA, "seed": config.SEMILLA,
                             "cache_prompt": True}).encode("utf-8")
        reg = {"n": len(self.peticiones) + 1, "max_tokens": max_tokens}
        self.peticiones.append(reg)
        self.n_en_curso += 1
        try:
            antes = self.mon.muestra_ahora()
            try:
                r = cliente_http.peticion(self.srv.puerto, "POST", "/v1/chat/completions",
                                          cuerpo, plazo_s, self._deberia_parar)
            except cliente_http.ErrorHTTP as e:
                motivo, fatal = e.motivo, e.fatal
                if not fatal and self.srv.murio_pronto():     # error de comunicación + hijo muerto
                    motivo, fatal = "servidor_muerto", True
                reg["fallo"] = motivo
                raise ErrorInferencia(motivo, fatal=fatal)
            despues = self.mon.muestra_ahora()
        finally:
            self.n_en_curso -= 1
        reg.update(status=r.status, pared_s=r.duracion_s)
        reg["memoria_kB"] = {k: [antes.get(k), despues.get(k)]
                             for k in ("MemAvailable", "VmRSS", "VmHWM", "RssAnon", "RssFile")}
        reg["delta_fallos"] = {k: (despues[k] - antes[k] if k in antes and k in despues else None)
                               for k in ("minflt", "majflt")}
        reg["criticas_ausentes"] = [k for k in config.CRITICAS if k not in antes or k not in despues]
        reg["log_errores"] = self.srv.log_nuevo()
        if r.status != 200:
            reg["fallo"] = f"http_{r.status}"
            reg["cuerpo_inicio"] = sanea.limpiar(r.cuerpo[:300].decode("utf-8", "replace"), 200)
            raise ErrorInferencia(f"http_{r.status}", fatal=False)
        try:
            d = json.loads(r.cuerpo)
            ch = d["choices"][0]
            txt = ch["message"]["content"]
            if not isinstance(txt, str):
                raise TypeError("content no es texto")
        except (ValueError, KeyError, IndexError, TypeError) as e:
            reg["fallo"] = "json_invalido"
            reg["detalle"] = sanea.limpiar(repr(e), 100)
            raise ErrorInferencia("json_invalido", fatal=False)
        t = d.get("timings") if isinstance(d.get("timings"), dict) else {}
        u = d.get("usage") if isinstance(d.get("usage"), dict) else {}
        fin = ch.get("finish_reason") if isinstance(ch.get("finish_reason"), str) else None
        pn, cn = _entero(t.get("prompt_n")), _entero(t.get("cache_n"))
        gen = _entero(t.get("predicted_n"))
        if gen is None:
            gen = _entero(u.get("completion_tokens"))
        tok_prompt = _entero(u.get("prompt_tokens"))
        if tok_prompt is None and pn is not None and cn is not None:
            tok_prompt = pn + cn
        metr = {k: t.get(k) for k in ("prompt_n", "cache_n", "prompt_ms", "prompt_per_second",
                                      "predicted_n", "predicted_ms", "predicted_per_second")}
        esp = bool(_ESPECIALES.search(txt))
        diag = ("ok_stop" if fin == "stop" and not esp else
                "length_por_limite" if fin == "length" and not esp and gen is not None
                and gen >= max_tokens else "REVISAR_terminacion")
        motivos = []
        if diag == "REVISAR_terminacion":
            motivos.append("terminacion_no_normal")
        if reg["criticas_ausentes"]:
            motivos.append("medicion_critica_ausente:" + ",".join(reg["criticas_ausentes"]))
        faltan = [k for k, v in metr.items() if v is None]
        if faltan:
            motivos.append("metricas_servidor_ausentes")
        reg.update(finish_reason=fin, diagnostico=diag, tokens_especiales_en_texto=esp,
                   chars=len(txt), metricas=metr, tokens_prompt_real=tok_prompt,
                   tokens_generados=gen, motivos_no_concluyente=motivos,
                   concluyente=not motivos)
        return Respuesta(texto=txt, tokens_prompt=tok_prompt, tokens_gen=gen, cache_n=cn,
                         ms_prompt=_numero(t.get("prompt_ms")), ms_gen=_numero(t.get("predicted_ms")),
                         finish_reason=fin)

    # --- parada y limpieza ------------------------------------------------------------
    def detener(self):
        if self.detencion is not None:
            return self.detencion
        pasos = {}

        def paso(nombre, fn):
            try:
                pasos[nombre] = fn()
            except BaseException as e:           # cada paso es independiente
                pasos[nombre] = f"ERROR {type(e).__name__}"

        paso("servidor", self.srv.detener)       # lo primero y más importante
        paso("monitor", (lambda: self.mon.detener(self.espera_monitor)) if self.mon else (lambda: "sin_monitor"))
        paso("wake_unlock", (lambda: srv.wake_lock(self.ejecutar_wake, liberar=True))
             if self.usar_wake_lock and self.wake is not None else (lambda: "no_usado"))
        paso("puerto_liberado", self.srv.esperar_puerto_libre)
        paso("cerrar_log", self.srv.cerrar_log)
        paso("modelo_sin_cambios", lambda: modelo.mismo_modelo(
            self.srv.huella_inicial, modelo.huella_modelo()) if self.srv.huella_inicial else "no_comprobable")
        problemas = []
        s = str(pasos.get("servidor"))
        if s not in ("SIGTERM_ok", "sin_servidor"):
            problemas.append(f"servidor:{s}")
        if str(pasos.get("monitor")) not in ("ok", "sin_monitor"):
            problemas.append(f"monitor:{pasos.get('monitor')}")
        if pasos.get("puerto_liberado") is not True:
            problemas.append(f"puerto_liberado:{pasos.get('puerto_liberado')}")
        if str(pasos.get("cerrar_log")) != "ok":
            problemas.append(f"cerrar_log:{pasos.get('cerrar_log')}")
        w = str(pasos.get("wake_unlock"))
        if w not in ("ok", "no_usado"):
            problemas.append(f"wake_unlock:{w}")
        if pasos.get("modelo_sin_cambios") is False:
            problemas.append("modelo_cambio_durante_la_ejecucion")
        critico = s.startswith("NO_TERMINA") or s.startswith("ERROR")
        self.estado = "detenido"
        self.detencion = {"ok": not critico, "limpio": not problemas, "problemas": problemas,
                          "pasos": pasos, "informe": self.informe()}
        return self.detencion

    def informe(self):
        return {"etiqueta": self.etiqueta, "estado": self.estado,
                "comprobaciones": self.comprobaciones, "argv": self.srv.argv,
                "carga_s": self.carga_s, "wake_lock": self.wake,
                "soporta_continuacion": self.soporta_continuacion,
                "puerto_libre_antes": self.puerto_libre_antes,
                "peticiones": self.peticiones,
                "monitor": self.mon.resumen() if self.mon else None,
                "nota": "TEXTO del modelo = no confiable; nunca se ejecuta"}
