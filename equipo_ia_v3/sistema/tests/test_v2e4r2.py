"""V2-E.4-r2: ningún camino, manual o automático, eleva una causa a «respaldada por simulación» sin
reproducción y control sobre versiones OBSERVADAS por el motor; los tipos especializados son solo
declaraciones (su código es no confiable y nunca se invoca).

Todo es local y simulado. La garantía cubre los caminos del sistema y el texto de los agentes; no
protege frente a quien edite a mano el archivo SQLite.
"""
import hashlib
import os
import sqlite3
import subprocess
import sys
import unittest
import unittest.mock
from pathlib import Path

import _comun
from eq2 import config, ejecutor, incidencias, investigacion, laboratorio, motor, rutas
from test_v2e2 import ARREGLADO, SIM
from test_v2e4 import guion_ciclo

RAIZ = _comun.RAIZ
Inc = incidencias
FALLA = "def ordenar(xs):\n    xs.sort()\n    return xs\n"
PASA = "def ordenar(xs):\n    return sorted(xs)\n"


def sha(t):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = _comun.carpeta_temporal()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name) / "equipo_f2"
        self.base = self.raiz / "datos_v2e4r2"
        self.lab = rutas.Laboratorio(self.raiz, self.base)
        self.reg = Inc.RegistroIncidencias(self.lab)
        self.addCleanup(lambda: self.reg.cerrar())
        self.lb = laboratorio.Laboratorio(self.reg)
        self.inc = self.reg.crear("ordenar muta", "simulacion", 3, 3, causa="muta la lista")
        for t in Inc.NO_DECLARATIVAS[:2]:                              # hay evidencia estática y simulada
            self.reg.registrar_evidencia(self.inc, t, "fallida", t, "motor")

    def n(self, tabla):
        return self.reg.con.execute(f"SELECT count(*) FROM {tabla}").fetchone()[0]

    def confirmada(self):
        return self.reg.obtener(self.inc)["causa_estado"] == "confirmada"

    def pruebas_canonicas(self, hid, run="r", t_falla=FALLA, t_pasa=PASA):
        e1 = self.lb.planificar_prueba_de_hipotesis(hid, "reproduccion", run, 1, t_falla)
        e2 = self.lb.planificar_prueba_de_hipotesis(hid, "control", run, 2, t_pasa)
        self.assertEqual((self.lb.ejecutar(e1)["conclusion"], self.lb.ejecutar(e2)["conclusion"]), ("apoya", "apoya"))
        return e1, e2


# ============================ 1. confirmar_causa_con (el hallazgo de la auditoría) =============
class TestConfirmarCausaCon(Base):
    def test_una_sola_reproduccion_no_confirma_y_deja_constancia(self):
        e = self.lb.planificar("reproduce", "simulacion", SIM, {"prueba_falla": "test_no_muta"}, incidencia_id=self.inc)
        self.assertEqual(self.lb.ejecutar(e)["conclusion"], "apoya")
        for _ in range(3):
            self.assertFalse(self.lb.confirmar_causa_con(e))
        self.assertFalse(self.confirmada())
        reg = [x for x in self.reg.evidencias(self.inc) if x["tipo"] == "registro"]
        self.assertEqual(len(reg), 1)                                    # anotado una vez, sin duplicar
        self.assertIn("un experimento aislado no basta", reg[0]["descripcion"])
        with self.assertRaises(Inc.PermisoDenegado):
            self.lb.crear_regresion(e)

    def test_reproduccion_canonica_sin_control_no_confirma(self):
        hid, _ = self.reg.proponer_hipotesis(self.inc, "A2", "t", "m.py", ".sort()")
        e1 = self.lb.planificar_prueba_de_hipotesis(hid, "reproduccion", "r", 1, FALLA)
        self.lb.ejecutar(e1)
        self.assertFalse(self.lb.confirmar_causa_con(e1))
        self.assertFalse(self.confirmada())

    def test_con_hipotesis_respaldada_si_confirma(self):
        hid = _comun.respaldar_causa(self.reg, self.inc, "m.py", ".sort()", FALLA, PASA)
        rep = self.reg.con.execute("SELECT id FROM experimentos WHERE hipotesis_id=? AND rol='reproduccion'",
                                   (hid,)).fetchone()[0]
        self.reg.volver_a_hipotesis(self.inc, "usuario", "volver a decidir")
        self.assertTrue(self.lb.confirmar_causa_con(rep))
        i = self.reg.obtener(self.inc)
        self.assertEqual((i["causa_estado"], i["causa_respaldo"], i["causa_hipotesis"]), ("confirmada", "simulacion", hid))


