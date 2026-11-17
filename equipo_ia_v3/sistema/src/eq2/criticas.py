"""V2-E.5: evaluación DETERMINISTA y auditable de las críticas de los agentes.

Módulo puro: sin E/S, sin red, sin ejecutar nada. El texto de los agentes es NO CONFIABLE.

Una objeción («OBJECION: <qué falla> | EVIDENCIA: <…>») se clasifica SOLO por lo que se puede
comprobar sin ejecutar código:
  * fundamentada        la evidencia CITA un fragmento (`…`, "…" o el propio texto) que aparece
                        literalmente en la propuesta (o en el enunciado: requisito citado).
  * cita_no_encontrada  la evidencia cita un fragmento que NO está en la propuesta ni en el
                        enunciado: probable CRÍTICA FALSA (afirma algo del código que no existe).
  * linea_inexistente   cita «línea N» y la propuesta no tiene esa línea: referencia inválida.
  * no_verificable      describe un caso o comportamiento («ordenar([]) debe dar []», «línea 3»)
                        que solo se comprobaría ejecutando: queda como INCERTIDUMBRE.
  * sin_evidencia       no da evidencia: afirmación sin respaldo.
Nada de esto prueba que la objeción sea cierta o falsa en el comportamiento: solo si su
referencia es comprobable en el texto.

Contradicciones detectadas (entre la revisión, la réplica y los votos):
  * la revisión dice a la vez «SIN OBJECIONES» y plantea objeciones;
  * la réplica ACEPTA una objeción fundamentada pero el fragmento citado sigue en la propuesta final;
  * un agente vota «aprobar» con una objeción fundamentada PENDIENTE (el fragmento sigue ahí);
  * A3 (el revisor) aprueba sin que sus objeciones fundamentadas se hayan resuelto;
  * votos válidos opuestos (aprobar frente a rechazar).
El consenso NUNCA se presenta como demostración de corrección: `consenso_no_es_correccion`.
Las respuestas de la réplica se asocian a las objeciones POR ORDEN (n-ésima respuesta, n-ésima
objeción): es una convención explícita y documentada, no una inferencia.

V2-E.5-r2 — formatos inesperados (tolerancia ACOTADA y registrada, sin heurísticas semánticas):
  * «OBJECIÓN» con tilde, «Objection» (inglés), negritas Markdown (**OBJECION 1:**), viñetas «- », «#»;
  * evidencia separada por «|», «;», «—», «(evidencia: …)» o en la LÍNEA SIGUIENTE («EVIDENCIA: …»);
  * «no hay objeciones», «ninguna objeción», «no objections» equivalen a «SIN OBJECIONES».
  Cada revisión informa `formato_revision`: estandar | tolerado | no_reconocido | vacia. Una revisión
  con texto pero sin objeciones ni «sin objeciones» es INCERTIDUMBRE («revision:formato_no_reconocido»):
  nunca se interpreta como aprobación.
"""
from __future__ import annotations

import re
import unicodedata

ESTADOS = ("fundamentada", "cita_no_encontrada", "linea_inexistente", "no_verificable", "sin_evidencia")
NO_FUNDAMENTADAS = ("cita_no_encontrada", "linea_inexistente", "sin_evidencia")
MIN_CITA = 4                       # caracteres mínimos de una cita comprobable
MAX_OBJECIONES = 20                # se analizan como mucho estas (el resto se cuenta como omitido)

_OBJ = re.compile(r"^\s*[-*]?\s*objecion(?:\s+(\d{1,2}))?\s*:\s*(.*)$", re.IGNORECASE | re.MULTILINE)
# V2-E.5-r2: variantes toleradas (una línea cada vez; ver la cabecera del módulo).
_OBJ_TOL = re.compile(r"^\s*(?:[-*#>]+\s*)?(?:\*\*|__)?\s*objec(?:i[oó]n|tion)(?:\s*#?\s*(\d{1,2}))?\s*(?:\*\*|__)?"
                      r"\s*:\s*(?:\*\*|__)?\s*(.*)$", re.IGNORECASE)
_EVID_LINEA = re.compile(r"^\s*(?:[-*>]+\s*)?(?:\*\*|__)?\s*(?:evidencia|evidence)\s*(?:\*\*|__)?\s*:\s*(?:\*\*|__)?"
                         r"\s*(.*)$", re.IGNORECASE)
_SIN_OBJ = re.compile(r"^\s*(?:[-*#>]+\s*)?(?:\*\*|__)?\s*(?:sin objeciones|no hay objeciones|ninguna objeci[oó]n|"
                      r"no objections)\b", re.IGNORECASE | re.MULTILINE)
