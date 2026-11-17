#!/usr/bin/env python3
"""tabla_cumplimiento.py — (para el DESARROLLADOR al empaquetar) genera CUMPLIMIENTO_V2E6.md a partir de
cumplimiento.json y, si se indica, del cumplimiento_resultado.json de una verificación REAL ejecutada.

Uso: python3 -B herramientas/tabla_cumplimiento.py [RUTA/cumplimiento_resultado.json]
La tabla del paquete refleja la verificación de la sandbox de Claude; la de TU verificación queda en
$TMPDIR/equipo_f2/lab_v2f1/verificacion/<id>/cumplimiento_resultado.md.
"""
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def main() -> int:
    cum = json.loads((RAIZ / "cumplimiento.json").read_text(encoding="utf-8"))
    res, origen = {}, "sin verificación asociada"
    if len(sys.argv) > 1:
        p = Path(sys.argv[1])
        res = {f["id"]: f for f in json.loads(p.read_text(encoding="utf-8"))}
        origen = f"verificación de la sandbox de Claude ({p.parent.name})"
    md = ["# Tabla de cumplimiento V2-E.6 (requisito → archivo → prueba → resultado)", "",
          f"Resultados: {origen}. Datos en `cumplimiento.json`; el verificador la recalcula en cada ejecución (V-CUM-03).",
          "«OK» = todas las comprobaciones asociadas pasaron en esa verificación (pruebas SIMULADAS salvo que se diga REAL). "
          "«NO VERIFICADA» = no se pudo comprobar aquí (motivo en la nota).", "",
          "| Req. | Fuente | Requisito | Archivos | Pruebas | Resultado | Nota |", "|---|---|---|---|---|---|---|"]
    for r in cum["requisitos"]:
        f = res.get(r["id"], {})
        md.append(f"| {r['id']} | {r.get('fuente', '')} | {r['requisito']} | "
                  + "<br>".join(f"`{a}`" for a in r.get("archivos", [])) + " | "
                  + "<br>".join(f"`{t}`" for t in r.get("pruebas", []) + r.get("verificacion", [])) + " | "
                  + f"**{f.get('resultado', '—')}** | {r.get('no_verificable') or r.get('nota') or ''} |")
    (RAIZ / "CUMPLIMIENTO_V2E6.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"{len(cum['requisitos'])} requisitos -> CUMPLIMIENTO_V2E6.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
