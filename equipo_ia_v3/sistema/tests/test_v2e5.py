"""V2-E.5: fiabilidad de las deliberaciones (críticas fundamentadas o no, contradicciones,
incertidumbre, aclaración acotada), adaptadores de plataforma (fase 1) y extensiones futuras.

Todo es local y SIMULADO: BackendSimulado (no es Qwen), ejecutor simulado, directorios temporales.
La evaluación de críticas es determinista y solo comprueba REFERENCIAS en el texto: no demuestra
que una objeción sea cierta ni que una propuesta funcione.
"""
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

import _comun
from eq2 import (config, criticas, ejecutor, extensiones, inferencia, motor, orquestador, plataforma,
                 servidor, vigilancia)
from eq2.inferencia import ErrorInferencia

RAIZ = _comun.RAIZ
T = config.TAREA_V2B
ENUN = "Escribe ordenar(xs) en Python; no debe modificar la lista de entrada."
CODIGO_MUTA = "```python\ndef ordenar(xs):\n    xs.sort()\n    return xs\n```"
CODIGO_BIEN = "```python\ndef ordenar(xs):\n    return sorted(xs)\n```"
PROP = "Propuesta:\n" + CODIGO_MUTA + "\nPrueba: ordenar([2, 1]) == [1, 2]\nFIN"


# ============================ 1. clasificación de críticas (puro) =============================
class TestClasificacion(unittest.TestCase):
    def c(self, ev, prop=PROP, enun=ENUN):
        return criticas.clasificar("x", ev, prop, enun)

    def test_cada_estado(self):
        casos = [("`xs.sort()`", "fundamentada", "codigo"),
                 ('"no debe modificar la lista"', "fundamentada", "requisito"),
                 ("`for i in range(len(xs))`", "cita_no_encontrada", "cita"),
                 ("línea 40", "linea_inexistente", "linea"),
                 ("línea 2", "no_verificable", "linea"),
                 ("ordenar([]) debe dar []", "no_verificable", "caso"),
                 (None, "sin_evidencia", None), ("", "sin_evidencia", None),
                 ("xs.sort()", "fundamentada", "codigo")]                     # código sin comillas
        for ev, estado, tipo in casos:
            with self.subTest(ev=ev):
                r = self.c(ev)
                self.assertEqual((r["estado"], r["tipo_referencia"]), (estado, tipo), r)

    def test_normalizacion_y_citas_minimas(self):
        self.assertEqual(self.c("`XS.SORT()`")["estado"], "fundamentada")          # mayúsculas
        self.assertEqual(self.c("`def ordenar(xs): xs.sort()`")["estado"], "fundamentada")   # saltos de línea
        self.assertEqual(self.c("`xs`")["estado"], "no_verificable")               # cita demasiado corta
        r = self.c("`xs.sort()` y `inventado()`")
        self.assertEqual((r["estado"], r["citas_encontradas"]), ("fundamentada", ["xs.sort()"]))

    def test_entradas_no_confiables_o_enormes(self):
        for prop in (None, 3, "", "x" * 300_000):
            r = criticas.clasificar("x", "`y = 1`", prop, None)
            self.assertIn(r["estado"], criticas.ESTADOS)
        t0 = time.monotonic()
        revision = ("OBJECION: " + "a" * 5000 + " | EVIDENCIA: `" + "b(" * 90 + "`\n") * 50
        criticas.evaluar_deliberacion({"propuesta": "c" * 100_000, "revision": revision}, {}, "")
        self.assertLess(time.monotonic() - t0, 5.0)                                 # sin retroceso catastrófico

    def test_determinista(self):
        h = {"propuesta": PROP, "revision": "OBJECION: muta | EVIDENCIA: `xs.sort()`\nOBJECION: lenta",
             "replica": "ACEPTADA: uso sorted\n" + CODIGO_BIEN + "\nFIN"}
        a = json.dumps(criticas.evaluar_deliberacion(h, {}, ENUN), sort_keys=True)
        self.assertEqual(a, json.dumps(criticas.evaluar_deliberacion(h, {}, ENUN), sort_keys=True))


