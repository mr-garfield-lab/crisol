#!/usr/bin/env python3
"""verificar.py — VERIFICADOR INTEGRAL de Equipo IA (V2-E.6; ampliado en V2-F). Un único comando:

    python3 -B verificar.py                    batería completa: TODO lo seguro disponible, por fases
    python3 -B verificar.py --rapido           sin repeticiones (más corto)
    python3 -B verificar.py --lista            catálogo de pruebas por fase, sin ejecutar nada
    python3 -B verificar.py --lista-demos      órdenes de demostración por función (para ejecutarlas a mano)
    python3 -B verificar.py --demo             solo la fase de demostraciones (todas SIMULADAS)
    python3 -B verificar.py --solo V-STOP      solo las pruebas cuyo identificador empieza así (repetible)
    python3 -B verificar.py --semilla 7        semilla adicional para las pruebas variables (fijas: 11, 42, 2026)
    python3 -B verificar.py --repeticiones 10  repeticiones para buscar errores intermitentes (1–50)
    python3 -B verificar.py --fallo-controlado añade una prueba que FALLA a propósito (comprueba el verificador)
    python3 -B verificar.py --autorizar-paquete RUTA.zip   el USUARIO autoriza un paquete de auditoría/desafío
    python3 -B verificar.py --qwen-real --iniciar-servidor-real   añade pruebas con el modelo REAL

Qué hace:
  1. PREPARA el entorno (carpeta de trabajo aislada con HOME y TMPDIR propios, catálogo de pruebas).
  2. Muestra «*** INICIO DE GRABACIÓN / PRUEBAS ***» y ejecuta las FASES en orden, cada una entre
     «===== INICIO FASE …» y «===== FIN FASE …». Cada comprobación muestra identificador, descripción,
     resultado, duración y su NATURALEZA: REAL (comprueba el árbol o la plataforma reales, o el modelo real),
     SIMULADA (backends simulados, servidor FALSO o datos sintéticos), OMITIDA o NO VERIFICADA.
  3. Escribe en $TMPDIR/equipo_f2/lab_v2f1/verificacion/<id>/: informe.json, informe.md, terminal.log
     (todo lo mostrado), eventos.jsonl (inicio/fin de cada comprobación con CPU y RAM), trazas de los
     fallos, cumplimiento_resultado.{json,md}, diff_r3.json y las salidas de las demostraciones.
  4. Sale con 0 si no hay fallos, 1 si hay fallos y 2 si no se pudo preparar.
Métricas: CPU (getrusage de este proceso y de sus hijos) y RAM disponible (/proc/meminfo) MEDIDAS cuando la
plataforma lo permite; si no, se marca «medido: false». No son medidas de Qwen salvo en la fase QWEN.
No modifica el proyecto existente, no ejecuta código generado por los agentes, ni código de paquetes, ni
retos/zomboid_v1/material_original/generar_reto.py.
"""
import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    import resource                                     # no existe en Windows
except ImportError:                                     # pragma: no cover
    resource = None

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ / "src"))
sys.dont_write_bytecode = True

VERSION = config = PA = plataforma = rutas = None          # se cargan en cargar_nucleo()
CARPETA_LAB = "lab_v2f1"                                      # también en config.CARPETA_ACTUAL (sin núcleo: literal)


def cargar_nucleo():
    """Importa el núcleo DESPUÉS de comprobar las huellas (un núcleo alterado no se importa a ciegas)."""
    global VERSION, config, PA, plataforma, rutas
    from eq2 import VERSION as v, config as c, paquetes_auditoria as pa, plataforma as pl, rutas as ru
    VERSION, config, PA, plataforma, rutas = v, c, pa, pl, ru


INICIO = "*** INICIO DE GRABACIÓN / PRUEBAS ***"
FIN = "*** FIN DE GRABACIÓN / PRUEBAS ***"
ESTADOS = ("OK", "FALLO", "OMITIDA", "NO_VERIFICADA", "NO_DISPONIBLE")
AREAS = {
    1: ("INT", "Integridad del paquete y estructura del proyecto"),
    2: ("EST", "Validación estática y seguridad"),
    3: ("UNI", "Pruebas unitarias y regresiones"),
    4: ("MOT", "Motor, estados y transiciones"),
    5: ("STOP", "STOP, cancelaciones, reanudación y recuperación"),
    6: ("SRV", "Inicio y cierre del servidor local"),
    7: ("PROC", "Procesos, puertos y archivos temporales"),
    8: ("AGT", "Agentes A1, A2 y A3, roles, independencia, deliberaciones y personalidad"),
    9: ("MEM", "Memoria, SQLite, incidentes y auditoría"),
    10: ("LAB", "Laboratorios individuales y pendientes del coordinador"),
    11: ("CRI", "Clasificación de críticas y evidencias"),
    12: ("CON", "Contratos de integración, compatibilidad y paquetes de auditoría"),
    13: ("REP", "Pruebas repetidas (errores intermitentes)"),
    14: ("QWEN", "Pruebas con Qwen real (solo con autorización explícita)"),
    15: ("CTX", "Contexto, tokens y recursos"),
    16: ("APR", "Aprendizaje acotado y auditable"),
    17: ("VAR", "Pruebas variables con semillas, oráculos ocultos y adversarios"),
    18: ("ZOM", "Reto Zomboid y paquetes de desafío"),
    19: ("DEMO", "Demostraciones por función (todas SIMULADAS)"),
    20: ("CUM", "Cumplimiento, cambios frente a r3 y evidencias de fábrica"),
    21: ("CIE", "Cierre: procesos, temporales y __pycache__ tras las pruebas"),
    22: ("CAP", "V2-F: plan, debate por evidencias, memoria de experiencias, autocorrección y herramientas"),
    23: ("BAN", "V2-F: banco comparativo un agente frente al equipo (oráculos ocultos)"),
    24: ("FUN", "V2-F.1: función supervisada A1/A2/A3 sin ejecución dinámica e interfaces para Codex"),
}
ORDEN_FASES = (1, 2, 3, 15, 4, 5, 6, 7, 8, 9, 10, 11, 12, 16, 17, 18, 22, 23, 24, 13, 19, 20, 21, 14)
# Módulo de pruebas -> área. Una clase puede tener un área propia (MAPA_CLASES).
MAPA_MODULOS = {"test_contexto": 3, "test_correcciones": 3, "test_protocolo": 3, "test_sanea": 2, "test_estatico": 2,
                "test_memoria": 9, "test_orquestador": 8, "test_v2_backend": 6, "test_v2_cli": 8, "test_v2_cliente": 7,
                "test_v2_servidor": 6, "test_v2b": 3, "test_v2c": 3, "test_v2d": 3, "test_v2e": 4, "test_v2e1": 3,
                "test_v2e2": 9, "test_v2e3": 9, "test_v2e4": 9, "test_v2e4r2": 9, "test_v2e5": 11, "test_v2e5r2": 12,
                "test_v2e5r3_stop": 5, "test_v2e5r3": 12, "test_vigilancia": 7, "test_verificador": 12,
                # V2-E.6
                "test_v2e6_contexto": 15, "test_v2e6_laboratorios": 10, "test_v2e6_agentes": 8,
                "test_v2e6_aprendizaje": 16, "test_v2e6_retos": 18, "test_v2e6_calidad": 5,
                "test_v2e6r2_adversarial": 16,                                    # V2-E.6-r2
                "test_v2e6r3_indirecta": 16,                                      # V2-E.6-r3
                "test_v2e7_equipo": 8,                                            # V2-E.7
                "test_v2e7r2_modlab": 8,                                          # V2-E.7-r2
                "test_v2e7r3_auditoria_pz": 8,                                    # V2-E.7-r3
                "test_v2f_componentes": 22, "test_v2f_motor": 22, "test_v2f_debate": 22,  # V2-F
                "test_v2f_tareas": 22, "test_v2f_banco": 23,
                "test_v2f1_funcion": 24, "test_v2f1_codex": 24}                   # V2-F.1
MAPA_CLASES = {("test_v2e5", "TestMotorRevisiones"): 11, ("test_v2e5", "TestAdaptadores"): 12,
               ("test_v2e5", "TestExtensionesFuturas"): 12, ("test_v2e5", "TestVersionV2E5"): 12,
               ("test_v2e5r2", "TestFormatosDeRevision"): 11, ("test_v2e5r2", "TestCorpusCriticas"): 11,
               ("test_v2e5r2", "TestLaboratorios"): 10, ("test_v2e5r2", "TestValidacionPersonalidad"): 8,
               ("test_v2e5r2", "TestEleccion"): 8, ("test_v2e5r2", "TestGestion"): 8,
               ("test_v2e5r2", "TestProteccion"): 8, ("test_v2e", "TestMotorServidorFalso"): 4,
               ("test_v2e5r3", "TestLaboratoriosR3"): 10, ("test_v2e5r3", "TestCategoriasCriticas"): 11,
               ("test_v2e6_retos", "TestPruebasVariables"): 17, ("test_v2e6_calidad", "TestAislamientoYTransacciones"): 9}
