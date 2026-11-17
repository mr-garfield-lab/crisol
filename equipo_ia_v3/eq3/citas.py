"""Equipo IA V3 · VERIFICADOR DE CITAS y calidad de la deliberación (Etapa 4).

Los roles de V2-F.1 exigen «citar evidencia con fuente y líneas» y prohíben a A2 «citar líneas que no existen».
Este módulo lo COMPRUEBA, de forma determinista y sin ejecutar nada. Contrasta cada cita con el archivo real.

Formas reconocidas:
- `línea N` / `líneas N-M`: líneas de la versión de la solución que el agente tenía delante (protocolo de
  V2-F.1).
- `caso ID`: identificador de un caso registrado (`pruebas_pendientes/casos.json`, usados o excluidos).
- `EVn`: uno de los hechos del controlador, EV1…EV7.
- `ruta.py:N`, `ruta.py:N-M`, `ruta.py::símbolo`: código de una raíz (por ejemplo `sistema/src`); el símbolo
  debe estar definido (`def`/`class`, también `Clase.método`) según `ast`.
- Un texto entre comillas invertidas en la misma frase que una cita de líneas debe aparecer en esas líneas.

Estados: verificada · archivo_inexistente · ruta_no_permitida · lineas_fuera_de_rango · simbolo_inexistente ·
texto_no_coincide · caso_inexistente · hecho_inexistente · sin_base (no hay versión a la que referirse).

`deliberacion(traza, lab, eid)` aplica el verificador a cada paso de A1/A2/A3 de una ejecución de la traza.
Cada paso se contrasta con la versión de la solución vigente en ese momento: el número de pasos
`fs_generar`/`fs_corregir` anteriores. Ese mapeo sigue el protocolo de la función supervisada y se declara aquí
como supuesto. El resultado es un informe de calidad por agente, junto con las objeciones abiertas y cerradas y
las afirmaciones sin evidencia que ya registra V2-F.1.
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

from . import ingesta as I

RE_LINEAS = re.compile(r"\bl[ií]neas?\s+(\d{1,6})(?:\s*[-–]\s*(\d{1,6}))?", re.I)
RE_CASO = re.compile(r"\bcaso\s+([A-Za-z0-9][A-Za-z0-9_\-]{0,40})", re.I)
RE_HECHO = re.compile(r"\bEV(\d{1,2})\b")
RE_RUTA = re.compile(r"(?<![\w/.])([./A-Za-z0-9_][A-Za-z0-9_./-]{0,200}\.py)(?::(\d{1,6})(?:-(\d{1,6}))?|::([A-Za-z_][\w.]{0,120}))")
RE_TEXTO = re.compile(r"`([^`\n]{3,200})`")
HECHOS = {f"EV{i}" for i in range(1, 8)}
PASOS_QUE_CREAN_VERSION = ("fs_generar", "fs_corregir")


def simbolos(codigo: str) -> set:
    """Nombres definidos (funciones y clases, con su forma `Clase.método`). Solo `ast.parse`: nada se ejecuta."""
    try:
        arbol = ast.parse(codigo)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return set()
    nombres = set()

    def visitar(nodo, prefijo=""):
        for hijo in ast.iter_child_nodes(nodo):
            if isinstance(hijo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                nombre = prefijo + hijo.name
                nombres.add(nombre)
                visitar(hijo, nombre + ".")
    visitar(arbol)
    return nombres


def _comprobar_lineas(lineas: list, ini: int, fin: int, frase: str) -> tuple:
    if not (1 <= ini <= fin <= len(lineas)):
        return "lineas_fuera_de_rango", f"el archivo tiene {len(lineas)} líneas"
    tramo = "\n".join(lineas[ini - 1:fin])
    for texto in RE_TEXTO.findall(frase):
        if texto.strip() and texto.strip() not in tramo:
            return "texto_no_coincide", f"«{texto}» no aparece en las líneas {ini}-{fin}"
    return "verificada", ""


def verificar_texto(texto: str, version: str | None = None, casos: set = frozenset(),
                    raiz: Path | None = None) -> list:
    """Citas de un texto de agente con su estado. `version`: código visible para «línea N»; `raiz`: base de
    las rutas `x.py:N` (confinada: sin «..», sin rutas absolutas ni enlaces simbólicos)."""
    citas = []
    lineas_version = version.splitlines() if version is not None else None
    # Frases: se corta en «;», «|», saltos de línea y en un punto SEGUIDO de espacio (nunca dentro de «x.py»).
    for frase in re.split(r"[;\n|]|\.\s+", texto):
        sin_rutas = RE_RUTA.sub(" ", frase)
        for m in RE_LINEAS.finditer(sin_rutas):
            ini, fin = int(m.group(1)), int(m.group(2) or m.group(1))
            if lineas_version is None:
                estado, detalle = "sin_base", "no hay versión de la solución a la que referirse"
            else:
                estado, detalle = _comprobar_lineas(lineas_version, min(ini, fin), max(ini, fin), frase)
            citas.append({"cita": m.group(0), "tipo": "linea", "estado": estado, "detalle": detalle})
        for m in RE_CASO.finditer(frase):
            ok = m.group(1) in casos
            citas.append({"cita": m.group(0), "tipo": "caso", "estado": "verificada" if ok else "caso_inexistente",
                          "detalle": "" if ok else "no figura en los casos registrados"})
        for m in RE_HECHO.finditer(frase):
            ok = f"EV{m.group(1)}" in HECHOS
            citas.append({"cita": m.group(0), "tipo": "hecho", "estado": "verificada" if ok else "hecho_inexistente",
                          "detalle": "" if ok else "solo existen EV1…EV7"})
        for m in RE_RUTA.finditer(frase):
            citas.append(_cita_ruta(m, frase, raiz))
    return citas


def _cita_ruta(m, frase: str, raiz: Path | None) -> dict:
    ruta, ini, fin, simbolo = m.group(1), m.group(2), m.group(3), m.group(4)
    base = {"cita": m.group(0), "tipo": "simbolo" if simbolo else "ruta"}
    if raiz is None:
        return dict(base, estado="sin_base", detalle="no se indicó la raíz del código")
    try:
        codigo = I.leer(Path(raiz).resolve(), ruta).decode("utf-8", "replace")
    except I.ErrorValidacion as e:
        estado = "archivo_inexistente" if str(e).startswith("no existe") else "ruta_no_permitida"
        return dict(base, estado=estado, detalle=str(e))
    if simbolo:
        ok = simbolo in simbolos(codigo)
        return dict(base, estado="verificada" if ok else "simbolo_inexistente",
                    detalle="" if ok else f"{ruta} no define {simbolo}")
    a = int(ini)
    b = int(fin) if fin else a
    estado, detalle = _comprobar_lineas(codigo.splitlines(), min(a, b), max(a, b), frase)
    return dict(base, estado=estado, detalle=detalle)


def _casos(lab: Path, eid: str) -> set:
    tarea, ejec = eid.split("/")
    rel = f"tareas/{tarea}/ejecuciones/{ejec}/funcion/pruebas_pendientes/casos.json"
    if not I.existe(lab, rel):
        return set()
    datos = I.json_de(lab, rel)
    ids = {c.get("id") for c in datos.get("usados", []) if isinstance(c, dict)}
    ids |= {c.get("caso") for c in datos.get("excluidos", []) if isinstance(c, dict)}   # «excluidos» usa «caso»
    return {x for x in ids if isinstance(x, str)}


def deliberacion(traza, lab: Path, eid: str) -> dict:
    """Informe de calidad de la deliberación de una ejecución importada en la traza."""
    lab = Path(lab).resolve()
    acciones = [a for a in traza.filas("acciones", ejecucion_id=eid) if a["tipo"] == "paso"]
    versiones = {c["version"]: c for c in traza.filas("cambios", ejecucion_id=eid)}
    casos = _casos(lab, eid)
    por_agente, pasos, alterados, creadas = {}, [], [], 0
    for a in sorted(acciones, key=lambda x: x["n"]):
        visible = versiones.get(creadas)
        codigo = I.leer(lab, visible["ruta"]).decode("utf-8", "replace") if visible else None
        bruto = I.leer(lab, a["archivo"])
        if I.sha256_bytes(bruto) != a["sha256"]:        # un texto alterado no se analiza como si fuera auténtico
            alterados.append({"n": a["n"], "agente": a["agente"], "archivo": a["archivo"]})
            if a["nombre"] in PASOS_QUE_CREAN_VERSION:
                creadas += 1
            continue
        texto = bruto.decode("utf-8", "replace")
        citas = verificar_texto(texto, codigo, casos)
        detalle = json.loads(a["detalle"]) if isinstance(a["detalle"], str) else a["detalle"]
        sin_evidencia = detalle.get("afirmaciones_sin_evidencia") or []
        pasos.append({"n": a["n"], "agente": a["agente"], "paso": a["nombre"],
                      "version_visible": visible["version"] if visible else None,   # la que se USÓ para contrastar
                      "citas": citas, "afirmaciones_sin_evidencia": sin_evidencia})
        r = por_agente.setdefault(a["agente"], {"citas": 0, "verificadas": 0, "invalidas": 0, "sin_base": 0,
                                                "afirmaciones_sin_evidencia": 0})
        r["citas"] += len(citas)
        r["verificadas"] += sum(c["estado"] == "verificada" for c in citas)
        r["sin_base"] += sum(c["estado"] == "sin_base" for c in citas)
        r["invalidas"] += sum(c["estado"] not in ("verificada", "sin_base") for c in citas)
        r["afirmaciones_sin_evidencia"] += len(sin_evidencia)
        if a["nombre"] in PASOS_QUE_CREAN_VERSION:
            creadas += 1
    decisiones = traza.filas("decisiones", ejecucion_id=eid)
    objeciones = sum(d["tipo"] == "objecion" for d in decisiones)
    cerradas = sum(d["tipo"] == "objecion_cerrada" for d in decisiones)
    return {"ejecucion": eid, "por_agente": por_agente, "pasos": pasos, "alterados": alterados,
            "objeciones": {"abiertas": objeciones - cerradas, "cerradas": cerradas, "total": objeciones},
            "invalidas": [dict(c, n=p["n"], agente=p["agente"]) for p in pasos for c in p["citas"]
                          if c["estado"] not in ("verificada", "sin_base")]}
