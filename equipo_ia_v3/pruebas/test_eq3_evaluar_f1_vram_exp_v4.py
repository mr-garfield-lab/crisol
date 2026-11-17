"""Pruebas SIMULADAS de V3.1 F1-VRAM-EXP-V4 (`eq3/evaluar_f1_vram_exp_v4.py`): E2, presupuesto, persona ≠ GPU,
Wallpaper Engine reversible y configuración efectiva de llama.cpp. Nada generado se ejecuta; no se lanza ningún modelo.

Ejecutar desde equipo_ia_v3/:   python -B -m unittest discover -s pruebas -t pruebas -p test_eq3_evaluar_f1_vram_exp_v4.py -v
"""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import comun  # noqa: F401
from eq3 import evaluar_f1 as EV
from eq3 import evaluar_f1_vram_exp as X
from eq3 import evaluar_f1_vram_exp_v4 as V

LIBRE = {"inactividad_s": 10_000.0, "sesiones": {}, "notificacion": 5, "motivos": []}
OCUPADA = LIBRE | {"notificacion": 2, "motivos": ["aplicacion_ocupada"]}
ESCRITORIO = lambda: {"clase": "Progman", "pantalla_completa": True}
VIDEO = lambda: {"clase": "MediaPlayerClassicW", "pantalla_completa": True}
LOG_E2 = ("load_tensors: offloaded 29/29 layers to GPU\nllama_context: n_ubatch              = 128\n"
          "llama_context: flash_attn            = enabled\n")


class TestLimitesYE2(unittest.TestCase):
    def test_presupuesto_verificado(self):
        self.assertEqual(V.VRAM_TOPE, 6912)
        self.assertEqual((V.PICO_E2_MEDIDO, V.MARGEN, V.VRAM_OTRAS_MAX), (4420, 500, 1992))
        self.assertGreaterEqual(V.MARGEN, 2 * V.CRECIMIENTO_AJENO_MAX - 2)
        self.assertEqual((EV.VRAM_TOPE, X.VRAM_TOPE_EXP, X.VRAM_OTRAS_MAX_EXP), (6144, 6912, 1832))   # V2/V3 intactas

    def test_e2_explicito(self):
        self.assertEqual(V.E2[:4], ["--fit", "off", "-ngl", "all"])
        for f in ("-c", "-t", "-np", "--ctx-size"):
            self.assertNotIn(f, V.E2)                       # contexto e hilos: los de V2-F.1
        from eq2 import servidor
        srv = servidor.ServidorLlama(8080, comando=["llama-server.exe"] + V.E2)
        argv = srv.construir_argv()
        self.assertEqual(argv[:1 + len(V.E2)], ["llama-server.exe"] + V.E2)   # V2-F.1 solo añade sus opciones
        self.assertIn("--no-ui", argv)

    def test_configuracion_efectiva(self):
        self.assertTrue(V.configuracion_efectiva(LOG_E2)["ok"])
        malos = {"capas_en_cpu": LOG_E2.replace("29/29", "25/29"),
                 "ubatch_por_defecto": LOG_E2.replace("= 128", "= 512"),
                 "fit_activo": LOG_E2 + "common_fit_a: fitting params to device memory ...\n",
                 "sin_registro": ""}
        for nombre, log in malos.items():
            with self.subTest(nombre):
                self.assertFalse(V.configuracion_efectiva(log)["ok"])

    def _tarea(self, log, infra=None):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            if log is not None:
                (d / "runs").mkdir()
                (d / "runs" / "server.log").write_text(log, encoding="utf-8")
            orig = EV.ejecutar_tarea
            EV.ejecutar_tarea = lambda *a: {"evaluacion": {"categoria": "CORRECTO"}, "infraestructura": infra}
            try:
                return V.ejecutar_tarea_e2("S1", {"id": "T01"}, {}, {}, d, None, None)
            except EV.Abortada:
                guardada = json.loads((d / "fila_no_e2.json").read_text(encoding="utf-8"))
                self.assertEqual(guardada["infraestructura"], "configuracion_llama_no_e2")   # queda la evidencia
                raise
            finally:
                EV.ejecutar_tarea = orig

    def test_tarea_sin_e2_aborta_toda_la_evaluacion(self):
        for nombre, log in (("capas_en_cpu", LOG_E2.replace("29/29", "20/29")), ("sin_registro", None)):
            with self.subTest(nombre):
                with self.assertRaises(EV.Abortada):
                    self._tarea(log)
        self.assertTrue(self._tarea(LOG_E2)["llama_efectiva"]["ok"])
        f = self._tarea(None, infra="vram_excedida_7000MiB")       # no llegó a arrancar: no es un fallo de E2
        self.assertEqual(f["infraestructura"], "vram_excedida_7000MiB")


