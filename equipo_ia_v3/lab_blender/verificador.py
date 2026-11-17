"""Verificador SIN IA de escenas de Blender (laboratorio): compara los hechos del informe con lo que pide la tarea.

    python -B -X utf8 lab_blender/verificador.py TAREA CARPETA_DE_EJECUCION

Cada tarea (lab_blender/tareas.py) lleva una lista de comprobaciones medibles: nombres, medidas, posiciones, colores, padres,
contacto entre piezas, apoyo en el suelo, movimiento entre fotogramas. Aquí no opina ningún modelo: una comprobación se
cumple o no, y dice lo medido. El texto de los fallos es lo que se le devuelve al cerebro para que corrija.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

TOL = 0.05                                                   # metros
GEOMETRIA = ("MESH", "CURVE", "SURFACE", "FONT", "META")


class Falta(Exception):
    """Un objeto que la comprobación necesita no existe."""


def _ob(E: dict, nombre: str) -> dict:
    for o in E.get("objetos", []):
        if o["nombre"] == nombre:
            return o
    raise Falta(f"no existe ningún objeto llamado «{nombre}» (hay: {', '.join(o['nombre'] for o in E.get('objetos', [])[:12]) or 'ninguno'})")


def _cerca(a, b, tol) -> bool:
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def _f(v) -> str:
    return "(" + ", ".join(f"{x:.2f}" for x in v) + ")"


def _momentos(o: dict) -> list:
    """Cajas del objeto en cada fotograma de muestra (o la única que hay)."""
    return o.get("muestras") or [{"fotograma": None, "posicion": o["posicion"], "rotacion_grados": o["rotacion_grados"],
                                  "caja_min": o["caja_min"], "caja_max": o["caja_max"]}]


def _hueco(a: dict, b: dict) -> float:
    """Separación entre dos cajas (0 si se tocan o se solapan)."""
    return max(max(0.0, a["caja_min"][i] - b["caja_max"][i], b["caja_min"][i] - a["caja_max"][i]) for i in range(3))


# --- comprobaciones: cada una devuelve (cumple, lo medido) ----------------------------------------------------------------
def solo(E, nombres):
    hay = sorted(o["nombre"] for o in E["objetos"] if o["tipo"] in GEOMETRIA)
    return hay == sorted(nombres), f"objetos con geometría: {', '.join(hay) or 'ninguno'}; se piden exactamente: {', '.join(sorted(nombres))}"


def existe(E, nombre, tipo=None):
    o = _ob(E, nombre)
    return (tipo is None or o["tipo"] == tipo), f"«{nombre}» es de tipo {o['tipo']}" + (f"; se pide {tipo}" if tipo else "")


def posicion(E, nombre, xyz, tol=TOL):
    o = _ob(E, nombre)
    return _cerca(o["posicion"], xyz, tol), f"«{nombre}» está en {_f(o['posicion'])}; se pide {_f(xyz)}"


def centro(E, nombre, xyz, tol=TOL):
    o = _ob(E, nombre)
    c = [(a + b) / 2 for a, b in zip(o["caja_min"], o["caja_max"])]
    return _cerca(c, xyz, tol), f"el centro de «{nombre}» está en {_f(c)}; se pide {_f(xyz)}"


def dimensiones(E, nombre, xyz, tol=TOL):
    o = _ob(E, nombre)
    d = [b - a for a, b in zip(o["caja_min"], o["caja_max"])]
    return _cerca(d, xyz, tol), f"«{nombre}» mide {_f(d)} m; se pide {_f(xyz)}"


def color(E, nombre, rgb, tol=0.12):
    o = _ob(E, nombre)
    vistos = [c["nodos"] for c in o.get("colores", []) if c and c.get("nodos")]
    if not vistos:
        solo_vista = [c["vista"] for c in o.get("colores", []) if c]
        return False, (f"«{nombre}» no tiene material con color de render" +
                       (f" (solo cambia el color de la vista 3D, {_f(solo_vista[0][:3])}: en Blender 5 el color del render "
                        "es el Base Color del nodo Principled BSDF)" if solo_vista else ""))
    ok = any(_cerca(c[:3], rgb, tol) for c in vistos)
    return ok, f"el color de render de «{nombre}» es {_f(vistos[0][:3])}; se pide {_f(rgb)}"


def desciende(E, nombre, antepasado):
    o, cadena = _ob(E, nombre), []
    while o.get("padre") and len(cadena) < 50:
        cadena.append(o["padre"])
        if o["padre"] == antepasado:
            return True, f"«{nombre}» cuelga de «{antepasado}»"
        o = _ob(E, o["padre"])
    return False, f"«{nombre}» no cuelga de «{antepasado}» (su padre es {cadena[0] if cadena else 'ninguno'})"


def toca(E, a, b, tol=0.02):
    A, B = _momentos(_ob(E, a)), _momentos(_ob(E, b))
    peor = max(_hueco(x, y) for x, y in zip(A, B))
    return peor <= tol, (f"«{a}» y «{b}» se tocan" if peor <= tol else
                         f"«{a}» y «{b}» están separados {peor:.2f} m" + (" en algún fotograma" if len(A) > 1 else ""))


def apoyado(E, nombre, z=0.0, tol=0.02):
    zs = [m["caja_min"][2] for m in _momentos(_ob(E, nombre))]
    ok = all(abs(v - z) <= tol for v in zs)
    return ok, f"la base de «{nombre}» está a z = {min(zs):.2f}" + (f"…{max(zs):.2f}" if max(zs) - min(zs) > tol else "") + f"; se pide {z:.2f}"


def no_se_hunde(E, nombres, z=0.0, tol=0.02):
    peor = min((m["caja_min"][2], n) for n in nombres for m in _momentos(_ob(E, n)))
    return peor[0] >= z - tol, f"el punto más bajo es z = {peor[0]:.2f} («{peor[1]}»); no debe bajar de {z:.2f}"


def simetricos(E, a, b, tol=TOL):
    A, B = _ob(E, a), _ob(E, b)
    ca = [(x + y) / 2 for x, y in zip(A["caja_min"], A["caja_max"])]
    cb = [(x + y) / 2 for x, y in zip(B["caja_min"], B["caja_max"])]
    ok = abs(ca[0] + cb[0]) <= tol and abs(ca[1] - cb[1]) <= tol and abs(ca[2] - cb[2]) <= tol and abs(ca[0]) > tol
    return ok, f"«{a}» está en {_f(ca)} y «{b}» en {_f(cb)}; se piden simétricos respecto al plano x = 0"


def lado(E, nombre, signo):
    o = _ob(E, nombre)
    x = (o["caja_min"][0] + o["caja_max"][0]) / 2
    return (x < 0) == (signo < 0) and abs(x) > 0.01, f"«{nombre}» está en x = {x:.2f}; se pide x {'negativa' if signo < 0 else 'positiva'}"


def a_un_lado(E, a, b, signo, tol=0.02):
    """«a» queda por fuera del lado x negativo (signo < 0) o positivo de «b» y a su altura (no debajo ni metida dentro)."""
    A, B = _ob(E, a), _ob(E, b)
    fuera = A["caja_max"][0] <= B["caja_min"][0] + tol if signo < 0 else A["caja_min"][0] >= B["caja_max"][0] - tol
    altura = min(A["caja_max"][2], B["caja_max"][2]) - max(A["caja_min"][2], B["caja_min"][2]) > tol
    return fuera and altura, (f"«{a}» ocupa x de {A['caja_min'][0]:.2f} a {A['caja_max'][0]:.2f} y z de "
                              f"{A['caja_min'][2]:.2f} a {A['caja_max'][2]:.2f}; «{b}» ocupa x de {B['caja_min'][0]:.2f} a "
                              f"{B['caja_max'][0]:.2f} y z de {B['caja_min'][2]:.2f} a {B['caja_max'][2]:.2f}; se pide "
                              f"«{a}» por fuera del lado x {'negativo' if signo < 0 else 'positivo'} de «{b}» y a su altura")


def _hundido(a: dict, b: dict) -> float:
    """Cuánto se meten dos cajas una en otra (0 si solo se tocan o están separadas)."""
    return max(0.0, min(min(a["caja_max"][i], b["caja_max"][i]) - max(a["caja_min"][i], b["caja_min"][i])
                        for i in range(3)))


def sin_solapes(E, nombres, tol=0.02):
    peor = (0.0, None, None)
    for i, a in enumerate(nombres):
        for b in nombres[i + 1:]:
            for x, y in zip(_momentos(_ob(E, a)), _momentos(_ob(E, b))):
                h = _hundido(x, y)
                if h > peor[0]:
                    peor = (h, a, b)
    return peor[0] <= tol, ("ninguna pieza se mete dentro de otra" if peor[0] <= tol else
                            f"«{peor[1]}» y «{peor[2]}» se meten {peor[0]:.2f} m una dentro de la otra")


# --- tanda 13: formas, articulaciones y caminata ------------------------------------------------------------------------
VERTICES_FORMA = {"caja": 8, "cilindro": 64, "esfera": 266, "cono": 33, "cuna": 6}   # primitivas del generador de relacional2.py


def forma(E, nombre, tipo):
    o = _ob(E, nombre)
    v = o.get("vertices")
    hay = next((k for k, n in VERTICES_FORMA.items() if n == v), f"otra ({v} vértices)")
    return hay == tipo, f"«{nombre}» tiene forma de {hay}; se pide {tipo}"


def delante_de(E, a, b, tol=0.02):
    """«a» pegada a la cara delantera (y negativa) de «b»."""
    A, B = _ob(E, a), _ob(E, b)
    ca = (A["caja_min"][1] + A["caja_max"][1]) / 2
    ok = ca <= B["caja_min"][1] + tol and _hueco(A, B) <= tol
    return ok, (f"el centro de «{a}» está en y = {ca:.2f}, la cara delantera de «{b}» en y = {B['caja_min'][1]:.2f} y "
                f"están separados {_hueco(A, B):.2f} m; se pide «{a}» pegada a la cara delantera (y negativa) de «{b}»")


def pivote(E, nombre, padre, tol=0.02):
    """El origen de «nombre» (su articulación) está en el centro de su cara de arriba y no se separa de «padre»."""
    o, p = _ob(E, nombre), _ob(E, padre)
    arriba = [(o["caja_min"][0] + o["caja_max"][0]) / 2, (o["caja_min"][1] + o["caja_max"][1]) / 2, o["caja_max"][2]]
    en_sitio = _cerca(o["posicion"], arriba, tol)
    rel = [[a - b for a, b in zip(x["posicion"], y["posicion"])] for x, y in zip(_momentos(o), _momentos(p))]
    fijo = all(_cerca(r, rel[0], tol) for r in rel)
    return en_sitio and fijo, (f"la articulación de «{nombre}» está en {_f(o['posicion'])}; el centro de su cara de "
                               f"arriba en {_f(arriba)}" + ("" if fijo else f"; y se separa de «{padre}» al moverse"))


def balanceo(E, nombre, eje, grados, tol=6.0):
    r = [m["rotacion_grados"][eje] for m in _momentos(_ob(E, nombre))]
    ok = max(r) >= grados - tol and min(r) <= -grados + tol and max(abs(x) for x in r) <= grados + tol
    return ok, (f"«{nombre}» gira en {'XYZ'[eje]}: {', '.join(f'{x:.0f}' for x in r)}°; se pide un balanceo de "
                f"±{grados:.0f}°")


def contrafase(E, a, b, eje, umbral=5.0):
    ra = [m["rotacion_grados"][eje] for m in _momentos(_ob(E, a))]
    rb = [m["rotacion_grados"][eje] for m in _momentos(_ob(E, b))]
    activos = [(x, y) for x, y in zip(ra, rb) if abs(x) > umbral or abs(y) > umbral]
    ok = bool(activos) and all(x * y < 0 for x, y in activos)
    return ok, (f"giros en {'XYZ'[eje]} de «{a}»: {', '.join(f'{x:.0f}' for x in ra)}; de «{b}»: "
                f"{', '.join(f'{x:.0f}' for x in rb)}; se pide que vayan siempre en sentidos contrarios")


def recto_en_extremos(E, nombre, tol=3.0):
    m = _momentos(_ob(E, nombre))
    r = [m[0]["rotacion_grados"], m[-1]["rotacion_grados"]]
    ok = all(abs(x) <= tol for x in r[0] + r[1])
    return ok, f"«{nombre}» está girada {_f(r[0])}° al principio y {_f(r[1])}° al final; se pide recta (0°)"


# --- tanda 14: componentes ------------------------------------------------------------------------------------------------
def concentricos(E, a, b, tol=0.02):
    A, B = _ob(E, a), _ob(E, b)
    ca = [(x + y) / 2 for x, y in zip(A["caja_min"], A["caja_max"])]
    cb = [(x + y) / 2 for x, y in zip(B["caja_min"], B["caja_max"])]
    return _cerca(ca, cb, tol), f"el centro de «{a}» está en {_f(ca)} y el de «{b}» en {_f(cb)}; se piden iguales"


def conectado(E, nombres, tol=0.02):
    """Todas las piezas forman un solo bloque: cada una toca (o se mete en) alguna otra del grupo."""
    obs = {n: _ob(E, n) for n in nombres}
    vistos, pila = {nombres[0]}, [nombres[0]]
    while pila:
        x = pila.pop()
        for y in nombres:
            if y not in vistos and _hueco(obs[x], obs[y]) <= tol:
                vistos.add(y)
                pila.append(y)
    sueltas = [n for n in nombres if n not in vistos]
    return not sueltas, ("todas las piezas están unidas" if not sueltas else
                         f"piezas sueltas, que no tocan al resto: {', '.join(sueltas)}")


def caja_total(E, nombres, medidas, tol=0.02):
    """La caja que ocupa el grupo mide lo declarado (la ficha del componente)."""
    obs = [_ob(E, n) for n in nombres]
    d = [max(o["caja_max"][i] for o in obs) - min(o["caja_min"][i] for o in obs) for i in range(3)]
    return _cerca(d, medidas, tol), f"el conjunto ocupa {_f(d)} m; su ficha declara {_f(medidas)}"


def en_reposo(E, comprobacion):
    """Evalúa otra comprobación solo en la postura de reposo (fotograma inicial), sin los fotogramas de muestra."""
    E2 = {**E, "objetos": [{k: v for k, v in o.items() if k != "muestras"} for o in E["objetos"]]}
    nombre, *args = comprobacion
    return COMPROBACIONES[nombre](E2, *args)


def encima(E, a, b, tol=0.02):
    A, B = _ob(E, a), _ob(E, b)
    ok = A["caja_min"][2] >= B["caja_max"][2] - tol and all(
        A["caja_min"][i] <= B["caja_max"][i] and B["caja_min"][i] <= A["caja_max"][i] for i in (0, 1))
    return ok, f"la base de «{a}» está a z = {A['caja_min'][2]:.2f} y lo alto de «{b}» a z = {B['caja_max'][2]:.2f}"


def desplazamiento(E, nombre, xyz, tol=TOL):
    m = _momentos(_ob(E, nombre))
    d = [b - a for a, b in zip(m[0]["posicion"], m[-1]["posicion"])]
    return _cerca(d, xyz, tol), f"«{nombre}» se desplaza {_f(d)} del primer al último fotograma; se pide {_f(xyz)}"


def giro(E, nombre, eje, grados, tol=2.0):
    m = _momentos(_ob(E, nombre))
    d = (m[-1]["rotacion_grados"][eje] - m[0]["rotacion_grados"][eje] + 180) % 360 - 180
    ok = abs((d - grados + 180) % 360 - 180) <= tol
    return ok, f"«{nombre}» gira {d:.1f}° en el eje {'XYZ'[eje]} del primer al último fotograma; se pide {grados:.1f}°"


def fotogramas(E, inicio, fin, fps=None):
    ok = E["fotograma_inicial"] == inicio and E["fotograma_final"] == fin and (fps is None or abs(E["fps"] - fps) < 0.01)
    return ok, (f"la escena va del fotograma {E['fotograma_inicial']} al {E['fotograma_final']} a {E['fps']:g} fps; se pide "
                f"{inicio}–{fin}" + (f" a {fps} fps" if fps else ""))


def huesos(E, nombre, lista):
    o = _ob(E, nombre)
    hay = o.get("huesos") or []
    faltan = [h for h in lista if h not in hay]
    return o["tipo"] == "ARMATURE" and not faltan, (f"«{nombre}» es {o['tipo']} con huesos: {', '.join(hay) or 'ninguno'}" +
                                                    (f"; faltan: {', '.join(faltan)}" if faltan else ""))


def alternan(E, a, b, altura, suelo=0.03):
    A = [m["caja_min"][2] for m in _momentos(_ob(E, a))]
    B = [m["caja_min"][2] for m in _momentos(_ob(E, b))]
    a_solo = any(x >= altura and y <= suelo for x, y in zip(A, B))
    b_solo = any(y >= altura and x <= suelo for x, y in zip(A, B))
    los_dos = any(x > suelo and y > suelo for x, y in zip(A, B))
    return a_solo and b_solo and not los_dos, (
        f"altura de «{a}» en las muestras: {', '.join(f'{x:.2f}' for x in A)}; de «{b}»: {', '.join(f'{x:.2f}' for x in B)}; "
        f"se pide que cada uno suba al menos {altura:.2f} m mientras el otro está en el suelo, y nunca los dos en el aire")


COMPROBACIONES = {f.__name__: f for f in (solo, existe, posicion, centro, dimensiones, color, desciende, toca, apoyado,
                                          no_se_hunde, simetricos, lado, a_un_lado, sin_solapes, forma, delante_de, pivote, balanceo, contrafase,
                                          recto_en_extremos, en_reposo, concentricos, conectado, caja_total, encima, desplazamiento, giro, fotogramas, huesos,
                                          alternan)}


def verificar(tarea: dict, resultado: dict) -> dict:
    """`resultado` es el de ejecutor.ejecutar. Devuelve aprobado, las comprobaciones y el texto para el cerebro."""
    estado = resultado.get("estado")
    inf = resultado.get("informe") or {}
    if estado != "OK":
        return {"aprobado": False, "estado": estado, "comprobaciones": [], "texto": texto_de_estado(resultado)}
    E, filas = inf["escena"], []
    for nombre, *args in tarea["comprobaciones"]:
        try:
            ok, medido = COMPROBACIONES[nombre](E, *args)
        except Falta as e:
            ok, medido = False, str(e)
        filas.append({"comprobacion": nombre, "args": args, "cumple": bool(ok), "medido": medido})
    fallos = [f["medido"] for f in filas if not f["cumple"]]
    vistos, unicos = set(), []
    for f in fallos:                                         # el mismo objeto que falta no se repite diez veces
        if f not in vistos:
            vistos.add(f)
            unicos.append(f)
    return {"aprobado": not fallos, "estado": estado, "comprobaciones": filas, "cumplidas": len(filas) - len(fallos),
            "total": len(filas), "texto": "todo correcto" if not fallos else "\n".join(f"- {f}" for f in unicos[:8])}


def texto_de_estado(r: dict) -> str:
    e, inf = r.get("estado"), r.get("informe") or {}
    if e == "RECHAZADO":
        return "El script no pasó el filtro de seguridad y NO se ejecutó:\n" + "\n".join(f"- {m}" for m in r["filtro"]["motivos"][:6])
    if e == "ERROR_SCRIPT":
        s = inf["script"]
        return (f"El script falló al ejecutarse en la línea {s.get('linea')}: {s.get('error')}\n"
                f"  código de esa línea: {s.get('codigo_de_la_linea')}")
    if e == "TIEMPO":
        return f"El script tardó más de {r['limites']['tiempo_s']:.0f} s y se cortó (¿un bucle sin fin?)."
    if e == "MEMORIA":
        return "El script gastó demasiada memoria y se cortó."
    if e == "LIMITE":
        return "La escena supera los límites: " + "; ".join(inf["escena"]["limites_superados"])
    return f"Blender no terminó bien ({e})."


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import tareas
    r = json.loads((Path(sys.argv[2]) / "resultado.json").read_text(encoding="utf-8"))
    v = verificar(tareas.TAREAS[sys.argv[1]], r)
    print("APROBADO" if v["aprobado"] else "NO APROBADO", f"({v.get('cumplidas', 0)}/{v.get('total', 0)})")
    print(v["texto"])
