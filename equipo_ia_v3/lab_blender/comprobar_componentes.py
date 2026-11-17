"""Comprobación SIN cerebro real de la tanda 14 (componentes y biblioteca), en Blender real y con una biblioteca
temporal: fichas de referencia de los tres componentes, montaje del F1 y del kart, un fallo adrede en cada etapa que
solo se arregla si el aviso lo propone, y reutilización de la rueda en el kart.

    py -B -X utf8 lab_blender/comprobar_componentes.py <salida_blender>          (desde equipo_ia_v3/)
"""
from __future__ import annotations

import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import componentes as C  # noqa: E402
import relacional2 as R  # noqa: E402

PZ = lambda n, f, m, padre=None, **k: {"nombre": n, "forma": f, "medidas": m, **({"padre": padre} if padre else {}), **k}
FICHAS = {
    "rueda": {"nombre": "rueda", "para_que": "rueda de F1: neumático, llanta y tuerca", "medidas": [0.44, 0.66, 0.66],
              "piezas": [PZ("Neumatico", "cilindro", [0.38, 0.66, 0.66], eje="x"),
                         PZ("Llanta", "cilindro", [0.40, 0.42, 0.42], "Neumatico", eje="x"),
                         PZ("Tuerca", "cilindro", [0.44, 0.10, 0.10], "Neumatico", eje="x")],
              "relaciones": [["centro", "Neumatico", 0, 0, 0], ["centro", "Llanta", 0, 0, 0], ["centro", "Tuerca", 0, 0, 0]]},
    "aleron_delantero": {"nombre": "aleron_delantero", "para_que": "alerón delantero con placas y soporte",
                         "medidas": [1.66, 0.4, 0.18],
                         "piezas": [PZ("Plano", "caja", [1.6, 0.35, 0.04]), PZ("Placa_I", "caja", [0.03, 0.4, 0.12], "Plano"),
                                    PZ("Placa_D", "caja", [0.03, 0.4, 0.12], "Plano"), PZ("Soporte", "caja", [0.1, 0.1, 0.1], "Plano")],
                         "relaciones": [["centro", "Plano", 0, 0, 0], ["izquierda", "Placa_I", "Plano"],
                                        ["derecha", "Placa_D", "Plano"], ["encima", "Soporte", "Plano"]]},
    "aleron_trasero": {"nombre": "aleron_trasero", "para_que": "alerón trasero con placas y soporte",
                       "medidas": [1.06, 0.45, 0.775],
                       "piezas": [PZ("Plano", "caja", [1.0, 0.3, 0.05]), PZ("Placa_I", "caja", [0.03, 0.45, 0.5], "Plano"),
                                  PZ("Placa_D", "caja", [0.03, 0.45, 0.5], "Plano"), PZ("Soporte", "caja", [0.06, 0.1, 0.5], "Plano")],
                       "relaciones": [["centro", "Plano", 0, 0, 0], ["izquierda", "Placa_I", "Plano"],
                                      ["derecha", "Placa_D", "Plano"], ["debajo", "Soporte", "Plano"]]},
}
W = {"DI": (-0.95, -1.1), "TI": (-0.95, 1.2)}
F1 = {"piezas": [PZ("Chasis", "caja", [0.7, 3.0, 0.35]), PZ("Morro", "cuna", [0.4, 1.0, 0.3], "Chasis"),
                 PZ("Cabina", "caja", [0.5, 0.8, 0.25], "Chasis"), PZ("Motor", "caja", [0.5, 1.0, 0.4], "Chasis"),
                 PZ("Ponton_I", "caja", [0.35, 1.2, 0.3], "Chasis"), PZ("Ponton_D", "caja", [0.35, 1.2, 0.3], "Chasis"),
                 *[{"nombre": f"Rueda_{w}", "componente": "rueda", "padre": "Chasis"} for w in ("DI", "DD", "TI", "TD")],
                 {"nombre": "Aleron_D", "componente": "aleron_delantero", "padre": "Chasis"},
                 {"nombre": "Aleron_T", "componente": "aleron_trasero", "padre": "Chasis"},
                 *[{"nombre": f"Susp_{w}", "forma": "tubo", "diametro": 0.05, "desde": f"Rueda_{w}", "hasta": "Chasis",
                    "padre": "Chasis"} for w in ("DI", "DD", "TI", "TD")]],
      "relaciones": [["centro", "Chasis", 0, 0, 0.35], ["delante", "Morro", "Chasis"], ["encima", "Cabina", "Chasis"],
                     ["mover", "Cabina", 0, 0.2, 0], ["encima", "Motor", "Chasis"], ["mover", "Motor", 0, 1.1, 0],
                     ["izquierda", "Ponton_I", "Chasis"], ["mover", "Ponton_I", 0, 0.3, 0],
                     ["espejo_x", "Ponton_D", "Ponton_I"],
                     *[r for w, (x, y) in W.items() for r in (["x", f"Rueda_{w}", x], ["y", f"Rueda_{w}", y],
                                                               ["en_el_suelo", f"Rueda_{w}"])],
                     ["espejo_x", "Rueda_DD", "Rueda_DI"], ["espejo_x", "Rueda_TD", "Rueda_TI"],
                     ["debajo", "Aleron_D", "Morro"], ["mover", "Aleron_D", 0, -0.3, 0],
                     ["encima", "Aleron_T", "Motor"], ["mover", "Aleron_T", 0, 0.4, 0]]}
