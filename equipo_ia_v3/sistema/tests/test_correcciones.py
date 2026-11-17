"""Pruebas de las correcciones de la auditoría de GPT-6 (revisión r2).

Todo con backend SIMULADO, en carpetas temporales. Las pruebas de enlaces
simbólicos y de SIGKILL usan el sistema de archivos y procesos REALES del
entorno donde se ejecutan (no son simulaciones del sistema operativo).
"""
import json
import os
import signal
import sqlite3
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

import _comun
from eq2 import config, contexto, memoria, orquestador, rutas, sanea, vigilancia
from eq2.inferencia import BackendSimulado


def vig_ok():
    return vigilancia.Vigilante(lector_mem=lambda: 1_500_000, lector_bat=lambda: (80, False))


class Lab(unittest.TestCase):
    def setUp(self):
        self.tmp = _comun.carpeta_temporal()
        self.t = Path(self.tmp.name)
        self.lab = self.t / "equipo_f2"
        self.fuera = self.t / "fuera"
        self.fuera.mkdir()
        self.reloj = _comun.Reloj()

    def tearDown(self):
        self.tmp.cleanup()

    def orq(self, backend=None, base=None, **kw):
        return orquestador.Orquestador(base or self.lab, backend or BackendSimulado(),
                                       vig_ok(), reloj=self.reloj,
                                       raiz_laboratorio=self.lab, **kw)

    def sql(self, consulta, params=()):
        con = sqlite3.connect(str(self.lab / "datos" / "sesion.db"))
        try:
            return con.execute(consulta, params).fetchall()
        finally:
            con.close()


