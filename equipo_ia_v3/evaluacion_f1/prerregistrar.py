"""F1 — escribe `evaluacion_f1/PRERREGISTRO_F1.json` con el SHA-256 de cada archivo del diseño de la evaluación.

    python -B evaluacion_f1/prerregistrar.py VERSION

Se niega a sobrescribir un prerregistro existente de otra versión sin conservarlo: la versión anterior se guarda como
`PRERREGISTRO_F1_v<N>.json`. El ejecutor (`eq3.evaluacion_f1.comprobar_prerregistro`) compara estos SHA-256 antes de
evaluar nada.
"""
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DESTINO = RAIZ / "evaluacion_f1" / "PRERREGISTRO_F1.json"
ARCHIVOS = ["evaluacion_f1/tareas_f1.json", "evaluacion_f1/oraculos_f1.json", "evaluacion_f1/definicion.py",
            "evaluacion_f1/prerregistrar.py", "eq3/evaluacion_f1.py", "pruebas/test_eq3_evaluacion_f1.py",
            "v3/mutaciones/v31_f1_oraculos.json", "docs/V31_F1_PLAN_EVALUACION.md",
            # versión 2: el ejecutor y sus pruebas también forman parte del método prerregistrado
            "eq3/evaluar_f1.py", "pruebas/test_eq3_evaluar_f1.py", "pruebas/aux_evaluar_f1.py",
            "v3/mutaciones/v31_f1_ejecutor.json"]

version = int(sys.argv[1])
if DESTINO.is_file():
    previo = json.loads(DESTINO.read_text(encoding="utf-8"))
    if previo["version"] == version:
        raise SystemExit(f"ya existe el prerregistro versión {version}: no se sobrescribe")
    (DESTINO.parent / f"PRERREGISTRO_F1_v{previo['version']}.json").write_text(
        DESTINO.read_text(encoding="utf-8"), encoding="utf-8")
datos = {"version": version, "fecha_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
         "estado": "PRERREGISTRADO, NO EJECUTADO: pendiente de revisión con GPT-6",
         "sha256": {a: hashlib.sha256((RAIZ / a).read_bytes()).hexdigest() for a in ARCHIVOS}}
DESTINO.write_text(json.dumps(datos, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
for a, h in datos["sha256"].items():
    print(h, a)
