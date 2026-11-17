"""Comprobación SIN cerebro real de la tanda 12 (arquitecturas): cerebros falsos con respuestas correctas y con fallos
adrede, en Blender real, y pruebas del resolvedor sin Blender.

    py -B -X utf8 lab_blender/comprobar_arquitecturas.py <salida_blender>          (desde equipo_ia_v3/)
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import arquitecturas as A  # noqa: E402

ROBOT_F = '''caja("Torso", (1.0, 0.6, 1.2), centro=(0, 0, 2.0))
caja("Cabeza", (0.5, 0.5, 0.5))
encima("Cabeza", "Torso")
for n, x in (("Pierna_I", -0.3), ("Pierna_D", 0.3)):
    caja(n, (0.3, 0.3, 1.4))
    debajo(n, "Torso")
    poner(n, x=x)
caja("Brazo_I", (0.25, 0.25, 1.0))
a_la_izquierda("Brazo_I", "Torso")
caja("Brazo_D", (0.25, 0.25, 1.0))
a_la_derecha("Brazo_D", "Torso")
for n in ("Cabeza", "Pierna_I", "Pierna_D", "Brazo_I", "Brazo_D"):
    hijo(n, "Torso")
'''
ANIM_F = 'avanzar("Torso", (0, -4, 0), 1, 48)\n'
# el fallo de la tanda 11: brazos debajo del torso, dentro de las piernas
MAL_F = ROBOT_F.replace('a_la_izquierda("Brazo_I", "Torso")', 'debajo("Brazo_I", "Torso")\nponer("Brazo_I", x=-0.25)') \
               .replace('a_la_derecha("Brazo_D", "Torso")', 'debajo("Brazo_D", "Torso")\nponer("Brazo_D", x=0.25)')

PIEZAS_R = [{"nombre": "Torso", "medidas": [1.0, 0.6, 1.2], "centro": [0, 0, 2.0]},
            *[{"nombre": n, "medidas": m, "padre": "Torso"} for n, m in
              (("Cabeza", [0.5, 0.5, 0.5]), ("Pierna_I", [0.3, 0.3, 1.4]), ("Pierna_D", [0.3, 0.3, 1.4]),
               ("Brazo_I", [0.25, 0.25, 1.0]), ("Brazo_D", [0.25, 0.25, 1.0]))]]
REL_R = [["encima", "Cabeza", "Torso"], ["debajo", "Pierna_I", "Torso"], ["x", "Pierna_I", -0.3],
         ["debajo", "Pierna_D", "Torso"], ["x", "Pierna_D", 0.3], ["izquierda", "Brazo_I", "Torso"],
         ["derecha", "Brazo_D", "Torso"]]
ANIM_R = {"objeto": "Torso", "desplazamiento": [0, -4, 0], "desde": 1, "hasta": 48}


def falso(msgs, max_tokens):
    sis, u = msgs[0]["content"], msgs[-1]["content"]
    animada = "avance 4 m" in u
    reintento = "Resultado:" in u
    if "YA ESTÁN CARGADAS" in sis:                                        # A · funciones
        cod = (ROBOT_F if reintento else MAL_F) + (ANIM_F if animada else "")
        return f"```python\n{cod}```", 60, "stop"
    rel = list(REL_R)
    if not reintento:                                                    # conflicto adrede: la pierna, también en el suelo a 0.5
        rel.append(["z", "Pierna_I", 0.5])
    d = {"piezas": PIEZAS_R, "relaciones": rel, **({"animacion": ANIM_R} if animada else {})}
    return f"```json\n{json.dumps(d)}\n```", 60, "stop"


def resolvedor() -> list:
    ok = []
    def falla(d, trozo):
        try:
            A.resolver(d)
        except A.ErrorRel as e:
            return trozo in str(e)
        return False
    sol = A.resolver({"piezas": PIEZAS_R, "relaciones": REL_R})
    ok.append(("posiciones exactas", sol["Cabeza"]["centro"] == [0.0, 0.0, 2.85]
               and sol["Brazo_D"]["centro"] == [0.625, 0.0, 2.0] and sol["Pierna_I"]["centro"] == [-0.3, 0.0, 0.7]))
    ok.append(("conflicto", falla({"piezas": PIEZAS_R, "relaciones": REL_R + [["z", "Pierna_I", 0.5]]}, "conflicto en «Pierna_I»")))
    ok.append(("relación desconocida", falla({"piezas": PIEZAS_R, "relaciones": [["sobre", "Cabeza", "Torso"]]}, "desconocida")))
    ok.append(("pieza inexistente", falla({"piezas": PIEZAS_R, "relaciones": [["encima", "Gorro", "Torso"]]}, "no está")))
    ok.append(("referencia sin posición", falla({"piezas": [{"nombre": "A", "medidas": [1, 1, 1]},
                                                         {"nombre": "B", "medidas": [1, 1, 1]}],
                                               "relaciones": [["encima", "A", "B"]]}, "no tiene posición")))
    ok.append(("JSON roto", not A.construir("relacional", "```json\n{\"piezas\": [\n```")[1]))
    ok.append(("orden indiferente", A.resolver({"piezas": PIEZAS_R, "relaciones": REL_R[::-1]}) == sol))
    return ok


def main() -> int:
    salida = Path(sys.argv[1])
    bien = True
    for nombre, r in resolvedor():
        print(f"[{'PASA' if r else 'FALLA'}] resolvedor: {nombre}")
        bien &= r
    ev = Path(tempfile.mkdtemp(prefix="arq_"))
    try:
        A.correr("falso", list(A.TAREAS_ARQ), ev, salida, falso)
        filas = A.leer_filas(ev)
        for c in A.CONDICIONES:
            for id_ in A.TAREAS_ARQ:
                h = A._hechas(filas, "falso", c, id_)
                esperado = (len(h) == 2 and not h[0]["aprobado"] and h[1]["aprobado"]
                            and (h[0]["estado"] == "ERROR_RESOLVEDOR") == (c == "relacional"))
                bien &= esperado
                print(f"[{'PASA' if esperado else 'FALLA'}] {c} {id_}: " +
                      " → ".join(f"{f['estado']} {f['cumplidas']}/{f['total']}" for f in h)
                      + f" | 1.er aviso: {h[0]['feedback'][:110]!r}")
        print(A.informe(ev))
    finally:
        shutil.rmtree(ev, ignore_errors=True)
    return 0 if bien else 1


if __name__ == "__main__":
    raise SystemExit(main())