class TestEvaluacionDeliberacion(unittest.TestCase):
    V_OK = {ag: {"estado": "valido", "postura": "aprobar"} for ag in config.AGENTES}

    def ev(self, revision, replica, votos=None, prop=PROP):
        return criticas.evaluar_deliberacion({"propuesta": prop, "revision": revision, "replica": replica},
                                             self.V_OK if votos is None else votos, ENUN)

    def test_critica_falsa_se_marca_y_no_cuenta_como_pendiente(self):
        r = self.ev("OBJECION: usa burbuja | EVIDENCIA: `for i in range(len(xs))`",
                    "REBATIDA: no hay bucle\n" + CODIGO_MUTA + "\nFIN")
        self.assertEqual(r["posibles_criticas_falsas"], [1])
        self.assertEqual(r["problemas_no_resueltos"], [])
        self.assertIn("objecion_1:cita_no_encontrada", r["incertidumbre"])
        self.assertTrue(r["consenso_no_es_correccion"])

    def test_aceptada_pero_no_aplicada(self):
        r = self.ev("OBJECION: muta la lista | EVIDENCIA: `xs.sort()`", "ACEPTADA: uso sorted\n" + CODIGO_MUTA + "\nFIN")
        self.assertIn("replica_acepta_pero_no_aplica:objecion_1", r["contradicciones"])
        self.assertEqual(r["problemas_no_resueltos"], ["objecion_1: muta la lista"])
        for ag in config.AGENTES:
            self.assertIn(f"{ag}_aprueba_con_objecion_fundamentada_pendiente", r["contradicciones"])
        self.assertIn("A3_aprueba_sin_resolver_sus_objeciones_fundamentadas", r["contradicciones"])

    def test_resuelta_en_el_texto(self):
        r = self.ev("OBJECION: muta | EVIDENCIA: `xs.sort()`", "ACEPTADA: uso sorted\n" + CODIGO_BIEN + "\nFIN")
        self.assertEqual(r["objeciones"][0]["resolucion"], "resuelta_en_texto")
        self.assertEqual((r["contradicciones"], r["problemas_no_resueltos"]), ([], []))

    def test_rebatida_sin_cambio_queda_como_incertidumbre(self):
        r = self.ev("OBJECION: muta | EVIDENCIA: `xs.sort()`", "REBATIDA: es intencionado\n" + CODIGO_MUTA + "\nFIN",
                    votos={"A1": {"estado": "valido", "postura": "aprobar_con_cambios"}})
        self.assertEqual(r["objeciones"][0]["resolucion"], "rebatida_sin_cambio")
        self.assertIn("objecion_1:rebatida_sin_cambio", r["incertidumbre"])
        self.assertEqual(r["problemas_no_resueltos"], [])

    def test_revision_contradictoria_y_votos_opuestos(self):
        votos = {"A1": {"estado": "valido", "postura": "aprobar"}, "A2": {"estado": "valido", "postura": "rechazar"},
                 "A3": {"estado": "invalido", "postura": None}}
        r = self.ev("SIN OBJECIONES: todo bien\nOBJECION: falla con [] | EVIDENCIA: ordenar([]) debe dar []",
                    "ACEPTADA: ok\n" + CODIGO_BIEN + "\nFIN", votos)
        self.assertIn("revision_sin_objeciones_y_con_objeciones", r["contradicciones"])
        self.assertIn("votos_opuestos_aprobar_y_rechazar", r["contradicciones"])
        self.assertIn("objecion_1:no_verificable", r["incertidumbre"])

    def test_evidencia_insuficiente(self):
        r = self.ev("OBJECION: no me convence\nOBJECION: es mala | EVIDENCIA: x", "FIN")
        self.assertEqual(r["conteo"]["sin_evidencia"], 2)                      # «x» no es evidencia
        self.assertEqual(len(r["incertidumbre"]), 2)
        self.assertEqual(r["contradicciones"], [])

    def test_tope_de_objeciones_analizadas(self):
        rev = "\n".join(f"OBJECION: o{i} | EVIDENCIA: `xs.sort()`" for i in range(criticas.MAX_OBJECIONES + 5))
        r = self.ev(rev, "")
        self.assertEqual(len(r["objeciones"]), criticas.MAX_OBJECIONES)
        self.assertIn("objeciones_no_analizadas:5", r["incertidumbre"])

    def test_fusionar_aclaracion(self):
        rev = ("OBJECION: muta | EVIDENCIA: `xs.sort()`\nOBJECION: no me gusta\nOBJECION: usa burbuja | "
               "EVIDENCIA: `while True`\nFALTA: tamaño máximo")
        acl = ("OBJECION 2: muta la entrada | EVIDENCIA: `xs.sort()`\nRETIRADA: 3\nOBJECION 1: cambio colado\n"
               "OBJECION 7: nueva objeción que no se pidió")
        texto, info = criticas.fusionar_aclaracion(rev, acl, [2, 3])
        self.assertEqual(info, {"retiradas": [3], "aclaradas": [2], "ignoradas": 2})
        objs = criticas.objeciones_de(texto)
        self.assertEqual([o[1] for o in objs], ["muta", "muta la entrada"])
        self.assertIn("FALTA: tamaño máximo", texto)
        self.assertEqual(criticas.fusionar_aclaracion("OBJECION: a\n", "RETIRADA: 1", [1])[0].split(":")[0],
                         "SIN OBJECIONES")

    def test_contradicciones_entre_versiones_del_motor(self):
        v1 = {"version": 1, "texto": "OBJECION: muta | EVIDENCIA: `xs.sort()`", "archivos": CODIGO_MUTA}
        v2 = {"version": 2, "texto": "SIN OBJECIONES: correcto", "archivos": CODIGO_MUTA + "\n# cambio"}
        v2b = {"version": 2, "texto": "SIN OBJECIONES: correcto", "archivos": CODIGO_BIEN}
        self.assertEqual(len(criticas.contradicciones_entre_versiones([v1, v2])), 1)
        self.assertEqual(criticas.contradicciones_entre_versiones([v1, v2b]), [])


