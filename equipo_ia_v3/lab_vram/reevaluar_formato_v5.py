"""F1-V5 — análisis EXPLORATORIO (no prerregistrado): ¿cuánto cambia el cribado con un formato de respuesta tolerante?

    python -B -X utf8 eq3/lanzador_eq2.py lab_vram/reevaluar_formato_v5.py CRIBADO/comparacion.json SALIDA.json

Solo lee: vuelve a puntuar los textos YA generados en el cribado con el MISMO oráculo estático (nunca ejecuta código).
Lo único que cambia es la extracción: si V2-F.1 no encuentra el bloque «ARCHIVO: solucion.py», se aceptan los bloques
``` del texto (aunque lleven explicaciones alrededor). Igual para los 4 cerebros. No sustituye al resultado
prerregistrado ni cambia la elección del equipo.
"""
import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
from eq3 import evaluar_f1 as EV  # noqa: E402

BLOQUE = re.compile(r"```(?:python|py)?[ \t]*\n(.*?)```", re.S)


def codigo_tolerante(texto: str) -> tuple:
    estricto = EV.codigo_de(texto)
    if estricto.strip():
        return estricto, "estricto"
    bloques = [b for b in BLOQUE.findall(texto or "") if "def " in b]
    return "\n\n".join(bloques), ("bloques" if bloques else "sin_codigo")


def main(argv) -> int:
    cribado, salida = Path(argv[0]), Path(argv[1])
    if salida.exists():
        raise SystemExit(f"ya existe {salida}: no se sobrescribe")
    res = json.loads(cribado.read_text(encoding="utf-8"))
    tareas, oraculos = EV.E.cargar()
    EV.preparar_contexto()
    filas = []
    for f in res["filas"]:
        carpeta = cribado.parent / f"r{f['repeticion']}" / f["configuracion"].replace("@", "_") / f["tarea"]
        fila = json.loads(next(iter(sorted(carpeta.glob("intento*/fila.json"))), carpeta / "fila.json")
                          .read_text(encoding="utf-8")) if not (carpeta / "fila.json").is_file() else \
            json.loads((carpeta / "fila.json").read_text(encoding="utf-8"))
        texto = fila["muestras"][0]["texto"]
        cod, via = codigo_tolerante(texto)
        ev = EV.E.evaluar(tareas[f["tarea"]], oraculos[f["tarea"]], cod, rechazo=EV.es_rechazo(texto, cod))
        filas.append({"configuracion": f["configuracion"], "tarea": f["tarea"], "estricta": f["categoria"],
                      "tolerante": ev["categoria"], "extraccion": via, "motivo": ev["motivo"][:200]})
    resumen = {}
    for e in dict.fromkeys(x["configuracion"] for x in filas):
        fs = [x for x in filas if x["configuracion"] == e]
        resumen[e] = {"estricta": {k: sum(x["estricta"] == k for x in fs) for k in EV.E.CATEGORIAS},
                      "tolerante": {k: sum(x["tolerante"] == k for x in fs) for k in EV.E.CATEGORIAS},
                      "rescatadas_por_bloques": sum(x["extraccion"] == "bloques" for x in fs)}
    out = {"tipo": "EXPLORATORIO, no prerregistrado", "cribado": str(cribado), "resumen": resumen, "filas": filas}
    salida.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(resumen, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
