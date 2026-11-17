"""BackendLlama + Orquestador contra el FALSO llama-server: procesos hijos, sockets, señales
y archivos REALES del entorno donde se ejecuten; el «modelo» es simulado (NO es Qwen)."""
import json
import os
import signal
import sqlite3
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import _comun
from _v2 import MARCA_CARGA, MARCA_PETICION, EntornoV2, al_ver_en_log  # CAMBIO V2-F.1 (V2-F: EntornoV2)
from eq2 import config, inferencia, orquestador, servidor
from eq2.backend_llama import BackendLlama
from eq2.monitor import muestra_proceso

TAREA = "Escribe una función en Python que sume dos números enteros."


def muestra_ok(pid=None):
    m = muestra_proceso(pid)
    m.setdefault("MemAvailable", 2_000_000)
    return m


class TestLlamadaUnica(EntornoV2):
    def test_exito_una_sola_llamada(self):
        be = self.backend()
        orq = self.orq(be)
        res = orq.run_una_llamada(TAREA)
        self.assertEqual(res["modo"], "una_llamada")
        self.assertEqual(res["estado"], "completa", res)
        self.assertEqual(res["resultado_global"], "completo", res["errores_cierre"])
        self.assertEqual(res["llamadas_total"], 1)
        t = res["tareas"][0]
        self.assertEqual((t["resultado"], t["agente"], t["fase"]), ("analisis_unico", "A2", "analisis"))
        self.assertIn("Respuesta simulada", t["respuesta_texto_no_confiable"])
        # el servidor recibió EXACTAMENTE una petición, con los parámetros acordados
        log = self.log(res)
        reqs = [l for l in log.splitlines() if l.startswith("REQ ")]
        self.assertEqual(len(reqs), 1)
        cuerpo = json.loads(reqs[0][4:])
        self.assertEqual((cuerpo["temperature"], cuerpo["seed"], cuerpo["cache_prompt"]), (0, 1, True))
        self.assertEqual(cuerpo["max_tokens"], config.MAX_TOKENS["analisis"])
        self.assertEqual([m["role"] for m in cuerpo["messages"]], ["system", "user"])
        self.assertIn("Eres A2", cuerpo["messages"][0]["content"])
        self.assertNotIn("stream", cuerpo)
        # BD: un turno, una tarea, memoria SOLO de A2, todo sin verificar
        self.assertEqual(self.sql("SELECT fase,agente,estado,tokens_prompt,tokens_gen,cache_n,"
                                  "ms_prompt,ms_gen,finish_reason FROM turnos"),
                         [("analisis", "A2", "ok", 88, 12, 0, 1000.0, 1200.0, "stop")])
        self.assertEqual(self.sql("SELECT estado FROM tareas"), [("analisis_unico",)])
        self.assertEqual(self.sql("SELECT estado FROM sesiones"), [("completa",)])
        self.assertEqual(self.sql("SELECT count(*), min(verificacion) FROM memoria", db="a2"),
                         [(1, "sin_verificar")])
        self.assertEqual(self.sql("SELECT count(*) FROM memoria", db="a1"), [(0,)])
        self.assertEqual(self.sql("SELECT count(*) FROM memoria", db="a3"), [(0,)])
        # limpieza
        self.assertIsNotNone(be.srv.proc.poll())
        self.assertTrue(servidor.puerto_libre(be.srv.puerto))
        self.assertFalse((self.raiz / "datos_v2" / "lock").exists())
        bi = res["backend_informe"]
        self.assertTrue(bi["limpio"], bi["problemas"])
        self.assertEqual(bi["pasos"]["servidor"], "SIGTERM_ok")
        self.assertIs(bi["pasos"]["puerto_liberado"], True)
        self.assertIs(bi["pasos"]["modelo_sin_cambios"], True)
        self.assertIs(bi["informe"]["puerto_libre_antes"], True)
        self.assertEqual(bi["informe"]["peticiones"][0]["diagnostico"], "ok_stop")
        self.assertTrue(bi["informe"]["peticiones"][0]["concluyente"])
        # calibración de tokens: estimación vs. valor «real» del servidor (falso)
        self.assertEqual(len(res["calibracion_tokens"]), 1)
        self.assertEqual(res["calibracion_tokens"][0]["tokens_real"], 88)
        en_disco = json.loads((self.raiz / "datos_v2" / "runs" / res["run_id"] / "summary.json").read_text())
        self.assertEqual(en_disco["run_id"], res["run_id"])
        self.assertIn("limitaciones", en_disco)

    def test_la_memoria_de_a2_vuelve_en_la_segunda_ejecucion(self):
        r1 = self.orq(self.backend()).run_una_llamada(TAREA)
        self.assertEqual(r1["resultado_global"], "completo")
        r2 = self.orq(self.backend()).run_una_llamada(TAREA)
        self.assertEqual(r2["resultado_global"], "completo", r2["errores_cierre"])
        log2 = self.log(r2)
        self.assertIn("memorias_hipotesis", log2)
        self.assertIn("sin verificar", log2)
        self.assertEqual(self.sql("SELECT count(*) FROM memoria", db="a2"), [(2,)])
        self.assertEqual(self.sql("SELECT count(*) FROM sesiones"), [(2,)])

    def test_no_ejecuta_lo_que_devuelve_el_modelo(self):
        marca = self.t / "marca_pwned"
        with mock.patch.dict(os.environ, {"FAKE_MARCA": str(marca)}):
            res = self.orq(self.backend("peligro")).run_una_llamada(TAREA)
        self.assertFalse(marca.exists())
        self.assertEqual(res["resultado_global"], "completo")
        self.assertIn("touch", res["tareas"][0]["respuesta_texto_no_confiable"])
        ficheros = sorted(p.name for p in (self.raiz / "datos_v2" / "runs" / res["run_id"] / "propuestas").iterdir())
        self.assertEqual(ficheros, ["tarea_1.txt"])

    def test_solo_loopback_y_flags(self):
        res = self.orq(self.backend()).run_una_llamada(TAREA)
        argv = json.loads([l for l in self.log(res).splitlines() if l.startswith("ARGV ")][0][5:])
        self.assertEqual(argv[argv.index("--host") + 1], "127.0.0.1")
        for malo in ("--no-mmap", "--mlock", "--cache-ram"):
            self.assertNotIn(malo, argv)

    def test_validaciones_de_la_llamada_unica(self):
        o = self.orq(self.backend())
        for fase, ag in (("voto", "A2"), ("ejecutar", "A2"), ("analisis", "A9")):
            with self.assertRaises(ValueError):
                o.run_una_llamada(TAREA, fase, ag)
        with self.assertRaises(ValueError):
            o.run_una_llamada("")