# ============================ 2. orquestador: deliberación simulada ===========================
def guion(revision, replica, votos=None, aclaracion=None, fallar_aclaracion=False, propuesta=PROP):
    votos = votos or {}

    def g(n, fase, mensajes, max_tokens):
        sis = mensajes[0]["content"]
        ag = next((a for a in config.AGENTES if f"Eres {a}" in sis), "?")
        if fase == "voto":
            ag = next((a for a in config.AGENTES if f"Eres {a}," in mensajes[-1]["content"]), ag)
            return votos.get(ag, "VOTO: aprobar\nRAZON: correcto")
        if fase == "aclaracion":
            if fallar_aclaracion:
                return ErrorInferencia("caida_simulada")
            return aclaracion or "RETIRADA: 1"
        return {"analisis": "Objetivo: ordenar sin mutar.", "propuesta": propuesta, "revision": revision,
                "replica": replica}.get(fase, "?")
    return g


class LabDelib(unittest.TestCase):
    def setUp(self):
        self.tmp = _comun.carpeta_temporal()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name) / "equipo_f2"
        self.base = self.raiz / "datos_v2e5"

    def correr(self, g, solicitar=False):
        be = inferencia.BackendSimulado(g)
        v = vigilancia.Vigilante(lector_mem=lambda: 1_500_000, lector_bat=lambda: (80, False))
        o = orquestador.Orquestador(self.base, be, v, reloj=_comun.Reloj(), raiz_laboratorio=self.raiz,
                                    solicitar_evidencia=solicitar)
        r = o.run_deliberacion([ENUN])
        return r, r["tareas"][0], be

    def sql(self, q, p=()):
        con = sqlite3.connect(str(self.base / "datos" / "sesion.db"))
        try:
            return con.execute(q, p).fetchall()
        finally:
            con.close()

    def propuesta_archivo(self, r):
        return next((self.base / "runs" / r["run_id"] / "propuestas").glob("*.txt")).read_text()


