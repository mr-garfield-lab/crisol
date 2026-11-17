"""Verifica la integridad del paquete de entrega de F1-VRAM-EXP-V4.5.1 contra `MANIFIESTO_PAQUETE_SHA256.json`.

    python -B -X utf8 equipo_ia_v3/verificar_paquete.py [RAIZ_DEL_PAQUETE]    (por defecto, la carpeta que contiene equipo_ia_v3/)

Comprueba el SHA-256 de cada archivo listado y avisa de los que faltan, cambian o sobran. No ejecuta nada del paquete. Código de
salida 0 solo si TODO coincide. Descomprime el ZIP tal cual: un editor que cambie los finales de línea altera los hashes.
"""
import hashlib
import json
import sys
from pathlib import Path


def main(argv=None) -> int:
    raiz = Path(argv[0] if argv else Path(__file__).resolve().parents[1]).resolve()
    manifiesto = raiz / "MANIFIESTO_PAQUETE_SHA256.json"
    if not manifiesto.is_file():
        print(f"FALLO: no existe {manifiesto}")
        return 2
    datos = json.loads(manifiesto.read_text(encoding="utf-8"))
    faltan, cambian = [], []
    for rel, h in datos["archivos"].items():
        p = raiz / rel
        if not p.is_file():
            faltan.append(rel)
        elif hashlib.sha256(p.read_bytes()).hexdigest() != h:
            cambian.append(rel)
    conocidos = set(datos["archivos"]) | {"MANIFIESTO_PAQUETE_SHA256.json"}
    sobran = sorted(p.relative_to(raiz).as_posix() for p in raiz.rglob("*")
                    if p.is_file() and "__pycache__" not in p.parts and not p.name.endswith((".pyc", ".db"))
                    and p.relative_to(raiz).as_posix() not in conocidos)
    print(f"paquete: {datos['paquete']} · commit {datos['commit'][:12]} · {datos['n_archivos']} archivos")
    print(f"faltan: {len(faltan)} · cambiados: {len(cambian)} · no listados: {len(sobran)}")
    for titulo, lista in (("FALTAN", faltan), ("CAMBIADOS", cambian), ("NO LISTADOS", sobran)):
        for x in lista[:10]:
            print(f"  {titulo}: {x}")
    ok = not faltan and not cambian
    print("RESULTADO:", "INTEGRIDAD OK" if ok else "FALLO DE INTEGRIDAD")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