class TestNoConcluyente(EntornoV2):
    def test_diagnosticos_no_concluyentes(self):
        for modo, motivo in (("especiales", "terminacion_no_normal"),
                             ("length", None), ("sin_metricas", "metricas_servidor_ausentes")):
            with self.subTest(modo):
                self.setUp_run = None
                res = self.orq(self.backend(modo)).run_una_llamada(TAREA)
                p = res["backend_informe"]["informe"]["peticiones"][0]
                if modo == "length":
                    self.assertEqual(p["diagnostico"], "length_por_limite")
                    self.assertFalse(p["tokens_especiales_en_texto"])
                else:
                    self.assertFalse(p["concluyente"])
                    self.assertIn(motivo, p["motivos_no_concluyente"])
                    self.assertEqual(res["resultado_global"], "completo_no_concluyente")
                    self.assertEqual(res["peticiones_no_concluyentes"], [1])
                self.assertEqual(res["estado"], "completa")

    def test_medicion_critica_ausente_es_no_concluyente(self):
        be = self.backend(lector_muestra=lambda pid: {"MemAvailable": 2_000_000})   # sin VmRSS ni majflt
        res = self.orq(be).run_una_llamada(TAREA)
        p = res["backend_informe"]["informe"]["peticiones"][0]
        self.assertFalse(p["concluyente"])
        self.assertEqual(sorted(p["criticas_ausentes"]), ["VmRSS", "majflt"])
        self.assertEqual(res["resultado_global"], "completo_no_concluyente")


