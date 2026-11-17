"""Pruebas de V3.1 F0.5: adaptadores de plataforma (Linux/Termux y Windows con el mismo código).

Ejecutar desde equipo_ia_v3/:   python -B -m unittest discover -s pruebas -t pruebas -p test_eq3_plataforma.py -v

Lo que solo existe en una plataforma (uniones de directorio en Windows, symlinks de archivo sin privilegio) se OMITE
con su motivo, nunca se da por bueno.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import comun
from eq3 import plataforma as P

TEXTO = "ñandú · €uro · «comillas» · 漢字"
LANZADOR = comun.RAIZ / "eq3" / "lanzador_eq2.py"


def _tmp(caso) -> Path:
    d = tempfile.TemporaryDirectory(prefix="eq3_pf_", dir=os.environ.get("TMPDIR"))
    caso.addCleanup(d.cleanup)
    return Path(d.name).resolve()


def _enlace_a_carpeta(caso, destino, objetivo) -> None:
    """Symlink a carpeta (Linux/Termux) o, en Windows sin privilegio, unión de directorio."""
    comun.enlazar_o_omitir(caso, destino, objetivo)


class TestProcesosHijo(unittest.TestCase):
    def test_entorno_minimo_y_aislado(self):
        t = _tmp(self)
        e = P.entorno_hijo(t, {"EXTRA": "1"})
        self.assertEqual((e["HOME"], e["TMPDIR"], e["EXTRA"]), (str(t), str(t), "1"))
        v3 = {"PATH", "LANG", "HOME", "TMPDIR", "PYTHONDONTWRITEBYTECODE", "EXTRA"}
        if not P.WINDOWS:
            self.assertEqual(set(e), v3)                                    # Linux/Termux: el entorno de V3, tal cual
            return
        windows = {"USERPROFILE", "TEMP", "TMP", "APPDATA", "LOCALAPPDATA", "PYTHONUTF8", "PYTHONIOENCODING"}
        self.assertLessEqual(set(e), v3 | windows | set(P.VARIABLES_SISTEMA_WINDOWS))   # nada más del usuario
        self.assertEqual({e[k] for k in ("USERPROFILE", "TEMP", "TMP", "APPDATA", "LOCALAPPDATA")}, {str(t)})
        self.assertEqual((e["PYTHONUTF8"], e["PYTHONIOENCODING"]), ("1", "utf-8"))
        self.assertIn("SYSTEMROOT", e)

    def test_hijo_real_carpeta_personal_temporal_y_utf8(self):
        # `~` y la carpeta temporal del hijo son la carpeta de la prueba (en Windows, `~` sale de USERPROFILE), y un
        # texto no ASCII vuelve intacto en las dos direcciones.
        t = _tmp(self)
        codigo = ("import json, sys, tempfile; from pathlib import Path; "
                  "print(json.dumps({'home': str(Path.home()), 'tmp': tempfile.gettempdir(), 'eco': sys.argv[1]}, "
                  "ensure_ascii=False))")
        r = P.ejecutar([sys.executable, "-B", "-c", codigo, TEXTO], env=P.entorno_hijo(t), timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        d = json.loads(r.stdout)
        self.assertEqual((Path(d["home"]).resolve(), Path(d["tmp"]).resolve(), d["eco"]), (t, t, TEXTO))

    def test_orden_de_v2f1_segun_plataforma(self):
        o = P.orden_eq2("equipo.py", "demo")
        self.assertEqual(o[:2], [sys.executable, "-B"])
        if P.WINDOWS:
            self.assertEqual((o[2:4], Path(o[4]).name, o[5:]), (["-X", "utf8"], "lanzador_eq2.py", ["equipo.py", "demo"]))
        else:
            self.assertEqual(o[2:], ["equipo.py", "demo"])               # Linux/Termux: exactamente como antes


class TestLanzadorEq2(unittest.TestCase):
    """El lanzador se prueba en TODAS las plataformas (en Linux no cambia nada; en Windows evita el «\\r\\n»)."""

    def test_texto_con_lf_y_mismo_entorno_que_python_programa(self):
        t = _tmp(self)
        prog = t / "prog" / "escribe.py"
        prog.parent.mkdir()
        prog.write_text(
            "import json, os, sys\nfrom pathlib import Path\n"
            "open('a.txt', 'w', encoding='utf-8').write('uno\\ndos\\n')\n"
            "Path('b.txt').write_text('tres\\n', encoding='utf-8')\n"
            "fd = os.open('c.txt', os.O_CREAT | os.O_EXCL | os.O_WRONLY)\n"
            "with os.fdopen(fd, 'w', encoding='utf-8') as f:\n    f.write('cuatro\\n')\n"
            "open('d.txt', 'w', encoding='utf-8', newline='\\r\\n').write('cinco\\n')\n"   # explícito: se respeta
            "print(json.dumps({'argv': sys.argv, 'path0': sys.path[0], 'main': __name__}))\n", encoding="utf-8")
        trabajo = t / "trabajo"
        trabajo.mkdir()
        lanzador = comun.RAIZ / "eq3" / "lanzador_eq2.py"
        r = P.ejecutar([sys.executable, "-B", str(lanzador), str(prog), "x", "y"], cwd=trabajo,
                       env=P.entorno_hijo(t), timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual({n: (trabajo / n).read_bytes() for n in ("a.txt", "b.txt", "c.txt", "d.txt")},
                         {"a.txt": b"uno\ndos\n", "b.txt": b"tres\n", "c.txt": b"cuatro\n", "d.txt": b"cinco\r\n"})
        d = json.loads(r.stdout)
        self.assertEqual((d["argv"], Path(d["path0"]), d["main"]), ([str(prog), "x", "y"], prog.parent, "__main__"))

    def test_rechaza_lo_que_no_es_un_programa(self):
        t = _tmp(self)
        (t / "datos.txt").write_text("x", encoding="utf-8")
        for args in ([], ["-x"], ["-c"], ["-m"], [str(t / "no_existe.py")], [str(t / "datos.txt")]):
            with self.subTest(args=args):
                r = P.ejecutar([sys.executable, "-B", str(LANZADOR), *args], env=P.entorno_hijo(t), timeout=60)
                self.assertNotEqual(r.returncode, 0)

    def test_la_cadena_de_hijos_hereda_utf8_y_lf_y_conserva_opciones(self):
        # padre (lanzador) → hijo «-I -c» → nieto «script.py»: los tres en modo UTF-8, escribiendo «\n», con sus
        # opciones intactas y el código de salida propagado.
        t = _tmp(self)
        (t / "nieto.py").write_text(
            "import json, sys\nwith open('nieto.txt', 'w') as f:\n    f.write('n\\n')\n"
            "print(json.dumps({'utf8': sys.flags.utf8_mode, 'argv': sys.argv, 'dev': sys.flags.dev_mode}))\n"
            "sys.exit(5)\n", encoding="utf-8")
        hijo = ("import json, subprocess, sys\nwith open('hijo.txt', 'w') as f:\n    f.write('h\\n')\n"
                "r = subprocess.run([sys.executable, '-X', 'dev', 'nieto.py', 'z'], capture_output=True, text=True)\n"
                "print(json.dumps({'utf8': sys.flags.utf8_mode, 'aislado': sys.flags.isolated, 'eco': sys.argv[1],"
                " 'nieto_rc': r.returncode, 'nieto': json.loads(r.stdout)}, ensure_ascii=False))\n")
        (t / "padre.py").write_text(
            "import subprocess, sys\n"
            f"r = subprocess.run([sys.executable, '-B', '-I', '-c', {hijo!r}, {TEXTO!r}], capture_output=True)\n"
            "sys.stdout.buffer.write(r.stdout)\nsys.exit(r.returncode)\n", encoding="utf-8")
        r = P.ejecutar([sys.executable, "-B", "-X", "utf8", str(LANZADOR), "padre.py"], cwd=t,
                       env=P.entorno_hijo(t), timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr)
        d = json.loads(r.stdout)
        self.assertEqual((d["utf8"], d["aislado"], d["eco"]), (1, 1, TEXTO))              # -I conservado
        self.assertEqual((d["nieto_rc"], d["nieto"]["utf8"], d["nieto"]["dev"], d["nieto"]["argv"]),
                         (5, 1, True, ["nieto.py", "z"]))                                 # -X dev y argv[0] intactos
        self.assertEqual({n: (t / n).read_bytes() for n in ("hijo.txt", "nieto.txt")},
                         {"hijo.txt": b"h\n", "nieto.txt": b"n\n"})

    def test_home_define_la_carpeta_personal_como_en_linux(self):
        # V2-F.1 cambia HOME DENTRO del proceso (mock.patch.dict) para que ~/equipo-ia sea un laboratorio.
        t = _tmp(self)
        otra = t / "casa_de_prueba"
        otra.mkdir()
        codigo = ("import json, os; from pathlib import Path; from unittest import mock\n"
                  f"with mock.patch.dict(os.environ, {{'HOME': {str(otra)!r}}}):\n"
                  "    print(json.dumps([str(Path.home()), str(Path('~/x').expanduser()), os.path.expanduser('~nadie/y')]))")
        r = P.ejecutar([sys.executable, "-B", str(LANZADOR), "-c", codigo], env=P.entorno_hijo(t), timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        casa, x, ajeno = json.loads(r.stdout)
        self.assertEqual((Path(casa), Path(x)), (otra, otra / "x"))
        self.assertNotIn(str(otra), ajeno)                               # «~usuario» no se toca

    def _lanzador(self):
        sys.path.insert(0, str(comun.RAIZ / "eq3"))
        self.addCleanup(sys.path.remove, str(comun.RAIZ / "eq3"))
        import lanzador_eq2 as L
        return L

    def test_proc_solo_mediciones_reales_y_nada_inventado(self):
        L = self._lanzador()
        abiertos = []

        def abrir(file, mode="r", *a, **kw):
            abiertos.append((os.fspath(file), mode))
            raise FileNotFoundError(file)
        o = L.con_proc(abrir, medir_sistema=lambda: 1234567, medir_proceso=lambda pid: (2000, 3000))
        self.assertEqual(o("/proc/meminfo").read(), "MemAvailable:   1234567 kB\n")
        self.assertEqual(o("/proc/42/status").read(), "VmHWM:\t3000 kB\nVmRSS:\t2000 kB\n")   # solo lo medido
        self.assertEqual(abiertos, [])
        for ruta, modo in (("/proc/42/stat", "r"), ("/proc/meminfo", "rb"), ("/proc/meminfo", "w"),
                           ("/proc/self/status", "r"), ("/proc/meminfo.bak", "r"), ("datos.txt", "r")):
            with self.subTest(ruta=ruta, modo=modo), self.assertRaises(FileNotFoundError):
                o(ruta, modo)                                        # majflt (stat) y todo lo demás: sin tocar
        self.assertEqual(len(abiertos), 6)

    def test_proc_sin_medicion_se_comporta_como_sin_adaptador(self):
        # Si Windows no da el dato, NO se fabrica: se abre la ruta real (inexistente) y V2-F.1 aborta como antes.
        L = self._lanzador()

        def abrir(file, mode="r", *a, **kw):
            raise FileNotFoundError(file)
        o = L.con_proc(abrir, medir_sistema=lambda: None, medir_proceso=lambda pid: None)
        for ruta in ("/proc/meminfo", "/proc/42/status"):
            with self.subTest(ruta=ruta), self.assertRaises(FileNotFoundError):
                o(ruta)

    def test_v2f1_lee_la_memoria_real_de_windows(self):
        if not P.WINDOWS:
            self.skipTest("PLATAFORMA: en Linux y Termux V2-F.1 lee /proc directamente, sin adaptador")
        t = _tmp(self)
        codigo = ("import json, os, sys\n"
                  f"sys.path.append({str(comun.SISTEMA / 'src')!r})\n"
                  "from eq2 import monitor, vigilancia\n"
                  "import lanzador_eq2 as L\n"
                  "m = monitor.muestra_proceso(os.getpid())\n"
                  "print(json.dumps({'m': m, 'vig': vigilancia.leer_mem_available(), 'api': L.memoria_disponible_kb()}))")
        r = P.ejecutar([sys.executable, "-B", "-X", "utf8", str(LANZADOR), "-c",
                        f"import sys; sys.path.insert(0, {str(comun.RAIZ / 'eq3')!r})\n" + codigo],
                       env=P.entorno_hijo(t), timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        d = json.loads(r.stdout)
        m = d["m"]
        self.assertGreater(m["MemAvailable"], 0)
        self.assertLess(abs(m["MemAvailable"] - d["api"]), 512 * 1024)          # mismo dato que la API (±512 MiB)
        self.assertLess(abs(d["vig"] - d["api"]), 512 * 1024)
        self.assertGreater(m["VmRSS"], 1024)                                     # este proceso usa > 1 MiB
        self.assertGreaterEqual(m["VmHWM"], m["VmRSS"])
        for ausente in ("majflt", "minflt", "RssAnon", "RssFile", "SwapFree"):
            self.assertNotIn(ausente, m)                                         # nada inventado

    def test_no_se_interpone_en_el_ejecutor_restringido_ni_en_ordenes_ajenas(self):
        sys.path.insert(0, str(comun.RAIZ / "eq3"))
        self.addCleanup(sys.path.remove, str(comun.RAIZ / "eq3"))
        import lanzador_eq2 as L
        py = sys.executable
        intactas = [[py, "-I", "-S", "-B", "corredor.py", "x"],          # ejecutor restringido de V2-F.1
                    [py, "-IS", "x.py"], [py, "-i", "x.py"], [py, "-"], [py], [py, "--version"],
                    [py, "x.txt"], ["llama-server", "-m", "a.gguf"], "python x.py", [py, "-c"],
                    [py, str(LANZADOR), "x.py"],                          # ya adaptada: no se encadena
                    [py, "-B", "-X", "utf8", str(Path("otro") / "espejo" / "eq3" / "lanzador_eq2.py"), "x.py"]]
        # (F1) la última es OTRA copia del lanzador (espejo de mutación): envolverla instalaba los ajustes dos veces
        for orden in intactas:
            with self.subTest(orden=orden):
                self.assertIs(L.adaptar_orden(orden), orden)
        self.assertEqual(L.adaptar_orden([py, "-B", "-W", "error", "-X", "dev", "-m", "unittest", "-v"]),
                         [py, "-B", "-W", "error", "-X", "dev", "-X", "utf8", L.LANZADOR, "-m", "unittest", "-v"])

    def test_dos_copias_del_lanzador_no_entran_en_recursion(self):
        # F1: un proceso con el lanzador original que ejecuta el de un espejo tenía DOS buscadores de clases distintas
        # que se llamaban entre sí (RecursionError al importar eq2.backend_llama).
        import importlib.util
        copias = []
        for i in range(2):
            spec = importlib.util.spec_from_file_location(f"lanzador_copia_{i}", LANZADOR)
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            copias.append(m)
        antes = list(sys.meta_path)
        self.addCleanup(lambda: sys.meta_path.__setitem__(slice(None), antes))
        sys.meta_path[:0] = [copias[0].BuscadorBackend(), copias[1].BuscadorBackend()]
        self.assertIsNone(copias[0].BuscadorBackend().find_spec("eq2.backend_llama_que_no_existe"))
        spec = sys.meta_path[0].find_spec("json")
        self.assertIsNone(spec)                                                   # solo reconoce eq2.backend_llama
        sys.path.insert(0, str(comun.SISTEMA / "src"))
        self.addCleanup(sys.path.remove, str(comun.SISTEMA / "src"))
        ruta = [str(comun.SISTEMA / "src" / "eq2")]                               # __path__ del paquete eq2
        spec = sys.meta_path[0].find_spec("eq2.backend_llama", ruta)              # antes: RecursionError
        self.assertIsNotNone(spec)
        self.assertEqual(type(spec.loader).__name__, "_CargadorBackend")


class _ErrorFalso(Exception):
    def __init__(self, motivo="error", fatal=False):
        super().__init__(motivo)
        self.motivo, self.fatal = str(motivo), bool(fatal)


class _ServidorFalso:
    def __init__(self, proc):
        self.proc = proc


class _BackendFalso:
    """Lo mínimo de BackendLlama que mira el adaptador: `srv.proc`, `peticiones` y `completar`."""

    def __init__(self, proc, motivo=None, fatal=True):
        self.srv, self.peticiones, self.motivo, self.fatal = _ServidorFalso(proc), [], motivo, fatal

    def completar(self, mensajes, max_tokens, plazo_s):
        reg = {"n": len(self.peticiones) + 1}
        self.peticiones.append(reg)
        if self.motivo is None:
            return "respuesta"
        reg["fallo"] = self.motivo
        raise _ErrorFalso(self.motivo, fatal=self.fatal)


class TestServidorMuerto(unittest.TestCase):
    """Adaptador de Windows para V-SRV-12 / V-UNI-23: «conexion_perdida» pasa a «servidor_muerto» SOLO con evidencia de
    que el proceso del servidor terminó. La lógica se prueba en todas las plataformas, con procesos REALES."""
    CORTE = "conexion_perdida:ConnectionResetError"

    def setUp(self):
        sys.path.insert(0, str(comun.RAIZ / "eq3"))
        self.addCleanup(sys.path.remove, str(comun.RAIZ / "eq3"))
        import lanzador_eq2 as L
        self.L = L

    def _proceso(self, codigo):
        import subprocess
        p = subprocess.Popen([sys.executable, "-I", "-S", "-c", codigo])

        def cerrar():
            if p.poll() is None:
                p.kill()
            p.wait(30)
        self.addCleanup(cerrar)
        return p

    def _terminado(self):
        p = self._proceso("import os; os._exit(9)")
        p.wait(30)
        return p

    def _vivo(self):
        return self._proceso("import time; time.sleep(600)")

    def _completar(self, proc, motivo, fatal=True, **kw):
        be = _BackendFalso(proc, motivo, fatal)
        adaptado = self.L.con_servidor_muerto(_BackendFalso.completar, _ErrorFalso, **kw)
        try:
            return be, adaptado(be, [], 1, 1.0), None
        except _ErrorFalso as e:
            return be, None, e

    def test_positiva_proceso_terminado_es_servidor_muerto(self):
        be, _, e = self._completar(self._terminado(), self.CORTE)
        self.assertEqual((e.motivo, e.fatal), ("servidor_muerto", True))
        self.assertEqual(be.peticiones[-1]["fallo"], "servidor_muerto")
        self.assertEqual(e.__cause__.motivo, self.CORTE)                 # el error original queda en la traza

    def test_positiva_proceso_que_termina_dentro_de_la_espera(self):
        # Windows puede entregar el corte unos milisegundos antes de que el proceso tenga código de salida.
        p = self._proceso("import os, time; time.sleep(0.15); os._exit(9)")
        _, _, e = self._completar(p, self.CORTE)
        self.assertEqual((e.motivo, p.returncode), ("servidor_muerto", 9))

    def test_negativa_servidor_vivo_conserva_conexion_perdida(self):
        p = self._vivo()
        be, _, e = self._completar(p, self.CORTE)
        self.assertEqual((e.motivo, e.fatal), (self.CORTE, True))        # misma etiqueta, y sigue siendo fatal
        self.assertEqual(be.peticiones[-1]["fallo"], self.CORTE)
        self.assertIsNone(p.poll())                                      # el adaptador no ha tocado el proceso

    def test_negativa_estado_indeterminado_conserva_conexion_perdida(self):
        class SinEstado:                                                 # consultar el proceso falla
            def wait(self, espera):
                raise OSError("no se puede consultar")

            def poll(self):
                raise OSError("no se puede consultar")

        class SinCodigo:                                                 # `wait` vuelve, pero sin código de salida
            def wait(self, espera):
                return None

            def poll(self):
                return None
        for nombre, proc in (("sin_proceso", None), ("consulta_falla", SinEstado()), ("sin_codigo", SinCodigo()),
                             ("no_es_un_proceso", object())):
            with self.subTest(nombre):
                be, _, e = self._completar(proc, self.CORTE)
                self.assertEqual((e.motivo, e.fatal, be.peticiones[-1]["fallo"]), (self.CORTE, True, self.CORTE))
        be = _BackendFalso(None, self.CORTE)
        del be.srv                                                       # ni siquiera hay servidor
        with self.assertRaises(_ErrorFalso) as c:
            self.L.con_servidor_muerto(_BackendFalso.completar, _ErrorFalso)(be, [], 1, 1.0)
        self.assertEqual(c.exception.motivo, self.CORTE)

    def test_negativa_otros_motivos_no_cambian_aunque_el_servidor_haya_muerto(self):
        # Una parada pedida, un plazo agotado u otro fallo NUNCA se convierten en «servidor_muerto».
        muerto = self._terminado()
        consultas = []

        def terminado(backend):
            consultas.append(backend)
            return True
        for motivo, fatal in (("stop_usuario", True), ("senal", True), ("plazo_agotado", True),
                              ("presion_memoria", True), ("respuesta_truncada", False), ("http_500", False),
                              ("envio_fallido:ConnectionResetError", True), ("conexion_fallida:OSError", False),
                              ("x_conexion_perdida:ConnectionResetError", True)):
            with self.subTest(motivo):
                be, _, e = self._completar(muerto, motivo, fatal, terminado=terminado)
                self.assertEqual((e.motivo, e.fatal, be.peticiones[-1]["fallo"]), (motivo, fatal, motivo))
        self.assertEqual(consultas, [])                                  # ni se consulta el proceso

    def test_respuesta_normal_y_otras_excepciones_pasan_intactas(self):
        be, r, e = self._completar(self._terminado(), None)
        self.assertEqual((r, e, be.peticiones), ("respuesta", None, [{"n": 1}]))

        def revienta(self_, *a):
            raise KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            self.L.con_servidor_muerto(revienta, _ErrorFalso)(_BackendFalso(None))

    def test_servidor_terminado_con_procesos_reales(self):
        vivo, muerto = self._vivo(), self._terminado()
        self.assertTrue(self.L.servidor_terminado(_BackendFalso(muerto)))
        self.assertFalse(self.L.servidor_terminado(_BackendFalso(vivo), espera=0.2))
        self.assertIsNone(vivo.poll())
        self.assertFalse(self.L.servidor_terminado(_BackendFalso(None)))
        self.assertFalse(self.L.servidor_terminado(object()))

    def test_adaptar_backend_solo_una_vez_y_solo_con_la_forma_esperada(self):
        import types
        m = types.ModuleType("m")
        m.BackendLlama, m.ErrorInferencia = type("BackendLlama", (_BackendFalso,), {}), _ErrorFalso
        original = m.BackendLlama.completar
        self.assertTrue(self.L.adaptar_backend(m))
        self.assertIs(m.BackendLlama.completar.__wrapped__, original)
        self.assertFalse(self.L.adaptar_backend(m))                      # no se encadena
        self.assertIs(m.BackendLlama.completar.__wrapped__, original)
        for raro in (types.ModuleType("vacio"), types.SimpleNamespace(BackendLlama=object(), ErrorInferencia=_ErrorFalso),
                     types.SimpleNamespace(BackendLlama=type("B", (), {}), ErrorInferencia=_ErrorFalso)):
            self.assertFalse(self.L.adaptar_backend(raro))

    def _backend_de_v2f1(self, con_lanzador):
        t = _tmp(self)
        codigo = ("import json, sys\n"
                  f"sys.path.insert(0, {str(comun.SISTEMA / 'src')!r})\n"
                  "from eq2 import backend_llama as B, cliente_http, inferencia\n"
                  "print(json.dumps({'adaptado': hasattr(B.BackendLlama.completar, '__wrapped__'),\n"
                  " 'archivo': B.__file__, 'error': B.ErrorInferencia is inferencia.ErrorInferencia,\n"
                  " 'otros': [hasattr(f, '__wrapped__') for f in (B.BackendLlama.iniciar, B.BackendLlama.detener,\n"
                  "           B.BackendLlama.supervisar, B.BackendLlama._deberia_parar, cliente_http.peticion)]}))")
        orden = [sys.executable, "-B", "-X", "utf8", *([str(LANZADOR)] if con_lanzador else []), "-c", codigo]
        r = P.ejecutar(orden, env=P.entorno_hijo(t), timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_el_lanzador_adapta_el_backend_real_solo_en_windows(self):
        d = self._backend_de_v2f1(con_lanzador=True)
        self.assertEqual(d["adaptado"], P.WINDOWS)                       # en Linux/Termux V2-F.1 queda tal cual
        self.assertEqual(Path(d["archivo"]).resolve(), (comun.SISTEMA / "src" / "eq2" / "backend_llama.py").resolve())
        self.assertTrue(d["error"])
        self.assertEqual(d["otros"], [False] * 5)                        # STOP, vigilancia y cliente HTTP: sin tocar
        self.assertFalse(self._backend_de_v2f1(con_lanzador=False)["adaptado"])

    def test_v2f1_real_servidor_que_muere_en_la_peticion(self):
        # De punta a punta con el BackendLlama REAL de V2-F.1 y su servidor falso: la prueba de V2-F.1 que fallaba en
        # Windows (V-SRV-12), ejecutada a través del lanzador como hace F11.
        if not P.WINDOWS:
            self.skipTest("PLATAFORMA: en Linux y Termux la comprueba la propia V2-F.1 sin adaptador (línea base)")
        t = _tmp(self)
        r = P.ejecutar(P.orden_eq2("-m", "unittest", "-v",
                                   "test_v2_backend.TestErroresHTTP.test_servidor_muere_durante_la_peticion"),
                       cwd=comun.SISTEMA / "tests", env=P.entorno_hijo(t), timeout=300)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Ran 1 test", r.stderr)


class TestEnlaces(unittest.TestCase):
    def test_archivos_y_carpetas_normales_no_son_enlaces(self):
        t = _tmp(self)
        (t / "f.txt").write_text("x", encoding="utf-8")
        (t / "d").mkdir()
        self.assertEqual([P.es_enlace(t / n) for n in ("f.txt", "d", "no_existe")], [False, False, False])

    def test_enlace_a_carpeta_detectado(self):
        t = _tmp(self)
        (t / "objetivo").mkdir()
        _enlace_a_carpeta(self, t / "enlace", t / "objetivo")
        self.assertTrue(P.es_enlace(t / "enlace"))

    def test_union_de_windows_detectada_aunque_is_symlink_no_la_vea(self):
        t = _tmp(self)
        (t / "objetivo").mkdir()
        comun.union_o_omitir(self, t / "union", t / "objetivo")
        self.assertFalse((t / "union").is_symlink())                       # por esto no basta con is_symlink()
        self.assertTrue(P.es_enlace(t / "union"))

    def test_enlace_a_archivo(self):
        t = _tmp(self)
        (t / "f.txt").write_text("x", encoding="utf-8")
        if not P.puede_enlazar_archivos(t):
            with self.assertRaises(P.EnlaceNoDisponible):
                P.crear_enlace(t / "e.txt", t / "f.txt")
            self.skipTest("PLATAFORMA: sin privilegio para symlinks de archivo (comprobado que se informa)")
        P.crear_enlace(t / "e.txt", t / "f.txt")
        self.assertTrue(P.es_enlace(t / "e.txt"))

    def test_replica_de_solo_lectura_no_alcanza_el_original_al_borrarla(self):
        t = _tmp(self)
        (t / "origen" / "sub").mkdir(parents=True)
        (t / "origen" / "sub" / "f.txt").write_text("original", encoding="utf-8")
        (t / "espejo").mkdir()
        modo = P.replicar_solo_lectura(t / "origen", t / "espejo" / "origen")
        self.assertIn(modo, ("simbolico", "copia"))
        self.assertEqual((t / "espejo" / "origen" / "sub" / "f.txt").read_text(encoding="utf-8"), "original")
        shutil.rmtree(t / "espejo")
        self.assertEqual((t / "origen" / "sub" / "f.txt").read_text(encoding="utf-8"), "original")

    def test_replicar_con_acceso_denegado_copia_y_otros_errores_no_se_ocultan(self):
        if not P.WINDOWS:
            self.skipTest("PLATAFORMA: los códigos WinError solo existen en Windows")
        t = _tmp(self)
        (t / "origen").mkdir()
        (t / "origen" / "f.txt").write_text("original", encoding="utf-8")

        def falla(codigo):
            def symlink(*a, **kw):
                e = OSError(codigo, "simulado")
                e.winerror = codigo
                raise e
            return symlink
        with mock.patch.object(P.os, "symlink", falla(5)):                    # acceso denegado esporádico
            self.assertEqual(P.replicar_solo_lectura(t / "origen", t / "copia5"), "copia")
        self.assertEqual((t / "copia5" / "f.txt").read_text(encoding="utf-8"), "original")
        with mock.patch.object(P.os, "symlink", falla(3)), self.assertRaises(OSError):   # ruta no encontrada: falla
            P.replicar_solo_lectura(t / "origen", t / "copia3")
        self.assertFalse((t / "copia3").exists())


class TestLecturaAcotada(unittest.TestCase):
    def setUp(self):
        self.t = _tmp(self)
        (self.t / "pkg").mkdir()
        (self.t / "pkg" / "m.py").write_bytes(b"x = 1\r\ny = 2\n")

    def test_lee_los_bytes_exactos(self):
        self.assertEqual(P.leer_acotado(self.t, "pkg/m.py", 100), b"x = 1\r\ny = 2\n")

    def test_rutas_rechazadas(self):
        for mala in ("../m.py", "/etc/passwd", "pkg\\m.py", "pkg/m.py\x00", "", ".", "pkg/m.py:flujo",
                     "pkg/m.py.", "pkg/m.py ", "C:/x.py", 5):
            with self.subTest(ruta=mala), self.assertRaises(ValueError):
                P.leer_acotado(self.t, mala, 100)

    def test_limites_y_tipos(self):
        with self.assertRaisesRegex(ValueError, "excede"):
            P.leer_acotado(self.t, "pkg/m.py", 4)
        with self.assertRaisesRegex(ValueError, "no regular"):
            P.leer_acotado(self.t, "pkg", 100)
        with self.assertRaises(OSError):
            P.leer_acotado(self.t, "pkg/no_existe.py", 100)
        with self.assertRaises(ValueError):
            P.leer_acotado(self.t, "pkg/m.py", -1)

    def test_ningun_componente_ni_la_raiz_puede_ser_un_enlace(self):
        fuera = self.t / "fuera"
        fuera.mkdir()
        (fuera / "s.py").write_text("secreto = 1\n", encoding="utf-8")
        _enlace_a_carpeta(self, self.t / "pkg" / "puente", fuera)
        with self.assertRaisesRegex(ValueError, "no permitida"):
            P.leer_acotado(self.t, "pkg/puente/s.py", 100)
        _enlace_a_carpeta(self, self.t / "raiz_enlazada", self.t / "pkg")
        with self.assertRaisesRegex(ValueError, "no permitida"):
            P.leer_acotado(self.t / "raiz_enlazada", "m.py", 100)

    def test_el_archivo_abierto_debe_ser_el_comprobado(self):
        real = os.fstat

        def otro(fd):
            st = real(fd)
            return os.stat_result((st.st_mode, st.st_ino + 1, *st[2:]))
        with mock.patch.object(P.os, "fstat", otro), self.assertRaisesRegex(ValueError, "cambiado"):
            P.leer_acotado(self.t, "pkg/m.py", 100)

    def test_contexto_ligero_solo_se_adapta_donde_falta_la_lectura_posix(self):
        from eq3 import grafo
        from contexto_core import safety
        self.assertEqual(grafo.LECTURA_ADAPTADA, not P.lectura_posix_disponible())
        self.assertEqual(safety.read_bounded is P.leer_acotado, not P.lectura_posix_disponible())
        self.assertEqual(safety.read_bounded(self.t, "pkg/m.py", 100), b"x = 1\r\ny = 2\n")


class TestRutasEnTextos(unittest.TestCase):
    def test_variantes(self):
        p = Path("/x/salida")
        self.assertIn("/x/salida", P.variantes_ruta(p))
        if P.WINDOWS:
            self.assertIn("C:\\\\a\\\\b", P.variantes_ruta(Path("C:\\a\\b")))   # repr de Windows: «\» escapadas

    def test_barras_tras_marca_solo_en_windows(self):
        texto = "falta '<SALIDA>\\\\a\\\\b.txt' y <SISTEMA>\\src\\x.py; fuera\\de\\marca"
        r = P.barras_tras_marca(texto, ("<SALIDA>", "<SISTEMA>"))
        if P.WINDOWS:
            self.assertEqual(r, "falta '<SALIDA>/a/b.txt' y <SISTEMA>/src/x.py; fuera\\de\\marca")
        else:
            self.assertEqual(r, texto)                                      # Linux: firmas byte a byte iguales


if __name__ == "__main__":
    unittest.main()
