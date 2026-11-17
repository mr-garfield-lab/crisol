"""ServidorLlama con el FALSO llama-server (procesos hijos y sockets reales; NO es Qwen)."""
import os
import socket
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

import _comun
from _v2 import EntornoV2
from eq2 import config, rutas, servidor
from eq2.inferencia import ErrorInferencia


class Base(EntornoV2):
    def lab(self, run="r1"):
        l = rutas.Laboratorio(self.raiz)
        l.crear_base()
        l.crear_dir("runs", run)
        return l

    def arrancar(self, srv, run="r1"):
        c = srv.comprobaciones(True)
        self.assertTrue(c["ok"], c["problemas"])
        srv.lanzar(self.lab(run), run)
        return srv


class TestArgv(Base):
    def test_argv_exacto_produccion(self):
        s = servidor.ServidorLlama(8089)
        self.assertEqual(s.construir_argv(),
                         ["llama-server", "-m", str(self.modelo), "--host", "127.0.0.1", "--port", "8089",
                          "-c", "1024", "-t", "4", "-np", "1", "--no-ui"])

    def test_sin_flags_prohibidos(self):
        a = servidor.ServidorLlama(8089).construir_argv()
        for malo in ("--no-mmap", "--mlock", "--cache-ram", "0.0.0.0", "--api-key", "--host=0.0.0.0"):
            self.assertNotIn(malo, a)
        self.assertEqual(a[a.index("--host") + 1], "127.0.0.1")

    def test_puerto_invalido(self):
        for p in (0, 80, 1023, 65536, "8089", None, True):
            with self.assertRaises(ValueError):
                servidor.ServidorLlama(p)


class TestComprobaciones(Base):
    def comp(self, **kw):
        return self.servidor(**kw).comprobaciones(True)

    def test_ok(self):
        c = self.comp()
        self.assertTrue(c["ok"], c["problemas"])
        self.assertTrue(c["puerto_libre"])
        self.assertEqual(c["modelo"]["magic"], "GGUF")

    def test_modelo_ausente_pequeno_o_sin_marca_o_enlace(self):
        self.modelo.unlink()
        self.assertFalse(self.comp()["ok"])
        self.modelo.write_bytes(b"GGUF" + b"\0" * 10)
        with mock.patch.object(config, "MIN_MODELO_BYTES", 10 ** 6):
            self.assertTrue(any("pequeño" in p for p in self.comp()["problemas"]))
        self.modelo.write_bytes(b"XXXX" + b"\0" * 100)
        self.assertTrue(any("GGUF" in p for p in self.comp()["problemas"]))
        self.modelo.unlink()
        os.symlink(self.t / "otro.gguf", self.modelo)
        self.assertTrue(any("enlace" in p for p in self.comp()["problemas"]))

    def test_proceso_llama_activo_no_se_mata(self):
        c = self.servidor(detector_llama=lambda: "4242").comprobaciones(True)
        self.assertFalse(c["ok"])
        self.assertTrue(any("4242" in p for p in c["problemas"]))

    def test_puerto_ocupado(self):
        l = socket.socket()
        l.bind(("127.0.0.1", 0))
        l.listen(1)
        self.addCleanup(l.close)
        c = self.comp(puerto=l.getsockname()[1])
        self.assertFalse(c["puerto_libre"])
        self.assertIn("puerto ocupado", c["problemas"])

    def test_sin_lectura_de_memoria(self):
        c = self.comp(lector_mem=lambda: None)
        self.assertTrue(any("MemAvailable" in p for p in c["problemas"]))

    def test_flags_faltantes_y_ayuda_ilegible(self):
        c = self.comp(ayuda_fn=lambda: "--host --port")
        self.assertTrue(any("flags" in p for p in c["problemas"]))
        self.assertIn("--no-ui", c["flags_faltantes"])

        def mala():
            raise OSError("x")
        self.assertFalse(self.comp(ayuda_fn=mala)["ok"])

    def test_binario_inexistente(self):
        s = servidor.ServidorLlama(_comun.puerto_aleatorio(), comando=["/no/existe/llama-server"],
                                   detector_llama=lambda: None, lector_mem=lambda: 1)
        self.assertTrue(any("ejecutable" in p for p in s.comprobaciones(False)["problemas"]))

    def test_lanzar_exige_comprobaciones(self):
        s = self.servidor()
        with self.assertRaises(ErrorInferencia):
            s.lanzar(self.lab(), "r1")
        s.comprobaciones(True)
        s.lanzar(self.lab(), "r1")
        with self.assertRaises(ErrorInferencia):                 # un solo hijo por ejecución
            s.lanzar(self.lab(), "r1")
        s.detener()


