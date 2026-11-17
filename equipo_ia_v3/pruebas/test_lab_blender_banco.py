"""Pruebas del verificador y del banco de Blender. El cerebro y Blender son SIMULADOS aquí, salvo una prueba REAL con la
solución de referencia de T01 (se OMITE si no hay Blender)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "lab_blender"))
import banco as B  # noqa: E402
import ejecutor as E  # noqa: E402
import tareas as T  # noqa: E402
import verificador as V  # noqa: E402


def objeto(nombre, centro, medidas, tipo="MESH", padre=None, color=None, muestras=None):
    mn = [c - m / 2 for c, m in zip(centro, medidas)]
    mx = [c + m / 2 for c, m in zip(centro, medidas)]
    o = {"nombre": nombre, "tipo": tipo, "posicion": list(centro), "rotacion_grados": [0, 0, 0], "caja_min": mn,
         "caja_max": mx, "padre": padre, "colores": [{"nodos": color, "vista": [0.8, 0.8, 0.8, 1]}] if color else []}
    if muestras:
        o["muestras"] = [{"fotograma": f, "posicion": list(c), "rotacion_grados": list(r),
                          "caja_min": [a - m / 2 for a, m in zip(c, medidas)],
                          "caja_max": [a + m / 2 for a, m in zip(c, medidas)]} for f, c, r in muestras]
    return o


def resultado(objetos, ini=1, fin=250, fps=24.0, estado="OK"):
    return {"estado": estado, "limites": {"tiempo_s": 90}, "filtro": {"motivos": []},
            "informe": {"escena": {"objetos": objetos, "fotograma_inicial": ini, "fotograma_final": fin, "fps": fps,
                                   "limites_superados": []}, "script": {"ok": True}}}


class Verificador(unittest.TestCase):
    def test_t01_correcta_y_con_fallos(self):
        t = T.TAREAS["T01"]
        self.assertTrue(V.verificar(t, resultado([objeto("Caja", (0, 0, 1), (2, 2, 2))]))["aprobado"])
        v = V.verificar(t, resultado([objeto("Caja", (0, 0, 2), (2, 2, 1))]))
        self.assertFalse(v["aprobado"])
        self.assertEqual((v["cumplidas"], v["total"]), (1, 4))
        self.assertIn("mide (2.00, 2.00, 1.00)", v["texto"])
        v = V.verificar(t, resultado([objeto("Cubo", (0, 0, 1), (2, 2, 2))]))
        self.assertIn("no existe ningún objeto llamado «Caja»", v["texto"])
        self.assertEqual(v["texto"].count("no existe"), 1)              # el mismo aviso no se repite

    def test_contacto_padre_y_color(self):
        torso = objeto("Torso", (0, 0, 2.0), (1.0, 0.6, 1.2))
        ok = V.verificar(T.TAREAS["T04"], resultado([torso, objeto("Cabeza", (0, 0, 2.85), (0.5, 0.5, 0.5), padre="Torso")]))
        self.assertTrue(ok["aprobado"], ok["texto"])
        flota = V.verificar(T.TAREAS["T04"], resultado([torso, objeto("Cabeza", (0, 0, 3.2), (0.5, 0.5, 0.5))]))
        self.assertIn("separados 0.35 m", flota["texto"])
        self.assertIn("no cuelga de «Torso»", flota["texto"])
        bola = objeto("Bola", (0, 0, 1), (2, 2, 2), color=[0.8, 0.8, 0.8, 1])
        self.assertIn("color de render", V.verificar(T.TAREAS["T03"], resultado([bola]))["texto"])
        sin = dict(bola, colores=[{"nodos": None, "vista": [1, 0, 0, 1]}])
        self.assertIn("vista 3D", V.verificar(T.TAREAS["T03"], resultado([sin]))["texto"])

    def test_movimiento_giro_y_alternancia(self):
        m = [(1, (0, 0, 0.5), (0, 0, 0)), (24, (2.5, 0, 0.5), (0, 0, 0)), (48, (5, 0, 0.5), (0, 0, 0))]
        movil = objeto("Movil", (0, 0, 0.5), (1, 1, 1), muestras=m)
        self.assertTrue(V.verificar(T.TAREAS["T06"], resultado([movil], 1, 48))["aprobado"])
        self.assertIn("del fotograma 1 al 250", V.verificar(T.TAREAS["T06"], resultado([movil]))["texto"])
        quieto = objeto("Movil", (0, 0, 0.5), (1, 1, 1), muestras=[(1, (0, 0, 0.5), (0, 0, 0)), (48, (0, 0, 0.5), (0, 0, 0))])
        self.assertIn("se desplaza (0.00, 0.00, 0.00)", V.verificar(T.TAREAS["T06"], resultado([quieto], 1, 48))["texto"])
        self.assertEqual(V.giro({"objetos": [objeto("A", (0, 0, 0), (1, 1, 1), muestras=[(1, (0, 0, 0), (0, 0, 170)),
                                                                                           (9, (0, 0, 0), (0, 0, -100))])]},
                                "A", 2, 90.0)[0], True)                # 170° → −100° es un giro de +90°
        E_ = {"objetos": [objeto("I", (0, 0, 0.1), (1, 1, 0.2), muestras=[(1, (0, 0, 0.1), (0, 0, 0)), (2, (0, 0, 0.4), (0, 0, 0)),
                                                                           (3, (0, 0, 0.1), (0, 0, 0))]),
                          objeto("D", (0, 0, 0.1), (1, 1, 0.2), muestras=[(1, (0, 0, 0.1), (0, 0, 0)), (2, (0, 0, 0.1), (0, 0, 0)),
                                                                           (3, (0, 0, 0.4), (0, 0, 0))])]}
        self.assertTrue(V.alternan(E_, "I", "D", 0.2)[0])
        E_["objetos"][1]["muestras"][1]["caja_min"][2] = 0.3            # los dos en el aire a la vez
        self.assertFalse(V.alternan(E_, "I", "D", 0.2)[0])

    def test_estados_que_no_son_ok(self):
        r = {"estado": "RECHAZADO", "filtro": {"motivos": ["línea 1: importa «os»"]}, "informe": None}
        v = V.verificar(T.TAREAS["T01"], r)
        self.assertEqual((v["aprobado"], "importa «os»" in v["texto"], "NO se ejecutó" in v["texto"]), (False, True, True))
        r = {"estado": "ERROR_SCRIPT", "informe": {"script": {"linea": 3, "error": "KeyError: 'x'", "codigo_de_la_linea": "a['x']"}}}
        self.assertIn("línea 3: KeyError", V.verificar(T.TAREAS["T01"], r)["texto"])

    def test_todas_las_tareas_tienen_referencia_y_comprobaciones_conocidas(self):
        self.assertEqual(sorted(T.TAREAS), sorted(T.REFERENCIAS))
        for id_, t in T.TAREAS.items():
            for nombre, *_ in t["comprobaciones"]:
                self.assertIn(nombre, V.COMPROBACIONES, id_)
            self.assertEqual(E.filtro.revisar(T.REFERENCIAS[id_]), [], id_)


class Prompt(unittest.TestCase):
    def test_extraer_script(self):
        self.assertEqual(B.extraer_script("Claro:\n```python\nimport bpy\nx = 1\n```\nfin"), "import bpy\nx = 1\n")
        self.assertEqual(B.extraer_script("```\nimport bpy\n```"), "import bpy\n")
        self.assertEqual(B.extraer_script("import bpy"), "import bpy\n")
        self.assertEqual(B.extraer_script("```python\nimport bpy\nx = (1,"), "import bpy\nx = (1,\n")   # cortada

    def test_el_prompt_no_lleva_la_clave(self):
        for id_, t in T.TAREAS.items():
            for previo in (None, {"script": "import bpy\n", "feedback": "- «Caja» mide (1.00, 1.00, 1.00) m; se pide (2.00, 2.00, 2.00)"}):
                texto = "\n".join(m["content"] for m in B.mensajes(t, previo))
                self.assertIn(t["enunciado"], texto)
                self.assertNotIn("comprobaciones", texto)
                self.assertNotIn(T.REFERENCIAS[id_][-60:], texto)
        dos = B.mensajes(T.TAREAS["T01"], {"script": "import bpy\n", "feedback": "- falla"})[1]["content"]
        self.assertIn("Tu script anterior", dos)
        self.assertIn("- falla", dos)

    def test_el_sistema_respeta_el_filtro(self):
        ejemplo = ('import bpy\nbpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 1))\nob = bpy.context.active_object\n'
                   'ob.name = "A"\nob.scale = (1, 2, 3)\nm = bpy.data.materials.new("N")\nm.use_nodes = True\n'
                   'm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (1, 0, 0, 1.0)\n'
                   'ob.data.materials.append(m)\nob.keyframe_insert(data_path="location", frame=1)\n'
                   'bpy.context.scene.frame_start = 1\nbpy.context.view_layer.update()\n')
        self.assertEqual(E.filtro.revisar(ejemplo), [])                 # lo que enseña el prompt pasa el filtro


class Bucle(unittest.TestCase):
    """Cerebro y Blender SIMULADOS: se comprueba el orden de intentos, la corrección y la reanudación."""

    def montar(self, aprobar_en):
        llamadas = []

        def completar(msgs, max_tokens):
            llamadas.append(msgs[1]["content"])
            return f"```python\n# intento {len(llamadas)}\nimport bpy\n```", 20, "stop"

        def probar(id_, script, carpeta, salida, render=None):
            n = sum(1 for c in llamadas if T.TAREAS[id_]["enunciado"] in c)
            ok = n >= aprobar_en.get(id_, 99)
            return ({"estado": "OK", "segundos": 1.0}, {"aprobado": ok, "cumplidas": 4 if ok else 2, "total": 4,
                                                        "texto": "todo correcto" if ok else f"- falla {n}"})
        return llamadas, completar, probar

    def test_corrige_hasta_aprobar_o_agotar_intentos(self):
        with tempfile.TemporaryDirectory() as d:
            llamadas, completar, probar = self.montar({"T01": 1, "T02": 2})
            fin = B.correr_modelo("m", ["T01", "T02", "T03"], Path(d), Path(d) / "b", completar, probar_fn=probar)
            self.assertEqual(fin, "completo")
            filas = B.leer_filas(Path(d))
            self.assertEqual([(f["tarea"], f["intento"], f["aprobado"]) for f in filas],
                             [("T01", 1, True), ("T02", 1, False), ("T02", 2, True), ("T03", 1, False), ("T03", 2, False),
                              ("T03", 3, False)])
            self.assertNotIn("Tu script anterior", llamadas[0])
            self.assertIn("- falla 1", llamadas[2])                     # el segundo intento de T02 lleva lo medido
            self.assertIn("# intento 2", llamadas[2])
            an = B.analizar(filas)["m"]
            self.assertEqual((an["aprobadas"], an["aprobadas_a_la_primera"], an["aprobadas_gracias_a_corregir"]), (2, 1, 1))
            self.assertEqual(an["tareas"]["T03"]["mejora"], ["2/4", "2/4", "2/4"])
            self.assertEqual(B.pendientes("m", ["T01", "T02", "T03"], Path(d)), [])
            self.assertIn("✔ al intento 2", B.informe(Path(d)))

    def test_stop_y_reanudar_no_repite(self):
        with tempfile.TemporaryDirectory() as d:
            llamadas, completar, probar = self.montar({"T01": 2, "T02": 1})
            parar = lambda: len(llamadas) >= 1
            self.assertEqual(B.correr_modelo("m", ["T01", "T02"], Path(d), Path(d) / "b", completar, parar=parar,
                                             probar_fn=probar), "parado")
            self.assertEqual(len(B.leer_filas(Path(d))), 1)
            self.assertTrue(json.loads((Path(d) / "estado.json").read_text(encoding="utf-8"))["parado"])
            self.assertEqual(B.correr_modelo("m", ["T01", "T02"], Path(d), Path(d) / "b", completar, probar_fn=probar),
                             "completo")
            self.assertEqual([(f["tarea"], f["intento"]) for f in B.leer_filas(Path(d))], [("T01", 1), ("T01", 2), ("T02", 1)])
            self.assertEqual(len(llamadas), 3)
            self.assertIn("Tu script anterior", llamadas[1])            # al reanudar recupera el intento anterior


@unittest.skipUnless(E.blender_exe(), "OMITIDO: no hay Blender instalado")
class Real(unittest.TestCase):
    def test_referencia_de_t01_aprueba_y_script_vacio_no(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            _, v = B.probar("T01", T.REFERENCIAS["T01"], Path(d) / "a", Path(d))
            self.assertTrue(v["aprobado"], v["texto"])
            _, v = B.probar("T01", "import bpy\n", Path(d) / "b", Path(d))
            self.assertFalse(v["aprobado"])


if __name__ == "__main__":
    unittest.main()