class TestErroresHTTP(EntornoV2):
    def comprobar(self, modo, motivo_tarea, esperado_fatal=False, **kw):
        previos = len(self.sql("SELECT estado FROM turnos")) if (self.raiz / "datos_v2" / "datos" / "sesion.db").exists() else 0
        be = self.backend(modo, **kw)
        res = self.orq(be).run_una_llamada(TAREA)
        self.assertEqual(res["resultado_global"], "incompleto", modo)
        self.assertEqual(self.sql("SELECT estado FROM turnos")[previos:], [("fallido",)])
        self.assertEqual(self.sql("SELECT count(*) FROM memoria", db="a2"), [(0,)])
        self.assertIsNotNone(be.srv.proc.poll())                       # el servidor se detuvo siempre
        self.assertTrue(servidor.puerto_libre(be.srv.puerto))
        self.assertFalse((self.raiz / "datos_v2" / "lock").exists())
        if esperado_fatal:
            self.assertEqual(res["estado"], "abortada")
            self.assertEqual(res["motivo_fin"], motivo_tarea)
        else:
            self.assertEqual(res["tareas"][0]["motivo"], motivo_tarea)
        return res

    def test_http_500(self):
        self.comprobar("http500", "inferencia_fallida")

    def test_json_invalido_sin_choices_y_content_no_texto(self):
        for modo in ("json_invalido", "sin_choices", "content_no_texto"):
            with self.subTest(modo):
                self.comprobar(modo, "inferencia_fallida")

    def test_respuesta_enorme_se_corta_y_no_es_fatal(self):
        self.comprobar("enorme", "inferencia_fallida")

    def test_servidor_muere_durante_la_peticion(self):
        res = self.comprobar("muere_en_peticion", "backend_servidor_muerto", esperado_fatal=True, pausa=0.2)
        self.assertEqual(res["backend_informe"]["pasos"]["servidor"], "ya_terminado_rc_9")

    def test_cierra_sin_responder_es_fatal_si_muere(self):
        self.comprobar("cierra_sin_responder", "inferencia_fallida")

    def test_plazo_efectivo_con_servidor_colgado(self):
        with mock.patch.object(config, "SEG_POR_LLAMADA", 1.5):
            t = time.monotonic()
            res = self.comprobar("cuelga", "backend_plazo_agotado", esperado_fatal=True)
            self.assertLess(time.monotonic() - t, 12)
        self.assertEqual(res["backend_informe"]["pasos"]["servidor"], "SIGTERM_ok")
        self.assertEqual(res["backend_informe"]["informe"]["peticiones"][0]["fallo"], "plazo_agotado")

    def test_plazo_efectivo_con_servidor_que_gotea(self):
        with mock.patch.object(config, "SEG_POR_LLAMADA", 1.5):
            self.comprobar("gotea", "backend_plazo_agotado", esperado_fatal=True)

    def test_proceso_que_ignora_sigterm_tras_un_cuelgue(self):
        with mock.patch.object(config, "SEG_POR_LLAMADA", 1.0):
            be = self.backend("cuelga", srv_kw={"gracia_term": 0.5})
            be.srv.comando[-5:-4]          # sin efecto: documenta que el modo se fija al crear
            res = self.orq(be).run_una_llamada(TAREA)
        self.assertEqual(res["motivo_fin"], "backend_plazo_agotado")