# 1. Confinamiento de rutas ---------------------------------------------------
class TestRutas(Lab):
    def test_raiz_desde_tmpdir(self):
        self.assertEqual(rutas.raiz_laboratorio({"TMPDIR": "/x/tmp"}), Path("/x/tmp/equipo_f2"))
        for env in ({}, {"TMPDIR": ""}, {"TMPDIR": "relativo/tmp"}):
            with self.assertRaises(rutas.RutaInsegura):
                rutas.raiz_laboratorio(env)

    def test_raiz_por_defecto_usa_tmpdir_del_entorno(self):
        with mock.patch.dict(os.environ, {"TMPDIR": str(self.t)}):
            o = orquestador.Orquestador(self.lab, BackendSimulado(), vig_ok())
            self.assertEqual(o.lab.raiz.name, "equipo_f2")
            with self.assertRaises(rutas.RutaInsegura):
                orquestador.Orquestador(self.fuera, BackendSimulado(), vig_ok())

    def test_base_fuera_del_laboratorio(self):
        for base in (self.fuera, self.t, self.lab / ".." / "fuera", Path("/etc"),
                     Path(str(self.lab) + "_otro")):
            with self.assertRaises(rutas.RutaInsegura, msg=str(base)):
                rutas.Laboratorio(self.lab, base)

    def test_subcarpeta_del_laboratorio_permitida(self):
        lab = rutas.Laboratorio(self.lab, self.lab / "sub")
        lab.crear_base()
        self.assertTrue((self.lab / "sub").is_dir())

    def test_nombres_peligrosos(self):
        lab = rutas.Laboratorio(self.lab)
        lab.crear_base()
        for malo in ("..", ".", "", "a/b", "/etc/passwd", "a\\b", "x\x00y", None, 5):
            with self.assertRaises(rutas.RutaInsegura, msg=repr(malo)):
                lab.ruta(malo)

    def test_laboratorio_enlace_simbolico_rechazado(self):
        os.symlink(self.fuera, self.lab)
        with self.assertRaises(rutas.RutaInsegura):
            rutas.Laboratorio(self.lab)
        with self.assertRaises(rutas.RutaInsegura):
            self.orq()
        self.assertEqual(list(self.fuera.iterdir()), [])

    def test_tmpdir_enlace_simbolico_si_se_acepta(self):
        real = self.t / "real_tmp"
        real.mkdir()
        enlace = self.t / "enlace_tmp"
        os.symlink(real, enlace)
        lab = rutas.Laboratorio(enlace / "equipo_f2")
        lab.crear_base()
        self.assertTrue((real / "equipo_f2").is_dir())

    def test_subcarpeta_enlace_a_fuera(self):
        for nombre in ("datos", "copias", "runs"):
            with self.subTest(nombre):
                self.lab.mkdir(exist_ok=True)
                os.symlink(self.fuera, self.lab / nombre)
                with self.assertRaises(rutas.RutaInsegura):
                    self.orq().run(["t"])
                self.assertEqual(list(self.fuera.iterdir()), [])
                self.assertFalse((self.lab / "lock").exists())      # candado no queda
                os.unlink(self.lab / nombre)

    def test_enlace_hacia_otra_carpeta_del_mismo_laboratorio(self):
        """El destino real queda dentro del laboratorio, pero aun así se prohíbe el enlace."""
        (self.lab / "real").mkdir(parents=True)
        os.symlink(self.lab / "real", self.lab / "datos")
        with self.assertRaises(rutas.RutaInsegura):
            self.orq().run(["t"])
        self.assertEqual(list((self.lab / "real").iterdir()), [])
        lab = rutas.Laboratorio(self.lab)
        with self.assertRaises(rutas.RutaInsegura):
            lab.ruta("datos", "sesion.db")
        with self.assertRaises(rutas.RutaInsegura):
            lab.crear_dir("datos")

    def test_bd_enlace_a_fuera(self):
        (self.lab / "datos").mkdir(parents=True)
        objetivo = self.fuera / "robado.db"
        os.symlink(objetivo, self.lab / "datos" / "a1.db")
        r = self.orq().run(["t"])
        self.assertFalse(objetivo.exists())
        self.assertTrue(r["motivo_fin"].startswith("error_interno:RutaInsegura"), r["motivo_fin"])
        self.assertEqual(r["resultado_global"], "incompleto")
        self.assertFalse((self.lab / "lock").exists())

    def test_bd_enlace_directo_rechazada_por_memoria(self):
        os.symlink(self.fuera / "x.db", self.t / "enlace.db")
        with self.assertRaises(rutas.RutaInsegura):
            memoria.SesionDB(self.t / "enlace.db")
        with self.assertRaises(rutas.RutaInsegura):
            memoria.MemoriaAgente(self.t / "enlace.db", "A1")
        self.assertFalse((self.fuera / "x.db").exists())

    def test_respaldo_rechaza_enlaces(self):
        m = memoria.MemoriaAgente(self.t / "a1.db", "A1")
        m.cerrar()
        os.symlink(self.t / "a1.db", self.t / "a1_enlace.db")
        (self.t / "c").mkdir()
        with self.assertRaises(rutas.RutaInsegura):
            memoria.respaldar(self.t / "a1_enlace.db", self.t / "c")
        os.symlink(self.fuera, self.t / "c_enlace")
        with self.assertRaises(rutas.RutaInsegura):
            memoria.respaldar(self.t / "a1.db", self.t / "c_enlace")
        self.assertEqual(list(self.fuera.iterdir()), [])

    def test_crear_exclusivo_no_sobrescribe_ni_sigue_enlaces(self):
        lab = rutas.Laboratorio(self.lab)
        lab.crear_base()
        objetivo = self.fuera / "victima.txt"
        objetivo.write_text("original")
        os.symlink(objetivo, self.lab / "trampa.txt")
        for fn in (lambda: lab.crear_exclusivo(("trampa.txt",), "malo"),
                   lambda: lab.anexar(("trampa.txt",), "malo")):
            with self.assertRaises((rutas.RutaInsegura, OSError)):
                fn()
        self.assertEqual(objetivo.read_text(), "original")
        lab.crear_exclusivo(("a.txt",), "uno")
        with self.assertRaises(FileExistsError):
            lab.crear_exclusivo(("a.txt",), "dos")
        self.assertEqual((self.lab / "a.txt").read_text(), "uno")

    def test_ejecucion_solo_escribe_dentro_del_laboratorio(self):
        (self.fuera / "centinela.txt").write_text("x")
        self.orq().run(["una tarea"])
        todos = {p for p in self.t.rglob("*")}
        permitido = {self.lab, self.fuera, self.fuera / "centinela.txt"}
        for p in todos:
            self.assertTrue(p in permitido or self.lab in p.parents, str(p))
        self.assertEqual([p.name for p in self.fuera.iterdir()], ["centinela.txt"])

    def test_stop_enlace_colgante_cuenta_como_parada(self):
        self.lab.mkdir()
        os.symlink(self.t / "no_existe", self.lab / "STOP")
        be = BackendSimulado()
        r = self.orq(be).run(["t"])
        self.assertEqual(r["motivo_fin"], "stop_usuario")
        self.assertEqual(len(be.llamadas), 0)

    def test_candado_no_se_toca_si_es_ajeno(self):
        (self.lab / "lock").mkdir(parents=True)
        (self.lab / "lock" / "pid").write_text("999999999")
        with self.assertRaises(orquestador.SesionActiva) as c:
            self.orq().run(["t"])
        self.assertTrue(c.exception.obsoleto)
        self.assertEqual(c.exception.pid, "999999999")
        self.assertTrue((self.lab / "lock" / "pid").exists())

    def test_candado_con_pid_vivo(self):
        (self.lab / "lock").mkdir(parents=True)
        (self.lab / "lock" / "pid").write_text(str(os.getpid()))
        with self.assertRaises(orquestador.SesionActiva) as c:
            self.orq().run(["t"])
        self.assertFalse(c.exception.obsoleto)


