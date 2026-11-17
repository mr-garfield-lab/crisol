"""Banco de Blender · ARQUITECTURAS (tanda 12): el cerebro dice QUÉ va dónde y un programa calcula el CUÁNTO.

Tandas 9–11: los cerebros entienden la estructura del robot pero fallan al combinar medidas. Aquí se prueban dos
arquitecturas de la literatura (ver ESTUDIO_ARQUITECTURAS.md), pidiendo el robot entero de una vez:
- `funciones` (A, estilo aDSL/SceneCraft): el cerebro escribe Python con una biblioteca ya cargada (`caja`, `encima`,
  `debajo`, `a_la_izquierda`, `en_el_suelo`, `hijo`, `avanzar`…) que hace las cuentas exactas.
- `relacional` (B, estilo Holodeck 2.0/AIDL): el cerebro solo escribe un JSON con piezas y relaciones; un resolvedor
  sin IA (aquí, en Python, fuera de Blender) coloca las piezas, detecta conflictos y genera el script de Blender.
Mismo verificador con TODAS las comprobaciones de la tarea; hasta 3 intentos con lo medido (o el error del resolvedor).

    py -B -X utf8 eq3/lanzador_eq2.py lab_blender/arquitecturas.py ejecutar <externos> <evidencia> <salida_blender> \
        --modelos qwen25 ministral3
    py -B -X utf8 lab_blender/arquitecturas.py informe <evidencia>
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
for p in (str(AQUI.parent), str(AQUI)):
    if p not in sys.path:
        sys.path.insert(0, p)
import banco as BB  # noqa: E402
import tareas as T  # noqa: E402

TAREAS_ARQ = ("T05", "T08")
CONDICIONES = ["funciones", "relacional"]
INTENTOS = 3

# --- A · biblioteca de funciones (se antepone al script del cerebro; corre dentro de Blender) ------------------------
BIBLIOTECA = '''import bpy

_MEDIDAS = {}


def caja(nombre, medidas, centro=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=centro)
    ob = bpy.context.active_object
    ob.name = nombre
    ob.scale = medidas
    _MEDIDAS[nombre] = tuple(medidas)
    return ob


def _o(n):
    return bpy.data.objects[n]


def poner(a, x=None, y=None, z=None):
    A = _o(a)
    if x is not None:
        A.location.x = x
    if y is not None:
        A.location.y = y
    if z is not None:
        A.location.z = z


def mover(a, dx=0, dy=0, dz=0):
    A = _o(a)
    A.location.x += dx
    A.location.y += dy
    A.location.z += dz


def encima(a, b):
    A, B = _o(a), _o(b)
    A.location = (B.location.x, B.location.y, B.location.z + _MEDIDAS[b][2] / 2 + _MEDIDAS[a][2] / 2)


def debajo(a, b):
    A, B = _o(a), _o(b)
    A.location.z = B.location.z - _MEDIDAS[b][2] / 2 - _MEDIDAS[a][2] / 2


def a_la_izquierda(a, b):
    A, B = _o(a), _o(b)
    A.location = (B.location.x - _MEDIDAS[b][0] / 2 - _MEDIDAS[a][0] / 2, B.location.y, B.location.z)


def a_la_derecha(a, b):
    A, B = _o(a), _o(b)
    A.location = (B.location.x + _MEDIDAS[b][0] / 2 + _MEDIDAS[a][0] / 2, B.location.y, B.location.z)


def en_el_suelo(a):
    _o(a).location.z = _MEDIDAS[a][2] / 2


def hijo(a, padre):
    bpy.context.view_layer.update()
    A, P = _o(a), _o(padre)
    A.parent = P
    A.matrix_parent_inverse = P.matrix_world.inverted()


def avanzar(a, desplazamiento, desde, hasta):
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = desde, hasta
    A = _o(a)
    A.keyframe_insert(data_path="location", frame=desde)
    A.location.x += desplazamiento[0]
    A.location.y += desplazamiento[1]
    A.location.z += desplazamiento[2]
    A.keyframe_insert(data_path="location", frame=hasta)

# ---- fin de la biblioteca ----
'''
DOC_FUNCIONES = '''
YA ESTÁN CARGADAS estas funciones (no las escribas; no hace falta «import bpy»). Hacen las cuentas exactas por ti:
- caja(nombre, (ancho_x, fondo_y, alto_z), centro=(x, y, z)) crea una caja con esas medidas.
- encima(a, b): pone «a» justo encima de «b», centrada y tocándolo.
- debajo(a, b): pone la cara de arriba de «a» tocando la cara de abajo de «b» (solo cambia z).
- a_la_izquierda(a, b) / a_la_derecha(a, b): pone «a» pegada al lado x negativo / x positivo de «b», a su altura.
- en_el_suelo(a): apoya la base de «a» en z = 0 (solo cambia z).
- poner(a, x=…, y=…, z=…) fija esas coordenadas del centro; mover(a, dx=…, dy=…, dz=…) lo desplaza.
- hijo(a, padre): hace «a» hija de «padre» sin moverla. Llámala DESPUÉS de colocar las piezas.
- avanzar(a, (dx, dy, dz), desde, hasta): ajusta la escena a esos fotogramas y anima «a» desplazándose eso
  (sus hijas van con ella). Llámala al FINAL.
Las piezas se colocan unas respecto a otras: crea primero la que tiene posición absoluta.
Ejemplo (una mesa, no la tarea): caja("Tablero", (2, 1, 0.1), centro=(0, 0, 1)); caja("Pata", (0.1, 0.1, 0.95));
debajo("Pata", "Tablero"); poner("Pata", x=-0.9); hijo("Pata", "Tablero")
'''

# --- B · JSON + resolvedor (fuera de Blender, sin IA) -----------------------------------------------------------------
SISTEMA_REL = (
    "Describes escenas de Blender como un JSON de piezas y relaciones; un programa calcula las posiciones exactas y "
    "construye la escena. Responde SOLO con un bloque ```json … ```, sin explicaciones.\n"
    "Formato:\n"
    '{"piezas": [{"nombre": "…", "medidas": [ancho_x, fondo_y, alto_z], "centro": [x, y, z] (solo si la tarea da '
    'su posición), "padre": "…" (opcional)}],\n'
    ' "relaciones": [["encima", "A", "B"], …],\n'
    ' "animacion": {"objeto": "…", "desplazamiento": [dx, dy, dz], "desde": f0, "hasta": f1} (opcional)}\n'
    "Relaciones (A se coloca respecto a B, que ya debe tener posición):\n"
    '- ["encima", A, B]: A justo encima de B, centrada y tocándolo.\n'
    '- ["debajo", A, B]: la cara de arriba de A toca la de abajo de B (fija z de A; x e y de B salvo que las fijes).\n'
    '- ["izquierda", A, B] / ["derecha", A, B]: A pegada al lado x negativo / x positivo de B, a su altura.\n'
    '- ["en_el_suelo", A]: la base de A en z = 0 (fija z).\n'
    '- ["x", A, valor] / ["y", A, valor] / ["z", A, valor]: fija esa coordenada del centro de A.\n'
    "Si dos relaciones dan valores distintos a la misma coordenada, el programa te lo dirá.\n"
    "Unidades en metros, Z hacia arriba; las medidas «a × b × c» son en X, Y, Z. Usa exactamente los nombres pedidos.\n"
    'Ejemplo (una mesa, no la tarea): {"piezas": [{"nombre": "Tablero", "medidas": [2, 1, 0.1], "centro": [0, 0, 1]}, '
    '{"nombre": "Pata", "medidas": [0.1, 0.1, 0.95], "padre": "Tablero"}], "relaciones": [["debajo", "Pata", '
    '"Tablero"], ["x", "Pata", -0.9]]}')
_JSON = re.compile(r"```(?:json)?[ \t]*\r?\n(.*?)```", re.S | re.I)


class ErrorRel(Exception):
    pass


def leer_json(texto: str) -> dict:
    m = _JSON.search(texto or "")
    s = m.group(1) if m else (texto or "")
    if not m and "{" in s:
        s = s[s.index("{"): s.rindex("}") + 1] if "}" in s else s[s.index("{"):]
    try:
        d = json.loads(s)
    except json.JSONDecodeError as e:
        raise ErrorRel(f"el JSON no se puede leer: {e.msg} (línea {e.lineno}, columna {e.colno})")
    if not isinstance(d, dict) or not isinstance(d.get("piezas"), list):
        raise ErrorRel('falta la lista "piezas"')
    return d


def _num(v, que):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ErrorRel(f"{que} debe ser un número (es {v!r})")
    return float(v)


def resolver(d: dict) -> dict:
    """Piezas y relaciones → {nombre: {"medidas", "centro", "padre"}}. Lanza ErrorRel con un mensaje para el cerebro."""
    P = {}
    for p in d["piezas"]:
        if not isinstance(p, dict) or not isinstance(p.get("nombre"), str):
            raise ErrorRel(f"pieza sin nombre: {p!r}")
        n = p["nombre"]
        if n in P:
            raise ErrorRel(f"la pieza «{n}» está repetida")
        med = p.get("medidas")
        if not isinstance(med, list) or len(med) != 3:
            raise ErrorRel(f"«{n}»: \"medidas\" debe ser [ancho_x, fondo_y, alto_z]")
        med = [_num(v, f"«{n}» medidas") for v in med]
        if min(med) <= 0:
            raise ErrorRel(f"«{n}»: las medidas deben ser positivas")
        c = p.get("centro")
        if c is not None and (not isinstance(c, list) or len(c) != 3):
            raise ErrorRel(f"«{n}»: \"centro\" debe ser [x, y, z]")
        P[n] = {"medidas": med, "padre": p.get("padre"), "fijo": [None] * 3, "origen": [None] * 3}
        if c is not None:
            for i in range(3):
                P[n]["fijo"][i], P[n]["origen"][i] = _num(c[i], f"«{n}» centro"), "centro"
    for n, p in P.items():
        if p["padre"] is not None and p["padre"] not in P:
            raise ErrorRel(f"«{n}»: su padre «{p['padre']}» no es ninguna pieza")

    def fijar(n, i, v, por):
        q = P[n]
        if q["fijo"][i] is not None and abs(q["fijo"][i] - v) > 1e-6:
            raise ErrorRel(f"conflicto en «{n}»: {q['origen'][i]} pone {'xyz'[i]} = {q['fijo'][i]:.3f} y {por} pone "
                           f"{'xyz'[i]} = {v:.3f}")
        q["fijo"][i], q["origen"][i] = v, por

    rels = d.get("relaciones") or []
    for r in rels:
        if not isinstance(r, list) or not r or r[0] not in {"encima", "debajo", "izquierda", "derecha", "en_el_suelo",
                                                             "x", "y", "z"}:
            raise ErrorRel(f"relación desconocida: {r!r} (valen encima, debajo, izquierda, derecha, en_el_suelo, x, y, z)")
        if len(r) != (2 if r[0] == "en_el_suelo" else 3):
            raise ErrorRel(f"relación mal escrita: {r!r}")
        if r[1] not in P or (r[0] in {"encima", "debajo", "izquierda", "derecha"} and r[2] not in P):
            raise ErrorRel(f"la relación {r!r} usa una pieza que no está en \"piezas\"")
    # 1.º lo absoluto (centro, x/y/z, suelo); luego lo relativo, hasta que no cambie nada
    for r in rels:
        if r[0] in "xyz":
            fijar(r[1], "xyz".index(r[0]), _num(r[2], f"{r!r}"), f'["{r[0]}", "{r[1]}"]')
        elif r[0] == "en_el_suelo":
            fijar(r[1], 2, P[r[1]]["medidas"][2] / 2, f'["en_el_suelo", "{r[1]}"]')
    pend = [r for r in rels if r[0] in {"encima", "debajo", "izquierda", "derecha"}]
    while pend:
        resto = []
        for r in pend:
            _, a, b = r
            B, A = P[b], P[a]
            ejes = {"encima": (0, 1, 2), "debajo": (2,), "izquierda": (0, 1, 2), "derecha": (0, 1, 2)}[r[0]]
            if any(B["fijo"][i] is None for i in ejes):
                resto.append(r)
                continue
            por = f'["{r[0]}", "{a}", "{b}"]'
            ha, hb = A["medidas"], B["medidas"]
            if r[0] == "encima":
                for i, v in ((0, B["fijo"][0]), (1, B["fijo"][1]), (2, B["fijo"][2] + hb[2] / 2 + ha[2] / 2)):
                    fijar(a, i, v, por)
            elif r[0] == "debajo":
                fijar(a, 2, B["fijo"][2] - hb[2] / 2 - ha[2] / 2, por)
                for i in (0, 1):                         # x e y de B salvo que ya estén fijadas
                    if A["fijo"][i] is None and B["fijo"][i] is not None:
                        A["fijo"][i], A["origen"][i] = B["fijo"][i], por
            else:
                s = -1 if r[0] == "izquierda" else 1
                fijar(a, 0, B["fijo"][0] + s * (hb[0] / 2 + ha[0] / 2), por)
                for i in (1, 2):                         # a la altura de B salvo que ya estén fijadas
                    if A["fijo"][i] is None:
                        A["fijo"][i], A["origen"][i] = B["fijo"][i], por
        if len(resto) == len(pend):
            raise ErrorRel("no puedo colocar " + ", ".join(f"«{r[1]}» ({r[0]} de «{r[2]}»)" for r in resto)
                           + ": la pieza de referencia no tiene posición (dale \"centro\" o colócala antes)")
        pend = resto
    return {n: {"medidas": p["medidas"], "centro": [v if v is not None else 0.0 for v in p["fijo"]], "padre": p["padre"]}
            for n, p in P.items()}


def script_relacional(d: dict) -> str:
    sol = resolver(d)
    L = [BIBLIOTECA]
    for n, p in sol.items():
        L.append(f"caja({n!r}, {tuple(round(v, 6) for v in p['medidas'])}, centro={tuple(round(v, 6) for v in p['centro'])})")
    for n, p in sol.items():
        if p["padre"]:
            L.append(f"hijo({n!r}, {p['padre']!r})")
    a = d.get("animacion")
    if a:
        if not isinstance(a, dict) or a.get("objeto") not in sol:
            raise ErrorRel('"animacion" necesita "objeto" (una pieza), "desplazamiento", "desde" y "hasta"')
        dz = a.get("desplazamiento")
        if not isinstance(dz, list) or len(dz) != 3:
            raise ErrorRel('"desplazamiento" debe ser [dx, dy, dz]')
        L.append(f"avanzar({a['objeto']!r}, {tuple(_num(v, 'desplazamiento') for v in dz)}, "
                 f"{int(_num(a.get('desde'), 'desde'))}, {int(_num(a.get('hasta'), 'hasta'))})")
    return "\n".join(L) + "\n"


# --- bucle ----------------------------------------------------------------------------------------------------------
def mensajes(cond: str, id_: str, previo: dict | None) -> list:
    u = f"TAREA:\n{T.TAREAS[id_]['enunciado']}"
    if cond == "funciones":
        sis = BB.SISTEMA + "\n" + DOC_FUNCIONES
        if previo:
            u += (f"\n\nTu script anterior:\n```python\n{previo['respuesta']}```\n\nResultado:\n{previo['feedback']}\n\n"
                  "Corrige el script y devuélvelo completo.")
    else:
        sis = SISTEMA_REL
        if previo:
            u += (f"\n\nTu JSON anterior:\n```json\n{previo['respuesta']}\n```\n\nResultado:\n{previo['feedback']}\n\n"
                  "Corrige el JSON y devuélvelo completo.")
    return [{"role": "system", "content": sis}, {"role": "user", "content": u}]


def construir(cond: str, texto: str) -> tuple:
    """(respuesta del cerebro, script para Blender o None, error del resolvedor o None)."""
    if cond == "funciones":
        nuevo = BB.extraer_script(texto)
        return nuevo, BIBLIOTECA + "\n" + nuevo, None
    m = _JSON.search(texto or "")
    resp = (m.group(1) if m else (texto or "")).strip()
    try:
        return resp, script_relacional(leer_json(texto)), None
    except ErrorRel as e:
        return resp, None, str(e)


def leer_filas(evidencia: Path) -> list:
    return BB.leer_filas(evidencia)


def _hechas(filas, modelo, cond, id_):
    return [f for f in filas if f["modelo"] == modelo and f.get("condicion") == cond and f["tarea"] == id_]


def pendientes(modelo, ids, evidencia) -> bool:
    filas = leer_filas(evidencia)
    return any(not any(f["aprobado"] for f in h) and len(h) < INTENTOS
               for c in CONDICIONES for i in (ids or TAREAS_ARQ) for h in [_hechas(filas, modelo, c, i)])


def correr(modelo, ids, evidencia, salida_blender, completar, parar=lambda: False) -> str:
    evidencia = Path(evidencia)
    for cond in CONDICIONES:
        for id_ in (ids or TAREAS_ARQ):
            while True:
                h = _hechas(leer_filas(evidencia), modelo, cond, id_)
                if any(f["aprobado"] for f in h) or len(h) >= INTENTOS:
                    break
                if parar():
                    return "parado"
                t0 = time.monotonic()
                texto, tokens, fin = completar(mensajes(cond, id_, h[-1] if h else None), BB.TOKENS)
                t_gen = round(time.monotonic() - t0, 2)
                resp, script, err = construir(cond, texto)
                fila = {"modelo": modelo, "condicion": cond, "tarea": id_, "intento": len(h) + 1, "texto": texto,
                        "respuesta": resp, "script": script, "tokens": tokens, "finish_reason": fin,
                        "segundos_cerebro": t_gen, "base_intacta": None, "motivos_filtro": [],
                        "fecha": time.strftime("%Y-%m-%dT%H:%M:%S")}
                if err:
                    fila.update(estado="ERROR_RESOLVEDOR", aprobado=False, cumplidas=0,
                                total=len(T.TAREAS[id_]["comprobaciones"]),
                                feedback=f"El programa no pudo construir la escena: {err}")
                else:
                    carpeta = Path(salida_blender) / modelo / f"{cond}_{id_}_i{len(h) + 1}_{int(time.time())}"
                    r, v = BB.probar(id_, script, carpeta, salida_blender)
                    fila.update(estado=r["estado"], aprobado=v["aprobado"], cumplidas=v.get("cumplidas", 0),
                                total=v.get("total", len(T.TAREAS[id_]["comprobaciones"])), feedback=v["texto"],
                                motivos_filtro=(r.get("filtro") or {}).get("motivos", []))
                with (evidencia / "peticiones.jsonl").open("a", encoding="utf-8", newline="\n") as fh:
                    fh.write(json.dumps(fila, ensure_ascii=False) + "\n")
    return "completo"


def informe(evidencia: Path) -> str:
    filas = leer_filas(evidencia)
    L = ["# Banco de Blender · arquitecturas: informe", "",
         "| modelo | condición | tarea | resultado | mejor | intentos | estados |", "|---|---|---|---|---|---|---|"]
    for m in dict.fromkeys(f["modelo"] for f in filas):
        for c in CONDICIONES:
            for id_ in TAREAS_ARQ:
                h = _hechas(filas, m, c, id_)
                if not h:
                    continue
                ok = next((f for f in h if f["aprobado"]), None)
                mejor = max(h, key=lambda f: f["cumplidas"])
                L.append(f"| {m} | {c} | {id_} | {'APROBADO al ' + str(ok['intento']) + '.º' if ok else 'no'} | "
                         f"{mejor['cumplidas']}/{mejor['total']} | {len(h)} | {' · '.join(f['estado'] for f in h)} |")
    texto = "\n".join(L) + "\n"
    (Path(evidencia) / "INFORME.md").write_text(texto, encoding="utf-8", newline="\n")
    return texto


def main(argv=None) -> int:
    global CONDICIONES
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("orden", choices=("ejecutar", "informe"))
    ap.add_argument("rutas", nargs="+")
    ap.add_argument("--modelos", nargs="+", default=["qwen25", "ministral3"])
    ap.add_argument("--condiciones", nargs="+", default=CONDICIONES, choices=("funciones", "relacional"))
    ap.add_argument("--reanudar", action="store_true")
    a = ap.parse_args(argv)
    if a.orden == "informe":
        print(informe(Path(a.rutas[0])))
        return 0
    CONDICIONES = list(a.condiciones)
    r = BB.ejecutar(Path(a.rutas[0]), Path(a.rutas[1]), Path(a.rutas[2]), tuple(a.modelos), list(TAREAS_ARQ),
                    a.reanudar, correr=correr, pendientes_fn=pendientes)
    print(json.dumps({k: r.get(k) for k in ("inicio", "fin", "abortada")}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
