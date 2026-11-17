"""V2-C: evaluación ESTRICTA de votos y señales de calidad de la deliberación.

Módulo puro: sin E/S, sin red, sin ejecutar nada. El texto del modelo es NO CONFIABLE.

Reglas de voto (decisiones de GPT-6):
  * finish_reason == "stop"            -> se evalúa el formato.
  * finish_reason == "length"          -> 'truncado'        (nunca concluyente).
  * cualquier otro / ausente           -> 'no_verificable'  (nunca concluyente).
  * formato inválido                   -> 'invalido'.
  Los tres casos no válidos se reintentan UNA vez; si persiste -> abstención obligatoria.
  * Contradicción postura/razón por frases -> ADVERTENCIA (no invalida).

Las señales de calidad (objeciones con evidencia, réplica que responde, falta de información)
son HEURÍSTICAS DETERMINISTAS sobre el formato pedido en los prompts: no prueban que la
propuesta sea correcta ni que una objeción sea cierta.
"""
from __future__ import annotations

import re
import unicodedata

from . import config, sanea

RAZON_AVISO_CHARS = 200
RAZON_MAX_CHARS = 300
POSTURAS_CON_RAZON = ("aprobar_con_cambios", "rechazar")

_VOTO = re.compile(r"VOTO:\s*(aprobar_con_cambios|aprobar|rechazar|abstencion)\s*", re.IGNORECASE)
_RAZON = re.compile(r"RAZON:\s*(.*)", re.IGNORECASE)
_ESPECIALES = re.compile(r"<\|[^|>]{1,40}\|>|</?s>|\[/?INST\]")


def terminacion(finish_reason) -> str:
    """'completa' | 'truncada' | 'no_verificable' a partir de finish_reason."""
    if finish_reason == "stop":
        return "completa"
    if finish_reason == "length":
        return "truncada"
    return "no_verificable"


def _plano(t: str) -> str:
    """minúsculas sin tildes, espacios simples por línea (solo para comparar frases)."""
    t = unicodedata.normalize("NFKD", t if isinstance(t, str) else "")
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return re.sub(r"[^\S\n]+", " ", t)


def evaluar_voto(texto, finish_reason) -> dict:
    """Devuelve {estado, postura, razon, motivo, terminacion, advertencias}.

    estado: 'valido' | 'truncado' | 'no_verificable' | 'invalido'. Solo 'valido' cuenta.
    Si no es válido, postura es None (nunca se infiere una postura de un texto no válido).
    """
    term = terminacion(finish_reason)
    out = {"estado": "invalido", "postura": None, "razon": "", "motivo": None,
           "terminacion": term, "advertencias": []}
    if term == "truncada":
        out.update(estado="truncado", motivo="voto_truncado")
        return out
    if term == "no_verificable":
        out.update(estado="no_verificable", motivo="voto_no_verificable")
        return out
    if not isinstance(texto, str):
        out["motivo"] = "voto_sin_texto"
        return out
    if _ESPECIALES.search(texto):
        out["motivo"] = "voto_tokens_especiales"
        return out
    lineas = [l.strip() for l in texto.replace("\r", "\n").split("\n") if l.strip()]
    if not 1 <= len(lineas) <= 2:
        out["motivo"] = "voto_formato_lineas"
        return out
    m = _VOTO.fullmatch(lineas[0])
    if not m:
        out["motivo"] = "voto_formato_linea_voto"
        return out
    postura = m.group(1).lower()
    razon = ""
    if len(lineas) == 2:
        r = _RAZON.fullmatch(lineas[1])
        if not r:
            out["motivo"] = "voto_formato_linea_razon"
            return out
        razon = sanea.limpiar(r.group(1), RAZON_MAX_CHARS + 1)
    if re.search(r"\bVOTO\s*:", razon, re.IGNORECASE):
        out["motivo"] = "voto_repetido_en_razon"
        return out
    if len(razon) > RAZON_MAX_CHARS:
        out["motivo"] = "razon_demasiado_larga"
        return out
    if postura in POSTURAS_CON_RAZON and not razon:
        out["motivo"] = "razon_obligatoria"
        return out
    adv = []
    if len(razon) > RAZON_AVISO_CHARS:
        adv.append("razon_larga")
    if postura == "abstencion" and not razon:
        adv.append("abstencion_sin_motivo")
    adv += contradicciones(postura, razon)
    out.update(estado="valido", postura=postura, razon=razon, advertencias=adv)
    return out


