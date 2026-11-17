#!/usr/bin/env python3
"""Equipo IA V3 — PRUEBAS DE MUTACIÓN: ¿detectan las pruebas los defectos que deben detectar?

    python3 -B v3/mutacion.py v3/mutaciones/<etapa>.json        (desde equipo_ia_v3/)

Cada especificación JSON declara la orden de pruebas, qué se copia y qué se enlaza, y una lista de mutaciones
`{id, archivo, antes, despues, motivo}`. Funcionamiento:

1. **Espejo.** Por cada mutación se crea un ESPEJO temporal de `equipo_ia_v3/`. Lo que se modifica se copia;
   lo que solo se lee (`sistema/`, `../fuentes`) se enlaza simbólicamente y no se escribe nunca.
2. **Aplicación.** Se aplica la mutación (el texto `antes` debe aparecer EXACTAMENTE una vez) y se ejecuta la
   orden.
3. **Veredicto.** La mutación queda DETECTADA si la orden falla.
4. **Control previo.** Primero se ejecuta un CONTROL sin mutación, que debe pasar; si no pasa, el resultado no
   significaría nada y la herramienta termina con código 2.

Seguridad (auditoría de la Etapa 7). La especificación es un DATO:
- **AUD-01:** solo admite `unittest discover` con `-s`, `-t` y `-p` y rutas simples; ninguna otra orden.
- **AUD-02:** `copiar` y `enlazar` deben ser rutas relativas existentes. Una mutación solo puede tocar archivos
  COPIADOS: nunca los enlazados (`sistema/`), ni `fuentes/`, ni nada fuera del espejo, y el destino se resuelve y
  se comprueba dentro del espejo.

Código de salida: 0 todas detectadas · 1 alguna sobrevive (las pruebas no cubren ese defecto) · 2 error de la
especificación o del control.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]          # equipo_ia_v3/
REPO = RAIZ.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
from eq3 import plataforma  # noqa: E402
PREFIJO = ["{python}", "-B", "-m", "unittest", "discover"]
OPCIONES = {"-s", "-t", "-p"}
# Capacidad de plataforma que una mutación necesita para poder detectarse (campo opcional «requiere»). Sin ella, la
# mutación queda OMITIDA y se informa: ni DETECTADA ni SOBREVIVE (p. ej. Windows sin privilegio de symlinks, o una
# defensa que solo existe en Windows, como el rechazo de uniones de directorio, medida en Linux).
REQUISITOS = ("ninguno", "enlaces_a_archivos", "windows")


def capacidad(requisito: str) -> bool:
    if requisito == "enlaces_a_archivos":
        with tempfile.TemporaryDirectory(prefix="eq3_sonda_", dir=os.environ.get("TMPDIR")) as t:
            return plataforma.puede_enlazar_archivos(t)
    if requisito == "windows":
        return plataforma.WINDOWS
    return True
RE_SIMPLE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_./*-]{0,119}")


def _relativa(rel, que: str) -> Path:
    if not isinstance(rel, str) or not RE_SIMPLE.fullmatch(rel) or ".." in Path(rel).parts:
        raise ValueError(f"{que}: ruta no permitida: {rel!r}")
    return Path(rel)


def validar(spec: dict) -> None:
    """Rechaza (ValueError) cualquier especificación que no sea «unittest discover» sobre un espejo propio."""
    orden = spec.get("orden")
    if not isinstance(orden, list) or orden[:len(PREFIJO)] != PREFIJO:
        raise ValueError("AUD-01: la orden debe ser «{python} -B -m unittest discover ...»")
    resto = orden[len(PREFIJO):]
    if len(resto) % 2 or any(o not in OPCIONES for o in resto[::2]):
        raise ValueError(f"AUD-01: opciones permitidas: {sorted(OPCIONES)}")
    for v in resto[1::2]:
        _relativa(v, "AUD-01 argumento")
    copiar = {_relativa(r, "AUD-02 copiar").parts[0] for r in spec.get("copiar", [])}
    enlazar = {_relativa(r, "AUD-02 enlazar").parts[0] for r in spec.get("enlazar", [])}
    for rel in list(spec.get("copiar", [])) + list(spec.get("enlazar", [])):
        if not (RAIZ / rel).exists():
            raise ValueError(f"AUD-02: no existe en equipo_ia_v3/: {rel}")
    for rel in spec.get("copiar_raiz", []):            # archivos sueltos de la raíz del repositorio (p. ej. AGENTS.md)
        p = _relativa(rel, "AUD-02 copiar_raiz")
        if len(p.parts) != 1 or "gameagentengine" in rel.lower() or not (REPO / rel).is_file():
            raise ValueError(f"AUD-02: copiar_raiz solo admite archivos existentes de la raíz: {rel!r}")
    for m in spec.get("mutaciones", []):
        if m.get("requiere", REQUISITOS[0]) not in REQUISITOS:
            raise ValueError(f"{m.get('id')}: requisito de plataforma desconocido: {m.get('requiere')!r}")
        destino = _relativa(m.get("archivo"), f"AUD-02 mutación {m.get('id')}")
        if destino.parts[0] not in copiar or destino.parts[0] in enlazar:
            raise ValueError(f"AUD-02: {m.get('id')}: solo se mutan archivos COPIADOS al espejo: {m.get('archivo')}")


def _espejo(base: Path, spec: dict) -> Path:
    espejo = base / "espejo" / "equipo_ia_v3"
    espejo.mkdir(parents=True)
    for rel in spec["copiar"]:
        origen = RAIZ / rel
        (shutil.copytree(origen, espejo / rel, ignore=shutil.ignore_patterns("__pycache__")) if origen.is_dir()
         else shutil.copy2(origen, espejo / rel))
    for rel in spec.get("enlazar", []):                 # symlink; en Windows sin privilegio, una COPIA
        plataforma.replicar_solo_lectura(RAIZ / rel, espejo / rel)
    plataforma.replicar_solo_lectura(REPO / "fuentes", base / "espejo" / "fuentes")
    for rel in spec.get("copiar_raiz", []):
        shutil.copy2(REPO / rel, base / "espejo" / rel)
    return espejo


def _ejecutar(spec: dict, mutacion: dict | None, limite: int) -> tuple:
    with tempfile.TemporaryDirectory(prefix="eq3_mut_", dir=os.environ.get("TMPDIR")) as t:
        base = Path(t)
        espejo = _espejo(base, spec)
        if mutacion:
            f = espejo / mutacion["archivo"]
            real = f.resolve()
            if not real.is_relative_to(espejo.resolve()) or any(
                    plataforma.es_enlace(q) for q in [f, *f.parents] if q.is_relative_to(espejo)) or \
                    Path(mutacion["archivo"]).parts[0] in spec.get("enlazar", []):   # réplica en copia (Windows)
                raise ValueError(f"AUD-02: {mutacion['id']}: el destino sale del espejo o pasa por un enlace")
            texto = f.read_text(encoding="utf-8")
            if texto.count(mutacion["antes"]) != 1:
                raise ValueError(f"{mutacion['id']}: el texto «antes» aparece {texto.count(mutacion['antes'])} veces "
                                 f"en {mutacion['archivo']} (debe ser 1)")
            f.write_text(texto.replace(mutacion["antes"], mutacion["despues"]), encoding="utf-8")
        tmp = base / "tmp"
        tmp.mkdir()
        r = plataforma.ejecutar([sys.executable if x == "{python}" else x for x in spec["orden"]], cwd=espejo,
                                env=plataforma.entorno_hijo(tmp), timeout=limite)
        resumen = [l for l in (r.stdout + r.stderr).splitlines() if l.startswith(("FAILED", "OK", "Ran "))][-2:]
        return r.returncode, resumen


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print(__doc__)
        return 2
    spec = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    try:
        validar(spec)
    except ValueError as e:
        print(f"=== ESPECIFICACIÓN RECHAZADA: {e} ===")
        return 2
    limite = int(spec.get("limite_s", 900))
    print(f"=== MUTACIÓN: {spec['descripcion']} ({len(spec['mutaciones'])} mutaciones) ===", flush=True)
    rc, resumen = _ejecutar(spec, None, limite)
    print(f"  CONTROL sin mutación: rc={rc} {resumen}", flush=True)
    if rc != 0:
        print("=== FIN MUTACIÓN: el CONTROL falla; las mutaciones no significarían nada ===")
        return 2
    resultados, omitidas = [], []
    for m in spec["mutaciones"]:
        requisito = m.get("requiere", "ninguno")
        if not capacidad(requisito):
            omitidas.append(m["id"])
            print(f"  {m['id']:34} OMITIDA   (la plataforma no permite «{requisito}»)  — {m['motivo']}", flush=True)
            continue
        try:
            rc, resumen = _ejecutar(spec, m, limite)
        except ValueError as e:
            print(f"  ERROR de especificación: {e}")
            return 2
        detectada = rc != 0
        resultados.append({"id": m["id"], "detectada": detectada, "rc": rc, "resumen": resumen})
        print(f"  {m['id']:34} {'DETECTADA' if detectada else 'SOBREVIVE'}  rc={rc} {resumen[-1:]}  — {m['motivo']}",
              flush=True)
    vivas = [r["id"] for r in resultados if not r["detectada"]]
    print(f"=== FIN MUTACIÓN: {len(resultados) - len(vivas)}/{len(resultados)} detectadas"
          + (f"; SOBREVIVEN: {', '.join(vivas)}" if vivas else "")
          + (f"; OMITIDAS por plataforma: {', '.join(omitidas)}" if omitidas else "") + " ===")
    return 1 if vivas else 0


if __name__ == "__main__":
    sys.exit(main())
