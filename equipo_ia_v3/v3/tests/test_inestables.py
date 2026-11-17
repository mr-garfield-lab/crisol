"""X1 (V3.1 F1): la tolerancia a pruebas inestables NO deja pasar ninguna regresión.

Ejecutar desde equipo_ia_v3/:   python -B -m unittest discover -s v3/tests -t v3/tests -p "test_inestables.py" -v

Una diferencia solo pasa a INESTABLE con la firma EXACTA declarada (subprueba, línea, código, `A != B` dentro de la
tolerancia), con todos los fallos conocidos presentes, y si la subprueba repetida aislada pasa por mayoría estricta
y vuelve a fallar solo de la forma declarada. Cada condición se prueba rompiéndola, y dos regresiones REALES
sembradas en una copia de `sistema/` (desplazamiento constante de 4 kB y error de unidades) no se aceptan.
"""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

V3 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V3))
import linea_base as LB  # noqa: E402

DECL = json.loads((V3 / "causas_windows.json").read_text(encoding="utf-8"))["inestables"][0]
SUB = DECL["subprueba"]
ARCH = 'File "C:\\proyecto\\sistema\\tests\\test_v2e5.py"'

CANDADO = f"""======================================================================
FAIL: test_candado_sin_forma_de_comprobar_no_se_da_por_obsoleto (test_v2e5.TestAdaptadores.test_candado_sin_forma_de_comprobar_no_se_da_por_obsoleto)
----------------------------------------------------------------------
Traceback (most recent call last):
  {ARCH}, line 409, in test_candado_sin_forma_de_comprobar_no_se_da_por_obsoleto
    self.assertEqual(cm.exception.obsoleto, not os.path.exists("/proc/999999"))
AssertionError: False != True
"""
SELECCION = f"""======================================================================
FAIL: test_seleccion (test_v2e5.TestAdaptadores.test_seleccion)
----------------------------------------------------------------------
Traceback (most recent call last):
  {ARCH}, line 356, in test_seleccion
    self.assertIsInstance(plataforma.adaptador({{"PREFIX": "/data/data/com.termux/files/usr"}}),
AssertionError: <eq2.plataforma.AdaptadorWindows object at 0x00000201478C0C40> is not an instance of <class 'eq2.plataforma.AdaptadorTermux'>
"""


def memoria(cls="AdaptadorLinux", a=18518192, b=18517168, linea=375, header="FAIL",
            codigo="self.assertEqual(a.mem_disponible_kb(), vigilancia.leer_mem_available())", extra_marco="",
            cola="", sub=SUB):
    return f"""======================================================================
{header}: {sub.rsplit(".", 1)[1]} ({sub}) (cls='{cls}')
----------------------------------------------------------------------
Traceback (most recent call last):
  {ARCH}, line {linea}, in test_termux_y_linux_dan_lo_mismo_que_el_codigo_anterior
    {codigo}
{extra_marco}AssertionError: {a} != {b}
{cola}"""


def traza(*bloques, ran=6):
    n = len(bloques)
    return "\n" + "".join(bloques) + f"\n----------------------------------------------------------------------\n" \
           f"Ran {ran} tests in 1.056s\n\nFAILED (failures={n})\n"


INTENTO1 = traza(CANDADO, SELECCION, memoria(), memoria("AdaptadorTermux", 18518928, 18518920))   # traza REAL (§1.1)


def esperado(estado="FALLO", firma="6/6 ejecutadas; failures=2", decls=(DECL,)):
    b = {"estado": estado}
    if estado != "OK":
        b.update(firma=firma, causa="C", subpruebas=[
            {"subprueba": "test_v2e5.TestAdaptadores.test_candado_sin_forma_de_comprobar_no_se_da_por_obsoleto"},
            {"subprueba": "test_v2e5.TestAdaptadores.test_seleccion"}])
    return {"causas": {"C": "x", DECL["causa"]: "y"}, "inestables": list(decls),
            "suites": {"verificador": {"pruebas": {"V-CON-11": b}}}}


def diferencia(firma="6/6 ejecutadas; failures=4", veredicto="CAMBIO"):
    return {"suite": "verificador", "id": "V-CON-11", "veredicto": veredicto,
            "real": {"estado": "FALLO", "firma": firma}}


