"""V2-E.7-r2: adaptador de LISTA BLANCA hacia PZ ModLab 0.2 (`modlab_pz/`, de GPT-6, incluido sin modificar).

Solo las tres operaciones de `modlab_pz/contrato_agentes.json`, todas sin ejecutar código del mod:
  simular_escenario      -> laboratorio.simulate(JSON)     (máquina de estados propia; no es el juego)
  analizar_lua_estatico  -> lua_analisis.analizar_lua(bytes) (patrones; NO ejecuta Lua)
  inspeccionar_zip       -> laboratorio.inspect_zip(ruta)    (lista y hashea; no extrae ni ejecuta)
NO se usa `lua_analisis.comprobar_sintaxis_archivo` (lanza luac) ni `laboratorio.main` (escribe fuera de
rutas.py). Los resultados NO certifican compatibilidad con Project Zomboid ni con Build 42.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_RAIZ = str(Path(__file__).resolve().parents[2])
if _RAIZ not in sys.path:
    sys.path.append(_RAIZ)
from modlab_pz import laboratorio as _lab, lua_analisis as _lua  # noqa: E402

CONTRATO = json.loads((Path(_RAIZ) / "modlab_pz" / "contrato_agentes.json").read_text(encoding="utf-8"))
EXTENSION = {"simular_escenario": ".json", "analizar_lua_estatico": ".lua", "inspeccionar_zip": ".zip"}
if set(EXTENSION) != set(CONTRATO["operaciones_permitidas"]):
    raise RuntimeError("el contrato de modlab_pz no coincide con el adaptador: no se usa")
MAX_ENTRADA = 1_000_000


def ejecutar(operacion: str, ruta: Path) -> dict:
    if operacion not in EXTENSION:
        raise PermissionError(f"operación no permitida por el contrato: {operacion}")
    if ruta.suffix.lower() != EXTENSION[operacion] or not ruta.is_file() or ruta.is_symlink():
        raise ValueError(f"{operacion} necesita un archivo {EXTENSION[operacion]} propio de la tarea")
    if ruta.stat().st_size > MAX_ENTRADA:
        raise ValueError("entrada demasiado grande")
    if operacion == "simular_escenario":
        return _lab.simulate(json.loads(ruta.read_text(encoding="utf-8")))
    if operacion == "analizar_lua_estatico":
        return _lua.analizar_lua(ruta.read_bytes(), ruta.name)
    return _lab.inspect_zip(ruta)
