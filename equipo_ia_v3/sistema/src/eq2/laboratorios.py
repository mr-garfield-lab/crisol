"""V2-E.5-r2: laboratorios INDIVIDUALES de A1, A2 y A3 sobre la infraestructura existente.

No es un sistema paralelo: los cuadernos viven en la MISMA base `incidencias.db` y referencian sus
tablas (incidencias, hipotesis, experimentos) con claves foráneas. Este módulo solo añade dos tablas
(`cuaderno`, `intercambios`; marca `esquema_cuaderno` en `meta`) y no cambia el esquema 4.

Cada agente tiene un espacio lógico propio (su cuaderno):
  A1 (programación): soluciones, alternativas, versiones candidatas, comparación de correcciones.
  A2 (análisis): investigaciones, causas raíz, evidencias, comparación de explicaciones (hipótesis).
  A3 (verificación): casos de prueba, regresiones propuestas, objeciones, contradicciones, pendientes.

Reglas que impone la BASE (valen para cualquier camino de código):
  * solo anexar: ninguna entrada se modifica ni se borra (una versión nueva SUSTITUYE a otra);
  * un agente solo escribe en su cuaderno y solo con respaldo «declaracion_agente»;
  * respaldo «simulacion» solo con un experimento COMPLETADO y escrito por motor/laboratorio;
  * no existe el respaldo «prueba_real» (Modo B deshabilitado): una simulación nunca se presenta
    como prueba real;
  * los tipos de entrada dependen del agente; una versión solo sustituye a otra del mismo agente;
  * los intercambios entre agentes solo los hace el COORDINADOR y solo con entradas del emisor;
  * límites: 500 entradas por agente, 4000 caracteres por entrada, 300 intercambios.
Alcance de la garantía: protege frente a los caminos del sistema y frente al texto de los agentes;
no frente a quien edite a mano el archivo SQLite (`verificar_integridad` detecta contenidos
alterados comparando su SHA-256).
No ejecuta código: el contenido de las entradas es TEXTO NO CONFIABLE.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import re
import sqlite3

from . import config, criticas, sanea
from .incidencias import AGENTES, RegistroIncidencias
from .memoria import EsquemaIncompatible

ESQUEMA_CUADERNO = "3"                 # V2-E.6: evidencia con fuente/líneas, artefactos, pendientes
TIPOS_POR_AGENTE = {
    "A1": ("solucion", "alternativa", "candidata", "comparacion_correcciones",
           "parche_texto", "contrato", "prueba_propuesta", "supuesto", "riesgo"),               # V2-E.6
    "A2": ("investigacion", "causa_raiz", "evidencia_analisis", "comparacion_explicaciones",
           "perfilado_estatico", "hipotesis_competidora", "solicitud_datos", "evidencia_citada"),  # V2-E.6
    "A3": ("caso_prueba", "regresion_propuesta", "objecion", "contradiccion", "evaluacion_pendiente",
           "contraejemplo", "comprobacion_declarativa", "falsacion", "rechazo", "abstencion"),   # V2-E.6
}
CON_FUENTE = ("evidencia_citada", "contraejemplo", "perfilado_estatico")     # exigen fuente y líneas
FALSABLES = ("hipotesis_competidora", "falsacion")                          # exigen condición de falsación
ESTADOS_PENDIENTE = ("propuesta", "cambios_solicitados", "aplicado", "no_aplicado", "verificado",
                     "no_verificable", "rechazado_justificado")
MAX_ARTEFACTOS_ESPACIO = 50        # igual que el disparador art_limite
MAX_ARTEFACTO_CHARS = 200_000
# V2-E.6: el código y los parches conservan la indentación (antes se colapsaban los espacios)
TIPOS_CODIGO = ("solucion", "alternativa", "candidata", "parche_texto", "contrato", "prueba_propuesta")
TIPOS_COMUNES = ("hipotesis", "decision", "aprendizaje")       # V2-E.5-r3: los tres agentes
RESULTADOS = ("positivo", "negativo", "no_concluyente", "pendiente", "informativo")
RESPALDOS = ("declaracion_agente", "simulacion", "analisis_estatico", "registro")
PROCEDENCIAS = ("A1", "A2", "A3", "motor", "laboratorio", "usuario")
MAX_ENTRADAS_AGENTE = 500          # igual que el disparador cua_limite_por_agente
MAX_CONTENIDO = 4000               # igual que el CHECK de la tabla
MAX_TITULO = 200
MAX_INTERCAMBIOS = 300             # igual que el disparador icb_limite
DE_CONCLUSION = {"apoya": "positivo", "refuta": "negativo", "no_concluyente": "no_concluyente"}

DDL_CUADERNO = """
CREATE TABLE IF NOT EXISTS cuaderno(
  num INTEGER PRIMARY KEY, id TEXT NOT NULL UNIQUE, ts TEXT NOT NULL,
  agente TEXT NOT NULL CHECK(agente IN ('A1','A2','A3')),
  tipo TEXT NOT NULL CHECK(
    (agente = 'A1' AND tipo IN ('solucion','alternativa','candidata','comparacion_correcciones',
                                'parche_texto','contrato','prueba_propuesta','supuesto','riesgo')) OR
    (agente = 'A2' AND tipo IN ('investigacion','causa_raiz','evidencia_analisis','comparacion_explicaciones',
                                'perfilado_estatico','hipotesis_competidora','solicitud_datos','evidencia_citada')) OR
    (agente = 'A3' AND tipo IN ('caso_prueba','regresion_propuesta','objecion','contradiccion',
                                'evaluacion_pendiente','contraejemplo','comprobacion_declarativa','falsacion',
                                'rechazo','abstencion')) OR
    tipo IN ('hipotesis','decision','aprendizaje')),
  titulo TEXT NOT NULL CHECK(length(titulo) BETWEEN 1 AND 200),
  contenido TEXT NOT NULL CHECK(length(contenido) <= 4000),
  sha256 TEXT NOT NULL CHECK(length(sha256) = 64),
  resultado TEXT NOT NULL CHECK(resultado IN ('positivo','negativo','no_concluyente','pendiente','informativo')),
  respaldo TEXT NOT NULL CHECK(respaldo IN ('declaracion_agente','simulacion','analisis_estatico','registro')),
  procedencia TEXT NOT NULL CHECK(procedencia IN ('A1','A2','A3','motor','laboratorio','usuario')),
  incidencia_id TEXT REFERENCES incidencias(id),
  hipotesis_id TEXT REFERENCES hipotesis(id),
  experimento_id TEXT REFERENCES experimentos(id),
  sustituye TEXT REFERENCES cuaderno(id),
  relacionada TEXT REFERENCES cuaderno(id),
  run_id TEXT,
  fuente TEXT CHECK(fuente IS NULL OR length(fuente) BETWEEN 1 AND 200),
  lineas TEXT CHECK(lineas IS NULL OR length(lineas) BETWEEN 1 AND 200),
  condicion_falsacion TEXT CHECK(condicion_falsacion IS NULL OR length(condicion_falsacion) <= 500),
  escenario TEXT CHECK(escenario IS NULL OR length(escenario) <= 200),
  CHECK(procedencia NOT IN ('A1','A2','A3') OR procedencia = agente),
  CHECK(procedencia NOT IN ('A1','A2','A3') OR respaldo = 'declaracion_agente'),
  CHECK(respaldo <> 'simulacion' OR (experimento_id IS NOT NULL AND procedencia IN ('motor','laboratorio'))));
