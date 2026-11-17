"""V2-D: integridad de respuestas (truncamiento semántico) y unión segura de continuaciones.

Módulo puro: sin E/S ni red. El texto del modelo es NO CONFIABLE; aquí solo se inspecciona.

Terminación de una respuesta:
  * finish_reason 'length'                      -> truncada
  * finish_reason ausente/desconocido            -> no_verificable
  * recortada al guardar (MAX_TURNO_CHARS)       -> truncada
  * bloque de código ``` sin cerrar              -> truncada (aunque finish_reason sea 'stop')
  * propuesta/réplica sin la línea final 'FIN'   -> completa con aviso 'fin_no_marcado' y
                                                    candidata a UNA continuación
"""
from __future__ import annotations

import re

from . import config, votos

_FENCE = re.compile(r"^\s*```")
_FIN = re.compile(r"^\s*\**\s*FIN\s*\.?\s*\**\s*$", re.IGNORECASE)
MIN_SOLAPE = 8
MAX_SOLAPE = 600


def _lineas_no_vacias(texto):
    return [l for l in (texto or "").split("\n") if l.strip()]


def marca_fin_presente(texto) -> bool:
    ls = _lineas_no_vacias(texto)
    return bool(ls) and bool(_FIN.match(ls[-1]))


def quitar_marca_fin(texto: str) -> str:
    """Quita la ÚLTIMA línea si es la marca FIN (es protocolo, no contenido)."""
    if not marca_fin_presente(texto):
        return texto
    ls = texto.rstrip().split("\n")
    while ls and not ls[-1].strip():
        ls.pop()
    ls.pop()
    return "\n".join(ls).rstrip()


def bloque_codigo_abierto(texto) -> bool:
    return sum(1 for l in (texto or "").split("\n") if _FENCE.match(l)) % 2 == 1


def evaluar(fase: str, texto, finish_reason, recortado_al_guardar: bool = False) -> dict:
    """{terminacion, motivos, avisos, sin_fin}. Solo 'completa' permite usar el texto como final."""
    term = votos.terminacion(finish_reason)
    motivos, avisos = [], []
    if term == "truncada":
        motivos.append("finish_length")
    elif term == "no_verificable":
        motivos.append("finish_reason_desconocido")
    if recortado_al_guardar:
        term = "truncada"
        motivos.append("recortado_al_guardar")
    if bloque_codigo_abierto(texto):
        if term == "completa":
            term = "truncada"
        motivos.append("bloque_codigo_abierto")
    sin_fin = fase in config.FASES_CON_MARCA_FIN and not marca_fin_presente(texto)
    if sin_fin and term == "completa":
        avisos.append("fin_no_marcado")
    return {"terminacion": term, "motivos": motivos, "avisos": avisos, "sin_fin": sin_fin}


def necesita_continuacion(fase: str, ev: dict) -> bool:
    """Truncada por longitud o código abierto, o sin marca FIN: se intenta UNA continuación.
    'no_verificable' no se continúa (no sabemos dónde terminó)."""
    if fase not in config.FASES_CON_CONTINUACION:
        return False
    if ev["terminacion"] == "truncada" and "recortado_al_guardar" not in ev["motivos"]:
        return True
    return ev["terminacion"] == "completa" and ev["sin_fin"]


def unir(parcial: str, continuacion) -> dict:
    """Une el texto BRUTO parcial y la continuación sin duplicar.

    - Si la continuación repite el texto previo completo (eco), se quita el eco.
    - Si empieza otra vez desde el principio (reinicio), se RECHAZA (no se mezcla).
    - Se elimina el solape entre el final del parcial y el inicio de la continuación.
    - Si toda la continuación ya estaba en el parcial, se rechaza como duplicada.
    Devuelve {texto, ok, problema, añadido}.
    """
    if not isinstance(continuacion, str):
        return {"texto": parcial, "ok": False, "problema": "continuacion_sin_texto", "añadido": 0}
    c = continuacion
    if parcial and c.startswith(parcial):
        c = c[len(parcial):]
    else:
        # Reinicio: la continuación vuelve a empezar desde el principio (aunque luego diverja).
        cabeza = parcial.strip()[:20]
        if len(parcial.strip()) >= 20 and c.lstrip().startswith(cabeza):
            return {"texto": parcial, "ok": False, "problema": "reinicio", "añadido": 0}
    k_max = min(len(parcial), len(c), MAX_SOLAPE)
    for k in range(k_max, MIN_SOLAPE - 1, -1):
        if parcial.endswith(c[:k]):
            c = c[k:]
            break
    nucleo = c.strip()
    if len(nucleo) >= 20 and nucleo in parcial:
        return {"texto": parcial, "ok": False, "problema": "duplicado", "añadido": 0}
    return {"texto": parcial + c, "ok": True, "problema": None if nucleo else "continuacion_vacia",
            "añadido": len(c)}
