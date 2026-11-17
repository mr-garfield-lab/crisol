"""Equipo IA V3 · TRAZA unificada (Etapa 1).

Una base SQLite por laboratorio con la cadena completa de cada ejecución:
  objetivo → análisis → agente → decisión → autorización → acción → cambio → prueba → resultado → experiencia.

Garantías:
- **Almacén común:** `eq3.almacen.Almacen` aporta la base de solo añadir (disparadores), la cadena de hashes en
  `registro` y `verificar_cadena()`, que detecta alteraciones aunque se quiten los disparadores.
- **Claves foráneas y CHECK:** no puede existir una decisión, acción o cambio sin su ejecución y su agente, ni
  una prueba ejecutada sin una autorización concedida por el usuario.
- **Textos por referencia:** los textos de los agentes NO se copian. Se guardan su ruta (relativa al laboratorio)
  y su SHA-256, y la verificación vuelve a calcular los hashes de los archivos.

Esquema v2: v1 creaba su propia tabla `meta` sin el campo `tipo`; desde v2 la crea el almacén común. Las bases v1
se rechazan con un mensaje claro: nunca se reinterpretan.
"""
from __future__ import annotations

from .almacen import GENESIS, Almacen, ErrorAlmacen, ahora, canonico, sha256_texto  # noqa: F401  (API pública)

ErrorTraza = ErrorAlmacen

TABLAS = {
    "objetivos": ("id", "tarea", "titulo", "instrucciones", "criterios", "tarea_sha256"),
    "ejecuciones": ("id", "objetivo_id", "inicio", "fin", "backend", "naturaleza", "version_sistema",
                    "manifiesto_sha256"),
    "agentes": ("ejecucion_id", "agente", "rol", "tarjeta_sha256", "backend", "naturaleza"),
    "analisis": ("id", "ejecucion_id", "tipo", "version", "archivo", "sha256", "resumen"),
    "decisiones": ("id", "ejecucion_id", "n", "tipo", "agente", "ronda", "version", "contenido"),
    "autorizaciones": ("id", "ejecucion_id", "accion", "concedida", "actor", "origen", "decision_id"),
    "acciones": ("id", "ejecucion_id", "n", "tipo", "agente", "nombre", "archivo", "sha256", "detalle"),
    "cambios": ("id", "ejecucion_id", "version", "version_previa", "origen", "archivo", "sha256_antes",
                "sha256_despues", "ruta", "diff"),
    "pruebas": ("id", "ejecucion_id", "caso", "fuente", "estado", "autorizacion_id"),
    "resultados": ("ejecucion_id", "estado_final", "resultado", "aceptada", "version_recomendada", "motivo",
                   "informe", "informe_sha256"),
    "experiencias": ("id", "ejecucion_id", "agente", "recuerdo_id", "tipo", "estado", "texto_sha256", "base"),
}
CLAVES = {"agentes": ("ejecucion_id", "agente"), "resultados": ("ejecucion_id",)}

