"""Pruebas SIMULADAS del supervisor térmico de F1 V4.3 (`lab_vram/f1_v4_3_supervisado.py`). No lanza Qwen.

Ejecutar desde equipo_ia_v3/:   python -B -m unittest discover -s pruebas -t pruebas -p test_lab_f1_supervisado.py -v
"""
import tempfile
import threading
import time
import unittest
from pathlib import Path

import comun  # noqa: F401
from lab_vram import f1_v4_3_supervisado as S


class TestTermica(unittest.TestCase):
    def test_umbrales(self):
        self.assertIsNone(S.anomalia({"temp_C": 80}, {"temp_C": 86}))
        self.assertIsNone(S.anomalia({"temp_C": 88}, {"temp_C": 80}))              # un pico aislado de aviso
        self.assertTrue(S.anomalia({"temp_C": 88}, {"temp_C": 87}).startswith("temperatura_sostenida"))
        self.assertEqual(S.anomalia({"temp_C": 90}, None), "temperatura_90C")
        self.assertEqual(S.anomalia({"temp_C": 60, "freno_termico": True}, None), "freno_termico_activo")
        self.assertIsNone(S.anomalia({"error": "sin sensor"}, None))               # sin sensor: se anota

    def test_interrumpe_ante_anomalia(self):
        lecturas = iter([{"temp_C": 70}, {"temp_C": 88}, {"temp_C": 89}, {"temp_C": 50}])
        hecho = threading.Event()
        with tempfile.TemporaryDirectory() as d:
            v = S.VigiaTermico(Path(d) / "t.jsonl", leer=lambda: next(lecturas), interrumpir=hecho.set, intervalo=0.01)
            v.start()
            self.assertTrue(hecho.wait(5))
            v.join(5)
            self.assertEqual(v.motivo, "temperatura_sostenida_88-89C")
            self.assertEqual(v.maxima, 89)
            self.assertEqual(len((Path(d) / "t.jsonl").read_text(encoding="utf-8").splitlines()), 3)

    def test_interrupt_main_llega_al_hilo_principal(self):
        with tempfile.TemporaryDirectory() as d:
            v = S.VigiaTermico(Path(d) / "t.jsonl", leer=lambda: {"temp_C": 95}, intervalo=0.01)
            with self.assertRaises(KeyboardInterrupt):
                v.start()
                for _ in range(500):
                    time.sleep(0.01)
            v.join(5)
            self.assertEqual(v.motivo, "temperatura_95C")

    def test_sin_anomalia_no_interrumpe(self):
        with tempfile.TemporaryDirectory() as d:
            llamado = []
            v = S.VigiaTermico(Path(d) / "t.jsonl", leer=lambda: {"temp_C": 60}, interrumpir=lambda: llamado.append(1),
                               intervalo=0.01)
            v.start()
            time.sleep(0.2)
            v.detener()
            v.join(5)
            self.assertEqual((llamado, v.motivo, v.maxima), ([], None, 60))


if __name__ == "__main__":
    unittest.main()
