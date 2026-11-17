"""Pruebas de la Etapa 2: índice de código, contexto, grafo de tareas y medición (Contexto Ligero reutilizado).

Ejecutar desde equipo_ia_v3/:   python3 -B -m unittest discover -s pruebas -t pruebas -v
"""
import hashlib
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

import comun
from eq3 import grafo as G, ingesta as I, traza as T

SRC = comun.SISTEMA / "src"
FUENTE_CTX = comun.RAIZ.parent / "fuentes" / "contexto_ligero_v35"


def _tmp(caso):
    d = tempfile.TemporaryDirectory(prefix="eq3_g_", dir=os.environ.get("TMPDIR"))
    caso.addCleanup(d.cleanup)
    return Path(d.name)


class TestCopiaIdenticaDeContextoLigero(unittest.TestCase):
    def test_cada_archivo_coincide_con_su_origen(self):
        manifiesto = json.loads((G.CONTEXTO / "ORIGEN_SHA256.json").read_text(encoding="utf-8"))["archivos"]
        presentes = {p.relative_to(G.CONTEXTO).as_posix() for p in G.CONTEXTO.rglob("*")
                     if p.is_file() and p.name != "ORIGEN_SHA256.json" and "__pycache__" not in p.parts}
        self.assertEqual(presentes, set(manifiesto))                     # nada añadido ni quitado
        for rel, h in manifiesto.items():
            self.assertEqual(hashlib.sha256((G.CONTEXTO / rel).read_bytes()).hexdigest(), h, rel)
            if FUENTE_CTX.is_dir():                                         # en el repositorio, también con fuentes/
                self.assertEqual(hashlib.sha256((FUENTE_CTX / rel).read_bytes()).hexdigest(), h, rel)


class TestIndiceIncremental(unittest.TestCase):
    def setUp(self):
        t = _tmp(self)
        self.src = t / "src"
        shutil.copytree(SRC, self.src)
        self.g = G.Grafo(t / "indice.sqlite3")
        self.addCleanup(self.g.cerrar)

    def test_incremental_cambio_y_borrado_invalidan(self):
        n = len(list(self.src.rglob("*.py")))
        self.assertEqual((self.g.indexar(self.src)["changed"], n), (n, n))
        st = self.g.indexar(self.src)
        self.assertEqual((st["changed"], st["unchanged"]), (0, n))             # nada cambió: nada se reprocesa
        f = self.src / "eq2" / "vigilancia.py"
        f.write_text(f.read_text(encoding="utf-8") + "\n\ndef funcion_nueva_etapa_dos():\n    return 1\n",
                     encoding="utf-8")
        st = self.g.indexar(self.src)
        self.assertEqual((st["changed"], st["unchanged"]), (1, n - 1))
        primero = self.g.recuperar("funcion_nueva_etapa_dos", 3)[0]
        self.assertEqual(primero["ruta"], "eq2/vigilancia.py")
        self.assertIn("funcion_nueva_etapa_dos", primero["simbolos"])
        self.assertEqual(primero["sha256"], hashlib.sha256(f.read_bytes()).hexdigest())   # hash ACTUAL
        (self.src / "eq2" / "votos.py").unlink()
        self.assertEqual(self.g.indexar(self.src)["stale_removed"], 1)
        rutas = {x["ruta"] for x in self.g.recuperar("evaluar votos estricta calidad deliberacion", 12)}
        self.assertNotIn("eq2/votos.py", rutas)                                 # invalidado: no se ofrece más

    def test_paquete_en_presupuesto_y_honesto_con_los_tokens(self):
        self.g.indexar(self.src)
        p = self.g.paquete(self.src, "vigilancia leer_mem_available", 1500)
        m = p["metricas"]
        self.assertLessEqual(m["tokens_estimated"], 1500)
        self.assertIsNone(m["tokens_measured"])                                 # no se presentan como reales
        self.assertIn("no es cota de tokens reales", m["estimation_method"])
        self.assertIn("leer_mem_available", p["texto"])

    def test_dependencias_nunca_se_declaran_completas_en_ejecucion(self):
        self.g.indexar(self.src)
        d = self.g.dependencias([("eq2/vigilancia.py", "leer_mem_available")])
        self.assertIs(d["runtime_complete"], False)


class TestGrafoDeTrazas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._d = tempfile.TemporaryDirectory(prefix="eq3_gt_", dir=os.environ.get("TMPDIR"))
        t = Path(cls._d.name)
        cls.lab = comun.demo(t / "demo")
        cls.traza = T.Traza(t / "traza.sqlite3")
        I.importar_tarea(cls.traza, cls.lab, "LAB-001")
        cls.g = G.Grafo(t / "grafo.sqlite3")
        cls.cuenta = cls.g.importar_traza(cls.traza)

    @classmethod
    def tearDownClass(cls):
        cls.g.cerrar()
        cls.traza.cerrar()
        cls._d.cleanup()

    def test_nodos_y_aristas_de_la_cadena(self):
        db = self.g.db
        tareas = dict(db.execute("SELECT id, status FROM tasks").fetchall())
        self.assertEqual(tareas, {"obj:LAB-001": "active", "ejec:LAB-001/E001": "done"})
        decisiones = db.execute("SELECT count(*), min(source) FROM decisions").fetchone()
        self.assertEqual(decisiones[0], 23)
        self.assertTrue(decisiones[1].startswith("traza_v3:LAB-001/E001/D"))
        v = self.g.vecinos("ejec:LAB-001/E001")
        self.assertIn(["obj:LAB-001", "depends_on"], v["salientes"])
        self.assertEqual({d for d, k in v["salientes"] if k == "relates_to"},
                         {"ver:LAB-001/E001/v1", "ver:LAB-001/E001/v2", "ver:LAB-001/E001/v3"})
        self.assertEqual(self.g.vecinos("ver:LAB-001/E001/v3")["salientes"], [["ver:LAB-001/E001/v2", "depends_on"]])
        n_exp = len(self.traza.filas("experiencias", ejecucion_id="LAB-001/E001"))
        self.assertEqual(len([s for s, k in v["entrantes"] if s.startswith("exp:")]), n_exp)

    def test_reimportar_es_idempotente(self):
        filas = lambda: [self.g.db.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
                         for t in ("tasks", "decisions", "edges")]
        antes = filas()
        self.g.importar_traza(self.traza)
        self.assertEqual(filas(), antes)

    def test_ciclo_de_dependencias_rechazado(self):
        with self.assertRaisesRegex(ValueError, "ciclo"):
            G.index.edge(self.g.db, "ver:LAB-001/E001/v1", "ver:LAB-001/E001/v3", "depends_on")


class TestMedicion(unittest.TestCase):
    def test_recall_frente_a_oraculos_prerregistrados(self):
        t = _tmp(self)
        with G.Grafo(t / "m.sqlite3") as g:
            g.indexar(SRC)
            m1, m2 = G.medir(g, SRC), G.medir(g, SRC)
        self.assertEqual(m1, m2)                                                   # reproducible
        self.assertGreaterEqual(m1["tareas"], 15)
        for fila in m1["por_tarea"]:
            for k, v in fila.items():
                if "@" in k:
                    self.assertTrue(0 <= v <= 1, (fila["id"], k, v))
        self.assertTrue(all(d.startswith("tasks_independientes.json:") for d in m1["descartados"]),
                        m1["descartados"])                                         # otro corpus: se informa
        self.assertGreaterEqual(m1["media"]["contexto@3"], m1["media"]["ingenua@3"])   # no peor que la ingenua


if __name__ == "__main__":
    unittest.main()
