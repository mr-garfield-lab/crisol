"""V2-E.1: escritura sin sobrescritura cuando os.link NO existe (Android/Termux), errores de
enlace acotados por errno, rechazo de sobrescrituras y enlaces, concurrencia (hilos y procesos)
y limpieza de temporales/parciales ante errores.

Todo se ejecuta contra el sistema de archivos REAL de un directorio temporal. La ausencia de
os.link se SIMULA retirando el atributo del módulo os durante la prueba.
"""
import ast
import contextlib
import errno
import json
import os
import subprocess
import sys
import threading
import unittest
from pathlib import Path
from unittest import mock

import _comun
from eq2 import asesoria, config, ejecutor, motor, proyecto, rutas

RAIZ = _comun.RAIZ
T = config.TAREA_V2B


@contextlib.contextmanager
def sin_link():
    """Simula una plataforma sin os.link (como el Python de Termux)."""
    original = getattr(os, "link", None)
    if original is not None:
        del os.link
    try:
        yield
    finally:
        if original is not None:
            os.link = original


MODOS = {"con_link": contextlib.nullcontext, "sin_link": sin_link}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = _comun.carpeta_temporal()
        self.addCleanup(self.tmp.cleanup)
        self.t = Path(self.tmp.name)
        self.raiz = self.t / "equipo_f2"
        self.lab = rutas.Laboratorio(self.raiz, self.raiz / "datos_v2e1")
        self.lab.crear_base()
        self.lab.crear_dir("d")
        self.d = self.raiz / "datos_v2e1" / "d"

    def temporales(self):
        return [p.name for p in (self.raiz / "datos_v2e1").rglob(".tmp_*")]


# ============================ 1. regresión: sin os.link ==================================
class TestSinLink(Base):
    def test_deteccion_explicita(self):
        self.assertEqual(rutas.hay_enlaces_duros(), hasattr(os, "link"))
        with sin_link():
            self.assertFalse(rutas.hay_enlaces_duros())
            self.assertFalse(hasattr(os, "link"))

    def test_escribe_sin_link_sin_atomicidad_y_lo_indica(self):
        with sin_link():
            p, atomico = self.lab.escribir_atomico(("d", "a.txt"), "contenido completo")
        self.assertFalse(atomico)
        self.assertEqual(p.read_text(), "contenido completo")
        self.assertEqual(self.temporales(), [])
        if hasattr(os, "link"):
            p2, at2 = self.lab.escribir_atomico(("d", "b.txt"), "x")
            self.assertTrue(at2)

    def test_no_usa_os_replace_ni_rename(self):
        with sin_link(), mock.patch.object(rutas.os, "replace", side_effect=AssertionError("replace")), \
                mock.patch.object(rutas.os, "rename", side_effect=AssertionError("rename")):
            self.lab.escribir_atomico(("d", "a.txt"), "x")

    def test_proyecto_y_motor_completos_sin_link(self):
        """Los 23 resultados de Termux: el motor completo debe funcionar sin os.link."""
        from test_v2e import ejec_sim, guion_proyecto
        with sin_link():
            inf = motor.Motor(self.raiz / "datos_v2e1", motor.AgentesMotorSimulados(guion_proyecto()),
                              ejecutor.EjecutorSimulado(ejec_sim), raiz_laboratorio=self.raiz).ejecutar(T)
        self.assertEqual(inf["estado_final"], "criterios_superados_en_simulacion", inf["errores"])
        self.assertEqual(inf["errores"], [])
        self.assertTrue(all(v["atomico"] is False for v in inf["versiones"]))
        d = self.raiz / "datos_v2e1" / "runs" / inf["run_id"] / "proyecto"
        man = json.loads((d / "v2" / "manifiesto.json").read_text())
        import hashlib
        for f in man["archivos"]:
            self.assertEqual(hashlib.sha256((d / "v2" / f["ruta"]).read_bytes()).hexdigest(), f["sha256"])
        self.assertEqual(self.temporales(), [])

    def test_asesoria_sin_link(self):
        with sin_link():
            n = asesoria.exportar(self.lab, {"run_id": "r1", "tarea": "t"})
        self.assertTrue((self.raiz / "datos_v2e1" / "asesoria" / n).is_file())


