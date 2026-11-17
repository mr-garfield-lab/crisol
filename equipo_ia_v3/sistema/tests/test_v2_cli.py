"""ejecutar_v2.py (como proceso) y modelo.py. Sin servidor: nada de esto arranca llama-server."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import _comun
from eq2 import config, modelo

RUN = str(_comun.RAIZ / "ejecutar_v2.py")


class TestCLI(unittest.TestCase):
    def setUp(self):
        self.t = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, self.t, True)
        self.env = dict(os.environ, HOME=str(self.t / "home"), TMPDIR=str(self.t / "tmp"))
        (self.t / "home").mkdir()
        (self.t / "tmp").mkdir()

    def ejecutar(self, *a):
        return subprocess.run([sys.executable, "-B", "-I", RUN, *a], capture_output=True, text=True,
                              timeout=60, env=self.env)

    def test_una_llamada_exige_confirmacion_explicita(self):
        r = self.ejecutar("--modo", "una_llamada")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--iniciar-servidor-real", r.stderr + r.stdout)
        self.assertEqual(list((self.t / "tmp").iterdir()), [])         # no escribió nada

    def test_comprobar_no_escribe_ni_arranca(self):
        r = self.ejecutar("--modo", "comprobar", "--sin-help")
        self.assertIn("NO APTO", r.stdout)                              # no hay modelo en el HOME falso
        self.assertEqual(r.returncode, 1)
        self.assertEqual(list((self.t / "tmp").iterdir()), [])
        self.assertEqual(list((self.t / "home").iterdir()), [])

    def test_puerto_fuera_de_rango(self):
        self.assertNotEqual(self.ejecutar("--modo", "comprobar", "--puerto", "80").returncode, 0)


class TestModelo(unittest.TestCase):
    def setUp(self):
        self.t = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, self.t, True)

    def test_huella_solo_lectura(self):
        m = self.t / "m.gguf"
        m.write_bytes(b"GGUF" + os.urandom(3 << 20))
        antes = (m.read_bytes(), os.stat(m).st_mtime_ns)
        h = modelo.huella_modelo(m)
        self.assertEqual(h["magic"], "GGUF")
        self.assertTrue(modelo.mismo_modelo(h, modelo.huella_modelo(m)))
        self.assertEqual((m.read_bytes(), os.stat(m).st_mtime_ns), antes)

    def test_cambio_detectado_y_enlace_rechazado(self):
        m = self.t / "m.gguf"
        m.write_bytes(b"GGUF" + b"a" * 100)
        h = modelo.huella_modelo(m)
        m.write_bytes(b"GGUF" + b"b" * 100)
        self.assertFalse(modelo.mismo_modelo(h, modelo.huella_modelo(m)))
        e = self.t / "enlace.gguf"
        e.symlink_to(m)
        self.assertIn("error", modelo.huella_modelo(e))
        self.assertTrue(modelo.problemas_modelo(modelo.huella_modelo(e)))

    def test_ausente_y_no_gguf(self):
        self.assertTrue(modelo.problemas_modelo(modelo.huella_modelo(self.t / "no.gguf")))
        f = self.t / "x.gguf"
        f.write_bytes(b"XXXX" * 10)
        self.assertTrue(modelo.problemas_modelo(modelo.huella_modelo(f)))


if __name__ == "__main__":
    unittest.main()
