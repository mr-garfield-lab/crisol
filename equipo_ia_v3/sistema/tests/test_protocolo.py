import unittest
import _comun  # noqa
from eq2 import protocolo


def v(a2, a3, a1):
    return {"A2": (a2, "r2"), "A3": (a3, "r3"), "A1": (a1, "r1")}


A, C, R, X = "aprobar", "aprobar_con_cambios", "rechazar", "abstencion"


class TestContar(unittest.TestCase):
    def casos(self):
        return [
            ((A, A, A), "aprobada"), ((A, A, R), "aprobada"), ((A, A, X), "aprobada"),
            ((A, C, A), "aprobada_con_cambios"), ((C, C, R), "aprobada_con_cambios"),
            ((A, C, X), "aprobada_con_cambios"),
            ((R, R, A), "rechazada"), ((R, R, R), "rechazada"), ((R, R, X), "rechazada"),
            ((A, C, R), "sin_consenso"), ((C, A, R), "sin_consenso"),
            ((A, R, X), "sin_consenso"), ((C, R, X), "sin_consenso"),
            ((A, X, X), "sin_consenso"), ((X, X, X), "sin_consenso"),
            ((R, X, X), "sin_consenso"),
        ]

    def test_tabla(self):
        for votos, esperado in self.casos():
            self.assertEqual(protocolo.contar(v(*votos))["resultado"], esperado, votos)

    def test_conteo_suma_3(self):
        for votos, _ in self.casos():
            self.assertEqual(sum(protocolo.contar(v(*votos))["conteo"].values()), 3)

    def test_cambios_pendientes_conservados(self):
        r = protocolo.contar(v(C, A, A))
        self.assertEqual(r["cambios_pendientes"], ["A2: r2"])
        self.assertEqual(protocolo.contar(v(A, A, A))["cambios_pendientes"], [])

    def test_sesgo_autoria(self):
        self.assertTrue(protocolo.contar(v(A, A, A))["sesgo_autoria"])
        self.assertFalse(protocolo.contar(v(A, A, R))["sesgo_autoria"])
        self.assertEqual(protocolo.contar(v(A, A, R))["nota_sesgo"], "A1 votó su propia propuesta")

    def test_orden_de_llegada_irrelevante(self):
        a = protocolo.contar({"A1": (A, ""), "A2": (R, ""), "A3": (A, "")})
        b = protocolo.contar({"A3": (A, ""), "A2": (R, ""), "A1": (A, "")})
        self.assertEqual(a, b)

    def test_entradas_invalidas(self):
        with self.assertRaises(ValueError):
            protocolo.contar({"A1": ("quizas", "")})
        with self.assertRaises(ValueError):
            protocolo.contar({"A9": (A, "")})

    def test_no_hay_azar(self):
        for _ in range(20):
            self.assertEqual(protocolo.contar(v(A, C, R))["resultado"], "sin_consenso")


if __name__ == "__main__":
    unittest.main()
