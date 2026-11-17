"""Comprobación SIN cerebro real de los robots por pasos: un cerebro falso construye T05 y T08 por partes con el
código de referencia (y falla adrede la cabeza en el primer intento). Necesita Blender (no GPU de IA).

    py -B -X utf8 lab_blender/comprobar_pasos.py <salida_blender>          (desde equipo_ia_v3/)
"""
from __future__ import annotations

import re
import shutil
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import pasos as P  # noqa: E402

AYUDA = '''import bpy

def caja(nombre, tam, pos, padre=None):
    bpy.ops.mesh.primitive_cube_add(size=1, location=pos)
    ob = bpy.context.active_object
    ob.name = nombre
    ob.scale = tam
    if padre:
        ob.parent = padre
        ob.matrix_parent_inverse = padre.matrix_world.inverted()
    return ob

torso = caja("Torso", (1.0, 0.6, 1.2), (0, 0, 2.0))
bpy.context.view_layer.update()
'''
T = 'bpy.data.objects["Torso"]'
POR_PASO = {
    1: AYUDA,
    2: f'caja("Cabeza", (0.5, 0.5, 0.5), (0, 0, 2.85), {T})\n',
    3: f'caja("Pierna_I", (0.3, 0.3, 1.4), (-0.3, 0, 0.7), {T})\ncaja("Pierna_D", (0.3, 0.3, 1.4), (0.3, 0, 0.7), {T})\n',
    4: f'caja("Brazo_I", (0.25, 0.25, 1.0), (-0.625, 0, 2.1), {T})\n'
       f'caja("Brazo_D", (0.25, 0.25, 1.0), (0.625, 0, 2.1), {T})\n',
    5: f'sc = bpy.context.scene\nsc.frame_start, sc.frame_end = 1, 48\nt = {T}\n'
       't.keyframe_insert(data_path="location", frame=1)\nt.location.y = -4\n'
       't.keyframe_insert(data_path="location", frame=48)\n',
}
MAL_CABEZA = f'caja("Cabeza", (0.5, 0.5, 0.5), (0, 0, 4.0), {T})\n'      # flotando: no toca el torso


def falso(msgs, max_tokens):
    u = msgs[-1]["content"]
    k = int(re.search(r"PASO (\d+) de", u).group(1))
    codigo = POR_PASO[k]
    if k == 2 and "Tu código para este paso" not in u:
        codigo = MAL_CABEZA
    return f"```python\n{codigo}```", 50, "stop"


def falso_mejoras(msgs, max_tokens):
    """Repite la cabeza mal hasta ver el aviso de código repetido y la pista de apoyo; solo entonces la arregla."""
    u = msgs[-1]["content"]
    k = int(re.search(r"PASO (\d+) de", u).group(1))
    codigo = POR_PASO[k]
    if k == 2 and not ("IDÉNTICO" in u and P.PISTA_APOYO in u):
        codigo = MAL_CABEZA
    return f"```python\n{codigo}```", 50, "stop"


def mejoras(salida: Path) -> bool:
    ev = Path(tempfile.mkdtemp(prefix="pasos10_"))
    P.MEJORAS = True
    try:
        sin_datos = "4.0" not in "\n".join(P.ayudas([{"nuevo": "x", "fallidas": ["dimensiones", "encima", "toca"]}]))
        P.correr("falso", ["T05"], ev, salida, falso_mejoras)
        filas = P.leer_filas(ev)
        fin = next(f for f in filas if f.get("tipo") == "final")
        cab = [f for f in filas if f.get("paso") == 2]
        bien = (sin_datos and fin["aprobado"] and len(cab) == 3 and [f["aprobado"] for f in cab] == [False, False, True]
                and "toca" in cab[0]["fallidas"])
        print(f"[{'PASA' if bien else 'FALLA'}] mejoras T05: final {fin['cumplidas']}/{fin['total']}, cabeza "
              f"{[f['aprobado'] for f in cab]}, fallidas 1.er intento {cab[0]['fallidas']}, pistas sin números={sin_datos}")
        return bien
    finally:
        P.MEJORAS = False
        shutil.rmtree(ev, ignore_errors=True)


CABEZA_BAJA = f'caja("Cabeza", (0.5, 0.5, 0.5), (0, 0, 2.6), {T})\n'    # el fallo real de la tanda 10 (base 2,35)


def falso_cuentas(msgs, max_tokens):
    """Cabeza baja hasta ver la cuenta medida (+0.25 en z); en las piernas reescribe primero el torso."""
    u, ult = msgs[1]["content"], msgs[-1]["content"]
    k = int(re.search(r"PASO (\d+) de", u).group(1))
    codigo = POR_PASO[k]
    if k == 2 and "mueve «Cabeza» +0.25 m en z" not in u:
        codigo = CABEZA_BAJA
    if k == 3 and not ult.startswith("Tu código vuelve a crear «Torso»"):
        codigo = POR_PASO[1] + codigo
    return f"```python\n{codigo}```", 50, "stop"


def cuentas(salida: Path) -> bool:
    ev = Path(tempfile.mkdtemp(prefix="pasos11_"))
    P.MEJORAS = P.CUENTAS = True
    try:
        P.correr("falso", ["T05"], ev, salida, falso_cuentas)
        filas = P.leer_filas(ev)
        fin = next(f for f in filas if f.get("tipo") == "final")
        cab = [f for f in filas if f.get("paso") == 2 and f.get("tipo") == "paso"]
        rees = [f for f in filas if f.get("tipo") == "reescritura"]
        pie = [f for f in filas if f.get("paso") == 3 and f.get("tipo") == "paso"]
        bien = (fin["aprobado"] and [f["aprobado"] for f in cab] == [False, True] and len(rees) == 1
                and rees[0]["objetos"] == ["Torso"] and len(pie) == 1 and pie[0]["aprobado"])
        print(f"[{'PASA' if bien else 'FALLA'}] cuentas T05: final {fin['cumplidas']}/{fin['total']}, cabeza "
              f"{[f['aprobado'] for f in cab]}, cuentas 1.er intento {cab[0]['cuentas']}, reescrituras "
              f"{[f['objetos'] for f in rees]}, piernas en {len(pie)} intento(s)")
        return bien
    finally:
        P.MEJORAS = P.CUENTAS = False
        shutil.rmtree(ev, ignore_errors=True)


def main() -> int:
    salida = Path(sys.argv[1])
    ev = Path(tempfile.mkdtemp(prefix="pasos_"))
    ok = []
    try:
        P.correr("falso", list(P.TAREAS_PASOS), ev, salida, falso)
        filas = P.leer_filas(ev)
        for id_ in P.TAREAS_PASOS:
            fin = next(f for f in filas if f["tarea"] == id_ and f.get("tipo") == "final")
            reint = [f for f in filas if f["tarea"] == id_ and f.get("paso") == 2]
            bien = fin["aprobado"] and len(reint) == 2 and not reint[0]["aprobado"] and reint[1]["aprobado"]
            ok.append(bien)
            print(f"[{'PASA' if bien else 'FALLA'}] {id_}: final {fin['cumplidas']}/{fin['total']} "
                  f"({'aprobado' if fin['aprobado'] else 'NO'}), pasos {fin['pasos_aprobados']}/{fin['pasos']}, "
                  f"cabeza: fallo y arreglo en 2 intentos = {len(reint) == 2}")
        print(P.informe(ev))
    finally:
        shutil.rmtree(ev, ignore_errors=True)
    ok.append(mejoras(salida))
    ok.append(cuentas(salida))
    return 0 if all(ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
