"""Recuento determinista de votos. El código cuenta; el modelo no decide el resultado.

Reglas (provisionales; el punto de las abstenciones queda abierto para GPT-6):
  1. Se ignoran las abstenciones para decidir. Con menos de 2 votos válidos -> sin_consenso.
  2. Reparto 1 aprobar / 1 aprobar_con_cambios / 1 rechazar -> sin_consenso (se
     presentan las posturas al usuario; no hay sorteo).
  3. favor = aprobar + aprobar_con_cambios.  rechazar > favor -> rechazada.
  4. favor == rechazar -> sin_consenso.
  5. favor > rechazar: si hay algún aprobar_con_cambios -> aprobada_con_cambios
     (se conservan los cambios pendientes); si no -> aprobada (plena).

V2-C:
  * `estados` ({agente: 'valido'|'abstencion_forzada'}) es obligatorio desde el orquestador.
    Un voto no 'valido' DEBE tener postura 'abstencion' (si no, ValueError: nunca se cuenta
    un voto truncado o no verificable). Los cambios pendientes salen SOLO de votos válidos.
  * El resultado del CONSENSO (contar) y la FIABILIDAD del procedimiento (fiabilidad) son
    indicadores separados: la fiabilidad no altera el recuento.
"""
from __future__ import annotations

from . import config

AGENTE_AUTOR = "A1"   # A1 redacta la propuesta/réplica


ESTADOS_VOTO = ("valido", "abstencion_forzada")


def contar(votos: dict, estados: dict | None = None) -> dict:
    """votos: {agente: (postura, razon)}. Devuelve un dict serializable.

    estados None equivale a todos 'valido' (compatibilidad con V0-V1/V2-B).
    """
    estados = estados if estados is not None else {ag: "valido" for ag in votos}
    if set(estados) != set(votos):
        raise ValueError("estados y votos no corresponden")
    for ag, (p, _r) in votos.items():
        if ag not in config.AGENTES or p not in config.POSTURAS:
            raise ValueError(f"voto inválido: {ag!r} {p!r}")
        if estados[ag] not in ESTADOS_VOTO:
            raise ValueError(f"estado de voto inválido: {ag!r} {estados[ag]!r}")
        if estados[ag] != "valido" and p != "abstencion":
            raise ValueError(f"un voto no válido no puede contar: {ag!r} {p!r}")
    c = {p: 0 for p in config.POSTURAS}
    for p, _r in votos.values():
        c[p] += 1
    a, cc, r, ab = (c["aprobar"], c["aprobar_con_cambios"], c["rechazar"], c["abstencion"])
    validos = a + cc + r
    favor = a + cc
    if validos < 2:
        res = "sin_consenso"
    elif a >= 1 and cc >= 1 and r >= 1:
        res = "sin_consenso"
    elif r > favor:
        res = "rechazada"
    elif r == favor:
        res = "sin_consenso"
    else:
        res = "aprobada_con_cambios" if cc >= 1 else "aprobada"
    cambios = [f"{ag}: {rz}" for ag, (p, rz) in sorted(votos.items())
               if p == "aprobar_con_cambios" and rz and estados[ag] == "valido"]
    forzadas = sorted(ag for ag in votos if estados[ag] == "abstencion_forzada")
    sesgo = (AGENTE_AUTOR in votos and votos[AGENTE_AUTOR][0] in ("aprobar", "aprobar_con_cambios"))
    return {
        "resultado": res,
        "conteo": c,
        "cambios_pendientes": cambios,
        "sesgo_autoria": bool(sesgo),
        "nota_sesgo": ("A1 votó su propia propuesta" if AGENTE_AUTOR in votos else ""),
        "votos_validos": validos,
        "abstenciones_forzadas": forzadas,
    }


ORDEN_NIVEL = ("normal", "reducida", "no_valida")


def fiabilidad(cuenta: dict, terminaciones: dict, motivos_abstencion: dict,
               advertencias: list, motivos_extra=()) -> dict:
    """Fiabilidad del PROCEDIMIENTO (independiente del resultado del consenso).

    terminaciones: {fase: 'completa'|'truncada'|'no_verificable'} de las fases no-voto.
    motivos_abstencion: {agente: motivo} de las abstenciones FORZADAS.
    Devuelve {nivel, impide_conclusion, propuesta_estado, motivos, advertencias}.

    no_valida  (impide una conclusión válida):
       - réplica (propuesta final) truncada o no verificable;
       - menos de 2 votos válidos por culpa de abstenciones forzadas.
    reducida:  otra fase truncada/no verificable, alguna abstención forzada, o `motivos_extra`
               (p. ej. la propuesta final se recortó para caber en el prompt de un votante).
    Las advertencias (contradicciones, sesgo de autoría, calidad del debate) se informan
    pero no cambian el nivel.
    """
    motivos = []
    rep = terminaciones.get("replica")
    propuesta = "completa" if rep == "completa" else ("incompleta" if rep == "truncada"
                                                      else "no_verificable")
    impide = False
    if propuesta != "completa":
        motivos.append(f"propuesta_final_{propuesta}")
        impide = True
    if cuenta.get("votos_validos", 0) < 2 and motivos_abstencion:
        motivos.append("menos_de_2_votos_validos_por_abstencion_forzada")
        impide = True
    for fase in ("analisis", "propuesta", "revision"):
        t = terminaciones.get(fase)
        if t is not None and t != "completa":
            motivos.append(f"{fase}_{t}")
    for ag, m in sorted(motivos_abstencion.items()):
        motivos.append(f"abstencion_forzada:{ag}:{m}")
    motivos += list(motivos_extra)
    nivel = "no_valida" if impide else ("reducida" if motivos else "normal")
    adv = list(advertencias)
    if cuenta.get("sesgo_autoria"):
        adv.insert(0, "sesgo_autoria: A1 votó a favor de su propia propuesta")
    return {"nivel": nivel, "impide_conclusion": impide, "propuesta_estado": propuesta,
            "motivos": motivos, "advertencias": adv}


def depende_del_autor(votos: dict, estados: dict | None = None) -> bool:
    """True si el voto A FAVOR del autor (A1) es el que decide el resultado: quitándolo
    (como abstención) el recuento cambia. Protección de V2-D frente al sesgo de autoría."""
    estados = estados if estados is not None else {ag: "valido" for ag in votos}
    p = votos.get(AGENTE_AUTOR, ("abstencion", ""))[0]
    if estados.get(AGENTE_AUTOR) != "valido" or p not in ("aprobar", "aprobar_con_cambios"):
        return False
    sin = dict(votos)
    sin[AGENTE_AUTOR] = ("abstencion", "")
    return contar(sin, estados)["resultado"] != contar(votos, estados)["resultado"]
