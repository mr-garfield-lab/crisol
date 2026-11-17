"""Banco de revisión de código: ¿encuentra el cerebro los errores que impiden compilar, señala la línea correcta y los
arregla sin tocar lo que estaba bien? Python y Java. Sin código malicioso ni errores de lógica (tandas futuras).

Órdenes (desde equipo_ia_v3/):
  preparar <evidencia>                       corpus de 32 casos y validación: las herramientas SIN IA deben encontrar
                                             exactamente los errores plantados (si no, no se sigue)
  ejecutar <externos> <evidencia> [--reanudar] [--modelos …]
  informe <evidencia>

Condiciones:
  solo         el cerebro revisa solo, un intento.
  herramienta  la herramienta (compilador / analizador) encuentra los errores; el cerebro los explica y arregla; se
               vuelve a compilar y, si sigue fallando, recibe los errores nuevos con su línea (hasta 3 intentos). Si la
               herramienta no encuentra nada, no se pregunta al cerebro.
El código del cerebro NUNCA se ejecuta: solo se compila / analiza (regla de seguridad del proyecto).
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
RAIZ = AQUI.parent
for p in (str(RAIZ), str(AQUI), str(RAIZ / "lab_flujos")):
    if p not in sys.path:
        sys.path.insert(0, p)
import corpus as C  # noqa: E402
import herramientas as H  # noqa: E402

MODELOS = ("qwen25", "ministral3")
CONDICIONES = ("solo", "herramienta")             # tanda 1
CONDICIONES_T3 = ("herramienta3",)                # tanda 3: + órdenes anidadas y aviso de import recolocado
CONDICIONES_T2 = ("herramienta2",)                # tanda 2: imports colocados y aviso de arreglo repetido
MAX_INTENTOS = 3
TOKENS = 500

FORMATO = (
    "El código lleva delante el número de cada línea («12| …»). Responde SOLO con este formato:\n"
    "- Una línea por error: ERROR: línea N | tipo | explicación breve\n"
    "- Si no hay ningún error: SIN_ERRORES\n"
    "- Para arreglar, por cada línea que cambie: ARREGLO N: <línea completa corregida, con su sangría>\n"
    "- Si hace falta una línea nueva (por ejemplo un import) antes de la línea N: INSERTAR N: <línea>\n"
    "- Para borrar una línea: ELIMINAR N\n"
    "Los números son SIEMPRE los de la numeración que te doy. No reescribas el archivo entero ni cambies lo que está "
    "bien. Termina con la línea: RESPUESTA: LISTO")
SISTEMA_SOLO = (
    "Eres un revisor de código. Busca SOLO errores que impiden compilar o que harían fallar el programa al "
    "ejecutarse: sintaxis, nombres (variables, funciones, módulos, clases) que no existen o no están importados, "
    "tipos incompatibles y llamadas con un número de argumentos que no encaja. No comentes estilo ni mejoras.\n"
    + FORMATO)
SISTEMA_HERRAMIENTA = (
    "Eres un revisor de código. Un compilador (sin IA) ya ha comprobado el archivo y te da sus errores con la línea. "
    "Explica cada uno y arréglalo. No inventes otros errores ni cambies lo que está bien.\n" + FORMATO)


def escribir(ruta: Path, datos) -> None:
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")


# --- preparar --------------------------------------------------------------------------------------------------------
def _deshacer_fase1(caso: dict) -> str:
    _, b, r, _ = C.DOS_FASES[(caso["lenguaje"], caso["archivo"].split(".")[0])][0]
    return caso["codigo"].replace(r, b, 1)


def preparar(evidencia: Path, condiciones=CONDICIONES) -> dict:
    evidencia = Path(evidencia)
    evidencia.mkdir(parents=True, exist_ok=False)
    casos = C.generar()
    validacion, fallos = {}, []
    for c in casos:
        vistas = sorted({e["linea"] for e in H.revisar(c["lenguaje"], c["codigo"], c["archivo"])})
        esperadas = c["fases"][0] if c["fases"] else []
        v = {"herramienta": vistas, "oraculo_fase1": esperadas, "ok": vistas == esperadas}
        if c["id"].endswith("_F2"):
            v2 = sorted({e["linea"] for e in H.revisar(c["lenguaje"], _deshacer_fase1(c), c["archivo"])})
            v.update(herramienta_fase2=v2, oraculo_fase2=c["fases"][1], ok=v["ok"] and v2 == c["fases"][1])
        validacion[c["id"]] = v
        if not v["ok"]:
            fallos.append(c["id"])
    escribir(evidencia / "casos.json", casos)
    res = {"fecha": time.strftime("%Y-%m-%dT%H:%M:%S"), "casos": len(casos), "condiciones": list(condiciones), "javac": H.javac() and
           Path(H.javac()).parent.parent.name, "validacion": validacion, "fallos_de_validacion": fallos}
    escribir(evidencia / "preparacion.json", res)
    if fallos:
        raise SystemExit(f"el oráculo no se reproduce con las herramientas en {fallos}: no se sigue")
    return res


# --- respuesta del cerebro: lectura y aplicación ---------------------------------------------------------------------
def numerar(codigo: str) -> str:
    return "\n".join(f"{i:3d}| {l}" for i, l in enumerate(codigo.split("\n"), 1))


# Marcas que los modelos ponen delante (2026-11-15: qwen25 escribía «- ERROR: …» y el lector las ignoraba):
# viñetas «- * • >», números «1.» «1)» y negrita/código «** ``» antes de la orden.
_ORDEN = re.compile(r"(?i)^\s*(?:[-*•>]+\s*|\d+[.)]\s+)?[`*]*\s*(SIN_ERRORES|ERROR|ARREGLO|INSERTAR|ELIMINAR)\b")


_ANIDADA = re.compile(r"(?i)^\s*[`*]*\s*(ARREGLO|INSERTAR|ELIMINAR)\s+\d+")


def _desenvolver(l: str) -> str:
    """«ARREGLO 18: INSERTAR 18: import x;» → «INSERTAR 18: import x;» (tanda 2: qwen25 anidaba órdenes)."""
    while True:
        m = re.match(r"(?i)^(\s*(?:[-*•>]+\s*|\d+[.)]\s+)?[`*]*\s*(?:ARREGLO|INSERTAR)\s+\d+[*`]*\s*:[*`]*\s?)(.*)$", l)
        if not (m and _ANIDADA.match(m.group(2))):
            return l
        l = m.group(2)


def leer_respuesta(texto: str) -> dict:
    out = {"errores": [], "sin_errores": False, "arreglos": {}, "insertar": [], "eliminar": set()}
    for l in (texto or "").splitlines():
        l = _desenvolver(l)
        o = _ORDEN.match(l)
        if not o:
            continue
        s = l[o.start(1):]
        if o.group(1).upper() == "SIN_ERRORES":
            out["sin_errores"] = True
            continue
        m = re.match(r"(?i)^ERROR[*`]*\s*:?[*`]*\s*(?:l[ií]nea|line)?\s*(\d+)", s)
        if m:
            out["errores"].append(int(m.group(1)))
            continue
        m = re.match(r"(?i)^ARREGLO\s+(\d+)[*`]*\s*:[*`]*\s?(.*)$", s)
        if m:
            out["arreglos"][int(m.group(1))] = _limpiar(m.group(2))
            continue
        m = re.match(r"(?i)^INSERTAR\s+(\d+)[*`]*\s*:[*`]*\s?(.*)$", s)
        if m:
            out["insertar"].append((int(m.group(1)), _limpiar(m.group(2))))
            continue
        m = re.match(r"(?i)^ELIMINAR\s+(\d+)", s)
        if m:
            out["eliminar"].add(int(m.group(1)))
    out["eliminar"] = sorted(out["eliminar"])
    return out


def _limpiar(t: str) -> str:
    t = t.rstrip()
    t = re.sub(r"^\s*\d+\|\s?", "", t)                    # «12| …»: el cerebro copió la numeración
    if len(t) >= 2 and t[0] == t[-1] == "`":
        t = t[1:-1]
    return t


def aplicar(codigo: str, r: dict) -> str:
    """Aplica los cambios sobre la numeración ORIGINAL, de abajo arriba. Si una línea corregida llega sin sangría y la
    original la tenía, se conserva la original (los modelos a veces la pierden)."""
    lineas = codigo.split("\n")
    n = len(lineas)
    for num in sorted(set(r["arreglos"]) | set(r["eliminar"]) | {i for i, _ in r["insertar"]}, reverse=True):
        if not 1 <= num <= n + 1:
            continue
        if num in r["eliminar"] and num <= n:
            del lineas[num - 1]
        elif num in r["arreglos"] and num <= n:
            nueva, vieja = r["arreglos"][num], lineas[num - 1]
            if nueva and not nueva[:1].isspace() and vieja[:1].isspace():
                nueva = vieja[:len(vieja) - len(vieja.lstrip())] + nueva
            lineas[num - 1] = nueva
        for i, texto in reversed([x for x in r["insertar"] if x[0] == num]):
            lineas.insert(num - 1, texto)
    return "\n".join(lineas)


def cambios(original: str, final: str) -> dict:
    """Líneas originales cambiadas o borradas, y líneas insertadas (con su posición en el original)."""
    a, b = original.split("\n"), final.split("\n")
    tocadas, insertadas = set(), []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if op in ("replace", "delete"):
            tocadas.update(range(i1 + 1, i2 + 1))
        if op in ("replace", "insert") and j2 - j1 > i2 - i1:
            insertadas += [(i1 + 1, t) for t in b[j1 + (i2 - i1):j2]]
    return {"tocadas": sorted(tocadas), "insertadas": insertadas}


def evaluar(caso: dict, final: str, respuestas: list) -> dict:
    """Estado final del caso frente al ORIGINAL y al oráculo. Nada se ejecuta: solo se compila / analiza."""
    errores_final = H.revisar(caso["lenguaje"], final, caso["archivo"])
    oraculo = sorted({e["linea"] for e in caso["errores"]})
    cb = cambios(caso["codigo"], final)
    permitidas = {x for n in oraculo for x in (n - 1, n, n + 1)}
    extra = [n for n in cb["tocadas"] if n not in permitidas]
    extra += [p for p, t in cb["insertadas"] if not (t.strip().startswith(("import ", "from ")) or p - 1 in permitidas
                                                      or p in permitidas)]
    dichas = sorted({n for r in respuestas for n in r["errores"]})
    hubo_cambios = bool(cb["tocadas"] or cb["insertadas"])
    if oraculo:
        estado = ("arreglado" if not errores_final and not extra else
                  "arreglado_tocando_mas" if not errores_final else
                  "sin_cambios" if not hubo_cambios else "no_compila")
    else:
        estado = ("rompio" if errores_final else
                  "falsa_alarma" if (dichas or hubo_cambios) else "correcto")
    return {"estado": estado, "errores_final": errores_final, "lineas_tocadas": cb["tocadas"],
            "insertadas": [t for _, t in cb["insertadas"]], "cambios_fuera_de_sitio": sorted(set(extra)),
            "errores_dichos": dichas, "encontrados": [n for n in oraculo if n in dichas],
            "falsas": [n for n in dichas if n not in oraculo]}


# --- bucle con un cerebro --------------------------------------------------------------------------------------------
def mensajes(caso: dict, codigo: str, errores_herramienta=None, avisos=()) -> list:
    sistema = SISTEMA_HERRAMIENTA if errores_herramienta is not None else SISTEMA_SOLO
    u = f"ARCHIVO: {caso['archivo']} ({caso['lenguaje']})\n```\n{numerar(codigo)}\n```"
    if errores_herramienta is not None:
        u += "\nERRORES DEL COMPILADOR:\n" + "\n".join(f"- línea {e['linea']}: {e['mensaje']}"
                                                      for e in errores_herramienta)
    if avisos:
        u += "\n" + "\n".join(avisos)
    return [{"role": "system", "content": sistema}, {"role": "user", "content": u}]


# --- tanda 2: dos mejoras SIN IA del bucle con herramienta -------------------------------------------------------------
_IMPORT = {"java": re.compile(r"^\s*import\s+(static\s+)?[\w.]+(\.\*)?\s*;\s*$"),
           "python": re.compile(r"^\s*(import\s+[\w.]+(\s+as\s+\w+)?(\s*,\s*[\w.]+(\s+as\s+\w+)?)*|"
                                r"from\s+[\w.]+\s+import\s+.+)\s*$")}


def separar_imports(r: dict, codigo: str, lenguaje: str) -> tuple:
    """Saca de la respuesta los `import` propuestos (ARREGLO o INSERTAR) para ponerlos arriba. Si un ARREGLO ponía un
    import ENCIMA de una línea que no lo era (tanda 1: qwen25 borró así la declaración de un campo), esa línea se
    conserva tal cual."""
    patron, lineas = _IMPORT[lenguaje], codigo.split("\n")
    nuevos, r = [], {**r, "arreglos": dict(r["arreglos"]), "insertar": list(r["insertar"])}
    for n, texto in list(r["arreglos"].items()):
        if patron.match(texto) and not (1 <= n <= len(lineas) and patron.match(lineas[n - 1])):
            nuevos.append(texto.strip())
            del r["arreglos"][n]
    for n, texto in list(r["insertar"]):
        if patron.match(texto):
            nuevos.append(texto.strip())
            r["insertar"].remove((n, texto))
    return r, list(dict.fromkeys(nuevos))


def colocar_imports(codigo: str, nuevos: list, lenguaje: str) -> str:
    """Pone los import nuevos en su sitio: tras el último import de cabecera (o tras `package` / el docstring)."""
    lineas = codigo.split("\n")
    existentes = {l.strip() for l in lineas}
    nuevos = [i for i in nuevos if i not in existentes]
    if not nuevos:
        return codigo
    patron, pos = _IMPORT[lenguaje], 0
    for i, l in enumerate(lineas):
        if patron.match(l) and not l[:1].isspace():
            pos = i + 1
        elif lenguaje == "java" and l.startswith("package "):
            pos = max(pos, i + 1)
    if pos == 0 and lenguaje == "python":
        try:
            import ast
            cuerpo = ast.parse(codigo).body
            if cuerpo and isinstance(cuerpo[0], ast.Expr) and isinstance(getattr(cuerpo[0], "value", None),
                                                                        ast.Constant):
                pos = cuerpo[0].end_lineno
        except SyntaxError:
            pass
    return "\n".join(lineas[:pos] + nuevos + lineas[pos:])


def lineas_cambiadas(antes: str, despues: str) -> set:
    """Números de línea (en `despues`) que el último arreglo cambió o añadió."""
    a, b = antes.split("\n"), despues.split("\n")
    out = set()
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if op in ("replace", "insert"):
            out.update(range(j1 + 1, j2 + 1))
    return out


def avisos_de(antes: str, despues: str, errores: list, r: dict, recolocados=(), avisar_import=False) -> list:
    if not (r["arreglos"] or r["insertar"] or r["eliminar"]):
        return ["AVISO: en tu respuesta anterior no había ningún arreglo aplicable. Usa «ARREGLO N: <línea>»."]
    tocadas, lineas = lineas_cambiadas(antes, despues), despues.split("\n")
    out = []
    for n in sorted({e["linea"] for e in errores if e["linea"] in tocadas}):
        out.append(f"AVISO: tu arreglo anterior en la línea {n} no resolvió el error; ahora esa línea dice "
                   f"«{lineas[n - 1].strip()}». Propón un arreglo DISTINTO.")
    if avisar_import and recolocados:
        # tanda 3: el import se recolocó arriba, así que la línea que falla no la «tocó» el cerebro
        for e in errores:
            if e["linea"] and e["linea"] not in tocadas and e["clase"] in ("nombre", "simbolo"):
                out.append(f"AVISO: el sistema colocó arriba tu import «{'», «'.join(recolocados)}», pero el "
                           f"compilador sigue fallando en la línea {e['linea']} («{lineas[e['linea'] - 1].strip()}»): "
                           f"{e['mensaje']}. Comprueba que el import corresponde a cómo se usa el nombre en esa línea.")
    return out


def leer_filas(evidencia: Path) -> list:
    f = Path(evidencia) / "peticiones.jsonl"
    out = []
    if f.is_file():
        for l in f.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(l))
            except json.JSONDecodeError:
                break
    return out


def _casos(evidencia: Path) -> list:
    return json.loads((Path(evidencia) / "casos.json").read_text(encoding="utf-8"))


def condiciones_de(evidencia: Path) -> tuple:
    prep = json.loads((Path(evidencia) / "preparacion.json").read_text(encoding="utf-8"))
    return tuple(prep.get("condiciones") or CONDICIONES)


def pendientes(modelo, evidencia: Path) -> bool:
    hechas = {(f["condicion"], f["caso"]) for f in leer_filas(evidencia) if f["modelo"] == modelo}
    return any((c, x["id"]) not in hechas for c in condiciones_de(evidencia) for x in _casos(evidencia))


def correr_modelo(modelo, evidencia: Path, completar, parar=lambda: False) -> str:
    evidencia = Path(evidencia)
    for cond in condiciones_de(evidencia):
        for caso in _casos(evidencia):
            if (cond, caso["id"]) in {(f["condicion"], f["caso"]) for f in leer_filas(evidencia)
                                      if f["modelo"] == modelo}:
                continue
            if parar():
                return "parado"
            t0, intentos, codigo, respuestas = time.monotonic(), [], caso["codigo"], []
            if cond == "solo":
                texto, info = completar(mensajes(caso, codigo), TOKENS)
                r = leer_respuesta(texto)
                respuestas.append(r)
                codigo = aplicar(codigo, r)
                intentos.append({"texto": texto, **info})
            else:
                mejorada = cond in ("herramienta2", "herramienta3")
                errores, avisos = H.revisar(caso["lenguaje"], codigo, caso["archivo"]), []
                for _ in range(MAX_INTENTOS):
                    if not errores:
                        break
                    if parar():
                        return "parado"                    # el caso se repite entero al reanudar: nada a medias
                    texto, info = completar(mensajes(caso, codigo, errores, avisos if mejorada else ()), TOKENS)
                    r = leer_respuesta(texto)
                    respuestas.append(r)
                    antes, recolocados = codigo, []
                    if mejorada:
                        r_aplicar, recolocados = separar_imports(r, codigo, caso["lenguaje"])
                        codigo = colocar_imports(aplicar(codigo, r_aplicar), recolocados, caso["lenguaje"])
                    else:
                        codigo = aplicar(codigo, r)
                    errores = H.revisar(caso["lenguaje"], codigo, caso["archivo"])
                    avisos = (avisos_de(antes, codigo, errores, r, recolocados, cond == "herramienta3")
                              if mejorada and errores else [])
                    intentos.append({"texto": texto, "errores_despues": errores, "imports_recolocados": recolocados,
                                     "avisos_siguientes": avisos, **info})
            fila = {"modelo": modelo, "condicion": cond, "caso": caso["id"], "lenguaje": caso["lenguaje"],
                    "nota": caso["nota"], "oraculo": caso["errores"], "llamadas": len(intentos),
                    "intentos": intentos, "final": codigo, **evaluar(caso, codigo, respuestas),
                    "segundos": round(time.monotonic() - t0, 2), "fecha": time.strftime("%Y-%m-%dT%H:%M:%S")}
            with (evidencia / "peticiones.jsonl").open("a", encoding="utf-8", newline="\n") as fh:
                fh.write(json.dumps(fila, ensure_ascii=False) + "\n")
    return "completo"


def recalificar(evidencia: Path) -> dict:
    """Vuelve a puntuar las filas de `solo` desde el TEXTO guardado del cerebro (un solo intento: es exacto). Para
    corregir el lector sin repetir llamadas. Las de `herramienta` no se tocan (cada intento depende del anterior)."""
    evidencia = Path(evidencia)
    f = evidencia / "peticiones.jsonl"
    casos = {c["id"]: c for c in _casos(evidencia)}
    filas = leer_filas(evidencia)
    copia = evidencia / f"peticiones_antes_de_recalificar_{time.strftime('%Y%m%dT%H%M%S')}.jsonl"
    copia.write_text(f.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    cambiadas = 0
    for fila in filas:
        if fila["condicion"] != "solo":
            continue
        caso = casos[fila["caso"]]
        r = leer_respuesta(fila["intentos"][0]["texto"])
        final = aplicar(caso["codigo"], r)
        nuevo = evaluar(caso, final, [r])
        if nuevo["estado"] != fila["estado"] or nuevo["errores_dichos"] != fila["errores_dichos"]:
            cambiadas += 1
        fila.update(nuevo, final=final, recalificada=True)
    f.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in filas), encoding="utf-8", newline="\n")
    return {"filas": len(filas), "recalificadas_con_cambio": cambiadas, "copia": copia.name}


def ejecutar(externos: Path, evidencia: Path, modelos=MODELOS, reanudar=False, permitir_uso=False,
             perfil_auto=False) -> dict:
    import banco_flujos as BF                           # mismo armazón de seguridad (PC libre, térmica, reanudar)
    return BF.ejecutar(externos, evidencia, modelos, reanudar,
                       correr=lambda m, e, c, parar: correr_modelo(m, e, c, parar),
                       pendientes_fn=pendientes, requisito="casos.json", permitir_uso=permitir_uso,
                       perfil_auto=perfil_auto)


# --- informe ---------------------------------------------------------------------------------------------------------
def informe(evidencia: Path) -> str:
    evidencia = Path(evidencia)
    filas = leer_filas(evidencia)
    L = ["# Banco de revisión de código: informe", "",
         "32 casos (16 Python, 16 Java): 20 con un error plantado, 4 con dos errores de fases distintas y 8 correctos "
         "(4 que parecen sospechosos). El oráculo se validó con las herramientas antes de empezar.", "",
         "| modelo | condición | lenguaje | arreglado | tocando de más | no compila | sin cambios | correctos bien | "
         "falsa alarma | rompió | errores bien señalados (solo) | falsas alarmas (solo) | llamadas |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for m in dict.fromkeys(f["modelo"] for f in filas):
        for c in condiciones_de(evidencia):
            for lang in ("python", "java"):
                fs = [f for f in filas if f["modelo"] == m and f["condicion"] == c and f["lenguaje"] == lang]
                if not fs:
                    continue
                n = lambda e: sum(f["estado"] == e for f in fs)
                con = [f for f in fs if f["oraculo"]]
                total_or = sum(len({e["linea"] for e in f["oraculo"]}) for f in con)
                bien = sum(len(f["encontrados"]) for f in con)
                falsas = sum(len(f["falsas"]) for f in fs)
                L.append(f"| {m} | {c} | {lang} | {n('arreglado')}/{len(con)} | {n('arreglado_tocando_mas')} | "
                         f"{n('no_compila')} | {n('sin_cambios')} | {n('correcto')}/{len(fs) - len(con)} | "
                         f"{n('falsa_alarma')} | {n('rompio')} | "
                         + (f"{bien}/{total_or} | {falsas}" if c == "solo" else "– | –")
                         + f" | {sum(f['llamadas'] for f in fs)} |")
    L += ["", "## Dos fases (la sintaxis tapa un error de nombres)", ""]
    for f in filas:
        if f["caso"].endswith("_F2"):
            L.append(f"- {f['modelo']} / {f['condicion']} / {f['caso']}: {f['estado']} en {f['llamadas']} llamada(s)")
    texto = "\n".join(L) + "\n"
    (evidencia / "INFORME.md").write_text(texto, encoding="utf-8", newline="\n")
    return texto


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("orden", choices=("preparar", "ejecutar", "informe", "recalificar"))
    ap.add_argument("rutas", nargs="+")
    ap.add_argument("--modelos", nargs="+", default=list(MODELOS))
    ap.add_argument("--reanudar", action="store_true")
    ap.add_argument("--permitir_uso", action="store_true")
    ap.add_argument("--perfil_auto", action="store_true", help="topes y capas calculados para ESTE equipo")
    ap.add_argument("--condiciones", nargs="+", default=list(CONDICIONES))
    a = ap.parse_args(argv)
    if a.orden == "preparar":
        r = preparar(Path(a.rutas[0]), tuple(a.condiciones))
        print(json.dumps({k: r[k] for k in ("casos", "javac", "fallos_de_validacion")}, ensure_ascii=False))
    elif a.orden == "recalificar":
        print(json.dumps(recalificar(Path(a.rutas[0])), ensure_ascii=False))
    elif a.orden == "informe":
        print(informe(Path(a.rutas[0])))
    else:
        r = ejecutar(Path(a.rutas[0]), Path(a.rutas[1]), tuple(a.modelos), a.reanudar, a.permitir_uso, a.perfil_auto)
        print(json.dumps({k: r[k] for k in ("inicio", "fin", "abortada", "llama_al_final") if k in r},
                         ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
