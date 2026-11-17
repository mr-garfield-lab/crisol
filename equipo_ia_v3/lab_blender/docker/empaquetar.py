"""Crea el paquete Docker para compartir: el banco de Blender y el de diagnóstico de partidas. Solo código, tareas y
pruebas; sin datos de nadie.

    python -B -X utf8 lab_blender/docker/empaquetar.py DESTINO.zip

Antes de escribir el ZIP revisa cada archivo (ya con las transformaciones de ruta aplicadas): si aparece una ruta con
un usuario real, un correo o el nombre interno de este proyecto, NO se crea el paquete. El ZIP lleva fechas fijas (no
las del disco) y un MANIFIESTO.json con el SHA-256 de cada archivo. No incluye evidencias, resultados, modelos,
partidas ni el historial de git.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import zipfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parents[1]
RAIZ_SAVES = RAIZ / "lab_saves" / "docker"
RAIZ_ZIP = "banco_local_ia"
ARCHIVOS = {                                                  # ruta dentro del ZIP -> archivo de origen
    "Dockerfile": AQUI / "Dockerfile",
    "LEEME.md": AQUI / "LEEME.md",
    "lab_blender/LEEME.md": RAIZ / "lab_blender" / "docker" / "LEEME_blender.md",
    "lab_saves/LEEME.md": RAIZ_SAVES / "LEEME.md",
    ".dockerignore": AQUI / "dockerignore.txt",
    **{f"lab_blender/{n}": RAIZ / "lab_blender" / n for n in
       ("filtro.py", "ejecutor.py", "dentro_blender.py", "verificador.py", "tareas.py", "banco.py", "portable.py")},
    **{f"lab_saves/{n}": RAIZ_SAVES / n for n in
       ("traductor_pz.py", "traductor_rimworld.py", "hallazgos.py", "crear_copias_pz.py", "crear_copias_rimworld.py",
        "portable.py")},
    **{f"pruebas/{n}": RAIZ / "pruebas" / n for n in
       ("test_lab_blender_filtro.py", "test_lab_blender_ejecutor.py", "test_lab_blender_banco.py",
        "test_lab_blender_portable.py", "test_lab_saves_portable.py")},
}
# en el ZIP los módulos de lab_saves viven en «lab_saves/», no en «lab_saves/docker/»: se ajustan las rutas que lo asumen
TRANSFORMACIONES = {
    "pruebas/test_lab_saves_portable.py": [
        ('sys.path.insert(0, str(RAIZ / "lab_saves" / "docker"))', 'sys.path.insert(0, str(RAIZ / "lab_saves"))'),
    ],
}
# cualquier coincidencia (tras las transformaciones) impide crear el paquete
PRIVADO = re.compile(r"[A-Za-z]:\\\\Users\\\\(?!Public\\\\|Default\\\\)|/home/[a-z][\w-]*/|/Users/[A-Za-z][\w-]*/|"
                     r"@[a-z0-9_.-]+\.(?:com|es|org|net|io)\b|AI_Workspace|EquipoIA_V3|equipo_ia_v3|evidencias[\\/]v31|"
                     r"WhatsApp|Remote Control"
                     # 2026-11-17: los nombres propios ya no van escritos en el código (se publicaban con él); cada
                     # persona pone los suyos en la variable CRISOL_TERMINOS_PRIVADOS, separados por «;»
                     + "".join("|" + re.escape(t.strip()) for t in os.environ.get("CRISOL_TERMINOS_PRIVADOS", "").split(";")
                               if t.strip()), re.I)
FECHA = (2026, 1, 1, 0, 0, 0)


def _contenido(destino: str, origen: Path) -> bytes:
    texto = origen.read_text(encoding="utf-8")
    for vieja, nueva in TRANSFORMACIONES.get(destino, []):
        if vieja not in texto:
            raise SystemExit(f"NO se crea el paquete: {destino} ya no contiene el texto a sustituir «{vieja[:50]}»")
        texto = texto.replace(vieja, nueva)
    return texto.replace("\r\n", "\n").encode("utf-8")


def revisar(datos: dict) -> list:
    problemas = []
    for destino, b in datos.items():
        for n, linea in enumerate(b.decode("utf-8").splitlines(), 1):
            m = PRIVADO.search(linea)
            if m:
                problemas.append(f"{destino}:{n}: «{m.group()}»")
    return problemas


def empaquetar(destino: Path) -> dict:
    faltan = [str(o) for o in ARCHIVOS.values() if not o.is_file()]
    if faltan:
        raise SystemExit("NO se crea el paquete; faltan archivos:\n" + "\n".join(faltan))
    datos = {d: _contenido(d, o) for d, o in ARCHIVOS.items()}
    problemas = revisar(datos)
    if problemas:
        raise SystemExit("NO se crea el paquete; hay datos que no deben salir:\n" + "\n".join(problemas))
    manifiesto = {"paquete": RAIZ_ZIP, "archivos": {d: {"bytes": len(b), "sha256": hashlib.sha256(b).hexdigest()}
                                                    for d, b in sorted(datos.items())}}
    datos["MANIFIESTO.json"] = (json.dumps(manifiesto, ensure_ascii=False, indent=1) + "\n").encode("utf-8")
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
        for d, b in sorted(datos.items()):
            info = zipfile.ZipInfo(f"{RAIZ_ZIP}/{d}", date_time=FECHA)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, b)
    return {"zip": str(destino), "bytes": destino.stat().st_size, "archivos": len(datos),
            "sha256": hashlib.sha256(destino.read_bytes()).hexdigest()}


if __name__ == "__main__":
    print(json.dumps(empaquetar(Path(sys.argv[1])), ensure_ascii=False, indent=1))