class TestDeliberacion(LabDelib):
    def test_critica_falsa_queda_registrada_sin_cambiar_el_recuento(self):
        r, t, be = self.correr(guion("OBJECION: usa burbuja | EVIDENCIA: `for i in range(len(xs))`",
                                     "REBATIDA: no hay bucle\n" + CODIGO_BIEN + "\nFIN"))
        self.assertEqual(t["resultado"], "aprobada")
        self.assertEqual(t["criticas"]["posibles_criticas_falsas"], [1])
        self.assertIn("posible_critica_falsa:objecion_1", t["fiabilidad"]["advertencias"])
        self.assertEqual(len(be.llamadas), 7)                                 # sin llamadas extra
        fj = json.loads(self.sql("SELECT fiabilidad_json FROM conclusiones")[0][0])
        self.assertEqual(fj["criticas"]["posibles_criticas_falsas"], [1])    # trazable en la base
        self.assertTrue(fj["consenso_no_es_correccion"])

    def test_consenso_con_objecion_fundamentada_pendiente_reduce_la_fiabilidad(self):
        r, t, _be = self.correr(guion("OBJECION: muta la lista | EVIDENCIA: `xs.sort()`",
                                      "ACEPTADA: uso sorted\n" + CODIGO_MUTA + "\nFIN"))
        self.assertEqual(t["resultado"], "aprobada")                          # el recuento no cambia...
        self.assertEqual(t["fiabilidad"]["nivel"], "reducida")               # ...pero no es fiable
        self.assertIn("critica:replica_acepta_pero_no_aplica:objecion_1", t["fiabilidad"]["motivos"])
        self.assertTrue(t["consenso_no_es_correccion"])
        cab = self.propuesta_archivo(r)
        self.assertIn("CONSENSO: el acuerdo de los agentes NO demuestra", cab)
        self.assertIn("NO_RESUELTO: objecion_1: muta la lista", cab)
        self.assertIn("replica_acepta_pero_no_aplica:objecion_1", cab)

    def test_objecion_resuelta_no_reduce(self):
        _r, t, _be = self.correr(guion("OBJECION: muta | EVIDENCIA: `xs.sort()`",
                                       "ACEPTADA: uso sorted\n" + CODIGO_BIEN + "\nFIN"))
        self.assertEqual((t["fiabilidad"]["nivel"], t["criticas"]["contradicciones"]), ("normal", []))

    def test_votos_opuestos_se_anotan(self):
        _r, t, _be = self.correr(guion("SIN OBJECIONES: probé [2, 1]", CODIGO_BIEN + "\nFIN",
                                       votos={"A2": "VOTO: rechazar\nRAZON: no valida tipos"}))
        self.assertIn("critica:votos_opuestos_aprobar_y_rechazar", t["fiabilidad"]["advertencias"])

    def test_sin_aclaracion_por_defecto(self):
        _r, t, be = self.correr(guion("OBJECION: no me convence", CODIGO_BIEN + "\nFIN"))
        self.assertEqual([c["fase"] for c in be.llamadas].count("aclaracion"), 0)
        self.assertEqual(len(be.llamadas), 7)
        self.assertIsNone(t["criticas"]["aclaracion"])
        self.assertIn("objecion_1:sin_evidencia", t["criticas"]["incertidumbre"])

    def test_aclaracion_retira_la_objecion_sin_evidencia(self):
        r, t, be = self.correr(guion("OBJECION: no me convence\nOBJECION: muta | EVIDENCIA: `xs.sort()`",
                                     "ACEPTADA: uso sorted\n" + CODIGO_BIEN + "\nFIN", aclaracion="RETIRADA: 1"),
                               solicitar=True)
        fases = [c["fase"] for c in be.llamadas]
        self.assertEqual(fases.count("aclaracion"), 1)
        self.assertEqual(fases.index("aclaracion"), fases.index("revision") + 1)
        self.assertEqual(len(be.llamadas), 8)
        a = t["criticas"]["aclaracion"]
        self.assertEqual((a["realizada"], a["pedidas"], a["retiradas"]), (True, [1], [1]))
        replica_prompt = be.llamadas[fases.index("replica")]["mensajes"][-1]["content"]
        self.assertNotIn("no me convence", replica_prompt)                  # la objeción retirada ya no llega
        self.assertIn("OBJECION: muta | EVIDENCIA: `xs.sort()`", replica_prompt)
        self.assertEqual(self.sql("SELECT fase, agente FROM turnos WHERE fase='aclaracion'"), [("aclaracion", "A3")])
        self.assertEqual(t["criticas"]["conteo"]["sin_evidencia"], 0)

    def test_aclaracion_aporta_cita_y_la_objecion_pasa_a_fundamentada(self):
        _r, t, _be = self.correr(guion("OBJECION: muta la entrada", "ACEPTADA: uso sorted\n" + CODIGO_BIEN + "\nFIN",
                                       aclaracion="OBJECION 1: muta la entrada | EVIDENCIA: `xs.sort()`\n"
                                                  "OBJECION 5: otra nueva"),
                                 solicitar=True)
        o = t["criticas"]["objeciones"][0]
        self.assertEqual((o["estado"], o["resolucion"]), ("fundamentada", "resuelta_en_texto"))
        self.assertEqual(t["criticas"]["aclaracion"]["ignoradas"], 1)        # no se cuelan objeciones nuevas

    def test_no_se_pide_aclaracion_si_todo_esta_fundamentado(self):
        _r, t, be = self.correr(guion("OBJECION: muta | EVIDENCIA: `xs.sort()`", CODIGO_BIEN + "\nFIN"), solicitar=True)
        self.assertEqual(len(be.llamadas), 7)
        self.assertEqual(t["criticas"]["aclaracion"], {"pedidas": [], "realizada": False})

    def test_fallo_de_la_aclaracion_no_aborta_la_tarea(self):
        _r, t, be = self.correr(guion("OBJECION: no me convence", CODIGO_BIEN + "\nFIN", fallar_aclaracion=True),
                                solicitar=True)
        self.assertEqual(t["estado"], "completa")
        self.assertIn("aclaracion_no_valida:fallido", t["fiabilidad"]["advertencias"])
        self.assertFalse(t["criticas"]["aclaracion"]["realizada"])
        self.assertIn("objecion_1:sin_evidencia", t["criticas"]["incertidumbre"])  # se conserva la original

    def test_informe_de_la_linea_de_ordenes_muestra_criticas(self):
        import contextlib
        import importlib.util
        import io
        r, _t, _be = self.correr(guion("OBJECION: muta | EVIDENCIA: `xs.sort()`\nOBJECION: burbuja | EVIDENCIA: "
                                       "`while i < n`", "ACEPTADA: uso sorted\n" + CODIGO_MUTA + "\nFIN"))
        spec = importlib.util.spec_from_file_location("ejecutar_v2_e5", str(RAIZ / "ejecutar_v2.py"))
        ej = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ej)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ej.informe_deliberacion(r)
        s = buf.getvalue()
        for frag in ("CRÍTICAS", "posibles críticas falsas (cita o línea inexistente): [2]",
                     "problemas no resueltos: ['objecion_1: muta']", "NO demuestra que la propuesta sea correcta"):
            self.assertIn(frag, s)

    def test_limites_de_la_deliberacion(self):
        """Una sola aclaración por tarea y el tope de llamadas sube exactamente en 1."""
        self.assertEqual(config.LLAMADAS_ACLARACION, 1)
        malos = {"A2": "no sé votar", "A3": "tampoco"}                          # fuerzan reintentos de voto
        _r, t, be = self.correr(guion("OBJECION: a\nOBJECION: b\nOBJECION: c", CODIGO_BIEN + "\nFIN", votos=malos,
                                      aclaracion="RETIRADA: 1"), solicitar=True)
        fases = [c["fase"] for c in be.llamadas]
        self.assertEqual(fases.count("aclaracion"), 1)
        self.assertLessEqual(len(be.llamadas), config.MAX_LLAMADAS_TAREA + config.LLAMADAS_ACLARACION)
        self.assertEqual(t["estado"], "completa")
        r2, _t2, _be2 = self.correr(guion("OBJECION: a", CODIGO_BIEN + "\nFIN"))
        self.assertEqual(r2["config"]["max_llamadas_tarea"], config.MAX_LLAMADAS_TAREA)
        self.assertFalse(r2["config"]["solicitar_evidencia"])

    def test_la_opcion_de_linea_de_ordenes_existe_y_esta_desactivada(self):
        r = subprocess.run([sys.executable, "-B", "-I", str(RAIZ / "ejecutar_v2.py"), "--help"],
                           capture_output=True, text=True, timeout=60)
        self.assertIn("--solicitar-evidencia", r.stdout)
        src = (RAIZ / "ejecutar_v2.py").read_text()
        self.assertIn('ap.add_argument("--solicitar-evidencia", action="store_true"', src)


