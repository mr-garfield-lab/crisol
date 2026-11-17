"""Pruebas de la Etapa 4: verificador de citas y calidad de la deliberación de A1/A2/A3.

Ejecutar desde equipo_ia_v3/:   python3 -B -m unittest discover -s pruebas -t pruebas -v
"""
import os
import shutil
import tempfile
import unittest
from pathlib import Path

import comun
from eq3 import citas as Q, ingesta as I, traza as T

CODIGO = "def mediana(v):\n    s = sorted(v)\n    n = len(s)\n    return s[n // 2]\n"      # 4 líneas
SRC = comun.SISTEMA / "src"


def estados(citas):
    return [(c["cita"], c["estado"]) for c in citas]


class TestCitasDelProtocolo(unittest.TestCase):
    def test_citas_correctas(self):
        c = Q.verificar_texto("MEJORA: M1 | alta | par | EVIDENCIA: línea 4, caso U1 | EV6", CODIGO, {"U1"})
        self.assertEqual(estados(c), [("línea 4", "verificada"), ("caso U1", "verificada"), ("EV6", "verificada")])

    def test_citas_inventadas_se_rechazan(self):
        c = Q.verificar_texto("EVIDENCIA: línea 9 | caso Z9 | EV9 | líneas 2-7 | línea 0", CODIGO, {"U1"})
        self.assertEqual(estados(c), [("línea 9", "lineas_fuera_de_rango"), ("caso Z9", "caso_inexistente"),
                                      ("EV9", "hecho_inexistente"), ("líneas 2-7", "lineas_fuera_de_rango"),
                                      ("línea 0", "lineas_fuera_de_rango")])

    def test_texto_citado_debe_estar_en_esas_lineas(self):
        ok = Q.verificar_texto("la línea 2 contiene `s = sorted(v)`", CODIGO)
        mal = Q.verificar_texto("la línea 2 contiene `v.sort()`", CODIGO)
        self.assertEqual([c["estado"] for c in ok + mal], ["verificada", "texto_no_coincide"])

    def test_sin_version_nunca_cuenta_como_verificada(self):
        self.assertEqual(estados(Q.verificar_texto("EVIDENCIA: línea 1", None)), [("línea 1", "sin_base")])


class TestCitasDeCodigo(unittest.TestCase):
    def test_simbolos_rutas_y_confinamiento(self):
        texto = ("ver eq2/contexto.py::construir y eq2/contexto.py::Prompt.mensajes. También eq2/contexto.py:1-3; "
                 "eq2/contexto.py::inventada; eq2/nada.py:1; eq2/contexto.py:99999; ../../secreto.py:1; /etc/x.py:2")
        self.assertEqual(estados(Q.verificar_texto(texto, raiz=SRC)), [
            ("eq2/contexto.py::construir", "verificada"), ("eq2/contexto.py::Prompt.mensajes", "verificada"),
            ("eq2/contexto.py:1-3", "verificada"), ("eq2/contexto.py::inventada", "simbolo_inexistente"),
            ("eq2/nada.py:1", "archivo_inexistente"), ("eq2/contexto.py:99999", "lineas_fuera_de_rango"),
            ("../../secreto.py:1", "ruta_no_permitida"), ("/etc/x.py:2", "ruta_no_permitida")])

    def test_sin_raiz_no_se_verifica(self):
        self.assertEqual(estados(Q.verificar_texto("eq2/contexto.py:1")), [("eq2/contexto.py:1", "sin_base")])

    def test_simbolos_solo_por_ast(self):
        self.assertEqual(Q.simbolos("class A:\n    def b(self):\n        pass\n\ndef c():\n    pass\n"),
                         {"A", "A.b", "c"})
        self.assertEqual(Q.simbolos("def roto(:\n"), set())


class TestDeliberacionReal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._d = tempfile.TemporaryDirectory(prefix="eq3_q_", dir=os.environ.get("TMPDIR"))
        cls.origen = comun.demo(Path(cls._d.name) / "demo")

    @classmethod
    def tearDownClass(cls):
        cls._d.cleanup()

    def _informe(self, alterar=None):
        t = tempfile.TemporaryDirectory(prefix="eq3_qc_", dir=os.environ.get("TMPDIR"))
        self.addCleanup(t.cleanup)
        lab = Path(t.name) / "lab"
        shutil.copytree(self.origen, lab)
        with T.Traza(Path(t.name) / "traza.sqlite3") as traza:
            I.importar_tarea(traza, lab, "LAB-001")
            if alterar:
                alterar(lab)
            return Q.deliberacion(traza, lab, "LAB-001/E001")

    def test_informe_de_una_ejecucion_real(self):
        r = self._informe()
        self.assertEqual(set(r["por_agente"]), {"A1", "A2", "A3"})
        self.assertEqual(r["invalidas"], [])
        self.assertEqual(r["alterados"], [])
        self.assertEqual([p["version_visible"] for p in r["pasos"]], [None, 1, 1, 1, 2, 3, 3])
        self.assertEqual(r["objeciones"], {"abiertas": 1, "cerradas": 5, "total": 6})
        self.assertGreater(r["por_agente"]["A2"]["verificadas"], 0)

    def test_orden_de_linea_de_comandos(self):
        import json, sys
        t = tempfile.TemporaryDirectory(prefix="eq3_qcli_", dir=os.environ.get("TMPDIR"))
        self.addCleanup(t.cleanup)
        lab = Path(t.name) / "lab"
        shutil.copytree(self.origen, lab)
        cli = lambda *x: comun.plataforma.ejecutar([sys.executable, "-B", str(comun.RAIZ / "equipo3.py"), "traza",
                                                    "--lab", str(lab), *x], timeout=120, cwd=comun.RAIZ)
        self.assertEqual(cli("importar", "LAB-001").returncode, 0)
        r = cli("deliberacion", "LAB-001/E001", "--json")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(set(json.loads(r.stdout)["por_agente"]), {"A1", "A2", "A3"})
        (lab / "tareas/LAB-001/ejecuciones/E001/funcion/agentes/06_A2_fs_revisar.txt").write_text("x", encoding="utf-8")
        r = cli("deliberacion", "LAB-001/E001")
        self.assertEqual(r.returncode, 1)                                      # texto alterado: no es correcto
        self.assertIn("TEXTO ALTERADO paso 6", r.stdout)

    def test_texto_de_agente_alterado_no_se_analiza(self):
        def alterar(lab):
            f = lab / "tareas/LAB-001/ejecuciones/E001/funcion/agentes/02_A2_fs_revisar.txt"
            f.write_text("MEJORA: M9 | alta | inventada | EVIDENCIA: línea 99", encoding="utf-8")
        r = self._informe(alterar)
        self.assertEqual([x["n"] for x in r["alterados"]], [2])
        self.assertEqual(r["invalidas"], [])                   # la cita inventada no se cuenta como del agente
        self.assertNotIn(2, [p["n"] for p in r["pasos"]])


if __name__ == "__main__":
    unittest.main()
