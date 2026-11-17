"""Comprobaciones del banco de flujos SIN GPU y SIN cerebro real (cerebros falsos, deterministas).

    python -B -X utf8 lab_flujos/humo/comprobar_sin_gpu.py            (desde equipo_ia_v3/)

Comprueba, en carpetas temporales nuevas:
  1. Reproducibilidad: el corpus generado es byte a byte el de referencia y la cobertura de Contexto Ligero coincide
     con la medida en el PC de origen (`referencia_cobertura.json`).
  2. Troceado híbrido: parar a mitad y reanudar no repite ni pierde trozos, y no cierra tareas a medias.
  3. Verificación estricta y trampas con un cerebro TRAMPOSO: descarta funciones que no cumplen y registra el invento.
  4. Flujo de identidad: un número falso o una cita a otra función se descartan siempre.
Sale con código 0 solo si TODO pasa.
"""
from __future__ import annotations

import hashlib
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


def comprobar(nombre: str, ok: bool, detalle: str = "") -> None:
    RESULTADOS.append(ok)
    print(f"[{'PASA' if ok else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else ""))


def objetivo(t):
    return t["donde"][0].split("::")[1] if t.get("donde") else None


def prueba_reproducible(base: Path) -> None:
    ref = json.loads((AQUI / "referencia_cobertura.json").read_text(encoding="utf-8"))
    e = base / "repro"
    prep = BF.preparar(e, ("ligero", "identidad"), ["P", "A", "B", "D", "R", "T"])
    huella = hashlib.sha256()
    for p in sorted((e / "corpus").glob("*.py")):
        huella.update(p.name.encode() + p.read_bytes())
    comprobar("corpus idéntico al de origen", huella.hexdigest() == ref["corpus_sha256"], huella.hexdigest()[:12])
    cob = prep["cobertura"]["ligero"]
    distintas = {k: (v, ref["cobertura_ligero"].get(k)) for k, v in cob.items() if ref["cobertura_ligero"].get(k) != v}
    comprobar("cobertura de Contexto Ligero igual que en origen", not distintas,
              f"{sum(cob.values())}/{len(cob)}" + (f"; distintas: {distintas}" if distintas else ""))


def prueba_troceado(base: Path) -> None:
    e = base / "troceado"
    BF.preparar(e, ("ligero", "hibrida"), ["A", "B", "C", "D", "R", "T"])
    tareas = {t["id"]: t for t in json.loads((e / "tareas.json").read_text(encoding="utf-8"))["tareas"]}

    def falso(msgs, n):
        u = msgs[1]["content"]
        if "(trozo " not in u:
            return "RESPUESTA: NO_ENCONTRADO", {"tokens_prompt": 1}
        if "Lista los nombres" in u:
            cat = re.search(r"categoría '(\w+)'", u).group(1)
            bien = re.findall(rf"def (\w+)\([^)]*\):(?:(?!\ndef ).)*registrar_auditoria\('{cat}'", u, re.S)
            intrusa = next((x for x in re.findall(r"^def (\w+)\(", u, re.M) if x not in bien), None)
            return "\n".join(f"FUNCION: {x}" for x in bien + ([intrusa] if intrusa else [])) + "\nRESPUESTA: LISTO", {}
        for t in tareas.values():
            if t["tipo"] in "DR" and t["pregunta"] in u and re.search(rf"^\s*{objetivo(t)}\s*=", u, re.M):
                return f"RESPUESTA: {t['respuesta']}", {}
        return "RESPUESTA: NO_ENCONTRADO", {}

    def parar_a_mitad():                     # con 3 trozos guardados se está DENTRO de una tarea de varios trozos
        f = e / "trozos.jsonl"
        return f.exists() and len(f.read_text(encoding="utf-8").splitlines()) >= 3

    r1 = BF.correr_modelo("falso", e, falso, parar_a_mitad, ("hibrida",))
    contextos = json.loads((e / "contextos.json").read_text(encoding="utf-8"))
    guardados = Counter(k[1] for k in BF.leer_trozos(e))
    # Toda tarea cerrada por troceado al parar debe tener TODOS sus trozos hechos.
    cerradas_incompletas = [f["unidad"] for f in BF.leer_filas(e) if f.get("ruta") == "troceado" and
                            guardados[f["unidad"]] != len(contextos[f["unidad"]]["hibrida"]["trozos"])]
    a_medias = [u for u in guardados if u not in {f["unidad"] for f in BF.leer_filas(e)}]
    r2 = BF.correr_modelo("falso", e, falso, lambda: False, ("hibrida",))
    lineas = (e / "trozos.jsonl").read_text(encoding="utf-8").splitlines()
    claves = [(json.loads(x)["modelo"], json.loads(x)["unidad"], json.loads(x)["trozo"]) for x in lineas]
    filas = BF.leer_filas(e)
    comprobar("parar a mitad y reanudar", r1 == "parado" and r2 == "completo", f"{r1} → {r2}")
    comprobar("ningún trozo repetido al reanudar", len(claves) == len(set(claves)), f"{len(claves)} trozos")
    comprobar("ninguna tarea cerrada a medias", not cerradas_incompletas and bool(a_medias),
              f"al parar quedó a medias {a_medias or 'ninguna'} sin cerrar; cerradas incompletas: "
              f"{cerradas_incompletas or 'ninguna'}")
    cs = [f for f in filas if f["tipo"] == "C"]
    comprobar("recuentos exactos aunque el cerebro añada intrusas", all(f["resultado"] == "acierto" for f in cs),
              ", ".join(f"{f['unidad']}={f['valor']}" for f in cs))
    ts = [f for f in filas if f["tipo"] == "T"]
    comprobar("trampas: «no existe» sin preguntar al cerebro", all(f["resultado"] == "acierto" for f in ts),
              ", ".join(f"{f['unidad']}:{f['ruta']}" for f in ts))


def prueba_identidad(base: Path) -> None:
    e = base / "identidad"
    BF.preparar(e, ("ligero", "identidad"), ["P", "A", "B", "D", "R", "T"])
    T = {t["pregunta"]: t for t in json.loads((e / "tareas.json").read_text(encoding="utf-8"))["tareas"]}
    modo = {"m": ""}

    def falso(msgs, n):
        sis, u = msgs[0]["content"], msgs[-1]["content"]
        if "Propón palabras clave" in sis:
            o = objetivo(T[msgs[1]["content"].split("LUEGO: ", 1)[1]]) or "nada"
            return "\n".join(f"{w.upper()}: {w.lower()}" for w in o.split("_")) + "\nRESPUESTA: LISTO", {}
        if "Elige el ÚNICO nombre" in sis:
            o = objetivo(T[re.search(r"DESCRIPCIÓN: (.*?)\n\nNOMBRES:", u, re.S).group(1)])
            hit = next((x for x in u.split("\n") if o and x.endswith("." + o)), None)
            return f"ELEGIDA: {hit or 'NINGUNA'}\nRESPUESTA: LISTO", {}
        t = T[re.search(r"PREGUNTA: (.*?)\n", u).group(1)]
        if modo["m"] == "numero_falso":
            return f"FUNCION_USADA: {objetivo(t)}\nRESPUESTA: 99999", {}
        if modo["m"] == "cita_otra":
            return f"FUNCION_USADA: registrar_auditoria\nRESPUESTA: {t['respuesta']}", {}
        usada = t["donde"][1].split("::")[1] if t.get("tipo_origen", t["tipo"]) == "B" else objetivo(t)
        return f"FUNCION_USADA: {usada}\nRESPUESTA: {t['respuesta']}", {}

    for m, esperado in (("perfecto", "acierto"), ("numero_falso", "descarte"), ("cita_otra", "descarte")):
        modo["m"] = m
        (e / "peticiones.jsonl").unlink(missing_ok=True)
        BF.correr_modelo("falso", e, falso, lambda: False, ("identidad",))
        F = BF.leer_filas(e)
        r = Counter(f["resultado"] for f in F)
        if esperado == "acierto":
            comprobar("identidad: cerebro honrado acierta todo", r["acierto"] == len(F), f"{r['acierto']}/{len(F)}")
        else:
            con_dato = [f for f in F if f["esperado"] != "NO_ENCONTRADO"]
            desc = sum(f["identidad"]["ruta"] == "descartada_por_verificacion" for f in con_dato)
            comprobar(f"identidad: «{m}» se descarta siempre", desc == len(con_dato), f"{desc}/{len(con_dato)}")


def main() -> int:
    base = Path(tempfile.mkdtemp(prefix="banco_flujos_"))
    try:
        prueba_reproducible(base)
        prueba_troceado(base)
        prueba_identidad(base)
    finally:
        shutil.rmtree(base, ignore_errors=True)
    print(f"\n{sum(RESULTADOS)}/{len(RESULTADOS)} comprobaciones pasan")
    return 0 if all(RESULTADOS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
