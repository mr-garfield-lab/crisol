"""V2-E.2: informes de AUDITORÍA del registro de incidencias.

Separa siempre el TIPO de comprobación: análisis estático, simulación y ejecución real. Nunca
afirma que una solución funciona: «verificada» solo existe con una prueba real superada (imposible
en V2-E.2) y el informe lo dice explícitamente.
"""
from __future__ import annotations

import json
import os

from . import VERSION
from . import incidencias as inc_mod
from . import prioridad


def informe(registro: inc_mod.RegistroIncidencias) -> dict:
    todas = registro.listar()
    prio = {x["id"]: x for x in prioridad.puntuar(registro)}
    filas = []
    for i in todas:
        evs = registro.evidencias(i["id"])
        por_tipo = {}
        for e in evs:
            k = f"{e['tipo']}:{e['resultado']}"
            por_tipo[k] = por_tipo.get(k, 0) + 1
        filas.append({"id": i["id"], "titulo": i["titulo"], "estado": i["estado"],
                      "gravedad": i["gravedad"], "causa_estado": i["causa_estado"],
                      "respaldo_causa": inc_mod.respaldo(i),                       # V2-E.3
                      "fase": registro.ficha(i["id"])["fase"],                        # V2-E.4
                      "etiqueta": registro.etiqueta(i["id"]),
                      "hipotesis": {h["id"]: h["estado"] for h in registro.hipotesis(i["id"])},
                      "revisiones_A3": [f"v{r['version']}:{r['resultado']}" for r in registro.revisiones(i["id"])],
                      "asignado": i["asignado"], "reaperturas": registro.reaperturas(i["id"]),
                      "intentos": len(registro.intentos(i["id"])), "evidencias": por_tipo,
                      "prueba_real": any(e["tipo"] == "prueba_real" for e in evs),
                      "prioridad": (prio.get(i["id"]) or {}).get("prioridad"),
                      "bloqueada_por_limite": bool(i["bloqueada_por_limite"]),
                      "entregas_por_agente": {a: n for a, n in registro.con.execute(
                          "SELECT agente, count(*) FROM entregas WHERE incidencia_id=? AND evidencia_num IS NULL "
                          "GROUP BY agente", (i["id"],)).fetchall()}})
    grupo = lambda est: [f["id"] for f in filas if f["estado"] in est]
    exps = [dict(r) for r in registro.con.execute(
        "SELECT id,tipo,estado,conclusion,incidencia_id FROM experimentos ORDER BY num").fetchall()]
    regs = [dict(r) for r in registro.con.execute(
        "SELECT id,incidencia_id,tipo FROM regresiones ORDER BY num").fetchall()]
    verificadas = grupo(("verificada",))
    return {
        "version": VERSION, "generado": registro.ahora(),
        "resumen": {"total": len(filas), "pendientes": len(grupo(inc_mod.PENDIENTES)),
                    "atendidas_sin_verificar": len(grupo(("corregida_sin_verificar",))),
                    "reabiertas": sum(1 for f in filas if f["reaperturas"]),
                    "verificadas": len(verificadas), "descartadas": len(grupo(("descartada",))),
                    "escaladas_al_usuario": sum(1 for f in filas if f["bloqueada_por_limite"])},
        "pendientes": grupo(inc_mod.PENDIENTES),
        "atendidas_sin_verificar": grupo(("corregida_sin_verificar",)),
        "reabiertas": [f["id"] for f in filas if f["reaperturas"]],
        "verificadas": verificadas, "descartadas": grupo(("descartada",)),
        "incidencias": filas, "experimentos": exps, "regresiones": regs,
        "respaldo_de_causas": {r: sum(1 for f in filas if f["respaldo_causa"] == r) for r in inc_mod.RESPALDOS},
        "hipotesis_por_estado": {e: registro.con.execute("SELECT count(*) FROM hipotesis WHERE estado=?",
                                                         (e,)).fetchone()[0] for e in inc_mod.ESTADOS_HIPOTESIS},
        "fases": {fa: sum(1 for f in filas if f["fase"] == fa) for fa in inc_mod.FASES},
        "tipos_de_comprobacion": {
            "analisis_estatico": "ast.parse sobre texto: detecta errores de forma, no de comportamiento",
            "simulacion": "resultados guionizados o reglas declarativas: NO es ejecución",
            "prueba_real": "solo con aislamiento real (Modo B): deshabilitada en esta versión"},
        "declaracion": ("Ninguna solución se ha verificado con pruebas reales." if not verificadas else
                        f"{len(verificadas)} incidencias verificadas con pruebas reales."),
    }


def _markdown(inf) -> str:
    r = inf["resumen"]
    l = [f"# Informe de auditoría ({inf['version']}, {inf['generado']})", "",
         f"**{inf['declaracion']}**", "",
         f"Total {r['total']} · pendientes {r['pendientes']} · atendidas sin verificar "
         f"{r['atendidas_sin_verificar']} · reabiertas {r['reabiertas']} · verificadas {r['verificadas']} · "
         f"descartadas {r['descartadas']} · escaladas {r['escaladas_al_usuario']}", "",
         "| Incidencia | Estado | Grav. | Respaldo de la causa | Prioridad | Evidencias (tipo:resultado) |",
         "|---|---|---|---|---|---|"]
    for f in inf["incidencias"]:
        ev = ", ".join(f"{k}×{v}" for k, v in sorted(f["evidencias"].items())) or "—"
        l.append(f"| {f['id']} {f['titulo'][:50]} | {f['estado']} | {f['gravedad']} | {f['respaldo_causa']} | "
                 f"{f['prioridad']} | {ev} |")
    l += ["", "## Qué se comprobó realmente (V2-E.4)"] + [f"- **{f['id']}**: {f['etiqueta']}" for f in inf["incidencias"]]
    l += ["", "## Tipos de comprobación"] + [f"- **{k}**: {v}" for k, v in inf["tipos_de_comprobacion"].items()]
    l += ["", f"Experimentos: {len(inf['experimentos'])} · casos de regresión: {len(inf['regresiones'])}"]
    return "\n".join(l) + "\n"


def escribir(registro: inc_mod.RegistroIncidencias) -> dict:
    inf = informe(registro)
    sello = inf["generado"].replace(":", "").replace("-", "").replace("+", "_")[:15] + "_" + os.urandom(3).hex()
    pj, _ = registro.lab.escribir_atomico(("incidencias", "informes", f"informe_{sello}.json"),
                                          json.dumps(inf, ensure_ascii=False, indent=2, default=str))
    pm, _ = registro.lab.escribir_atomico(("incidencias", "informes", f"informe_{sello}.md"), _markdown(inf))
    return {"json": pj, "md": pm, "informe": inf}