class TestFuncionesAuxiliares(Base):
    def test_llama_activo(self):
        d = self.t / "proc"
        for pid, comm in (("100", "bash\n"), ("200", "llama-server\n"), ("abc", "llama\n")):
            (d / pid).mkdir(parents=True)
            (d / pid / "comm").write_text(comm)
        self.assertEqual(servidor.llama_activo(str(d)), "200")
        self.assertIsNone(servidor.llama_activo(str(self.t / "no_existe")))
        (d / "200" / "comm").write_text("python\n")
        self.assertIsNone(servidor.llama_activo(str(d)))

    def test_puerto_libre(self):
        p = _comun.puerto_aleatorio()
        self.assertTrue(servidor.puerto_libre(p))
        l = socket.socket()
        l.bind(("127.0.0.1", p))
        l.listen(1)
        try:
            self.assertFalse(servidor.puerto_libre(p))
        finally:
            l.close()
        self.assertTrue(servidor.puerto_libre(p))

    def test_entorno_sin_credenciales(self):
        e = servidor.entorno({"PATH": "/bin", "MI_API_KEY": "x", "GITHUB_TOKEN": "y",
                              "db_password": "z", "ANTHROPIC_BASE": "w", "openai_org": "v",
                              "MY_SECRET": "s", "HOME": "/h"})
        self.assertEqual(sorted(e), ["HOME", "PATH"])

    def test_wake_lock(self):
        llamadas = []
        self.assertEqual(servidor.wake_lock(lambda a, t: llamadas.append(a)), "ok")
        self.assertEqual(servidor.wake_lock(lambda a, t: llamadas.append(a), liberar=True), "ok")
        self.assertEqual(llamadas, [["termux-wake-lock"], ["termux-wake-unlock"]])

        def falla(a, t):
            raise FileNotFoundError()
        self.assertTrue(servidor.wake_lock(falla).startswith("fallo"))


