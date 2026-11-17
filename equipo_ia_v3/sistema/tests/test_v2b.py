"""V2-B: deliberación completa contra el FALSO llama-server (procesos, sockets y señales reales;
el «modelo» es simulado, NO es Qwen)."""
import json
import os
import signal
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import _comun
from _v2 import EntornoV2
from eq2 import config
from eq2 import desbordes, orquestador, servidor
from eq2.monitor import muestra_proceso

T1 = config.TAREA_V2B
T2 = "Escribe una función que invierta una cadena."
ORDEN = [("analisis", "A2"), ("propuesta", "A1"), ("revision", "A3"), ("replica", "A1"),
         ("voto", "A2"), ("voto", "A3"), ("voto", "A1")]


class Base(EntornoV2):
    carpeta_datos = "datos_v2b"

    def reqs(self, res):
        out = []
        for l in self.log(res).splitlines():
            if l.startswith("REQ "):
                out.append(json.loads(l[4:]))
        return out

    def fases(self, res):
        claves = (("Vota sobre", "voto"), ("Analiza la tarea", "analisis"), ("Propón una solución", "propuesta"),
                  ("Revisa la propuesta", "revision"), ("Responde a la revisión", "replica"))
        sal = []
        for r in self.reqs(res):
            u = r["messages"][-1]["content"]
            sal.append(next((f for c, f in claves if c in u), "?"))
        return sal

    def limpio(self, be, res):
        self.assertIsNotNone(be.srv.proc.poll())
        self.assertTrue(servidor.puerto_libre(be.srv.puerto))
        self.assertFalse((self.raiz / self.carpeta_datos / "lock").exists())

    def ejecutar(self, be, tareas=(T1,), **kw):
        return self.orq_b(be, **kw).run_deliberacion(list(tareas))