class TestExplicar(unittest.TestCase):
    def test_traza_real_del_intento_1_se_explica_entera(self):
        e = LB.explicar_inestable(diferencia(), esperado(), {"V-CON-11": INTENTO1})
        self.assertEqual(e["declaraciones"], [DECL["id"]])
        self.assertEqual([f["diferencia_kB"] for f in e["fallos"]], [1024, 8])
        self.assertEqual(e["fallos"][1]["subprueba"], f"{SUB} (cls='AdaptadorTermux')")

    def test_prueba_ok_en_la_linea_base_que_solo_falla_por_la_inestabilidad(self):
        e = LB.explicar_inestable(diferencia("6/6 ejecutadas; failures=1", "REGRESION"), esperado("OK"),
                                  {"V-CON-11": traza(memoria())})
        self.assertEqual([f["diferencia_kB"] for f in e["fallos"]], [1024])

    def test_cualquier_desviacion_de_la_firma_declarada_no_se_explica(self):
        conocidos = (CANDADO, SELECCION)
        control = LB.explicar_inestable(diferencia("6/6 ejecutadas; failures=3"), esperado(),
                                        {"V-CON-11": traza(*conocidos, memoria())})
        self.assertIsNotNone(control)                  # control: la misma construcción sin desviación SÍ se explica
        casos = {
            "diferencia por encima de la tolerancia": traza(*conocidos, memoria(a=18518192, b=18518192 - 32769)),
            "error de unidades (kB frente a bytes)": traza(*conocidos, memoria(a=18518192, b=18518192 * 1024)),
            "lectura a cero": traza(*conocidos, memoria(a=0, b=5)),
            "otra línea": traza(*conocidos, memoria(linea=376)),
            "otro código en la línea": traza(*conocidos, memoria(codigo="self.assertEqual(a.comando_servidor(), [])")),
            "ERROR en vez de FAIL": traza(*conocidos, memoria(header="ERROR")),
            "un marco más (el fallo viene de otra función)": traza(*conocidos, memoria(
                extra_marco=f"  {ARCH}, line 12, in ayuda\n    return x\n")),
            "un fallo conocido desaparece": traza(SELECCION, memoria(), memoria("AdaptadorTermux")),
            "un fallo nuevo en otra prueba": traza(*conocidos, memoria(), SELECCION.replace("test_seleccion",
                                                                                           "test_auditoria")),
            "número de pruebas distinto": traza(*conocidos, memoria(), memoria("AdaptadorTermux"), ran=7),
            "texto de más tras el mensaje": traza(*conocidos, memoria(cola="Nota añadida al fallo\n")),
            "misma firma en otra subprueba": traza(*conocidos, memoria(
                sub="test_v2e5.TestAdaptadores.test_otra_prueba_con_la_misma_linea")),
        }
        for nombre, texto in casos.items():
            with self.subTest(nombre):
                n = texto.count("\n" + "=" * 70)
                firma = f"{7 if 'Ran 7' in texto else 6}/{7 if 'Ran 7' in texto else 6} ejecutadas; failures={n}"
                self.assertIsNone(LB.explicar_inestable(diferencia(firma), esperado(), {"V-CON-11": texto}))
        with self.subTest("la traza y la firma no coinciden en el número de pruebas"):
            texto = traza(*conocidos, memoria(), ran=7)
            self.assertIsNone(LB.explicar_inestable(diferencia("6/6 ejecutadas; failures=3"), esperado(),
                                                    {"V-CON-11": texto}))

    def test_sin_declaracion_traza_o_firma_coherente_no_se_explica(self):
        t = {"V-CON-11": INTENTO1}
        self.assertIsNone(LB.explicar_inestable(diferencia(), esperado(decls=()), t))
        otra = dict(DECL, prueba="V-CON-12")
        self.assertIsNone(LB.explicar_inestable(diferencia(), esperado(decls=(otra,)), t))
        self.assertIsNone(LB.explicar_inestable(diferencia(), esperado(), {}))
        self.assertIsNone(LB.explicar_inestable(diferencia("6/6 ejecutadas; failures=3"), esperado(), t))
        self.assertIsNone(LB.explicar_inestable(diferencia("5/6 ejecutadas; failures=4"), esperado(), t))
        self.assertIsNone(LB.explicar_inestable(dict(diferencia(), veredicto="AUSENTE"), esperado(), t))
        self.assertIsNone(LB.explicar_inestable(dict(diferencia(), real={"estado": "ERROR", "firma": "x"}),
                                                esperado(), t))
        self.assertIsNone(LB.explicar_inestable(diferencia(), esperado(firma="7/7 ejecutadas; failures=2"), t))


