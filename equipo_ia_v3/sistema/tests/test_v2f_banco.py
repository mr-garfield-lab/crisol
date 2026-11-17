"""V2-F: banco comparativo (un agente frente al equipo). Las variantes de código y los casos del banco se comprueban
EJECUTÁNDOLOS; el modo simulado usa la política parametrizada (no Qwen) con ejecuciones REALES."""
import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import _comun
from eq2 import banco_capacidades as B, casos as C, debate, herramientas as H, motor_v2f, rutas
from eq2.inferencia import BackendSimulado

RAIZ = _comun.RAIZ
CARPETA = RAIZ / "bancos" / "capacidades_v1"


class TestDatosDelBanco(unittest.TestCase):
    """El banco no se cree: se comprueba ejecutando cada variante y cada caso."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = _comun.carpeta_temporal()
        d = Path(cls.tmp.name)
        cls.lab = rutas.Laboratorio(d, d / "lab")
        cls.lab.crear_base()
        cls.banco = B.cargar(CARPETA)
        cls.desp = H.Despachador(cls.lab, ("datos",), autorizado=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_variantes_oraculos_y_casos_coinciden_con_sus_etiquetas(self):
        for t in self.banco["tareas"]:
            sim = self.banco["simulacion"]["tareas"][t["id"]]
            ora = self.banco["oraculos"][t["id"]]
            ej = C.con_ids(C.ejemplos_del_enunciado(t["instrucciones"]), "E")
            pool = [C.parsear_expresion(c["caso"], "A1", f"K{i}") for i, c in enumerate(sim["casos_agentes"], 1)]
            self.assertTrue(ej, t["id"])                                    # cada tarea lleva un ejemplo visible
            claves = [c.clave() for c in ora + ej + pool]
            self.assertEqual(len(claves), len(set(claves)), f"{t['id']}: oráculo, ejemplos y casos deben ser disjuntos")
            res = {}
            for v, info in sim["variantes"].items():
                r = self.desp.ejecutar_casos({"solucion.py": info["codigo"]}, ora + ej + pool)
                res[v] = {k: x["estado"] for k, x in r["por_caso"].items()}
                falla = sorted(c.clave() for c in ora if res[v][c.id] != "pasa")
                self.assertEqual(falla, info["falla_oraculo"], f"{t['id']}/{v}")
                self.assertEqual(bool(falla), not info["correcta"], f"{t['id']}/{v}")
            self.assertTrue(all(res["correcta"][c.id] == "pasa" for c in ej), t["id"])
            for c, info in zip(pool, sim["casos_agentes"]):
                self.assertEqual(res["correcta"][c.id] == "pasa", info["correcto"], f"{t['id']}: {c.clave()}")
                detecta = sorted(v for v in sim["variantes"] if v != "correcta" and res[v][c.id] != "pasa") \
                    if info["correcto"] else []
                self.assertEqual(detecta, info["detecta"], f"{t['id']}: {c.clave()}")

    def test_carga_y_huella(self):
        b2 = B.cargar(CARPETA)
        self.assertEqual(b2["sha256"], self.banco["sha256"])
        self.assertEqual(len(b2["tareas"]), 8)
        self.assertTrue(all(len(t["instrucciones"]) <= 600 for t in b2["tareas"]))


class TestIdentificacionDePasos(unittest.TestCase):
    def test_los_prompts_reales_se_reconocen(self):
        vistos = []

        def guion(n, fase, mensajes, max_tokens):
            vistos.append(B.identificar(mensajes))
            return "x"
        be = BackendSimulado(guion)
        ad = debate.AgentesDebateLLM(be)
        for ag in ("A1", "A2", "A3"):
            ad.proponer(ag, "Tarea")
            ad.cuestionar(ag, "Tarea", "ev", "props")
            ad.reparar(ag, "Tarea", "cod", "ev")
        am = motor_v2f.AgentesMotorLLMV2F(be)
        am.planificar("T")
        am.generar("T", "plan")
        am.escribir_pruebas("T", "plan", "cod")
        am.revisar("T", "plan", "cod")
        am.evaluar("T", "res")
        am.corregir("T", "plan", "cod", "diag")
        am.replanificar("T", "plan", "ev", "pruebas")
        am.auditar("T", "ev")
        esperado = [(f"{p}_{a.lower()}", a) for a in ("A1", "A2", "A3") for p in ("propuesta", "cuestionar", "reparar")] + \
            [("planificar", "A2"), ("generar", "A1"), ("pruebas", "A2"), ("revisar", "A3"), ("evaluar", "A2"),
             ("corregir", "A1"), ("replanificar", "A2"), ("auditar", "A3")]
        self.assertEqual(vistos, esperado)


class TestBancoSimulado(unittest.TestCase):
    TAREAS = ["mediana", "dedup"]

    def setUp(self):
        tmp = _comun.carpeta_temporal()
        self.addCleanup(tmp.cleanup)
        d = Path(tmp.name) / "equipo_f2"
        d.mkdir()
        self.lab = rutas.Laboratorio(d, d / "lab_v2f1")  # CAMBIO V2-F.1 (V2-F: lab_v2f)
        self.lab.crear_base()
        self.banco = B.cargar(CARPETA)
        self.params = {k: v for k, v in self.banco["simulacion"]["parametros"].items() if k != "explicacion"}

    def correr(self, semilla, nombre, autorizado=True):
        backends = []

        def crear(t, modo):
            be = B.BackendGuion(B.PoliticaSimulada(self.banco["simulacion"]["tareas"][t["id"]], t, semilla, modo,
                                                   self.params))
            backends.append(be)
            return be
        bc = B.Banco(self.lab, ("banco", nombre), self.banco, autorizado=autorizado, crear_backend=crear, simulado=True,
                     semilla=semilla, parametros=self.params)
        filas = bc.ejecutar(B.MODOS, self.TAREAS)
        return B.informe(self.banco, filas, {"simulado": True, "parametros": self.params}), backends

    def test_informe_completo_reproducible_y_sin_fugas_del_oraculo(self):
        inf, backends = self.correr(11, "a")
        self.assertEqual(len(inf["filas"]), len(self.TAREAS) * len(B.MODOS))
        self.assertEqual(set(inf["por_modo"]), set(B.MODOS))
        for f in inf["filas"]:
            self.assertIsNone(f["error"], f)
            self.assertFalse(f["tokens_medidos"])
            self.assertEqual(f["falsa_certeza"], f["afirma_exito"] and not f["correcta"])
            self.assertGreater(f["llamadas"], 0)
        llam = {m: d["llamadas_media"] for m, d in inf["por_modo"].items()}
        self.assertEqual(llam["individual"], 1.0)
        self.assertGreaterEqual(llam["equipo_debate"], 6)
        oraculo = [c.clave() for t in self.TAREAS for c in self.banco["oraculos"][t]]
        textos = [p["texto"] for be in backends for p in be.prompts]
        self.assertTrue(textos)
        for o in oraculo:                                       # ningún caso oculto llega nunca a un prompt
            self.assertFalse(any(o in x for x in textos), o)
        inf2, _ = self.correr(11, "b")
        self.assertEqual(inf["huella_decisiones"], inf2["huella_decisiones"])          # misma semilla, mismo resultado
        md = B.texto_md(inf)
        self.assertIn("SIMULADO", md)
        self.assertIn("Frente a «individual»", md)
        self.assertTrue(self.lab.ruta("banco", "a", "por_ejecucion.jsonl").is_file())
        # comparar: mismo banco -> sin aviso; banco distinto -> aviso
        self.assertEqual(B.comparar_informes(inf, inf2)["avisos"], [])
        otro = dict(inf2, banco_sha256="0" * 64)
        self.assertTrue(B.comparar_informes(inf, otro)["avisos"])

    def test_sin_autorizacion_no_se_ejecuta(self):
        with self.assertRaises(PermissionError):
            self.correr(11, "c", autorizado=False)

    def test_semillas_distintas_cambian_el_caso_no_el_banco(self):
        a, _ = self.correr(11, "d")
        b, _ = self.correr(42, "e")
        self.assertEqual(a["banco_sha256"], b["banco_sha256"])
        self.assertNotEqual(a["semillas"], b["semillas"])


class TestCLI(unittest.TestCase):
    def test_lista_y_autorizacion(self):
        import sys
        if str(RAIZ) not in sys.path:
            sys.path.insert(0, str(RAIZ))
        import banco as cli
        f = io.StringIO()
        with redirect_stdout(f):
            self.assertEqual(cli.main(["lista"]), 0)
        self.assertIn("mediana", f.getvalue())
        tmp = _comun.carpeta_temporal()
        self.addCleanup(tmp.cleanup)
        import os
        viejo = os.environ.get("TMPDIR")
        os.environ["TMPDIR"] = tmp.name
        try:
            with redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(["simular", "--tareas", "mediana"]), 2)       # sin --autorizo-pruebas
            self.assertFalse(Path(tmp.name, "equipo_f2").exists())                     # nada creado
            for malo, msg in ((["--parametro", "p_inventado=0.5"], "desconocido"), (["--parametro", "p_reparar=2"], "entre 0 y 1"),
                              (["--parametro", "p_reparar=x"], "no numérico")):
                with self.assertRaises(SystemExit) as cm, redirect_stdout(io.StringIO()):
                    cli.main(["simular", "--autorizo-pruebas", "--tareas", "mediana", "--modos", "individual"] + malo)
                self.assertIn(msg, str(cm.exception))
            with redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(["simular", "--autorizo-pruebas", "--tareas", "mediana", "--modos", "individual",
                                           "--solo-semillas", "--semilla", "5", "--parametro", "p_reparar=0.2"]), 0)
            inf = json.loads(next(Path(tmp.name, "equipo_f2").rglob("informe.json")).read_text(encoding="utf-8"))
            self.assertEqual((inf["contexto"]["parametros"]["p_reparar"], inf["semillas"]), (0.2, [5]))
        finally:
            if viejo is None:
                os.environ.pop("TMPDIR", None)
            else:
                os.environ["TMPDIR"] = viejo


if __name__ == "__main__":
    unittest.main()