# 2. Recuperación de sesiones en_curso ---------------------------------------
class TestRecuperacion(Lab):
    def preparar_huerfana(self):
        (self.lab / "datos").mkdir(parents=True)
        db = memoria.SesionDB(self.lab / "datos" / "sesion.db")
        s_vieja = db.crear_sesion()
        t1 = db.crear_tarea(s_vieja, "tarea a medias")
        db.estado_tarea(t1, "en_deliberacion")
        t2 = db.crear_tarea(s_vieja, "tarea pendiente")
        s_ok = db.crear_sesion()
        db.cerrar_sesion(s_ok, "completa", "fin_normal")
        t3 = db.crear_tarea(s_ok, "tarea cerrada")
        db.estado_tarea(t3, "decidida")
        db.cerrar()
        return s_vieja, s_ok

    def test_unidad_recuperar(self):
        with _comun.carpeta_temporal() as d:
            db = memoria.SesionDB(Path(d) / "s.db")
            a = db.crear_sesion()
            ta = db.crear_tarea(a, "x")
            db.estado_tarea(ta, "en_deliberacion")
            tb = db.crear_tarea(a, "y")
            tc = db.crear_tarea(a, "z")
            db.estado_tarea(tc, "decidida")
            b = db.crear_sesion()
            db.cerrar_sesion(b, "abortada", "tiempo_sesion")
            self.assertEqual(db.recuperar_interrumpidas(), [a])
            self.assertEqual(db.recuperar_interrumpidas(), [])           # idempotente
            ses = dict(db.con.execute("SELECT id,estado FROM sesiones").fetchall())
            self.assertEqual(ses, {a: "interrumpida", b: "abortada"})
            self.assertEqual(db.con.execute("SELECT motivo_fin FROM sesiones WHERE id=?", (a,))
                             .fetchone()[0], "recuperada_tras_interrupcion")
            tar = dict(db.con.execute("SELECT id,estado FROM tareas").fetchall())
            self.assertEqual(tar, {ta: "abortada", tb: "abortada", tc: "decidida"})
            self.assertEqual(db.con.execute(
                "SELECT count(*) FROM eventos WHERE tipo='sesion_recuperada'").fetchone()[0], 1)
            db.cerrar()

    def test_el_orquestador_recupera_y_no_reanuda(self):
        vieja, ok = self.preparar_huerfana()
        be = BackendSimulado()
        r = self.orq(be).run(["tarea nueva"])
        self.assertEqual(r["sesiones_recuperadas"], [vieja])
        self.assertEqual(len(be.llamadas), 7)                  # solo la tarea NUEVA
        for c in be.llamadas:
            self.assertNotIn("tarea a medias", c["mensajes"][-1]["content"])
        ses = dict(self.sql("SELECT id,estado FROM sesiones"))
        self.assertEqual(ses[vieja], "interrumpida")
        self.assertEqual(ses[ok], "completa")
        self.assertEqual(ses[r["sesion_id"]], "completa")
        self.assertEqual(self.sql("SELECT count(*) FROM sesiones WHERE estado='en_curso'"), [(0,)])
        self.assertEqual(self.sql("SELECT estado FROM tareas WHERE sesion_id=? ORDER BY id", (vieja,)),
                         [("abortada",), ("abortada",)])
        self.assertTrue(self.sql("SELECT 1 FROM eventos WHERE tipo='sesiones_recuperadas'"))

    def test_sigkill_real_deja_candado_y_se_recupera_en_la_siguiente(self):
        codigo = (
            "import sys, os, signal\n"
            "sys.path.insert(0, sys.argv[1])\n"
            "from eq2.orquestador import Orquestador\n"
            "from eq2.inferencia import BackendSimulado\n"
            "from eq2.vigilancia import Vigilante\n"
            "def g(n, f, m, mt):\n"
            "    if n == 3:\n"
            "        os.kill(os.getpid(), signal.SIGKILL)\n"
            "    return 'VOTO: aprobar\\nRAZON: x' if f == 'voto' else 'texto'\n"
            "v = Vigilante(lector_mem=lambda: 10**6, lector_bat=lambda: (None, None))\n"
            "Orquestador(sys.argv[2], BackendSimulado(g), v, raiz_laboratorio=sys.argv[2]).run(['t'])\n")
        p = subprocess.run([sys.executable, "-B", "-I", "-c", codigo,
                            str(_comun.RAIZ / "src"), str(self.lab)],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, -signal.SIGKILL, p.stderr)
        pid_hijo = (self.lab / "lock" / "pid").read_text()
        self.assertEqual(self.sql("SELECT estado FROM sesiones"), [("en_curso",)])
        self.assertEqual(self.sql("SELECT estado FROM tareas"), [("en_deliberacion",)])

        with self.assertRaises(orquestador.SesionActiva) as c:       # NO se borra solo
            self.orq().run(["otra"])
        self.assertTrue(c.exception.obsoleto)
        self.assertEqual(c.exception.pid, pid_hijo)
        self.assertEqual(self.sql("SELECT estado FROM sesiones"), [("en_curso",)])

        os.remove(self.lab / "lock" / "pid")                          # borrado manual
        os.rmdir(self.lab / "lock")
        r = self.orq().run(["otra"])
        self.assertEqual(r["sesiones_recuperadas"], [1])
        self.assertEqual(r["estado"], "completa")
        self.assertEqual(self.sql("SELECT estado FROM sesiones ORDER BY id"),
                         [("interrumpida",), ("completa",)])
        self.assertEqual(self.sql("SELECT estado FROM tareas ORDER BY id"),
                         [("abortada",), ("decidida",)])


