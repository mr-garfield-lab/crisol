"""Paquete para repetir los bancos en otro PC, con TODAS las protecciones de privacidad de `v3/empaquetar.py`.

    py -B -X utf8 lab_flujos/paquete_amigo.py --salida DIR_NUEVO           (desde equipo_ia_v3/)

No modifica `v3/empaquetar.py`: lo importa y solo cambia QUÉ se incluye. Siguen valiendo sus rechazos (credenciales,
correos, rutas personales fuera de registros y documentación, archivos de más de 15 MB, enlaces) y su anonimización
de rutas en `evidencias/`, `docs/` y `PROGRESO.md`.

Cambios respecto al paquete general:
- Fuera: `lab_saves/` (laboratorio de partidas guardadas de juegos), `distribucion/` (guía antigua de otra
  evaluación), `entregas/` y las copias de seguridad `*.bak_*` de Contexto Ligero.
- De `evidencias/` solo van los dos bancos que se repiten: `v31_lab_flujos/` y `v31_lab_blender/`.
- El `LEEME_PAQUETE.md` generado apunta a `equipo_ia_v3/GUIA_AMIGO_BANCOS.md`.
"""
from __future__ import annotations

import hashlib
import importlib.util
import os
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
_spec = importlib.util.spec_from_file_location("empaquetar", RAIZ / "v3" / "empaquetar.py")
E = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(E)

FUERA = {"lab_saves", "distribucion", "entregas", "evidencias", "__pycache__", ".git"}
EVIDENCIAS = ("v31_lab_flujos", "v31_lab_blender", "v31_lab_revision")

incluir = []
for p in sorted(RAIZ.iterdir()):
    if p.is_dir() and p.name not in FUERA:
        incluir.append((f"equipo_ia_v3/{p.name}", p))
for nombre in EVIDENCIAS:
    incluir.append((f"equipo_ia_v3/evidencias/{nombre}", RAIZ / "evidencias" / nombre))
incluir += [x for x in E.INCLUIR if x[0].startswith("fuentes/")]
E.INCLUIR = incluir
E.SUELTOS = list(E.SUELTOS) + [(f"equipo_ia_v3/{p.name}", p) for p in sorted(RAIZ.iterdir()) if p.is_file()]
E.SUELTOS.append(("README.md", RAIZ / "lab_flujos" / "README_PAQUETE.md"))      # README en la raíz del ZIP
# server.log (diagnóstico de llama.cpp), imágenes y vídeos: el empaquetador no puede revisar ni anonimizar lo que no
# es UTF-8, y ahí aparecieron rutas de la máquina de origen (2026-11-15). Fuera.
E.EXCLUIR_SUFIJOS = tuple(E.EXCLUIR_SUFIJOS) + ("bak_2026-11-15", "_constantes", ".marca", ".marca.log",
                                                "server.log", ".png", ".jpg", ".mp4", ".blend", ".blend1")
_recoger = E.recoger
EN_CURSO = ()   # tandas que se están ejecutando al empaquetar: sus resultados aún no están completos


# Identificadores personales del dueño, guardados como SHA-256 (este archivo va en el paquete y no debe contenerlos).
PROHIBIDOS_SHA256 = {"a3881b18ae5924dbd283ad06d717c0c56d5d3da400c0b8753e4becb416a5f1d2",
                     "86bfc83253b9a536b182d2c22936e6333a9c45a7a9be5bfafbd516a2bd0ffad4"}
_PALABRA = re.compile(r"[a-z0-9][a-z0-9._@-]{3,}[a-z0-9]")


def _prohibidos() -> set:
    """Las huellas fijas más el nombre de este equipo, leído al ejecutar (no se guarda en ningún archivo)."""
    out = set(PROHIBIDOS_SHA256)
    equipo = os.environ.get("COMPUTERNAME", "").strip().lower()
    if equipo:
        out.add(hashlib.sha256(equipo.encode()).hexdigest())
    return out


def recoger() -> list:
    """Falla cerrado: solo entran archivos de texto UTF-8 (los únicos que el empaquetador revisa y anonimiza) y ninguno
    puede contener un identificador personal de la lista de huellas."""
    entradas = [(n, p) for n, p in _recoger() if "/lab_blender/docker/" not in n and ".bak_" not in n and not any(
        f"/evidencias/v31_lab_flujos/{t}/" in n for t in EN_CURSO)]
    no_texto, personales = [], []
    huellas = _prohibidos()
    for nombre, p in entradas:
        try:
            texto = p.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            no_texto.append(nombre)
            continue
        if any(hashlib.sha256(w.encode()).hexdigest() in huellas for w in set(_PALABRA.findall(texto.lower()))):
            personales.append(nombre)
    if no_texto:
        raise E.Rechazo("archivos que no son texto UTF-8 (no revisables): " + "; ".join(no_texto[:10]))
    if personales:
        raise E.Rechazo("identificador personal: " + "; ".join(personales[:10]))
    return entradas


E.recoger = recoger


def leeme(n: int) -> str:
    return (f"# Equipo IA V3.1 — paquete para repetir los bancos\n\nContiene {n} archivos con su SHA-256 en "
            "`MANIFIESTO_SHA256.json`.\n\n**Empieza por `equipo_ia_v3/GUIA_AMIGO_BANCOS.md`.**\n\n"
            "No contiene modelos, llama.cpp, Blender, bases de datos, secretos ni datos personales: el empaquetador "
            "rechaza el paquete si encuentra credenciales, correos o rutas personales, y en los registros sustituye "
            "las rutas de la máquina de origen por `<TRABAJO>` y `<CASA>`.\n")


E.leeme = leeme

if __name__ == "__main__":
    sys.exit(E.main())
