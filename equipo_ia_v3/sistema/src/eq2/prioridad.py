"""V2-E.2: análisis de causa raíz, prioridad EXPLICABLE y asignación de tareas a A1/A2/A3.

Prioridad (cada componente se devuelve para auditarla):
  base     = 2·gravedad + 1.5·impacto
  causal   = 6 · confianza · Σ_{d alcanzable por causa/bloquea} certeza(d) · (gravedad_d + impacto_d) / 10
             (certeza de un camino = la menor de sus aristas: confirmada 1.0, hipótesis 0.5)
             -> se priorizan las RAÍCES que causan o bloquean otros problemas
  efecto   = −3 · certeza si otra incidencia PENDIENTE la causa (corregir la causa puede resolverla)
  bloqueo  = −4 si la bloquea otra incidencia pendiente (se atiende después de su bloqueante)
  reapert. = +2 por cada reapertura (máx. 3)
  dific.   = −0.3·dificultad (desempate leve: NO se premia lo difícil)
El planificador respeta las dependencias, limita los intentos y evita ciclos:
  * sin causa (o tras un rediagnóstico)  -> A2 diagnostica
  * causa confirmada                    -> A1 corrige
  * V2-E.3: hipótesis vigente de A2      -> A1 «corregir_con_hipotesis» (marcada como NO confirmada)
  * corregida_sin_verificar             -> A3 revisa; la verificación exige prueba REAL (pendiente)
  * 2 intentos sin efecto desde el último rediagnóstico
                                        -> reasignar a A2 (rediagnóstico; la causa vuelve a hipótesis)
  * escalar al usuario (bloqueada_por_limite; no más tareas) si se alcanza cualquiera de:
      MAX_INTENTOS intentos · MAX_TAREAS_POR_INCIDENCIA tareas · más rediagnósticos que MAX_REDIAGNOSTICOS
Los contadores salen del HISTORIAL (solo anexar) y se reinician solo cuando el usuario desbloquea.
Así ninguna incidencia puede circular indefinidamente entre agentes.
"""
from __future__ import annotations

from . import incidencias as inc_mod

CERTEZA = {"confirmada": 1.0, "hipotesis": 0.5}
MAX_INTENTOS = 3
INTENTOS_PARA_REASIGNAR = 2
MAX_TAREAS_RONDA = 6
MAX_REDIAGNOSTICOS = 1
MAX_TAREAS_POR_INCIDENCIA = 8


def _grafo(deps):
    sal = {}
    for d in deps:
        if d["tipo"] in ("causa", "bloquea"):
            sal.setdefault(d["origen"], []).append((d["destino"], d["certeza"], d["tipo"]))
    return sal


def _alcance(grafo, origen):
    """{destino: certeza efectiva} alcanzables (la certeza de un camino es la menor de sus aristas)."""
    mejor, pila = {}, [(origen, 1.0)]
    while pila:
        x, c = pila.pop()
        for d, cert, _t in grafo.get(x, []):
            cc = min(c, CERTEZA[cert])
            if cc > mejor.get(d, 0):
                mejor[d] = cc
                pila.append((d, cc))
    return mejor


def puntuar(registro: inc_mod.RegistroIncidencias) -> list:
    """Lista de {id, prioridad, componentes, ...} de las incidencias PENDIENTES, ordenada."""
    todas = {i["id"]: i for i in registro.listar()}
    pend = {k: v for k, v in todas.items() if v["estado"] in inc_mod.PENDIENTES}
    deps = registro.dependencias()
    g = _grafo(deps)
    bloqueada = {d["destino"] for d in deps if d["tipo"] == "bloquea" and d["origen"] in pend}
    causada = {}
    for d in deps:
        if d["tipo"] == "causa" and d["origen"] in pend:
            causada[d["destino"]] = max(causada.get(d["destino"], 0), CERTEZA[d["certeza"]])
    out = []
    for iid, i in pend.items():
        alc = _alcance(g, iid)
        causal = 6.0 * i["confianza"] * sum(c * (todas[d]["gravedad"] + todas[d]["impacto"]) / 10.0
                                            for d, c in alc.items() if d in pend)
        comp = {"base": 2 * i["gravedad"] + 1.5 * i["impacto"], "causal": round(causal, 3),
                "efecto": -3.0 * causada.get(iid, 0),
                "bloqueo": -4.0 if iid in bloqueada else 0.0,
                "reaperturas": 2.0 * min(3, registro.reaperturas(iid)),
                "dificultad": -0.3 * i["dificultad"]}
        out.append({"id": iid, "prioridad": round(sum(comp.values()), 3), "componentes": comp,
                    "afecta_a": sorted(d for d in alc if d in pend), "bloqueada": iid in bloqueada,
                    "es_efecto_de_pendiente": iid in causada,
                    "causa_estado": i["causa_estado"], "estado": i["estado"], "gravedad": i["gravedad"]})
    out.sort(key=lambda x: (-x["prioridad"], x["id"]))
    return out


