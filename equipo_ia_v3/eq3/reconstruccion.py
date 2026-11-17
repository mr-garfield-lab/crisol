"""Equipo IA V3 · RECONSTRUCCIÓN y VERIFICACIÓN de una ejecución desde la traza unificada (Etapa 1).

`reconstruir()` devuelve la cadena completa de una ejecución:
  objetivo → análisis → agentes → decisiones → autorizaciones → acciones → cambios → pruebas → resultado →
  experiencias.
`verificar()` devuelve la lista de problemas (vacía si todo cuadra). Comprueba:
  1. la cadena de hashes de toda la traza y que cada tabla contiene exactamente lo registrado;
  2. que los archivos referenciados (respuestas y prompts de los agentes, versiones, análisis, informe) siguen
     teniendo el SHA-256 registrado;
  3. que los recuerdos de las bases de aprendizaje siguen existiendo con el mismo hash;
  4. la completitud y coherencia de la cadena (reglas R1–R6, abajo).
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from . import ingesta as I
from . import traza as T


def reconstruir(traza: T.Traza, eid: str) -> dict:
    ejec = traza.filas("ejecuciones", id=eid)
    if not ejec:
        raise I.ErrorValidacion(f"ejecución no importada: {eid}")
    ejec = ejec[0]
    por = {t: traza.filas(t, ejecucion_id=eid) for t in T.TABLAS if t not in ("objetivos", "ejecuciones")}
    for t in ("decisiones", "acciones"):
        for f in por[t]:
            f["contenido" if t == "decisiones" else "detalle"] = json.loads(
                f["contenido" if t == "decisiones" else "detalle"])
    for f in por["analisis"]:
        f["resumen"] = json.loads(f["resumen"])
    objetivo = traza.filas("objetivos", id=ejec["objetivo_id"])[0]
    objetivo["criterios"] = json.loads(objetivo["criterios"])
    return {"objetivo": objetivo, "ejecucion": ejec, "analisis": por["analisis"], "agentes": por["agentes"],
            "decisiones": por["decisiones"], "autorizaciones": por["autorizaciones"],
            "acciones": sorted(por["acciones"], key=lambda a: (a["tipo"], a["n"])),
            "cambios": sorted(por["cambios"], key=lambda c: (c["version"], c["archivo"])),
            "pruebas": por["pruebas"], "resultado": (por["resultados"] or [None])[0],
            "experiencias": por["experiencias"]}


def _hash_archivo(lab: Path, rel: str, esperado: str, que: str, problemas: list) -> None:
    try:
        if I.sha256_bytes(I.leer(lab, rel)) != esperado:
            problemas.append(f"{que}: {rel} fue modificado (SHA-256 distinto)")
    except I.ErrorValidacion as e:
        problemas.append(f"{que}: {e}")


def verificar(traza: T.Traza, lab: Path, eid: str) -> list:
    lab = Path(lab).resolve()
    problemas = list(traza.verificar_cadena())
    try:
        r = reconstruir(traza, eid)
    except I.ErrorValidacion as e:
        return problemas + [str(e)]
    agentes = {a["agente"]: a for a in r["agentes"]}
    # Archivos referenciados.
    for a in r["acciones"]:
        if a["archivo"]:
            _hash_archivo(lab, a["archivo"], a["sha256"], f"acción {a['id']}", problemas)
        prompt = a["detalle"].get("prompt") if isinstance(a["detalle"], dict) else None
        if prompt:
            _hash_archivo(lab, prompt["archivo"], prompt["sha256"], f"prompt de {a['id']}", problemas)
    for c in r["cambios"]:
        _hash_archivo(lab, c["ruta"], c["sha256_despues"], f"cambio {c['id']}", problemas)
    for x in r["analisis"]:
        _hash_archivo(lab, x["archivo"], x["sha256"], f"análisis {x['id']}", problemas)
    if r["resultado"]:
        _hash_archivo(lab, r["resultado"]["informe"], r["resultado"]["informe_sha256"], "informe", problemas)
    # Recuerdos (bases de aprendizaje de eq2, en solo lectura).
    for x in r["experiencias"]:
        try:
            con = sqlite3.connect(f"file:{(lab / x['base']).as_posix()}?mode=ro", uri=True)
            try:
                fila = con.execute("SELECT sha256 FROM recuerdos WHERE id = ?", (x["recuerdo_id"],)).fetchone()
            finally:
                con.close()
        except sqlite3.Error as e:
            fila = None
            problemas.append(f"experiencia {x['id']}: base ilegible ({type(e).__name__})")
        if fila is None or fila[0] != x["texto_sha256"]:
            problemas.append(f"experiencia {x['id']}: el recuerdo ya no existe o cambió")
    # R1: hay resultado y, si el objetivo es de código, al menos una acción de un agente de modelo.
    if r["resultado"] is None:
        problemas.append("R1: la ejecución no tiene resultado")
    if not any(a["agente"] in I.AGENTES_MODELO for a in r["acciones"] if a["tipo"] == "paso"):
        problemas.append("R1: ningún paso de A1/A2/A3")
    # R2: cada versión enlaza con la anterior (sha256_antes = sha256_despues de la versión previa).
    por_version = {(c["version"], c["archivo"]): c for c in r["cambios"]}
    for c in r["cambios"]:
        if c["version_previa"] is not None:
            previa = por_version.get((c["version_previa"], c["archivo"]))
            if previa is None or previa["sha256_despues"] != c["sha256_antes"]:
                problemas.append(f"R2: {c['id']} no enlaza con la versión {c['version_previa']}")
    versiones = {c["version"] for c in r["cambios"]}
    # R3: las decisiones y el resultado solo citan versiones que existen.
    for d in r["decisiones"]:
        if d["version"] is not None and versiones and d["version"] not in versiones:
            problemas.append(f"R3: la decisión {d['id']} cita la versión inexistente {d['version']}")
    vr = r["resultado"] and r["resultado"]["version_recomendada"]
    if vr is not None and vr not in versiones:
        problemas.append(f"R3: versión recomendada inexistente: {vr}")
    # R4: ninguna prueba ejecutada sin una autorización concedida (también lo impone un CHECK de la base).
    concedidas = {a["id"] for a in r["autorizaciones"] if a["concedida"] == 1}
    for p in r["pruebas"]:
        if p["estado"] != "pendiente_no_ejecutada" and p["autorizacion_id"] not in concedidas:
            problemas.append(f"R4: prueba {p['id']} ejecutada sin autorización concedida")
    # R5: naturaleza coherente: una ejecución SIMULADA no puede tener agentes de modelo REALES, ni al revés.
    for ag, a in agentes.items():
        if ag in I.AGENTES_MODELO and a["naturaleza"] != r["ejecucion"]["naturaleza"]:
            problemas.append(f"R5: el agente {ag} es {a['naturaleza']} en una ejecución {r['ejecucion']['naturaleza']}")
    # R6: un resultado aceptado sin ejecución dinámica nunca figura como «verificado».
    if r["resultado"] and r["resultado"]["resultado"] == "verificado" and not concedidas:
        problemas.append("R6: resultado «verificado» sin ninguna ejecución autorizada")
    return problemas