# ============================ 2. errores de os.link ======================================
class TestErroresDeLink(Base):
    def test_errno_de_sistema_sin_enlaces_usa_la_alternativa(self):
        for en in (errno.EPERM, errno.EACCES, errno.EXDEV, errno.EMLINK, errno.ENOSYS,
                   getattr(errno, "ENOTSUP", errno.EPERM)):
            with self.subTest(errno=errno.errorcode.get(en)):
                n = f"f{en}.txt"
                with mock.patch.object(rutas.os, "link", side_effect=OSError(en, "x"), create=True):
                    p, at = self.lab.escribir_atomico(("d", n), "ok")
                self.assertFalse(at)
                self.assertEqual(p.read_text(), "ok")
                self.assertEqual(self.temporales(), [])

    def test_otros_errores_se_propagan_y_limpian(self):
        for exc in (OSError(errno.EIO, "disco"), OSError(errno.ENOSPC, "lleno"), OSError("sin errno")):
            with self.subTest(exc=repr(exc)):
                with mock.patch.object(rutas.os, "link", side_effect=exc, create=True):
                    with self.assertRaises(OSError):
                        self.lab.escribir_atomico(("d", "e.txt"), "x")
                self.assertFalse((self.d / "e.txt").exists())
                self.assertEqual(self.temporales(), [])

    def test_carrera_el_destino_aparece_justo_antes_del_link(self):
        def otro_escritor(src, dst):
            Path(dst).write_text("del otro")
            raise FileExistsError(errno.EEXIST, "existe", dst)
        with mock.patch.object(rutas.os, "link", side_effect=otro_escritor, create=True):
            with self.assertRaises(FileExistsError):
                self.lab.escribir_atomico(("d", "c.txt"), "mío")
        self.assertEqual((self.d / "c.txt").read_text(), "del otro")
        self.assertEqual(self.temporales(), [])

    def test_errores_no_previstos_no_se_disfrazan(self):
        with mock.patch.object(rutas.os, "link", side_effect=AttributeError("raro"), create=True):
            with self.assertRaises(AttributeError):
                self.lab.escribir_atomico(("d", "z.txt"), "x")
        self.assertEqual(self.temporales(), [])


# ============================ 3. rechazo de sobrescrituras y enlaces =====================
class TestSobrescritura(Base):
    def test_rechazos_en_ambos_modos(self):
        fuera = self.t / "fuera.txt"
        fuera.write_text("ajeno")
        for modo, ctx in MODOS.items():
            with self.subTest(modo=modo), ctx():
                (self.d / f"{modo}.txt").write_text("original")
                with self.assertRaises(FileExistsError):
                    self.lab.escribir_atomico(("d", f"{modo}.txt"), "nuevo")
                self.assertEqual((self.d / f"{modo}.txt").read_text(), "original")
                (self.d / f"{modo}_enlace.txt").symlink_to(fuera)
                with self.assertRaises((rutas.RutaInsegura, FileExistsError)):
                    self.lab.escribir_atomico(("d", f"{modo}_enlace.txt"), "nuevo")
                (self.d / f"{modo}_colgante.txt").symlink_to(self.t / "no_existe.txt")
                with self.assertRaises((rutas.RutaInsegura, FileExistsError)):
                    self.lab.escribir_atomico(("d", f"{modo}_colgante.txt"), "nuevo")
                self.assertFalse((self.t / "no_existe.txt").exists())
                (self.d / f"{modo}_dir").mkdir()
                with self.assertRaises(FileExistsError):
                    self.lab.escribir_atomico(("d", f"{modo}_dir"), "nuevo")
                with self.assertRaises(rutas.RutaInsegura):
                    self.lab.escribir_atomico(("..", "x.txt"), "nuevo")
                self.assertEqual(self.temporales(), [])
        self.assertEqual(fuera.read_text(), "ajeno")

    def test_carpeta_enlazada_rechazada(self):
        fuera = self.t / "fuera"
        fuera.mkdir()
        (self.raiz / "datos_v2e1" / "enlazada").symlink_to(fuera)
        for modo, ctx in MODOS.items():
            with self.subTest(modo=modo), ctx():
                with self.assertRaises(rutas.RutaInsegura):
                    self.lab.escribir_atomico(("enlazada", "x.txt"), "x")
        self.assertEqual(list(fuera.iterdir()), [])

    def test_alternativa_crea_con_o_excl_y_o_nofollow(self):
        vistos = []
        real = os.open

        def espia(ruta, flags, *a, **k):
            vistos.append((os.path.basename(ruta), flags))
            return real(ruta, flags, *a, **k)
        with sin_link(), mock.patch.object(rutas.os, "open", side_effect=espia):
            self.lab.escribir_atomico(("d", "flags.txt"), "x")
        flags = dict(vistos)["flags.txt"]
        self.assertTrue(flags & os.O_EXCL and flags & os.O_CREAT)
        self.assertFalse(flags & os.O_TRUNC)
        if hasattr(os, "O_NOFOLLOW"):
            self.assertTrue(flags & os.O_NOFOLLOW)