# 3. Timeout de V0-V1 ---------------------------------------------------------
class TestTimeoutDocumentado(Lab):
    def test_limitacion_en_el_resumen(self):
        r = self.orq().run(["t"])
        texto = " ".join(r["limitaciones"])
        self.assertIn("no se puede interrumpir una llamada bloqueada", texto)
        self.assertIn("plazo efectivo", texto)
        self.assertIn("supervisión independiente", texto)
        en_disco = json.loads(next((self.lab / "runs").glob("*/summary.json")).read_text())
        self.assertEqual(en_disco["limitaciones"], r["limitaciones"])

    def test_el_plazo_solo_se_detecta_al_volver_la_llamada(self):
        """Demuestra la limitación: la llamada se deja terminar y luego se marca como fallida."""
        estado = {"terminada": False}

        def g(n, f, m, mt):
            self.reloj.avanzar(config.SEG_POR_LLAMADA + 500)       # backend "bloqueado"
            estado["terminada"] = True                              # nadie lo interrumpió
            return "texto"
        be = BackendSimulado(g)
        r = self.orq(be).run(["t"])
        self.assertTrue(estado["terminada"])
        self.assertEqual(be.llamadas[0]["plazo_s"], config.SEG_POR_LLAMADA)
        self.assertEqual(r["tareas"][0]["motivo"], "inferencia_fallida")
        self.assertEqual(self.sql("SELECT texto FROM turnos"), [("plazo_superado",)])


# 4. Tope de tamaño SQLite ----------------------------------------------------
class TestTamano(Lab):
    LIMITE = 96 * 1024

    def setUp(self):
        super().setUp()
        self.viejo = config.MAX_DB_BYTES
        config.MAX_DB_BYTES = self.LIMITE

    def tearDown(self):
        config.MAX_DB_BYTES = self.viejo
        super().tearDown()

    def test_agregar_se_detiene_antes_del_limite_y_revierte(self):
        ruta = self.t / "a1.db"
        m = memoria.MemoriaAgente(ruta, "A1")
        ok = 0
        with self.assertRaises(memoria.MemoriaLlena):
            for i in range(config.MAX_MEMORIA_ENTRADAS + 50):
                m.agregar("hecho", f"entrada {i} " + "palabra%d " % i * 40)
                ok += 1
        self.assertGreater(ok, 5)
        self.assertLess(ok, config.MAX_MEMORIA_ENTRADAS)              # paró por tamaño, no por nº
        self.assertEqual(m.contar_vigentes(), ok)                     # la fallida se revirtió
        self.assertLessEqual(m.tamano_bytes(), self.LIMITE)
        self.assertLessEqual(os.path.getsize(ruta), self.LIMITE)
        self.assertTrue(m.quick_check())
        self.assertTrue(m.buscar("entrada"))                          # FTS coherente
        m.cerrar()

    def test_tope_duro_de_sqlite_aunque_se_salte_agregar(self):
        ruta = self.t / "s.db"
        db = memoria.SesionDB(ruta)
        sid = db.crear_sesion()
        with self.assertRaises(sqlite3.OperationalError) as c:
            for i in range(10_000):
                db.con.execute("INSERT INTO eventos(sesion_id,ts,tipo,detalle) VALUES(?,?,?,?)",
                               (sid, "t", "x", "y" * 4000))
                db.con.commit()
        self.assertIn("full", str(c.exception).lower())
        self.assertLessEqual(os.path.getsize(ruta), self.LIMITE)
        db.cerrar()

    def test_sesiondb_llena_no_falla_en_silencio(self):
        db = memoria.SesionDB(self.t / "s2.db")
        sid = db.crear_sesion()
        with self.assertRaises(sqlite3.OperationalError):
            for i in range(10_000):
                db.evento(sid, "x", "z" * 500)
                db.con.execute("INSERT INTO muestras(sesion_id,ts) VALUES(?,?)", (sid, "t" * 4000))
                db.con.commit()
        db.cerrar()

    def test_pragma_solo_acepta_enteros(self):
        for malo in ("5; DROP TABLE x", 0, -1, True, 2.5, None):
            with self.assertRaises(ValueError):
                memoria._pragma_max_paginas(malo)
        self.assertEqual(memoria._pragma_max_paginas(24), "PRAGMA max_page_count=24")


