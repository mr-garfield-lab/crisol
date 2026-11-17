import unittest
import _comun  # noqa
from eq2 import vigilancia as vg

MEMINFO = "MemTotal:  7000000 kB\nMemAvailable:    1395864 kB\nSwapTotal: 0 kB\n"


def secuencia(valores):
    it = iter(valores)
    return lambda: next(it)


class TestVigilancia(unittest.TestCase):
    def test_parsear(self):
        self.assertEqual(vg.parsear_meminfo(MEMINFO), 1395864)
        self.assertIsNone(vg.parsear_meminfo("MemTotal: 5 kB\n"))
        self.assertIsNone(vg.parsear_meminfo("MemAvailable: abc kB\n"))
        self.assertIsNone(vg.parsear_meminfo(""))

    def test_lector_inexistente(self):
        self.assertIsNone(vg.leer_mem_available("/no/existe/meminfo"))
        self.assertEqual(vg.leer_bateria("/no/existe/bat"), (None, None))

    def test_tres_bajas_consecutivas_abortan(self):
        v = vg.Vigilante(lector_mem=secuencia([100, 100, 100]), lector_bat=lambda: (None, None))
        self.assertIsNone(v.verificar())
        self.assertIsNone(v.verificar())
        self.assertEqual(v.verificar(), "memoria_baja")

    def test_baja_aislada_no_aborta(self):
        v = vg.Vigilante(lector_mem=secuencia([100, 100, 999999, 100, 100, 999999]),
                         lector_bat=lambda: (None, None))
        for _ in range(6):
            self.assertIsNone(v.verificar())

    def test_monitor_falla(self):
        v = vg.Vigilante(lector_mem=lambda: None, lector_bat=lambda: (None, None))
        self.assertIsNone(v.verificar())
        self.assertIsNone(v.verificar())
        self.assertEqual(v.verificar(), "monitor_falla")

    def test_excepcion_del_lector_se_trata_como_fallo(self):
        def malo():
            raise RuntimeError("x")
        v = vg.Vigilante(lector_mem=malo, lector_bat=malo)
        r = [v.verificar() for _ in range(3)]
        self.assertEqual(r[-1], "monitor_falla")
        self.assertIsNone(v.historial[0].mem_kb)        # N/D, nunca 0

    def test_fallo_se_resetea_con_lectura_buena(self):
        v = vg.Vigilante(lector_mem=secuencia([None, None, 999999, None, None, 999999]),
                         lector_bat=lambda: (None, None))
        for _ in range(6):
            self.assertIsNone(v.verificar())

    def test_bateria(self):
        v = vg.Vigilante(lector_mem=lambda: 999999, lector_bat=lambda: (15, False))
        self.assertEqual(v.verificar(), "bateria_baja")
        v = vg.Vigilante(lector_mem=lambda: 999999, lector_bat=lambda: (15, True))
        self.assertIsNone(v.verificar())
        v = vg.Vigilante(lector_mem=lambda: 999999, lector_bat=lambda: (15, None))
        self.assertIsNone(v.verificar())        # sin dato de carga no se pausa
        v = vg.Vigilante(lector_mem=lambda: 999999, lector_bat=lambda: (None, None))
        self.assertIsNone(v.verificar())


if __name__ == "__main__":
    unittest.main()
