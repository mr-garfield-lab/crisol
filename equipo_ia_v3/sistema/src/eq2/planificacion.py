"""V2-F: PLANIFICACIÓN estructurada y revisable (módulo puro: sin E/S, sin modelo, sin ejecutar nada).

En V2-E.7 A2 escribía ARCHIVOS + CRITERIO y el motor ignoraba sus líneas FALTA. Aquí el plan es un objeto que el
CONTROLADOR comprueba:

  SUBTAREA: S1 | <qué hay que hacer> | CRITERIOS: C1,C2 | DEPENDE: - | PRIORIDAD: alta|media|baja
  CRITERIO: C1 | <qué se comprueba> | PRUEBA: test_<nombre>        (el formato de V2-E, sin cambios)
  FALTA: <pregunta concreta> [| SUPUESTO: <qué se asume si no hay respuesta>]
  SUPUESTO: <supuesto explícito>

Garantías deterministas:
  * descomposición: subtareas con dependencias (grafo sin ciclos), prioridad y criterios asignados;
  * orden de trabajo: orden topológico, desempate por prioridad y después por identificador;
  * cobertura: qué subtareas no tienen ningún criterio verificable (aviso) y qué criterios no son de ninguna;
  * información: una FALTA sin SUPUESTO es BLOQUEANTE; con la política «preguntar» el motor se detiene y
    entrega las preguntas al usuario en lugar de programar sobre una suposición oculta;
  * revisión del plan con evidencia: qué criterios cambian, se añaden o se RETIRAN, y si las pruebas nuevas
    son más débiles que las anteriores (menos aserciones). Un criterio retirado o una prueba debilitada nunca
    se aceptan en silencio: impiden la conclusión «verificado» hasta que el usuario lo revise.
Si A2 no escribe SUBTAREA (un modelo pequeño puede no hacerlo), el plan tiene una subtarea IMPLÍCITA S0 con
todos los criterios: el comportamiento es entonces el de V2-E.7.
"""
from __future__ import annotations

import ast
import re
from dataclasses import asdict, dataclass, field

from . import sanea
from .motor import MAX_CRITERIOS, archivos_del_plan, criterios_de

MAX_SUBTAREAS = 6
PRIORIDADES = {"alta": 0, "media": 1, "baja": 2}
POLITICAS_FALTA = ("preguntar", "asumir_y_marcar")
_SUB = re.compile(r"^[ \t]*[-*]?[ \t]*SUBTAREA[ \t]*:[ \t]*(.+)$", re.IGNORECASE | re.MULTILINE)
_FALTA = re.compile(r"^[ \t]*[-*]?[ \t]*FALTA[ \t]*:[ \t]*(.+)$", re.IGNORECASE | re.MULTILINE)
_SUPUESTO = re.compile(r"^[ \t]*[-*]?[ \t]*SUPUESTO[ \t]*:[ \t]*(.+)$", re.IGNORECASE | re.MULTILINE)
_RETIRO = re.compile(r"^[ \t]*[-*]?[ \t]*RETIRO[ \t]*:[ \t]*([A-Za-z0-9_-]{1,20})[ \t]*\|[ \t]*(\S.*)$",
                     re.IGNORECASE | re.MULTILINE)
_ID_SUB = re.compile(r"S[0-9]{1,2}", re.IGNORECASE)
_ID_CRIT = re.compile(r"[A-Za-z0-9_-]{1,20}")


@dataclass
class Plan:
    subtareas: list = field(default_factory=list)      # {id, descripcion, criterios, depende, prioridad}
    criterios: list = field(default_factory=list)      # {id, descripcion, prueba} (formato de V2-E)
    archivos: list = field(default_factory=list)
    faltas: list = field(default_factory=list)         # {texto, supuesto}
    supuestos: list = field(default_factory=list)
    problemas: list = field(default_factory=list)
    avisos: list = field(default_factory=list)
    implicita: bool = False
    orden: list = field(default_factory=list)

    def a_dict(self) -> dict:
        return asdict(self)

    def subtarea_de(self, criterio_id) -> str | None:
        for s in self.subtareas:
            if criterio_id in s["criterios"]:
                return s["id"]
        return None


