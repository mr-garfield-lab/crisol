"""Pruebas de V3.1 F1 (D3): `eq3/majflt_windows.py` — HardFaultCount de Windows donde V2-F.1 lee majflt.

Ejecutar desde equipo_ia_v3/:   python -B -m unittest discover -s pruebas -t pruebas -p test_eq3_majflt.py -v

Lo que se garantiza: sin sonda superada no se sirve nada; un contador ilegible deja el dato AUSENTE (nunca cero); la
etiqueta dice que no es el majflt de Linux; y V2-F.1 (sin modificar) lo lee y da la respuesta por concluyente solo
cuando el dato existe.
"""
import builtins
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

import comun
from eq3 import majflt_windows as M
from eq3 import plataforma as P

AUX = comun.RAIZ / "pruebas" / "aux_servidor_pc.py"


def _tmp(caso) -> Path:
    d = tempfile.TemporaryDirectory(prefix="eq3_mf_", dir=os.environ.get("TMPDIR"))
    caso.addCleanup(d.cleanup)
    return Path(d.name).resolve()


def _contadores(*valores):
    it = iter(valores)
    return lambda pid: next(it)


class TestSonda(unittest.TestCase):
    def _sonda(self, *valores, escribir=None, leer=None):
        return M.sonda(_tmp(self), 1, contadores=_contadores(*valores),
                       escribir=escribir or (lambda ruta, mib: Path(ruta).write_bytes(b"x")),
                       leer=leer or (lambda ruta: None))

    def test_solo_pasa_con_fria_positiva_y_caliente_cero(self):
        self.assertTrue(self._sonda((10, 100), (142, 400), (142, 500))["ok"])
        casos = {
            "lectura_fria_sin_fallos_duros": ((10, 100), (10, 400), (10, 500)),
            "lectura_caliente_con_fallos_duros": ((10, 100), (142, 400), (143, 500)),
            "contador_no_disponible": ((10, 100), None, (142, 500)),
        }
        for motivo, valores in casos.items():
            with self.subTest(motivo):
                r = self._sonda(*valores)
                self.assertEqual((r["ok"], r["motivo"]), (False, motivo))
        r = self._sonda(None, None, None)
        self.assertEqual((r["ok"], r["fria"], r["caliente"]), (False, None, None))

    def test_un_fallo_de_la_sonda_no_rompe_la_sesion_y_no_la_supera(self):
        def falla(*a):
            raise OSError("disco")
        for kw in ({"escribir": falla}, {"leer": falla}):
            r = self._sonda((1, 2), (3, 4), (3, 4), **kw)
            self.assertEqual((r["ok"], r["motivo"]), (False, "sonda_fallida:OSError"))

    def test_la_sonda_borra_su_archivo(self):
        t = _tmp(self)
        M.sonda(t, 1, contadores=_contadores((1, 2), (3, 4), (3, 4)),
                escribir=lambda ruta, mib: Path(ruta).write_bytes(b"x"), leer=lambda ruta: None)
        self.assertEqual(list(t.iterdir()), [])


class TestSerie(unittest.TestCase):
    """El texto servido lo lee el código REAL de V2-F.1 (`eq2.monitor.leer_fallos`)."""

    def setUp(self):
        sys.path.insert(0, str(comun.SISTEMA / "src"))
        self.addCleanup(sys.path.remove, str(comun.SISTEMA / "src"))
        from eq2 import monitor
        self.monitor = monitor
        self.real = builtins.open

    def _con(self, contadores):
        builtins.open = M.con_majflt(self.real, contadores)
        self.addCleanup(setattr, builtins, "open", self.real)

    def test_v2f1_lee_majflt_y_minflt(self):
        self._con(lambda pid: (5, 105) if pid == 4242 else None)
        self.assertEqual(self.monitor.leer_fallos(4242), {"minflt": 100, "majflt": 5})

    def test_contador_ilegible_es_ausente_nunca_cero(self):
        self._con(lambda pid: None)
        self.assertEqual(self.monitor.leer_fallos(4242), {})            # ausente: V2-F.1 lo dará por no concluyente

    def test_contadores_incoherentes_no_se_sirven(self):
        self._con(lambda pid: (200, 100))                               # más fallos duros que totales: no es creíble
        self.assertEqual(self.monitor.leer_fallos(4242), {})

    def test_solo_lectura_de_texto_de_esa_ruta(self):
        llamadas = []
        abrir = M.con_majflt(lambda f, mode="r", *a, **k: llamadas.append((f, mode)) or io.StringIO(""),
                             lambda pid: (1, 2))
        for ruta, modo in (("/proc/1/status", "r"), ("/proc/meminfo", "r"), ("/proc/1/stat", "rb"),
                           ("/proc/1/stat", "w"), ("/proc/abc/stat", "r"), ("/proc/1/stat/x", "r")):
            abrir(ruta, modo)
        self.assertEqual(len(llamadas), 6)                              # ninguna se sirvió: todas pasaron al open real
        self.assertEqual(abrir("/proc/1/stat").read().split()[9 + 2], "1")