class TestArranque(EntornoV2):
    def fallo_inicio(self, be, esperado):
        res = self.orq(be).run_una_llamada(TAREA)
        self.assertEqual(res["estado"], "abortada")
        self.assertTrue(res["motivo_fin"].startswith("backend_no_inicia:"), res["motivo_fin"])
        self.assertIn(esperado, res["motivo_fin"])
        self.assertEqual(res["llamadas_total"], 0)
        self.assertEqual(res["resultado_global"], "incompleto")
        self.assertFalse((self.raiz / "datos_v2" / "lock").exists())
        return res

    def test_muere_al_arrancar(self):
        be = self.backend("muere_al_arrancar")
        self.fallo_inicio(be, "servidor_muerto")
        self.assertEqual(self.sql("SELECT count(*) FROM turnos"), [(0,)])

    def test_nunca_listo(self):
        be = self.backend("nunca_listo", srv_kw={"max_carga_s": 1.0})
        res = self.fallo_inicio(be, "timeout_carga")
        self.assertEqual(res["backend_informe"]["pasos"]["servidor"], "SIGTERM_ok")

    def test_puerto_ocupado_no_lanza_nada(self):
        import socket
        l = socket.socket()
        l.bind(("127.0.0.1", 0))
        l.listen(1)
        self.addCleanup(l.close)
        be = self.backend(srv_kw={"puerto": l.getsockname()[1]})
        self.fallo_inicio(be, "puerto ocupado")
        self.assertIsNone(be.srv.proc)

    def test_modelo_ausente_no_lanza_nada(self):
        self.modelo.unlink()
        be = self.backend()
        self.fallo_inicio(be, "modelo")
        self.assertIsNone(be.srv.proc)

    def test_llama_previo_activo_no_lanza_ni_mata(self):
        be = self.backend(srv_kw={"detector_llama": lambda: "777"})
        self.fallo_inicio(be, "777")
        self.assertIsNone(be.srv.proc)

    def test_mem_available_ilegible_no_lanza(self):
        be = self.backend(srv_kw={"lector_mem": lambda: None})
        self.fallo_inicio(be, "MemAvailable")
        self.assertIsNone(be.srv.proc)

    def test_backend_no_reutilizable(self):
        be = self.backend()
        self.orq(be).run_una_llamada(TAREA)
        with self.assertRaises(inferencia.ErrorInferencia):
            be.iniciar({})
        with self.assertRaises(inferencia.ErrorInferencia):
            be.completar([{"role": "user", "content": "x"}], 10, 5)

    def test_completar_sin_iniciar(self):
        be = self.backend()
        with self.assertRaises(inferencia.ErrorInferencia) as e:
            be.completar([{"role": "user", "content": "x"}], 10, 5)
        self.assertTrue(e.exception.fatal)