# ============================ 2. confirmar_causa directa: cerrada en la base ==================
class TestConfirmarCausaDirecta(Base):
    def test_ningun_actor_ni_respaldo_confirma_sin_hipotesis_respaldada(self):
        for actor in ("laboratorio", "motor", "usuario"):
            for respaldo in (None, "simulacion", "analisis_estatico", "prueba_real"):
                with self.subTest(actor=actor, respaldo=respaldo), self.assertRaises(sqlite3.IntegrityError):
                    self.reg.confirmar_causa(self.inc, actor, "intento", respaldo=respaldo)
        for ag in Inc.AGENTES:
            with self.assertRaises(Inc.PermisoDenegado):
                self.reg.confirmar_causa(self.inc, ag, "intento")
        self.assertFalse(self.confirmada())
        self.assertFalse([h for h in self.reg.historial(self.inc) if h["despues"] == "confirmada"])   # nada a medias

    def test_hipotesis_no_respaldada_o_de_otra_incidencia_no_sirve(self):
        hid, _ = self.reg.proponer_hipotesis(self.inc, "A2", "t", "m.py", ".sort()")
        for estado in ("propuesta", "consistente"):
            if estado == "consistente":
                self.reg.cambiar_hipotesis(hid, "consistente", "laboratorio", "x")
            with self.subTest(estado=estado), self.assertRaises(sqlite3.IntegrityError):
                self.reg.confirmar_causa(self.inc, "laboratorio", "x", hipotesis_id=hid)
        otra = self.reg.crear("otra", "x", 3, 3)
        hid_otra = _comun.respaldar_causa(self.reg, otra)
        with self.assertRaises(sqlite3.IntegrityError):
            self.reg.confirmar_causa(self.inc, "laboratorio", "x", hipotesis_id=hid_otra)
        with self.assertRaises(sqlite3.IntegrityError):                  # respaldada pero con respaldo estático
            self.reg.confirmar_causa(otra, "laboratorio", "x", respaldo="analisis_estatico", hipotesis_id=hid_otra)
        self.assertFalse(self.confirmada())

    def test_hipotesis_respaldada_solo_da_respaldo_de_simulacion(self):
        hid = _comun.respaldar_causa(self.reg, self.inc)                 # self.inc TIENE evidencia estática
        self.reg.volver_a_hipotesis(self.inc, "usuario", "x")
        with self.assertRaises(sqlite3.IntegrityError):
            self.reg.confirmar_causa(self.inc, "laboratorio", "x", respaldo="analisis_estatico", hipotesis_id=hid)
        self.assertFalse(self.confirmada())
        self.reg.confirmar_causa(self.inc, "laboratorio", "x", hipotesis_id=hid)          # simulación: válido
        self.assertEqual(self.reg.obtener(self.inc)["causa_respaldo"], "simulacion")

    def test_sql_directo_tampoco(self):
        for q in ("UPDATE incidencias SET causa_estado='confirmada' WHERE id=?",
                  "UPDATE incidencias SET causa_estado='confirmada', causa_respaldo='simulacion' WHERE id=?",
                  "UPDATE incidencias SET causa_estado='confirmada', causa_respaldo='simulacion', "
                  "causa_hipotesis='HIP-999999' WHERE id=?"):
            with self.subTest(q=q), self.assertRaises(sqlite3.IntegrityError), self.reg.con:
                self.reg.con.execute(q, (self.inc,))
        with self.assertRaises(sqlite3.IntegrityError), self.reg.con:
            self.reg.con.execute("INSERT INTO incidencias(id,creada,actualizada,titulo,categoria,gravedad,impacto,"
                                 "dificultad,confianza,estado,origen,causa_estado) VALUES('INC-X','t','t','x','c',1,1,1,"
                                 "0.5,'abierta','sql','confirmada')")


