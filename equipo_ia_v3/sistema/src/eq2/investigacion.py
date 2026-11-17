"""V2-E.4: investigación AUTOMÁTICA de incidencias (sin ejecutar código, sin pruebas reales).

Ciclo: detección → registro → priorización → diagnóstico (A2) → EXPERIMENTO → evaluación de las
evidencias → propuesta de corrección (A1) → revisión (A3) → REGRESIÓN → seguimiento.

Hipótesis LOCALIZADAS. A2 escribe:
    HIPOTESIS INC-000001: ARCHIVO pkg/ordenar.py PATRON .sort()
es decir, «el fallo de INC-000001 está asociado a que pkg/ordenar.py contiene '.sort()'».

Política de evidencias. Un experimento aislado con una regla «si contiene X, falla» solo comprueba
lo que la propia regla supone, así que NO basta. La hipótesis se evalúa con dos experimentos del
laboratorio (tipo «simulacion», reglas declarativas sobre el TEXTO de versiones reales del proyecto):
  * REPRODUCCIÓN: en la última versión donde se observó el fallo, el patrón está presente.
  * CONTROL: en una versión posterior donde el fallo ya NO se observa, el patrón está ausente.
Resultado:
  * reproducción refuta (el patrón no está donde falla)         -> refutada
  * reproducción apoya, aún no hay versión de control            -> consistente (NO confirmada)
  * control refuta (el patrón sigue donde ya no falla)           -> refutada
  * reproducción y control apoyan, y es la ÚNICA hipótesis así   -> respaldada: causa confirmada con
    respaldo «simulación» (correlación entre versiones, no causalidad ni funcionamiento real) y
    regresión creada (si se cumplen sus condiciones)
  * dos o más hipótesis respaldadas a la vez                     -> ambiguas: la causa vuelve a hipótesis
  * una hipótesis respaldada que luego se contradice             -> refutada: la causa vuelve a hipótesis
V2-E.4-r2: cada observación del motor se REGISTRA en la base (incidencia presente/ausente y SHA-256
del texto de cada archivo) y los experimentos se crean con `planificar_prueba_de_hipotesis`, que
guarda su procedencia. La base solo admite 'respaldada' si reproducción y control coinciden con
observaciones reales, y solo admite una causa confirmada si apunta a una hipótesis respaldada.
La base impide 'respaldada' sin los dos experimentos. Experimentos y regresiones son idempotentes
(firma / origen): reintentar no duplica nada; un experimento interrumpido se reanuda.

Seguimiento. En cada versión nueva se comprueban las regresiones de las hipótesis respaldadas; si el
patrón vuelve, se registra evidencia fallida y una incidencia «corregida» se reabre.

Límites (PresupuestoInvestigacion, con máximos duros en config): hipótesis por incidencia,
experimentos por incidencia y por ejecución, regresiones por incidencia y tiempo de investigación.
Al alcanzar uno se registra el motivo y la incidencia queda pendiente.
"""
from __future__ import annotations

import hashlib
import re
import sqlite3
import time
from dataclasses import asdict, dataclass

from . import config, proyecto, sanea
from . import incidencias as inc_mod
from . import laboratorio

_HIP = re.compile(r"^\s*[-*]?\s*HIPOTESIS\s+(INC-\d{6})\s*:\s*ARCHIVO\s+(\S+)\s+PATRON\s+(.+?)\s*$",
                  re.IGNORECASE | re.MULTILINE)
LIMITACION = ("correlación textual entre versiones en simulación: no demuestra causalidad ni "
              "funcionamiento real")


@dataclass(frozen=True)
class PresupuestoInvestigacion:
    max_hipotesis_por_incidencia: int = 3
    max_experimentos_por_incidencia: int = 6
    max_experimentos_por_ejecucion: int = 12
    max_regresiones_por_incidencia: int = 2
    seg_max_investigacion: float = 30.0

    def acotado(self) -> "PresupuestoInvestigacion":
        m = config.INVESTIGACION_MAXIMOS
        return PresupuestoInvestigacion(
            *(max(0, min(int(getattr(self, k)), m[k])) for k in (
                "max_hipotesis_por_incidencia", "max_experimentos_por_incidencia",
                "max_experimentos_por_ejecucion", "max_regresiones_por_incidencia")),
            max(0.0, min(float(self.seg_max_investigacion), float(m["seg_max_investigacion"]))))


