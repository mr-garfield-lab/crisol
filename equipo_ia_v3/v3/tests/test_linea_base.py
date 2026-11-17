"""Pruebas de la línea base V3: el mecanismo de regresión no oculta fallos nuevos ni convierte errores en éxitos.

Ejecutar desde equipo_ia_v3/:   python3 -B -m unittest discover -s v3/tests -t v3/tests -v
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

V3 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V3))
import linea_base as LB  # noqa: E402

SINTETICO = '''
import os
import unittest


class T(unittest.TestCase):
    def test_ok(self):
        pass

    def test_falla(self):
        self.assertEqual(1, 2)

    def test_error(self):
        raise ValueError("boom")

    @unittest.skip("motivo declarado")
    def test_omitida(self):
        pass

    @unittest.expectedFailure
    def test_fallo_esperado(self):
        self.assertTrue(False)

    @unittest.expectedFailure
    def test_exito_inesperado(self):
        pass

    def test_subtest(self):
        for i in range(3):
            with self.subTest(i=i):
                self.assertNotEqual(i, 1)

    def test_redefine_id(self):
        self.id = "R-1"          # como test_complementos.py: rompía la versión anterior del corredor

    def test_error_tras_tapar_id(self):
        self.id = "R-2"
        raise KeyError("x")

    def test_archivo_ausente(self):
        open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "no_existe.txt"))


class ErrorEnSetUp(unittest.TestCase):
    def setUp(self):
        raise RuntimeError("setup roto")

    def test_x(self):
        pass
'''

ESTADOS_SINTETICOS = {
    "test_sintetico.T.test_ok": "OK",
    "test_sintetico.T.test_falla": "FALLO",
    "test_sintetico.T.test_error": "ERROR",
    "test_sintetico.T.test_omitida": "OMITIDA",
    "test_sintetico.T.test_fallo_esperado": "FALLO_ESPERADO",
    "test_sintetico.T.test_exito_inesperado": "EXITO_INESPERADO",
    "test_sintetico.T.test_subtest": "FALLO",
    "test_sintetico.T.test_redefine_id": "OK",
    "test_sintetico.T.test_error_tras_tapar_id": "ERROR",
    "test_sintetico.T.test_archivo_ausente": "ERROR",
    "test_sintetico.ErrorEnSetUp.test_x": "ERROR",
    "unittest.loader._FailedTest.test_roto": "ERROR",
}


def _tmp(caso):
    d = tempfile.TemporaryDirectory(prefix="eq3_lb_", dir=os.environ.get("TMPDIR"))
    caso.addCleanup(d.cleanup)
    return Path(d.name)


def _codex(base, origen=None):
    return LB.ejecutar_unittest("codex", origen or LB.FUENTES / "codex_complementos", base, LB.SISTEMA,
                                [LB.SISTEMA / "src"], 600, {"COMPLEMENTOS_SALIDA": "{TMP}"})


def _como_linea_base(res, causa="C"):
    return {"causas": {causa: "prueba"},
            "suites": {"codex": {"pruebas": {k: ({"estado": "OK"} if v["estado"] == "OK" else dict(v, causa=causa))
                                             for k, v in res["pruebas"].items()}}}}


class TestCorredor(unittest.TestCase):
    def setUp(self):
        self.t = _tmp(self)
        self.origen = self.t / "origen"
        (self.origen / "tests").mkdir(parents=True)
        (self.origen / "tests" / "test_sintetico.py").write_text(SINTETICO, encoding="utf-8")
        (self.origen / "tests" / "test_roto.py").write_text("raise ImportError('modulo roto a proposito')\n",
                                                            encoding="utf-8")

    def _correr(self, nombre):
        return LB.ejecutar_unittest("sint", self.origen, self.t / nombre, LB.SISTEMA, [], 120)

    def test_estados_exactos_ningun_error_se_aprueba(self):
        r = self._correr("a")
        self.assertEqual({k: v["estado"] for k, v in r["pruebas"].items()}, ESTADOS_SINTETICOS)
        aprobadas = {k for k, v in r["pruebas"].items() if v["estado"] == "OK"}
        self.assertEqual(aprobadas, {"test_sintetico.T.test_ok", "test_sintetico.T.test_redefine_id"})

    def test_firmas_informativas_y_estables_entre_ejecuciones(self):
        # Carpetas de salida de LONGITUD muy distinta: recortar antes de normalizar cambiaba la firma (defecto
        # real encontrado por el verificador integral, cuya carpeta de salida es más profunda).
        # En Windows, el directorio de trabajo de un proceso no puede pasar de ~258 caracteres (WinError 267) ni
        # conviene superar 260 en los archivos: el nombre largo se ajusta a lo que cabe, y si no cabe una diferencia
        # apreciable la prueba se OMITE con su motivo (no se da por buena).
        largo = 150 if not LB.plataforma.WINDOWS else min(150, 210 - len(str(self.t)))
        if largo < 60:
            self.skipTest(f"PLATAFORMA: la carpeta temporal es demasiado profunda para Windows ({len(str(self.t))} "
                          "caracteres); use un TMPDIR más corto")
        a, b = self._correr("a"), self._correr("b" * largo)
        fa = {k: v["firma"] for k, v in a["pruebas"].items()}
        self.assertEqual(fa, {k: v["firma"] for k, v in b["pruebas"].items()})    # rutas distintas, misma firma
        self.assertEqual(fa["test_sintetico.T.test_error"], "ValueError: boom")
        self.assertEqual(fa["test_sintetico.T.test_omitida"], "motivo declarado")
        self.assertTrue(fa["test_sintetico.T.test_falla"].startswith("AssertionError: 1 != 2"))
        self.assertIn("modulo roto a proposito", fa["unittest.loader._FailedTest.test_roto"])
        self.assertIn("'<SALIDA>/copia_sint/tests/no_existe.txt'", fa["test_sintetico.T.test_archivo_ausente"])
        self.assertNotIn(str(self.t), json.dumps(fa))
        self.assertEqual(fa["test_sintetico.T.test_ok"], "")

    def test_suite_sin_pruebas_es_error_de_la_herramienta(self):
        vacio = self.t / "vacio"
        (vacio / "tests").mkdir(parents=True)
        with self.assertRaises(LB.ErrorHerramienta):
            LB.ejecutar_unittest("vacio", vacio, self.t / "v", LB.SISTEMA, [], 60)


class TestVeredictos(unittest.TestCase):
    OK = {"estado": "OK", "firma": ""}
    ERR = {"estado": "ERROR", "firma": "FileNotFoundError: x", "causa": "C"}

    def test_tabla_de_veredictos(self):
        casos = [
            (self.OK, self.OK, "IGUAL"),
            (self.OK, {"estado": "FALLO", "firma": "AssertionError: a"}, "REGRESION"),
            (self.OK, {"estado": "ERROR", "firma": "E: b"}, "REGRESION"),
            (self.OK, {"estado": "OMITIDA", "firma": "motivo"}, "REGRESION"),        # un skip nuevo no se oculta
            (self.OK, {"estado": "NO VERIFICADA", "firma": "x"}, "REGRESION"),
            (self.OK, None, "AUSENTE"),
            (self.ERR, dict(self.ERR), "IGUAL"),
            (self.ERR, {"estado": "ERROR", "firma": "LookupError: otra causa"}, "CAMBIO"),   # misma prueba, otra causa
            (self.ERR, {"estado": "FALLO", "firma": "FileNotFoundError: x"}, "CAMBIO"),
            (self.ERR, {"estado": "OMITIDA", "firma": "FileNotFoundError: x"}, "CAMBIO"),
            (self.ERR, self.OK, "MEJORA"),
            (self.ERR, None, "AUSENTE"),
            (None, self.OK, "NUEVA"),
            (None, {"estado": "ERROR", "firma": "E"}, "REGRESION"),
            (None, {"estado": "OMITIDA", "firma": "m"}, "REGRESION"),
        ]
        for esperado, real, v in casos:
            with self.subTest(esperado=esperado, real=real):
                self.assertEqual(LB.veredicto(esperado, real), v)

    def test_codigos_de_salida(self):
        cero = {v: 0 for v in LB.VEREDICTOS}
        self.assertEqual(LB.codigo_salida(dict(cero, IGUAL=9, NUEVA=2)), 0)
        self.assertEqual(LB.codigo_salida(dict(cero, MEJORA=1)), 3)
        for v in ("REGRESION", "CAMBIO", "AUSENTE"):
            self.assertEqual(LB.codigo_salida(dict(cero, MEJORA=4, **{v: 1})), 1)

    def test_comparar_lista_todas_las_diferencias(self):
        esperado = {"suites": {"s": {"pruebas": {"a": self.OK, "b": self.ERR, "c": self.OK}}}}
        obtenido = {"s": {"pruebas": {"a": self.OK, "b": {"estado": "ERROR", "firma": "Otro: y"},
                                      "d": {"estado": "FALLO", "firma": "F"}}}}
        cmp_ = LB.comparar(obtenido, esperado)
        self.assertEqual(cmp_["totales"], {"IGUAL": 1, "NUEVA": 0, "MEJORA": 0, "REGRESION": 1, "CAMBIO": 1,
                                           "AUSENTE": 1})
        self.assertEqual({(d["id"], d["veredicto"]) for d in cmp_["diferencias"]},
                         {("b", "CAMBIO"), ("c", "AUSENTE"), ("d", "REGRESION")})


class TestLineaBaseYNormalizacion(unittest.TestCase):
    def test_causas_obligatorias_y_declaradas(self):
        # SIN_CLASIFICAR se rechaza aunque alguien la declare en el catálogo para colarla.
        esp = {"causas": {"C": "x", LB.SIN_CLASIFICAR: "intento de colarla"}, "suites": {"s": {"pruebas": {
            "ok": {"estado": "OK"}, "a": {"estado": "ERROR", "causa": "C"},
            "b": {"estado": "FALLO", "causa": LB.SIN_CLASIFICAR}, "c": {"estado": "OMITIDA"},
            "d": {"estado": "ERROR", "causa": "NO_DECLARADA"}}}}}
        problemas = LB.validar_esperada(esp, ("s", "falta"))
        self.assertEqual(sorted(problemas), sorted([
            "s: b: causa sin clasificar", "s: c: causa sin clasificar",
            "s: d: causa no declarada en el catálogo: NO_DECLARADA", "falta: la línea base no tiene pruebas"]))

    def test_main_rechaza_linea_base_sin_clasificar_antes_de_ejecutar(self):
        t = _tmp(self)
        mala = t / "esperada.json"
        mala.write_text(json.dumps({"causas": {}, "suites": {"codex": {"pruebas": {
            "x": {"estado": "ERROR", "causa": LB.SIN_CLASIFICAR}}}}}), encoding="utf-8")
        self.assertEqual(LB.main(["--solo", "codex", "--esperada", str(mala), "--salida", str(t / "s")]), 2)
        self.assertFalse((t / "s").exists())                     # no llegó a ejecutar nada

    def test_main_rechaza_salida_existente(self):
        t = _tmp(self)
        self.assertEqual(LB.main(["--solo", "codex", "--salida", str(t)]), 2)

    def test_normalizar_rutas_identificadores_y_temporales(self):
        base = Path("/x/salida")
        pares = LB.reemplazos(base, Path("/x/sis"))
        texto = "/x/salida/tmp/eq2_test_ab12cd34/f /x/sis/src 20261110_004350_809535_264 tmpq1w2e3r4"
        self.assertEqual(LB.normalizar(texto, pares), "<SALIDA>/tmp/eq2_test_<X>/f <SISTEMA>/src <ID> tmp<X>")

    def test_windows_rechaza_una_salida_demasiado_larga_para_el_verificador(self):
        if not LB.plataforma.WINDOWS:
            self.skipTest("PLATAFORMA: el límite de longitud de rutas solo existe en Windows")
        with tempfile.TemporaryDirectory(prefix="eq3_lb_") as t:
            larga = Path(t) / ("x" * LB.MAX_BASE_WINDOWS)
            self.assertEqual(LB.main(["--salida", str(larga), "--solo", "verificador"]), 2)
            self.assertFalse(larga.exists())                       # se rechaza antes de crear ni ejecutar nada

    def test_normalizar_firmas_que_cambian_entre_ejecuciones(self):
        # V3.1: dos ejecuciones de la MISMA prueba fallida deben dar la misma firma (si no, la puerta es inestable).
        pares = LB.reemplazos(Path("/x/salida"), Path("/x/sis"))
        a = LB.normalizar("PermissionError: '/x/salida/tmp_contexto/ctx33_integracion_5gjpys5m/sesion/datos/sesion.db'", pares)
        b = LB.normalizar("PermissionError: '/x/salida/tmp_contexto/ctx33_integracion__b2ehaun/sesion/datos/sesion.db'", pares)
        self.assertEqual(a, b)
        self.assertEqual(a, "PermissionError: '<SALIDA>/tmp_contexto/ctx33_integracion_<X>/sesion/datos/sesion.db'")
        c = LB.normalizar("AssertionError: Items in the second set but not the first: … ('billing.py', 'calculate_total')", pares)
        d = LB.normalizar("AssertionError: Items in the second set but not the first: … ('billing.py', 'validate_invoice')", pares)
        self.assertEqual(c, d)
        self.assertEqual(c, "AssertionError: Items in the second set but not the first: <ELEMENTOS>")
        # Lo que SÍ distingue un fallo de otro se conserva: tipo de error, sentido de la diferencia y otros mensajes.
        self.assertNotEqual(c, LB.normalizar("AssertionError: Items in the first set but not the second: … 'x'", pares))
        self.assertNotEqual(c, LB.normalizar("AssertionError: 'a' != 'b'", pares))
        self.assertEqual(LB.normalizar("AssertionError: 'calculate_total' != 'validate_invoice'", pares),
                         "AssertionError: 'calculate_total' != 'validate_invoice'")

    def test_normalizar_firma_que_no_depende_de_la_carpeta_del_proyecto(self):
        # unittest abrevia el resumen y parte la ruta real por la mitad: la firma no puede depender de dónde está el
        # proyecto (si no, la línea base de Windows solo valdría en la máquina que la generó).
        def firma(base):
            completa = f"{base}/tmp_contexto/tmpab12cd34/segundo.txt"
            return LB.normalizar(
                f"AssertionError: Lists differ: [Wind[{len(base) + 40} chars]txt')] != [Wind[{len(base) + 40} chars]txt'), "
                f"WindowsPath('{completa[:len(base) - 6]}[{len(completa) - len(base) + 4} chars]xt')] … "
                f"+  WindowsPath('{completa}')]", LB.reemplazos(Path(base), Path("/x/sis")))
        a, b = firma("C:/proyectos/EquipoIA_V3_1/t/l5"), firma("D:/otra/carpeta/mucho/mas/larga/que/la/primera")
        self.assertEqual(a, b)
        self.assertEqual(a, "AssertionError: Lists differ: <ABREVIADO> … +  WindowsPath('<SALIDA>/tmp_contexto/tmp<X>/segundo.txt')]")
        sin_abreviar = "AssertionError: Lists differ: [1, 2] != [1, 3] … +  3"
        self.assertEqual(LB.normalizar(sin_abreviar, []), sin_abreviar)          # sin «[N chars]» no se toca

    def test_informe_del_verificador(self):
        pares = LB.reemplazos(Path("/b"), Path("/s"))
        inf = {"resultados": [{"id": "V-1", "estado": "OK", "detalle": "/b/algo"},
                              {"id": "V-2", "estado": "FALLO", "detalle": "falta /b/x.zip"},
                              {"id": "V-3", "estado": "NO VERIFICADA", "detalle": "requiere --qwen-real"}]}
        self.assertEqual(LB.estados_de_informe(inf, pares), {
            "V-1": {"estado": "OK", "firma": ""},
            "V-2": {"estado": "FALLO", "firma": "falta <SALIDA>/x.zip"},
            "V-3": {"estado": "NO VERIFICADA", "firma": "requiere --qwen-real"}})
        inf["resultados"].append({"id": "V-1", "estado": "OK", "detalle": ""})
        with self.assertRaises(LB.ErrorHerramienta):
            LB.estados_de_informe(inf, pares)


class TestMutacionSobreCodexReal(unittest.TestCase):
    """Suite REAL de codex_complementos (copia): control negativo y mutaciones conocidas."""

    @classmethod
    def setUpClass(cls):
        cls._d = tempfile.TemporaryDirectory(prefix="eq3_mut_", dir=os.environ.get("TMPDIR"))
        cls.t = Path(cls._d.name)
        cls.ref = _codex(cls.t / "ref")
        cls.esperada = _como_linea_base(cls.ref)

    @classmethod
    def tearDownClass(cls):
        cls._d.cleanup()

    def test_control_negativo_sin_cambios_todo_igual_y_el_error_conocido_sigue_siendo_error(self):
        cmp_ = LB.comparar({"codex": _codex(self.t / "ctl")}, self.esperada)
        self.assertEqual(cmp_["diferencias"], [])
        self.assertEqual(LB.codigo_salida(cmp_["totales"]), 0)
        no_ok = {k: v["estado"] for k, v in self.ref["pruebas"].items() if v["estado"] != "OK"}
        self.assertEqual(no_ok, {"test_complementos.Evaluacion.test_callback_solo_publicos_presupuesto_y_roles":
                                 "ERROR"})

    def test_mutaciones_detectadas(self):
        origen = self.t / "mut_origen"
        shutil.copytree(LB.FUENTES / "codex_complementos", origen,
                        ignore=shutil.ignore_patterns("__pycache__", "resultados"))
        f = origen / "tests" / "test_complementos.py"
        src = f.read_text(encoding="utf-8")
        mutaciones = [
            ("    def test_integridad_archivo_alterado(self):\n",            # OK → ERROR
             "    def test_integridad_archivo_alterado(self):\n        raise RuntimeError('mutacion')\n"),
            ("    def test_diagnostico_y_no_repeticion(self):\n",            # desaparece y aparece con otro nombre
             "    def test_diagnostico_renombrada(self):\n"),
            ("    def test_callback_solo_publicos_presupuesto_y_roles(self):\n",   # fallo conocido, otra causa
             "    def test_callback_solo_publicos_presupuesto_y_roles(self):\n        raise LookupError('otra causa')\n"),
        ]
        for viejo, nuevo in mutaciones:
            self.assertEqual(src.count(viejo), 1, viejo)                  # ninguna mutación queda en vacío
            src = src.replace(viejo, nuevo)
        f.write_text(src, encoding="utf-8")
        (origen / "tests" / "test_zz_inyectada.py").write_text(
            "import unittest\n\n\nclass Z(unittest.TestCase):\n    def test_nueva_falla(self):\n"
            "        self.fail('inyectado')\n", encoding="utf-8")
        cmp_ = LB.comparar({"codex": _codex(self.t / "mut", origen)}, self.esperada)
        v = {d["id"].split(".")[-1]: d["veredicto"] for d in cmp_["diferencias"]}
        self.assertEqual(v, {"test_integridad_archivo_alterado": "REGRESION",
                             "test_diagnostico_y_no_repeticion": "AUSENTE",
                             "test_diagnostico_renombrada": "NUEVA",
                             "test_callback_solo_publicos_presupuesto_y_roles": "CAMBIO",
                             "test_nueva_falla": "REGRESION"})
        self.assertEqual(LB.codigo_salida(cmp_["totales"]), 1)


if __name__ == "__main__":
    unittest.main()
