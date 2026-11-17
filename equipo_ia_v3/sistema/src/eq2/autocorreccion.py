"""V2-F: AUTOCORRECCIÓN con evidencia (módulo puro: no escribe archivos ni llama al modelo).

Cuatro mecanismos, todos deterministas y con el CONTROLADOR como juez:

  1. Precomprobación estática del código de A1 ANTES de gastar llamadas: si no se puede ni analizar (sintaxis,
     nombre importado que no existe, módulo inexistente) el diagnóstico lo escribe el controlador con el archivo y
     la línea, y se pasa directamente a CORREGIR. Se ahorran las llamadas de pruebas (A2), revisión (A3) y
     diagnóstico (A2) de esa iteración.
  2. Historial de INTENTOS FALLIDOS de la tarea para A1: qué versión falló qué prueba y qué cambió A1, para que
     no repita una corrección que ya no funcionó.
  3. CONTRAEJEMPLOS ejecutables de A3: sus líneas «CASO: f(x) == y» se ejecutan de verdad (con autorización) y
     bloquean la aceptación mientras fallen. A1 puede impugnarlos («REBATIDA: CASO A3-n | motivo»): el caso
     queda DISPUTADO, deja de bloquear el bucle, pero la conclusión ya no puede ser «verificado» sin el usuario.
  4. AFIRMACIONES SIN EVIDENCIA: frases como «todas las pruebas pasan» o «está verificado» cuando no existe una
     ejecución real que lo respalde se registran como error de calibración del agente (no cambian el flujo).
"""
from __future__ import annotations

import re
import unicodedata

from . import sanea

TIPOS_BLOQUEANTES = ("sintaxis", "no_analizable", "nombre_no_definido", "modulo_inexistente", "demasiado_grande")
_AFIRMACIONES = [
    ("pruebas_pasan", r"(?<!no )(?<!ni )\b(todas las pruebas|las pruebas|los tests|todos los tests)\s+(pasan|se superan|"
                      r"funcionan|estan en verde)\b"),
    ("pasa_pruebas", r"(?<!no )\bpasa(n)?\s+(todas\s+)?(las\s+)?pruebas\b"),
    ("verificado", r"(?<!no )(?<!sin )\b(esta|queda|ha sido|fue)\s+(verificad|probad|comprobad|testead)[oa]s?\b"),
    ("funciona", r"(?<!no )\bfunciona\s+(correctamente|perfectamente|bien|sin (errores|fallos|problemas))\b"),
    ("sin_errores", r"(?<!no )\b(no (tiene|contiene|hay) (ningun )?(errores|error|fallos|bugs?)|libre de errores|"
                    r"sin (ningun )?(error|errores|fallo|fallos|bugs?))\b"),
    ("he_probado", r"(?<!no )\b(lo |la |las |los )?he (probado|comprobado|verificado|ejecutado|testeado)\b"),
    ("corregido_confirmado", r"(?<!no )\b(ya )?(esta|queda) (corregido|arreglado|resuelto) (y|e) (verificado|probado)\b"),
]
_REBATIDA = re.compile(r"^[ \t]*[-*]?[ \t]*REBATIDA[ \t]*:[ \t]*(?:CASO[ \t]+)?([A-Za-z0-9_-]{1,12})[ \t]*\|[ \t]*(\S.*)$",
                       re.IGNORECASE | re.MULTILINE)
_CAMBIOS = re.compile(r"^[ \t]*[-*]?[ \t]*CAMBIOS[ \t]*:[ \t]*(\S.*)$", re.IGNORECASE | re.MULTILINE)


def _plano(t: str) -> str:
    t = unicodedata.normalize("NFKD", t if isinstance(t, str) else "")
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return re.sub(r"[^\S\n]+", " ", t)


# --- 1. precomprobación ----------------------------------------------------------------------------------
def errores_bloqueantes(analisis: dict) -> list:
    return [e for e in (analisis or {}).get("errores", []) if e.get("tipo") in TIPOS_BLOQUEANTES]