ESTRUCTURA = ("src/eq2/__init__.py", "src/eq2/config.py", "src/eq2/motor.py", "src/eq2/orquestador.py",
              "src/eq2/personalidad.py", "src/eq2/laboratorios.py", "src/eq2/paquetes_auditoria.py",
              "src/eq2/perfiles_contexto.py", "src/eq2/aprendizaje.py", "src/eq2/evaluacion_aprendizaje.py",
              "src/eq2/independencia.py", "src/eq2/roles.py", "src/eq2/contaminacion.py", "src/eq2/retos.py", "src/eq2/pruebas_variables.py",
              "validar_estatico.py", "ejecutar_v2.py", "auditar.py", "perfiles.py", "verificar.py", "aprender.py",
              "retos.py", "tests/_comun.py", "tests/fake_llama_server.py", "contratos/personalidad_v1.json",
              "auditoria_ejemplo/auditoria_ejemplo.zip", "retos/zomboid_v1/material_original/MANIFIESTO.json",
              "retos/zomboid_v1/paquete_desafio/desafio_zomboid_v1.zip", "cumplimiento.json", "LEEME_V2E6.md",
              "CAMBIOS_V2E6.md", "CUMPLIMIENTO_V2E6.md", "LIMITES_Y_RIESGOS_V2E6.md", "ROLLBACK_V2E6.md",
              "VERIFICADOR.md", "herramientas/manifiesto_r3.txt", "herramientas/manifiesto_v2e6.txt",
              "LEEME_V2E6R2.md", "CAMBIOS_V2E6R2.md", "herramientas/manifiesto_v2e6r2.txt",
              "LEEME_V2E6R3.md", "CAMBIOS_V2E6R3.md",
              # V2-E.7
              "equipo.py", "src/eq2/tareas.py", "src/eq2/ejecutor_restringido.py", "src/eq2/corredor_pruebas.py",
              "ejemplos/tarea_demo.json", "herramientas/manifiesto_v2e6r3.txt", "LEEME_V2E7.md", "CAMBIOS_V2E7.md",
              # V2-E.7-r2
              "src/eq2/modlab_pz_adaptador.py", "modlab_pz/contrato_agentes.json", "modlab_pz/laboratorio.py",
              "modlab_pz/lua_analisis.py", "ejemplos/tarea_pz_fallo_intencional.json", "herramientas/manifiesto_v2e7.txt",
              "LEEME_V2E7R2.md", "CAMBIOS_V2E7R2.md",
              # V2-E.7-r3
              "src/eq2/evidencia_pz.py", "herramientas/manifiesto_v2e7r2.txt", "LEEME_V2E7R3.md", "CAMBIOS_V2E7R3.md",
              # V2-F
              "src/eq2/casos.py", "src/eq2/herramientas.py", "src/eq2/planificacion.py", "src/eq2/autocorreccion.py",
              "src/eq2/experiencias.py", "src/eq2/motor_v2f.py", "src/eq2/debate.py", "src/eq2/banco_capacidades.py",
              "banco.py", "bancos/capacidades_v1/tareas.json", "bancos/capacidades_v1/oraculos.json",
              "bancos/capacidades_v1/simulacion.json", "ejemplos/tarea_v2f_codigo.json", "ejemplos/tarea_v2f_debate.json",
              "herramientas/manifiesto_v2e7r3.txt", "LEEME_V2F.md", "CAMBIOS_V2F.md",
              # V2-F.1
              "src/eq2/funcion_supervisada.py", "src/eq2/interfaces_codex.py", "src/eq2/demo_funcion.py",
              "ejemplos/tarea_funcion_demo.json", "ejemplos/tarea_funcion_falta_info.json",
              "herramientas/manifiesto_v2f.txt", "LEEME_V2F1.md", "CAMBIOS_V2F1.md", "INTERFACES_CODEX.md")
MANIFIESTO = "MANIFIESTO_SHA256.txt"
SEMILLAS_FIJAS = (11, 42, 2026)                             # = pruebas_variables.SEMILLAS_FIJAS
REPETIBLES = (("V-REP-01", "test_v2e5r3_stop", "STOP determinista (todas las variantes)", 1),
              ("V-REP-02", "test_v2e.TestMotorServidorFalso.test_stop_durante_la_tarea",
               "STOP heredado dependiente del reloj (el intermitente de V2-E.4)", 3),
              ("V-REP-03", "test_v2_servidor", "arranque y cierre del servidor falso", 1),
              ("V-REP-04", "test_v2e6_calidad.TestStopContinuacionYLimpieza",
               "STOP durante la continuación y la limpieza (V2-E.6)", 1))
# Demostraciones por función: (nombre, argv relativo a la raíz, descripción). Todas SIMULADAS y en un TMPDIR aislado.
DEMOS = (
    ("aprendizaje_pre_post", ["aprender.py", "evaluar", "--repeticiones", "2"],
     "aprendizaje: tarea inicial, feedback por prueba estática, variante inédita y agente sin memoria"),
    ("auditoria_memoria", ["aprender.py", "auditar"], "auditoría de las bases de aprendizaje (integridad y reglas)"),
    ("reto_referencias", ["retos.py", "referencias"], "puntuador Zomboid con respuestas de referencia buena/mala"),
    ("reto_tuberia", ["retos.py", "tuberia", "--caso", "viewpoint"], "A2 -> A1 -> A3 sobre los laboratorios"),
    ("reto_simulado", ["ejecutar_v2.py", "--modo", "reto_simulado", "--semilla", "{semilla}"],
     "reto completo con backend simulado (3 casos)"),
    ("pruebas_variables", ["retos.py", "variables", "--solo-semillas", "--semilla", "{semilla}", "--repeticiones", "2",
                           "--n", "3"], "pruebas variables con la semilla elegida"),
    ("laboratorio_incidencias", ["auditar.py", "demo-laboratorio"], "experimentos del laboratorio (estático/simulado)"),
    ("ciclo_simulado", ["ejecutar_v2.py", "--modo", "ciclo_simulado"], "ciclo plan -> generar -> revisar -> corregir"),
    ("tarea_simulada", ["ejecutar_v2.py", "--modo", "tarea_simulada"], "motor autónomo con agentes simulados"),
    ("banco_lista", ["banco.py", "lista"], "V2-F: tareas del banco comparativo (sin ejecutar nada)"),
    ("funcion_corregible", ["equipo.py", "demo", "funcion", "--escenario", "corregible"],
     "V2-F.1: A1 escribe, A2 revisa, A3 propone casos, se corrige y se acepta SIN ejecutar (guion)"),
    ("funcion_falta_informacion", ["equipo.py", "demo", "funcion", "--escenario", "falta_informacion"],
     "V2-F.1: falta un dato: A1 pregunta y la tarea se detiene sin programar (guion)"),
    ("funcion_sin_progreso", ["equipo.py", "demo", "funcion", "--escenario", "sin_progreso"],
     "V2-F.1: código idéntico tras la revisión: sin progreso y escalada al usuario (guion)"),
)


# ============================ utilidades ======================================================
def sha256_archivo(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def archivos_del_paquete(raiz: Path) -> list:
    out = []
    for p in sorted(raiz.rglob("*")):
        rel = p.relative_to(raiz).as_posix()
        if p.is_file() and not p.is_symlink() and "__pycache__" not in p.parts and rel != MANIFIESTO:
            out.append(rel)
    return out


def generar_manifiesto(raiz: Path) -> str:
    """Huellas de TODOS los archivos, incluidas las evidencias de fábrica (evidencias_claude/): en r3 quedaron
    fuera del manifiesto y el verificador del usuario las vio como «no declaradas» (falso fallo de integridad)."""
    return "".join(f"{sha256_archivo(raiz / r)}  {r}\n" for r in archivos_del_paquete(raiz))


def leer_manifiesto(m: Path) -> dict:
    out = {}
    for linea in m.read_text(encoding="utf-8").splitlines():
        h, _, ruta = linea.partition("  ")
        if ruta:
            out[ruta] = h
    return out


def mem_disponible_kb():
    try:
        for l in Path("/proc/meminfo").read_text().splitlines():
            if l.startswith("MemAvailable:"):
                return int(l.split()[1])
    except (OSError, ValueError, IndexError):
        pass
    return None


def cpu_ahora():
    if resource is None:
        return None
    s, h = resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN)
    return {"propio": s.ru_utime + s.ru_stime, "hijos": h.ru_utime + h.ru_stime, "maxrss_hijos_kB": h.ru_maxrss}