def contadores(registro: inc_mod.RegistroIncidencias, iid: str) -> dict:
    """Intentos, tareas y rediagnósticos desde el último desbloqueo del usuario (del historial)."""
    c = {"intentos": 0, "sin_efecto_desde_rediagnostico": 0, "rediagnosticos": 0, "tareas": 0,
         "diagnostico_vigente": False}
    for h in registro.historial(iid):
        if h["campo"] == "bloqueada_por_limite" and h["despues"] == "0":
            c = dict.fromkeys(c, 0)
            c["diagnostico_vigente"] = False
        elif h["campo"] == "causa":
            c["diagnostico_vigente"] = True
        elif h["campo"] == "causa_retirada":                 # V2-E.4: hipótesis refutada
            c["diagnostico_vigente"] = False
        elif h["campo"] == "intento":
            c["intentos"] += 1
            if (h["despues"] or "").split(":")[-1] in ("sin_efecto", "empeora"):
                c["sin_efecto_desde_rediagnostico"] += 1
        elif h["campo"] == "rediagnostico":
            c["rediagnosticos"] += 1
            c["sin_efecto_desde_rediagnostico"] = 0
            c["diagnostico_vigente"] = False
        elif h["campo"] == "tarea":
            c["tareas"] += 1
    return c


def _motivo_escalada(c) -> str | None:
    if c["intentos"] >= MAX_INTENTOS:
        return f"{c['intentos']} intentos sin verificar"
    if c["tareas"] >= MAX_TAREAS_POR_INCIDENCIA:
        return f"{c['tareas']} tareas sin resolverla"
    if c["sin_efecto_desde_rediagnostico"] >= INTENTOS_PARA_REASIGNAR and c["rediagnosticos"] >= MAX_REDIAGNOSTICOS:
        return "sigue sin efecto tras rediagnosticar"
    return None


def recalcular(registro: inc_mod.RegistroIncidencias, motivo: str) -> list:
    """Guarda la prioridad en la base y anota el recálculo (cuándo y por qué)."""
    p = puntuar(registro)
    with registro.con:
        for x in p:
            registro.con.execute("UPDATE incidencias SET prioridad=? WHERE id=?", (x["prioridad"], x["id"]))
        registro.con.execute("INSERT INTO recalculos(ts,motivo,n) VALUES(?,?,?)",
                             (registro.ahora(), motivo[:200], len(p)))
    return p


def planificar(registro: inc_mod.RegistroIncidencias, max_tareas: int = MAX_TAREAS_RONDA,
               aplicar: bool = True, ambito=None) -> dict:
    """Tareas de la siguiente ronda, por prioridad y sin violar dependencias ni límites.
    Con aplicar=False es una VISTA PREVIA: no escribe nada en la base (ni asigna, ni escala).
    V2-E.3: `ambito` (conjunto de IDs) limita la ronda a esas incidencias (p. ej. las de una ejecución
    del motor); las demás no reciben tareas ni consumen sus límites."""
    orden = recalcular(registro, "planificar") if aplicar else puntuar(registro)
    if ambito is not None:
        ambito = set(ambito)
        orden = [x for x in orden if x["id"] in ambito]
    tope = max(1, min(int(max_tareas), MAX_TAREAS_RONDA))
    tareas, escaladas, esperando = [], [], []
    for x in orden:
        if len(tareas) >= tope:
            break
        inc = registro.obtener(x["id"])
        if inc["bloqueada_por_limite"]:
            continue
        c = contadores(registro, x["id"])
        motivo_esc = _motivo_escalada(c)
        if motivo_esc:
            if aplicar:
                registro.marcar_bloqueo_por_limite(x["id"], "motor", motivo_esc)
                registro.asignar(x["id"], "usuario", "motor", "límite alcanzado: decide el usuario")
            escaladas.append(x["id"])
            continue
        if x["bloqueada"]:
            esperando.append(x["id"])
            continue
        if c["sin_efecto_desde_rediagnostico"] >= INTENTOS_PARA_REASIGNAR:
            accion, agente, motivo = "rediagnosticar", "A2", "reasignada tras intentos sin efecto"
            if aplicar:
                registro.rediagnosticar(x["id"], "motor", f"{c['sin_efecto_desde_rediagnostico']} intentos sin efecto")
        elif inc["causa_estado"] == "confirmada":
            accion, agente, motivo = "corregir", "A1", "causa confirmada"
        elif inc["causa"] and c["diagnostico_vigente"]:
            accion, agente, motivo = ("corregir_con_hipotesis", "A1",
                                      "hipótesis de A2 sin confirmar: corregir y comprobar")
        else:
            accion, agente, motivo = "diagnosticar", "A2", "causa sin confirmar (hipótesis)"
        if aplicar:
            if inc["asignado"] != agente:
                registro.asignar(x["id"], agente, "motor", motivo)
            registro.anotar_tarea(x["id"], agente, accion)
        tareas.append({"incidencia": x["id"], "agente": agente, "accion": accion, "motivo": motivo,
                       "prioridad": x["prioridad"], "componentes": x["componentes"], "contadores": c})
    for i in registro.listar(("corregida_sin_verificar",)):
        if ambito is not None and i["id"] not in ambito:
            continue
        if len(tareas) < MAX_TAREAS_RONDA:
            tareas.append({"incidencia": i["id"], "agente": "A3", "accion": "revisar",
                           "motivo": "corregida solo según simulación/estático; falta prueba real",
                           "prioridad": None, "componentes": None, "contadores": None})
    return {"tareas": tareas, "escaladas_al_usuario": escaladas, "esperando_bloqueante": esperando,
            "orden": [x["id"] for x in orden], "aplicado": aplicar}