class TestMonitorYParadas(EntornoV2):
    def test_memoria_baja_durante_la_peticion_aborta_y_detiene(self):
        estado = {"bajo": False}

        def lector(pid=None):
            m = muestra_ok(pid)
            if estado["bajo"]:
                m["MemAvailable"] = 1000
            return m
        # CAMBIO V2-F.1 (V2-F: threading.Timer(1.0, …)): se dispara al ver la petición en el servidor
        hecho = al_ver_en_log(self.raiz / "datos_v2", MARCA_PETICION, lambda: estado.update(bajo=True))
        be = self.backend(pausa=8.0, carga=0.1, lector_muestra=lector)
        t = time.monotonic()
        res = self.orq(be).run_una_llamada(TAREA)
        self.assertTrue(hecho.is_set(), "la memoria baja no llegó a producirse durante una petición activa")
        self.assertLess(time.monotonic() - t, 8)
        self.assertEqual(res["estado"], "abortada")
        self.assertTrue(res["motivo_fin"].startswith("backend_presion_memoria"), res["motivo_fin"])
        self.assertIsNotNone(be.srv.proc.poll())
        self.assertTrue(servidor.puerto_libre(be.srv.puerto))
        self.assertEqual(res["resultado_global"], "incompleto")

    def test_memoria_baja_durante_la_carga(self):
        be = self.backend("nunca_listo", lector_muestra=lambda pid=None: {"MemAvailable": 1000, "VmRSS": 1, "majflt": 0})
        res = self.orq(be).run_una_llamada(TAREA)
        self.assertIn("presion_memoria", res["motivo_fin"])
        self.assertEqual(res["backend_informe"]["pasos"]["servidor"], "SIGTERM_ok")

    def test_sin_medicion_de_memoria_aborta(self):
        be = self.backend("nunca_listo", lector_muestra=lambda pid=None: {})
        res = self.orq(be).run_una_llamada(TAREA)
        self.assertIn("sin_medicion_MemAvailable", res["motivo_fin"])

    def test_monitor_bloqueado_se_detecta_desde_el_hilo_principal(self):
        liberar = threading.Event()
        n = {"i": 0}

        def lector(pid=None):
            if threading.current_thread().name == "eq2-monitor":
                n["i"] += 1
                if n["i"] > 3:
                    liberar.wait(30)                       # la lectura de /proc «se cuelga»
            return muestra_ok(pid)
        self.addCleanup(liberar.set)
        be = self.backend(pausa=8.0, carga=0.1, lector_muestra=lector, margen_latido=0.4,
                          espera_monitor=0.3)
        t = time.monotonic()
        res = self.orq(be).run_una_llamada(TAREA)
        self.assertLess(time.monotonic() - t, 10)
        self.assertIn("monitor_sin_latido", res["motivo_fin"])
        liberar.set()
        # el hilo atascado se informa como incidencia de limpieza (no como éxito)
        self.assertEqual(res["resultado_global"], "incompleto")

    def test_archivo_stop_durante_la_peticion(self):
        be = self.backend(pausa=8.0, carga=0.1)
        base = self.raiz / "datos_v2"
        # CAMBIO V2-F.1 (V2-F: threading.Timer(1.0, …)): STOP solo cuando la petición está en curso
        hecho = al_ver_en_log(base, MARCA_PETICION, lambda: (base / "STOP").write_text(""))
        t = time.monotonic()
        res = self.orq(be).run_una_llamada(TAREA)
        self.assertTrue(hecho.is_set(), "el STOP no llegó a producirse durante una petición activa")
        self.assertLess(time.monotonic() - t, 8)
        self.assertEqual((res["estado"], res["motivo_fin"]), ("interrumpida", "stop_usuario"))
        self.assertIsNotNone(be.srv.proc.poll())
        self.assertEqual(self.sql("SELECT estado FROM sesiones"), [("interrumpida",)])
        self.assertEqual(self.sql("SELECT estado FROM tareas"), [("abortada",)])

    def test_parada_solicitada_durante_la_peticion(self):
        be = self.backend(pausa=8.0, carga=0.1)
        orq = self.orq(be)
        hecho = al_ver_en_log(self.raiz / "datos_v2", MARCA_PETICION, orq.solicitar_parada)  # CAMBIO V2-F.1 (V2-F: Timer 1.0)
        res = orq.run_una_llamada(TAREA)
        self.assertTrue(hecho.is_set())
        self.assertEqual((res["estado"], res["motivo_fin"]), ("interrumpida", "senal"))
        self.assertIsNotNone(be.srv.proc.poll())

    def test_ctrl_c_real_sigint(self):
        be = self.backend(pausa=8.0, carga=0.1)
        orq = self.orq(be, instalar_senales=True)
        previo = signal.getsignal(signal.SIGINT)
        hecho = al_ver_en_log(self.raiz / "datos_v2", MARCA_PETICION,  # CAMBIO V2-F.1 (V2-F: Timer 1.0)
                              lambda: os.kill(os.getpid(), signal.SIGINT))
        res = orq.run_una_llamada(TAREA)
        self.assertTrue(hecho.is_set())
        self.assertEqual((res["estado"], res["motivo_fin"]), ("interrumpida", "senal"))
        self.assertIsNotNone(be.srv.proc.poll())
        self.assertTrue(servidor.puerto_libre(be.srv.puerto))
        self.assertIs(signal.getsignal(signal.SIGINT), previo)          # manejador restaurado

    def test_sigterm_real(self):
        be = self.backend(pausa=8.0, carga=0.1)
        orq = self.orq(be, instalar_senales=True)
        hecho = al_ver_en_log(self.raiz / "datos_v2", MARCA_PETICION,  # CAMBIO V2-F.1 (V2-F: Timer 1.0)
                              lambda: os.kill(os.getpid(), signal.SIGTERM))
        res = orq.run_una_llamada(TAREA)
        self.assertTrue(hecho.is_set())
        self.assertEqual(res["motivo_fin"], "senal")
        self.assertIsNotNone(be.srv.proc.poll())

    def test_stop_antes_de_empezar_no_lanza_servidor(self):
        (self.raiz / "datos_v2").mkdir(parents=True)
        (self.raiz / "datos_v2" / "STOP").write_text("")
        be = self.backend()
        res = self.orq(be).run_una_llamada(TAREA)
        self.assertEqual(res["estado"], "interrumpida")
        self.assertEqual(res["llamadas_total"], 0)

    def test_ctrl_c_durante_la_carga(self):
        be = self.backend("nunca_listo")
        orq = self.orq(be)
        hecho = al_ver_en_log(self.raiz / "datos_v2", MARCA_CARGA, orq.solicitar_parada)  # CAMBIO V2-F.1 (V2-F: Timer 0.7)
        res = orq.run_una_llamada(TAREA)
        self.assertTrue(hecho.is_set())
        self.assertIn("senal", res["motivo_fin"])
        self.assertIsNotNone(be.srv.proc.poll())

    # V2-F.1 (portado de V2-E.9-r2): pruebas EXPLÍCITAS de interrupción durante el ARRANQUE (antes de que exista ninguna petición)
    def test_archivo_stop_durante_la_carga(self):
        be = self.backend("nunca_listo")
        base = self.raiz / "datos_v2"
        hecho = al_ver_en_log(base, MARCA_CARGA, lambda: (base / "STOP").write_text(""))
        res = self.orq(be).run_una_llamada(TAREA)
        self.assertTrue(hecho.is_set())
        self.assertEqual(res["estado"], "interrumpida")
        self.assertIn("stop_usuario", res["motivo_fin"])
        self.assertEqual(res["llamadas_total"], 0)
        self.assertEqual(self.sql("SELECT estado FROM tareas"), [])               # aún no había tarea: correcto
        self.assertEqual(self.sql("SELECT estado FROM sesiones"), [("interrumpida",)])
        self.assertIsNotNone(be.srv.proc.poll())
        self.assertTrue(servidor.puerto_libre(be.srv.puerto))
        self.assertFalse((base / "lock").exists())

    def test_memoria_baja_al_empezar_a_escuchar_durante_la_carga(self):
        estado = {"bajo": False}

        def lector(pid=None):
            m = muestra_ok(pid)
            if estado["bajo"]:
                m["MemAvailable"] = 1000
            return m
        hecho = al_ver_en_log(self.raiz / "datos_v2", MARCA_CARGA, lambda: estado.update(bajo=True))
        be = self.backend("nunca_listo", lector_muestra=lector)
        res = self.orq(be).run_una_llamada(TAREA)
        self.assertTrue(hecho.is_set())
        self.assertIn("abortado_durante_carga:presion_memoria", res["motivo_fin"])
        self.assertEqual(res["llamadas_total"], 0)
        self.assertEqual(self.sql("SELECT estado FROM tareas"), [])
        self.assertIsNotNone(be.srv.proc.poll())
        self.assertTrue(servidor.puerto_libre(be.srv.puerto))


