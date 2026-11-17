"""Banco de Blender · RELACIONAL v2 (tanda 13): piezas con forma, articulaciones y construcción por fases.

Sigue la arquitectura que ganó en la tanda 12 (el cerebro escribe un JSON de piezas y relaciones; un programa sin IA
calcula las posiciones y genera el script de Blender) y la amplía:
- **piezas más complicadas**: forma `caja`, `cilindro`, `esfera` o `cono`, orientada en el eje x, y o z;
- **articulaciones**: una pieza puede girar desde el centro de su cara de arriba, de abajo o desde su centro (cadera,
  hombro…); el programa pone ahí su origen;
- **animación** con desplazamiento del conjunto y giros por fotogramas clave en cada articulación;
- **relaciones nuevas**: `delante`, `detras`, `espejo_x` (simetría), `mover` (desplazamiento relativo) y `centro`;
- **avisos que proponen el arreglo** (el resolvedor y lo medido en Blender se traducen al vocabulario de relaciones);
- **por fases** (condición `fases`): 1 piezas → 2 relaciones → 3 articulaciones → 4 animación; cada fase se comprueba
  en Blender con lo que ya se puede medir y tiene hasta 3 intentos. La condición `una_vez` pide todo el JSON junto.
Tareas: T05 y T08 (robots), T13 (robot articulado que camina) y T14 (robot detallado de 15 piezas con cilindros,
esferas y pies). T13 y T14 se registran aquí, no en tareas.py, para no cambiar los bancos anteriores.

    py -B -X utf8 eq3/lanzador_eq2.py lab_blender/relacional2.py ejecutar <externos> <evidencia> <salida_blender> \
        --modelos qwen25 ministral3
    py -B -X utf8 lab_blender/relacional2.py informe <evidencia>
"""
from __future__ import annotations

import argparse
import difflib
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
import verificador as VF  # noqa: E402
import ejecutor as EJ  # noqa: E402

# --- tareas nuevas ---------------------------------------------------------------------------------------------------
P = T.PIEZAS
EXTREMIDADES = ["Pierna_I", "Pierna_D", "Brazo_I", "Brazo_D"]
T13 = {
    "enunciado": (f"Crea {T.ROBOT_TXT}. Las piernas y los brazos son ARTICULADOS: cada uno gira desde el centro de su "
                  "cara de arriba (cadera u hombro). Anima una caminata del fotograma 1 al 48: el robot entero avanza "
                  "4 m hacia Y negativa; cada pierna se balancea alrededor del eje X hasta 30° hacia cada lado, las dos "
                  "en sentidos contrarios; cada brazo se balancea alrededor del eje X hasta 20° hacia cada lado, al "
                  "revés que la pierna de su lado. En los fotogramas 1, 24 y 48 todas las piezas están rectas; los "
                  "balanceos máximos, en los fotogramas 12 y 36. La escena va del 1 al 48."),
    "animada": True, "muestras": 13,
    "comprobaciones": [*[("en_reposo", c) for c in T.ROBOT_OK], ("fotogramas", 1, 48),
                       *[("desplazamiento", p, (0, -4, 0)) for p in P],
                       *[("pivote", p, "Torso") for p in EXTREMIDADES],
                       ("balanceo", "Pierna_I", 0, 30.0), ("balanceo", "Pierna_D", 0, 30.0),
                       ("balanceo", "Brazo_I", 0, 20.0), ("balanceo", "Brazo_D", 0, 20.0),
                       ("contrafase", "Pierna_I", "Pierna_D", 0), ("contrafase", "Brazo_I", "Pierna_I", 0),
                       ("contrafase", "Brazo_D", "Pierna_D", 0),
                       *[("recto_en_extremos", p) for p in EXTREMIDADES]]}
P14 = ["Torso", "Cabeza", "Ojo_I", "Ojo_D", "Antena", "Punta", "Brazo_I", "Brazo_D", "Mano_I", "Mano_D", "Pierna_I",
       "Pierna_D", "Pie_I", "Pie_D"]
FORMAS14 = {"Torso": "caja", "Cabeza": "caja", "Ojo_I": "esfera", "Ojo_D": "esfera", "Antena": "cilindro",
            "Punta": "esfera", "Brazo_I": "cilindro", "Brazo_D": "cilindro", "Mano_I": "esfera", "Mano_D": "esfera",
            "Pierna_I": "cilindro", "Pierna_D": "cilindro", "Pie_I": "caja", "Pie_D": "caja"}
MED14 = {"Torso": (1.0, 0.6, 1.2), "Cabeza": (0.5, 0.5, 0.5), "Ojo_I": (0.12,) * 3, "Ojo_D": (0.12,) * 3,
         "Antena": (0.06, 0.06, 0.3), "Punta": (0.12,) * 3, "Brazo_I": (0.25, 0.25, 1.0), "Brazo_D": (0.25, 0.25, 1.0),
         "Mano_I": (0.25,) * 3, "Mano_D": (0.25,) * 3, "Pierna_I": (0.3, 0.3, 1.2), "Pierna_D": (0.3, 0.3, 1.2),
         "Pie_I": (0.3, 0.5, 0.1), "Pie_D": (0.3, 0.5, 0.1)}
T14 = {
    "enunciado": (
        "Crea un robot detallado. «Torso»: caja de 1.0 × 0.6 × 1.2 m con su centro en (0, 0, 1.9). «Cabeza»: caja de "
        "0.5 × 0.5 × 0.5 m justo encima del torso, centrada y tocándolo. «Ojo_I» y «Ojo_D»: esferas de 0.12 m de "
        "diámetro pegadas a la cara delantera de la cabeza (la de y negativa), 0.1 m por encima del centro de la "
        "cabeza, en x = -0.12 y x = 0.12. «Antena»: cilindro vertical de 0.06 m de diámetro y 0.3 m de alto, encima de "
        "la cabeza, centrado y tocándola; «Punta»: esfera de 0.12 m de diámetro encima de la antena, tocándola. "
        "«Brazo_I» y «Brazo_D»: cilindros verticales de 0.25 m de diámetro y 1.0 m de alto, uno a cada lado del torso, "
        "a su altura y tocándolo. «Mano_I» y «Mano_D»: esferas de 0.25 m de diámetro justo debajo de cada brazo, "
        "tocándolo. «Pierna_I» y «Pierna_D»: cilindros verticales de 0.3 m de diámetro y 1.2 m de alto, debajo del "
        "torso y tocándolo, en x = -0.3 y x = 0.3. «Pie_I» y «Pie_D»: cajas de 0.3 × 0.5 × 0.1 m debajo de cada "
        "pierna, tocándola, apoyadas en el suelo (z = 0) y desplazadas 0.1 m hacia delante (y negativa) respecto a su "
        "pierna. Las piezas «_I» van en x negativa y las «_D» en x positiva, simétricas. Todas cuelgan de «Torso» "
        "(directamente o a través de otra pieza)."),
    "comprobaciones": [
        ("solo", P14), *[("dimensiones", n, MED14[n]) for n in P14], *[("forma", n, FORMAS14[n]) for n in P14],
        ("centro", "Torso", (0, 0, 1.9)),
        ("encima", "Cabeza", "Torso"), ("toca", "Cabeza", "Torso"), ("centro", "Cabeza", (0, 0, 2.75)),
        ("delante_de", "Ojo_I", "Cabeza"), ("delante_de", "Ojo_D", "Cabeza"),
        ("centro", "Ojo_I", (-0.12, -0.31, 2.85)), ("simetricos", "Ojo_I", "Ojo_D"),
        ("encima", "Antena", "Cabeza"), ("toca", "Antena", "Cabeza"), ("centro", "Antena", (0, 0, 3.15)),
        ("encima", "Punta", "Antena"), ("toca", "Punta", "Antena"),
        ("a_un_lado", "Brazo_I", "Torso", -1), ("a_un_lado", "Brazo_D", "Torso", 1), ("toca", "Brazo_I", "Torso"),
        ("toca", "Brazo_D", "Torso"), ("simetricos", "Brazo_I", "Brazo_D"), ("centro", "Brazo_I", (-0.625, 0, 1.9)),
        ("encima", "Brazo_I", "Mano_I"), ("encima", "Brazo_D", "Mano_D"), ("toca", "Mano_I", "Brazo_I"),
        ("toca", "Mano_D", "Brazo_D"), ("simetricos", "Mano_I", "Mano_D"),
        ("toca", "Pierna_I", "Torso"), ("toca", "Pierna_D", "Torso"), ("centro", "Pierna_I", (-0.3, 0, 0.7)),
        ("simetricos", "Pierna_I", "Pierna_D"),
        ("apoyado", "Pie_I"), ("apoyado", "Pie_D"), ("toca", "Pie_I", "Pierna_I"), ("toca", "Pie_D", "Pierna_D"),
        ("centro", "Pie_I", (-0.3, -0.1, 0.05)), ("simetricos", "Pie_I", "Pie_D"),
        *[("lado", n, -1) for n in P14 if n.endswith("_I")], ("sin_solapes", P14),
        *[("desciende", n, "Torso") for n in P14[1:]]]}
