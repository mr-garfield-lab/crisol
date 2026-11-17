"""V2-E.5-r3: paquetes de auditoría ADICIONALES (p. ej. preparados por GPT-6), solo DECLARATIVOS.

Un paquete es un ZIP con `manifiesto.json` y archivos de datos (.json, .md, .txt). NUNCA se ejecuta
código del paquete: cada prueba nombra una OPERACIÓN de una lista cerrada que implementa Equipo IA y
le pasa datos. Lo que pida otra cosa (código Python, órdenes, red, el modelo) se marca «no_disponible»
hasta que exista un aislamiento real; no se improvisa.

Seguridad de la lectura:
  * el ZIP se lee EN MEMORIA (nada se extrae al disco): ninguna ruta puede salir del laboratorio;
  * se rechazan nombres absolutos, con «..», «\\», unidades de Windows, controles, enlaces simbólicos,
    entradas cifradas, duplicados, extensiones no admitidas, archivos no declarados y desajustes de
    SHA-256; hay límites de tamaño, número de archivos y tasa de compresión;
  * el manifiesto tiene esquema cerrado y versión de formato; la compatibilidad se comprueba contra la
    versión de Equipo IA.
UN HASH CORRECTO SOLO PRUEBA INTEGRIDAD (que el contenido es el declarado), NO QUE SEA CONFIABLE.
La confianza la da el usuario autorizando el paquete (verificar.py --autorizar-paquete).
"""
from __future__ import annotations

import hashlib
import json
import re
import stat
import zipfile

from . import analisis_estatico, evaluacion_criticas, inferencia, personalidad, sanea

FORMATO = "eq2/auditoria"
VERSION_FORMATO = 1
# V2-E.6: paquetes de DESAFÍO (retos de diagnóstico estático con oráculos), mismo contenedor y mismas reglas.
FORMATOS = {"eq2/auditoria": 1, "eq2/desafio": 1}
OPERACIONES = {
    "clasificar_criticas": "casos etiquetados -> informe de críticas; compara con el resumen o veredictos esperados",
    "validar_perfil": "respuestas de elección de personalidad -> categoría esperada (valida/invalida/...)",
    "motivo_parada": "motivos de error -> si son o no la materialización de una parada pedida",
    "analisis_estatico": "archivos de texto -> tipos de error del análisis estático (AST; no ejecuta nada)",
    "huella_archivo": "un archivo de la versión instalada debe tener el SHA-256 indicado",
    "repetir_prueba": "repite N veces una prueba EXISTENTE de Equipo IA (código propio, no del paquete)",
    "puntuar_reto": "respuestas -> puntuación 0-12 con el material y los oráculos del paquete (V2-E.6)",
    "generar_reto": "semilla -> casos del generador propio seguro; comprueba el orden esperado (V2-E.6)",
}
NO_DISPONIBLES = {"python": "ejecutar código del paquete requiere un aislamiento real que no existe",
                  "comando": "las órdenes del sistema no se permiten",
                  "red": "sin acceso a red", "modelo": "las pruebas con el modelo real no se delegan a paquetes"}
