"""Pruebas SIMULADAS de V3.1 F1-VRAM-EXP-V4.5.1: la `Termica` de G12 con el origen REAL y el resto de V4.5 sin cambios.

V4.5 creaba la `Termica` de G12 sin `propio_activo` (origen «incierto» por defecto); su servidor llama estaba vivo, así que el
freno simulado salía `freno_termico_hardware_origen_incierto` y G12 no podía pasar. V4.5.1 solo cambia eso. Estas pruebas
comprueban: (1) con el servidor propio vivo, el freno es crítico y propio; (2) si el origen es realmente incierto (lista de
procesos ilegible, error al consultarla) se CONSERVA «_origen_incierto»; (3) sin ningún llama es externo y no crítico;
(4) la causa de V4.5 reproducida; (5) límites, STOP, pausas y método: iguales que en V4.5 (código idéntico salvo lo permitido).

Ejecutar desde equipo_ia_v3/:   python -B -m unittest discover -s pruebas -t pruebas -p test_eq3_g12_v4_5_1.py -v
"""
import hashlib
import inspect
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import comun  # noqa: F401
from eq3 import evaluar_f1_vram_exp_v4_5 as V45
from eq3 import evaluar_f1_vram_exp_v4_5_1 as V
from eq3 import termica_v4_5 as TM

RAIZ = Path(__file__).resolve().parents[1]
LECTURA = {"temp_C": 53, "freno_hw_termico": True, "freno_sw_termico": False, "freno_hw": False, "freno_hw_potencia": False}
LLAMA_VIVO = [(1234, "llama-server.exe")]


def _g12(procesos):
    """La Termica de G12 con una lectura de freno térmico de hardware, según lo que `procesos_llama()` devuelva."""
    with mock.patch.object(V.servidor_pc, "procesos_llama", return_value=procesos), mock.patch.object(V, "_EN_TAREA", 0):
        t = V.termica_g12(lambda: dict(LECTURA), None)
        t.muestrear()
        return t


class AtribucionG12(unittest.TestCase):
    def test_servidor_propio_vivo_es_critico_y_propio(self):
        t = _g12(LLAMA_VIVO)
        self.assertEqual(t.critico, "freno_termico_hardware")
        self.assertEqual(t.ultima["origen"], "propio")
        self.assertEqual(t.externos, [])

    def test_origen_realmente_incierto_conserva_su_clasificacion(self):
        """Lista de procesos ilegible: NO se atribuye ni a nosotros ni a terceros → crítico «_origen_incierto»."""
        t = _g12(None)
        self.assertEqual(t.critico, "freno_termico_hardware_origen_incierto")
        self.assertEqual(t.ultima["origen"], "incierto")

    def test_error_al_consultar_los_procesos_tambien_es_incierto(self):
        with mock.patch.object(V.servidor_pc, "procesos_llama", side_effect=OSError("sin acceso")), \
                mock.patch.object(V, "_EN_TAREA", 0):
            t = V.termica_g12(lambda: dict(LECTURA), None)
            t.muestrear()
        self.assertEqual(t.critico, "freno_termico_hardware_origen_incierto")

    def test_sin_ningun_llama_es_externo_y_no_critico(self):
        t = _g12([])
        self.assertIsNone(t.critico)
        self.assertEqual(t.ultima["origen"], "externo")
        self.assertEqual(len(t.externos), 1)

    def test_externo_a_temperatura_insegura_sigue_siendo_critico(self):
        with mock.patch.object(V.servidor_pc, "procesos_llama", return_value=[]), mock.patch.object(V, "_EN_TAREA", 0):
            t = V.termica_g12(lambda: LECTURA | {"temp_C": TM.T_EXTERNA_MAX}, None)
            t.muestrear()
        self.assertTrue(str(t.critico).startswith("externa_insegura_"))

    def test_tarea_en_curso_es_propia_aunque_no_se_vea_el_proceso(self):
        with mock.patch.object(V.servidor_pc, "procesos_llama", return_value=[]), mock.patch.object(V, "_EN_TAREA", 1):
            t = V.termica_g12(lambda: dict(LECTURA), None)
            t.muestrear()
        self.assertEqual(t.critico, "freno_termico_hardware")

    def test_causa_de_v4_5_reproducida(self):
        """La Termica SIN `propio_activo` (como la de G12 en V4.5) da «incierto» con la misma lectura y el servidor vivo."""
        with mock.patch.object(V.servidor_pc, "procesos_llama", return_value=LLAMA_VIVO):
            t = TM.Termica(registro=None, leer=lambda: dict(LECTURA), intervalo=0.5)
            t.muestrear()
        self.assertEqual(t.critico, "freno_termico_hardware_origen_incierto")

    def test_el_helper_usa_la_funcion_real_de_origen(self):
        t = V.termica_g12(lambda: dict(LECTURA), None)
        self.assertIs(t.propio_activo, V.propio_activo)
        self.assertIn("propio_activo=propio_activo", inspect.getsource(V.termica_g12))

    def test_g12_usa_el_helper_y_el_mismo_criterio(self):
        fuente = inspect.getsource(V.corte_termico_real)
        self.assertIn('term = termica_g12(leer, carpeta / "termica.jsonl")', fuente)
        self.assertIn('out["termica"]["critico"] == "freno_termico_hardware"', fuente)    # exacto, no «empieza por»
        self.assertNotIn("startswith(\"freno_termico_hardware\")", fuente)
        self.assertIn("es_termica(out[\"vigia\"][\"excedida\"])", fuente)
        self.assertIn('out["segundos_hasta_interrupcion"] <= 3', fuente)