T.TAREAS.setdefault("T13", T13)
T.TAREAS.setdefault("T14", T14)

TAREAS_R2 = ("T05", "T08", "T13", "T14")
CONDICIONES = ["una_vez", "fases"]
INTENTOS = 3
FORMAS = ("caja", "cilindro", "esfera", "cono", "cuna")
REL_POS = {"encima", "debajo", "izquierda", "derecha", "delante", "detras", "espejo_x"}
REL_ABS = {"centro", "x", "y", "z", "en_el_suelo"}
RELACIONES = REL_POS | REL_ABS | {"mover"}
MOVIMIENTO = {"fotogramas", "desplazamiento", "balanceo", "contrafase", "recto_en_extremos", "giro", "alternan"}

SISTEMA = (
    "Describes escenas de Blender como un JSON; un programa calcula las posiciones exactas, construye las piezas y la "
    "animación. Responde SOLO con un bloque ```json … ```, sin explicaciones. Unidades en metros, Z hacia arriba, "
    "«delante» es y negativa. Las medidas «a × b × c» son en X, Y, Z. Usa exactamente los nombres pedidos.\n\n"
    "1) \"piezas\": [{\"nombre\": …, \"forma\": \"caja\"|\"cilindro\"|\"esfera\"|\"cono\", \"medidas\": [x, y, z], "
    "\"eje\": \"z\" (solo cilindro o cono; \"x\" o \"y\" si está tumbado), \"padre\": … (opcional)}]\n"
    "   \"medidas\" es la caja que ocupa la pieza: un cilindro vertical de diámetro d y alto h es [d, d, h]; una esfera "
    "de diámetro d es [d, d, d].\n"
    "2) \"relaciones\": lista; A se coloca respecto a B (que ya debe estar colocada):\n"
    "   [\"centro\", A, x, y, z] posición absoluta (úsala solo si la tarea la da) · [\"x\", A, v] / [\"y\", A, v] / "
    "[\"z\", A, v] fija una coordenada del centro\n"
    "   [\"encima\", A, B] A sobre B, centrada y tocándolo · [\"debajo\", A, B] la cara de arriba de A toca la de abajo "
    "de B (x e y de B salvo que las fijes)\n"
    "   [\"izquierda\", A, B] / [\"derecha\", A, B] A pegada al lado x negativo / positivo de B, a su altura\n"
    "   [\"delante\", A, B] / [\"detras\", A, B] A pegada a la cara y negativa / positiva de B, a su altura\n"
    "   [\"en_el_suelo\", A] base de A en z = 0 · [\"espejo_x\", A, B] A es el reflejo de B (x cambiada de signo)\n"
    "   [\"mover\", A, dx, dy, dz] desplaza A después de colocarla\n"
    "   Cada coordenada de cada pieza la debe fijar UNA sola relación (si no, el programa avisa del conflicto).\n"
    "   CALCULADORA: cualquier número puede ser una fórmula entre comillas que empieza por \"=\". Úsala SOLO para "
    "una coordenada que ninguna relación fija (si encima, debajo, izquierda… ya colocan la pieza, no escribas nada "
    "más). Medidas (son DISTANCIAS, no posiciones): alto, ancho, fondo, mitad, mitad_x, mitad_y de una pieza. "
    "Posiciones de una pieza ya colocada: x(P), y(P), z(P) (su centro), arriba(P), abajo(P), borde_izq(P), "
    "borde_der(P), borde_delante(P), borde_detras(P). Ejemplo: [\"x\", \"Pierna_I\", \"= borde_izq(Torso) + "
    "mitad_x(Pierna_I)\"]. + - * / ( ), sqrt, sin, cos en grados. No hagas cuentas de cabeza.\n"
    "3) \"articulaciones\": [{\"pieza\": A, \"punto\": \"arriba\"|\"abajo\"|\"centro\"}] desde dónde gira A "
    "(«arriba» = centro de su cara de arriba).\n"
    "4) \"animacion\": {\"objeto\": A, \"desplazamiento\": [dx, dy, dz], \"desde\": f0, \"hasta\": f1, "
    "\"giros\": [{\"pieza\": B, \"eje\": \"x\"|\"y\"|\"z\", \"claves\": [[fotograma, grados], …]}]}\n"
    "   El objeto se desplaza con sus hijas; cada giro mueve una pieza alrededor de su articulación.\n\n"
    "Ejemplo (una lámpara, no la tarea): {\"piezas\": [{\"nombre\": \"Base\", \"forma\": \"cilindro\", \"medidas\": "
    "[0.4, 0.4, 0.05]}, {\"nombre\": \"Brazo\", \"forma\": \"caja\", \"medidas\": [0.05, 0.05, 0.6], \"padre\": "
    "\"Base\"}, {\"nombre\": \"Foco\", \"forma\": \"cono\", \"medidas\": [0.2, 0.2, 0.15], \"padre\": \"Brazo\"}], "
    "\"relaciones\": [[\"en_el_suelo\", \"Base\"], [\"x\", \"Base\", 0], [\"y\", \"Base\", 0], [\"encima\", \"Brazo\", "
    "\"Base\"], [\"encima\", \"Foco\", \"Brazo\"]], \"articulaciones\": [{\"pieza\": \"Brazo\", \"punto\": \"abajo\"}], "
    "\"animacion\": {\"desde\": 1, \"hasta\": 24, \"giros\": [{\"pieza\": \"Brazo\", \"eje\": \"y\", \"claves\": "
    "[[1, 0], [24, 15]]}]}}")
FASES = {
    "piezas": "Escribe SOLO {\"piezas\": […]}: nombre, forma, medidas (y eje, padre). Sin posiciones todavía.",
    "relaciones": "Escribe SOLO {\"relaciones\": […]}: las relaciones que colocan TODAS las piezas ya aprobadas.",
    "articulaciones": "Escribe SOLO {\"articulaciones\": […]}: qué piezas giran y desde qué punto.",
    "animacion": "Escribe SOLO {\"animacion\": {…}}: desplazamiento del conjunto y giros de las articulaciones.",
}
_JSON = re.compile(r"```(?:json)?[ \t]*\r?\n(.*?)```", re.S | re.I)


class ErrorRel(Exception):
    pass


def _parecido(x, opciones) -> str:
    m = difflib.get_close_matches(str(x), list(opciones), n=1, cutoff=0.6)
    return f" (¿querías decir «{m[0]}»?)" if m else ""


def leer_json(texto: str) -> dict:
    m = _JSON.search(texto or "")
    s = m.group(1) if m else (texto or "")
    if not m and "{" in s:
        s = s[s.index("{"): s.rindex("}") + 1] if "}" in s else s[s.index("{"):]
    try:
        d = json.loads(s)
    except json.JSONDecodeError as e:
        corte = " — la respuesta parece cortada: escribe el JSON más compacto (una pieza por línea)" \
            if e.msg.startswith(("Expecting", "Unterminated")) and e.pos >= len(s.rstrip()) - 2 else ""
        raise ErrorRel(f"el JSON no se puede leer: {e.msg} (línea {e.lineno}, columna {e.colno}){corte}")
    if not isinstance(d, dict):
        raise ErrorRel("la respuesta debe ser un objeto JSON {…}")
    return d