# ============================ 3. no se puede fabricar la evidencia ============================
class TestProcedencia(Base):
    def setUp(self):
        super().setUp()
        self.hid, _ = self.reg.proponer_hipotesis(self.inc, "A2", "t", "m.py", ".sort()")

    def respaldar(self):
        self.reg.cambiar_hipotesis(self.hid, "respaldada", "laboratorio", "intento")

    def test_planificar_ya_no_acepta_rol_ni_hipotesis(self):
        for kw in ({"rol": "control"}, {"hipotesis_id": self.hid}):
            with self.subTest(kw=kw), self.assertRaises(TypeError):
                self.lb.planificar("x", "simulacion", SIM, {"prueba_pasa": "test_no_muta"}, incidencia_id=self.inc, **kw)
        with self.assertRaises(ValueError):
            self.lb.planificar_prueba_de_hipotesis(self.hid, "otro_rol", "r", 1, FALLA)

    def test_reproduccion_y_control_sin_observaciones_no_respaldan(self):
        self.pruebas_canonicas(self.hid)
        with self.assertRaises(sqlite3.IntegrityError):
            self.respaldar()

    def test_texto_distinto_del_observado_no_respalda(self):
        self.reg.registrar_observacion("r", 1, self.inc, True, {"m.py": FALLA})
        self.reg.registrar_observacion("r", 2, self.inc, False, {"m.py": PASA})
        self.pruebas_canonicas(self.hid, t_pasa="def ordenar(xs):\n    return list(xs)  # inventado\n")
        with self.assertRaises(sqlite3.IntegrityError):
            self.respaldar()

    def test_presencia_cambiada_u_otra_ejecucion_no_respaldan(self):
        self.reg.registrar_observacion("r", 1, self.inc, True, {"m.py": FALLA})
        self.reg.registrar_observacion("r", 2, self.inc, True, {"m.py": PASA})      # en v2 el fallo SIGUE
        self.reg.registrar_observacion("otra", 2, self.inc, False, {"m.py": PASA})  # ausente, pero en otra ejecución
        self.pruebas_canonicas(self.hid)
        with self.assertRaises(sqlite3.IntegrityError):
            self.respaldar()

    def test_reproduccion_fabricada_no_respalda(self):
        self.reg.registrar_observacion("r", 1, self.inc, True, {"m.py": FALLA})
        self.reg.registrar_observacion("r", 2, self.inc, False, {"m.py": PASA})
        self.pruebas_canonicas(self.hid, t_falla="x.sort()  # texto que el motor nunca observó\n")
        with self.assertRaises(sqlite3.IntegrityError):
            self.respaldar()

    def test_reproduccion_sobre_version_donde_no_fallaba_no_respalda(self):
        self.reg.registrar_observacion("r", 1, self.inc, False, {"m.py": FALLA})   # v1 observada SIN el fallo
        self.reg.registrar_observacion("r", 2, self.inc, False, {"m.py": PASA})
        self.pruebas_canonicas(self.hid)
        with self.assertRaises(sqlite3.IntegrityError):
            self.respaldar()

    def test_con_la_procedencia_correcta_si_respalda(self):
        self.reg.registrar_observacion("r", 1, self.inc, True, {"m.py": FALLA})
        self.reg.registrar_observacion("r", 2, self.inc, False, {"m.py": PASA})
        self.pruebas_canonicas(self.hid)
        self.respaldar()
        self.assertEqual(self.reg.hipotesis(hid=self.hid)[0]["estado"], "respaldada")
        e = self.reg.con.execute("SELECT run_id, version, archivo_sha256 FROM experimentos WHERE rol='control'").fetchone()
        self.assertEqual(tuple(e), ("r", 2, sha(PASA)))

    def test_regla_canonica_construida_desde_la_hipotesis(self):
        e1, _e2 = self.pruebas_canonicas(self.hid)
        x = self.lb.experimento(e1)
        self.assertEqual(x["entradas"]["reglas"], [{"archivo": "m.py", "si_contiene": ".sort()",
                                                    "prueba": "fallo_inc_000001", "resultado": "fallo"}])
        self.assertEqual(x["esperado"], {"prueba_falla": "fallo_inc_000001"})

    def test_observaciones_solo_del_motor_idempotentes_y_de_solo_anexar(self):
        for actor in ("laboratorio", "usuario", "A1", "A2", "A3"):
            with self.assertRaises(Inc.PermisoDenegado):
                self.reg.registrar_observacion("r", 1, self.inc, True, {"m.py": FALLA}, actor=actor)
        self.assertEqual(self.reg.registrar_observacion("r", 1, self.inc, True, {"m.py": FALLA, "t.py": "x"}), 2)
        self.assertEqual(self.reg.registrar_observacion("r", 1, self.inc, False, {"m.py": PASA}), 0)  # no se reescribe
        for q in ("UPDATE observaciones SET presente=0", "DELETE FROM observaciones"):
            with self.subTest(q=q), self.assertRaises(sqlite3.IntegrityError), self.reg.con:
                self.reg.con.execute(q)
        self.assertEqual([o["presente"] for o in self.reg.observaciones(self.inc)], [1, 1])

    def test_experimento_con_rol_exige_procedencia(self):
        with self.assertRaises(sqlite3.IntegrityError), self.reg.con:
            self.reg.con.execute("INSERT INTO experimentos(id,creado,hipotesis,tipo,entradas_json,limites_json,estado,"
                                 "rol,hipotesis_id) VALUES('EXP-X','t','h','simulacion','{}','{}','planificado',"
                                 "'control',?)", (self.hid,))


