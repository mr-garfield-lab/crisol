"""Humo del banco de flujos en JAVA con cerebros falsos (sin GPU): la combinación ligero + identidad funciona en Java.

    python -B -X utf8 lab_flujos/humo/comprobar_java_banco.py         (desde equipo_ia_v3/; necesita javac)
"""
from __future__ import annotations

import json
import re
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))
import banco_flujos as BF  # noqa: E402

RESULTADOS = []


def comprobar(nombre, ok, detalle=""):
    RESULTADOS.append(ok)
    print(f"[{'PASA' if ok else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else ""))


def main() -> int:
    base = Path(tempfile.mkdtemp(prefix="banco_java_"))
    try:
        e = base / "j"
        prep = BF.preparar(e, ("ligero", "combinada"), None, "java")
        comprobar("el proyecto Java compila con javac", (prep.get("compila") or {}).get("codigo") == 0)
        T = {t["pregunta"]: t for t in json.loads((e / "tareas.json").read_text(encoding="utf-8"))["tareas"]}
        simple = lambda t: t["donde"][0].split("::")[1].split(".")[-1] if t.get("donde") else None

        def falso(msgs, n):
            sis, u = msgs[0]["content"], msgs[-1]["content"]
            if "Propón palabras clave" in sis:
                o = simple(T[msgs[1]["content"].split("LUEGO: ", 1)[1]]) or "nada"
                return "\n".join(f"CLAVE: {w}" for w in re.findall(r"[A-Z]?[a-z]+", o)) + "\nRESPUESTA: LISTO", {}
            if "Elige el ÚNICO nombre" in sis:
                o = simple(T[re.search(r"DESCRIPCIÓN: (.*?)\n\nNOMBRES:", u, re.S).group(1)])
                hit = next((x for x in u.split("\n") if o and x.endswith("." + o)), None)
                return f"ELEGIDA: {hit or 'NINGUNA'}\nRESPUESTA: LISTO", {}
            t = T[re.search(r"PREGUNTA: (.*?)\n", u).group(1)]
            if "FUNCION_USADA" not in u:                    # paso de Contexto Ligero: solo «encuentra» lo exacto
                if t["tipo"] in "PT":
                    return "RESPUESTA: NO_ENCONTRADO", {}
                return f"RESPUESTA: {t['respuesta']}", {}
            usada = t["donde"][1].split("::")[1].split(".")[-1] if t.get("tipo_origen", t["tipo"]) == "B" else simple(t)
            return f"FUNCION_USADA: {usada}\nRESPUESTA: {t['respuesta']}", {}

        BF.correr_modelo("falso", e, falso, lambda: False, ("combinada",))
        F = BF.leer_filas(e)
        r = Counter(f["resultado"] for f in F)
        comprobar("combinada en Java con cerebro perfecto: todo acierta", r["acierto"] == len(F), f"{dict(r)}")
        ident = [f for f in F if f.get("identidad")]
        comprobar("las parafraseadas pasan por la identidad y la elección es correcta",
                  all(f["identidad"]["elegida_correcta"] for f in ident) and len(ident) >= 22,
                  f"{len(ident)} por identidad")
        comprobar("la comprobación literal funciona en Java",
                  all(f["identidad"].get("comprobacion") in ("verificada", None) for f in ident),
                  str(Counter(f["identidad"].get("comprobacion") for f in ident)))
    finally:
        shutil.rmtree(base, ignore_errors=True)
    print(f"\n{sum(RESULTADOS)}/{len(RESULTADOS)} comprobaciones pasan")
    return 0 if all(RESULTADOS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
