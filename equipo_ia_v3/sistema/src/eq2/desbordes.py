"""Detección de desbordamientos de contexto a partir de las medidas REALES del servidor.

Función pura: no escribe nada, no abre archivos, no usa red. Nunca oculta un hallazgo: todo lo
detectado se devuelve y se imprime. No cambia ningún límite (el contexto sigue en config.CTX).
"""
from __future__ import annotations

import re

from . import config

_INDICIO_LOG = re.compile(r"exceed|context|truncat|too (long|large)|n_ctx|shift", re.IGNORECASE)


def _int(x):
    return x if isinstance(x, int) and not isinstance(x, bool) else None


def analizar(resumen: dict, ctx: int | None = None) -> dict:
    """Devuelve {'hallazgos': [...], 'hay_desbordamiento': bool, 'calls': [...]}.

    Tipos de hallazgo (gravedad):
      desborde_efectivo    (grave)  prompt real + tokens generados > ctx
      riesgo_desborde      (aviso)  prompt real + max_tokens pedido > ctx (pudo no ocurrir)
      corte_por_max_tokens (aviso)  finish_reason == 'length'
      subestimacion_tokens (aviso)  prompt real > estimación del orquestador
      indicio_en_log       (aviso)  el log del servidor menciona contexto/truncado
      medida_ausente       (aviso)  no hay prompt_tokens reales: no se puede descartar desborde
    """
    ctx = config.CTX if ctx is None else ctx
    inf = ((resumen.get("backend_informe") or {}).get("informe")) or {}
    peticiones = inf.get("peticiones") or []
    calib = list(resumen.get("calibracion_tokens") or [])
    hallazgos, filas = [], []
    for p in peticiones:
        n = p.get("n")
        real = _int(p.get("tokens_prompt_real"))
        gen = _int(p.get("tokens_generados"))
        mx = _int(p.get("max_tokens"))
        est = None
        if real is not None and calib:
            est = _int(calib.pop(0).get("tokens_est"))
        filas.append({"n": n, "tokens_est": est, "tokens_real": real, "max_tokens": mx,
                      "generados": gen, "finish_reason": p.get("finish_reason"),
                      "suma_real_mas_gen": (real + gen) if None not in (real, gen) else None})
        if p.get("fallo") is None and real is None:
            hallazgos.append({"n": n, "tipo": "medida_ausente", "gravedad": "aviso"})
        if real is not None and gen is not None and real + gen > ctx:
            hallazgos.append({"n": n, "tipo": "desborde_efectivo", "gravedad": "grave",
                              "detalle": f"{real}+{gen} > {ctx}"})
        if real is not None and mx is not None and real + mx > ctx:
            hallazgos.append({"n": n, "tipo": "riesgo_desborde", "gravedad": "aviso",
                              "detalle": f"{real}+{mx} > {ctx}"})
        if p.get("finish_reason") == "length":
            hallazgos.append({"n": n, "tipo": "corte_por_max_tokens", "gravedad": "aviso"})
        if est is not None and real is not None and real > est:
            hallazgos.append({"n": n, "tipo": "subestimacion_tokens", "gravedad": "aviso",
                              "detalle": f"real {real} > estimado {est}"})
        texto_log = " ".join(str(x) for x in (p.get("log_errores") or [])) \
            if isinstance(p.get("log_errores"), list) else str(p.get("log_errores") or "")
        if texto_log and _INDICIO_LOG.search(texto_log + " " + str(p.get("cuerpo_inicio") or "")):
            hallazgos.append({"n": n, "tipo": "indicio_en_log", "gravedad": "aviso",
                              "detalle": texto_log[:200]})
        elif p.get("cuerpo_inicio") and _INDICIO_LOG.search(str(p["cuerpo_inicio"])):
            hallazgos.append({"n": n, "tipo": "indicio_en_log", "gravedad": "aviso",
                              "detalle": str(p["cuerpo_inicio"])[:200]})
    return {"ctx": ctx, "hallazgos": hallazgos,
            "hay_desbordamiento": any(h["gravedad"] == "grave" for h in hallazgos),
            "llamadas": filas}