# ============================ 4. coherencia automática y regresiones ===========================
class TestCoherencia(Base):
    def test_si_la_hipotesis_deja_de_estar_respaldada_la_base_revierte_la_causa(self):
        hid = _comun.respaldar_causa(self.reg, self.inc, "m.py", ".sort()", FALLA, PASA)
        self.assertTrue(self.confirmada())
        self.reg.cambiar_hipotesis(hid, "refutada", "laboratorio", "nueva evidencia en contra")
        i = self.reg.obtener(self.inc)
        self.assertEqual((i["causa_estado"], i["causa_respaldo"], i["causa_hipotesis"]), ("hipotesis", "ninguno", None))
        self.assertTrue(any(h["motivo"] == f"{hid} ya no está respaldada" for h in self.reg.historial(self.inc)))

    def test_control_sin_el_archivo_no_respalda_ni_desactiva_la_investigacion(self):
        inv = investigacion.Investigador(self.reg, "rx")
        hid = inv.proponer_desde_texto(f"HIPOTESIS {self.inc}: ARCHIVO m.py PATRON .sort()", [self.inc])[0]
        inv.observar(1, {"m.py": FALLA}, {self.inc}, {self.inc})
        inv.observar(2, {"otro.py": "x = 1\n"}, set(), {self.inc})      # m.py ya no existe en v2
        inv.investigar([self.inc])
        self.assertEqual(self.reg.hipotesis(hid=hid)[0]["estado"], "consistente")
        self.assertFalse(self.confirmada())
        with __import__("unittest").mock.patch.object(investigacion.Investigador, "_evaluar",
                                                       return_value=("completa", "forzado", "EXP-000001")):
            inv.investigar([self.inc])                                   # aunque se fuerce, la base no lo admite
        self.assertEqual(self.reg.hipotesis(hid=hid)[0]["estado"], "consistente")
        self.assertIn(f"{self.inc}: procedencia insuficiente para respaldar", inv.resumen()["limites_alcanzados"])

    def test_regresion_solo_desde_la_reproduccion_de_la_hipotesis_que_respalda(self):
        hid = _comun.respaldar_causa(self.reg, self.inc, "m.py", ".sort()", FALLA, PASA)
        rep, ctl = (self.reg.con.execute("SELECT id FROM experimentos WHERE hipotesis_id=? AND rol=?", (hid, r)).fetchone()[0]
                    for r in ("reproduccion", "control"))
        libre = self.lb.planificar("libre", "simulacion", SIM, {"prueba_falla": "test_no_muta"}, incidencia_id=self.inc)
        self.lb.ejecutar(libre)
        with self.assertRaises(Inc.PermisoDenegado):
            self.lb.crear_regresion(libre)
        with self.assertRaises(ValueError):
            self.lb.crear_regresion(ctl)
        h2, _ = self.reg.proponer_hipotesis(self.inc, "A2", "otra", "m.py", "xs.sort")
        self.reg.registrar_observacion("r9", 1, self.inc, True, {"m.py": FALLA})
        e_otra = self.lb.planificar_prueba_de_hipotesis(h2, "reproduccion", "r9", 1, FALLA)
        self.lb.ejecutar(e_otra)
        with self.assertRaises(Inc.PermisoDenegado):                   # reproducción de OTRA hipótesis
            self.lb.crear_regresion(e_otra)
        rid = self.lb.crear_regresion(rep)
        self.assertTrue(self.lb.ejecutar_regresion(rid)["reproduce"])
        self.assertTrue(self.lb.ejecutar_regresion(rid, ARREGLADO)["supera"])

    def test_el_ciclo_automatico_registra_procedencia_y_sigue_funcionando(self):
        base = self.raiz / "ciclo"
        reg = Inc.RegistroIncidencias(rutas.Laboratorio(self.raiz, base))   # registro limpio: INC-000001
        self.addCleanup(reg.cerrar)
        inf = motor.Motor(base, motor.AgentesMotorSimulados(guion_ciclo()),
                          ejecutor.EjecutorSimulado(__import__("test_v2e").ejec_sim), raiz_laboratorio=self.raiz,
                          incidencias=reg).ejecutar(config.TAREA_V2B)
        self.assertEqual(inf["estado_final"], "criterios_superados_en_simulacion", inf["errores"])
        i = reg.obtener("INC-000001")
        self.assertEqual((i["causa_estado"], i["causa_respaldo"]), ("confirmada", "simulacion"))
        obs = reg.observaciones("INC-000001")
        self.assertEqual(sorted({(o["version"], o["presente"]) for o in obs}), [(1, 1), (2, 0)])
        self.assertTrue(all(o["run_id"] == inf["run_id"] for o in obs))
        self.assertEqual(reg.con.execute("SELECT count(*) FROM regresiones").fetchone()[0], 1)


