"""V2-E.5-r2: personalidad individual de A1, A2 y A3. MÓDULO OPCIONAL, DESACTIVADO POR DEFECTO.

Qué hace
  * ELECCIÓN INICIAL PROPIA: cada agente propone sus rasgos, su estilo de comunicación y sus
    preferencias no críticas en UNA llamada independiente (sin ver lo que eligieron los otros), con
    el modelo local existente, de forma secuencial (un solo servidor del modelo; nunca tres copias del GGUF).
    No se imponen rasgos: el prompt solo describe el formato. Sin elección, el agente tiene el
    PERFIL BASE neutral (sin rasgos).
  * Validación ESTRICTA de la respuesta (esquema cerrado). Se rechazan, con motivo registrado:
    respuestas inválidas, fuera del esquema, contradictorias y maliciosas (claves o rasgos que tocan
    permisos, función, seguridad o criterios de evaluación).
  * Registro persistente con PROCEDENCIA (simulado | qwen | usuario | ...) y VERSIÓN. Una elección
    válida queda «propuesta»: solo es vigente cuando el USUARIO la aprueba. No se repite en cada
    reinicio: solo se vuelve a elegir si el usuario lo solicita.
  * Consultar, editar, restablecer, solicitar nueva elección; historial de solo anexar; reversión.
  * Memoria de EXPERIENCIAS por agente (hechos verificados del sistema o del usuario frente a
    afirmaciones no verificadas de un agente) y PROPUESTAS de cambio graduales (un paso cada vez),
    que nunca se aplican sin la aprobación del usuario.
  * Límites: tokens, llamadas por agente, intentos por día, tamaño de la base, experiencias,
    propuestas pendientes y frecuencia de adaptación.

Qué NO hace (y la base lo impide)
  * No contiene ni puede contener permisos, función, políticas de seguridad, límites de recursos ni
    criterios de evaluación: el esquema es cerrado y los campos modificables son una lista fija
    (CHECK de la tabla `cambios`).
  * No se inyecta en los prompts de deliberación ni del motor (sin efecto en V2-E.5-r2).
  * No usa avatares, voces, diálogos entre agentes ni emociones.
  * Una elección SIMULADA nunca se presenta como generada por Qwen: el almacén se crea como
    «simulado» o «real» y la base rechaza el origen contrario.
Alcance: protege frente a los caminos del sistema y frente al texto del modelo; no frente a quien
edite a mano el archivo SQLite (`verificar` detecta contenidos alterados por su SHA-256).
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import unicodedata
from datetime import datetime, timedelta

from . import config, laboratorios, memoria, sanea
from .inferencia import ErrorInferencia

ESQUEMA_PERSONALIDAD = "1"
ESQUEMA_PERFIL = "1"
AGENTES = ("A1", "A2", "A3")
FUNCIONES = {"A1": "el programador", "A2": "el analista", "A3": "el revisor"}   # fijadas por el sistema
ALMACENES = ("real", "simulado")
TONOS = ("formal", "neutral", "cercano")
FORMATOS = ("prosa", "listas", "mixto")
ACLARACIONES = ("rara_vez", "a_veces", "a_menudo")
CLAVES = ("rasgos", "estilo", "preferencias")
CLAVES_ESTILO = ("tono", "verbosidad", "formato")
CLAVES_PREF = ("ejemplos", "explicar_razonamiento", "pedir_aclaraciones")
CAMPOS = ("estilo.tono", "estilo.verbosidad", "estilo.formato", "preferencias.ejemplos",
          "preferencias.explicar_razonamiento", "preferencias.pedir_aclaraciones", "rasgos")
MAX_RASGOS, MIN_LONG_RASGO, MAX_LONG_RASGO = 4, 3, 24
PERFIL_BASE = {"rasgos": [], "estilo": {"tono": "neutral", "verbosidad": 3, "formato": "mixto"},
               "preferencias": {"ejemplos": False, "explicar_razonamiento": False, "pedir_aclaraciones": "a_veces"}}
TIPOS_EXPERIENCIA = ("critica_falsa_posible", "critica_sin_evidencia", "critica_fundamentada",
                     "formato_no_reconocido", "respuesta_truncada", "acepta_sin_aplicar",
                     "preferencia_usuario_mas_detalle", "preferencia_usuario_menos_detalle",
                     "preferencia_usuario_mas_ejemplos", "otra")
FUENTES = ("sistema", "usuario", "agente")

# Palabras que delatan un intento de tocar permisos, función, seguridad o evaluación (sin tildes).
_PROHIBIDAS_CLAVE = ("permis", "rol", "funcion", "segur", "modo", "politic", "criteri", "limit", "evalu",
                     "herramient", "acceso", "privileg", "admin", "root", "sudo", "ejecut", "red", "api",
                     "contrasen", "token", "voto", "votar", "prompt", "instruccion", "sistema", "codigo")
_PROHIBIDAS_RASGO = ("permis", "admin", "root", "sudo", "segur", "ignor", "ejecut", "codig", "sistem", "rol",
                     "funcion", "politic", "criteri", "limit", "restricc", "autorid", "jefe", "supervis",
                     "privileg", "acces", "contrasen", "hack", "desobedi", "evalu", "vot", "aprob", "instrucc")
_SOSPECHOSO = re.compile(r"ignora|olvida (?:las|tus)|instrucciones|system|<\|[a-z_]+\|>|\bassistant\b|```python",
                         re.IGNORECASE)
_RASGO = re.compile(r"^[a-záéíóúüñ]+(?:[ -][a-záéíóúüñ]+)?$")
_VALLA = re.compile(r"^```(?:json)?[ \t]*\n?(.*?)\n?```$", re.DOTALL)
OPUESTOS = ((("conciso", "breve", "escueto"), ("detallista", "exhaustivo", "extenso")),
            (("formal",), ("informal", "desenfadado")),
            (("prudente", "cauteloso"), ("impulsivo", "temerario")),
            (("paciente",), ("impaciente",)),
            (("reservado", "callado"), ("hablador", "locuaz")))


class EleccionDeshabilitada(PermissionError):
    pass


class LimiteExcedido(ValueError):
    pass


class DatosCorruptos(Exception):
    """La base de personalidad no se puede leer. NO se sobrescribe ni se borra: se informa."""


def _sin_tildes(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _sha(t: str) -> str:
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def _canonico(perfil: dict) -> str:
    return json.dumps(perfil, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _prohibida(texto: str, raices) -> bool:
    t = _sin_tildes(texto.lower())
    return any(re.search(r"(?:^|[^a-z])" + r, t) for r in raices)


# ============================ validación (pura) ==============================================
def validar_perfil(d, permitir_sin_rasgos=False) -> dict:
    """Valida un perfil ya decodificado. {valida, perfil (normalizado) | None, errores, categoria}."""
    errores = []
    if not isinstance(d, dict):
        return _resultado(["invalida:no_es_objeto"])
    for k in d:
        if k not in CLAVES:
            errores.append(("maliciosa:clave_prohibida:" if _prohibida(str(k), _PROHIBIDAS_CLAVE)
                            else "fuera_del_esquema:clave_desconocida:") + str(k)[:40])
    for k in CLAVES:
        if k not in d:
            errores.append("fuera_del_esquema:falta:" + k)
    rasgos = d.get("rasgos")
    norm = []
    if "rasgos" in d:
        if not isinstance(rasgos, list):
            errores.append("invalida:tipo:rasgos")
        else:
            if not rasgos and not permitir_sin_rasgos:
                errores.append("invalida:vacia:rasgos")
            if len(rasgos) > MAX_RASGOS:
                errores.append("invalida:rango:rasgos")
            for r in rasgos[:MAX_RASGOS + 2]:
                if not isinstance(r, str):
                    errores.append("invalida:tipo:rasgo")
                    continue
                s = unicodedata.normalize("NFC", r.strip().lower())
                if _prohibida(s, _PROHIBIDAS_RASGO):
                    errores.append("maliciosa:rasgo_prohibido:" + s[:30])
                elif not (MIN_LONG_RASGO <= len(s) <= MAX_LONG_RASGO) or not _RASGO.match(s):
                    errores.append("invalida:formato:rasgo")
                elif s in norm:
                    errores.append("contradictoria:rasgo_repetido:" + s)
                else:
                    norm.append(s)
    for clave, subclaves in (("estilo", CLAVES_ESTILO), ("preferencias", CLAVES_PREF)):
        sub = d.get(clave)
        if clave not in d:
            continue
        if not isinstance(sub, dict):
            errores.append("invalida:tipo:" + clave)
            continue
        for k in sub:
            if k not in subclaves:
                errores.append(("maliciosa:clave_prohibida:" if _prohibida(str(k), _PROHIBIDAS_CLAVE)
                                else "fuera_del_esquema:clave_desconocida:") + f"{clave}.{str(k)[:30]}")
        for k in subclaves:
            if k not in sub:
                errores.append(f"fuera_del_esquema:falta:{clave}.{k}")
    est, pref = d.get("estilo") if isinstance(d.get("estilo"), dict) else {}, \
        d.get("preferencias") if isinstance(d.get("preferencias"), dict) else {}
    for k, opciones, sub in (("tono", TONOS, est), ("formato", FORMATOS, est),
                             ("pedir_aclaraciones", ACLARACIONES, pref)):
        if k in sub and sub[k] not in opciones:
            errores.append("invalida:valor:" + k)
    v = est.get("verbosidad")
    if "verbosidad" in est and (not isinstance(v, int) or isinstance(v, bool)):
        errores.append("invalida:tipo:verbosidad")
    elif "verbosidad" in est and not 1 <= v <= 5:
        errores.append("invalida:rango:verbosidad")
    for k in ("ejemplos", "explicar_razonamiento"):
        if k in pref and not isinstance(pref[k], bool):
            errores.append("invalida:tipo:" + k)
    if not errores:
        errores += _contradicciones(norm, est)
    if errores:
        return _resultado(errores)
    perfil = {"rasgos": norm, "estilo": {k: est[k] for k in CLAVES_ESTILO},
              "preferencias": {k: pref[k] for k in CLAVES_PREF}}
    return {"valida": True, "perfil": perfil, "errores": [], "categoria": "valida"}


def _contradicciones(rasgos, estilo) -> list:
    out = []
    planos = {_sin_tildes(r) for r in rasgos}
    for a, b in OPUESTOS:
        x, y = planos & set(a), planos & set(b)
        if x and y:
            out.append(f"contradictoria:rasgos_opuestos:{sorted(x)[0]}/{sorted(y)[0]}")
    v, tono = estilo.get("verbosidad"), estilo.get("tono")
    if planos & {"conciso", "breve", "escueto"} and v >= 4:
        out.append("contradictoria:rasgo_estilo:conciso/verbosidad")
    if planos & {"detallista", "exhaustivo", "extenso"} and v <= 2:
        out.append("contradictoria:rasgo_estilo:detallista/verbosidad")
    if "formal" in planos and tono == "cercano":
        out.append("contradictoria:rasgo_estilo:formal/tono")
    if planos & {"informal", "desenfadado"} and tono == "formal":
        out.append("contradictoria:rasgo_estilo:informal/tono")
    return out


def _resultado(errores) -> dict:
    orden = ("maliciosa", "contradictoria", "fuera_del_esquema", "invalida")
    cats = {e.split(":")[0] for e in errores}
    cat = next(c for c in orden if c in cats) if cats else "invalida"
    return {"valida": False, "perfil": None, "errores": list(dict.fromkeys(errores))[:20], "categoria": cat}


def _sin_duplicados(pares):
    d = {}
    for k, v in pares:
        if k in d:
            raise ValueError("clave_duplicada:" + str(k)[:30])
        d[k] = v
    return d


def _constante(c):
    raise ValueError("constante_no_permitida:" + c)


def validar_respuesta(texto) -> dict:
    """Valida la respuesta BRUTA del modelo: SOLO un objeto JSON (se admite una valla ```json)."""
    if not isinstance(texto, str) or not texto.strip():
        return _resultado(["invalida:vacia"])
    if len(texto) > config.PERSONALIDAD_MAX_RESPUESTA_CHARS:
        return _resultado(["invalida:demasiado_larga"])
    t = texto.strip()
    m = _VALLA.match(t)
    if m:
        t = m.group(1).strip()
    sospechoso = bool(_SOSPECHOSO.search(texto))
    if not (t.startswith("{") and t.endswith("}")):
        return _resultado(["maliciosa:texto_sospechoso"] * sospechoso + ["invalida:texto_fuera_del_json"])
    try:
        d = json.loads(t, object_pairs_hook=_sin_duplicados, parse_constant=_constante)
    except ValueError as e:
        msg = str(e)
        if msg.startswith("clave_duplicada:"):
            return _resultado(["contradictoria:" + msg])
        return _resultado(["maliciosa:texto_sospechoso"] * sospechoso + ["invalida:no_json"])
    r = validar_perfil(d)
    if sospechoso:                     # aunque el perfil sea válido (p. ej. un rasgo «assistant»)
        r = _resultado(["maliciosa:texto_sospechoso"] + r["errores"])
    return r


# ============================ prompt de elección (independiente por agente) ===================
FORMATO_RESPUESTA = ('{"rasgos": [de 1 a 4 palabras en minúsculas], '
                     '"estilo": {"tono": "formal" | "neutral" | "cercano", "verbosidad": entero de 1 a 5, '
                     '"formato": "prosa" | "listas" | "mixto"}, '
                     '"preferencias": {"ejemplos": true | false, "explicar_razonamiento": true | false, '
                     '"pedir_aclaraciones": "rara_vez" | "a_veces" | "a_menudo"}}')


def mensajes_eleccion(agente: str, errores_previos=()) -> list:
    """Prompt de elección. Solo describe el FORMATO: no sugiere ningún rasgo concreto ni incluye lo
    que eligieron otros agentes."""
    if agente not in AGENTES:
        raise ValueError(f"agente desconocido: {agente!r}")
    sistema = (f"Eres {agente}, {FUNCIONES[agente]} de un equipo de tres agentes. Tu función, tus permisos, "
               "las reglas de seguridad y los criterios de evaluación los fija el sistema y no se pueden elegir.")
    usuario = ("Elige tu personalidad inicial: solo tus rasgos, tu estilo de comunicación y preferencias no "
               "críticas. Responde SOLO con un objeto JSON con exactamente estas claves y sin texto adicional:\n"
               + FORMATO_RESPUESTA)
    if errores_previos:
        usuario += ("\nTu respuesta anterior no era válida (" + ", ".join(sorted(set(errores_previos)))[:300]
                    + "). Responde de nuevo SOLO con el JSON.")
    return [{"role": "system", "content": sistema}, {"role": "user", "content": usuario}]


# ============================ almacén persistente ==============================================
DDL = """
CREATE TABLE IF NOT EXISTS meta(clave TEXT PRIMARY KEY, valor TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS elecciones(
  num INTEGER PRIMARY KEY, ts TEXT NOT NULL, agente TEXT NOT NULL CHECK(agente IN ('A1','A2','A3')),
  origen TEXT NOT NULL CHECK(origen IN ('simulado','qwen')), modelo TEXT,
  intento INTEGER NOT NULL CHECK(intento BETWEEN 1 AND 2), prompt_sha256 TEXT NOT NULL,
  respuesta TEXT NOT NULL CHECK(length(respuesta) <= 1500), respuesta_sha256 TEXT NOT NULL,
  valida INTEGER NOT NULL CHECK(valida IN (0, 1)), categoria TEXT NOT NULL, errores_json TEXT NOT NULL,
  max_tokens INTEGER NOT NULL CHECK(max_tokens BETWEEN 1 AND 200),
  CHECK(origen <> 'qwen' OR (modelo IS NOT NULL AND length(modelo) > 0)));
CREATE TABLE IF NOT EXISTS cambios(
  num INTEGER PRIMARY KEY, ts TEXT NOT NULL, agente TEXT NOT NULL CHECK(agente IN ('A1','A2','A3')),
  campo TEXT NOT NULL CHECK(campo IN ('estilo.tono','estilo.verbosidad','estilo.formato','preferencias.ejemplos',
    'preferencias.explicar_razonamiento','preferencias.pedir_aclaraciones','rasgos','*')),
  antes TEXT, despues TEXT NOT NULL CHECK(length(despues) <= 2000),
  motivo TEXT NOT NULL CHECK(length(motivo) BETWEEN 1 AND 300),
  importancia TEXT NOT NULL CHECK(importancia IN ('menor','importante')),
  origen TEXT NOT NULL CHECK(origen IN ('adaptacion','usuario','eleccion','restablecimiento','reversion')),
  estado TEXT NOT NULL CHECK(estado IN ('pendiente','aplicado','rechazado','revertido')),
  decidido_por TEXT CHECK(decidido_por IS NULL OR decidido_por = 'usuario'), decidido_ts TEXT,
  perfil_previo INTEGER, perfil_resultante INTEGER,
  CHECK(estado = 'pendiente' OR decidido_por = 'usuario'));
CREATE TABLE IF NOT EXISTS perfiles(
  num INTEGER PRIMARY KEY, ts TEXT NOT NULL, agente TEXT NOT NULL CHECK(agente IN ('A1','A2','A3')),
  version INTEGER NOT NULL CHECK(version >= 1), esquema_perfil TEXT NOT NULL,
  datos_json TEXT NOT NULL CHECK(length(datos_json) <= 2000), sha256 TEXT NOT NULL CHECK(length(sha256) = 64),
  origen TEXT NOT NULL CHECK(origen IN ('simulado','qwen','usuario','adaptacion','restablecimiento','reversion')),
  estado TEXT NOT NULL CHECK(estado IN ('propuesto','vigente','sustituido','rechazado')),
  eleccion_num INTEGER REFERENCES elecciones(num), cambio_num INTEGER REFERENCES cambios(num),
  UNIQUE(agente, version));
CREATE TABLE IF NOT EXISTS experiencias(
  num INTEGER PRIMARY KEY, ts TEXT NOT NULL, agente TEXT NOT NULL CHECK(agente IN ('A1','A2','A3')),
  tipo TEXT NOT NULL CHECK(tipo IN ('critica_falsa_posible','critica_sin_evidencia','critica_fundamentada',
    'formato_no_reconocido','respuesta_truncada','acepta_sin_aplicar','preferencia_usuario_mas_detalle',
    'preferencia_usuario_menos_detalle','preferencia_usuario_mas_ejemplos','otra')),
  descripcion TEXT NOT NULL CHECK(length(descripcion) BETWEEN 1 AND 300),
  fuente TEXT NOT NULL CHECK(fuente IN ('sistema','usuario','agente')),
  verificada INTEGER NOT NULL CHECK(verificada IN (0, 1)), referencia TEXT CHECK(length(referencia) <= 120),
  run_id TEXT, archivada INTEGER NOT NULL DEFAULT 0 CHECK(archivada IN (0, 1)),
  CHECK(fuente <> 'agente' OR verificada = 0), CHECK(verificada = 0 OR referencia IS NOT NULL),
  UNIQUE(agente, tipo, referencia));
CREATE TABLE IF NOT EXISTS cambio_experiencias(
  cambio_num INTEGER NOT NULL REFERENCES cambios(num), experiencia_num INTEGER NOT NULL UNIQUE
  REFERENCES experiencias(num));
CREATE TABLE IF NOT EXISTS solicitudes(
  num INTEGER PRIMARY KEY, ts TEXT NOT NULL, agente TEXT NOT NULL CHECK(agente IN ('A1','A2','A3')),
  actor TEXT NOT NULL CHECK(actor = 'usuario'), atendida INTEGER NOT NULL DEFAULT 0 CHECK(atendida IN (0, 1)));
CREATE TABLE IF NOT EXISTS historial(
  num INTEGER PRIMARY KEY, ts TEXT NOT NULL, agente TEXT NOT NULL CHECK(agente IN ('A1','A2','A3')),
  accion TEXT NOT NULL, detalle TEXT CHECK(length(detalle) <= 600),
  actor TEXT NOT NULL CHECK(actor IN ('usuario','sistema')));

CREATE TRIGGER IF NOT EXISTS hist_solo_anexar_u BEFORE UPDATE ON historial
  BEGIN SELECT RAISE(ABORT, 'el historial no se modifica'); END;
CREATE TRIGGER IF NOT EXISTS hist_solo_anexar_d BEFORE DELETE ON historial
  BEGIN SELECT RAISE(ABORT, 'el historial no se borra'); END;
CREATE TRIGGER IF NOT EXISTS ele_solo_anexar_u BEFORE UPDATE ON elecciones
  BEGIN SELECT RAISE(ABORT, 'las elecciones registradas no se modifican'); END;
CREATE TRIGGER IF NOT EXISTS ele_solo_anexar_d BEFORE DELETE ON elecciones
  BEGIN SELECT RAISE(ABORT, 'las elecciones registradas no se borran'); END;
CREATE TRIGGER IF NOT EXISTS ele_origen_del_almacen BEFORE INSERT ON elecciones
  WHEN (NEW.origen = 'simulado' AND (SELECT valor FROM meta WHERE clave = 'almacen') <> 'simulado')
    OR (NEW.origen = 'qwen' AND (SELECT valor FROM meta WHERE clave = 'almacen') <> 'real')
  BEGIN SELECT RAISE(ABORT, 'el origen de la elección no corresponde a este almacén (simulado/real)'); END;
CREATE TRIGGER IF NOT EXISTS per_no_borrar BEFORE DELETE ON perfiles
  BEGIN SELECT RAISE(ABORT, 'las versiones de perfil no se borran'); END;
CREATE TRIGGER IF NOT EXISTS per_inmutable BEFORE UPDATE ON perfiles
  WHEN NEW.datos_json IS NOT OLD.datos_json OR NEW.sha256 IS NOT OLD.sha256 OR NEW.agente IS NOT OLD.agente
    OR NEW.version IS NOT OLD.version OR NEW.origen IS NOT OLD.origen OR NEW.eleccion_num IS NOT OLD.eleccion_num
    OR NEW.esquema_perfil IS NOT OLD.esquema_perfil OR NEW.ts IS NOT OLD.ts
    OR (OLD.cambio_num IS NOT NULL AND NEW.cambio_num IS NOT OLD.cambio_num)
  BEGIN SELECT RAISE(ABORT, 'una versión de perfil no se modifica: se crea una nueva'); END;
CREATE TRIGGER IF NOT EXISTS per_transiciones BEFORE UPDATE OF estado ON perfiles
  WHEN NOT (NEW.estado = OLD.estado OR (OLD.estado = 'propuesto' AND NEW.estado IN ('vigente','rechazado'))
    OR (OLD.estado = 'vigente' AND NEW.estado = 'sustituido'))
  BEGIN SELECT RAISE(ABORT, 'transición de estado de perfil no permitida'); END;
CREATE TRIGGER IF NOT EXISTS per_un_vigente_i BEFORE INSERT ON perfiles
  WHEN NEW.estado = 'vigente' AND EXISTS (SELECT 1 FROM perfiles WHERE agente = NEW.agente AND estado = 'vigente')
  BEGIN SELECT RAISE(ABORT, 'ya hay un perfil vigente para este agente'); END;
CREATE TRIGGER IF NOT EXISTS per_un_vigente_u BEFORE UPDATE OF estado ON perfiles
  WHEN NEW.estado = 'vigente' AND OLD.estado <> 'vigente' AND EXISTS (SELECT 1 FROM perfiles
    WHERE agente = NEW.agente AND estado = 'vigente')
  BEGIN SELECT RAISE(ABORT, 'ya hay un perfil vigente para este agente'); END;
CREATE TRIGGER IF NOT EXISTS per_un_propuesto BEFORE INSERT ON perfiles
  WHEN NEW.estado = 'propuesto' AND EXISTS (SELECT 1 FROM perfiles WHERE agente = NEW.agente AND estado = 'propuesto')
  BEGIN SELECT RAISE(ABORT, 'ya hay una elección propuesta pendiente para este agente'); END;
CREATE TRIGGER IF NOT EXISTS per_nace_propuesto_o_decidido BEFORE INSERT ON perfiles
  WHEN NEW.estado NOT IN ('propuesto','vigente')
    OR (NEW.estado = 'propuesto' AND NEW.origen NOT IN ('simulado','qwen'))
  BEGIN SELECT RAISE(ABORT, 'un perfil nace propuesto (elección) o vigente (decisión del usuario)'); END;
CREATE TRIGGER IF NOT EXISTS per_eleccion_con_procedencia BEFORE INSERT ON perfiles
  WHEN NEW.origen IN ('simulado','qwen') AND NOT EXISTS (SELECT 1 FROM elecciones WHERE num = NEW.eleccion_num
    AND agente = NEW.agente AND origen = NEW.origen AND valida = 1)
  BEGIN SELECT RAISE(ABORT, 'un perfil elegido exige una elección válida del mismo agente y origen'); END;
CREATE TRIGGER IF NOT EXISTS per_vigente_exige_usuario_i BEFORE INSERT ON perfiles
  WHEN NEW.estado = 'vigente' AND NOT EXISTS (SELECT 1 FROM cambios WHERE num = NEW.cambio_num
    AND agente = NEW.agente AND estado = 'aplicado' AND decidido_por = 'usuario')
  BEGIN SELECT RAISE(ABORT, 'un perfil solo es vigente por decisión del usuario'); END;
CREATE TRIGGER IF NOT EXISTS per_vigente_exige_usuario_u BEFORE UPDATE OF estado ON perfiles
  WHEN NEW.estado = 'vigente' AND OLD.estado = 'propuesto' AND NOT EXISTS (SELECT 1 FROM cambios
    WHERE num = NEW.cambio_num AND agente = NEW.agente AND estado = 'aplicado' AND decidido_por = 'usuario')
  BEGIN SELECT RAISE(ABORT, 'un perfil solo es vigente por decisión del usuario'); END;
CREATE TRIGGER IF NOT EXISTS cam_no_borrar BEFORE DELETE ON cambios
  BEGIN SELECT RAISE(ABORT, 'los cambios no se borran'); END;
CREATE TRIGGER IF NOT EXISTS cam_transiciones BEFORE UPDATE ON cambios
  WHEN NOT ((OLD.estado = 'pendiente' AND NEW.estado IN ('aplicado','rechazado'))
    OR (OLD.estado = 'aplicado' AND NEW.estado = 'revertido') OR (OLD.estado = NEW.estado))
    OR NEW.campo IS NOT OLD.campo OR NEW.despues IS NOT OLD.despues OR NEW.agente IS NOT OLD.agente
    OR NEW.antes IS NOT OLD.antes OR NEW.origen IS NOT OLD.origen
  BEGIN SELECT RAISE(ABORT, 'cambio no permitido en la propuesta'); END;
CREATE TRIGGER IF NOT EXISTS cam_pendientes_limite BEFORE INSERT ON cambios
  WHEN NEW.estado = 'pendiente' AND (SELECT COUNT(*) FROM cambios WHERE agente = NEW.agente
    AND estado = 'pendiente') >= 3
  BEGIN SELECT RAISE(ABORT, 'demasiadas propuestas pendientes para este agente'); END;
CREATE TRIGGER IF NOT EXISTS cex_mismo_agente BEFORE INSERT ON cambio_experiencias
  WHEN (SELECT agente FROM cambios WHERE num = NEW.cambio_num) IS NOT
       (SELECT agente FROM experiencias WHERE num = NEW.experiencia_num)
  BEGIN SELECT RAISE(ABORT, 'una propuesta solo usa experiencias del mismo agente'); END;
CREATE TRIGGER IF NOT EXISTS cex_solo_verificadas BEFORE INSERT ON cambio_experiencias
  WHEN NOT EXISTS (SELECT 1 FROM experiencias WHERE num = NEW.experiencia_num AND verificada = 1)
  BEGIN SELECT RAISE(ABORT, 'una propuesta solo se apoya en experiencias verificadas'); END;
CREATE TRIGGER IF NOT EXISTS exp_no_borrar BEFORE DELETE ON experiencias
  BEGIN SELECT RAISE(ABORT, 'las experiencias no se borran: se archivan'); END;
CREATE TRIGGER IF NOT EXISTS exp_solo_archivar BEFORE UPDATE ON experiencias
  WHEN NOT (OLD.archivada = 0 AND NEW.archivada = 1) OR NEW.tipo IS NOT OLD.tipo
    OR NEW.descripcion IS NOT OLD.descripcion OR NEW.verificada IS NOT OLD.verificada
    OR NEW.fuente IS NOT OLD.fuente OR NEW.agente IS NOT OLD.agente OR NEW.referencia IS NOT OLD.referencia
  BEGIN SELECT RAISE(ABORT, 'una experiencia solo se puede archivar'); END;
CREATE TRIGGER IF NOT EXISTS exp_limite_activas BEFORE INSERT ON experiencias
  WHEN (SELECT COUNT(*) FROM experiencias WHERE agente = NEW.agente AND archivada = 0) >= 200
  BEGIN SELECT RAISE(ABORT, 'límite de experiencias activas para este agente'); END;
CREATE TRIGGER IF NOT EXISTS exp_limite_total BEFORE INSERT ON experiencias
  WHEN (SELECT COUNT(*) FROM experiencias WHERE agente = NEW.agente) >= 1000
  BEGIN SELECT RAISE(ABORT, 'límite total de experiencias para este agente'); END;
CREATE TRIGGER IF NOT EXISTS sol_solo_atender BEFORE UPDATE ON solicitudes
  WHEN NOT (OLD.atendida = 0 AND NEW.atendida = 1) OR NEW.agente IS NOT OLD.agente
  BEGIN SELECT RAISE(ABORT, 'una solicitud solo se marca como atendida'); END;
CREATE TRIGGER IF NOT EXISTS sol_no_borrar BEFORE DELETE ON solicitudes
  BEGIN SELECT RAISE(ABORT, 'las solicitudes no se borran'); END;
"""

MAX_EXPERIENCIAS_TOTAL = 1000        # igual que exp_limite_total
MAX_EXPERIENCIAS_ACTIVAS_DURO = 200  # igual que exp_limite_activas
MAX_PENDIENTES_DURO = 3              # igual que cam_pendientes_limite


def _parse_ts(s):
    try:
        return datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return None


class RegistroPersonalidad(memoria._Base):
    """Almacén de personalidad en `<carpeta>/personalidad.db`. `almacen`: «real» o «simulado»."""

    def __init__(self, lab, almacen="real", ahora=memoria.ahora_iso):
        if almacen not in ALMACENES:
            raise ValueError("almacén desconocido")
        carpeta = "personalidad" if almacen == "real" else "personalidad_simulada"
        lab.crear_base()
        lab.crear_dir(carpeta)
        self.almacen = almacen
        try:
            super().__init__(lab.ruta(carpeta, "personalidad.db"), ahora)
            if not self.quick_check():
                raise sqlite3.DatabaseError("quick_check")
            previo = self._leer_meta("esquema")
            if previo is not None and previo != ESQUEMA_PERSONALIDAD:
                self.con.close()
                raise memoria.EsquemaIncompatible(f"personalidad.db tiene esquema {previo}")
            tipo = self._leer_meta("almacen")
            if tipo is not None and tipo != almacen:
                self.con.close()
                raise ValueError(f"este almacén es «{tipo}», no «{almacen}»")
            self.con.executescript(DDL)
            laboratorios.comprobar_disparadores(self.con, DDL)
            self._meta_set("esquema", ESQUEMA_PERSONALIDAD)
            if tipo is None:
                self._meta_set("almacen", almacen)
            ps = self.con.execute("PRAGMA page_size").fetchone()[0]
            limite = memoria._pragma_max_paginas(max(1, int(config.PERSONALIDAD_MAX_DB_BYTES) // int(ps)))
            self.con.execute(limite)
        except sqlite3.DatabaseError as e:
            try:
                self.con.close()
            except (AttributeError, sqlite3.Error):
                pass
            raise DatosCorruptos(f"personalidad.db no se puede leer ({type(e).__name__}: {str(e)[:80]}); "
                                 "no se ha modificado: muévela a otra carpeta para empezar de cero") from None

    def _leer_meta(self, clave):
        try:
            return self._meta_get(clave)
        except sqlite3.OperationalError:          # base nueva: aún no hay tabla meta
            return None

    # --- utilidades ---------------------------------------------------------------------------
    @staticmethod
    def _agente(agente):
        if agente not in AGENTES:
            raise ValueError(f"agente desconocido: {agente!r}")

    def _espacio(self):
        if self.tamano_bytes() > config.PERSONALIDAD_MAX_DB_BYTES:
            raise LimiteExcedido("la base de personalidad alcanzó su tamaño máximo")

    def _hist(self, agente, accion, detalle, actor):
        self.con.execute("INSERT INTO historial(ts,agente,accion,detalle,actor) VALUES(?,?,?,?,?)",
                         (self.ahora(), agente, accion, sanea.limpiar(detalle or "", 600) or None, actor))

    # --- perfiles -----------------------------------------------------------------------------
    def _fila_perfil(self, r) -> dict:
        d = dict(r)
        problemas = []
        try:
            datos = json.loads(d["datos_json"])
        except ValueError:
            datos, problemas = None, ["datos_json_ilegible"]
        if datos is not None and _sha(d["datos_json"]) != d["sha256"]:
            problemas.append("sha256_no_coincide")
        if datos is not None and not validar_perfil(datos, permitir_sin_rasgos=True)["valida"]:
            problemas.append("fuera_del_esquema")
        d["datos"], d["problemas"] = (None if problemas else datos), problemas
        return d

    def _por_estado(self, agente, estado):
        r = self.con.execute("SELECT * FROM perfiles WHERE agente=? AND estado=? ORDER BY num DESC LIMIT 1",
                             (agente, estado)).fetchone()
        return self._fila_perfil(r) if r else None

    def perfil(self, agente) -> dict:
        """Perfil en uso: el vigente o, si no hay (o está dañado), el BASE neutral. Nunca falla."""
        self._agente(agente)
        v = self._por_estado(agente, "vigente")
        if v and v["datos"] is not None:
            return {"agente": agente, "fuente": "vigente", "version": v["version"], "origen": v["origen"],
                    "datos": v["datos"], "avisos": []}
        avisos = ["perfil_vigente_danado:" + ",".join(v["problemas"])] if v else []
        return {"agente": agente, "fuente": "base", "version": None, "origen": "base",
                "datos": json.loads(json.dumps(PERFIL_BASE)), "avisos": avisos}

    def propuesto(self, agente):
        self._agente(agente)
        return self._por_estado(agente, "propuesto")

    def versiones(self, agente) -> list:
        self._agente(agente)
        return [self._fila_perfil(r) for r in self.con.execute(
            "SELECT * FROM perfiles WHERE agente=? ORDER BY version", (agente,))]

    def _siguiente_version(self, agente) -> int:
        return (self.con.execute("SELECT COALESCE(MAX(version), 0) FROM perfiles WHERE agente=?",
                                 (agente,)).fetchone()[0]) + 1

    def _insertar_perfil(self, agente, datos, origen, estado, eleccion_num=None, cambio_num=None) -> int:
        js = _canonico(datos)
        c = self.con.execute(
            "INSERT INTO perfiles(ts,agente,version,esquema_perfil,datos_json,sha256,origen,estado,eleccion_num,"
            "cambio_num) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (self.ahora(), agente, self._siguiente_version(agente), ESQUEMA_PERFIL, js, _sha(js), origen, estado,
             eleccion_num, cambio_num))
        return c.lastrowid

    def _aplicar(self, agente, datos, origen_perfil, origen_cambio, campo, antes, despues, motivo, importancia,
                 actor="usuario", cambio_existente=None, perfil_propuesto=None) -> dict:
        """Consolida un perfil nuevo como VIGENTE (siempre por decisión del usuario). Transacción única."""
        if actor != "usuario":
            raise PermissionError("solo el usuario consolida cambios de personalidad")
        r = validar_perfil(datos, permitir_sin_rasgos=True)
        if not r["valida"]:
            raise ValueError("perfil no válido: " + ", ".join(r["errores"]))
        self._espacio()
        previo = self._por_estado(agente, "vigente")
        ts = self.ahora()
        with self.con:
            if cambio_existente is None:
                cnum = self.con.execute(
                    "INSERT INTO cambios(ts,agente,campo,antes,despues,motivo,importancia,origen,estado,decidido_por,"
                    "decidido_ts,perfil_previo) VALUES(?,?,?,?,?,?,?,?,'aplicado','usuario',?,?)",
                    (ts, agente, campo, antes, despues, sanea.limpiar(motivo, 300) or "sin motivo", importancia,
                     origen_cambio, ts, previo["num"] if previo else None)).lastrowid
            else:
                cnum = cambio_existente
                self.con.execute("UPDATE cambios SET estado='aplicado', decidido_por='usuario', decidido_ts=?, "
                                 "perfil_previo=? WHERE num=?", (ts, previo["num"] if previo else None, cnum))
            if previo:
                self.con.execute("UPDATE perfiles SET estado='sustituido' WHERE num=?", (previo["num"],))
            if perfil_propuesto is not None:
                self.con.execute("UPDATE perfiles SET estado='vigente', cambio_num=? WHERE num=?",
                                 (cnum, perfil_propuesto))
                pnum = perfil_propuesto
            else:
                pnum = self._insertar_perfil(agente, r["perfil"], origen_perfil, "vigente", cambio_num=cnum)
            self.con.execute("UPDATE cambios SET perfil_resultante=? WHERE num=?", (pnum, cnum))
            self._hist(agente, "cambio_aplicado", f"cambio {cnum} ({origen_cambio}, {campo}): {motivo}", actor)
        return {"cambio": cnum, "perfil": pnum}

    # --- elección -----------------------------------------------------------------------------
    def necesita_eleccion(self, agente) -> bool:
        """Solo si el usuario la pidió o si el agente nunca tuvo perfil (ni propuesto, ni rechazado, ni
        editado): una elección hecha NO se repite en cada reinicio."""
        self._agente(agente)
        if self._solicitud_pendiente(agente):
            return True
        return self.con.execute("SELECT 1 FROM perfiles WHERE agente=? LIMIT 1", (agente,)).fetchone() is None

    def _solicitud_pendiente(self, agente):
        return self.con.execute("SELECT num FROM solicitudes WHERE agente=? AND atendida=0 ORDER BY num LIMIT 1",
                                (agente,)).fetchone()

    def solicitar_nueva_eleccion(self, agente, actor="usuario") -> int:
        self._agente(agente)
        if actor != "usuario":
            raise PermissionError("solo el usuario solicita una nueva elección")
        with self.con:
            p = self._por_estado(agente, "propuesto")
            if p:
                self.con.execute("UPDATE perfiles SET estado='rechazado' WHERE num=?", (p["num"],))
            n = self.con.execute("INSERT INTO solicitudes(ts,agente,actor) VALUES(?,?,'usuario')",
                                 (self.ahora(), agente)).lastrowid
            self._hist(agente, "nueva_eleccion_solicitada", f"solicitud {n}", "usuario")
        return n

    def intentos_recientes(self, agente, horas=24) -> int:
        ahora = _parse_ts(self.ahora())
        n = 0
        for (ts,) in self.con.execute("SELECT ts FROM elecciones WHERE agente=?", (agente,)):
            t = _parse_ts(ts)
            if t is None or ahora is None or ahora - t < timedelta(hours=horas):
                n += 1                                        # una fecha ilegible cuenta (conservador)
        return n

    def registrar_intento(self, agente, origen, modelo, intento, mensajes, respuesta, validacion, max_tokens) -> int:
        self._espacio()
        texto = sanea.limpiar(respuesta or "", config.PERSONALIDAD_MAX_RESPUESTA_CHARS)
        with self.con:
            return self.con.execute(
                "INSERT INTO elecciones(ts,agente,origen,modelo,intento,prompt_sha256,respuesta,respuesta_sha256,valida,"
                "categoria,errores_json,max_tokens) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (self.ahora(), agente, origen, modelo, intento, _sha(_canonico({"m": list(mensajes)})), texto,
                 _sha(respuesta or ""), int(validacion["valida"]), validacion["categoria"],
                 json.dumps(validacion["errores"], ensure_ascii=False), max_tokens)).lastrowid

    def registrar_propuesta(self, agente, perfil, origen, eleccion_num) -> int:
        with self.con:
            num = self._insertar_perfil(agente, perfil, origen, "propuesto", eleccion_num=eleccion_num)
            s = self._solicitud_pendiente(agente)
            if s:
                self.con.execute("UPDATE solicitudes SET atendida=1 WHERE num=?", (s[0],))
            self._hist(agente, "eleccion_propuesta", f"perfil {num} origen={origen} eleccion={eleccion_num}", "sistema")
        return num

    def aprobar_eleccion(self, agente, actor="usuario", motivo="elección aprobada por el usuario") -> dict:
        p = self.propuesto(agente)
        if p is None:
            raise ValueError("no hay ninguna elección propuesta para " + agente)
        if p["datos"] is None:
            raise ValueError("la elección propuesta está dañada: " + ",".join(p["problemas"]))
        return self._aplicar(agente, p["datos"], None, "eleccion", "*", None, p["datos_json"], motivo,
                             "importante", actor, perfil_propuesto=p["num"])

    def rechazar_eleccion(self, agente, actor="usuario") -> int:
        if actor != "usuario":
            raise PermissionError("solo el usuario rechaza una elección")
        p = self.propuesto(agente)
        if p is None:
            raise ValueError("no hay ninguna elección propuesta para " + agente)
        with self.con:
            self.con.execute("UPDATE perfiles SET estado='rechazado' WHERE num=?", (p["num"],))
            self._hist(agente, "eleccion_rechazada", f"perfil {p['num']}", "usuario")
        return p["num"]

    # --- edición, restablecimiento y reversión (usuario) -------------------------------------
    @staticmethod
    def _con_valor(datos, campo, valor) -> dict:
        nuevo = json.loads(json.dumps(datos))
        if campo == "rasgos":
            nuevo["rasgos"] = valor
        else:
            g, k = campo.split(".")
            nuevo[g][k] = valor
        return nuevo

    @staticmethod
    def _valor(datos, campo):
        if campo == "rasgos":
            return datos["rasgos"]
        g, k = campo.split(".")
        return datos[g][k]

    def editar(self, agente, campo, valor, actor="usuario", motivo="edición del usuario") -> dict:
        self._agente(agente)
        if campo not in CAMPOS:
            raise ValueError(f"campo no editable: {campo!r} (solo {', '.join(CAMPOS)})")
        actual = self.perfil(agente)["datos"]
        nuevo = self._con_valor(actual, campo, valor)
        return self._aplicar(agente, nuevo, "usuario", "usuario", campo,
                             json.dumps(self._valor(actual, campo), ensure_ascii=False),
                             json.dumps(valor, ensure_ascii=False), motivo,
                             "importante" if campo == "rasgos" else "menor", actor)

    def restablecer(self, agente, a="base", actor="usuario") -> dict:
        """«base»: perfil neutral sin rasgos. «inicial»: la primera elección aprobada del agente."""
        self._agente(agente)
        if a == "base":
            datos = PERFIL_BASE
        elif a == "inicial":
            r = self.con.execute("SELECT * FROM perfiles WHERE agente=? AND origen IN ('simulado','qwen') AND "
                                 "estado IN ('vigente','sustituido') ORDER BY version LIMIT 1", (agente,)).fetchone()
            if r is None:
                raise ValueError("no hay ninguna elección aprobada a la que volver")
            fila = self._fila_perfil(r)
            if fila["datos"] is None:
                raise ValueError("la elección inicial está dañada: " + ",".join(fila["problemas"]))
            datos = fila["datos"]
        else:
            raise ValueError("restablecer a 'base' o 'inicial'")
        return self._aplicar(agente, datos, "restablecimiento", "restablecimiento", "*", None, _canonico(datos),
                             f"restablecido a {a}", "importante", actor)

    def revertir_ultimo(self, agente, actor="usuario") -> dict:
        """Deshace el ÚLTIMO cambio aplicado, solo si el perfil vigente es el que ese cambio produjo."""
        self._agente(agente)
        c = self.con.execute("SELECT * FROM cambios WHERE agente=? AND estado='aplicado' ORDER BY num DESC LIMIT 1",
                             (agente,)).fetchone()
        if c is None:
            raise ValueError("no hay cambios aplicados que revertir")
        v = self._por_estado(agente, "vigente")
        if v is None or v["num"] != c["perfil_resultante"]:
            raise ValueError("el perfil cambió después de ese cambio: usa restablecer o editar")
        if c["perfil_previo"] is None:
            datos = PERFIL_BASE
        else:
            fila = self._fila_perfil(self.con.execute("SELECT * FROM perfiles WHERE num=?",
                                                      (c["perfil_previo"],)).fetchone())
            if fila["datos"] is None:
                raise ValueError("la versión anterior está dañada: " + ",".join(fila["problemas"]))
            datos = fila["datos"]
        out = self._aplicar(agente, datos, "reversion", "reversion", "*", None, _canonico(datos),
                            f"reversión del cambio {c['num']}", "importante", actor)
        with self.con:
            self.con.execute("UPDATE cambios SET estado='revertido' WHERE num=?", (c["num"],))
            self._hist(agente, "cambio_revertido", f"cambio {c['num']}", actor)
        return dict(out, revertido=c["num"])

    # --- experiencias -------------------------------------------------------------------------
    def registrar_experiencia(self, agente, tipo, descripcion, fuente, referencia=None, run_id=None):
        """Devuelve el número o None si ya existía (misma referencia: importación idempotente).
        Verificada = la aporta el sistema (con referencia comprobable) o el usuario; lo que afirma un
        agente se guarda SIEMPRE como no verificado."""
        self._agente(agente)
        if tipo not in TIPOS_EXPERIENCIA or fuente not in FUENTES:
            raise ValueError("tipo o fuente de experiencia desconocidos")
        d = sanea.limpiar(descripcion, 300)
        if not d:
            raise ValueError("la experiencia necesita una descripción")
        ref = sanea.limpiar(referencia or "", 120) or None
        verificada = int(fuente in ("sistema", "usuario") and ref is not None)
        activas = self.con.execute("SELECT COUNT(*) FROM experiencias WHERE agente=? AND archivada=0",
                                   (agente,)).fetchone()[0]
        if activas >= min(config.PERSONALIDAD_MAX_EXPERIENCIAS_ACTIVAS, MAX_EXPERIENCIAS_ACTIVAS_DURO):
            raise LimiteExcedido("límite de experiencias activas: archiva algunas antes de añadir más")
        self._espacio()
        try:
            with self.con:
                return self.con.execute(
                    "INSERT INTO experiencias(ts,agente,tipo,descripcion,fuente,verificada,referencia,run_id) "
                    "VALUES(?,?,?,?,?,?,?,?)", (self.ahora(), agente, tipo, d, fuente, verificada, ref, run_id)).lastrowid
        except sqlite3.IntegrityError as e:
            if "UNIQUE" in str(e):
                return None
            raise

    def experiencias(self, agente, activas=True) -> list:
        self._agente(agente)
        return [dict(r) for r in self.con.execute(
            "SELECT * FROM experiencias WHERE agente=? AND (archivada=0 OR ?=0) ORDER BY num",
            (agente, int(activas)))]

    def archivar_experiencia(self, num, actor="usuario"):
        if actor != "usuario":
            raise PermissionError("solo el usuario archiva experiencias")
        r = self.con.execute("SELECT agente FROM experiencias WHERE num=?", (num,)).fetchone()
        if r is None:
            raise KeyError(num)
        with self.con:
            self.con.execute("UPDATE experiencias SET archivada=1 WHERE num=?", (num,))
            self._hist(r[0], "experiencia_archivada", f"experiencia {num}", "usuario")

    def importar_resumen(self, resumen: dict, run_id: str) -> dict:
        """Experiencias de un summary.json. Un almacén REAL solo acepta ejecuciones con el modelo real y
        uno SIMULADO solo ejecuciones simuladas: lo simulado nunca se convierte en experiencia real."""
        simulado = bool(resumen.get("simulado", True))
        if simulado != (self.almacen == "simulado"):
            raise ValueError("esa ejecución es " + ("SIMULADA" if simulado else "real") + " y este almacén es "
                             + self.almacen + ": no se mezclan")
        nuevas = sum(self.importar_tarea(t, run_id)["nuevas"] for t in resumen.get("tareas") or [])
        return {"nuevas": nuevas, "simulado": simulado}

    def importar_tarea(self, tarea: dict, run_id: str) -> dict:
        nuevas = 0
        for ag, tipo, desc, ref in experiencias_de_tarea(tarea, run_id):
            if self.registrar_experiencia(ag, tipo, desc, "sistema", ref, run_id) is not None:
                nuevas += 1
        return {"nuevas": nuevas}

    # --- adaptación gradual (solo propuestas; las decide el usuario) ---------------------------
    def proponer_adaptaciones(self, agente) -> dict:
        self._agente(agente)
        ahora = _parse_ts(self.ahora())
        ult = self.con.execute("SELECT ts FROM cambios WHERE agente=? AND origen='adaptacion' ORDER BY num DESC "
                               "LIMIT 1", (agente,)).fetchone()
        if ult and (ahora is None or _parse_ts(ult[0]) is None
                    or ahora - _parse_ts(ult[0]) < timedelta(hours=config.PERSONALIDAD_HORAS_ENTRE_PROPUESTAS)):
            return {"propuestas": [], "motivo": "frecuencia: ya hubo una propuesta reciente"}
        pend = self.con.execute("SELECT campo FROM cambios WHERE agente=? AND estado='pendiente'", (agente,)).fetchall()
        tope = min(config.PERSONALIDAD_MAX_CAMBIOS_PENDIENTES, MAX_PENDIENTES_DURO)
        if len(pend) >= tope:
            return {"propuestas": [], "motivo": "demasiadas propuestas pendientes"}
        campos_pend = {p[0] for p in pend}
        libres = {}
        for r in self.con.execute(
                "SELECT e.num, e.tipo FROM experiencias e WHERE e.agente=? AND e.verificada=1 AND e.archivada=0 "
                "AND NOT EXISTS (SELECT 1 FROM cambio_experiencias c WHERE c.experiencia_num = e.num) ORDER BY e.num",
                (agente,)):
            libres.setdefault(r[1], []).append(r[0])
        actual = self.perfil(agente)["datos"]
        candidatos, notas = {}, []
        for tipo, (solo, campo, paso) in REGLAS.items():
            nums = libres.get(tipo, [])
            if (solo and agente not in solo) or len(nums) < config.PERSONALIDAD_MIN_EXPERIENCIAS:
                continue
            candidatos.setdefault(campo, []).append((tipo, paso, nums))
        propuestas = []
        for campo, opciones in sorted(candidatos.items()):
            if campo in campos_pend or len(campos_pend) + len(propuestas) >= tope:
                continue
            valores = {self._paso(actual, campo, paso) for _t, paso, _n in opciones}
            if len(valores) > 1:
                notas.append(f"{campo}: experiencias contradictorias ({', '.join(t for t, _p, _n in opciones)}); "
                             "no se propone nada")
                continue
            nuevo = valores.pop()
            antes = self._valor(actual, campo)
            if nuevo is None or nuevo == antes:
                continue
            tipos = ", ".join(t for t, _p, _n in opciones)
            with self.con:
                c = self.con.execute(
                    "INSERT INTO cambios(ts,agente,campo,antes,despues,motivo,importancia,origen,estado) "
                    "VALUES(?,?,?,?,?,?,'menor','adaptacion','pendiente')",
                    (self.ahora(), agente, campo, json.dumps(antes), json.dumps(nuevo),
                     sanea.limpiar(f"{sum(len(n) for _t, _p, n in opciones)} experiencias verificadas: {tipos}", 300)))
                for _t, _p, nums in opciones:
                    for n in nums:
                        self.con.execute("INSERT INTO cambio_experiencias(cambio_num, experiencia_num) VALUES(?,?)",
                                         (c.lastrowid, n))
                self._hist(agente, "adaptacion_propuesta", f"cambio {c.lastrowid}: {campo} {antes} -> {nuevo}",
                           "sistema")
            propuestas.append(c.lastrowid)
        return {"propuestas": propuestas, "notas": notas}

    @staticmethod
    def _paso(datos, campo, paso):
        """Un solo paso (gradual). Devuelve el valor nuevo o None si ya está en el extremo."""
        actual = RegistroPersonalidad._valor(datos, campo)
        if isinstance(paso, bool):
            return paso
        v = actual + paso
        return v if 1 <= v <= 5 else None

    def cambios(self, agente, estado=None) -> list:
        self._agente(agente)
        return [dict(r) for r in self.con.execute(
            "SELECT * FROM cambios WHERE agente=? AND (? IS NULL OR estado=?) ORDER BY num", (agente, estado, estado))]

    def aprobar_cambio(self, num, actor="usuario") -> dict:
        c = self.con.execute("SELECT * FROM cambios WHERE num=?", (num,)).fetchone()
        if c is None or c["estado"] != "pendiente":
            raise ValueError("solo se aprueba un cambio pendiente")
        actual = self.perfil(c["agente"])["datos"]
        if json.dumps(self._valor(actual, c["campo"])) != c["antes"]:
            raise ValueError("el perfil cambió desde la propuesta: recházala y vuelve a proponer")
        nuevo = self._con_valor(actual, c["campo"], json.loads(c["despues"]))
        return self._aplicar(c["agente"], nuevo, "adaptacion", "adaptacion", c["campo"], c["antes"], c["despues"],
                             c["motivo"], c["importancia"], actor, cambio_existente=num)

    def rechazar_cambio(self, num, actor="usuario"):
        if actor != "usuario":
            raise PermissionError("solo el usuario rechaza propuestas")
        c = self.con.execute("SELECT agente, estado FROM cambios WHERE num=?", (num,)).fetchone()
        if c is None or c["estado"] != "pendiente":
            raise ValueError("solo se rechaza un cambio pendiente")
        with self.con:
            self.con.execute("UPDATE cambios SET estado='rechazado', decidido_por='usuario', decidido_ts=? WHERE num=?",
                             (self.ahora(), num))
            self._hist(c["agente"], "cambio_rechazado", f"cambio {num}", "usuario")

    # --- auditoría ----------------------------------------------------------------------------
    def historial(self, agente) -> list:
        self._agente(agente)
        return [dict(r) for r in self.con.execute("SELECT * FROM historial WHERE agente=? ORDER BY num", (agente,))]

    def elecciones(self, agente) -> list:
        self._agente(agente)
        return [dict(r) for r in self.con.execute("SELECT * FROM elecciones WHERE agente=? ORDER BY num", (agente,))]

    def verificar(self) -> list:
        """Problemas de integridad (sin modificar nada)."""
        out = []
        for r in self.con.execute("SELECT * FROM perfiles ORDER BY num"):
            f = self._fila_perfil(r)
            if f["problemas"]:
                out.append(f"perfil {f['num']} ({f['agente']} v{f['version']}): {','.join(f['problemas'])}")
        for ag in AGENTES:
            n = self.con.execute("SELECT COUNT(*) FROM perfiles WHERE agente=? AND estado='vigente'", (ag,)).fetchone()[0]
            if n > 1:
                out.append(f"{ag}: {n} perfiles vigentes")
        if not self.quick_check():
            out.append("quick_check no es 'ok'")
        return out


# Reglas de adaptación: tipo de experiencia -> (agentes a los que aplica | None, campo, paso).
REGLAS = {
    "respuesta_truncada": (None, "estilo.verbosidad", -1),
    "preferencia_usuario_menos_detalle": (None, "estilo.verbosidad", -1),
    "preferencia_usuario_mas_detalle": (None, "estilo.verbosidad", +1),
    "preferencia_usuario_mas_ejemplos": (None, "preferencias.ejemplos", True),
    "critica_sin_evidencia": (("A3",), "preferencias.explicar_razonamiento", True),
    "critica_falsa_posible": (("A3",), "preferencias.explicar_razonamiento", True),
}
_AGENTE_DE_FASE = {f: a for _o, f, a in config.PLAN if f != "voto"}
_AGENTE_DE_FASE["aclaracion"] = "A3"


def experiencias_de_tarea(tarea: dict, run_id: str) -> list:
    """Experiencias VERIFICABLES de una tarea deliberada: (agente, tipo, descripción, referencia).
    Solo hechos que el sistema registró (cita no encontrada, respuesta truncada...), con referencia."""
    out = []
    tid = tarea.get("tarea_id")
    base = f"{sanea.limpiar(str(run_id), 60)}/t{tid}"
    crit = tarea.get("criticas") or {}
    for o in crit.get("objeciones") or []:
        if o.get("estado") in ("cita_no_encontrada", "linea_inexistente"):
            out.append(("A3", "critica_falsa_posible", f"objeción {o.get('n')}: la cita o la línea no aparece en el "
                        "texto (no prueba que la crítica sea falsa)", f"{base}/obj{o.get('n')}"))
        elif o.get("estado") == "sin_evidencia":
            out.append(("A3", "critica_sin_evidencia", f"objeción {o.get('n')} sin evidencia comprobable",
                        f"{base}/obj{o.get('n')}"))
        elif o.get("estado") == "fundamentada":
            out.append(("A3", "critica_fundamentada", f"objeción {o.get('n')} con cita existente",
                        f"{base}/obj{o.get('n')}"))
    if crit.get("formato_revision") == "no_reconocido":
        out.append(("A3", "formato_no_reconocido", "revisión sin objeciones reconocibles", f"{base}/revision"))
    for c in crit.get("contradicciones") or []:
        if c.startswith("replica_acepta_pero_no_aplica:"):
            out.append(("A1", "acepta_sin_aplicar", "aceptó una objeción y el fragmento siguió igual",
                        f"{base}/{c.split(':', 1)[1]}"))
    for fase, term in sorted((tarea.get("terminaciones") or {}).items()):
        ag = _AGENTE_DE_FASE.get(fase)
        if ag and term not in (None, "completa"):
            out.append((ag, "respuesta_truncada", f"respuesta de {fase} terminada como {term}", f"{base}/{fase}"))
    return out


# ============================ V2-E.5-r3: contrato de integración (solo validación) ==============
CONTRATO = "eq2/personalidad"
VERSION_CONTRATO = "1.0"
CLAVES_CONTRATO = ("contrato", "version_contrato", "agente", "perfil", "origen", "creado", "notas")
CLAVES_ORIGEN = ("tipo", "proveedor", "version_modulo")
TIPOS_ORIGEN = ("modulo_externo", "simulado", "qwen")


def validar_contrato(doc) -> dict:
    """Valida un documento del CONTRATO de personalidad v1 (p. ej. producido por un módulo externo).
    Solo valida: no guarda, no aprueba y no activa nada. Un documento válido, en el futuro, solo podrá
    entrar como PROPUESTA pendiente de aprobación del usuario. {valida, categoria, errores, perfil}."""
    if not isinstance(doc, dict):
        return _resultado(["invalida:no_es_objeto"])
    errores = []
    for k in doc:
        if k not in CLAVES_CONTRATO:
            errores.append(("maliciosa:clave_prohibida:" if _prohibida(str(k), _PROHIBIDAS_CLAVE)
                            else "fuera_del_esquema:clave_desconocida:") + str(k)[:40])
    for k in ("contrato", "version_contrato", "agente", "perfil", "origen", "creado"):
        if k not in doc:
            errores.append("fuera_del_esquema:falta:" + k)
    if doc.get("contrato", CONTRATO) != CONTRATO:
        errores.append("invalida:contrato_desconocido")
    v = doc.get("version_contrato", VERSION_CONTRATO)
    if not (isinstance(v, str) and re.match(r"^1\.\d{1,3}$", v)):
        errores.append("invalida:version_contrato_no_admitida")
    if "agente" in doc and doc["agente"] not in AGENTES:
        errores.append("invalida:agente")
    o = doc.get("origen")
    if "origen" in doc:
        if not isinstance(o, dict):
            errores.append("invalida:tipo:origen")
        else:
            for k in o:
                if k not in CLAVES_ORIGEN:
                    errores.append(("maliciosa:clave_prohibida:" if _prohibida(str(k), _PROHIBIDAS_CLAVE)
                                    else "fuera_del_esquema:clave_desconocida:") + "origen." + str(k)[:30])
            if o.get("tipo") not in TIPOS_ORIGEN:
                errores.append("invalida:origen.tipo")
            for k in ("proveedor", "version_modulo"):
                if not isinstance(o.get(k), str) or not 1 <= len(o[k]) <= 80:
                    errores.append(f"invalida:origen.{k}")
    if "creado" in doc and _parse_ts(doc["creado"]) is None:
        errores.append("invalida:creado")
    if "notas" in doc and (not isinstance(doc["notas"], str) or len(doc["notas"]) > 300
                           or _SOSPECHOSO.search(doc["notas"])):
        errores.append("maliciosa:texto_sospechoso" if isinstance(doc["notas"], str) and _SOSPECHOSO.search(
            doc["notas"]) else "invalida:notas")
    r = validar_perfil(doc.get("perfil")) if "perfil" in doc else None
    if r is not None and not r["valida"]:
        errores += r["errores"]
    if errores:
        return _resultado(errores)
    return {"valida": True, "categoria": "valida", "errores": [], "perfil": r["perfil"],
            "nota": "válido según el contrato v1: NO se ha guardado ni activado"}


# ============================ elector ==========================================================
class ElectorPersonalidad:
    """Elección inicial: UNA llamada por agente (+1 reintento), secuencial e independiente."""

    def __init__(self, reg: RegistroPersonalidad):
        self.reg = reg

    def elegir(self, llamar, simulado: bool, modelo=None, agentes=AGENTES, autorizado=False) -> dict:
        """`llamar(agente, mensajes, max_tokens) -> (texto | None, fallo | None)`."""
        if not (config.PERSONALIDAD_ELECCION_HABILITADA or autorizado):
            raise EleccionDeshabilitada("la elección de personalidad está desactivada (requiere autorización "
                                        "explícita del usuario)")
        origen = "simulado" if simulado else "qwen"
        if origen == "qwen" and not modelo:
            raise ValueError("una elección real exige el nombre del modelo")
        res, llamadas = {}, 0
        for ag in agentes:
            self.reg._agente(ag)
            if not self.reg.necesita_eleccion(ag):
                res[ag] = {"estado": "ya_elegida", "llamadas": 0}
                continue
            errores, hecho, n = (), False, 0
            for intento in range(1, config.PERSONALIDAD_MAX_INTENTOS_AGENTE + 1):
                if self.reg.intentos_recientes(ag) >= config.PERSONALIDAD_MAX_INTENTOS_DIA:
                    res[ag] = {"estado": "limite_frecuencia", "llamadas": n, "errores": list(errores)}
                    break
                mensajes = mensajes_eleccion(ag, errores)
                texto, fallo = llamar(ag, mensajes, config.PERSONALIDAD_MAX_TOKENS)
                n += 1
                llamadas += 1
                v = (validar_respuesta(texto) if fallo is None else
                     _resultado(["invalida:llamada_fallida:" + sanea.limpiar(str(fallo), 60)]))
                enum = self.reg.registrar_intento(ag, origen, modelo, intento, mensajes, texto or "", v,
                                                  config.PERSONALIDAD_MAX_TOKENS)
                if v["valida"]:
                    pnum = self.reg.registrar_propuesta(ag, v["perfil"], origen, enum)
                    res[ag] = {"estado": "propuesta_pendiente_de_aprobacion", "perfil_num": pnum, "llamadas": n,
                               "perfil": v["perfil"]}
                    hecho = True
                    break
                errores = tuple(v["errores"])
            if not hecho and ag not in res:
                with self.reg.con:
                    self.reg._hist(ag, "eleccion_no_valida", ", ".join(errores)[:500], "sistema")
                res[ag] = {"estado": "no_valida", "llamadas": n, "errores": list(errores)}
        return {"origen": origen, "modelo": modelo, "agentes": res, "llamadas": llamadas,
                "nota": ("ELECCIÓN SIMULADA: no la generó Qwen" if simulado else
                         "elección generada por el modelo local; queda PROPUESTA hasta que el usuario la apruebe")}


def llamar_con_backend(backend, plazo_s=None):
    """Adaptador sencillo `llamar` sobre un backend (pruebas y demostraciones simuladas)."""
    def llamar(agente, mensajes, max_tokens):
        try:
            r = backend.completar(list(mensajes), max_tokens, plazo_s or config.SEG_POR_LLAMADA)
        except ErrorInferencia as e:
            return None, e.motivo
        return (r.texto if isinstance(getattr(r, "texto", None), str) else None), None
    return llamar
