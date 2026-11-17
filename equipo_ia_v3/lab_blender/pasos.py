"""Banco de Blender · ROBOTS POR PASOS (tanda 9).

Los robots (T05 y T08: 25 y 32 comprobaciones) no los ha aprobado ningún cerebro pidiéndolos de una vez (lo mejor:
ministral3 al 88 %). Aquí se piden por partes: torso → cabeza → piernas → brazos (→ animación en T08). En cada paso:
- el cerebro escribe SOLO el código nuevo; se añade al final del script ya aprobado (no reescribe ni rompe lo hecho
  y no le corta el tope de 800 tokens);
- se ejecuta en Blender y se verifica sin IA con las comprobaciones de ese paso Y de los anteriores;
- hasta 3 intentos por paso con lo medido como respuesta. Si un paso se agota, el robot queda sin terminar.
Al final se verifica el script completo con TODAS las comprobaciones originales de la tarea.

    py -B -X utf8 eq3/lanzador_eq2.py lab_blender/pasos.py ejecutar <externos> <evidencia> <salida_blender> \
        --modelos qwen25 ministral3 --manual lab_blender/MANUAL_BLENDER_V6.md
    py -B -X utf8 lab_blender/pasos.py informe <evidencia>
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
for p in (str(AQUI.parent), str(AQUI)):
    if p not in sys.path:
        sys.path.insert(0, p)
import banco as BB  # noqa: E402
import tareas as T  # noqa: E402
import verificador as VF  # noqa: E402
import ejecutor as EJ  # noqa: E402

TAREAS_PASOS = ("T05", "T08")
INTENTOS = 3
PIEZAS = [
    (["Torso"], "Crea «Torso», una caja de 1.0 × 0.6 × 1.2 m con su centro en (0, 0, 2.0)."),
    (["Cabeza"], "Añade «Cabeza», un cubo de 0.5 m justo encima del torso, centrada y tocándolo. Debe ser hija de "
                 "«Torso»."),
    (["Pierna_I", "Pierna_D"], "Añade «Pierna_I» y «Pierna_D» de 0.3 × 0.3 × 1.4 m, debajo del torso, tocándolo y "
                               "apoyadas en el suelo (z = 0). «Pierna_I» en x negativa y «Pierna_D» en x positiva, "
                               "simétricas. Las dos, hijas de «Torso»."),
    (["Brazo_I", "Brazo_D"], "Añade «Brazo_I» y «Brazo_D» de 0.25 × 0.25 × 1.0 m, uno a cada lado del torso y "
                             "tocándolo. «Brazo_I» en x negativa y «Brazo_D» en x positiva, simétricos. Los dos, hijos "
                             "de «Torso»."),
]
ANIMAR = ("Anima el robot entero para que avance 4 m hacia Y negativa entre el fotograma 1 y el 48 (sin subir ni "
          "bajar, con todas las piezas juntas). La escena va del 1 al 48.")
NOMBRES_ANIM = {"fotogramas", "desplazamiento"}


def _objetos(c) -> set:
    """Nombres de objeto que usa una comprobación (los argumentos de texto, o la lista de «solo»)."""
    out = set()
    for a in c[1:]:
        if isinstance(a, str):
            out.add(a)
        elif isinstance(a, (list, tuple)) and all(isinstance(x, str) for x in a):
            out.update(a)
    return out


def pasos(id_: str) -> list:
    """[(instrucción, comprobaciones acumuladas)] de una tarea robot."""
    todas = T.TAREAS[id_]["comprobaciones"]
    out, hechas = [], []
    for piezas, texto in PIEZAS:
        hechas += piezas
        cs = [("solo", list(hechas))] + [c for c in todas if c[0] not in NOMBRES_ANIM | {"solo"}
                                          and _objetos(c) <= set(hechas)]
        out.append((texto, cs))
    if any(c[0] in NOMBRES_ANIM for c in todas):
        out.append((ANIMAR, list(todas)))
    return out


def tarea_paso(id_: str, comprobaciones: list) -> dict:
    return {**T.TAREAS[id_], "comprobaciones": comprobaciones}


MEJORAS = False                                          # tanda 10: aviso de código repetido y pistas geométricas
PISTA_APOYO = ("PISTA: para que un objeto quede apoyado ENCIMA de otro, su BASE debe quedar a la altura de lo ALTO "
               "del otro. Con cajas centradas en su origen: centro_z = (alto del otro) + (altura propia) / 2. Para "
               "apoyarlo en el suelo: centro_z = (altura propia) / 2.")
PISTA_LADO = ("PISTA: para que un objeto toque a otro POR UN LADO, la distancia entre sus centros en ese eje debe ser "
              "la suma de sus medias anchuras en ese eje.")
PISTA_TAMANO = ("PISTA: bpy.ops.mesh.primitive_cube_add(size=1) crea un cubo de 1 m de lado (con el valor por defecto, "
                "size=2, mide 2 m). La medida final de cada eje es size × scale de ese eje.")


CUENTAS = False                                          # tanda 11: cuentas con lo medido + reescritura detectada
AVISO_REESCRITURA = ("Tu código vuelve a crear {objs}, que YA están en el script actual (quedarían duplicados). "
                     "Escribe SOLO el código nuevo de este paso, sin repetir nada del script actual; para usar esos "
                     "objetos, búscalos con bpy.data.objects[\"Nombre\"]. Responde con un único bloque ```python```.")
_EJES = "xyz"


def ya_hechas(k: int) -> list:
    return [n for piezas, _ in PIEZAS[:k - 1] for n in piezas]


def reescribe(nuevo: str, hechas: list) -> list:
    """Objetos ya aprobados a los que el código nuevo vuelve a poner nombre (señal de que reescribe el script)."""
    out = []
    for n in hechas:
        q = r"""["']""" + re.escape(n) + r"""["']"""
        # «ob.name = "X"» o una función propia que lo crea, «caja("X", …)» (no bpy.data.objects["X"] ni .get("X"))
        if re.search(r"\.name\s*=\s*" + q, nuevo or "") or re.search(r"\b(?!get\()\w+\(\s*" + q, nuevo or ""):
            out.append(n)
    return out


def _mueve(nombre: str, eje: int, d: float) -> str:
    return f"mueve «{nombre}» {d:+.2f} m en {_EJES[eje]} (su centro {_EJES[eje]} debe cambiar {d:+.2f})"


def cuentas_medidas(tarea: dict, r: dict) -> list:
    """Traduce lo MEDIDO en Blender a cuánto mover o escalar cada pieza que falla (sin IA, sin datos ocultos)."""
    E = (r.get("informe") or {}).get("escena")
    if r.get("estado") != "OK" or not E:
        return []
    out = []
    for nombre, *args in tarea["comprobaciones"]:
        try:
            ok, _ = VF.COMPROBACIONES[nombre](E, *args)
            if ok:
                continue
            if nombre == "encima":
                A, B = VF._ob(E, args[0]), VF._ob(E, args[1])
                d = B["caja_max"][2] - A["caja_min"][2]
                out.append(f"la base de «{args[0]}» está a z = {A['caja_min'][2]:.2f} y lo alto de «{args[1]}» a "
                           f"z = {B['caja_max'][2]:.2f}: {_mueve(args[0], 2, d)}")
            elif nombre == "toca":
                A, B = VF._momentos(VF._ob(E, args[0])), VF._momentos(VF._ob(E, args[1]))
                a, b = max(zip(A, B), key=lambda p: VF._hueco(*p))
                for i in range(3):
                    if a["caja_min"][i] - b["caja_max"][i] > 0.02:
                        out.append(f"«{args[0]}» y «{args[1]}» están separados {a['caja_min'][i] - b['caja_max'][i]:.2f} m "
                                   f"en {_EJES[i]}: {_mueve(args[0], i, b['caja_max'][i] - a['caja_min'][i])}")
                    elif b["caja_min"][i] - a["caja_max"][i] > 0.02:
                        out.append(f"«{args[0]}» y «{args[1]}» están separados {b['caja_min'][i] - a['caja_max'][i]:.2f} m "
                                   f"en {_EJES[i]}: {_mueve(args[0], i, b['caja_min'][i] - a['caja_max'][i])}")
            elif nombre == "apoyado":
                z = args[1] if len(args) > 1 else 0.0
                base = min(m["caja_min"][2] for m in VF._momentos(VF._ob(E, args[0])))
                out.append(f"la base de «{args[0]}» está a z = {base:.2f} y debe estar a z = {z:.2f}: "
                           f"{_mueve(args[0], 2, z - base)}")
            elif nombre == "dimensiones":
                o = VF._ob(E, args[0])
                med = [o["caja_max"][i] - o["caja_min"][i] for i in range(3)]
                fac = ", ".join(f"{_EJES[i]} ×{args[1][i] / med[i]:.2f}" for i in range(3) if med[i] > 1e-6)
                out.append(f"«{args[0]}» mide {VF._f(med)} m y debe medir {VF._f(args[1])}: multiplica su scale por "
                           f"{fac}")
            elif nombre == "centro":
                o = VF._ob(E, args[0])
                c = [(o["caja_max"][i] + o["caja_min"][i]) / 2 for i in range(3)]
                out += [_mueve(args[0], i, args[1][i] - c[i]) for i in range(3) if abs(args[1][i] - c[i]) > 0.02]
        except (VF.Falta, KeyError, IndexError, TypeError, ZeroDivisionError):
            continue
    return out


def _norm(codigo: str) -> str:
    return "\n".join(l.strip() for l in (codigo or "").strip().splitlines() if l.strip())


def ayudas(previos: list) -> list:
    """Avisos y pistas GENÉRICAS para el siguiente intento (nunca los números de la tarea)."""
    if not previos:
        return []
    ult, out = previos[-1], []
    out.append("AVISO: tu código anterior para este paso falló; no lo repitas: cambia lo que indica el resultado.")
    if len(previos) >= 2 and _norm(previos[-1]["nuevo"]) == _norm(previos[-2]["nuevo"]):
        out.append("AVISO: tu último código es IDÉNTICO al del intento anterior, que ya falló. Escribe uno DISTINTO.")
    fall = set(ult.get("fallidas") or [])
    if fall & {"encima", "apoyado", "toca"}:
        out.append(PISTA_APOYO)
    if "toca" in fall:
        out.append(PISTA_LADO)
    if "dimensiones" in fall:
        out.append(PISTA_TAMANO)
    if CUENTAS and ult.get("cuentas"):
        out.append("CUENTAS HECHAS CON LO QUE MIDIÓ BLENDER EN TU INTENTO (aplícalas a tu código):\n- "
                   + "\n- ".join(ult["cuentas"]))
    return out


def mensajes(id_: str, k: int, total: int, instruccion: str, actual: str, previo: dict | None,
             previos: list | None = None) -> list:
    u = (f"OBJETIVO FINAL (se construye por pasos): {T.TAREAS[id_]['enunciado']}\n\n"
         + (f"SCRIPT ACTUAL (ya funciona y cumple los pasos anteriores; NO lo repitas):\n```python\n{actual}```\n\n"
            if actual.strip() else "SCRIPT ACTUAL: vacío, empiezas tú (incluye «import bpy» al principio).\n\n")
         + f"PASO {k} de {total}: {instruccion}\n\n"
         "Escribe SOLO el código NUEVO que se añadirá al final del script actual. Para usar objetos que ya existen, "
         "búscalos con bpy.data.objects[\"Nombre\"]. Responde con un único bloque ```python```.")
    if previo:
        u += (f"\n\nTu código para este paso:\n```python\n{previo['nuevo']}```\n\nResultado al ejecutarlo en Blender:\n"
              f"{previo['feedback']}\n\nCorrige SOLO el código de este paso y devuélvelo completo (solo lo nuevo).")
        if MEJORAS:
            u += "\n\n" + "\n".join(ayudas(previos or [previo]))
    return [{"role": "system", "content": BB.SISTEMA + BB.MANUAL}, {"role": "user", "content": u}]


def leer_filas(evidencia: Path) -> list:
    return BB.leer_filas(evidencia)


def estado_tarea(modelo, id_, filas) -> dict:
    """Reconstruye por dónde va: script aprobado acumulado, paso actual, intentos del paso y si terminó."""
    fs = [f for f in filas if f["modelo"] == modelo and f["tarea"] == id_]
    if any(f.get("tipo") == "final" for f in fs):
        return {"terminada": True}
    actual, k = "", 1
    lista = pasos(id_)
    while k <= len(lista):
        del_paso = [f for f in fs if f.get("paso") == k and f.get("tipo") == "paso"]
        ok = next((f for f in del_paso if f["aprobado"]), None)
        if ok:
            actual = ok["script"]
            k += 1
            continue
        return {"terminada": False, "actual": actual, "paso": k, "intentos": del_paso,
                "agotado": len(del_paso) >= INTENTOS}
    return {"terminada": False, "actual": actual, "paso": k, "intentos": [], "agotado": False}


def pendientes(modelo, ids, evidencia) -> bool:
    filas = leer_filas(evidencia)
    return any(not estado_tarea(modelo, i, filas)["terminada"] for i in (ids or TAREAS_PASOS))


def _guardar(evidencia: Path, fila: dict) -> None:
    with (Path(evidencia) / "peticiones.jsonl").open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(fila, ensure_ascii=False) + "\n")