class TestDeliberacionCompleta(Base):
    def test_siete_llamadas_secuenciales_con_un_solo_servidor(self):
        be = self.backend()
        res = self.ejecutar(be)
        self.assertEqual(res["resultado_global"], "completo", res["errores_cierre"])
        self.assertEqual(res["estado"], "completa")
        self.assertEqual(res["llamadas_total"], 7)
        self.assertEqual(self.fases(res), [f for f, _ in ORDEN])
        log = self.log(res)
        self.assertEqual(log.count("ARGV "), 1)                       # un único servidor
        activas = [int(l.split()[1]) for l in log.splitlines() if l.startswith("ACTIVAS ")]
        self.assertEqual(activas, [1] * 7)                            # nunca dos peticiones a la vez
        self.assertEqual(self.sql("SELECT fase, agente, estado FROM turnos ORDER BY orden"),
                         [(f, a, "ok") for f, a in ORDEN])
        t = res["tareas"][0]
        self.assertEqual(t["estado"], "completa")
        self.assertEqual(t["resultado"], "aprobada")
        self.assertEqual(self.sql("SELECT count(*) FROM votos"), [(3,)])
        self.assertIn("texto_final_no_confiable", t)
        self.assertTrue((self.raiz / "datos_v2b" / "runs" / res["run_id"] / "propuestas"
                         / f"tarea_{t['tarea_id']}.txt").exists())
        self.assertTrue((self.raiz / "datos_v2b" / "runs" / res["run_id"] / "informe_deliberacion.json").exists())
        self.limpio(be, res)
        self.assertEqual(res["backend_informe"]["pasos"]["servidor"], "SIGTERM_ok")
        self.assertFalse(res["desbordes"]["hay_desbordamiento"])
        self.assertEqual(res["desbordes"]["hallazgos"], [])

    def test_bases_sqlite_aisladas_por_agente(self):
        res = self.ejecutar(self.backend())
        self.assertEqual(res["resultado_global"], "completo")
        dbs = sorted(p.name for p in (self.raiz / "datos_v2b" / "datos").glob("*.db"))
        self.assertEqual(dbs, ["a1.db", "a2.db", "a3.db", "sesion.db"])
        for ag in ("a1", "a2", "a3"):
            self.assertEqual(self.sql("SELECT count(*), min(verificacion) FROM memoria", db=ag),
                             [(1, "sin_verificar")])
            self.assertEqual(self.sql("SELECT count(*) FROM decisiones", db=ag), [(1,)])
        # cada base contiene solo el voto de su propio agente
        for ag in ("a1", "a2", "a3"):
            self.assertEqual(self.sql("SELECT count(*) FROM memoria WHERE texto LIKE ?",
                                      (f"%mi voto aprobar%",), db=ag), [(1,)])
        # la carpeta de V2-A no se crea
        self.assertFalse((self.raiz / "datos_v2").exists())

    def test_segunda_ejecucion_reutiliza_memoria_y_sigue_aislada(self):
        self.ejecutar(self.backend())
        res = self.ejecutar(self.backend())
        self.assertEqual(res["resultado_global"], "completo", res["errores_cierre"])
        self.assertIn("memorias_hipotesis", self.log(res))
        for ag in ("a1", "a2", "a3"):
            self.assertEqual(self.sql("SELECT count(*) FROM memoria", db=ag), [(2,)])

    def test_dos_tareas(self):
        be = self.backend()
        res = self.ejecutar(be, (T1, T2))
        self.assertEqual(res["resultado_global"], "completo")
        self.assertEqual(res["llamadas_total"], 14)
        self.assertEqual([t["estado"] for t in res["tareas"]], ["completa", "completa"])
        self.assertEqual(res["tareas_no_iniciadas"], 0)

    def test_voto_invalido_reintenta_una_vez(self):
        res = self.ejecutar(self.backend("voto_invalido_1"))
        self.assertEqual(res["llamadas_total"], 8)
        self.assertEqual(res["resultado_global"], "completo")
        self.assertEqual(res["tareas"][0]["estado"], "completa")
        self.assertEqual(self.sql("SELECT estado FROM turnos WHERE fase='voto' ORDER BY orden")[0], ("invalido",))

    def test_votos_siempre_invalidos_se_abstienen_y_no_superan_el_limite(self):
        res = self.ejecutar(self.backend("votos_mal"))
        self.assertEqual(res["llamadas_total"], 10)                   # 7 + 3 reintentos = MAX_LLAMADAS_TAREA
        t = res["tareas"][0]
        self.assertEqual(t["estado"], "completa")
        self.assertEqual(t["resultado"], "sin_consenso")
        self.assertEqual(self.sql("SELECT postura FROM votos ORDER BY agente"),
                         [("abstencion",)] * 3)
        self.assertEqual(res["resultado_global"], "completo")         # decisión del equipo ≠ fallo de sistema

    def test_lo_que_devuelve_el_modelo_no_se_ejecuta(self):
        marca = self.t / "marca_pwned"
        with mock.patch.dict(os.environ, {"FAKE_MARCA": str(marca)}):
            res = self.ejecutar(self.backend("peligro"))
        self.assertFalse(marca.exists())
        self.assertGreaterEqual(res["llamadas_total"], 1)
        self.assertFalse(list(self.t.rglob("marca_pwned")))

    def test_solo_loopback_y_flags(self):
        res = self.ejecutar(self.backend())
        argv = json.loads([l for l in self.log(res).splitlines() if l.startswith("ARGV ")][0][5:])
        self.assertEqual(argv[argv.index("--host") + 1], "127.0.0.1")
        self.assertEqual(argv[argv.index("-c") + 1], "1024")
        self.assertEqual(argv[argv.index("-np") + 1], "1")
        for malo in ("--no-mmap", "--mlock", "--cache-ram"):
            self.assertNotIn(malo, argv)
        for r in self.reqs(res):
            self.assertEqual((r["temperature"], r["seed"], r["cache_prompt"]), (0, 1, True))
            self.assertLessEqual(r["max_tokens"], max(config.MAX_TOKENS.values()))

    def test_el_modelo_y_el_proyecto_no_se_tocan(self):
        antes = (self.modelo.read_bytes(), os.stat(self.modelo).st_mtime_ns)
        eventos, activo = [], {"on": True}
        proyecto, modelo = str(self.proyecto.resolve()), str(self.modelo.resolve())

        def hook(ev, args):
            if not activo["on"]:
                return
            if ev == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
                ruta = os.fsdecode(args[0])
                if ruta.startswith(proyecto) or ".env" in os.path.basename(ruta):
                    eventos.append((ev, ruta, args[1], args[2]))
            elif ev in ("os.listdir", "os.scandir", "os.mkdir", "os.remove", "os.rename", "os.rmdir",
                        "os.chmod", "shutil.rmtree"):
                a = args[0]
                if isinstance(a, (str, bytes, os.PathLike)) and os.fsdecode(a).startswith(proyecto):
                    eventos.append((ev, os.fsdecode(a)))
        sys.addaudithook(hook)
        try:
            res = self.ejecutar(self.backend())
        finally:
            activo["on"] = False
        self.assertEqual(res["resultado_global"], "completo")
        self.assertTrue(eventos)
        for e in eventos:
            self.assertEqual(e[0], "open", e)
            self.assertEqual(os.path.realpath(e[1]), modelo, e)
            self.assertEqual((e[3] or 0) & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC), 0, e)
        self.assertEqual((self.modelo.read_bytes(), os.stat(self.modelo).st_mtime_ns), antes)
        self.assertEqual((self.proyecto / ".env").read_text(), "SECRETO=1")
        self.assertEqual(sorted(p.name for p in self.proyecto.iterdir()),
                         [".env", "coordinador.py", "modelos"])

    def test_carpeta_fuera_del_laboratorio_rechazada(self):
        for destino in (self.proyecto / "x", self.t / "otra"):
            with self.assertRaises(ValueError):
                orquestador.Orquestador(destino, self.backend(), self.vigilante(),
                                        raiz_laboratorio=self.raiz)