# ============================ 3. motor: revisiones de A3 (solo registro) ======================
class TestMotorRevisiones(unittest.TestCase):
    def setUp(self):
        self.tmp = _comun.carpeta_temporal()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name) / "equipo_f2"

    def test_criticas_de_A3_por_version_y_contradiccion_entre_versiones(self):
        from test_v2e import ejec_sim, guion_proyecto

        def revisar(kw):
            if ".sort()" in kw["archivos"] and "# v" not in kw["archivos"]:
                return "OBJECION: muta | EVIDENCIA: `xs.sort()`\nOBJECION: usa burbuja | EVIDENCIA: `while i < n`"
            return "SIN OBJECIONES: correcto"

        def g(paso, n, **kw):
            if paso == "corregir":
                return guion_proyecto(arreglar=False)("generar", n).replace("return xs", f"return xs  # v{n}")
            return guion_proyecto(revisar=revisar)(paso, n, **kw)
        inf = motor.Motor(self.raiz / "d", motor.AgentesMotorSimulados(g), ejecutor.EjecutorSimulado(ejec_sim),
                          raiz_laboratorio=self.raiz, presupuesto=motor.Presupuesto(max_iteraciones_correccion=1)
                          ).ejecutar(T)
        cr = inf["criticas_revisiones"]
        self.assertEqual(cr["por_version"][0]["posibles_criticas_falsas"], [2])
        self.assertEqual(cr["por_version"][0]["conteo"]["fundamentada"], 1)
        self.assertTrue(any(c.startswith("v2_omite_objecion_fundamentada_de_v1") for c in
                            cr["contradicciones_entre_versiones"]), cr)

    def test_el_flujo_del_motor_no_cambia(self):
        from test_v2e import ejec_sim, guion_proyecto
        inf = motor.Motor(self.raiz / "d", motor.AgentesMotorSimulados(guion_proyecto()),
                          ejecutor.EjecutorSimulado(ejec_sim), raiz_laboratorio=self.raiz).ejecutar(T)
        self.assertEqual(inf["estado_final"], "criterios_superados_en_simulacion")
        self.assertEqual(inf["criticas_revisiones"]["contradicciones_entre_versiones"], [])