def correr(modelo, ids, evidencia, salida_blender, completar, parar=lambda: False) -> str:
    evidencia = Path(evidencia)
    for id_ in (ids or TAREAS_PASOS):
        lista = pasos(id_)
        while True:
            e = estado_tarea(modelo, id_, leer_filas(evidencia))
            if e["terminada"]:
                break
            if parar():
                return "parado"
            if e["agotado"] or e["paso"] > len(lista):
                # cierre: el script aprobado hasta aquí, con TODAS las comprobaciones originales de la tarea
                carpeta = Path(salida_blender) / modelo / f"{id_}_final_{int(time.time())}"
                r, v = BB.probar(id_, e["actual"] or "import bpy\n", carpeta, salida_blender)
                _guardar(evidencia, {"modelo": modelo, "tarea": id_, "tipo": "final", "aprobado": v["aprobado"],
                                     "cumplidas": v.get("cumplidas", 0), "total": v.get("total", 0),
                                     "pasos_aprobados": e["paso"] - 1, "pasos": len(lista), "estado": r["estado"],
                                     "script": e["actual"], "feedback": v["texto"], "intento": 0,
                                     "segundos_cerebro": 0.0, "motivos_filtro": [], "finish_reason": None,
                                     "base_intacta": None, "fecha": time.strftime("%Y-%m-%dT%H:%M:%S")})
                break
            k, instruccion = e["paso"], lista[e["paso"] - 1][0]
            previo = e["intentos"][-1] if e["intentos"] else None
            t0 = time.monotonic()
            msgs = mensajes(id_, k, len(lista), instruccion, e["actual"], previo, e["intentos"])
            texto, tokens, fin = completar(msgs, BB.TOKENS)
            nuevo = BB.extraer_script(texto)
            rep = reescribe(nuevo, ya_hechas(k)) if CUENTAS else []
            if rep:                     # reescribe lo aprobado: se le pide otra vez, sin ejecutar ni gastar intento
                _guardar(evidencia, {"modelo": modelo, "tarea": id_, "tipo": "reescritura", "paso": k,
                                     "intento": len(e["intentos"]) + 1, "texto": texto, "nuevo": nuevo,
                                     "objetos": rep, "fecha": time.strftime("%Y-%m-%dT%H:%M:%S")})
                texto, tok2, fin = completar(msgs + [{"role": "assistant", "content": texto}, {
                    "role": "user", "content": AVISO_REESCRITURA.format(objs=", ".join(f"«{n}»" for n in rep))}],
                    BB.TOKENS)
                tokens, nuevo = (tokens or 0) + (tok2 or 0), BB.extraer_script(texto)
            t_gen = round(time.monotonic() - t0, 2)
            script = (e["actual"] + "\n" + nuevo) if e["actual"] else nuevo
            carpeta = Path(salida_blender) / modelo / f"{id_}_p{k}_i{len(e['intentos']) + 1}_{int(time.time())}"
            tarea = tarea_paso(id_, lista[k - 1][1])
            r = EJ.ejecutar(script, carpeta, base=None, muestras=tarea.get("muestras", 5), tiempo_s=BB.TIEMPO_BLENDER_S)
            v = VF.verificar(tarea, r)
            _guardar(evidencia, {"modelo": modelo, "tarea": id_, "tipo": "paso", "paso": k, "pasos": len(lista),
                                 "intento": len(e["intentos"]) + 1, "texto": texto, "nuevo": nuevo, "script": script,
                                 "tokens": tokens, "finish_reason": fin, "segundos_cerebro": t_gen,
                                 "estado": r["estado"], "aprobado": v["aprobado"], "cumplidas": v.get("cumplidas", 0),
                                 "total": v.get("total", len(tarea["comprobaciones"])), "feedback": v["texto"],
                                 "fallidas": sorted({c["comprobacion"] for c in v.get("comprobaciones", [])
                                                     if not c["cumple"]}), "mejoras": MEJORAS,
                                 "cuentas": cuentas_medidas(tarea, r) if CUENTAS and not v["aprobado"] else [],
                                 "motivos_filtro": (r.get("filtro") or {}).get("motivos", []),
                                 "fecha": time.strftime("%Y-%m-%dT%H:%M:%S")})
    return "completo"