class TestPersona(unittest.TestCase):
    def test_escritorio_no_es_persona_un_video_si(self):
        self.assertFalse(V.persona(act=lambda: OCUPADA, plano=ESCRITORIO)["hay"])
        self.assertTrue(V.persona(act=lambda: OCUPADA, plano=VIDEO)["hay"])
        self.assertTrue(V.persona(act=lambda: OCUPADA, plano=lambda: None)["hay"])          # fallo cerrado

    def test_senales_humanas(self):
        casos = {"entrada": LIBRE | {"inactividad_s": 30.0}, "sin_medida": LIBRE | {"inactividad_s": None},
                 "sesion": LIBRE | {"motivos": ["otra_sesion_activa_[2]"]},
                 "d3d": LIBRE | {"motivos": ["pantalla_completa_d3d"]},
                 "sesiones_no_medibles": LIBRE | {"motivos": ["sesiones_no_medibles"]}}
        for nombre, a in casos.items():
            with self.subTest(nombre):
                self.assertTrue(V.persona(act=lambda a=a: a, plano=ESCRITORIO)["hay"])

    def test_vigia_corta_por_persona_no_por_fondo(self):
        t = [0.0]
        v = X.VigiaExp(medir=lambda: {"usada": 5000}, act=lambda: V.actividad_vigia(lambda: OCUPADA, ESCRITORIO),
                       reloj=lambda: t[0])
        t[0] = 50.0
        v._muestrear()
        self.assertIsNone(v.parar())                                                    # el fondo no corta
        v.act = lambda: V.actividad_vigia(lambda: OCUPADA | {"inactividad_s": 5.0}, ESCRITORIO)
        v._muestrear()
        self.assertTrue(X.por_terceros(v.parar()))                                      # una persona sí
        v = X.VigiaExp(medir=lambda: {"usada": 6913}, act=lambda: V.actividad_vigia(lambda: LIBRE, ESCRITORIO))
        v._muestrear()
        self.assertTrue(X.por_vram(v.parar()))

    def test_condiciones_recursos_aparte(self):
        def cond(mibs, usos, quien=lambda: {"hay": False, "motivos": [], "inactividad_s": 900}):
            it, iu = iter(mibs), iter(usos)
            return V.condiciones(len(mibs) * 2.0, medir=lambda: {"usada": next(it)}, util=lambda: next(iu),
                                 quien=quien, dormir=lambda s: None)
        self.assertTrue(cond([1900, 1992], [5, 5])["ok"])
        self.assertIn("vram_otras_1993MiB", cond([1900, 1993], [5, 5])["recursos"])
        self.assertIn("uso_gpu_41pct", cond([900, 900], [5, 41])["recursos"])
        self.assertIn("vram_inestable_900-1101MiB", cond([900, 1101], [5, 5])["recursos"])
        r = cond([900], [5], quien=lambda: {"hay": True, "motivos": ["entrada_reciente_3s"], "inactividad_s": 3})
        self.assertFalse(r["ok"])
        self.assertEqual(r["recursos"], [])                                             # persona ≠ recursos


class Fondo:
    def __init__(self, para=True):
        self.c = SimpleNamespace(estado="normal", inicial={"abierto": True})
        self.registro, self.para = [], para

    def liberar(self):
        self.registro.append("stop")
        if self.para:
            self.c.estado = "detenido"
        return self.para

    def restaurar(self):
        self.registro.append("play")
        self.c.estado = "normal"
        return True


class TestFondoAnimado(unittest.TestCase):
    def test_se_restaura_siempre(self):
        f = Fondo()
        with self.assertRaises(RuntimeError):
            with V.fondo_gestionado(f):
                f.liberar()
                raise RuntimeError("fallo a mitad")
        self.assertEqual(f.registro, ["stop", "play"])

    def test_persona_recupera_el_fondo_y_luego_se_vuelve_a_detener(self):
        f = Fondo()
        f.liberar()
        quien = iter([{"hay": True, "motivos": ["entrada_reciente_2s"], "inactividad_s": 2},
                      {"hay": False, "motivos": [], "inactividad_s": 900}])
        orig = V.persona
        V.persona = lambda: next(quien)
        t = [0.0]
        try:
            r = V.esperar_v4(f, cond=lambda v: {"ok": True, "motivos": []}, dormir=lambda s: t.__setitem__(0, t[0] + s),
                             reloj=lambda: t[0])
        finally:
            V.persona = orig
        self.assertTrue(r["ok"])
        self.assertEqual(f.registro, ["stop", "play", "stop"])

    def test_fondo_que_no_se_detiene_no_deja_empezar(self):
        f = Fondo(para=False)
        orig = V.persona
        V.persona = lambda: {"hay": False, "motivos": [], "inactividad_s": 900}
        try:
            r = V.esperar_v4(f, cond=lambda v: {"ok": True, "motivos": []}, max_espera_s=0)
        finally:
            V.persona = orig
        self.assertFalse(r["ok"])
        self.assertIn("fondo_no_detenido", r["motivos"])

    def test_solo_wallpaper_engine(self):
        from lab_vram import wallpaper as W
        self.assertEqual(W.NOMBRES, ("wallpaper64.exe", "wallpaper32.exe"))
        import inspect
        fuente = inspect.getsource(W) + inspect.getsource(V)
        self.assertNotIn('"/F"]', fuente)
        self.assertNotIn("Stop-Process", fuente)


