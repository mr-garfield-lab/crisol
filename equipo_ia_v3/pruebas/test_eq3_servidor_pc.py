"""Pruebas de V3.1 F1: `eq3/servidor_pc.py` (llama-server REAL en el PC con el ciclo de vida de V2-F.1).

Ejecutar desde equipo_ia_v3/:   python -B -m unittest discover -s pruebas -t pruebas -p test_eq3_servidor_pc.py -v

Los escenarios de arranque usan el ciclo de vida REAL de V2-F.1 (procesos, sockets, archivos) contra su servidor
FALSO, en un proceso hijo (`aux_servidor_pc.py`): lo único SIMULADO es el modelo. Aquí no se arranca ningún
llama-server real ni se usa la GPU.
"""
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

import comun
from eq3 import plataforma as P
from eq3 import servidor_pc as S

AUX = comun.RAIZ / "pruebas" / "aux_servidor_pc.py"


def _tmp(caso) -> Path:
    d = tempfile.TemporaryDirectory(prefix="eq3_srv_", dir=os.environ.get("TMPDIR"))
    caso.addCleanup(d.cleanup)
    return Path(d.name).resolve()


def _externos(t: Path) -> tuple:
    ext = t / "ext"
    (ext / "ll").mkdir(parents=True)
    (ext / "modelos").mkdir()
    datos = {"llama-server.exe": b"exe", "a.dll": b"dll"}
    for n, b in datos.items():
        (ext / "ll" / n).write_bytes(b)
    (ext / "modelos" / "m.gguf").write_bytes(b"GGUF123")
    reg = {"llama": {"carpeta": "ll", "ejecutable": "llama-server.exe", "version": "v",
                     "archivos": {n: {"sha256": hashlib.sha256(b).hexdigest(), "bytes": len(b)} for n, b in datos.items()}},
           "modelo": {"archivo": "modelos/m.gguf", "sha256": hashlib.sha256(b"GGUF123").hexdigest(), "bytes": 7}}
    return ext, reg


def _escenario(caso, nombre) -> dict:
    t = _tmp(caso)
    r = P.ejecutar(P.orden_eq2(str(AUX), nombre, str(t)), cwd=comun.SISTEMA, env=P.entorno_hijo(t), timeout=180)
    caso.assertEqual(r.returncode, 0, r.stderr[-1500:])
    return json.loads(r.stdout.strip().splitlines()[-1])


class TestVerificacionDeExternos(unittest.TestCase):
    def test_todo_coincide(self):
        ext, reg = _externos(_tmp(self))
        v = S.verificar_externos(ext, reg)
        self.assertTrue(v["ok"], v)
        self.assertEqual((v["archivos"], len(v["huellas"])), (3, 3))
        self.assertEqual(Path(v["ejecutable"]), ext / "ll" / "llama-server.exe")
        self.assertEqual(S.sin_cambios(v), [])

    def test_cualquier_diferencia_se_detecta(self):
        casos = {
            "binario alterado (mismo tamaño)": (lambda e: (e / "ll" / "a.dll").write_bytes(b"dlx"), "SHA-256 distinto: a.dll"),
            "binario de otro tamaño": (lambda e: (e / "ll" / "a.dll").write_bytes(b"dll+"), "tamaño distinto: a.dll"),
            "falta un binario": (lambda e: (e / "ll" / "a.dll").unlink(), "falta: a.dll"),
            "archivo de más junto al ejecutable": (lambda e: (e / "ll" / "extra.dll").write_bytes(b"x"),
                                                   "archivo no registrado: extra.dll"),
            "modelo alterado": (lambda e: (e / "modelos" / "m.gguf").write_bytes(b"GGUF124"),
                                "SHA-256 distinto: modelos/m.gguf"),
            "falta el modelo": (lambda e: (e / "modelos" / "m.gguf").unlink(), "falta: modelos/m.gguf"),
        }
        for nombre, (alterar, problema) in casos.items():
            with self.subTest(nombre):
                ext, reg = _externos(_tmp(self))
                alterar(ext)
                v = S.verificar_externos(ext, reg)
                self.assertFalse(v["ok"])
                self.assertIn(problema, v["problemas"])
                with self.assertRaises(S.ExternosNoVerificados):
                    S.crear_backend(v)

    def test_falta_la_carpeta(self):
        _, reg = _externos(_tmp(self))
        v = S.verificar_externos(_tmp(self), reg)
        self.assertFalse(v["ok"])
        self.assertIn("falta la carpeta ll", v["problemas"])

    def test_cambio_posterior_a_la_verificacion(self):
        ext, reg = _externos(_tmp(self))
        v = S.verificar_externos(ext, reg)
        (ext / "ll" / "a.dll").write_bytes(b"dll cambiada")
        self.assertEqual([Path(c).name for c in S.sin_cambios(v)], ["a.dll"])
        with self.assertRaises(S.ExternosNoVerificados):
            S.crear_backend(v)
        with self.assertRaises(S.ExternosNoVerificados):              # una verificación sin huellas no vale
            S.crear_backend({"ok": True})

    def test_el_registro_real_es_coherente(self):
        reg = S.cargar_registro()
        self.assertIn(reg["llama"]["ejecutable"], reg["llama"]["archivos"])
        for d in list(reg["llama"]["archivos"].values()) + [reg["modelo"]]:
            self.assertRegex(d["sha256"], r"^[0-9a-f]{64}$")
            self.assertGreater(d["bytes"], 0)
        self.assertNotIn(":\\", json.dumps(reg))                       # ninguna ruta de esta máquina


