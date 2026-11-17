#!/usr/bin/env python3
"""lista_cambios.py — (para el DESARROLLADOR al empaquetar) rellena la sección «Archivos» de CAMBIOS_V2E6.md
comparando el árbol con herramientas/manifiesto_r3.txt. No toca nada más.

Uso: python3 -B herramientas/lista_cambios.py [--comprobar] [--base manifiesto_v2e6.txt --doc CAMBIOS_V2E6R2.md]
     python3 -B herramientas/lista_cambios.py [--comprobar] --base manifiesto_v2e6r2.txt --doc CAMBIOS_V2E6R3.md  (V2-E.6-r3)
"""
import hashlib
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
MARCA = "<!-- LISTA_DE_ARCHIVOS"


def archivos():
    out = {}
    for p in sorted(RAIZ.rglob("*")):
        rel = p.relative_to(RAIZ).as_posix()
        if (p.is_file() and not p.is_symlink() and "__pycache__" not in p.parts and rel != "MANIFIESTO_SHA256.txt"
                and not rel.startswith("evidencias_claude/")):
            out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def main() -> int:
    r3 = {}
    base, doc_nombre = "manifiesto_r3.txt", "CAMBIOS_V2E6.md"
    if "--base" in sys.argv:
        base = sys.argv[sys.argv.index("--base") + 1]
        doc_nombre = sys.argv[sys.argv.index("--doc") + 1]
    for l in (RAIZ / "herramientas" / base).read_text(encoding="utf-8").splitlines():
        h, _, r = l.partition("  ")
        if r and not r.startswith("evidencias_claude/"):
            r3[r] = h
    act = archivos()
    doc = RAIZ / doc_nombre
    texto = doc.read_text(encoding="utf-8")
    cab = texto[:texto.index(MARCA)]
    nuevos = sorted(set(act) - set(r3))
    quitados = sorted(set(r3) - set(act))
    cambiados = sorted(r for r in set(act) & set(r3) if act[r] != r3[r])
    # CAMBIOS_V2E6.md no puede incluir su propia huella: se lista como nuevo (lo es)
    sec = [MARCA + ": generada por herramientas/lista_cambios.py -->", "",
           f"Nuevos ({len(nuevos)}):", ""] + [f"- `{r}`" for r in nuevos] + ["", f"Cambiados ({len(cambiados)}):", ""] + \
          [f"- `{r}`" for r in cambiados] + ["", f"Quitados ({len(quitados)}):", ""] + \
          ([f"- `{r}`" for r in quitados] or ["- ninguno"]) + ["", f"Sin cambios: {len(set(act) & set(r3)) - len(cambiados)}.", ""]
    nuevo = cab + "\n".join(sec)
    if "--comprobar" in sys.argv:
        return 0 if nuevo == texto else 1
    if nuevo != texto:
        doc.write_text(nuevo, encoding="utf-8")
    print(f"{len(nuevos)} nuevos, {len(cambiados)} cambiados, {len(quitados)} quitados")
    return 0


if __name__ == "__main__":
    sys.exit(main())