def _num(v, que):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ErrorRel(f"{que} debe ser un número (es {v!r})")
    return float(v)


AYUDA_FORMULA = ("solo valen números, + - * / **, paréntesis, pi, sqrt, sin, cos, tan (en grados), abs, min, max, "
                 "las medidas alto(P), ancho(P), fondo(P), mitad(P), mitad_x(P), mitad_y(P) y las posiciones x(P), "
                 "y(P), z(P), arriba(P), abajo(P), borde_izq(P), borde_der(P), borde_delante(P), borde_detras(P)")


class _Pendiente(ErrorRel):
    """La fórmula usa la posición de una pieza que aún no está colocada (se reintenta más tarde)."""


def _formula(expr: str, que: str, P_: dict) -> float:
    """Calculadora segura (tanda 13b): «= alto(Torso)/2 + mitad(Cabeza)». Nunca ejecuta código: recorre el árbol."""
    import ast
    import math
    if len(expr) > 200:
        raise ErrorRel(f"{que}: la fórmula es demasiado larga")
    try:
        arbol = ast.parse(expr, mode="eval")
    except SyntaxError:
        raise ErrorRel(f"{que}: la fórmula «{expr}» no se puede leer; {AYUDA_FORMULA}")

    def med(nombre, i):
        if nombre not in P_:
            raise ErrorRel(f"{que}: la fórmula usa «{nombre}», que no es una pieza{_parecido(nombre, P_)}")
        return P_[nombre]["medidas"][i]
    de_pieza = {"alto": lambda n: med(n, 2), "ancho": lambda n: med(n, 0), "fondo": lambda n: med(n, 1),
                "mitad": lambda n: med(n, 2) / 2, "mitad_x": lambda n: med(n, 0) / 2, "mitad_y": lambda n: med(n, 1) / 2,
                "mitad_z": lambda n: med(n, 2) / 2, "alto_z": lambda n: med(n, 2), "ancho_x": lambda n: med(n, 0),
                "fondo_y": lambda n: med(n, 1)}

    def pos(nombre, i, lado):                            # tanda 13c: posición de una pieza ya colocada
        med(nombre, 0)
        q = P_[nombre]
        if any(v is None for v in q["fijo"]):
            raise _Pendiente(nombre)
        return q["fijo"][i] + q["mover"][i] + lado * q["medidas"][i] / 2
    de_pieza.update({"x": lambda n: pos(n, 0, 0), "y": lambda n: pos(n, 1, 0), "z": lambda n: pos(n, 2, 0),
                     "arriba": lambda n: pos(n, 2, 1), "abajo": lambda n: pos(n, 2, -1),
                     "borde_izq": lambda n: pos(n, 0, -1), "borde_der": lambda n: pos(n, 0, 1),
                     "borde_delante": lambda n: pos(n, 1, -1), "borde_detras": lambda n: pos(n, 1, 1)})
    numericas = {"sqrt": math.sqrt, "abs": abs, "min": min, "max": max,
                 "sin": lambda g: math.sin(math.radians(g)), "cos": lambda g: math.cos(math.radians(g)),
                 "tan": lambda g: math.tan(math.radians(g))}

    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool):
            return float(n.value)
        if isinstance(n, ast.Name) and n.id == "pi":
            return math.pi
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)):
            v = ev(n.operand)
            return -v if isinstance(n.op, ast.USub) else v
        if isinstance(n, ast.BinOp) and isinstance(n.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)):
            a, b = ev(n.left), ev(n.right)
            if isinstance(n.op, ast.Pow):
                if abs(b) > 10:
                    raise ErrorRel(f"{que}: exponente demasiado grande en «{expr}»")
                return a ** b
            return a + b if isinstance(n.op, ast.Add) else a - b if isinstance(n.op, ast.Sub) else \
                a * b if isinstance(n.op, ast.Mult) else a / b
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and not n.keywords:
            f = n.func.id
            if f in de_pieza and len(n.args) == 1:
                a = n.args[0]
                nombre = a.id if isinstance(a, ast.Name) else a.value if isinstance(a, ast.Constant) and \
                    isinstance(a.value, str) else None
                if nombre is None:
                    raise ErrorRel(f"{que}: {f}() necesita el nombre de una pieza, como {f}(Torso)")
                return float(de_pieza[f](nombre))
            if f in numericas:
                return float(numericas[f](*[ev(a) for a in n.args]))
            raise ErrorRel(f"{que}: la función «{f}» no existe{_parecido(f, list(de_pieza) + list(numericas))}; "
                           f"{AYUDA_FORMULA}")
        raise ErrorRel(f"{que}: en la fórmula «{expr}» {AYUDA_FORMULA}")
    try:
        return ev(arbol)
    except (ZeroDivisionError, ValueError, TypeError, OverflowError) as e:
        raise ErrorRel(f"{que}: la fórmula «{expr}» no da un número ({type(e).__name__})")


def _valor(v, que, P_=None):
    """Un número o una fórmula «= …» calculada con las medidas de las piezas."""
    if isinstance(v, str) and v.strip().startswith("="):
        return _formula(v.strip()[1:].strip(), que, P_ or {})
    return _num(v, que)


