"""Pruebas de V3.1 F1: variante EXPERIMENTAL «F1-VRAM-EXP» (`eq3/evaluar_f1_vram_exp.py`, tope 6912 MiB).

Ejecutar desde equipo_ia_v3/:   python -B -m unittest discover -s pruebas -t pruebas -p test_eq3_evaluar_f1_vram_exp.py -v

Las unitarias simulan la VRAM, el uso de la GPU y la actividad de terceros. Las de integración usan el ciclo de vida REAL
de V2-F.1 contra su servidor FALSO en un proceso hijo (`aux_evaluar_f1_vram_exp.py`). Nada generado se ejecuta.
"""
import inspect
import json
import os
import tempfile
import unittest
from pathlib import Path

import comun
from eq3 import evaluar_f1 as EV
from eq3 import evaluar_f1_vram_exp as X
from eq3 import plataforma as P

AUX = comun.RAIZ / "pruebas" / "aux_evaluar_f1_vram_exp.py"
LIBRE = {"inactividad_s": 10_000.0, "sesiones": {"propia": 1, "consola": 1, "activas_ajenas": []}, "notificacion": 5,
         "motivos": []}


def _tmp(caso) -> Path:
    d = tempfile.TemporaryDirectory(prefix="eq3_vx_", dir=os.environ.get("TMPDIR"))
    caso.addCleanup(d.cleanup)
    return Path(d.name).resolve()


def _escenario(caso, nombre):
    t = _tmp(caso)
    r = P.ejecutar(P.orden_eq2(str(AUX), nombre, str(t)), cwd=comun.SISTEMA, env=P.entorno_hijo(t), timeout=600)
    caso.assertEqual(r.returncode, 0, r.stderr[-2000:])
    return json.loads(r.stdout.strip().splitlines()[-1])


def vram(mib):
    return lambda: {"usada": mib, "total": 8192, "procesos": {}}


class TestLimites(unittest.TestCase):
    def test_variante_separada_y_estable_intacta(self):
        self.assertEqual((X.VRAM_TOPE_EXP, X.VRAM_OTRAS_MAX_EXP), (6912, 1832))
        self.assertEqual((EV.VRAM_TOPE, EV.VRAM_OTRAS_MAX), (6144, 1500))
        self.assertEqual(EV.Vigia().tope, 6144)                    # el vigía estable no cambia
        self.assertEqual(X.VigiaExp().tope, 6912)

    def test_resultados_en_carpeta_separada(self):
        with self.assertRaises(EV.Abortada):
            X.separada(Path("t/f1ev/cmp2"))
        X.separada(Path("t/f1_vram_exp/cmp1"))

    def test_no_cierra_procesos_ajenos(self):
        fuente = inspect.getsource(X).lower()
        for prohibido in ("taskkill", "terminateprocess", ".kill(", ".terminate(", "os.kill", "stop-process"):
            self.assertNotIn(prohibido, fuente)


class TestVigiaExp(unittest.TestCase):
    def vigia(self, mib, act=lambda: LIBRE, reloj=None):
        return X.VigiaExp(medir=vram(mib), intervalo=0.01, act=act, **({"reloj": reloj} if reloj else {}))

    def test_tope_experimental(self):
        v = self.vigia(6912)
        v._muestrear()
        self.assertIsNone(v.parar())                               # justo en el tope: sigue
        hechas = []
        v = self.vigia(6913)
        v.acciones.append(lambda: hechas.append(1))
        v._muestrear()
        v._muestrear()
        self.assertEqual(v.parar(), "vram_excedida_6913MiB")
        self.assertTrue(X.por_vram(v.parar()))
        self.assertEqual(hechas, [1])

    def test_entrada_durante_la_tarea(self):
        t = [100.0]
        reloj = lambda: t[0]
        v = self.vigia(5000, act=lambda: LIBRE | {"inactividad_s": 30.0}, reloj=reloj)
        t[0] = 120.0                                               # 20 s de tarea; última entrada hace 30 s: anterior
        v._muestrear()
        self.assertIsNone(v.parar())
        t[0] = 140.0                                               # 40 s de tarea; entrada hace 30 s: DURANTE la tarea
        hechas = []
        v.acciones.append(lambda: hechas.append(1))
        v._muestrear()
        self.assertTrue(X.por_terceros(v.parar()), v.parar())
        self.assertIn("entrada_durante_la_tarea", v.parar())
        self.assertEqual(hechas, [1])
        self.assertIsNotNone(v.detener()["actividad"])

    def test_sesion_ajena_pantalla_completa_y_fallo_cerrado(self):
        casos = {"otra_sesion": LIBRE | {"motivos": ["otra_sesion_activa_[2]"]},
                 "d3d": LIBRE | {"motivos": ["pantalla_completa_d3d"]}}
        for nombre, foto in casos.items():
            with self.subTest(nombre):
                v = self.vigia(5000, act=lambda f=foto: f)
                v._muestrear()
                self.assertTrue(X.por_terceros(v.parar()))
        a = X.actividad(inactividad=lambda: None, sesiones_fn=lambda: None, notificacion_fn=lambda: None)
        self.assertEqual(a["motivos"], ["sesiones_no_medibles", "notificacion_no_medible", "inactividad_no_medible"])