class TestLimpiezaYEntorno(EntornoV2):
    def test_wake_lock_se_adquiere_y_se_libera(self):
        llamadas = []
        be = self.backend(usar_wake_lock=True, ejecutar_wake=lambda a, t: llamadas.append(a))
        res = self.orq(be).run_una_llamada(TAREA)
        self.assertEqual(llamadas, [["termux-wake-lock"], ["termux-wake-unlock"]])
        self.assertEqual(res["resultado_global"], "completo", res["errores_cierre"])

    def test_wake_lock_que_falla_no_impide_pero_se_informa(self):
        def falla(a, t):
            raise FileNotFoundError()
        be = self.backend(usar_wake_lock=True, ejecutar_wake=falla)
        res = self.orq(be).run_una_llamada(TAREA)
        self.assertEqual(res["estado"], "completa")
        self.assertEqual(res["resultado_global"], "incompleto")          # no se presenta como éxito limpio
        self.assertTrue(any("wake_unlock" in p for p in res["backend_informe"]["problemas"]))

    def test_sigkill_necesario_no_es_limpio(self):
        be = self.backend("ignora_sigterm", srv_kw={"gracia_term": 0.5})
        res = self.orq(be).run_una_llamada(TAREA)
        self.assertEqual(res["backend_informe"]["pasos"]["servidor"], "SIGKILL_usado")
        self.assertFalse(res["backend_informe"]["limpio"])
        self.assertEqual(res["resultado_global"], "incompleto")
        self.assertIsNotNone(be.srv.proc.poll())

    def test_el_modelo_no_se_modifica(self):
        antes = (self.modelo.read_bytes(), os.stat(self.modelo).st_mtime_ns)
        self.orq(self.backend()).run_una_llamada(TAREA)
        self.assertEqual((self.modelo.read_bytes(), os.stat(self.modelo).st_mtime_ns), antes)

    def test_auditoria_de_archivos_del_proyecto(self):
        """Con sys.addaudithook: ningún acceso al proyecto salvo LEER el modelo; nada de .env."""
        eventos = []
        activo = {"on": True}
        proyecto = str(self.proyecto.resolve())
        modelo = str(self.modelo.resolve())

        def hook(evento, args):
            if not activo["on"]:
                return
            if evento == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
                ruta = os.fsdecode(args[0])
                if ruta.startswith(proyecto) or ".env" in os.path.basename(ruta):
                    eventos.append((evento, ruta, args[1], args[2]))
            elif evento in ("os.listdir", "os.scandir", "os.mkdir", "os.remove", "os.rename",
                            "os.rmdir", "os.chmod", "shutil.rmtree"):
                a = args[0]
                if isinstance(a, (str, bytes, os.PathLike)) and os.fsdecode(a).startswith(proyecto):
                    eventos.append((evento, os.fsdecode(a)))
        sys.addaudithook(hook)
        try:
            res = self.orq(self.backend()).run_una_llamada(TAREA)
        finally:
            activo["on"] = False
        self.assertEqual(res["resultado_global"], "completo", res["errores_cierre"])
        self.assertTrue(eventos)                              # sí lee el modelo (comprobación del hook)
        for e in eventos:
            self.assertEqual(e[0], "open", e)
            self.assertEqual(os.path.realpath(e[1]), modelo, e)
            self.assertIn(e[2], ("rb", "r", None), e)
            self.assertEqual((e[3] or 0) & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC), 0, e)
        self.assertEqual((self.proyecto / ".env").read_text(), "SECRETO=1")

    def test_variables_sensibles_no_llegan_al_hijo(self):
        with mock.patch.dict(os.environ, {"X_API_KEY": "secreto"}):
            res = self.orq(self.backend()).run_una_llamada(TAREA)
        self.assertIn("ENV_SENSIBLES []", self.log(res))

    def test_carpeta_fuera_del_laboratorio_rechazada(self):
        with self.assertRaises(ValueError):
            orquestador.Orquestador(self.t / "otra", self.backend(), self.vigilante(),
                                    raiz_laboratorio=self.raiz)
        with self.assertRaises(ValueError):
            orquestador.Orquestador(self.proyecto / "x", self.backend(), self.vigilante(),
                                    raiz_laboratorio=self.proyecto / "x")

    def test_sesion_en_curso_previa_se_recupera_antes_de_arrancar(self):
        be1 = self.backend(pausa=8.0, carga=0.1)
        # simula un cierre brusco: sesión en_curso en la BD y candado ajeno ausente
        from eq2 import memoria
        (self.raiz / "datos_v2" / "datos").mkdir(parents=True)
        db = memoria.SesionDB(self.raiz / "datos_v2" / "datos" / "sesion.db")
        sid = db.crear_sesion()
        db.crear_tarea(sid, "huérfana")
        db.cerrar()
        res = self.orq(self.backend()).run_una_llamada(TAREA)
        self.assertEqual(res["sesiones_recuperadas"], [sid])
        self.assertEqual(res["estado"], "completa")


