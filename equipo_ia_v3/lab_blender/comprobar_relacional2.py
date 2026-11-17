"""Comprobación SIN cerebro real de la tanda 13 (relacional v2): resolvedor sin Blender, JSON de referencia de las
cuatro tareas en Blender real y cerebros falsos (de una vez y por fases) que fallan adrede y se arreglan solo si el
aviso propone el arreglo.

    py -B -X utf8 lab_blender/comprobar_relacional2.py <salida_blender>          (desde equipo_ia_v3/)
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
import relacional2 as R  # noqa: E402

PZ = lambda n, f, m, padre=None, eje=None: {k: v for k, v in (("nombre", n), ("forma", f), ("medidas", m),
                                                              ("padre", padre), ("eje", eje)) if v is not None}
ROBOT_P = [PZ("Torso", "caja", [1.0, 0.6, 1.2]), PZ("Cabeza", "caja", [0.5, 0.5, 0.5], "Torso"),
           PZ("Pierna_I", "caja", [0.3, 0.3, 1.4], "Torso"), PZ("Pierna_D", "caja", [0.3, 0.3, 1.4], "Torso"),
           PZ("Brazo_I", "caja", [0.25, 0.25, 1.0], "Torso"), PZ("Brazo_D", "caja", [0.25, 0.25, 1.0], "Torso")]
ROBOT_R = [["centro", "Torso", 0, 0, 2.0], ["encima", "Cabeza", "Torso"], ["debajo", "Pierna_I", "Torso"],
           ["x", "Pierna_I", -0.3], ["espejo_x", "Pierna_D", "Pierna_I"], ["izquierda", "Brazo_I", "Torso"],
           ["espejo_x", "Brazo_D", "Brazo_I"]]
AVANZA = {"objeto": "Torso", "desplazamiento": [0, -4, 0], "desde": 1, "hasta": 48}
ONDA = lambda a: [[1, 0], [12, a], [24, 0], [36, -a], [48, 0]]
REF = {
    "T05": {"piezas": ROBOT_P, "relaciones": ROBOT_R},
    "T08": {"piezas": ROBOT_P, "relaciones": ROBOT_R, "animacion": AVANZA},
    "T13": {"piezas": ROBOT_P, "relaciones": ROBOT_R,
            "articulaciones": [{"pieza": p, "punto": "arriba"} for p in R.EXTREMIDADES],
            "animacion": {**AVANZA, "giros": [{"pieza": "Pierna_I", "eje": "x", "claves": ONDA(30)},
                                              {"pieza": "Pierna_D", "eje": "x", "claves": ONDA(-30)},
                                              {"pieza": "Brazo_I", "eje": "x", "claves": ONDA(-20)},
                                              {"pieza": "Brazo_D", "eje": "x", "claves": ONDA(20)}]}},
    "T14": {"piezas": [PZ("Torso", "caja", [1.0, 0.6, 1.2]), PZ("Cabeza", "caja", [0.5, 0.5, 0.5], "Torso"),
                       PZ("Ojo_I", "esfera", [0.12] * 3, "Cabeza"), PZ("Ojo_D", "esfera", [0.12] * 3, "Cabeza"),
                       PZ("Antena", "cilindro", [0.06, 0.06, 0.3], "Cabeza"), PZ("Punta", "esfera", [0.12] * 3, "Antena"),
                       PZ("Brazo_I", "cilindro", [0.25, 0.25, 1.0], "Torso"),
                       PZ("Brazo_D", "cilindro", [0.25, 0.25, 1.0], "Torso"),
                       PZ("Mano_I", "esfera", [0.25] * 3, "Brazo_I"), PZ("Mano_D", "esfera", [0.25] * 3, "Brazo_D"),
                       PZ("Pierna_I", "cilindro", [0.3, 0.3, 1.2], "Torso"),
                       PZ("Pierna_D", "cilindro", [0.3, 0.3, 1.2], "Torso"),
                       PZ("Pie_I", "caja", [0.3, 0.5, 0.1], "Pierna_I"), PZ("Pie_D", "caja", [0.3, 0.5, 0.1], "Pierna_D")],
            "relaciones": [["centro", "Torso", 0, 0, 1.9], ["encima", "Cabeza", "Torso"], ["delante", "Ojo_I", "Cabeza"],
                           ["x", "Ojo_I", -0.12], ["mover", "Ojo_I", 0, 0, 0.1], ["espejo_x", "Ojo_D", "Ojo_I"],
                           ["encima", "Antena", "Cabeza"], ["encima", "Punta", "Antena"],
                           ["izquierda", "Brazo_I", "Torso"], ["espejo_x", "Brazo_D", "Brazo_I"],
                           ["debajo", "Mano_I", "Brazo_I"], ["espejo_x", "Mano_D", "Mano_I"],
                           ["debajo", "Pierna_I", "Torso"], ["x", "Pierna_I", -0.3], ["espejo_x", "Pierna_D", "Pierna_I"],
                           ["debajo", "Pie_I", "Pierna_I"], ["mover", "Pie_I", 0, -0.1, 0],
                           ["espejo_x", "Pie_D", "Pie_I"]]},
}


def _tarea(u):
    return "T14" if "robot detallado" in u else "T13" if "ARTICULADOS" in u else "T08" if "avance 4 m" in u else "T05"


def _mal(id_, ref, fase):
    """El fallo adrede del primer intento (cada uno se arregla solo si el aviso propone el arreglo)."""
    d = json.loads(json.dumps(ref))
    if id_ == "T05" and fase in (None, "relaciones"):            # cabeza debajo en vez de encima
        d["relaciones"][1] = ["debajo", "Cabeza", "Torso"]
    elif id_ == "T14" and fase in (None, "relaciones"):          # centro de más: conflicto
        d["relaciones"].append(["centro", "Cabeza", 0, 0, 2.7])
    elif id_ == "T13" and fase == "articulaciones":              # olvida los brazos
        d["articulaciones"] = d["articulaciones"][:2]
    elif id_ == "T13" and fase is None:                          # piernas sin x: una dentro de otra
        d["relaciones"] = [r for r in d["relaciones"] if r[0] != "x"]
    return d


ARREGLO = {"T05": '["encima", "Cabeza", "Torso"]', "T14": "BORRA",
           "T13": '"punto": "arriba"', "T13u": "espejo_x"}


def falso(msgs, max_tokens):
    u = msgs[-1]["content"]
    id_ = _tarea(u)
    m = re.search(r'FASE \d+ de \d+: Escribe SOLO \{"(\w+)"', u)
    fase = m.group(1) if m else None
    clave = "T13u" if id_ == "T13" and fase is None else id_
    arreglado = "Resultado:" in u and ARREGLO.get(clave, "\0") in u
    d = REF[id_] if arreglado else _mal(id_, REF[id_], fase)
    if fase:
        d = {fase: d[fase]}
        g = re.search(r"ESTAS piezas[^:]*: (.*?)\. Las demás", u)
        if g:                                                    # condición «trozos»: solo las de este trozo
            grupo = g.group(1).split(", ")
            d = {fase: [x for x in d[fase] if (x["nombre"] if isinstance(x, dict) else x[1]) in grupo]}
    return f"```json\n{json.dumps(d, ensure_ascii=False)}\n```", 100, "stop"


def resolvedor() -> list:
    ok = []

    def error(d):
        try:
            R.generar(d)
        except R.ErrorRel as e:
            return str(e)
        return ""
    sol = R.resolver(REF["T14"])
    ok.append(("posiciones T14 (ojo, pie, mano, punta)",
               [round(v, 6) for v in sol["Ojo_D"]["centro"]] == [0.12, -0.31, 2.85]
               and [round(v, 6) for v in sol["Pie_D"]["centro"]] == [0.3, -0.1, 0.05]
               and [round(v, 6) for v in sol["Mano_I"]["centro"]] == [-0.625, 0.0, 1.275]
               and [round(v, 6) for v in sol["Punta"]["centro"]] == [0.0, 0.0, 3.36]))
    ok.append(("conflicto propone quitar", "BORRA" in error(_mal("T14", REF["T14"], None))))
    ok.append(("errata en relación", "¿querías decir «encima»?" in error({**REF["T05"], "relaciones": [["enzima", "Cabeza", "Torso"]]})))
    ok.append(("errata en forma", "¿querías decir «cilindro»?" in error({"piezas": [PZ("A", "cilindr", [1, 1, 1])]})))
    ok.append(("pieza sin colocar", "sin posición completa" in error({**REF["T05"], "relaciones": ROBOT_R[:2]})))
    ok.append(("JSON cortado", _cortado()))
    pos = R.resolver({**REF["T05"], "relaciones": [["z", "Cabeza", "= arriba(Torso) + mitad(Cabeza)"], ["x", "Cabeza", 0],
                                                   ["y", "Cabeza", 0]] + [r for r in ROBOT_R if r[1] != "Cabeza"]})
    ok.append(("fórmula con posiciones (diferida)", [round(v, 6) for v in pos["Cabeza"]["centro"]] == [0.0, 0.0, 2.85]))
    ok.append(("conflicto con distancias explica posiciones", "son distancias" in error(
        {**REF["T05"], "relaciones": ROBOT_R + [["centro", "Cabeza", 0, 0, "= alto(Torso) / 2 + mitad(Cabeza)"]]})))
    ok.append(("orden indiferente", R.resolver({**REF["T14"], "relaciones": REF["T14"]["relaciones"][::-1]}) == sol))
    ok.append(("trozos T14", R.fases_de("T14", "trozos")[2:4] == ["piezas@3", "relaciones@1"]
               and R.fases_de("T13", "trozos") == R.fases_de("T13")
               and len(R.comprobaciones_fase("T14", "relaciones@3")) == len(R.comprobaciones_fase("T14", "relaciones"))))
    ok.append(("fases T13", R.fases_de("T13") == ["piezas", "relaciones", "articulaciones", "animacion"]
               and R.fases_de("T05") == ["piezas", "relaciones"] and R.fases_de("T08") == ["piezas", "relaciones", "animacion"]))
    return ok


def _cortado():
    try:
        R.leer_json('```json\n{"piezas": [{"nombre": "A", "medidas": [1, 1\n```')
    except R.ErrorRel as e:
        return "cortada" in str(e)
    return False


def main() -> int:
    salida = Path(sys.argv[1])
    bien = True
    for nombre, r in resolvedor():
        print(f"[{'PASA' if r else 'FALLA'}] resolvedor: {nombre}")
        bien &= bool(r)
    ev = Path(tempfile.mkdtemp(prefix="rel2_"))
    try:
        R.CONDICIONES = ["una_vez", "fases", "trozos"]
        R.correr("falso", list(R.TAREAS_R2), ev, salida, falso)
        filas = R.leer_filas(ev)
        for c in R.CONDICIONES:
            for id_ in R.TAREAS_R2:
                fin = next(f for f in filas if f.get("condicion") == c and f["tarea"] == id_ and f.get("tipo") == "final")
                hs = [f for f in filas if f.get("condicion") == c and f["tarea"] == id_ and f.get("tipo") != "final"]
                fallos = [f for f in hs if not f["aprobado"]]
                esperado_fallos = {("una_vez", "T05"): 1, ("una_vez", "T14"): 1, ("una_vez", "T13"): 1,
                                   ("fases", "T05"): 1, ("fases", "T14"): 1, ("fases", "T13"): 1,
                                   ("trozos", "T05"): 1, ("trozos", "T14"): 1, ("trozos", "T13"): 1}.get((c, id_), 0)
                ok = fin["aprobado"] and len(fallos) == esperado_fallos
                bien &= ok
                print(f"[{'PASA' if ok else 'FALLA'}] {c} {id_}: final {fin['cumplidas']}/{fin['total']}, "
                      f"{len(hs)} llamadas, fallos adrede arreglados {len(fallos)}/{esperado_fallos}"
                      + (f" | aviso: {fallos[0]['feedback'][-160:]!r}" if fallos else ""))
                if not fin["aprobado"]:
                    print("   ", fin["feedback"][:600])
        print(R.informe(ev))
    finally:
        shutil.rmtree(ev, ignore_errors=True)
    return 0 if bien else 1


if __name__ == "__main__":
    raise SystemExit(main())
