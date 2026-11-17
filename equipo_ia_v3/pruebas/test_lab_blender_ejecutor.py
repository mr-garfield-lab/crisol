"""Pruebas del ejecutor de Blender (lab_blender/ejecutor.py). Las REALES lanzan el Blender instalado, sin ventana y sin
render (unos segundos cada una); si no hay Blender se OMITEN. Los scripts que se ejecutan son los de este archivo."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "lab_blender"))
import ejecutor as E  # noqa: E402

EXE = E.blender_exe()
TRES_CUBOS = '''import bpy
for i in range(3):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(2 * i, 0, 0.5))
    bpy.context.active_object.name = f"Cubo_{i}"
m = bpy.data.materials.new("Rojo")
m.diffuse_color = (1, 0, 0, 1)
bpy.data.objects["Cubo_0"].data.materials.append(m)
sc = bpy.context.scene
sc.frame_start, sc.frame_end = 1, 20
ob = bpy.data.objects["Cubo_2"]
ob.keyframe_insert(data_path="location", frame=1)
ob.location.z = 3.0
ob.keyframe_insert(data_path="location", frame=20)
print("hecho", len(bpy.data.objects))
'''


class SinBlender(unittest.TestCase):
    """No lanzan Blender."""

    def test_rechazado_no_lanza_blender(self):
        with tempfile.TemporaryDirectory() as d:
            r = E.ejecutar("import os\nos.system('echo hola')", Path(d) / "s", exe=Path(d) / "no_existe.exe")
            self.assertEqual((r["estado"], r["blender_lanzado"], r["filtro"]["pasa"]), ("RECHAZADO", False, False))
            self.assertTrue((Path(d) / "s" / "resultado.json").is_file())
            self.assertEqual(sorted(p.name for p in (Path(d) / "s").iterdir()), ["resultado.json", "script_cerebro.py"])

    def test_sin_blender_no_se_finge(self):
        with tempfile.TemporaryDirectory() as d:
            r = E.ejecutar("x = 1", Path(d) / "s", exe=Path(d) / "no_existe.exe")
            self.assertEqual((r["estado"], r["blender_lanzado"]), ("FALLO_BLENDER", False))

    def test_la_carpeta_de_salida_tiene_que_ser_nueva(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(FileExistsError):
                E.ejecutar("x = 1", d)

    def test_base_que_no_es_blend(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "a.txt").write_text("x", encoding="utf-8")
            r = E.ejecutar("x = 1", Path(d) / "s", base=Path(d) / "a.txt", exe=sys.executable)
            self.assertEqual((r["estado"], r["blender_lanzado"]), ("FALLO_BLENDER", False))


class TerceraBarrera(unittest.TestCase):
    """Aunque un script saltara los dos filtros, dentro solo existen las funciones y módulos de la lista cerrada.
    SIMULADO: se carga dentro_blender.py con módulos bpy y mathutils vacíos (aquí no hay Blender)."""

    @classmethod
    def setUpClass(cls):
        import types
        cls.puestos = [n for n in ("bpy", "mathutils") if n not in sys.modules]
        for n in cls.puestos:
            sys.modules[n] = types.ModuleType(n)
        sys.modules["mathutils"].Vector = tuple
        import dentro_blender
        cls.D = dentro_blender

    @classmethod
    def tearDownClass(cls):
        for n in cls.puestos + ["dentro_blender"]:
            sys.modules.pop(n, None)

    def test_importar_fuera_de_la_lista_falla(self):
        for texto in ("import os", "import sys", "import subprocess", "from os import path", "import bpy.utils"):
            r = self.D.ejecutar_script(texto, E.filtro)
            self.assertFalse(r["ok"], texto)
            self.assertIn("ImportError", r["error"])

    def test_funciones_fuera_de_la_lista_no_existen(self):
        for texto in ("open('a')", "eval('1')", "exec('x=1')", "getattr(1, 'real')", "globals()", "type(1)",
                      "class A:\n    pass", "__import__('os')"):
            r = self.D.ejecutar_script(texto, E.filtro)
            self.assertFalse(r["ok"], texto)
            self.assertRegex(r["error"], "NameError|ImportError")

    def test_lo_permitido_funciona_y_se_recoge_la_salida(self):
        r = self.D.ejecutar_script("import math\nprint('a', round(math.pi, 2))\nprint(len([1, 2]))", E.filtro)
        self.assertEqual((r["ok"], r["salida"]), (True, "a 3.14\n2\n"))

    def test_error_con_linea(self):
        r = self.D.ejecutar_script("x = 1\ny = x / 0\n", E.filtro)
        self.assertEqual((r["ok"], r["linea"], r["codigo_de_la_linea"]), (False, 2, "y = x / 0"))

    def test_salir_del_script_no_tumba_el_informe(self):
        r = self.D.ejecutar_script("raise SystemExit(5)", E.filtro)
        self.assertFalse(r["ok"])


@unittest.skipUnless(EXE, "OMITIDO: no hay Blender instalado")
class ConBlender(unittest.TestCase):
    """REALES: lanzan Blender sin ventana. Sin render (no usan la GPU)."""

    def correr(self, texto, **kw):
        d = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)   # tras cortar Blender, Windows tarda en soltar archivos
        self.addCleanup(d.cleanup)
        return E.ejecutar(texto, Path(d.name) / "s", **kw), Path(d.name) / "s"

    def test_script_correcto_da_hechos(self):
        r, s = self.correr(TRES_CUBOS)
        self.assertEqual(r["estado"], "OK", r.get("error") or r["informe"])
        inf = r["informe"]
        self.assertEqual((inf["de_fabrica"], inf["scripts_automaticos"], inf["con_red"]), (True, False, False))
        self.assertEqual(inf["script"]["salida"].strip(), "hecho 3")
        esc = inf["escena"]
        self.assertEqual((esc["n_objetos"], esc["por_tipo"]), (3, {"MESH": 3}))
        cubo = {o["nombre"]: o for o in esc["objetos"]}
        self.assertEqual(cubo["Cubo_1"]["posicion"], [2.0, 0.0, 0.5])
        self.assertEqual(cubo["Cubo_1"]["dimensiones"], [1.0, 1.0, 1.0])
        self.assertEqual(cubo["Cubo_0"]["colores"][0]["vista"], [1.0, 0.0, 0.0, 1.0])
        self.assertEqual(esc["objetos_que_se_mueven"], ["Cubo_2"])
        self.assertEqual(cubo["Cubo_2"]["muestras"][-1]["posicion"][2], 3.0)
        self.assertTrue((s / "resultado.blend").is_file())
        self.assertEqual(json.loads((s / "resultado.json").read_text(encoding="utf-8"))["estado"], "OK")

    def test_error_del_script_con_su_linea(self):
        r, _ = self.correr("import bpy\nx = 1\nbpy.data.objects['NoExiste'].location.x = 2\n")
        self.assertEqual(r["estado"], "ERROR_SCRIPT")
        sc = r["informe"]["script"]
        self.assertEqual(sc["linea"], 3)
        self.assertIn("KeyError", sc["error"])
        self.assertIn("NoExiste", sc["codigo_de_la_linea"])

    def test_bucle_infinito_se_corta_por_tiempo(self):
        r, _ = self.correr("x = 0\nwhile True:\n    x += 1\n", tiempo_s=8)
        self.assertEqual(r["estado"], "TIEMPO")
        self.assertEqual(r["fase_al_cortar"], "ejecutando")
        self.assertLess(r["segundos"], 20)

    def test_consumo_de_memoria_se_corta(self):
        r, _ = self.correr("x = []\nwhile True:\n    x.append([0.5] * 200000)\n", tiempo_s=60, memoria_max_mb=1500)
        self.assertEqual(r["estado"], "MEMORIA")

    def test_segunda_barrera_el_filtro_se_repite_dentro_de_blender(self):
        # se anula SOLO el filtro de fuera (en esta prueba): Blender arranca, pero el filtro de dentro lo rechaza sin ejecutar
        from unittest import mock
        with mock.patch.object(E.filtro, "revisar", return_value=[]):
            r, s = self.correr("import os\nprint(os.getcwd())\n")
        self.assertEqual((r["estado"], r["blender_lanzado"]), ("RECHAZADO", True))
        self.assertEqual(r["informe"]["fase"], "rechazado_dentro")
        self.assertNotIn("script", r["informe"])
        self.assertIn("importa «os»", " ".join(r["filtro"]["motivos"]))
        self.assertFalse((s / "resultado.blend").exists())

    def test_trabaja_sobre_una_copia_del_blend(self):
        _, s0 = self.correr(TRES_CUBOS)
        base = s0 / "resultado.blend"
        antes = E.huella(base)
        r, s = self.correr("import bpy\nbpy.data.objects['Cubo_1'].location.z = 9\nbpy.data.objects.remove(bpy.data.objects['Cubo_0'])\n",
                           base=base)
        self.assertEqual(r["estado"], "OK", r.get("error"))
        self.assertTrue(r["base"]["intacta"])
        self.assertEqual(E.huella(base), antes)
        nombres = {o["nombre"]: o for o in r["informe"]["escena"]["objetos"]}
        self.assertEqual(sorted(nombres), ["Cubo_1", "Cubo_2"])
        self.assertEqual(nombres["Cubo_1"]["posicion"][2], 9.0)
        self.assertTrue((s / "entrada.blend").is_file())

    def test_modificador_que_escribe_en_disco_no_se_mide(self):
        # el nombre se compone por trozos para saltar el filtro de texto: lo detiene la comprobación de dentro
        r, _ = self.correr("import bpy\nbpy.ops.mesh.primitive_cube_add()\n"
                           "bpy.context.active_object.modifiers.new('x', 'OCE' + 'AN')\n")
        self.assertEqual(r["estado"], "LIMITE")
        self.assertIn("OCEAN", " ".join(r["informe"]["escena"]["limites_superados"]))

    def test_limite_de_objetos(self):
        r, _ = self.correr("import bpy\nfor i in range(12):\n    bpy.data.objects.new(f'E{i}', None)\n"
                           "for o in bpy.data.objects:\n    bpy.context.scene.collection.objects.link(o)\n",
                           limites={"objetos": 10, "vertices": 1000})
        self.assertEqual(r["estado"], "LIMITE")


if __name__ == "__main__":
    unittest.main()
