#!/usr/bin/env python3
"""comparar_metricas.py — compara la duración y los tokens de dos ejecuciones (SOLO LECTURA).

Uso:  python3 -B comparar_metricas.py BASE/summary.json NUEVA/summary.json [--objetivo 30]

Acepta summary.json de V2-B, V2-C y V2-D (todas guardan backend_informe.informe.peticiones).
No escribe nada. Avisa si las tareas no son equivalentes o si faltan medidas.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
sys.dont_write_bytecode = True

from eq2 import metricas  # noqa: E402

MAX_BYTES = 20 * 1024 * 1024


def leer(ruta: str) -> dict:
    p = Path(ruta)
    if p.is_symlink() or not p.is_file():
        sys.exit(f"no es un archivo normal: {ruta}")
    if p.stat().st_size > MAX_BYTES:
        sys.exit(f"archivo demasiado grande: {ruta}")
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("base")
    ap.add_argument("nueva")
    ap.add_argument("--objetivo", type=float, default=30.0, help="incremento máximo de tiempo (%%)")
    a = ap.parse_args()
    b, n = metricas.desde_summary(leer(a.base)), metricas.desde_summary(leer(a.nueva))
    c = metricas.comparar(b, n, a.objetivo)
    print(f"{'medida':<16}{'base':>12}{'nueva':>12}{'variación':>12}")
    for k in ("llamadas", "pared_s", "tokens_prompt", "tokens_gen", "ms_prompt", "ms_gen", "carga_s"):
        v = c["variacion_pct"].get(k)
        print(f"{k:<16}{str(b.get(k)):>12}{str(n.get(k)):>12}{(str(v) + ' %') if v is not None else '—':>12}")
    print("versiones:", b.get("version"), "->", n.get("version"))
    print("conclusión válida:", b.get("conclusion_valida"), "->", n.get("conclusion_valida"))
    d = c["dentro_del_objetivo"]
    print(f"objetivo de tiempo (+{a.objetivo:g} %):",
          "CUMPLIDO" if d else "NO CUMPLIDO" if d is False else "no calculable")
    for av in c["avisos"]:
        print("AVISO:", av)
    vb, vn = b.get("votacion"), n.get("votacion")
    if vb and vn:
        print("votación (base -> nueva):",
              {k: (vb.get(k), vn.get(k)) for k in ("llamadas", "reintentos", "pared_s",
                                                   "pared_reintentos_s", "tokens_prompt", "cache_n")})
        ahorro = round((vb.get("pared_s") or 0) - (vn.get("pared_s") or 0), 3)
        print(f"tiempo de votación ahorrado: {ahorro} s (positivo = la nueva vota más rápido; "
              "solo es comparable con la misma tarea)")
    else:
        print("votación: sin desglose en alguno de los dos summary.json (V2-C no lo guarda)")
    if n.get("por_fase"):
        print("tiempo por fase (nueva):", {f: v.get("pared_s") for f, v in n["por_fase"].items()})
    return 0


if __name__ == "__main__":
    sys.exit(main())