def informe(evidencia: Path) -> str:
    filas = leer_filas(evidencia)
    L = ["# Banco de Blender · robots por pasos: informe", "",
         "| modelo | tarea | pasos aprobados | resultado final (todas las comprobaciones) | intentos por paso | "
         "llamadas |", "|---|---|---|---|---|---|"]
    for m in dict.fromkeys(f["modelo"] for f in filas):
        for id_ in TAREAS_PASOS:
            fin = next((f for f in filas if f["modelo"] == m and f["tarea"] == id_ and f.get("tipo") == "final"), None)
            ps = [f for f in filas if f["modelo"] == m and f["tarea"] == id_ and f.get("tipo") == "paso"]
            if not fin:
                continue
            por_paso = {}
            for f in ps:
                por_paso[f["paso"]] = por_paso.get(f["paso"], 0) + 1
            L.append(f"| {m} | {id_} | {fin['pasos_aprobados']}/{fin['pasos']} | "
                     f"{'APROBADO' if fin['aprobado'] else 'no'} ({fin['cumplidas']}/{fin['total']}) | "
                     f"{' · '.join(f'p{k}:{n}' for k, n in sorted(por_paso.items()))} | {len(ps)} |")
    texto = "\n".join(L) + "\n"
    (Path(evidencia) / "INFORME.md").write_text(texto, encoding="utf-8", newline="\n")
    return texto


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("orden", choices=("ejecutar", "informe"))
    ap.add_argument("rutas", nargs="+")
    ap.add_argument("--modelos", nargs="+", default=["qwen25", "ministral3"])
    ap.add_argument("--manual", default=None)
    ap.add_argument("--reanudar", action="store_true")
    ap.add_argument("--mejoras", action="store_true", help="tanda 10: aviso de código repetido y pistas")
    ap.add_argument("--cuentas", action="store_true", help="tanda 11: --mejoras + cuentas con lo medido + reescritura")
    a = ap.parse_args(argv)
    if a.orden == "informe":
        print(informe(Path(a.rutas[0])))
        return 0
    global MEJORAS, CUENTAS
    CUENTAS = a.cuentas
    MEJORAS = a.mejoras or a.cuentas
    if a.manual:
        BB.MANUAL = "\n\nMANUAL DE REFERENCIA:\n" + Path(a.manual).read_text(encoding="utf-8")
    r = BB.ejecutar(Path(a.rutas[0]), Path(a.rutas[1]), Path(a.rutas[2]), tuple(a.modelos), list(TAREAS_PASOS),
                    a.reanudar, correr=correr, pendientes_fn=pendientes)
    print(json.dumps({k: r.get(k) for k in ("inicio", "fin", "abortada")}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