CREATE TABLE IF NOT EXISTS intercambios(
  num INTEGER PRIMARY KEY, ts TEXT NOT NULL, entrada_id TEXT NOT NULL REFERENCES cuaderno(id),
  de_agente TEXT NOT NULL CHECK(de_agente IN ('A1','A2','A3')),
  para_agente TEXT NOT NULL CHECK(para_agente IN ('A1','A2','A3')),
  actor TEXT NOT NULL CHECK(actor = 'coordinador'),
  motivo TEXT NOT NULL CHECK(length(motivo) BETWEEN 1 AND 300),
  CHECK(de_agente <> para_agente), UNIQUE(entrada_id, para_agente));

CREATE TABLE IF NOT EXISTS artefactos(
  num INTEGER PRIMARY KEY, id TEXT NOT NULL UNIQUE, ts TEXT NOT NULL,
  espacio TEXT NOT NULL CHECK(espacio IN ('A1','A2','A3','comun')),
  nombre TEXT NOT NULL CHECK(length(nombre) BETWEEN 1 AND 200),
  origen TEXT NOT NULL CHECK(length(origen) BETWEEN 1 AND 300),
  numeracion TEXT NOT NULL CHECK(numeracion IN ('archivo','prefijo_L')),
  sha256 TEXT NOT NULL CHECK(length(sha256) = 64), lineas INTEGER NOT NULL,
  contenido TEXT NOT NULL CHECK(length(contenido) <= 200000),
  procedencia TEXT NOT NULL CHECK(procedencia IN ('laboratorio','usuario','coordinador')),
  sustituye TEXT REFERENCES artefactos(id));
CREATE TABLE IF NOT EXISTS pendientes(
  num INTEGER PRIMARY KEY, ts TEXT NOT NULL, entrada_id TEXT NOT NULL REFERENCES cuaderno(id),
  estado TEXT NOT NULL CHECK(estado IN ('propuesta','cambios_solicitados','aplicado','no_aplicado','verificado',
    'no_verificable','rechazado_justificado')),
  motivo TEXT NOT NULL CHECK(length(motivo) BETWEEN 1 AND 500),
  evidencia_id TEXT REFERENCES cuaderno(id),
  actor TEXT NOT NULL CHECK(actor IN ('coordinador','usuario')));

CREATE TRIGGER IF NOT EXISTS art_no_modificar BEFORE UPDATE ON artefactos
  BEGIN SELECT RAISE(ABORT, 'los artefactos no se modifican: se registra una versión nueva'); END;
CREATE TRIGGER IF NOT EXISTS art_no_borrar BEFORE DELETE ON artefactos
  BEGIN SELECT RAISE(ABORT, 'los artefactos no se borran'); END;
CREATE TRIGGER IF NOT EXISTS art_limite BEFORE INSERT ON artefactos
  WHEN (SELECT COUNT(*) FROM artefactos WHERE espacio = NEW.espacio) >= 50
  BEGIN SELECT RAISE(ABORT, 'límite de artefactos de este espacio'); END;
CREATE TRIGGER IF NOT EXISTS cua_evidencia_con_fuente BEFORE INSERT ON cuaderno
  WHEN NEW.tipo IN ('evidencia_citada','contraejemplo','perfilado_estatico')
    AND (NEW.fuente IS NULL OR NEW.lineas IS NULL)
  BEGIN SELECT RAISE(ABORT, 'evidencia insuficiente: falta la fuente o las líneas'); END;
CREATE TRIGGER IF NOT EXISTS cua_falsable BEFORE INSERT ON cuaderno
  WHEN NEW.tipo IN ('hipotesis_competidora','falsacion')
    AND (NEW.condicion_falsacion IS NULL OR length(trim(NEW.condicion_falsacion)) < 10)
  BEGIN SELECT RAISE(ABORT, 'una hipótesis o falsación necesita una condición de falsación'); END;
CREATE TRIGGER IF NOT EXISTS cua_rechazo_justificado BEFORE INSERT ON cuaderno
  WHEN NEW.tipo IN ('rechazo','abstencion') AND (length(trim(NEW.contenido)) < 20
    OR (NEW.tipo = 'rechazo' AND NEW.relacionada IS NULL))
  BEGIN SELECT RAISE(ABORT, 'un rechazo o una abstención deben estar razonados (y el rechazo, referido)'); END;
CREATE TRIGGER IF NOT EXISTS cua_comprobacion_del_laboratorio BEFORE INSERT ON cuaderno
  WHEN NEW.tipo = 'comprobacion_declarativa' AND NEW.procedencia <> 'laboratorio'
  BEGIN SELECT RAISE(ABORT, 'las comprobaciones declarativas las evalúa el laboratorio, no el agente'); END;
CREATE TRIGGER IF NOT EXISTS pen_no_modificar BEFORE UPDATE ON pendientes
  BEGIN SELECT RAISE(ABORT, 'el historial de pendientes no se modifica'); END;
CREATE TRIGGER IF NOT EXISTS pen_no_borrar BEFORE DELETE ON pendientes
  BEGIN SELECT RAISE(ABORT, 'el historial de pendientes no se borra'); END;
CREATE TRIGGER IF NOT EXISTS pen_transiciones BEFORE INSERT ON pendientes
  WHEN NOT (
    (NOT EXISTS (SELECT 1 FROM pendientes WHERE entrada_id = NEW.entrada_id)
      AND NEW.estado IN ('propuesta','cambios_solicitados','rechazado_justificado')) OR
    ((SELECT estado FROM pendientes WHERE entrada_id = NEW.entrada_id ORDER BY num DESC LIMIT 1) = 'propuesta'
      AND NEW.estado IN ('cambios_solicitados','aplicado','no_aplicado','no_verificable','rechazado_justificado')) OR
    ((SELECT estado FROM pendientes WHERE entrada_id = NEW.entrada_id ORDER BY num DESC LIMIT 1) = 'cambios_solicitados'
      AND NEW.estado IN ('aplicado','no_aplicado','rechazado_justificado')) OR
    ((SELECT estado FROM pendientes WHERE entrada_id = NEW.entrada_id ORDER BY num DESC LIMIT 1) = 'aplicado'
      AND NEW.estado IN ('verificado','no_verificable','cambios_solicitados')) OR
    ((SELECT estado FROM pendientes WHERE entrada_id = NEW.entrada_id ORDER BY num DESC LIMIT 1) = 'no_aplicado'
      AND NEW.estado IN ('cambios_solicitados','rechazado_justificado')))
  BEGIN SELECT RAISE(ABORT, 'transición de pendiente no permitida'); END;
CREATE TRIGGER IF NOT EXISTS pen_verificado_exige_comprobacion BEFORE INSERT ON pendientes
  WHEN NEW.estado = 'verificado' AND NOT EXISTS (SELECT 1 FROM cuaderno WHERE id = NEW.evidencia_id
    AND resultado = 'positivo' AND respaldo IN ('analisis_estatico','registro','simulacion')
    AND tipo IN ('comprobacion_declarativa','evidencia_analisis','perfilado_estatico')
    AND relacionada = NEW.entrada_id)
  BEGIN SELECT RAISE(ABORT, 'verificado exige una comprobación positiva del sistema SOBRE esa propuesta (no un voto ni una declaración)'); END;
CREATE TRIGGER IF NOT EXISTS pen_rechazo_razonado BEFORE INSERT ON pendientes
  WHEN NEW.estado IN ('rechazado_justificado','no_verificable','no_aplicado') AND length(trim(NEW.motivo)) < 10
  BEGIN SELECT RAISE(ABORT, 'este estado exige un motivo razonado'); END;