# --- resolvedor ------------------------------------------------------------------------------------------------------
def _rot_matriz(grados) -> list:
    """Matriz de giro XYZ de Blender (R = Rz · Ry · Rx), sin mathutils."""
    from math import cos, radians, sin
    a, b, c = (radians(g) for g in grados)
    rx = [[1, 0, 0], [0, cos(a), -sin(a)], [0, sin(a), cos(a)]]
    ry = [[cos(b), 0, sin(b)], [0, 1, 0], [-sin(b), 0, cos(b)]]
    rz = [[cos(c), -sin(c), 0], [sin(c), cos(c), 0], [0, 0, 1]]
    mul = lambda A, B: [[sum(A[i][k] * B[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    return mul(rz, mul(ry, rx))


def _caja_girada(med, grados) -> list:
    """Medidas de la caja alineada con los ejes que ocupa una pieza de medidas `med` girada `grados`."""
    R = _rot_matriz(grados)
    return [sum(abs(R[i][j]) * med[j] for j in range(3)) for i in range(3)]


def _piezas(d: dict, biblioteca: dict | None = None) -> dict:
    if not isinstance(d.get("piezas"), list) or not d["piezas"]:
        raise ErrorRel('falta la lista "piezas"')
    P_ = {}
    for p in d["piezas"]:
        if not isinstance(p, dict) or not isinstance(p.get("nombre"), str):
            raise ErrorRel(f"pieza sin nombre: {p!r}")
        n = p["nombre"]
        if n in P_:
            raise ErrorRel(f"la pieza «{n}» está repetida")
        base = {"padre": p.get("padre"), "fijo": [None] * 3, "origen": [None] * 3, "mover": [0.0, 0.0, 0.0],
                "defecto": [False] * 3,
                "rot": None, "componente": None, "espejo": bool(p.get("espejo")), "tubo": None, "eje": "z"}
        if p.get("componente") is not None:                  # una instancia de un componente de la biblioteca
            comp = (biblioteca or {}).get(p["componente"])
            if comp is None:
                raise ErrorRel(f"«{n}»: el componente «{p['componente']}» no está en tu biblioteca"
                               f"{_parecido(p['componente'], biblioteca or {})}")
            P_[n] = {**base, "forma": "componente", "componente": p["componente"], "medidas": list(comp["caja"]),
                     "base": list(comp["caja"])}
        elif p.get("forma") == "tubo":                       # un tubo entre dos piezas (no se coloca con relaciones)
            if not isinstance(p.get("desde"), str) or not isinstance(p.get("hasta"), str):
                raise ErrorRel(f"«{n}»: un tubo necesita \"desde\" y \"hasta\" (dos piezas) y \"diametro\"")
            P_[n] = {**base, "forma": "tubo", "medidas": [0.0] * 3, "base": [0.0] * 3,
                     "tubo": (p["desde"], p["hasta"], _num(p.get("diametro"), f"«{n}» diametro"))}
        else:
            forma = p.get("forma", "caja")
            if forma not in FORMAS:
                raise ErrorRel(f"«{n}»: forma «{forma}» desconocida{_parecido(forma, FORMAS + ('tubo',))}; valen "
                               f"{', '.join(FORMAS)}, tubo o un \"componente\" de tu biblioteca")
            eje = p.get("eje", "z")
            if eje not in ("x", "y", "z"):
                raise ErrorRel(f"«{n}»: \"eje\" debe ser \"x\", \"y\" o \"z\"")
            med = p.get("medidas")
            if not isinstance(med, list) or len(med) != 3:
                raise ErrorRel(f"«{n}»: \"medidas\" debe ser [x, y, z] (la caja que ocupa la pieza)")
            med = [_num(v, f"«{n}» medidas") for v in med]
            if min(med) <= 0:
                raise ErrorRel(f"«{n}»: las medidas deben ser positivas")
            rot = p.get("rotacion")
            if rot is not None:
                if not isinstance(rot, list) or len(rot) != 3:
                    raise ErrorRel(f"«{n}»: \"rotacion\" debe ser [grados_x, grados_y, grados_z]")
                rot = [_num(v, f"«{n}» rotacion") for v in rot]
            P_[n] = {**base, "forma": forma, "eje": eje, "base": med, "rot": rot,
                     "medidas": _caja_girada(med, rot) if rot else med}
        if p.get("centro") is not None:
            c = p["centro"]
            if not isinstance(c, list) or len(c) != 3:
                raise ErrorRel(f"«{n}»: \"centro\" debe ser [x, y, z]")
            for i in range(3):
                P_[n]["fijo"][i], P_[n]["origen"][i] = _num(c[i], f"«{n}» centro"), f'el "centro" de «{n}»'
    for n, p in P_.items():
        if p["padre"] is not None and p["padre"] not in P_:
            raise ErrorRel(f"«{n}»: su padre «{p['padre']}» no es ninguna pieza{_parecido(p['padre'], P_)}")
    for n in P_:                                         # sin ciclos de padres
        visto, x = set(), n
        while P_[x]["padre"] is not None:
            if x in visto:
                raise ErrorRel(f"los padres de «{n}» forman un círculo")
            visto.add(x)
            x = P_[x]["padre"]
    return P_


def resolver(d: dict, biblioteca: dict | None = None) -> dict:
    """JSON → {nombre: {forma, eje, medidas, centro, padre, …}}. Lanza ErrorRel con un mensaje que propone el arreglo."""
    P_ = _piezas(d, biblioteca)
    for n, p in P_.items():
        if p["tubo"]:
            for x in p["tubo"][:2]:
                if x not in P_ or P_[x]["tubo"]:
                    raise ErrorRel(f"el tubo «{n}» va a «{x}», que no es una pieza (ni otro tubo){_parecido(x, P_)}")
    rels = d.get("relaciones") or []
    if not isinstance(rels, list):
        raise ErrorRel('"relaciones" debe ser una lista')
    largo = {"en_el_suelo": 2, "centro": 5, "mover": 5, "x": 3, "y": 3, "z": 3}
    for r in rels:
        if not isinstance(r, list) or not r or r[0] not in RELACIONES:
            q = r[0] if isinstance(r, list) and r else r
            raise ErrorRel(f"relación desconocida: {r!r}{_parecido(q, RELACIONES)}")
        if len(r) != largo.get(r[0], 3):
            forma = {"en_el_suelo": '["en_el_suelo", A]', "centro": '["centro", A, x, y, z]',
                     "mover": '["mover", A, dx, dy, dz]'}.get(r[0], f'["{r[0]}", A, ' + ("v]" if r[0] in "xyz" else "B]"))
            raise ErrorRel(f"relación mal escrita: {r!r}; se escribe {forma}"
                           + (" (para desplazarla un poco, añade aparte [\"mover\", A, dx, dy, dz])"
                              if r[0] in REL_POS and len(r) > 3 else ""))
        nombres = [r[1]] + ([r[2]] if r[0] in REL_POS else [])
        for n in nombres:
            if n not in P_:
                raise ErrorRel(f"la relación {r!r} usa «{n}», que no está en \"piezas\"{_parecido(n, P_)}")
            if P_[n]["tubo"]:
                raise ErrorRel(f"«{n}» es un tubo: no se coloca con relaciones, va de su \"desde\" a su \"hasta\"")

    def fijar(n, i, v, por):
        q = P_[n]
        if q["fijo"][i] is not None and not q["defecto"][i] and abs(q["fijo"][i] - v) > 1e-6:
            fija = lambda o: o.startswith(('["centro"', '["x"', '["y"', '["z"', 'el "centro"'))
            borrar = q["origen"][i] if fija(q["origen"][i]) and not fija(por) else por
            queda = por if borrar is q["origen"][i] else q["origen"][i]
            raise ErrorRel(
                f"conflicto en «{n}»: {q['origen'][i]} pone {'xyz'[i]} = {q['fijo'][i]:.3f} y {por} pone "
                f"{'xyz'[i]} = {v:.3f}. Cada coordenada la fija una sola cosa: BORRA {borrar} y deja {queda}"
                f"{' (la relación ya coloca la pieza: no hace falta el número)' if fija(borrar) and not fija(queda) else ''}"
                f". Para un pequeño ajuste usa [\"mover\", \"{n}\", dx, dy, dz]."
                + (" Ojo: alto(), mitad()… son distancias, no posiciones; la posición de otra pieza es z(P), "
                   "arriba(P), borde_izq(P)…" if '"=' in borrar else ""))
        q["fijo"][i], q["origen"][i], q["defecto"][i] = v, por, False

    for r in rels:
        if r[0] == "mover":
            for i in range(3):
                try:
                    P_[r[1]]["mover"][i] += _valor(r[2 + i], f"{r!r}", P_)
                except _Pendiente:
                    raise ErrorRel(f"{r!r}: en «mover» las fórmulas solo pueden usar medidas (alto, mitad…), no "
                                   "posiciones")

    def absoluta(r):                                     # True si se pudo fijar; False si espera una posición
        por = json.dumps(r, ensure_ascii=False)
        try:
            if r[0] == "centro":
                vs = [_valor(r[2 + i], f"{r!r}", P_) for i in range(3)]
                for i in range(3):
                    fijar(r[1], i, vs[i], por)
            elif r[0] in ("x", "y", "z"):
                fijar(r[1], "xyz".index(r[0]), _valor(r[2], f"{r!r}", P_), por)
            elif r[0] == "en_el_suelo":
                fijar(r[1], 2, P_[r[1]]["medidas"][2] / 2, por)
        except _Pendiente:
            return False
        return True
    diferidas = [r for r in rels if r[0] in REL_ABS and not absoluta(r)]

    def ef(n, i):                                        # posición efectiva (con «mover»)
        return P_[n]["fijo"][i] + P_[n]["mover"][i]

    pend = [r for r in rels if r[0] in REL_POS] + diferidas
    while pend:
        resto = []
        for r in pend:
            if r[0] in REL_ABS:
                if not absoluta(r):
                    resto.append(r)
                continue
            _, a, b = r
            A, B = P_[a], P_[b]
            if any(B["fijo"][i] is None for i in range(3)):
                resto.append(r)
                continue
            por, ma, mb = json.dumps(r, ensure_ascii=False), A["medidas"], B["medidas"]

            def libre(i, v):                             # por defecto: una relación explícita la puede cambiar
                if A["fijo"][i] is None:
                    A["fijo"][i], A["origen"][i], A["defecto"][i] = v, por, True
            if r[0] == "encima":
                fijar(a, 0, ef(b, 0), por)
                fijar(a, 1, ef(b, 1), por)
                fijar(a, 2, ef(b, 2) + mb[2] / 2 + ma[2] / 2, por)
            elif r[0] == "debajo":
                fijar(a, 2, ef(b, 2) - mb[2] / 2 - ma[2] / 2, por)
                libre(0, ef(b, 0)), libre(1, ef(b, 1))
            elif r[0] in ("izquierda", "derecha"):
                s = -1 if r[0] == "izquierda" else 1
                fijar(a, 0, ef(b, 0) + s * (mb[0] / 2 + ma[0] / 2), por)
                libre(1, ef(b, 1)), libre(2, ef(b, 2))
            elif r[0] in ("delante", "detras"):
                s = -1 if r[0] == "delante" else 1
                fijar(a, 1, ef(b, 1) + s * (mb[1] / 2 + ma[1] / 2), por)
                libre(0, ef(b, 0)), libre(2, ef(b, 2))
            else:                                        # espejo_x
                fijar(a, 0, -ef(b, 0), por)
                fijar(a, 1, ef(b, 1), por)
                fijar(a, 2, ef(b, 2), por)
        if len(resto) == len(pend) and all(r[0] in REL_ABS for r in resto):
            raise ErrorRel("no puedo calcular " + ", ".join(json.dumps(r, ensure_ascii=False) for r in resto)
                           + ": la fórmula usa la posición de una pieza que no queda colocada (o que se coloca a "
                             "partir de esta misma). Coloca antes esa pieza con una relación o con un número.")
        if len(resto) == len(pend):
            resto = [r for r in resto if r[0] in REL_POS] or resto
            faltan = {r[2]: ", ".join("xyz"[i] for i in range(3) if P_[r[2]]["fijo"][i] is None) for r in resto}
            raise ErrorRel("no puedo colocar " + ", ".join(f"«{r[1]}» ({r[0]} de «{r[2]}»)" for r in resto)
                           + ": a la pieza de referencia le falta posición: "
                           + "; ".join(f"«{b}» no tiene {ejes}" for b, ejes in faltan.items())
                           + ". Fíjala con una relación (encima, debajo, en_el_suelo, izquierda…, o x, y, z) o coloca "
                             "primero la pieza principal con [\"centro\", …].")
        pend = resto
    sin = [n for n, p in P_.items() if not p["tubo"] and any(v is None for v in p["fijo"])]
    out = {}
    for n, p in P_.items():
        out[n] = {"forma": p["forma"], "eje": p["eje"], "medidas": p["medidas"], "base": p["base"], "rot": p["rot"],
                  "componente": p["componente"], "espejo": p["espejo"], "padre": p["padre"], "tubo": None,
                  "centro": [(v if v is not None else 0.0) + p["mover"][i] for i, v in enumerate(p["fijo"])]}
    for n, p in P_.items():                              # tubo: del centro de «desde» al punto más cercano de «hasta»
        if p["tubo"]:
            a, b, diam = p["tubo"]
            p0 = out[a]["centro"]
            cb, mb = out[b]["centro"], out[b]["medidas"]
            p1 = [min(max(p0[i], cb[i] - mb[i] / 2), cb[i] + mb[i] / 2) for i in range(3)]
            if sum((x - y) ** 2 for x, y in zip(p0, p1)) < 1e-6:   # sin largo: provisional (fase de piezas)
                p1 = [p0[0], p0[1], p0[2] + 0.1]
                sin.append(n)
            out[n].update(tubo=(p0, p1, diam), centro=[(x + y) / 2 for x, y in zip(p0, p1)],
                          medidas=[abs(x - y) + diam for x, y in zip(p0, p1)])
    for a in out:                                        # pareja «_I»/«_D» en el mismo sitio: falta su x
        b = a[:-2] + "_D" if a.endswith("_I") else None
        if b in out and a not in sin and b not in sin and not P_[a]["tubo"] and \
                all(abs(x - y) < 1e-6 for x, y in zip(out[a]["centro"], out[b]["centro"])):
            raise ErrorRel(f"«{a}» y «{b}» quedan en el mismo sitio, una dentro de la otra (x = {out[a]['centro'][0]:.2f}): "
                           f"fija la x de «{a}» con [\"x\", \"{a}\", valor negativo] y coloca «{b}» con "
                           f"[\"espejo_x\", \"{b}\", \"{a}\"] (quita lo demás que fije la x de «{b}»)")
    out["_sin_colocar"] = sin
    return out


def _articulaciones(d: dict, sol: dict) -> dict:
    art = d.get("articulaciones") or []
    if not isinstance(art, list):
        raise ErrorRel('"articulaciones" debe ser una lista')
    out = {}
    for a in art:
        if isinstance(a, str):
            a = {"pieza": a, "punto": "arriba"}
        if not isinstance(a, dict) or a.get("pieza") not in sol or a.get("pieza") == "_sin_colocar":
            raise ErrorRel(f"articulación mal escrita o de una pieza que no existe: {a!r}")
        punto = a.get("punto", "arriba")
        if punto not in ("arriba", "abajo", "centro"):
            raise ErrorRel(f"«{a['pieza']}»: \"punto\" debe ser \"arriba\", \"abajo\" o \"centro\"{_parecido(punto, ('arriba', 'abajo', 'centro'))}")
        out[a["pieza"]] = punto
    return out


BIBLIOTECA = '''import bpy
import bmesh
from math import radians
from mathutils import Euler, Matrix, Vector


def pieza(nombre, forma, eje, medidas, centro, punto=None, rot=None):
    if forma in ("caja", "cuna"):
        bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0))
    elif forma == "cilindro":
        bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=0.5, depth=1, location=(0, 0, 0))
    elif forma == "esfera":
        bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, radius=0.5, location=(0, 0, 0))
    else:
        bpy.ops.mesh.primitive_cone_add(vertices=32, radius1=0.5, radius2=0, depth=1, location=(0, 0, 0))
    ob = bpy.context.active_object
    ob.name = nombre
    if forma == "cuna":                              # la arista de arriba delantera baja al suelo: rampa hacia -y
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        for v in bm.verts:
            if v.co.y < 0 and v.co.z > 0:
                v.co.z = -0.5
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
        bm.to_mesh(ob.data)
        bm.free()
    if eje == "x":
        ob.data.transform(Matrix.Rotation(radians(90), 4, "Y"))
    elif eje == "y":
        ob.data.transform(Matrix.Rotation(radians(90), 4, "X"))
    ob.data.transform(Matrix.Diagonal((medidas[0], medidas[1], medidas[2], 1.0)))
    if rot:
        ob.data.transform(Euler([radians(g) for g in rot], "XYZ").to_matrix().to_4x4())
    dz = {"arriba": -medidas[2] / 2, "abajo": medidas[2] / 2}.get(punto, 0.0)
    ob.data.transform(Matrix.Translation((0, 0, dz)))
    ob.location = (centro[0], centro[1], centro[2] - dz)
    return ob


def tubo(nombre, p0, p1, diametro):
    a, b = Vector(p0), Vector(p1)
    bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=0.5, depth=1, location=(0, 0, 0))
    ob = bpy.context.active_object
    ob.name = nombre
    ob.data.transform(Matrix.Diagonal((diametro, diametro, (b - a).length, 1.0)))
    ob.data.transform(Vector((0, 0, 1)).rotation_difference(b - a).to_matrix().to_4x4())
    ob.location = (a + b) / 2
    return ob


def hijo(a, padre):
    bpy.context.view_layer.update()
    A, P = bpy.data.objects[a], bpy.data.objects[padre]
    A.parent = P
    A.matrix_parent_inverse = P.matrix_world.inverted()

# ---- fin de la biblioteca ----
'''


def resolver_componente(comp: dict) -> dict:
    """Ficha de componente → sus piezas colocadas, la caja total que ocupa y su centro."""
    sol = resolver(comp)
    sin = sol.pop("_sin_colocar")
    if sin:
        raise ErrorRel("piezas del componente sin posición: " + ", ".join(f"«{n}»" for n in sin)
                       + ". Coloca la primera con [\"centro\", …, 0, 0, 0] y las demás respecto a ella.")
    if any(p["componente"] or p["tubo"] for p in sol.values()):
        raise ErrorRel("un componente no puede llevar otros componentes ni tubos (todavía)")
    lo = [min(p["centro"][i] - p["medidas"][i] / 2 for p in sol.values()) for i in range(3)]
    hi = [max(p["centro"][i] + p["medidas"][i] / 2 for p in sol.values()) for i in range(3)]
    return {"partes": sol, "caja": [b - a for a, b in zip(lo, hi)], "centro": [(a + b) / 2 for a, b in zip(lo, hi)]}


def _expandir(sol: dict, biblioteca: dict | None) -> tuple:
    """Instancias de componentes → piezas sueltas «Instancia_Parte». Devuelve (objetos, pieza real de cada nombre)."""
    objs, raiz = {}, {}
    for n, p in sol.items():
        if not p["componente"]:
            objs[n], raiz[n] = p, n
            continue
        comp = biblioteca[p["componente"]]
        for pn, pp in comp["partes"].items():
            off = [pp["centro"][i] - comp["centro"][i] for i in range(3)]
            rot = pp["rot"]
            if p["espejo"]:
                off[0] = -off[0]
                rot = [rot[0], -rot[1], -rot[2]] if rot else None
            if not pp["padre"] and n not in raiz:
                raiz[n] = f"{n}_{pn}"
            objs[f"{n}_{pn}"] = {**pp, "rot": rot, "centro": [p["centro"][i] + off[i] for i in range(3)],
                                 "padre": f"{n}_{pp['padre']}" if pp["padre"] else ("@" + p["padre"] if p["padre"] else None)}
    for o in objs.values():                              # el padre que es una instancia: su pieza raíz
        if o["padre"] and o["padre"].startswith("@"):
            o["padre"] = raiz.get(o["padre"][1:], o["padre"][1:])
        elif o["padre"] in raiz:
            o["padre"] = raiz[o["padre"]]
    return objs, raiz


def generar(d: dict, sin_relaciones_ok: bool = False, biblioteca: dict | None = None) -> str:
    """JSON completo (o el de las fases aprobadas) → script de Blender."""
    sol = resolver(d, biblioteca)
    sin = sol.pop("_sin_colocar")
    if sin and not sin_relaciones_ok:
        tubos = [n for n in sin if sol[n].get("tubo")]
        if tubos:
            raise ErrorRel("tubos sin largo: " + ", ".join(f"«{n}»" for n in tubos)
                           + ": su «desde» está dentro de su «hasta»; coloca bien esas piezas")
        raise ErrorRel("sin posición completa (quedarían en 0): " + ", ".join(f"«{n}»" for n in sin)
                       + ". Coloca cada pieza con una relación respecto a otra (o con \"centro\").")
    art = _articulaciones(d, sol)
    for n in art:
        if sol[n]["componente"] or sol[n]["tubo"]:
            raise ErrorRel(f"«{n}»: las articulaciones son de piezas sueltas (no de componentes ni tubos)")
    objs, raiz = _expandir(sol, biblioteca)
    L = [BIBLIOTECA]
    for n, p in objs.items():
        if p.get("tubo"):
            p0, p1, diam = p["tubo"]
            L.append(f"tubo({n!r}, {tuple(round(v, 6) for v in p0)}, {tuple(round(v, 6) for v in p1)}, {diam})")
        else:
            L.append(f"pieza({n!r}, {p['forma']!r}, {p['eje']!r}, {tuple(round(v, 6) for v in p['base'])}, "
                     f"{tuple(round(v, 6) for v in p['centro'])}, {art.get(n)!r}, {p['rot']!r})")
    for n, p in objs.items():
        if p["padre"]:
            L.append(f"hijo({n!r}, {p['padre']!r})")
    a = d.get("animacion")
    if a:
        if not isinstance(a, dict):
            raise ErrorRel('"animacion" debe ser un objeto {…}')
        f0, f1 = int(_num(a.get("desde"), '"desde"')), int(_num(a.get("hasta"), '"hasta"'))
        if f1 <= f0:
            raise ErrorRel('"hasta" debe ser mayor que "desde"')
        L.append(f"sc = bpy.context.scene\nsc.frame_start, sc.frame_end = {f0}, {f1}")
        if a.get("objeto") is not None or a.get("desplazamiento") is not None:
            if a.get("objeto") not in sol:
                raise ErrorRel(f'"animacion": "objeto" debe ser una pieza{_parecido(a.get("objeto"), sol)}')
            dz = a.get("desplazamiento")
            if not isinstance(dz, list) or len(dz) != 3:
                raise ErrorRel('"desplazamiento" debe ser [dx, dy, dz]')
            dz = [_num(v, '"desplazamiento"') for v in dz]
            L.append(f"o = bpy.data.objects[{raiz.get(a['objeto'], a['objeto'])!r}]\no.keyframe_insert(data_path='location', frame={f0})\n"
                     f"o.location.x += {dz[0]}\no.location.y += {dz[1]}\no.location.z += {dz[2]}\n"
                     f"o.keyframe_insert(data_path='location', frame={f1})")
        giros = a.get("giros") or []
        if not isinstance(giros, list):
            raise ErrorRel('"giros" debe ser una lista')
        for g in giros:
            if not isinstance(g, dict) or g.get("pieza") not in sol:
                raise ErrorRel(f"giro mal escrito o de una pieza que no existe: {g!r}")
            if g.get("eje") not in ("x", "y", "z"):
                raise ErrorRel(f"giro de «{g['pieza']}»: \"eje\" debe ser \"x\", \"y\" o \"z\"")
            claves = g.get("claves")
            if not isinstance(claves, list) or not claves or not all(isinstance(c, list) and len(c) == 2 for c in claves):
                raise ErrorRel(f"giro de «{g['pieza']}»: \"claves\" debe ser [[fotograma, grados], …]")
            i = "xyz".index(g["eje"])
            for f, gr in claves:
                L.append(f"o = bpy.data.objects[{raiz.get(g['pieza'], g['pieza'])!r}]\no.rotation_euler[{i}] = radians({_num(gr, 'grados')})\n"
                         f"o.keyframe_insert(data_path='rotation_euler', index={i}, frame={int(_num(f, 'fotograma'))})")
        L.append(f"sc.frame_set({f0})")
    return "\n".join(L) + "\n"


# --- avisos con el arreglo, en el vocabulario de relaciones -------------------------------------------------------------
def como_arreglar(tarea: dict, v: dict) -> list:
    out = []
    for c in v.get("comprobaciones", []):
        if c["cumple"]:
            continue
        nombre, args = c["comprobacion"], list(c["args"])
        if nombre == "en_reposo":
            nombre, args = args[0][0], list(args[0][1:])
        a = args[0] if args else None
        b = args[1] if len(args) > 1 else None
        h = {
            "encima": f"«{a}» debe ir sobre «{b}»: usa [\"encima\", \"{a}\", \"{b}\"]",
            "toca": f"«{a}» y «{b}» deben tocarse: coloca una respecto a la otra con encima, debajo, izquierda, "
                    f"derecha, delante o detras (no con números sueltos)",
            "simetricos": f"«{a}» y «{b}» deben ser simétricas: fija la x de una y usa [\"espejo_x\", \"{b}\", \"{a}\"]",
            "lado": f"«{a}» debe ir en x {'negativa' if isinstance(b, (int, float)) and b < 0 else 'positiva'}",
            "a_un_lado": f"«{a}» debe ir pegada por fuera al lado de «{b}»: usa [\"" + (
                "izquierda" if len(args) > 2 and isinstance(args[2], (int, float)) and args[2] < 0 else "derecha")
                         + f"\", \"{a}\", \"{b}\"]",
            "apoyado": f"«{a}» debe tocar el suelo: [\"en_el_suelo\", \"{a}\"] o apóyala sobre algo que lo toque",
            "sin_solapes": "dos piezas ocupan el mismo sitio: revisa que cada una tenga su propia x (o use "
                           "izquierda/derecha/espejo_x)",
            "forma": f"pon \"forma\": \"{b}\" en «{a}»",
            "dimensiones": f"revisa \"medidas\" de «{a}» ([x, y, z]; diámetro en x e y para cilindros y esferas)",
            "delante_de": f"usa [\"delante\", \"{a}\", \"{b}\"] (y \"mover\" para subirla o bajarla)",
            "pivote": f"añade {{\"pieza\": \"{a}\", \"punto\": \"arriba\"}} a \"articulaciones\"",
            "desciende": f"«{a}» debe colgar de «{b}»: pon su \"padre\"",
            "balanceo": f"revisa los \"giros\" de «{a}»: claves en grados, positivas y negativas",
            "contrafase": f"los giros de «{a}» y «{b}» deben tener signos contrarios en cada clave",
            "recto_en_extremos": f"«{a}» debe estar a 0° en el primer y el último fotograma",
            "desplazamiento": "revisa \"desplazamiento\" del objeto principal (sus hijas van con él)",
            "fotogramas": "revisa \"desde\" y \"hasta\" de la animación",
        }.get(nombre)
        if h and h not in out:
            out.append(h)
    return out


# --- fases y bucle ---------------------------------------------------------------------------------------------------
TROZO = 5                                                # tanda 13d: piezas por trozo


def piezas_de(id_: str) -> list:
    """Las piezas que pide la tarea (de su comprobación «solo»)."""
    return next((list(c[1]) for c in T.TAREAS[id_]["comprobaciones"] if c[0] == "solo"), [])


def grupos_de(id_: str) -> list:
    """Trozos de piezas para la condición «trozos»: uno solo si la tarea tiene pocas piezas."""
    ps = piezas_de(id_)
    return [ps[i:i + TROZO] for i in range(0, len(ps), TROZO)] if len(ps) > 8 else [ps]


def clave(fase: str) -> str:
    return fase.split("@")[0]


def grupo_de_fase(id_: str, fase: str) -> tuple:
    """(piezas del trozo, piezas de este trozo y los anteriores); todo si la fase no está troceada."""
    if "@" not in fase:
        return None, None
    gs, k = grupos_de(id_), int(fase.split("@")[1])
    return gs[k - 1], [n for g in gs[:k] for n in g]


def unir(aprobado: dict) -> dict:
    """Junta las partes aprobadas: las listas de los trozos se concatenan."""
    out = {}
    for f in aprobado.values():
        for k, v in f.items():
            out[k] = out.get(k, []) + v if isinstance(v, list) and isinstance(out.get(k), list) else v
    return out


def restringir(cs: list, nombres: list, todas: list) -> list:
    """Solo las comprobaciones de las piezas ya hechas; las listas de piezas se recortan a esas."""
    hechas, out = set(nombres), []
    for c in cs:
        listas = [i for i, a in enumerate(c) if isinstance(a, (list, tuple)) and a and all(isinstance(x, str) for x in a)]
        if listas:
            c = tuple([x for x in a if x in hechas] if i in listas else a for i, a in enumerate(c))
            if all(c[i] for i in listas):
                out.append(c)
        elif all(a in hechas for a in c[1:] if isinstance(a, str) and a in todas):
            out.append(c)
    return out


def fases_de(id_: str, cond: str = "fases") -> list:
    cs = [c[1][0] if c[0] == "en_reposo" else c[0] for c in T.TAREAS[id_]["comprobaciones"]]
    gs = grupos_de(id_) if cond == "trozos" else [None]
    if len(gs) > 1:
        out = [f"piezas@{k}" for k in range(1, len(gs) + 1)] + [f"relaciones@{k}" for k in range(1, len(gs) + 1)]
    else:
        out = ["piezas", "relaciones"]
    if "pivote" in cs:
        out.append("articulaciones")
    if any(c in MOVIMIENTO for c in cs):
        out.append("animacion")
    return out


def comprobaciones_fase(id_: str, fase: str) -> list:
    _, hechas = grupo_de_fase(id_, fase)
    cs = _comprobaciones_fase(id_, clave(fase))
    return restringir(cs, hechas, piezas_de(id_)) if hechas else cs


def _comprobaciones_fase(id_: str, fase: str) -> list:
    todas = T.TAREAS[id_]["comprobaciones"]
    base = lambda c: c[1][0] if c[0] == "en_reposo" else c[0]
    if fase == "piezas":
        return [c for c in todas if base(c) in {"solo", "dimensiones", "forma", "desciende"}]
    if fase == "relaciones":
        return [c for c in todas if base(c) not in MOVIMIENTO | {"pivote"}]
    if fase == "articulaciones":
        return [c for c in todas if base(c) not in MOVIMIENTO]
    return list(todas)


def mensajes(cond: str, id_: str, previo: dict | None, fase: str | None = None, aprobado: dict | None = None,
             k: int = 0, n: int = 0) -> list:
    u = f"TAREA:\n{T.TAREAS[id_]['enunciado']}"
    if cond in ("fases", "trozos"):
        if aprobado:
            u += f"\n\nYA APROBADO (no lo repitas):\n```json\n{json.dumps(unir(aprobado), ensure_ascii=False)}\n```"
        grupo, _ = grupo_de_fase(id_, fase)
        if grupo:                                        # trozo: solo estas piezas
            u += (f"\n\nFASE {k} de {n}: Escribe SOLO {{\"{clave(fase)}\": […]}} "
                  + ("de ESTAS piezas (nombre, forma, medidas, y eje, padre; sin posiciones): "
                     if clave(fase) == "piezas" else "con las relaciones que colocan ESTAS piezas: ")
                  + ", ".join(grupo) + ". Las demás ya están aprobadas o se piden después"
                  + (" (puedes colocar estas respecto a las ya colocadas)." if clave(fase) == "relaciones" else "."))
        else:
            u += f"\n\nFASE {k} de {n}: {FASES[clave(fase)]}"
    if previo:
        u += (f"\n\nTu respuesta anterior:\n```json\n{previo['respuesta']}\n```\n\nResultado:\n{previo['feedback']}\n\n"
              "Corrige y devuélvelo completo.")
    return [{"role": "system", "content": SISTEMA}, {"role": "user", "content": u}]


def leer_filas(evidencia: Path) -> list:
    return BB.leer_filas(evidencia)


def _hechas(filas, modelo, cond, id_, fase=None):
    return [f for f in filas if f["modelo"] == modelo and f.get("condicion") == cond and f["tarea"] == id_
            and f.get("fase") == fase and f.get("tipo") != "final"]


def estado(filas, modelo, cond, id_) -> dict:
    """Por dónde va: fase actual, JSON aprobado acumulado, intentos de la fase y si terminó."""
    if any(f["modelo"] == modelo and f.get("condicion") == cond and f["tarea"] == id_ and f.get("tipo") == "final"
           for f in filas):
        return {"terminada": True}
    if cond == "una_vez":
        h = _hechas(filas, modelo, cond, id_)
        return {"terminada": False, "fase": None, "aprobado": {}, "intentos": h,
                "cerrar": any(f["aprobado"] for f in h) or len(h) >= INTENTOS, "k": 0}
    acum = {}
    for k, fase in enumerate(fases_de(id_, cond), 1):
        h = _hechas(filas, modelo, cond, id_, fase)
        ok = next((f for f in h if f["aprobado"]), None)
        if ok:
            acum[fase] = ok["parte"]
            continue
        return {"terminada": False, "fase": fase, "aprobado": acum, "intentos": h, "cerrar": len(h) >= INTENTOS,
                "k": k}
    return {"terminada": False, "fase": None, "aprobado": acum, "intentos": [], "cerrar": True, "k": 0}


def _guardar(evidencia, fila):
    with (Path(evidencia) / "peticiones.jsonl").open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(fila, ensure_ascii=False) + "\n")


def _probar(id_, comprobaciones, script, carpeta):
    t = {**T.TAREAS[id_], "comprobaciones": comprobaciones}
    r = EJ.ejecutar(script, carpeta, base=None, muestras=t.get("muestras", 5), tiempo_s=BB.TIEMPO_BLENDER_S)
    return r, VF.verificar(t, r)


def correr(modelo, ids, evidencia, salida_blender, completar, parar=lambda: False) -> str:
    evidencia = Path(evidencia)
    for cond in CONDICIONES:
        for id_ in (ids or TAREAS_R2):
            while True:
                e = estado(leer_filas(evidencia), modelo, cond, id_)
                if e["terminada"]:
                    break
                if parar():
                    return "parado"
                if e["cerrar"]:                          # cierre: lo último construible, con TODAS las comprobaciones
                    if cond == "una_vez":
                        ok = next((f for f in e["intentos"] if f["aprobado"]), None) or \
                            max(e["intentos"], key=lambda f: f["cumplidas"])
                        script, json_final = ok["script"], ok.get("parte")
                    else:
                        json_final = unir(e["aprobado"])
                        try:
                            script = generar(json_final, sin_relaciones_ok=True) if json_final.get("piezas") else None
                        except ErrorRel:
                            script = None
                    tot = len(T.TAREAS[id_]["comprobaciones"])
                    if script:
                        r, v = _probar(id_, T.TAREAS[id_]["comprobaciones"], script,
                                       Path(salida_blender) / modelo / f"{cond}_{id_}_final_{int(time.time())}")
                        res = {"aprobado": v["aprobado"], "cumplidas": v.get("cumplidas", 0), "total": v.get("total", tot),
                               "estado": r["estado"], "feedback": v["texto"]}
                    else:
                        res = {"aprobado": False, "cumplidas": 0, "total": tot, "estado": "SIN_ESCENA", "feedback": ""}
                    _guardar(evidencia, {"modelo": modelo, "condicion": cond, "tarea": id_, "tipo": "final",
                                         "fases_aprobadas": len(e["aprobado"]), "fases": len(fases_de(id_, cond)),
                                         "json": json_final, "script": script, **res,
                                         "fecha": time.strftime("%Y-%m-%dT%H:%M:%S")})
                    break
                fase, h = e["fase"], e["intentos"]
                n = len(fases_de(id_, cond))
                t0 = time.monotonic()
                texto, tokens, fin = completar(mensajes(cond, id_, h[-1] if h else None, fase, e["aprobado"], e["k"], n),
                                               BB.TOKENS)
                t_gen = round(time.monotonic() - t0, 2)
                m = _JSON.search(texto or "")
                resp = (m.group(1) if m else (texto or "")).strip()
                fila = {"modelo": modelo, "condicion": cond, "tarea": id_, "fase": fase, "intento": len(h) + 1,
                        "texto": texto, "respuesta": resp, "tokens": tokens, "finish_reason": fin,
                        "segundos_cerebro": t_gen, "fecha": time.strftime("%Y-%m-%dT%H:%M:%S")}
                try:
                    d = leer_json(texto)
                    if fase:
                        cl = clave(fase)
                        if cl not in d:
                            raise ErrorRel(f"falta la clave \"{cl}\": {FASES[cl]}")
                        parte = {cl: d[cl]}
                        completo = unir({**e["aprobado"], fase: parte})
                        grupo, hechas = grupo_de_fase(id_, fase)
                        if grupo:                        # trozo: la escena solo con las piezas hechas hasta aquí
                            if not isinstance(d[cl], list):
                                raise ErrorRel(f"\"{cl}\" debe ser una lista")
                            if cl == "piezas":
                                nombres = [q.get("nombre") for q in d[cl] if isinstance(q, dict)]
                                fuera = [x for x in nombres if x not in grupo]
                                if fuera:
                                    raise ErrorRel(f"en este trozo van solo {', '.join(grupo)}; sobran "
                                                   f"{', '.join(map(str, fuera))} (ya están aprobadas o se piden después)")
                            completo["piezas"] = [dict(q, padre=q.get("padre") if q.get("padre") in hechas else None)
                                                  for q in completo["piezas"] if q.get("nombre") in hechas]
                        script = generar(completo, sin_relaciones_ok=(cl == "piezas"))
                        cs = comprobaciones_fase(id_, fase)
                    else:
                        parte = d
                        script = generar(d)
                        cs = T.TAREAS[id_]["comprobaciones"]
                except ErrorRel as err:
                    fila.update(parte=None, script=None, estado="ERROR_RESOLVEDOR", aprobado=False, cumplidas=0,
                                total=0, feedback=f"El programa no pudo construir la escena: {err}")
                    _guardar(evidencia, fila)
                    continue
                carpeta = Path(salida_blender) / modelo / f"{cond}_{id_}_{fase or 'todo'}_i{len(h) + 1}_{int(time.time())}"
                r, v = _probar(id_, cs, script, carpeta)
                pistas = como_arreglar(T.TAREAS[id_], v) if not v["aprobado"] else []
                fila.update(parte=parte, script=script, estado=r["estado"], aprobado=v["aprobado"],
                            cumplidas=v.get("cumplidas", 0), total=v.get("total", len(cs)),
                            feedback=v["texto"] + ("\n\nCÓMO ARREGLARLO:\n- " + "\n- ".join(pistas) if pistas else ""),
                            motivos_filtro=(r.get("filtro") or {}).get("motivos", []))
                _guardar(evidencia, fila)
    return "completo"


def pendientes(modelo, ids, evidencia) -> bool:
    filas = leer_filas(evidencia)
    return any(not estado(filas, modelo, c, i)["terminada"] for c in CONDICIONES for i in (ids or TAREAS_R2))


def informe(evidencia: Path) -> str:
    filas = leer_filas(evidencia)
    L = ["# Banco de Blender · relacional v2: informe", "",
         "| modelo | condición | tarea | resultado final | fases | llamadas | estados |", "|---|---|---|---|---|---|---|"]
    for m in dict.fromkeys(f["modelo"] for f in filas):
        for c in ("una_vez", "fases", "trozos"):
            for id_ in TAREAS_R2:
                fin = next((f for f in filas if f["modelo"] == m and f.get("condicion") == c and f["tarea"] == id_
                            and f.get("tipo") == "final"), None)
                if not fin:
                    continue
                hs = [f for f in filas if f["modelo"] == m and f.get("condicion") == c and f["tarea"] == id_
                      and f.get("tipo") != "final"]
                fases = f"{fin['fases_aprobadas']}/{fin['fases']}" if c != "una_vez" else "—"
                L.append(f"| {m} | {c} | {id_} | {'APROBADO' if fin['aprobado'] else 'no'} ({fin['cumplidas']}/"
                         f"{fin['total']}) | {fases} | {len(hs)} | "
                         f"{' · '.join((f.get('fase') or '')[:4] + (f.get('fase') or '@').partition('@')[2] + ':' + f['estado'] for f in hs)} |")
    texto = "\n".join(L) + "\n"
    (Path(evidencia) / "INFORME.md").write_text(texto, encoding="utf-8", newline="\n")
    return texto


def main(argv=None) -> int:
    global CONDICIONES
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("orden", choices=("ejecutar", "informe"))
    ap.add_argument("rutas", nargs="+")
    ap.add_argument("--modelos", nargs="+", default=["qwen25", "ministral3"])
    ap.add_argument("--condiciones", nargs="+", default=CONDICIONES, choices=("una_vez", "fases", "trozos"))
    ap.add_argument("--tareas", nargs="+", default=list(TAREAS_R2), choices=TAREAS_R2)
    ap.add_argument("--reanudar", action="store_true")
    ap.add_argument("--permitir_uso", action="store_true", help="el PC se usa a la vez: no mira teclado/ratón (VRAM, GPU y térmica siguen)")
    a = ap.parse_args(argv)
    if a.orden == "informe":
        print(informe(Path(a.rutas[0])))
        return 0
    CONDICIONES = list(a.condiciones)
    r = BB.ejecutar(Path(a.rutas[0]), Path(a.rutas[1]), Path(a.rutas[2]), tuple(a.modelos), list(a.tareas),
                    a.reanudar, correr=correr, pendientes_fn=pendientes,
                    permitir_uso=a.permitir_uso)
    print(json.dumps({k: r.get(k) for k in ("inicio", "fin", "abortada")}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
