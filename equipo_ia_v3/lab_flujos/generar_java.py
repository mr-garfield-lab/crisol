"""Banco de flujos grandes · proyecto sintético en JAVA (determinista) y sus tareas con oráculo exacto.

Mismo diseño que `generar_corpus.py` (Python), adaptado a Java para medir la lectura de Java con cerebros reales:
clases del mismo paquete con métodos estáticos parecidos entre sí (distractores), un número escondido en cada método
(`int factor = N;`), constantes `static final`, llamadas entre clases y trampas. El proyecto debe COMPILAR con javac
(se comprueba en `preparar`). Mismo `SEMILLA` → mismos bytes.

Tipos: A aguja en un método · B dos saltos (un método llama al de OTRA clase) · D constante de clase ·
T trampa (no existe) · P las mismas búsquedas parafraseadas (parcial y total). Sin recuentos (C) en esta versión.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import generar_corpus as GP                              # mismos verbos, objetos, adjetivos y sinónimos

SEMILLA = 20261116
N_CLASES = 64
METODOS_POR_CLASE = 8
PAQUETE = "com.ejemplo.logistica"


def camel(nombre: str) -> str:
    """calcular_recargo_urgente -> calcularRecargoUrgente"""
    a, *resto = nombre.split("_")
    return a + "".join(x.capitalize() for x in resto)


def clase(area: str, i: int) -> str:
    return f"{area.capitalize()}{i:03d}"


def _cuerpo(rnd, nombre: str, factor: int, extra: int, llama=None) -> list:
    var = rnd.choice(["importe", "cantidad", "valor", "total"])
    L = [f"    public static double {nombre}(Map<String, Double> registro, Map<String, String> opciones) {{",
         f"        double {var} = registro.getOrDefault(\"{var}\", 0.0);",
         f"        int factor = {factor};"]
    for i in range(extra):
        k = rnd.randint(2, 97)
        L += [f"        if (registro.containsKey(\"campo{i}\")) {{",
              f"            {var} += (registro.get(\"campo{i}\") % {k}) * 0.{rnd.randint(1, 9)};",
              f"        }} else if (\"revision{i}\".equals(opciones.get(\"modo\"))) {{",
              f"            {var} -= {k} / 10.0;",
              "        }"]
    L.append(f"        double resultado = {var} * factor / 100.0;")
    if llama:
        L.append(f"        resultado += {llama[0]}.{llama[1]}(registro, opciones);")
    L += ["        return resultado;", "    }", ""]
    return L


def generar(destino: Path) -> dict:
    rnd = random.Random(SEMILLA)
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=False)
    usados, clases = set(), []
    for c in range(N_CLASES):
        area = GP.AREAS[c % len(GP.AREAS)]
        clases.append({"nombre": clase(area, c), "metodos": [], "constantes": {}})
    for cl in clases:
        for _ in range(METODOS_POR_CLASE):
            cl["metodos"].append({"py": GP._nombre_funcion(rnd, usados), "factor": rnd.randint(101, 9899),
                                  "extra": rnd.randint(3, 6), "llama": None})
        for _ in range(3):
            n = f"LIMITE_{rnd.choice(GP.OBJETOS).upper()}_{rnd.choice(GP.ADJ).upper()}"
            cl["constantes"][n] = rnd.randint(11, 9973)
    tareas = []
    for i, c in enumerate(rnd.sample(range(N_CLASES), 6)):
        m = rnd.choice(clases[c]["metodos"])
        tareas.append({"id": f"JA{i + 1}", "tipo": "A", "clase": "entero", "respuesta": m["factor"],
                       "pregunta": f"En el proyecto, el método `{camel(m['py'])}` asigna un número entero a la variable "
                                   "local `factor`. ¿Qué número es?",
                       "donde": [f"{clases[c]['nombre']}.java::{clases[c]['nombre']}.{camel(m['py'])}"], "py": m["py"]})
    for i in range(4):
        a, b = rnd.sample(range(N_CLASES), 2)
        f = rnd.choice([x for x in clases[a]["metodos"] if x["llama"] is None])
        g = rnd.choice(clases[b]["metodos"])
        f["llama"] = (clases[b]["nombre"], camel(g["py"]))
        tareas.append({"id": f"JB{i + 1}", "tipo": "B", "clase": "entero", "respuesta": g["factor"],
                       "pregunta": f"El método `{camel(f['py'])}` llama a un método de OTRA clase del proyecto. ¿Qué "
                                   "número entero asigna ese OTRO método a su variable local `factor`?",
                       "donde": [f"{clases[a]['nombre']}.java::{clases[a]['nombre']}.{camel(f['py'])}",
                                 f"{clases[b]['nombre']}.java::{clases[b]['nombre']}.{camel(g['py'])}"],
                       "py": f["py"]})
    for i, c in enumerate(rnd.sample(range(N_CLASES), 3)):
        n, v = rnd.choice(sorted(clases[c]["constantes"].items()))
        tareas.append({"id": f"JD{i + 1}", "tipo": "D", "clase": "entero", "respuesta": v,
                       "pregunta": f"En la clase `{clases[c]['nombre']}`, ¿qué valor entero tiene la constante `{n}`?",
                       "donde": [f"{clases[c]['nombre']}.java::{clases[c]['nombre']}.{n}"], "constante": n})
    for cl in clases:
        L = [f"package {PAQUETE};", "", "import java.util.Map;", "",
             f"/** Operaciones de {cl['nombre'][:-3].lower()} (proyecto sintético del banco de flujos). */",
             f"public final class {cl['nombre']} {{", ""]
        for n, v in cl["constantes"].items():
            L.append(f"    public static final int {n} = {v};")
        L.append("")
        for m in cl["metodos"]:
            L += _cuerpo(rnd, camel(m["py"]), m["factor"], m["extra"], m["llama"])
        L += [f"    private {cl['nombre']}() {{", "    }", "}"]
        (destino / f"{cl['nombre']}.java").write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")
    tareas += _trampas(clases, usados)
    tareas += _parafrasis(tareas)
    for t in tareas:
        t.pop("py", None)
    total = sum(p.stat().st_size for p in destino.glob("*.java"))
    return {"semilla": SEMILLA, "lenguaje": "java", "modulos": N_CLASES, "caracteres": total,
            "tokens_estimados": total // 3, "tareas": tareas}


def _trampas(clases: list, usados: set) -> list:
    rnd = random.Random(SEMILLA + 1)
    todas = {n for c in clases for n in c["constantes"]}
    while True:
        f = f"{rnd.choice(GP.VERBOS)}_{rnd.choice(GP.OBJETOS)}_{rnd.choice(GP.ADJ)}"
        if f not in usados:
            break
    c2 = rnd.choice(clases)
    real = sorted(c2["constantes"])[0]
    pre = real.rsplit("_", 1)[0]
    casi = next(f"{pre}_{a.upper()}" for a in GP.ADJ if f"{pre}_{a.upper()}" not in todas)
    c3 = rnd.choice(clases)
    m3 = rnd.choice(c3["metodos"])
    base = {"tipo": "T", "clase": "ausente", "respuesta": "NO_ENCONTRADO", "donde": []}
    return [
        {**base, "id": "JT1", "py": f, "pregunta": f"En el proyecto, el método `{camel(f)}` asigna un número entero a "
                                                   "la variable local `factor`. ¿Qué número es?"},
        {**base, "id": "JT2", "pregunta": f"En la clase `{c2['nombre']}`, ¿qué valor entero tiene la constante "
                                          f"`{casi}`?", "parecida": real},
        {**base, "id": "JT3", "pregunta": f"En el proyecto, el método `{camel(m3['py'])}` asigna un número entero a la "
                                          "variable local `limiteDiario`. ¿Qué número es?"},
    ]


def _parafrasis(tareas: list) -> list:
    out = []
    for nivel, suf in (("parcial", "p"), ("total", "t")):
        for t in [x for x in tareas if x["tipo"] in ("A", "B") or x["id"] == "JT1"]:
            desc = GP.describir(t["py"], nivel)
            if t["tipo"] == "B":
                q = (f"El método que {desc} llama a un método de OTRA clase. ¿Qué número entero asigna ese OTRO método "
                     "a su variable local `factor`?")
            else:
                q = f"En el proyecto hay un método que {desc}. ¿Qué número entero asigna a su variable local `factor`?"
            out.append({**t, "id": f"JP{t['id'][1:]}{suf}", "tipo": "P", "tipo_origen": t["tipo"], "origen": t["id"],
                        "nivel": nivel, "pregunta": q})
    return out


if __name__ == "__main__":
    salida = Path(sys.argv[1])
    datos = generar(salida / "corpus")
    (salida / "tareas.json").write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in datos.items() if k != "tareas"}, ensure_ascii=False))
    print("tareas:", len(datos["tareas"]), [t["id"] for t in datos["tareas"]])
