import sqlite3
import unittest
from pathlib import Path
import _comun  # noqa
from eq2 import config, memoria


class TestSesionDB(unittest.TestCase):
    def setUp(self):
        self.tmp = _comun.carpeta_temporal()
        self.db = memoria.SesionDB(Path(self.tmp.name) / "sesion.db")

    def tearDown(self):
        self.db.cerrar()
        self.tmp.cleanup()

    def test_pragmas(self):
        self.assertEqual(self.db.con.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        self.assertEqual(self.db.con.execute("PRAGMA busy_timeout").fetchone()[0], 5000)
        self.assertTrue(self.db.quick_check())

    def test_claves_foraneas(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.crear_tarea(999, "x")

    def test_checks(self):
        sid = self.db.crear_sesion()
        tid = self.db.crear_tarea(sid, "t")
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.registrar_turno(tid, 1, "ejecutar", "A1", "ok", "x", None)
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.registrar_turno(tid, 1, "voto", "A9", "ok", "x", None)
        t = self.db.registrar_turno(tid, 1, "voto", "A1", "ok", "x", None)
        with self.assertRaises(sqlite3.IntegrityError):          # UNIQUE(tarea, orden)
            self.db.registrar_turno(tid, 1, "voto", "A2", "ok", "x", None)
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.registrar_voto(tid, "A1", t, "quizas", "")
        self.db.registrar_voto(tid, "A1", t, "aprobar", "")
        with self.assertRaises(sqlite3.IntegrityError):          # un voto por agente
            self.db.registrar_voto(tid, "A1", t, "rechazar", "")
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.registrar_conclusion(tid, "genial", "{}", "")
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.crear_tarea(sid, "x" * 1501)

    def test_conclusion_nace_como_hipotesis(self):
        sid = self.db.crear_sesion()
        tid = self.db.crear_tarea(sid, "t")
        # CAMBIO V2-D: una conclusión 'aprobada' exige propuesta completa (CHECK del esquema 4).
        self.db.registrar_conclusion(tid, "aprobada", "{}", "x", propuesta_estado="completa",
                                     fiabilidad="normal", fiabilidad_json="{}")
        v = self.db.con.execute("SELECT verificacion FROM conclusiones").fetchone()[0]
        self.assertEqual(v, "hipotesis")

    def test_eventos_append_only(self):
        sid = self.db.crear_sesion()
        self.db.evento(sid, "a", "b")
        with self.assertRaises(sqlite3.DatabaseError):
            self.db.con.execute("UPDATE eventos SET tipo='x'")
        with self.assertRaises(sqlite3.DatabaseError):
            self.db.con.execute("DELETE FROM eventos")
        self.assertEqual(self.db.contar("eventos"), 1)

    def test_muestra_none_no_es_cero(self):
        from eq2.vigilancia import Muestra
        sid = self.db.crear_sesion()
        self.db.registrar_muestra(sid, Muestra(0.0, None, None, None))
        r = self.db.con.execute("SELECT mem_available_kb,bateria_pct,cargando FROM muestras").fetchone()
        self.assertEqual(tuple(r), (None, None, None))

    def test_texto_malicioso_se_guarda_literal(self):
        sid = self.db.crear_sesion()
        mal = "x'); DROP TABLE tareas;--"
        self.db.crear_tarea(sid, mal)
        self.assertEqual(self.db.con.execute("SELECT enunciado FROM tareas").fetchone()[0], mal)
        self.assertEqual(self.db.contar("tareas"), 1)

    def test_contar_solo_tablas_fijas(self):
        with self.assertRaises(KeyError):
            self.db.contar("tareas; DROP TABLE meta")


class TestMemoriaAgente(unittest.TestCase):
    def setUp(self):
        self.tmp = _comun.carpeta_temporal()
        self.ruta = Path(self.tmp.name) / "a1.db"
        self.m = memoria.MemoriaAgente(self.ruta, "A1")

    def tearDown(self):
        self.m.cerrar()
        self.tmp.cleanup()

    def test_todo_entra_sin_verificar(self):
        for tipo in ("hecho", "hipotesis", "leccion"):
            i = self.m.agregar(tipo, "dato " + tipo)
            fila = self.m.con.execute("SELECT verificacion,confianza FROM memoria WHERE id=?",
                                      (i,)).fetchone()
            self.assertEqual(tuple(fila), ("sin_verificar", "baja"))

    def test_check_directo_rechaza_verificacion_invalida(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.m.con.execute(
                "INSERT INTO memoria(creado,tipo,texto,verificacion) VALUES('x','hecho','t','confiable')")

    def test_validaciones(self):
        with self.assertRaises(ValueError):
            self.m.agregar("orden", "x")
        with self.assertRaises(ValueError):
            self.m.agregar("hecho", "   ")
        with self.assertRaises(ValueError):
            self.m.agregar("hecho", "x", confianza="total")

    def test_texto_acotado(self):
        i = self.m.agregar("hecho", "z" * 5000)
        n = self.m.con.execute("SELECT length(texto) FROM memoria WHERE id=?", (i,)).fetchone()[0]
        self.assertEqual(n, config.MAX_MEMORIA_CHARS)

    def test_limite_de_entradas(self):
        for i in range(config.MAX_MEMORIA_ENTRADAS):
            self.m.agregar("hecho", f"entrada {i}")
        with self.assertRaises(memoria.MemoriaLlena):
            self.m.agregar("hecho", "una más")
        self.assertEqual(self.m.contar_vigentes(), config.MAX_MEMORIA_ENTRADAS)

    def test_limite_de_tamano(self):
        viejo = config.MAX_DB_BYTES
        try:
            config.MAX_DB_BYTES = 1
            with self.assertRaises(memoria.MemoriaLlena):
                self.m.agregar("hecho", "x")
        finally:
            config.MAX_DB_BYTES = viejo

    def test_busqueda_fts(self):
        self.assertTrue(self.m.fts)
        self.m.agregar("leccion", "Los servidores de inferencia locales usan poca memoria")
        self.m.agregar("hecho", "El gato duerme en el sofá")
        r = self.m.buscar("¿cuánta memoria usa el servidor de inferencia?")
        self.assertTrue(r and "memoria" in r[0]["texto"])
        self.assertEqual(r[0]["verificacion"], "sin_verificar")

    def test_busqueda_con_caracteres_de_fts(self):
        self.m.agregar("hecho", "prueba de comillas y asteriscos")
        for q in ('"', '* OR NEAR(', 'a" OR "b', "x'; DROP TABLE memoria;--", "", "  ", None):
            self.m.buscar(q)            # no debe lanzar
        self.assertEqual(self.m.contar_vigentes(), 1)

    def test_busqueda_sin_fts(self):
        self.m.fts = False
        self.m.agregar("hecho", "100% seguro con_guion")
        self.assertTrue(self.m.buscar("seguro"))
        self.assertEqual(self.m.buscar("%%%"), [])

    def test_refutada_no_se_recupera(self):
        i = self.m.agregar("hecho", "dato refutable palabra")
        with self.m.con:
            self.m.con.execute("UPDATE memoria SET estado='refutado' WHERE id=?", (i,))
        self.assertEqual(self.m.buscar("refutable palabra"), [])

    def test_fts_sigue_al_actualizar(self):
        i = self.m.agregar("hecho", "alfa bravo charlie")
        with self.m.con:
            self.m.con.execute("UPDATE memoria SET texto='delta eco foxtrot' WHERE id=?", (i,))
        self.assertEqual(self.m.buscar("alfa"), [])
        self.assertTrue(self.m.buscar("delta"))

    def test_decision(self):
        self.m.registrar_decision(1, 2, "aprobar", "porque sí")
        r = self.m.con.execute("SELECT postura,consecuencia_corto FROM decisiones").fetchone()
        self.assertEqual(tuple(r), ("aprobar", "pendiente de observar"))


class TestAislamiento(unittest.TestCase):
    def test_no_se_abre_la_base_de_otro_agente(self):
        with _comun.carpeta_temporal() as d:
            m = memoria.MemoriaAgente(Path(d) / "a1.db", "A1")
            m.cerrar()
            with self.assertRaises(memoria.AislamientoViolado):
                memoria.MemoriaAgente(Path(d) / "a1.db", "A2")

    def test_agente_desconocido(self):
        with _comun.carpeta_temporal() as d:
            with self.assertRaises(ValueError):
                memoria.MemoriaAgente(Path(d) / "x.db", "A7")

    def test_reabrir_conserva_datos(self):
        with _comun.carpeta_temporal() as d:
            m = memoria.MemoriaAgente(Path(d) / "a2.db", "A2")
            m.agregar("hecho", "persistente")
            m.cerrar()
            m = memoria.MemoriaAgente(Path(d) / "a2.db", "A2")
            self.assertEqual(m.contar_vigentes(), 1)
            m.cerrar()


class TestRespaldo(unittest.TestCase):
    def test_respaldo_verificado_y_sin_sobrescribir(self):
        with _comun.carpeta_temporal() as d:
            d = Path(d)
            m = memoria.MemoriaAgente(d / "a3.db", "A3")
            m.agregar("hecho", "dato")
            m.cerrar()
            (d / "copias").mkdir()
            c = memoria.respaldar(d / "a3.db", d / "copias", etiqueta="t1")
            self.assertTrue(c.exists())
            con = sqlite3.connect(str(c))
            self.assertEqual(con.execute("SELECT count(*) FROM memoria").fetchone()[0], 1)
            con.close()
            with self.assertRaises(FileExistsError):
                memoria.respaldar(d / "a3.db", d / "copias", etiqueta="t1")

    def test_origen_inexistente_no_se_crea(self):
        with _comun.carpeta_temporal() as d:
            (Path(d) / "copias").mkdir()
            with self.assertRaises(sqlite3.Error):
                memoria.respaldar(Path(d) / "no_existe.db", Path(d) / "copias")
            self.assertFalse((Path(d) / "no_existe.db").exists())


if __name__ == "__main__":
    unittest.main()