def _campos(resto: str) -> dict:
    """«S1 | desc | CRITERIOS: C1 | ...» -> {id, descripcion, criterios, depende, prioridad} (tolerante)."""
    partes = [p.strip() for p in resto.split("|")]
    d = {"id": partes[0].strip(" *`").upper() if partes else "", "descripcion": "", "criterios": [],
         "depende": [], "prioridad": "media"}
    for p in partes[1:]:
        m = re.match(r"(CRITERIOS?|DEPENDE(?:_DE)?|PRIORIDAD)\s*:\s*(.*)$", p, re.IGNORECASE)
        if not m:
            if not d["descripcion"]:
                d["descripcion"] = sanea.limpiar(p, 200)
            continue
        clave, valor = m.group(1).upper(), m.group(2).strip()
        lista = [x.strip(" .`").upper() for x in re.split(r"[,\s]+", valor) if x.strip(" .`-")]
        if clave.startswith("CRITERIO"):
            d["criterios"] = [x for x in lista if _ID_CRIT.fullmatch(x)]
        elif clave.startswith("DEPENDE"):
            d["depende"] = [x for x in lista if x not in ("NINGUNA", "NADA", "-")]
        else:
            v = valor.lower().strip(" .")
            d["prioridad"] = v if v in PRIORIDADES else "media"
    return d


def analizar(texto) -> Plan:
    t = texto or ""
    p = Plan(criterios=criterios_de(t), archivos=sorted(archivos_del_plan(t)))
    ids_crit = {c["id"] for c in p.criterios}
    vistas = set()
    for m in _SUB.finditer(t):
        d = _campos(m.group(1))
        if not _ID_SUB.fullmatch(d["id"]):
            p.problemas.append(f"subtarea con identificador no válido: {d['id'][:12]!r}")
            continue
        if d["id"] in vistas:
            p.problemas.append(f"subtarea duplicada: {d['id']}")
            continue
        if len(p.subtareas) >= MAX_SUBTAREAS:
            p.problemas.append(f"más de {MAX_SUBTAREAS} subtareas: {d['id']} y siguientes se ignoran")
            break
        vistas.add(d["id"])
        for c in d["criterios"]:
            if c not in ids_crit:
                p.problemas.append(f"{d['id']} cita el criterio {c}, que no existe")
        d["criterios"] = [c for c in d["criterios"] if c in ids_crit]
        p.subtareas.append(d)
    if not p.subtareas:
        p.implicita = True
        p.subtareas = [{"id": "S0", "descripcion": "tarea completa (plan sin subtareas)",
                        "criterios": [c["id"] for c in p.criterios], "depende": [], "prioridad": "alta"}]
    ids_sub = {s["id"] for s in p.subtareas}
    for s in p.subtareas:
        malas = [x for x in s["depende"] if x not in ids_sub or x == s["id"]]
        for x in malas:
            p.problemas.append(f"{s['id']} depende de {x}, que no existe" if x != s["id"] else
                               f"{s['id']} depende de sí misma")
        s["depende"] = [x for x in s["depende"] if x in ids_sub and x != s["id"]]
        if not s["criterios"]:
            p.avisos.append(f"{s['id']} no tiene ningún criterio verificable")
    asignados = {c for s in p.subtareas for c in s["criterios"]}
    for c in p.criterios:
        if c["id"] not in asignados:
            p.avisos.append(f"el criterio {c['id']} no pertenece a ninguna subtarea")
    if not p.criterios:
        p.problemas.append("el plan no tiene criterios verificables (CRITERIO: Cn | ... | PRUEBA: test_x)")
    for m in _FALTA.finditer(t):
        partes = [x.strip() for x in m.group(1).split("|")]
        sup = None
        for x in partes[1:]:
            ms = re.match(r"SUPUESTO\s*:\s*(\S.*)$", x, re.IGNORECASE)
            if ms:
                sup = sanea.limpiar(ms.group(1), 200)
        texto_f = sanea.limpiar(partes[0], 200)
        if texto_f:
            p.faltas.append({"texto": texto_f, "supuesto": sup})
    p.supuestos = [sanea.limpiar(x, 200) for x in _SUPUESTO.findall(t) if x.strip()][:8]
    p.orden, ciclo = orden_topologico(p.subtareas)
    if ciclo:
        p.problemas.append("dependencias circulares entre " + ", ".join(ciclo))
    return p


