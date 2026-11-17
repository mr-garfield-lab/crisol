"""V2-E.7-r3: EVIDENCIA VERIFICADA para la auditoría de A3 en tareas «modlab_pz».

En r2, A3 recibía solo conclusión, esperado, obtenido y una línea por herramienta: no veía los pasos ni el inventario
final, y en LAB-003 afirmó que el simulador no había rechazado el consumo imposible. Aquí la evidencia se construye
RELEYENDO DEL DISCO los registros que escribió el coordinador (nunca el texto de A1/A2) y comprobando sus SHA-256:
  herramientas/H<nnn>/registro.json   ->  operación, archivo, estado, huellas de entrada y de resultado
  herramientas/H<nnn>/resultado.json  ->  pasos (ok por paso), inventario final, eventos, todos_ok
  escenario/<archivo>                 ->  acción, objeto y cantidad de cada paso
Cada paso y cada operación se clasifica en una de las cuatro categorías pedidas:
  1 simulada_exitosa · 2 fallo_esperado · 3 fallo_inesperado (laboratorio o escenario) · 4 sin_evidencia
La clasificación es INFORMATIVA para A3: no cambia `auditoria/determinista.json` ni la conclusión del código.
"""
from __future__ import annotations

import hashlib
import json

CATEGORIAS = {"simulada_exitosa": "1. operación simulada exitosa",
              "fallo_esperado": "2. operación simulada fallida de manera esperada",
              "fallo_inesperado": "3. fallo inesperado del laboratorio o del escenario",
              "sin_evidencia": "4. evidencia insuficiente para concluir"}
ADVERTENCIA = "ModLab es una simulación declarativa propia; NO es Project Zomboid ni certifica compatibilidad."
MAX_PASOS = 25


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _leer(lab, *partes):
    p = lab.ruta(*partes)
    return p.read_bytes() if p.is_file() and not p.is_symlink() else None


def construir(lab, tarea: dict, herramientas: list, det: dict) -> dict:
    """{texto (lo que recibe A3), datos (lo mismo, estructurado)} a partir de los registros en disco."""
    esperado = tarea.get("resultado_esperado")
    ops, contradicciones = [], []
    for h in herramientas:
        n = h.get("n")
        op = {"id": f"H{n:03d}" if isinstance(n, int) else "H???", "operacion": h.get("operacion"),
              "archivo": h.get("archivo"), "estado": h.get("estado")}
        bruto = _leer(lab, "herramientas", op["id"], "registro.json")
        reg = json.loads(bruto) if bruto else None
        if reg is None or any(reg.get(k) != h.get(k) for k in ("operacion", "archivo", "estado")):
            op.update(categoria="sin_evidencia", motivo="registro ausente o distinto del de la ejecución")
            contradicciones.append(f"{op['id']}: registro ausente o distinto")
            ops.append(op)
            continue
        if reg["estado"] == "error":
            op.update(categoria="fallo_inesperado", motivo="la herramienta no completó la operación: "
                      + str(reg.get("error"))[:200])
            ops.append(op)
            continue
        if reg["estado"] != "ejecutada":
            op.update(categoria="sin_evidencia", motivo=f"no ejecutada ({reg['estado']})")
            ops.append(op)
            continue
        res_b = _leer(lab, "herramientas", op["id"], "resultado.json")
        ent_b = _leer(lab, "escenario", op["archivo"])
        if res_b is None or _sha(res_b) != reg.get("resultado_sha256") or ent_b is None \
                or _sha(ent_b) != reg.get("entrada_sha256"):
            op.update(categoria="sin_evidencia", motivo="el resultado o la entrada no coinciden con su SHA-256")
            contradicciones.append(f"{op['id']}: huellas que no coinciden")
            ops.append(op)
            continue
        op["evidencia"] = "verificada (SHA-256 de entrada y de resultado)"
        res = json.loads(res_b)
        if op["operacion"] != "simular_escenario":
            op.update(categoria="simulada_exitosa", resumen={k: res.get(k) for k in
                      ("eventos", "llamadas", "patrones_revision_manual", "hallazgos") if k in res})
            ops.append(op)
            continue
        try:
            acciones = json.loads(ent_b.decode("utf-8")).get("acciones") or []
        except (ValueError, AttributeError):
            acciones = []
        pasos = res.get("pasos") or []
        coherente = (len(pasos) == len(acciones) and res.get("todos_ok") == all(p.get("ok") for p in pasos)
                     and reg.get("todos_ok") == res.get("todos_ok"))
        detalle = []
        for i, p in enumerate(pasos):
            a = acciones[i] if i < len(acciones) and isinstance(acciones[i], dict) else {}
            cat = "simulada_exitosa" if p.get("ok") else ("fallo_esperado" if esperado == "fallo_detectado"
                                                         else "fallo_inesperado")
            detalle.append({"paso": p.get("paso"), "accion": a.get("accion", p.get("accion")),
                            "objeto": a.get("objeto"), "cantidad": a.get("cantidad"), "ok": bool(p.get("ok")),
                            "categoria": cat})
        op.update(pasos=detalle, inventario_final=res.get("inventario_final"), eventos=res.get("eventos"),
                  todos_ok=res.get("todos_ok"))
        if not coherente:
            op["categoria"] = "sin_evidencia"
            op["motivo"] = "resultados contradictorios (pasos, todos_ok y registro no concuerdan)"
            contradicciones.append(f"{op['id']}: resultados contradictorios")
        elif any(d["categoria"] == "fallo_inesperado" for d in detalle):
            op["categoria"] = "fallo_inesperado"
        elif any(d["categoria"] == "fallo_esperado" for d in detalle):
            op["categoria"] = "fallo_esperado"
        else:
            op["categoria"] = "simulada_exitosa"
        ops.append(op)
    sims_validas = [o for o in ops if o["operacion"] == "simular_escenario" and o["categoria"] != "sin_evidencia"]
    suficiente = bool(sims_validas) and not contradicciones
    datos = {"objetivo": tarea.get("instrucciones"), "resultado_esperado": esperado,
             "conclusion_del_codigo": det.get("conclusion"), "obtenido_por_el_codigo": det.get("obtenido"),
             "solicitadas": len(herramientas), "ejecutadas": sum(o["estado"] == "ejecutada" for o in ops),
             "operaciones": ops, "contradicciones": contradicciones, "evidencia_suficiente": suficiente,
             "advertencia": ADVERTENCIA}
    return {"texto": _texto(datos), "datos": datos}


