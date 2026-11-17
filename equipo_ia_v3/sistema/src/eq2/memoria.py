"""SQLite: base de sesión y una base por agente. Solo el orquestador usa este módulo.

Reglas: todo SQL son literales con parámetros (nunca texto del modelo dentro de
la sentencia); toda memoria generada entra como 'sin_verificar'; cada agente
solo abre su propia base y se comprueba su identidad al abrirla.
"""
from __future__ import annotations

import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from . import config, sanea
from .rutas import RutaInsegura

ESQUEMA_SESION = "6"      # v6 (V2-E.5): fase 'aclaracion' (petición de evidencia, opcional)
#                          con V2-D (la biblioteca rechaza su carpeta en solo lectura).
#                          v4 (V2-D): tipo de turno (continuación/reintento), tiempos, 'no_votada'
#                          v3 (V2-C): terminación/motivo de turnos, estado de votos, fiabilidad
#                          v2: estado de tarea 'analisis_unico'. No hay migración automática.
ESQUEMA_AGENTE = "1"


class MemoriaLlena(Exception):
    pass


class AislamientoViolado(Exception):
    pass


class EsquemaIncompatible(Exception):
    """La base existente se creó con otra versión del esquema; no se migra sola."""


def ahora_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


DDL_SESION = """
CREATE TABLE IF NOT EXISTS meta(clave TEXT PRIMARY KEY, valor TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sesiones(
  id INTEGER PRIMARY KEY, inicio TEXT NOT NULL, fin TEXT,
  estado TEXT NOT NULL CHECK(estado IN ('en_curso','completa','abortada','interrumpida')),
  motivo_fin TEXT, script_sha256 TEXT, modelo_id TEXT, params_json TEXT);
CREATE TABLE IF NOT EXISTS tareas(
  id INTEGER PRIMARY KEY, sesion_id INTEGER NOT NULL REFERENCES sesiones(id),
  enunciado TEXT NOT NULL CHECK(length(enunciado)<=1500),
  estado TEXT NOT NULL CHECK(estado IN
    ('pendiente','en_deliberacion','decidida','sin_consenso','abortada','analisis_unico',
     'propuesta_incompleta')));
CREATE TABLE IF NOT EXISTS turnos(
  id INTEGER PRIMARY KEY, tarea_id INTEGER NOT NULL REFERENCES tareas(id),
  orden INTEGER NOT NULL,
  fase TEXT NOT NULL CHECK(fase IN ('analisis','propuesta','revision','replica','voto','aclaracion')),
  agente TEXT NOT NULL CHECK(agente IN ('A1','A2','A3')),
  estado TEXT NOT NULL CHECK(estado IN ('ok','invalido','fallido','omitido')),
  texto TEXT, prompt_sha256 TEXT, tokens_prompt INTEGER, tokens_gen INTEGER,
  cache_n INTEGER, ms_prompt REAL, ms_gen REAL, finish_reason TEXT,
  inicio TEXT, fin TEXT,
  terminacion TEXT CHECK(terminacion IS NULL OR terminacion IN
    ('completa','truncada','no_verificable')),
  motivo TEXT,
  tipo TEXT NOT NULL DEFAULT 'normal' CHECK(tipo IN ('normal','continuacion','reintento_voto')),
  max_tokens INTEGER, pared_s REAL,
  UNIQUE(tarea_id, orden));
CREATE TABLE IF NOT EXISTS votos(
  id INTEGER PRIMARY KEY, tarea_id INTEGER NOT NULL REFERENCES tareas(id),
  agente TEXT NOT NULL CHECK(agente IN ('A1','A2','A3')),
  turno_id INTEGER REFERENCES turnos(id),
  postura TEXT NOT NULL CHECK(postura IN
    ('aprobar','aprobar_con_cambios','rechazar','abstencion')),
  razon TEXT,
  estado_voto TEXT NOT NULL CHECK(estado_voto IN ('valido','abstencion_forzada')),
  motivo TEXT, intentos INTEGER NOT NULL CHECK(intentos >= 1), finish_reason TEXT,
  advertencias_json TEXT NOT NULL DEFAULT '[]',
  CHECK(estado_voto = 'valido' OR postura = 'abstencion'),
  CHECK(estado_voto = 'valido' OR motivo IS NOT NULL),
  UNIQUE(tarea_id, agente));
CREATE TABLE IF NOT EXISTS conclusiones(
  id INTEGER PRIMARY KEY, tarea_id INTEGER NOT NULL UNIQUE REFERENCES tareas(id),
  resultado TEXT NOT NULL CHECK(resultado IN
    ('aprobada','aprobada_con_cambios','rechazada','sin_consenso','no_votada')),
  conteo_json TEXT NOT NULL, texto_final TEXT,
  verificacion TEXT NOT NULL DEFAULT 'hipotesis'
    CHECK(verificacion IN ('hipotesis','verificada_por_usuario','refutada')),
  propuesta_estado TEXT NOT NULL CHECK(propuesta_estado IN
    ('completa','incompleta','no_verificable')),
  fiabilidad TEXT NOT NULL CHECK(fiabilidad IN ('normal','reducida','no_valida')),
  fiabilidad_json TEXT NOT NULL,
  CHECK(propuesta_estado = 'completa' OR fiabilidad = 'no_valida'),
  CHECK(propuesta_estado = 'completa' OR resultado NOT IN ('aprobada','aprobada_con_cambios')),
  CHECK(resultado <> 'no_votada' OR fiabilidad = 'no_valida'));
CREATE TABLE IF NOT EXISTS muestras(
  id INTEGER PRIMARY KEY, sesion_id INTEGER REFERENCES sesiones(id), ts TEXT NOT NULL,
  mem_available_kb INTEGER, bateria_pct INTEGER, cargando INTEGER);
CREATE TABLE IF NOT EXISTS eventos(
  id INTEGER PRIMARY KEY, sesion_id INTEGER REFERENCES sesiones(id),
  ts TEXT NOT NULL, tipo TEXT NOT NULL, detalle TEXT);
CREATE TRIGGER IF NOT EXISTS eventos_no_upd BEFORE UPDATE ON eventos
  BEGIN SELECT RAISE(ABORT,'eventos es append-only'); END;
CREATE TRIGGER IF NOT EXISTS eventos_no_del BEFORE DELETE ON eventos
  BEGIN SELECT RAISE(ABORT,'eventos es append-only'); END;
"""