class Verificador:
    def __init__(self, args, salida=print, raiz=RAIZ):
        self.args, self._print, self.raiz = args, salida, raiz
        self.resultados, self.catalogo, self.fases = [], [], []
        self.lab = None
        self.trabajo = None
        self.pycache_antes = None
        self._pendiente_log = []

    # ---------------------------------------------------------------- salida persistente
    def out(self, texto=""):
        self._print(texto)
        linea = str(texto) + "\n"
        if self.lab is None or not getattr(self, "id_ejec", None):
            self._pendiente_log.append(linea)
            return
        try:
            if self._pendiente_log:
                self.lab.anexar((self.id_ejec, "terminal.log"), "".join(self._pendiente_log))
                self._pendiente_log = []
            self.lab.anexar((self.id_ejec, "terminal.log"), linea)
        except (OSError, ValueError):
            pass

    def evento(self, **d):
        if self.lab is None:
            return
        d = dict(ts=datetime.now().astimezone().isoformat(timespec="milliseconds"), t_monotonico=round(time.monotonic(), 3), **d)
        try:
            self.lab.anexar((self.id_ejec, "eventos.jsonl"), json.dumps(d, ensure_ascii=False, default=str) + "\n")
        except (OSError, ValueError):
            pass

    # ---------------------------------------------------------------- preparación
    def preparar(self):
        if sys.version_info < (3, 11):
            raise RuntimeError("se necesita Python 3.11 o superior")
        raiz_lab = rutas.raiz_laboratorio()                       # exige TMPDIR absoluto
        self.lab = rutas.Laboratorio(raiz_lab, raiz_lab / config.CARPETA_ACTUAL / "verificacion")   # V2-E.6
        self.lab.crear_base()
        self.id_ejec = datetime.now().strftime("%Y%m%d_%H%M%S_%f") + f"_{os.getpid()}"
        self.lab.crear_dir(self.id_ejec)
        self.lab.crear_dir(self.id_ejec, "trazas")
        self.lab.crear_dir(self.id_ejec, "demos")
        self.lab.crear_dir(self.id_ejec, "trabajo")
        self.trabajo = self.lab.ruta(self.id_ejec, "trabajo")
        for d in ("home", "tmp", "demos_tmp", "variables_tmp", "funcion_tmp"):        # V2-F.1: funcion_tmp
            self.lab.crear_dir(self.id_ejec, "trabajo", d)
        self.env = dict(os.environ, HOME=str(self.trabajo / "home"), TMPDIR=str(self.trabajo / "tmp"),
                        PYTHONDONTWRITEBYTECODE="1", PYTHONHASHSEED="0")
        self.env.pop("EQ2_SIMULAR_SIN_LINK", None)
        if self.args.sin_link:                            # solo en la sandbox de desarrollo
            self.env["EQ2_SIMULAR_SIN_LINK"] = "1"
        self.pycache_antes = self._pycache()
        self.catalogo = self.construir_catalogo()

    def _pycache(self):
        return sorted(p.relative_to(self.raiz).as_posix() for p in self.raiz.rglob("__pycache__"))

    def descubrir_pruebas(self) -> list:
        codigo = ("import sys, json, unittest\nsys.path.insert(0, '.')\nids = []\n"
                  "def rec(s):\n    for t in s:\n        rec(t) if isinstance(t, unittest.TestSuite) else ids.append(t.id())\n"
                  "rec(unittest.defaultTestLoader.discover('.', pattern='test_*.py'))\nprint(json.dumps(ids))")
        r = subprocess.run([sys.executable, "-B", "-c", codigo], cwd=self.raiz / "tests", capture_output=True,
                           text=True, timeout=300, env=self.env)
        if r.returncode != 0:
            raise RuntimeError("no se pudieron descubrir las pruebas: " + r.stderr[-500:])
        return json.loads(r.stdout.strip().splitlines()[-1])

    def semillas(self):
        extra = getattr(self.args, "semilla", None)
        return SEMILLAS_FIJAS + ((extra,) if extra is not None and extra not in SEMILLAS_FIJAS else ())

    # ---------------------------------------------------------------- catálogo
    def construir_catalogo(self) -> list:
        cat = []

        def add(area, n, desc, fn, tipo="SIMULADA", fase=None, **kw):
            cat.append({"id": f"V-{AREAS[area][0]}-{n:02d}", "area": area, "fase": fase or area, "descripcion": desc,
                        "fn": fn, "tipo": tipo, **kw})
        add(1, 1, "huellas SHA-256 del manifiesto de la versión (incluye evidencias_claude/)", self.c_manifiesto, "REAL")
        add(1, 2, "sin __pycache__, .pyc, enlaces simbólicos ni sitecustomize en el paquete", self.c_limpieza, "REAL")
        add(1, 3, "estructura mínima del proyecto", self.c_estructura, "REAL")
        add(2, 1, "validador estático (imports, SQL literal, escrituras, red, ejecución)", self.c_validador, "REAL")
        add(2, 2, "todos los .py compilan (en memoria, sin escribir .pyc)", self.c_compilar, "REAL")
        add(2, 3, "protecciones de configuración (Modo B, personalidad, adaptación)", self.c_protecciones, "REAL")
        add(15, 1, "perfiles de contexto: presupuestos dentro del tope, reservas y retroceso por RAM", self.c_perfiles, "SIMULADA")
        self.ids_pruebas = self.descubrir_pruebas()
        grupos = {}
        for t in self.ids_pruebas:
            partes = t.split(".")
            clave = tuple(partes[:2]) if len(partes) >= 3 else (partes[0], "")
            grupos.setdefault(clave, []).append(t)
        contador = {}
        for (mod, clase), ids in sorted(grupos.items()):
            area = MAPA_CLASES.get((mod, clase), MAPA_MODULOS.get(mod, 3))
            if mod.startswith("unittest"):
                area = 1
            contador[area] = contador.get(area, 10) + 1
            nombre = f"{mod}.{clase}" if clase else mod
            add(area, contador[area], f"{nombre} ({len(ids)} pruebas)", self.c_unittest, "SIMULADA", objetivo=nombre,
                n_pruebas=len(ids))
        add(1, 4, "cobertura: cada prueba descubierta pertenece a exactamente un grupo del catálogo", self.c_cobertura,
            "REAL", grupos=grupos)
        rep = 1 if self.args.rapido else self.args.repeticiones
        for ident, objetivo, desc, factor in REPETIBLES:
            cat.append({"id": ident, "area": 13, "fase": 13, "descripcion": f"{desc} × {rep * factor}", "fn": self.c_repetir,
                        "tipo": "SIMULADA", "objetivo": objetivo, "veces": rep * factor, "omitir": self.args.rapido})
        add(12, 1, "paquete de auditoría de ejemplo (declarativo, incluido en la versión)", self.c_paquete_ejemplo)
        add(12, 2, "paquetes externos AUTORIZADOS en $TMPDIR/equipo_f2/lab_v2f1/auditoria/entrada", self.c_paquetes_externos)
        add(12, 3, "paquete de DESAFÍO de ejemplo (eq2/desafio, Zomboid)", self.c_paquete_desafio)
        add(16, 1, "evaluación pre/post del aprendizaje y auditoría de memoria (CLI, carpeta aislada)", self.c_aprendizaje)
        add(17, 1, "batería de pruebas variables: semillas fijas " + ", ".join(map(str, self.semillas())) +
            ", niveles 1-3, determinismo", self.c_variables)
        add(18, 1, "material Zomboid ÍNTEGRO (MANIFIESTO.json del usuario) y generar_reto.py sin ejecutar",
            self.c_material_zomboid, "REAL")
        add(23, 1, "V2-F: banco SIMULADO completo (4 modos × 8 tareas, semilla " + str(self.semillas()[0]) +
            "), ejecutado DOS veces: informe, modos, sin errores y mismas decisiones", self.c_banco_simulado)
        add(24, 1, "V2-F.1: función supervisada SIMULADA (guion) dos veces por la CLI: mismas decisiones, nada "
            "ejecutado, informe y manifiesto íntegros", self.c_funcion_simulada)
        for i, (nombre, argv, desc) in enumerate(DEMOS, 1):
            add(19, i, f"demo «{nombre}»: {desc}", self.c_demo, demo=nombre, argv=argv)
        add(20, 1, "tabla de cumplimiento: archivos y pruebas referenciados existen", self.c_cumplimiento_estatico, "REAL")
        add(20, 2, "diferencias frente a V2-E.5-r3, V2-E.6, V2-E.6-r2, V2-E.6-r3, V2-E.7, V2-E.7-r2, V2-E.7-r3 y V2-F documentadas (CAMBIOS_V2E6*.md, CAMBIOS_V2E7*.md, CAMBIOS_V2F.md, CAMBIOS_V2F1.md)",
            self.c_diff_r3, "REAL")
        add(20, 3, "resultado por requisito (requisito -> archivo -> prueba -> resultado)", self.c_cumplimiento_resultado,
            "REAL")
        add(7, 1, "sin procesos del servidor falso vivos tras las pruebas", self.c_procesos, "REAL", fase=21)
        add(7, 2, "sin carpetas temporales de prueba sin limpiar", self.c_temporales, "REAL", fase=21)
        add(1, 5, "las pruebas no crearon __pycache__ en el paquete", self.c_pycache_final, "REAL", fase=21)
        add(14, 1, "comprobaciones previas con el binario real (--modo comprobar)", self.c_qwen, "REAL", modo="comprobar")
        add(14, 2, "UNA llamada real a Qwen (--modo una_llamada)", self.c_qwen, "REAL", modo="una_llamada")
        add(14, 3, "reto Zomboid con Qwen real (1 caso, 3 llamadas; --modo reto)", self.c_qwen, "REAL", modo="reto")
        add(14, 4, "V2-F: banco con Qwen real (tarea mediana; individual frente a equipo_debate)", self.c_qwen_banco,
            "REAL")
        add(14, 5, "V2-F.1: función supervisada con Qwen real (ejemplos/tarea_funcion_demo.json; el código NO se "
            "ejecuta)", self.c_qwen_funcion, "REAL")
        if self.args.solo:
            cat = [c for c in cat if any(c["id"].startswith(s) for s in self.args.solo)]
        if self.args.fallo_controlado:                      # siempre, aunque se filtre con --solo
            cat.append({"id": "V-AUTO-01", "area": 12, "fase": 12, "descripcion": "FALLO CONTROLADO: debe aparecer como FALLO",
                        "fn": self.c_fallo_controlado, "tipo": "REAL"})
        cat.sort(key=lambda c: ORDEN_FASES.index(c["fase"]))             # orden estable dentro de cada fase
        return cat

    # ---------------------------------------------------------------- ejecución
    def ejecutar(self) -> int:
        self.out(INICIO)
        self.evento(tipo="inicio_verificacion", id=self.id_ejec, semillas=list(self.semillas()))
        t0 = time.monotonic()
        fases = [f for f in ORDEN_FASES if any(c["fase"] == f for c in self.catalogo)]
        for nf, fase in enumerate(fases, 1):
            checks = [c for c in self.catalogo if c["fase"] == fase]
            cab = f"FASE {nf}/{len(fases)} · {AREAS[fase][0]} — {AREAS[fase][1]}"
            self.out(f"===== INICIO {cab} ({len(checks)} comprobaciones) =====")
            self.evento(tipo="inicio_fase", fase=AREAS[fase][0])
            tf = time.monotonic()
            for c in checks:
                self._una(c)
            res_f = [r for r in self.resultados if r["fase"] == AREAS[fase][0]]
            cuenta = {e: sum(r["estado"] == e for r in res_f) for e in ESTADOS}
            dur = round(time.monotonic() - tf, 2)
            self.fases.append({"fase": AREAS[fase][0], "nombre": AREAS[fase][1], "duracion_s": dur, **cuenta})
            self.out(f"===== FIN {cab} · " + ", ".join(f"{v} {k}" for k, v in cuenta.items() if v) + f" · {dur:.2f} s =====")
            self.evento(tipo="fin_fase", fase=AREAS[fase][0], duracion_s=dur, **cuenta)
        self.duracion = round(time.monotonic() - t0, 2)
        self.out(FIN)
        return self.resumir()

    def _una(self, c):
        self.out(f"[{c['id']}] {c['descripcion']} ...")
        m0, cpu0, ti = mem_disponible_kb(), cpu_ahora(), time.monotonic()
        self.evento(tipo="inicio", id=c["id"], fase=AREAS[c["fase"]][0], mem_disponible_kB=m0)
        try:
            if c.get("omitir"):
                estado, detalle = "OMITIDA", "se pidió --rapido"
            else:
                estado, detalle = c["fn"](c)
        except Exception as e:                       # un fallo del verificador también es un FALLO
            import traceback
            estado, detalle = "FALLO", f"error del verificador: {type(e).__name__}: {e}"
            self._traza(c["id"], traceback.format_exc())
        dur = round(time.monotonic() - ti, 2)
        m1, cpu1 = mem_disponible_kb(), cpu_ahora()
        met = {"medido": cpu0 is not None and m0 is not None,
               "cpu_propio_s": round(cpu1["propio"] - cpu0["propio"], 3) if cpu0 else None,
               "cpu_hijos_s": round(cpu1["hijos"] - cpu0["hijos"], 3) if cpu0 else None,
               "maxrss_hijos_kB_acumulado": cpu1["maxrss_hijos_kB"] if cpu1 else None,
               "mem_disponible_kB": {"antes": m0, "despues": m1}}
        naturaleza = {"OMITIDA": "OMITIDA", "NO_VERIFICADA": "NO VERIFICADA", "NO_DISPONIBLE": "NO VERIFICADA"}.get(
            estado, c["tipo"])
        r = {"id": c["id"], "area": c["area"], "area_nombre": AREAS[c["area"]][1], "fase": AREAS[c["fase"]][0],
             "descripcion": c["descripcion"], "estado": estado, "naturaleza": naturaleza, "duracion_s": dur,
             "detalle": detalle, "metricas": met, "objetivo": c.get("objetivo"),
             "real": c["area"] == 14 and estado in ("OK", "FALLO")}
        if estado == "FALLO" and (self.lab.ruta(self.id_ejec, "trazas", c["id"] + ".txt")).exists():
            r["traza"] = str(self.lab.ruta(self.id_ejec, "trazas", c["id"] + ".txt"))
        self.resultados.append(r)
        self.evento(tipo="fin", id=c["id"], estado=estado, naturaleza=naturaleza, duracion_s=dur, metricas=met)
        self.out(f"[{c['id']}] {estado} ({dur:.2f} s) [{naturaleza}] — {detalle}")

    def _traza(self, ident, texto):
        try:
            self.lab.crear_exclusivo((self.id_ejec, "trazas", ident + ".txt"), texto[-200_000:])
        except (OSError, ValueError, FileExistsError):
            pass

    def _python(self, argv, timeout, cwd=None, env=None):
        return subprocess.run([sys.executable, "-B", "-W", "error::ResourceWarning", "-X", "dev", *argv],
                              cwd=cwd or self.raiz / "tests", capture_output=True, text=True, timeout=timeout,
                              env=env or self.env)

    # ---------------------------------------------------------------- comprobaciones
    def c_manifiesto(self, c):
        m = self.raiz / MANIFIESTO
        if not m.is_file():
            return "NO_VERIFICADA", f"no hay {MANIFIESTO} (árbol de desarrollo, no un paquete entregado)"
        esperado = leer_manifiesto(m)
        reales = set(archivos_del_paquete(self.raiz))
        mal = [r for r, h in esperado.items() if r not in reales or sha256_archivo(self.raiz / r) != h]
        extra = sorted(reales - set(esperado))
        if mal or extra:
            self._traza(c["id"], "distintos o ausentes:\n" + "\n".join(mal) + "\nno declarados:\n" + "\n".join(extra))
            return "FALLO", f"{len(mal)} archivos distintos o ausentes, {len(extra)} no declarados"
        ev = sum(1 for r in esperado if r.startswith("evidencias_claude/"))
        return "OK", f"{len(esperado)} archivos coinciden ({ev} de evidencias_claude/)"

    def c_limpieza(self, c):
        malos = []
        for p in self.raiz.rglob("*"):
            rel = p.relative_to(self.raiz).as_posix()
            if p.is_symlink() or p.suffix == ".pyc" or p.name in ("sitecustomize.py", "usercustomize.py"):
                malos.append(rel)
        if self.pycache_antes:
            malos += self.pycache_antes
        if malos:
            return "FALLO", "presentes: " + ", ".join(sorted(malos)[:10])
        return "OK", "limpio"

    def c_estructura(self, c):
        faltan = [f for f in ESTRUCTURA if not (self.raiz / f).is_file()]
        return ("FALLO", "faltan: " + ", ".join(faltan)) if faltan else ("OK", f"{len(ESTRUCTURA)} archivos presentes")

    def c_validador(self, c):
        r = self._python(["-I", str(self.raiz / "validar_estatico.py")], 300, cwd=self.raiz)
        if r.returncode != 0:
            self._traza(c["id"], r.stdout + r.stderr)
            return "FALLO", (r.stdout.strip().splitlines() or ["sin salida"])[-1]
        return "OK", r.stdout.strip().splitlines()[-1]

    def c_compilar(self, c):
        errores = []
        for f in sorted(self.raiz.rglob("*.py")):
            try:
                compile(f.read_text(encoding="utf-8"), str(f), "exec")
            except (SyntaxError, UnicodeDecodeError) as e:
                errores.append(f"{f.relative_to(self.raiz)}: {e}")
        if errores:
            self._traza(c["id"], "\n".join(errores))
            return "FALLO", f"{len(errores)} archivos no compilan"
        return "OK", "todos compilan (compilar NO ejecuta: generar_reto.py solo se analiza sintácticamente)"

    def c_protecciones(self, c):
        mal = [n for n, v in (("MODO_B_HABILITADO", config.MODO_B_HABILITADO),
                              ("PERSONALIDAD_ELECCION_HABILITADA", config.PERSONALIDAD_ELECCION_HABILITADA),
                              ("PERSONALIDAD_ADAPTACION_AUTOMATICA", config.PERSONALIDAD_ADAPTACION_AUTOMATICA)) if v]
        if (config.HILOS, config.NP) != (4, 1):                        # V2-E.6: 4 hilos y NP=1 por defecto
            mal.append(f"HILOS/NP = {config.HILOS}/{config.NP} (se esperaba 4/1)")
        return (("FALLO", "activadas o cambiadas: " + ", ".join(mal)) if mal else
                ("OK", "Modo B y personalidad desactivados; 4 hilos y NP=1"))

    def c_perfiles(self, c):
        from eq2 import perfiles_contexto as P
        mal = []
        for n in P.ORDEN:
            p = P.PERFILES[n]
            for v in list(p["max_tokens"].values()) + list(p["motor"].values()) + [p["aclaracion"], p["continuacion"]]:
                if v > config.TOPE_MAX_TOKENS:
                    mal.append(f"{n}: {v} > tope")
            for fase, r in P.presupuesto_detallado(n).items():
                if r["historial_y_tarea"] <= 200:
                    mal.append(f"{n}/{fase}: sin sitio para el historial")
        sel = P.seleccionar("experimental", mem_kb=None)
        if sel["efectivo"] != "referencia":
            mal.append("sin RAM medible no retrocede a referencia")
        det = f"{len(P.ORDEN)} perfiles; sin RAM medible -> {sel['efectivo']} ({'; '.join(sel['motivos'])})"
        return ("FALLO", "; ".join(mal)) if mal else ("OK", det)

    def c_unittest(self, c):
        r = self._python(["-m", "unittest", c["objetivo"]], 1200)
        m = re.search(r"Ran (\d+) tests? in", r.stderr)
        n = int(m.group(1)) if m else 0
        if r.returncode != 0 or n != c["n_pruebas"]:
            self._traza(c["id"], r.stdout + "\n" + r.stderr)
            fallos = re.search(r"FAILED \(([^)]*)\)", r.stderr)
            return "FALLO", f"{n}/{c['n_pruebas']} ejecutadas; " + (fallos.group(1) if fallos else f"rc={r.returncode}")
        omitidas = re.search(r"OK \(skipped=(\d+)\)", r.stderr)
        return "OK", f"{n} pruebas" + (f" ({omitidas.group(1)} omitidas por la plataforma)" if omitidas else "")

    def c_cobertura(self, c):
        vistos = [t for ids in c["grupos"].values() for t in ids]
        if len(vistos) != len(set(vistos)) or set(vistos) != set(self.ids_pruebas):
            return "FALLO", "hay pruebas repetidas o fuera del catálogo"
        rotas = [t for t in self.ids_pruebas if t.startswith("unittest.loader")]
        if rotas:
            return "FALLO", "módulos de prueba que no se pueden importar: " + ", ".join(rotas)[:300]
        sin_mapa = sorted({m for (m, _c) in c["grupos"] if m not in MAPA_MODULOS})
        if sin_mapa:
            return "FALLO", "módulos de prueba sin área asignada en MAPA_MODULOS: " + ", ".join(sin_mapa)
        return "OK", f"{len(self.ids_pruebas)} pruebas en {len(c['grupos'])} grupos"

    def c_repetir(self, c):
        fallos, salidas = 0, []
        for i in range(c["veces"]):
            r = self._python(["-m", "unittest", c["objetivo"]], 1200)
            if r.returncode != 0:
                fallos += 1
                salidas.append(f"--- repetición {i + 1} ---\n{r.stderr[-6000:]}")
        if fallos:
            self._traza(c["id"], "\n".join(salidas))
            return "FALLO", f"{fallos}/{c['veces']} repeticiones fallaron (error intermitente)"
        return "OK", f"{c['veces']}/{c['veces']} correctas (no demuestra ausencia de errores)"

    def _ejecutar_paquete(self, info, origen):
        """Ejecuta las pruebas declarativas de un paquete válido. Devuelve (estado, detalle, filas)."""
        filas = []
        for p in info["manifiesto"]["pruebas"]:
            if p["operacion"] == "repetir_prueba" and PA._disponibilidad(p) == "si":
                prm = p["parametros"]
                if not (self.raiz / "tests" / (prm["prueba"].split(".")[0] + ".py")).is_file():
                    filas.append((p["id"], "FALLO", "la prueba indicada no existe en esta versión"))
                    continue
                n_ok = sum(self._python(["-m", "unittest", prm["prueba"]], int(p.get("segundos_max", 60)) + 60)
                           .returncode == 0 for _ in range(prm.get("repeticiones", 1)))
                filas.append((p["id"], "OK" if n_ok == prm.get("repeticiones", 1) else "FALLO",
                              f"{n_ok}/{prm.get('repeticiones', 1)} correctas"))
                continue
            r = PA.ejecutar_declarativa(p, info["datos"], self.raiz)
            filas.append((p["id"], {"ok": "OK", "fallo": "FALLO"}.get(r["resultado"], "NO_DISPONIBLE"), r["detalle"]))
        for pid, est, det in filas:
            self.out(f"    [{origen}:{pid}] {est} — {str(det)[:200]}")
        fallidas = [f for f in filas if f[1] == "FALLO"]
        nd = sum(f[1] == "NO_DISPONIBLE" for f in filas)
        if fallidas:
            self._traza(f"paquete_{info['manifiesto']['id']}", json.dumps(filas, ensure_ascii=False, indent=1))
        return ("FALLO" if fallidas else "OK",
                f"{len(filas) - len(fallidas) - nd} OK, {len(fallidas)} FALLO, {nd} NO_DISPONIBLE", filas)

    def c_paquete_ejemplo(self, c):
        z = self.raiz / "auditoria_ejemplo" / "auditoria_ejemplo.zip"
        info = PA.inspeccionar(z, VERSION)
        if info["problemas"] or not info["compatible"]:
            return "FALLO", "paquete de ejemplo inválido: " + "; ".join(info["problemas"])[:300]
        estado, detalle, filas = self._ejecutar_paquete(info, "ejemplo")
        if not any(f[1] == "NO_DISPONIBLE" for f in filas):
            return "FALLO", "el ejemplo debe incluir una prueba no disponible (código) y no aparece"
        return estado, detalle

    def c_paquete_desafio(self, c):
        z = self.raiz / "retos" / "zomboid_v1" / "paquete_desafio" / "desafio_zomboid_v1.zip"
        info = PA.inspeccionar(z, VERSION)
        if info["problemas"] or not info["compatible"] or info["manifiesto"].get("formato") != "eq2/desafio":
            return "FALLO", "paquete de desafío inválido: " + "; ".join(info["problemas"])[:300]
        estado, detalle, filas = self._ejecutar_paquete(info, "desafio")
        if not any(f[1] == "NO_DISPONIBLE" for f in filas):
            return "FALLO", "el desafío debe incluir una prueba que pide el modelo y quedar NO_DISPONIBLE"
        return estado, detalle + f" (sha256 {info['sha256'][:12]}…)"

    def _carpeta_auditoria(self):
        raiz_lab = rutas.raiz_laboratorio()
        return rutas.Laboratorio(raiz_lab, raiz_lab / config.CARPETA_ACTUAL / "auditoria")     # V2-E.6

    def autorizados(self):
        lab = self._carpeta_auditoria()
        try:
            texto = lab.leer_texto(("autorizados.json",), 1_000_000)
            return set(json.loads(texto)) if texto else set()
        except (ValueError, OSError):
            return set()

    def c_paquetes_externos(self, c):
        lab = self._carpeta_auditoria()
        entrada = lab.ruta("entrada")
        if not entrada.is_dir():
            return "OMITIDA", f"no hay paquetes ({entrada} no existe)"
        zips = sorted(p for p in entrada.iterdir() if p.suffix == ".zip" and p.is_file() and not p.is_symlink())
        if not zips:
            return "OMITIDA", "no hay paquetes en la carpeta de entrada"
        aut, resumen, fallo, ejecutados = self.autorizados(), [], False, 0
        for z in zips:
            try:
                info = PA.inspeccionar(z, VERSION)
            except PA.PaqueteInvalido as e:
                resumen.append(f"{z.name}: RECHAZADO ({e})")
                self._registrar(z.name, None, "rechazado", str(e))
                continue
            mid = info["manifiesto"].get("id") if isinstance(info["manifiesto"], dict) else "?"
            if info["problemas"]:
                resumen.append(f"{z.name}: RECHAZADO ({'; '.join(info['problemas'])[:200]})")
                self._registrar(z.name, info["sha256"], "rechazado", "; ".join(info["problemas"]))
            elif not info["compatible"]:
                resumen.append(f"{z.name} ({mid}): INCOMPATIBLE con {VERSION}")
                self._registrar(z.name, info["sha256"], "incompatible", "")
            elif info["sha256"] not in aut:
                resumen.append(f"{z.name} ({mid}): NO AUTORIZADO (sha256 {info['sha256'][:12]}…); "
                               f"autorízalo con --autorizar-paquete")
                self._registrar(z.name, info["sha256"], "no_autorizado", "")
            else:
                estado, detalle, _ = self._ejecutar_paquete(info, mid)
                fallo, ejecutados = fallo or estado == "FALLO", ejecutados + 1
                resumen.append(f"{z.name} ({mid}): AUTORIZADO, {detalle}")
                self._registrar(z.name, info["sha256"], "ejecutado", detalle)
        for s in resumen:
            self.out("    " + s)
        if fallo:
            return "FALLO", "algún paquete autorizado tiene pruebas fallidas"
        return ("OK" if ejecutados else "OMITIDA"), f"{len(zips)} paquetes; {ejecutados} ejecutados"

    def _registrar(self, nombre, huella, estado, detalle):
        lab = self._carpeta_auditoria()
        lab.crear_base()
        linea = json.dumps({"ts": datetime.now().astimezone().isoformat(timespec="seconds"), "archivo": nombre,
                            "sha256": huella, "estado": estado, "detalle": str(detalle)[:300],
                            "version": VERSION, "verificacion": self.id_ejec}, ensure_ascii=False)
        try:
            lab.anexar(("registro.jsonl",), linea + "\n")
        except (OSError, ValueError):
            pass

    def _cli(self, argv, tmp, timeout=900):
        env = dict(self.env, TMPDIR=str(tmp))
        return subprocess.run([sys.executable, "-B", "-I", *argv], cwd=self.raiz, capture_output=True, text=True,
                              timeout=timeout, env=env)

    def c_aprendizaje(self, c):
        tmp = self.trabajo / "demos_tmp"
        r1 = self._cli([str(self.raiz / "aprender.py"), "evaluar", "--repeticiones", "3"], tmp)
        r2 = self._cli([str(self.raiz / "aprender.py"), "auditar"], tmp)
        if r1.returncode != 0 or r2.returncode != 0:
            self._traza(c["id"], r1.stdout + r1.stderr + "\n" + r2.stdout + r2.stderr)
            return "FALLO", f"evaluar rc={r1.returncode}, auditar rc={r2.returncode}"
        m = {k: v for k, v in re.findall(r"^\s+(\w+)\s{2,}(.+)$", r1.stdout, re.M)}
        return "OK", (f"pre={m.get('pre')} post={m.get('post')}; variantes inéditas: con memoria "
                      f"{m.get('variantes_con_memoria')}, sin memoria {m.get('variantes_sin_memoria')}; "
                      f"voto_no_verifica={m.get('voto_no_verifica')}; SIMULADO (política determinista, no Qwen)")

    def c_variables(self, c):
        tmp = self.trabajo / "variables_tmp"
        argv = [str(self.raiz / "retos.py"), "variables", "--repeticiones", "1" if self.args.rapido else "2", "--n", "4"]
        for s in self.semillas():
            if s not in SEMILLAS_FIJAS:
                argv += ["--semilla", str(s)]
        r = self._cli(argv, tmp, timeout=1800)
        inf = next((Path(p) for p in re.findall(r"informes: (\S+informe\.json)", r.stdout)), None)
        if inf and inf.is_file():
            try:
                self.lab.crear_exclusivo((self.id_ejec, "pruebas_variables.json"), inf.read_text(encoding="utf-8"))
                self.lab.crear_exclusivo((self.id_ejec, "pruebas_variables.md"),
                                         inf.with_suffix(".md").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass
        if r.returncode != 0:
            self._traza(c["id"], r.stdout[-20000:] + r.stderr[-5000:])
            return "FALLO", f"rc={r.returncode} (ver pruebas_variables.md)"
        filas = len(re.findall(r"^\| \d+ \| \d \|", r.stdout, re.M))
        return "OK", (f"{filas} combinaciones semilla×nivel superadas y deterministas; semillas {list(self.semillas())}; "
                      "la variación entre semillas NO es aprendizaje")

    def c_material_zomboid(self, c):
        from eq2 import retos as R
        m = R.cargar(self.raiz / "retos" / "zomboid_v1")
        if not m["integro"]:
            return "FALLO", "; ".join(m["problemas"])[:300]
        if "generar_reto" in sys.modules:
            return "FALLO", "generar_reto aparece importado"
        return "OK", f"{len(m['huellas'])} archivos del usuario coinciden; generar_reto.py: solo huella, no ejecutado"

    def c_demo(self, c):
        argv = [a.replace("{semilla}", str(getattr(self.args, "semilla", None) or 42)) for a in c["argv"]]
        tmp = self.trabajo / "demos_tmp"
        r = self._cli([str(self.raiz / argv[0]), *argv[1:]], tmp)
        try:
            self.lab.crear_exclusivo((self.id_ejec, "demos", c["demo"] + ".txt"),
                                     f"$ python3 -B {' '.join(argv)}\n(rc={r.returncode})\n\n{r.stdout}\n{r.stderr}")
        except (OSError, ValueError):
            pass
        if r.returncode != 0:
            self._traza(c["id"], r.stdout[-20000:] + r.stderr[-5000:])
            return "FALLO", f"rc={r.returncode}"
        ultima = next((l for l in reversed(r.stdout.strip().splitlines()) if l.strip()), "")
        return "OK", f"rc=0 · salida en demos/{c['demo']}.txt · {ultima[:120]}"

    def _cumplimiento(self):
        return json.loads((self.raiz / "cumplimiento.json").read_text(encoding="utf-8"))

    def c_cumplimiento_estatico(self, c):
        cum, prob = self._cumplimiento(), []
        ids = getattr(self, "ids_pruebas", None) or self.descubrir_pruebas()
        for req in cum["requisitos"]:
            for a in req.get("archivos", []):
                if not (self.raiz / a).exists():
                    prob.append(f"{req['id']}: falta {a}")
            for t in req.get("pruebas", []):
                if not any(i == t or i.startswith(t + ".") for i in ids):
                    prob.append(f"{req['id']}: prueba inexistente {t}")
            if not req.get("pruebas") and not req.get("no_verificable"):
                prob.append(f"{req['id']}: sin pruebas ni justificación")
        if prob:
            self._traza(c["id"], "\n".join(prob))
            return "FALLO", f"{len(prob)} referencias rotas (ver traza)"
        return "OK", f"{len(cum['requisitos'])} requisitos con archivos y pruebas existentes"

    def c_diff_r3(self, c):
        act = {r: sha256_archivo(self.raiz / r) for r in archivos_del_paquete(self.raiz)
               if not r.startswith("evidencias_claude/")}
        dets, malos, todo = [], [], {}
        for base, doc in (("manifiesto_r3.txt", "CAMBIOS_V2E6.md"), ("manifiesto_v2e6.txt", "CAMBIOS_V2E6R2.md"),
                          ("manifiesto_v2e6r2.txt", "CAMBIOS_V2E6R3.md"),
                          ("manifiesto_v2e6r3.txt", "CAMBIOS_V2E7.md"),
                          ("manifiesto_v2e7.txt", "CAMBIOS_V2E7R2.md"),
                          ("manifiesto_v2e7r2.txt", "CAMBIOS_V2E7R3.md"),
                          ("manifiesto_v2e7r3.txt", "CAMBIOS_V2F.md"),
                          ("manifiesto_v2f.txt", "CAMBIOS_V2F1.md")):
            ref = {r: h for r, h in leer_manifiesto(self.raiz / "herramientas" / base).items()
                   if not r.startswith("evidencias_claude/")}
            nuevos = sorted(set(act) - set(ref))
            quitados = sorted(set(ref) - set(act))
            cambiados = sorted(r for r in set(act) & set(ref) if act[r] != ref[r])
            texto = (self.raiz / doc).read_text(encoding="utf-8")
            sin_doc = [r for r in nuevos + quitados + cambiados if f"`{r}`" not in texto]
            todo[base] = {"nuevos": nuevos, "quitados": quitados, "cambiados": cambiados, "sin_documentar": sin_doc,
                          "iguales": len(set(act) & set(ref)) - len(cambiados)}
            dets.append(f"{base[11:-4]}: {len(nuevos)} nuevos, {len(cambiados)} cambiados, {len(quitados)} quitados")
            malos += [f"{doc}: {r}" for r in sin_doc]
        try:
            self.lab.crear_exclusivo((self.id_ejec, "diff_r3.json"), json.dumps(todo, ensure_ascii=False, indent=1))
        except (OSError, ValueError):
            pass
        if malos:
            self._traza(c["id"], "\n".join(malos))
            return "FALLO", "; ".join(dets) + f"; {len(malos)} sin documentar"
        return "OK", "; ".join(dets) + "; todos documentados"

    def c_cumplimiento_resultado(self, c):
        cum, filas, fallo = self._cumplimiento(), [], False
        por_objetivo = {r["objetivo"]: r for r in self.resultados if r.get("objetivo")}
        por_id = {r["id"]: r for r in self.resultados}
        for req in cum["requisitos"]:
            rel = []
            for t in req.get("pruebas", []):
                for obj, r in por_objetivo.items():
                    if t == obj or t.startswith(obj + ".") or obj.startswith(t + "."):
                        rel.append(r)
            rel += [por_id[v] for v in req.get("verificacion", []) if v in por_id]
            estados = {r["estado"] for r in rel}
            if req.get("no_verificable") and not rel:
                res = "NO VERIFICADA"
            elif "FALLO" in estados:
                res, fallo = "FALLO", True
            elif rel and estados <= {"OK"} and not req.get("no_verificable"):
                res = "OK"
            elif rel and estados <= {"OK"}:
                res = "OK PARCIAL"                    # lo comprobable pasó; el resto está en la nota
            elif rel and "OK" in estados:
                res = "OK PARCIAL"
            else:
                res = "NO VERIFICADA"
            filas.append({"id": req["id"], "requisito": req["requisito"], "fuente": req.get("fuente"),
                          "archivos": req.get("archivos", []), "pruebas": req.get("pruebas", []),
                          "comprobaciones": sorted({r["id"] for r in rel}), "resultado": res,
                          "nota": req.get("no_verificable") or req.get("nota", "")})
        md = [f"# Cumplimiento ({VERSION}) — resultado de esta verificación", "", f"Verificación {self.id_ejec}", "",
              "| Req. | Requisito | Archivos | Pruebas | Comprobaciones | Resultado |", "|---|---|---|---|---|---|"]
        md += [f"| {f['id']} | {f['requisito']} | {', '.join(f['archivos'][:3])} | {', '.join(f['pruebas'][:3])} | "
               f"{', '.join(f['comprobaciones'][:4])} | {f['resultado']}{' — ' + f['nota'] if f['nota'] else ''} |"
               for f in filas]
        try:
            self.lab.crear_exclusivo((self.id_ejec, "cumplimiento_resultado.json"),
                                     json.dumps(filas, ensure_ascii=False, indent=1))
            self.lab.crear_exclusivo((self.id_ejec, "cumplimiento_resultado.md"), "\n".join(md) + "\n")
        except (OSError, ValueError):
            pass
        cuenta = {}
        for f in filas:
            cuenta[f["resultado"]] = cuenta.get(f["resultado"], 0) + 1
        det = ", ".join(f"{v} {k}" for k, v in sorted(cuenta.items())) + " (cumplimiento_resultado.md)"
        return ("FALLO" if fallo else "OK"), det

    def c_procesos(self, c):
        try:
            ad = plataforma.adaptador()
            if not isinstance(ad, plataforma.AdaptadorLinux):
                return "NO_VERIFICADA", "esta plataforma no permite listar procesos sin dependencias nuevas"
        except plataforma.NoSoportado:
            return "NO_VERIFICADA", "plataforma no soportada"
        vivos = []
        for d in Path("/proc").iterdir():
            if d.name.isdigit():
                try:
                    cmd = (d / "cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace")
                    if "fake_llama_server.py" in cmd and str(self.trabajo) in (d / "environ").read_bytes().decode(
                            "utf-8", "replace"):
                        vivos.append(d.name)
                except OSError:                                  # proceso ajeno o ya terminado
                    continue
        return ("FALLO", "procesos vivos: " + ", ".join(vivos)) if vivos else ("OK", "ninguno")

    def c_temporales(self, c):
        restos = sorted(p.name for p in (self.trabajo / "tmp").iterdir()) if (self.trabajo / "tmp").is_dir() else []
        return ("FALLO", "quedan: " + ", ".join(restos[:10])) if restos else ("OK", "la carpeta temporal quedó vacía")

    def c_pycache_final(self, c):
        nuevos = sorted(set(self._pycache()) - set(self.pycache_antes or []))
        return ("FALLO", "creados: " + ", ".join(nuevos[:10])) if nuevos else ("OK", "ninguno")

    def c_qwen(self, c):
        if not (self.args.qwen_real and self.args.iniciar_servidor_real):
            return "NO_VERIFICADA", "requiere --qwen-real y --iniciar-servidor-real (autorización explícita)"
        argv = [str(self.raiz / "ejecutar_v2.py"), "--modo", c["modo"]]
        if c["modo"] != "comprobar":
            argv.append("--iniciar-servidor-real")
        if c["modo"] == "reto":
            argv += ["--max-casos", "1", "--semilla", str(getattr(self.args, "semilla", None) or 42)]
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")                # laboratorio REAL del usuario
        r = subprocess.run([sys.executable, "-B", *argv], cwd=self.raiz, capture_output=True, text=True,
                           timeout=1800, env=env)
        self._traza(c["id"], r.stdout + r.stderr)
        return ("OK" if r.returncode == 0 else "FALLO"), f"REAL: rc={r.returncode} (salida completa en trazas/{c['id']}.txt)"

    def c_banco_simulado(self, c):
        """V2-F: el banco simulado se ejecuta dos veces con la misma semilla en un TMPDIR aislado. Comprueba el informe,
        los cuatro modos, que no hay errores del sistema y que las decisiones son idénticas (reproducible)."""
        semilla = str(self.semillas()[0])
        tmp = self.trabajo / "demos_tmp"
        rs, informes = [], []
        for _ in range(2):
            r = self._cli([str(self.raiz / "banco.py"), "simular", "--autorizo-pruebas", "--solo-semillas",
                           "--semilla", semilla], tmp, timeout=1800)
            rs.append(r)
            m = re.search(r"^informe: (.+\.md)$", r.stdout, re.M)
            if r.returncode != 0 or not m:
                self._traza(c["id"], r.stdout[-20000:] + r.stderr[-5000:])
                return "FALLO", f"banco.py rc={r.returncode}"
            informes.append(json.loads(Path(m.group(1)).with_suffix(".json").read_text(encoding="utf-8")))
        a, b = informes
        prob = []
        if set(a["por_modo"]) != {"individual", "individual_autoprueba", "equipo_debate", "equipo_motor"}:
            prob.append(f"modos: {sorted(a['por_modo'])}")
        if any(f["error"] for f in a["filas"]):
            prob.append("errores del sistema: " + "; ".join(f["error"] for f in a["filas"] if f["error"])[:300])
        if a["huella_decisiones"] != b["huella_decisiones"]:
            prob.append("la misma semilla dio decisiones distintas")
        if not a["contexto"].get("simulado") or not any("SIMULADO" in n for n in a["notas"]):
            prob.append("el informe no se declara SIMULADO")
        try:
            self.lab.crear_exclusivo((self.id_ejec, "demos", "banco_simulado.md"),
                                     Path(re.search(r"^informe: (.+\.md)$", rs[0].stdout, re.M).group(1)).read_text(
                                         encoding="utf-8"))
        except (OSError, ValueError):
            pass
        if prob:
            self._traza(c["id"], "\n".join(prob))
            return "FALLO", "; ".join(prob)[:200]
        resumen = ", ".join(f"{m}: {d['correctas']}/{d['ejecuciones']} ({d['llamadas_media']} llam.)"
                            for m, d in a["por_modo"].items())
        return "OK", f"reproducible (huella {a['huella_decisiones'][:12]}); {resumen} — SIMULADO, ver demos/banco_simulado.md"

    def c_qwen_banco(self, c):
        if not (self.args.qwen_real and self.args.iniciar_servidor_real):
            return "NO_VERIFICADA", "requiere --qwen-real y --iniciar-servidor-real (autorización explícita)"
        argv = [str(self.raiz / "banco.py"), "real", "--autorizo-pruebas", "--iniciar-servidor-real", "--tareas",
                "mediana", "--modos", "individual", "equipo_debate"]
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")                # laboratorio REAL del usuario
        r = subprocess.run([sys.executable, "-B", *argv], cwd=self.raiz, capture_output=True, text=True,
                           timeout=7200, env=env)
        self._traza(c["id"], r.stdout + r.stderr)
        return ("OK" if r.returncode == 0 else "FALLO"), f"REAL: rc={r.returncode} (salida completa en trazas/{c['id']}.txt)"

    def c_funcion_simulada(self, c):
        """V2-F.1: el escenario «corregible» dos veces por la CLI en un TMPDIR aislado. Mismas decisiones (huella), el
        resultado esperado, nada ejecutado (ni informe de unittest ni carpeta pruebas/) y manifiesto de la ejecución
        íntegro. SIMULADA: las respuestas de los agentes son de guion."""
        tmp = self.trabajo / "funcion_tmp"
        informes, prob = [], []
        for _ in range(2):
            r = self._cli([str(self.raiz / "equipo.py"), "demo", "funcion", "--escenario", "corregible"], tmp)
            m = re.search(r"Informe: (\S+informe\.md)$", r.stdout, re.M)
            if r.returncode != 0 or not m:
                self._traza(c["id"], r.stdout[-20000:] + r.stderr[-5000:])
                return "FALLO", f"equipo.py demo funcion rc={r.returncode}"
            informes.append(Path(m.group(1)))
        a, b = (json.loads(p.with_suffix(".json").read_text(encoding="utf-8")) for p in informes)
        if a["huella_decisiones"] != b["huella_decisiones"]:
            prob.append("el mismo guion dio decisiones distintas")
        if a["resultado"] != "aceptada_sin_ejecucion" or not a["backend"]["simulado"]:
            prob.append(f"resultado {a['resultado']} / simulado {a['backend']['simulado']}")
        if a["pruebas_pendientes"].get("ejecutado") is not False or a["ejecucion_dinamica"]["estado"] != "bloqueada":
            prob.append("las pruebas pendientes no constan como NO ejecutadas")
        ejec = informes[0].parent.parent
        if list(ejec.rglob("informe_unittest.txt")) or (ejec / "pruebas").exists():
            prob.append("hay rastros de una ejecución de pruebas")
        for l in (ejec / "MANIFIESTO_SHA256.txt").read_text(encoding="utf-8").splitlines():
            h, _, rel = l.partition("  ")
            if sha256_archivo(ejec / rel) != h:
                prob.append(f"manifiesto: {rel} no coincide")
        try:
            self.lab.crear_exclusivo((self.id_ejec, "demos", "funcion_supervisada_informe.md"),
                                     informes[0].read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
        if prob:
            self._traza(c["id"], "\n".join(prob))
            return "FALLO", "; ".join(prob)[:200]
        return "OK", (f"reproducible (huella {a['huella_decisiones'][:12]}); {a['resultado']} en v"
                      f"{a['version_recomendada']['version']}; {a['limites']['pasos']} pasos; pruebas pendientes "
                      f"{a['pruebas_pendientes']['pruebas']} (no ejecutadas) — SIMULADO, ver demos/funcion_supervisada_informe.md")

    def c_qwen_funcion(self, c):
        if not (self.args.qwen_real and self.args.iniciar_servidor_real):
            return "NO_VERIFICADA", "requiere --qwen-real y --iniciar-servidor-real (autorización explícita)"
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")                # laboratorio REAL del usuario
        r1 = subprocess.run([sys.executable, "-B", str(self.raiz / "equipo.py"), "tarea", "importar",
                             str(self.raiz / "ejemplos" / "tarea_funcion_demo.json")], cwd=self.raiz,
                            capture_output=True, text=True, timeout=120, env=env)
        m = re.search(r'"id": "(LAB-[0-9]+)"', r1.stdout)
        if r1.returncode != 0 or not m:
            self._traza(c["id"], r1.stdout + r1.stderr)
            return "FALLO", f"REAL: importar rc={r1.returncode}"
        r = subprocess.run([sys.executable, "-B", str(self.raiz / "equipo.py"), "tarea", "ejecutar", m.group(1)],
                           cwd=self.raiz, capture_output=True, text=True, timeout=4 * 3600, env=env)
        self._traza(c["id"], r1.stdout + r.stdout + r.stderr)
        mi = re.search(r"informe: (\S+informe\.md)$", r.stdout, re.M)
        if not mi:
            return "FALLO", f"REAL: rc={r.returncode}, sin informe (salida en trazas/{c['id']}.txt)"
        inf = json.loads(Path(mi.group(1)).with_suffix(".json").read_text(encoding="utf-8"))
        estado = "OK" if inf["estado_final"] == "completada" and not inf["backend"]["simulado"] else "FALLO"
        return estado, (f"REAL ({inf['backend']['etiqueta']}): {inf['resultado']} ({inf['motivo']}), "
                        f"{inf['limites']['pasos']} pasos; informe {mi.group(1)}")

    def c_fallo_controlado(self, c):
        r = self._python(["-c", "raise AssertionError('fallo introducido a propósito por --fallo-controlado')"], 60)
        self._traza(c["id"], r.stderr)
        return ("FALLO", "fallo controlado detectado correctamente") if r.returncode != 0 else ("OK", "¿?")

    # ---------------------------------------------------------------- resumen e informes
    def resumir(self) -> int:
        cuenta = {e: sum(r["estado"] == e for r in self.resultados) for e in ESTADOS}
        nat = {n: sum(r["naturaleza"] == n for r in self.resultados) for n in ("REAL", "SIMULADA", "OMITIDA", "NO VERIFICADA")}
        parcial = bool(self.args.solo or self.args.rapido)
        general = ("CON FALLOS" if cuenta["FALLO"] else
                   ("VERIFICACIÓN PARCIAL SIN FALLOS (" + ("--solo" if self.args.solo else "--rapido") + ")"
                    if parcial else "VERIFICADA EN ESTA PLATAFORMA") + " (pruebas simuladas" +
                   ("; incluye pruebas REALES" if any(r["real"] for r in self.resultados) else
                    "; Qwen real NO verificado") + ")")
        inf = {"version": VERSION, "id_verificacion": self.id_ejec, "python": sys.version.split()[0],
               "plataforma": platform.platform(), "adaptador": plataforma.adaptador().informe(),
               "sin_link_simulado": bool(self.args.sin_link), "duracion_s": self.duracion,
               "semillas": {"fijas": list(SEMILLAS_FIJAS), "opcional": getattr(self.args, "semilla", None)},
               "modo_demo": bool(getattr(self.args, "demo", False)),
               "resumen": {"total": len(self.resultados), "correctas": cuenta["OK"], "fallidas": cuenta["FALLO"],
                           "omitidas": cuenta["OMITIDA"], "no_verificadas": cuenta["NO_VERIFICADA"],
                           "no_disponibles": cuenta["NO_DISPONIBLE"]},
               "naturaleza": nat, "fases": self.fases, "carpeta": str(self.lab.ruta(self.id_ejec)),
               "estado_general": general, "parcial": parcial, "resultados": self.resultados,
               "nota": ("REAL = comprueba el árbol o la plataforma reales (o el modelo real en la fase QWEN); SIMULADA = "
                        "backends simulados, servidor FALSO o datos sintéticos. Ninguna simulación es una prueba con Qwen.")}
        md = [f"# Verificación {self.id_ejec} — Equipo IA {VERSION}", "", f"Estado general: **{general}**", "",
              f"Naturaleza: {nat} · semillas: {list(SEMILLAS_FIJAS)} + {getattr(self.args, 'semilla', None)}", "",
              "| Fase | OK | FALLO | OMITIDA | NO_VERIFICADA | NO_DISPONIBLE | Duración (s) |", "|---|---|---|---|---|---|---|"]
        md += [f"| {f['fase']} — {f['nombre']} | {f['OK']} | {f['FALLO']} | {f['OMITIDA']} | {f['NO_VERIFICADA']} | "
               f"{f['NO_DISPONIBLE']} | {f['duracion_s']} |" for f in self.fases]
        md += ["", "| ID | Fase | Descripción | Resultado | Naturaleza | Duración (s) | CPU hijos (s) | Detalle |",
               "|---|---|---|---|---|---|---|---|"]
        md += [f"| {r['id']} | {r['fase']} | {r['descripcion']} | {r['estado']} | {r['naturaleza']} | {r['duracion_s']} | "
               f"{r['metricas']['cpu_hijos_s']} | {str(r['detalle']).replace('|', '/')} |" for r in self.resultados]
        rj = rm = None
        try:
            self.lab.crear_exclusivo((self.id_ejec, "informe.json"), json.dumps(inf, ensure_ascii=False, indent=1, default=str))
            self.lab.crear_exclusivo((self.id_ejec, "informe.md"), "\n".join(md) + "\n")
            rj, rm = self.lab.ruta(self.id_ejec, "informe.json"), self.lab.ruta(self.id_ejec, "informe.md")
        except (OSError, ValueError) as e:
            self.out(f"AVISO: no se pudieron escribir los informes: {e}")
        if self.trabajo is not None and self.trabajo.is_dir() and not self.args.conservar_trabajo:
            shutil.rmtree(self.trabajo, ignore_errors=True)               # solo la carpeta de trabajo propia
        r = inf["resumen"]
        self.out("")
        self.out("RESUMEN")
        self.out(f"  Total de pruebas:        {r['total']}")
        self.out(f"  Correctas:               {r['correctas']}")
        self.out(f"  Fallidas:                {r['fallidas']}")
        self.out(f"  Omitidas:                {r['omitidas']}")
        self.out(f"  No verificadas:          {r['no_verificadas']}")
        self.out(f"  No disponibles:          {r['no_disponibles']}")
        self.out(f"  Naturaleza:              REAL {nat['REAL']} · SIMULADA {nat['SIMULADA']} · OMITIDA {nat['OMITIDA']}"
                 f" · NO VERIFICADA {nat['NO VERIFICADA']}")
        self.out(f"  Semillas:                fijas {list(SEMILLAS_FIJAS)}, opcional {getattr(self.args, 'semilla', None)}")
        self.out(f"  Duración total:          {self.duracion} s")
        self.out(f"  Informes:                {rj}  |  {rm}")
        self.out(f"  Registro de terminal:    {self.lab.ruta(self.id_ejec, 'terminal.log')}")
        self.out(f"  Eventos (JSON):          {self.lab.ruta(self.id_ejec, 'eventos.jsonl')}")
        self.out(f"  Trazas de los fallos:    {self.lab.ruta(self.id_ejec, 'trazas')}")
        self.out(f"  ESTADO GENERAL:          {general}")
        return 1 if r["fallidas"] else 0


def comprobar_huellas_sin_importar(raiz: Path):
    """(estado, detalle) del manifiesto usando SOLO la biblioteca estándar."""
    m = raiz / MANIFIESTO
    if not m.is_file():
        return "NO_VERIFICADA", "sin manifiesto"
    esperado = leer_manifiesto(m)
    reales = set(archivos_del_paquete(raiz))
    mal = sorted(r for r, h in esperado.items() if r not in reales or sha256_archivo(raiz / r) != h)
    extra = sorted(reales - set(esperado))
    return ("FALLO" if mal or extra else "OK"), {"distintos_o_ausentes": mal, "no_declarados": extra}


def informe_sin_nucleo(previo, error) -> int:
    """El núcleo no se puede importar: se informa igualmente, con marcas y resumen (solo stdlib)."""
    print("Equipo IA — verificador integral. Preparando el entorno...")
    print(INICIO)
    print(f"[V-INT-01] huellas SHA-256 del manifiesto de la versión ... {previo[0]} — {previo[1]}")
    print(f"[V-INT-00] importar el núcleo eq2 ... FALLO — {type(error).__name__}: {error}")
    print(FIN)
    print("\nRESUMEN\n  Total de pruebas:        2\n  Fallidas:                "
          f"{1 + (previo[0] == 'FALLO')}\n  ESTADO GENERAL:          CON FALLOS (el núcleo no se puede importar; "
          "no se ejecutó ninguna otra prueba)")
    tmp = os.environ.get("TMPDIR")
    if tmp and os.path.isabs(tmp):
        d = Path(tmp) / "equipo_f2" / CARPETA_LAB / "verificacion" / (
            datetime.now().strftime("%Y%m%d_%H%M%S_%f") + f"_{os.getpid()}")
        try:
            d.mkdir(parents=True, exist_ok=False)
            (d / "informe.json").write_text(json.dumps({"estado_general": "CON FALLOS", "huellas": previo,
                                                        "error_importacion": f"{type(error).__name__}: {error}"},
                                                       ensure_ascii=False, indent=1, default=str))
            print("  Informes:               ", d / "informe.json")
        except OSError as e:
            print("  AVISO: no se pudo escribir el informe:", e)
    return 1


def autorizar(ruta) -> int:
    """El USUARIO autoriza un paquete concreto (por su SHA-256). No lo ejecuta."""
    z = Path(ruta)
    try:
        info = PA.inspeccionar(z, VERSION)
    except PA.PaqueteInvalido as e:
        print("RECHAZADO:", e)
        return 1
    if info["problemas"]:
        print("RECHAZADO:", "; ".join(info["problemas"]))
        return 1
    m = info["manifiesto"]
    print(f"Paquete {m['id']} ({m['formato']}) — «{m['titulo']}» de {m['autor']} (origen: {m['origen']})")
    print(f"SHA-256: {info['sha256']}  (comprueba INTEGRIDAD; NO garantiza que el contenido sea seguro)")
    for p in info["pruebas"]:
        print(f"  {p['id']}: {p['operacion']} — {p['objetivo']} [ejecutable: {p['ejecutable']}]")
    raiz_lab = rutas.raiz_laboratorio()
    lab = rutas.Laboratorio(raiz_lab, raiz_lab / config.CARPETA_ACTUAL / "auditoria")          # V2-E.6
    lab.crear_base()
    previos = []
    try:
        texto = lab.leer_texto(("autorizados.json",), 1_000_000)
        previos = json.loads(texto) if texto else []
    except ValueError:
        print("autorizados.json ilegible: no se modifica")
        return 2
    if info["sha256"] not in previos:
        lab.reemplazar_atomico(("autorizados.json",), json.dumps(sorted(previos + [info["sha256"]]), indent=1))
    lab.anexar(("registro.jsonl",), json.dumps({"ts": datetime.now().astimezone().isoformat(timespec="seconds"),
                                                "archivo": z.name, "sha256": info["sha256"], "estado": "autorizado_por_el_usuario",
                                                "id": m["id"], "version": VERSION}, ensure_ascii=False) + "\n")
    print("AUTORIZADO. Copia el ZIP a", lab.ruta("entrada"), "y ejecuta: python3 -B verificar.py --solo V-CON-02")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--rapido", action="store_true")
    ap.add_argument("--repeticiones", type=int, default=3)
    ap.add_argument("--solo", action="append", default=None, metavar="PREFIJO")
    ap.add_argument("--lista", action="store_true")
    ap.add_argument("--lista-demos", action="store_true")
    ap.add_argument("--demo", action="store_true", help="solo la fase de demostraciones")
    ap.add_argument("--semilla", type=int, default=None, help="semilla adicional para las pruebas variables")
    ap.add_argument("--fallo-controlado", action="store_true")
    ap.add_argument("--sin-link", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--conservar-trabajo", action="store_true", help="no borrar la carpeta de trabajo al terminar")
    ap.add_argument("--autorizar-paquete", metavar="RUTA.zip")
    ap.add_argument("--qwen-real", action="store_true")
    ap.add_argument("--iniciar-servidor-real", action="store_true")
    ap.add_argument("--generar-manifiesto", action="store_true", help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    if not 1 <= a.repeticiones <= 50:
        ap.error("--repeticiones entre 1 y 50")
    if a.semilla is not None and not 0 <= a.semilla <= 2 ** 31:
        ap.error("--semilla entre 0 y 2^31")
    if a.generar_manifiesto:                       # uso del desarrollador al empaquetar
        sys.stdout.write(generar_manifiesto(RAIZ))
        return 0
    if a.lista_demos:
        print("Órdenes de demostración por función (todas SIMULADAS; escriben solo en $TMPDIR/equipo_f2/lab_v2f1/):")
        for nombre, argv_d, desc in DEMOS:
            print(f"  {nombre:<24} python3 -B {' '.join(x.replace('{semilla}', str(a.semilla or 42)) for x in argv_d)}")
            print(f"  {'':<24} {desc}")
        return 0
    if a.demo:
        a.solo = (a.solo or []) + ["V-DEMO"]
    previo = comprobar_huellas_sin_importar(RAIZ)
    try:
        cargar_nucleo()
    except Exception as e:                       # p. ej. un archivo del núcleo alterado o dañado
        return informe_sin_nucleo(previo, e)
    if a.autorizar_paquete:
        return autorizar(a.autorizar_paquete)
    v = Verificador(a)
    v.out(f"Equipo IA {VERSION} — verificador integral. Preparando el entorno...")
    try:
        v.preparar()
    except (RuntimeError, rutas.RutaInsegura, OSError, subprocess.TimeoutExpired) as e:
        print("NO SE PUDO PREPARAR:", e)
        return 2
    v.out(f"Carpeta de la verificación: {v.lab.ruta(v.id_ejec)}  |  {len(v.catalogo)} comprobaciones")
    if a.lista:
        fase = None
        for c in v.catalogo:
            if c["fase"] != fase:
                fase = c["fase"]
                print(f"FASE {AREAS[fase][0]} — {AREAS[fase][1]}")
            print(f"  {c['id']:<10} [{c['tipo']}] {c['descripcion']}")
        shutil.rmtree(v.trabajo, ignore_errors=True)
        return 0
    return v.ejecutar()


if __name__ == "__main__":
    sys.exit(main())
