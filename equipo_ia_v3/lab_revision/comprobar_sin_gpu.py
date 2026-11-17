"""Comprobaciones del banco de revisión SIN GPU, con tres cerebros FALSOS (perfecto, chapucero y alarmista).

    python -B -X utf8 lab_revision/comprobar_sin_gpu.py           (desde equipo_ia_v3/; necesita un JDK para Java)
Sale con 0 solo si la puntuación distingue bien los tres comportamientos en las dos condiciones.
"""
from __future__ import annotations

import difflib
import re
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import banco_revision as BR  # noqa: E402
import corpus as C  # noqa: E402

RESULTADOS = []


def comprobar(nombre, ok, detalle=""):
    RESULTADOS.append(ok)
    print(f"[{'PASA' if ok else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else ""))


def parche_hacia_base(codigo: str, base: str) -> list:
    """Instrucciones ARREGLO/INSERTAR/ELIMINAR (numeración de `codigo`) que lo convierten en `base`."""
    a, b, out = codigo.split("\n"), base.split("\n"), []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if op == "replace":
            for k in range(i2 - i1):
                out.append(f"ARREGLO {i1 + k + 1}: {b[j1 + k]}" if j1 + k < j2 else f"ELIMINAR {i1 + k + 1}")
            for k in range(i2 - i1, j2 - j1):
                out.append(f"INSERTAR {i2 + 1}: {b[j1 + k]}")
        elif op == "delete":
            out += [f"ELIMINAR {k + 1}" for k in range(i1, i2)]
        elif op == "insert":
            out += [f"INSERTAR {i1 + 1}: {b[k]}" for k in range(j1, j2)]
    return out


def fabrica(modo: str):
    oraculos = {c["codigo"]: sorted({e["linea"] for e in c["errores"]}) for c in C.generar()}

    def falso(msgs, n):
        u = msgs[-1]["content"]
        archivo = re.search(r"ARCHIVO: (\S+)", u).group(1)
        lang = "python" if archivo.endswith(".py") else "java"
        codigo = "\n".join(re.sub(r"^\s*\d+\| ?", "", l) for l in u.split("```\n", 1)[1].split("\n```")[0].split("\n"))
        base = C.BASES[(lang, archivo.split(".")[0])]
        limpio = codigo in (base, C._trampa(base, lang, C.LIMPIOS_TRAMPA[(lang, archivo.split(".")[0])][0]))
        if limpio:
            if modo == "alarmista":
                return "ERROR: línea 1 | sintaxis | inventado\nARREGLO 1: " + codigo.split("\n")[0] + "  \nRESPUESTA: LISTO", {}
            return "SIN_ERRORES\nRESPUESTA: LISTO", {}
        if modo == "alarmista":
            return "SIN_ERRORES\nRESPUESTA: LISTO", {}
        p = parche_hacia_base(codigo, base)
        if modo == "por_fases":                  # solo lo que señala el compilador (y los import que falten)
            dadas = {int(x) for x in re.findall(r"- línea (\d+):", u)}
            p = [x for x in p if x.startswith("INSERTAR") or int(re.search(r"\d+", x).group()) in dadas]
        lineas = oraculos.get(codigo) or sorted({int(re.search(r"\d+", x).group()) for x in p})
        errores = [f"ERROR: línea {n} | x | y" for n in lineas]          # la línea que FALLA, no la del arreglo
        if modo == "chapucero":
            primera = codigo.split("\n")[0]
            p.append(f"ARREGLO 1: {primera} {'#' if lang == 'python' else '//'} tocado")
        return "\n".join(errores + p + ["RESPUESTA: LISTO"]), {}
    return falso


def main() -> int:
    base = Path(tempfile.mkdtemp(prefix="banco_revision_"))
    try:
        e = base / "prep"
        BR.preparar(e)
        comprobar("validación del oráculo con las herramientas", True, "32/32")
        esperado = {"perfecto": ({"arreglado": 24}, {"correcto": 8}),
                    "chapucero": ({"arreglado_tocando_mas": 24}, {"correcto": 8}),
                    "alarmista": ({"sin_cambios": 24}, {"falsa_alarma": 8})}
        for modo, (con_error, limpios) in esperado.items():
            d = base / modo
            shutil.copytree(e, d)
            BR.correr_modelo("falso", d, fabrica(modo), lambda: False)
            F = BR.leer_filas(d)
            for cond in BR.CONDICIONES:
                fs = [f for f in F if f["condicion"] == cond]
                a = dict(Counter(f["estado"] for f in fs if f["oraculo"]))
                b = dict(Counter(f["estado"] for f in fs if not f["oraculo"]))
                exp_b = {"correcto": 8} if cond == "herramienta" else limpios   # con herramienta no se pregunta
                exp_a = con_error if not (modo == "alarmista" and cond == "herramienta") else {"sin_cambios": 24}
                comprobar(f"{modo} / {cond}: con error {a}, correctos {b}", a == exp_a and b == exp_b)
            if modo == "perfecto":
                sol = [f for f in F if f["condicion"] == "solo" and f["oraculo"]]
                bien = sum(len(f["encontrados"]) for f in sol)
                total = sum(len({x["linea"] for x in f["oraculo"]}) for f in sol)
                comprobar("perfecto / solo: señala todas las líneas del oráculo", bien == total, f"{bien}/{total}")
                f2 = [f for f in F if f["condicion"] == "herramienta" and f["caso"].endswith("_F2")]
                comprobar("dos fases con herramienta: arregladas", all(f["estado"] == "arreglado" for f in f2),
                          ", ".join(f"{f['caso']}:{f['llamadas']} llamada(s)" for f in f2))
        d = base / "por_fases"
        shutil.copytree(e, d)
        BR.correr_modelo("falso", d, fabrica("por_fases"), lambda: False)
        f2 = [f for f in BR.leer_filas(d) if f["condicion"] == "herramienta" and f["caso"].endswith("_F2")]
        comprobar("bucle con herramienta: las dos fases se arreglan en 2 llamadas",
                  all(f["estado"] == "arreglado" and f["llamadas"] == 2 for f in f2),
                  ", ".join(f"{f['caso']}:{f['estado']}/{f['llamadas']}" for f in f2))
        # Tanda 2: falsos que imitan los dos fallos reales de la tanda 1, en «herramienta» y «herramienta2».
        e2 = base / "t2"
        BR.preparar(e2, ("herramienta", "herramienta2"))
        casos = {c["id"]: c for c in C.generar()}

        def import_dentro(msgs, n):                    # el import ENCIMA de la línea del campo (como qwen25)
            u = msgs[-1]["content"]
            if "ArrayList" in u and "import java.util.ArrayList" not in u:
                linea = next(int(x) for x in re.findall(r"^\s*(\d+)\| .*new ArrayList", u, re.M))
                return f"ERROR: línea {linea} | símbolo | falta import\nARREGLO {linea}: import java.util.ArrayList;\n" \
                       "RESPUESTA: LISTO", {}
            return "RESPUESTA: LISTO", {}

        def repite(msgs, n):                           # repite el arreglo malo hasta que recibe un AVISO
            u = msgs[-1]["content"]
            if "return totl" not in u and "total = totl" not in u:
                return "RESPUESTA: LISTO", {}
            linea = next(int(x) for x in re.findall(r"^\s*(\d+)\| .*(?:return totl|total = totl)", u, re.M))
            if "AVISO: tu arreglo anterior" in u:
                return f"ARREGLO {linea}:     return total\nRESPUESTA: LISTO", {}
            return f"ARREGLO {linea}:     total = totl\nRESPUESTA: LISTO", {}

        for nombre, falso, caso, cond, esperado, llamadas in [
                ("import_dentro", import_dentro, "JV_INV_E4", "herramienta", "no_compila", 3),
                ("import_dentro", import_dentro, "JV_INV_E4", "herramienta2", "arreglado", 1),
                ("repite", repite, "PY_INV_E2", "herramienta", "no_compila", 3),
                ("repite", repite, "PY_INV_E2", "herramienta2", "arreglado", 2)]:
            d = base / f"t2_{nombre}"
            if not d.exists():
                shutil.copytree(e2, d)
                BR.correr_modelo("falso", d, falso, lambda: False)
            f = next(x for x in BR.leer_filas(d) if x["caso"] == caso and x["condicion"] == cond)
            extra = ""
            if caso == "JV_INV_E4" and cond == "herramienta2":
                extra = " · campo conservado" if "private final List<Integer> unidades = new ArrayList<>();" in f["final"] \
                    else " · ¡CAMPO PERDIDO!"
            comprobar(f"tanda 2 · {nombre} / {cond}: {f['estado']} en {f['llamadas']} llamada(s){extra}",
                      f["estado"] == esperado and f["llamadas"] == llamadas and "PERDIDO" not in extra)
        _ = casos
        # Tanda 3: orden anidada y import que no casa con cómo se usa el nombre (lo que hizo qwen25 en la tanda 2).
        e3 = base / "t3"
        BR.preparar(e3, ("herramienta2", "herramienta3"))

        def anidada(msgs, n):
            u = msgs[-1]["content"]
            if "Arrays" in u and "import java.util.Arrays" not in u:
                linea = next(int(x) for x in re.findall(r"^\s*(\d+)\| .*Arrays\.copyOf", u, re.M))
                return f"ARREGLO {linea}: INSERTAR {linea}: import java.util.Arrays;\nRESPUESTA: LISTO", {}
            return "RESPUESTA: LISTO", {}

        def from_import(msgs, n):
            u = msgs[-1]["content"]
            if "math.ceil" not in u or "import math" in u:
                return "RESPUESTA: LISTO", {}
            if "AVISO: el sistema colocó arriba tu import" in u:
                return "INSERTAR 1: import math\nRESPUESTA: LISTO", {}
            linea = next(int(x) for x in re.findall(r"^\s*(\d+)\| .*math\.ceil", u, re.M))
            return f"ARREGLO {linea}: from math import ceil\nRESPUESTA: LISTO", {}

        for nombre, falso, caso, cond, esperado, llamadas in [
                ("anidada", anidada, "JV_RUT_E4", "herramienta3", "arreglado", 1),
                ("from_import", from_import, "PY_RUT_E3", "herramienta2", "no_compila", 3),
                ("from_import", from_import, "PY_RUT_E3", "herramienta3", "arreglado", 2)]:
            d = base / f"t3_{nombre}"
            if not d.exists():
                shutil.copytree(e3, d)
                BR.correr_modelo("falso", d, falso, lambda: False)
            f = next(x for x in BR.leer_filas(d) if x["caso"] == caso and x["condicion"] == cond)
            comprobar(f"tanda 3 · {nombre} / {cond}: {f['estado']} en {f['llamadas']} llamada(s)",
                      f["estado"] == esperado and f["llamadas"] == llamadas)
    finally:
        shutil.rmtree(base, ignore_errors=True)
    print(f"\n{sum(RESULTADOS)}/{len(RESULTADOS)} comprobaciones pasan")
    return 0 if all(RESULTADOS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