def diagnostico_estatico(errores: list) -> str:
    """Diagnóstico ESCRITO POR EL CONTROLADOR (sin modelo) a partir de errores estáticos."""
    lineas = ["DIAGNOSTICO (del controlador, sin modelo; el código no se puede analizar, no se ejecutó nada):"]
    for e in errores[:6]:
        donde = e.get("archivo", "?") + (f":{e['linea']}" if e.get("linea") else "")
        if e["tipo"] == "sintaxis":
            lineas.append(f"- {donde}: error de sintaxis: {e.get('mensaje', '')}")
        elif e["tipo"] == "nombre_no_definido":
            lineas.append(f"- {donde}: importa {e.get('nombre')} de {e.get('modulo')}, que no lo define")
        elif e["tipo"] == "modulo_inexistente":
            lineas.append(f"- {donde}: importa el módulo {e.get('modulo')}, que no existe en el proyecto")
        else:
            lineas.append(f"- {donde}: {e['tipo']}")
    lineas.append("Corrige SOLO esos errores y vuelve a escribir los archivos completos.")
    return "\n".join(lineas)


# --- 2. historial de intentos -------------------------------------------------------------------------------
def cambios_de(texto) -> str:
    m = _CAMBIOS.findall(texto or "")
    return sanea.limpiar(m[-1], 160) if m else ""


def historial_intentos(intentos: list, max_chars=700) -> str:
    """intentos: [{version, fallidas: [pruebas], error: str, cambios: str, origen: 'pruebas'|'estatico'}]."""
    if not intentos:
        return ""
    lineas = ["INTENTOS ANTERIORES EN ESTA TAREA (no repitas lo que ya falló):"]
    for it in intentos[-4:]:
        f = ", ".join(it.get("fallidas") or [])[:120] or it.get("origen", "?")
        lin = f"- v{it['version']}: falló {f}"
        if it.get("error"):
            lin += f" ({it['error'][:100]})"
        if it.get("cambios"):
            lin += f"; tu cambio había sido: {it['cambios'][:120]}"
        lineas.append(lin)
    return "\n".join(lineas)[:max_chars]


# --- 3. contraejemplos y disputas ---------------------------------------------------------------------------
def rebatidas(texto) -> dict:
    """{caso_id: motivo} de las líneas «REBATIDA: CASO A3-1 | motivo» (solo identificadores de caso)."""
    out = {}
    for cid, motivo in _REBATIDA.findall(texto or ""):
        if re.fullmatch(r"(A[1-3]|U|E)[A-Za-z0-9_-]*", cid, re.IGNORECASE):
            out[cid] = sanea.limpiar(motivo, 200)
    return out


_REBATIDA_PRUEBA = re.compile(r"^[ \t]*[-*]?[ \t]*REBATIDA[ \t]*:[ \t]*(?:PRUEBA[ \t]+)?(test_[A-Za-z0-9_]{1,60})[ \t]*\|"
                              r"[ \t]*(\S.*)$", re.IGNORECASE | re.MULTILINE)


def rebatidas_pruebas(texto) -> dict:
    """{prueba: motivo} de «REBATIDA: test_x | motivo»: A1 sostiene que una PRUEBA de A2 es errónea."""
    return {n: sanea.limpiar(m, 200) for n, m in _REBATIDA_PRUEBA.findall(texto or "")}


def bloque_contraejemplos(resultados: dict, casos_por_id: dict, disputados: dict) -> str:
    """Texto para A1 y A2: qué contraejemplos de A3 fallan, con el valor OBTENIDO al ejecutarlos."""
    lineas = []
    for cid, r in sorted(resultados.items()):
        c = casos_por_id.get(cid)
        if c is None:
            continue
        if cid in disputados:
            lineas.append(f"- {cid} DISPUTADO ({disputados[cid][:80]}): {c.clave()}")
        elif r["estado"] == "falla":
            lineas.append(f"- {cid} FALLA: {c.clave()} -> {(r.get('obtenido') or '')[:120]}")
        elif r["estado"] in ("error", "no_ejecutado"):
            lineas.append(f"- {cid} NO EJECUTADO: {c.clave()} ({(r.get('obtenido') or '')[:80]})")
    if not lineas:
        return ""
    return ("CONTRAEJEMPLOS DE A3 EJECUTADOS POR EL CONTROLADOR (si uno es erróneo, responde "
            "'REBATIDA: CASO <id> | motivo'):\n" + "\n".join(lineas[:8]))


# --- 4. afirmaciones sin evidencia --------------------------------------------------------------------------
def afirmaciones(texto) -> list:
    t = _plano(texto)
    out = []
    for tipo, rx in _AFIRMACIONES:
        m = re.search(rx, t)
        if m:
            out.append({"tipo": tipo, "frase": m.group(0)[:80]})
    return out


def afirmaciones_sin_evidencia(texto, respaldo_real: bool) -> list:
    """Afirmaciones de éxito cuando NO hay una ejecución real con resultado ok de la versión vigente."""
    return [] if respaldo_real else afirmaciones(texto)