def _sha(t: str) -> str:
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def _limpiar_patron(p: str) -> str:
    p = p.strip()
    if len(p) >= 2 and p[0] == p[-1] and p[0] in "`'\"":
        p = p[1:-1]
    return p


def hipotesis_de(texto: str) -> list:
    """[(INC, archivo, patrón)] de las líneas 'HIPOTESIS INC-…: ARCHIVO … PATRON …' (sin validar)."""
    return [(i.upper(), a.strip("`'\""), _limpiar_patron(p)) for i, a, p in _HIP.findall(texto or "")]


class Investigador:
    def __init__(self, registro: inc_mod.RegistroIncidencias, run_id: str,
                 presupuesto: PresupuestoInvestigacion = None, reloj=time.monotonic):
        self.reg, self.run_id, self.reloj = registro, run_id, reloj
        self.pres = (presupuesto or PresupuestoInvestigacion()).acotado()
        self.lab = laboratorio.Laboratorio(registro, reloj=reloj)
        self.obs = {}                        # versión -> {"contenidos", "presentes", "comprobadas"}
        self.experimentos_run = 0
        self.t_usado = 0.0
        self.acciones = []                   # registro legible de lo que se hizo (para el informe)
        self.rechazadas = []                 # hipótesis inválidas (no llegan a la base)
        self._limites_anotados = set()

    # --- observaciones del motor -----------------------------------------------------------------
    def observar(self, version: int, contenidos: dict, presentes, comprobadas):
        """`presentes`: incidencias cuyo fallo se observa en `version`; `comprobadas`: incidencias cuya
        comprobación se hizo en esa versión (si está comprobada y no presente, no se observó)."""
        self.obs[int(version)] = {"contenidos": dict(contenidos or {}), "presentes": set(presentes),
                                  "comprobadas": set(comprobadas)}
        for iid in sorted(set(presentes) | set(comprobadas)):        # V2-E.4-r2: procedencia persistente
            self.reg.registrar_observacion(self.run_id, version, iid, iid in presentes, contenidos)

    # --- hipótesis -----------------------------------------------------------------------------------
    def proponer_desde_texto(self, texto: str, ids_validos, actor="A2", version=None) -> list:
        validos, out = set(ids_validos), []
        for iid, archivo, patron in hipotesis_de(texto)[:10]:
            motivo = None
            if iid not in validos:
                motivo = "incidencia no recibida por el agente"
            elif not proyecto.ruta_valida(archivo):
                motivo = "ruta no válida"
            elif not 2 <= len(patron) <= 120 or "\n" in patron:
                motivo = "patrón vacío o demasiado largo"
            elif (len(self.reg.hipotesis(iid)) >= self.pres.max_hipotesis_por_incidencia
                  and not any(h["archivo"] == archivo and h["patron"] == patron for h in self.reg.hipotesis(iid))):
                motivo = "límite de hipótesis por incidencia"
                self._limite(iid, motivo)
            if motivo:
                self.rechazadas.append({"incidencia": iid, "archivo": archivo[:80], "motivo": motivo})
                continue
            hid, nueva = self.reg.proponer_hipotesis(iid, actor, f"patrón '{patron}' en {archivo}", archivo,
                                                     patron, version=version)
            out.append(hid)
            if nueva:
                self.acciones.append(f"{hid} propuesta por {actor} para {iid}")
        return out

    # --- límites --------------------------------------------------------------------------------------
    def _limite(self, iid, motivo):
        clave = (iid, motivo)
        if clave in self._limites_anotados:
            return
        self._limites_anotados.add(clave)
        self.reg.registrar_evidencia(iid, "registro", "informativa", f"límite de investigación: {motivo}",
                                     "laboratorio", limitaciones="la incidencia queda pendiente")
        self.acciones.append(f"{iid}: límite de investigación ({motivo})")

    def _motivo_limite(self, iid):
        if self.t_usado >= self.pres.seg_max_investigacion:
            return "tiempo máximo de investigación"
        if self.experimentos_run >= self.pres.max_experimentos_por_ejecucion:
            return "experimentos por ejecución"
        n = self.reg.con.execute("SELECT count(*) FROM experimentos WHERE incidencia_id=? AND rol IS NOT NULL",
                                 (iid,)).fetchone()[0]
        if n >= self.pres.max_experimentos_por_incidencia:
            return "experimentos por incidencia"
        return None

    # --- experimentos -------------------------------------------------------------------------------
    def _experimento(self, h, rol, version):
        iid, archivo, patron = h["incidencia_id"], h["archivo"], h["patron"]
        texto = self.obs[version]["contenidos"].get(archivo, "")
        firma = _sha(f"{h['id']}|{rol}|{_sha(texto)}")[:32]
        previo = self.reg.con.execute("SELECT id, estado, conclusion FROM experimentos WHERE firma=?",
                                      (firma,)).fetchone()
        if previo and previo["estado"] != "planificado":
            return previo["conclusion"], previo["id"]               # ya hecho: no se repite
        if not previo:
            motivo = self._motivo_limite(iid)
            if motivo:
                self._limite(iid, motivo)
                return None, None
        try:
            eid = self.lab.planificar_prueba_de_hipotesis(h["id"], rol, self.run_id, version, texto,
                                                          limitaciones=LIMITACION)
        except ValueError as e:                                     # entradas fuera de límites
            self._limite(iid, f"experimento no planificable: {e}"[:120])
            return None, None
        t0 = self.reloj()
        r = self.lab.ejecutar(eid)                                  # reanuda si estaba 'planificado'
        self.t_usado += max(0.0, self.reloj() - t0)
        self.experimentos_run += 1
        self.acciones.append(f"{eid} {rol} de {h['id']} en v{version}: {r['conclusion']}")
        return r["conclusion"], eid

    def _evaluar(self, h):
        """'refutada' | 'consistente' | 'completa' (reproducción y control apoyan) | None."""
        iid = h["incidencia_id"]
        fallos = sorted(v for v, o in self.obs.items() if iid in o["presentes"])
        if not fallos:
            return None
        vf = fallos[-1]
        rep, eid_rep = self._experimento(h, "reproduccion", vf)
        if rep == "refuta":
            return "refutada", "el patrón no está en la versión donde se observa el fallo", eid_rep
        if rep != "apoya":
            return None
        pases = sorted(v for v, o in self.obs.items()
                       if v > fallos[0] and iid in o["comprobadas"] and iid not in o["presentes"]
                       and h["archivo"] in o["contenidos"])           # r2: el control exige el archivo observado
        if not pases:
            return "consistente", "reproducción apoya; falta una versión de control", eid_rep
        ctl, _e = self._experimento(h, "control", pases[-1])
        if ctl == "refuta":
            return "refutada", "el patrón sigue presente donde el fallo ya no se observa", eid_rep
        if ctl == "apoya":
            return "completa", "reproducción y control apoyan", eid_rep
        # Control no disponible (límite) o no concluyente: la reproducción sigue valiendo como consistencia.
        return "consistente", "reproducción apoya; control no disponible o no concluyente", eid_rep

    def investigar(self, iids) -> None:
        for iid in iids:
            completas = []
            for h in self.reg.hipotesis(iid):
                if h["estado"] == "refutada":
                    continue
                r = self._evaluar(h)
                if r is None:
                    continue
                res, motivo, eid_rep = r
                if res == "refutada":
                    self._refutar(h, motivo)
                elif res == "consistente" and h["estado"] == "propuesta":
                    self.reg.cambiar_hipotesis(h["id"], "consistente", "laboratorio", motivo)
                elif res == "completa":
                    completas.append((h, eid_rep))
            self._resolver(iid, completas)

    def _refutar(self, h, motivo):
        self.reg.cambiar_hipotesis(h["id"], "refutada", "laboratorio", motivo)
        self.acciones.append(f"{h['id']} refutada: {motivo}")
        inc = self.reg.obtener(h["incidencia_id"])
        if inc["causa_hipotesis"] == h["id"] or inc["causa"] in (h["texto"], f"{h['texto']} ({h['id']})"):
            # La causa vigente era ESTA hipótesis: se retira y la incidencia vuelve a diagnóstico.
            self.reg.retirar_causa(inc["id"], "laboratorio", f"{h['id']} refutada: {motivo}")

    def _resolver(self, iid, completas):
        inc = self.reg.obtener(iid)
        if len(completas) > 1:                                      # evidencias contradictorias
            for h, _e in completas:
                self.reg.cambiar_hipotesis(h["id"], "ambigua", "laboratorio",
                                           "varias hipótesis apoyadas a la vez: no se elige ninguna")
            if inc["causa_estado"] == "confirmada" and inc["causa_hipotesis"]:
                self.reg.volver_a_hipotesis(iid, "laboratorio", "hipótesis ambiguas")
            self.acciones.append(f"{iid}: hipótesis ambiguas ({', '.join(h['id'] for h, _e in completas)})")
            return
        if len(completas) == 1:
            h, eid_rep = completas[0]
            if h["estado"] != "respaldada":
                try:
                    self.reg.cambiar_hipotesis(h["id"], "respaldada", "laboratorio", "reproducción y control apoyan")
                except sqlite3.IntegrityError:          # r2: la base no encuentra la procedencia exigida
                    self._limite(iid, "procedencia insuficiente para respaldar")
                    return
                self.acciones.append(f"{h['id']} respaldada (simulación)")
            if not (inc["causa_estado"] == "confirmada" and inc["causa_hipotesis"] == h["id"]):
                self.reg.actualizar_diagnostico(iid, "laboratorio", causa=f"{h['texto']} ({h['id']})",
                                                motivo=f"{h['id']} respaldada")
                self.reg.confirmar_causa(iid, "laboratorio", f"{h['id']}: reproducción y control apoyan",
                                         respaldo="simulacion", hipotesis_id=h["id"])
            self._regresion(iid, h, eid_rep)

    def _regresion(self, iid, h, eid_rep):
        if self.reg.con.execute("SELECT 1 FROM regresiones WHERE origen=?", (eid_rep,)).fetchone():
            return
        n = self.reg.con.execute("SELECT count(*) FROM regresiones WHERE incidencia_id=?", (iid,)).fetchone()[0]
        if n >= self.pres.max_regresiones_por_incidencia:
            self._limite(iid, "regresiones por incidencia")
            return
        rid = self.lab.crear_regresion(eid_rep)
        self.acciones.append(f"{rid} creada desde {eid_rep} ({h['id']})")

    # --- seguimiento ----------------------------------------------------------------------------------
    def seguimiento(self, version: int, iids) -> list:
        """Comprueba en `version` las regresiones de hipótesis respaldadas. Devuelve las que fallan."""
        if version not in self.obs:
            return []
        contenidos, falladas = self.obs[version]["contenidos"], []
        for iid in iids:
            for r in self.reg.con.execute("SELECT r.id, r.hipotesis_id FROM regresiones r JOIN hipotesis h "
                                          "ON h.id = r.hipotesis_id WHERE r.incidencia_id=? AND "
                                          "h.estado='respaldada' ORDER BY r.num", (iid,)).fetchall():
                res = self.lab.ejecutar_regresion(r["id"], contenidos)
                if not res["fallo_presente"]:
                    continue
                falladas.append(r["id"])
                ya = self.reg.con.execute("SELECT 1 FROM evidencias WHERE experimento_id=? AND version=? AND "
                                          "incidencia_id=?", (r["id"], version, iid)).fetchone()
                if not ya:
                    self.reg.registrar_evidencia(iid, "simulacion", "fallida",
                                                 f"{r['id']}: el patrón vuelve a aparecer en v{version}", "laboratorio",
                                                 experimento_id=r["id"], hipotesis_id=r["hipotesis_id"],
                                                 version=version, confianza=0.6, limitaciones=LIMITACION)
                    self.acciones.append(f"{r['id']} detecta el patrón en v{version} ({iid})")
                if self.reg.obtener(iid)["estado"] in ("corregida_sin_verificar", "verificada"):
                    self.reg.cambiar_estado(iid, "reabierta", "laboratorio", f"{r['id']} falla en v{version}")
        return falladas

    def resumen(self) -> dict:
        return {"presupuesto": asdict(self.pres), "experimentos_en_esta_ejecucion": self.experimentos_run,
                "segundos_de_investigacion": round(self.t_usado, 3), "acciones": self.acciones[-40:],
                "hipotesis_rechazadas": self.rechazadas[-20:],
                "limites_alcanzados": sorted(f"{i}: {m}" for i, m in self._limites_anotados),
                "nota": "experimentos simulados sobre el texto de las versiones; ninguna ejecución real"}
