"""Pruebas de la Etapa 6: planificación de recursos para el PC del usuario (estimaciones, sin lanzar nada).

Ejecutar desde equipo_ia_v3/:   python3 -B -m unittest discover -s pruebas -t pruebas -v
"""
import dataclasses
import os
import tempfile
import unittest
from pathlib import Path

import comun  # noqa: F401  (añade equipo_ia_v3/ a sys.path)
from eq3 import perfiles_pc as P

M7 = P.CATALOGO["qwen2.5-coder-7b-q4_k_m"]
M14 = P.CATALOGO["qwen2.5-coder-14b-q4_k_m"]


class TestCalculo(unittest.TestCase):
    def test_cache_kv_y_presupuesto_a_mano(self):
        self.assertEqual(round(P.kv_mib(M7, 8192)), 448)                     # 2·28·8192·512·2 B
        p = P.planificar(M7, 8192)
        # 4460 + 448 + (300 + 0,05·4460) = 5431 MiB ≤ min(8192 − 1024, 6144) = 6144
        self.assertEqual((p["capas_gpu"], p["vram_estimada_mib"], p["tope_vram_mib"]), (28, 5431, 6144))
        self.assertTrue(p["cabe"])

    def test_descarga_parcial_respeta_el_tope_y_avisa(self):
        p = P.planificar(M14, 8192)
        self.assertTrue(0 < p["capas_gpu"] < p["capas"])
        self.assertLessEqual(p["vram_estimada_mib"], p["tope_vram_mib"])
        self.assertTrue(any("descarga parcial" in a for a in p["avisos"]))

    def test_mas_contexto_nunca_da_mas_capas_en_gpu(self):
        capas = [P.planificar(M14, c)["capas_gpu"] for c in P.CTX_PC]
        self.assertEqual(capas, sorted(capas, reverse=True))

    def test_el_limite_del_coordinador_se_respeta_y_no_se_modifica(self):
        self.assertEqual(P.PC_USUARIO.limite_coordinador_mib, 6144)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            P.PC_USUARIO.limite_coordinador_mib = 8192
        estrecho = dataclasses.replace(P.PC_USUARIO, limite_coordinador_mib=3000)
        p = P.planificar(M7, 8192, estrecho)
        self.assertEqual(p["tope_vram_mib"], 3000)
        self.assertLessEqual(p["vram_estimada_mib"], 3000)

    def test_reserva_de_vram_se_descuenta(self):
        # Con una tarjeta de 4 GB, el tope lo fija la reserva de Windows (4096 − 1024), no el coordinador (6144).
        tarjeta4 = dataclasses.replace(P.PC_USUARIO, vram_mib=4096)
        p = P.planificar(M7, 8192, tarjeta4)
        self.assertEqual(p["tope_vram_mib"], 3072)
        self.assertLessEqual(p["vram_estimada_mib"], 3072)

    def test_ram_insuficiente_no_cabe(self):
        pequeno = dataclasses.replace(P.PC_USUARIO, ram_mib=4096, reserva_ram_mib=2048, vram_mib=0,
                                      reserva_vram_mib=0)
        p = P.planificar(M14, 8192, pequeno)
        self.assertEqual(p["capas_gpu"], 0)
        self.assertFalse(p["cabe"])
        self.assertTrue(any("RAM insuficiente" in a for a in p["avisos"]))


class TestSeguridadDeLaOrden(unittest.TestCase):
    def test_un_servidor_para_tres_agentes_solo_local(self):
        p = P.planificar(M7, 8192, ruta_modelo="C:/modelos/qwen 7b.gguf")
        self.assertEqual((p["servidores"], p["agentes"]), (1, ["A1", "A2", "A3"]))
        a = p["argv"]
        self.assertEqual(a[a.index("--host") + 1], "127.0.0.1")
        self.assertEqual(a[a.index("--parallel") + 1], "1")
        self.assertEqual(a[a.index("-m") + 1], "C:/modelos/qwen 7b.gguf")       # un argumento, sin shell
        self.assertTrue(all(isinstance(x, str) for x in a))
        self.assertIn("no validada en el PC real", p["naturaleza"])

    def test_entradas_invalidas(self):
        for kw in ({"ctx": 3000}, {"ctx": 8192, "ruta_modelo": "a.gguf\nrm -rf /"}, {"ctx": 8192, "puerto": 80}):
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                P.planificar(M7, **kw)

    def test_tamano_real_del_archivo_solo_con_stat(self):
        d = tempfile.TemporaryDirectory(prefix="eq3_pc_", dir=os.environ.get("TMPDIR"))
        self.addCleanup(d.cleanup)
        f = Path(d.name) / "modelo.gguf"
        with f.open("wb") as h:
            h.truncate(3000 * P.MIB)                                         # archivo disperso: no ocupa disco
        m = P.con_archivo(M7, f)
        self.assertEqual((m.archivo_mib, m.capas), (3000, 28))
        self.assertTrue(m.fuente.startswith("tamaño real"))
        self.assertFalse(any("catálogo" in a for a in P.planificar(m, 8192)["avisos"]))
        with self.assertRaises(ValueError):
            P.con_archivo(M7, Path(d.name) / "no_existe.gguf")

    def test_un_enlace_no_es_el_archivo_real(self):
        d = tempfile.TemporaryDirectory(prefix="eq3_pc_", dir=os.environ.get("TMPDIR"))
        self.addCleanup(d.cleanup)
        f = Path(d.name) / "modelo.gguf"
        f.write_bytes(b"GGUF")
        enlace = Path(d.name) / "enlace.gguf"
        comun.enlazar_o_omitir(self, enlace, f)                              # Windows sin privilegio: OMITIDA
        with self.assertRaises(ValueError):
            P.con_archivo(M7, enlace)                                         # un enlace no es «el archivo real»

    def test_orden_de_linea_de_comandos(self):
        import sys
        cli = lambda *x: comun.plataforma.ejecutar([sys.executable, "-B", str(comun.RAIZ / "equipo3.py"), "pc", *x],
                                                   timeout=60, cwd=comun.RAIZ)
        r = cli("recomendar")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("recomendado: qwen2.5-coder-7b-q4_k_m", r.stdout)
        self.assertIn("no validada en el PC real", r.stdout)
        r = cli("planificar", "qwen2.5-coder-7b-q4_k_m", "--ctx", "8192")
        self.assertIn("-ngl 28", r.stdout)
        self.assertIn("(no se ejecuta)", r.stdout)
        self.assertEqual(cli("planificar", "inventado").returncode, 2)
        self.assertEqual(cli("planificar", "qwen2.5-coder-7b-q4_k_m", "--ctx", "3000").returncode, 2)

    def test_recomendacion(self):
        r = P.recomendar()
        self.assertEqual(r["recomendado"], "qwen2.5-coder-7b-q4_k_m")          # el mayor que cabe ENTERO en la GPU


if __name__ == "__main__":
    unittest.main()