def _texto(d: dict) -> str:
    # lo esencial primero: si el contexto (1024) recorta, se pierden los últimos pasos, no el resumen
    L = [f"OBJETIVO DE LA MISIÓN: {d['objetivo']}",
         "ADVERTENCIA: " + d["advertencia"],
         f"RESULTADO_ESPERADO: {d['resultado_esperado']}",
         f"CONCLUSIÓN DEL EVALUADOR DETERMINISTA: {d['conclusion_del_codigo']} (obtenido: {d['obtenido_por_el_codigo']})",
         f"OPERACIONES SOLICITADAS POR A2: {d['solicitadas']} · EJECUTADAS: {d['ejecutadas']}",
         "EVIDENCIA SUFICIENTE: " + ("sí" if d["evidencia_suficiente"] else
                                     "NO (ninguna simulación ejecutada con evidencia verificada y coherente)"),
         "CONTRADICCIONES: " + ("; ".join(d["contradicciones"]) or "ninguna")]
    for o in d["operaciones"]:
        L.append(f"{o['id']} {o['operacion']} {o['archivo']}: {o['estado']} -> {CATEGORIAS[o['categoria']]}"
                 + (f" ({o['motivo']})" if o.get("motivo") else "") + (f"; evidencia {o['evidencia']}" if o.get("evidencia") else ""))
        for p in (o.get("pasos") or [])[:MAX_PASOS]:
            r = "ok" if p["ok"] else "RECHAZADO por el simulador"
            cant = "" if p["cantidad"] is None else f" x{p['cantidad']}"
            L.append(f"  paso {p['paso']}: {p['accion']} {p['objeto']}{cant} -> {r} [{CATEGORIAS[p['categoria']]}]")
        if len(o.get("pasos") or []) > MAX_PASOS:
            L.append(f"  (… {len(o['pasos']) - MAX_PASOS} pasos más en resultado.json)")
        if "inventario_final" in o:
            L.append(f"  inventario final: {json.dumps(o['inventario_final'], ensure_ascii=False)}; "
                     f"eventos: {json.dumps(o.get('eventos'), ensure_ascii=False)}; todos_ok: {o.get('todos_ok')}")
        if o.get("resumen"):
            L.append(f"  resumen: {json.dumps(o['resumen'], ensure_ascii=False)[:300]}")
    return "\n".join(L)
