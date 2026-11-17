"""Banco de flujos grandes · generador DETERMINISTA del proyecto sintético y de sus tareas con oráculo exacto.

El proyecto imita un sistema de logística en Python: muchos módulos, funciones parecidas entre sí (distractores)
y datos concretos escondidos en sitios conocidos. Como lo generamos nosotros, la respuesta correcta de cada
pregunta se sabe con exactitud y no puede venir del entrenamiento del cerebro. Mismo `SEMILLA` → mismos bytes.

Tipos de tarea:
  A  aguja dentro de una función (un número local), con funciones de nombre casi igual como distractores
  B  dos saltos: una función llama a otra de OTRO módulo; la respuesta está en la segunda
  C  agregación: contar cuántas funciones, repartidas por el proyecto, hacen una cosa concreta
  D  constante a nivel de módulo (no dentro de una función)
  E  dos rondas: la segunda pregunta depende de la respuesta de la primera
  R  preguntas sobre el código REAL de sistema/src/eq2 (oráculo leído con `ast`, no escrito a mano)
"""
from __future__ import annotations

import ast
import hashlib
import json
import random
import sys
from pathlib import Path

SEMILLA = 20261115
N_MODULOS = 80
FUNCIONES_POR_MODULO = 8
AQUI = Path(__file__).resolve().parent
REAL = AQUI.parent / "sistema" / "src" / "eq2"

AREAS = ["pagos", "envios", "aduanas", "almacen", "facturas", "rutas", "clientes", "inventario", "devoluciones",
         "proveedores"]
VERBOS = ["calcular", "validar", "procesar", "ajustar", "estimar", "revisar", "agrupar", "normalizar"]
OBJETOS = ["comision", "recargo", "descuento", "peso", "plazo", "margen", "tarifa", "lote", "turno", "cupo",
           "reserva", "saldo"]
ADJ = ["urgente", "nacional", "internacional", "mayorista", "minorista", "nocturno", "express", "fragil",
       "refrigerado", "estandar"]
CATEGORIAS = ["fraude", "precio", "acceso", "stock"]


def _nombre_funcion(rnd, usados):
    while True:
        n = f"{rnd.choice(VERBOS)}_{rnd.choice(OBJETOS)}_{rnd.choice(ADJ)}"
        if n not in usados:
            usados.add(n)
            return n


def _cuerpo_ruido(rnd, nombre, factor, extra_lineas):
    """Una función plausible y algo larga; `factor` es el número local que puede ser la aguja."""
    var = rnd.choice(["importe", "cantidad", "valor", "total"])
    L = [f"def {nombre}(registro, opciones=None):",
         f'    """{nombre.replace("_", " ").capitalize()} a partir del registro y las opciones de la sesión."""',
         "    opciones = opciones or {}",
         f"    {var} = float(registro.get('{var}', 0))",
         f"    factor = {factor}"]
    for i in range(extra_lineas):
        k = rnd.randint(2, 97)
        L += [f"    if registro.get('campo_{i}') is not None:",
              f"        {var} += (registro['campo_{i}'] % {k}) * 0.{rnd.randint(1, 9)}",
              f"    elif opciones.get('modo') == 'revision_{i}':",
              f"        {var} -= {k} / 10"]
    L += [f"    resultado = round({var} * factor / 100, 2)",
          "    return {'resultado': resultado, 'origen': '" + nombre + "'}", ""]
    return L


