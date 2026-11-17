"""Pruebas de la Etapa 5: memoria individual, episódica y de proyecto; evaluación prerregistrada.

Ejecutar desde equipo_ia_v3/:   python3 -B -m unittest discover -s pruebas -t pruebas -v
"""
import hashlib
import os
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

import comun
from eq3 import cambios as C, ingesta as I, memoria as Mm, traza as T

V3 = comun.RAIZ / "v3"
AHORA = "2026-11-10T12:00:00+00:00"


def _tmp(caso):
    d = tempfile.TemporaryDirectory(prefix="eq3_m_", dir=os.environ.get("TMPDIR"))
    caso.addCleanup(d.cleanup)
    return Path(d.name)


class TestEvaluacionPrerregistrada(unittest.TestCase):
    def test_los_escenarios_no_cambiaron_desde_su_registro(self):
        for nombre in ("escenarios_memoria.json", "escenarios_memoria_2.json"):
            registrado = (V3 / nombre.replace(".json", ".sha256")).read_text(encoding="utf-8").split()[0]
            self.assertEqual(hashlib.sha256((V3 / nombre).read_bytes()).hexdigest(), registrado, nombre)

    def _evaluar(self, nombre):
        return Mm.evaluar(V3 / nombre, _tmp(self))

    def test_conjunto_de_contraste(self):
        r = self._evaluar("escenarios_memoria_2.json")
        self.assertEqual(r["resumen"]["memoria_v3"], {"recall_medio": 1.0, "falsos": 0, "prohibidos": 0})
        for q in r["por_consulta"]:
            if not q["relevantes"]:
                self.assertEqual(q["memoria_v3"]["seleccion"], [], q["id"])        # controles negativos
        self.assertGreater(r["resumen"]["recencia"]["prohibidos"], 0)            # sin filtrar, se cuela lo prohibido
        self.assertEqual(r["resumen"]["sin_memoria"]["recall_medio"], 0.0)

    def test_conjunto_de_diagnostico_y_defensas_de_v2f1(self):
        r = self._evaluar("escenarios_memoria.json")
        self.assertEqual(r["resumen"]["memoria_v3"], {"recall_medio": 1.0, "falsos": 0, "prohibidos": 0})
        self.assertEqual([x["etiqueta"] for x in r["rechazados_al_escribir"]], ["R7"])   # instructivo: al escribir
        q5 = next(q for q in r["por_consulta"] if q["id"] == "Q5")
        self.assertEqual(q5["memoria_v3"]["seleccion"], [])


