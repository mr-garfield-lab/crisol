"""V2-E.7: equipo operativo. UNA prueba demostrativa de extremo a extremo (A1 crea un archivo, A2 escribe y
ejecuta una prueba REAL, A3 revisa y audita la evidencia; se guarda y se exporta) y las comprobaciones mínimas de
seguridad del ejecutor restringido.

En la demostración los textos de los agentes vienen de un GUION (aquí no hay Qwen); la ejecución de las pruebas,
el guardado, la auditoría determinista y la exportación son REALES. Con Qwen se ejecuta en Termux con
`equipo.py tarea ejecutar <id> --autorizo-pruebas`."""
import ast
import json
import zipfile
import hashlib
import unittest
from pathlib import Path

import _comun
from eq2 import ejecutor_restringido as ER, motor, rutas, tareas
from eq2.ejecutor import Politica

RAIZ = _comun.RAIZ
MAL = "ARCHIVO: ordenar.py\n```python\ndef ordenar(xs):\n    xs.sort()\n    return xs\n```\nFIN"
BIEN = "ARCHIVO: ordenar.py\n```python\ndef ordenar(xs):\n    return sorted(xs)\n```\nCAMBIOS: copia con sorted\nFIN"
PRUEBAS_A2 = ("ARCHIVO: test_ordenar.py\n```python\nimport unittest\nfrom ordenar import ordenar\n\n"
              "class T(unittest.TestCase):\n    def test_ordena(self):\n        self.assertEqual(ordenar([3, 1, 2]), [1, 2, 3])\n\n"
              "    def test_no_muta(self):\n        a = [2, 1]\n        ordenar(a)\n        self.assertEqual(a, [2, 1])\n\n"
              "def test_vacia():\n    assert ordenar([]) == []\n```\nFIN")


def guion(paso, n, **kw):
    return {"planificar": "ARCHIVOS: ordenar.py, test_ordenar.py\n"
                          "CRITERIO: C1 | devuelve la lista ordenada | PRUEBA: test_ordena\n"
                          "CRITERIO: C2 | no modifica la entrada | PRUEBA: test_no_muta\n"
                          "CRITERIO: C3 | lista vacía | PRUEBA: test_vacia",
            "generar": MAL, "pruebas": PRUEBAS_A2, "revisar": "SIN OBJECIONES",
            "evaluar": "DIAGNOSTICO: ordenar modifica la entrada; devolver una copia",
            "corregir": BIEN, "auditar": "AUDITORIA: conforme\nOBSERVACION: la prueba test_no_muta falló y luego pasó"}[paso]


class TestDemoEquipo(unittest.TestCase):
    def test_a1_crea_a2_prueba_a3_audita_y_se_exporta(self):
        tmp = _comun.carpeta_temporal()
        self.addCleanup(tmp.cleanup)
        d = Path(tmp.name)
        (d / "tarea.json").write_text(json.dumps({"id": "LAB-001", "titulo": "demo", "max_iteraciones": 2,
                                                  "instrucciones": "Crea ordenar(xs) sin modificar la entrada."}))
        ts = tareas.Tareas(raiz=d / "equipo_f2")
        ts.importar(d / "tarea.json")
        with self.assertRaises(tareas.ErrorTarea):                    # nunca se sobrescribe una tarea
            ts.importar(d / "tarea.json")
        r = ts.ejecutar("LAB-001", motor.AgentesMotorSimulados(guion), autorizo_pruebas=True, instalar_senales=False)
        self.assertEqual((r["estado_final"], r["resultado"], r["auditoria_A3"]),
                         ("criterios_verificados", "verificado", "conforme"), r)
        e = ts.lab.ruta("tareas", "LAB-001", "ejecuciones", "E001")
        # A1 creó el archivo (dos versiones: la errónea y la corregida), A2 escribió las pruebas
        v = sorted(e.glob("runs/*/proyecto/v*/ordenar.py"))
        self.assertEqual([p.read_text().count("sorted(xs)") for p in v], [0, 1])
        self.assertTrue(all((p.parent / "test_ordenar.py").is_file() for p in v))
        # A2 ejecutó las pruebas DE VERDAD: primero fallan, después pasan; salidas y códigos guardados
        regs = [json.loads((e / "pruebas" / p / "registro.json").read_text()) for p in ("P001", "P002")]
        self.assertEqual([(x["estado"], x["codigo_retorno"], x["nonce_valido"]) for x in regs],
                         [("fallos", 1, True), ("ok", 0, True)])
        self.assertEqual(regs[0]["resultado"]["pruebas"]["test_no_muta"], "fallo")
        self.assertIn("AssertionError", (e / "pruebas" / "P001" / "informe_unittest.txt").read_text())
        # A3: auditoría guardada aparte; la conclusión es la del código
        det = json.loads((e / "auditoria" / "determinista.json").read_text())
        self.assertEqual(det["conclusion"], "verificado")
        self.assertTrue(all(x["coincide"] for x in det["integridad_archivos"]))
        self.assertIn("AUDITORIA: conforme", (e / "auditoria" / "A3_auditoria.txt").read_text())
        # sin autorización: ninguna prueba se ejecuta y nunca queda «verificado»
        r2 = ts.ejecutar("LAB-001", motor.AgentesMotorSimulados(guion), autorizo_pruebas=False, instalar_senales=False)
        self.assertEqual((r2["ejecucion"], r2["resultado"], r2["ejecuciones_de_pruebas"]), ("E002", "no_verificado", 0))
        self.assertEqual(ts.estado("ultima")["estado"], "terminada")
        # exportar: ZIP con manifiesto comprobable; un segundo export no sobrescribe
        z1, z2 = ts.exportar("LAB-001"), ts.exportar("ultima")
        self.assertEqual((z1.name, z2.name), ("EQUIPO_IA_LAB-001_ENTREGA.zip", "EQUIPO_IA_LAB-001_ENTREGA_v2.zip"))
        with zipfile.ZipFile(z1) as z:
            nombres = z.namelist()
            raiz = nombres[0].split("/")[0]
            man = z.read(f"{raiz}/MANIFIESTO_SHA256.txt").decode().splitlines()
            for linea in man:
                h, ruta = linea.split("  ", 1)
                self.assertEqual(hashlib.sha256(z.read(f"{raiz}/{ruta}")).hexdigest(), h, ruta)
        self.assertTrue(any(n.endswith("tarea/tarea_original.json") for n in nombres))
        self.assertTrue(any(n.endswith("pruebas/P002/salida.txt") for n in nombres))
        self.assertTrue(any(n.endswith("auditoria/A3_auditoria.txt") for n in nombres))
        tipos = [x["tipo"] for x in ts.eventos("LAB-001")]
        self.assertEqual(tipos.count("ejecucion_terminada"), 2)
        self.assertEqual(tipos[-2:], ["exportada", "exportada"])