KART = {"piezas": [PZ("Bastidor", "caja", [1.2, 2.0, 0.1]),
                   *[{"nombre": f"Rueda_{w}", "componente": "rueda", "padre": "Bastidor"} for w in ("DI", "DD", "TI", "TD")],
                   PZ("Asiento", "caja", [0.5, 0.5, 0.4], "Bastidor"), PZ("Volante", "cilindro", [0.3, 0.04, 0.3], "Bastidor", eje="y"),
                   {"nombre": "Columna", "forma": "tubo", "diametro": 0.04, "desde": "Volante", "hasta": "Bastidor",
                    "padre": "Bastidor"}],
        "relaciones": [["centro", "Bastidor", 0, 0, 0.33], ["izquierda", "Rueda_DI", "Bastidor"], ["y", "Rueda_DI", -0.7],
                       ["espejo_x", "Rueda_DD", "Rueda_DI"], ["izquierda", "Rueda_TI", "Bastidor"], ["y", "Rueda_TI", 0.7],
                       ["espejo_x", "Rueda_TD", "Rueda_TI"], ["encima", "Asiento", "Bastidor"],
                       ["mover", "Asiento", 0, 0.3, 0], ["centro", "Volante", 0, -0.4, 0.75]]}


def falso(msgs, max_tokens):
    u = msgs[-1]["content"]
    reintento = "Resultado:" in u
    m = re.search(r"COMPONENTE «(\w+)»", u)
    if m:
        nombre = m.group(1)
        if "Ya tienes «" in u and not reintento:
            return '```json\n{"decision": "reutilizar"}\n```', 10, "stop"
        ficha = json.loads(json.dumps(FICHAS[nombre]))
        if nombre == "rueda" and not (reintento and "tu ficha no coincide" in u):
            ficha["medidas"] = [0.40, 0.66, 0.66]                 # preregistro mal hecho: la tuerca sobresale
        return f"```json\n{json.dumps({'componente': ficha}, ensure_ascii=False)}\n```", 100, "stop"
    fase = re.search(r'FASE \d+ de \d+: Escribe SOLO \{"(\w+)"', u).group(1)
    d = json.loads(json.dumps(F1 if "Fórmula 1" in u else KART))
    if "Fórmula 1" in u and fase == "relaciones" and not (reintento and '«Rueda_DI» no tiene z' in u):
        d["relaciones"] = [r for r in d["relaciones"] if r[:2] != ["en_el_suelo", "Rueda_DI"]]   # rueda flotando
    return f"```json\n{json.dumps({fase: d[fase]}, ensure_ascii=False)}\n```", 100, "stop"


