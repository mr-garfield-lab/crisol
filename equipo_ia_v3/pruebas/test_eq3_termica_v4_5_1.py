"""[V4.5.1: copia de la de V4.5, apuntando a V4.5.1]
[V4.5: copia de las de V4.4, apuntando a V4.5] Pruebas SIMULADAS del protocolo térmico de V3.1 F1-VRAM-EXP-V4.4 (`eq3/termica_v4_4.py` y su cableado).

Ejecutar desde equipo_ia_v3/:   python -B -m unittest discover -s pruebas -t pruebas -p test_eq3_termica_v4_5_1.py -v

Sensores SIMULADOS (lecturas inyectadas); el flujo de `EV.ejecutar_tarea` (S1, S1×3, E3 de V2-F.1) es el real con un
backend de guion. No lanza Qwen ni toca la GPU.
"""
import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path

import comun  # noqa: F401
import aux_procedencia_v4_3 as A
from eq2 import inferencia
from eq3 import evaluar_f1 as EV
from eq3 import evaluar_f1_vram_exp_v4_5_1 as V
from eq3 import termica_v4_5 as TM

TAREAS, ORACULOS = EV.E.cargar()
LINEA = "41, Not Active, Not Active, Not Active, Not Active, 0x0000000000000001, 427, 810, 37, P5, 43, 1020, [N/A]"


def _tmp(caso) -> Path:
    d = tempfile.TemporaryDirectory(prefix="eq3_v44_", dir=os.environ.get("TMPDIR"))
    caso.addCleanup(d.cleanup)
    return Path(d.name).resolve()


def lec(temp=50, **k):
    return {"temp_C": temp, "freno_hw_termico": False, "freno_sw_termico": False, "freno_hw": False,
            "freno_hw_potencia": False} | k


class Reloj:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def termica_de(lecturas, reloj=None, paso=1.0):
    """Termica con lecturas en secuencia (la última se repite) y un reloj que avanza `paso` por lectura."""
    it, ultima, r = iter(lecturas), {"v": None}, reloj or Reloj()

    def leer():
        r.t += paso
        ultima["v"] = next(it, ultima["v"])
        return dict(ultima["v"])
    # V4.5: Equipo IA ACTIVO (origen «propio»), como suponía V4.4; el origen se prueba en test_eq3_compartido_v4_5_1
    return TM.Termica(leer=leer, reloj=r, intervalo=0.01, propio_activo=lambda: True), r


class TermicaFalsa:
    """Para el cableado: cuenta las esperas y puede volverse crítica."""

    def __init__(self):
        self.enfriados, self.critico, self.pico, self.iniciada, self.detenida = 0, None, 55, False, False

    def enfriar(self, dormir=None):
        self.enfriados += 1
        if self.critico:
            return {"ok": False, "motivo": self.critico, "enfriamiento_s": 0.0, "temp_inicio_C": 90, "temp_fin_C": 90}
        return {"ok": True, "enfriamiento_s": 1.5, "temp_inicio_C": 70, "temp_fin_C": 60}

    def motivo_parada(self):
        return self.critico

    def resumen(self):
        return {"critico": self.critico, "enfriados": self.enfriados}

    def iniciar(self):
        self.iniciada = True
        return self

    def detener(self):
        self.detenida = True
        return self.resumen()


class TestLectura(unittest.TestCase):
    def test_parsear_y_ausentes(self):
        d = TM.parsear(LINEA)
        self.assertEqual((d["temp_C"], d["freno_hw_termico"], d["freno_sw_termico"], d["ventilador_pct"],
                          d["reloj_sm_MHz"], d["pstate"]), (41, False, False, 37, 427, "P5"))
        self.assertIsNone(d["potencia_W"])                               # [N/A]: no se inventa
        self.assertIn("error", TM.parsear("41, Active"))
        self.assertTrue(TM.parsear(LINEA.replace("41, Not Active", "84, Active", 1))["freno_hw_termico"])

    def test_sensor_que_falla(self):
        def roto(*a, **k):
            raise FileNotFoundError("nvidia-smi")
        self.assertIn("error", TM.leer_gpu(ejecutar=roto))
        self.assertIn("error", TM.leer_gpu(ejecutar=lambda *a, **k: type("R", (), {"stdout": ""})()))


