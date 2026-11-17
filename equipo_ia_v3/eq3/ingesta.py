"""Equipo IA V3 · INGESTA de ejecuciones de V2-F.1 en la traza unificada (Etapa 1).

Lee lo que V2-F.1 escribe en su laboratorio para una tarea de tipo «funcion_supervisada»: `tarea.json`,
`eventos.jsonl`, `decisiones.jsonl`, `herramientas.jsonl`, `plan.json`, `estatico/vN.json`,
`pruebas_pendientes/casos.json`, `informe.json`, las versiones de la solución y las bases de aprendizaje de
A1/A2/A3. Inserta cada elemento en la traza, enlazado con los demás.

Seguridad (todo lo leído son DATOS no confiables):
- Nunca se ejecuta ni se importa nada de lo leído: solo se analiza como JSON o como texto.
- Rutas confinadas al laboratorio: se rechazan las absolutas, «..», los enlaces simbólicos y los archivos que
  no son normales. Hay límites de tamaño por archivo y de líneas por registro.
- Los SHA-256 que declaran los eventos se comprueban contra los archivos; si uno no coincide, no se importa nada.
- Cada ejecución se inserta en UNA transacción, y un error o un STOP (`<lab>/STOP` o `<lab>/tareas/<id>/STOP`)
  la deshace entera.
- Las bases de aprendizaje de eq2 se abren en SOLO LECTURA.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import re
import sqlite3
import stat
from pathlib import Path, PurePosixPath

from . import traza as T
from .plataforma import es_enlace

MAX_ARCHIVO = 4 * 1024 * 1024
MAX_LINEAS = 20_000
MAX_CONTENIDO = 64 * 1024
RE_TAREA = re.compile(r"LAB-\d{3,6}")
RE_EJEC = re.compile(r"E\d{3,6}")
RE_VERSION = re.compile(r"v(\d{1,4})\.json")
AGENTES_MODELO = ("A1", "A2", "A3")


class ErrorIngesta(Exception):
    """Base de los errores de ingesta: nunca dejan filas parciales."""


class ErrorValidacion(ErrorIngesta):
    """Datos o rutas inválidos."""


class ErrorIntegridad(ErrorIngesta):
    """Un SHA-256 declarado no coincide con el archivo, o una tarea cambió entre importaciones."""


class NoSoportado(ErrorIngesta):
    """Tipo de tarea o situación que esta versión todavía no sabe importar (se informa, no se adivina)."""


class Detenido(ErrorIngesta):
    """Un archivo STOP pidió parar: la transacción se deshace."""


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def ruta_segura(lab: Path, rel: str, maximo: int = MAX_ARCHIVO) -> Path:
    """Valida `rel` (relativa al laboratorio) sin leerla: sin «..», sin rutas absolutas, sin enlaces en NINGÚN
    componente (un enlace a una carpeta haría pasar por normal el último archivo; en Windows también las uniones:
    `plataforma.es_enlace`), solo archivos normales y no más grandes que `maximo`."""
    p = PurePosixPath(rel)
    if not p.parts or p.is_absolute() or ".." in p.parts or "\\" in rel:
        raise ErrorValidacion(f"ruta no permitida: {rel!r}")
    actual = lab
    for parte in p.parts:
        actual = actual / parte
        if es_enlace(actual):
            raise ErrorValidacion(f"enlace simbólico no permitido: {rel}")
    try:
        st = actual.lstat()
    except FileNotFoundError:
        raise ErrorValidacion(f"no existe: {rel}") from None
    if not stat.S_ISREG(st.st_mode):
        raise ErrorValidacion(f"no es un archivo normal: {rel}")
    if st.st_size > maximo:
        raise ErrorValidacion(f"archivo demasiado grande ({st.st_size} bytes): {rel}")
    return actual


def leer(lab: Path, rel: str, maximo: int = MAX_ARCHIVO) -> bytes:
    """Lee `rel` con el confinamiento de `ruta_segura`."""
    return ruta_segura(lab, rel, maximo).read_bytes()


def existe(lab: Path, rel: str) -> bool:
    try:
        ruta_segura(lab, rel)
        return True
    except ErrorValidacion:
        return False


def _decodificar(texto: str, que: str):
    try:
        return json.loads(texto)
    except (ValueError, RecursionError) as e:          # RecursionError: anidamiento extremo («[[[[…]]]]»)
        raise ErrorValidacion(f"JSON inválido en {que}: {type(e).__name__}") from None


def json_de(lab: Path, rel: str):
    try:
        texto = leer(lab, rel).decode("utf-8")
    except UnicodeDecodeError:
        raise ErrorValidacion(f"{rel}: no es UTF-8") from None
    return _decodificar(texto, rel)


def jsonl_de(lab: Path, rel: str) -> list:
    try:
        lineas = leer(lab, rel).decode("utf-8").splitlines()
    except UnicodeDecodeError:
        raise ErrorValidacion(f"{rel}: no es UTF-8") from None
    if len(lineas) > MAX_LINEAS:
        raise ErrorValidacion(f"{rel}: demasiadas líneas ({len(lineas)})")
    salida = []
    for i, linea in enumerate(lineas, 1):
        if not linea.strip():
            continue
        d = _decodificar(linea, f"{rel}:{i}")
        if not isinstance(d, dict):
            raise ErrorValidacion(f"{rel}:{i}: se esperaba un objeto")
        salida.append(d)
    return salida


def _texto(v, campo: str, maximo: int = 4096, opcional: bool = True):
    if v is None and opcional:
        return None
    if not isinstance(v, str) or len(v) > maximo:
        raise ErrorValidacion(f"campo {campo}: se esperaba texto de hasta {maximo} caracteres")
    return v


def _entero(v, campo: str):
    if v is None:
        return None
    if isinstance(v, bool) or not isinstance(v, int):
        raise ErrorValidacion(f"campo {campo}: se esperaba un entero")
    return v


def _contenido(obj, campo: str) -> str:
    c = T.canonico(obj)
    if len(c) > MAX_CONTENIDO:
        raise ErrorValidacion(f"{campo}: contenido demasiado grande ({len(c)} caracteres)")
    return c


def _verificado(lab: Path, rel: str, esperado: str, que: str) -> bytes:
    b = leer(lab, rel)
    if sha256_bytes(b) != esperado:
        raise ErrorIntegridad(f"{que}: el SHA-256 de {rel} no coincide con el declarado")
    return b


def comprobar_stop(lab: Path, tarea: str) -> None:
    for rel in ("STOP", f"tareas/{tarea}/STOP"):
        if (lab / rel).exists():
            raise Detenido(f"STOP encontrado en {rel}")


def _tarjeta(agente: str):
    from eq2 import roles                         # tarjetas de rol de V2-F.1 (la identidad de cada agente)
    tarjeta = roles.ROLES[agente]
    return tarjeta["rol"], T.sha256_texto(T.canonico(tarjeta))


def leer_ejecucion(lab: Path, tarea: str, ejec: str) -> dict:
    """Lee, valida y comprueba los hashes de una ejecución. No toca la traza: devuelve las filas preparadas."""
    eid = f"{tarea}/{ejec}"
    raiz_t = f"tareas/{tarea}"
    raiz_e = f"{raiz_t}/ejecuciones/{ejec}"
    fdir = f"{raiz_e}/funcion"
    tarea_b = leer(lab, f"{raiz_t}/tarea.json")
    tarea_d = json_de(lab, f"{raiz_t}/tarea.json")
    if not isinstance(tarea_d, dict) or tarea_d.get("tipo") != "funcion_supervisada":
        raise NoSoportado(f"{tarea}: tipo de tarea no soportado todavía: {tarea_d.get('tipo') if isinstance(tarea_d, dict) else '?'}")
    informe_b = leer(lab, f"{fdir}/informe.json")
    informe = json_de(lab, f"{fdir}/informe.json")
    eventos = jsonl_de(lab, f"{fdir}/eventos.jsonl")
    decisiones = jsonl_de(lab, f"{fdir}/decisiones.jsonl")
    herramientas = jsonl_de(lab, f"{fdir}/herramientas.jsonl") if existe(lab, f"{fdir}/herramientas.jsonl") else []
    dinamica = informe.get("ejecucion_dinamica")
    if (dinamica.get("estado") if isinstance(dinamica, dict) else dinamica) != "bloqueada":
        raise NoSoportado(f"{eid}: solo se importan ejecuciones con la ejecución dinámica bloqueada")
    inicio = next((e for e in eventos if e.get("tipo") == "inicio"), None)
    fin = next((e for e in eventos if e.get("tipo") == "fin"), None)
    if inicio is None or not isinstance(inicio.get("backend"), dict):
        raise ErrorValidacion(f"{eid}: falta el evento de inicio con su backend")
    backend = _texto(inicio["backend"].get("etiqueta"), "backend", 64, opcional=False)
    naturaleza = "SIMULADA" if inicio["backend"].get("simulado") is not False else "REAL"
    filas = {t: [] for t in T.TABLAS}
    filas["objetivos"].append({
        "id": tarea, "tarea": tarea, "titulo": _texto(tarea_d.get("titulo"), "titulo", 512),
        "instrucciones": _texto(tarea_d.get("instrucciones"), "instrucciones", 16384, opcional=False),
        "criterios": _contenido({k: tarea_d.get(k) for k in ("funcion", "casos", "propiedades", "resultado_esperado",
                                                             "max_iteraciones", "politica_falta")}, "criterios"),
        "tarea_sha256": sha256_bytes(tarea_b)})
    manifiesto = f"{raiz_e}/MANIFIESTO_SHA256.txt"
    filas["ejecuciones"].append({
        "id": eid, "objetivo_id": tarea, "inicio": _texto(inicio.get("ts"), "ts", 64),
        "fin": _texto(fin.get("ts"), "ts", 64) if fin else None, "backend": backend, "naturaleza": naturaleza,
        "version_sistema": _texto(inicio.get("version"), "version", 64, opcional=False),
        "manifiesto_sha256": sha256_bytes(leer(lab, manifiesto)) if existe(lab, manifiesto) else None})
    pasos = [e for e in eventos if e.get("tipo") == "paso"]
    agentes = {_texto(p.get("agente"), "agente", 32, opcional=False) for p in pasos}
    agentes |= {_texto(h.get("agente"), "agente", 32, opcional=False) for h in herramientas}
    for ag in sorted(agentes):
        if ag in AGENTES_MODELO:
            rol, tarjeta = _tarjeta(ag)
            filas["agentes"].append({"ejecucion_id": eid, "agente": ag, "rol": rol, "tarjeta_sha256": tarjeta,
                                     "backend": backend, "naturaleza": naturaleza})
        elif ag == "controlador":
            filas["agentes"].append({"ejecucion_id": eid, "agente": ag, "rol": "controlador (código determinista)",
                                     "tarjeta_sha256": None, "backend": "codigo", "naturaleza": "DETERMINISTA"})
        else:
            raise ErrorValidacion(f"{eid}: agente desconocido: {ag!r}")
    for p in pasos:
        n = _entero(p.get("n"), "n")
        archivo = f"{fdir}/{_texto(p.get('archivo'), 'archivo', 256, opcional=False)}"
        _verificado(lab, archivo, _texto(p.get("sha256"), "sha256", 64, opcional=False), f"paso {n}")
        prompt = archivo.replace("/agentes/", "/prompts/", 1)
        detalle = {k: p.get(k) for k in ("omitidos", "recortados", "afirmaciones_sin_evidencia")}
        if prompt != archivo and existe(lab, prompt):
            detalle["prompt"] = {"archivo": prompt, "sha256": sha256_bytes(leer(lab, prompt))}
        filas["acciones"].append({"id": f"{eid}/P{n}", "ejecucion_id": eid, "n": n, "tipo": "paso",
                                  "agente": p["agente"], "nombre": _texto(p.get("paso"), "paso", 64, opcional=False),
                                  "archivo": archivo, "sha256": p["sha256"], "detalle": _contenido(detalle, "detalle")})
    for h in herramientas:
        n = _entero(h.get("n"), "n")
        filas["acciones"].append({
            "id": f"{eid}/H{n}", "ejecucion_id": eid, "n": n, "tipo": "herramienta", "agente": h["agente"],
            "nombre": _texto(h.get("herramienta"), "herramienta", 64, opcional=False), "archivo": None,
            "sha256": None, "detalle": _contenido({k: h.get(k) for k in ("estado", "categoria", "errores")}, "detalle")})
    if existe(lab, f"{fdir}/plan.json"):
        plan_b = leer(lab, f"{fdir}/plan.json")
        plan = json_de(lab, f"{fdir}/plan.json")
        sub = plan.get("subtareas", []) if isinstance(plan, dict) else []
        filas["analisis"].append({"id": f"{eid}/plan", "ejecucion_id": eid, "tipo": "plan", "version": None,
                                  "archivo": f"{fdir}/plan.json", "sha256": sha256_bytes(plan_b),
                                  "resumen": _contenido({"subtareas": len(sub) if isinstance(sub, list) else None},
                                                        "resumen")})
    estat = lab / fdir / "estatico"
    if estat.is_dir() and not es_enlace(estat):
        for nombre in sorted(x.name for x in estat.iterdir()):
            m = RE_VERSION.fullmatch(nombre)
            if not m:
                continue
            rel = f"{fdir}/estatico/{nombre}"
            b = leer(lab, rel)
            filas["analisis"].append({"id": f"{eid}/estatico/v{m.group(1)}", "ejecucion_id": eid, "tipo": "estatico",
                                      "version": int(m.group(1)), "archivo": rel, "sha256": sha256_bytes(b),
                                      "resumen": _contenido(json_de(lab, rel), "estatico")})
    for d in decisiones:
        n = _entero(d.get("n"), "n")
        quien = next((d[k] for k in ("autor", "responsable", "por") if isinstance(d.get(k), str)), None)
        filas["decisiones"].append({"id": f"{eid}/D{n}", "ejecucion_id": eid, "n": n,
                                    "tipo": _texto(d.get("tipo"), "tipo", 64, opcional=False),
                                    "agente": _texto(quien, "agente", 32), "ronda": _entero(d.get("ronda"), "ronda"),
                                    "version": _entero(d.get("version"), "version"),
                                    "contenido": _contenido(d, "decision")})
        if d.get("tipo") == "ejecucion_dinamica":
            concedida = d.get("autorizo_pruebas_recibido") is True
            seleccion = d.get("seleccion") if isinstance(d.get("seleccion"), dict) else {}
            filas["autorizaciones"].append({
                "id": f"{eid}/AUT{n}", "ejecucion_id": eid,
                "accion": _texto(seleccion.get("principal") or "pruebas_python", "accion", 64),
                "concedida": int(concedida), "actor": "usuario" if concedida else None,
                "origen": "bandera --autorizo-pruebas de equipo.py", "decision_id": f"{eid}/D{n}"})
    versiones = {}
    for ev in (e for e in eventos if e.get("tipo") == "version"):
        v = _entero(ev.get("version"), "version")
        archivos = ev.get("archivos")
        if not isinstance(archivos, dict):
            raise ErrorValidacion(f"{eid}: versión {v} sin archivos")
        versiones[v] = (archivos, _texto(ev.get("origen"), "origen", 64, opcional=False))
    for v in sorted(versiones):
        archivos, origen = versiones[v]
        for nombre, h in sorted(archivos.items()):
            _texto(nombre, "archivo", 128, opcional=False)
            rel = f"{raiz_e}/runs/{ejec}/proyecto/v{v}/{nombre}"
            actual = _verificado(lab, rel, _texto(h, "sha256", 64, opcional=False), f"versión {v}")
            previa = versiones.get(v - 1)
            antes_h = previa[0].get(nombre) if previa else None
            antes = leer(lab, f"{raiz_e}/runs/{ejec}/proyecto/v{v - 1}/{nombre}") if antes_h else b""
            diff = "".join(difflib.unified_diff(antes.decode("utf-8", "replace").splitlines(True),
                                                actual.decode("utf-8", "replace").splitlines(True),
                                                f"v{v - 1}/{nombre}" if antes_h else "/dev/null", f"v{v}/{nombre}"))
            filas["cambios"].append({"id": f"{eid}/C{v}/{nombre}", "ejecucion_id": eid, "version": v,
                                     "version_previa": v - 1 if previa else None, "origen": origen,
                                     "archivo": nombre, "sha256_antes": antes_h, "sha256_despues": h, "ruta": rel,
                                     "diff": diff[:MAX_CONTENIDO]})
    casos_rel = f"{fdir}/pruebas_pendientes/casos.json"
    if existe(lab, casos_rel):
        casos = json_de(lab, casos_rel)
        if not isinstance(casos, dict) or not isinstance(casos.get("usados", []), list):
            raise ErrorValidacion(f"{casos_rel}: formato desconocido")
        # El archivo entero (usados, excluidos con su motivo, conflictos...) queda enlazado por su hash;
        # los casos «usados» son las pruebas pendientes.
        filas["analisis"].append({"id": f"{eid}/casos", "ejecucion_id": eid, "tipo": "casos", "version": None,
                                  "archivo": casos_rel, "sha256": sha256_bytes(leer(lab, casos_rel)),
                                  "resumen": _contenido({g: len(v) for g, v in sorted(casos.items())
                                                         if isinstance(v, (list, dict))}, "resumen")})
        for c in casos.get("usados", []):
            if not isinstance(c, dict):
                raise ErrorValidacion(f"{casos_rel}: caso inválido")
            filas["pruebas"].append({"id": f"{eid}/T/{_texto(c.get('id'), 'id', 64, opcional=False)}",
                                     "ejecucion_id": eid, "caso": _texto(c.get("caso"), "caso", 4096, opcional=False),
                                     "fuente": _texto(c.get("fuente"), "fuente", 64) or "desconocida",
                                     "estado": "pendiente_no_ejecutada", "autorizacion_id": None})
    aceptada = informe.get("aceptada")
    filas["resultados"].append({
        "ejecucion_id": eid, "estado_final": _texto(informe.get("estado_final"), "estado_final", 64, opcional=False),
        "resultado": _texto(informe.get("resultado"), "resultado", 64, opcional=False),
        "aceptada": None if aceptada is None else int(bool(aceptada)),
        "version_recomendada": _version_recomendada(lab, fdir, informe.get("version_recomendada")),
        "motivo": _texto(informe.get("motivo"), "motivo", 4096), "informe": f"{fdir}/informe.json",
        "informe_sha256": sha256_bytes(informe_b)})
    filas["experiencias"] = _experiencias(lab, eid, filas["agentes"])
    return filas


def _version_recomendada(lab: Path, fdir: str, vr):
    """V2-F.1 la escribe como {version, carpeta, archivos}; los archivos de esa carpeta deben tener esos hashes."""
    if vr is None or isinstance(vr, int) and not isinstance(vr, bool):
        return vr
    if not isinstance(vr, dict) or not isinstance(vr.get("archivos"), dict):
        raise ErrorValidacion("version_recomendada con un formato desconocido")
    carpeta = _texto(vr.get("carpeta"), "carpeta", 64, opcional=False)
    if "/" in carpeta or carpeta in (".", ".."):
        raise ErrorValidacion(f"carpeta de la versión recomendada no permitida: {carpeta!r}")
    for nombre, h in sorted(vr["archivos"].items()):
        if "/" in _texto(nombre, "archivo", 128, opcional=False):
            raise ErrorValidacion(f"archivo de la versión recomendada no permitido: {nombre!r}")
        _verificado(lab, f"{fdir}/{carpeta}/{nombre}", _texto(h, "sha256", 64, opcional=False), "versión recomendada")
    return _entero(vr.get("version"), "version_recomendada")


def _experiencias(lab: Path, eid: str, agentes: list) -> list:
    """Recuerdos de A1/A2/A3 cuya `tarea_ref` es esta ejecución, leídos de su base de aprendizaje (solo lectura)."""
    presentes = {a["agente"] for a in agentes}
    salida = []
    for ag in AGENTES_MODELO:
        rel = f"aprendizaje/{ag.lower()}.db"
        if not existe(lab, rel) or ag not in presentes:
            continue
        con = sqlite3.connect(f"file:{(lab / rel).as_posix()}?mode=ro", uri=True)
        try:
            filas = con.execute("SELECT id, tipo, estado_inicial, sha256 FROM recuerdos WHERE tarea_ref = ? "
                                "ORDER BY num", (eid,)).fetchall()
        except sqlite3.Error as e:
            raise ErrorValidacion(f"{rel}: base de aprendizaje ilegible: {type(e).__name__}") from None
        finally:
            con.close()
        for rid, tipo, estado, h in filas:
            salida.append({"id": f"{eid}/X/{ag}/{rid}", "ejecucion_id": eid, "agente": ag, "recuerdo_id": rid,
                           "tipo": tipo, "estado": estado, "texto_sha256": h, "base": rel})
    return salida


ORDEN = ("ejecuciones", "agentes", "analisis", "decisiones", "autorizaciones", "acciones", "cambios", "pruebas",
         "resultados", "experiencias")


def insertar(traza: T.Traza, filas: dict, comprobar=lambda: None) -> None:
    """Inserta una ejecución preparada. Debe llamarse dentro de `traza.transaccion()`."""
    for obj in filas["objetivos"]:
        previo = traza.filas("objetivos", id=obj["id"])
        if previo:
            if previo[0]["tarea_sha256"] != obj["tarea_sha256"]:
                raise ErrorIntegridad(f"{obj['id']}: la tarea cambió desde la importación anterior")
        else:
            traza.insertar("objetivos", obj)
    for tabla in ORDEN:
        comprobar()
        for fila in filas[tabla]:
            traza.insertar(tabla, fila)


def importar_tarea(traza: T.Traza, lab: Path, tarea: str, comprobar=None) -> list:
    """Importa las ejecuciones de `tarea` que aún no están en la traza. Devuelve sus identificadores."""
    lab = Path(lab).resolve()
    if not RE_TAREA.fullmatch(tarea):
        raise ErrorValidacion(f"identificador de tarea inválido: {tarea!r}")
    comprobar = comprobar or (lambda: comprobar_stop(lab, tarea))
    dir_e = lab / "tareas" / tarea / "ejecuciones"
    if es_enlace(dir_e) or not dir_e.is_dir():
        raise ErrorValidacion(f"{tarea}: no hay ejecuciones")
    importadas = []
    for ejec in sorted(d.name for d in dir_e.iterdir() if RE_EJEC.fullmatch(d.name)):
        eid = f"{tarea}/{ejec}"
        if traza.existe("ejecuciones", id=eid):
            continue
        comprobar()
        filas = leer_ejecucion(lab, tarea, ejec)
        with traza.transaccion():
            insertar(traza, filas, comprobar)
        importadas.append(eid)
    return importadas
