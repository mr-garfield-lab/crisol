#!/usr/bin/env python3
"""Equipo IA V3.1 F0.5 — LÍNEA BASE DE OTRA PLATAFORMA derivada de la de Linux, con causa declarada por diferencia.

    python -B v3/linea_base_plataforma.py --ejecucion DIR --causas v3/causas_windows.json --salida ARCHIVO_NUEVO

`DIR` es la salida de `v3/linea_base.py --proponer` o de una comparación (contiene `estados.json`). La línea base
de Linux (`v3/linea_base_esperada.json`) NO se modifica: es la referencia de la que se parte.

Para cada prueba:
- **OK en esta plataforma** → OK (si en Linux no lo era, se anota como MEJORA de plataforma: no se oculta).
- **Mismo estado y firma que en Linux** → se conserva su causa de Linux.
- **Cualquier otra diferencia** → se busca la EVIDENCIA (firma, traza del verificador de V2-F.1 o bloque del
  registro de unittest) y se aplica la primera regla de `causas_*.json` cuyo patrón aparezca. La línea base guarda
  la causa, la regla y la línea de evidencia que la justifica.
- **Sin regla que la explique** → SIN_CLASIFICAR: no se escribe ninguna línea base (código 1) y se listan.
- **Ausente en esta plataforma** → error (código 2): una prueba que desaparece no se clasifica.

Así ninguna diferencia de plataforma entra en la línea base sin una causa revisable, y la puerta de regresión de
esa plataforma sigue detectando cualquier cambio posterior.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

V3 = Path(__file__).resolve().parent
LINUX = V3 / "linea_base_esperada.json"
SIN_CLASIFICAR = "SIN_CLASIFICAR"
MAX_EVIDENCIA = 300


def _trazas_verificador(ejecucion: Path) -> dict:
    """{id de comprobación: texto de su traza} del verificador de V2-F.1 en esa ejecución (puede no haber)."""
    trazas = {}
    for f in ejecucion.glob("tmp_verificador/**/verificacion/*/trazas/*.txt"):
        trazas[f.stem] = f.read_text(encoding="utf-8", errors="replace")
    return trazas


def _partes_unittest(registro: str) -> list:
    """[(id de prueba, texto)] con UNA entrada por cada fallo o error que informa unittest: una misma prueba puede
    tener varios (subTest, o un fallo más un error en tearDown) y cada uno se explica por separado. El texto empieza
    por «CABECERA: FAIL|ERROR <parámetros del subTest>»."""
    partes, actual = [], None
    for linea in registro.splitlines():
        m = re.match(r"^(ERROR|FAIL): \S+ \(([^)]+)\)(.*)$", linea)
        if m:
            actual = (m.group(2).split(" ")[0], [f"CABECERA: {m.group(1)} {m.group(3).strip()}".rstrip()])
            partes.append(actual)
            continue
        if actual is not None:
            if linea.startswith("=" * 20):
                actual = None
            else:
                actual[1].append(linea)
    return [(pid, "\n".join(lineas)) for pid, lineas in partes]


def _bloques_unittest(registro: str) -> dict:
    """{id de prueba: todos sus fallos y errores juntos} a partir de un registro de unittest (verbosity=2)."""
    bloques = {}
    for pid, texto in _partes_unittest(registro):
        bloques[pid] = (bloques[pid] + "\n" + texto) if pid in bloques else texto
    return bloques


def evidencias(ejecucion: Path) -> dict:
    """{suite: {id: texto de evidencia}}. Para el verificador de V2-F.1, si la traza contiene fallos de unittest, el
    valor es la LISTA de ellos («id de prueba\\ntexto»): cada uno tendrá que explicarse por separado."""
    ev = {"verificador": {}}
    for cid, texto in _trazas_verificador(ejecucion).items():
        partes = _partes_unittest(texto)
        ev["verificador"][cid] = [f"{pid}\n{b}" for pid, b in partes] if partes else texto
    for suite in ("codex", "contexto"):
        log = ejecucion / f"{suite}.log"
        ev[suite] = _bloques_unittest(log.read_text(encoding="utf-8", errors="replace")) if log.is_file() else {}
    return ev


def anadir_evidencia(ev: dict, extra: dict) -> None:
    """Añade líneas de evidencia medida: a cada fallo cuya prueba coincide con el id, o a la comprobación entera."""
    for suite, por_id in extra.items():
        destino = ev.setdefault(suite, {})
        for clave, lineas in por_id.items():
            texto = "\n".join(lineas)
            for cid, valor in list(destino.items()):
                if isinstance(valor, list):
                    destino[cid] = [p + "\n" + texto if p.split("\n", 1)[0] == clave else p for p in valor]
            if not any(isinstance(v, list) and any(p.split("\n", 1)[0] == clave for p in v)
                       for v in destino.values()):
                previo = destino.get(clave, "")
                if isinstance(previo, str):
                    destino[clave] = (previo + "\n" + texto).strip("\n")


def clasificar(texto: str, reglas: list, suite: str):
    """(causa, regla, línea de evidencia) de la primera regla aplicable, o (None, None, None)."""
    for i, r in enumerate(reglas):
        if r.get("suites") and suite not in r["suites"]:
            continue
        m = re.search(r["patron"], texto, re.M)
        if m:
            ini = texto.rfind("\n", 0, m.start()) + 1
            fin = texto.find("\n", m.end())
            return r["causa"], i, texto[ini:fin if fin != -1 else None].strip()[:MAX_EVIDENCIA]
    return None, None, None


def derivar(linux: dict, estados: dict, causas: dict, ev: dict, plataforma: str) -> tuple:
    """(línea base derivada, sin clasificar, ausentes)."""
    for c in causas["causas"]:
        if c in linux["causas"]:
            raise ValueError(f"la causa {c} ya existe en la línea base de Linux")
    for r in causas["reglas"]:
        if r["causa"] not in causas["causas"] and r["causa"] not in linux["causas"]:
            raise ValueError(f"regla con causa no declarada: {r['causa']}")
        re.compile(r["patron"])
    # Reglas especiales: «bloquea» = causa DEMOSTRADA de un fallo funcional que no se acepta (sigue bloqueando);
    # «solo_si_todo_explicado» = agregados (p. ej. el resumen de cumplimiento), aplicables solo si nada más falta.
    normales = [r for r in causas["reglas"] if not r.get("solo_si_todo_explicado")]
    agregadas = [r for r in causas["reglas"] if r.get("solo_si_todo_explicado")]
    bloquean = {r["causa"] for r in causas["reglas"] if r.get("bloquea")}
    suites, sin, ausentes, mejoras = {}, [], [], []
    con_causa = []
    for suite, base in linux["suites"].items():
        reales = estados.get(suite)
        if reales is None:
            ausentes.append(f"{suite}: suite completa")
            continue
        pruebas = {}
        for pid in sorted(set(base["pruebas"]) | set(reales)):
            l, w = base["pruebas"].get(pid), reales.get(pid)
            if w is None:
                ausentes.append(f"{suite}: {pid}")
                continue
            if w["estado"] == "OK":
                pruebas[pid] = {"estado": "OK"}
                if l is not None and l["estado"] != "OK":
                    mejoras.append(f"{suite}: {pid}")
                continue
            if l is not None and l["estado"] == w["estado"] and l.get("firma", "") == w["firma"]:
                pruebas[pid] = dict(l)
                continue
            evid = ev.get(suite, {}).get(pid, "")
            # Varias subpruebas: CADA una debe tener su regla; con una sola sin explicar, la prueba queda sin clasificar.
            partes = evid if isinstance(evid, list) and evid else ["\n".join([w["firma"], evid if isinstance(evid, str) else ""])]
            explicadas, sin_explicar = [], []
            for parte in partes:
                causa, regla, linea = clasificar(parte, normales, suite)
                if regla is not None:
                    regla = causas["reglas"].index(normales[regla])
                (explicadas if causa else sin_explicar).append(
                    {"subprueba": parte.splitlines()[0][:160], "causa": causa, "regla": regla, "evidencia": linea})
            entrada = {"estado": w["estado"], "firma": w["firma"],
                       "linux": l and {k: l.get(k) for k in ("estado", "firma", "causa")}}
            if sin_explicar:
                entrada.update(causa=SIN_CLASIFICAR, sin_explicar=sin_explicar, explicadas=explicadas)
                sin.append(f"{suite}: {pid} [{w['estado']}] {w['firma'][:120]} — sin explicar: "
                           + "; ".join(x["subprueba"][:70] for x in sin_explicar[:3]))
            else:
                cuenta = {}
                for x in explicadas:
                    cuenta[x["causa"]] = cuenta.get(x["causa"], 0) + 1
                entrada.update(causa=max(cuenta, key=cuenta.get), causas=sorted(cuenta), regla=explicadas[0]["regla"],
                               evidencia=explicadas[0]["evidencia"], subpruebas=explicadas)
                if bloquean & set(cuenta):
                    con_causa.append(f"{suite}: {pid} [{w['estado']}] causas {sorted(cuenta)} (BLOQUEA: "
                                     f"{', '.join(sorted(bloquean & set(cuenta)))})")
                    entrada["bloquea"] = sorted(bloquean & set(cuenta))
            pruebas[pid] = entrada
        suites[suite] = {"pruebas": pruebas}
    # Segunda pasada: agregados, solo si en su suite no queda nada sin explicar salvo ellos mismos.
    for suite, s in suites.items():
        pendientes = [p for p, d in s["pruebas"].items() if d.get("causa") == SIN_CLASIFICAR]
        for pid in pendientes:
            d = s["pruebas"][pid]
            causa, regla, linea = clasificar(d["firma"], agregadas, suite)
            if causa and len(pendientes) == 1 and not con_causa:
                d.update(causa=causa, causas=[causa], regla=causas["reglas"].index(agregadas[regla]),
                         evidencia=linea, subpruebas=[{"subprueba": pid, "causa": causa, "evidencia": linea}])
                d.pop("sin_explicar", None)
                sin[:] = [x for x in sin if not x.startswith(f"{suite}: {pid} [")]
    # Lo que tiene causa pero BLOQUEA se trata como no aceptado (visible en la puerta), con su causa documentada.
    for x in con_causa:
        sin.append(x)
    derivada = {"version": 1, "plataforma": plataforma,
                "nota": (f"Línea base de {plataforma} DERIVADA de la de Linux (que no cambia). Cada diferencia tiene "
                         "causa de plataforma, regla y evidencia; no significa que esas pruebas funcionen aquí."),
                "causas": {**linux["causas"], **causas["causas"]}, "mejoras_de_plataforma": mejoras,
                "suites": suites}
    # X1: las inestabilidades declaradas pasan tal cual; v3/linea_base.py las valida y solo las aplica con su firma
    # exacta y confirmación por repetición. Su causa tiene que ser de esta plataforma.
    if causas.get("inestables"):
        for d in causas["inestables"]:
            if d.get("causa") not in causas["causas"]:
                raise ValueError(f"inestabilidad con causa no declarada: {d.get('causa')}")
        derivada["inestables"] = causas["inestables"]
    return derivada, sin, ausentes


def sin_rutas_locales(obj, pares: list):
    """Copia de `obj` con las rutas de ESTA máquina (ejecución, proyecto, carpeta personal) sustituidas por marcas en
    todos sus textos: la línea base y su revisión se comparten, y la evidencia citada (trazas) las contiene."""
    if isinstance(obj, dict):
        return {k: sin_rutas_locales(v, pares) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sin_rutas_locales(v, pares) for v in obj]
    if isinstance(obj, str):
        for ruta, marca in pares:
            obj = obj.replace(ruta, marca)
    return obj


def rutas_locales(ejecucion: Path) -> list:
    import linea_base as LB
    pares = LB.reemplazos(ejecucion.resolve(), LB.SISTEMA.resolve())
    pares += [(v, "<CASA>") for v in LB.plataforma.variantes_ruta(Path.home())]
    for carpeta in (ejecucion.resolve().parent, LB.REPO.resolve().parent):     # otras ejecuciones y copias vecinas
        pares += [(v, "<TRABAJO>") for v in LB.plataforma.variantes_ruta(carpeta)]
    return sorted(pares, key=lambda p: -len(p[0]))


def firmas(derivada: dict) -> dict:
    return {(s, p): d.get("firma", "") for s, x in derivada["suites"].items() for p, d in x["pruebas"].items()}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ejecucion", type=Path, required=True, help="salida de v3/linea_base.py (con estados.json)")
    ap.add_argument("--causas", type=Path, required=True, help="catálogo de causas y reglas de la plataforma")
    ap.add_argument("--salida", type=Path, required=True, help="archivo NUEVO de línea base derivada")
    ap.add_argument("--linux", type=Path, default=LINUX, help="línea base de referencia (no se modifica)")
    ap.add_argument("--parcial", action="store_true",
                    help="escribe la línea base con SOLO lo justificado; lo no explicado sigue esperando el estado de "
                         "Linux y por tanto sigue fallando (visible y bloqueante) en la puerta de regresión")
    ap.add_argument("--evidencia", action="append", default=[], metavar="ARCHIVO",
                    help="evidencia adicional MEDIDA (JSON {suite: {id: [líneas]}}; el id es el de una prueba de "
                         "unittest o el de una comprobación): se añade a la evidencia de cada fallo de ese id")
    ap.add_argument("--revision", type=Path, help="escribe aquí la derivación completa (incluido lo no explicado)")
    ap.add_argument("--contrafactual", action="append", default=[], metavar="SUITE=ARCHIVO",
                    help="resultado de repetir la suite con un adaptador: cada prueba suma a su evidencia la línea "
                         "«CONTRAFACTUAL: <veredicto>» (las reglas pueden exigirla)")
    a = ap.parse_args(argv)
    linux = json.loads(a.linux.read_text(encoding="utf-8"))
    causas = json.loads(a.causas.read_text(encoding="utf-8"))
    estados = json.loads((a.ejecucion / "estados.json").read_text(encoding="utf-8"))
    ev = evidencias(a.ejecucion)
    for cf in a.contrafactual:
        suite, _, archivo = cf.partition("=")
        for fila in json.loads(Path(archivo).read_text(encoding="utf-8"))["pruebas"]:
            ev.setdefault(suite, {})[fila["id"]] = (ev.get(suite, {}).get(fila["id"], "")
                                                    + f"\nCONTRAFACTUAL: {fila['veredicto']}"
                                                    + f"\nCONTRAFACTUAL_FIRMA: {fila.get('con_adaptador_firma') or ''}")
    for archivo in a.evidencia:
        anadir_evidencia(ev, json.loads(Path(archivo).read_text(encoding="utf-8")))
    try:
        derivada, sin, ausentes = derivar(linux, estados, causas, ev, causas["plataforma"])
    except (KeyError, ValueError, re.error) as e:
        print(f"catálogo o línea base inválidos: {type(e).__name__}: {e}")
        return 2
    if ausentes:
        print(f"{len(ausentes)} pruebas AUSENTES en esta plataforma (no se clasifican): " + "; ".join(ausentes[:10]))
        return 2
    # Ninguna ruta de esta máquina en lo que se escribe. Las FIRMAS no pueden contener ninguna: si la sustitución
    # cambiara una, esa firma dependería de la máquina y la línea base no valdría en otra carpeta ni en otro equipo.
    limpia = sin_rutas_locales(derivada, rutas_locales(a.ejecucion))
    dependientes = [f"{s}: {p}" for (s, p), f in firmas(derivada).items() if firmas(limpia)[(s, p)] != f]
    if dependientes:
        print(f"{len(dependientes)} firmas dependen de rutas de esta máquina (falta normalizarlas): "
              + "; ".join(dependientes[:5]))
        return 2
    derivada, sin = limpia, sin_rutas_locales(sin, rutas_locales(a.ejecucion))
    if a.revision:                                                  # todo, también lo no explicado, para revisarlo
        a.revision.write_text(json.dumps({"sin_clasificar": sin, **derivada}, ensure_ascii=False, indent=1),
                              encoding="utf-8")
    if sin:
        print(f"{len(sin)} diferencias SIN CLASIFICAR" + ("" if a.parcial else "; no se escribe ninguna línea base") + ":")
        for s in sin:
            print("  " + s)
        if not a.parcial:
            return 1
        # PARCIAL: lo no explicado conserva la expectativa de Linux → la puerta de regresión de esta plataforma lo
        # seguirá marcando (REGRESION/CAMBIO) hasta que tenga causa. Nada sin explicar se acepta.
        for suite, s in derivada["suites"].items():
            for pid, d in list(s["pruebas"].items()):
                if d.get("causa") == SIN_CLASIFICAR or d.get("bloquea"):
                    if d.get("bloquea"):
                        derivada.setdefault("bloqueantes_con_causa", {})[f"{suite}: {pid}"] = {
                            k: d.get(k) for k in ("estado", "firma", "causas", "subpruebas")}
                    previo = linux["suites"][suite]["pruebas"].get(pid)
                    if previo is None:
                        del s["pruebas"][pid]
                    else:
                        s["pruebas"][pid] = dict(previo)
        derivada["bloqueantes_sin_explicar"] = sin
    derivada["derivada_de"] = {"archivo": a.linux.name, "sha256": hashlib.sha256(a.linux.read_bytes()).hexdigest()}
    derivada["catalogo"] = {"archivo": a.causas.name, "sha256": hashlib.sha256(a.causas.read_bytes()).hexdigest()}
    try:
        with a.salida.open("x", encoding="utf-8") as f:                 # nunca sobrescribe
            json.dump(derivada, f, ensure_ascii=False, indent=1)
            f.write("\n")
    except FileExistsError:
        print(f"salida rechazada (debe ser un archivo nuevo): {a.salida}")
        return 2
    por_causa = {}
    for s in derivada["suites"].values():
        for d in s["pruebas"].values():
            if d.get("regla") is not None:
                por_causa[d["causa"]] = por_causa.get(d["causa"], 0) + 1
    print(f"línea base de {causas['plataforma']} escrita en {a.salida}: diferencias por causa {por_causa}; "
          f"mejoras de plataforma: {len(derivada['mejoras_de_plataforma'])}; "
          f"BLOQUEANTES sin explicar: {len(derivada.get('bloqueantes_sin_explicar', []))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