class TestMemoriaIndividual(unittest.TestCase):
    def setUp(self):
        from eq2.aprendizaje import AprendizajeAgente
        self.lab = _tmp(self) / "lab"
        (self.lab / "aprendizaje").mkdir(parents=True)
        self.db = self.lab / "aprendizaje" / "a1.db"
        apr = AprendizajeAgente(self.db, "A1", ahora=lambda: AHORA)
        try:
            self.hecho = apr.recordar("hecho", "sorted devuelve una lista nueva sin modificar la original",
                                      "observado", estado="sin_verificar")["id"]
            self.hipo = apr.recordar("hipotesis", "quizá sorted sea lento con listas enormes", "opinion")["id"]
        finally:
            apr.cerrar()

    def test_solo_lectura_y_sin_escrituras(self):
        antes = hashlib.sha256(self.db.read_bytes()).hexdigest()
        r = Mm.individual(self.lab, "A1", "ordenar una lista con sorted", AHORA)
        self.assertEqual([s["id"] for s in r["seleccion"]], [self.hecho])
        self.assertEqual(r["seleccion"][0]["clase"], "semantica")
        self.assertEqual(r["escrituras"], 0)
        self.assertEqual(hashlib.sha256(self.db.read_bytes()).hexdigest(), antes)
        lector = Mm._Lector(self.db, "A1", AHORA)
        self.addCleanup(lector.con.close)
        with self.assertRaises(sqlite3.OperationalError):
            lector.con.execute("DELETE FROM recuerdos")                          # la conexión es de SOLO LECTURA

    def test_hipotesis_excluida_salvo_permiso(self):
        r = Mm.individual(self.lab, "A1", "sorted lento listas enormes", AHORA)
        self.assertNotIn(self.hipo, [s["id"] for s in r["seleccion"]])
        self.assertIn({"id": self.hipo, "motivo": "hipotesis_excluida"}, r["omitidos"])
        r = Mm.individual(self.lab, "A1", "sorted lento listas enormes", AHORA, permitir_hipotesis=True)
        self.assertIn(self.hipo, [s["id"] for s in r["seleccion"]])

    def test_el_filtro_solo_quita(self):
        lector = Mm._Lector(self.db, "A1", AHORA)
        self.addCleanup(lector.con.close)          # Windows no deja borrar una base SQLite con una conexión abierta
        crudo = Mm.M.recuperar(Mm.V.capturar(lector, "A1"), "de la un en", ahora=AHORA)
        self.assertTrue(crudo["seleccion"])                                    # sin filtro: coincidencia por «la»…
        r = Mm.individual(self.lab, "A1", "de la un en", AHORA)
        self.assertEqual(r["seleccion"], [])                                    # …con filtro: ninguna de contenido
        self.assertTrue(all(o["motivo"] == "sin_coincidencia_de_contenido" for o in r["omitidos"]
                            if o["id"] in {s["id"] for s in crudo["seleccion"]}))

    def test_sin_base_y_agente_desconocido(self):
        vacio = _tmp(self)
        self.assertEqual(Mm.individual(vacio, "A2", "x", AHORA)["nota"], "sin base de aprendizaje")
        with self.assertRaises(ValueError):
            Mm.individual(self.lab, "A9", "x", AHORA)


class TestEpisodicaYProyecto(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._d = tempfile.TemporaryDirectory(prefix="eq3_me_", dir=os.environ.get("TMPDIR"))
        cls.lab = comun.demo(Path(cls._d.name) / "demo")
        cls.traza = T.Traza(cls.lab / "traza_v3.sqlite3")
        I.importar_tarea(cls.traza, cls.lab, "LAB-001")

    @classmethod
    def tearDownClass(cls):
        cls.traza.cerrar()
        cls._d.cleanup()

    def test_episodios_relevantes_y_control_negativo(self):
        e = Mm.episodica(self.traza, "calcular la mediana de una lista de valores")
        self.assertEqual([x["ejecucion"] for x in e], ["LAB-001/E001"])
        self.assertEqual(e[0]["naturaleza"], "SIMULADA")
        self.assertEqual(Mm.episodica(self.traza, "ordenar un diccionario por clave"), [])

    def test_memoria_de_proyecto_y_bloque_para_el_prompt(self):
        lab = _tmp(self) / "lab"
        shutil.copytree(self.lab, lab)
        with T.Traza(lab / "traza_v3.sqlite3") as t, C.Controlador(lab) as c:
            r = C.proponer_desde_traza(c, t, "LAB-001/E001", "demo", "mediana.py")
            c.autorizar(r["id"], r["sha256_despues"][:12])
            c.aplicar(r["id"])
            p = Mm.de_proyecto(c.cambios, "mejorar la función mediana del proyecto")
            self.assertEqual([x["propuesta"] for x in p], [r["id"]])
            self.assertEqual(Mm.de_proyecto(c.cambios, "dibujar un gráfico de barras"), [])
            b = Mm.consultar(lab, "A2", "mediana", AHORA, traza=t, cambios=c.cambios)["bloque"]
        self.assertTrue(b.startswith(Mm.CABECERA))                              # siempre marcado como DATOS
        self.assertIn("episodio LAB-001/E001", b)
        self.assertIn(r["id"], b)


if __name__ == "__main__":
    unittest.main()
