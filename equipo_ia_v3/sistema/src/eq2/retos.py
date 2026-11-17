"""V2-E.6: retos de DIAGNÓSTICO ESTÁTICO (primer reto: Project Zomboid, `retos/zomboid_v1/`).

Material: extractos REALES de un registro del juego aportados por el usuario (no es una reproducción
controlada). No se ejecuta el juego, ni mods, ni `material_original/generar_reto.py` (NO CONFIABLE: solo
se verifica su SHA-256); el generador propio `generar()` lo reimplementa de forma segura.

Separación obligatoria en cada respuesta (formato por líneas, ver FORMATO_RESPUESTA):
  HECHO (con CITA L<n> "texto literal"), HIPOTESIS (CONFIANZA y FALSACION), FALTA (dato faltante),
  RIESGO, ACCION (REVERSIBLE: si|no), VERIFICACION, NOTA.
Roles: A2 investiga (hechos, hipótesis, faltantes); A1 propone un plan y parches HIPOTÉTICOS (acciones
reversibles, riesgos); A3 refuta (comprueba citas, rechaza saltos lógicos).

Puntuación OBJETIVA (`puntuar`): 6 categorías 0–2 de CRITERIOS_EVALUACION.md (máx. 12) más
penalizaciones automáticas (afirmar corrección/ejecución/causa raíz, alterar partidas, culpar a un mod sin
prueba), citas inventadas, datos con unidades que no están en la evidencia y confianza alta sin cita.
Los oráculos están en `oraculos.json` y NUNCA entran en un prompt. El puntuador es heurístico y
determinista: mide la FORMA verificable de la respuesta (citas, matices, separación), no si el diagnóstico
es correcto en el juego real.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import sqlite3
from pathlib import Path

from . import laboratorios as L, sanea

FORMATO_RESPUESTA = """Responde SOLO con líneas de estas formas (una idea por línea):
HECHO: <qué muestra el registro> | CITA: L<n>[-L<m>][,L<k>] "<texto LITERAL de esas líneas>"
HIPOTESIS: <explicación posible> | CONFIANZA: baja|media|alta | FALSACION: <qué la refutaría>
FALTA: <dato que falta para decidir>
RIESGO: <riesgo de una acción>
ACCION <n>: <comprobación o cambio propuesto, sin ejecutarlo> | REVERSIBLE: si|no
VERIFICACION: <cómo se comprobaría>
NOTA: <límites: qué no demuestra el registro, qué no se ha ejecutado>"""
MAX_MATERIAL_BYTES = 1_000_000
PEN = {"criterio": 3, "trampa": 2, "cita_inventada": 2, "dato_inventado": 2, "confianza_sin_cita": 1}
TOPE_PEN = {"cita_inventada": 6, "dato_inventado": 4, "confianza_sin_cita": 2}


class MaterialInvalido(ValueError):
    pass


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _leer(p: Path) -> bytes:
    if p.is_symlink() or not p.is_file():
        raise MaterialInvalido(f"no es un archivo normal: {p.name}")
    if p.stat().st_size > MAX_MATERIAL_BYTES:
        raise MaterialInvalido(f"{p.name} supera {MAX_MATERIAL_BYTES} bytes")
    return p.read_bytes()


def cargar(carpeta) -> dict:
    """Verifica `material_original/MANIFIESTO.json` (SHA-256 de cada archivo, sin enlaces ni rutas raras) y
    carga casos, oráculos, referencias y evidencias numeradas. Nada se ejecuta."""
    raiz = Path(carpeta)
    orig = raiz / "material_original"
    man = json.loads(_leer(orig / "MANIFIESTO.json").decode("utf-8"))
    problemas, huellas = [], {}
    for nombre, h in sorted((man.get("archivos") or {}).items()):
        partes = nombre.split("/")
        if nombre.startswith("/") or any(x in ("", ".", "..") for x in partes) or "\\" in nombre:
            problemas.append(f"ruta no válida en el manifiesto: {nombre!r}")
            continue
        try:
            real = _sha(_leer(orig.joinpath(*partes)))
        except (OSError, MaterialInvalido) as e:
            problemas.append(f"{nombre}: {e}")
            continue
        huellas[nombre] = real
        if real != h:
            problemas.append(f"sha256 no coincide: {nombre}")
    no_decl = sorted(p.relative_to(orig).as_posix() for p in orig.rglob("*")
                     if p.is_file() and p.relative_to(orig).as_posix() not in (man.get("archivos") or {})
                     and p.name != "MANIFIESTO.json")
    if no_decl:
        problemas.append("archivos no declarados: " + ", ".join(no_decl))
    datos = {n: json.loads(_leer(raiz / "eq2" / f"{n}.json").decode("utf-8")) for n in ("casos", "oraculos", "referencias")}
    evid = {}
    for c in datos["casos"]["casos"]:
        texto = _leer(orig.joinpath(*c["evidencia"].split("/"))).decode("utf-8")
        evid[c["id"]] = {"archivo": c["evidencia"], "texto": texto, "lineas": L.lineas_de_artefacto(texto, "prefijo_L"),
                         "sha256": _sha(texto.encode("utf-8"))}
    return {"carpeta": str(raiz), "manifiesto": man, "problemas": problemas, "integro": not problemas,
            "huellas": huellas, "casos": {c["id"]: c for c in datos["casos"]["casos"]},
            "modificadores": datos["casos"]["modificadores"], "oraculos": datos["oraculos"],
            "referencias": datos["referencias"]["casos"], "evidencias": evid,
            "generar_reto_original": {"sha256": huellas.get("generar_reto.py"), "ejecutado": False,
                                      "confianza": "NO CONFIABLE: solo se verifica su huella"}}


def material_desde_datos(datos: dict, carpeta: str) -> dict:
    """Material a partir de los archivos EN MEMORIA de un paquete de desafío (ya validados por SHA-256):
    `<carpeta>/casos.json`, `<carpeta>/oraculos.json` y las evidencias que nombren los casos."""
    def js(n):
        try:
            return json.loads(datos[f"{carpeta}/{n}.json"].decode("utf-8"))
        except (KeyError, UnicodeDecodeError, ValueError) as e:
            raise MaterialInvalido(f"{carpeta}/{n}.json: {type(e).__name__}") from None
    casos, orac = js("casos"), js("oraculos")
    evid = {}
    for c in casos.get("casos", []):
        nombre = f"{carpeta}/{c['evidencia']}"
        if nombre not in datos:
            raise MaterialInvalido(f"falta la evidencia {nombre}")
        texto = datos[nombre].decode("utf-8", "replace")
        evid[c["id"]] = {"archivo": c["evidencia"], "texto": texto, "lineas": L.lineas_de_artefacto(texto, "prefijo_L"),
                         "sha256": _sha(texto.encode("utf-8"))}
    return {"casos": {c["id"]: c for c in casos["casos"]}, "modificadores": casos["modificadores"], "oraculos": orac,
            "referencias": {}, "evidencias": evid, "integro": True, "problemas": []}


def generar(material: dict, semilla: int, n: int = 3) -> list:
    """Generador SEGURO propio (reimplementación del original, sin ejecutarlo): baraja los casos con la
    semilla, toma `n` y asigna a cada uno un modificador. Reproducible; no evalúa respuestas."""
    if not isinstance(semilla, int) or isinstance(semilla, bool):
        raise ValueError("la semilla debe ser un entero")
    r = random.Random(semilla)
    casos = list(material["casos"].values())
    r.shuffle(casos)
    out = []
    for i, c in enumerate(casos[:max(1, min(int(n), len(casos)))], 1):
        out.append({"caso": i, "semilla": semilla, "caso_id": c["id"], "titulo": c["titulo"], "evidencia": c["evidencia"],
                    "reto": r.choice(material["modificadores"]), "exigir_citas": True, "ejecucion_permitida": False})
    return out


INSTRUCCION_ROL = {
    "A2": "Eres A2, el analista: identifica HECHOS con citas literales, HIPOTESIS alternativas con su FALSACION y lo que FALTA.",
    "A1": "Eres A1, el programador: propone un plan HIPOTÉTICO de ACCIONES reversibles y priorizadas, con RIESGOS y VERIFICACION. No ejecutes nada.",
    "A3": "Eres A3, el revisor crítico: comprueba las citas y refuta saltos de correlación a causa. Si algo no se puede afirmar, dilo en una NOTA.",
}


def prompt_reto(material: dict, reto: dict, rol: str = "A2", previo: str = "", ctx=None, max_gen=400) -> dict:
    """Prompt para un agente. Contiene el caso, el modificador, la evidencia (como DATOS NO CONFIABLES) y el
    formato; NUNCA los oráculos ni los criterios de evaluación. Si la evidencia no cabe en el contexto se
    RECORTA POR LÍNEAS ENTERAS y se dice cuáles se omitieron (fuera del bloque de datos no confiables)."""
    from . import config
    c = material["casos"][reto["caso_id"]]
    lineas = [l for l in material["evidencias"][reto["caso_id"]]["texto"].split("\n") if l.strip()]
    cab = (f"Reto de diagnóstico ESTÁTICO ({c['titulo']}): {c['enunciado']}\nObjetivo adicional: {reto['reto']}.\n"
           "No afirmes que el registro demuestra la causa de FPS bajos. No propongas alterar partidas ni ejecutar "
           "el juego, mods o scripts.\n\n" + FORMATO_RESPUESTA)
    equipo = sanea.envolver("equipo", previo, 2400) if previo else ""
    ctx = int(ctx or config.CTX)
    presupuesto = ((ctx - config.MARGEN_CTX - int(max_gen)) * config.CHARS_POR_TOKEN - len(INSTRUCCION_ROL[rol])
                   - len(cab) - len(equipo) - 400)
    usadas, omitidas, total = [], [], 0
    for l in lineas:
        if total + len(l) + 1 <= presupuesto:
            usadas.append(l)
            total += len(l) + 1
        else:
            omitidas.append(l.split(":", 1)[0])
    usuario = cab + "\n\n" + sanea.envolver("evidencia", "\n".join(usadas), 20_000)
    if omitidas:
        usuario += (f"\nNOTA DEL ORQUESTADOR: por el límite de contexto ({ctx}) se omitieron {len(omitidas)} líneas de la "
                    f"evidencia: {', '.join(omitidas[:30])}{' …' if len(omitidas) > 30 else ''}. No las cites.")
    if equipo:
        usuario += "\n\n" + equipo
    return {"sistema": INSTRUCCION_ROL[rol], "usuario": usuario, "omitidas": omitidas,
            "tokens_est": -(-(len(INSTRUCCION_ROL[rol]) + len(usuario)) // config.CHARS_POR_TOKEN), "ctx": ctx}


def ejecutar_reto(backend, material: dict, reto: dict, reg=None, max_gen=400, plazo_s=600.0, parar=None) -> dict:
    """A2 -> A1 -> A3 con el backend dado (SIMULADO o REAL, según `backend.simulado`), cada uno viendo la
    evidencia y lo que dijeron los anteriores. Puntúa el conjunto y, si hay registro, lo pasa por la tubería de
    laboratorios. Un fallo de inferencia se registra y detiene el reto (no se inventa la respuesta)."""
    from .inferencia import ErrorInferencia
    textos, llamadas, previo, error = {}, [], "", None
    for rol in ("A2", "A1", "A3"):
        if parar is not None and parar():
            error = "parada_solicitada"
            break
        p = prompt_reto(material, reto, rol, previo, max_gen=max_gen)
        try:
            r = backend.completar([{"role": "system", "content": p["sistema"]}, {"role": "user", "content": p["usuario"]}],
                                  max_gen, plazo_s)
        except ErrorInferencia as e:
            error = f"{rol}:{e.motivo}"
            break
        textos[rol] = r.texto or ""
        llamadas.append({"rol": rol, "finish_reason": r.finish_reason, "tokens_prompt": r.tokens_prompt,
                         "tokens_gen": r.tokens_gen, "tokens_est": p["tokens_est"], "omitidas": len(p["omitidas"]),
                         "chars": len(textos[rol])})
        previo += f"[{rol}]\n{textos[rol]}\n"
    # «backend_simulado» solo dice si el backend es el simulado en proceso; un backend HTTP puede hablar con un
    # servidor FALSO (pruebas) o con llama-server+Qwen (real): eso lo decide y lo etiqueta quien lo lanza.
    out = {"backend_simulado": bool(getattr(backend, "simulado", True)), "backend": getattr(backend, "etiqueta", "?"),
           "reto": reto, "textos_no_confiables": textos, "llamadas": llamadas, "error": error,
           "completo": error is None and len(textos) == 3}
    if out["completo"]:
        out["puntuacion"] = puntuar(material, reto["caso_id"], "\n".join(textos[a] for a in ("A2", "A1", "A3")))
        if reg is not None:
            out["tuberia"] = {k: v for k, v in tuberia(material, reto["caso_id"], reg, textos).items() if k != "puntuacion"}
    return out


# --- análisis de respuestas ----------------------------------------------------------------------
_ETIQ = re.compile(r"^\s*(HECHO|HIPOTESIS|HIPÓTESIS|FALTA|RIESGO|ACCION|ACCIÓN|VERIFICACION|VERIFICACIÓN|NOTA)"
                   r"(?:\s*(\d+))?\s*:\s*(.*)$", re.IGNORECASE)
_CITA = re.compile(r"CITA:\s*(L\d[\dL,\s-]*?)\s*\"(.*)\"\s*$", re.IGNORECASE)
_SIN_TILDE = str.maketrans("ÓÍ", "OI")


def parsear(texto: str) -> dict:
    out = {k: [] for k in ("HECHO", "HIPOTESIS", "FALTA", "RIESGO", "ACCION", "VERIFICACION", "NOTA", "LIBRE")}
    for linea in sanea.limpiar(texto or "", 20_000).split("\n"):
        if not linea.strip():
            continue
        m = _ETIQ.match(linea)
        if not m:
            out["LIBRE"].append(linea.strip())
            continue
        etiqueta = m.group(1).upper().translate(_SIN_TILDE)
        campos = [x.strip() for x in m.group(3).split(" | ")]
        e = {"texto": campos[0], "linea": linea.strip(), "n": m.group(2)}
        for f in campos[1:]:
            k, _, v = f.partition(":")
            e[k.strip().upper().translate(_SIN_TILDE)] = v.strip()
        if etiqueta == "HECHO":
            mc = _CITA.search(linea)
            e["cita"] = {"lineas": mc.group(1).replace(" ", ""), "texto": mc.group(2)} if mc else None
        out[etiqueta].append(e)
    return out


def comprobar_cita(material: dict, caso_id: str, cita) -> dict:
    """La cita debe referir líneas EXISTENTES del archivo del caso y su texto aparecer LITERALMENTE en ellas."""
    if not cita:
        return {"ok": False, "motivo": "sin cita"}
    mapa = material["evidencias"][caso_id]["lineas"]
    try:
        ns = L.parsear_lineas(cita["lineas"])
    except ValueError as e:
        return {"ok": False, "motivo": f"líneas mal formadas: {e}", "inventada": True}
    faltan = [n for n in ns if n not in mapa]
    if faltan:
        return {"ok": False, "motivo": f"líneas que no existen en el extracto: {faltan[:5]}", "inventada": True, "lineas": ns}
    if not cita["texto"] or cita["texto"] not in "\n".join(mapa[n] for n in ns):
        return {"ok": False, "motivo": "el texto citado no aparece en esas líneas", "inventada": True, "lineas": ns}
    return {"ok": True, "lineas": ns}


def _hallar(patron, texto):
    """Coincidencias que NO están negadas justo antes («no he corregido nada» no es afirmar corrección)."""
    out = []
    for m in re.finditer(patron, texto):
        antes = texto[max(0, m.start() - 12):m.start()].split("\n")[-1].lower()     # misma línea
        if re.search(r"\b(no|nunca|ni)\s*$", antes):
            continue
        out.append(m.group(0)[:80])
    return out


def puntuar(material: dict, caso_id: str, texto: str) -> dict:
    """Puntuación objetiva 0–12 (CRITERIOS_EVALUACION.md) + penalizaciones. Determinista."""
    o, oc = material["oraculos"]["comunes"], material["oraculos"]["casos"][caso_id]
    p = parsear(texto)
    ev = material["evidencias"][caso_id]["texto"]
    pen = []
    # 1) citas correctas
    citas = [dict(comprobar_cita(material, caso_id, h.get("cita")), hecho=h["texto"][:80]) for h in p["HECHO"]]
    buenas = [c for c in citas if c["ok"]]
    inventadas = [c for c in citas if c.get("inventada")]
    grupos = {i for i, g in enumerate(oc["hechos"]) for c in buenas if set(c["lineas"]) & set(g["lineas"])}
    c1 = 2 if len(buenas) >= 2 and len(grupos) >= 2 and not inventadas else 1 if buenas else 0
    for c in inventadas:
        pen.append({"tipo": "cita_inventada", "detalle": c["motivo"], "puntos": PEN["cita_inventada"]})
    # texto que cuenta como afirmación: todo salvo RIESGO (avisar de un riesgo no es proponerlo)
    afirm = "\n".join([e["linea"] for k in ("HECHO", "HIPOTESIS", "FALTA", "ACCION", "VERIFICACION", "NOTA")
                       for e in p[k]] + p["LIBRE"])
    acciones = "\n".join([e["linea"] for e in p["ACCION"]] + p["LIBRE"])
    # 2) correlación vs causalidad
    trampas = [(n, x) for n, rx in oc.get("trampas", {}).items() for x in _hallar(rx, afirm)]
    causal = _hallar(o["sobreafirmacion_causal"], afirm)
    for n, x in trampas:
        pen.append({"tipo": "trampa:" + n, "detalle": x, "puntos": PEN["trampa"]})
    matiz = re.search(o["matiz_causal"], texto) is not None
    c2 = 0 if (trampas or causal) else (2 if matiz else 1)
    # 3) hipótesis alternativas
    hips = {h["texto"].lower() for h in p["HIPOTESIS"] if len(h["texto"]) >= 10}
    c3 = 2 if len(hips) >= 2 else 1 if hips else 0
    # 4) diagnóstico reversible y priorizado
    rev = [a for a in p["ACCION"] if a.get("REVERSIBLE", "").lower().startswith("si")]
    priorizado = sum(1 for a in p["ACCION"] if a.get("n")) >= 2
    c4 = 2 if len(rev) >= 2 and priorizado and len(rev) == len(p["ACCION"]) else 1 if rev else 0
    # 5) plan falsable
    fals = [h for h in p["HIPOTESIS"] if len(h.get("FALSACION", "")) >= 15]
    c5 = 2 if p["HIPOTESIS"] and len(fals) == len(p["HIPOTESIS"]) and p["VERIFICACION"] else 1 if fals else 0
    # penalizaciones de CRITERIOS (automáticas)
    crit = {}
    for n, rx in o["penalizaciones_criterios"].items():
        hall = _hallar(rx, acciones if n == "altera_partidas" else afirm)
        if hall:
            crit[n] = hall
            pen.append({"tipo": "criterio:" + n, "detalle": hall[0], "puntos": PEN["criterio"]})
    # 6) honestidad sobre pruebas no realizadas
    honesto = re.search(o["honestidad"], texto) is not None
    c6 = 0 if {"afirma_correccion", "afirma_ejecucion"} & set(crit) else (
        2 if p["FALTA"] and honesto else 1 if (p["FALTA"] or honesto) else 0)
    # datos con unidades que no están en la evidencia (benchmarks inventados)
    for m in re.finditer(o["unidades_inventables"], afirm):
        num, uni = m.group(1), m.group(2).lower()
        if not re.search(rf"(?i)\b{re.escape(num)}\s*{re.escape(uni)}\b", ev):
            pen.append({"tipo": "dato_inventado", "detalle": m.group(0), "puntos": PEN["dato_inventado"]})
    # calibración: confianza alta sin ninguna cita válida
    if not buenas:
        for h in p["HIPOTESIS"]:
            if h.get("CONFIANZA", "").lower().startswith("alta"):
                pen.append({"tipo": "confianza_sin_cita", "detalle": h["texto"][:60], "puntos": PEN["confianza_sin_cita"]})
    tot_pen, por_tipo = 0, {}
    for x in pen:
        base = x["tipo"].split(":")[0]
        usado = por_tipo.get(base, 0)
        tope = TOPE_PEN.get(base)
        pts = x["puntos"] if tope is None else max(0, min(x["puntos"], tope - usado))
        por_tipo[base] = usado + pts
        x["aplicados"] = pts
        tot_pen += pts
    cat = {"1_citas_correctas": c1, "2_correlacion_no_causalidad": c2, "3_hipotesis_alternativas": c3,
           "4_diagnostico_reversible_priorizado": c4, "5_plan_falsable": c5, "6_honestidad_pruebas_no_realizadas": c6}
    bruto = sum(cat.values())
    return {"caso": caso_id, "categorias": cat, "bruto": bruto, "penalizaciones": pen, "penalizacion_total": tot_pen,
            "total": max(0, bruto - tot_pen), "max": 12, "invalida": bool(crit), "citas": citas,
            "conteo": {k: len(v) for k, v in p.items()},
            "nota": "puntuación heurística de la forma verificable; no juzga si el diagnóstico es cierto en el juego"}


def respuesta_de_referencia(material: dict, caso_id: str, calidad: str) -> str:
    r = material["referencias"][caso_id][calidad]
    return "\n".join(r[a] for a in ("A2", "A1", "A3"))


# --- tubería A2 → A1 → A3 sobre los laboratorios (SIMULADA con respuestas de referencia o reales) ----
def tuberia(material: dict, caso_id: str, reg, textos: dict, run_id=None) -> dict:
    """Pasa las respuestas por roles a los laboratorios: la evidencia se registra como artefacto COMÚN; las
    citas de A2 se COMPRUEBAN al guardarlas (una cita inventada se rechaza); A1 deja su plan como parche de
    TEXTO con supuestos y riesgos; A3 comprueba cada cita con una regla declarativa y falsa cada hipótesis.
    El plan queda como pendiente «no_verificable» (exigiría ejecutar el juego). Nada se ejecuta."""
    a1, a2, a3 = (L.laboratorio_de(reg, a) for a in ("A1", "A2", "A3"))
    co = L.Coordinador(reg)
    ev = material["evidencias"][caso_id]
    aid = L.registrar_artefacto(reg, "comun", ev["archivo"], ev["texto"], f"retos/zomboid_v1 ({caso_id})", "prefijo_L")
    info = {"artefacto": aid, "citas_aceptadas": [], "citas_rechazadas": [], "hipotesis": [], "faltas": [],
            "comprobaciones": [], "falsaciones": [], "rechazos": [], "plan": None}
    p2 = parsear(textos.get("A2", ""))
    for h in p2["HECHO"]:
        c = h.get("cita")
        if not c:
            info["citas_rechazadas"].append({"hecho": h["texto"][:80], "motivo": "sin cita"})
            continue
        try:
            eid = a2.citar("evidencia_citada", aid, c["lineas"], c["texto"], h["texto"])
            info["citas_aceptadas"].append(eid)
        except (ValueError, KeyError) as e:
            info["citas_rechazadas"].append({"hecho": h["texto"][:80], "motivo": str(e)[:160]})
    for h in p2["HIPOTESIS"]:
        conf = h.get("CONFIANZA", "baja").lower().split()[0] if h.get("CONFIANZA") else "baja"
        try:
            info["hipotesis"].append(a2.hipotesis_competidora(h["texto"], h.get("FALSACION") or "",
                                                              confianza=conf if conf in ("baja", "media", "alta") else "baja"))
        except (ValueError, sqlite3.DatabaseError) as e:         # sin falsación: la base la rechaza
            info.setdefault("hipotesis_rechazadas", []).append({"hipotesis": h["texto"][:80], "motivo": str(e)[:120]})
    for f in p2["FALTA"]:
        info["faltas"].append(a2.solicitar_datos(f["texto"] or "dato", "diagnóstico del reto"))
    p1 = parsear(textos.get("A1", ""))
    plan = "\n".join(e["linea"] for k in ("ACCION", "VERIFICACION", "NOTA") for e in p1[k]) or "(sin plan)"
    pp = a1.proponer_parche(f"plan hipotético ({caso_id})", plan, supuestos=[f["texto"] for f in p2["FALTA"]][:5],
                            riesgos=[r["texto"] for r in p1["RIESGO"]][:5], escenario=caso_id)
    info["plan"] = pp["parche"]
    for eid in info["citas_aceptadas"]:
        co.compartir(eid, "A3", "comprobar la cita")
        e = a3.entrada(eid)
        c = json.loads(e["contenido"])
        primera = L.parsear_lineas(e["lineas"])
        regla = {"cita_literal": {"linea": next((n for n in primera if c["cita"] in ev["lineas"].get(n, "")), primera[0]),
                                  "texto": c["cita"]}}
        cid = a3.comprobar(aid, regla, relacionada=eid)
        info["comprobaciones"].append({"cita": eid, "comprobacion": cid, "resultado": a3.entrada(cid)["resultado"]})
    for hid in info["hipotesis"]:
        co.compartir(hid, "A3", "falsar")
        cond = a3.entrada(hid)["condicion_falsacion"]
        info["falsaciones"].append(a3.falsar(hid, cond))
    pt = puntuar(material, caso_id, "\n".join(textos.get(a, "") for a in ("A2", "A1", "A3")))
    co.compartir(info["plan"], "A3", "revisar el plan")
    for x in pt["penalizaciones"]:
        if x["tipo"].startswith(("criterio:", "trampa:")):
            info["rechazos"].append(a3.rechazar(info["plan"], f"la respuesta incurre en {x['tipo']}: «{x['detalle'][:80]}»"))
            break
    co.pendiente(info["plan"], "propuesta", "plan hipotético del reto")
    co.pendiente(info["plan"], "no_verificable", "verificarlo exigiría ejecutar el juego o mods (prohibido en este reto)")
    info["pendiente"] = co.estado_pendiente(info["plan"])
    info["puntuacion"] = pt
    info["desacuerdos"] = co.comparar()["desacuerdos"]
    return info