_EVID = re.compile(r"\|\s*evidencia\s*:\s*(.*)$", re.IGNORECASE)
_EVID_TOL = re.compile(r"(?:\||;|—|–|\()\s*(?:\*\*|__)?\s*(?:evidencia|evidence)\s*(?:\*\*|__)?\s*:\s*(.*)$",
                       re.IGNORECASE)
_RESP = re.compile(r"^\s*[-*]?\s*(aceptada|rebatida)\s*:\s*(\S.*)$", re.IGNORECASE | re.MULTILINE)
_RETIRADA = re.compile(r"^\s*[-*]?\s*retirada\s*:?\s*(\d{1,2})\b", re.IGNORECASE | re.MULTILINE)
_CITAS = re.compile(r"`([^`\n]{%d,200})`|\"([^\"\n]{%d,200})\"|'([^'\n]{%d,200})'" % ((MIN_CITA,) * 3))
_LINEA = re.compile(r"\bl[ií]nea\s+(\d{1,4})\b", re.IGNORECASE)
_CODIGO = re.compile(r"[()\[\]{}=.:_]")


def _norm(t: str) -> str:
    """Para comparar citas: NFKC, minúsculas y espacios colapsados (incluidos los saltos de línea)."""
    t = unicodedata.normalize("NFKC", t if isinstance(t, str) else "").lower()
    return re.sub(r"\s+", " ", t).strip()


def _lineas_de_codigo(propuesta: str) -> int:
    bloques = re.findall(r"```[^\n]*\n(.*?)```", propuesta or "", re.S)
    texto = "\n".join(bloques) if bloques else (propuesta or "")
    return len(texto.split("\n"))


def clasificar(objecion: str, evidencia: str | None, propuesta: str, enunciado: str = "") -> dict:
    """Clasifica UNA objeción. Devuelve {estado, tipo_referencia, citas, citas_encontradas, motivo}."""
    out = {"estado": "sin_evidencia", "tipo_referencia": None, "citas": [], "citas_encontradas": [],
           "motivo": "la objeción no aporta evidencia"}
    ev = (evidencia or "").strip()
    if len(ev) < 2:
        return out
    p, e = _norm(propuesta), _norm(enunciado)
    citas = [next(g for g in m if g) for m in _CITAS.findall(ev)]
    if citas:
        out["citas"] = citas[:5]
        dentro = [c for c in citas if _norm(c) in p or (e and _norm(c) in e)]
        out["citas_encontradas"] = dentro
        if dentro:
            req = all(_norm(c) not in p for c in dentro)
            out.update(estado="fundamentada", tipo_referencia="requisito" if req else "codigo",
                       motivo="la cita aparece literalmente en " + ("el enunciado" if req else "la propuesta"))
        else:
            out.update(estado="cita_no_encontrada", tipo_referencia="cita",
                       motivo="lo citado NO aparece en la propuesta ni en el enunciado")
        return out
    m = _LINEA.search(ev)
    if m:
        n, total = int(m.group(1)), _lineas_de_codigo(propuesta)
        if n < 1 or n > total:
            out.update(estado="linea_inexistente", tipo_referencia="linea",
                       motivo=f"la propuesta tiene {total} líneas de código; no existe la línea {n}")
        else:
            out.update(estado="no_verificable", tipo_referencia="linea",
                       motivo=f"la línea {n} existe, pero lo que se afirma de ella no se comprueba sin ejecutar")
        return out
    if len(_norm(ev)) >= MIN_CITA + 2 and _CODIGO.search(ev) and _norm(ev) in p:
        out.update(estado="fundamentada", tipo_referencia="codigo", citas=[ev[:200]], citas_encontradas=[ev[:200]],
                   motivo="el fragmento de código citado aparece literalmente en la propuesta")
        return out
    if e and len(_norm(ev)) >= 8 and _norm(ev) in e:
        out.update(estado="fundamentada", tipo_referencia="requisito", citas=[ev[:200]], citas_encontradas=[ev[:200]],
                   motivo="la evidencia reproduce literalmente un requisito del enunciado")
        return out
    out.update(estado="no_verificable", tipo_referencia="caso",
               motivo="describe un caso o comportamiento que solo se comprobaría ejecutando")
    return out


def _limpiar(s: str) -> str:
    return s.replace("**", "").replace("__", "").strip()


