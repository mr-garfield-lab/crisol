"""V2-E.6 área 1: perfiles de contexto, reservas, retroceso y límites estrictos de tokens (SIMULADO)."""
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

import _comun
from eq2 import config, inferencia, orquestador, perfiles_contexto as PC, prompts, vigilancia

RAIZ = _comun.RAIZ
T = "Escribe ordenar(xs) en Python sin modificar la lista de entrada."


class ConfigLimpia(unittest.TestCase):
    def setUp(self):
        nombres = ("CTX", "MAX_TOKENS", "MAX_TOKENS_ACLARACION", "MAX_TOKENS_CONTINUACION", "MOTOR_MAX_TOKENS",
                   "PERFIL_CONTEXTO")
        guardado = {n: getattr(config, n) for n in nombres}
        self.addCleanup(lambda: [setattr(config, n, v) for n, v in guardado.items()])


class TestPerfiles(ConfigLimpia):
    def test_referencia_es_identica_a_r3(self):
        PC.aplicar("referencia")
        self.assertEqual((config.CTX, config.MAX_TOKENS),
                         (2048, {"analisis": 160, "propuesta": 320, "revision": 160, "replica": 240, "voto": 120}))
        self.assertEqual(config.max_tokens_motor("generar"), 640)
        PC.aplicar("seguro")
        self.assertEqual((config.CTX, config.max_tokens_motor("generar")), (1024, 400))

    def test_ampliacion_moderada_y_voto_sin_cambios(self):
        ref = PC.PERFILES["referencia"]["max_tokens"]
        for nombre in ("ampliado", "experimental"):
            p = PC.PERFILES[nombre]
            for fase, v in p["max_tokens"].items():
                self.assertLessEqual(v, int(ref[fase] * 1.5), (nombre, fase))   # como mucho +50 %
                self.assertLessEqual(v, config.TOPE_MAX_TOKENS)
            self.assertEqual(p["max_tokens"]["voto"], 120)
            self.assertGreater(p["mem_min_kb"], PC.PERFILES["referencia"]["mem_min_kb"])

    def test_reservas_cuadran_y_dejan_historial(self):
        for nombre in PC.ORDEN:
            for fase, r in PC.presupuesto_detallado(nombre).items():
                self.assertEqual(r["salida"] + r["margen"] + r["sistema"] + r["memoria"] + r["historial_y_tarea"], r["ctx"])
                self.assertGreater(r["historial_y_tarea"], 200, (nombre, fase))

    def test_prompts_caben_con_historial_maximo_en_todos_los_perfiles(self):
        hist = {f: "x" * config.MAX_TURNO_CHARS for f in prompts.FASES_HIST}
        for nombre in PC.ORDEN:
            PC.aplicar(nombre)
            for _o, fase, ag in config.PLAN:
                with self.subTest(perfil=nombre, fase=fase):
                    p = prompts.construir(fase, ag, "t" * config.MAX_TAREA_CHARS, hist, ["m" * 200] * 3,
                                          truncados=tuple(prompts.FASES_HIST))
                    self.assertLessEqual(p.tokens_est + p.max_gen + config.MARGEN_CTX, config.CTX)


class TestSeleccionYRetroceso(unittest.TestCase):
    def test_retroceso_por_ram(self):
        s = PC.seleccionar("ampliado", mem_kb=1_500_000)
        self.assertEqual((s["efectivo"], s["retroceso"]), ("referencia", True))
        self.assertIn("RAM disponible 1500000 kB", s["motivos"][0])
        self.assertEqual(PC.seleccionar("ampliado", mem_kb=900_000)["efectivo"], "seguro")
        self.assertEqual(PC.seleccionar("ampliado", mem_kb=3_000_000)["efectivo"], "ampliado")

    def test_ram_no_medible_no_permite_ampliar(self):
        s = PC.seleccionar("ampliado", mem_kb=None)
        self.assertEqual((s["efectivo"], s["medido"]), ("referencia", False))
        self.assertIn("no medible", s["motivos"][0])

    def test_experimental_exige_aceptacion_y_ram(self):
        self.assertEqual(PC.seleccionar("experimental", mem_kb=4_000_000)["efectivo"], "ampliado")
        self.assertEqual(PC.seleccionar("experimental", mem_kb=4_000_000, aceptar_experimental=True)["efectivo"],
                         "experimental")
        self.assertEqual(PC.seleccionar("experimental", mem_kb=2_500_000, aceptar_experimental=True)["efectivo"],
                         "ampliado")

    def test_servidor_con_contexto_menor(self):
        s = PC.seleccionar("ampliado", mem_kb=3_000_000, ctx_servidor=2048)
        self.assertEqual(s["efectivo"], "referencia")
        with self.assertRaises(ValueError):
            PC.seleccionar("enorme")


class TestLimitesDeTokens(ConfigLimpia):
    def correr(self, guion, tareas=(T,)):
        tmp = _comun.carpeta_temporal()
        self.addCleanup(tmp.cleanup)
        raiz = Path(tmp.name) / "equipo_f2"
        v = vigilancia.Vigilante(lector_mem=lambda: 1_500_000, lector_bat=lambda: (80, False))
        be = inferencia.BackendSimulado(guion)
        return orquestador.Orquestador(raiz / "d", be, v, reloj=_comun.Reloj(), raiz_laboratorio=raiz).run_deliberacion(
            list(tareas)), be

    def test_agotamiento_del_limite_por_tarea(self):
        PC.aplicar("seguro")
        with mock.patch.dict(PC.TOKENS_TAREA, {"seguro": 600}):
            res, be = self.correr(None)
        t = res["tareas"][0]
        self.assertEqual((t["estado"], t["motivo"]), ("abortada", "limite_tokens_tarea"))
        self.assertLessEqual(sum(c["max_tokens"] for c in be.llamadas), 600)
        self.assertIn("tokens_pedidos_sesion", res)

    def test_agotamiento_del_limite_por_sesion(self):
        PC.aplicar("seguro")
        with mock.patch.dict(PC.TOKENS_SESION, {"seguro": 900}):
            res, be = self.correr(None, tareas=(T, T + " otra"))
        self.assertEqual((res["estado"], res["motivo_fin"]), ("abortada", "limite_tokens_sesion"))
        self.assertLessEqual(res["tokens_pedidos_sesion"], 900)

    def test_deliberacion_normal_no_se_acerca_al_limite(self):
        PC.aplicar("referencia")
        res, be = self.correr(None)
        self.assertEqual(res["tareas"][0]["estado"], "completa")
        self.assertLess(res["tokens_pedidos_sesion"], PC.TOKENS_TAREA["referencia"])
        self.assertEqual(res["config"]["perfil_contexto"], "referencia")


class TestCLIPerfil(unittest.TestCase):
    def test_ayuda_y_retroceso_visible(self):
        r = subprocess.run([sys.executable, "-B", "-I", str(RAIZ / "ejecutar_v2.py"), "--help"], capture_output=True,
                           text=True, timeout=60)
        for s in ("--perfil-contexto", "--aceptar-experimental", "experimental"):
            self.assertIn(s, r.stdout)


if __name__ == "__main__":
    unittest.main()