def orden_topologico(subtareas) -> tuple:
    """(orden, nodos_en_ciclo). Kahn con desempate (prioridad, número). Con ciclo, los nodos del ciclo se
    añaden al final por prioridad para no perder trabajo, y se informan."""
    pend = {s["id"]: set(s["depende"]) for s in subtareas}
    prio = {s["id"]: (PRIORIDADES.get(s["prioridad"], 1), int(s["id"][1:]) if s["id"][1:].isdigit() else 99)
            for s in subtareas}
    orden = []
    while True:
        listos = sorted((n for n, d in pend.items() if not d), key=lambda n: prio[n])
        if not listos:
            break
        n = listos[0]
        orden.append(n)
        del pend[n]
        for d in pend.values():
            d.discard(n)
    ciclo = sorted(pend, key=lambda n: prio[n])
    return orden + ciclo, ciclo


def decision_informacion(plan: Plan, politica="preguntar") -> dict:
    """¿Se puede seguir? continuar | continuar_con_supuestos | preguntar.
    Una FALTA con SUPUESTO deja de bloquear (el supuesto queda registrado y se informa)."""
    if politica not in POLITICAS_FALTA:
        raise ValueError(f"política de información desconocida: {politica}")
    bloqueantes = [f for f in plan.faltas if not f["supuesto"]]
    supuestos = list(plan.supuestos) + [f"{f['texto']} -> se asume: {f['supuesto']}" for f in plan.faltas
                                         if f["supuesto"]]
    if bloqueantes and politica == "preguntar":
        return {"accion": "preguntar", "preguntas": [f["texto"] for f in bloqueantes], "supuestos": supuestos}
    if bloqueantes:
        supuestos += [f"SIN RESPUESTA: {f['texto']} (A2 no indicó qué asumir; la solución puede no cumplirlo)"
                      for f in bloqueantes]
    return {"accion": "continuar_con_supuestos" if supuestos else "continuar", "preguntas": [],
            "supuestos": supuestos}


def texto_para_programador(plan: Plan) -> str:
    """Bloque compacto con el ORDEN de trabajo para A1 (no repite lo que ya lleva el plan)."""
    if plan.implicita:
        return ""
    por_id = {s["id"]: s for s in plan.subtareas}
    lineas = ["ORDEN DE TRABAJO (decidido por el controlador a partir del plan):"]
    for n, sid in enumerate(plan.orden, 1):
        s = por_id[sid]
        lineas.append(f"{n}. {sid} [{s['prioridad']}] {s['descripcion'][:90]} -> criterios: "
                      f"{', '.join(s['criterios']) or 'ninguno'}")
    if plan.supuestos:
        lineas.append("SUPUESTOS (explícitos, se informarán al usuario): " + "; ".join(plan.supuestos)[:300])
    return "\n".join(lineas)


def progreso(plan: Plan, estados_criterios: list) -> list:
    """Estado de cada subtarea en ORDEN: completada | con_fallos | pendiente | sin_criterios."""
    est = {c["id"]: c.get("estado") for c in estados_criterios or []}
    ok = ("verificado", "superado_en_simulacion")
    malos = ("fallido_en_simulacion",)
    out = []
    por_id = {s["id"]: s for s in plan.subtareas}
    for sid in plan.orden:
        s = por_id[sid]
        cs = [est.get(c) for c in s["criterios"]]
        if not cs:
            e = "sin_criterios"
        elif all(x in ok for x in cs):
            e = "completada"
        elif any(x in malos for x in cs):
            e = "con_fallos"
        else:
            e = "pendiente"
        out.append({"subtarea": sid, "estado": e, "criterios": dict(zip(s["criterios"], cs))})
    return out


def subtareas_afectadas(plan: Plan, criterios_fallidos) -> list:
    return sorted({plan.subtarea_de(c) for c in criterios_fallidos if plan.subtarea_de(c)})


