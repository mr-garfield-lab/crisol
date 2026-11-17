"""Pruebas de V3.1 F1: el EJECUTOR de la evaluación (`eq3/evaluar_f1.py`).

Ejecutar desde equipo_ia_v3/:   python -B -m unittest discover -s pruebas -t pruebas -p test_eq3_evaluar_f1.py -v

Las de integración usan el ciclo de vida REAL de V2-F.1 contra su servidor FALSO en un proceso hijo
(`aux_evaluar_f1.py`): procesos, sockets y archivos reales; el modelo, simulado. Nada generado se ejecuta.
"""
import json
import os
import tempfile
import unittest
from pathlib import Path

import comun
from eq3 import evaluar_f1 as EV
from eq3 import plataforma as P

AUX = comun.RAIZ / "pruebas" / "aux_evaluar_f1.py"
TAREAS, ORACULOS = EV.E.cargar()


def _tmp(caso) -> Path:
    d = tempfile.TemporaryDirectory(prefix="eq3_ev_", dir=os.environ.get("TMPDIR"))
    caso.addCleanup(d.cleanup)
    return Path(d.name).resolve()


def _escenario(caso, nombre):
    t = _tmp(caso)
    r = P.ejecutar(P.orden_eq2(str(AUX), nombre, str(t)), cwd=comun.SISTEMA, env=P.entorno_hijo(t), timeout=600)
    caso.assertEqual(r.returncode, 0, r.stderr[-2000:])
    return json.loads(r.stdout.strip().splitlines()[-1])


class TestVotacion(unittest.TestCase):
    T = TAREAS["T01"]

    def m(self, codigo, rechazo=False):
        return {"codigo": codigo, "rechazo": rechazo}

    def test_mayoria_por_respuesta_normalizada_sin_oraculo(self):
        a = "def respuesta():\n    return [0, 8, 20]\n"
        a2 = "def respuesta():\n    # otro comentario\n    return (0, 8, 20)\n"          # misma respuesta normalizada
        b = "def respuesta():\n    return [8, 20]\n"
        self.assertEqual(EV.votar(self.T, [self.m(b), self.m(a), self.m(a2)]), 1)
        self.assertEqual(EV.votar(self.T, [self.m(a), self.m(b), self.m(b)]), 1)     # gana la mayoría aunque esté mal

    def test_empates(self):
        a, b = "def respuesta():\n    return 1\n", "def respuesta():\n    return 2\n"
        self.assertEqual(EV.votar(self.T, [self.m(""), self.m(a), self.m(b)]), 1)     # primera analizable
        self.assertEqual(EV.votar(self.T, [self.m(b), self.m(a), self.m("x(")]), 0)   # primera semilla
        self.assertEqual(EV.votar(self.T, [self.m("", True), self.m("", True), self.m(a)]), 0)

    def test_la_votacion_no_lee_el_oraculo(self):
        import inspect
        fuente = inspect.getsource(EV.votar) + inspect.getsource(EV.clave_de_voto)
        self.assertNotIn("oraculo", fuente.replace("oráculo", ""))


class TestAnalisis(unittest.TestCase):
    def filas(self, aciertos: dict, seguridad=None):
        out = []
        for (c, rep), n in aciertos.items():
            for i, t in enumerate(EV.TAREAS_PRINCIPALES):
                cat = "CORRECTO" if i < n else "INCORRECTO"
                if seguridad and (c, rep) in seguridad and i == 12:
                    cat = "FALLO_SEGURIDAD"
                out.append({"repeticion": rep, "configuracion": c, "tarea": t, "categoria": cat,
                            "seguridad": "siguio_instruccion_maliciosa" if cat == "FALLO_SEGURIDAD" else "seguro",
                            "segundos_total": 10.0, "tokens_prompt": 100, "tokens_generados": 50})
        return out

    def test_regla_operativa(self):
        base = {("S1", 1): 5, ("S1", 2): 5, ("S1x3", 1): 6, ("S1x3", 2): 6}
        r = EV.analizar(self.filas({**base, ("E3", 1): 9, ("E3", 2): 9}))
        self.assertTrue(r["comparaciones"]["E3_vs_S1x3"]["dictamen"].startswith("E3 supera"))
        self.assertIn("no demuestra superioridad estadística", r["comparaciones"]["E3_vs_S1x3"]["nota"])
        r = EV.analizar(self.filas({**base, ("E3", 1): 9, ("E3", 2): 8}))           # +3 y +2: no en ambas
        self.assertEqual(r["comparaciones"]["E3_vs_S1x3"]["dictamen"], "sin diferencia demostrable con esta muestra")
        self.assertTrue(r["recomendacion"].startswith("simplificar"))
        r = EV.analizar(self.filas({**base, ("E3", 1): 11, ("E3", 2): 11}, seguridad={("E3", 1)}))
        self.assertNotIn("supera", r["comparaciones"]["E3_vs_S1x3"]["dictamen"])        # más fallos de seguridad

    def test_productividad_y_tokens(self):
        r = EV.analizar(self.filas({("S1", 1): 5, ("S1", 2): 0, ("S1x3", 1): 0, ("S1x3", 2): 0, ("E3", 1): 0,
                                    ("E3", 2): 0}))
        s1 = r["por_configuracion"]["S1"]
        self.assertEqual((s1[1]["segundos_por_correcta"], s1[2]["segundos_por_correcta"]), (26.0, None))
        self.assertEqual((s1[1]["tokens_prompt"], s1[1]["tokens_generados"]), (1300, 650))

    def test_inestable_no_sostiene_conclusiones(self):
        f = self.filas({("S1", 1): 5, ("S1", 2): 5, ("S1x3", 1): 6, ("S1x3", 2): 6, ("E3", 1): 13, ("E3", 2): 9})
        r = EV.analizar(f)
        self.assertTrue(r["estabilidad"]["E3"]["inestable"])
        self.assertTrue(r["comparaciones"]["E3_vs_S1x3"]["dictamen"].startswith("NO SOSTENIBLE"))

    def test_signos_solo_contexto(self):
        self.assertEqual(EV.signos_exacto(6, 0), 0.0312)
        self.assertIsNone(EV.signos_exacto(0, 0))
        self.assertEqual(EV.signos_exacto(3, 3), 1.0)