class TestActividad(unittest.TestCase):
    def test_motivos(self):
        ses = {"propia": 1, "consola": 1, "activas_ajenas": []}
        self.assertEqual(X.actividad(lambda: 900.0, lambda: ses, lambda: 5)["motivos"], [])
        self.assertEqual(X.actividad(lambda: 900.0, lambda: ses | {"activas_ajenas": [3]}, lambda: 5)["motivos"],
                         ["otra_sesion_activa_[3]"])
        self.assertEqual(X.actividad(lambda: 900.0, lambda: ses | {"consola": 3}, lambda: 1)["motivos"],
                         ["consola_en_otra_sesion_3"])
        for n, m in ((2, "aplicacion_ocupada"), (3, "pantalla_completa_d3d"), (4, "modo_presentacion")):
            self.assertEqual(X.actividad(lambda: 900.0, lambda: ses, lambda n=n: n)["motivos"], [m])


class TestCondiciones(unittest.TestCase):
    def cond(self, mibs, usos=None, inact=900.0, act=None):
        it, iu = iter(mibs), iter(usos or [5] * len(mibs))
        return X.condiciones(len(mibs) * 2.0, medir=lambda: (lambda m: m and {"usada": m})(next(it)),
                             util=lambda: next(iu), act=act or (lambda: LIBRE | {"inactividad_s": inact}),
                             dormir=lambda s: None)

    def test_libre(self):
        r = self.cond([1700, 1750, 1832])
        self.assertTrue(r["ok"], r)
        self.assertEqual(len(r["vram_MiB"]), 3)

    def test_no_libre(self):
        casos = {"vram_otras_1833MiB": self.cond([1500, 1833]),
                 "vram_inestable_1000-1201MiB": self.cond([1000, 1201]),
                 "uso_gpu_41pct": self.cond([1000, 1000], usos=[10, 41]),
                 "entrada_reciente_599s": self.cond([1000, 1000], inact=599.0),
                 "vram_no_medible": self.cond([1000, None]),
                 "uso_gpu_no_medible": self.cond([1000, 1000], usos=[None, 3]),
                 "pantalla_completa_d3d": self.cond([1000], act=lambda: LIBRE | {"motivos": ["pantalla_completa_d3d"]})}
        for motivo, r in casos.items():
            with self.subTest(motivo):
                self.assertFalse(r["ok"])
                self.assertIn(motivo, r["motivos"])

    def test_esperar(self):
        resp = iter([{"ok": False, "motivos": ["x"]}, {"ok": False, "motivos": ["x"]}, {"ok": True, "motivos": []}])
        t = [0.0]
        r = X.esperar_libre(cond=lambda v: next(resp), dormir=lambda s: t.__setitem__(0, t[0] + s), reloj=lambda: t[0])
        self.assertTrue(r["ok"])
        self.assertEqual((r["intentos"], r["esperado_s"]), (3, 60.0))
        t[0] = 0.0
        r = X.esperar_libre(cond=lambda v: {"ok": False, "motivos": ["x"]}, max_espera_s=100,
                            dormir=lambda s: t.__setitem__(0, t[0] + s), reloj=lambda: t[0])
        self.assertFalse(r["ok"])
        self.assertGreaterEqual(r["esperado_s"], 100)