DDL_AGENTE = """
CREATE TABLE IF NOT EXISTS meta(clave TEXT PRIMARY KEY, valor TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS memoria(
  id INTEGER PRIMARY KEY, creado TEXT NOT NULL,
  tipo TEXT NOT NULL CHECK(tipo IN ('hecho','hipotesis','leccion')),
  texto TEXT NOT NULL CHECK(length(texto)<=500 AND length(texto)>0),
  estado TEXT NOT NULL DEFAULT 'vigente' CHECK(estado IN ('vigente','dudoso','refutado')),
  verificacion TEXT NOT NULL DEFAULT 'sin_verificar'
    CHECK(verificacion IN ('sin_verificar','verificada_por_usuario','verificada_por_prueba')),
  confianza TEXT NOT NULL DEFAULT 'baja' CHECK(confianza IN ('baja','media','alta')),
  sesion_ref INTEGER, turno_ref INTEGER, supersede_id INTEGER);
CREATE TABLE IF NOT EXISTS decisiones(
  id INTEGER PRIMARY KEY, creado TEXT NOT NULL, tarea_ref INTEGER, turno_ref INTEGER,
  postura TEXT NOT NULL, razon TEXT, consecuencia_corto TEXT, consecuencia_largo TEXT,
  resultado_observado TEXT);
"""

DDL_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS memoria_fts USING fts5(
  texto, content='memoria', content_rowid='id');
CREATE TRIGGER IF NOT EXISTS memoria_ai AFTER INSERT ON memoria BEGIN
  INSERT INTO memoria_fts(rowid, texto) VALUES (new.id, new.texto); END;