class TestDesbordes(Base):
    def test_contexto_real_excedido_se_reporta_y_no_se_oculta(self):
        res = self.ejecutar(self.backend("contexto"))
        d = res["desbordes"]
        self.assertTrue(d["hay_desbordamiento"])
        tipos = {h["tipo"] for h in d["hallazgos"]}
        self.assertIn("desborde_efectivo", tipos)
        self.assertIn("riesgo_desborde", tipos)
        self.assertIn("subestimacion_tokens", tipos)
        en_disco = json.loads((self.raiz / "datos_v2b" / "runs" / res["run_id"] / "informe_deliberacion.json").read_text())
        self.assertTrue(en_disco["desbordes"]["hay_desbordamiento"])

    def test_analizar_sin_hallazgos(self):
        r = {"backend_informe": {"informe": {"peticiones": [
            {"n": 1, "tokens_prompt_real": 142, "tokens_generados": 107, "max_tokens": 160,
             "finish_reason": "stop"}]}}, "calibracion_tokens": [{"tokens_est": 173}]}
        d = desbordes.analizar(r)
        self.assertEqual(d["hallazgos"], [])
        self.assertFalse(d["hay_desbordamiento"])
        self.assertEqual(d["llamadas"][0]["tokens_est"], 173)

    def test_analizar_casos(self):
        pet = [
            {"n": 1, "tokens_prompt_real": 900, "tokens_generados": 160, "max_tokens": 160, "finish_reason": "length"},
            {"n": 2, "tokens_prompt_real": 870, "tokens_generados": 10, "max_tokens": 160, "finish_reason": "stop"},
            {"n": 3, "finish_reason": "stop", "max_tokens": 80},                      # sin medida real
            {"n": 4, "fallo": "http_400", "cuerpo_inicio": "request exceeds the available context size"},
            {"n": 5, "tokens_prompt_real": True, "tokens_generados": 5, "max_tokens": 5},   # bool no es entero
        ]
        calib = [{"tokens_est": 800}, {"tokens_est": 900}]
        d = desbordes.analizar({"backend_informe": {"informe": {"peticiones": pet}},
                                "calibracion_tokens": calib})
        por = {}
        for h in d["hallazgos"]:
            por.setdefault(h["n"], set()).add(h["tipo"])
        self.assertEqual(por[1], {"desborde_efectivo", "riesgo_desborde", "corte_por_max_tokens", "subestimacion_tokens"})
        self.assertEqual(por[2], {"riesgo_desborde"})
        self.assertEqual(por[3], {"medida_ausente"})
        self.assertEqual(por[4], {"indicio_en_log"})
        self.assertEqual(por[5], {"medida_ausente"})                   # un bool no cuenta como medida
        self.assertTrue(d["hay_desbordamiento"])

    def test_analizar_entradas_vacias_o_raras(self):
        for r in ({}, {"backend_informe": None}, {"backend_informe": {"informe": None}},
                  {"backend_informe": {"informe": {"peticiones": [{}]}}}):
            d = desbordes.analizar(r)
            self.assertFalse(d["hay_desbordamiento"])


