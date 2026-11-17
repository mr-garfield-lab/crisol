"""V2-E.2: recuperación inteligente de contexto para incidencias.

Cuando las incidencias (con sus criterios y evidencias) no caben en el presupuesto de un agente:
  * se ordenan: críticas (gravedad ≥ 4) primero y después por prioridad;
  * cada incidencia incluida lleva SIEMPRE su cabecera y sus criterios de aceptación;
  * sus evidencias se ordenan por relevancia (prueba real > simulación > estático > observación >
    declaración; las más recientes primero) y entran mientras caben; las que no, se anotan como
    OMITIDAS y viajan en un paquete posterior («continuación»);
  * las incidencias que no caben quedan PENDIENTES para el paquete siguiente;
  * cada paquete se registra en la tabla `paquetes` (incluidas, omitidas, pendientes): nada se
    pierde en silencio y se puede auditar qué vio cada agente.
Contabilidad EXACTA: cada línea cuenta sus tokens estimados más uno por el salto de línea, y se
RESERVA el espacio de la nota de omisión antes de aceptar una evidencia, así que ningún paquete
supera el presupuesto (estimación len/3).
Si una cabecera sola no cabe, se recorta conservando primero el identificador y los CRITERIOS de
aceptación (marcada «CABECERA RECORTADA»).
Garantía de PROGRESO: si en un paquete de continuación no entra nada nuevo (una evidencia sola no
cabe), la primera evidencia pendiente se incluye RECORTADA y marcada; su texto completo sigue en la
base y en su archivo. Así no puede haber bucles de paquetes que no avanzan.
Lo que diga un agente («CORREGIDO: INC-…») solo se registra como declaración: no cambia el estado.

V2-E.3 — `ColaAgente`: paquetes para UNA llamada de un agente dentro de una ejecución del motor.
  * Solo las incidencias que el planificador le asigna a ese agente, en el orden recibido.
  * Cabecera compacta SIEMPRE (el modelo no recuerda llamadas anteriores) con el nivel de respaldo
    de la causa: hipótesis, estático, simulación o prueba real.
  * Evidencias SIN duplicar: lo ya entregado a ese agente en esa ejecución no se repite. Una
    evidencia larga se reparte en fragmentos entre llamadas sucesivas ([CONTINÚA] / (cont.)).
  * La cola es PERSISTENTE: lo pendiente es lo que no consta en la tabla `entregas`.
  * Dos fases: preparar() no escribe nada; confirmar() registra la entrega solo cuando el paquete
    ha llegado de verdad al agente (si el prompt no lo admite, sigue pendiente).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from . import contexto, sanea
from . import incidencias as inc_mod
from . import prioridad

RELEVANCIA = {"prueba_real": 0, "simulacion": 1, "analisis_estatico": 2, "observacion": 3,
              "registro": 4, "declaracion_agente": 5}
_CORREGIDO = re.compile(r"\b(CORREGID[OA]|RESUELT[OA]|ARREGLAD[OA]|VERIFICAD[OA]|SOLUCIONAD[OA])\s*:?\s*(INC-\d{6})",
                        re.IGNORECASE)
_DIAG_ID = re.compile(r"^\s*[-*]?\s*DIAGNOSTICO\s+(INC-\d{6})\s*:\s*(\S.*)$", re.IGNORECASE | re.MULTILINE)
_DIAG = re.compile(r"^\s*[-*]?\s*DIAGNOSTICO\s*:\s*(\S.*)$", re.IGNORECASE | re.MULTILINE)
MIN_FRAGMENTO = 30                   # caracteres mínimos de un fragmento de evidencia


def _cabecera(i) -> str:
    crit = "; ".join(i["criterios"]) or "(sin criterios definidos)"
    return (f"[{i['id']}] {i['titulo']} | gravedad {i['gravedad']} impacto {i['impacto']} | "
            f"estado {i['estado']} | causa ({i['causa_estado']}): {i['causa'] or 'desconocida'}\n"
            f"  CRITERIOS: {crit}")


def _ev_txt(e) -> str:
    return f"  - E{e['num']} [{e['tipo']}/{e['resultado']}] {e['descripcion']}"


def _nota(n) -> str:
    return f"  (+{n} evidencias en el paquete siguiente)"


def _t(texto) -> int:
    """Tokens de una línea, incluido su salto de línea."""
    return contexto.estimar_tokens(texto) + 1


T_NOTA = _t(_nota(999_999))          # reserva para la nota de omisión (cota superior)


def _ajustar(texto, sufijo, max_tokens) -> str | None:
    """`texto` recortado + `sufijo` sin superar `max_tokens` (incluido el salto). None si no cabe."""
    chars = (max_tokens - 1) * 3 - len(sufijo)
    while chars >= 1:
        t = sanea.limpiar(texto, chars) + sufijo
        if _t(t) <= max_tokens:
            return t
        chars -= 3
    return None


def _cabecera_minima(i, max_tokens) -> str:
    """Identificador + criterios (lo más importante) recortados al espacio disponible."""
    crit = "; ".join(i["criterios"]) or "(sin criterios definidos)"
    t = _ajustar(f"[{i['id']}] CRITERIOS: {crit}", " [CABECERA RECORTADA]", max_tokens)
    return t if t is not None else f"[{i['id']}]"


class Empaquetador:
    """Genera paquetes sucesivos que respetan `presupuesto_tokens`."""
    MINIMO = 40

    def __init__(self, registro: inc_mod.RegistroIncidencias, presupuesto_tokens: int, agente=None):
        if presupuesto_tokens < self.MINIMO:
            raise ValueError("presupuesto demasiado pequeño")
        self.reg, self.pres, self.agente = registro, int(presupuesto_tokens), agente
        orden = {x["id"]: n for n, x in enumerate(prioridad.puntuar(registro))}
        pend = registro.listar(inc_mod.PENDIENTES + ("corregida_sin_verificar",))
        pend.sort(key=lambda i: (0 if i["gravedad"] >= 4 else 1, orden.get(i["id"], 10 ** 6), i["id"]))
        self.cola = [(i["id"], None) for i in pend]      # (id, evidencias restantes o None = todas)

    def _evs(self, iid):
        evs = self.reg.evidencias(iid)
        evs.sort(key=lambda e: (RELEVANCIA[e["tipo"]], -e["num"]))
        return evs

    def siguiente(self):
        """Devuelve el próximo paquete o None si ya no queda nada."""
        if not self.cola:
            return None
        partes, incluidas, omitidas, recortadas, cab_recortadas = [], [], {}, [], []
        usado, nueva_cola = 0, []
        for n, (iid, restantes) in enumerate(self.cola):
            i = self.reg.obtener(iid)
            mapa = {e["num"]: e for e in self.reg.evidencias(iid)}
            evs = restantes if restantes is not None else [e["num"] for e in self._evs(iid)]
            reserva = T_NOTA if evs else 0
            # La continuación lleva cabecera compacta: los criterios viajaron en el primer paquete.
            cab = f"[{i['id']}] (cont.)" if restantes is not None else _cabecera(i)
            if usado + _t(cab) + reserva > self.pres:
                if incluidas:
                    nueva_cola.extend(self.cola[n:])
                    break
                cab = _cabecera_minima(i, self.pres - reserva)          # sola en el paquete
                cab_recortadas.append(iid)
            usado += _t(cab)
            bloque, puestas, quedan = [cab], [], []
            for k, num in enumerate(evs):
                t = _ev_txt(mapa[num])
                extra = 0 if k == len(evs) - 1 else T_NOTA
                if not quedan and usado + _t(t) + extra <= self.pres:
                    bloque.append(t)
                    puestas.append(num)
                    usado += _t(t)
                    continue
                if not quedan and not puestas and not incluidas and restantes is not None:
                    # Continuación en un paquete vacío y ni así cabe: se recorta para avanzar.
                    t = _ajustar(t, f" [E{num} RECORTADA]", self.pres - usado - extra)
                    if t is not None:
                        bloque.append(t)
                        puestas.append(num)
                        recortadas.append(num)
                        usado += _t(t)
                        continue
                quedan.append(num)
            if quedan:
                bloque.append(_nota(len(quedan)))
                usado += T_NOTA
                omitidas[iid] = quedan
                nueva_cola.append((iid, quedan))
            partes.append("\n".join(bloque))
            incluidas.append(iid)
        self.cola = nueva_cola
        pendientes = [iid for iid, r in self.cola if iid not in omitidas]
        texto = "\n".join(partes)
        with self.reg.con:
            self.reg.con.execute(
                "INSERT INTO paquetes(ts,agente,incluidas_json,evidencias_omitidas_json,pendientes_json,tokens_est) "
                "VALUES(?,?,?,?,?,?)", (self.reg.ahora(), self.agente, json.dumps(incluidas),
                                        json.dumps(omitidas), json.dumps(pendientes), usado))
        return {"texto": texto, "incluidas": incluidas, "evidencias_omitidas": omitidas,
                "evidencias_recortadas": recortadas, "cabeceras_recortadas": cab_recortadas,
                "pendientes": pendientes, "tokens_est": usado}

    def todos(self, max_paquetes=50):
        """Todos los paquetes. Si se alcanza el tope con cosas pendientes, el último lo indica."""
        out = []
        while len(out) < max_paquetes:
            p = self.siguiente()
            if p is None:
                break
            out.append(p)
        if self.cola and out:
            out[-1]["tope_alcanzado_con_pendientes"] = [i for i, _r in self.cola]
        return out


def procesar_respuesta_agente(registro: inc_mod.RegistroIncidencias, agente: str, texto: str,
                              ids_validos=None) -> list:
    """Registra cada «CORREGIDO: INC-…» como DECLARACIÓN (informativa). El estado NO cambia.
    V2-E.3: `ids_validos` limita las declaraciones a esas incidencias (p. ej. las de la ejecución)."""
    hechas = []
    validos = None if ids_validos is None else set(ids_validos)
    for _pal, iid in _CORREGIDO.findall(texto or ""):
        iid = iid.upper()
        if (validos is not None and iid not in validos) or iid in hechas:
            continue
        try:
            registro.obtener(iid)
        except KeyError:
            continue
        registro.declaracion_de_agente(iid, agente, f"{agente} afirma que está corregida (no verificado)")
        hechas.append(iid)
    return hechas


# ============================ V2-E.3: cola por agente ==========================================
ETIQUETA_HIPOTESIS = {"propuesta": "propuesta, sin probar", "consistente": "consistente (falta control)",
                      "respaldada": "respaldada por simulación (no es prueba real)", "refutada": "REFUTADA",
                      "ambigua": "ambigua (hay otra igual de apoyada)"}


def _linea_hipotesis(hips) -> str:
    if not hips:
        return ""
    orden = sorted(hips, key=lambda h: (h["estado"] == "refutada", h["num"]))[:3]
    return "\n  HIPÓTESIS: " + "; ".join(
        f"{h['id']} [{ETIQUETA_HIPOTESIS[h['estado']]}] patrón '{sanea.limpiar(h['patron'], 60)}' en {h['archivo']}"
        for h in orden)


def _cab_agente(i, tarea, hips=()) -> str:
    l1 = (f"[{i['id']}] {sanea.limpiar(i['titulo'], 120)} | gravedad {i['gravedad']} impacto {i['impacto']}"
          f" | estado {i['estado']}")
    if tarea:
        l1 += f" | tarea {tarea['accion']}: {tarea['motivo']}"
    l2 = "  " + inc_mod.ETIQUETA_RESPALDO[inc_mod.respaldo(i)] + (
        f": {sanea.limpiar(i['causa'], 300)}" if i.get("causa") else "")
    crit = "; ".join(i["criterios"]) or "(sin criterios definidos)"
    return f"{l1}\n{l2}{_linea_hipotesis(hips)}\n  CRITERIOS: {crit}"


@dataclass
class PaqueteAgente:
    agente: str
    paso: str
    run_id: str
    texto: str
    tokens_est: int
    incluidas: list
    entregas: list = field(default_factory=list)            # [{incidencia_id, evidencia_num, desde, hasta, completa}]
    pendientes_evidencias: dict = field(default_factory=dict)
    pendientes_incidencias: list = field(default_factory=list)


def _nota_cola(n) -> str:
    return f"  (+{n} pend.)"


T_NOTA_COLA = _t(_nota_cola(999_999))


class ColaAgente:
    """Cola persistente de lo que falta entregar a `agente` en la ejecución `run_id`.
    MINIMO: por debajo, la cabecera ocuparía todo y las evidencias no avanzarían nunca."""
    MINIMO = 80

    def __init__(self, registro: inc_mod.RegistroIncidencias, run_id: str, agente: str):
        if agente not in inc_mod.AGENTES:
            raise ValueError("agente inválido")
        self.reg, self.run_id, self.agente = registro, run_id, agente

    def _estado(self) -> dict:
        """{evidencia_num: (hasta, completa)} ya entregado a este agente en esta ejecución."""
        out = {}
        for r in self.reg.con.execute(
                "SELECT evidencia_num, max(hasta), max(completa) FROM entregas WHERE run_id=? AND agente=? "
                "AND evidencia_num IS NOT NULL GROUP BY evidencia_num", (self.run_id, self.agente)).fetchall():
            out[r[0]] = (r[1], bool(r[2]))
        return out

    def pendientes(self, ids) -> dict:
        """{incidencia: [evidencias aún no entregadas por completo]} (para el informe)."""
        est = self._estado()
        return {iid: [e["num"] for e in self.reg.evidencias(iid) if not est.get(e["num"], (0, False))[1]]
                for iid in ids}

    def preparar(self, paso: str, elementos, presupuesto: int):
        """`elementos`: [(id, tarea|None)] en orden de prioridad. NO escribe en la base.
        Devuelve None si no hay nada que entregar o el presupuesto no llega al mínimo."""
        elementos = list(elementos)
        if not elementos or presupuesto < self.MINIMO:
            return None
        pres, est = int(presupuesto), self._estado()
        partes, incluidas, entregas, pend_ev, pend_inc = [], [], [], {}, []
        usado, avance = 0, False
        for n, (iid, tarea) in enumerate(elementos):
            i = self.reg.obtener(iid)
            evs = [e for e in sorted(self.reg.evidencias(iid), key=lambda e: (RELEVANCIA[e["tipo"]], -e["num"]))
                   if not est.get(e["num"], (0, False))[1]]
            reserva = T_NOTA_COLA if evs else 0
            cab = _cab_agente(i, tarea, self.reg.hipotesis(iid))
            if usado + _t(cab) + reserva > pres:
                if partes:
                    pend_inc = [x for x, _t2 in elementos[n:]]
                    break
                cab = _cabecera_minima(i, pres - reserva)
            usado += _t(cab)
            bloque, quedan = [cab], []
            entregas.append({"incidencia_id": iid, "evidencia_num": None, "desde": 0, "hasta": 0, "completa": 1})
            for k, e in enumerate(evs):
                desde = est.get(e["num"], (0, False))[0]
                resto = e["descripcion"][desde:]
                pref = f"  - E{e['num']} [{e['tipo']}/{e['resultado']}] " + ("(cont.) " if desde else "")
                extra = 0 if k == len(evs) - 1 else T_NOTA_COLA
                t = pref + resto
                if not quedan and usado + _t(t) + extra <= pres:
                    bloque.append(t)
                    usado += _t(t)
                    avance = True
                    entregas.append({"incidencia_id": iid, "evidencia_num": e["num"], "desde": desde,
                                     "hasta": len(e["descripcion"]), "completa": 1})
                    continue
                if not quedan and not avance:
                    # Evidencia larga: se reparte en fragmentos entre llamadas (progreso garantizado).
                    # Un fragmento deja siempre algo pendiente: reserva SIEMPRE la nota.
                    disp, marca = pres - usado - T_NOTA_COLA, " [CONTINÚA]"
                    chars = (disp - 1) * 3 - len(pref) - len(marca)
                    while chars >= MIN_FRAGMENTO and _t(pref + resto[:chars] + marca) > disp:
                        chars -= 3
                    if chars >= MIN_FRAGMENTO:
                        t = pref + resto[:chars] + marca
                        bloque.append(t)
                        usado += _t(t)
                        avance = True
                        entregas.append({"incidencia_id": iid, "evidencia_num": e["num"], "desde": desde,
                                         "hasta": desde + chars, "completa": 0})
                        quedan.append(e["num"])          # el resto sigue pendiente
                        continue
                quedan.append(e["num"])
            if quedan:
                bloque.append(_nota_cola(len(quedan)))
                usado += T_NOTA_COLA
                pend_ev[iid] = quedan
            partes.append("\n".join(bloque))
            incluidas.append(iid)
        return PaqueteAgente(self.agente, paso, self.run_id, "\n".join(partes), usado, incluidas, entregas,
                             pend_ev, pend_inc)

    def confirmar(self, paq: PaqueteAgente) -> int:
        """Registra que `paq` llegó al agente: paquete + una fila por cabecera/fragmento entregado."""
        ahora = self.reg.ahora()
        with self.reg.con:
            c = self.reg.con.execute(
                "INSERT INTO paquetes(ts,agente,incluidas_json,evidencias_omitidas_json,pendientes_json,tokens_est) "
                "VALUES(?,?,?,?,?,?)", (ahora, self.agente, json.dumps(paq.incluidas),
                                        json.dumps(paq.pendientes_evidencias), json.dumps(paq.pendientes_incidencias),
                                        paq.tokens_est))
            for x in paq.entregas:
                self.reg.con.execute(
                    "INSERT INTO entregas(ts,run_id,agente,paso,incidencia_id,evidencia_num,desde,hasta,completa,"
                    "paquete_num) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (ahora, self.run_id, self.agente, paq.paso, x["incidencia_id"], x["evidencia_num"],
                     x["desde"], x["hasta"], x["completa"], c.lastrowid))
        return c.lastrowid


def diagnosticos_de(texto: str, ids_validos, unico=None) -> dict:
    """{INC: diagnóstico} a partir de 'DIAGNOSTICO INC-…: …'. Un 'DIAGNOSTICO: …' sin identificador solo
    se asigna si el agente recibió UNA sola incidencia (`unico`). Siempre son HIPÓTESIS."""
    out = {}
    validos = set(ids_validos)
    for iid, d in _DIAG_ID.findall(texto or ""):
        if iid.upper() in validos and iid.upper() not in out:
            out[iid.upper()] = sanea.limpiar(d, 300)
    if not out and unico in validos:
        m = _DIAG.search(texto or "")
        if m:
            out[unico] = sanea.limpiar(m.group(1), 300)
    return out