class _Ejecucion:
    def __init__(self, rc, stderr):
        self.returncode, self.stdout, self.stderr = rc, "", stderr


OK1 = "\n.\n----------------------------------------------------------------------\nRan 1 test in 0.1s\n\nOK\n"


def falla(*bloques):
    return traza(*bloques, ran=1)


class TestConfirmar(unittest.TestCase):
    def _confirmar(self, salidas, decl=DECL):
        it = iter(salidas)
        t = Path(tempfile.mkdtemp(prefix="eq3_inest_"))
        self.addCleanup(shutil.rmtree, t, True)
        return LB.confirmar_inestable(decl, Path("/no/se/usa"), t, ejecutar=lambda *a, **k: next(it))

    def test_mayoria_estricta(self):
        f = _Ejecucion(1, falla(memoria()))
        o = _Ejecucion(0, OK1)
        self.assertTrue(self._confirmar([o] * 5)["confirmada"])
        self.assertTrue(self._confirmar([o, f, o, f, o])["confirmada"])
        r = self._confirmar([f, o, f, f, o])
        self.assertFalse(r["confirmada"])
        self.assertIn("solo 2 de 5", r["motivo"])

    def test_un_fallo_distinto_la_descarta_al_momento(self):
        o = _Ejecucion(0, OK1)
        distintos = {
            "otro mensaje": _Ejecucion(1, falla(memoria(a=1, b=1 * 1024 * 1024))),
            "error": _Ejecucion(1, falla(memoria(header="ERROR"))),
            "no se ejecutó ninguna prueba": _Ejecucion(0, "\nRan 0 tests in 0.0s\n\nNO TESTS RAN\n"),
            "rc distinto de cero sin fallos": _Ejecucion(1, "Traceback\nImportError: x\n"),
            "se ejecutaron otras pruebas": _Ejecucion(0, OK1.replace("Ran 1 test", "Ran 2 tests")),
        }
        for nombre, e in distintos.items():
            with self.subTest(nombre):
                r = self._confirmar([o, e, o, o, o])
                self.assertFalse(r["confirmada"])
                self.assertEqual(r["repeticiones"], 2)
                self.assertIn("fallo distinto", r["motivo"])


class TestRevisarYCodigo(unittest.TestCase):
    def _cmp(self, confirmada):
        t = Path(tempfile.mkdtemp(prefix="eq3_inest_"))
        self.addCleanup(shutil.rmtree, t, True)
        d = t / "tmp_verificador" / "x" / "verificacion" / "id" / "trazas"
        d.mkdir(parents=True)
        (d / "V-CON-11.txt").write_text(INTENTO1, encoding="utf-8")
        cmp_ = {"totales": {v: 0 for v in LB.VEREDICTOS}, "diferencias": [diferencia()]}
        cmp_["totales"].update(IGUAL=502, CAMBIO=1)
        LB.revisar_inestables(cmp_, esperado(), t, Path("/s"),
                              confirmar=lambda *a: {"confirmada": confirmada, "correctas": 4, "repeticiones": 5,
                                                    "motivo": None if confirmada else "solo 2 de 5"})
        return cmp_

    def test_confirmada_pasa_a_inestable_y_sale_con_4_visible(self):
        cmp_ = self._cmp(True)
        self.assertEqual(cmp_["diferencias"][0]["veredicto"], LB.INESTABLE)
        self.assertEqual(cmp_["diferencias"][0]["veredicto_sin_inestabilidad"], "CAMBIO")
        self.assertEqual((cmp_["totales"]["CAMBIO"], cmp_["totales"][LB.INESTABLE]), (0, 1))
        self.assertEqual(LB.codigo_salida(cmp_["totales"]), 4)

    def test_no_confirmada_conserva_el_cambio_y_la_puerta_falla(self):
        cmp_ = self._cmp(False)
        self.assertEqual(cmp_["diferencias"][0]["veredicto"], "CAMBIO")
        self.assertIn("inestabilidad", cmp_["diferencias"][0])
        self.assertEqual(LB.codigo_salida(cmp_["totales"]), 1)

    def test_inestable_no_oculta_ninguna_otra_diferencia(self):
        tot = {v: 0 for v in LB.VEREDICTOS}
        for v in ("REGRESION", "CAMBIO", "AUSENTE"):
            self.assertEqual(LB.codigo_salida(dict(tot, **{v: 1, LB.INESTABLE: 3})), 1)
        self.assertEqual(LB.codigo_salida(dict(tot, MEJORA=1, **{LB.INESTABLE: 1})), 3)