# --- contradicciones postura/razón (solo ADVERTENCIAS) ------------------------------------
# Frases «fuertes». (?<!no )/(?<!sin ) evitan marcar la forma negada («no hay errores»).
_NEG = r"(?<!no )(?<!sin )(?<!ningun )"
_CONTRA_APROBAR = [
    _NEG + r"\b(es|esta) incorrect[ao]",
    r"\bno (cumple|funciona|es correct[ao]|resuelve)\b",
    _NEG + r"\b(tiene|hay|contiene) (un |algun |varios )?(error|errores|fallo|fallos|bug)\b",
    _NEG + r"\bmodifica la lista original\b",
    r"\bhay que (cambiar|corregir)\b",
    r"\bdeberia rechazarse\b",
]
_CONTRA_RECHAZAR = [
    r"(?<!no )\b(es|esta) correct[ao]\b",
    r"(?<!no )\bcumple (todos|todo|la tarea|los requisitos)\b",
    r"(?<!no )\bfunciona correctamente\b",
    r"\b(no hay|sin) (errores|fallos|problemas)\b",
    r"\bno (tiene|contiene) (errores|fallos)\b",
]
_CONTRA_CAMBIOS = [r"\b(no requiere|no necesita|sin) cambios\b"]


def contradicciones(postura, razon) -> list:
    """Lista de advertencias 'contradiccion:<postura>:<patrón n>'. Nunca invalida."""
    t = _plano(razon)
    if not t:
        return []
    tabla = {"aprobar": _CONTRA_APROBAR, "rechazar": _CONTRA_RECHAZAR,
             "aprobar_con_cambios": _CONTRA_CAMBIOS}.get(postura, [])
    return [f"contradiccion:{postura}:{i}" for i, p in enumerate(tabla) if re.search(p, t)]


# --- señales de calidad sobre el formato pedido en los prompts -----------------------------
_OBJ = re.compile(r"^\s*[-*]?\s*objecion\s*:\s*(.*)$", re.MULTILINE)
_SIN_OBJ = re.compile(r"^\s*[-*]?\s*sin objeciones\b", re.MULTILINE)
_FALTA = re.compile(r"^\s*[-*]?\s*falta\s*:\s*(\S.*)$", re.MULTILINE)
_RESP = re.compile(r"^\s*[-*]?\s*(aceptada|rebatida)\s*:\s*(\S.*)$", re.MULTILINE)
_EVID = re.compile(r"\|\s*evidencia\s*:\s*(\S.{2,})")


def analizar_revision(texto) -> dict:
    t = _plano(texto)
    objeciones = [o for o in _OBJ.findall(t)]
    sin_evidencia = [o for o in objeciones if not _EVID.search(o)]
    return {"objeciones": len(objeciones), "objeciones_sin_evidencia": len(sin_evidencia),
            "sin_objeciones": bool(_SIN_OBJ.search(t)), "falta_info": len(_FALTA.findall(t)),
            "estructurada": bool(objeciones) or bool(_SIN_OBJ.search(t)) or bool(_FALTA.search(t))}


def analizar_replica(texto) -> dict:
    t = _plano(texto)
    r = _RESP.findall(t)
    return {"aceptadas": sum(1 for k, _ in r if k == "aceptada"),
            "rebatidas": sum(1 for k, _ in r if k == "rebatida")}


def senales_calidad(hist: dict, votos_eval: dict) -> list:
    """Advertencias sobre la calidad del debate (no cambian el recuento).

    hist: textos por fase. votos_eval: {agente: evaluación final del voto}.
    """
    adv = []
    rev = analizar_revision(hist.get("revision", ""))
    rep = analizar_replica(hist.get("replica", ""))
    if not rev["estructurada"]:
        adv.append("revision_sin_formato_de_objeciones")
    if rev["objeciones_sin_evidencia"]:
        adv.append(f"objeciones_sin_evidencia:{rev['objeciones_sin_evidencia']}")
    respondidas = rep["aceptadas"] + rep["rebatidas"]
    if rev["objeciones"] and respondidas < rev["objeciones"]:
        adv.append(f"replica_no_responde_todas:{respondidas}/{rev['objeciones']}")
    if rev["falta_info"] or _FALTA.search(_plano(hist.get("analisis", ""))):
        adv.append("informacion_insuficiente_senalada")
    a3 = votos_eval.get("A3") or {}
    if (rev["objeciones"] and a3.get("estado") == "valido" and a3.get("postura") == "aprobar"
            and respondidas < rev["objeciones"]):
        adv.append("A3_aprueba_con_objeciones_sin_resolver")
    posturas = [v.get("postura") for v in votos_eval.values() if v.get("estado") == "valido"]
    if len(posturas) == len(config.AGENTES) and len(set(posturas)) == 1 and posturas[0] == "aprobar" \
            and rev["objeciones"]:
        adv.append("unanimidad_pese_a_objeciones")
    return adv