class TestFallosDeInfraestructura(Base):
    def test_http500_a_mitad_detiene_la_sesion_y_no_inicia_mas_tareas(self):
        be = self.backend("http500", en=4)
        res = self.ejecutar(be, (T1, T2))
        self.assertEqual(res["estado"], "abortada")
        self.assertEqual(res["motivo_fin"], "infraestructura_inferencia_fallida")
        self.assertEqual(res["tareas_no_iniciadas"], 1)
        self.assertEqual(len(res["tareas"]), 1)
        self.assertEqual(res["tareas"][0]["estado"], "abortada")
        self.assertEqual(len(self.reqs(res)), 4)                       # no hubo más peticiones
        self.assertEqual(res["resultado_global"], "incompleto")
        self.assertEqual(self.sql("SELECT count(*) FROM tareas"), [(1,)])
        self.limpio(be, res)

    def test_run_del_orquestador_tambien_se_detiene(self):
        """CAMBIO V2-C (antes: test_el_orquestador_base_si_continuaria...). La parada por
        infraestructura ya no vive en una subclase: Orquestador.run la aplica directamente."""
        be = self.backend("http500", en=4)
        res = orquestador.Orquestador(
            self.raiz / "datos_v2b", be, self.vigilante(), raiz_laboratorio=self.raiz).run([T1, T2])
        self.assertEqual(len(self.reqs(res)), 4)
        self.assertEqual([t["estado"] for t in res["tareas"]], ["abortada"])
        self.assertEqual(res["motivo_fin"], "infraestructura_inferencia_fallida")

    def test_json_invalido_tambien_detiene(self):
        res = self.ejecutar(self.backend("json_invalido", en=2), (T1, T2))
        self.assertEqual(res["motivo_fin"], "infraestructura_inferencia_fallida")
        self.assertEqual(res["tareas_no_iniciadas"], 1)

    def test_servidor_muere_en_la_peticion_3(self):
        be = self.backend("muere_en_peticion", en=3, pausa=0.1)
        res = self.ejecutar(be, (T1, T2))
        self.assertEqual(res["estado"], "abortada")
        self.assertEqual(res["motivo_fin"], "backend_servidor_muerto")
        self.assertEqual(res["tareas_no_iniciadas"], 1)
        self.limpio(be, res)
        self.assertEqual(res["resultado_global"], "incompleto")

    def test_timeout_en_la_peticion_2(self):
        with mock.patch.object(config, "SEG_POR_LLAMADA", 1.5):
            be = self.backend("cuelga", en=2)
            t = time.monotonic()
            res = self.ejecutar(be, (T1, T2))
            self.assertLess(time.monotonic() - t, 15)
        self.assertEqual(res["motivo_fin"], "backend_plazo_agotado")
        self.assertEqual(res["tareas_no_iniciadas"], 1)
        self.assertEqual(res["backend_informe"]["pasos"]["servidor"], "SIGTERM_ok")
        self.limpio(be, res)

    def test_tiempo_de_tarea_agotado_detiene_la_sesion(self):
        with mock.patch.object(config, "SEG_POR_TAREA", 0.5):
            be = self.backend(pausa=0.4)
            res = self.ejecutar(be, (T1, T2))
        self.assertEqual(res["motivo_fin"], "infraestructura_tiempo_tarea")
        self.assertEqual(res["tareas_no_iniciadas"], 1)
        self.limpio(be, res)

    def test_tiempo_de_sesion_agotado(self):
        with mock.patch.object(config, "SEG_POR_SESION", 0.6):
            be = self.backend(pausa=0.4)
            res = self.ejecutar(be, (T1, T2))
        self.assertEqual(res["motivo_fin"], "tiempo_sesion")
        self.assertEqual(res["estado"], "abortada")
        self.limpio(be, res)

    def test_memoria_baja_a_mitad_de_la_deliberacion(self):
        estado = {"bajo": False}

        def lector(pid=None):
            m = muestra_proceso(pid)
            m["MemAvailable"] = 1000 if estado["bajo"] else 2_000_000
            return m
        from _v2 import MARCA_PETICION, al_ver_en_log      # CAMBIO V2-F.1 (V2-F: threading.Timer(1.2, …))
        hecho = al_ver_en_log(self.raiz / "datos_v2b", MARCA_PETICION, lambda: estado.update(bajo=True))
        be = self.backend(pausa=0.5, lector_muestra=lector)
        res = self.ejecutar(be)
        self.assertTrue(hecho.is_set(), "la memoria baja no llegó a producirse durante una petición")  # CAMBIO V2-F.1
        self.assertEqual(res["estado"], "abortada")
        self.assertTrue(res["motivo_fin"].startswith("backend_presion_memoria"), res["motivo_fin"])
        self.assertLess(res["llamadas_total"], 7)
        self.limpio(be, res)

    def test_sigkill_necesario_marca_incompleto_y_detiene_la_sesion(self):
        be = self.backend("ignora_sigterm", srv_kw={"gracia_term": 0.5})
        res = self.ejecutar(be)
        self.assertEqual(res["estado"], "completa")                    # la deliberación sí terminó
        self.assertEqual(res["backend_informe"]["pasos"]["servidor"], "SIGKILL_usado")
        self.assertEqual(res["resultado_global"], "incompleto")
        self.limpio(be, res)

    def test_arranque_fallido_no_hace_peticiones(self):
        be = self.backend("muere_al_arrancar")
        res = self.ejecutar(be)
        self.assertEqual(res["llamadas_total"], 0)
        self.assertTrue(res["motivo_fin"].startswith("backend_no_inicia"))
        self.assertEqual(res["resultado_global"], "incompleto")
        self.assertEqual(res["desbordes"]["hallazgos"], [])

    def test_modelo_ausente_no_lanza_nada(self):
        self.modelo.unlink()
        be = self.backend()
        res = self.ejecutar(be)
        self.assertIsNone(be.srv.proc)
        self.assertEqual(res["llamadas_total"], 0)