def _parsear(revision: str) -> tuple:
    """V2-E.5-r2: ([(numero|None, objecion, evidencia|None)], líneas consumidas, toleradas: bool)."""
    lineas = (revision or "").split("\n")
    out, usadas, tolerado = [], set(), False
    for i, linea in enumerate(lineas):
        if i in usadas:
            continue
        m = _OBJ.match(linea)
        estandar = m is not None
        if m is None:
            m = _OBJ_TOL.match(linea)
            if m is None:
                continue
        num, cuerpo = m.group(1), m.group(2)
        usadas.add(i)
        e = _EVID.search(cuerpo) if estandar else None
        if e is None:
            e = _EVID_TOL.search(cuerpo)
            tolerado = tolerado or (e is not None) or not estandar
        else:
            tolerado = tolerado or not estandar
        if e is not None:
            texto, ev = cuerpo[:e.start()], e.group(1).strip()
            if cuerpo[e.start()] == "(" and ev.endswith(")"):
                ev = ev[:-1]
        else:
            texto, ev = cuerpo, None
            if i + 1 < len(lineas) and not _OBJ_TOL.match(lineas[i + 1]):
                s = _EVID_LINEA.match(lineas[i + 1])
                if s is not None:
                    ev, tolerado = s.group(1), True
                    usadas.add(i + 1)
        ev = _limpiar(ev)[:300] if ev is not None else None
        out.append((int(num) if num else None, _limpiar(texto)[:300], ev or None))
    return out, usadas, tolerado


def objeciones_de(revision: str) -> list:
    """[(numero|None, objecion, evidencia|None)] en orden de aparición."""
    return _parsear(revision)[0]


def formato_revision(revision: str) -> str:
    """V2-E.5-r2: estandar | tolerado | no_reconocido | vacia."""
    if not (revision or "").strip():
        return "vacia"
    objs, _u, tol = _parsear(revision)
    if objs:
        return "tolerado" if tol else "estandar"
    if _SIN_OBJ.search(revision):
        return "estandar"
    return "no_reconocido"


def analizar_objeciones(revision: str, propuesta: str, enunciado: str = "") -> list:
    res = []
    for i, (_n, obj, ev) in enumerate(objeciones_de(revision)[:MAX_OBJECIONES], 1):
        c = clasificar(obj, ev, propuesta, enunciado)
        res.append(dict(c, n=i, objecion=obj, evidencia=ev))
    return res