# --- revisión del plan --------------------------------------------------------------------------------------
def aplicar_revision(plan: Plan, texto) -> dict:
    """Aplica la revisión de A2: CRITERIO con id existente = MODIFICADO; id nuevo = AÑADIDO;
    «RETIRO: Cn | motivo» = RETIRADO (se conserva y bloquea «verificado»). Devuelve
    {criterios, modificados, anadidos, retirados, sin_cambio, problemas}."""
    nuevos = criterios_de(texto or "")
    previos = {c["id"]: c for c in plan.criterios}
    retirados, problemas = [], []
    for cid, motivo in _RETIRO.findall(texto or ""):
        cid = cid.upper()
        if cid not in previos:
            problemas.append(f"RETIRO de {cid}, que no existe")
            continue
        if cid not in [r["id"] for r in retirados]:
            retirados.append(dict(previos[cid], motivo=sanea.limpiar(motivo, 200)))
    ret_ids = {r["id"] for r in retirados}
    modificados, anadidos = [], []
    resultado = {cid: dict(c) for cid, c in previos.items() if cid not in ret_ids}
    for c in nuevos:
        if c["id"] in ret_ids:
            problemas.append(f"{c['id']} se retira y se redefine a la vez: se mantiene retirado")
            continue
        if c["id"] in previos:
            a = previos[c["id"]]
            if (a["descripcion"], a["prueba"]) != (c["descripcion"], c["prueba"]):
                modificados.append({"id": c["id"], "antes": a, "despues": c})
                resultado[c["id"]] = dict(c)
        elif len(resultado) < MAX_CRITERIOS:
            anadidos.append(c)
            resultado[c["id"]] = dict(c)
        else:
            problemas.append(f"{c['id']} no cabe: máximo {MAX_CRITERIOS} criterios")
    orden = [c["id"] for c in plan.criterios if c["id"] in resultado] + [c["id"] for c in anadidos]
    return {"criterios": [resultado[i] for i in orden], "modificados": modificados, "anadidos": anadidos,
            "retirados": retirados, "problemas": problemas,
            "sin_cambio": [i for i in previos if i not in ret_ids and i not in {m["id"] for m in modificados}]}


def _aserciones_por_prueba(texto: str) -> dict:
    try:
        arbol = ast.parse(texto or "")
    except (SyntaxError, ValueError, MemoryError, RecursionError):
        return {}
    fns = [n for n in arbol.body if isinstance(n, ast.FunctionDef)]
    for c in arbol.body:
        if isinstance(c, ast.ClassDef):
            fns += [n for n in c.body if isinstance(n, ast.FunctionDef)]
    out = {}
    for f in fns:
        if f.name.startswith("test"):
            out[f.name] = sum(1 for n in ast.walk(f) if isinstance(n, ast.Assert) or (
                isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr.startswith("assert")))
    return out


def debilitamiento(pruebas_antes: dict, pruebas_despues: dict, criterios_previos) -> list:
    """Avisos si la revisión DEBILITA las pruebas: una prueba de un criterio previo desaparece o pierde
    aserciones. Heurística determinista (puede dar falsos positivos si se reorganizan las aserciones): por eso
    no rechaza nada, pero impide la conclusión «verificado» hasta que el usuario lo revise."""
    a, d = {}, {}
    for t in (pruebas_antes or {}).values():
        a.update(_aserciones_por_prueba(t))
    for t in (pruebas_despues or {}).values():
        d.update(_aserciones_por_prueba(t))
    avisos = []
    for c in criterios_previos:
        p = c["prueba"]
        if p == "*" or p not in a:
            continue
        if p not in d:
            avisos.append(f"la prueba {p} del criterio {c['id']} desapareció")
        elif d[p] < a[p]:
            avisos.append(f"la prueba {p} del criterio {c['id']} pasó de {a[p]} a {d[p]} aserciones")
    return avisos


def pruebas_ausentes(criterios, resultado) -> list:
    """Criterios cuya PRUEBA no apareció entre las pruebas EJECUTADAS de verdad (plan y pruebas no casan: A1 no
    puede arreglarlo; hace falta revisar el plan)."""
    if (resultado or {}).get("tipo") != "real":
        return []
    det = resultado.get("detalle") or {}
    vistas = set(det.get("pruebas") or {})
    if not vistas or any(v.startswith("importar:") for v in vistas):
        return []                       # un error al importar es del código, no del plan
    return [c["id"] for c in criterios if c["prueba"] != "*" and c["prueba"] not in vistas]