# ============================ 5. tipos especializados: solo declaraciones =====================
class TestTiposSoloDeclarativos(Base):
    def test_registrar_no_invoca_nada_y_planificar_lo_rechaza(self):
        def explota(*_a, **_k):
            raise AssertionError("código de terceros invocado")
        laboratorio.registrar_tipo(laboratorio.TipoExperimento("tipo_no_confiable", "simulacion", explota, explota))
        self.addCleanup(laboratorio.retirar_tipo, "tipo_no_confiable")
        with self.assertRaises(laboratorio.TipoNoEjecutable):
            self.lb.planificar("x", "tipo_no_confiable", {"a": 1}, {"sin_errores": True})
        self.assertEqual(self.n("experimentos"), 0)
        doc = laboratorio.TipoExperimento.__doc__ + laboratorio.__doc__
        self.assertIn("NO CONFIABLE", doc)
        self.assertIn("NO es un aislamiento de seguridad", doc)


# ============================ 6. CLI, versión y esquema ======================================
class TestCLIYVersion(unittest.TestCase):
    def setUp(self):
        self.tmp = _comun.carpeta_temporal()
        self.addCleanup(self.tmp.cleanup)
        self.t = Path(self.tmp.name)
        (self.t / "home").mkdir()
        (self.t / "tmp").mkdir()
        self.env = dict(os.environ, HOME=str(self.t / "home"), TMPDIR=str(self.t / "tmp"))

    def py(self, *a):
        return subprocess.run([sys.executable, "-B", "-I", str(RAIZ / "auditar.py"), *a], capture_output=True,
                              text=True, timeout=180, env=self.env)

    def test_demo_laboratorio_ya_no_confirma_con_un_experimento(self):
        r = self.py("demo-laboratorio")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("causa confirmada: False", r.stdout)
        self.assertIn("regresión no creada", r.stdout)
        lista = self.py("listar").stdout
        self.assertIn("causa hipotesis", lista)
        self.assertNotIn("causa confirmada", lista)
        c = self.py("demo-ciclo")                                       # el camino completo sigue funcionando
        self.assertEqual(c.returncode, 0, c.stderr)
        self.assertIn("HIP-000001 respaldada (simulación)", c.stdout)
        self.assertEqual(sorted(p.name for p in (self.t / "tmp" / "equipo_f2").iterdir()), ["lab_v2f1"])  # CAMBIO V2-E.6 (V2-E.5-r3: datos_v2e5r3)  # CAMBIO V2-E.6-r2 (V2-E.6: lab_v2e6)  # CAMBIO V2-E.6-r3 (V2-E.6-r2: lab_v2e6r2)  # CAMBIO V2-E.7 (V2-E.6-r3: lab_v2e6r3)  # CAMBIO V2-E.7-r2 (V2-E.7: lab_v2e7)  # CAMBIO V2-E.7-r3 (V2-E.7-r2: lab_v2e7r2)  # CAMBIO V2-F (V2-E.7-r3: lab_v2e7r3)  # CAMBIO V2-F.1 (V2-F: lab_v2f)

    def test_version_esquema_y_carpetas(self):
        import eq2
        self.assertEqual(eq2.VERSION, "f2-v2f1")  # CAMBIO V2-E.6 (V2-E.5-r3: f2-v2e5-r3)  # CAMBIO V2-E.6-r2 (V2-E.6: f2-v2e6-r1)  # CAMBIO V2-E.6-r3 (V2-E.6-r2: f2-v2e6-r2)  # CAMBIO V2-E.7 (V2-E.6-r3: f2-v2e6-r3)  # CAMBIO V2-E.7-r2 (V2-E.7: f2-v2e7-r1)  # CAMBIO V2-E.7-r3 (V2-E.7-r2: f2-v2e7-r2)  # CAMBIO V2-F (V2-E.7-r3: f2-v2e7-r3)  # CAMBIO V2-F.1 (V2-F: f2-v2f)
        self.assertEqual(Inc.ESQUEMA_INCIDENCIAS, "4")
        self.assertEqual(config.CARPETA_V2E4R2, "datos_v2e4r2")
        self.assertIn("datos_v2e4", config.CARPETAS_ANTERIORES)
        self.assertFalse(config.MODO_B_HABILITADO)

    def test_base_de_v2e4_r1_rechazada(self):
        raiz = self.t / "x" / "equipo_f2"
        raiz.parent.mkdir()
        reg = Inc.RegistroIncidencias(rutas.Laboratorio(raiz, raiz / "d"))
        reg._meta_set("esquema", "3")
        reg.cerrar()
        from eq2 import memoria
        with self.assertRaises(memoria.EsquemaIncompatible):
            Inc.RegistroIncidencias(rutas.Laboratorio(raiz, raiz / "d"))


if __name__ == "__main__":
    unittest.main()