def generar(destino: Path) -> dict:
    rnd = random.Random(SEMILLA)
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=False)
    (destino / "__init__.py").write_text("", encoding="utf-8", newline="\n")
    usados, modulos = set(), []
    for m in range(N_MODULOS):
        area = AREAS[m % len(AREAS)]
        modulos.append({"nombre": f"{area}_{m:03d}", "area": area, "funciones": [], "constantes": {},
                        "importa": [], "auditoria": []})
    # funciones con su número local (todas tienen uno: todas son distractores posibles)
    for mod in modulos:
        for _ in range(FUNCIONES_POR_MODULO):
            mod["funciones"].append({"nombre": _nombre_funcion(rnd, usados), "factor": rnd.randint(101, 9899),
                                     "extra": rnd.randint(3, 7), "llama": None, "auditoria": None})
        for _ in range(3):
            c = f"LIMITE_{rnd.choice(OBJETOS).upper()}_{rnd.choice(ADJ).upper()}"
            mod["constantes"][c] = rnd.randint(11, 9973)
    tareas = []

    # A: agujas locales. Se elige una función y se pregunta por su factor por el nombre exacto.
    for i, m in enumerate(rnd.sample(range(N_MODULOS), 6)):
        f = rnd.choice(modulos[m]["funciones"])
        tareas.append({"id": f"A{i + 1}", "tipo": "A", "pregunta":
                       f"En el proyecto, la función `{f['nombre']}` asigna un número entero a la variable local "
                       f"`factor`. ¿Qué número es?", "respuesta": f["factor"], "clase": "entero",
                       "donde": [f"{modulos[m]['nombre']}.py::{f['nombre']}"]})

    # B: dos saltos. f (módulo a) llama a g (módulo b); se pregunta por el factor de g sin nombrarla.
    for i in range(4):
        a, b = rnd.sample(range(N_MODULOS), 2)
        f = rnd.choice([x for x in modulos[a]["funciones"] if x["llama"] is None])
        g = rnd.choice(modulos[b]["funciones"])
        f["llama"] = (modulos[b]["nombre"], g["nombre"])
        modulos[a]["importa"].append((modulos[b]["nombre"], g["nombre"]))
        tareas.append({"id": f"B{i + 1}", "tipo": "B", "pregunta":
                       f"La función `{f['nombre']}` llama a otra función definida en otro módulo del proyecto. "
                       f"¿Qué número entero asigna esa OTRA función a su variable local `factor`?",
                       "respuesta": g["factor"], "clase": "entero",
                       "donde": [f"{modulos[a]['nombre']}.py::{f['nombre']}", f"{modulos[b]['nombre']}.py::{g['nombre']}"]})

    # C: agregación. Para cada categoría, k funciones repartidas llaman a registrar_auditoria('<cat>').
    libres = [(mi, fi) for mi, mod in enumerate(modulos) for fi, f in enumerate(mod["funciones"])
              if f["llama"] is None]
    rnd.shuffle(libres)
    for i, cat in enumerate(CATEGORIAS[:3]):
        k = rnd.randint(4, 9)
        elegidas = [libres.pop() for _ in range(k)]
        for mi, fi in elegidas:
            modulos[mi]["funciones"][fi]["auditoria"] = cat
        tareas.append({"id": f"C{i + 1}", "tipo": "C", "pregunta":
                       f"¿Cuántas funciones del proyecto llaman a `registrar_auditoria` con la categoría "
                       f"'{cat}'? Cuenta todas las del proyecto.", "respuesta": k, "clase": "entero",
                       "pregunta_lista": f"Lista los nombres de TODAS las funciones de estos fragmentos que llaman a "
                                         f"`registrar_auditoria` con la categoría '{cat}'.",
                       "donde": [f"{modulos[mi]['nombre']}.py::{modulos[mi]['funciones'][fi]['nombre']}"
                                 for mi, fi in elegidas]})
    # la 4.ª categoría se usa como distractor, sin pregunta
    for _ in range(6):
        mi, fi = libres.pop()
        modulos[mi]["funciones"][fi]["auditoria"] = CATEGORIAS[3]

    # D: constantes de módulo
    for i, m in enumerate(rnd.sample(range(N_MODULOS), 3)):
        c, v = rnd.choice(sorted(modulos[m]["constantes"].items()))
        tareas.append({"id": f"D{i + 1}", "tipo": "D", "pregunta":
                       f"En el módulo `{modulos[m]['nombre']}`, ¿qué valor entero tiene la constante `{c}`?",
                       "respuesta": v, "clase": "entero", "donde": [f"{modulos[m]['nombre']}.py::{c}"]})

    # E: dos rondas. 1.ª: ¿a qué función llama f? 2.ª: ¿en qué módulo está esa función?
    for i in range(2):
        a, b = rnd.sample(range(N_MODULOS), 2)
        f = rnd.choice([x for x in modulos[a]["funciones"] if x["llama"] is None and x["auditoria"] is None])
        g = rnd.choice(modulos[b]["funciones"])
        f["llama"] = (modulos[b]["nombre"], g["nombre"])
        modulos[a]["importa"].append((modulos[b]["nombre"], g["nombre"]))
        tareas.append({"id": f"E{i + 1}", "tipo": "E", "rondas": [
            {"pregunta": f"La función `{f['nombre']}` llama a otra función de otro módulo del proyecto. "
                         f"¿Cómo se llama esa otra función?",
             "respuesta": g["nombre"], "clase": "nombre"},
            {"pregunta": "¿En qué módulo está definida esa función? Da el nombre del módulo, sin «.py».",
             "respuesta": modulos[b]["nombre"], "clase": "nombre"}],
            "donde": [f"{modulos[a]['nombre']}.py::{f['nombre']}", f"{modulos[b]['nombre']}.py::{g['nombre']}"]})

    # escribir los módulos
    for mod in modulos:
        L = [f'"""Módulo {mod["nombre"]}: operaciones de {mod["area"]} (proyecto sintético del banco de flujos)."""',
             "from __future__ import annotations", ""]
        L += ["from .comun import registrar_auditoria"]
        for (mb, g) in sorted(set(mod["importa"])):
            L.append(f"from .{mb} import {g}")
        L.append("")
        for c, v in mod["constantes"].items():
            L.append(f"{c} = {v}")
        L.append("")
        for f in mod["funciones"]:
            cuerpo = _cuerpo_ruido(rnd, f["nombre"], f["factor"], f["extra"])
            ret = cuerpo[-2]
            extra = []
            if f["auditoria"]:
                extra.append(f"    registrar_auditoria('{f['auditoria']}', origen='{f['nombre']}')")
            if f["llama"]:
                extra.append(f"    complemento = {f['llama'][1]}(registro, opciones)")
                extra.append("    resultado += complemento['resultado']")
            L += cuerpo[:-2] + extra + [ret, ""]
        (destino / f"{mod['nombre']}.py").write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")
    (destino / "comun.py").write_text(
        '"""Utilidades comunes."""\n\n\ndef registrar_auditoria(categoria, origen=None):\n'
        '    """Anota una entrada de auditoría (en el proyecto sintético no hace nada)."""\n'
        '    return {"categoria": categoria, "origen": origen}\n', encoding="utf-8", newline="\n")

    tareas += trampas(modulos, usados)
    tareas += parafrasis(tareas, modulos)
    tareas += tareas_reales()
    tareas += tareas_t6()
    manifiesto = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(destino.glob("*.py"))}
    total_chars = sum(p.stat().st_size for p in destino.glob("*.py"))
    return {"semilla": SEMILLA, "modulos": N_MODULOS + 2, "caracteres": total_chars,
            "tokens_estimados": total_chars // 3, "tareas": tareas, "manifiesto_sha256": manifiesto}


def trampas(modulos: list, usados: set) -> list:
    """Preguntas cuya respuesta correcta es «no existe». Usa su PROPIO generador aleatorio: el corpus no cambia.
    T1 función inexistente · T2 constante casi igual a una que SÍ hay en ese módulo · T3 variable que la función no tiene."""
    rnd = random.Random(SEMILLA + 1)
    todas_constantes = {c for m in modulos for c in m["constantes"]}
    while True:
        f = f"{rnd.choice(VERBOS)}_{rnd.choice(OBJETOS)}_{rnd.choice(ADJ)}"
        if f not in usados:
            break
    mod = rnd.choice(modulos)
    real = sorted(mod["constantes"])[0]
    pre = real.rsplit("_", 1)[0]
    casi = next(f"{pre}_{a.upper()}" for a in ADJ if f"{pre}_{a.upper()}" not in todas_constantes)
    m3 = rnd.choice(modulos)
    g = rnd.choice(m3["funciones"])
    return [
        {"id": "T1", "tipo": "T", "pregunta": f"En el proyecto, la función `{f}` asigna un número entero a la variable "
         "local `factor`. ¿Qué número es?", "respuesta": "NO_ENCONTRADO", "clase": "ausente", "donde": []},
        {"id": "T2", "tipo": "T", "pregunta": f"En el módulo `{mod['nombre']}`, ¿qué valor entero tiene la constante "
         f"`{casi}`?", "respuesta": "NO_ENCONTRADO", "clase": "ausente", "donde": [], "parecida": real},
        {"id": "T3", "tipo": "T", "pregunta": f"En el proyecto, la función `{g['nombre']}` asigna un número entero a la "
         "variable local `limite_diario`. ¿Qué número es?", "respuesta": "NO_ENCONTRADO", "clase": "ausente",
         "donde": [], "parecida": f"factor = {g['factor']}"},
    ]


SIN_VERBO = {"calcular": "computa", "validar": "comprueba", "procesar": "tramita", "ajustar": "corrige",
             "estimar": "aproxima", "revisar": "examina", "agrupar": "junta", "normalizar": "uniformiza"}
SIN_OBJETO = {"comision": "el porcentaje que se cobra", "recargo": "el cargo adicional", "descuento": "la rebaja",
              "peso": "los kilos", "plazo": "el tiempo de entrega", "margen": "la ganancia", "tarifa": "el precio base",
              "lote": "la partida", "turno": "el horario", "cupo": "el límite de unidades", "reserva": "lo apartado",
              "saldo": "el balance"}
SIN_ADJ = {"urgente": "de los envíos con prisa", "nacional": "dentro del país", "internacional": "hacia el extranjero",
           "mayorista": "de los grandes clientes", "minorista": "de los clientes pequeños", "nocturno": "de noche",
           "express": "de los envíos rápidos", "fragil": "de la mercancía delicada", "refrigerado": "de la carga en frío",
           "estandar": "de los envíos normales"}


def describir(nombre: str, nivel: str) -> str:
    """Describe una función por lo que hace, sin su nombre. «total»: todo sinónimos; «parcial»: conserva el objeto."""
    v, o, a = nombre.split("_")
    art = "la" if o in ("comision", "tarifa", "reserva") else "el"
    objeto = f"{art} {o}" if nivel == "parcial" else SIN_OBJETO[o]
    return f"{SIN_VERBO[v]} {objeto} {SIN_ADJ[a]}"


def parafrasis(tareas: list, modulos: list) -> list:
    """Las mismas búsquedas de A, B, D y la trampa T1, sin escribir el identificador exacto (tanda 4).
    Determinista: no usa el generador aleatorio, así que el corpus y las demás tareas no cambian."""
    out = []
    por_id = {t["id"]: t for t in tareas}
    for nivel, sufijo in (("parcial", "p"), ("total", "t")):
        for t in [x for x in tareas if x["tipo"] == "A"]:
            f = t["donde"][0].split("::")[1]
            out.append({**t, "id": f"P{t['id']}{sufijo}", "tipo": "P", "tipo_origen": t["tipo"], "origen": t["id"], "nivel": nivel,
                        "pregunta": f"En el proyecto hay una función que {describir(f, nivel)}. ¿Qué número entero "
                                    "asigna a su variable local `factor`?"})
        for t in [x for x in tareas if x["tipo"] == "B"]:
            f = t["donde"][0].split("::")[1]
            out.append({**t, "id": f"P{t['id']}{sufijo}", "tipo": "P", "tipo_origen": t["tipo"], "origen": t["id"], "nivel": nivel,
                        "pregunta": f"La función que {describir(f, nivel)} llama a otra función definida en otro "
                                    "módulo. ¿Qué número entero asigna esa OTRA función a su variable local `factor`?"})
    for t in [x for x in tareas if x["tipo"] == "D"]:
        c = t["donde"][0].split("::")[1]
        o, a = c.lower().split("_")[1:]
        mod = t["donde"][0].split(".py")[0]
        out.append({**t, "id": f"P{t['id']}t", "tipo": "P", "tipo_origen": t["tipo"], "origen": t["id"], "nivel": "total",
                    "pregunta": f"En el módulo {mod}, ¿qué valor entero tiene la constante del límite de "
                                f"{SIN_OBJETO[o].split(' ', 1)[1]} {SIN_ADJ[a]}?"})
    t1 = por_id["T1"]
    f = t1["pregunta"].split("`")[1]
    for nivel, sufijo in (("parcial", "p"), ("total", "t")):
        out.append({**t1, "id": f"PT1{sufijo}", "tipo": "P", "tipo_origen": "T", "origen": "T1", "nivel": nivel,
                    "pregunta": f"En el proyecto hay una función que {describir(f, nivel)}. ¿Qué número entero "
                                "asigna a su variable local `factor`?"})
    return out


NATURALES_T6 = [  # (pregunta como la haría una persona, archivo, constante que la responde)
    ("¿Cuántos tokens como máximo puede pedir el sistema en una sola respuesta del modelo?", "config.py", "TOPE_MAX_TOKENS"),
    ("Cuando una respuesta del modelo se corta, ¿cuántos tokens como máximo se piden para continuarla?", "config.py",
     "MAX_TOKENS_CONTINUACION"),
    ("¿Cuántas continuaciones de una respuesta cortada se permiten como máximo en cada fase?", "config.py",
     "MAX_CONTINUACIONES_POR_FASE"),
    ("¿En qué puerto escucha el servidor local del modelo?", "config.py", "PUERTO"),
    ("¿Cuántos hilos de CPU usa por defecto el servidor del modelo?", "config.py", "HILOS"),
    ("¿Cuántas tareas como máximo se pueden hacer en una misma sesión?", "config.py", "MAX_TAREAS_SESION"),
    ("¿Cuántas llamadas al modelo se permiten como máximo por cada tarea?", "config.py", "MAX_LLAMADAS_TAREA"),
    ("¿Cuántas llamadas al modelo puede hacer como máximo el motor de programación?", "config.py", "MOTOR_MAX_LLAMADAS"),
    ("¿Cuántos segundos como máximo se esperan por cada llamada al modelo?", "config.py", "SEG_POR_LLAMADA"),
    ("¿Con qué porcentaje de batería, o menos, se niega a seguir trabajando el sistema?", "config.py", "BATERIA_MIN_PCT"),
    ("¿Cuántas memorias guardadas se incluyen como máximo en cada prompt?", "config.py", "MEMORIAS_POR_PROMPT"),
    ("¿Cuántos megabytes de memoria tiene como límite el ejecutor de código?", "config.py", "EJECUTOR_MEM_MB"),
    ("¿Cuántos segundos como máximo puede durar cada ejecución del ejecutor de código?", "config.py",
     "EJECUTOR_SEG_POR_EJECUCION"),
    ("¿Cuántas veces como máximo intenta el motor corregir el código que falla?", "config.py",
     "MOTOR_MAX_ITERACIONES_CORRECCION"),
    ("En el debate entre agentes, ¿cuántos casos de prueba puede llevar como máximo una propuesta?", "debate.py",
     "MAX_CASOS_PROPUESTA"),
    ("¿Cuántas objeciones como máximo se admiten en una crítica?", "criticas.py", "MAX_OBJECIONES"),
    ("¿Cuántas horas tienen que pasar como mínimo entre dos propuestas de cambio de personalidad?", "config.py",
     "PERSONALIDAD_HORAS_ENTRE_PROPUESTAS"),
    ("Al unir una respuesta cortada con su continuación, ¿cuántos caracteres de solapamiento mínimo se exigen?",
     "integridad.py", "MIN_SOLAPE"),
]
EXACTAS_T6 = [("config.py", "MARGEN_CTX"), ("config.py", "MIN_TOKENS_CONTINUACION"), ("casos.py", "MAX_CASOS"),
              ("asesoria.py", "MAX_CHARS")]
TRAMPAS_T6 = [  # comprobado con ast al generar: estos nombres NO existen en sistema/src/eq2
    ("En `config.py`, ¿qué valor entero tiene `MAX_REINTENTOS_RED`?", "MAX_REINTENTOS_RED"),
    ("¿Cuántos gigabytes de VRAM reserva el sistema como mínimo para el modelo?", "VRAM_MINIMA_GB"),
]


def tareas_t6() -> list:
    """Tanda 6: preguntas sobre el código REAL (sistema/src/eq2) escritas como las haría una persona. La respuesta se
    lee con ast al generar (no a mano); los nombres de las trampas se comprueban ausentes. Sin azar."""
    nombres = set()
    for f in REAL.glob("*.py"):
        for n in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(n, ast.Name):
                nombres.add(n.id)
            elif isinstance(n, (ast.FunctionDef, ast.ClassDef)):
                nombres.add(n.name)
    out = []
    for i, (q, archivo, c) in enumerate(NATURALES_T6, 1):
        out.append({"id": f"N{i}", "tipo": "N", "raiz": "real", "pregunta": q, "clase": "entero",
                    "respuesta": _constante_ast(REAL / archivo, c), "donde": [f"{archivo}::{c}"]})
    for i, (archivo, c) in enumerate(EXACTAS_T6, 1):
        out.append({"id": f"X{i}", "tipo": "X", "raiz": "real", "clase": "entero",
                    "pregunta": f"En `{archivo}`, ¿qué valor entero tiene `{c}`?",
                    "respuesta": _constante_ast(REAL / archivo, c), "donde": [f"{archivo}::{c}"]})
    for i, (q, falso) in enumerate(TRAMPAS_T6, 1):
        assert falso not in nombres, f"la trampa {falso} existe en el código real"
        out.append({"id": f"U{i}", "tipo": "U", "raiz": "real", "pregunta": q, "clase": "ausente",
                    "respuesta": "NO_ENCONTRADO", "donde": []})
    return out


def _constante_ast(ruta: Path, nombre: str):
    for n in ast.parse(ruta.read_text(encoding="utf-8")).body:
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == nombre for t in n.targets):
            return ast.literal_eval(n.value)
    raise KeyError(nombre)