class ControlFalso:
    def __init__(self, abierto=True):
        self.inicial = {"abierto": abierto, "procesos": [{"ruta": "we.exe"}] if abierto else []}
        self.estado, self.ordenes = "normal", []

    def capturar(self):
        return self.inicial

    def _exe(self):
        return "we.exe"

    def control(self, orden):
        self.ordenes.append(orden)
        self.estado = {"stop": "detenido", "play": "normal"}[orden]
        return True

    def restaurar(self):
        if self.estado != "normal":
            self.control("play")
        return {"ok": True}


class TestGuardian(unittest.TestCase):
    def test_guardian_antes_de_detener_y_marca_retirada(self):
        with tempfile.TemporaryDirectory() as d:
            marca, lanzados = Path(d) / "m.marca", []
            c = ControlFalso()
            f = V.FondoAnimado(control=c, marca=marca,
                               guardian=lambda pid, m, exe: lanzados.append((pid, m, marca.exists())) or {"rc": 0, "pid": 7})
            self.assertTrue(f.liberar())
            self.assertEqual(len(lanzados), 1)
            self.assertTrue(lanzados[0][2])                     # la marca existía ANTES de lanzar el guardián
            self.assertEqual(c.ordenes, ["stop"])
            self.assertTrue(f.restaurar())
            self.assertFalse(marca.exists())
            self.assertTrue(f.liberar())
            self.assertEqual(len(lanzados), 2)                  # un guardián nuevo por cada detención

    def test_sin_guardian_no_se_detiene(self):
        with tempfile.TemporaryDirectory() as d:
            for nombre, lanzar, marca in (("guardian_falla", lambda *a: {"rc": 8, "pid": None}, Path(d) / "m"),
                                          ("sin_marca", lambda *a: {"rc": 0, "pid": 7}, None)):
                with self.subTest(nombre):
                    c = ControlFalso()
                    f = V.FondoAnimado(control=c, marca=marca, guardian=lanzar)
                    self.assertFalse(f.liberar())
                    self.assertEqual(c.ordenes, [])
                    if marca:
                        self.assertFalse(marca.exists())


class TestPuertasLigadas(unittest.TestCase):
    def test_comparar_rechaza_puertas_de_otro_codigo(self):
        with tempfile.TemporaryDirectory() as d:
            pu = Path(d) / "puertas.json"
            pu.write_text(json.dumps({"variante": V.VARIANTE, "ok": True, "codigo": {"x": "0"}}), encoding="utf-8")
            def prohibido(**k):                                   # una prueba NUNCA toca el Wallpaper Engine real
                raise AssertionError("comparar siguió adelante con puertas de otro código")
            orig, orig_f = V.comprobar_v4, V.FondoAnimado
            V.comprobar_v4, V.FondoAnimado = (lambda: []), prohibido
            try:
                with self.assertRaises(EV.Abortada) as e:
                    V.comparar(Path(d), Path(d) / "vram_exp_v4_x", pu)
            finally:
                V.comprobar_v4, V.FondoAnimado = orig, orig_f
            self.assertIn("cambiaron desde las puertas", str(e.exception))

    def test_g10_equivalencia_estatica(self):
        with tempfile.TemporaryDirectory() as d:
            orig = V._unittest
            V._unittest = lambda patron, carpeta: {"rc": 0, "resultado": ["OK"]}
            orig_c = V.comparar
            try:
                r = V.g10_equivalencia(Path(d) / "a")
                V.comparar = lambda *a: X.ejecutar_bucle(fabrica=EV.fabrica_real)   # una comparación SIN E2
                malo = V.g10_equivalencia(Path(d) / "b")
            finally:
                V._unittest, V.comparar = orig, orig_c
            self.assertTrue(r["ok"], r)
            self.assertTrue(r["estatico"]["comparar_usa_e2_para_todas"])
            self.assertFalse(malo["ok"])


class TestPrerregistroV4(unittest.TestCase):
    def test_detecta_cambios(self):
        with tempfile.TemporaryDirectory() as d:
            pre = Path(d) / "p.json"
            pre.write_text(json.dumps({"variante": V.VARIANTE, "llama_e2": V.E2,
                                       "limites": {"vram_tope_MiB": 6912, "vram_otras_max_MiB": 1992},
                                       "sha256": {"eq3/evaluar_f1_vram_exp_v4.py": "0" * 64}}), encoding="utf-8")
            orig = V.PRERREGISTRO_V4
            V.PRERREGISTRO_V4 = pre
            try:
                self.assertIn("eq3/evaluar_f1_vram_exp_v4.py", V.comprobar_v4())
                pre.write_text(json.dumps({"variante": V.VARIANTE, "llama_e2": V.E2[:-2], "sha256": {},
                                           "limites": {"vram_tope_MiB": 6912, "vram_otras_max_MiB": 1992}}),
                               encoding="utf-8")
                self.assertIn("variante, límites o E2 del prerregistro V4", V.comprobar_v4())
            finally:
                V.PRERREGISTRO_V4 = orig


if __name__ == "__main__":
    unittest.main()
