"""Pruebas de V3.1 F0.5: la línea base de otra plataforma solo admite diferencias con causa, regla y evidencia."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

V3 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V3))
import linea_base as LB  # noqa: E402
import linea_base_plataforma as LP  # noqa: E402

LINUX = {"causas": {"C": "causa de Linux"}, "suites": {"codex": {"pruebas": {
    "m.T.a": {"estado": "OK"}, "m.T.b": {"estado": "ERROR", "firma": "F", "causa": "C"},
    "m.T.c": {"estado": "OK"}, "m.T.e": {"estado": "ERROR", "firma": "G", "causa": "C"}}}}}
CAUSAS = {"plataforma": "windows", "causas": {"WIN_ENLACE": "sin privilegio de symlinks"},
          "reglas": [{"causa": "WIN_ENLACE", "patron": r"WinError 1314"}]}


def _estados(**cambios):
    e = {"m.T.a": {"estado": "OK", "firma": ""}, "m.T.b": {"estado": "ERROR", "firma": "F"},
         "m.T.c": {"estado": "ERROR", "firma": "OSError: [WinError 1314] privilegio"},
         "m.T.e": {"estado": "OK", "firma": ""}}
    e.update(cambios)
    return {"codex": {k: v for k, v in e.items() if v is not None}}


class TestDerivar(unittest.TestCase):
    def test_conserva_lo_igual_clasifica_lo_distinto_y_anota_mejoras(self):
        d, sin, aus = LP.derivar(LINUX, _estados(), CAUSAS, {}, "windows")
        p = d["suites"]["codex"]["pruebas"]
        self.assertEqual((sin, aus), ([], []))
        self.assertEqual(p["m.T.b"]["causa"], "C")                                 # igual que en Linux
        self.assertEqual((p["m.T.c"]["causa"], p["m.T.c"]["regla"]), ("WIN_ENLACE", 0))
        self.assertIn("WinError 1314", p["m.T.c"]["evidencia"])
        self.assertEqual(p["m.T.c"]["linux"]["estado"], "OK")                     # se ve qué era en Linux
        self.assertEqual(d["mejoras_de_plataforma"], ["codex: m.T.e"])            # una mejora no se oculta
        self.assertEqual(LB.validar_esperada(d, ("codex",)), [])                  # la puerta la acepta

    def test_sin_regla_queda_sin_clasificar(self):
        _, sin, _ = LP.derivar(LINUX, _estados(**{"m.T.d": {"estado": "FALLO", "firma": "AssertionError: x"}}),
                               CAUSAS, {}, "windows")
        self.assertEqual(len(sin), 1)
        self.assertIn("m.T.d", sin[0])

    def test_misma_prueba_que_falla_de_otra_manera_no_hereda_la_causa_de_linux(self):
        _, sin, _ = LP.derivar(LINUX, _estados(**{"m.T.b": {"estado": "ERROR", "firma": "otra"}}), CAUSAS, {},
                               "windows")
        self.assertEqual(len(sin), 1)

    def test_cada_subprueba_necesita_su_propia_evidencia(self):
        ev = {"codex": {"m.T.c": ["t1\nOSError: [WinError 1314] x", "t2\nAssertionError: otra cosa"]}}
        d, sin, _ = LP.derivar(LINUX, _estados(), CAUSAS, ev, "windows")
        self.assertEqual(len(sin), 1)                                              # t2 no tiene regla
        self.assertEqual(d["suites"]["codex"]["pruebas"]["m.T.c"]["sin_explicar"][0]["subprueba"], "t2")
        ev["codex"]["m.T.c"] = ["t1\nOSError: [WinError 1314] x", "t2\nPermissionError [WinError 1314]"]
        _, sin, _ = LP.derivar(LINUX, _estados(), CAUSAS, ev, "windows")
        self.assertEqual(sin, [])

    def test_fallo_funcional_con_causa_sigue_bloqueando(self):
        cat = {**CAUSAS, "causas": {**CAUSAS["causas"], "FUNCIONAL": "defecto demostrado"},
               "reglas": CAUSAS["reglas"] + [{"causa": "FUNCIONAL", "patron": "etiqueta distinta", "bloquea": True}]}
        d, sin, _ = LP.derivar(LINUX, _estados(**{"m.T.a": {"estado": "FALLO", "firma": "etiqueta distinta"}}),
                               cat, {}, "windows")
        self.assertEqual(d["suites"]["codex"]["pruebas"]["m.T.a"]["bloquea"], ["FUNCIONAL"])
        self.assertTrue(any("BLOQUEA" in s for s in sin))                         # explicado, pero NO aceptado

    def test_agregado_solo_si_todo_lo_demas_esta_explicado(self):
        cat = {**CAUSAS, "causas": {**CAUSAS["causas"], "AGREGADO": "resumen"},
               "reglas": CAUSAS["reglas"] + [{"causa": "AGREGADO", "patron": "^resumen", "solo_si_todo_explicado": True}]}
        cum = {"m.T.f": {"estado": "FALLO", "firma": "resumen 3 FALLO"}}
        d, sin, _ = LP.derivar(LINUX, _estados(**cum), cat, {}, "windows")
        self.assertEqual((sin, d["suites"]["codex"]["pruebas"]["m.T.f"]["causa"]), ([], "AGREGADO"))
        _, sin, _ = LP.derivar(LINUX, _estados(**cum, **{"m.T.g": {"estado": "FALLO", "firma": "sin regla"}}),
                               cat, {}, "windows")
        self.assertEqual(len(sin), 2)                                              # el agregado tampoco se acepta

    def test_ausente_no_se_clasifica(self):
        _, _, aus = LP.derivar(LINUX, _estados(**{"m.T.a": None}), CAUSAS, {}, "windows")
        self.assertEqual(aus, ["codex: m.T.a"])

    def test_catalogo_invalido(self):
        for malo in ({**CAUSAS, "causas": {"C": "choca con Linux"}, "reglas": []},
                     {**CAUSAS, "reglas": [{"causa": "NO_DECLARADA", "patron": "x"}]}):
            with self.subTest(malo=malo), self.assertRaises(ValueError):
                LP.derivar(LINUX, _estados(), malo, {}, "windows")

    def test_la_evidencia_sale_del_registro_de_unittest(self):
        registro = ("ERROR: test_d (m.T.d)\n" + "-" * 70 + "\nTraceback...\nOSError: [WinError 1314] x\n" + "=" * 70
                    + "\nFAIL: test_z (m.T.z)\nAssertionError\n")
        b = LP._bloques_unittest(registro)
        self.assertIn("WinError 1314", b["m.T.d"])
        self.assertNotIn("WinError", b["m.T.z"])
        d, sin, _ = LP.derivar(LINUX, _estados(**{"m.T.d": {"estado": "ERROR", "firma": "OSError: x"}}), CAUSAS,
                               {"codex": b}, "windows")
        self.assertEqual((sin, d["suites"]["codex"]["pruebas"]["m.T.d"]["causa"]), ([], "WIN_ENLACE"))


class TestMain(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory(prefix="eq3_lbp_", dir=os.environ.get("TMPDIR"))
        self.addCleanup(d.cleanup)
        self.t = Path(d.name)
        (self.t / "linux.json").write_text(json.dumps(LINUX), encoding="utf-8")
        (self.t / "causas.json").write_text(json.dumps(CAUSAS), encoding="utf-8")
        (self.t / "ejec").mkdir()
        (self.t / "ejec" / "estados.json").write_text(json.dumps(_estados()), encoding="utf-8")

    def _main(self, salida):
        return LP.main(["--ejecucion", str(self.t / "ejec"), "--causas", str(self.t / "causas.json"),
                        "--salida", str(salida), "--linux", str(self.t / "linux.json")])

    def test_escribe_y_nunca_sobrescribe(self):
        s = self.t / "windows.json"
        self.assertEqual(self._main(s), 0)
        d = json.loads(s.read_text(encoding="utf-8"))
        self.assertEqual((d["plataforma"], d["derivada_de"]["archivo"]), ("windows", "linux.json"))
        antes = s.read_bytes()
        self.assertEqual(self._main(s), 2)
        self.assertEqual(s.read_bytes(), antes)

    def test_parcial_lo_no_explicado_sigue_siendo_bloqueante(self):
        (self.t / "ejec" / "estados.json").write_text(
            json.dumps(_estados(**{"m.T.a": {"estado": "FALLO", "firma": "x"}})), encoding="utf-8")
        s = self.t / "w.json"
        self.assertEqual(LP.main(["--ejecucion", str(self.t / "ejec"), "--causas", str(self.t / "causas.json"),
                                  "--salida", str(s), "--linux", str(self.t / "linux.json"), "--parcial"]), 0)
        d = json.loads(s.read_text(encoding="utf-8"))
        self.assertEqual(d["suites"]["codex"]["pruebas"]["m.T.a"], {"estado": "OK"})   # se sigue esperando OK
        self.assertEqual(len(d["bloqueantes_sin_explicar"]), 1)
        self.assertEqual(d["suites"]["codex"]["pruebas"]["m.T.c"]["causa"], "WIN_ENLACE")   # lo justificado sí entra
        cmp_ = LB.comparar({"codex": {"pruebas": _estados(**{"m.T.a": {"estado": "FALLO", "firma": "x"}})["codex"]}}, d)
        self.assertEqual(LB.codigo_salida(cmp_["totales"]), 1)                     # la puerta sigue fallando

    def test_la_linea_base_no_contiene_rutas_de_esta_maquina(self):
        ejec = self.t / "ejec"
        (ejec / "estados.json").write_text(
            json.dumps(_estados(**{"m.T.d": {"estado": "ERROR", "firma": "OSError: x"}})), encoding="utf-8")
        (ejec / "codex.log").write_text(
            "ERROR: test_d (m.T.d)\n" + "-" * 70 + f"\nOSError: [WinError 1314] x: '{ejec / 'tmp_codex' / 'a.txt'}' -> "
            f"'{Path.home() / 'b.txt'}'\n", encoding="utf-8")
        s, rev = self.t / "w.json", self.t / "rev.json"
        self.assertEqual(LP.main(["--ejecucion", str(ejec), "--causas", str(self.t / "causas.json"), "--salida", str(s),
                                  "--linux", str(self.t / "linux.json"), "--revision", str(rev)]), 0)
        for archivo in (s, rev):
            texto = json.dumps(json.loads(archivo.read_text(encoding="utf-8")), ensure_ascii=False)
            for ruta in (str(ejec.resolve()), ejec.resolve().as_posix(), str(Path.home()), Path.home().as_posix()):
                self.assertNotIn(ruta, texto)
        ev = json.loads(s.read_text(encoding="utf-8"))["suites"]["codex"]["pruebas"]["m.T.d"]["evidencia"]
        self.assertRegex(ev, r"<SALIDA>.tmp_codex.a\.txt")                         # la evidencia sigue siendo legible
        self.assertRegex(ev, r"<CASA>.b\.txt")

    def test_una_firma_que_depende_de_la_maquina_se_rechaza(self):
        (self.t / "ejec" / "estados.json").write_text(json.dumps(_estados(**{"m.T.d": {
            "estado": "ERROR", "firma": f"OSError: [WinError 1314] {(self.t / 'ejec').resolve()}"}})), encoding="utf-8")
        self.assertEqual(self._main(self.t / "w.json"), 2)
        self.assertFalse((self.t / "w.json").exists())

    def test_sin_clasificar_no_escribe_nada(self):
        (self.t / "ejec" / "estados.json").write_text(
            json.dumps(_estados(**{"m.T.d": {"estado": "FALLO", "firma": "x"}})), encoding="utf-8")
        self.assertEqual(self._main(self.t / "w.json"), 1)
        self.assertFalse((self.t / "w.json").exists())


class TestEleccionPorPlataforma(unittest.TestCase):
    def test_linux_usa_siempre_la_referencia(self):
        if LB.plataforma.WINDOWS:
            self.assertIn(LB.esperada_por_defecto(), (LB.ESPERADA, LB.ESPERADA_WINDOWS))
        else:
            self.assertEqual(LB.esperada_por_defecto(), LB.ESPERADA)


if __name__ == "__main__":
    unittest.main()
