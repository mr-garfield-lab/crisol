"""Pruebas del filtro de scripts de Blender (lab_blender/filtro.py). No lanzan Blender ni ejecutan ningún script."""
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "lab_blender"))
import filtro as F  # noqa: E402

BUENO = '''import bpy, bmesh
import math
from mathutils import Vector, Matrix
from math import pi, radians

def pieza(nombre, pos, mat=None):
    bpy.ops.mesh.primitive_cube_add(size=1, location=pos)
    ob = bpy.context.active_object
    ob.name = nombre
    if mat:
        ob.data.materials.append(mat)
    return ob

rojo = bpy.data.materials.new("Rojo")
rojo.use_nodes = True
torso = pieza("Torso", (0, 0, 2), rojo)
brazo = pieza("Brazo", (1, 0, 2))
brazo.parent = torso
brazo.matrix_parent_inverse = torso.matrix_world.inverted()
arm = bpy.data.armatures.new("Esqueleto")
rig = bpy.data.objects.new("Rig", arm)
bpy.context.scene.collection.objects.link(rig)
bm = bmesh.new()
bmesh.ops.create_cube(bm, size=1.0)
bm.free()
sc = bpy.context.scene
sc.frame_start, sc.frame_end = 1, 48
sc.render.fps = 24
torso.keyframe_insert(data_path="location", frame=1)
torso.location = Vector((0, -3, 2))
torso.keyframe_insert(data_path="location", frame=48)
bpy.ops.object.select_all(action="DESELECT")
with bpy.context.temp_override(active_object=torso):
    bpy.ops.object.shade_smooth()
nombres = sorted(o.name for o in bpy.data.objects if o.type == "MESH")
try:
    print(len(nombres), max(1, 2), round(pi, 2))
except (ValueError, RuntimeError) as e:
    print(e)
if __name__ == "__main__":
    print("fin")
'''

# (script, trozo que debe aparecer en algún motivo)
MALOS = [
    ("import os", "importa «os»"),
    ("import sys", "importa «sys»"),
    ("import subprocess", "importa"),
    ("import bpy.utils", "importa"),
    ("from bpy import ops", "from bpy import"),
    ("from os import system", "from os import"),
    ("from math import *", "import *"),
    ("from . import x", "no está permitido"),
    ("open('x', 'w')", "«open»"),
    ("eval('1')", "«eval»"),
    ("exec('x = 1')", "«exec»"),
    ("compile('1', 'a', 'eval')", "«compile»"),
    ("x = __import__('os')", "nombre interno"),
    ("import bpy\ngetattr(bpy, 'ops')", "«getattr»"),
    ("import bpy\nsetattr(bpy.context.scene, 'x', 1)", "«setattr»"),
    ("globals()", "«globals»"),
    ("vars()", "«vars»"),
    ("type(1)", "«type»"),
    ("().__class__", "atributo interno"),
    ("x = [].__class__.__base__", "atributo interno"),
    ("import bpy\nbpy._x", "atributo interno"),
    ("class A:\n    pass", "ClassDef"),
    ("async def f():\n    pass", "AsyncFunctionDef"),
    ("def d(f):\n    return f\n@d\ndef g():\n    pass", "decoradores"),
    # bpy.ops: solo grupos permitidos y sin alias
    ("import bpy\nbpy.ops.wm.save_as_mainfile()", "bpy.ops.wm"),
    ("import bpy\nbpy.ops.wm.quit_blender()", "bpy.ops.wm"),
    ("import bpy\nbpy.ops.script.python_file_run()", "bpy.ops.script"),
    ("import bpy\nbpy.ops.render.render()", "bpy.ops.render"),
    ("import bpy\nbpy.ops.export_scene.fbx()", "bpy.ops.export_scene"),
    ("import bpy\nbpy.ops.file.pack_all()", "bpy.ops.file"),
    ("import bpy\nbpy.ops.preferences.addon_enable()", "bpy.ops.preferences"),
    ("import bpy\no = bpy.ops\no.wm.quit_blender()", "guarda o pasa «bpy.ops»"),
    ("import bpy\nm = bpy.ops.mesh\nm.primitive_cube_add()", "guarda o pasa «bpy.ops.mesh»"),
    ("import bpy\nprint(bpy.ops)", "guarda o pasa «bpy.ops»"),
    ("import bpy\nx = bpy\nx.ops.mesh.primitive_cube_add()", "no es directamente el módulo bpy"),
    ("import bpy\nbpy.context.ops.mesh.x()", "no es directamente el módulo bpy"),
    ("import bpy as b\nb.ops.wm.quit_blender()", "bpy.ops.wm"),
    ("import bpy\nbpy.ops.object.bake(type='DIFFUSE')", "bpy.ops.object.bake"),
    ("import bpy\nbpy.ops.object.multires_external_save()", "multires_external_save"),
    ("import bpy\nbpy.ops.collection.exporter_add(name='x')", "exporter_add"),
    ("import bpy\nbpy.ops.uv.export_layout()", "export_layout"),
    ("import bpy\nbpy.ops.object.empty_image_add()", "empty_image_add"),
    ("import bpy\nbpy.ops.mesh.primitive_cube_add(**{'size': 1})", "**"),
    ("import bpy\nbpy = 3", "reasigna el módulo"),
    ("import bpy\ndef f(bpy):\n    pass", "como parámetro"),
    ("import bmesh\nfor bmesh in [1]:\n    pass", "reasigna el módulo"),
    # archivos, código y preferencias
    ("import bpy\nbpy.data.libraries.write('a', set())", ".libraries"),
    ("import bpy\nbpy.data.texts.new('a')", ".texts"),
    ("import bpy\nbpy.data.images.load('a')", ".load"),
    ("import bpy\nim = bpy.data.images.new('a', 4, 4)\nim.save()", ".save"),
    ("import bpy\nbpy.app.handlers.frame_change_pre.append(print)", ".app"),
    ("import bpy\nbpy.utils.register_class(1)", ".utils"),
    ("import bpy\nbpy.types.Scene.x = 1", ".types"),
    ("import bpy\nbpy.context.preferences.view.x = 1", ".preferences"),
    ("import bpy\nbpy.path.abspath('a')", ".path"),
    ("import bpy\nfc = 1\nfc.driver.expression = 'x'", ".driver"),
    ("import bpy\nbpy.context.object.driver_add('location')", ".driver_add"),
    ("import bpy\nbpy.context.scene.render.filepath = 'salida'", "escribe en «.filepath»"),
    ("import bpy\nx = 1\nx.cache_directory = 'a'", "escribe en «.cache_directory»"),
    ("import bpy\nx = 1\nx.use_disk_cache = True", "escribe en «.use_disk_cache»"),
    ("import bpy\nbpy.ops.mesh.primitive_cube_add(filepath='a')", "argumento «filepath»"),
    ("f(directory='a')\ndef f(directory=1):\n    pass", "argumento «directory»"),
    ("x = 'C:/Windows/a'", "ruta absoluta"),
    ("x = 'a/../b'", "ruta absoluta"),
    ("x = '{0.__class__}'", "«__»"),
    ("x = b'abc'", "literal de bytes"),
    ("import bpy\nob = 1\nob.modifiers.new('a', 'FLUID')", "FLUID"),
    ("import math\nmath.degrees = len", "modifica el módulo «math»"),
    ("import bpy\nbpy.context = None", "modifica el módulo «bpy»"),
    ("import bpy\ndel bpy.data", "modifica el módulo «bpy»"),
    ("import bpy\nbpy.context.scene.sequence_editor_create()", ".sequence_editor_create"),
    # marcos de ejecución
    ("def g():\n    yield 1\nx = g()\nx.gi_frame", "marcos de ejecución"),
    ("def g():\n    yield 1\nx = g().gi_frame.f_back", "marcos de ejecución"),
    ("x = 1\nx.f_globals", "marcos de ejecución"),
    ("x = 1\nx.tb_frame", "marcos de ejecución"),
    ("def f():\n    pass\nf.co_consts", "marcos de ejecución"),
    ("try:\n    1 / 0\nexcept Exception as e:\n    e.with_traceback(None)", "marcos de ejecución"),
    # forma
    ("def f(:\n  pass", "no es Python válido"),
    ("x = 1\x00", "bytes nulos"),
]