class TestDetector(unittest.TestCase):
    def test_procesos_llama_por_prefijo(self):
        lista = lambda: [(4, "System"), (10, "LLAMA-server.exe"), (11, "llama-cli.exe"), (12, "ollama.exe")]
        self.assertEqual(S.procesos_llama(lista), [(10, "LLAMA-server.exe"), (11, "llama-cli.exe")])
        self.assertEqual(S.procesos_llama(lambda: [(4, "System")]), [])
        self.assertIsNone(S.procesos_llama(lambda: None))
        self.assertIsNone(S.procesos_llama(lambda: []))                # una lista vacía no es creíble

    @unittest.skipUnless(P.WINDOWS, "PLATAFORMA: el detector propio solo se usa en Windows (en Linux, el de V2-F.1)")
    def test_detector_falla_cerrado(self):
        self.assertEqual(S.detector_llama(lambda: [(10, "llama-server.exe")]), "10")
        self.assertIsNone(S.detector_llama(lambda: [(4, "System")]))
        self.assertEqual(S.detector_llama(lambda: None), S.SIN_LISTA)  # no se puede saber: V2-F.1 no lanzará nada

    @unittest.skipUnless(P.WINDOWS, "PLATAFORMA: instantánea de procesos de Windows")
    def test_lista_real_de_procesos(self):
        procesos = S.listar_procesos_windows()
        nombres = {pid: n for pid, n in procesos}
        self.assertIn(os.getpid(), nombres)
        self.assertTrue(nombres[os.getpid()].lower().startswith("python"), nombres[os.getpid()])


class TestVram(unittest.TestCase):
    def test_lectura_y_fallo(self):
        class R:
            def __init__(self, rc, out):
                self.returncode, self.stdout = rc, out
        salidas = iter([R(0, "1297, 8192\n"), R(0, "4242, 5300\n")])
        self.assertEqual(S.vram_mib(lambda *a, **k: next(salidas)),
                         {"usada": 1297, "total": 8192, "procesos": {4242: 5300}})
        self.assertIsNone(S.vram_mib(lambda *a, **k: R(1, "")))

        def falla(*a, **k):
            raise FileNotFoundError("nvidia-smi")
        self.assertIsNone(S.vram_mib(falla))


class TestCicloDeVidaConServidorFalso(unittest.TestCase):
    """REAL: procesos, sockets, monitor y STOP de V2-F.1. SIMULADO: el modelo (servidor falso de V2-F.1)."""

    def test_arranque_peticion_y_cierre_limpio(self):
        r = _escenario(self, "normal")
        self.assertTrue(r["verificacion_ok"])
        self.assertNotIn("error", r)
        self.assertEqual(Path(r["perfil"]["modelo"]).name, "m.gguf")
        self.assertEqual(r["perfil"]["hilos"], S.HILOS_PC)
        argv = r["argv"]
        self.assertEqual(argv[argv.index("--host") + 1], "127.0.0.1")
        self.assertEqual((argv[argv.index("-t") + 1], argv[argv.index("-np") + 1]), (str(S.HILOS_PC), "1"))
        self.assertIn("--no-ui", argv)
        self.assertEqual(Path(argv[argv.index("-m") + 1]).name, "m.gguf")
        self.assertTrue(r["detencion"]["limpio"], r["detencion"])
        self.assertTrue(r["proceso_terminado"] and r["puerto_libre_despues"])

    def test_llama_ya_activo_no_lanza_nada(self):
        r = _escenario(self, "llama_activo")
        self.assertIn("comprobaciones_fallidas", r["error"])
        self.assertIn("pid 4242", r["error"])
        self.assertFalse(r["lanzado"])

    @unittest.skipUnless(P.WINDOWS, "PLATAFORMA: el detector propio solo se usa en Windows")
    def test_procesos_no_listables_no_lanza_nada(self):
        r = _escenario(self, "sin_lista")
        self.assertIn(S.SIN_LISTA, r["error"])
        self.assertFalse(r["lanzado"])

    def test_externos_alterados_tras_verificar_no_lanza_nada(self):
        r = _escenario(self, "externos_alterados")
        self.assertEqual(r["error"], "ExternosNoVerificados")
        self.assertIn("llama-server.exe", r["detalle"])

    def test_stop_durante_la_peticion_detiene_y_libera(self):
        r = _escenario(self, "stop")
        self.assertIn("stop_usuario", r["error"])
        self.assertLess(r["segundos_hasta_error"], 15)                 # el servidor falso tardaría 30 s en responder
        self.assertTrue(r["lanzado"])
        self.assertTrue(r["proceso_terminado"] and r["puerto_libre_despues"], r)
        self.assertTrue(r["detencion"]["puerto_liberado"])


if __name__ == "__main__":
    unittest.main()
