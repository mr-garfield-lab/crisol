"""Crisol: todas las comprobaciones que no necesitan GPU ni modelos, con un solo comando.

    py -B -X utf8 comprobar_todo.py              (núcleo y laboratorios publicados)
    py -B -X utf8 comprobar_todo.py --json       (salida para un asistente de IA)

Cada comprobación sale como PASA, FALLA u OMITIDO (le falta algo externo: Blender, el JDK…). OMITIDO no es un fallo:
dice qué instalar para poder comprobarlo. No carga ningún modelo de IA, no descarga nada y no ejecuta código escrito por
un cerebro (los de Blender usan scripts de referencia, escritos a mano).
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
EQ = RAIZ / "equipo_ia_v3"
EXTERNOS = RAIZ.parent / "externos"

# (nombre, script relativo a equipo_ia_v3, argumentos, qué necesita)
COMPROBACIONES = [
    ("perfiles de hardware", "perfiles/comprobar_perfiles.py", [], None),
    ("modelos elegidos por el usuario", "perfiles/comprobar_modelos_usuario.py", [], None),
    ("laboratorio de proyectos grandes", "lab_flujos/humo/comprobar_sin_gpu.py", [], None),
    ("revisión de código (Python y Java)", "lab_revision/comprobar_sin_gpu.py", [], "jdk"),
    ("Java del laboratorio de flujos", "lab_flujos/humo/comprobar_java_banco.py", [], "jdk"),
    ("Blender: escenas relacionales", "lab_blender/comprobar_relacional2.py", ["{tmp}"], "blender"),
    ("Blender: componentes y biblioteca", "lab_blender/comprobar_componentes.py", ["{tmp}"], "blender"),
]
FALTA = re.compile(r"no encuentro|no se encontr|not found|no está instalad|falta (el |la )?(jdk|blender|java)", re.I)


def _hay(que: str) -> bool:
    if que == "jdk":
        import os
        if os.environ.get("EQUIPO_JAVAC") and Path(os.environ["EQUIPO_JAVAC"]).is_file():
            return True
        return any(EXTERNOS.glob("jdk*/bin/javac*")) or any(EXTERNOS.glob("jdk*/*/bin/javac*")) or subprocess.run(
            ["where" if sys.platform == "win32" else "which", "javac"], capture_output=True).returncode == 0
    if que == "blender":
        sys.path.insert(0, str(EQ / "lab_blender"))
        try:
            import ejecutor
            return bool(ejecutor.blender_exe())
        except Exception:
            return False
    return True


def main(argv=None) -> int:
    argv = argv or sys.argv[1:]
    import tempfile                                      # fuera del repositorio: lo de Blender lleva rutas locales
    tmp = Path(tempfile.gettempdir()) / "crisol_comprobar" / time.strftime("%Y%m%d_%H%M%S")
    res = []
    for nombre, script, args, necesita in COMPROBACIONES:
        ruta = EQ / script
        if not ruta.is_file():
            res.append({"nombre": nombre, "estado": "OMITIDO", "detalle": "no está en esta copia"})
            continue
        if necesita and not _hay(necesita):
            res.append({"nombre": nombre, "estado": "OMITIDO", "detalle": f"falta {necesita} (ver INSTALL.md)"})
            continue
        tmp.mkdir(parents=True, exist_ok=True)
        t0 = time.monotonic()
        try:
            p = subprocess.run([sys.executable, "-B", "-X", "utf8", str(ruta), *[a.format(tmp=tmp) for a in args]],
                               cwd=EQ, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1200)
            salida, rc = (p.stdout + p.stderr).strip(), p.returncode
        except subprocess.TimeoutExpired:
            salida, rc = "más de 20 minutos", -1
        lineas = salida.splitlines()
        resumen = next((l for l in reversed(lineas) if re.search(r"comprobaciones|RESULTADO|^Ran \d+|^OK", l)),
                       next((l for l in reversed(lineas) if re.search(r"\d+/\d+", l)), lineas[-1] if lineas else ""))
        estado = "PASA" if rc == 0 else ("OMITIDO" if FALTA.search(salida) else "FALLA")
        res.append({"nombre": nombre, "estado": estado, "detalle": resumen[:160],
                    "segundos": round(time.monotonic() - t0, 1)})
    if "--json" in argv:
        print(json.dumps(res, ensure_ascii=False, indent=1))
    else:
        for r in res:
            print(f"[{r['estado']:7}] {r['nombre']}: {r['detalle']}" + (f" ({r['segundos']} s)" if "segundos" in r else ""))
        n = {e: sum(r["estado"] == e for r in res) for e in ("PASA", "FALLA", "OMITIDO")}
        print(f"\nRESULTADO: {n['PASA']} pasan, {n['FALLA']} fallan, {n['OMITIDO']} omitidas")
    return 1 if any(r["estado"] == "FALLA" for r in res) else 0


if __name__ == "__main__":
    raise SystemExit(main())