# ============================ 4. adaptadores de plataforma (fase 1) ===========================
class TestAdaptadores(unittest.TestCase):
    def test_seleccion(self):
        with mock.patch.object(plataforma.os, "name", "nt"):
            self.assertIsInstance(plataforma.adaptador({}), plataforma.AdaptadorWindows)
        with mock.patch.object(plataforma.os.path, "isdir", return_value=False):
            self.assertIsInstance(plataforma.adaptador({"PREFIX": "/data/data/com.termux/files/usr"}),
                                  plataforma.AdaptadorTermux)
            if sys.platform.startswith("linux"):
                self.assertIs(type(plataforma.adaptador({})), plataforma.AdaptadorLinux)

    def test_termux_y_linux_dan_lo_mismo_que_el_codigo_anterior(self):
        tmp = _comun.carpeta_temporal()
        self.addCleanup(tmp.cleanup)
        proc = Path(tmp.name)
        (proc / "123").mkdir()
        (proc / "123" / "comm").write_text("llama-server\n")
        (proc / "45").mkdir()
        (proc / "45" / "comm").write_text("python3\n")
        for cls in (plataforma.AdaptadorLinux, plataforma.AdaptadorTermux):
            with self.subTest(cls=cls.__name__):
                a = cls(str(proc))
                self.assertEqual(a.proceso_llama_activo(), servidor.llama_activo(str(proc)))
                for pid in ("123", "45", "999", "abc", ""):
                    self.assertEqual(a.pid_vivo(pid), pid.isdigit() and os.path.exists(f"{proc}/{pid}"))
                self.assertEqual(a.mem_disponible_kb(), vigilancia.leer_mem_available())
                self.assertEqual(a.comando_servidor(), ["llama-server"])
                self.assertEqual(a.raiz_temporal({"TMPDIR": "/x/tmp"}), "/x/tmp")
                self.assertIsNone(a.raiz_temporal({"TMPDIR": "relativa"}))
        self.assertTrue(plataforma.AdaptadorLinux().pid_vivo(os.getpid()) if os.path.isdir("/proc/self") else True)

    def test_windows_es_solo_diseno_y_nunca_inventa_datos(self):
        w = plataforma.AdaptadorWindows()
        for f in (lambda: w.pid_vivo(1), w.mem_disponible_kb, w.bateria, w.proceso_llama_activo,
                  lambda: w.raiz_temporal({"TEMP": "C:\\Temp"})):
            with self.assertRaises(plataforma.NoSoportado):
                f()
        inf = w.informe()
        self.assertEqual((inf["estado"], inf["mem_disponible_kB"], inf["comando_servidor"]),
                         ("solo_diseno", "no_soportado", ["llama-server.exe"]))
        self.assertIn("solo diseño", inf["verificacion"])

    def test_candado_sin_forma_de_comprobar_no_se_da_por_obsoleto(self):
        tmp = _comun.carpeta_temporal()
        self.addCleanup(tmp.cleanup)
        raiz = Path(tmp.name) / "equipo_f2"
        v = vigilancia.Vigilante(lector_mem=lambda: 1_500_000, lector_bat=lambda: (80, False))
        o = orquestador.Orquestador(raiz / "d", inferencia.BackendSimulado(), v, reloj=_comun.Reloj(),
                                    raiz_laboratorio=raiz)
        o.lab.crear_base()
        o.lab.crear_dir_exclusivo("lock")
        o.lab.crear_exclusivo(("lock", "pid"), "999999")
        with mock.patch.object(plataforma, "adaptador", return_value=plataforma.AdaptadorWindows()):
            with self.assertRaises(orquestador.SesionActiva) as cm:
                o.run_deliberacion([ENUN])
        self.assertFalse(cm.exception.obsoleto)
        self.assertIn("no se puede comprobar", str(cm.exception))
        with self.assertRaises(orquestador.SesionActiva) as cm:          # Linux: comportamiento anterior
            o.run_deliberacion([ENUN])
        self.assertEqual(cm.exception.obsoleto, not os.path.exists("/proc/999999"))

    def test_auditoria_de_dependencias(self):
        a = plataforma.auditar_dependencias()
        self.assertEqual(a, plataforma.auditar_dependencias())            # determinista
        self.assertIn("servidor.py", a["servidor"])
        self.assertIn("vigilancia.py", a["recursos"])
        self.assertIn("rutas.py", a["rutas"])
        self.assertIn("orquestador.py", a["senales"])
        self.assertNotIn("plataforma.py", {f for d in a.values() for f in d})
        self.assertNotIn("criticas.py", {f for d in a.values() for f in d})   # el núcleo nuevo es portable

    def test_cli_plataforma_solo_lee(self):
        tmp = _comun.carpeta_temporal()
        self.addCleanup(tmp.cleanup)
        env = dict(os.environ, HOME=str(Path(tmp.name) / "h"), TMPDIR=str(Path(tmp.name) / "t"))
        (Path(tmp.name) / "h").mkdir()
        (Path(tmp.name) / "t").mkdir()
        r = subprocess.run([sys.executable, "-B", "-I", str(RAIZ / "auditar.py"), "plataforma"], capture_output=True,
                           text=True, timeout=60, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('"adaptador"', r.stdout)
        self.assertIn("Windows es diseño", r.stdout)
        self.assertEqual(list((Path(tmp.name) / "t").iterdir()), [])        # no crea el laboratorio
        self.assertEqual(list((Path(tmp.name) / "h").iterdir()), [])


# ============================ 5. extensiones futuras (solo diseño) ===========================
class TestExtensionesFuturas(unittest.TestCase):
    def test_ningun_modulo_visual_se_carga(self):
        # CAMBIO V2-E.5-r2 (V2-E.5 miraba TODO sys.modules y daba un falso positivo si el entorno ya tenía
        # Pillow cargado, p. ej. por un sitecustomize). Ahora: proceso aislado (-I) y solo cuentan los
        # módulos gráficos que aparecen DESPUÉS de una foto de sys.modules tomada antes de importar eq2.
        # Controles positivos y del caso precargado: test_v2e5r2.TestSondeoImportaciones.
        r = subprocess.run([sys.executable, "-B", "-I", str(RAIZ / "tests" / "_sondeo_importaciones.py"),
                            str(RAIZ / "src")], capture_output=True, text=True, timeout=60, cwd=RAIZ)
        self.assertEqual(r.returncode, 0, r.stderr)
        d = json.loads(r.stdout)
        self.assertEqual((d["nuevos"], d["errores"]), ([], []), d)
        self.assertGreater(len(d["modulos_eq2"]), 30)                  # de verdad se importó el núcleo

    def test_la_configuracion_no_admite_avatar_ni_personalidad_ni_permisos(self):
        for d in ({"avatar": True}, {"personalidad": "alegre"}, {"personalidad": {"modo_b": True}}, {"gui": True}):
            with self.subTest(d=d), self.assertRaises(ValueError):
                extensiones.ConfiguracionModular.desde_dict(d)
        for k in ("modo_b", "ejecucion_real", "privilegios"):
            with self.assertRaises(PermissionError):
                extensiones.ConfiguracionModular.desde_dict({k: True})

    def test_documento_de_extensiones(self):
        t = (RAIZ / "EXTENSIONES_FUTURAS.md").read_text()
        for s in ("Plugins de lenguajes", "Migraciones", "ModLab", "AvatarLab", "Personalidades", "Interfaz gráfica",
                  "no se implementa", "nunca modifica los permisos"):
            self.assertIn(s.lower(), t.lower())


class TestVersionV2E5(unittest.TestCase):
    def test_version_y_carpetas(self):
        import eq2
        from eq2 import incidencias, memoria
        self.assertEqual(eq2.VERSION, "f2-v2f1")  # CAMBIO V2-E.6 (V2-E.5-r3: f2-v2e5-r3)  # CAMBIO V2-E.6-r2 (V2-E.6: f2-v2e6-r1)  # CAMBIO V2-E.6-r3 (V2-E.6-r2: f2-v2e6-r2)  # CAMBIO V2-E.7 (V2-E.6-r3: f2-v2e6-r3)  # CAMBIO V2-E.7-r2 (V2-E.7: f2-v2e7-r1)  # CAMBIO V2-E.7-r3 (V2-E.7-r2: f2-v2e7-r2)  # CAMBIO V2-F (V2-E.7-r3: f2-v2e7-r3)  # CAMBIO V2-F.1 (V2-F: f2-v2f)
        self.assertEqual(config.CARPETA_V2E5, "datos_v2e5")
        self.assertIn("datos_v2e4r2", config.CARPETAS_ANTERIORES)
        self.assertEqual((memoria.ESQUEMA_SESION, incidencias.ESQUEMA_INCIDENCIAS), ("6", "4"))
        self.assertFalse(config.MODO_B_HABILITADO)


if __name__ == "__main__":
    unittest.main()
