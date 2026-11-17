"""Pruebas de la reanudación del verificador integral (V3.1, mantenimiento): `verificar_v3.py --reanudar`.

Fases FALSAS pero ejecutadas de verdad (procesos hijo de Python de una línea), un árbol de archivos temporal en lugar
del proyecto y `integridad_sistema` sustituida: así cada prueba tarda segundos y puede cambiar código y entorno.
"""
import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
import verificar_v3 as V  # noqa: E402

PY = sys.executable


def _fase(fid, codigo):
    return (fid, f"fase falsa {fid}", "REAL", [PY, "-B", "-c", codigo])


class TestReanudar(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory(prefix="eq3_rea_", dir=os.environ.get("TMPDIR"))
        self.addCleanup(d.cleanup)
        self.t = Path(d.name)
        self.arbol = self.t / "arbol"
        (self.arbol / "eq3").mkdir(parents=True)
        (self.arbol / "eq3" / "m.py").write_text("x = 1\n", encoding="utf-8")
        (self.arbol / "datos.json").write_text("{}", encoding="utf-8")
        self.marca = self.t / "fallar_fc"                                     # si existe, FC falla
        self.marca.write_text("1", encoding="utf-8")
        self.fases = [_fase("FA", "print('a ok')"), _fase("FB", "print('b ok')"),
                      _fase("FC", f"import os, sys; sys.exit(1 if os.path.exists({str(self.marca)!r}) else 0)")]
        self.ejecutadas = []
        real = V.plataforma.ejecutar

        def ejecutar(orden, **kw):
            self.ejecutadas.append(orden[-1] if orden[-2] == "-c" else orden)
            return real(orden, **kw)
        self.entorno = {}
        for p in (mock.patch.object(V, "FASES", self.fases),
                  mock.patch.object(V, "integridad_sistema", lambda: (True, "integridad simulada")),
                  mock.patch.object(V, "archivos_huella", self._archivos),
                  mock.patch.object(V.plataforma, "ejecutar", ejecutar),
                  mock.patch.dict(os.environ, {"TMPDIR": str(self.t / "tmp")})):
            p.start()
            self.addCleanup(p.stop)

    def _archivos(self):
        return {p.relative_to(self.arbol).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(self.arbol.rglob("*")) if p.is_file()}

    def _ejecucion(self, *argv):
        """(código de salida, carpeta de la ejecución, informe)."""
        self.ejecutadas.clear()
        antes = set((self.t / "tmp" / "eq3_verificacion").glob("*")) if (self.t / "tmp" / "eq3_verificacion").exists() else set()
        with mock.patch("builtins.print"):
            rc = V.main(list(argv))
        nuevas = set((self.t / "tmp" / "eq3_verificacion").glob("*")) - antes
        (carpeta,) = nuevas
        inf = carpeta / "informe.json"
        return rc, carpeta, json.loads(inf.read_text(encoding="utf-8")) if inf.is_file() else None

    def _main(self, *argv):
        """Ejecuta el verificador sin crear informe esperado; devuelve (código, todo lo impreso)."""
        self.ejecutadas.clear()
        with mock.patch("builtins.print") as p:
            rc = V.main(list(argv))
        return rc, " ".join(str(a) for c in p.call_args_list for a in c.args)

    def _ids_ejecutadas(self):
        return sorted({"FA" if "a ok" in o else "FB" if "b ok" in o else "FC" for o in self.ejecutadas})

    def test_reutiliza_solo_las_correctas_y_repite_las_fallidas(self):
        rc, primera, inf = self._ejecucion()
        self.assertEqual((rc, inf["fallidas"]), (1, ["FC"]))
        self.marca.unlink()                                                   # el fallo era del ENTORNO de FC…
        # …pero la marca está fuera del árbol: el código es idéntico y se puede reanudar.
        rc, segunda, inf = self._ejecucion("--reanudar", str(primera))
        self.assertEqual(rc, 0)
        self.assertEqual(self._ids_ejecutadas(), ["FC"])                      # FA y FB no se repiten
        por_id = {r["id"]: r for r in inf["resultados"]}
        self.assertEqual((por_id["FA"]["reutilizada_de"], por_id["FB"]["reutilizada_de"]),
                         (primera.name, primera.name))
        self.assertNotIn("reutilizada_de", por_id["FC"])
        self.assertNotIn("reutilizada_de", por_id["F0"])                       # F0 siempre se repite
        self.assertEqual(inf["reanuda"], primera.name)
        # Una tercera reanudación sobre la segunda conserva el origen REAL de cada resultado.
        rc, _, inf = self._ejecucion("--reanudar", str(segunda))
        self.assertEqual((rc, self._ids_ejecutadas()), (0, []))
        por_id = {r["id"]: r for r in inf["resultados"]}
        self.assertEqual((por_id["FA"]["reutilizada_de"], por_id["FC"]["reutilizada_de"]),
                         (primera.name, segunda.name))

    def test_codigo_cambiado_no_reutiliza_nada(self):
        self.marca.unlink()
        rc, primera, _ = self._ejecucion()
        self.assertEqual(rc, 0)
        for cambio in ("modificado", "añadido", "eliminado"):
            with self.subTest(cambio):
                arbol_antes = self._archivos()
                if cambio == "modificado":
                    (self.arbol / "eq3" / "m.py").write_text("x = 2\n", encoding="utf-8")
                elif cambio == "añadido":
                    (self.arbol / "nuevo.py").write_text("", encoding="utf-8")
                else:
                    (self.arbol / "datos.json").unlink()
                rc, salida = self._main("--reanudar", str(primera))

                self.assertEqual(rc, 2)
                self.assertIn("REANUDACIÓN RECHAZADA", salida)
                self.assertIn(cambio, salida)
                self.assertEqual(self.ejecutadas, [])                         # no se ejecutó ninguna fase
                self.assertNotEqual(self._archivos(), arbol_antes)

    def test_entorno_cambiado_no_reutiliza_nada(self):
        self.marca.unlink()
        rc, primera, _ = self._ejecucion()
        original = V.huella_entorno
        for clave, valor in (("python", "3.99.0 (otra)"), ("enlaces_a_archivos", "cambiado"),
                             ("entorno_hijo", {"PATH": "otro"})):
            with self.subTest(clave), mock.patch.object(
                    V, "huella_entorno", lambda base, c=clave, v=valor: {**original(base), c: v}):
                rc, salida = self._main("--reanudar", str(primera))
                self.assertEqual(rc, 2)
                self.assertIn(f"entorno.{clave}", salida)
                self.assertEqual(self.ejecutadas, [])

    def test_codigo_4_de_inestables_solo_vale_en_F11_queda_marcado_y_no_se_reutiliza(self):
        # X1: la línea base sale con 4 si solo hay pruebas inestables declaradas y confirmadas.
        cuatro = "import sys; sys.exit(4)"
        with mock.patch.object(V, "FASES", [_fase("F11", cuatro), _fase("FD", cuatro)]):
            rc, _, inf = self._ejecucion()
        por_id = {r["id"]: r for r in inf["resultados"]}
        self.assertEqual((rc, por_id["F11"]["estado"], por_id["FD"]["estado"]), (1, "OK", "FALLO"))
        self.assertTrue(por_id["F11"]["con_inestables"])
        self.assertEqual(inf["estado_general"], "CON FALLOS")
        with mock.patch.object(V, "FASES", [_fase("F11", cuatro), _fase("FA", "print('a ok')")]):
            rc, primera, inf = self._ejecucion()
            self.assertEqual((rc, inf["fases_con_inestables"]), (0, ["F11"]))
            self.assertEqual(inf["estado_general"], "CORRECTO CON PRUEBAS INESTABLES CONFIRMADAS (F11)")
            rc, _, inf = self._ejecucion("--reanudar", str(primera))
        por_id = {r["id"]: r for r in inf["resultados"]}
        self.assertNotIn("reutilizada_de", por_id["F11"])                     # se vuelve a medir
        self.assertIn("reutilizada_de", por_id["FA"])
        self.assertTrue(por_id["F11"]["con_inestables"])

    def test_orden_de_una_fase_cambiada_se_repite(self):
        self.marca.unlink()
        _, primera, _ = self._ejecucion()
        self.fases[1] = ("FB", "fase falsa FB", "REAL", [PY, "-B", "-X", "utf8", "-c", "print('b ok')"])
        rc, _, inf = self._ejecucion("--reanudar", str(primera))
        self.assertEqual((rc, self._ids_ejecutadas()), (0, ["FB"]))
        self.assertNotIn("reutilizada_de", {r["id"]: r for r in inf["resultados"]}["FB"])

    def test_progreso_ilegible_o_ausente_se_rechaza(self):
        self.marca.unlink()
        _, primera, _ = self._ejecucion()
        vacia = self.t / "vacia"
        vacia.mkdir()
        (self.t / "rota").mkdir()
        (self.t / "rota" / V.PROGRESO).write_text("{no es json", encoding="utf-8")
        (self.t / "otra").mkdir()
        (self.t / "otra" / V.PROGRESO).write_text(json.dumps({"version": 99, "fases": {}, "huella": {}}), encoding="utf-8")
        for carpeta in (vacia, self.t / "rota", self.t / "otra", self.t / "no_existe"):
            with self.subTest(carpeta=carpeta.name):
                self.assertEqual(self._main("--reanudar", str(carpeta))[0], 2)
                self.assertEqual(self.ejecutadas, [])

    def test_progreso_manipulado_no_se_acepta(self):
        # Cambiar a mano la huella guardada para que «coincida» no sirve: se compara archivo por archivo.
        self.marca.unlink()
        _, primera, _ = self._ejecucion()
        (self.arbol / "eq3" / "m.py").write_text("x = 3\n", encoding="utf-8")
        prog = json.loads((primera / V.PROGRESO).read_text(encoding="utf-8"))
        prog["huella"]["archivos_sha256"] = V.huella(self.t)["archivos_sha256"]
        (primera / V.PROGRESO).write_text(json.dumps(prog), encoding="utf-8")
        self.assertEqual(self._main("--reanudar", str(primera))[0], 2)
        self.assertEqual(self.ejecutadas, [])

    def test_cambio_durante_la_ejecucion_invalida_el_resultado(self):
        self.marca.unlink()
        destino = self.arbol / "eq3" / "m.py"
        self.fases[1] = _fase("FB", f"open({str(destino)!r}, 'w').write('x = 9\\n'); print('b ok')")
        rc, carpeta, inf = self._ejecucion()
        self.assertEqual(rc, 1)
        self.assertIn("HUELLA", inf["fallidas"])
        self.assertIn("eq3/m.py", {r["id"]: r for r in inf["resultados"]}["HUELLA"]["detalle"])
        destino.write_text("x = 1\n", encoding="utf-8")                      # aunque el archivo vuelva a su estado
        rc, salida = self._main("--reanudar", str(carpeta))
        self.assertEqual(rc, 2)                                              # …esa ejecución ya no vale
        self.assertIn("INVÁLIDA", salida)
        self.assertEqual(self.ejecutadas, [])

    def test_ejecucion_interrumpida_se_puede_reanudar(self):
        # Tras cada fase queda un progreso completo y legible: es lo que permite reanudar tras un corte.
        self.marca.unlink()
        _, primera, _ = self._ejecucion()
        prog = json.loads((primera / V.PROGRESO).read_text(encoding="utf-8"))
        del prog["fases"]["FC"]                                              # como si se hubiera cortado en FC
        (primera / V.PROGRESO).write_text(json.dumps(prog), encoding="utf-8")
        self.assertFalse((primera / (V.PROGRESO + ".tmp")).exists())
        rc, _, _ = self._ejecucion("--reanudar", str(primera))
        self.assertEqual((rc, self._ids_ejecutadas()), (0, ["FC"]))


class TestHuellaReal(unittest.TestCase):
    def test_huella_del_proyecto(self):
        h = V.archivos_huella()
        self.assertIn("equipo_ia_v3/verificar_v3.py", h)
        self.assertIn("equipo_ia_v3/sistema/src/eq2/backend_llama.py", h)
        self.assertFalse([n for n in h if "/__pycache__/" in n or n.startswith(".git/") or n.endswith(".pyc")])
        self.assertEqual(h, V.archivos_huella())                             # estable


if __name__ == "__main__":
    unittest.main()