EXTENSIONES = (".json", ".md", ".txt")
MAX_ZIP_BYTES = 2_000_000
MAX_ARCHIVOS = 50
MAX_ARCHIVO_BYTES = 1_000_000
MAX_TOTAL_BYTES = 5_000_000
MAX_RATIO = 50
MAX_PRUEBAS = 100
MAX_REPETICIONES = 20
MAX_SEGUNDOS = 600
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{1,63}$")
_NOMBRE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,62}(?:/[A-Za-z0-9_][A-Za-z0-9_.-]{0,62}){0,3}$")
_PRUEBA_EXISTENTE = re.compile(r"^(test_[a-z0-9_]+)(?:\.[A-Za-z][A-Za-z0-9_]*){0,2}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
CLAVES_MANIFIESTO = {"formato", "version_formato", "id", "titulo", "autor", "origen", "creado", "compatible_con",
                     "descripcion", "archivos", "pruebas"}
CLAVES_PRUEBA = {"id", "objetivo", "operacion", "parametros", "criterio", "recursos", "segundos_max"}


class PaqueteInvalido(ValueError):
    pass


def _nombre_seguro(n: str) -> str | None:
    """Motivo de rechazo del nombre de una entrada del ZIP, o None si es seguro."""
    if not isinstance(n, str) or not n or len(n) > 200:
        return "nombre vacío o demasiado largo"
    if n.startswith(("/", "\\")) or "\\" in n or re.match(r"^[A-Za-z]:", n):
        return "ruta absoluta o con barra invertida"
    if any(p in ("", ".", "..") for p in n.rstrip("/").split("/")):
        return "componente de ruta no permitido"
    if any(ord(c) < 32 or c in '<>:"|?*' for c in n):
        return "carácter no permitido"
    return None


def sha256(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


def inspeccionar(ruta, version_actual: str) -> dict:
    """Valida un ZIP SIN extraerlo. Devuelve {sha256, manifiesto, datos, problemas, compatible, pruebas}.
    Lanza PaqueteInvalido si el contenedor no es aceptable (nada se ejecuta en ningún caso)."""
    try:
        bruto = ruta.read_bytes() if hasattr(ruta, "read_bytes") else bytes(ruta)
    except OSError as e:
        raise PaqueteInvalido(f"no se puede leer el paquete: {type(e).__name__}") from None
    if len(bruto) > MAX_ZIP_BYTES:
        raise PaqueteInvalido(f"el ZIP supera {MAX_ZIP_BYTES} bytes")
    huella = sha256(bruto)
    import io
    try:
        zf = zipfile.ZipFile(io.BytesIO(bruto))
    except zipfile.BadZipFile:
        raise PaqueteInvalido("no es un ZIP válido") from None
    datos, vistos, total = {}, set(), 0
    with zf:
        infos = zf.infolist()
        if len(infos) > MAX_ARCHIVOS + 10:
            raise PaqueteInvalido("demasiadas entradas en el ZIP")
        for zi in infos:
            motivo = _nombre_seguro(zi.filename)
            if motivo:
                raise PaqueteInvalido(f"entrada {zi.filename[:60]!r}: {motivo}")
            if zi.is_dir():
                continue
            modo = zi.external_attr >> 16
            if stat.S_ISLNK(modo):
                raise PaqueteInvalido(f"entrada {zi.filename!r}: enlace simbólico")
            if zi.flag_bits & 0x1:
                raise PaqueteInvalido(f"entrada {zi.filename!r}: cifrada")
            if zi.filename in vistos:
                raise PaqueteInvalido(f"entrada duplicada: {zi.filename!r}")
            vistos.add(zi.filename)
            if not zi.filename.endswith(EXTENSIONES):
                raise PaqueteInvalido(f"extensión no admitida: {zi.filename!r} (solo {', '.join(EXTENSIONES)})")
            if zi.file_size > MAX_ARCHIVO_BYTES:
                raise PaqueteInvalido(f"{zi.filename!r} supera {MAX_ARCHIVO_BYTES} bytes")
            if zi.compress_size and zi.file_size / max(1, zi.compress_size) > MAX_RATIO:
                raise PaqueteInvalido(f"{zi.filename!r}: tasa de compresión sospechosa")
            total += zi.file_size
            if total > MAX_TOTAL_BYTES or len(datos) >= MAX_ARCHIVOS:
                raise PaqueteInvalido("el contenido descomprimido supera los límites")
            contenido = zf.read(zi)
            if len(contenido) != zi.file_size:
                raise PaqueteInvalido(f"{zi.filename!r}: tamaño inconsistente")
            datos[zi.filename] = contenido
    if "manifiesto.json" not in datos:
        raise PaqueteInvalido("falta manifiesto.json")
    man = _json(datos["manifiesto.json"], "manifiesto.json")
    problemas = validar_manifiesto(man, datos)
    compatible = isinstance(man, dict) and version_actual in (man.get("compatible_con") or [])
    pruebas = []
    if not problemas:
        for p in man["pruebas"]:
            pruebas.append({"id": p["id"], "objetivo": p["objetivo"], "operacion": p["operacion"],
                            "ejecutable": _disponibilidad(p)})
    return {"sha256": huella, "manifiesto": man, "datos": datos, "problemas": problemas,
            "compatible": compatible, "pruebas": pruebas}


def _json(b: bytes, nombre: str):
    try:
        return json.loads(b.decode("utf-8"), parse_constant=lambda c: (_ for _ in ()).throw(ValueError(c)))
    except (UnicodeDecodeError, ValueError) as e:
        raise PaqueteInvalido(f"{nombre}: JSON inválido ({type(e).__name__})") from None


def validar_manifiesto(man, datos: dict) -> list:
    """Problemas del manifiesto (lista vacía = válido). Esquema cerrado."""
    pr = []
    if not isinstance(man, dict):
        return ["el manifiesto no es un objeto"]
    extra = set(man) - CLAVES_MANIFIESTO
    if extra:
        pr.append("claves desconocidas en el manifiesto: " + ", ".join(sorted(map(str, extra)))[:200])
    if man.get("formato") not in FORMATOS:
        pr.append("formato no admitido (se admiten " + ", ".join(sorted(FORMATOS)) + ")")
    elif man.get("version_formato") != FORMATOS[man["formato"]]:
        pr.append(f"version_formato no admitida (se admite {FORMATOS[man['formato']]})")
    if not isinstance(man.get("id"), str) or not _ID.match(man["id"]):
        pr.append("id inválido")
    for k in ("titulo", "autor", "origen"):
        if not isinstance(man.get(k), str) or not 1 <= len(man[k]) <= 200:
            pr.append(f"«{k}» debe ser texto (1–200)")
    cc = man.get("compatible_con")
    if not isinstance(cc, list) or not cc or not all(isinstance(v, str) and len(v) <= 40 for v in cc):
        pr.append("compatible_con debe ser una lista de versiones")
    arch = man.get("archivos")
    if not isinstance(arch, dict):
        pr.append("archivos debe ser un objeto {ruta: sha256}")
        arch = {}
    for n, h in arch.items():
        if not isinstance(n, str) or _nombre_seguro(n) or not _NOMBRE.match(n) or n == "manifiesto.json":
            pr.append(f"ruta declarada no válida: {str(n)[:60]!r}")
        elif not isinstance(h, str) or not _HEX64.match(h):
            pr.append(f"sha256 mal formado para {n!r}")
        elif n not in datos:
            pr.append(f"archivo declarado ausente: {n!r}")
        elif sha256(datos[n]) != h:
            pr.append(f"sha256 no coincide: {n!r}")
    no_decl = sorted(set(datos) - set(arch) - {"manifiesto.json"})
    if no_decl:
        pr.append("archivos no declarados en el manifiesto: " + ", ".join(no_decl)[:200])
    pruebas = man.get("pruebas")
    if not isinstance(pruebas, list) or not 1 <= len(pruebas) <= MAX_PRUEBAS:
        pr.append(f"pruebas: lista de 1 a {MAX_PRUEBAS}")
        return pr
    ids = set()
    for i, p in enumerate(pruebas):
        if not isinstance(p, dict):
            pr.append(f"prueba {i}: no es un objeto")
            continue
        extra = set(p) - CLAVES_PRUEBA
        if extra:
            pr.append(f"prueba {i}: claves desconocidas " + ", ".join(sorted(map(str, extra)))[:120])
        if not isinstance(p.get("id"), str) or not _ID.match(p["id"]) or p["id"] in ids:
            pr.append(f"prueba {i}: id inválido o repetido")
        ids.add(p.get("id"))
        if not isinstance(p.get("objetivo"), str) or not 1 <= len(p["objetivo"]) <= 300:
            pr.append(f"prueba {i}: objetivo (1–300)")
        if not isinstance(p.get("operacion"), str):
            pr.append(f"prueba {i}: operación ausente")
        if not isinstance(p.get("parametros", {}), dict) or not isinstance(p.get("criterio", {}), dict):
            pr.append(f"prueba {i}: parametros y criterio deben ser objetos")
        rec = p.get("recursos", {})
        if not isinstance(rec, dict) or not all(isinstance(v, bool) for v in rec.values()):
            pr.append(f"prueba {i}: recursos debe ser {{nombre: bool}}")
        s = p.get("segundos_max", 60)
        if not isinstance(s, (int, float)) or isinstance(s, bool) or not 1 <= s <= MAX_SEGUNDOS:
            pr.append(f"prueba {i}: segundos_max entre 1 y {MAX_SEGUNDOS}")
        archivo = (p.get("parametros") or {}).get("archivo") if isinstance(p.get("parametros"), dict) else None
        if archivo is not None and archivo not in arch:
            pr.append(f"prueba {i}: usa un archivo no declarado")
        reto = (p.get("parametros") or {}).get("reto") if isinstance(p.get("parametros"), dict) else None
        if reto is not None and (not isinstance(reto, str) or not _NOMBRE.match(reto)
                                 or any(f"{reto}/{n}.json" not in arch for n in ("casos", "oraculos"))):
            pr.append(f"prueba {i}: «reto» debe ser una carpeta declarada con casos.json y oraculos.json")
    return pr


def _disponibilidad(p: dict) -> str:
    """'si' o 'no:<motivo>'. Una operación desconocida o un recurso no admitido nunca se ejecutan."""
    rec = p.get("recursos") or {}
    for r, motivo in NO_DISPONIBLES.items():
        if rec.get(r):
            return f"no:{motivo}"
    op = p.get("operacion")
    if op in NO_DISPONIBLES:
        return f"no:{NO_DISPONIBLES[op]}"
    if op not in OPERACIONES:
        return f"no:operación desconocida {str(op)[:40]!r}"
    if op == "repetir_prueba":
        prm = p.get("parametros") or {}
        if not isinstance(prm.get("prueba"), str) or not _PRUEBA_EXISTENTE.match(prm["prueba"]):
            return "no:nombre de prueba no válido"
        n = prm.get("repeticiones", 1)
        if not isinstance(n, int) or isinstance(n, bool) or not 1 <= n <= MAX_REPETICIONES:
            return f"no:repeticiones entre 1 y {MAX_REPETICIONES}"
    return "si"


def _datos_json(p, datos):
    nombre = (p.get("parametros") or {}).get("archivo")
    if nombre is None:
        raise PaqueteInvalido("la operación necesita parametros.archivo")
    return _json(datos[nombre], nombre)


def ejecutar_declarativa(p: dict, datos: dict, raiz_version=None) -> dict:
    """Ejecuta UNA prueba de operación PURA (todas salvo repetir_prueba, que hace el verificador).
    Devuelve {resultado: ok|fallo|no_disponible, detalle}. Nunca evalúa código del paquete."""
    disp = _disponibilidad(p)
    if disp != "si":
        return {"resultado": "no_disponible", "detalle": disp[3:]}
    op, crit = p["operacion"], p.get("criterio") or {}
    try:
        if op == "clasificar_criticas":
            casos = evaluacion_criticas.validar_casos(_datos_json(p, datos))
            inf = evaluacion_criticas.informe(casos)
            fallos = []
            for k, v in (crit.get("resumen") or {}).items():
                if inf["resumen"].get(k) != v:
                    fallos.append(f"resumen.{k}: {inf['resumen'].get(k)!r} != {v!r}")
            ver = {c["id"]: [o["veredicto"] for o in c["objeciones"]] for c in inf["casos"]}
            for cid, esperado in (crit.get("veredictos") or {}).items():
                if ver.get(cid) != esperado:
                    fallos.append(f"{cid}: {ver.get(cid)!r} != {esperado!r}")
            return _res(fallos, {"resumen": inf["resumen"]})
        if op == "validar_perfil":
            casos, fallos = _datos_json(p, datos), []
            for i, c in enumerate(casos if isinstance(casos, list) else []):
                r = personalidad.validar_respuesta(c.get("respuesta"))
                cat = "valida" if r["valida"] else r["categoria"]
                if cat != c.get("categoria_esperada"):
                    fallos.append(f"caso {i}: {cat} != {c.get('categoria_esperada')}")
            return _res(fallos, {"casos": len(casos) if isinstance(casos, list) else 0})
        if op == "motivo_parada":
            casos, fallos = _datos_json(p, datos), []
            for i, c in enumerate(casos if isinstance(casos, list) else []):
                es = inferencia.parada_de(c.get("motivo")) is not None
                if es != c.get("es_parada"):
                    fallos.append(f"caso {i} ({str(c.get('motivo'))[:40]!r}): {es} != {c.get('es_parada')}")
            return _res(fallos, {"casos": len(casos) if isinstance(casos, list) else 0})
        if op == "analisis_estatico":
            d = _datos_json(p, datos)
            arch = d.get("archivos") if isinstance(d, dict) else None
            if not isinstance(arch, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in arch.items()):
                return {"resultado": "fallo", "detalle": "archivos: {ruta: texto}"}
            r = analisis_estatico.analizar(arch)
            tipos = sorted({e["tipo"] for e in r["errores"]})
            esperado = sorted(crit.get("tipos_error", []))
            return _res([] if tipos == esperado else [f"{tipos} != {esperado}"], {"tipos_error": tipos})
        if op == "huella_archivo":
            prm = p.get("parametros") or {}
            ruta, h = prm.get("ruta"), prm.get("sha256")
            if raiz_version is None or not isinstance(ruta, str) or _nombre_seguro(ruta) or not isinstance(h, str):
                return {"resultado": "fallo", "detalle": "ruta o sha256 inválidos"}
            f = raiz_version / ruta
            if f.is_symlink() or not f.is_file():
                return {"resultado": "fallo", "detalle": f"no existe {ruta}"}
            real = sha256(f.read_bytes())
            return _res([] if real == h else [f"sha256 {real[:12]}… != {h[:12]}…"], {"ruta": ruta})
        if op in ("puntuar_reto", "generar_reto"):                          # V2-E.6
            from . import retos
            prm = p.get("parametros") or {}
            if not isinstance(prm.get("reto"), str):
                return {"resultado": "fallo", "detalle": "parametros.reto: carpeta del reto en el paquete"}
            mat = retos.material_desde_datos(datos, prm["reto"])
            if op == "generar_reto":
                sem = prm.get("semilla")
                if not isinstance(sem, int) or isinstance(sem, bool):
                    return {"resultado": "fallo", "detalle": "parametros.semilla entera"}
                casos = [r["caso_id"] for r in retos.generar(mat, sem, int(prm.get("n", 3)))]
                esp = crit.get("casos")
                return _res([] if casos == esp else [f"{casos} != {esp}"], {"casos": casos})
            fallos, filas = [], []
            for i, r in enumerate(_datos_json(p, datos) or []):
                if not isinstance(r, dict) or r.get("caso") not in mat["casos"] or not isinstance(r.get("texto"), str):
                    fallos.append(f"respuesta {i}: caso o texto no válidos")
                    continue
                pt = retos.puntuar(mat, r["caso"], r["texto"])
                filas.append({"id": r.get("id", i), "caso": r["caso"], "total": pt["total"]})
                lo, hi = int(r.get("total_min", 0)), int(r.get("total_max", 12))
                if not lo <= pt["total"] <= hi:
                    fallos.append(f"{r.get('id', i)}: {pt['total']} fuera de [{lo}, {hi}]")
                tipos = {x["tipo"] for x in pt["penalizaciones"]}
                for t in r.get("penalizaciones_esperadas", []):
                    if t not in tipos:
                        fallos.append(f"{r.get('id', i)}: falta la penalización {t!r}")
            return _res(fallos, {"respuestas": filas})
    except PaqueteInvalido as e:
        return {"resultado": "fallo", "detalle": str(e)[:300]}
    except ValueError as e:
        return {"resultado": "fallo", "detalle": "datos no válidos: " + sanea.limpiar(str(e), 200)}
    return {"resultado": "no_disponible", "detalle": "la ejecuta el verificador"}


def _res(fallos, extra):
    return {"resultado": "fallo" if fallos else "ok", "detalle": "; ".join(fallos)[:600] or "ok", **extra}
