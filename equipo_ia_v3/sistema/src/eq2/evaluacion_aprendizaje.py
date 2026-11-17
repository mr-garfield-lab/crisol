"""V2-E.6: evaluación PRE/POST del aprendizaje — SIMULADA y determinista.

Qué demuestra: el MECANISMO completo (recordar → actualizar con evidencia probatoria → recuperar con
metadatos → usar → transferir a un caso INÉDITO), comparando con un agente idéntico SIN ese recuerdo y con
una tarea de control no relacionada. Qué NO demuestra: que Qwen aprenda. El «agente» es una política
determinista que solo aplica lecciones VERIFICADAS que recupera; no es el modelo.

Protocolo (cada paso queda en el informe):
  1. pre        tarea inicial con memoria vacía (oráculo oculto, declarativo)
  2. feedback   el oráculo (prueba estática autorizada) registra el fallo; una lección candidata se
                VERIFICA con esa evidencia (no con votos); antes de verificarla, el agente la recupera pero NO
                la aplica
  3. post       la misma tarea inicial
  4. variantes  tareas INÉDITAS de la misma familia: con recuerdo vs agente sin recuerdo
  5. control    tarea no relacionada: el recuerdo no debe cambiar la respuesta
  6. falsas certezas: un voto «seguro» que contradice la lección no se verifica, se marca como
                contradicción y no cambia la respuesta; una lección refutada no se recupera
No hay azar: repetir da el mismo resultado (la variación aleatoria no se presenta como aprendizaje).
"""
from __future__ import annotations

import re

from . import aprendizaje

ETIQUETA = "SIMULADO: política determinista, no Qwen"
EN_SITIO = ("sort", "reverse", "append", "extend", "insert", "pop", "remove", "clear")
TAREAS = {
    "inicial": {"id": "T-ordenar", "funcion": "ordenar", "metodo": "sort", "copia": "sorted(xs)",
                "enunciado": "Escribe ordenar(xs) en Python sin modificar la lista de entrada."},
    "variante_invertir": {"id": "T-invertir", "funcion": "invertir", "metodo": "reverse", "copia": "xs[::-1]",
                          "enunciado": "Escribe invertir(xs) en Python sin modificar la lista de entrada."},
    "variante_desc": {"id": "T-ordenar-desc", "funcion": "ordenar_desc", "metodo": "sort(reverse=True)",
                      "copia": "sorted(xs, reverse=True)",
                      "enunciado": "Escribe ordenar_desc(xs) en Python, de mayor a menor, sin modificar la lista de entrada."},
    "control": {"id": "T-sumar", "funcion": "sumar", "metodo": None, "copia": "sum(xs)",
                "enunciado": "Escribe sumar(xs) en Python que devuelva la suma de los números."},
}
LECCION = ("Lección: los métodos in situ (sort, reverse, append...) modifican la lista de entrada; si la tarea "
           "pide no modificarla, devolver una copia (sorted, xs[::-1]).")
FALSA = "Estoy seguro: sort no modifica la lista de entrada, se puede usar sin problema."


def oraculo(tarea: dict, respuesta: str) -> dict:
    """Oráculo OCULTO y declarativo (nada se ejecuta): si la tarea exige no modificar la entrada, la
    respuesta no puede llamar métodos in situ sobre `xs`; debe definir la función y devolver algo."""
    defin = re.search(rf"def\s+{re.escape(tarea['funcion'])}\s*\(", respuesta) is not None
    devuelve = "return" in respuesta
    muta = [m for m in EN_SITIO if re.search(rf"\bxs\.{m}\(", respuesta)]
    exige = "sin modificar" in tarea["enunciado"]
    ok = defin and devuelve and (not exige or not muta)
    return {"ok": ok, "define_funcion": defin, "devuelve": devuelve, "metodos_in_situ": muta,
            "exige_no_modificar": exige}


def _verificador_oraculo(artefacto, parametros):
    """Verificador registrado (V2-E.6-r2): el oráculo se EJECUTA sobre el artefacto; nadie declara el resultado."""
    clave = parametros.get("tarea")
    if clave not in TAREAS:
        raise ValueError("tarea desconocida para el oráculo")
    o = oraculo(TAREAS[clave], artefacto)
    return o["ok"], f"oráculo {TAREAS[clave]['id']}: ok={o['ok']} in_situ={o['metodos_in_situ']}"


aprendizaje.registrar_verificador("oraculo_no_mutar", "1", _verificador_oraculo)


