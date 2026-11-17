"""Pruebas SIMULADAS del control reversible de Wallpaper Engine (`lab_vram/wallpaper.py`). No toca la aplicación real.

Ejecutar desde equipo_ia_v3/:   python -B -m unittest discover -s pruebas -t pruebas -p test_lab_wallpaper.py -v
"""
import unittest
from types import SimpleNamespace

import comun  # noqa: F401
from lab_vram import wallpaper as W

P = {"pid": 10, "nombre": "wallpaper64.exe", "ruta": r"C:\we\wallpaper64.exe", "orden": '"C:\\we\\wallpaper64.exe" -silent',
     "sesion": 1}


class Falso:
    """Wallpaper Engine simulado: procesos, órdenes -control y WM_CLOSE (que puede ignorar)."""

    def __init__(self, cierra=True, duplica=False):
        self.vivos, self.cierra, self.duplica, self.ordenes, self.creados = [dict(P)], cierra, duplica, [], []

    def listar(self):
        return [dict(p) for p in self.vivos]

    def ejecutar(self, orden, **k):
        self.ordenes.append(orden)
        if orden[0] == "taskkill":
            assert "/F" not in orden                     # nunca forzado
            if self.cierra:
                self.vivos = []
        elif self.duplica:
            self.vivos.append(dict(P, pid=99))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    def crear(self, orden, carpeta):
        self.creados.append(orden)
        self.vivos.append(dict(P, pid=11))
        return {"rc": 0, "pid": 11}


def control(f):
    return W.Control(ejecutar=f.ejecutar, listar=f.listar, crear=f.crear, dormir=lambda s: None)


class TestControl(unittest.TestCase):
    def test_pausa_y_restauracion(self):
        f = Falso()
        c = control(f)
        c.capturar()
        self.assertTrue(c.control("pause"))
        self.assertEqual(c.estado, "pausado")
        self.assertTrue(c.restaurar()["ok"])
        self.assertEqual(f.ordenes[-1][1:], ["-control", "play"])
        self.assertEqual(c.estado, "normal")

    def test_cierre_ordenado_y_reapertura_con_la_misma_orden(self):
        f = Falso()
        c = control(f)
        c.capturar()
        self.assertTrue(c.cerrar_ordenado())
        self.assertEqual(f.ordenes[-1], ["taskkill", "/PID", "10"])
        self.assertTrue(c.restaurar()["ok"])
        self.assertEqual(f.creados, [P["orden"]])
        self.assertEqual(len(f.vivos), 1)

    def test_si_no_cierra_no_se_fuerza(self):
        f = Falso(cierra=False)
        t = [0.0]
        c = W.Control(ejecutar=f.ejecutar, listar=f.listar, crear=f.crear, reloj=lambda: t[0],
                      dormir=lambda s: t.__setitem__(0, t[0] + s))
        c.capturar()
        self.assertFalse(c.cerrar_ordenado(espera_s=5))
        self.assertTrue(all("/F" not in o for o in f.ordenes))
        self.assertEqual(len(f.vivos), 1)
        self.assertTrue(c.restaurar()["ok"])
        self.assertEqual(f.creados, [])                  # no abre otra instancia

    def test_duplicado_detectado(self):
        f = Falso(duplica=True)
        c = control(f)
        c.capturar()
        self.assertFalse(c.control("pause"))
        self.assertFalse(c.restaurar()["ok"])            # hay más procesos que al empezar: no se oculta

    def test_no_abierto_no_se_abre(self):
        f = Falso()
        f.vivos = []
        c = control(f)
        c.capturar()
        self.assertFalse(c.control("pause"))
        self.assertTrue(c.restaurar()["ok"])
        self.assertEqual(f.creados, [])

    def test_humano_independiente_de_la_gpu(self):
        base = {"inactividad_s": 900.0, "sesiones": {}, "notificacion": 2, "motivos": ["aplicacion_ocupada"]}
        self.assertTrue(W.nadie(act=lambda: base)["ok"])                      # el fondo animado no es una persona
        self.assertFalse(W.nadie(act=lambda: base | {"inactividad_s": 30.0})["ok"])
        self.assertFalse(W.nadie(act=lambda: base | {"inactividad_s": None})["ok"])
        self.assertFalse(W.nadie(act=lambda: base | {"motivos": ["pantalla_completa_d3d"]})["ok"])
        self.assertFalse(W.nadie(act=lambda: base | {"motivos": ["otra_sesion_activa_[2]"]})["ok"])


if __name__ == "__main__":
    unittest.main()
