"""Pruebas del LABORATORIO de VRAM (`lab_vram/banco_vram.py`): parser de búferes, criterio de PC libre y vigía.

Ejecutar desde equipo_ia_v3/:   python -B -m unittest discover -s pruebas -t pruebas -p test_lab_vram.py -v

El vigía se prueba con un proceso hijo PROPIO que solo duerme (sin modelo). Nada generado se ejecuta.
"""
import subprocess
import sys
import unittest

import comun  # noqa: F401
from lab_vram import banco_vram as B

LIBRE = {"inactividad_s": 10_000.0, "sesiones": {}, "notificacion": 5, "motivos": []}
LOG = """load_tensors: offloaded 29/29 layers to GPU
load_tensors:          CPU model buffer size =   292.36 MiB
load_tensors:        CUDA0 model buffer size =  4168.09 MiB
llama_kv_cache:      CUDA0 KV buffer size =   112.00 MiB
llama_context:      CUDA0 compute buffer size =   304.00 MiB
llama_context:  CUDA_Host compute buffer size =    11.01 MiB
"""


def dormilon():
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])


class TestBanco(unittest.TestCase):
    def test_bufers(self):
        b = B.bufers(LOG)
        self.assertEqual(b["capas_gpu"], "29/29")
        self.assertEqual(b["CUDA0 model"], 4168.09)
        self.assertEqual(b["cuda_total_MiB"], 4584.1)              # CUDA0 (model+KV+compute); CUDA_Host no es VRAM

    def test_limites_no_cambian(self):
        self.assertEqual((B.TOPE_MIB, B.OTRAS_MAX_MIB), (6912, 1832))
        for nombre, extra in B.CONFIGURACIONES.items():
            self.assertNotIn("-c", extra, nombre)                   # mismo contexto que V2-F.1 en todas
            self.assertNotIn("-t", extra, nombre)

    def test_pc_libre(self):
        ok = B.pc_libre(act=lambda: LIBRE | {"motivos": ["aplicacion_ocupada"]}, medir=lambda: {"vram_MiB": 900,
                                                                                                 "uso_pct": 30})
        self.assertTrue(ok["ok"], ok)                                # Wallpaper Engine no es una persona
        casos = {"entrada_reciente_5s": (LIBRE | {"inactividad_s": 5.0}, 900),
                 "vram_otras_1900MiB": (LIBRE, 1900),
                 "otra_sesion_activa_[2]": (LIBRE | {"motivos": ["otra_sesion_activa_[2]"]}, 900),
                 "pantalla_completa_d3d": (LIBRE | {"motivos": ["pantalla_completa_d3d"]}, 900)}
        for motivo, (a, v) in casos.items():
            with self.subTest(motivo):
                r = B.pc_libre(act=lambda a=a: a, medir=lambda v=v: {"vram_MiB": v, "uso_pct": 0})
                self.assertIn(motivo, r["motivos"])
        self.assertIn("gpu_no_medible", B.pc_libre(act=lambda: LIBRE, medir=lambda: None)["motivos"])

    def test_vigia_termina_solo_el_proceso_propio(self):
        for nombre, medir, act, motivo in (
                ("vram", lambda: {"vram_MiB": 6913, "uso_pct": 50}, lambda: LIBRE, "vram_excedida_6913MiB"),
                ("terceros", lambda: {"vram_MiB": 6000, "uso_pct": 50}, lambda: LIBRE | {"inactividad_s": 0.0},
                 "actividad_de_terceros"),
                ("sin_medida", lambda: None, lambda: LIBRE, "vram_no_medible")):
            with self.subTest(nombre):
                p, testigo = dormilon(), dormilon()
                self.addCleanup(testigo.kill)
                self.addCleanup(p.kill)
                t = [0.0]
                v = B.Vigia(p, medir=medir, act=act, reloj=lambda: t[0])
                t[0] = 1.0
                v.paso()
                self.assertEqual(v.motivo, motivo)
                p.wait(10)
                self.assertIsNotNone(p.poll())
                self.assertIsNone(testigo.poll())                    # otro proceso: intacto

    def test_ram_baja_termina_el_servidor_propio(self):
        p = dormilon()
        self.addCleanup(p.kill)
        v = B.Vigia(p, medir=lambda: {"vram_MiB": 5000, "uso_pct": 50}, act=lambda: LIBRE, ram=lambda: 2000)
        v.paso()
        self.assertEqual(v.motivo, "ram_disponible_baja_2000MiB")
        p.wait(10)
        v = B.Vigia(dormilon(), medir=lambda: {"vram_MiB": 5000, "uso_pct": 50}, act=lambda: LIBRE, ram=lambda: None)
        self.addCleanup(v.proc.kill)
        v.paso()
        self.assertEqual(v.motivo, "ram_disponible_baja_NoneMiB")   # no medible = baja (fallo cerrado)

    def test_carpeta_de_laboratorio(self):
        import hashlib
        import json
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "lab").mkdir()
            (d / "lab" / "a.dll").write_bytes(b"x")
            m = d / "m.json"
            m.write_text(json.dumps({"sha256": {"a.dll": hashlib.sha256(b"x").hexdigest()}}), encoding="utf-8")
            self.assertEqual(B.verificar_lab(d / "lab", m), [])
            (d / "lab" / "b.dll").write_bytes(b"y")
            (d / "lab" / "a.dll").write_bytes(b"z")
            self.assertEqual(B.verificar_lab(d / "lab", m), ["sobra: b.dll", "distinto: a.dll"])

    def test_por_debajo_del_tope_no_corta(self):
        p = dormilon()
        self.addCleanup(p.kill)
        v = B.Vigia(p, medir=lambda: {"vram_MiB": 6912, "uso_pct": 90},
                    act=lambda: LIBRE | {"motivos": ["aplicacion_ocupada"]})
        v.paso()
        self.assertIsNone(v.motivo)
        self.assertIsNone(p.poll())


if __name__ == "__main__":
    unittest.main()
