#!/usr/bin/env python3
"""construir_paquete.py — ayuda para AUTORES de paquetes de auditoría (p. ej. GPT-6 o el usuario).

Uso: python3 -B herramientas/construir_paquete.py CARPETA SALIDA.zip

CARPETA contiene `manifiesto.json` (sin el campo «archivos») y los archivos de datos (.json, .md, .txt).
La herramienta calcula el SHA-256 de cada archivo, completa «archivos» y escribe un ZIP determinista
(fechas fijas, orden alfabético). Después valida el resultado con las mismas reglas que el verificador.
No ejecuta nada del contenido.
"""
import json
import sys
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))
sys.dont_write_bytecode = True
from eq2 import VERSION, paquetes_auditoria as PA  # noqa: E402


def construir(carpeta: Path, salida: Path) -> dict:
    man = json.loads((carpeta / "manifiesto.json").read_text(encoding="utf-8"))
    archivos = {}
    for p in sorted(carpeta.rglob("*")):
        rel = p.relative_to(carpeta).as_posix()
        if p.is_symlink():
            raise SystemExit(f"enlace simbólico no admitido: {rel}")
        if p.is_file() and rel != "manifiesto.json":
            archivos[rel] = PA.sha256(p.read_bytes())
    man["archivos"] = archivos
    if salida.exists():
        raise SystemExit(f"{salida} ya existe: no se sobrescribe")
    with zipfile.ZipFile(salida, "x", zipfile.ZIP_DEFLATED) as zf:
        for nombre, datos in [("manifiesto.json", json.dumps(man, ensure_ascii=False, indent=1).encode("utf-8"))] + [
                (r, (carpeta / r).read_bytes()) for r in archivos]:
            zi = zipfile.ZipInfo(nombre, date_time=(1980, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o644 << 16
            zf.writestr(zi, datos)
    return PA.inspeccionar(salida, VERSION)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    info = construir(Path(sys.argv[1]), Path(sys.argv[2]))
    print(json.dumps({"sha256": info["sha256"], "problemas": info["problemas"], "compatible": info["compatible"],
                      "pruebas": info["pruebas"]}, ensure_ascii=False, indent=1))
    sys.exit(1 if info["problemas"] else 0)