ESQUEMA = """
CREATE TABLE objetivos (id TEXT PRIMARY KEY, tarea TEXT NOT NULL, titulo TEXT, instrucciones TEXT NOT NULL,
  criterios TEXT NOT NULL, tarea_sha256 TEXT NOT NULL);
CREATE TABLE ejecuciones (id TEXT PRIMARY KEY, objetivo_id TEXT NOT NULL REFERENCES objetivos(id),
  inicio TEXT, fin TEXT, backend TEXT NOT NULL,
  naturaleza TEXT NOT NULL CHECK (naturaleza IN ('SIMULADA', 'REAL')),
  version_sistema TEXT NOT NULL, manifiesto_sha256 TEXT);
CREATE TABLE agentes (ejecucion_id TEXT NOT NULL REFERENCES ejecuciones(id), agente TEXT NOT NULL,
  rol TEXT NOT NULL, tarjeta_sha256 TEXT, backend TEXT NOT NULL,
  naturaleza TEXT NOT NULL CHECK (naturaleza IN ('SIMULADA', 'REAL', 'DETERMINISTA')),
  PRIMARY KEY (ejecucion_id, agente));
CREATE TABLE analisis (id TEXT PRIMARY KEY, ejecucion_id TEXT NOT NULL REFERENCES ejecuciones(id),
  tipo TEXT NOT NULL CHECK (tipo IN ('plan', 'estatico', 'casos')), version INTEGER, archivo TEXT NOT NULL,
  sha256 TEXT NOT NULL, resumen TEXT NOT NULL);
CREATE TABLE decisiones (id TEXT PRIMARY KEY, ejecucion_id TEXT NOT NULL REFERENCES ejecuciones(id),
  n INTEGER NOT NULL, tipo TEXT NOT NULL, agente TEXT, ronda INTEGER, version INTEGER, contenido TEXT NOT NULL,
  UNIQUE (ejecucion_id, n));
CREATE TABLE autorizaciones (id TEXT PRIMARY KEY, ejecucion_id TEXT NOT NULL REFERENCES ejecuciones(id),
  accion TEXT NOT NULL, concedida INTEGER NOT NULL CHECK (concedida IN (0, 1)), actor TEXT,
  origen TEXT NOT NULL, decision_id TEXT REFERENCES decisiones(id),
  CHECK (concedida = 0 OR actor = 'usuario'));
CREATE TABLE acciones (id TEXT PRIMARY KEY, ejecucion_id TEXT NOT NULL, n INTEGER NOT NULL,
  tipo TEXT NOT NULL CHECK (tipo IN ('paso', 'herramienta')), agente TEXT NOT NULL, nombre TEXT NOT NULL,
  archivo TEXT, sha256 TEXT, detalle TEXT NOT NULL, UNIQUE (ejecucion_id, tipo, n),
  FOREIGN KEY (ejecucion_id, agente) REFERENCES agentes(ejecucion_id, agente));
CREATE TABLE cambios (id TEXT PRIMARY KEY, ejecucion_id TEXT NOT NULL REFERENCES ejecuciones(id),
  version INTEGER NOT NULL, version_previa INTEGER, origen TEXT NOT NULL, archivo TEXT NOT NULL,
  sha256_antes TEXT, sha256_despues TEXT NOT NULL, ruta TEXT NOT NULL, diff TEXT NOT NULL,
  UNIQUE (ejecucion_id, version, archivo));
CREATE TABLE pruebas (id TEXT PRIMARY KEY, ejecucion_id TEXT NOT NULL REFERENCES ejecuciones(id),
  caso TEXT NOT NULL, fuente TEXT NOT NULL,
  estado TEXT NOT NULL CHECK (estado IN ('pendiente_no_ejecutada', 'ejecutada_ok', 'ejecutada_fallo')),
  autorizacion_id TEXT REFERENCES autorizaciones(id),
  CHECK (estado = 'pendiente_no_ejecutada' OR autorizacion_id IS NOT NULL));
CREATE TABLE resultados (ejecucion_id TEXT PRIMARY KEY REFERENCES ejecuciones(id), estado_final TEXT NOT NULL,
  resultado TEXT NOT NULL, aceptada INTEGER, version_recomendada INTEGER, motivo TEXT, informe TEXT NOT NULL,
  informe_sha256 TEXT NOT NULL);
CREATE TABLE experiencias (id TEXT PRIMARY KEY, ejecucion_id TEXT NOT NULL, agente TEXT NOT NULL,
  recuerdo_id TEXT NOT NULL, tipo TEXT NOT NULL, estado TEXT, texto_sha256 TEXT NOT NULL, base TEXT NOT NULL,
  FOREIGN KEY (ejecucion_id, agente) REFERENCES agentes(ejecucion_id, agente));
"""


class Traza(Almacen):
    """Base de trazas de un laboratorio. Uso: `with Traza(ruta) as t: ...`."""
    NOMBRE = "traza"
    ESQUEMA_VERSION = "2"
    TABLAS = TABLAS
    CLAVES = CLAVES
    ESQUEMA = ESQUEMA