CREATE TRIGGER IF NOT EXISTS cua_no_modificar BEFORE UPDATE ON cuaderno
  BEGIN SELECT RAISE(ABORT, 'las entradas del cuaderno no se modifican: se anota una versión nueva'); END;
CREATE TRIGGER IF NOT EXISTS cua_no_borrar BEFORE DELETE ON cuaderno
  BEGIN SELECT RAISE(ABORT, 'las entradas del cuaderno no se borran'); END;
CREATE TRIGGER IF NOT EXISTS cua_limite_por_agente BEFORE INSERT ON cuaderno
  WHEN (SELECT COUNT(*) FROM cuaderno WHERE agente = NEW.agente) >= 500
  BEGIN SELECT RAISE(ABORT, 'límite de entradas del cuaderno alcanzado para este agente'); END;
CREATE TRIGGER IF NOT EXISTS cua_simulacion_exige_experimento_completado BEFORE INSERT ON cuaderno
  WHEN NEW.respaldo = 'simulacion' AND NOT EXISTS (SELECT 1 FROM experimentos
    WHERE id = NEW.experimento_id AND estado = 'completado')
  BEGIN SELECT RAISE(ABORT, 'respaldo de simulación sin un experimento completado'); END;
CREATE TRIGGER IF NOT EXISTS cua_sustituye_mismo_agente BEFORE INSERT ON cuaderno
  WHEN NEW.sustituye IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cuaderno
    WHERE id = NEW.sustituye AND agente = NEW.agente AND tipo = NEW.tipo)
  BEGIN SELECT RAISE(ABORT, 'una versión solo sustituye a una entrada del mismo agente y tipo'); END;
CREATE TRIGGER IF NOT EXISTS cua_relacionada_visible BEFORE INSERT ON cuaderno
  WHEN NEW.relacionada IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cuaderno
    WHERE id = NEW.relacionada AND agente = NEW.agente) AND NOT EXISTS (SELECT 1 FROM intercambios
    WHERE entrada_id = NEW.relacionada AND para_agente = NEW.agente)
  BEGIN SELECT RAISE(ABORT, 'solo se relaciona con entradas propias o recibidas del coordinador'); END;
CREATE TRIGGER IF NOT EXISTS cua_aprendizaje_sustentado BEFORE INSERT ON cuaderno
  WHEN NEW.tipo = 'aprendizaje' AND NOT EXISTS (SELECT 1 FROM cuaderno WHERE id = NEW.relacionada
    AND respaldo IN ('simulacion','analisis_estatico','registro'))
  BEGIN SELECT RAISE(ABORT, 'un aprendizaje debe apoyarse en un resultado registrado por el sistema'); END;
CREATE TRIGGER IF NOT EXISTS cua_hipotesis_de_la_incidencia BEFORE INSERT ON cuaderno
  WHEN NEW.hipotesis_id IS NOT NULL AND NEW.incidencia_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM hipotesis
    WHERE id = NEW.hipotesis_id AND incidencia_id = NEW.incidencia_id)
  BEGIN SELECT RAISE(ABORT, 'la hipótesis no pertenece a esa incidencia'); END;
CREATE TRIGGER IF NOT EXISTS icb_entrada_del_emisor BEFORE INSERT ON intercambios
  WHEN NOT EXISTS (SELECT 1 FROM cuaderno WHERE id = NEW.entrada_id AND agente = NEW.de_agente)
  BEGIN SELECT RAISE(ABORT, 'solo se comparten entradas del propio emisor'); END;
CREATE TRIGGER IF NOT EXISTS icb_limite BEFORE INSERT ON intercambios
  WHEN (SELECT COUNT(*) FROM intercambios) >= 300
  BEGIN SELECT RAISE(ABORT, 'límite de intercambios alcanzado'); END;
CREATE TRIGGER IF NOT EXISTS icb_no_modificar BEFORE UPDATE ON intercambios
  BEGIN SELECT RAISE(ABORT, 'los intercambios no se modifican'); END;
CREATE TRIGGER IF NOT EXISTS icb_no_borrar BEFORE DELETE ON intercambios
  BEGIN SELECT RAISE(ABORT, 'los intercambios no se borran'); END;