def _prestamo(salida) -> bool:
    """Tanda 14b: una rueda siempre mal (medidas de pie) → aviso del orden; agotada → el F1 se monta con la prestada."""
    ev, bib = Path(tempfile.mkdtemp(prefix="comp_")), Path(tempfile.mkdtemp(prefix="bib_"))
    C.BIBLIOTECA_DIR = bib

    def torpe(msgs, max_tokens):
        if "COMPONENTE «rueda»" in msgs[-1]["content"]:
            ficha = json.loads(json.dumps(FICHAS["rueda"]))
            ficha["piezas"][0]["medidas"] = [0.66, 0.66, 0.38]
            return f"```json\n{json.dumps({'componente': ficha}, ensure_ascii=False)}\n```", 100, "stop"
        return falso(msgs, max_tokens)
    try:
        C.correr("torpe", ["T15"], ev, salida, torpe)
        filas = R.leer_filas(ev)
        rueda = [f for f in filas if f.get("fase") == "comp:rueda"]
        fin = next(f for f in filas if f.get("tipo") == "final")
        ok1 = len(rueda) == 3 and "en otro orden" in rueda[0]["feedback"]
        ok2 = fin["aprobado"] and fin.get("prestados") == ["rueda"] and not (bib / "torpe" / "rueda_v1.json").exists()
        print(f"[{'PASA' if ok1 else 'FALLA'}] rueda con medidas de pie → el aviso explica el orden")
        print(f"[{'PASA' if ok2 else 'FALLA'}] rueda agotada → el F1 se monta con la PRESTADA "
              f"({fin['cumplidas']}/{fin['total']}, prestados {fin.get('prestados')}) y no entra en su biblioteca")
        return ok1 and ok2
    finally:
        shutil.rmtree(ev, ignore_errors=True)
        shutil.rmtree(bib, ignore_errors=True)


def main() -> int:
    salida = Path(sys.argv[1])
    ev, bib = Path(tempfile.mkdtemp(prefix="comp_")), Path(tempfile.mkdtemp(prefix="bib_"))
    C.BIBLIOTECA_DIR = bib
    bien = True
    try:
        C.correr("falso", list(C.TAREAS_C), ev, salida, falso)
        filas = R.leer_filas(ev)
        for id_ in C.TAREAS_C:
            fin = next(f for f in filas if f["tarea"] == id_ and f.get("tipo") == "final")
            hs = [f for f in filas if f["tarea"] == id_ and f.get("tipo") != "final"]
            ok = fin["aprobado"]
            print(f"[{'PASA' if ok else 'FALLA'}] {id_}: final {fin['cumplidas']}/{fin['total']}, {len(hs)} llamadas: "
                  + " · ".join(f"{f['fase']}:{f.get('decision', '')}{'✓' if f['aprobado'] else '✗'}" for f in hs))
            if not ok:
                print("   ", fin["feedback"][:800])
            bien &= ok
        rueda = [f for f in filas if f["tarea"] == "T15" and f.get("fase") == "comp:rueda"]
        ok = len(rueda) == 2 and "tu ficha no coincide" in rueda[0]["feedback"] and rueda[1].get("guardado") == 1
        print(f"[{'PASA' if ok else 'FALLA'}] preregistro de la rueda mal declarado → avisado → v1 guardada")
        bien &= ok
        susp = [f for f in filas if f["tarea"] == "T15" and f.get("fase") == "relaciones"]
        ok = len(susp) == 2 and '«Rueda_DI» no tiene z' in susp[0]["feedback"]
        print(f"[{'PASA' if ok else 'FALLA'}] el aviso dice qué coordenada le falta a la rueda: {susp[0]['feedback'][-200:]!r}")
        bien &= ok
        kr = [f for f in filas if f["tarea"] == "T16" and f.get("fase") == "comp:rueda"]
        ok = len(kr) == 1 and kr[0].get("decision") == "reutilizar" and kr[0]["aprobado"]
        print(f"[{'PASA' if ok else 'FALLA'}] el kart reutiliza la rueda de su biblioteca en 1 llamada")
        bien &= ok
        archivos = sorted(p.name for p in (bib / "falso").iterdir())
        ok = "rueda_v1.json" in archivos and "aleron_trasero_v1.json" in archivos
        print(f"[{'PASA' if ok else 'FALLA'}] biblioteca: {archivos}")
        bien &= ok
        print(C.informe(ev))
        f1 = next(f for f in filas if f["tarea"] == "T15" and f.get("tipo") == "final")
        (Path(salida) / "ref_F1.py").write_text(f1["script"] or "", encoding="utf-8")
        bien &= _prestamo(salida)
    finally:
        shutil.rmtree(ev, ignore_errors=True)
        shutil.copytree(bib, Path(salida) / "biblioteca_humo", dirs_exist_ok=True)
        shutil.rmtree(bib, ignore_errors=True)
    return 0 if bien else 1


if __name__ == "__main__":
    raise SystemExit(main())