class TestBucle(unittest.TestCase):
    """El bucle de bloques con un `ejecutar` falso que usa el vigía de verdad (sin servidor)."""
    IDS = ("T01", "T02")

    def correr(self, guion, esperas=None):
        llamadas = []
        tiempos = [0.0]

        def vigia_fn():
            return X.VigiaExp(medir=vram(5000), intervalo=1, act=lambda: LIBRE, reloj=lambda: tiempos[0])

        def ejecutar(c, tarea, oraculo, oraculos, carpeta, be, vigia):
            n = len(llamadas)
            llamadas.append((c, tarea["id"], carpeta.name))
            accion = guion(n)
            if accion == "vram":
                vigia.medir = vram(7000)
            elif accion == "terceros":
                vigia.act = lambda: LIBRE | {"inactividad_s": 0.0}
                tiempos[0] += 5
            vigia._muestrear()
            return {"evaluacion": {"categoria": "CORRECTO", "calidad": "CORRECTO", "seguridad": "seguro", "motivo": ""},
                    "segundos_total": 1.0, "metricas": {"tokens_prompt": 10, "tokens_generados": 5},
                    "infraestructura": vigia.excedida, "servidor_terminado": True}
        it = iter(esperas or [])
        esperar = lambda: next(it, {"ok": True, "motivos": [], "esperado_s": 0})
        res = {"filas": [], "bloques": []}
        tareas = {t: {"id": t} for t in self.IDS}
        X.ejecutar_bucle(res, _tmp(self) / "vram_exp", tareas, {t: {} for t in self.IDS}, list(self.IDS), (1, 2),
                         ejecutar=ejecutar, fabrica=lambda ver: None, esperar=esperar, vigia_fn=vigia_fn)
        return res, llamadas

    def test_orden_prerregistrado(self):
        res, llamadas = self.correr(lambda n: None)
        self.assertEqual(len(res["filas"]), 12)
        self.assertEqual([b["configuracion"] for b in res["bloques"]], list(EV.ORDEN[1] + EV.ORDEN[2]))
        self.assertIsNone(res["abortada"])
        self.assertTrue(res["valida"])
        self.assertTrue(all(f["categoria"] == "CORRECTO" for f in res["filas"]))

    def test_terceros_a_mitad_se_repite_la_tarea(self):
        res, llamadas = self.correr(lambda n: "terceros" if n == 0 else None)
        self.assertEqual(llamadas[:2], [("S1", "T01", "intento1"), ("S1", "T01", "intento2")])
        f = res["filas"][0]
        self.assertEqual((f["interrupciones_por_terceros"], f["infraestructura"]), (1, None))
        self.assertEqual(len(res["filas"]), 12)

    def test_terceros_persistentes_no_se_puntuan(self):
        res, llamadas = self.correr(lambda n: "terceros" if n <= 2 else None)
        self.assertEqual([l[2] for l in llamadas[:4]], ["intento1", "intento2", "intento3", "intento1"])
        self.assertEqual(llamadas[3][:2], ("S1", "T02"))                # tras 1 + MAX_INTERRUPCIONES intentos
        f = res["filas"][0]
        self.assertTrue(X.por_terceros(f["infraestructura"]))
        self.assertEqual(f["interrupciones_por_terceros"], X.MAX_INTERRUPCIONES)

    def test_vram_por_encima_del_tope_aborta_todo(self):
        res, llamadas = self.correr(lambda n: "vram" if n == 0 else None)
        self.assertEqual(len(llamadas), 1)
        self.assertEqual(res["abortada"], "vram_excedida_7000MiB")
        self.assertEqual(len(res["filas"]), 12)
        self.assertFalse(res["valida"])
        self.assertEqual(res["filas"][0]["infraestructura"], "vram_excedida_7000MiB")
        self.assertTrue(all(f["categoria"] == "NO_CONCLUYENTE" for f in res["filas"][1:]))
        self.assertTrue(all("evaluacion_abortada" in f["infraestructura"] for f in res["filas"][1:]))

    def test_pc_ocupado_no_empieza(self):
        res, llamadas = self.correr(lambda n: None, esperas=[{"ok": False, "motivos": ["x"], "esperado_s": 3600}])
        self.assertEqual(llamadas, [])
        self.assertTrue(res["abortada"].startswith("terceros_o_gpu"))
        self.assertTrue(all(f["categoria"] == "NO_CONCLUYENTE" for f in res["filas"]))


class TestPrerregistroV3(unittest.TestCase):
    def test_detecta_cambios(self):
        t = _tmp(self)
        pre = t / "p.json"
        pre.write_text(json.dumps({"variante": X.VARIANTE, "limites": {"vram_tope_MiB": 6912},
                                   "sha256": {"eq3/evaluar_f1_vram_exp.py": "0" * 64}}), encoding="utf-8")
        original = X.PRERREGISTRO_V3
        X.PRERREGISTRO_V3 = pre
        try:
            self.assertIn("eq3/evaluar_f1_vram_exp.py", X.comprobar_v3())
            pre.write_text(json.dumps({"variante": X.VARIANTE, "limites": {"vram_tope_MiB": 7168}, "sha256": {}}),
                           encoding="utf-8")
            self.assertIn("variante o límites del prerregistro V3", X.comprobar_v3())
        finally:
            X.PRERREGISTRO_V3 = original


class TestIntegracionConServidorFalso(unittest.TestCase):
    """REAL: V2-F.1 (FuncionSupervisada, BackendLlama, ServidorLlama), procesos y sockets. SIMULADO: modelo, VRAM y
    actividad de terceros."""

    def test_por_debajo_del_tope_no_corta(self):
        f = _escenario(self, "vram6900_S1")["fila"]
        self.assertIsNone(f["infraestructura"], f)
        self.assertTrue(f["servidor_terminado"])

    def test_por_encima_del_tope_corta_y_cierra(self):
        for c in ("S1", "E3"):
            with self.subTest(c):
                r = _escenario(self, f"vram6913_{c}")
                f = r["fila"]
                self.assertEqual(r["vram"]["excedida"], "vram_excedida_6913MiB")
                self.assertTrue(f["infraestructura"])
                self.assertTrue(f["servidor_terminado"])
                self.assertLess(f["segundos_total"], 18)           # el servidor falso tardaría 20 s

    def test_terceros_cortan_y_cierran(self):
        for c in ("S1", "E3"):
            with self.subTest(c):
                r = _escenario(self, f"terceros_{c}")
                f = r["fila"]
                self.assertTrue(X.por_terceros(r["vram"]["excedida"]), r["vram"])
                self.assertTrue(f["servidor_terminado"])
                self.assertLess(f["segundos_total"], 18)


if __name__ == "__main__":
    unittest.main()