class TestCicloDeVida(Base):
    def test_arranque_listo_y_parada_limpia(self):
        s = self.arrancar(self.servidor())
        pid = s.pid()
        self.assertTrue(s.vivo())
        self.assertIsNotNone(s.esperar_listo())
        self.assertEqual(s.detener(), "SIGTERM_ok")
        self.assertFalse(s.vivo())
        self.assertTrue(s.esperar_puerto_libre())
        self.assertEqual(s.cerrar_log(), "ok")
        self.assertEqual(s.detener(), f"ya_terminado_rc_{s.proc.returncode}")      # idempotente
        self.assertFalse(os.path.exists(f"/proc/{pid}") and "python" in
                         Path(f"/proc/{pid}/comm").read_text() and s.proc.poll() is None)

    def test_hijo_recibe_argv_cwd_y_entorno_filtrado(self):
        with mock.patch.dict(os.environ, {"PRUEBA_API_KEY": "no-debe-llegar", "PRUEBA_OK": "1"}):
            s = self.arrancar(self.servidor())
            s.esperar_listo()
        s.detener()
        s.cerrar_log()
        log = (self.raiz / "runs" / "r1" / "server.log").read_text()
        self.assertIn('"--host", "127.0.0.1"', log)
        self.assertIn('"-c", "1024"', log)
        self.assertIn('"-t", "4"', log)
        self.assertIn('"-np", "1"', log)
        self.assertIn("ENV_SENSIBLES []", log)
        self.assertIn("CWD " + str((self.raiz / "runs" / "r1").resolve()), log)

    def test_popen_una_sola_vez_sin_shell(self):
        with mock.patch.object(servidor.subprocess, "Popen", wraps=subprocess.Popen) as p:
            s = self.arrancar(self.servidor())
            s.esperar_listo()
            s.detener()
        self.assertEqual(p.call_count, 1)
        args, kw = p.call_args
        self.assertIsInstance(args[0], list)
        self.assertFalse(kw.get("shell", False))
        self.assertEqual(kw["stdin"], subprocess.DEVNULL)
        self.assertNotIn("PRUEBA_API_KEY", kw["env"])

    def test_sigterm_ignorado_se_usa_sigkill_solo_al_hijo(self):
        ajeno = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        self.addCleanup(lambda: (ajeno.kill(), ajeno.wait()))
        s = self.arrancar(self.servidor("ignora_sigterm", gracia_term=0.5))
        s.esperar_listo()
        self.assertEqual(s.detener(), "SIGKILL_usado")
        self.assertIsNone(ajeno.poll())                      # un proceso ajeno sigue vivo
        self.assertTrue(s.esperar_puerto_libre())

    def test_cierre_lento_dentro_de_la_gracia(self):
        s = self.arrancar(self.servidor("tarda_en_cerrar", gracia_term=5))
        s.esperar_listo()
        t = time.monotonic()
        self.assertEqual(s.detener(), "SIGTERM_ok")
        self.assertGreater(time.monotonic() - t, 1.0)

    def test_cierre_lento_fuera_de_la_gracia(self):
        s = self.arrancar(self.servidor("tarda_en_cerrar", gracia_term=0.3))
        s.esperar_listo()
        self.assertEqual(s.detener(), "SIGKILL_usado")

    def test_muere_al_arrancar(self):
        s = self.arrancar(self.servidor("muere_al_arrancar"))
        with self.assertRaises(ErrorInferencia) as e:
            s.esperar_listo()
        self.assertIn("servidor_murio_al_arrancar_rc_3", e.exception.motivo)
        self.assertTrue(e.exception.fatal)
        self.assertEqual(s.detener(), "ya_terminado_rc_3")

    def test_nunca_listo_timeout_de_carga(self):
        s = self.arrancar(self.servidor("nunca_listo", max_carga_s=1.0))
        t = time.monotonic()
        with self.assertRaises(ErrorInferencia) as e:
            s.esperar_listo()
        self.assertEqual(e.exception.motivo, "timeout_carga")
        self.assertLess(time.monotonic() - t, 4)
        self.assertEqual(s.detener(), "SIGTERM_ok")

    def test_esperar_listo_se_aborta_desde_fuera(self):
        s = self.arrancar(self.servidor("nunca_listo"))
        t0 = time.monotonic()
        with self.assertRaises(ErrorInferencia) as e:
            s.esperar_listo(deberia_parar=lambda: "stop_usuario" if time.monotonic() - t0 > 0.5 else None)
        self.assertIn("stop_usuario", e.exception.motivo)
        s.detener()
        with self.assertRaises(ErrorInferencia):
            s2 = self.arrancar(self.servidor("nunca_listo"), run="r2")
            try:
                s2.esperar_listo(supervisar=lambda: "monitor_sin_latido")
            finally:
                s2.detener()

    def test_puerto_libre_despues_de_cerrar_y_log_de_errores(self):
        s = self.arrancar(self.servidor("muere_al_arrancar"))
        time.sleep(0.8)
        self.assertTrue(any("error" in l for l in s.log_nuevo()))
        self.assertEqual(s.log_nuevo(), [])                  # posiciones en bytes: no repite
        s.detener()
        self.assertTrue(s.esperar_puerto_libre())

    def test_detener_sin_lanzar(self):
        self.assertEqual(self.servidor().detener(), "sin_servidor")


if __name__ == "__main__":
    unittest.main()
