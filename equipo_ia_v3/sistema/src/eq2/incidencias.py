"""V2-E.2: registro PERSISTENTE de incidencias (SQLite = fuente de verdad).

Ubicación (dentro del laboratorio): <base>/incidencias/incidencias.db, y subcarpetas
evidencias/<INC-…>/, informes/ y regresiones/.

Garantías IMPUESTAS POR LA BASE (disparadores), no solo por el código:
  * Las incidencias NO se borran. Evidencias, intentos, historial y paquetes son de solo anexar.
  * 'verificada' exige una evidencia 'prueba_real' con resultado 'superada' (imposible en V2-E.2:
    el Modo B está deshabilitado y el código se niega a registrar pruebas reales).
  * 'corregida_sin_verificar' exige una evidencia NO declarativa (estática, simulada o real) superada:
    que un agente diga «corregido» no basta.
  * Una causa 'confirmada' exige alguna evidencia no declarativa.
Garantías del código: permisos por actor (los agentes no pueden verificar, descartar ni confirmar
causas o dependencias), transiciones de estado explícitas y grafo de dependencias sin ciclos.

V2-E.3 (esquema 2):
  * `causa_respaldo` distingue QUÉ respalda una causa confirmada: análisis estático, simulación o
    prueba real (la base exige que exista una evidencia de ese tipo; prueba real imposible aquí).
    `respaldo()` da la etiqueta: sin_causa · hipotesis · respaldada_estatico ·
    respaldada_simulacion · confirmada_prueba_real.
  * Tabla `entregas` (solo anexar): qué incidencia y qué fragmento de cada evidencia recibió cada
    agente en cada ejecución; es la cola persistente de lo pendiente de entregar.

V2-E.4 (esquema 3):
  * Tabla `hipotesis` (HIP-…): hipótesis LOCALIZADAS (archivo + patrón) con autor, versión y estado
    propuesta · consistente · respaldada · refutada · ambigua. La base exige, para 'respaldada', un
    experimento de REPRODUCCIÓN y otro de CONTROL que la apoyen (un solo experimento no basta).
  * Evidencias con trazabilidad: hipótesis evaluada, versión, confianza y limitaciones.
  * Experimentos con `firma` única (no se duplican al reintentar), `rol` y `hipotesis_id`; un
    experimento terminado no se puede modificar. Regresiones con `origen` único (idempotentes).
  * Tabla `revisiones` (solo anexar): la revisión de A3 de cada corrección (no es evidencia del fallo).
  * `ficha()` / `etiqueta()`: qué se comprobó realmente y con qué (nunca «corregida» a secas).

V2-E.4-r2 (esquema 4) — NINGÚN camino, manual o automático, eleva una causa sin la evidencia exigida:
  * Tabla `observaciones` (solo anexar): lo que el MOTOR observó en cada versión de cada ejecución
    (incidencia presente o ausente, archivo y SHA-256 de su texto).
  * Una hipótesis solo pasa a 'respaldada' si su experimento de REPRODUCCIÓN coincide con una
    observación con la incidencia PRESENTE y su experimento de CONTROL con una observación con la
    incidencia AUSENTE (misma ejecución, versión, archivo y SHA-256 del texto).
  * Una causa solo puede quedar 'confirmada' (a) con respaldo 'simulacion' apuntando a una hipótesis
    RESPALDADA de esa misma incidencia, o (b) con respaldo 'prueba_real' y una prueba real registrada
    (imposible mientras el Modo B esté deshabilitado). Ninguna incidencia nace confirmada.
  * Si una hipótesis deja de estar respaldada, la base devuelve su causa a hipótesis (y lo anota).
  Límite: esto protege frente a los caminos del sistema y al texto de los agentes; quien tenga acceso
  local puede editar el archivo SQLite a mano.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3

from . import config, memoria, rutas, sanea

ESQUEMA_INCIDENCIAS = "4"                 # V2-E.4-r2: observaciones y confirmación con procedencia
AGENTES = ("A1", "A2", "A3")
ACTORES = AGENTES + ("motor", "laboratorio", "usuario")
ESTADOS = ("abierta", "en_analisis", "asignada", "en_correccion", "corregida_sin_verificar",
           "verificada", "reabierta", "descartada")
PENDIENTES = ("abierta", "en_analisis", "asignada", "en_correccion", "reabierta")
TRANSICIONES = {
    "abierta": {"en_analisis", "asignada", "descartada"},
    "en_analisis": {"asignada", "abierta", "descartada"},
    "asignada": {"en_correccion", "en_analisis", "descartada"},
    "en_correccion": {"corregida_sin_verificar", "asignada", "en_analisis"},
    "corregida_sin_verificar": {"verificada", "reabierta"},
    "verificada": {"reabierta"},
    "reabierta": {"en_analisis", "asignada", "descartada"},
    "descartada": {"reabierta"},
}
# Estados que un AGENTE nunca puede fijar.
SOLO_NO_AGENTES = {"verificada", "descartada", "corregida_sin_verificar"}
TIPOS_EVIDENCIA = ("analisis_estatico", "simulacion", "prueba_real", "observacion",
                   "declaracion_agente", "registro")
NO_DECLARATIVAS = ("analisis_estatico", "simulacion", "prueba_real")
MAX_EVIDENCIA_BYTES = 64_000

DDL = """
CREATE TABLE IF NOT EXISTS meta(clave TEXT PRIMARY KEY, valor TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS incidencias(
  num INTEGER PRIMARY KEY, id TEXT NOT NULL UNIQUE, firma TEXT UNIQUE,
  creada TEXT NOT NULL, actualizada TEXT NOT NULL,
  titulo TEXT NOT NULL CHECK(length(titulo) BETWEEN 1 AND 200),
  descripcion TEXT CHECK(descripcion IS NULL OR length(descripcion) <= 2000),
  categoria TEXT NOT NULL,
  gravedad INTEGER NOT NULL CHECK(gravedad BETWEEN 1 AND 5),
  impacto INTEGER NOT NULL CHECK(impacto BETWEEN 1 AND 5),
  dificultad INTEGER NOT NULL CHECK(dificultad BETWEEN 1 AND 5),
  confianza REAL NOT NULL CHECK(confianza >= 0 AND confianza <= 1),
  causa TEXT, causa_estado TEXT NOT NULL DEFAULT 'hipotesis'
    CHECK(causa_estado IN ('hipotesis','confirmada','descartada')),
  estado TEXT NOT NULL CHECK(estado IN ('abierta','en_analisis','asignada','en_correccion',
    'corregida_sin_verificar','verificada','reabierta','descartada')),
  asignado TEXT CHECK(asignado IS NULL OR asignado IN ('A1','A2','A3','usuario')),
  criterios_json TEXT NOT NULL DEFAULT '[]', origen TEXT NOT NULL,
  prioridad REAL, bloqueada_por_limite INTEGER NOT NULL DEFAULT 0,
  causa_respaldo TEXT NOT NULL DEFAULT 'ninguno'
    CHECK(causa_respaldo IN ('ninguno','analisis_estatico','simulacion','prueba_real')),
  causa_hipotesis TEXT,
  CHECK(causa_respaldo = 'ninguno' OR causa_estado = 'confirmada'));
CREATE TABLE IF NOT EXISTS archivos_afectados(
  incidencia_id TEXT NOT NULL REFERENCES incidencias(id), ruta TEXT NOT NULL, sha256 TEXT,
  UNIQUE(incidencia_id, ruta, sha256));
CREATE TABLE IF NOT EXISTS evidencias(
  num INTEGER PRIMARY KEY, incidencia_id TEXT REFERENCES incidencias(id), experimento_id TEXT,
  creada TEXT NOT NULL,
  tipo TEXT NOT NULL CHECK(tipo IN ('analisis_estatico','simulacion','prueba_real','observacion',
    'declaracion_agente','registro')),
  resultado TEXT NOT NULL CHECK(resultado IN ('superada','fallida','informativa')),
  descripcion TEXT NOT NULL, archivo TEXT, sha256 TEXT,
  actor TEXT NOT NULL CHECK(actor IN ('A1','A2','A3','motor','laboratorio','usuario')),
  hipotesis_id TEXT, version INTEGER,
  confianza REAL CHECK(confianza IS NULL OR (confianza >= 0 AND confianza <= 1)), limitaciones TEXT,
  CHECK(tipo <> 'declaracion_agente' OR resultado = 'informativa'));
CREATE TABLE IF NOT EXISTS intentos(
  num INTEGER PRIMARY KEY, incidencia_id TEXT NOT NULL REFERENCES incidencias(id), creado TEXT NOT NULL,
  agente TEXT NOT NULL CHECK(agente IN ('A1','A2','A3')), descripcion TEXT NOT NULL,
  resultado TEXT NOT NULL CHECK(resultado IN ('pendiente','sin_efecto','parcial','supera_simulacion',
    'supera_estatico','supera_prueba_real','empeora')), version INTEGER);
CREATE TABLE IF NOT EXISTS dependencias(
  origen TEXT NOT NULL REFERENCES incidencias(id), destino TEXT NOT NULL REFERENCES incidencias(id),
  tipo TEXT NOT NULL CHECK(tipo IN ('causa','bloquea','relacionada')),
  certeza TEXT NOT NULL CHECK(certeza IN ('hipotesis','confirmada')), evidencia_num INTEGER,
  creada TEXT NOT NULL, CHECK(origen <> destino),
  CHECK(certeza = 'hipotesis' OR evidencia_num IS NOT NULL), UNIQUE(origen, destino, tipo));
CREATE TABLE IF NOT EXISTS historial(
  num INTEGER PRIMARY KEY, incidencia_id TEXT NOT NULL, ts TEXT NOT NULL, campo TEXT NOT NULL,
  antes TEXT, despues TEXT, actor TEXT NOT NULL, motivo TEXT);
CREATE TABLE IF NOT EXISTS recalculos(num INTEGER PRIMARY KEY, ts TEXT NOT NULL, motivo TEXT, n INTEGER);
CREATE TABLE IF NOT EXISTS paquetes(
  num INTEGER PRIMARY KEY, ts TEXT NOT NULL, agente TEXT, incluidas_json TEXT NOT NULL,
  evidencias_omitidas_json TEXT NOT NULL, pendientes_json TEXT NOT NULL, tokens_est INTEGER);
CREATE TABLE IF NOT EXISTS experimentos(
  num INTEGER PRIMARY KEY, id TEXT NOT NULL UNIQUE, creado TEXT NOT NULL, hipotesis TEXT NOT NULL,
  tipo TEXT NOT NULL CHECK(length(tipo) BETWEEN 3 AND 40 AND tipo NOT GLOB '*[^a-z_]*'),
  entradas_json TEXT NOT NULL, limites_json TEXT NOT NULL,
  estado TEXT NOT NULL CHECK(estado IN ('planificado','completado','abortado')),
  resultado_json TEXT, conclusion TEXT CHECK(conclusion IS NULL OR conclusion IN
    ('apoya','refuta','no_concluyente')), incidencia_id TEXT,
  firma TEXT UNIQUE, rol TEXT CHECK(rol IS NULL OR rol IN ('reproduccion','control')),
  hipotesis_id TEXT, version INTEGER, evidencia_num INTEGER, run_id TEXT, archivo_sha256 TEXT,
  CHECK(rol IS NULL OR (hipotesis_id IS NOT NULL AND run_id IS NOT NULL AND version IS NOT NULL
                        AND archivo_sha256 IS NOT NULL)));
CREATE TABLE IF NOT EXISTS observaciones(
  num INTEGER PRIMARY KEY, ts TEXT NOT NULL, run_id TEXT NOT NULL, version INTEGER NOT NULL,
  incidencia_id TEXT NOT NULL REFERENCES incidencias(id), presente INTEGER NOT NULL CHECK(presente IN (0, 1)),
  archivo TEXT NOT NULL, sha256 TEXT NOT NULL, UNIQUE(run_id, version, incidencia_id, archivo));
CREATE TABLE IF NOT EXISTS revisiones(
  num INTEGER PRIMARY KEY, ts TEXT NOT NULL, run_id TEXT NOT NULL,
  incidencia_id TEXT NOT NULL REFERENCES incidencias(id), version INTEGER NOT NULL,
  agente TEXT NOT NULL CHECK(agente = 'A3'),
  resultado TEXT NOT NULL CHECK(resultado IN ('sin_objeciones','con_objeciones')),
  detalle TEXT, UNIQUE(run_id, incidencia_id, version));
CREATE TABLE IF NOT EXISTS hipotesis(
  num INTEGER PRIMARY KEY, id TEXT NOT NULL UNIQUE, creada TEXT NOT NULL, actualizada TEXT NOT NULL,
  incidencia_id TEXT NOT NULL REFERENCES incidencias(id),
  actor TEXT NOT NULL CHECK(actor IN ('A1','A2','A3','laboratorio','usuario')),
  version INTEGER, texto TEXT NOT NULL CHECK(length(texto) BETWEEN 1 AND 300),
  archivo TEXT NOT NULL CHECK(length(archivo) BETWEEN 1 AND 200),
  patron TEXT NOT NULL CHECK(length(patron) BETWEEN 2 AND 120),
  firma TEXT NOT NULL UNIQUE,
  estado TEXT NOT NULL CHECK(estado IN ('propuesta','consistente','respaldada','refutada','ambigua')),
  motivo TEXT);
CREATE TABLE IF NOT EXISTS entregas(
  num INTEGER PRIMARY KEY, ts TEXT NOT NULL, run_id TEXT NOT NULL,
  agente TEXT NOT NULL CHECK(agente IN ('A1','A2','A3')), paso TEXT NOT NULL,
  incidencia_id TEXT NOT NULL REFERENCES incidencias(id), evidencia_num INTEGER,
  desde INTEGER NOT NULL DEFAULT 0, hasta INTEGER NOT NULL DEFAULT 0, completa INTEGER NOT NULL DEFAULT 1,
  paquete_num INTEGER);
CREATE TABLE IF NOT EXISTS regresiones(
  num INTEGER PRIMARY KEY, id TEXT NOT NULL UNIQUE, creado TEXT NOT NULL,
  incidencia_id TEXT NOT NULL REFERENCES incidencias(id),
  tipo TEXT NOT NULL CHECK(tipo IN ('analisis_estatico','simulacion')),
  entradas_json TEXT NOT NULL, esperado_json TEXT NOT NULL, archivo TEXT, sha256 TEXT,
  origen TEXT UNIQUE, hipotesis_id TEXT);

CREATE TRIGGER IF NOT EXISTS inc_no_borrar BEFORE DELETE ON incidencias
  BEGIN SELECT RAISE(ABORT, 'las incidencias no se eliminan'); END;
CREATE TRIGGER IF NOT EXISTS inc_no_nacer_verificada BEFORE INSERT ON incidencias
  WHEN NEW.estado IN ('verificada','corregida_sin_verificar')
  BEGIN SELECT RAISE(ABORT, 'una incidencia no puede nacer verificada ni corregida'); END;
CREATE TRIGGER IF NOT EXISTS inc_verificada_exige_prueba_real BEFORE UPDATE OF estado ON incidencias
  WHEN NEW.estado = 'verificada' AND NOT EXISTS (SELECT 1 FROM evidencias WHERE
    incidencia_id = NEW.id AND tipo = 'prueba_real' AND resultado = 'superada')
  BEGIN SELECT RAISE(ABORT, 'verificada exige una prueba real superada'); END;
CREATE TRIGGER IF NOT EXISTS inc_corregida_exige_evidencia BEFORE UPDATE OF estado ON incidencias
  WHEN NEW.estado = 'corregida_sin_verificar' AND NOT EXISTS (SELECT 1 FROM evidencias WHERE
    incidencia_id = NEW.id AND tipo IN ('analisis_estatico','simulacion','prueba_real')
    AND resultado = 'superada')
  BEGIN SELECT RAISE(ABORT, 'corregida exige una evidencia no declarativa superada'); END;
CREATE TRIGGER IF NOT EXISTS inc_causa_exige_evidencia BEFORE UPDATE OF causa_estado ON incidencias
  WHEN NEW.causa_estado = 'confirmada' AND NOT EXISTS (SELECT 1 FROM evidencias WHERE
    incidencia_id = NEW.id AND tipo IN ('analisis_estatico','simulacion','prueba_real'))
  BEGIN SELECT RAISE(ABORT, 'una causa confirmada exige evidencia no declarativa'); END;
CREATE TRIGGER IF NOT EXISTS inc_respaldo_exige_evidencia BEFORE UPDATE OF causa_respaldo ON incidencias
  WHEN NEW.causa_respaldo <> 'ninguno' AND NOT EXISTS (SELECT 1 FROM evidencias WHERE
    incidencia_id = NEW.id AND tipo = NEW.causa_respaldo)
  BEGIN SELECT RAISE(ABORT, 'el respaldo de la causa exige una evidencia de ese tipo'); END;
CREATE TRIGGER IF NOT EXISTS inc_respaldo_real_exige_superada BEFORE UPDATE OF causa_respaldo ON incidencias
  WHEN NEW.causa_respaldo = 'prueba_real' AND NOT EXISTS (SELECT 1 FROM evidencias WHERE
    incidencia_id = NEW.id AND tipo = 'prueba_real' AND resultado IN ('superada','fallida'))
  BEGIN SELECT RAISE(ABORT, 'una causa confirmada con prueba real exige esa prueba'); END;
CREATE TRIGGER IF NOT EXISTS rev_no_mod BEFORE UPDATE ON revisiones
  BEGIN SELECT RAISE(ABORT, 'revisiones: solo anexar'); END;
CREATE TRIGGER IF NOT EXISTS rev_no_borrar BEFORE DELETE ON revisiones
  BEGIN SELECT RAISE(ABORT, 'revisiones: solo anexar'); END;
CREATE TRIGGER IF NOT EXISTS hip_no_borrar BEFORE DELETE ON hipotesis
  BEGIN SELECT RAISE(ABORT, 'las hipótesis no se eliminan'); END;
CREATE TRIGGER IF NOT EXISTS hip_no_nacer_respaldada BEFORE INSERT ON hipotesis
  WHEN NEW.estado <> 'propuesta'
  BEGIN SELECT RAISE(ABORT, 'una hipótesis nace propuesta'); END;
CREATE TRIGGER IF NOT EXISTS hip_respaldada_exige_reproduccion_y_control BEFORE UPDATE OF estado ON hipotesis
  WHEN NEW.estado = 'respaldada' AND NOT (
    EXISTS (SELECT 1 FROM experimentos e JOIN observaciones o ON o.run_id = e.run_id AND o.version = e.version
              AND o.incidencia_id = NEW.incidencia_id AND o.archivo = NEW.archivo
              AND o.sha256 = e.archivo_sha256 AND o.presente = 1
            WHERE e.hipotesis_id = NEW.id AND e.incidencia_id = NEW.incidencia_id AND e.rol = 'reproduccion'
              AND e.estado = 'completado' AND e.conclusion = 'apoya')
    AND EXISTS (SELECT 1 FROM experimentos e JOIN observaciones o ON o.run_id = e.run_id AND o.version = e.version
              AND o.incidencia_id = NEW.incidencia_id AND o.archivo = NEW.archivo
              AND o.sha256 = e.archivo_sha256 AND o.presente = 0
            WHERE e.hipotesis_id = NEW.id AND e.incidencia_id = NEW.incidencia_id AND e.rol = 'control'
              AND e.estado = 'completado' AND e.conclusion = 'apoya'))
  BEGIN SELECT RAISE(ABORT, 'respaldada exige reproducción y control sobre versiones observadas por el motor'); END;
CREATE TRIGGER IF NOT EXISTS hip_deja_de_respaldar AFTER UPDATE OF estado ON hipotesis
  WHEN OLD.estado = 'respaldada' AND NEW.estado <> 'respaldada'
  BEGIN
    INSERT INTO historial(incidencia_id, ts, campo, antes, despues, actor, motivo)
      SELECT id, strftime('%Y-%m-%dT%H:%M:%S', 'now'), 'causa_estado', 'confirmada', 'hipotesis', 'laboratorio',
             NEW.id || ' ya no está respaldada' FROM incidencias
      WHERE causa_hipotesis = NEW.id AND causa_estado = 'confirmada';
    UPDATE incidencias SET causa_estado = 'hipotesis', causa_respaldo = 'ninguno', causa_hipotesis = NULL
      WHERE causa_hipotesis = NEW.id AND causa_estado = 'confirmada';
  END;
CREATE TRIGGER IF NOT EXISTS inc_no_nacer_confirmada BEFORE INSERT ON incidencias
  WHEN NEW.causa_estado = 'confirmada' OR NEW.causa_respaldo <> 'ninguno'
  BEGIN SELECT RAISE(ABORT, 'una incidencia no nace con la causa confirmada'); END;
CREATE TRIGGER IF NOT EXISTS inc_confirmada_exige_hipotesis_respaldada
  BEFORE UPDATE OF causa_estado, causa_respaldo, causa_hipotesis ON incidencias
  WHEN NEW.causa_estado = 'confirmada' AND NOT (
    (NEW.causa_respaldo = 'prueba_real' AND EXISTS (SELECT 1 FROM evidencias WHERE incidencia_id = NEW.id
       AND tipo = 'prueba_real' AND resultado IN ('superada','fallida')))
    OR (NEW.causa_respaldo = 'simulacion' AND EXISTS (SELECT 1 FROM hipotesis WHERE id = NEW.causa_hipotesis
       AND incidencia_id = NEW.id AND estado = 'respaldada')))
  BEGIN SELECT RAISE(ABORT, 'una causa confirmada exige una hipótesis respaldada (reproducción y control observados)'); END;
CREATE TRIGGER IF NOT EXISTS obs_no_mod BEFORE UPDATE ON observaciones
  BEGIN SELECT RAISE(ABORT, 'observaciones: solo anexar'); END;
CREATE TRIGGER IF NOT EXISTS obs_no_borrar BEFORE DELETE ON observaciones
  BEGIN SELECT RAISE(ABORT, 'observaciones: solo anexar'); END;
CREATE TRIGGER IF NOT EXISTS hip_refutada_es_final BEFORE UPDATE OF estado ON hipotesis
  WHEN OLD.estado = 'refutada' AND NEW.estado <> 'refutada'
  BEGIN SELECT RAISE(ABORT, 'una hipótesis refutada no vuelve atrás'); END;
CREATE TRIGGER IF NOT EXISTS exp_no_borrar BEFORE DELETE ON experimentos
  BEGIN SELECT RAISE(ABORT, 'los experimentos no se eliminan'); END;
CREATE TRIGGER IF NOT EXISTS exp_terminado_inmutable BEFORE UPDATE ON experimentos
  WHEN OLD.estado <> 'planificado'
  BEGIN SELECT RAISE(ABORT, 'un experimento terminado no se modifica'); END;
CREATE TRIGGER IF NOT EXISTS ent_no_mod BEFORE UPDATE ON entregas
  BEGIN SELECT RAISE(ABORT, 'entregas: solo anexar'); END;
CREATE TRIGGER IF NOT EXISTS ent_no_borrar BEFORE DELETE ON entregas
  BEGIN SELECT RAISE(ABORT, 'entregas: solo anexar'); END;
CREATE TRIGGER IF NOT EXISTS ev_no_mod BEFORE UPDATE ON evidencias
  BEGIN SELECT RAISE(ABORT, 'evidencias: solo anexar'); END;
CREATE TRIGGER IF NOT EXISTS ev_no_borrar BEFORE DELETE ON evidencias
  BEGIN SELECT RAISE(ABORT, 'evidencias: solo anexar'); END;
CREATE TRIGGER IF NOT EXISTS int_no_borrar BEFORE DELETE ON intentos
  BEGIN SELECT RAISE(ABORT, 'intentos: solo anexar'); END;
CREATE TRIGGER IF NOT EXISTS hist_no_mod BEFORE UPDATE ON historial
  BEGIN SELECT RAISE(ABORT, 'historial: solo anexar'); END;
CREATE TRIGGER IF NOT EXISTS hist_no_borrar BEFORE DELETE ON historial
  BEGIN SELECT RAISE(ABORT, 'historial: solo anexar'); END;
CREATE TRIGGER IF NOT EXISTS paq_no_borrar BEFORE DELETE ON paquetes
  BEGIN SELECT RAISE(ABORT, 'paquetes: solo anexar'); END;
CREATE TRIGGER IF NOT EXISTS dep_no_borrar BEFORE DELETE ON dependencias
  BEGIN SELECT RAISE(ABORT, 'dependencias: no se borran'); END;
CREATE TRIGGER IF NOT EXISTS reg_no_borrar BEFORE DELETE ON regresiones
  BEGIN SELECT RAISE(ABORT, 'regresiones: no se borran'); END;
"""


RESPALDOS = ("sin_causa", "hipotesis", "respaldada_estatico", "respaldada_simulacion",
             "confirmada_prueba_real")
ETIQUETA_RESPALDO = {
    "sin_causa": "causa desconocida",
    "hipotesis": "causa HIPÓTESIS (sin evidencia que la respalde)",
    "respaldada_estatico": "causa respaldada por ANÁLISIS ESTÁTICO (no es una prueba real)",
    "respaldada_simulacion": "causa respaldada por SIMULACIÓN (no es una prueba real)",
    "confirmada_prueba_real": "causa CONFIRMADA con prueba real",
}


def respaldo(inc: dict) -> str:
    """Nivel de respaldo de la causa de una incidencia (ver ETIQUETA_RESPALDO)."""
    if inc.get("causa_estado") == "confirmada":
        # Conservador: una confirmación sin tipo de respaldo conocido se trata como hipótesis.
        return {"analisis_estatico": "respaldada_estatico", "simulacion": "respaldada_simulacion",
                "prueba_real": "confirmada_prueba_real"}.get(inc.get("causa_respaldo"), "hipotesis")
    return "hipotesis" if inc.get("causa") else "sin_causa"


ESTADOS_HIPOTESIS = ("propuesta", "consistente", "respaldada", "refutada", "ambigua")
TRANSICIONES_HIPOTESIS = {
    "propuesta": {"consistente", "respaldada", "refutada", "ambigua"},
    "consistente": {"respaldada", "refutada", "ambigua"},
    "respaldada": {"refutada", "ambigua"},
    "ambigua": {"respaldada", "refutada", "consistente"},
    "refutada": set(),
}
FASES = ("detectada", "causa_hipotetica", "causa_respaldada", "correccion_propuesta", "correccion_revisada",
         "comprobada_con_pruebas_disponibles", "verificada_con_prueba_real", "descartada")
VALIDACION_REAL_PENDIENTE = "pendiente (Modo B deshabilitado: no hay pruebas reales)"
REVISION_A3 = "revisión de A3"


class PermisoDenegado(PermissionError):
    pass


class TransicionInvalida(ValueError):
    pass


class CicloDependencias(ValueError):
    pass


def _ident(prefijo, num) -> str:
    return f"{prefijo}-{int(num):06d}"


_ID = re.compile(r"(INC|EXP|REG)-\d{6}")


class RegistroIncidencias(memoria._Base):
    def __init__(self, lab: rutas.Laboratorio, ahora=memoria.ahora_iso):
        self.lab = lab
        lab.crear_base()
        for d in (("incidencias",), ("incidencias", "evidencias"), ("incidencias", "informes"),
                  ("incidencias", "regresiones")):
            lab.crear_dir(*d)
        super().__init__(lab.ruta("incidencias", "incidencias.db"), ahora)
        previo = None
        try:
            previo = self._meta_get("esquema")
        except sqlite3.OperationalError:                    # base nueva: aún no hay tabla meta
            previo = None
        if previo is not None and previo != ESQUEMA_INCIDENCIAS:
            self.con.close()
            raise memoria.EsquemaIncompatible(f"incidencias.db tiene esquema {previo}")
        self.con.executescript(DDL)
        self._meta_set("esquema", ESQUEMA_INCIDENCIAS)

    # --- utilidades -------------------------------------------------------------------------
    @staticmethod
    def _actor(actor):
        if actor not in ACTORES:
            raise PermisoDenegado(f"actor desconocido: {actor!r}")

    def _hist(self, iid, campo, antes, despues, actor, motivo=None):
        self.con.execute("INSERT INTO historial(incidencia_id,ts,campo,antes,despues,actor,motivo) "
                         "VALUES(?,?,?,?,?,?,?)", (iid, self.ahora(), campo,
                                                   None if antes is None else str(antes),
                                                   None if despues is None else str(despues), actor,
                                                   sanea.limpiar(motivo or "", 300) or None))

    def obtener(self, iid) -> dict:
        r = self.con.execute("SELECT * FROM incidencias WHERE id=?", (iid,)).fetchone()
        if r is None:
            raise KeyError(iid)
        d = dict(r)
        d["criterios"] = json.loads(d.pop("criterios_json"))
        return d

    def listar(self, estados=None) -> list:
        filas = self.con.execute("SELECT id FROM incidencias ORDER BY num").fetchall()
        out = [self.obtener(f[0]) for f in filas]
        return [x for x in out if estados is None or x["estado"] in estados]

    # --- incidencias -----------------------------------------------------------------------
    def crear(self, titulo, categoria, gravedad, impacto, dificultad=3, confianza=0.5,
              descripcion=None, causa=None, criterios=(), origen="motor", actor="motor",
              firma=None, archivos=()) -> str:
        """Crea (o devuelve, si `firma` ya existe) una incidencia. Nace 'abierta' e 'hipotesis'."""
        self._actor(actor)
        if firma is not None:
            r = self.con.execute("SELECT id FROM incidencias WHERE firma=?", (firma,)).fetchone()
            if r:
                return r[0]
        crit = [sanea.limpiar(c, 200) for c in list(criterios)[:10]]
        ahora = self.ahora()
        with self.con:
            c = self.con.execute(
                "INSERT INTO incidencias(id,firma,creada,actualizada,titulo,descripcion,categoria,"
                "gravedad,impacto,dificultad,confianza,causa,estado,criterios_json,origen) "
                "VALUES('pendiente',?,?,?,?,?,?,?,?,?,?,?,'abierta',?,?)",
                (firma, ahora, ahora, sanea.limpiar(titulo, 200), sanea.limpiar(descripcion or "", 2000) or None,
                 sanea.limpiar(categoria, 60), int(gravedad), int(impacto), int(dificultad),
                 float(confianza), sanea.limpiar(causa or "", 500) or None,
                 json.dumps(crit, ensure_ascii=False), sanea.limpiar(origen, 60)))
            iid = _ident("INC", c.lastrowid)
            self.con.execute("UPDATE incidencias SET id=? WHERE num=?", (iid, c.lastrowid))
            self._hist(iid, "creada", None, "abierta", actor)
            for a in archivos:
                self.con.execute("INSERT OR IGNORE INTO archivos_afectados(incidencia_id,ruta,sha256) "
                                 "VALUES(?,?,?)", (iid, sanea.limpiar(a.get("ruta", ""), 200), a.get("sha256")))
        return iid

    def cambiar_estado(self, iid, nuevo, actor, motivo=None, asignado=None):
        self._actor(actor)
        if nuevo not in ESTADOS:
            raise TransicionInvalida(f"estado desconocido: {nuevo!r}")
        if actor in AGENTES and nuevo in SOLO_NO_AGENTES:
            raise PermisoDenegado(f"un agente no puede marcar una incidencia como {nuevo}")
        if nuevo == "descartada" and actor != "usuario":
            raise PermisoDenegado("solo el usuario puede descartar una incidencia")
        inc = self.obtener(iid)
        if nuevo not in TRANSICIONES[inc["estado"]]:
            raise TransicionInvalida(f"{inc['estado']} -> {nuevo} no permitido")
        with self.con:            # los disparadores pueden abortar (sqlite3.IntegrityError)
            self.con.execute("UPDATE incidencias SET estado=?, actualizada=?, asignado=COALESCE(?, asignado) "
                             "WHERE id=?", (nuevo, self.ahora(), asignado, iid))
            self._hist(iid, "estado", inc["estado"], nuevo, actor, motivo)

    def asignar(self, iid, agente, actor="motor", motivo=None):
        self._actor(actor)
        if agente not in AGENTES + ("usuario",):
            raise ValueError("asignación inválida")
        inc = self.obtener(iid)
        with self.con:
            self.con.execute("UPDATE incidencias SET asignado=?, actualizada=? WHERE id=?",
                             (agente, self.ahora(), iid))
            self._hist(iid, "asignado", inc["asignado"], agente, actor, motivo)

    def actualizar_diagnostico(self, iid, actor, gravedad=None, impacto=None, dificultad=None,
                               confianza=None, causa=None, criterios=None, motivo=None):
        """Los agentes pueden proponer valores; nunca confirmar la causa (ver confirmar_causa)."""
        self._actor(actor)
        inc = self.obtener(iid)
        nuevos = {"gravedad": gravedad, "impacto": impacto, "dificultad": dificultad,
                  "confianza": confianza, "causa": causa}
        with self.con:
            for campo, v in nuevos.items():
                if v is None:
                    continue
                if campo == "causa":
                    v = sanea.limpiar(v, 500)
                    self.con.execute("UPDATE incidencias SET causa=?, causa_estado='hipotesis', "
                                     "causa_respaldo='ninguno', causa_hipotesis=NULL WHERE id=?", (v, iid))
                elif campo == "confianza":
                    self.con.execute("UPDATE incidencias SET confianza=? WHERE id=?", (float(v), iid))
                elif campo == "gravedad":
                    self.con.execute("UPDATE incidencias SET gravedad=? WHERE id=?", (int(v), iid))
                elif campo == "impacto":
                    self.con.execute("UPDATE incidencias SET impacto=? WHERE id=?", (int(v), iid))
                else:
                    self.con.execute("UPDATE incidencias SET dificultad=? WHERE id=?", (int(v), iid))
                self._hist(iid, campo, inc.get(campo), v, actor, motivo)
            if criterios is not None:
                crit = [sanea.limpiar(c, 200) for c in list(criterios)[:10]]
                self.con.execute("UPDATE incidencias SET criterios_json=? WHERE id=?",
                                 (json.dumps(crit, ensure_ascii=False), iid))
                self._hist(iid, "criterios", len(inc["criterios"]), len(crit), actor, motivo)
            self.con.execute("UPDATE incidencias SET actualizada=? WHERE id=?", (self.ahora(), iid))

    def confirmar_causa(self, iid, actor, motivo, respaldo=None, hipotesis_id=None):
        """V2-E.4-r2: confirma la causa SOLO con (a) `hipotesis_id` de una hipótesis RESPALDADA de esta
        incidencia (respaldo «simulacion»), o (b) respaldo «prueba_real» con una prueba real registrada
        (imposible mientras el Modo B esté deshabilitado). Lo impone la base (sqlite3.IntegrityError):
        ningún otro camino, ni una sola reproducción, ni un experimento aislado, confirma una causa."""
        self._actor(actor)
        if actor in AGENTES:
            raise PermisoDenegado("un agente no puede confirmar una causa: hacen falta evidencias")
        inc = self.obtener(iid)
        if respaldo is None:
            respaldo = "simulacion" if hipotesis_id else "ninguno"
        if respaldo not in NO_DECLARATIVAS:
            respaldo = "ninguno"           # el disparador abortará: no hay respaldo válido
        with self.con:                     # UNA sola actualización: la base comprueba el conjunto
            self.con.execute("UPDATE incidencias SET causa_estado='confirmada', causa_respaldo=?, causa_hipotesis=?, "
                             "actualizada=? WHERE id=?", (respaldo, hipotesis_id, self.ahora(), iid))
            self._hist(iid, "causa_estado", inc["causa_estado"], "confirmada", actor, motivo)
            self._hist(iid, "causa_respaldo", inc["causa_respaldo"], respaldo, actor, motivo)

    def registrar_observacion(self, run_id, version, iid, presente, contenidos: dict, actor="motor") -> int:
        """V2-E.4-r2: lo que el MOTOR observó en `version`: incidencia presente o ausente y el SHA-256 del
        texto de cada archivo. Es la procedencia que exigen los experimentos de reproducción y control."""
        if actor != "motor":
            raise PermisoDenegado("solo el motor registra observaciones de las versiones")
        self.obtener(iid)
        ahora, n = self.ahora(), 0
        with self.con:
            for archivo, texto in sorted((contenidos or {}).items()):
                c = self.con.execute(
                    "INSERT OR IGNORE INTO observaciones(ts,run_id,version,incidencia_id,presente,archivo,sha256) "
                    "VALUES(?,?,?,?,?,?,?)", (ahora, run_id, int(version), iid, 1 if presente else 0,
                                              sanea.limpiar(archivo, 200),
                                              hashlib.sha256(str(texto).encode("utf-8")).hexdigest()))
                n += c.rowcount
        return n

    def observaciones(self, iid) -> list:
        return [dict(r) for r in self.con.execute("SELECT * FROM observaciones WHERE incidencia_id=? ORDER BY num",
                                                  (iid,)).fetchall()]

    def volver_a_hipotesis(self, iid, actor, motivo):
        self._actor(actor)
        inc = self.obtener(iid)
        with self.con:
            self.con.execute("UPDATE incidencias SET causa_estado='hipotesis', causa_respaldo='ninguno', "
                             "causa_hipotesis=NULL, actualizada=? WHERE id=?", (self.ahora(), iid))
            self._hist(iid, "causa_estado", inc["causa_estado"], "hipotesis", actor, motivo)

    def retirar_causa(self, iid, actor, motivo):
        """V2-E.4: la causa propuesta quedó refutada: se retira (vuelve a «sin causa», por diagnosticar)."""
        self._actor(actor)
        if actor in AGENTES:
            raise PermisoDenegado("un agente no retira causas: lo decide la evidencia")
        inc = self.obtener(iid)
        with self.con:
            self.con.execute("UPDATE incidencias SET causa=NULL, causa_estado='hipotesis', causa_respaldo='ninguno', "
                             "causa_hipotesis=NULL, actualizada=? WHERE id=?", (self.ahora(), iid))
            self._hist(iid, "causa_retirada", inc["causa"], None, actor, motivo)

    def marcar_bloqueo_por_limite(self, iid, actor, motivo):
        with self.con:
            self.con.execute("UPDATE incidencias SET bloqueada_por_limite=1, actualizada=? WHERE id=?",
                             (self.ahora(), iid))
            self._hist(iid, "bloqueada_por_limite", 0, 1, actor, motivo)

    def desbloquear(self, iid, actor, motivo):
        """Solo el USUARIO levanta un bloqueo por límite; los contadores se reinician desde aquí."""
        self._actor(actor)
        if actor != "usuario":
            raise PermisoDenegado("solo el usuario puede levantar un bloqueo por límite")
        with self.con:
            self.con.execute("UPDATE incidencias SET bloqueada_por_limite=0, actualizada=? WHERE id=?",
                             (self.ahora(), iid))
            self._hist(iid, "bloqueada_por_limite", 1, 0, actor, motivo)

    def anotar_tarea(self, iid, agente, accion):
        """Cada tarea emitida por el planificador queda en el historial (cuenta para los límites)."""
        with self.con:
            self._hist(iid, "tarea", None, f"{agente}:{accion}", "motor")

    def rediagnosticar(self, iid, actor, motivo):
        """La causa vuelve a hipótesis y queda anotado el rediagnóstico (cuenta para los límites)."""
        self._actor(actor)
        inc = self.obtener(iid)
        with self.con:
            self.con.execute("UPDATE incidencias SET causa_estado='hipotesis', causa_respaldo='ninguno', "
                             "causa_hipotesis=NULL, actualizada=? WHERE id=?", (self.ahora(), iid))
            self._hist(iid, "causa_estado", inc["causa_estado"], "hipotesis", actor, motivo)
            self._hist(iid, "rediagnostico", None, "1", actor, motivo)

    # --- evidencias e intentos --------------------------------------------------------------
    def registrar_evidencia(self, iid, tipo, resultado, descripcion, actor, contenido=None,
                            experimento_id=None, hipotesis_id=None, version=None, confianza=None,
                            limitaciones=None) -> int:
        """El contenido (si lo hay) se guarda como archivo en evidencias/<id>/ con su SHA-256.
        V2-E.4: hipótesis evaluada, versión, confianza (0-1) y limitaciones (trazabilidad)."""
        self._actor(actor)
        if tipo not in TIPOS_EVIDENCIA:
            raise ValueError("tipo de evidencia inválido")
        if tipo == "prueba_real" and not config.MODO_B_HABILITADO:
            raise PermisoDenegado("no hay ejecución real en esta versión (Modo B deshabilitado)")
        if actor in AGENTES and tipo in NO_DECLARATIVAS:
            raise PermisoDenegado("un agente solo puede aportar observaciones o declaraciones")
        if tipo == "declaracion_agente":
            resultado = "informativa"
        archivo = sha = None
        if contenido is not None:
            datos = contenido if isinstance(contenido, str) else json.dumps(contenido, ensure_ascii=False, default=str)
            datos = datos[:MAX_EVIDENCIA_BYTES]
            sha = hashlib.sha256(datos.encode("utf-8")).hexdigest()
            carpeta = iid if iid else (experimento_id or "general")
            self.lab.crear_dir("incidencias", "evidencias", carpeta)
            n = self.con.execute("SELECT count(*) FROM evidencias").fetchone()[0] + 1
            nombre = f"{n:06d}_{tipo}_{os.urandom(3).hex()}.txt"
            self.lab.escribir_atomico(("incidencias", "evidencias", carpeta, nombre), datos)
            archivo = f"evidencias/{carpeta}/{nombre}"
        with self.con:
            c = self.con.execute(
                "INSERT INTO evidencias(incidencia_id,experimento_id,creada,tipo,resultado,descripcion,"
                "archivo,sha256,actor,hipotesis_id,version,confianza,limitaciones) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (iid, experimento_id, self.ahora(), tipo, resultado, sanea.limpiar(descripcion, 500),
                 archivo, sha, actor, hipotesis_id, version,
                 None if confianza is None else float(confianza),
                 sanea.limpiar(limitaciones, 300) if limitaciones else None))
            if iid:
                self._hist(iid, "evidencia", None, f"{tipo}:{resultado}", actor)
        return c.lastrowid

    def evidencias(self, iid) -> list:
        return [dict(r) for r in self.con.execute(
            "SELECT * FROM evidencias WHERE incidencia_id=? ORDER BY num", (iid,)).fetchall()]

    def registrar_intento(self, iid, agente, descripcion, resultado="pendiente", version=None) -> int:
        if agente not in AGENTES:
            raise PermisoDenegado("los intentos de corrección los registran agentes")
        with self.con:
            c = self.con.execute("INSERT INTO intentos(incidencia_id,creado,agente,descripcion,resultado,version) "
                                 "VALUES(?,?,?,?,?,?)", (iid, self.ahora(), agente,
                                                         sanea.limpiar(descripcion, 500), resultado, version))
            self._hist(iid, "intento", None, f"{agente}:{resultado}", agente)
        return c.lastrowid

    def intentos(self, iid) -> list:
        return [dict(r) for r in self.con.execute(
            "SELECT * FROM intentos WHERE incidencia_id=? ORDER BY num", (iid,)).fetchall()]

    def declaracion_de_agente(self, iid, agente, texto) -> int:
        """«Lo he corregido»: queda como evidencia INFORMATIVA y el estado NO cambia."""
        return self.registrar_evidencia(iid, "declaracion_agente", "informativa", texto, agente)

    # --- dependencias ------------------------------------------------------------------------
    def _alcanzables(self, desde) -> set:
        vistos, pila = set(), [desde]
        while pila:
            x = pila.pop()
            for (d,) in self.con.execute("SELECT destino FROM dependencias WHERE origen=? AND "
                                         "tipo IN ('causa','bloquea')", (x,)).fetchall():
                if d not in vistos:
                    vistos.add(d)
                    pila.append(d)
        return vistos

    def anadir_dependencia(self, origen, destino, tipo, actor, certeza="hipotesis", evidencia_num=None):
        self._actor(actor)
        if certeza == "confirmada" and actor in AGENTES:
            raise PermisoDenegado("un agente no puede confirmar una dependencia")
        self.obtener(origen)
        self.obtener(destino)
        if tipo in ("causa", "bloquea") and (origen == destino or origen in self._alcanzables(destino)):
            raise CicloDependencias(f"{origen} -> {destino} crearía un ciclo")
        with self.con:
            self.con.execute("INSERT INTO dependencias(origen,destino,tipo,certeza,evidencia_num,creada) "
                             "VALUES(?,?,?,?,?,?)", (origen, destino, tipo, certeza, evidencia_num, self.ahora()))
            self._hist(origen, "dependencia", None, f"{tipo}->{destino}:{certeza}", actor)

    def dependencias(self) -> list:
        return [dict(r) for r in self.con.execute("SELECT * FROM dependencias ORDER BY rowid").fetchall()]

    def historial(self, iid) -> list:
        return [dict(r) for r in self.con.execute(
            "SELECT * FROM historial WHERE incidencia_id=? ORDER BY num", (iid,)).fetchall()]

    # --- V2-E.4: hipótesis localizadas ---------------------------------------------------------
    def proponer_hipotesis(self, iid, actor, texto, archivo, patron, version=None) -> tuple:
        """(id, nueva). Idempotente: la misma (incidencia, archivo, patrón) devuelve la existente.
        Las hipótesis nacen 'propuesta'; solo el laboratorio cambia su estado."""
        self._actor(actor)
        if actor == "motor":
            raise PermisoDenegado("el motor no propone hipótesis")
        self.obtener(iid)
        archivo, patron = sanea.limpiar(archivo, 200), sanea.limpiar(patron, 120)
        if "\n" in patron or len(patron.strip()) < 2 or not archivo:
            raise ValueError("hipótesis inválida: hace falta un archivo y un patrón de 2-120 caracteres")
        firma = hashlib.sha256(f"{iid}|{archivo}|{patron}".encode("utf-8")).hexdigest()[:32]
        r = self.con.execute("SELECT id FROM hipotesis WHERE firma=?", (firma,)).fetchone()
        if r:
            return r[0], False
        ahora = self.ahora()
        with self.con:
            c = self.con.execute(
                "INSERT INTO hipotesis(id,creada,actualizada,incidencia_id,actor,version,texto,archivo,patron,firma,estado) "
                "VALUES('pendiente',?,?,?,?,?,?,?,?,?,'propuesta')",
                (ahora, ahora, iid, actor, version, sanea.limpiar(texto or f"patrón en {archivo}", 300) or "hipótesis",
                 archivo, patron, firma))
            hid = _ident("HIP", c.lastrowid)
            self.con.execute("UPDATE hipotesis SET id=? WHERE num=?", (hid, c.lastrowid))
            self._hist(iid, "hipotesis", None, f"{hid} propuesta por {actor}", actor)
        return hid, True

    def registrar_revision(self, run_id, iid, version, resultado, detalle) -> bool:
        """Revisión de A3 de la corrección de la versión `version`. Idempotente por (ejecución, incidencia,
        versión). Es una OPINIÓN del modelo sobre el texto: no cambia el estado ni verifica nada."""
        self.obtener(iid)
        with self.con:
            c = self.con.execute("INSERT OR IGNORE INTO revisiones(ts,run_id,incidencia_id,version,agente,resultado,"
                                 "detalle) VALUES(?,?,?,?,'A3',?,?)",
                                 (self.ahora(), run_id, iid, int(version), resultado, sanea.limpiar(detalle or "", 500)))
            if c.rowcount:
                self._hist(iid, "revision", None, f"A3 v{version}: {resultado}", "A3")
        return bool(c.rowcount)

    def revisiones(self, iid) -> list:
        return [dict(r) for r in self.con.execute("SELECT * FROM revisiones WHERE incidencia_id=? ORDER BY num",
                                                  (iid,)).fetchall()]

    def hipotesis(self, iid=None, hid=None) -> list:
        filas = self.con.execute("SELECT * FROM hipotesis WHERE (?1 IS NULL OR incidencia_id = ?1) AND "
                                 "(?2 IS NULL OR id = ?2) ORDER BY num", (iid, hid)).fetchall()
        return [dict(r) for r in filas]

    def cambiar_hipotesis(self, hid, estado, actor, motivo):
        self._actor(actor)
        if actor != "laboratorio":
            raise PermisoDenegado("solo el laboratorio cambia el estado de una hipótesis (con experimentos)")
        h = self.hipotesis(hid=hid)
        if not h:
            raise KeyError(hid)
        h = h[0]
        if estado == h["estado"]:
            return
        if estado not in TRANSICIONES_HIPOTESIS[h["estado"]]:
            raise TransicionInvalida(f"hipótesis {h['estado']} -> {estado} no permitido")
        with self.con:
            self.con.execute("UPDATE hipotesis SET estado=?, motivo=?, actualizada=? WHERE id=?",
                             (estado, sanea.limpiar(motivo, 300), self.ahora(), hid))
            self._hist(h["incidencia_id"], "hipotesis", f"{hid}:{h['estado']}", f"{hid}:{estado}", actor, motivo)

    # --- V2-E.4: qué se comprobó realmente --------------------------------------------------
    def ficha(self, iid) -> dict:
        i = self.obtener(iid)
        evs = self.evidencias(iid)
        ints = self.intentos(iid)
        hips = self.hipotesis(iid)
        revs = self.revisiones(iid)
        comprobada = sorted({e["tipo"] for e in evs if e["resultado"] == "superada" and e["tipo"] in NO_DECLARATIVAS})
        real = any(e["tipo"] == "prueba_real" and e["resultado"] == "superada" for e in evs)
        # Las fases se miden desde la ÚLTIMA reapertura: lo anterior ya no describe el estado actual.
        hist = self.historial(iid)
        corte = max((h["num"] for h in hist if h["campo"] == "estado" and h["despues"] == "reabierta"), default=0)
        ints_vig = [x for x in ints if any(h["num"] > corte and h["campo"] == "intento" for h in hist)][-1:] \
            if corte else ints[-1:]
        revs_vig = [r for r in revs if any(h["num"] > corte and h["campo"] == "revision"
                                           and h["despues"].startswith(f"A3 v{r['version']}:") for h in hist)]
        ult_int = ints_vig[-1] if ints_vig else None
        ult_rev = revs_vig[-1] if revs_vig else None
        if i["estado"] == "descartada":
            fase = "descartada"
        elif i["estado"] == "verificada" and real:
            fase = "verificada_con_prueba_real"
        elif i["estado"] == "corregida_sin_verificar":
            fase = "comprobada_con_pruebas_disponibles"
        elif ult_int and ult_rev and (ult_rev["version"] or 0) >= (ult_int["version"] or 0):
            fase = "correccion_revisada"
        elif ult_int:
            fase = "correccion_propuesta"
        elif respaldo(i).startswith(("respaldada", "confirmada")):
            fase = "causa_respaldada"
        elif hips or i.get("causa"):
            fase = "causa_hipotetica"
        else:
            fase = "detectada"
        return {"id": iid, "estado": i["estado"], "fase": fase, "respaldo_causa": respaldo(i),
                "causa_hipotesis": i.get("causa_hipotesis"),
                "hipotesis": [{k: h[k] for k in ("id", "estado", "archivo", "patron", "actor", "version")} for h in hips],
                "correccion": {"intentos": len(ints), "ultimo_intento": ult_int["resultado"] if ult_int else None,
                               "revision_A3": (f"v{ult_rev['version']}: {ult_rev['resultado']}"
                                               + (f" ({ult_rev['detalle']})" if ult_rev["detalle"] else "")) if ult_rev else None,
                               "comprobada_con": comprobada if i["estado"] == "corregida_sin_verificar" else [],
                               "validacion_real": "realizada" if real else VALIDACION_REAL_PENDIENTE},
                "reaperturas": self.reaperturas(iid), "escalada_al_usuario": bool(i["bloqueada_por_limite"])}

    def etiqueta(self, iid) -> str:
        """Estado CON lo que se comprobó: nunca «corregida» o «verificada» a secas."""
        f = self.ficha(iid)
        base = f"{f['estado']} · fase {f['fase']} · {ETIQUETA_RESPALDO[f['respaldo_causa']]}"
        if f["estado"] == "corregida_sin_verificar":
            con = " y ".join({"simulacion": "simulación", "analisis_estatico": "análisis estático",
                              "prueba_real": "prueba real"}[t] for t in f["correccion"]["comprobada_con"])
            base += f" · comprobada solo con: {con or 'nada'}"
        return base + f" · validación real: {f['correccion']['validacion_real']}"

    def entregas(self, run_id=None, agente=None) -> list:
        filas = self.con.execute("SELECT * FROM entregas WHERE (?1 IS NULL OR run_id = ?1) AND "
                                 "(?2 IS NULL OR agente = ?2) ORDER BY num", (run_id, agente)).fetchall()
        return [dict(r) for r in filas]

    def reaperturas(self, iid) -> int:
        return self.con.execute("SELECT count(*) FROM historial WHERE incidencia_id=? AND campo='estado' "
                                "AND despues='reabierta'", (iid,)).fetchone()[0]