class TestSigkillDelSupervisor(EntornoV2):
    def test_si_matan_al_supervisor_el_hijo_puede_sobrevivir_y_se_documenta(self):
        """LIMITACIÓN REAL demostrada: tras SIGKILL del supervisor el hijo sigue vivo."""
        import subprocess
        codigo = (
            "import os, sys, signal, threading\n"
            f"sys.path.insert(0, {str(_comun.RAIZ / 'src')!r}); sys.path.insert(0, {str(_comun.RAIZ / 'tests')!r})\n"
            "os.environ['HOME'] = sys.argv[1]\n"
            "from eq2 import config, orquestador, vigilancia, servidor, backend_llama\n"
            "import _comun\n"
            "from _v2 import MARCA_PETICION, al_ver_en_log\n"
            "config.MIN_MODELO_BYTES = 1\n"
            "s = servidor.ServidorLlama(int(sys.argv[3]), comando=_comun.comando_fake('normal', 0.1, 30),\n"
            "    detector_llama=lambda: None, ayuda_fn=lambda: _comun.AYUDA_COMPLETA, lector_mem=lambda: 2000000,\n"
            "    sondeo_s=0.05)\n"
            "be = backend_llama.BackendLlama(s, intervalo_monitor=0.05)\n"
            "v = vigilancia.Vigilante(lector_mem=lambda: 1500000, lector_bat=lambda: (80, False))\n"
            "o = orquestador.Orquestador(sys.argv[2] + '/datos_v2', be, v, raiz_laboratorio=sys.argv[2])\n"
            # CAMBIO V2-F.1 (V2-F: threading.Timer(1.5, …)): SIGKILL cuando la petición está EN CURSO
            "al_ver_en_log(sys.argv[2] + '/datos_v2', MARCA_PETICION, lambda: (print('PID_HIJO', s.pid(), flush=True), "
            "os.kill(os.getpid(), signal.SIGKILL)))\n"
            "o.run_una_llamada('tarea')\n")
        puerto = _comun.puerto_aleatorio()
        p = subprocess.run([sys.executable, "-B", "-c", codigo, str(self.home), str(self.raiz), str(puerto)],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, -signal.SIGKILL, p.stderr[-500:])
        pid = int([l for l in p.stdout.splitlines() if l.startswith("PID_HIJO")][0].split()[1])
        try:
            vivo = os.path.exists(f"/proc/{pid}")
            self.assertTrue(vivo, "el hijo debería seguir vivo (limitación documentada)")
            self.assertFalse(servidor.puerto_libre(puerto))              # sigue ocupando el puerto
            # la siguiente ejecución lo detectaría por nombre `llama*` (aquí el falso se llama python)
            self.assertEqual(servidor.llama_activo(str(self.t / "proc_falso")), None)
            # V2-F.1 (portado de V2-E.9-r2): con el hijo superviviente vivo, NINGUNA ejecución siguiente arranca otro servidor
            self.assertTrue((self.raiz / "datos_v2" / "lock").exists())  # candado obsoleto sin borrar
            with self.assertRaises(orquestador.SesionActiva) as e:
                self.orq(self.backend(srv_kw={"puerto": puerto})).run_una_llamada(TAREA)
            self.assertIn("OBSOLETO", str(e.exception))
            for x in (self.raiz / "datos_v2" / "lock").iterdir():        # el usuario quita el candado a mano…
                x.unlink()
            (self.raiz / "datos_v2" / "lock").rmdir()
            be2 = self.backend(srv_kw={"puerto": puerto})
            res2 = self.orq(be2).run_una_llamada(TAREA)                  # …y el puerto ocupado lo sigue impidiendo
            self.assertEqual((res2["estado"], res2["llamadas_total"]), ("abortada", 0))
            self.assertIn("puerto ocupado", res2["motivo_fin"])
            self.assertIsNone(be2.srv.proc)                               # no se lanzó un segundo servidor
            self.assertTrue(os.path.exists(f"/proc/{pid}"))              # el superviviente sigue ahí: LIMITACIÓN
        finally:
            try:
                os.kill(pid, signal.SIGKILL)                              # limpieza de la PRUEBA
            except ProcessLookupError:
                pass
            for _ in range(200):                                          # espera a que desaparezca (estado, no tiempo)
                if not os.path.exists(f"/proc/{pid}"):
                    break
                time.sleep(0.01)


if __name__ == "__main__":
    unittest.main()