"""


class AccesoDenegado(PermissionError):
    """Un agente intenta leer o usar una entrada que no es suya ni le fue compartida."""


class LimiteExcedido(ValueError):
    pass


def _sha(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def disparadores_esperados(ddl: str) -> dict:
    """{nombre: tabla} de los disparadores declarados en un DDL."""
    return dict(re.findall(r"CREATE TRIGGER IF NOT EXISTS (\w+)\s+(?:BEFORE|AFTER)\s+(?:INSERT|UPDATE|DELETE)(?:\s+OF\s+[\w, ]+?)?\s+ON\s+(\w+)", ddl))


def comprobar_disparadores(con, ddl: str) -> None:
    """«IF NOT EXISTS» omite EN SILENCIO un disparador si ya existe otro con el mismo nombre (aunque sea
    de otra tabla). Se comprueba que cada uno existe y protege la tabla prevista."""
    reales = {r[0]: r[1] for r in con.execute("SELECT name, tbl_name FROM sqlite_master WHERE type='trigger'")}
    mal = sorted(n for n, tabla in disparadores_esperados(ddl).items() if reales.get(n) != tabla)
    if mal:
        raise EsquemaIncompatible("disparadores ausentes o sobre otra tabla: " + ", ".join(mal))


def asegurar_esquema(reg: RegistroIncidencias) -> None:
    previo = reg._meta_get("esquema_cuaderno")
    if previo is not None and previo != ESQUEMA_CUADERNO:
        raise EsquemaIncompatible(f"cuaderno con esquema {previo}, se esperaba {ESQUEMA_CUADERNO}")
    reg.con.executescript(DDL_CUADERNO)
    comprobar_disparadores(reg.con, DDL_CUADERNO)
    reg._meta_set("esquema_cuaderno", ESQUEMA_CUADERNO)


# --- V2-E.6: líneas, artefactos y comprobaciones declarativas ---------------------------------------
_LINEAS = re.compile(r"^L?(\d{1,7})(?:\s*-\s*L?(\d{1,7}))?$")
MAX_LINEAS_CITA = 200


def parsear_lineas(lineas) -> list:
    """«L12, L15-L18» o [12, 15] -> [12, 15, 16, 17, 18]. Lanza ValueError si el formato no es válido."""
    if isinstance(lineas, (list, tuple)):
        partes = [str(x) for x in lineas]
    elif isinstance(lineas, str):
        partes = [p.strip() for p in lineas.split(",") if p.strip()]
    else:
        raise ValueError("líneas: texto «L1,L3-L5» o lista de enteros")
    out = []
    for p in partes:
        m = _LINEAS.match(p.strip())
        if not m:
            raise ValueError(f"líneas mal formadas: {p!r}")
        a, b = int(m.group(1)), int(m.group(2) or m.group(1))
        if b < a or b - a > MAX_LINEAS_CITA:
            raise ValueError(f"rango de líneas no válido: {p!r}")
        out += range(a, b + 1)
    if not out or len(out) > MAX_LINEAS_CITA:
        raise ValueError("una cita necesita entre 1 y 200 líneas")
    return sorted(set(out))


def lineas_a_texto(lineas) -> str:
    ns = parsear_lineas(lineas)
    grupos, ini = [], ns[0]
    for a, b in zip(ns, ns[1:] + [None]):
        if b != a + 1:
            grupos.append(f"L{ini}" if ini == a else f"L{ini}-L{a}")
            ini = b
    return ",".join(grupos)


def lineas_de_artefacto(contenido: str, numeracion: str) -> dict:
    """{número de línea: texto}. «prefijo_L»: cada línea empieza por «L<n>:» (extractos de un registro)."""
    out = {}
    for i, l in enumerate(contenido.split("\n"), 1):
        if numeracion == "prefijo_L":
            m = re.match(r"^L(\d{1,7}):\s?(.*)$", l)
            if m:
                out[int(m.group(1))] = m.group(2)
        else:
            out[i] = l
    return out


REGLAS_DECLARATIVAS = ("contiene", "no_contiene", "cuenta_regex", "lineas_existen", "cita_literal")


def evaluar_regla(regla: dict, contenido: str, numeracion: str = "archivo") -> tuple:
    """Comprobación DECLARATIVA sobre un texto (nada se ejecuta). Devuelve (cumple: bool, detalle)."""
    if not isinstance(regla, dict) or len(regla) != 1 or next(iter(regla)) not in REGLAS_DECLARATIVAS:
        raise ValueError("regla desconocida (válidas: " + ", ".join(REGLAS_DECLARATIVAS) + ")")
    (k, v), = regla.items()
    if k in ("contiene", "no_contiene"):
        if not isinstance(v, str) or not 1 <= len(v) <= 500:
            raise ValueError("texto de 1 a 500 caracteres")
        esta = v in contenido
        return (esta if k == "contiene" else not esta), f"{'aparece' if esta else 'no aparece'}: {v[:60]!r}"
    if k == "cuenta_regex":
        if not isinstance(v, dict) or not isinstance(v.get("patron"), str) or len(v["patron"]) > 200:
            raise ValueError("cuenta_regex: {patron, min, max}")
        n = len(re.findall(v["patron"], contenido[:MAX_ARTEFACTO_CHARS]))
        lo, hi = int(v.get("min", 0)), int(v.get("max", 10 ** 9))
        return lo <= n <= hi, f"{n} coincidencias (esperado {lo}–{hi})"
    lineas = lineas_de_artefacto(contenido, numeracion)
    if k == "lineas_existen":
        faltan = [n for n in parsear_lineas(v) if n not in lineas]
        return not faltan, ("todas existen" if not faltan else f"no existen: {faltan[:10]}")
    if not isinstance(v, dict) or not isinstance(v.get("texto"), str):
        raise ValueError("cita_literal: {linea, texto}")
    n = int(v.get("linea", -1))
    ok = n in lineas and v["texto"] in lineas[n]
    return ok, ("la línea contiene el texto citado" if ok else f"L{n} no contiene {v['texto'][:60]!r}")


class CuadernoAgente:
    """Espacio lógico de UN agente. Solo lee lo suyo y lo que el coordinador le compartió."""

    def __init__(self, reg: RegistroIncidencias, agente: str, max_operaciones=None):
        if agente not in AGENTES:
            raise ValueError(f"agente desconocido: {agente!r}")
        self.reg, self.agente = reg, agente
        self.max_operaciones = min(int(max_operaciones or config.LAB_MAX_OPERACIONES_SESION),
                                   config.LAB_MAX_OPERACIONES_SESION)
        self.operaciones = 0
        asegurar_esquema(reg)

    # --- escritura ------------------------------------------------------------------------------
    def tipos(self) -> tuple:
        return TIPOS_POR_AGENTE[self.agente] + TIPOS_COMUNES

    def registrar_decision(self, titulo, justificacion, relacionada=None, incidencia_id=None) -> str:
        """Historial de decisiones del agente (declaración: no demuestra que la decisión sea correcta)."""
        return self.anotar("decision", titulo, justificacion, resultado="informativo", relacionada=relacionada,
                           incidencia_id=incidencia_id)

    def registrar_aprendizaje(self, titulo, texto, apoyo) -> str:
        """Aprendizaje SUSTENTADO: `apoyo` debe ser una entrada visible con respaldo del sistema
        (simulación, análisis estático o registro). La base lo exige."""
        e = self.entrada(apoyo)
        return self.anotar("aprendizaje", titulo, json.dumps(
            {"texto": sanea.limpiar(texto, 1000), "apoyo": apoyo, "respaldo_del_apoyo": e["respaldo"],
             "resultado_del_apoyo": e["resultado"],
             "nota": "basado en un resultado simulado o estático, no en una prueba real"},
            ensure_ascii=False, sort_keys=True), resultado="informativo", relacionada=apoyo,
            incidencia_id=e["incidencia_id"])

    def anotar(self, tipo, titulo, contenido, resultado="pendiente", respaldo="declaracion_agente",
               procedencia=None, incidencia_id=None, hipotesis_id=None, experimento_id=None,
               sustituye=None, relacionada=None, run_id=None, fuente=None, lineas=None,
               condicion_falsacion=None, escenario=None, cita=None) -> str:
        if tipo not in self.tipos():
            raise ValueError(f"{self.agente} no registra entradas de tipo {tipo!r}")
        if resultado not in RESULTADOS or respaldo not in RESPALDOS:
            raise ValueError("resultado o respaldo desconocido")
        procedencia = procedencia or self.agente
        if procedencia not in PROCEDENCIAS:
            raise ValueError(f"procedencia desconocida: {procedencia!r}")
        if self.operaciones >= self.max_operaciones:
            raise LimiteExcedido(f"límite de {self.max_operaciones} escrituras por sesión en el cuaderno")
        tit = sanea.limpiar(titulo, MAX_TITULO + 1)
        cont = (sanea.limpiar_codigo if tipo in TIPOS_CODIGO else sanea.limpiar)(contenido, MAX_CONTENIDO + 1)
        if not tit or len(tit) > MAX_TITULO:
            raise LimiteExcedido(f"el título debe tener entre 1 y {MAX_TITULO} caracteres")
        if len(cont) > MAX_CONTENIDO:
            raise LimiteExcedido(f"el contenido supera {MAX_CONTENIDO} caracteres (no se recorta en silencio)")
        if fuente is not None and str(fuente).startswith("AR-"):          # V2-E.6: la cita debe existir
            self._comprobar_cita(fuente, lineas, cita)
        self.operaciones += 1
        with self.reg.con:
            c = self.reg.con.execute(
                "INSERT INTO cuaderno(id,ts,agente,tipo,titulo,contenido,sha256,resultado,respaldo,procedencia,"
                "incidencia_id,hipotesis_id,experimento_id,sustituye,relacionada,run_id,fuente,lineas,"
                "condicion_falsacion,escenario) "
                "VALUES(printf('NB-%06d', COALESCE((SELECT MAX(num) FROM cuaderno), 0) + 1),"
                "?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (self.reg.ahora(), self.agente, tipo, tit, cont, _sha(cont), resultado, respaldo, procedencia,
                 incidencia_id, hipotesis_id, experimento_id, sustituye, relacionada, run_id,
                 sanea.limpiar(fuente, 200) if fuente else None, lineas_a_texto(lineas) if lineas else None,
                 sanea.limpiar(condicion_falsacion, 500) if condicion_falsacion else None,
                 sanea.limpiar(escenario, 200) if escenario else None))
            return self.reg.con.execute("SELECT id FROM cuaderno WHERE num=?", (c.lastrowid,)).fetchone()[0]

    def anotar_resultado_de_experimento(self, eid, tipo, titulo=None) -> str:
        """Resultado de un experimento SIMULADO ya completado (positivo o negativo: ambos se guardan).
        Lo escribe el laboratorio, no el agente; el respaldo es «simulacion», nunca «prueba_real»."""
        e = self.reg.con.execute("SELECT id, estado, conclusion, incidencia_id, hipotesis_id, resultado_json, "
                                 "run_id FROM experimentos WHERE id=?", (eid,)).fetchone()
        if e is None or e["estado"] != "completado":
            raise ValueError("solo se anotan experimentos completados")
        contenido = json.dumps({"experimento": eid, "conclusion": e["conclusion"],
                                "resultado": json.loads(e["resultado_json"] or "null"),
                                "nota": "SIMULADO: no es una prueba real"}, ensure_ascii=False, sort_keys=True)
        return self.anotar(tipo, titulo or f"resultado simulado de {eid}", contenido,
                           resultado=DE_CONCLUSION.get(e["conclusion"], "no_concluyente"), respaldo="simulacion",
                           procedencia="laboratorio", incidencia_id=e["incidencia_id"],
                           hipotesis_id=e["hipotesis_id"], experimento_id=eid, run_id=e["run_id"])

    # --- lectura (aislada) ----------------------------------------------------------------------
    def _fila(self, r) -> dict:
        return dict(r) if r is not None else None

    def entradas(self, tipo=None, incluir_sustituidas=False) -> list:
        filas = [dict(r) for r in self.reg.con.execute(
            "SELECT * FROM cuaderno WHERE agente=? ORDER BY num", (self.agente,))]
        if not incluir_sustituidas:
            viejas = {f["sustituye"] for f in filas if f["sustituye"]}
            filas = [f for f in filas if f["id"] not in viejas]
        return [f for f in filas if tipo is None or f["tipo"] == tipo]

    def recibidas(self) -> list:
        return [dict(r) for r in self.reg.con.execute(
            "SELECT c.*, i.de_agente, i.motivo AS motivo_intercambio FROM intercambios i "
            "JOIN cuaderno c ON c.id = i.entrada_id WHERE i.para_agente=? ORDER BY i.num", (self.agente,))]

    def entrada(self, eid) -> dict:
        r = self.reg.con.execute("SELECT * FROM cuaderno WHERE id=?", (eid,)).fetchone()
        if r is None:
            raise KeyError(eid)
        if r["agente"] != self.agente and not self.reg.con.execute(
                "SELECT 1 FROM intercambios WHERE entrada_id=? AND para_agente=?", (eid, self.agente)).fetchone():
            raise AccesoDenegado(f"{self.agente} no tiene acceso a {eid}")
        return dict(r)

    def versiones(self, eid) -> list:
        """Cadena de versiones (de la más antigua a la más reciente) que contiene `eid`."""
        e = self.entrada(eid)
        if e["agente"] != self.agente:
            raise AccesoDenegado("las versiones solo se consultan en el cuaderno propio")
        while e["sustituye"]:
            e = self.entrada(e["sustituye"])
        cadena = [e]
        while True:
            r = self.reg.con.execute("SELECT * FROM cuaderno WHERE sustituye=? AND agente=? ORDER BY num LIMIT 1",
                                     (cadena[-1]["id"], self.agente)).fetchone()
            if r is None:
                return cadena
            cadena.append(dict(r))

    def comparar(self, id_a, id_b, max_lineas=60) -> dict:
        """Compara dos entradas visibles para este agente SIN modificar ninguna."""
        a, b = self.entrada(id_a), self.entrada(id_b)
        diff = list(difflib.unified_diff(a["contenido"].split("\n"), b["contenido"].split("\n"),
                                         id_a, id_b, lineterm="", n=1))
        return {"a": id_a, "b": id_b, "sha256_a": a["sha256"], "sha256_b": b["sha256"],
                "iguales": a["sha256"] == b["sha256"], "diff": diff[:max_lineas],
                "diff_recortado": len(diff) > max_lineas,
                "lineas_anadidas": sum(1 for l in diff if l.startswith("+") and not l.startswith("+++")),
                "lineas_quitadas": sum(1 for l in diff if l.startswith("-") and not l.startswith("---"))}

    def verificar_integridad(self) -> list:
        """IDs propios cuyo contenido ya no coincide con su SHA-256 (edición manual del archivo)."""
        return [r["id"] for r in self.reg.con.execute(
            "SELECT id, contenido, sha256 FROM cuaderno WHERE agente=? ORDER BY num", (self.agente,))
                if _sha(r["contenido"]) != r["sha256"]]

    # --- V2-E.6: artefactos, citas verificadas y comprobaciones declarativas ------------------------
    def artefacto(self, aid) -> dict:
        r = self.reg.con.execute("SELECT * FROM artefactos WHERE id=?", (aid,)).fetchone()
        if r is None:
            raise KeyError(aid)
        if r["espacio"] not in (self.agente, "comun"):
            raise AccesoDenegado(f"{self.agente} no tiene acceso al artefacto {aid}")
        d = dict(r)
        if _sha(d["contenido"]) != d["sha256"]:
            raise ValueError(f"el artefacto {aid} está alterado (SHA-256 distinto)")
        return d

    def registrar_artefacto(self, nombre, contenido, origen, numeracion="archivo", sustituye=None) -> str:
        """Artefacto de TEXTO en el espacio propio (p. ej. un parche propuesto o una nota). No se ejecuta."""
        return registrar_artefacto(self.reg, self.agente, nombre, contenido, origen, numeracion, "laboratorio",
                                   sustituye)

    def _comprobar_cita(self, fuente, lineas, cita):
        """Rechaza evidencia insuficiente: el artefacto debe ser visible, las líneas existir y, si se da
        `cita`, aparecer literalmente en esas líneas."""
        a = self.artefacto(fuente)
        if lineas is None:
            raise ValueError("evidencia insuficiente: falta indicar las líneas")
        mapa = lineas_de_artefacto(a["contenido"], a["numeracion"])
        faltan = [n for n in parsear_lineas(lineas) if n not in mapa]
        if faltan:
            raise ValueError(f"evidencia insuficiente: {fuente} no tiene las líneas {faltan[:10]}")
        if cita is not None:
            texto = "\n".join(mapa[n] for n in parsear_lineas(lineas))
            if not cita or cita not in texto:
                raise ValueError(f"evidencia insuficiente: la cita no aparece en {fuente} {lineas_a_texto(lineas)}")

    def citar(self, tipo, fuente, lineas, cita, texto, **kw) -> str:
        """Evidencia con fuente y líneas. La cita se comprueba contra el artefacto antes de guardarla."""
        return self.anotar(tipo, kw.pop("titulo", f"cita {fuente} {lineas_a_texto(lineas)}"), json.dumps(
            {"cita": sanea.limpiar(cita, 500), "texto": sanea.limpiar(texto, 1500)}, ensure_ascii=False),
            fuente=fuente, lineas=lineas, cita=cita, **kw)


class LaboratorioA1(CuadernoAgente):
    """Programación: soluciones, alternativas, versiones candidatas y comparación de correcciones."""

    def __init__(self, reg, **kw):
        super().__init__(reg, "A1", **kw)

    def registrar_solucion(self, titulo, codigo, incidencia_id=None, run_id=None) -> str:
        return self.anotar("solucion", titulo, codigo, incidencia_id=incidencia_id, run_id=run_id)

    def registrar_alternativa(self, de, titulo, codigo) -> str:
        e = self.entrada(de)
        return self.anotar("alternativa", titulo, codigo, relacionada=de, incidencia_id=e["incidencia_id"])

    def nueva_version(self, eid, codigo, titulo=None) -> str:
        """Versión candidata nueva: la anterior queda intacta y se puede comparar."""
        e = self.entrada(eid)
        return self.anotar(e["tipo"], titulo or e["titulo"], codigo, sustituye=eid,
                           incidencia_id=e["incidencia_id"])

    def proponer_parche(self, titulo, diff_texto, supuestos=(), riesgos=(), incidencia_id=None,
                        escenario=None) -> dict:
        """Parche COMO TEXTO (nunca se aplica ni se ejecuta), con sus supuestos y riesgos enlazados."""
        pid = self.anotar("parche_texto", titulo, diff_texto, incidencia_id=incidencia_id, escenario=escenario)
        sup = [self.anotar("supuesto", f"supuesto de {pid}", s, relacionada=pid, resultado="informativo")
               for s in supuestos]
        rie = [self.anotar("riesgo", f"riesgo de {pid}", r, relacionada=pid, resultado="informativo") for r in riesgos]
        return {"parche": pid, "supuestos": sup, "riesgos": rie, "nota": "texto: no se ha aplicado ni ejecutado"}

    def registrar_contrato(self, titulo, contrato, relacionada=None) -> str:
        return self.anotar("contrato", titulo, contrato, relacionada=relacionada, resultado="informativo")

    def proponer_prueba(self, titulo, descripcion, relacionada=None) -> str:
        """Prueba PROPUESTA (texto); no se ejecuta (Modo B deshabilitado)."""
        return self.anotar("prueba_propuesta", titulo, descripcion, relacionada=relacionada)

    def comparar_correcciones(self, id_a, id_b) -> tuple:
        cmp = self.comparar(id_a, id_b)
        resumen = {k: cmp[k] for k in ("a", "b", "sha256_a", "sha256_b", "iguales", "lineas_anadidas",
                                       "lineas_quitadas")}
        eid = self.anotar("comparacion_correcciones", f"comparación {id_a} / {id_b}",
                          json.dumps(resumen, sort_keys=True), resultado="informativo", relacionada=id_a)
        return eid, cmp


class LaboratorioA2(CuadernoAgente):
    """Análisis: investigaciones, causas raíz, evidencias y comparación de hipótesis existentes."""

    def __init__(self, reg, **kw):
        super().__init__(reg, "A2", **kw)

    def investigar(self, incidencia_id, titulo, notas) -> str:
        self.reg.obtener(incidencia_id)                       # KeyError si no existe
        return self.anotar("investigacion", titulo, notas, incidencia_id=incidencia_id)

    def proponer_causa_raiz(self, incidencia_id, texto, hipotesis_id=None) -> str:
        return self.anotar("causa_raiz", "causa raíz propuesta", texto, incidencia_id=incidencia_id,
                           hipotesis_id=hipotesis_id)

    def perfilar(self, artefacto_id, patrones: dict) -> str:
        """PERFILADO ESTÁTICO de un artefacto de texto: cuenta coincidencias de patrones y registra en qué
        líneas aparecen. No mide rendimiento: no hay ni se inventan benchmarks."""
        a = self.artefacto(artefacto_id)
        mapa = lineas_de_artefacto(a["contenido"], a["numeracion"])
        res, todas = {}, []
        for nombre, patron in sorted((patrones or {}).items())[:20]:
            if not isinstance(patron, str) or len(patron) > 200:
                raise ValueError("patrón de 1 a 200 caracteres")
            ls = [n for n, l in sorted(mapa.items()) if re.search(patron, l)]
            res[nombre] = {"patron": patron, "coincidencias": len(ls), "lineas": ls[:50]}
            todas += ls
        if not todas:
            raise ValueError("evidencia insuficiente: ningún patrón aparece en el artefacto")
        return self.anotar("perfilado_estatico", f"perfil de {artefacto_id}", json.dumps(
            {"artefacto": artefacto_id, "sha256": a["sha256"], "resultados": res,
             "nota": "recuento estático de líneas; NO es un perfil de CPU/GPU ni una medida de rendimiento"},
            ensure_ascii=False, sort_keys=True), resultado="informativo", respaldo="analisis_estatico",
            procedencia="laboratorio", fuente=artefacto_id, lineas=sorted(set(todas))[:MAX_LINEAS_CITA])

    def hipotesis_competidora(self, texto, condicion_falsacion, relacionada=None, incidencia_id=None,
                              confianza="baja") -> str:
        if confianza not in ("baja", "media", "alta"):
            raise ValueError("confianza: baja | media | alta")
        return self.anotar("hipotesis_competidora", texto[:120] or "hipótesis", json.dumps(
            {"hipotesis": sanea.limpiar(texto, 1000), "confianza": confianza}, ensure_ascii=False),
            condicion_falsacion=condicion_falsacion, relacionada=relacionada, incidencia_id=incidencia_id)

    def solicitar_datos(self, descripcion, motivo) -> str:
        return self.anotar("solicitud_datos", descripcion[:120], json.dumps(
            {"falta": sanea.limpiar(descripcion, 500), "para_que": sanea.limpiar(motivo, 500)}, ensure_ascii=False))

    def comparar_explicaciones(self, incidencia_id) -> dict:
        """Hipótesis de la incidencia con sus experimentos (de la infraestructura V2-E.4). Solo lectura."""
        self.reg.obtener(incidencia_id)
        hips = []
        for h in self.reg.con.execute("SELECT id, actor, texto, archivo, patron, estado FROM hipotesis "
                                      "WHERE incidencia_id=? ORDER BY num", (incidencia_id,)):
            exps = [dict(e) for e in self.reg.con.execute(
                "SELECT id, rol, estado, conclusion, version FROM experimentos WHERE hipotesis_id=? ORDER BY num",
                (h["id"],))]
            hips.append(dict(h, experimentos=exps,
                             reproduccion=any(e["rol"] == "reproduccion" and e["conclusion"] == "apoya" for e in exps),
                             control=any(e["rol"] == "control" and e["conclusion"] == "apoya" for e in exps)))
        orden = {"respaldada": 0, "consistente": 1, "propuesta": 2, "ambigua": 3, "refutada": 4}
        return {"incidencia": incidencia_id,
                "hipotesis": sorted(hips, key=lambda x: (orden.get(x["estado"], 9), x["id"])),
                "nota": "«respaldada» es una correlación simulada entre versiones, no una causa demostrada"}


class LaboratorioA3(CuadernoAgente):
    """Verificación: casos de prueba, regresiones propuestas, objeciones, contradicciones y pendientes."""

    def __init__(self, reg, **kw):
        super().__init__(reg, "A3", **kw)

    def preparar_caso(self, titulo, descripcion, incidencia_id=None) -> str:
        return self.anotar("caso_prueba", titulo, descripcion, incidencia_id=incidencia_id)

    def registrar_objecion(self, objecion, evidencia, propuesta, enunciado="", incidencia_id=None) -> str:
        c = criticas.clasificar(objecion, evidencia, propuesta, enunciado)
        contenido = json.dumps({"objecion": sanea.limpiar(objecion, 300), "evidencia": sanea.limpiar(evidencia or "", 300),
                                "clasificacion": c["estado"], "motivo": c["motivo"]}, ensure_ascii=False,
                               sort_keys=True)
        return self.anotar("objecion", sanea.limpiar(objecion, 120) or "objeción", contenido,
                           incidencia_id=incidencia_id)

    def registrar_contradiccion(self, descripcion, referencias=()) -> str:
        return self.anotar("contradiccion", "contradicción", json.dumps(
            {"descripcion": sanea.limpiar(descripcion, 1000), "referencias": [str(r)[:40] for r in referencias][:10]},
            ensure_ascii=False, sort_keys=True))

    def contraejemplo(self, texto, fuente, lineas, cita, relacionada=None) -> str:
        return self.citar("contraejemplo", fuente, lineas, cita, texto, relacionada=relacionada,
                          titulo=f"contraejemplo {fuente} {lineas_a_texto(lineas)}")

    def comprobar(self, objetivo_id, regla, relacionada=None, escenario=None) -> str:
        """Comprobación DECLARATIVA y reproducible que evalúa EL LABORATORIO (no el agente) sobre un
        artefacto visible (AR-...) o una entrada visible (NB-...). Resultado positivo o negativo."""
        if str(objetivo_id).startswith("AR-"):
            a = self.artefacto(objetivo_id)
            contenido, numeracion, sha = a["contenido"], a["numeracion"], a["sha256"]
        else:
            e = self.entrada(objetivo_id)
            contenido, numeracion, sha = e["contenido"], "archivo", e["sha256"]
        ok, detalle = evaluar_regla(regla, contenido, numeracion)
        if relacionada is None and not str(objetivo_id).startswith("AR-"):
            relacionada = objetivo_id                  # la comprobación queda enlazada a lo comprobado
        return self.anotar("comprobacion_declarativa", f"comprobación sobre {objetivo_id}", json.dumps(
            {"objetivo": objetivo_id, "sha256_objetivo": sha, "regla": regla, "cumple": ok, "detalle": detalle},
            ensure_ascii=False, sort_keys=True), resultado="positivo" if ok else "negativo",
            respaldo="analisis_estatico", procedencia="laboratorio", relacionada=relacionada, escenario=escenario,
            fuente=objetivo_id if str(objetivo_id).startswith("AR-") else None,
            lineas=(regla.get("lineas_existen") if "lineas_existen" in regla else
                    [regla["cita_literal"]["linea"]] if "cita_literal" in regla else None))

    def falsar(self, hipotesis_id, condicion, resultado="pendiente") -> str:
        self.entrada(hipotesis_id)                                       # debe ser visible
        return self.anotar("falsacion", f"falsación de {hipotesis_id}", sanea.limpiar(condicion, 1000),
                           condicion_falsacion=condicion, relacionada=hipotesis_id, resultado=resultado)

    def rechazar(self, entrada_id, motivo) -> str:
        self.entrada(entrada_id)
        return self.anotar("rechazo", f"rechazo de {entrada_id}", motivo, relacionada=entrada_id,
                           resultado="negativo")

    def abstenerse(self, motivo, relacionada=None) -> str:
        return self.anotar("abstencion", "abstención razonada", motivo, relacionada=relacionada,
                           resultado="no_concluyente")

    def pendientes(self) -> dict:
        """Lo que queda por verificar (solo lectura)."""
        return {"objeciones": [e["id"] for e in self.entradas("objecion") if e["resultado"] == "pendiente"],
                "casos": [e["id"] for e in self.entradas("caso_prueba") if e["resultado"] == "pendiente"],
                "hipotesis_sin_respaldo": [r[0] for r in self.reg.con.execute(
                    "SELECT id FROM hipotesis WHERE estado IN ('propuesta','consistente') ORDER BY num")],
                "experimentos_planificados": [r[0] for r in self.reg.con.execute(
                    "SELECT id FROM experimentos WHERE estado='planificado' ORDER BY num")],
                "regresiones": [r[0] for r in self.reg.con.execute("SELECT id FROM regresiones ORDER BY num")]}


CLASES = {"A1": LaboratorioA1, "A2": LaboratorioA2, "A3": LaboratorioA3}


def registrar_artefacto(reg, espacio, nombre, contenido, origen, numeracion="archivo", procedencia="laboratorio",
                        sustituye=None) -> str:
    """Artefacto de texto con SHA-256 (solo anexar). `espacio`: A1/A2/A3 o «comun» (solo lectura para
    todos, p. ej. un corpus de diagnóstico)."""
    asegurar_esquema(reg)
    cont = contenido if isinstance(contenido, str) else ""
    if not cont or len(cont) > MAX_ARTEFACTO_CHARS:
        raise LimiteExcedido(f"el artefacto debe tener entre 1 y {MAX_ARTEFACTO_CHARS} caracteres")
    n = len(lineas_de_artefacto(cont, numeracion))
    if numeracion == "prefijo_L" and n == 0:
        raise ValueError("numeración «prefijo_L» sin líneas «L<n>:»")
    with reg.con:
        c = reg.con.execute(
            "INSERT INTO artefactos(id,ts,espacio,nombre,origen,numeracion,sha256,lineas,contenido,procedencia,sustituye) "
            "VALUES(printf('AR-%06d', COALESCE((SELECT MAX(num) FROM artefactos), 0) + 1),?,?,?,?,?,?,?,?,?,?)",
            (reg.ahora(), espacio, sanea.limpiar(nombre, 200), sanea.limpiar(origen, 300), numeracion, _sha(cont), n,
             cont, procedencia, sustituye))
        return reg.con.execute("SELECT id FROM artefactos WHERE num=?", (c.lastrowid,)).fetchone()[0]


def laboratorio_de(reg, agente, **kw) -> CuadernoAgente:
    if agente not in CLASES:
        raise ValueError(f"agente desconocido: {agente!r}")
    return CLASES[agente](reg, **kw)


class Coordinador:
    """Único camino para que un agente vea resultados de otro (intercambio controlado y auditable)."""

    def __init__(self, reg: RegistroIncidencias):
        self.reg = reg
        asegurar_esquema(reg)

    def compartir(self, entrada_id, para_agente, motivo) -> int:
        if para_agente not in AGENTES:
            raise ValueError(f"agente desconocido: {para_agente!r}")
        r = self.reg.con.execute("SELECT agente FROM cuaderno WHERE id=?", (entrada_id,)).fetchone()
        if r is None:
            raise KeyError(entrada_id)
        m = sanea.limpiar(motivo, 300)
        if not m:
            raise ValueError("el intercambio necesita un motivo")
        try:
            with self.reg.con:
                c = self.reg.con.execute(
                    "INSERT INTO intercambios(ts,entrada_id,de_agente,para_agente,actor,motivo) "
                    "VALUES(?,?,?,?,'coordinador',?)", (self.reg.ahora(), entrada_id, r[0], para_agente, m))
        except sqlite3.IntegrityError as e:
            raise ValueError(f"intercambio rechazado: {e}") from None
        return c.lastrowid

    def comparar(self, incidencia_id=None) -> dict:
        """V2-E.5-r3: compara los cuadernos de los tres agentes (sin compartir nada) y detecta
        DESACUERDOS deterministas:
          * resultados_opuestos: entradas de agentes distintos sobre el MISMO experimento o hipótesis,
            una «positivo» y otra «negativo»;
          * solucion_con_objecion_pendiente: A1 da una solución por positiva mientras A3 mantiene una
            objeción pendiente sobre la misma incidencia;
          * hipotesis_distintas: agentes distintos proponen causas o hipótesis con hipótesis registradas
            DIFERENTES para la misma incidencia;
          * decisiones_divergentes: agentes distintos registran decisiones con resultado distinto
            sobre la misma entrada relacionada.
        Un desacuerdo no dice quién tiene razón: se informa para que el usuario o el coordinador decidan."""
        q = "SELECT * FROM cuaderno" + (" WHERE incidencia_id=?" if incidencia_id else "") + " ORDER BY num"
        filas = [dict(r) for r in self.reg.con.execute(q, (incidencia_id,) if incidencia_id else ())]
        viejas = {f["sustituye"] for f in filas if f["sustituye"]}
        vigentes = [f for f in filas if f["id"] not in viejas]
        desac = []

        def opuestos(clave, etiqueta):
            grupos = {}
            for f in vigentes:
                if f[clave] and f["resultado"] in ("positivo", "negativo"):
                    grupos.setdefault(f[clave], []).append(f)
            for k, fs in sorted(grupos.items()):
                pos = sorted({f["agente"] for f in fs if f["resultado"] == "positivo"})
                neg = sorted({f["agente"] for f in fs if f["resultado"] == "negativo"})
                if pos and neg and len(set(pos) | set(neg)) > 1:                 # entre agentes distintos
                    desac.append({"tipo": "resultados_opuestos", etiqueta: k, "positivo": pos, "negativo": neg,
                                  "entradas": [f["id"] for f in fs]})
        opuestos("experimento_id", "experimento")
        opuestos("hipotesis_id", "hipotesis")
        por_inc = {}
        for f in vigentes:
            if f["incidencia_id"]:
                por_inc.setdefault(f["incidencia_id"], []).append(f)
        for inc, fs in sorted(por_inc.items()):
            sol = [f["id"] for f in fs if f["agente"] == "A1" and f["tipo"] in ("solucion", "candidata", "alternativa")
                   and f["resultado"] == "positivo"]
            obj = [f["id"] for f in fs if f["agente"] == "A3" and f["tipo"] == "objecion" and f["resultado"] == "pendiente"]
            if sol and obj:
                desac.append({"tipo": "solucion_con_objecion_pendiente", "incidencia": inc, "soluciones": sol,
                              "objeciones": obj})
            hips = {}
            for f in fs:
                if f["hipotesis_id"] and f["tipo"] in ("causa_raiz", "hipotesis"):
                    hips.setdefault(f["agente"], set()).add(f["hipotesis_id"])
            if len(hips) > 1 and len(set().union(*hips.values())) > 1:
                desac.append({"tipo": "hipotesis_distintas", "incidencia": inc,
                              "por_agente": {a: sorted(h) for a, h in sorted(hips.items())}})
        decs = {}
        for f in vigentes:
            if f["tipo"] == "decision" and f["relacionada"]:
                decs.setdefault(f["relacionada"], {}).setdefault(f["agente"], set()).add(f["sha256"])
        for rel, por_ag in sorted(decs.items()):
            if len(por_ag) > 1 and len(set().union(*por_ag.values())) > 1:
                desac.append({"tipo": "decisiones_divergentes", "relacionada": rel, "agentes": sorted(por_ag)})
        resumen = {ag: {} for ag in AGENTES}
        for f in vigentes:
            resumen[f["agente"]].setdefault(f["tipo"], {}).setdefault(f["resultado"], 0)
            resumen[f["agente"]][f["tipo"]][f["resultado"]] += 1
        return {"incidencia": incidencia_id, "por_agente": resumen, "desacuerdos": desac,
                "nota": "un desacuerdo no indica quién tiene razón; ningún resultado simulado es una prueba real"}

    # --- V2-E.6: pendientes explícitos ---------------------------------------------------------------
    def pendiente(self, entrada_id, estado, motivo, evidencia_id=None, actor="coordinador") -> int:
        """Anota el estado de una propuesta (historial de solo anexar; la base valida la transición y que
        «verificado» tenga una comprobación positiva del sistema)."""
        if estado not in ESTADOS_PENDIENTE:
            raise ValueError("estado de pendiente desconocido")
        try:
            with self.reg.con:
                return self.reg.con.execute(
                    "INSERT INTO pendientes(ts,entrada_id,estado,motivo,evidencia_id,actor) VALUES(?,?,?,?,?,?)",
                    (self.reg.ahora(), entrada_id, estado, sanea.limpiar(motivo, 500) or "-", evidencia_id,
                     actor)).lastrowid
        except sqlite3.IntegrityError as e:
            raise ValueError(f"pendiente rechazado: {e}") from None

    def estado_pendiente(self, entrada_id):
        r = self.reg.con.execute("SELECT estado FROM pendientes WHERE entrada_id=? ORDER BY num DESC LIMIT 1",
                                 (entrada_id,)).fetchone()
        return r[0] if r else None

    def pendientes(self) -> dict:
        """{estado: [entradas]} con el estado VIGENTE de cada propuesta."""
        out = {e: [] for e in ESTADOS_PENDIENTE}
        for r in self.reg.con.execute("SELECT entrada_id, estado FROM pendientes p WHERE num = (SELECT MAX(num) "
                                      "FROM pendientes q WHERE q.entrada_id = p.entrada_id) ORDER BY num"):
            out[r[1]].append(r[0])
        return out

    def desde_deliberacion(self, entrada_id, resultado, motivo="") -> int:
        """Traduce el resultado de una deliberación a un pendiente. El consenso NUNCA es «verificado»:
        aprobada -> propuesta; aprobada_con_cambios -> cambios_solicitados; rechazada -> rechazado_justificado."""
        mapa = {"aprobada": "propuesta", "aprobada_con_cambios": "cambios_solicitados",
                "rechazada": "rechazado_justificado"}
        if resultado not in mapa:
            return self.pendiente(entrada_id, "propuesta", f"resultado {resultado}: sin decisión clara")
        return self.pendiente(entrada_id, mapa[resultado],
                              f"deliberación: {resultado} (el consenso no es verificación). {motivo}".strip())

    def comparar_alternativas(self, ids) -> list:
        """Compara alternativas por rasgos DETERMINISTAS: supuestos y riesgos enlazados, comprobaciones
        positivas/negativas, rechazos y estado del pendiente. No decide cuál es mejor."""
        out = []
        for eid in ids:
            r = self.reg.con.execute("SELECT id, agente, tipo, sha256, length(contenido) FROM cuaderno WHERE id=?",
                                     (eid,)).fetchone()
            if r is None:
                raise KeyError(eid)
            cuenta = lambda tipo, res=None: self.reg.con.execute(  # noqa: E731
                "SELECT COUNT(*) FROM cuaderno WHERE relacionada=? AND tipo=? AND (? IS NULL OR resultado=?)",
                (eid, tipo, res, res)).fetchone()[0]
            out.append({"id": eid, "agente": r[1], "tipo": r[2], "sha256": r[3], "caracteres": r[4],
                        "supuestos": cuenta("supuesto"), "riesgos": cuenta("riesgo"),
                        "comprobaciones_positivas": cuenta("comprobacion_declarativa", "positivo"),
                        "comprobaciones_negativas": cuenta("comprobacion_declarativa", "negativo"),
                        "rechazos": cuenta("rechazo"), "pendiente": self.estado_pendiente(eid)})
        return out

    def resumen(self) -> dict:
        out = {ag: {} for ag in AGENTES}
        for r in self.reg.con.execute("SELECT agente, tipo, resultado, COUNT(*) FROM cuaderno "
                                      "GROUP BY agente, tipo, resultado ORDER BY agente, tipo, resultado"):
            out[r[0]].setdefault(r[1], {})[r[2]] = r[3]
        n = self.reg.con.execute("SELECT COUNT(*) FROM intercambios").fetchone()[0]
        return {"por_agente": out, "intercambios": n,
                "limites": {"entradas_por_agente": MAX_ENTRADAS_AGENTE, "intercambios": MAX_INTERCAMBIOS,
                            "caracteres_por_entrada": MAX_CONTENIDO,
                            "escrituras_por_sesion": config.LAB_MAX_OPERACIONES_SESION}}