class TestCriterios(unittest.TestCase):
    def cruzar(self, lecturas, paso=1.0):
        t, _ = termica_de(lecturas, paso=paso)
        for _ in lecturas:
            t.muestrear()
        return t

    def test_freno_de_hardware_es_inmediato(self):
        self.assertEqual(self.cruzar([lec(60, freno_hw_termico=True)]).critico, "freno_termico_hardware")
        self.assertEqual(self.cruzar([lec(60, freno_hw=True)]).critico, "freno_hardware")
        self.assertEqual(self.cruzar([lec(60, freno_hw_potencia=True)]).critico, "freno_hardware")

    def test_temperatura_critica(self):
        self.assertIsNone(self.cruzar([lec(TM.T_CRITICA - 1)] * 5).critico)
        self.assertEqual(self.cruzar([lec(TM.T_CRITICA)]).critico, f"temperatura_{TM.T_CRITICA}C")

    def test_freno_de_software_sostenido(self):
        n = TM.MAX_FRENO_SW_S
        self.assertIsNone(self.cruzar([lec(83, freno_sw_termico=True)] * n).critico)       # 19 s
        self.assertTrue(self.cruzar([lec(83, freno_sw_termico=True)] * (n + 1)).critico.startswith(
            "freno_termico_software"))
        intermitente = [lec(83, freno_sw_termico=True)] * (n - 2) + [lec(80)] + [lec(83, freno_sw_termico=True)] * (n - 2)
        t = self.cruzar(intermitente)
        self.assertIsNone(t.critico)
        self.assertGreater(t.freno_sw_total_s, 0)

    def test_fallo_de_supervision(self):
        self.assertIsNone(self.cruzar([{"error": "x"}] * (TM.MAX_FALLOS_LECTURA - 1) + [lec(50)]).critico)
        self.assertTrue(self.cruzar([{"error": "x"}] * TM.MAX_FALLOS_LECTURA).critico.startswith("fallo_supervision"))
        self.assertTrue(self.cruzar([lec(None)] * TM.MAX_FALLOS_LECTURA).critico.startswith("fallo_supervision"))

    def test_hilo_que_falla_o_muere(self):
        def explota():
            raise RuntimeError("x")
        t = TM.Termica(leer=explota, intervalo=0.01).iniciar()
        for _ in range(200):
            if t.critico:
                break
            time.sleep(0.01)
        t.detener()
        self.assertTrue(t.critico.startswith("fallo_supervision"))
        t2 = TM.Termica(leer=lambda: lec(50), intervalo=0.01)
        t2._hilo = threading.Thread(target=lambda: None)
        t2._hilo.start()
        t2._hilo.join()
        self.assertEqual(t2.motivo_parada(), "fallo_supervision_hilo_muerto")

    def test_registro_jsonl(self):
        d = _tmp(self)
        t, _ = termica_de([lec(50), lec(90)])
        t.registro = d / "t.jsonl"
        t.muestrear()
        t.muestrear()
        filas = [json.loads(x) for x in (d / "t.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([f["temp_C"] for f in filas], [50, 90])
        self.assertEqual(filas[-1]["critico"], "temperatura_90C")


class TestEnfriar(unittest.TestCase):
    def test_espera_hasta_reanudar(self):
        t, r = termica_de([lec(78), lec(70), lec(64), lec(TM.T_REANUDAR)])
        e = t.enfriar(dormir=lambda s: None)
        self.assertTrue(e["ok"])
        # 4 lecturas de 1 s (el reloj cuenta desde ANTES de la primera)
        self.assertEqual((e["temp_inicio_C"], e["temp_fin_C"], e["enfriamiento_s"]), (78, TM.T_REANUDAR, 4.0))
        self.assertEqual(t.pico, TM.T_REANUDAR)

    def test_no_reanuda_con_freno_de_software(self):
        t, _ = termica_de([lec(55, freno_sw_termico=True), lec(55)])
        e = t.enfriar(dormir=lambda s: None)
        self.assertTrue(e["ok"])
        self.assertEqual(e["enfriamiento_s"], 2.0)                    # esperó una lectura más

    def test_espera_maxima_aborta(self):
        t, _ = termica_de([lec(70)], paso=30.0)
        e = t.enfriar(dormir=lambda s: None)
        self.assertFalse(e["ok"])
        self.assertTrue(e["motivo"].startswith("enfriamiento_no_alcanzado"))
        self.assertEqual(t.critico, e["motivo"])

    def test_critico_durante_la_espera(self):
        t, _ = termica_de([lec(75), lec(76, freno_hw_termico=True)])
        e = t.enfriar(dormir=lambda s: None)
        self.assertEqual((e["ok"], e["motivo"]), (False, "freno_termico_hardware"))


class TestVigia(unittest.TestCase):
    def vigia(self):
        return V.VigiaTermica(act=lambda: {"inactividad_s": 1e9, "sesiones": {}, "notificacion": 5, "motivos": []},
                              medir=lambda: {"usada": 1000})

    def test_corta_y_ejecuta_acciones(self):
        f = TermicaFalsa()
        with V.termica_activa(f):
            v, hechas = self.vigia(), []
            v.agregar_accion(lambda: hechas.append("STOP"))
            self.assertIsNone(v.parar())
            f.critico = "freno_termico_hardware"
            self.assertEqual(v.parar(), "termica_critica_freno_termico_hardware")
            self.assertEqual(hechas, ["STOP"])
            v._muestrear()
            self.assertEqual(hechas, ["STOP"])                       # una sola vez

    def test_sin_termica_falla_cerrado(self):
        self.assertTrue(V.es_termica(self.vigia().parar()))

    def test_la_vram_sigue_mandando(self):
        f = TermicaFalsa()
        with V.termica_activa(f):
            v = V.VigiaTermica(act=lambda: {"inactividad_s": 1e9, "sesiones": {}, "notificacion": 5, "motivos": []},
                               medir=lambda: {"usada": 99999})
            v._muestrear()
            self.assertTrue(v.parar().startswith("vram_excedida"))


class TestProtector(unittest.TestCase):
    def test_enfria_antes_de_cada_peticion_y_separa_tiempos(self):
        f, reg = TermicaFalsa(), []
        be = V.proteger_backend_v44(A.Guion(), ORACULOS, reg, "E3", f)
        for _ in range(3):
            be.completar([{"role": "system", "content": "Eres A2"}, {"role": "user", "content": "hola"}], 10, 1)
        self.assertEqual(f.enfriados, 3)
        self.assertTrue(all(r["enfriamiento_s"] == 1.5 and "generacion_s" in r and r["pico_C"] == 55 for r in reg))

    def test_sin_enfriar_no_se_envia_nada(self):
        f, reg, g = TermicaFalsa(), [], A.Guion()
        f.critico = "enfriamiento_no_alcanzado_70C_en_180s"
        be = V.proteger_backend_v44(g, ORACULOS, reg, "S1", f)
        with self.assertRaises(inferencia.ErrorInferencia) as e:
            be.completar([{"role": "user", "content": "hola"}], 10, 1)
        self.assertTrue(e.exception.motivo.startswith("termica_critica"))
        self.assertEqual(g.prompts, [])
        be2 = V.proteger_backend_v44(A.Guion(), ORACULOS, [], "S1", None)
        with self.assertRaises(inferencia.ErrorInferencia):
            be2.completar([{"role": "user", "content": "hola"}], 10, 1)

    def test_tiempos_termicos(self):
        t = V.tiempos_termicos({"segundos_total": 30, "metricas": {"peticiones": [
            {"enfriamiento_s": 5, "generacion_s": 10, "pico_C": 70}, {"enfriamiento_s": 0, "generacion_s": 8,
                                                                       "pico_C": 81}]}})
        self.assertEqual(t, {"peticiones": 2, "enfriamiento_s": 5, "generacion_s": 18, "trabajo_s": 25, "total_s": 30,
                             "pico_C": 81, "esperas": 1, "espera_humana_s": None, "intentos_interrumpidos": 0})


class Lento(A.Guion):
    """Una generación LARGA (hasta 10 s) que, como BackendLlama, consulta `parar` mientras dura."""

    def iniciar(self, ctx=None):
        super().iniciar(ctx)
        self.ctx = ctx or {}

    def completar(self, mensajes, max_tokens, plazo_s):
        t0 = time.monotonic()
        while time.monotonic() - t0 < 10:
            m = (self.ctx.get("parar") or (lambda: None))()
            if m:
                raise inferencia.ErrorInferencia(m, fatal=True)
            time.sleep(0.05)
        return super().completar(mensajes, max_tokens, plazo_s)


class TestIntegracionFlujoReal(unittest.TestCase):
    """REAL: `EV.ejecutar_tarea` y V2-F.1. SIMULADO: el modelo y los sensores."""

    @classmethod
    def setUpClass(cls):
        EV.preparar_contexto()

    def vigia(self):
        return V.VigiaTermica(act=lambda: {"inactividad_s": 1e9, "sesiones": {}, "notificacion": 5, "motivos": []},
                              medir=lambda: {"usada": 1000}, intervalo=0.05).iniciar()

    def test_mismo_protocolo_en_los_tres_metodos(self):
        for c in ("S1", "S1x3", "E3"):
            f, be = TermicaFalsa(), A.Guion()
            vig = self.vigia()
            try:
                with V.termica_activa(f), V._protector_v44(c):
                    fila = EV.ejecutar_tarea(c, TAREAS["T10"], ORACULOS["T10"], ORACULOS, _tmp(self) / c,
                                             lambda: be, vig)
            finally:
                vig.detener()
            pet = fila["metricas"]["peticiones"]
            self.assertEqual(f.enfriados, len(be.prompts), c)          # una espera por CADA petición
            self.assertEqual(len(pet), len(be.prompts), c)
            self.assertTrue(all("enfriamiento_s" in p and "generacion_s" in p for p in pet), c)
            t = V.tiempos_termicos(fila)
            self.assertEqual(t["enfriamiento_s"], 1.5 * len(be.prompts), c)
            self.assertAlmostEqual(t["trabajo_s"], fila["segundos_total"] - t["enfriamiento_s"], places=2)

    def test_una_generacion_larga_no_elude_la_vigilancia(self):
        for c in ("S1", "E3"):
            with self.subTest(c):
                f, vig = TermicaFalsa(), self.vigia()
                threading.Timer(0.4, lambda: setattr(f, "critico", "freno_termico_hardware")).start()
                t0, d = time.monotonic(), _tmp(self) / c
                try:
                    with V.termica_activa(f), self.assertRaises(EV.Abortada) as e:
                        V.ejecutar_tarea_e2(c, TAREAS["T10"], ORACULOS["T10"], ORACULOS, d, lambda: Lento(), vig)
                finally:
                    vig.detener()
                self.assertLess(time.monotonic() - t0, 5)              # no esperó los 10 s de la generación
                self.assertIn("termica_critica", str(e.exception))
                self.assertTrue((d / "fila_termica.json").is_file())

    def test_sin_termica_no_se_ejecuta(self):
        with self.assertRaises(EV.Abortada) as e:
            V.ejecutar_tarea_e2("S1", TAREAS["T10"], ORACULOS["T10"], ORACULOS, _tmp(self) / "x", lambda: A.Guion(),
                                self.vigia())
        self.assertIn("sin vigilancia térmica", str(e.exception))


class TestG10(unittest.TestCase):
    def test_g10_exige_las_pruebas_termicas(self):
        orig = V._unittest
        V._unittest = lambda patron, carpeta: {"rc": 1 if "termica" in patron else 0, "resultado": []}
        try:
            r = V.g10_equivalencia(_tmp(self) / "g10")
        finally:
            V._unittest = orig
        self.assertFalse(r["ok"])
        self.assertTrue(r["estatico"]["comparar_usa_e2_para_todas"])


class TestComparar(unittest.TestCase):
    def test_aborto_termico_anotado_y_fondo_restaurado(self):
        from eq3 import majflt_windows
        d = _tmp(self)
        pu = d / "puertas.json"
        pu.write_text(json.dumps({"variante": V.VARIANTE, "ok": True, "codigo": V.huella_codigo()}), encoding="utf-8")
        restaurado, f = [], TermicaFalsa()

        class Fondo:                                              # una prueba NUNCA toca el Wallpaper Engine real
            def __init__(self, **k):
                self.registro, self.c = [], type("C", (), {"estado": "detenido"})()

            def liberar(self):
                return True

            def restaurar(self):
                restaurado.append(True)
                self.registro.append({"accion": "restaurar", "ok": True})
                return True

        def bucle(*a, **k):
            raise EV.Abortada("termica_critica en T02 (E3): freno_termico_hardware")
        orig = (V.comprobar_v4, V.FondoAnimado, V.esperar_v4, V.X.ejecutar_bucle, majflt_windows.activar, V.nueva_termica)
        V.comprobar_v4, V.FondoAnimado = (lambda: []), Fondo
        V.esperar_v4 = lambda fondo, **k: {"ok": True, "motivos": []}
        V.X.ejecutar_bucle, majflt_windows.activar = bucle, (lambda carpeta: {"simulado": True})
        V.nueva_termica = lambda registro: f
        try:
            with self.assertRaises(EV.Abortada):
                V.comparar(d, d / "vram_exp_v4_5_x", pu)
        finally:
            (V.comprobar_v4, V.FondoAnimado, V.esperar_v4, V.X.ejecutar_bucle, majflt_windows.activar,
             V.nueva_termica) = orig
        res = json.loads((d / "vram_exp_v4_5_x" / "comparacion.json").read_text(encoding="utf-8"))
        self.assertIn("termica_critica", res["abortada"])
        self.assertIs(res["valida"], False)
        self.assertEqual(restaurado, [True])
        self.assertTrue(f.iniciada and f.detenida)
        self.assertIsNone(V._TERMICA)


if __name__ == "__main__":
    unittest.main()
