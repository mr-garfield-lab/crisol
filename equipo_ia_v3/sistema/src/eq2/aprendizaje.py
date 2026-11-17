"""V2-E.6: aprendizaje ACOTADO y AUDITABLE por agente (una base SQLite por agente en `aprendizaje/`).

Distingue cuatro cosas que NO son lo mismo:
  recordar     guardar un recuerdo (nace como «hipotesis» o «sin_verificar», nunca verificado);
  recuperar    devolverlo al prompt con sus METADATOS (tipo, confianza, estado, fuente, tarea/turno,
               fecha y contradicciones), nunca solo el texto;
  actualizar   cambiar su estado SOLO con evidencia registrada (historial inmutable de evidencias y
               transiciones; la BASE impide que un voto, una opinión, el consenso o una evaluación
               simulada verifiquen o refuten nada);
  transferir   demostrar que un recuerdo verificado cambia la respuesta en un caso NUEVO, comparando con
               un agente sin ese recuerdo (`evaluacion_aprendizaje.py`, SIMULADO).
La persistencia en SQLite por sí sola NO es aprendizaje.

Estados: hipotesis, sin_verificar, verificada_por_prueba, refutada, supersedida.
Tipos de fuente/evidencia: observado (resultado registrado por el sistema), voto, opinion,
evaluacion_simulada, feedback_humano (solo el usuario, con autorización explícita), dato_externo
(con huella SHA-256 de lo consultado), prueba_estatica (EJECUCIÓN registrada de un verificador).
V2-E.6-r2 (auditoría adversarial, caso A): solo cambian el estado
  * prueba_estatica VINCULADA a una ejecución que este módulo realiza él mismo con `probar()`: verificador
    registrado en código, artefacto completo y su SHA-256, parámetros, resultado, esperado y huella. La
    evidencia no puede afirmar un resultado: lo deriva la ejecución, y la base lo impone (CHECK + disparador).
    `auditar()` RE-EJECUTA cada prueba registrada y señala las que no se reproducen;
  * feedback_humano (CLI con --autorizo).
observado y dato_externo quedan como evidencia de APOYO (se registran, no cambian el estado): en V2-E.6 una
llamada con un detalle inventado bastaba para «verificar».
NUNCA verifican ni refutan: voto, opinion, evaluacion_simulada. Una confianza verbal de un voto u
opinión se guarda siempre como «baja».
Protección contra contaminación (caso B): `contaminacion.analizar()` rechaza o pone en CUARENTENA los textos
instructivos (multilingüe, con plegado de ofuscaciones y cargas codificadas); lo que está en cuarentena se
guarda para auditoría pero nunca se recupera para un prompt. Además se deduplican, se detectan
contradicciones y caducan.
El sistema NUNCA se autoedita: este módulo solo escribe en su base.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import unicodedata
from datetime import datetime, timedelta

from . import config, contaminacion, sanea
from .memoria import EsquemaIncompatible, _Base, ahora_iso

ESQUEMA_APRENDIZAJE = "2"                # V2-E.6-r2: ejecuciones de prueba y cuarentena
ESTADOS = ("hipotesis", "sin_verificar", "verificada_por_prueba", "refutada", "supersedida")
VIGENTES = ("hipotesis", "sin_verificar", "verificada_por_prueba")
FUENTES = ("observado", "voto", "opinion", "evaluacion_simulada", "feedback_humano", "dato_externo",
           "prueba_estatica")
FUENTES_PROBATORIAS = ("feedback_humano", "prueba_estatica")   # V2-E.6-r2 (V2-E.6: + observado, dato_externo)
MAX_ARTEFACTO = 20_000
TIPOS = ("hecho", "hipotesis", "leccion", "criterio")
MAX_RECUERDOS = 400
MAX_TEXTO = 500
MIN_RELEVANCIA = 0.08
DIAS_CADUCIDAD = {"voto": 30, "opinion": 30, "evaluacion_simulada": 30, "observado": 180,
                  "prueba_estatica": 365, "feedback_humano": 365, "dato_externo": 180}

DDL = """
CREATE TABLE IF NOT EXISTS meta(clave TEXT PRIMARY KEY, valor TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS recuerdos(
  num INTEGER PRIMARY KEY, id TEXT NOT NULL UNIQUE, creado TEXT NOT NULL,
  agente TEXT NOT NULL CHECK(agente IN ('A1','A2','A3')),
  tipo TEXT NOT NULL CHECK(tipo IN ('hecho','hipotesis','leccion','criterio')),
  texto TEXT NOT NULL CHECK(length(texto) BETWEEN 1 AND 500),
  sha256 TEXT NOT NULL CHECK(length(sha256) = 64),
  confianza TEXT NOT NULL CHECK(confianza IN ('baja','media','alta')),
  estado_inicial TEXT NOT NULL CHECK(estado_inicial IN ('hipotesis','sin_verificar')),
  fuente TEXT NOT NULL CHECK(fuente IN ('observado','voto','opinion','evaluacion_simulada','feedback_humano',
                                        'dato_externo','prueba_estatica')),
  fuente_ref TEXT, tarea_ref TEXT, turno_ref TEXT, sesion_ref TEXT,
  ambito TEXT NOT NULL DEFAULT '', caduca TEXT,
  sustituye TEXT REFERENCES recuerdos(id),
  cuarentena TEXT,
  CHECK(fuente NOT IN ('voto','opinion','evaluacion_simulada') OR confianza = 'baja'));
CREATE TABLE IF NOT EXISTS ejecuciones(
  num INTEGER PRIMARY KEY, id TEXT NOT NULL UNIQUE, ts TEXT NOT NULL,
  recuerdo_id TEXT NOT NULL REFERENCES recuerdos(id),
  verificador TEXT NOT NULL, version_verificador TEXT NOT NULL,
  artefacto TEXT NOT NULL CHECK(length(artefacto) BETWEEN 1 AND 20000),
  artefacto_sha256 TEXT NOT NULL CHECK(length(artefacto_sha256) = 64),
  parametros TEXT NOT NULL, resultado TEXT NOT NULL CHECK(resultado IN ('cumple','no_cumple')),
  esperado TEXT NOT NULL CHECK(esperado IN ('cumple','no_cumple')),
  detalle TEXT NOT NULL, huella TEXT NOT NULL CHECK(length(huella) = 64));
CREATE TABLE IF NOT EXISTS evidencias(
  num INTEGER PRIMARY KEY, id TEXT NOT NULL UNIQUE, ts TEXT NOT NULL,
  recuerdo_id TEXT NOT NULL REFERENCES recuerdos(id),
  tipo TEXT NOT NULL CHECK(tipo IN ('observado','voto','opinion','evaluacion_simulada','feedback_humano',
                                    'dato_externo','prueba_estatica')),
  efecto TEXT NOT NULL CHECK(efecto IN ('apoya','refuta','neutra')),
  ref TEXT, detalle TEXT NOT NULL CHECK(length(detalle) BETWEEN 1 AND 1000),
  actor TEXT NOT NULL CHECK(actor IN ('sistema','usuario','agente')),
  autorizado_por TEXT, sha256_ref TEXT, ejecucion_id TEXT UNIQUE REFERENCES ejecuciones(id),
  CHECK(tipo <> 'prueba_estatica' OR efecto = 'neutra' OR ejecucion_id IS NOT NULL),
  CHECK(ejecucion_id IS NULL OR tipo = 'prueba_estatica'),
  CHECK(tipo <> 'feedback_humano' OR (actor = 'usuario' AND autorizado_por IS NOT NULL)),
  CHECK(actor <> 'agente' OR tipo IN ('voto','opinion')),
  CHECK(tipo <> 'dato_externo' OR (sha256_ref IS NOT NULL AND length(sha256_ref) = 64)),
  CHECK(tipo <> 'prueba_estatica' OR actor = 'sistema'));
CREATE TABLE IF NOT EXISTS transiciones(
  num INTEGER PRIMARY KEY, ts TEXT NOT NULL, recuerdo_id TEXT NOT NULL REFERENCES recuerdos(id),
  de TEXT, a TEXT NOT NULL CHECK(a IN ('hipotesis','sin_verificar','verificada_por_prueba','refutada','supersedida')),
  evidencia_id TEXT REFERENCES evidencias(id),
  motivo TEXT NOT NULL CHECK(length(motivo) BETWEEN 1 AND 500),
  actor TEXT NOT NULL CHECK(actor IN ('sistema','usuario')));
CREATE TABLE IF NOT EXISTS contradicciones(
  num INTEGER PRIMARY KEY, ts TEXT NOT NULL, a TEXT NOT NULL REFERENCES recuerdos(id),
  b TEXT NOT NULL REFERENCES recuerdos(id), motivo TEXT NOT NULL, UNIQUE(a, b));
CREATE TABLE IF NOT EXISTS usos(
  num INTEGER PRIMARY KEY, ts TEXT NOT NULL, recuerdo_id TEXT NOT NULL REFERENCES recuerdos(id),
  tarea_ref TEXT, relevancia REAL, contexto TEXT);

CREATE TRIGGER IF NOT EXISTS apr_rec_no_modificar BEFORE UPDATE ON recuerdos
  BEGIN SELECT RAISE(ABORT, 'los recuerdos no se modifican: se registra uno nuevo que los sustituye'); END;
CREATE TRIGGER IF NOT EXISTS apr_rec_no_borrar BEFORE DELETE ON recuerdos
  BEGIN SELECT RAISE(ABORT, 'los recuerdos no se borran'); END;
CREATE TRIGGER IF NOT EXISTS apr_rec_limite BEFORE INSERT ON recuerdos
  WHEN (SELECT COUNT(*) FROM recuerdos) >= 400
  BEGIN SELECT RAISE(ABORT, 'límite de recuerdos del agente'); END;
CREATE TRIGGER IF NOT EXISTS apr_ev_no_modificar BEFORE UPDATE ON evidencias
  BEGIN SELECT RAISE(ABORT, 'la historia de evidencias es inmutable'); END;
CREATE TRIGGER IF NOT EXISTS apr_ev_no_borrar BEFORE DELETE ON evidencias
  BEGIN SELECT RAISE(ABORT, 'la historia de evidencias es inmutable'); END;
CREATE TRIGGER IF NOT EXISTS apr_tr_no_modificar BEFORE UPDATE ON transiciones
  BEGIN SELECT RAISE(ABORT, 'el historial de estados es inmutable'); END;
CREATE TRIGGER IF NOT EXISTS apr_tr_no_borrar BEFORE DELETE ON transiciones
  BEGIN SELECT RAISE(ABORT, 'el historial de estados es inmutable'); END;
CREATE TRIGGER IF NOT EXISTS apr_tr_encadenada BEFORE INSERT ON transiciones
  WHEN NOT ((NEW.de IS NULL AND NOT EXISTS (SELECT 1 FROM transiciones WHERE recuerdo_id = NEW.recuerdo_id))
    OR NEW.de = (SELECT a FROM transiciones WHERE recuerdo_id = NEW.recuerdo_id ORDER BY num DESC LIMIT 1))
  BEGIN SELECT RAISE(ABORT, 'transición fuera de orden: «de» no es el estado vigente'); END;
CREATE TRIGGER IF NOT EXISTS apr_tr_permitidas BEFORE INSERT ON transiciones
  WHEN NOT ((NEW.de IS NULL AND NEW.a IN ('hipotesis','sin_verificar'))
    OR (NEW.de IN ('hipotesis','sin_verificar') AND NEW.a IN ('verificada_por_prueba','refutada','supersedida'))
    OR (NEW.de = 'hipotesis' AND NEW.a = 'sin_verificar')
    OR (NEW.de = 'verificada_por_prueba' AND NEW.a IN ('refutada','supersedida','sin_verificar'))
    OR (NEW.de = 'refutada' AND NEW.a = 'supersedida'))
  BEGIN SELECT RAISE(ABORT, 'transición de recuerdo no permitida'); END;
CREATE TRIGGER IF NOT EXISTS apr_tr_verificar_con_prueba BEFORE INSERT ON transiciones
  WHEN NEW.a = 'verificada_por_prueba' AND NOT EXISTS (SELECT 1 FROM evidencias WHERE id = NEW.evidencia_id
    AND recuerdo_id = NEW.recuerdo_id AND efecto = 'apoya'
    AND tipo IN ('feedback_humano','prueba_estatica'))
  BEGIN SELECT RAISE(ABORT, 'verificar exige evidencia probatoria que APOYE este recuerdo (un voto, una opinión, el consenso o una simulación no verifican)'); END;
CREATE TRIGGER IF NOT EXISTS apr_tr_refutar_con_prueba BEFORE INSERT ON transiciones
  WHEN NEW.a = 'refutada' AND NOT EXISTS (SELECT 1 FROM evidencias WHERE id = NEW.evidencia_id
    AND recuerdo_id = NEW.recuerdo_id AND efecto = 'refuta'
    AND tipo IN ('feedback_humano','prueba_estatica'))
  BEGIN SELECT RAISE(ABORT, 'refutar exige evidencia probatoria que REFUTE este recuerdo'); END;
CREATE TRIGGER IF NOT EXISTS apr_tr_revocar_por_usuario BEFORE INSERT ON transiciones
  WHEN NEW.de = 'verificada_por_prueba' AND NEW.a = 'sin_verificar' AND NOT EXISTS (SELECT 1 FROM evidencias
    WHERE id = NEW.evidencia_id AND recuerdo_id = NEW.recuerdo_id AND tipo = 'feedback_humano')
  BEGIN SELECT RAISE(ABORT, 'revocar una verificación exige feedback humano autorizado'); END;
CREATE TRIGGER IF NOT EXISTS apr_tr_supersedida_con_sustituto BEFORE INSERT ON transiciones
  WHEN NEW.a = 'supersedida' AND NOT EXISTS (SELECT 1 FROM recuerdos WHERE sustituye = NEW.recuerdo_id)
  BEGIN SELECT RAISE(ABORT, 'supersedida exige un recuerdo nuevo que lo sustituya'); END;
CREATE TRIGGER IF NOT EXISTS apr_ej_no_modificar BEFORE UPDATE ON ejecuciones
  BEGIN SELECT RAISE(ABORT, 'las ejecuciones de prueba son inmutables'); END;
CREATE TRIGGER IF NOT EXISTS apr_ej_no_borrar BEFORE DELETE ON ejecuciones
  BEGIN SELECT RAISE(ABORT, 'las ejecuciones de prueba son inmutables'); END;
CREATE TRIGGER IF NOT EXISTS apr_ev_prueba_vinculada BEFORE INSERT ON evidencias
  WHEN NEW.tipo = 'prueba_estatica' AND NEW.efecto <> 'neutra' AND NOT EXISTS (SELECT 1 FROM ejecuciones
    WHERE id = NEW.ejecucion_id AND recuerdo_id = NEW.recuerdo_id
      AND ((resultado = esperado AND NEW.efecto = 'apoya') OR (resultado <> esperado AND NEW.efecto = 'refuta')))
  BEGIN SELECT RAISE(ABORT, 'una prueba_estatica debe derivar de una ejecución registrada de ESTE recuerdo y su efecto del resultado'); END;
CREATE TRIGGER IF NOT EXISTS apr_ctr_no_borrar BEFORE DELETE ON contradicciones
  BEGIN SELECT RAISE(ABORT, 'las contradicciones registradas no se borran'); END;
"""
_PELIGROSO = [re.compile(p, re.IGNORECASE) for p in (
    r"\bignora(r)?\b.{0,40}\b(instrucci|regla|norma|restricci)",
    r"\b(cambia|modifica|edita|desactiva|activa|sobrescribe|borra)\w*\b.{0,40}\b(config|c[oó]digo|permiso|"
    r"regla|disparador|trigger|modo_b|prompt|verificador|manifiesto|\.py\b)",
    r"\bmodo_b(_habilitado)?\s*=", r"\b(rm\s+-rf|sudo|chmod|curl|wget|pip\s+install|subprocess|os\.system)\b",
    r"\b(eres|ahora eres|act[uú]a como)\b.{0,30}\b(administrador|root|sin restricciones)",
    r"\bsiempre\s+(aprueba|vota\s+aprobar|conf[ií]a)\b",
)]
_VACIAS = set("el la los las un una de del al y o en con por para que es se lo le su como mas pero muy ya hay ser".split())


VERIFICADORES = {}            # nombre -> (versión, función(artefacto: str, parametros: dict) -> (cumple, detalle))


def registrar_verificador(nombre, version, fn):
    """Registra un verificador DESDE CÓDIGO (nunca desde datos ni desde el texto de un agente). No se pueden
    reemplazar: un nombre ya registrado con otra función se rechaza."""
    if not re.fullmatch(r"[a-z][a-z0-9_]{2,40}", str(nombre)) or not callable(fn):
        raise ValueError("verificador no válido")
    previo = VERIFICADORES.get(nombre)
    if previo is not None and previo[1] is not fn:
        raise ValueError(f"el verificador {nombre!r} ya está registrado")
    VERIFICADORES[nombre] = (str(version), fn)


def _regla_declarativa(artefacto, parametros):
    from . import laboratorios                       # importación diferida (evita ciclos)
    return laboratorios.evaluar_regla(parametros.get("regla"), artefacto, parametros.get("numeracion", "archivo"))


registrar_verificador("regla_declarativa", "1", _regla_declarativa)


def _huella_ejecucion(d: dict) -> str:
    campos = {k: d[k] for k in ("recuerdo_id", "verificador", "version_verificador", "artefacto_sha256", "parametros",
                                "resultado", "esperado", "detalle")}
    return hashlib.sha256(json.dumps(campos, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


class RecuerdoRechazado(ValueError):
    """El texto intenta cambiar instrucciones, permisos, configuración o código (contaminación)."""


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", t)).strip()


def palabras(t: str) -> set:
    return {p for p in _norm(t).split() if len(p) >= 3 and p not in _VACIAS}


_NEG = {"no", "nunca", "jamas", "sin", "ningun", "ninguna", "ninguno"}


def polaridades(texto: str) -> dict:
    """{raíz (6 letras): {"+"|"-"}} — "-" si la palabra va precedida (a 2 palabras) de una negación."""
    w = _norm(texto).split()
    out = {}
    for i, p in enumerate(w):
        if len(p) < 4 or p in _VACIAS or p in _NEG:
            continue
        out.setdefault(p[:6], set()).add("-" if any(x in _NEG for x in w[max(0, i - 2):i]) else "+")
    return out


def _sha(t: str) -> str:
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def es_peligroso(texto: str):
    """Motivo de RECHAZO o None (compatibilidad V2-E.6). Ver `analizar_contenido` para la cuarentena."""
    for rx in _PELIGROSO:
        m = rx.search(texto or "")
        if m:
            return m.group(0)[:80]
    r = contaminacion.analizar(texto or "")
    return r["motivos"][0][:120] if r["veredicto"] == "rechazado" else None


def analizar_contenido(texto: str) -> dict:
    """{veredicto: aceptado|cuarentena|rechazado, motivos}: expresiones de V2-E.6 + `contaminacion.analizar`."""
    for rx in _PELIGROSO:
        m = rx.search(texto or "")
        if m:
            return {"veredicto": "rechazado", "motivos": [m.group(0)[:80]]}
    return contaminacion.analizar(texto or "")


def _iso_mas(ahora_txt: str, dias: int) -> str:
    try:
        base = datetime.fromisoformat(ahora_txt)
    except ValueError:
        base = datetime.now()
    return (base + timedelta(days=dias)).isoformat(timespec="seconds")


class AprendizajeAgente(_Base):
    """Base de aprendizaje de UN agente. Solo se escribe a través de estos métodos."""

    def __init__(self, ruta, agente, ahora=ahora_iso):
        if agente not in config.AGENTES:
            raise ValueError("agente desconocido")
        super().__init__(ruta, ahora)
        self.agente = agente
        self.con.executescript(DDL)
        # «IF NOT EXISTS» omite en silencio un disparador homónimo de otra tabla: se comprueba cada uno.
        reales = {r[0]: r[1] for r in self.con.execute("SELECT name, tbl_name FROM sqlite_master WHERE type='trigger'")}
        mal = sorted(n for n, t in re.findall(r"CREATE TRIGGER IF NOT EXISTS (\w+) BEFORE \w+ ON (\w+)", DDL)
                     if reales.get(n) != t)
        if mal:
            self.con.close()
            raise EsquemaIncompatible("disparadores ausentes o sobre otra tabla: " + ", ".join(mal))
        for clave, valor in (("agente", agente), ("esquema_aprendizaje", ESQUEMA_APRENDIZAJE)):
            previo = self._meta_get(clave)
            if previo is not None and previo != valor:
                self.con.close()
                raise EsquemaIncompatible(f"{self.ruta.name}: {clave}={previo}, se esperaba {valor}")
            self._meta_set(clave, valor)

    # --- recordar ------------------------------------------------------------------------------
    def recordar(self, tipo, texto, fuente, confianza="baja", fuente_ref=None, tarea_ref=None, turno_ref=None,
                 sesion_ref=None, ambito="", estado="hipotesis", sustituye=None, dias=None,
                 autorizado_por=None, sha256_ref=None) -> dict:
        """Guarda un recuerdo NO verificado. Devuelve {id, nuevo, contradicciones}. Si ya existe un recuerdo
        vigente con el mismo texto normalizado, NO se duplica (se devuelve el existente)."""
        if tipo not in TIPOS or fuente not in FUENTES or confianza not in ("baja", "media", "alta"):
            raise ValueError("tipo, fuente o confianza desconocidos")
        if estado not in ("hipotesis", "sin_verificar"):
            raise ValueError("un recuerdo nace como «hipotesis» o «sin_verificar»; verificar exige evidencia")
        t = sanea.limpiar(texto, MAX_TEXTO + 1)
        if not t or len(t) > MAX_TEXTO:
            raise ValueError(f"el texto debe tener entre 1 y {MAX_TEXTO} caracteres (no se recorta en silencio)")
        analisis = analizar_contenido(t)
        if analisis["veredicto"] == "rechazado":
            raise RecuerdoRechazado("recuerdo rechazado (contenido instructivo: intenta anular controles, reglas, "
                                    f"permisos o código): {analisis['motivos'][0]!r}")
        cuarentena = "; ".join(analisis["motivos"])[:500] if analisis["veredicto"] == "cuarentena" else None
        if fuente in ("voto", "opinion", "evaluacion_simulada"):
            confianza = "baja"                         # la confianza verbal no es prueba
        if fuente == "feedback_humano" and not autorizado_por:
            raise PermissionError("un recuerdo de feedback humano exige autorización explícita")
        if fuente == "dato_externo" and not (isinstance(sha256_ref, str) and len(sha256_ref) == 64):
            raise ValueError("un dato externo exige la huella SHA-256 de lo consultado")
        clave = _sha(_norm(t))
        for r in self.vigentes():
            if _sha(_norm(r["texto"])) == clave and r["id"] != sustituye:
                return {"id": r["id"], "nuevo": False, "contradicciones": [], "cuarentena": r["cuarentena"]}
        ahora = self.ahora()
        with self.con:
            c = self.con.execute(
                "INSERT INTO recuerdos(id,creado,agente,tipo,texto,sha256,confianza,estado_inicial,fuente,fuente_ref,"
                "tarea_ref,turno_ref,sesion_ref,ambito,caduca,sustituye,cuarentena) "
                "VALUES(printf('RC-%06d', COALESCE((SELECT MAX(num) FROM recuerdos), 0) + 1),"
                "?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (ahora, self.agente, tipo, t, _sha(t), confianza, estado, fuente,
                 None if fuente_ref is None else str(fuente_ref)[:120],
                 None if tarea_ref is None else str(tarea_ref)[:40],
                 None if turno_ref is None else str(turno_ref)[:40],
                 None if sesion_ref is None else str(sesion_ref)[:40],
                 sanea.limpiar(ambito, 200), _iso_mas(ahora, dias or DIAS_CADUCIDAD[fuente]), sustituye, cuarentena))
            rid = self.con.execute("SELECT id FROM recuerdos WHERE num=?", (c.lastrowid,)).fetchone()[0]
            self.con.execute("INSERT INTO transiciones(ts,recuerdo_id,de,a,evidencia_id,motivo,actor) "
                             "VALUES(?,?,NULL,?,NULL,?,'sistema')", (ahora, rid, estado, f"creado desde {fuente}"))
            self.con.execute("INSERT INTO evidencias(id,ts,recuerdo_id,tipo,efecto,ref,detalle,actor,autorizado_por,"
                             "sha256_ref) VALUES(printf('EV-%06d', COALESCE((SELECT MAX(num) FROM evidencias), 0) + 1),"
                             "?,?,?,'neutra',?,?,?,?,?)",
                             (ahora, rid, fuente, None if fuente_ref is None else str(fuente_ref)[:120],
                              "origen del recuerdo (no cambia su estado)",
                              "agente" if fuente in ("voto", "opinion") else
                              "usuario" if fuente == "feedback_humano" else "sistema",
                              None if autorizado_por is None else sanea.limpiar(autorizado_por, 80), sha256_ref))
        ctr = self._detectar_contradicciones(rid, t) if cuarentena is None else []
        if sustituye:
            self.transicion(sustituye, "supersedida", f"sustituido por {rid}")
        return {"id": rid, "nuevo": True, "contradicciones": ctr, "cuarentena": cuarentena}

    def _detectar_contradicciones(self, rid, texto) -> list:
        """Heurística DETERMINISTA: comparten >= 3 raíces (>= 25 % del más corto) y alguna raíz común aparece
        afirmada en uno y SOLO negada en el otro («sort modifica» / «sort no modifica»). Se registra como
        contradicción (para que el prompt la muestre); no decide cuál es cierto."""
        pa = polaridades(texto)
        out = []
        for r in self.vigentes():
            if r["id"] == rid:
                continue
            pb = polaridades(r["texto"])
            comunes = set(pa) & set(pb)
            if len(comunes) < 3 or len(comunes) < 0.25 * min(len(pa), len(pb)):
                continue
            choque = sorted(w for w in comunes if ("+" in pa[w] and pb[w] == {"-"}) or ("+" in pb[w] and pa[w] == {"-"}))
            if choque:
                with self.con:
                    self.con.execute("INSERT OR IGNORE INTO contradicciones(ts,a,b,motivo) VALUES(?,?,?,?)",
                                     (self.ahora(), r["id"], rid, "polaridad opuesta en: " + ", ".join(choque[:5])))
                out.append(r["id"])
        return out

    # --- actualizar con evidencia ------------------------------------------------------------------
    def evidencia(self, recuerdo_id, tipo, efecto, detalle, ref=None, actor="sistema", autorizado_por=None,
                  sha256_ref=None) -> str:
        if tipo not in FUENTES or efecto not in ("apoya", "refuta", "neutra"):
            raise ValueError("tipo o efecto de evidencia desconocido")
        if tipo == "prueba_estatica" and efecto != "neutra":
            raise ValueError("evidencia rechazada: una prueba_estatica solo se registra ejecutándola con probar() "
                             "(el resultado no se puede declarar)")
        self.recuerdo(recuerdo_id)
        d = sanea.limpiar(detalle, 1000)
        if not d:
            raise ValueError("la evidencia necesita un detalle")
        try:
            with self.con:
                c = self.con.execute(
                    "INSERT INTO evidencias(id,ts,recuerdo_id,tipo,efecto,ref,detalle,actor,autorizado_por,sha256_ref) "
                    "VALUES(printf('EV-%06d', COALESCE((SELECT MAX(num) FROM evidencias), 0) + 1),?,?,?,?,?,?,?,?,?)",
                    (self.ahora(), recuerdo_id, tipo, efecto, None if ref is None else str(ref)[:200], d, actor,
                     None if autorizado_por is None else sanea.limpiar(autorizado_por, 80), sha256_ref))
        except sqlite3.IntegrityError as e:
            raise ValueError(f"evidencia rechazada: {e}") from None
        return self.con.execute("SELECT id FROM evidencias WHERE num=?", (c.lastrowid,)).fetchone()[0]

    def transicion(self, recuerdo_id, a, motivo, evidencia_id=None, actor="sistema") -> str:
        de = self.estado(recuerdo_id)
        try:
            with self.con:
                self.con.execute("INSERT INTO transiciones(ts,recuerdo_id,de,a,evidencia_id,motivo,actor) "
                                 "VALUES(?,?,?,?,?,?,?)", (self.ahora(), recuerdo_id, de, a, evidencia_id,
                                                           sanea.limpiar(motivo, 500) or "-", actor))
        except sqlite3.IntegrityError as e:
            raise ValueError(f"transición rechazada: {e}") from None
        return a

    def aplicar_evidencia(self, recuerdo_id, tipo, efecto, detalle, **kw) -> dict:
        """Registra la evidencia y, si es PROBATORIA, actualiza el estado (apoya -> verificada_por_prueba;
        refuta -> refutada). Un voto/opinión/simulación se registra pero NO cambia el estado."""
        actor = kw.get("actor", "sistema")
        eid = self.evidencia(recuerdo_id, tipo, efecto, detalle, **kw)
        estado = self.estado(recuerdo_id)
        nuevo = estado
        if tipo in FUENTES_PROBATORIAS and efecto != "neutra":
            destino = "verificada_por_prueba" if efecto == "apoya" else "refutada"
            if estado != destino and estado not in ("refutada", "supersedida"):
                nuevo = self.transicion(recuerdo_id, destino, f"{tipo}: {detalle[:200]}", eid,
                                        "usuario" if actor == "usuario" else "sistema")
        return {"evidencia": eid, "antes": estado, "despues": nuevo, "cambio": nuevo != estado,
                "probatoria": tipo in FUENTES_PROBATORIAS}

    def probar(self, recuerdo_id, verificador, artefacto, parametros=None, esperado=True, motivo="") -> dict:
        """EJECUTA un verificador registrado sobre `artefacto` (texto) y registra la ejecución completa; la
        evidencia «prueba_estatica» se DERIVA del resultado (apoya si coincide con `esperado`, si no refuta) y se
        vincula a esa ejecución. Después cambia el estado como cualquier evidencia probatoria."""
        if verificador not in VERIFICADORES:
            raise ValueError(f"verificador no registrado: {verificador!r}")
        if not isinstance(artefacto, str) or not 1 <= len(artefacto) <= MAX_ARTEFACTO:
            raise ValueError(f"el artefacto debe ser texto de 1 a {MAX_ARTEFACTO} caracteres")
        if not isinstance(esperado, bool):
            raise ValueError("esperado debe ser True o False")
        self.recuerdo(recuerdo_id)
        version, fn = VERIFICADORES[verificador]
        prm = json.dumps(parametros or {}, sort_keys=True, ensure_ascii=False)
        cumple, detalle = fn(artefacto, json.loads(prm))
        d = {"recuerdo_id": recuerdo_id, "verificador": verificador, "version_verificador": version,
             "artefacto_sha256": _sha(artefacto), "parametros": prm, "resultado": "cumple" if cumple else "no_cumple",
             "esperado": "cumple" if esperado else "no_cumple", "detalle": sanea.limpiar(str(detalle), 500) or "-"}
        d["huella"] = _huella_ejecucion(d)
        efecto = "apoya" if d["resultado"] == d["esperado"] else "refuta"
        try:
            with self.con:
                c = self.con.execute(
                    "INSERT INTO ejecuciones(id,ts,recuerdo_id,verificador,version_verificador,artefacto,artefacto_sha256,"
                    "parametros,resultado,esperado,detalle,huella) VALUES(printf('EJ-%06d', COALESCE((SELECT MAX(num) "
                    "FROM ejecuciones), 0) + 1),?,?,?,?,?,?,?,?,?,?,?)",
                    (self.ahora(), recuerdo_id, verificador, version, artefacto, d["artefacto_sha256"], prm,
                     d["resultado"], d["esperado"], d["detalle"], d["huella"]))
                ejid = self.con.execute("SELECT id FROM ejecuciones WHERE num=?", (c.lastrowid,)).fetchone()[0]
                c = self.con.execute(
                    "INSERT INTO evidencias(id,ts,recuerdo_id,tipo,efecto,ref,detalle,actor,ejecucion_id) "
                    "VALUES(printf('EV-%06d', COALESCE((SELECT MAX(num) FROM evidencias), 0) + 1),?,?,'prueba_estatica',"
                    "?,?,?,'sistema',?)",
                    (self.ahora(), recuerdo_id, efecto, f"{verificador} v{version}",
                     sanea.limpiar(f"{motivo} | {d['detalle']}".strip(" |"), 1000) or "-", ejid))
                eid = self.con.execute("SELECT id FROM evidencias WHERE num=?", (c.lastrowid,)).fetchone()[0]
        except sqlite3.IntegrityError as e:
            raise ValueError(f"evidencia rechazada: {e}") from None
        self._comprobar_ejecucion(ejid)                        # vinculación comprobada ANTES de cambiar el estado
        estado = nuevo = self.estado(recuerdo_id)
        destino = "verificada_por_prueba" if efecto == "apoya" else "refutada"
        if estado != destino and estado not in ("refutada", "supersedida"):
            nuevo = self.transicion(recuerdo_id, destino, f"prueba_estatica {ejid}: {d['detalle'][:200]}", eid)
        return {"evidencia": eid, "ejecucion": ejid, "resultado": d["resultado"], "efecto": efecto, "antes": estado,
                "despues": nuevo, "cambio": nuevo != estado, "probatoria": True}

    def _comprobar_ejecucion(self, ejid) -> dict:
        """La ejecución existe, su huella y la del artefacto cuadran, y al RE-EJECUTAR el verificador se obtiene el
        mismo resultado. Lanza ValueError si no."""
        r = self.con.execute("SELECT * FROM ejecuciones WHERE id=?", (ejid,)).fetchone()
        if r is None:
            raise ValueError(f"ejecución inexistente: {ejid}")
        d = dict(r)
        if _sha(d["artefacto"]) != d["artefacto_sha256"] or _huella_ejecucion(d) != d["huella"]:
            raise ValueError(f"la ejecución {ejid} está alterada (huella)")
        if d["verificador"] not in VERIFICADORES or VERIFICADORES[d["verificador"]][0] != d["version_verificador"]:
            raise ValueError(f"la ejecución {ejid} usa un verificador que no está registrado en esta versión")
        cumple, _det = VERIFICADORES[d["verificador"]][1](d["artefacto"], json.loads(d["parametros"]))
        if ("cumple" if cumple else "no_cumple") != d["resultado"]:
            raise ValueError(f"la ejecución {ejid} no se reproduce")
        return d

    def feedback_humano(self, recuerdo_id, efecto, motivo, autorizado_por, revocar=False) -> dict:
        """Validación HUMANA explícita (la CLI exige --autorizo). `revocar`: devuelve un recuerdo verificado a
        sin_verificar."""
        if not autorizado_por:
            raise PermissionError("el feedback humano exige autorización explícita")
        if revocar:
            eid = self.evidencia(recuerdo_id, "feedback_humano", "neutra", motivo, actor="usuario",
                                 autorizado_por=autorizado_por)
            antes = self.estado(recuerdo_id)
            self.transicion(recuerdo_id, "sin_verificar", f"revocado por el usuario: {motivo}", eid, "usuario")
            return {"evidencia": eid, "antes": antes, "despues": "sin_verificar", "cambio": True, "probatoria": True}
        return self.aplicar_evidencia(recuerdo_id, "feedback_humano", efecto, motivo, actor="usuario",
                                      autorizado_por=autorizado_por)

    # --- consultar ---------------------------------------------------------------------------------
    def recuerdo(self, rid) -> dict:
        r = self.con.execute("SELECT * FROM recuerdos WHERE id=?", (rid,)).fetchone()
        if r is None:
            raise KeyError(rid)
        d = dict(r)
        d["estado"] = self.estado(rid)
        d["integro"] = _sha(d["texto"]) == d["sha256"]
        return d

    def estado(self, rid) -> str:
        r = self.con.execute("SELECT a FROM transiciones WHERE recuerdo_id=? ORDER BY num DESC LIMIT 1",
                             (rid,)).fetchone()
        if r is None:
            raise KeyError(rid)
        return r[0]

    def vigentes(self, incluir_caducados=True) -> list:
        ahora = self.ahora()
        out = []
        for r in self.con.execute("SELECT r.*, (SELECT a FROM transiciones t WHERE t.recuerdo_id = r.id "
                                  "ORDER BY t.num DESC LIMIT 1) AS estado FROM recuerdos r ORDER BY r.num"):
            d = dict(r)
            if d["estado"] in VIGENTES and (incluir_caducados or not d["caduca"] or d["caduca"] > ahora):
                out.append(d)
        return out

    def historial(self, rid) -> dict:
        return {"recuerdo": self.recuerdo(rid),
                "evidencias": [dict(r) for r in self.con.execute(
                    "SELECT * FROM evidencias WHERE recuerdo_id=? ORDER BY num", (rid,))],
                "transiciones": [dict(r) for r in self.con.execute(
                    "SELECT * FROM transiciones WHERE recuerdo_id=? ORDER BY num", (rid,))],
                "ejecuciones": [dict(r) for r in self.con.execute(
                    "SELECT * FROM ejecuciones WHERE recuerdo_id=? ORDER BY num", (rid,))],
                "contradicciones": self.contradicciones_de(rid)}

    def contradicciones_de(self, rid) -> list:
        return sorted({r[0] for r in self.con.execute(
            "SELECT CASE WHEN a=? THEN b ELSE a END FROM contradicciones WHERE a=? OR b=?", (rid, rid, rid))})

    # --- recuperar -----------------------------------------------------------------------------------
    def recuperar(self, consulta, n=config.MEMORIAS_POR_PROMPT, tarea_ref=None, registrar_uso=True) -> list:
        """Recuerdos VIGENTES y NO CADUCADOS relevantes para `consulta`, sin duplicados, con metadatos.
        Orden: verificados primero, luego relevancia y antigüedad. Excluye refutados y supersedidos."""
        q = palabras(consulta)
        if not q:
            return []
        cand, vistos = [], set()
        for r in self.vigentes(incluir_caducados=False):
            if r["cuarentena"]:                    # V2-E.6-r2: contenido instructivo: nunca va a un prompt
                continue
            pr = palabras(r["texto"] + " " + (r["ambito"] or ""))
            rel = len(q & pr) / len(q | pr) if pr else 0.0
            clave = _sha(_norm(r["texto"]))
            if rel < MIN_RELEVANCIA or clave in vistos:
                continue
            vistos.add(clave)
            cand.append((0 if r["estado"] == "verificada_por_prueba" else 1, -rel, r["num"], r, rel))
        out = []
        for *_, r, rel in sorted(cand, key=lambda x: x[:3])[: int(n)]:
            out.append({"id": r["id"], "agente": r["agente"], "tipo": r["tipo"], "texto": r["texto"],
                        "confianza": r["confianza"], "estado": r["estado"], "fuente": r["fuente"],
                        "fuente_ref": r["fuente_ref"], "tarea_ref": r["tarea_ref"], "turno_ref": r["turno_ref"],
                        "fecha": (r["creado"] or "")[:10], "caduca": (r["caduca"] or "")[:10],
                        "contradicciones": self.contradicciones_de(r["id"]), "relevancia": round(rel, 3)})
        if registrar_uso and out:
            with self.con:
                for m in out:
                    self.con.execute("INSERT INTO usos(ts,recuerdo_id,tarea_ref,relevancia,contexto) VALUES(?,?,?,?,?)",
                                     (self.ahora(), m["id"], None if tarea_ref is None else str(tarea_ref)[:40],
                                      m["relevancia"], sanea.limpiar(consulta, 120)))
        return out

    def auditar(self) -> dict:
        """Integridad (SHA-256), recuento por estado/fuente y comprobaciones de las reglas."""
        estados, fuentes, alterados = {}, {}, []
        for r in self.con.execute("SELECT id, texto, sha256, fuente FROM recuerdos ORDER BY num"):
            e = self.estado(r["id"])
            estados[e] = estados.get(e, 0) + 1
            fuentes[r["fuente"]] = fuentes.get(r["fuente"], 0) + 1
            if _sha(r["texto"]) != r["sha256"]:
                alterados.append(r["id"])
        mal = [r[0] for r in self.con.execute(
            "SELECT t.recuerdo_id FROM transiciones t JOIN evidencias e ON e.id = t.evidencia_id "
            "WHERE t.a IN ('verificada_por_prueba','refutada') AND e.tipo IN ('voto','opinion','evaluacion_simulada')")]
        no_reproducibles = []
        for (ejid,) in self.con.execute("SELECT id FROM ejecuciones ORDER BY num").fetchall():
            try:
                self._comprobar_ejecucion(ejid)
            except ValueError as e:
                no_reproducibles.append(f"{ejid}: {e}")
        sin_ejecucion = [r[0] for r in self.con.execute(
            "SELECT t.recuerdo_id FROM transiciones t JOIN evidencias e ON e.id = t.evidencia_id "
            "WHERE t.a IN ('verificada_por_prueba','refutada') AND e.tipo = 'prueba_estatica' AND e.ejecucion_id IS NULL")]
        cuarentena = self.con.execute("SELECT COUNT(*) FROM recuerdos WHERE cuarentena IS NOT NULL").fetchone()[0]
        faltan = sorted(n for n in ("apr_tr_verificar_con_prueba", "apr_tr_refutar_con_prueba", "apr_rec_no_modificar",
                                    "apr_ev_no_modificar", "apr_tr_no_modificar", "apr_tr_permitidas",
                                    "apr_ev_prueba_vinculada", "apr_ej_no_modificar", "apr_ej_no_borrar")
                        if not self.con.execute("SELECT 1 FROM sqlite_master WHERE type='trigger' AND name=?",
                                                (n,)).fetchone())
        return {"agente": self.agente, "por_estado": estados, "por_fuente": fuentes, "alterados": alterados,
                "verificados_por_voto": mal, "disparadores_ausentes": faltan,
                "pruebas_no_reproducibles": no_reproducibles, "pruebas_sin_ejecucion": sin_ejecucion,
                "en_cuarentena": cuarentena,
                "ejecuciones": self.con.execute("SELECT COUNT(*) FROM ejecuciones").fetchone()[0],
                "evidencias": self.con.execute("SELECT COUNT(*) FROM evidencias").fetchone()[0],
                "usos": self.con.execute("SELECT COUNT(*) FROM usos").fetchone()[0],
                "ok": not alterados and not mal and not faltan and not no_reproducibles and not sin_ejecucion}


def formatear_para_prompt(m) -> str:
    """Una línea con METADATOS + texto. Acepta un dict de `recuperar` (o de memoria r3) o un texto."""
    if isinstance(m, str):
        return "- " + sanea.limpiar(m, config.MEMORIA_PROMPT_CHARS)
    estado = m.get("estado") or m.get("verificacion") or "sin_verificar"
    meta = [m.get("id") or f"M{m.get('num', '?')}", m.get("tipo") or "?", f"conf={m.get('confianza') or 'baja'}",
            f"estado={estado}", f"fuente={m.get('fuente') or 'desconocida'}"]
    ref = "/".join(str(x) for x in (m.get("tarea_ref"), m.get("turno_ref")) if x not in (None, ""))
    if ref:
        meta.append(f"tarea/turno={ref}")
    if m.get("fecha"):
        meta.append(str(m["fecha"]))
    if m.get("contradicciones"):
        meta.append("contradice:" + ",".join(m["contradicciones"][:3]))
    return "- [" + " | ".join(meta) + "] " + sanea.limpiar(m.get("texto", ""), config.MEMORIA_PROMPT_CHARS)


def de_memoria_r3(fila: dict) -> dict:
    """Adapta una fila de memoria.MemoriaAgente.buscar (r3) al formato con metadatos."""
    return {"id": f"M{fila.get('id')}", "tipo": fila.get("tipo"), "texto": fila.get("texto"),
            "confianza": fila.get("confianza"), "estado": fila.get("verificacion") or "sin_verificar",
            "fuente": "deliberacion_r3", "tarea_ref": None, "turno_ref": fila.get("turno_ref"),
            "fecha": (fila.get("creado") or "")[:10], "contradicciones": []}


def exportar(apr: AprendizajeAgente) -> str:
    """JSON completo y ordenado (auditoría externa); no incluye nada fuera de la base del agente."""
    return json.dumps({"agente": apr.agente, "esquema": ESQUEMA_APRENDIZAJE,
                       "recuerdos": [apr.historial(r[0]) for r in apr.con.execute("SELECT id FROM recuerdos ORDER BY num")],
                       "auditoria": apr.auditar()}, ensure_ascii=False, indent=1, sort_keys=True, default=str)
