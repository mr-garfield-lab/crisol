"""V2-E: asesoría EXTERNA (GPT-6, Claude u otra persona) por intercambio MANUAL de archivos.

No hay integración automática ni se asume ninguna API. Se exporta una solicitud a
asesoria/solicitud_<run>.md; el usuario coloca la respuesta en asesoria/entrada/<nombre>.md.
La respuesta importada es TEXTO NO CONFIABLE: solo entra en el prompt de A2 como datos y
NUNCA cambia políticas, límites ni permisos.
"""
from __future__ import annotations

import hashlib
import json
import re

from . import rutas, sanea

NOMBRE = re.compile(r"[A-Za-z0-9_-]{1,40}\.md")
MAX_CHARS = 4000
_PERMISOS = re.compile(
    r"\b(pol[ií]tica|permisos?|privilegios?|sudo|root|modo[ _]b|red\s*=|max_[a-z_]+\s*=|"
    r"ignora(r)?\s+(las|todas\s+las)\s+instrucciones|desactiva(r)?\s+(la|las|el)\s+\w+)",
    re.IGNORECASE)


def intentos_de_permisos(texto) -> list:
    return sorted({m.group(0).lower() for m in _PERMISOS.finditer(texto or "")})


def exportar(lab: rutas.Laboratorio, informe: dict) -> str:
    run_id = informe.get("run_id") or "sin_run"
    lab.crear_dir("asesoria")
    lab.crear_dir("asesoria", "entrada")
    cuerpo = {k: informe.get(k) for k in ("tarea", "estado_final", "motivo", "resultado",
                                         "criterios", "criterios_pendientes", "errores")}
    texto = ("# Solicitud de asesoría (exportación manual; no se ha enviado a ningún servicio)\n\n"
             "Responde en un archivo asesoria/entrada/<nombre>.md. Tu respuesta se tratará como "
             "datos no confiables y no puede cambiar permisos ni límites.\n\n```json\n"
             + json.dumps(cuerpo, ensure_ascii=False, indent=2, default=str)[:12000] + "\n```\n")
    nombre = f"solicitud_{run_id}.md"
    lab.escribir_atomico(("asesoria", nombre), texto)
    return nombre


def importar(lab: rutas.Laboratorio, nombre: str) -> dict:
    if not isinstance(nombre, str) or not NOMBRE.fullmatch(nombre):
        raise rutas.RutaInsegura("nombre de respuesta no válido (solo letras, números, _ y -, .md)")
    bruto = lab.leer_texto(("asesoria", "entrada", nombre), MAX_CHARS * 4)
    if bruto is None:
        raise FileNotFoundError(nombre)
    texto = sanea.limpiar(bruto, MAX_CHARS)
    return {"nombre": nombre, "texto": texto, "chars": len(texto),
            "sha256": hashlib.sha256(texto.encode("utf-8")).hexdigest(),
            "intentos_de_permisos": intentos_de_permisos(texto),
            "nota": "datos no confiables: solo informan a A2"}