class AgenteSimulado:
    """Política determinista: si recupera una LECCIÓN VERIFICADA aplicable, devuelve una copia; si no,
    usa el método in situ (el error típico). Nunca aplica recuerdos no verificados."""

    def __init__(self, apr=None):
        self.apr = apr

    def responder(self, tarea: dict) -> dict:
        usados, recuperados = [], []
        if self.apr is not None:
            recuperados = self.apr.recuperar(tarea["enunciado"], n=3, tarea_ref=tarea["id"])
            for m in recuperados:
                if m["estado"] == "verificada_por_prueba" and m["tipo"] == "leccion" and "in situ" in m["texto"] \
                        and "sin modificar" in tarea["enunciado"]:
                    usados.append(m["id"])
        f = tarea["funcion"]
        if tarea["metodo"] is None:
            cuerpo = f"    return {tarea['copia']}"
        elif usados:
            cuerpo = f"    return {tarea['copia']}"
        else:
            cuerpo = f"    xs.{tarea['metodo'] if '(' in tarea['metodo'] else tarea['metodo'] + '()'}\n    return xs"
        return {"respuesta": f"def {f}(xs):\n{cuerpo}\n", "usados": usados,
                "recuperados": [{k: m[k] for k in ("id", "estado", "fuente", "relevancia")} for m in recuperados]}