CREATE TRIGGER IF NOT EXISTS memoria_ad AFTER DELETE ON memoria BEGIN
  INSERT INTO memoria_fts(memoria_fts, rowid, texto) VALUES ('delete', old.id, old.texto); END;
CREATE TRIGGER IF NOT EXISTS memoria_au AFTER UPDATE OF texto ON memoria BEGIN
  INSERT INTO memoria_fts(memoria_fts, rowid, texto) VALUES ('delete', old.id, old.texto);
  INSERT INTO memoria_fts(rowid, texto) VALUES (new.id, new.texto); END;
"""


def _pragma_max_paginas(paginas: int) -> str:
    """PRAGMA no admite parámetros '?'. Solo se interpola un ENTERO validado, nunca texto."""
    if not isinstance(paginas, int) or isinstance(paginas, bool) or paginas < 1:
        raise ValueError("número de páginas inválido")
    return "PRAGMA max_page_count=" + str(paginas)


def esquema_sesion_de(ruta):
    """Esquema de una sesion.db EXISTENTE, en SOLO LECTURA (immutable: no crea -wal/-shm ni
    escribe nada). None si no existe. Se usa ANTES de cualquier escritura en la carpeta."""
    ruta = Path(ruta)
    if not os.path.lexists(str(ruta)):
        return None
    if os.path.islink(str(ruta)):
        raise RutaInsegura(f"la base de datos no puede ser un enlace: {ruta.name}")
    con = sqlite3.connect(ruta.resolve().as_uri() + "?mode=ro&immutable=1", uri=True)
    try:
        r = con.execute("SELECT valor FROM meta WHERE clave='esquema'").fetchone()
    except sqlite3.DatabaseError:
        return "desconocido"
    finally:
        con.close()
    return r[0] if r else "desconocido"


class _Base:
    def __init__(self, ruta, ahora=ahora_iso):
        self.ruta = Path(ruta)
        self.ahora = ahora
        if os.path.islink(str(self.ruta)):
            raise RutaInsegura(f"la base de datos no puede ser un enlace: {self.ruta.name}")
        self.con = sqlite3.connect(str(self.ruta), timeout=5.0)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA foreign_keys=ON")
        self.con.execute("PRAGMA busy_timeout=5000")
        # Tope DURO de SQLite: ninguna escritura puede superar MAX_DB_BYTES.
        ps = self.con.execute("PRAGMA page_size").fetchone()[0]
        paginas = max(1, int(config.MAX_DB_BYTES) // int(ps))
        sentencia = _pragma_max_paginas(paginas)
        self.con.execute(sentencia)

    def quick_check(self) -> bool:
        return self.con.execute("PRAGMA quick_check").fetchone()[0] == "ok"

    def tamano_bytes(self) -> int:
        pc = self.con.execute("PRAGMA page_count").fetchone()[0]
        ps = self.con.execute("PRAGMA page_size").fetchone()[0]
        return int(pc) * int(ps)

    def _meta_get(self, clave):
        r = self.con.execute("SELECT valor FROM meta WHERE clave=?", (clave,)).fetchone()
        return r[0] if r else None

    def _meta_set(self, clave, valor):
        with self.con:
            self.con.execute(
                "INSERT INTO meta(clave,valor) VALUES(?,?) "
                "ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor", (clave, valor))

    def cerrar(self):
        self.con.close()


class SesionDB(_Base):
    def __init__(self, ruta, ahora=ahora_iso):
        super().__init__(ruta, ahora)
        previo = None
        try:
            previo = self._meta_get("esquema")
        except sqlite3.OperationalError:
            pass                                   # base nueva: aún no existe la tabla meta
        if previo is not None and previo != ESQUEMA_SESION:
            self.con.close()
            raise EsquemaIncompatible(f"sesion.db tiene esquema {previo}, se esperaba {ESQUEMA_SESION}")
        self.con.executescript(DDL_SESION)
        self._meta_set("esquema", ESQUEMA_SESION)

    def crear_sesion(self, script_sha256=None, modelo_id=None, params_json=None) -> int:
        with self.con:
            c = self.con.execute(
                "INSERT INTO sesiones(inicio,estado,script_sha256,modelo_id,params_json) "
                "VALUES(?,?,?,?,?)",
                (self.ahora(), "en_curso", script_sha256, modelo_id, params_json))
        return c.lastrowid

    def cerrar_sesion(self, sesion_id, estado, motivo):
        with self.con:
            self.con.execute("UPDATE sesiones SET fin=?, estado=?, motivo_fin=? WHERE id=?",
                             (self.ahora(), estado, motivo, sesion_id))

    def recuperar_interrumpidas(self):
        """Marca como 'interrumpida' toda sesión que quedó 'en_curso' (p. ej. tras SIGKILL).

        NUNCA reanuda nada: las tareas sin terminar pasan a 'abortada'. Devuelve los ids.
        """
        ids = [r[0] for r in self.con.execute(
            "SELECT id FROM sesiones WHERE estado='en_curso' ORDER BY id").fetchall()]
        if not ids:
            return []
        with self.con:
            for i in ids:
                self.con.execute(
                    "UPDATE sesiones SET estado='interrumpida', fin=?, "
                    "motivo_fin='recuperada_tras_interrupcion' WHERE id=?", (self.ahora(), i))
                self.con.execute(
                    "UPDATE tareas SET estado='abortada' WHERE sesion_id=? "
                    "AND estado IN ('pendiente','en_deliberacion')", (i,))
                self.con.execute(
                    "INSERT INTO eventos(sesion_id,ts,tipo,detalle) VALUES(?,?,?,?)",
                    (i, self.ahora(), "sesion_recuperada",
                     "estaba en_curso al iniciar otra ejecución; no se reanuda"))
        return ids

    def crear_tarea(self, sesion_id, enunciado) -> int:
        with self.con:
            c = self.con.execute(
                "INSERT INTO tareas(sesion_id,enunciado,estado) VALUES(?,?,?)",
                (sesion_id, enunciado, "pendiente"))
        return c.lastrowid

    def estado_tarea(self, tarea_id, estado):
        with self.con:
            self.con.execute("UPDATE tareas SET estado=? WHERE id=?", (estado, tarea_id))

    def registrar_turno(self, tarea_id, orden, fase, agente, estado, texto, prompt_sha256,
                        resp=None, inicio=None, fin=None, terminacion=None, motivo=None,
                        tipo="normal", max_tokens=None, pared_s=None) -> int:
        g = (lambda k: getattr(resp, k, None)) if resp is not None else (lambda k: None)
        with self.con:
            c = self.con.execute(
                "INSERT INTO turnos(tarea_id,orden,fase,agente,estado,texto,prompt_sha256,"
                "tokens_prompt,tokens_gen,cache_n,ms_prompt,ms_gen,finish_reason,inicio,fin,"
                "terminacion,motivo,tipo,max_tokens,pared_s) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (tarea_id, orden, fase, agente, estado, texto, prompt_sha256,
                 g("tokens_prompt"), g("tokens_gen"), g("cache_n"), g("ms_prompt"),
                 g("ms_gen"), g("finish_reason"), inicio, fin, terminacion, motivo,
                 tipo, max_tokens, pared_s))
        return c.lastrowid

    def registrar_voto(self, tarea_id, agente, turno_id, postura, razon, estado_voto="valido",
                       motivo=None, intentos=1, finish_reason=None, advertencias_json="[]") -> int:
        """Un voto 'abstencion_forzada' exige postura 'abstencion' y motivo (CHECK en la base)."""
        with self.con:
            c = self.con.execute(
                "INSERT INTO votos(tarea_id,agente,turno_id,postura,razon,estado_voto,motivo,"
                "intentos,finish_reason,advertencias_json) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (tarea_id, agente, turno_id, postura, razon, estado_voto, motivo, intentos,
                 finish_reason, advertencias_json))
        return c.lastrowid

    def registrar_conclusion(self, tarea_id, resultado, conteo_json, texto_final,
                             propuesta_estado="no_verificable", fiabilidad="no_valida",
                             fiabilidad_json="{}") -> int:
        """Por defecto, lo más conservador: propuesta no verificable y conclusión no válida."""
        with self.con:
            c = self.con.execute(
                "INSERT INTO conclusiones(tarea_id,resultado,conteo_json,texto_final,"
                "propuesta_estado,fiabilidad,fiabilidad_json) VALUES(?,?,?,?,?,?,?)",
                (tarea_id, resultado, conteo_json, texto_final, propuesta_estado, fiabilidad,
                 fiabilidad_json))
        return c.lastrowid

    def registrar_muestra(self, sesion_id, m):
        with self.con:
            self.con.execute(
                "INSERT INTO muestras(sesion_id,ts,mem_available_kb,bateria_pct,cargando) "
                "VALUES(?,?,?,?,?)",
                (sesion_id, self.ahora(), m.mem_kb, m.bateria_pct,
                 None if m.cargando is None else int(m.cargando)))

    def evento(self, sesion_id, tipo, detalle=""):
        with self.con:
            self.con.execute("INSERT INTO eventos(sesion_id,ts,tipo,detalle) VALUES(?,?,?,?)",
                             (sesion_id, self.ahora(), tipo, sanea.limpiar(detalle, 500)))

    def contar(self, tabla_fija: str) -> int:
        consultas = {
            "turnos": "SELECT count(*) FROM turnos",
            "votos": "SELECT count(*) FROM votos",
            "eventos": "SELECT count(*) FROM eventos",
            "tareas": "SELECT count(*) FROM tareas",
        }
        consulta = consultas[tabla_fija]          # KeyError si no es una tabla fija
        return self.con.execute(consulta).fetchone()[0]


class MemoriaAgente(_Base):
    TIPOS = ("hecho", "hipotesis", "leccion")

    def __init__(self, ruta, agente, ahora=ahora_iso):
        if agente not in config.AGENTES:
            raise ValueError("agente desconocido")
        super().__init__(ruta, ahora)
        self.agente = agente
        self.con.executescript(DDL_AGENTE)
        previo = self._meta_get("agente")
        if previo is not None and previo != agente:
            self.con.close()
            raise AislamientoViolado(f"{ruta} pertenece a {previo}, no a {agente}")
        esq = self._meta_get("esquema")
        if esq is not None and esq != ESQUEMA_AGENTE:
            self.con.close()
            raise EsquemaIncompatible(f"{ruta} tiene esquema {esq}, se esperaba {ESQUEMA_AGENTE}")
        self._meta_set("agente", agente)
        self._meta_set("esquema", ESQUEMA_AGENTE)
        try:
            self.con.executescript(DDL_FTS)
        except sqlite3.OperationalError:
            pass
        self.fts = self.con.execute(
            "SELECT 1 FROM sqlite_master WHERE name='memoria_fts'").fetchone() is not None

    def contar_vigentes(self) -> int:
        return self.con.execute(
            "SELECT count(*) FROM memoria WHERE estado='vigente'").fetchone()[0]

    def agregar(self, tipo, texto, confianza="baja", sesion_ref=None, turno_ref=None,
                supersede_id=None) -> int:
        """Toda entrada nace 'sin_verificar'. No hay parámetro para cambiarlo."""
        if tipo not in self.TIPOS:
            raise ValueError("tipo inválido")
        if confianza not in ("baja", "media", "alta"):
            raise ValueError("confianza inválida")
        t = sanea.limpiar(texto, config.MAX_MEMORIA_CHARS)
        if not t:
            raise ValueError("texto vacío")
        if self.contar_vigentes() >= config.MAX_MEMORIA_ENTRADAS:
            raise MemoriaLlena("límite de entradas")
        try:
            with self.con:       # cualquier excepción dentro revierte la inserción
                c = self.con.execute(
                    "INSERT INTO memoria(creado,tipo,texto,verificacion,confianza,sesion_ref,"
                    "turno_ref,supersede_id) VALUES(?,?,?,'sin_verificar',?,?,?,?)",
                    (self.ahora(), tipo, t, confianza, sesion_ref, turno_ref, supersede_id))
                if self.tamano_bytes() > config.MAX_DB_BYTES:
                    raise MemoriaLlena("la inserción superaría el límite de tamaño")
        except sqlite3.OperationalError as e:
            if "full" in str(e).lower():
                raise MemoriaLlena("SQLite alcanzó el tope de páginas")
            raise
        return c.lastrowid

    def buscar(self, consulta, n=config.MEMORIAS_POR_PROMPT):
        """Memorias vigentes relacionadas. La consulta se reduce a palabras simples."""
        palabras = []
        for p in re.findall(r"\w{3,}", str(consulta).lower()):
            if p not in palabras:
                palabras.append(p)
        palabras = palabras[:8]
        if not palabras:
            return []
        if self.fts:
            expr = " OR ".join('"' + p.replace('"', '') + '"' for p in palabras)
            filas = self.con.execute(
                "SELECT m.id,m.tipo,m.texto,m.verificacion,m.confianza,m.creado,m.sesion_ref,m.turno_ref "
                "FROM memoria_fts f "  # V2-E.6: + metadatos
                "JOIN memoria m ON m.id=f.rowid WHERE memoria_fts MATCH ? "
                "AND m.estado='vigente' ORDER BY rank LIMIT ?", (expr, int(n))).fetchall()
        else:
            filas = []
            for p in palabras:
                filas += self.con.execute(
                    "SELECT id,tipo,texto,verificacion,confianza,creado,sesion_ref,turno_ref FROM memoria "
                    "WHERE estado='vigente' AND texto LIKE ? ESCAPE '\\' LIMIT ?",
                    ("%" + p.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%",
                     int(n))).fetchall()
            vistos, unicas = set(), []
            for f in filas:
                if f["id"] not in vistos:
                    vistos.add(f["id"])
                    unicas.append(f)
            filas = unicas[: int(n)]
        return [dict(f) for f in filas]

    def recientes(self, n=5):
        return [dict(f) for f in self.con.execute(
            "SELECT id,tipo,texto,verificacion,confianza FROM memoria "
            "WHERE estado='vigente' ORDER BY id DESC LIMIT ?", (int(n),)).fetchall()]

    def registrar_decision(self, tarea_ref, turno_ref, postura, razon,
                           corto="pendiente de observar", largo="pendiente de observar"):
        with self.con:
            self.con.execute(
                "INSERT INTO decisiones(creado,tarea_ref,turno_ref,postura,razon,"
                "consecuencia_corto,consecuencia_largo) VALUES(?,?,?,?,?,?,?)",
                (self.ahora(), tarea_ref, turno_ref, postura,
                 sanea.limpiar(razon, 200), corto, largo))


def respaldar(origen, directorio_copias, etiqueta=None):
    """Copia verificada con la API de respaldo de SQLite. No sobrescribe nada."""
    origen = Path(origen)
    destino_dir = Path(directorio_copias)
    for p in (origen, destino_dir):
        if os.path.islink(str(p)):
            raise RutaInsegura(f"enlace simbólico no permitido: {p.name}")
    if not destino_dir.is_dir():
        raise FileNotFoundError(f"la carpeta de copias debe existir: {destino_dir.name}")
    sello = etiqueta or datetime.now().strftime("%Y%m%d_%H%M%S")
    destino = destino_dir / f"{origen.stem}_{sello}.db"
    if destino.exists():
        raise FileExistsError(str(destino))
    src = sqlite3.connect(f"file:{origen}?mode=ro", uri=True)
    dst = sqlite3.connect(str(destino))
    try:
        src.backup(dst)
        ok = dst.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    finally:
        dst.close()
        src.close()
    if not ok:
        raise sqlite3.DatabaseError(f"copia no verificada: {destino}")
    return destino