def tareas_reales() -> list:
    """Preguntas sobre sistema/src/eq2; la respuesta se lee del código con ast en el momento de generar."""
    debate = _constante_ast(REAL / "debate.py", "TOKENS_DEBATE")
    return [
        {"id": "R1", "tipo": "R", "pregunta": "En `config.py`, ¿qué valor entero tiene `TOPE_MAX_TOKENS`?",
         "respuesta": _constante_ast(REAL / "config.py", "TOPE_MAX_TOKENS"), "clase": "entero",
         "donde": ["config.py::TOPE_MAX_TOKENS"]},
        {"id": "R2", "tipo": "R", "pregunta": "En `config.py`, ¿qué valor entero tiene `MAX_TOKENS_CONTINUACION`?",
         "respuesta": _constante_ast(REAL / "config.py", "MAX_TOKENS_CONTINUACION"), "clase": "entero",
         "donde": ["config.py::MAX_TOKENS_CONTINUACION"]},
        {"id": "R3", "tipo": "R", "pregunta": "En `debate.py`, la tabla `TOKENS_DEBATE` fija tokens por contexto. Con "
         "contexto 2048, ¿cuántos tokens tiene la clase \"propuesta\"?", "respuesta": debate[2048]["propuesta"],
         "clase": "entero", "donde": ["debate.py::TOKENS_DEBATE"]},
        {"id": "R4", "tipo": "R", "pregunta": "En `integridad.py`, ¿qué valor entero tiene `MIN_SOLAPE`?",
         "respuesta": _constante_ast(REAL / "integridad.py", "MIN_SOLAPE"), "clase": "entero",
         "donde": ["integridad.py::MIN_SOLAPE"]},
    ]


if __name__ == "__main__":
    salida = Path(sys.argv[1])
    datos = generar(salida / "corpus")
    (salida / "tareas.json").write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in datos.items() if k not in ("tareas", "manifiesto_sha256")}, ensure_ascii=False))
    print("tareas:", len(datos["tareas"]), [t["id"] for t in datos["tareas"]])