class TestValidacion(unittest.TestCase):
    def test_la_linea_base_de_windows_es_valida(self):
        esp = json.loads(LB.ESPERADA_WINDOWS.read_text(encoding="utf-8"))
        self.assertEqual(LB.validar_esperada(esp), [])
        self.assertEqual([d["id"] for d in esp["inestables"]], [DECL["id"]])

    def test_declaraciones_mal_formadas_se_rechazan(self):
        malas = {
            "faltan campos": {k: v for k, v in DECL.items() if k != "codigo"},
            "mayoría no estricta": dict(DECL, repeticiones=4, minimo_ok=2),
            "pocas repeticiones": dict(DECL, repeticiones=2, minimo_ok=2),
            "tolerancia nula": dict(DECL, max_diferencia_kB=0),
            "tolerancia no entera": dict(DECL, max_diferencia_kB="32768"),
            "causa no declarada": dict(DECL, causa="OTRA"),
            "causa sin clasificar": dict(DECL, causa=LB.SIN_CLASIFICAR),
            "prueba ausente": dict(DECL, prueba="V-NO-00"),
            "suite sin trazas": dict(DECL, suite="codex"),
            "patrón con un número": dict(DECL, patron=r"AssertionError: (\d+)"),
            "patrón inválido": dict(DECL, patron="(("),
        }
        for nombre, d in malas.items():
            with self.subTest(nombre):
                esp = esperado(decls=(d,))
                esp["causas"][LB.SIN_CLASIFICAR] = "colada"
                self.assertTrue(LB.problemas_inestables(esp), nombre)
        self.assertEqual(LB.problemas_inestables(esperado()), [])
        self.assertTrue(LB.problemas_inestables(esperado(decls=(DECL, DECL))))          # id repetido


@unittest.skipUnless(LB.plataforma.WINDOWS, "PLATAFORMA: la inestabilidad declarada es la de la memoria real de Windows")
class TestRepeticionReal(unittest.TestCase):
    """La subprueba REAL de V2-F.1, por el lanzador y con las opciones del verificador."""

    def _sistema_mutado(self, viejo, nuevo):
        t = Path(tempfile.mkdtemp(prefix="eq3_inest_sis_"))
        self.addCleanup(shutil.rmtree, t, True)
        copia = t / "sistema"
        shutil.copytree(LB.SISTEMA, copia, ignore=shutil.ignore_patterns("__pycache__"))
        f = copia / "src" / "eq2" / "plataforma.py"
        src = f.read_text(encoding="utf-8")
        self.assertEqual(src.count(viejo), 1)
        f.write_text(src.replace(viejo, nuevo), encoding="utf-8")
        return copia, t

    def test_sin_cambios_ningun_fallo_distinto_del_declarado(self):
        t = Path(tempfile.mkdtemp(prefix="eq3_inest_"))
        self.addCleanup(shutil.rmtree, t, True)
        r = LB.confirmar_inestable(DECL, LB.SISTEMA, t)
        self.assertTrue(r["motivo"] is None or r["motivo"].startswith("solo "), r)

    def test_regresion_real_desplazamiento_constante_de_4_kB_no_se_acepta(self):
        # La regresión más difícil: el mismo mensaje y DENTRO de la tolerancia, pero en TODAS las repeticiones.
        copia, t = self._sistema_mutado("        return leer_mem_available()\n",
                                        "        return leer_mem_available() - 4\n")
        r = LB.confirmar_inestable(DECL, copia, t)
        self.assertFalse(r["confirmada"], r)
        self.assertEqual(r["correctas"], 0)

    def test_regresion_real_error_de_unidades_no_se_acepta(self):
        copia, t = self._sistema_mutado("        return leer_mem_available()\n",
                                        "        return leer_mem_available() * 1024\n")
        r = LB.confirmar_inestable(DECL, copia, t)
        self.assertFalse(r["confirmada"], r)
        self.assertIn("fallo distinto", r["motivo"])


if __name__ == "__main__":
    unittest.main()
