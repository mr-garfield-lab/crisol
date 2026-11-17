"""V2-E.5-r2: informe que COMPARA la clasificación automática de críticas con la corrección conocida.

Módulo puro y determinista (sin E/S, sin modelo, sin ejecutar código). Entrada: casos con el
formato de `corpus_criticas.CASOS`. Salida: veredicto por objeción y por deliberación, más un
resumen con recuentos. Sirve para MEDIR el clasificador, no para justificarlo: los casos en los que
falla (una cita real en una crítica falsa, un consenso erróneo sin objeciones) se muestran tal cual.
"""
from __future__ import annotations

from . import config, criticas

POSIBLE_FALSA = ("cita_no_encontrada", "linea_inexistente")
SIN_CONFIRMAR = ("sin_evidencia", "no_verificable")

VEREDICTOS_OBJECION = {
    "acierto_fundamentada": "crítica correcta y su cita existe",
    "acierto_falsa_detectada": "crítica falsa marcada como posible crítica falsa",
    "falsa_no_detectada": "crítica FALSA con cita existente: la cita no demuestra la crítica (límite)",
    "verdadera_marcada_falsa": "crítica CORRECTA marcada como posible falsa (p. ej. cita parafraseada)",
    "verdadera_sin_confirmar": "crítica correcta sin evidencia comprobable: queda como incertidumbre",
    "falsa_sin_confirmar": "crítica falsa sin evidencia comprobable: queda como incertidumbre",
    "sin_verdad_conocida": "no hay corrección conocida para esta objeción",
}
VEREDICTOS_DELIBERACION = {
    "alerta_justificada": "la solución final es incorrecta y el sistema avisó",
    "incorrecta_sin_alerta": "la solución final es INCORRECTA y no hubo aviso (consenso erróneo no detectado)",
    "falsa_alarma": "la solución final es correcta pero el sistema avisó",
    "correcta_sin_alerta": "la solución final es correcta y no hubo aviso",
}


def _votos(posturas: dict) -> dict:
    return {ag: {"estado": "valido", "postura": p} for ag, p in (posturas or {}).items()}


def _veredicto_objecion(estado: str, verdad) -> str:
    if verdad is None:
        return "sin_verdad_conocida"
    if estado == "fundamentada":
        return "acierto_fundamentada" if verdad else "falsa_no_detectada"
    if estado in POSIBLE_FALSA:
        return "verdadera_marcada_falsa" if verdad else "acierto_falsa_detectada"
    return "verdadera_sin_confirmar" if verdad else "falsa_sin_confirmar"


def evaluar_caso(caso: dict) -> dict:
    ev = criticas.evaluar_deliberacion({"propuesta": caso["propuesta"], "revision": caso["revision"],
                                        "replica": caso["replica"]}, _votos(caso["votos"]), caso["enunciado"])
    verdad = caso["verdad"]
    objs = []
    for i, o in enumerate(ev["objeciones"]):
        v = verdad["objeciones"][i] if i < len(verdad["objeciones"]) else None
        objs.append({"n": o["n"], "estado": o["estado"], "resolucion": o["resolucion"], "verdad": v,
                     "veredicto": _veredicto_objecion(o["estado"], v)})
    alerta = bool(ev["contradicciones"] or ev["problemas_no_resueltos"])
    ok = verdad["solucion_final_correcta"]
    delib = ("alerta_justificada" if alerta and not ok else "incorrecta_sin_alerta" if not ok else
             "falsa_alarma" if alerta else "correcta_sin_alerta")
    return {"id": caso["id"], "categoria": caso["categoria"], "descripcion": caso["descripcion"],
            "formato_revision": ev["formato_revision"],
            "objeciones_esperadas": len(verdad["objeciones"]), "objeciones_extraidas": len(ev["objeciones"]),
            "extraccion_correcta": len(ev["objeciones"]) == len(verdad["objeciones"]),
            "objeciones_implicitas_no_extraidas": verdad["objeciones_implicitas"],
            "objeciones": objs, "contradicciones": ev["contradicciones"],
            "contradiccion_real": verdad["contradiccion_real"],
            "contradiccion_detectada": bool(ev["contradicciones"]),
            "problemas_no_resueltos": ev["problemas_no_resueltos"], "incertidumbre": ev["incertidumbre"],
            "alerta": alerta, "solucion_final_correcta": ok, "veredicto_deliberacion": delib}


MAX_CASOS_EXTERNOS = 200
_POSTURAS = config.POSTURAS


