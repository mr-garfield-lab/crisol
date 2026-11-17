#!/usr/bin/env python3
"""Equipo IA V3 — VERIFICADOR INTEGRAL (una orden, sin red, sin modelos, sin instalar nada).

    python3 -B verificar_v3.py              fases F0–F10
    python3 -B verificar_v3.py --completo   además la línea base completa de 503 pruebas (~8 min más)
    (rápido: ~5 min en Linux)

Fases (cada una en un proceso hijo con HOME/TMPDIR propios, bajo $TMPDIR/eq3_verificacion/<fecha>/):
  F0  integridad de sistema/ frente a su MANIFIESTO_SHA256.txt original (sin cambios; 71 ausentes conocidos)
  F1  pruebas de la herramienta de línea base (v3/tests)
  F2  pruebas de V3 (pruebas/: traza, grafo, cambios): código V3 REAL sobre ejecuciones de V2-F.1 con agentes
      SIMULADOS
  F3  mutación de la Etapa 0 (v3/mutaciones/etapa0.json): cada defecto debe hacer fallar las pruebas
  F4  mutación de la Etapa 1 (v3/mutaciones/etapa1.json): traza unificada
  F5  mutación de la Etapa 2 (v3/mutaciones/etapa2.json): grafo y contexto
  F6  mutación de la Etapa 3 (v3/mutaciones/etapa3.json): propuesta → autorización → aplicación
  F7  mutación de la Etapa 4 (v3/mutaciones/etapa4.json): verificador de citas
  F8  mutación de la Etapa 5 (v3/mutaciones/etapa5.json): memoria y evaluación prerregistrada
  F9  mutación de la Etapa 6 (v3/mutaciones/etapa6.json): planificación de recursos del PC
  F10 mutación de la Etapa 8 (v3/mutaciones/etapa8.json): empaquetado sin datos privados ni enlaces
  F11 (--completo) línea base: verificador de V2-F.1 + codex + Contexto Ligero, comparados prueba a prueba
  F12 mutación de V3.1 F0.5 (v3/mutaciones/v31_plataforma.json): adaptadores de plataforma
  F13 mutación de V3.1 F0.5 (v3/mutaciones/v31_uniones.json): uniones de directorio de Windows
  F14 mutación de V3.1 mantenimiento (v3/mutaciones/v31_mantenimiento.json): rutas personales en el empaquetado
      y reanudación del verificador

PLATAFORMAS (V3.1 F0.5): el mismo verificador corre en Linux/WSL2, Termux y Windows nativo; lo que cambia está en
eq3/plataforma.py. Lo que una plataforma no permite comprobar (symlinks de archivo sin privilegio en Windows; las
defensas solo de Windows, medidas en Linux) queda OMITIDO con su motivo en el registro de la fase, nunca como OK.
En Windows, F11 se compara con `v3/linea_base_esperada_windows.json` SI EXISTE (se genera con
`v3/linea_base_plataforma.py`, que exige causa declarada para cada diferencia); si no, con la de Linux.

REANUDACIÓN (V3.1, mantenimiento):  python3 -B verificar_v3.py [--completo] --reanudar <carpeta de una ejecución>
Cada ejecución guarda `progreso.json` tras cada fase, con la HUELLA de lo que se verificó: el SHA-256 de cada archivo
del árbol (equipo_ia_v3/, fuentes/ y los sueltos; sin .git ni cachés) y el entorno (versión y ejecutable de Python,
sistema, entorno de los procesos hijo, carpeta temporal, capacidad de crear symlinks). Con `--reanudar`:
- si la huella actual no es IDÉNTICA a la guardada, NO se reutiliza nada (código 2) y se dice qué cambió;
- se reutilizan solo las fases que terminaron OK con la misma orden; las fallidas o no terminadas se ejecutan de
  nuevo, y F0 (integridad de sistema/) siempre se repite;
- al terminar se recalcula la huella: si algo cambió DURANTE la ejecución, el resultado no vale (fallo «HUELLA») y
  esa ejecución ya no se puede reanudar.
Cada fase reutilizada figura en el informe con «reutilizada_de» (sello de la ejecución que la ejecutó de verdad).

NATURALEZA de cada fase: REAL = código ejecutado de verdad en esta máquina; SIMULADA = respuestas de A1/A2/A3
desde un guion o un servidor falso. Ninguna fase usa Qwen real: eso exige validación en el dispositivo.
Código de salida: 0 todas las fases correctas; 1 alguna falla.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
PY = sys.executable
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
from eq3 import plataforma  # noqa: E402

FASES = [
    ("F1", "pruebas de la herramienta de línea base", "REAL",
     [PY, "-B", "-m", "unittest", "discover", "-s", "v3/tests", "-t", "v3/tests"]),
    ("F2", "pruebas de V3: traza, grafo y contexto, programación controlada",
     "REAL (código V3) sobre ejecuciones de V2-F.1 con agentes SIMULADOS",
     [PY, "-B", "-m", "unittest", "discover", "-s", "pruebas", "-t", "pruebas"]),
    ("F3", "mutación de la Etapa 0", "REAL", [PY, "-B", "v3/mutacion.py", "v3/mutaciones/etapa0.json"]),
    ("F4", "mutación de la Etapa 1", "REAL", [PY, "-B", "v3/mutacion.py", "v3/mutaciones/etapa1.json"]),
    ("F5", "mutación de la Etapa 2", "REAL", [PY, "-B", "v3/mutacion.py", "v3/mutaciones/etapa2.json"]),
    ("F6", "mutación de la Etapa 3", "REAL", [PY, "-B", "v3/mutacion.py", "v3/mutaciones/etapa3.json"]),
    ("F7", "mutación de la Etapa 4", "REAL", [PY, "-B", "v3/mutacion.py", "v3/mutaciones/etapa4.json"]),
    ("F8", "mutación de la Etapa 5", "REAL", [PY, "-B", "v3/mutacion.py", "v3/mutaciones/etapa5.json"]),
    ("F9", "mutación de la Etapa 6", "REAL", [PY, "-B", "v3/mutacion.py", "v3/mutaciones/etapa6.json"]),
    ("F10", "mutación de la Etapa 8", "REAL", [PY, "-B", "v3/mutacion.py", "v3/mutaciones/etapa8.json"]),
    ("F12", "mutación de V3.1 F0.5: adaptadores de plataforma", "REAL",
     [PY, "-B", "v3/mutacion.py", "v3/mutaciones/v31_plataforma.json"]),
    ("F13", "mutación de V3.1 F0.5: uniones de directorio de Windows", "REAL",
     [PY, "-B", "v3/mutacion.py", "v3/mutaciones/v31_uniones.json"]),
    ("F14", "mutación de V3.1 mantenimiento: rutas personales y reanudación", "REAL",
     [PY, "-B", "v3/mutacion.py", "v3/mutaciones/v31_mantenimiento.json"]),
    ("F15", "mutación de V3.1 F1 (X1): la tolerancia a pruebas inestables no acepta regresiones", "REAL",
     [PY, "-B", "v3/mutacion.py", "v3/mutaciones/v31_f1_inestables.json"]),
    ("F16", "mutación de V3.1 F1: servidor real del PC (externos verificados, detector, ciclo de vida)", "REAL",
     [PY, "-B", "v3/mutacion.py", "v3/mutaciones/v31_f1_servidor.json"]),
    ("F17", "mutación de V3.1 F1 (D3): HardFaultCount de Windows con sonda y fallo cerrado", "REAL",
     [PY, "-B", "v3/mutacion.py", "v3/mutaciones/v31_f1_majflt.json"]),
    ("F18", "mutación de V3.1 F1: oráculos de la evaluación (sin ejecutar, ambiguo = no concluyente)", "REAL",
     [PY, "-B", "v3/mutacion.py", "v3/mutaciones/v31_f1_oraculos.json"]),
    ("F19", "mutación de V3.1 F1: ejecutor de la evaluación (fugas, mismo prompt, temperaturas, VRAM, regla)", "REAL",
     [PY, "-B", "v3/mutacion.py", "v3/mutaciones/v31_f1_ejecutor.json"]),
    ("F20", "mutación de V3.1 F1-VRAM-EXP: tope 6912 MiB, terceros, GPU estable, aborto total y separación", "REAL",
     [PY, "-B", "v3/mutacion.py", "v3/mutaciones/v31_f1_vram_exp.json"]),
    ("F21", "mutación de V3.1 F1-VRAM-EXP-V4: E2, presupuesto verificado, persona ≠ GPU, fondo reversible", "REAL",
     [PY, "-B", "v3/mutacion.py", "v3/mutaciones/v31_f1_vram_exp_v4.json"]),
    ("F22", "mutación del laboratorio: control reversible de Wallpaper Engine (solo él, sin forzar)", "REAL",
     [PY, "-B", "v3/mutacion.py", "v3/mutaciones/v31_lab_wallpaper.json"]),
    ("F23", "mutación de V3.1 F1-VRAM-EXP-V4.3: lo de V4.2 + procedencia en el control de fugas del oráculo", "REAL",
     [PY, "-B", "v3/mutacion.py", "v3/mutaciones/v31_f1_vram_exp_v4_3.json"]),
    ("F24", "mutación de V3.1 F1-VRAM-EXP-V4.4: lo de V4.3 + protocolo térmico (enfriar, cortar, tiempos separados)",
     "REAL", [PY, "-B", "v3/mutacion.py", "v3/mutaciones/v31_f1_vram_exp_v4_4.json"]),
    ("F25", "mutación de V3.1 F1-VRAM-EXP-V4.5: lo de V4.4 + PC compartido (origen térmico, esperas de 4 h, STOP global)",
     "REAL", [PY, "-B", "v3/mutacion.py", "v3/mutaciones/v31_f1_vram_exp_v4_5.json"]),
    ("F26", "mutación de V3.1 F1-VRAM-EXP-V4.5.1: lo de V4.5 + atribución de G12 (propio / externo / incierto)",
     "REAL", [PY, "-B", "v3/mutacion.py", "v3/mutaciones/v31_f1_vram_exp_v4_5_1.json"]),
]
COMPLETA = ("F11", "línea base completa (503 pruebas, comparación exacta)",
            "MIXTA: REAL 14 · SIMULADA 244 · OMITIDA 1 · NO VERIFICADA 5 en el verificador de V2-F.1",
            [PY, "-B", "v3/linea_base.py"])
# X1: v3/linea_base.py sale con 4 si todo es igual salvo pruebas INESTABLES declaradas y CONFIRMADAS por repetición.
# Solo F11 lo admite; la fase cuenta como correcta pero queda marcada («con_inestables») en el informe y en el estado
# general, y --reanudar NUNCA la reutiliza (solo reutiliza rc = 0): se vuelve a medir.
CON_INESTABLES = 4
CODIGOS_OK = {"F11": (0, CON_INESTABLES)}
AUSENTES_CONOCIDOS = 71


def integridad_sistema() -> tuple:
    """sistema/ debe seguir idéntico a V2-F.1: ningún archivo distinto ni ajeno; solo los 71 omitidos ausentes."""
    raiz = RAIZ / "sistema"
    decl = {}
    for linea in (raiz / "MANIFIESTO_SHA256.txt").read_text(encoding="utf-8").splitlines():
        m = re.match(r"^([0-9a-f]{64})\s+\*?(.+)$", linea.strip())
        if m:
            decl[m.group(2)] = m.group(1)
    pres = {p.relative_to(raiz).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in raiz.rglob("*") if p.is_file() and p.name != "MANIFIESTO_SHA256.txt"}
    distintos = sorted(k for k in pres if k in decl and decl[k] != pres[k])
    ajenos = sorted(set(pres) - set(decl))
    ausentes = len(set(decl) - set(pres))
    ok = not distintos and not ajenos and ausentes == AUSENTES_CONOCIDOS
    return ok, f"{len(pres)} presentes, {len(distintos)} distintos, {len(ajenos)} ajenos, {ausentes} ausentes " \
               f"(conocidos: {AUSENTES_CONOCIDOS})" + (f"; distintos: {distintos[:5]}; ajenos: {ajenos[:5]}"
                                                       if distintos or ajenos else "")


# --- reanudación (V3.1, mantenimiento) ----------------------------------------------------------------------------
PROGRESO = "progreso.json"
VERSION_PROGRESO = 1
EXCLUIR_HUELLA = {".git", "__pycache__"}


def archivos_huella() -> dict:
    """{ruta relativa: SHA-256} de TODO el árbol que contiene equipo_ia_v3/ (código, pruebas, datos, fuentes/)."""
    arbol = RAIZ.parent
    return {p.relative_to(arbol).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(arbol.rglob("*")) if p.is_file() and not EXCLUIR_HUELLA & set(p.relative_to(arbol).parts)
            and p.suffix != ".pyc"}


def huella_entorno(base: Path) -> dict:
    """Lo que, fuera de los archivos, cambia el resultado de una fase."""
    return {"python": sys.version, "ejecutable": str(Path(sys.executable).resolve()), "plataforma": plataforma.nombre(),
            "sistema": platform.platform(), "entorno_hijo": plataforma.entorno_hijo("<FASE>"),
            "carpeta_temporal": str(base.parent), "enlaces_a_archivos": plataforma.puede_enlazar_archivos(base)}


def huella(base: Path) -> dict:
    archivos = archivos_huella()
    resumen = hashlib.sha256(json.dumps(archivos, sort_keys=True).encode("utf-8")).hexdigest()
    return {"archivos_sha256": resumen, "n_archivos": len(archivos), "entorno": huella_entorno(base),
            "archivos": archivos}


def diferencias_huella(antes: dict, ahora: dict) -> list:
    """Descripción legible de lo que cambió entre dos huellas (vacía si son idénticas)."""
    dif = [f"entorno.{k}" for k in sorted(set(antes.get("entorno", {})) | set(ahora["entorno"]))
           if antes.get("entorno", {}).get(k) != ahora["entorno"].get(k)]
    a, b = antes.get("archivos", {}), ahora["archivos"]
    for nombre in sorted(set(a) | set(b)):
        if a.get(nombre) != b.get(nombre):
            dif.append(("añadido: " if nombre not in a else "eliminado: " if nombre not in b else "modificado: ")
                       + nombre)
    if not dif and antes.get("archivos_sha256") != ahora["archivos_sha256"]:
        dif.append("resumen de archivos distinto")
    return dif


def cargar_previa(carpeta: Path, actual: dict):
    """(progreso previo, None) si se puede reanudar con EXACTAMENTE el código y el entorno actuales; si no,
    (None, motivo)."""
    try:
        previa = json.loads((carpeta / PROGRESO).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return None, f"no hay un {PROGRESO} legible en {carpeta}: {type(e).__name__}"
    if not isinstance(previa, dict) or previa.get("version") != VERSION_PROGRESO or not isinstance(
            previa.get("fases"), dict) or not isinstance(previa.get("huella"), dict):
        return None, f"{PROGRESO} con un formato desconocido"
    if previa.get("invalida"):
        return None, f"esa ejecución quedó INVÁLIDA ({previa['invalida']}); empiece una nueva"
    dif = diferencias_huella(previa["huella"], actual)
    if dif:
        return None, (f"el código o el entorno no son los de esa ejecución ({len(dif)} diferencias): "
                      + "; ".join(dif[:8]) + (" …" if len(dif) > 8 else ""))
    return previa, None


def guardar_progreso(base: Path, datos: dict) -> None:
    tmp = base / (PROGRESO + ".tmp")
    tmp.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, base / PROGRESO)                     # nunca queda un progreso a medio escribir


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--completo", action="store_true", help="incluye la línea base completa (F11)")
    ap.add_argument("--reanudar", type=Path, metavar="CARPETA",
                    help="reutiliza las fases correctas de esa ejecución si el código y el entorno son idénticos")
    a = ap.parse_args(argv)
    sello = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    base = Path(os.environ.get("TMPDIR") or tempfile.gettempdir()) / "eq3_verificacion" / sello
    base.mkdir(parents=True)
    huella_ini = huella(base)
    previa, reutilizables = None, {}
    if a.reanudar:
        previa, motivo = cargar_previa(a.reanudar, huella_ini)
        if motivo:
            print(f"REANUDACIÓN RECHAZADA: {motivo}\nNo se ha reutilizado ni ejecutado nada.")
            return 2
        reutilizables = {fid: d for fid, d in previa["fases"].items()
                         if d["resultado"].get("estado") == "OK" and d["resultado"].get("rc") == 0}
    progreso = {"version": VERSION_PROGRESO, "sello": sello, "completo": a.completo,
                "reanuda": previa["sello"] if previa else None, "huella": huella_ini, "fases": {}}
    guardar_progreso(base, progreso)
    print(f"Equipo IA V3 — verificador integral {sello}\nCarpeta: {base}"
          + (f"\nReanuda {previa['sello']}: {len(reutilizables)} fases correctas reutilizables "
             f"(código y entorno idénticos, {huella_ini['n_archivos']} archivos)" if previa else "")
          + "\n*** INICIO DE LAS PRUEBAS ***", flush=True)
    resultados = []
    t0 = time.monotonic()
    ok, detalle = integridad_sistema()
    resultados.append({"id": "F0", "descripcion": "integridad de sistema/ (V2-F.1 sin cambios)", "naturaleza": "REAL",
                       "estado": "OK" if ok else "FALLO", "duracion_s": round(time.monotonic() - t0, 1),
                       "detalle": detalle})
    print(f"[F0] {'OK' if ok else 'FALLO'} — {detalle}", flush=True)
    for fid, desc, nat, orden in FASES + ([COMPLETA] if a.completo else []):
        previo = reutilizables.get(fid)
        if previo is not None and previo["orden"] == orden:
            r = dict(previo["resultado"], reutilizada_de=previo["resultado"].get("reutilizada_de") or previa["sello"])
            resultados.append(r)
            progreso["fases"][fid] = {"orden": orden, "resultado": r}
            guardar_progreso(base, progreso)
            log = a.reanudar / f"{fid}.log"
            if log.is_file():
                shutil.copy2(log, base / f"{fid}.log")
            print(f"[{fid}] OK (REUTILIZADA de {r['reutilizada_de']}) — {r['detalle'][:140]}", flush=True)
            continue
        orden_fase = orden
        tmp = base / fid
        tmp.mkdir()
        if fid == "F11" and plataforma.WINDOWS:
            # Windows: la línea base necesita una carpeta de salida CORTA (v3/linea_base.py, MAX_BASE_WINDOWS); la
            # carpeta de esta fase es demasiado larga, así que se usa una nueva junto a «eq3_verificacion».
            orden = [*orden, "--salida", str(base.parent.parent / f"lb{sello[9:15]}")]
        print(f"[{fid}] INICIO {desc} ...", flush=True)
        t = time.monotonic()
        r = plataforma.ejecutar(orden, cwd=RAIZ, env=plataforma.entorno_hijo(tmp), timeout=3600)
        salida = r.stdout + r.stderr
        (base / f"{fid}.log").write_text(salida, encoding="utf-8")
        ultima = [l for l in salida.splitlines() if l.strip()][-1:] or [""]
        estado = "OK" if r.returncode in CODIGOS_OK.get(fid, (0,)) else "FALLO"
        resultados.append({"id": fid, "descripcion": desc, "naturaleza": nat, "estado": estado, "rc": r.returncode,
                           "duracion_s": round(time.monotonic() - t, 1), "detalle": ultima[0][:300]})
        if estado == "OK" and r.returncode == CON_INESTABLES:
            resultados[-1]["con_inestables"] = True
        progreso["fases"][fid] = {"orden": orden_fase, "resultado": resultados[-1]}
        guardar_progreso(base, progreso)
        print(f"[{fid}] {estado} ({resultados[-1]['duracion_s']} s) — {ultima[0][:160]}", flush=True)
    huella_fin = huella(base)
    cambios = diferencias_huella(huella_ini, huella_fin)
    if cambios:
        detalle = (f"el código o el entorno cambió DURANTE la verificación ({len(cambios)}): " + "; ".join(cambios[:5]))
        resultados.append({"id": "HUELLA", "descripcion": "mismo código y entorno al empezar y al terminar",
                           "naturaleza": "REAL", "estado": "FALLO", "detalle": detalle[:300]})
        progreso["invalida"] = detalle[:300]
        guardar_progreso(base, progreso)
        print(f"[HUELLA] FALLO — {detalle[:160]}", flush=True)
    fallos = [x["id"] for x in resultados if x["estado"] != "OK"]
    inestables = [x["id"] for x in resultados if x.get("con_inestables")]
    informe = {"version": "v3.1-f0.5", "sello": sello, "python": sys.version.split()[0],
               "plataforma": plataforma.nombre(),
               "completo": a.completo, "reanuda": progreso["reanuda"],
               "huella_archivos_sha256": huella_ini["archivos_sha256"], "resultados": resultados, "fallidas": fallos,
               "estado_general": ("CON FALLOS" if fallos else
                                  f"CORRECTO CON PRUEBAS INESTABLES CONFIRMADAS ({', '.join(inestables)})" if inestables
                                  else "CORRECTO"),
               "fases_con_inestables": inestables,
               "nota": "Sin Qwen real: los agentes de las fases F2 y F11 son SIMULADOS. Esta ejecución solo valida la "
                       f"plataforma «{plataforma.nombre()}»; las demás requieren su propia ejecución."}
    (base / "informe.json").write_text(json.dumps(informe, ensure_ascii=False, indent=1), encoding="utf-8")
    print("*** FIN DE LAS PRUEBAS ***")
    print(f"RESUMEN: {len(resultados)} fases, {len(resultados) - len(fallos)} correctas, {len(fallos)} fallidas"
          + (f" ({', '.join(fallos)})" if fallos else "") + f"; {round(time.monotonic() - t0, 1)} s")
    print(f"Informe: {base / 'informe.json'}\nESTADO GENERAL: {informe['estado_general']}")
    return 0 if not fallos else 1


if __name__ == "__main__":
    sys.exit(main())
