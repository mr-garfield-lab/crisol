"""[V4.5.1: copia de la de V4.5, apuntando a V4.5.1]
Pruebas SIMULADAS de V3.1 F1-VRAM-EXP-V4.5: PC compartido (origen de los eventos térmicos, esperas de hasta 4 h,
STOP global) e integridad metodológica con pausas.

Ejecutar desde equipo_ia_v3/:   python -B -m unittest discover -s pruebas -t pruebas -p test_eq3_compartido_v4_5_1.py -v

Sensores, personas y procesos SIMULADOS; el bucle (`ejecutar_bucle`) y `EV.ejecutar_tarea` (V2-F.1) son los reales con
un backend de guion. No lanza Qwen ni toca la GPU ni otras aplicaciones.
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


def _tmp(caso) -> Path:
    d = tempfile.TemporaryDirectory(prefix="eq3_v45_", dir=os.environ.get("TMPDIR"))
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


def termica(lecturas, origen, reloj=None):
    it, ult, r = iter(lecturas), {"v": None}, reloj or Reloj()

    def leer():
        r.t += 1
        ult["v"] = next(it, ult["v"])
        return dict(ult["v"])
    return TM.Termica(leer=leer, reloj=r, intervalo=0.01, propio_activo=origen), r


class TestOrigen(unittest.TestCase):
    def muestrear(self, lecturas, origen):
        t, r = termica(lecturas, origen)
        for _ in lecturas:
            t.muestrear()
        return t, r

    def test_propio_es_critico(self):
        t, _ = self.muestrear([lec(70, freno_hw_termico=True)], lambda: True)
        self.assertEqual(t.critico, "freno_termico_hardware")

    def test_externo_verificado_no_es_critico_pero_obliga_a_esperar(self):
        t, r = self.muestrear([lec(74, freno_hw_termico=True), lec(85), lec(88)], lambda: False)
        self.assertIsNone(t.critico)
        self.assertEqual([e["motivo"] for e in t.externos], ["freno_termico_hardware", "temperatura_88C"])
        self.assertFalse(t.reposo_externo_ok())
        r.t += TM.REPOSO_EXTERNO_S
        self.assertTrue(t.reposo_externo_ok())
        self.assertEqual(t.resumen()["interferencias_externas"][0]["temp_C"], 74)

    def test_externo_inseguro_o_incierto_es_critico(self):
        t, _ = self.muestrear([lec(TM.T_EXTERNA_MAX, freno_hw_termico=True)], lambda: False)
        self.assertTrue(t.critico.startswith("externa_insegura"))
        for origen in (lambda: None, lambda: 1 / 0):
            t, _ = self.muestrear([lec(74, freno_hw_termico=True)], origen)
            self.assertEqual(t.critico, "freno_termico_hardware_origen_incierto")

    def test_sin_sensor_es_critico_aunque_sea_externo(self):
        t, _ = self.muestrear([{"error": "x"}] * TM.MAX_FALLOS_LECTURA, lambda: False)
        self.assertTrue(t.critico.startswith("fallo_supervision"))

    def test_freno_sw_sostenido_externo(self):
        t, _ = self.muestrear([lec(83, freno_sw_termico=True)] * (TM.MAX_FRENO_SW_S + 2), lambda: False)
        self.assertIsNone(t.critico)
        self.assertTrue(t.externos[0]["motivo"].startswith("freno_termico_software"))

    def test_propio_activo(self):
        orig = V.servidor_pc.procesos_llama
        try:
            for llamas, esperado in ((None, None), ([], False), ([(7, "llama-server.exe")], True)):
                V.servidor_pc.procesos_llama = lambda llamas=llamas: llamas
                self.assertIs(V.propio_activo(), esperado)
            V.servidor_pc.procesos_llama = lambda: []
            V._EN_TAREA = 1
            self.assertIs(V.propio_activo(), True)
        finally:
            V._EN_TAREA, V.servidor_pc.procesos_llama = 0, orig


class TermicaFalsa:
    def __init__(self, critico=None, reposo=True, espera=1.5):
        self.critico, self.reposo, self.espera, self.enfriados, self.pico = critico, reposo, espera, 0, 55

    def motivo_parada(self):
        return self.critico

    def reposo_externo_ok(self):
        return self.reposo() if callable(self.reposo) else self.reposo

    def enfriar(self, dormir=None):
        self.enfriados += 1
        return {"ok": True, "enfriamiento_s": self.espera, "temp_inicio_C": 70, "temp_fin_C": 60}

    def resumen(self):
        return {"critico": self.critico}


class TestEsperar(unittest.TestCase):
    def esperar(self, rondas_ocupado, max_s=V.MAX_ESPERA_PERSONA_S, termica_=None, stop=None):
        r, llamadas, pausas = Reloj(), [], []

        def base(fondo, **k):
            llamadas.append(1)
            ok = len(llamadas) > rondas_ocupado
            return {"ok": ok, "motivos": [] if ok else ["persona", "uso_gpu_70pct"]}

        def dormir(s):
            r.t += s
        V._STOP_GLOBAL = stop
        try:
            with V.termica_activa(termica_ or TermicaFalsa()):
                c = V.esperar_v45(None, pausas=pausas, base=base, max_espera_s=max_s, dormir=dormir, reloj=r)
        finally:
            V._STOP_GLOBAL = None
        return c, pausas, llamadas

    def test_espera_y_registra_la_pausa(self):
        c, pausas, _ = self.esperar(3)
        self.assertTrue(c["ok"])
        self.assertEqual(c["esperado_s"], 3 * V.X.ESPERA_REINTENTO_S)
        self.assertEqual(pausas, [{"inicio": pausas[0]["inicio"], "esperado_s": 3 * V.X.ESPERA_REINTENTO_S,
                                   "motivos": ["persona", "uso_gpu_70pct"], "ok": True}])

    def test_sin_pausa_no_se_anota(self):
        c, pausas, _ = self.esperar(0)
        self.assertEqual((c["ok"], pausas), (True, []))

    def test_cuatro_horas_y_no_mas(self):
        n = int(V.MAX_ESPERA_PERSONA_S / V.X.ESPERA_REINTENTO_S)
        c, pausas, llamadas = self.esperar(n - 2)                  # algo menos de 4 h: sigue
        self.assertTrue(c["ok"])
        c, pausas, _ = self.esperar(10 ** 6)                        # siempre ocupado: no ok al llegar a 4 h
        self.assertFalse(c["ok"])
        self.assertGreaterEqual(c["esperado_s"], V.MAX_ESPERA_PERSONA_S)
        self.assertLess(c["esperado_s"], V.MAX_ESPERA_PERSONA_S + 2 * V.X.ESPERA_REINTENTO_S)
        self.assertFalse(pausas[-1]["ok"])

    def test_critico_o_stop_vuelven_en_el_acto(self):
        c, pausas, llamadas = self.esperar(10 ** 6, termica_=TermicaFalsa(critico="freno_termico_hardware"))
        self.assertEqual((c["ok"], c["motivos"], c["esperado_s"], llamadas), (False, ["termica_critica_freno_termico_hardware"],
                                                                             0.0, []))
        d = _tmp(self)
        (d / "STOP").write_text("x", encoding="utf-8")
        c, _, llamadas = self.esperar(10 ** 6, stop=d / "STOP")
        self.assertEqual((c["ok"], c["motivos"], llamadas), (False, ["stop_global"], []))

    def test_interferencia_externa_reciente_hace_esperar(self):
        estado = {"n": 0}

        def reposo():
            estado["n"] += 1
            return estado["n"] > 2
        c, pausas, _ = self.esperar(0, termica_=TermicaFalsa(reposo=reposo))
        self.assertTrue(c["ok"])
        self.assertIn("interferencia_termica_externa_reciente", pausas[0]["motivos"])


class VigiaFalso:
    def __init__(self, motivo=None):
        self.excedida, self.tope, self.acciones = motivo, 6912, []

    def iniciar(self):
        return self

    def detener(self):
        return {"excedida": self.excedida}


class TestIntegridadDelBucle(unittest.TestCase):
    def test_noventa_filas_sin_perder_ni_duplicar_con_pausas_e_interrupciones(self):
        d, llamadas, cortes = _tmp(self), [], {("E3", "T05", 2): 1}
        vigias = []

        def ejecutar(c, tarea, oraculo, oraculos, carpeta, be, vigia):
            rep = carpeta.parent.parent.parent.name                  # SALIDA/r{rep}/{C}/{T}/intento{n}
            llamadas.append((c, tarea["id"], rep, carpeta.name))
            clave = (c, tarea["id"], int(rep[1:]))
            if cortes.get(clave):
                cortes[clave] -= 1
                vigia.excedida = "actividad_de_terceros_entrada_durante_la_tarea"
            return {"evaluacion": {"categoria": "CORRECTO", "calidad": "CORRECTO", "seguridad": "seguro", "motivo": ""},
                    "segundos_total": 1, "metricas": {"tokens_prompt": 1, "tokens_generados": 1},
                    "prompt_primer_paso_sha256": f"{c}-{tarea['id']}"}
        ocupado = iter([False] * 3 + [True] * 2 + [False] * 1000)
        res = {"filas": [], "bloques": []}
        r = Reloj()

        def base(fondo, **k):
            o = next(ocupado)
            return {"ok": not o, "motivos": ["persona"] if o else []}
        pausas = []
        with V.termica_activa(TermicaFalsa()):
            V.X.ejecutar_bucle(res, d, {t: {"id": t} for t in TAREAS}, ORACULOS, list(TAREAS), (1, 2),
                               ejecutar=ejecutar, fabrica=lambda ver: None,
                               esperar=lambda: V.esperar_v45(None, pausas=pausas, base=base, dormir=lambda s: setattr(
                                   r, "t", r.t + s), reloj=r),
                               vigia_fn=lambda: vigias.append(VigiaFalso()) or vigias[-1])
        claves = [(f["repeticion"], f["configuracion"], f["tarea"]) for f in res["filas"]]
        esperado = [(rep, c, t) for rep in (1, 2) for c in EV.ORDEN[rep] for t in TAREAS]
        self.assertEqual(claves, esperado)                             # 90, en orden, sin huecos ni duplicados
        self.assertEqual(len(set(claves)), 90)
        self.assertTrue(res["valida"])
        corte = json.loads((d / "r2" / "E3" / "T05" / "fila.json").read_text(encoding="utf-8"))
        self.assertEqual([i["intento"] for i in corte["intentos_interrumpidos"]], ["intento1"])
        self.assertEqual(len([l for l in llamadas if l[:3] == ("E3", "T05", "r2")]), 2)      # se repitió desde cero
        self.assertEqual(len(pausas), 1)
        self.assertEqual(pausas[0]["motivos"], ["persona"])


class TestPausasNoAlteranElMetodo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        EV.preparar_contexto()

    def correr(self, c, espera):
        f, be = TermicaFalsa(espera=espera), A.Guion()
        vig = V.VigiaTermica(act=lambda: {"inactividad_s": 1e9, "sesiones": {}, "notificacion": 5, "motivos": []},
                             medir=lambda: {"usada": 1000}, intervalo=0.05).iniciar()
        try:
            with V.termica_activa(f), V._protector_v44(c):
                fila = EV.ejecutar_tarea(c, TAREAS["T10"], ORACULOS["T10"], ORACULOS, _tmp(self) / c, lambda: be, vig)
        finally:
            vig.detener()
        return fila, be

    def test_mismos_prompts_semillas_y_resultado_con_y_sin_pausas(self):
        for c in ("S1", "S1x3", "E3"):
            a, be_a = self.correr(c, 0.0)
            b, be_b = self.correr(c, 120.0)
            clave = lambda f: [(p.get("sha256"), p.get("temperatura"), p.get("semilla"), p.get("max_tokens"))
                               for p in f["metricas"]["peticiones"]]
            self.assertEqual(clave(a), clave(b), c)
            self.assertEqual(be_a.prompts, be_b.prompts, c)
            self.assertEqual(a["evaluacion"], b["evaluacion"], c)
            self.assertEqual(a["prompt_primer_paso_sha256"], b["prompt_primer_paso_sha256"], c)
            self.assertEqual(V.tiempos_termicos(b)["enfriamiento_s"], 120.0 * len(be_b.prompts), c)


class Lento(A.Guion):
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


class TestStopGlobal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        EV.preparar_contexto()

    def test_stop_corta_la_generacion_y_aborta(self):
        for c in ("S1", "E3"):
            with self.subTest(c):
                d = _tmp(self)
                stop = d / "STOP"
                V._STOP_GLOBAL, t0, vig = stop, time.monotonic(), None
                try:
                    with V.termica_activa(TermicaFalsa()), self.assertRaises(EV.Abortada) as e:
                        # como en comparar: el vigía arranca con la térmica YA activa
                        vig = V.VigiaTermica(act=lambda: {"inactividad_s": 1e9, "sesiones": {}, "notificacion": 5,
                                                          "motivos": []}, medir=lambda: {"usada": 1000},
                                             intervalo=0.05).iniciar()
                        threading.Timer(0.4, lambda: stop.write_text("x", encoding="utf-8")).start()
                        V.ejecutar_tarea_e2(c, TAREAS["T10"], ORACULOS["T10"], ORACULOS, d / "t", lambda: Lento(), vig)
                finally:
                    V._STOP_GLOBAL = None
                    if vig:
                        vig.detener()
                self.assertLess(time.monotonic() - t0, 5)
                self.assertIn("stop_global", str(e.exception))
                self.assertTrue((d / "t" / "fila_stop.json").is_file())
                self.assertEqual(V._EN_TAREA, 0)                          # el contador se libera siempre

    def test_vigia_y_acciones(self):
        d = _tmp(self)
        V._STOP_GLOBAL = d / "STOP"
        try:
            with V.termica_activa(TermicaFalsa()):
                v, hechas = V.VigiaTermica(act=lambda: {"inactividad_s": 1e9, "sesiones": {}, "notificacion": 5,
                                                        "motivos": []}, medir=lambda: {"usada": 1000}), []
                v.agregar_accion(lambda: hechas.append("STOP_E3"))
                self.assertIsNone(v.parar())
                (d / "STOP").write_text("x", encoding="utf-8")
                self.assertEqual(v.parar(), "stop_global")
                self.assertEqual(hechas, ["STOP_E3"])
        finally:
            V._STOP_GLOBAL = None


class TestTiempos(unittest.TestCase):
    def test_espera_humana_separada(self):
        t = V.tiempos_termicos({"segundos_total": 30, "espera_previa": {"esperado_s": 600},
                                "intentos_interrumpidos": [{"intento": "intento1"}],
                                "metricas": {"peticiones": [{"enfriamiento_s": 5, "generacion_s": 10, "pico_C": 70}]}})
        self.assertEqual((t["espera_humana_s"], t["intentos_interrumpidos"], t["enfriamiento_s"], t["trabajo_s"]),
                         (600, 1, 5, 25))


class TestCompararV45(unittest.TestCase):
    def test_comparar_usa_esperar_v45_y_limpia_el_stop(self):
        import inspect
        fuente = inspect.getsource(V.comparar)
        self.assertIn('esperar=lambda: esperar_v45(fondo, pausas=res["pausas"])', fuente)
        self.assertIn("_STOP_GLOBAL = None", fuente)
        self.assertEqual(V.MAX_ESPERA_PERSONA_S, 4 * 3600)
        self.assertIsNone(V._STOP_GLOBAL)

    def test_nueva_termica_atribuye_origen(self):
        t = V.nueva_termica(None)
        self.assertIs(t.propio_activo, V.propio_activo)

    def test_g10_exige_las_pruebas_de_pc_compartido(self):
        orig = V._unittest
        V._unittest = lambda patron, carpeta: {"rc": 1 if "compartido" in patron else 0, "resultado": []}
        try:
            r = V.g10_equivalencia(_tmp(self) / "g10")
        finally:
            V._unittest = orig
        self.assertFalse(r["ok"])


if __name__ == "__main__":
    unittest.main()
