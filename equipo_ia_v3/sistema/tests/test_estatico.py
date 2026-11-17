import ast
import subprocess  # solo en pruebas: ejecuta el validador estático, no el código de src
import sys
import unittest
from pathlib import Path
import _comun

RAIZ = _comun.RAIZ
sys.path.insert(0, str(RAIZ))
import validar_estatico as ve  # noqa: E402


class TestEstatico(unittest.TestCase):
    def test_src_limpio(self):
        for a in sorted((RAIZ / "src" / "eq2").glob("*.py")):
            self.assertEqual(ve.problemas_de(a), [], a.name)

    def test_el_validador_detecta_lo_prohibido(self):
        import tempfile
        malo = (
            "import subprocess\nimport os\nfrom urllib import request\n"
            "eval('1')\nos.system('ls')\nopen('f','w')\n"
            "def f(c, x):\n    c.execute(f'SELECT {x}')\n    c.execute('a' + x)\n"
            "    c.execute('x %s' % x)\n"
        )
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "malo.py"
            p.write_text(malo)
            pr = "\n".join(ve.problemas_de(p))
        for esperado in ("import prohibido subprocess", "import prohibido urllib",
                         "llamada prohibida eval", "os.system", "open() de escritura",
                         "SQL no literal en execute() (JoinedStr)", "(BinOp)"):
            self.assertIn(esperado, pr)

    def test_solo_rutas_py_puede_escribir_en_disco(self):
        import tempfile
        malo = ("import os\nfrom pathlib import Path\n"
                "os.open('f', 0)\nos.mkdir('d')\nos.rmdir('d')\nos.remove('f')\n"
                "Path('x').mkdir()\nPath('x').write_text('a')\n")
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "otro.py"
            p.write_text(malo)
            pr = "\n".join(ve.problemas_de(p))
            q = Path(d) / "rutas.py"
            q.write_text(malo)
            self.assertEqual(ve.problemas_de(q), [])      # rutas.py sí está autorizado
        for esperado in ("os.open() solo permitido en rutas.py", "os.mkdir()", "os.rmdir()",
                         "os.remove()", "escritura de archivo en otro.py"):
            self.assertIn(esperado, pr)
        for a in (RAIZ / "src" / "eq2").glob("*.py"):
            if a.name != "rutas.py":
                txt = a.read_text(encoding="utf-8")
                for prohibido in ("os.open(", "os.mkdir(", "os.makedirs(", "os.fdopen("):
                    self.assertNotIn(prohibido, txt, a.name)

    def test_menciona_equipo_ia_solo_en_config(self):
        for a in (RAIZ / "src" / "eq2").glob("*.py"):
            if a.name != "config.py":
                self.assertNotIn("equipo-ia", a.read_text(encoding="utf-8"), a.name)

    def test_el_unico_backend_es_simulado(self):
        arbol = ast.parse((RAIZ / "src" / "eq2" / "inferencia.py").read_text(encoding="utf-8"))
        clases = {n.name for n in ast.walk(arbol) if isinstance(n, ast.ClassDef)}
        self.assertEqual(clases, {"ErrorInferencia", "Respuesta", "BackendBase", "BackendSimulado"})

    def test_validador_como_proceso_sale_0(self):
        r = subprocess.run([sys.executable, "-B", "-I", str(RAIZ / "validar_estatico.py")],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_sin_bytecode_en_arbol(self):
        self.assertEqual(list(RAIZ.rglob("__pycache__")), [])


if __name__ == "__main__":
    unittest.main()