def evaluar(apr_con: "aprendizaje.AprendizajeAgente", apr_sin: "aprendizaje.AprendizajeAgente", repeticiones=2) -> dict:
    """`apr_con` y `apr_sin`: bases VACÍAS de dos agentes idénticos (la segunda nunca recibe la lección)."""
    con, sin = AgenteSimulado(apr_con), AgenteSimulado(apr_sin)
    pasos = []

    def paso(nombre, agente, clave):
        t = TAREAS[clave]
        r = agente.responder(t)
        o = oraculo(t, r["respuesta"])
        pasos.append({"paso": nombre, "tarea": t["id"], "agente": "con_memoria" if agente is con else "sin_memoria",
                      "ok": o["ok"], "oraculo": o, "usados": r["usados"], "recuperados": r["recuperados"]})
        return o, r

    o_pre, r_pre = paso("1_pre", con, "inicial")
    # 2. feedback: el oráculo es la evidencia (prueba estática autorizada), no un voto
    fallo = apr_con.recordar("hecho", f"El oráculo estático rechazó la respuesta a {TAREAS['inicial']['id']}: "
                             f"usa {o_pre['metodos_in_situ']} y la tarea exige no modificar la entrada.",
                             "prueba_estatica", fuente_ref="oraculo/T-ordenar", tarea_ref="T-ordenar",
                             estado="sin_verificar", ambito="ordenar lista modificar entrada")
    apr_con.probar(fallo["id"], "oraculo_no_mutar", r_pre["respuesta"], {"tarea": "inicial"}, esperado=False,
                   motivo="el oráculo rechaza la respuesta inicial")
    lec = apr_con.recordar("leccion", LECCION, "prueba_estatica", fuente_ref="oraculo/T-ordenar",
                           tarea_ref="T-ordenar", ambito="lista entrada modificar copia sorted reverse in situ")
    antes = apr_con.estado(lec["id"])
    # un voto de acuerdo NO verifica (la base lo impide aunque se intente)
    voto = apr_con.aplicar_evidencia(lec["id"], "voto", "apoya", "A2 y A3 votaron que la lección es correcta",
                                     actor="agente")
    # la lección SIN verificar se recupera (con su estado) pero NO se aplica
    o_sv, r_sv = paso("2_sin_verificar", con, "inicial")
    # V2-E.6-r2 (auditoría, caso A): una «prueba» DECLARADA sin ejecutar nada se rechaza
    try:
        apr_con.aplicar_evidencia(lec["id"], "prueba_estatica", "apoya", "Comprobado por oráculo inexistente")
        declarada_aceptada = True
    except ValueError:
        declarada_aceptada = False
    estado_tras_declarada = apr_con.estado(lec["id"])
    # la corrección candidata se comprueba EJECUTANDO el mismo oráculo (prueba estática registrada)
    apr_con.probar(lec["id"], "oraculo_no_mutar", "def ordenar(xs):\n    xs.sort()\n    return xs\n",
                   {"tarea": "inicial"}, esperado=False, motivo="la versión in situ debe fallar")
    ver = apr_con.probar(lec["id"], "oraculo_no_mutar", "def ordenar(xs):\n    return sorted(xs)\n",
                         {"tarea": "inicial"}, esperado=True, motivo="la versión con copia debe pasar")
    pasos.append({"paso": "2_feedback", "leccion": lec["id"], "estado_antes": antes,
                  "tras_voto": voto["despues"], "tras_prueba_declarada": estado_tras_declarada,
                  "prueba_declarada_aceptada": declarada_aceptada, "tras_prueba": ver["despues"],
                  "evidencia": ver["evidencia"], "ejecucion": ver["ejecucion"]})
    paso("3_post", con, "inicial")
    for clave in ("variante_invertir", "variante_desc"):
        paso("4_variante_con", con, clave)
        paso("4_variante_sin", sin, clave)
    o_ctl_con, _ = paso("5_control_con", con, "control")
    o_ctl_sin, _ = paso("5_control_sin", sin, "control")
    ctl_usados = [p for p in pasos if p["paso"] == "5_control_con"][0]["usados"]
    # 6. falsas certezas
    falsa = apr_con.recordar("hipotesis", FALSA, "voto", confianza="alta", fuente_ref="voto/A1",
                             ambito="ordenar lista modificar entrada sort")
    f_hist = apr_con.recuerdo(falsa["id"])
    try:
        apr_con.transicion(falsa["id"], "verificada_por_prueba", "consenso del equipo")
        voto_verifica = True
    except ValueError:
        voto_verifica = False
    o_falsa, r_falsa = paso("6_falsa_certeza", con, "inicial")
    ref = apr_con.recordar("leccion", "Lección errónea de prueba: para invertir basta xs.reverse() aunque la tarea "
                           "pida no modificar la entrada.", "evaluacion_simulada", ambito="invertir lista entrada")
    apr_con.probar(ref["id"], "oraculo_no_mutar", "def invertir(xs):\n    xs.reverse()\n    return xs\n",
                   {"tarea": "variante_invertir"}, esperado=True, motivo="la lección dice que basta xs.reverse()")
    recuperada = any(m["id"] == ref["id"] for m in apr_con.recuperar(TAREAS["variante_invertir"]["enunciado"], n=5,
                                                                        registrar_uso=False))
    pasos.append({"paso": "6_regresiones", "falsa": falsa["id"], "confianza_guardada": f_hist["confianza"],
                  "estado_falsa": apr_con.estado(falsa["id"]), "contradice": falsa["contradicciones"],
                  "voto_consigue_verificar": voto_verifica, "refutada_recuperada": recuperada})

    def ok(nombre, agente=None, tarea=None):
        return [p["ok"] for p in pasos if p["paso"] == nombre and (tarea is None or p["tarea"] == tarea)]
    variantes_con, variantes_sin = ok("4_variante_con"), ok("4_variante_sin")
    metr = {"pre": o_pre["ok"], "post": ok("3_post")[0],
            "variantes_con_memoria": f"{sum(variantes_con)}/{len(variantes_con)}",
            "variantes_sin_memoria": f"{sum(variantes_sin)}/{len(variantes_sin)}",
            "transferencia": all(variantes_con) and not any(variantes_sin),
            "control_sin_efecto": o_ctl_con["ok"] == o_ctl_sin["ok"] and not ctl_usados,
            "voto_no_verifica": voto["despues"] == antes and not voto_verifica,
            "prueba_declarada_rechazada": not declarada_aceptada and estado_tras_declarada == antes,
            "leccion_verificada_por_prueba": ver["despues"] == "verificada_por_prueba",
            "falsa_certeza_confianza_baja": f_hist["confianza"] == "baja",
            "falsa_certeza_no_cambia_respuesta": o_falsa["ok"] and falsa["id"] not in r_falsa["usados"],
            "contradiccion_detectada": lec["id"] in falsa["contradicciones"],
            "refutada_no_recuperada": not recuperada,
            "no_usa_recuerdos_sin_verificar": (not o_sv["ok"]) and not r_sv["usados"]
                                              and any(m["id"] == lec["id"] for m in r_sv["recuperados"])}
    criterios = ("transferencia", "control_sin_efecto", "voto_no_verifica", "prueba_declarada_rechazada",
                 "leccion_verificada_por_prueba",
                 "falsa_certeza_confianza_baja", "falsa_certeza_no_cambia_respuesta", "contradiccion_detectada",
                 "refutada_no_recuperada", "no_usa_recuerdos_sin_verificar")
    rep = []
    for _ in range(max(1, int(repeticiones)) - 1):      # determinismo: las respuestas no varían
        rep.append([AgenteSimulado(apr_sin).responder(TAREAS[c])["respuesta"] for c in TAREAS])
    base = [AgenteSimulado(apr_sin).responder(TAREAS[c])["respuesta"] for c in TAREAS]
    return {"etiqueta": ETIQUETA, "metricas": metr, "pasos": pasos,
            "superado": (not metr["pre"]) and metr["post"] and all(metr[c] for c in criterios),
            "determinista": all(r == base for r in rep), "repeticiones": max(1, int(repeticiones)),
            "conclusion": ("El mecanismo recupera, usa y transfiere una lección VERIFICADA por una prueba "
                           "estática y no se deja llevar por votos ni recuerdos refutados. Esto NO mide el "
                           "aprendizaje de Qwen.")}