def evaluar_deliberacion(hist: dict, votos_eval: dict, enunciado: str = "") -> dict:
    """Evaluación completa de una deliberación (análisis → propuesta → revisión → réplica → votos).

    hist: textos por fase. votos_eval: {agente: evaluación del voto (estado, postura, razon)}.
    Devuelve objeciones clasificadas, contradicciones, incertidumbre y problemas no resueltos.
    """
    propuesta, revision = hist.get("propuesta") or "", hist.get("revision") or ""
    final = hist.get("replica") or propuesta
    objs = analizar_objeciones(revision, propuesta, enunciado)
    resp = [k.lower() for k, _t in _RESP.findall(hist.get("replica") or "")]
    pf = _norm(final)
    for o in objs:
        o["respuesta"] = resp[o["n"] - 1] if o["n"] - 1 < len(resp) else None
        if o["estado"] == "fundamentada" and o["tipo_referencia"] == "codigo":
            sigue = any(_norm(c) in pf for c in o["citas_encontradas"])
            o["resolucion"] = ("pendiente" if sigue and o["respuesta"] != "rebatida" else
                               "rebatida_sin_cambio" if sigue else "resuelta_en_texto")
        elif o["estado"] == "fundamentada":
            # requisito citado: si A1 lo REBATE, el requisito sigue en el enunciado (V2-E.5-r2: se trata
            # como «rebatida sin cambio»: incertidumbre y aviso si A3 aprueba igualmente).
            o["resolucion"] = ("requisito_rebatido" if o["respuesta"] == "rebatida" else
                               o["respuesta"] or "sin_respuesta")
        else:
            o["resolucion"] = "no_aplicable"
    contradicciones = []
    if objs and _SIN_OBJ.search(revision):
        contradicciones.append("revision_sin_objeciones_y_con_objeciones")
    for o in objs:
        if o["estado"] == "fundamentada" and o["respuesta"] == "aceptada" and o["resolucion"] == "pendiente":
            contradicciones.append(f"replica_acepta_pero_no_aplica:objecion_{o['n']}")
    pendientes = [o for o in objs if o["resolucion"] == "pendiente"]
    validos = {ag: v for ag, v in (votos_eval or {}).items() if (v or {}).get("estado") == "valido"}
    for ag, v in sorted(validos.items()):
        if v.get("postura") == "aprobar" and pendientes:
            contradicciones.append(f"{ag}_aprueba_con_objecion_fundamentada_pendiente")
    a3 = validos.get("A3") or {}
    if a3.get("postura") in ("aprobar", "aprobar_con_cambios") and any(
            o["resolucion"] in ("pendiente", "rebatida_sin_cambio", "requisito_rebatido") for o in objs):
        contradicciones.append("A3_aprueba_sin_resolver_sus_objeciones_fundamentadas")
    posturas = {v.get("postura") for v in validos.values()}
    if "aprobar" in posturas and "rechazar" in posturas:
        contradicciones.append("votos_opuestos_aprobar_y_rechazar")
    incertidumbre = [f"objecion_{o['n']}:{o['estado']}" for o in objs if o["estado"] != "fundamentada"]
    incertidumbre += [f"objecion_{o['n']}:{o['resolucion']}" for o in objs
                      if o["resolucion"] in ("rebatida_sin_cambio", "requisito_rebatido")]
    if len(objeciones_de(revision)) > MAX_OBJECIONES:
        incertidumbre.append(f"objeciones_no_analizadas:{len(objeciones_de(revision)) - MAX_OBJECIONES}")
    fmt = formato_revision(revision)                                            # V2-E.5-r2
    if fmt in ("no_reconocido", "vacia"):
        incertidumbre.append("revision:formato_" + fmt)
    no_resueltos = [f"objecion_{o['n']}: {o['objecion'][:120]}" for o in pendientes]
    cuenta = {e: sum(1 for o in objs if o["estado"] == e) for e in ESTADOS}
    categorias = categorizar(objs, contradicciones)                              # V2-E.5-r3
    return {"objeciones": objs, "conteo": cuenta, "contradicciones": contradicciones, "formato_revision": fmt,
            "categorias": categorias, "nota_categorias": NOTA_CATEGORIAS,
            "incertidumbre": incertidumbre, "problemas_no_resueltos": no_resueltos,
            "posibles_criticas_falsas": [o["n"] for o in objs if o["estado"] in ("cita_no_encontrada",
                                                                                 "linea_inexistente")],
            "consenso_no_es_correccion": True,
            "nota": ("evaluación determinista de referencias en el texto: no prueba que una objeción sea "
                     "cierta ni que la propuesta funcione; el consenso de los agentes no es una demostración")}


# --- V2-E.5-r3: categorías (error demostrado, sospecha, sin evidencia, contradicción) -----------
CATEGORIAS = ("error_demostrado", "contradiccion", "sospecha_razonable", "sin_evidencia")
NOTA_CATEGORIAS = ("«error_demostrado» exige que una herramienta DETERMINISTA (análisis estático; en el futuro, "
                   "pruebas reales) señale el mismo fragmento citado; en una deliberación sin ejecución no hay "
                   "errores demostrados. «sospecha_razonable» = referencia existente o caso concreto, sin "
                   "demostración. Una cita existente NO demuestra la crítica.")


def _lineas_senaladas(archivos: dict, err: dict) -> list:
    """Líneas de código que una herramienta determinista señaló con un error (texto de la línea)."""
    cont = (archivos or {}).get(err.get("archivo") or "")
    if not isinstance(cont, str):
        return []
    lineas = cont.split("\n")
    n = err.get("linea")
    if isinstance(n, int) and not isinstance(n, bool) and 1 <= n <= len(lineas):
        return [lineas[n - 1]]
    mod, nombre = err.get("modulo"), err.get("nombre")
    if isinstance(mod, str) and mod:
        return [l for l in lineas if re.search(r"\b(?:from|import)\s+" + re.escape(mod) + r"\b", l)
                and (not isinstance(nombre, str) or re.search(r"\b" + re.escape(nombre) + r"\b", l))]
    return []


def demostraciones_estaticas(objeciones: list, archivos: dict, errores: list) -> dict:
    """{n: descripción} de las objeciones cuya cita aparece en una línea que el ANÁLISIS ESTÁTICO marcó
    con un error (coincidencia independiente del texto del revisor)."""
    out = {}
    for o in objeciones or []:
        if o.get("estado") != "fundamentada" or o.get("tipo_referencia") != "codigo":
            continue
        for err in errores or []:
            if not isinstance(err, dict):
                continue
            lineas = [_norm(l) for l in _lineas_senaladas(archivos, err)]
            if any(len(_norm(c)) >= MIN_CITA and _norm(c) in l for c in o.get("citas_encontradas") or []
                   for l in lineas):
                out[o["n"]] = f"analisis_estatico:{err.get('tipo')}:{err.get('archivo')}"
                break
    return out