class Filtro(unittest.TestCase):
    def test_script_normal_pasa(self):
        self.assertEqual(F.revisar(BUENO), [])
        self.assertTrue(F.pasa(BUENO))

    def test_scripts_peligrosos_se_rechazan(self):
        for texto, trozo in MALOS:
            with self.subTest(texto=texto):
                motivos = F.revisar(texto)
                self.assertTrue(motivos, "debería rechazarse")
                self.assertTrue(any(trozo in m for m in motivos), motivos)

    def test_cada_motivo_lleva_la_linea(self):
        m = F.revisar("import bpy\n\nimport os\nopen('a')")
        self.assertEqual([x.split(":")[0] for x in m], ["línea 3", "línea 4"])

    def test_limites_de_tamano(self):
        self.assertIn("bytes", F.revisar("x = 1\n" + "#" * (F.MAX_BYTES + 10))[0])
        self.assertIn("líneas", F.revisar("x = 1\n" * (F.MAX_LINEAS + 5))[0])

    def test_datos_que_si_se_permiten(self):
        for texto in ("import bpy\nob = bpy.context.object\nob.keyframe_insert(data_path='location', frame=1)",
                      "import bpy\nbpy.context.scene.render.resolution_x = 640",
                      "import bpy\nbpy.ops.object.text_add()",
                      "import bmesh\nbm = bmesh.new()\nbmesh.ops.create_cone(bm, segments=8)",
                      "import random\nrandom.seed(1)\nx = [random.random() for _ in range(3)]",
                      "x = {'a': 1}\nfor k, v in x.items():\n    print(k, v)",
                      "import bpy\nc = bpy.data.curves.new('c', 'CURVE')\nc.path_duration = 48",
                      "f = lambda a, b=2: a + b\nprint(f(1))"):
            with self.subTest(texto=texto):
                self.assertEqual(F.revisar(texto), [])

    def test_las_listas_no_incluyen_nada_peligroso(self):
        for nombre in ("open", "eval", "exec", "compile", "getattr", "setattr", "delattr", "globals", "locals", "vars",
                       "dir", "type", "object", "super", "input", "breakpoint", "memoryview", "__import__", "help", "exit"):
            self.assertNotIn(nombre, F.INTEGRADAS)
        self.assertEqual(F.MODULOS, {"bpy", "bmesh", "mathutils", "math", "random"})
        for grupo in ("wm", "script", "render", "file", "preferences", "image", "text", "export_scene", "import_scene",
                      "sound", "screen", "ui", "outliner"):
            self.assertNotIn(grupo, F.OPS)


if __name__ == "__main__":
    unittest.main()