class TestCancelaciones(Base):
    def test_stop_durante_la_deliberacion_deja_deliberacion_incompleta(self):
        be = self.backend(pausa=0.5)
        from _v2 import MARCA_PETICION, al_ver_en_log      # CAMBIO V2-F.1 (V2-F: threading.Timer(1.2, …))
        hecho = al_ver_en_log(self.raiz / "datos_v2b", MARCA_PETICION,
                              lambda: (self.raiz / "datos_v2b" / "STOP").write_text(""))
        res = self.ejecutar(be, (T1, T2))
        self.assertTrue(hecho.is_set(), "el STOP no llegó a producirse durante una petición")  # CAMBIO V2-F.1
        self.assertEqual((res["estado"], res["motivo_fin"]), ("interrumpida", "stop_usuario"))
        self.assertGreaterEqual(res["llamadas_total"], 1)
        self.assertLess(res["llamadas_total"], 7)
        self.assertEqual(res["resultado_global"], "incompleto")
        self.assertEqual(self.sql("SELECT estado FROM tareas"), [("abortada",)])
        self.assertEqual(self.sql("SELECT estado FROM sesiones"), [("interrumpida",)])
        self.assertEqual(self.sql("SELECT count(*) FROM votos"), [(0,)])
        for ag in ("a1", "a2", "a3"):                                   # no se guarda memoria de una tarea inconclusa
            self.assertEqual(self.sql("SELECT count(*) FROM memoria", db=ag), [(0,)])
        self.limpio(be, res)

    def test_solicitar_parada(self):
        be = self.backend(pausa=0.5)
        orq = self.orq_b(be)
        threading.Timer(1.2, orq.solicitar_parada).start()
        res = orq.run_deliberacion([T1])
        self.assertEqual((res["estado"], res["motivo_fin"]), ("interrumpida", "senal"))
        self.limpio(be, res)

    def test_sigint_real(self):
        be = self.backend(pausa=0.5)
        orq = self.orq_b(be, instalar_senales=True)
        previo = signal.getsignal(signal.SIGINT)
        threading.Timer(1.2, lambda: os.kill(os.getpid(), signal.SIGINT)).start()
        res = orq.run_deliberacion([T1])
        self.assertEqual((res["estado"], res["motivo_fin"]), ("interrumpida", "senal"))
        self.limpio(be, res)
        self.assertIs(signal.getsignal(signal.SIGINT), previo)

    def test_sigterm_real(self):
        be = self.backend(pausa=0.5)
        orq = self.orq_b(be, instalar_senales=True)
        threading.Timer(1.2, lambda: os.kill(os.getpid(), signal.SIGTERM)).start()
        res = orq.run_deliberacion([T1])
        self.assertEqual(res["motivo_fin"], "senal")
        self.limpio(be, res)

    def test_stop_antes_de_empezar(self):
        (self.raiz / "datos_v2b").mkdir(parents=True)
        (self.raiz / "datos_v2b" / "STOP").write_text("")
        be = self.backend()
        res = self.ejecutar(be)
        self.assertEqual(res["estado"], "interrumpida")
        self.assertEqual(res["llamadas_total"], 0)
        self.assertIsNone(be.srv.proc)

    def test_excepcion_inesperada_en_el_trabajo_limpia_el_servidor(self):
        be = self.backend()
        orq = self.orq_b(be)
        with mock.patch.object(type(orq), "_tarea", side_effect=RuntimeError("boom")):
            res = orq.run_deliberacion([T1])
        self.assertTrue(res["motivo_fin"].startswith("error_interno"))
        self.assertEqual(res["resultado_global"], "incompleto")
        self.limpio(be, res)

    def test_sesion_activa_no_arranca_otra(self):
        be = self.backend(pausa=0.5)
        o1 = self.orq_b(be)
        hilo_res = {}
        th = threading.Thread(target=lambda: hilo_res.update(r=o1.run_deliberacion([T1])))
        th.start()
        time.sleep(0.8)
        be2 = self.backend()
        with self.assertRaises(orquestador.SesionActiva):
            self.orq_b(be2).run_deliberacion([T1])
        self.assertIsNone(be2.srv.proc)
        o1.solicitar_parada()
        th.join(30)
        self.assertEqual(hilo_res["r"]["motivo_fin"], "senal")


