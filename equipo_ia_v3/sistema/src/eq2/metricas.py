"""V2-D: métricas comparables entre versiones (tokens y tiempo por llamada, fase y tipo).

Módulo puro. `agregar` resume la lista de llamadas que registra el orquestador; `desde_summary`
normaliza un summary.json de V2-B/V2-C/V2-D (todas guardan backend_informe.informe.peticiones)
para que comparar_metricas.py pueda comparar ejecuciones reales de versiones distintas.
"""
from __future__ import annotations

CAMPOS = ("tokens_prompt", "tokens_gen", "ms_prompt", "ms_gen", "pared_s", "cache_n")


def _num(x):
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def _acumular(dst: dict, fila: dict):
    dst["llamadas"] = dst.get("llamadas", 0) + 1
    for k in CAMPOS:
        v = _num(fila.get(k))
        if v is None:
            dst[k + "_ausentes"] = dst.get(k + "_ausentes", 0) + 1
        else:
            dst[k] = round(dst.get(k, 0) + v, 3)


def agregar(llamadas) -> dict:
    total, por_fase, por_tipo, por_agente = {}, {}, {}, {}
    for f in llamadas or []:
        _acumular(total, f)
        _acumular(por_fase.setdefault(str(f.get("fase")), {}), f)
        _acumular(por_tipo.setdefault(str(f.get("tipo")), {}), f)
        _acumular(por_agente.setdefault(str(f.get("agente")), {}), f)
    return {"total": total, "por_fase": por_fase, "por_tipo": por_tipo, "por_agente": por_agente,
            "votacion": votacion(llamadas)}


def votacion(llamadas) -> dict:
    """V2-E: coste de la votación (para medir lo que ahorran las optimizaciones)."""
    v = [f for f in (llamadas or []) if f.get("fase") == "voto"]
    r = [f for f in v if f.get("tipo") == "reintento_voto"]
    suma = lambda filas, k: round(sum(_num(f.get(k)) or 0 for f in filas), 3)
    return {"llamadas": len(v), "reintentos": len(r), "pared_s": suma(v, "pared_s"),
            "pared_reintentos_s": suma(r, "pared_s"), "tokens_prompt": suma(v, "tokens_prompt"),
            "cache_n": suma(v, "cache_n"), "tokens_gen": suma(v, "tokens_gen")}


def desde_summary(s: dict) -> dict:
    """Totales normalizados a partir de un summary.json (de cualquier versión V2)."""
    inf = ((s.get("backend_informe") or {}).get("informe")) or {}
    pets = inf.get("peticiones") or []
    t = {"version": s.get("version"), "run_id": s.get("run_id"), "llamadas": len(pets),
         "tareas_sha256": s.get("tareas_sha256"), "ctx": (s.get("config") or {}).get("ctx"),
         "carga_s": _num(inf.get("carga_s")), "pared_s": 0.0, "tokens_prompt": 0, "tokens_gen": 0,
         "ms_prompt": 0.0, "ms_gen": 0.0, "ausentes": 0,
         "resultado_global": s.get("resultado_global"), "conclusion_valida": s.get("conclusion_valida")}
    for p in pets:
        m = p.get("metricas") or {}
        vals = {"pared_s": _num(p.get("pared_s")), "tokens_prompt": _num(m.get("prompt_n")),
                "tokens_gen": _num(m.get("predicted_n")), "ms_prompt": _num(m.get("prompt_ms")),
                "ms_gen": _num(m.get("predicted_ms"))}
        for k, v in vals.items():
            if v is None:
                t["ausentes"] += 1
            else:
                t[k] = round(t[k] + v, 3)
    t["por_fase"] = ((s.get("metricas") or {}).get("por_fase"))
    llam = (s.get("metricas") or {}).get("llamadas")
    t["votacion"] = votacion(llam) if isinstance(llam, list) else None
    return t


def comparar(base: dict, nueva: dict, objetivo_pct: float = 30.0) -> dict:
    """Variación porcentual de nueva frente a base. No oculta nada: informa si no es comparable."""
    avisos = []
    if base.get("tareas_sha256") and nueva.get("tareas_sha256") \
            and base["tareas_sha256"] != nueva["tareas_sha256"]:
        avisos.append("las tareas NO son las mismas: la comparación no es equivalente")
    elif not base.get("tareas_sha256") or not nueva.get("tareas_sha256"):
        avisos.append("no se puede verificar que las tareas sean equivalentes (falta tareas_sha256)")
    if base.get("ausentes") or nueva.get("ausentes"):
        avisos.append("faltan medidas en alguna petición: los totales son parciales")
    var = {}
    for k in ("pared_s", "tokens_prompt", "tokens_gen", "ms_prompt", "ms_gen", "llamadas"):
        b, n = base.get(k), nueva.get(k)
        var[k] = (round(100.0 * (n - b) / b, 1) if isinstance(b, (int, float)) and b
                  and isinstance(n, (int, float)) else None)
    p = var.get("pared_s")
    return {"variacion_pct": var, "objetivo_pct": objetivo_pct,
            "dentro_del_objetivo": None if p is None else p <= objetivo_pct, "avisos": avisos}