def categorizar(objeciones: list, contradicciones=(), demostraciones=None) -> dict:
    """Asigna UNA categoría por objeción (prioridad: error_demostrado > contradiccion >
    sospecha_razonable > sin_evidencia) y devuelve también el recuento."""
    demostraciones = demostraciones or {}
    contr = set(contradicciones or ())
    revision_contradictoria = "revision_sin_objeciones_y_con_objeciones" in contr
    for o in objeciones:
        n = o["n"]
        if n in demostraciones:
            o["categoria"], o["motivo_categoria"] = "error_demostrado", demostraciones[n]
        elif revision_contradictoria or f"replica_acepta_pero_no_aplica:objecion_{n}" in contr:
            o["categoria"], o["motivo_categoria"] = "contradiccion", "la revisión o la réplica se contradicen"
        elif o["estado"] in ("fundamentada", "no_verificable"):
            o["categoria"], o["motivo_categoria"] = "sospecha_razonable", "referencia comprobable sin demostración"
        else:
            o["categoria"], o["motivo_categoria"] = "sin_evidencia", o["estado"]
    return {c: sum(1 for o in objeciones if o.get("categoria") == c) for c in CATEGORIAS}


# --- aclaración (opcional, UNA como máximo por tarea) -----------------------------------------
def objeciones_a_aclarar(revision: str, propuesta: str, enunciado: str = "") -> list:
    """Objeciones cuya evidencia falta o no se encuentra (las que justifican pedir una referencia)."""
    return [o for o in analizar_objeciones(revision, propuesta, enunciado) if o["estado"] in NO_FUNDAMENTADAS]


def texto_para_aclarar(pend: list) -> str:
    return "\n".join(f"OBJECION {o['n']}: {o['objecion']}" + (f" | EVIDENCIA: {o['evidencia']}" if o["evidencia"] else "")
                     for o in pend)


def fusionar_aclaracion(revision: str, aclaracion: str, pend_ns) -> tuple:
    """Revisión nueva (formato estándar) con las objeciones aclaradas o RETIRADAS.

    Solo cuentan las respuestas a objeciones pedidas (`pend_ns`); objeciones nuevas se ignoran.
    Devuelve (texto, {retiradas, aclaradas, ignoradas})."""
    pend_ns = set(pend_ns)
    retiradas = {int(n) for n in _RETIRADA.findall(aclaracion or "") if int(n) in pend_ns}
    nuevas = {}
    ignoradas = 0
    for num, obj, ev in objeciones_de(aclaracion):
        if num in pend_ns and num not in retiradas and num not in nuevas:
            nuevas[num] = (obj, ev)
        else:
            ignoradas += 1
    lineas = []
    objs_rev, usadas, _tol = _parsear(revision)
    for i, (_n, obj, ev) in enumerate(objs_rev, 1):
        if i in retiradas:
            continue
        o, e = nuevas.get(i, (obj, ev))
        lineas.append(f"OBJECION: {o or obj}" + (f" | EVIDENCIA: {e}" if e else ""))
    otras = [l for k, l in enumerate((revision or "").split("\n")) if l.strip() and k not in usadas]
    texto = "\n".join(lineas + otras) or "SIN OBJECIONES: todas las objeciones se retiraron en la aclaración"
    return texto, {"retiradas": sorted(retiradas), "aclaradas": sorted(nuevas), "ignoradas": ignoradas}


# --- revisiones sucesivas del motor (A3 revisa cada versión) -------------------------------------
def contradicciones_entre_versiones(revisiones: list) -> list:
    """`revisiones`: [{version, texto, archivos}] en orden. Marca una contradicción si A3 señaló con
    cita una objeción FUNDAMENTADA en la versión n, el fragmento sigue en la versión n+1 y en esa
    versión A3 no la repite (dice «sin objeciones» o no cita ese fragmento)."""
    out = []
    for a, b in zip(revisiones, revisiones[1:]):
        objs = [o for o in analizar_objeciones(a.get("texto") or "", a.get("archivos") or "")
                if o["estado"] == "fundamentada" and o["tipo_referencia"] == "codigo"]
        textob, archb = _norm(b.get("texto") or ""), _norm(b.get("archivos") or "")
        for o in objs:
            for c in o["citas_encontradas"]:
                if _norm(c) in archb and _norm(c) not in textob:
                    out.append(f"v{b.get('version')}_omite_objecion_fundamentada_de_v{a.get('version')}:"
                               f"{c[:40]}")
                    break
    return out