class TestActivar(unittest.TestCase):
    def setUp(self):
        self.real, self.real_io = builtins.open, io.open
        self.addCleanup(self._restaurar)

    def _restaurar(self):
        builtins.open, io.open = self.real, self.real_io
        M.ESTADO.update(activo=False, sonda=None)

    @unittest.skipUnless(P.WINDOWS, "PLATAFORMA: en Linux/Termux se usa el /proc real")
    def test_sonda_fallida_no_instala_nada(self):
        r = M.activar(_tmp(self), sondear=lambda c: {"ok": False, "motivo": "lectura_fria_sin_fallos_duros"})
        self.assertEqual((r["activo"], r["etiqueta"]), (False, None))
        self.assertIs(builtins.open, self.real)
        r = M.activar(_tmp(self), sondear=lambda c: {"ok": "sí"})        # solo True vale
        self.assertFalse(r["activo"])
        self.assertIs(builtins.open, self.real)

    @unittest.skipUnless(P.WINDOWS, "PLATAFORMA: en Linux/Termux se usa el /proc real")
    def test_sonda_superada_instala_una_sola_vez_y_etiqueta(self):
        r = M.activar(_tmp(self), sondear=lambda c: {"ok": True, "fria": 132, "caliente": 0})
        self.assertTrue(r["activo"])
        self.assertTrue(getattr(builtins.open, "es_majflt", False))
        primero = builtins.open
        M.activar(_tmp(self), sondear=lambda c: {"ok": True})
        self.assertIs(builtins.open, primero)
        self.assertIn("HardFaultCount de Windows", r["etiqueta"])
        self.assertIn("NO es el majflt de Linux", r["etiqueta"])
        self.assertIn("NO son comparables", r["etiqueta"])
        M.desactivar()
        self.assertIs(builtins.open, self.real)

    @unittest.skipIf(P.WINDOWS, "PLATAFORMA: solo fuera de Windows")
    def test_fuera_de_windows_no_hace_nada(self):
        r = M.activar(_tmp(self), sondear=lambda c: {"ok": True})
        self.assertFalse(r["activo"])
        self.assertIs(builtins.open, self.real)


@unittest.skipUnless(P.WINDOWS, "PLATAFORMA: contador de Windows")
class TestRealEnWindows(unittest.TestCase):
    def test_contador_real_de_este_proceso(self):
        c = M.contadores_fallos(os.getpid())
        self.assertIsNotNone(c)
        self.assertTrue(0 <= c[0] <= c[1], c)
        self.assertIsNone(M.contadores_fallos(0xFFFFFFF0))               # proceso inexistente: ausente

    def test_sonda_real_es_coherente(self):
        r = M.sonda(_tmp(self))
        self.assertEqual(r["ok"], r["motivo"] is None)
        if r["ok"]:
            self.assertTrue(r["fria"] > 0 and r["caliente"] == 0, r)

    def _escenario(self, nombre):
        t = _tmp(self)
        r = P.ejecutar(P.orden_eq2(str(AUX), nombre, str(t)), cwd=comun.SISTEMA, env=P.entorno_hijo(t), timeout=180)
        self.assertEqual(r.returncode, 0, r.stderr[-1500:])
        return json.loads(r.stdout.strip().splitlines()[-1])

    def test_v2f1_sin_majflt_es_no_concluyente(self):
        for nombre in ("normal", "majflt_sonda_fallida"):
            with self.subTest(nombre):
                p = self._escenario(nombre)["peticion"]
                self.assertEqual(p["criticas_ausentes"], ["majflt"])
                self.assertFalse(p["concluyente"])
                self.assertIn("medicion_critica_ausente:majflt", p["motivos_no_concluyente"])
                self.assertIsNone(p["delta_fallos"]["majflt"])            # ausente, no cero

    def test_v2f1_con_majflt_activo_tiene_la_medicion(self):
        r = self._escenario("majflt_activo")
        if not r["majflt"]["activo"]:
            self.skipTest(f"NO CONCLUYENTE: la sonda real no pasó en esta ejecución ({r['majflt']['sonda']})")
        p = r["peticion"]
        self.assertEqual(p["criticas_ausentes"], [])
        self.assertIsInstance(p["delta_fallos"]["majflt"], int)
        self.assertNotIn("medicion_critica_ausente:majflt", p["motivos_no_concluyente"])


if __name__ == "__main__":
    unittest.main()