class _Esp:
    def __init__(self, a):
        self.archivos = a


class TestEjecutorRestringido(unittest.TestCase):
    def setUp(self):
        tmp = _comun.carpeta_temporal()
        self.addCleanup(tmp.cleanup)
        self.d = Path(tmp.name)
        self.lab = rutas.Laboratorio(self.d, self.d / "lab")
        self.lab.crear_base()

    def correr(self, archivos, autorizado=True, seg=10):
        return ER.EjecutorRestringido(self.lab, ("x",), autorizado=autorizado, seg=seg).ejecutar(
            _Esp(archivos), "pruebas_python", Politica()).a_dict()

    def test_lista_blanca_rechaza_antes_de_ejecutar(self):
        for codigo in ("import os\ndef test_a():\n    os.system('true')\n",
                       "import unittest\ndef test_a():\n    unittest.loader.os.system('true')\n",
                       "def test_a():\n    open('/tmp/x', 'w')\n",
                       "def test_a():\n    ().__class__.__base__\n",
                       "import unittest\ndef test_a():\n    unittest.TestResult.addSuccess = None\n",
                       "from unittest import mock\ndef test_a():\n    pass\n"):
            r = self.correr({"test_x.py": codigo})
            self.assertEqual((r["tipo"], r["estado"]), ("estatico", "fallos"), codigo)
            self.assertFalse(list(self.lab.ruta("x", "pruebas").glob("*/espacio")), "no debe copiarse ni ejecutarse")

    def test_gancho_bloquea_aunque_falle_la_lista_blanca(self):
        """El corredor bloquea por sí solo (se llama sin pasar por validar): escritura fuera, sistema, red."""
        hostil = ("import os, sys\n"
                  "def _b(f):\n    try:\n        f()\n        return False\n    except Exception:\n        return True\n"
                  "def test_bloqueos():\n"
                  f"    assert _b(lambda: open({str(self.d / 'FUERA')!r}, 'w'))\n"
                  "    assert _b(lambda: os.system('true'))\n"
                  "    assert _b(lambda: __import__('socket'))\n"
                  "    assert _b(lambda: sys._getframe(1))\n"
                  "    assert not _b(lambda: open('dentro.txt', 'w').write('ok'))\n")
        orig, ER.validar = ER.validar, lambda a: []
        try:
            r = self.correr({"test_h.py": hostil})
        finally:
            ER.validar = orig
        self.assertEqual((r["tipo"], r["estado"], r["detalle"]["pruebas"]), ("real", "ok", {"test_bloqueos": "ok"}))
        self.assertFalse((self.d / "FUERA").exists())

    def test_resultado_falsificado_y_bucle(self):
        r = self.correr({"test_f.py": "def test_a():\n    print('EQ2RES ' + '0' * 32 + ' {\"total\": 9}')\n    assert False\n"})
        self.assertEqual((r["estado"], r["pruebas_fallidas"]), ("fallos", 1))     # la línea falsa no cuenta
        r = self.correr({"test_b.py": "def test_a():\n    while True:\n        pass\n"}, seg=2)
        self.assertEqual((r["tipo"], r["estado"]), ("real", "error"))
        self.assertFalse(r["detalle"]["nonce_valido"])

    def test_sin_autorizacion_no_ejecuta_y_solo_la_cli_autoriza(self):
        r = self.correr({"test_x.py": "def test_a():\n    pass\n"}, autorizado=False)
        self.assertEqual(r["estado"], "no_disponible")
        usos = []                                  # nadie concede la autorización con un literal
        for p in list((RAIZ / "src" / "eq2").glob("*.py")) + list(RAIZ.glob("*.py")):
            for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
                if isinstance(n, ast.Call) and (getattr(n.func, "attr", None) or getattr(n.func, "id", None)) in (
                        "EjecutorRestringido", "ejecutar"):
                    for k in n.keywords:
                        if k.arg in ("autorizo_pruebas", "autorizado") and isinstance(k.value, ast.Constant) \
                                and k.value.value is True:
                            usos.append(p.name)
                if isinstance(n, ast.Assign) and any(isinstance(t, ast.Attribute) and t.attr == "autorizado"
                                                     for t in n.targets) and p.name != "ejecutor_restringido.py":
                    usos.append(p.name)
        self.assertEqual(usos, [], "solo la CLI (args.autorizo_pruebas) puede autorizar")
        cli = (RAIZ / "equipo.py").read_text(encoding="utf-8")
        self.assertIn("autorizo_pruebas=a.autorizo_pruebas", cli)


if __name__ == "__main__":
    unittest.main()