class PuertasExigenLaAtribucion(unittest.TestCase):
    """G10 y G5 no pueden pasar sin la atribución de G12 ni sin la batería F26."""

    def test_g10_exige_las_pruebas_de_atribucion_de_g12(self):
        orig = V._unittest
        V._unittest = lambda patron, carpeta: {"rc": 1 if "g12" in patron else 0, "resultado": []}
        try:
            with tempfile.TemporaryDirectory() as d:
                r = V.g10_equivalencia(Path(d) / "g10")
        finally:
            V._unittest = orig
        self.assertFalse(r["ok"])
        self.assertEqual(r["atribucion_g12"]["rc"], 1)

    def test_g10_ejecuta_las_pruebas_de_g12_de_v4_5_1(self):
        vistos = []
        orig = V._unittest
        V._unittest = lambda patron, carpeta: vistos.append(patron) or {"rc": 0, "resultado": []}
        try:
            with tempfile.TemporaryDirectory() as d:
                V.g10_equivalencia(Path(d) / "g10")
        finally:
            V._unittest = orig
        self.assertIn("test_eq3_g12_v4_5_1.py", vistos)
        self.assertIn("test_eq3_compartido_v4_5_1.py", vistos)

    def test_g5_incluye_la_bateria_f26_de_v4_5_1(self):
        fuente = inspect.getsource(V.g5)
        self.assertIn('("F26", "v31_f1_vram_exp_v4_5_1")', fuente)
        self.assertIn('("F25", "v31_f1_vram_exp_v4_5")', fuente)


class SinCambiosRespectoAV45(unittest.TestCase):
    PERMITIDAS = {"corte_termico_real", "g10_equivalencia", "g5"}          # lo único que V4.5.1 cambia (y `termica_g12`, nueva)

    @staticmethod
    def _norm(fuente: str) -> str:
        return fuente.replace("V4.5.1", "V4.5").replace("v4_5_1", "v4_5")

    def _definidos(self, mod):
        return {n: o for n, o in vars(mod).items() if (inspect.isfunction(o) or inspect.isclass(o)) and o.__module__ == mod.__name__}

    def test_todo_el_codigo_es_identico_salvo_lo_permitido(self):
        a, b = self._definidos(V45), self._definidos(V)
        self.assertEqual(set(b) - set(a), {"termica_g12"})
        self.assertEqual(set(a) - set(b), set())
        distintas = sorted(n for n in a if self._norm(inspect.getsource(b[n])) != self._norm(inspect.getsource(a[n])))
        self.assertEqual(sorted(set(distintas) - self.PERMITIDAS), [], "funciones o clases cambiadas sin autorización")
        self.assertEqual(sorted(self.PERMITIDAS - set(distintas)), [], "se esperaba que estas SÍ cambiaran")

    def test_constantes_de_V4_5_sin_cambios(self):
        for n in ("E2", "VRAM_TOPE", "PICO_E2_MEDIDO", "CRECIMIENTO_AJENO_MAX", "MARGEN", "VRAM_OTRAS_MAX", "VARIACION_OTRAS_MAX",
                  "UTILIZACION_GPU_MAX", "INACTIVIDAD_MIN_S", "ESCRITORIO", "MAX_ESPERA_PERSONA_S", "ORDEN_FONDO"):
            self.assertEqual(getattr(V, n), getattr(V45, n), n)
        self.assertEqual((V.VRAM_TOPE, V.VRAM_OTRAS_MAX, V.MAX_ESPERA_PERSONA_S, V.ORDEN_FONDO), (6912, 1992, 4 * 3600, "pause"))

    def test_limites_termicos_de_V4_5(self):
        self.assertEqual((TM.T_REANUDAR, TM.MAX_ENFRIAR_S, TM.T_CRITICA, TM.MAX_FRENO_SW_S, TM.MAX_FALLOS_LECTURA,
                          TM.T_EXTERNA_MAX, TM.REPOSO_EXTERNO_S), (60, 180, 88, 20, 3, 92, 300))
        self.assertIs(V.TM, TM)                                           # el MISMO módulo térmico, no una copia

    def test_v4_5_y_su_prerregistro_siguen_intactos(self):
        pre = json.loads((RAIZ / "evaluacion_f1" / "PRERREGISTRO_F1_VRAM_EXP_v4_5.json").read_text(encoding="utf-8"))
        # solo el código (las carpetas que copian las baterías de mutaciones); G1 comprueba también docs y evidencias
        codigo = {a: h for a, h in pre["sha256"].items() if a.startswith(("eq3/", "evaluacion_f1/", "lab_vram/", "pruebas/"))}
        self.assertGreater(len(codigo), 30)
        dif = [a for a, h in codigo.items()
               if not (RAIZ / a).is_file() or hashlib.sha256((RAIZ / a).read_bytes()).hexdigest() != h]
        self.assertEqual(dif, [])
        self.assertIn("eq3/termica_v4_5.py", pre["sha256"])
        self.assertIn("eq3/evaluar_f1_vram_exp_v4_5.py", pre["sha256"])


if __name__ == "__main__":
    unittest.main()