class TestEjecutable(unittest.TestCase):
    RUN = str(_comun.RAIZ / "ejecutar_v2.py")

    def setUp(self):
        self.tmp = _comun.carpeta_temporal()
        self.t = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        (self.t / "home").mkdir()
        (self.t / "tmp").mkdir()
        self.env = dict(os.environ, HOME=str(self.t / "home"), TMPDIR=str(self.t / "tmp"))

    def ejecutar(self, *a):
        return subprocess.run([sys.executable, "-B", "-I", self.RUN, *a], capture_output=True,
                              text=True, timeout=60, env=self.env)

    def test_exige_confirmacion_explicita(self):
        r = self.ejecutar("--modo", "deliberacion")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--iniciar-servidor-real", r.stdout + r.stderr)
        self.assertEqual(list((self.t / "tmp").iterdir()), [])

    def test_la_carpeta_es_siempre_datos_v2c(self):
        """CAMBIO V2-C (antes: ..._datos_v2b): las carpetas anteriores se rechazan sin tocarlas."""
        for c in ("datos_v2", "datos_v2b", "datos_v2b/", "./datos_v2b", "otra", "../x"):
            r = self.ejecutar("--modo", "deliberacion", "--iniciar-servidor-real", "--carpeta", c)
            self.assertNotEqual(r.returncode, 0, c)
        self.assertEqual(list((self.t / "tmp").iterdir()), [])

    def test_tarea_delib_solo_en_deliberacion(self):
        r = self.ejecutar("--modo", "comprobar", "--tarea-delib", "x")
        self.assertNotEqual(r.returncode, 0)

    def test_sin_modelo_no_lanza_nada_y_sale_con_error(self):
        r = self.ejecutar("--modo", "deliberacion", "--iniciar-servidor-real", "--sin-wake-lock")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("backend_no_inicia", r.stdout)
        self.assertIn("lab_v2f1", r.stdout)  # CAMBIO V2-E.6 (V2-E.5-r3: datos_v2e5r3)  # CAMBIO V2-E.6-r2 (V2-E.6: lab_v2e6)  # CAMBIO V2-E.6-r3 (V2-E.6-r2: lab_v2e6r2)  # CAMBIO V2-E.7 (V2-E.6-r3: lab_v2e6r3)  # CAMBIO V2-E.7-r2 (V2-E.7: lab_v2e7)  # CAMBIO V2-E.7-r3 (V2-E.7-r2: lab_v2e7r2)  # CAMBIO V2-F (V2-E.7-r3: lab_v2e7r3)  # CAMBIO V2-F.1 (V2-F: lab_v2f)
        self.assertIn("CONCLUSIÓN VÁLIDA: NO", r.stdout)
        self.assertEqual(list((self.t / "home").iterdir()), [])
        self.assertFalse((self.t / "tmp" / "equipo_f2" / "datos_v2").exists())
        self.assertFalse((self.t / "tmp" / "equipo_f2" / "datos_v2b").exists())

    def test_modos_anteriores_siguen_exigiendo_su_confirmacion(self):
        r = self.ejecutar("--modo", "una_llamada")
        self.assertNotEqual(r.returncode, 0)
        r = self.ejecutar("--modo", "comprobar", "--sin-help")
        self.assertEqual(r.returncode, 1)
        self.assertIn("NO APTO", r.stdout)
        self.assertEqual(list((self.t / "tmp").iterdir()), [])

    def test_la_tarea_por_defecto_es_la_aprobada(self):
        self.assertIn("ordene una lista de enteros sin modificar la lista original", config.TAREA_V2B)
        self.assertLessEqual(len(config.TAREA_V2B), config.MAX_TAREA_CHARS)


if __name__ == "__main__":
    unittest.main()