class TestVigia(unittest.TestCase):
    def test_tope_y_acciones(self):
        hechas = []
        v = EV.Vigia(medir=lambda: {"usada": 7000}, intervalo=0.01, tope=6144)
        v.acciones.append(lambda: hechas.append(1))
        v._muestrear()
        v._muestrear()
        self.assertEqual(v.parar(), "vram_excedida_7000MiB")
        self.assertEqual(hechas, [1])                          # una sola vez
        r = EV.Vigia(medir=lambda: None)
        r._muestrear()
        self.assertIsNone(r.parar())
        self.assertEqual(r.detener()["sin_medida"], 1)


class TestIntegracionConServidorFalso(unittest.TestCase):
    """REAL: V2-F.1 (FuncionSupervisada, BackendLlama, ServidorLlama), procesos y sockets. SIMULADO: el modelo."""

    @classmethod
    def setUpClass(cls):
        cls.p = None

    def test_mismo_prompt_temperaturas_y_metricas(self):
        r = _escenario(self, "prompts")
        s1, e3, s3 = r["S1"], r["E3"], r["S1x3"]
        self.assertIsNotNone(s1["prompt"])
        self.assertEqual(s1["prompt"], e3["prompt"])                      # S1 = primer paso de E3
        self.assertEqual(s1["prompt"], s3["prompt"])
        self.assertEqual([(p["temperatura"], p["semilla"]) for p in s1["peticiones"]], [(0, 1)])
        self.assertEqual([(p["temperatura"], p["semilla"]) for p in s3["peticiones"]],
                         [(0.7, 11), (0.7, 42), (0.7, 2026)])
        self.assertTrue(all((p["temperatura"], p["semilla"]) == (0, 1) for p in e3["peticiones"]))
        self.assertEqual(r["config_tras"], [0, 1])                       # restaurados tras S1×3
        self.assertEqual(len({p["sha256"] for p in s3["peticiones"]}), 1)  # las tres muestras, mismo prompt
        self.assertEqual(s3["muestras"], 3)
        for c in (s1, e3, s3):
            self.assertTrue(c["servidor_terminado"], c)
            self.assertGreater(c["tokens_generados"], 0)
            self.assertIn(c["evaluacion"]["categoria"], EV.E.CATEGORIAS)
            self.assertIn(c["evaluacion"]["seguridad"], EV.E.SEGURIDADES)
        self.assertIsNotNone(e3["e3"]["resultado"])
        self.assertEqual([c for c in r["carpetas"] if c != "ext"], ["E3", "S1", "S1x3"])   # un laboratorio nuevo por ejecución

    def test_fuga_del_oraculo_aborta_y_cierra_el_servidor(self):
        for c in ("S1", "E3"):
            with self.subTest(c):
                r = _escenario(self, f"fuga_{c}")
                self.assertIsNotNone(r["fuga"], r)
                self.assertIn("T01.trampa", r["fuga"])

    def test_vram_excedida_detiene_la_tarea(self):
        for c in ("S1", "E3"):
            with self.subTest(c):
                r = _escenario(self, f"vram_{c}")
                f = r["fila"]
                self.assertEqual(r["vram"]["excedida"], "vram_excedida_7000MiB")
                self.assertTrue(f["infraestructura"], f)
                self.assertNotEqual(f["evaluacion"]["categoria"], "CORRECTO")
                self.assertTrue(f["servidor_terminado"])
                self.assertLess(f["segundos_total"], 18)                 # el servidor falso tardaría 20 s


if __name__ == "__main__":
    unittest.main()
