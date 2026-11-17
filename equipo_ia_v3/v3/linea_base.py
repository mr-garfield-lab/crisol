#!/usr/bin/env python3
"""Equipo IA V3 — LÍNEA BASE reproducible y puerta de regresión (Etapa 0).

Orden única (desde equipo_ia_v3/):   python3 -B v3/linea_base.py [--salida DIR_NUEVO]

Ejecuta, en un directorio NUEVO y con HOME/TMPDIR aislados (sin red, sin instalar nada, sin modelos):
  verificador  `<sistema>/verificar.py` (sin --qwen-real: nunca inicia Qwen ni llama-server);
  codex        COPIA de `fuentes/codex_complementos`, pruebas contra el `eq2` de `<sistema>/src`;
  contexto     COPIA de `fuentes/contexto_ligero_v35`, pruebas con el `eq2` de `<sistema>/src` en la ruta.
`<sistema>` es `equipo_ia_v3/sistema` salvo `--sistema`. Nunca se escribe en `fuentes/` ni en `<sistema>`.

Cada prueba tiene un ESTADO exacto (OK, FALLO, ERROR, OMITIDA, NO VERIFICADA, FALLO_ESPERADO,
EXITO_INESPERADO...) y, si no es OK, una FIRMA normalizada (causa del fallo sin rutas temporales). La
comparación con `v3/linea_base_esperada.json` es EXACTA, prueba a prueba:
  IGUAL      mismo estado y, si no es OK, misma firma;
  REGRESION  una prueba OK deja de estarlo (también si pasa a OMITIDA), o una prueba nueva no está OK;
  CAMBIO     un fallo conocido cambia de estado o de firma: falla de otra manera o por otra causa;
  AUSENTE    una prueba de la línea base no aparece;
  MEJORA     algo que no estaba OK ahora lo está: hay que revisarlo y actualizar la línea base;
  NUEVA      prueba que no estaba en la línea base y pasa (informativo).
  INESTABLE  (V3.1 F1, X1) una REGRESION o un CAMBIO del verificador de V2-F.1 que se explica ENTERO por una
             inestabilidad DECLARADA en la línea base (`inestables`) y que se CONFIRMA repitiendo la subprueba aislada.
Código de salida: 0 todo IGUAL o NUEVA · 1 alguna REGRESION, CAMBIO o AUSENTE · 3 solo MEJORAS por revisar ·
4 igual salvo pruebas INESTABLES confirmadas (no concluyentes en esta ejecución, y así se informa) · 2 error de la
herramienta (suite sin resultados, línea base inválida...). Un 0 NO significa «todo correcto»: significa «igual que
la línea base», que contiene fallos conocidos y documentados.

Inestabilidad declarada (`inestables` de la línea base; ver `docs/V31_F1_X1_INESTABLES.md`). Una diferencia solo pasa
a INESTABLE si se cumplen TODAS estas condiciones; si falla una, conserva su veredicto (la puerta sigue fallando) y
la explicación intentada queda en `resultado.json`:
  1. La comprobación es del verificador, falla (FALLO), con el MISMO número de pruebas que en la línea base, y su
     traza solo contiene fallos (FAIL), ningún error (ERROR).
  2. Están TODOS los fallos conocidos de la línea base (mismas subpruebas) y cada fallo de más es EXACTAMENTE el
     declarado: misma subprueba, un único marco en el archivo y la línea declarados, el mismo código fuente, y un
     mensaje `A != B` con A, B > 0 y |A − B| ≤ `max_diferencia_kB`.
  3. La subprueba, repetida aislada `repeticiones` veces con las opciones del verificador, pasa al menos `minimo_ok`
     veces (mayoría estricta), y cada repetición fallida vuelve a ser EXACTAMENTE el fallo declarado.

`--proponer ARCHIVO` escribe una línea base PROPUESTA a partir de la ejecución; cada prueba no OK queda con
causa «SIN_CLASIFICAR». La comparación rechaza (código 2) una línea base con causas sin clasificar o no
declaradas en su catálogo `causas`.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

V3 = Path(__file__).resolve().parent
RAIZ = V3.parent                                  # equipo_ia_v3/
REPO = RAIZ.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
from eq3 import plataforma  # noqa: E402
from v3 import linea_base_plataforma  # noqa: E402
SISTEMA = RAIZ / "sistema"
FUENTES = REPO / "fuentes"
ESPERADA = V3 / "linea_base_esperada.json"                          # Linux: la referencia, no cambia
ESPERADA_WINDOWS = V3 / "linea_base_esperada_windows.json"          # derivada con causas (linea_base_plataforma.py)
CORREDOR = V3 / "corredor_unittest.py"

SUITES = ("verificador", "codex", "contexto")
SIN_CLASIFICAR = "SIN_CLASIFICAR"
VEREDICTOS = ("IGUAL", "NUEVA", "MEJORA", "REGRESION", "CAMBIO", "AUSENTE")
MAX_FIRMA = 400
MAX_BASE_WINDOWS = 48        # longitud máxima de la carpeta de salida en Windows (ejecuciones verificadas: 34 y 41)
INESTABLE = "INESTABLE"
CAMPOS_INESTABLE = ("id", "suite", "prueba", "subprueba", "ubicacion", "codigo", "patron", "max_diferencia_kB",
                    "repeticiones", "minimo_ok", "causa", "evidencia")
SUITES_INESTABLES = ("verificador",)        # solo de él hay trazas con cada subprueba (las de V2-F.1)
_EJECUTADAS = re.compile(r"(\d+)/(\d+) ejecutadas; failures=(\d+)")


class ErrorHerramienta(RuntimeError):
    """Fallo de la propia herramienta o de una suite que no produce resultados: nunca cuenta como éxito."""


MARCAS = ("<SALIDA>", "<SISTEMA>", "<FUENTES>", "<REPO>")


def _entorno(tmp: Path, extra: dict | None = None) -> dict:
    """Entorno mínimo y aislado (`eq3.plataforma.entorno_hijo`): HOME/TMPDIR propios, UTF-8, semilla fija."""
    tmp.mkdir(parents=True, exist_ok=True)
    return plataforma.entorno_hijo(tmp, {"PYTHONHASHSEED": "0", **(extra or {})})


def reemplazos(base: Path, sistema: Path) -> list:
    """Rutas variables de una ejecución → marcas estables (la más larga primero), en todas sus formas
    (nativa, POSIX y con «\\» escapadas: `eq3.plataforma.variantes_ruta`)."""
    pares = [(v, marca) for ruta, marca in zip((base, sistema, FUENTES, REPO), MARCAS)
             for v in plataforma.variantes_ruta(ruta)]
    return sorted(pares, key=lambda p: -len(p[0]))


def normalizar(texto: str, pares: list) -> str:
    t = texto or ""
    for ruta, marca in pares:
        t = t.replace(ruta, marca)
    t = plataforma.barras_tras_marca(t, MARCAS)                          # Windows: «<SALIDA>\a» → «<SALIDA>/a»
    t = re.sub(r"\d{8}_\d{6}_\d{6}_\d+", "<ID>", t)                       # carpetas de verificación
    t = re.sub(r"\b(eq2_test_|tmp|manifest_|ctx\d+_[a-z]+_)[a-z0-9_]{8}\b", r"\1<X>", t)   # nombres de tempfile
    # Diferencia de conjuntos de unittest: QUÉ elemento se cita depende del orden de iteración del conjunto, que
    # cambia en cada proceso (los corredores usan `-I`, que ignora PYTHONHASHSEED). El estado y el tipo de fallo se
    # conservan; solo se quita el elemento citado, para que la firma sea la misma en cada ejecución.
    t = re.sub(r"(Items in the (?:first|second) set but not the (?:first|second):).*", r"\1 <ELEMENTOS>", t, flags=re.S)
    # Resumen ABREVIADO por unittest («[Wind[77 chars]txt')] != …»): los recortes «[N chars]» dependen de la longitud
    # de las rutas reales y pueden partir una ruta por la mitad, que entonces ya no se sustituye por su marca. La
    # firma dependería de la carpeta donde está el proyecto. Se quita el resumen; la última línea del diff se conserva.
    t = re.sub(r"^(\w+: \w+ differ:) (?=[^…]*\[\d+ chars\])[^…]*( … |$)", r"\1 <ABREVIADO>\2", t)
    return t[:MAX_FIRMA]


def estados_de_informe(inf: dict, pares: list) -> dict:
    """informe.json del verificador → {id: {estado, firma}}; la firma (detalle normalizado) solo si no es OK."""
    pruebas = {}
    for x in inf["resultados"]:
        if x["id"] in pruebas:
            raise ErrorHerramienta(f"identificador repetido en el informe del verificador: {x['id']}")
        estado = x["estado"]
        pruebas[x["id"]] = {"estado": estado, "firma": "" if estado == "OK" else normalizar(x.get("detalle", ""), pares)}
    return pruebas


def ejecutar_verificador(base: Path, sistema: Path, limite_s: int) -> dict:
    tmp = base / "tmp_verificador"
    t0 = time.monotonic()
    r = plataforma.ejecutar(plataforma.orden_eq2("verificar.py"), cwd=sistema, env=_entorno(tmp), timeout=limite_s)
    (base / "verificador.log").write_text(r.stdout + r.stderr, encoding="utf-8")
    m = re.search(r"^\s*Informes:\s*([^|\n]+)", r.stdout, re.M)
    ruta = Path(m.group(1).strip()) if m else None
    if ruta is None or not ruta.is_file() or base not in ruta.parents:
        raise ErrorHerramienta(f"el verificador no produjo un informe.json propio (rc={r.returncode}); ver verificador.log")
    inf = json.loads(ruta.read_text(encoding="utf-8"))
    pruebas = estados_de_informe(inf, reemplazos(base, sistema))
    if not pruebas:
        raise ErrorHerramienta("el informe del verificador no contiene resultados")
    return {"rc": r.returncode, "duracion_s": round(time.monotonic() - t0, 1), "ejecutadas": len(pruebas),
            "resumen": inf.get("resumen"), "naturaleza": inf.get("naturaleza"),
            "estado_general": inf.get("estado_general"), "version": inf.get("version"),
            "informe": str(ruta.relative_to(base)), "pruebas": pruebas}


def ejecutar_unittest(nombre: str, origen: Path, base: Path, sistema: Path, rutas_extra: list, limite_s: int,
                      entorno_extra: dict | None = None) -> dict:
    """Copia `origen` bajo `base` y ejecuta su carpeta tests/ con el corredor (proceso hijo, `-I`)."""
    base.mkdir(parents=True, exist_ok=True)
    copia = base / f"copia_{nombre}"
    shutil.copytree(origen, copia, symlinks=True,
                    ignore=shutil.ignore_patterns("__pycache__", "resultados", "*.pyc"))
    tmp = base / f"tmp_{nombre}"
    salida = base / f"{nombre}.json"
    extra = {k: (str(tmp) if v == "{TMP}" else v) for k, v in (entorno_extra or {}).items()}
    t0 = time.monotonic()
    # `-I` ignora PYTHONUTF8 del entorno: en Windows, `-X utf8` lo fija en la orden. En Linux, la orden de V3.
    utf8 = ["-X", "utf8"] if plataforma.WINDOWS else []
    r = plataforma.ejecutar([sys.executable, "-B", "-I", *utf8, str(CORREDOR), str(copia / "tests"), str(salida),
                             str(copia), *map(str, rutas_extra)], cwd=copia, env=_entorno(tmp, extra),
                            timeout=limite_s)
    if r.returncode != 0 or not salida.is_file():
        raise ErrorHerramienta(f"{nombre}: el corredor no produjo resultados (rc={r.returncode}): {r.stderr[-800:]}")
    datos = json.loads(salida.read_text(encoding="utf-8"))
    (base / f"{nombre}.log").write_text(datos["registro"] + r.stderr, encoding="utf-8")
    if datos["ejecutadas"] == 0 or not datos["pruebas"]:
        raise ErrorHerramienta(f"{nombre}: no se ejecutó ninguna prueba")
    pares = reemplazos(base, sistema)
    pruebas = {k: {"estado": v["estado"], "firma": "" if v["estado"] == "OK" else normalizar(v["firma"], pares)}
               for k, v in sorted(datos["pruebas"].items())}
    return {"rc": r.returncode, "duracion_s": round(time.monotonic() - t0, 1), "ejecutadas": datos["ejecutadas"],
            "pruebas": pruebas}


def esperada_por_defecto() -> Path:
    """Linux/Termux: la línea base de referencia. Windows: la derivada para Windows, si existe."""
    return ESPERADA_WINDOWS if plataforma.WINDOWS and ESPERADA_WINDOWS.is_file() else ESPERADA


def validar_esperada(esp: dict, suites=SUITES) -> list:
    """Problemas de una línea base: suites ausentes, o pruebas no OK sin causa clasificada y declarada."""
    problemas, causas = [], esp.get("causas", {})
    for suite in suites:
        decl = esp.get("suites", {}).get(suite)
        if not decl or not decl.get("pruebas"):
            problemas.append(f"{suite}: la línea base no tiene pruebas")
            continue
        for pid, d in decl["pruebas"].items():
            if d.get("estado") == "OK":
                continue
            causa = d.get("causa")
            if not causa or causa == SIN_CLASIFICAR:
                problemas.append(f"{suite}: {pid}: causa sin clasificar")
            elif causa not in causas:
                problemas.append(f"{suite}: {pid}: causa no declarada en el catálogo: {causa}")
    return problemas + problemas_inestables(esp)


def problemas_inestables(esp: dict) -> list:
    """Problemas de las declaraciones de inestabilidad: cada una completa, sobre una prueba de la línea base, con causa
    del catálogo, un patrón de dos números, tolerancia positiva y mayoría estricta de repeticiones correctas."""
    problemas, vistos = [], set()
    for i, d in enumerate(esp.get("inestables", [])):
        nombre = d.get("id", f"#{i}") if isinstance(d, dict) else f"#{i}"
        faltan = [c for c in CAMPOS_INESTABLE if not isinstance(d, dict) or d.get(c) in (None, "")]
        if faltan:
            problemas.append(f"inestable {nombre}: faltan campos {faltan}")
            continue
        if d["id"] in vistos:
            problemas.append(f"inestable {nombre}: identificador repetido")
        vistos.add(d["id"])
        if d["suite"] not in SUITES_INESTABLES:
            problemas.append(f"inestable {nombre}: suite no admitida: {d['suite']}")
        elif d["prueba"] not in esp.get("suites", {}).get(d["suite"], {}).get("pruebas", {}):
            problemas.append(f"inestable {nombre}: la prueba {d['prueba']} no está en la línea base")
        if d["causa"] not in esp.get("causas", {}) or d["causa"] == SIN_CLASIFICAR:
            problemas.append(f"inestable {nombre}: causa no declarada en el catálogo: {d['causa']}")
        try:
            if re.compile(d["patron"]).groups != 2:
                problemas.append(f"inestable {nombre}: el patrón debe capturar exactamente dos números")
        except (re.error, TypeError):
            problemas.append(f"inestable {nombre}: patrón inválido")
        n, m, tope = d["repeticiones"], d["minimo_ok"], d["max_diferencia_kB"]
        if not all(type(x) is int for x in (n, m, tope)) or tope <= 0 or n < 3 or not n // 2 < m <= n:
            problemas.append(f"inestable {nombre}: repeticiones ≥ 3, mayoría estricta de correctas y tolerancia > 0")
    return problemas


def veredicto(esperado: dict | None, real: dict | None) -> str:
    if real is None:
        return "AUSENTE"
    if esperado is None:
        return "NUEVA" if real["estado"] == "OK" else "REGRESION"
    if esperado["estado"] == "OK":
        return "IGUAL" if real["estado"] == "OK" else "REGRESION"
    if real["estado"] == "OK":
        return "MEJORA"
    if real["estado"] == esperado["estado"] and real.get("firma", "") == esperado.get("firma", ""):
        return "IGUAL"
    return "CAMBIO"


def comparar(obtenido: dict, esperado: dict) -> dict:
    """{suite: {pruebas}} frente a la línea base: veredicto exacto por prueba y totales."""
    totales = {v: 0 for v in VEREDICTOS}
    diferencias = []
    for suite, res in obtenido.items():
        base = esperado["suites"][suite]["pruebas"]
        reales = res["pruebas"]
        for pid in sorted(set(base) | set(reales)):
            b, r = base.get(pid), reales.get(pid)
            v = veredicto(b, r)
            totales[v] += 1
            if v != "IGUAL":
                diferencias.append({"suite": suite, "id": pid, "veredicto": v,
                                    "esperado": b and {k: b.get(k) for k in ("estado", "firma", "causa")},
                                    "real": r})
    return {"totales": totales, "diferencias": diferencias}


def codigo_salida(totales: dict) -> int:
    if totales["REGRESION"] or totales["CAMBIO"] or totales["AUSENTE"]:
        return 1
    if totales["MEJORA"]:
        return 3
    if totales.get(INESTABLE):
        return 4
    return 0


# --- inestabilidad declarada (X1) ---------------------------------------------------------------------------------
_CARETS = re.compile(r"^\s*[\^~]+\s*$")


def fallo_inestable(pid: str, texto: str, decl: dict):
    """Diferencia (kB) si este fallo de unittest («CABECERA: …» + traza, de `_partes_unittest`) es EXACTAMENTE el
    declarado; si no, None. Exacto = misma subprueba, FAIL, un único marco en el archivo y la línea declarados, con el
    código declarado, y mensaje `A != B` con A, B > 0 y 0 < |A − B| ≤ `max_diferencia_kB`."""
    if pid != decl["subprueba"]:
        return None
    crudas = texto.splitlines()
    for i, l in enumerate(crudas):                 # el último fallo arrastra el resumen de unittest («Ran N tests…»)
        if re.match(r"^Ran \d+ tests? in ", l):
            crudas = crudas[:i]
            break
    lineas = [l for l in crudas if l.strip() and not set(l.strip()) <= {"-"} and not _CARETS.match(l)]
    if len(lineas) != 5 or not lineas[0].startswith("CABECERA: FAIL") or \
            lineas[1].strip() != "Traceback (most recent call last):":
        return None
    marco, codigo, mensaje = lineas[2].strip(), lineas[3].strip(), lineas[4].strip()
    if not (marco.startswith('File "') and re.search(r'[\\/]' + re.escape(decl["ubicacion"]) + "$", marco)):
        return None
    if codigo != decl["codigo"]:
        return None
    m = re.fullmatch(decl["patron"], mensaje)
    if not m or not all(g and g.isdigit() for g in m.groups()):
        return None
    a, b = int(m.group(1)), int(m.group(2))
    dif = abs(a - b)
    return dif if a > 0 and b > 0 and 0 < dif <= decl["max_diferencia_kB"] else None


def explicar_inestable(dif: dict, esperado: dict, trazas: dict):
    """Para una diferencia (REGRESION o CAMBIO) del verificador: {declaraciones, fallos} si se explica ENTERA por
    inestabilidades declaradas (condiciones 1 y 2 del docstring del módulo); si no, None."""
    decls = [d for d in esperado.get("inestables", []) if d["suite"] == dif["suite"] and d["prueba"] == dif["id"]]
    real = dif.get("real")
    if not decls or dif["veredicto"] not in ("REGRESION", "CAMBIO") or not real or real["estado"] != "FALLO":
        return None
    b = esperado["suites"][dif["suite"]]["pruebas"].get(dif["id"])
    texto = trazas.get(dif["id"])
    m = _EJECUTADAS.fullmatch(real.get("firma", ""))
    if b is None or texto is None or not m or m.group(1) != m.group(2):
        return None
    ran = re.findall(r"^Ran (\d+) tests? in ", texto, re.M)
    fin = re.findall(r"^FAILED \(failures=(\d+)\)$", texto, re.M)
    if ran != [m.group(1)] or fin != [m.group(3)]:
        return None
    conocidas = []
    if b["estado"] != "OK":
        me = _EJECUTADAS.fullmatch(b.get("firma", ""))
        conocidas = [s["subprueba"] for s in b.get("subpruebas", [])]
        if b["estado"] != "FALLO" or not me or me.group(1) != m.group(1) or int(me.group(3)) != len(conocidas):
            return None
    partes = linea_base_plataforma._partes_unittest(texto)
    if len(partes) != int(m.group(3)):
        return None
    pendientes, fallos = list(conocidas), []
    for pid, t in partes:
        if pid in pendientes:
            pendientes.remove(pid)
            continue
        for d in decls:
            kb = fallo_inestable(pid, t, d)
            if kb is not None:
                param = t.splitlines()[0][len("CABECERA: FAIL"):].strip()
                fallos.append({"declaracion": d["id"], "subprueba": f"{pid} {param}".strip(), "diferencia_kB": kb})
                break
        else:
            return None
    if pendientes or not fallos:
        return None
    return {"declaraciones": sorted({f["declaracion"] for f in fallos}), "fallos": fallos}


def orden_subprueba(subprueba: str) -> list:
    """La orden con la que el verificador de V2-F.1 ejecuta una prueba (`_python`: -B -W error::ResourceWarning -X dev
    -m unittest), por `eq3/lanzador_eq2.py` en Windows (`plataforma.orden_eq2`)."""
    o = plataforma.orden_eq2("-m", "unittest", subprueba)
    return o[:2] + ["-W", "error::ResourceWarning", "-X", "dev"] + o[2:]


def confirmar_inestable(decl: dict, sistema: Path, base: Path, ejecutar=plataforma.ejecutar) -> dict:
    """Condición 3: repite la subprueba aislada. Confirmada SOLO si pasa al menos `minimo_ok` de `repeticiones` veces
    y cada repetición fallida es EXACTAMENTE el fallo declarado; un fallo distinto la descarta en el acto."""
    carpeta = base / "inestables" / decl["id"]
    carpeta.mkdir(parents=True, exist_ok=False)
    ok, fallos, motivo, hechas = 0, [], None, 0
    for i in range(1, decl["repeticiones"] + 1):
        hechas = i
        r = ejecutar(orden_subprueba(decl["subprueba"]), cwd=sistema / "tests", env=_entorno(carpeta / f"tmp{i}"),
                     timeout=600)
        (carpeta / f"repeticion_{i}.txt").write_text(f"rc={r.returncode}\n{r.stdout}{r.stderr}", encoding="utf-8")
        ran = re.findall(r"^Ran (\d+) tests? in ", r.stderr, re.M)
        if r.returncode == 0 and ran == ["1"] and re.search(r"^OK$", r.stderr, re.M):
            ok += 1
            continue
        partes = linea_base_plataforma._partes_unittest(r.stderr)
        kb = [fallo_inestable(pid, t, decl) for pid, t in partes]
        if r.returncode == 0 or ran != ["1"] or not partes or None in kb or \
                not re.search(rf"^FAILED \(failures={len(partes)}\)$", r.stderr, re.M):
            motivo = f"repetición {i}: rc={r.returncode}, fallo distinto del declarado (ver repeticion_{i}.txt)"
            break
        fallos.append(kb)
    if motivo is None and ok < decl["minimo_ok"]:
        motivo = f"solo {ok} de {decl['repeticiones']} repeticiones correctas (mínimo {decl['minimo_ok']})"
    return {"confirmada": motivo is None, "correctas": ok, "repeticiones": hechas, "fallos_kB": fallos,
            "motivo": motivo, "registros": str(carpeta.relative_to(base))}


def revisar_inestables(cmp_: dict, esperado: dict, base: Path, sistema: Path, confirmar=confirmar_inestable) -> None:
    """Pasa a INESTABLE las diferencias que cumplen las tres condiciones; las demás conservan su veredicto. Todo
    intento queda anotado en la diferencia (`inestabilidad`)."""
    if not esperado.get("inestables"):
        return
    por_id = {d["id"]: d for d in esperado["inestables"]}
    trazas = linea_base_plataforma._trazas_verificador(base)
    tot = cmp_["totales"]
    for d in cmp_["diferencias"]:
        exp = explicar_inestable(d, esperado, trazas)
        if exp is None:
            continue
        confs = {i: confirmar(por_id[i], sistema, base) for i in exp["declaraciones"]}
        d["inestabilidad"] = {**exp, "confirmaciones": confs}
        if all(c["confirmada"] for c in confs.values()):
            tot[d["veredicto"]] -= 1
            d["veredicto_sin_inestabilidad"], d["veredicto"] = d["veredicto"], INESTABLE
            tot[INESTABLE] = tot.get(INESTABLE, 0) + 1


def proponer(obtenido: dict, ruta: Path, sello: str) -> None:
    prop = {"version": 1, "generada": sello,
            "nota": "PROPUESTA generada por linea_base.py --proponer: clasificar la causa de cada prueba no OK",
            "causas": {},
            "suites": {s: {"pruebas": {pid: ({"estado": "OK"} if d["estado"] == "OK" else
                                              {"estado": d["estado"], "firma": d["firma"], "causa": SIN_CLASIFICAR})
                                        for pid, d in r["pruebas"].items()}}
                       for s, r in obtenido.items()}}
    with ruta.open("x", encoding="utf-8") as f:
        json.dump(prop, f, ensure_ascii=False, indent=1)
        f.write("\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--salida", type=Path, help="directorio NUEVO (por defecto $TMPDIR/eq3_linea_base/<fecha>)")
    ap.add_argument("--sistema", type=Path, default=SISTEMA, help="versión a medir (por defecto equipo_ia_v3/sistema)")
    ap.add_argument("--esperada", type=Path, default=esperada_por_defecto(),
                    help="línea base con la que comparar (por defecto, la de esta plataforma)")
    ap.add_argument("--proponer", type=Path, help="escribe una línea base PROPUESTA (archivo nuevo) y no compara")
    ap.add_argument("--solo", choices=SUITES, action="append", help="ejecuta solo estas suites")
    ap.add_argument("--limite", type=int, default=1800, help="segundos máximos por suite")
    a = ap.parse_args(argv)
    suites = a.solo or list(SUITES)
    sistema = a.sistema.resolve()
    sello = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    base = (a.salida or Path(os.environ.get("TMPDIR") or tempfile.gettempdir()) / "eq3_linea_base" / sello).resolve()
    if plataforma.WINDOWS and "verificador" in suites and len(str(base)) > MAX_BASE_WINDOWS:
        # El verificador de V2-F.1 anida ~170 caracteres de carpetas bajo la salida y Windows no puede crear procesos
        # en carpetas de más de ~258: con una salida larga aparecerían fallos (WinError 267) que no son regresiones.
        print(f"salida rechazada: en Windows la ruta de salida debe tener como mucho {MAX_BASE_WINDOWS} caracteres "
              f"(tiene {len(str(base))}): {base}\n  use --salida con una carpeta nueva más corta")
        return 2
    esperada = None
    if not a.proponer:
        try:
            esperada = json.loads(a.esperada.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            print(f"línea base ilegible: {a.esperada}: {e}")
            return 2
        problemas = validar_esperada(esperada, suites)
        if problemas:
            print(f"línea base inválida ({len(problemas)} problemas), p. ej.: " + "; ".join(problemas[:5]))
            return 2
    try:
        base.mkdir(parents=True, exist_ok=False)
    except OSError as e:
        print("salida rechazada (debe ser un directorio nuevo):", e)
        return 2
    print(f"=== INICIO LÍNEA BASE V3 === {sello}\n  sistema: {sistema}\n  salida:  {base}", flush=True)
    obtenido = {}
    try:
        if "verificador" in suites:
            print("  [verificador] sistema/verificar.py ...", flush=True)
            obtenido["verificador"] = ejecutar_verificador(base, sistema, a.limite)
        if "codex" in suites:
            print("  [codex] codex_complementos/tests ...", flush=True)
            obtenido["codex"] = ejecutar_unittest("codex", FUENTES / "codex_complementos", base, sistema,
                                                  [sistema / "src"], a.limite, {"COMPLEMENTOS_SALIDA": "{TMP}"})
        if "contexto" in suites:
            print("  [contexto] contexto_ligero_v35/tests ...", flush=True)
            obtenido["contexto"] = ejecutar_unittest("contexto", FUENTES / "contexto_ligero_v35", base, sistema,
                                                     [sistema / "src"], a.limite)
    except (ErrorHerramienta, subprocess.TimeoutExpired, OSError, ValueError, KeyError) as e:
        print(f"ERROR de la herramienta: {type(e).__name__}: {e}\n=== FIN LÍNEA BASE V3: INCONCLUSA ===")
        return 2
    for s, r in obtenido.items():
        conteo = {}
        for d in r["pruebas"].values():
            conteo[d["estado"]] = conteo.get(d["estado"], 0) + 1
        r["conteo"] = dict(sorted(conteo.items()))
        print(f"  {s:12} {r['ejecutadas']:4} pruebas  {r['duracion_s']:7.1f} s  {r['conteo']}")
    (base / "estados.json").write_text(json.dumps({s: r["pruebas"] for s, r in obtenido.items()},
                                                  ensure_ascii=False, indent=1), encoding="utf-8")
    if a.proponer:
        proponer(obtenido, a.proponer, sello)
        print(f"=== FIN LÍNEA BASE V3: PROPUESTA escrita en {a.proponer} (NO es una comparación) ===")
        return 0
    cmp_ = comparar(obtenido, esperada)
    if "verificador" in obtenido:
        revisar_inestables(cmp_, esperada, base, sistema)
    tot = cmp_["totales"]
    conocidos = sum(1 for s in obtenido for d in esperada["suites"][s]["pruebas"].values() if d["estado"] != "OK")
    codigo = codigo_salida(tot)
    resumen = {"sello": sello, "python": sys.version.split()[0], "plataforma": sys.platform,
               "sistema": str(sistema), "esperada": str(a.esperada),
               "esperada_sha256": hashlib.sha256(a.esperada.read_bytes()).hexdigest(),
               "fallos_conocidos_en_linea_base": conocidos, "codigo_salida": codigo,
               "suites": {s: {k: v for k, v in r.items() if k != "pruebas"} for s, r in obtenido.items()},
               "comparacion": cmp_}
    (base / "resultado.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  comparación: {tot}")
    for d in cmp_["diferencias"][:60]:
        esp_e = d["esperado"]["estado"] if d["esperado"] else "—"
        real_e = d["real"]["estado"] if d["real"] else "—"
        print(f"    {d['veredicto']:9} {d['suite']}: {d['id']}  ({esp_e} → {real_e})")
        if "inestabilidad" in d:
            for i, c in d["inestabilidad"]["confirmaciones"].items():
                kb = ", ".join(str(f["diferencia_kB"]) for f in d["inestabilidad"]["fallos"])
                print(f"              inestabilidad declarada {i} (diferencias {kb} kB): "
                      + (f"CONFIRMADA, {c['correctas']}/{c['repeticiones']} repeticiones correctas" if c["confirmada"]
                         else f"NO CONFIRMADA: {c['motivo']}"))
    if len(cmp_["diferencias"]) > 60:
        print(f"    ... {len(cmp_['diferencias']) - 60} diferencias más en resultado.json")
    texto = {0: f"IGUAL A LA LÍNEA BASE ({conocidos} fallos conocidos documentados; no significa que todo funcione)",
             1: "CON REGRESIONES O CAMBIOS", 3: "MEJORAS PENDIENTES DE REVISIÓN",
             4: (f"IGUAL A LA LÍNEA BASE SALVO {tot.get(INESTABLE, 0)} PRUEBAS INESTABLES DECLARADAS Y CONFIRMADAS "
                 f"(NO CONCLUYENTES en esta ejecución; {conocidos} fallos conocidos documentados)")}[codigo]
    print(f"=== FIN LÍNEA BASE V3: {texto} === {base / 'resultado.json'}")
    return codigo


if __name__ == "__main__":
    sys.exit(main())