# ============================ 4. concurrencia ============================================
class TestConcurrencia(Base):
    def correr_hilos(self, n=16, mismo=True):
        barrera = threading.Barrier(n)
        res = [None] * n

        def trabajo(i):
            barrera.wait()
            try:
                nombre = "mismo.txt" if mismo else f"h{i}.txt"
                self.lab.escribir_atomico(("d", nombre), f"escritor {i} " * 200)
                res[i] = "ok"
            except FileExistsError:
                res[i] = "existe"
        hs = [threading.Thread(target=trabajo, args=(i,)) for i in range(n)]
        for h in hs:
            h.start()
        for h in hs:
            h.join(30)
        return res

    def test_hilos_mismo_destino_un_unico_ganador(self):
        for modo, ctx in MODOS.items():
            with self.subTest(modo=modo), ctx():
                for f in self.d.iterdir():
                    f.unlink()
                res = self.correr_hilos()
                self.assertEqual(res.count("ok"), 1, res)
                self.assertEqual(res.count("existe"), 15)
                contenido = (self.d / "mismo.txt").read_text()
                ganador = res.index("ok")
                self.assertEqual(contenido, f"escritor {ganador} " * 200)       # sin mezclas
                self.assertEqual(self.temporales(), [])

    def test_hilos_destinos_distintos(self):
        for modo, ctx in MODOS.items():
            with self.subTest(modo=modo), ctx():
                for f in self.d.iterdir():
                    f.unlink()
                self.assertEqual(self.correr_hilos(mismo=False), ["ok"] * 16)
                self.assertEqual(len(list(self.d.iterdir())), 16)

    def test_procesos_mismo_destino(self):
        codigo = (
            "import os, sys, time\n"
            f"sys.path.insert(0, {str(RAIZ / 'src')!r})\n"
            "if sys.argv[3] == 'sin_link' and hasattr(os, 'link'):\n"
            "    del os.link\n"
            "from eq2 import rutas\n"
            "lab = rutas.Laboratorio(sys.argv[1], sys.argv[2])\n"
            "inicio = float(sys.argv[4])\n"
            "while time.time() < inicio:\n"
            "    time.sleep(0.001)\n"
            "try:\n"
            "    p, at = lab.escribir_atomico(('d', 'proc.txt'), ('proceso %d ' % os.getpid()) * 500)\n"
            "    print('ok', at)\n"
            "except FileExistsError:\n"
            "    print('existe')\n")
        import time
        for modo in MODOS:
            with self.subTest(modo=modo):
                for f in self.d.iterdir():
                    f.unlink()
                inicio = time.time() + 1.5
                ps = [subprocess.Popen([sys.executable, "-B", "-I", "-c", codigo, str(self.raiz),
                                        str(self.raiz / "datos_v2e1"), modo, str(inicio)],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                      for _ in range(6)]
                salidas = [p.communicate(timeout=60) for p in ps]
                lineas = [o.strip() for o, e in salidas]
                self.assertEqual(sum(1 for l in lineas if l.startswith("ok")), 1, salidas)
                self.assertEqual(sum(1 for l in lineas if l == "existe"), 5, salidas)
                if modo == "sin_link":
                    self.assertIn("ok False", lineas)
                c = (self.d / "proc.txt").read_text()
                self.assertEqual(len(set(c.split())), 2)                         # un único autor
                self.assertEqual(self.temporales(), [])


# ============================ 5. limpieza ante errores ===================================
class TestLimpieza(Base):
    def test_fallo_de_escritura_no_deja_restos(self):
        """Un sustituto suelto (\\udcff) no se puede codificar en UTF-8: falla la escritura."""
        for modo, ctx in MODOS.items():
            with self.subTest(modo=modo), ctx():
                with self.assertRaises(UnicodeEncodeError):
                    self.lab.escribir_atomico(("d", f"{modo}.txt"), "bien\udcffmal")
                self.assertFalse((self.d / f"{modo}.txt").exists())
                self.assertEqual(self.temporales(), [])

    def test_fallo_de_fsync_no_deja_restos(self):
        for modo, ctx in MODOS.items():
            with self.subTest(modo=modo), ctx(), \
                    mock.patch.object(rutas.os, "fsync", side_effect=OSError(errno.EIO, "fsync")):
                with self.assertRaises(OSError):
                    self.lab.escribir_atomico(("d", f"fs_{modo}.txt"), "x")
                self.assertFalse((self.d / f"fs_{modo}.txt").exists())
                self.assertEqual(self.temporales(), [])

    def test_fallo_de_fdopen_cierra_el_descriptor(self):
        cerrados = []
        real_close = os.close
        with mock.patch.object(rutas.os, "fdopen", side_effect=OSError(errno.EMFILE, "x")), \
                mock.patch.object(rutas.os, "close", side_effect=lambda fd: (cerrados.append(fd), real_close(fd))):
            with self.assertRaises(OSError):
                self.lab.crear_exclusivo(("d", "fd.txt"), "x")
        self.assertEqual(len(cerrados), 1)
        self.assertFalse((self.d / "fd.txt").exists())

    def test_crear_exclusivo_limpia_el_parcial(self):
        with self.assertRaises(UnicodeEncodeError):
            self.lab.crear_exclusivo(("d", "p.txt"), "a\udcff")
        self.assertFalse((self.d / "p.txt").exists())
        (self.d / "existente.txt").write_text("suyo")
        with self.assertRaises(FileExistsError):
            self.lab.crear_exclusivo(("d", "existente.txt"), "a\udcff")
        self.assertEqual((self.d / "existente.txt").read_text(), "suyo")      # no se borra lo ajeno

    def test_reemplazar_atomico_limpia_y_conserva_el_original(self):
        self.lab.reemplazar_atomico(("d", "estado.json"), "uno")
        with mock.patch.object(rutas.os, "replace", side_effect=OSError(errno.EIO, "x")):
            with self.assertRaises(OSError):
                self.lab.reemplazar_atomico(("d", "estado.json"), "dos")
        self.assertEqual((self.d / "estado.json").read_text(), "uno")
        self.assertEqual(self.temporales(), [])
        with self.assertRaises(UnicodeEncodeError):
            self.lab.reemplazar_atomico(("d", "estado.json"), "\udcff")
        self.assertEqual((self.d / "estado.json").read_text(), "uno")
        self.assertEqual(self.temporales(), [])

    def test_proyecto_con_error_a_mitad_no_deja_temporales(self):
        p = proyecto.Proyecto(self.lab, "r1", motor.Presupuesto())
        import hashlib
        malo = "x\udcff"
        lista = [{"nombre": "a.py", "contenido": "ok\n", "bytes": 3, "sha256": hashlib.sha256(b"ok\n").hexdigest()},
                 {"nombre": "b.py", "contenido": malo, "bytes": 2, "sha256": "0" * 64}]
        for modo, ctx in MODOS.items():
            with self.subTest(modo=modo), ctx():
                with self.assertRaises(UnicodeEncodeError):
                    p.guardar_version(lista)
                self.assertEqual(self.temporales(), [])
        # Defecto de V2-E corregido: tras un fallo, la siguiente versión se guarda (antes, FileExistsError)
        bien = p.guardar_version(lista[:1])
        self.assertEqual(bien["version"], 3)
        self.assertEqual(p.incompletas, [1, 2])
        d = self.raiz / "datos_v2e1" / "runs" / "r1" / "proyecto"
        self.assertFalse((d / "v1" / "manifiesto.json").exists())        # incompleta = sin manifiesto
        self.assertTrue((d / "v3" / "manifiesto.json").exists())
        self.assertEqual([m["version"] for m in p.versiones], [3])


# ============================ 6. garantías estáticas =====================================
class TestEstatico(unittest.TestCase):
    def test_rutas_no_captura_excepciones_de_forma_indiscriminada(self):
        arbol = ast.parse((RAIZ / "src" / "eq2" / "rutas.py").read_text(encoding="utf-8"))
        for n in ast.walk(arbol):
            if isinstance(n, ast.ExceptHandler):
                self.assertIsNotNone(n.type, f"except desnudo en la línea {n.lineno}")
                nombres = [t.id for t in (n.type.elts if isinstance(n.type, ast.Tuple) else [n.type])
                           if isinstance(t, ast.Name)]
                self.assertFalse({"Exception", "BaseException"} & set(nombres), f"línea {n.lineno}")

    def test_el_validador_lo_impone(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("validar_estatico", RAIZ / "validar_estatico.py")
        v = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(v)
        tmp = _comun.carpeta_temporal()
        self.addCleanup(tmp.cleanup)
        f = Path(tmp.name) / "rutas.py"
        for codigo in ("try:\n    pass\nexcept:\n    pass\n", "try:\n    pass\nexcept Exception:\n    pass\n",
                       "try:\n    pass\nexcept (OSError, BaseException):\n    pass\n"):
            f.write_text(codigo)
            self.assertTrue(any("prohibido en rutas.py" in p for p in v.problemas_de(f)), codigo)
        f.write_text("try:\n    pass\nexcept OSError:\n    pass\n")
        self.assertEqual(v.problemas_de(f), [])

    def test_modo_b_sigue_deshabilitado(self):
        self.assertFalse(config.MODO_B_HABILITADO)

    def test_carpetas(self):
        self.assertEqual(config.CARPETA_V2E1, "datos_v2e1")
        self.assertIn("datos_v2e", config.CARPETAS_ANTERIORES)


if __name__ == "__main__":
    unittest.main()