def validar_casos(casos) -> list:
    """Valida casos etiquetados por el usuario (p. ej. revisiones REALES de Qwen etiquetadas a mano).
    Mismo formato que corpus_criticas.CASOS. Lanza ValueError con el primer problema."""
    if not isinstance(casos, list) or not 1 <= len(casos) <= MAX_CASOS_EXTERNOS:
        raise ValueError(f"se espera una lista de 1 a {MAX_CASOS_EXTERNOS} casos")
    out = []
    for i, c in enumerate(casos):
        if not isinstance(c, dict):
            raise ValueError(f"caso {i}: no es un objeto")
        for k in ("id", "categoria", "descripcion", "enunciado", "propuesta", "revision", "replica"):
            if not isinstance(c.get(k), str) or len(c[k]) > 20000:
                raise ValueError(f"caso {i}: «{k}» debe ser texto (máx. 20000)")
        v, votos = c.get("verdad"), c.get("votos")
        if not isinstance(votos, dict) or any(a not in ("A1", "A2", "A3") or p not in _POSTURAS
                                              for a, p in votos.items()):
            raise ValueError(f"caso {i}: votos inválidos")
        if not isinstance(v, dict) or not isinstance(v.get("objeciones"), list) or any(
                x not in (True, False, None) for x in v["objeciones"]):
            raise ValueError(f"caso {i}: verdad.objeciones debe ser una lista de true/false/null")
        if not isinstance(v.get("solucion_final_correcta"), bool) or not isinstance(v.get("contradiccion_real", False), bool):
            raise ValueError(f"caso {i}: verdad.solucion_final_correcta y contradiccion_real son booleanos")
        n = v.get("objeciones_implicitas", 0)
        if not isinstance(n, int) or isinstance(n, bool) or not 0 <= n <= 50:
            raise ValueError(f"caso {i}: verdad.objeciones_implicitas fuera de rango")
        out.append({**c, "verdad": {"objeciones": list(v["objeciones"]), "objeciones_implicitas": n,
                                    "solucion_final_correcta": v["solucion_final_correcta"],
                                    "contradiccion_real": v.get("contradiccion_real", False)}})
    return out


def informe(casos) -> dict:
    filas = [evaluar_caso(c) for c in casos]
    v_obj = {k: 0 for k in VEREDICTOS_OBJECION}
    for f in filas:
        for o in f["objeciones"]:
            v_obj[o["veredicto"]] += 1
    v_del = {k: sum(1 for f in filas if f["veredicto_deliberacion"] == k) for k in VEREDICTOS_DELIBERACION}
    contr = {"reales_detectadas": sum(1 for f in filas if f["contradiccion_real"] and f["contradiccion_detectada"]),
             "reales_no_detectadas": sum(1 for f in filas if f["contradiccion_real"] and not f["contradiccion_detectada"]),
             "detectadas_sin_contradiccion_real": sum(1 for f in filas if f["contradiccion_detectada"]
                                                     and not f["contradiccion_real"])}
    return {"casos": filas,
            "resumen": {"casos": len(filas), "objeciones": v_obj, "deliberaciones": v_del, "contradicciones": contr,
                        "extraccion_incorrecta": [f["id"] for f in filas if not f["extraccion_correcta"]],
                        "objeciones_implicitas_no_extraidas": sum(f["objeciones_implicitas_no_extraidas"]
                                                                  for f in filas),
                        "formato_no_reconocido_senalado": [f["id"] for f in filas
                                                           if "revision:formato_no_reconocido" in f["incertidumbre"]]},
            "leyenda": {"objeciones": VEREDICTOS_OBJECION, "deliberaciones": VEREDICTOS_DELIBERACION},
            "nota": ("Corpus escrito a mano (no son salidas reales de Qwen). Una cita existente no demuestra "
                     "que una crítica sea correcta y el consenso no demuestra que una solución funcione: el "
                     "clasificador solo comprueba referencias en el texto.")}


def texto_informe(inf: dict) -> str:
    out = ["INFORME DE CRÍTICAS: clasificación automática frente a la corrección conocida", inf["nota"], ""]
    for f in inf["casos"]:
        objs = ", ".join(f"#{o['n']} {o['estado']} (verdad={o['verdad']}) → {o['veredicto']}"
                         for o in f["objeciones"]) or "ninguna"
        out.append(f"{f['id']} [{f['categoria']}] {f['descripcion']}")
        out.append(f"    formato={f['formato_revision']} objeciones={f['objeciones_extraidas']}/"
                   f"{f['objeciones_esperadas']} (+{f['objeciones_implicitas_no_extraidas']} implícitas): {objs}")
        out.append(f"    contradicción real={f['contradiccion_real']} detectada={f['contradiccion_detectada']} "
                   f"| solución correcta={f['solucion_final_correcta']} alerta={f['alerta']} "
                   f"→ {f['veredicto_deliberacion']}")
    r = inf["resumen"]
    out += ["", "RESUMEN", f"  casos: {r['casos']}", f"  objeciones: {r['objeciones']}",
            f"  deliberaciones: {r['deliberaciones']}", f"  contradicciones: {r['contradicciones']}",
            f"  extracción incorrecta: {r['extraccion_incorrecta']}",
            f"  críticas implícitas no extraídas: {r['objeciones_implicitas_no_extraidas']}",
            f"  formato no reconocido señalado como incertidumbre: {r['formato_no_reconocido_senalado']}"]
    return "\n".join(out)