# 5. Estimación de tokens provisional ----------------------------------------
class TestTokensProvisionales(Lab):
    def test_marcado_en_codigo_y_resultados(self):
        self.assertIn("provisional", config.ESTIMACION_TOKENS)
        self.assertIn("NO es una medida", contexto.estimar_tokens.__doc__)
        r = self.orq().run(["t"])
        self.assertEqual(r["estimacion_tokens"], config.ESTIMACION_TOKENS)
        self.assertIn("TOKENS: provisional", " ".join(r["limitaciones"]))
        params = json.loads(self.sql("SELECT params_json FROM sesiones")[0][0])
        self.assertEqual(params["estimacion_tokens"], config.ESTIMACION_TOKENS)

    def test_no_se_guarda_la_estimacion_como_medida(self):
        self.orq().run(["t"])
        filas = self.sql("SELECT tokens_prompt,tokens_gen,cache_n,ms_prompt,ms_gen FROM turnos")
        self.assertEqual(len(filas), 7)
        self.assertTrue(all(f == (None,) * 5 for f in filas))


# 6. Formato de voto estricto -------------------------------------------------
class TestVotoEstricto(Lab):
    def test_rechaza_lineas_inesperadas(self):
        malos = [
            "VOTO: aprobar\nRAZON: bien\nGracias por preguntar",
            "Mi análisis es positivo.\nVOTO: aprobar\nRAZON: bien",
            "VOTO: aprobar\nporque me parece bien",
            "VOTO: aprobar\nRAZON: a\nRAZON: b",
            "RAZON: bien\nVOTO: aprobar",
            "VOTO: aprobar\nRAZON: x\nVOTO: rechazar",
            "VOTO: aprobar\nVOTO: aprobar",
            "VOTO: aprobar\nRAZON: x\n\n- extra",
            "```\nVOTO: aprobar\nRAZON: x\n```",
            "- VOTO: aprobar\nRAZON: x",
            "**VOTO: aprobar**",
            "VOTO: aprobar.",
            "VOTO: aprobar porque sí",
            "VOTO: aprobar\n\n\nRAZON: a\nb",
            "VOTO: aprobar\nRAZON",
        ]
        for m in malos:
            self.assertIsNone(sanea.parsear_voto(m), repr(m))

    def test_acepta_solo_el_formato_exacto(self):
        self.assertEqual(sanea.parsear_voto("VOTO: aprobar"), ("aprobar", ""))
        self.assertEqual(sanea.parsear_voto("  VOTO: rechazar  \n\n  RAZON: riesgo  \n"),
                         ("rechazar", "riesgo"))
        self.assertEqual(sanea.parsear_voto("VOTO:abstencion\nRAZON:"), ("abstencion", ""))

    def test_en_el_orquestador_una_linea_extra_cuenta_como_invalida(self):
        be = BackendSimulado(lambda n, f, m, mt: ("VOTO: aprobar\nRAZON: ok\nDetalle extra"
                                                  if f == "voto" else "texto"))
        r = self.orq(be).run(["t"])
        self.assertEqual(len(be.llamadas), 4 + 6)                      # 3 votos x (1+1 reintento)
        self.assertEqual(self.sql("SELECT count(*) FROM turnos WHERE estado='invalido'"), [(6,)])
        self.assertEqual({v for _, v in self.sql("SELECT agente,postura FROM votos")}, {"abstencion"})
        self.assertEqual(r["tareas"][0]["resultado"], "sin_consenso")


if __name__ == "__main__":
    unittest.main()
