"""Pruebas del empaquetado (Etapa 8): exclusiones, rechazos de contenido privado o peligroso, extracción segura y
ZIP reproducible."""
import hashlib
import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

V3 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V3))
import empaquetar as E  # noqa: E402
from eq3 import plataforma  # noqa: E402  (empaquetar añade equipo_ia_v3/ a sys.path)


def _tmp(caso):
    d = tempfile.TemporaryDirectory(prefix="eq3_zip_", dir=os.environ.get("TMPDIR"))
    caso.addCleanup(d.cleanup)
    return Path(d.name)


class TestContenidoReal(unittest.TestCase):
    def test_exclusiones_del_arbol_real(self):
        nombres = [n for n, _ in E.recoger()]
        self.assertFalse([n for n in nombres if "GameAgentEngine" in n])
        self.assertFalse([n for n in nombres if "/fuentes/claude_v2f1/" in n])
        self.assertFalse([n for n in nombres if n.endswith(E.EXCLUIR_SUFIJOS) or "__pycache__" in n])
        for imprescindible in ("equipo_ia_v3/verificar_v3.py", "equipo_ia_v3/v3/linea_base_esperada.json",
                               "fuentes/contexto_ligero_v35/tests/test_index.py", "AGENTS.md"):
            self.assertIn(f"{E.PREFIJO}/{imprescindible}", nombres)


# Los datos de prueba se construyen en tiempo de ejecución: el propio archivo de pruebas no debe contener patrones
# de credenciales ni direcciones de correo literales, porque el empaquetado lo rechazaría (y con razón).
PEM = "-----BEGIN " + "PRIVATE KEY-----"
PEM_RSA = "-----BEGIN RSA " + "PRIVATE KEY-----"
CORREO = "alguien" + "@" + "ejemplo.com"


class TestRechazos(unittest.TestCase):
    def _con(self, nombre, contenido):
        d = _tmp(self) / "arbol"
        d.mkdir()
        (d / nombre).write_text(contenido, encoding="utf-8")
        return mock.patch.multiple(E, INCLUIR=[("x", d)], SUELTOS=[]), d

    def test_credencial_correo_y_enlace(self):
        clave = PEM_RSA + "\nMII"
        for nombre, contenido, motivo in (("a.txt", clave, "posible credencial"),
                                          ("b.txt", "token ghp_" + "a" * 36, "posible credencial"),
                                          ("c.md", "escribe a " + CORREO, "dirección de correo")):
            parche, _ = self._con(nombre, contenido)
            with self.subTest(nombre=nombre), parche, self.assertRaisesRegex(E.Rechazo, motivo):
                E.recoger()
        # Enlace a una carpeta (en Windows sin privilegio, una UNIÓN) y, donde se puede, a un archivo.
        parche, d = self._con("ok.txt", "nada")
        (d / "sub").mkdir()
        (d / "sub" / "x.txt").write_text("y", encoding="utf-8")
        objetivos = [d / "sub"] + ([d / "ok.txt"] if plataforma.puede_enlazar_archivos(d) else [])
        for i, objetivo in enumerate(objetivos):
            enlace = d / f"enlace{i}"
            plataforma.crear_enlace(enlace, objetivo)
            with self.subTest(objetivo=objetivo.name), parche, self.assertRaisesRegex(E.Rechazo, "enlace simbólico"):
                E.recoger()
            os.rmdir(enlace) if plataforma.WINDOWS and objetivo.is_dir() else enlace.unlink()

    def test_exclusiones_por_nombre_aunque_esten_dentro(self):
        d = _tmp(self) / "arbol"
        for rel in ("GameAgentEngine/motor.py", "__pycache__/x.pyc", "datos/b.sqlite3", "modelos/q.gguf", "ok.py"):
            (d / rel).parent.mkdir(parents=True, exist_ok=True)
            (d / rel).write_text("x = 1\n", encoding="utf-8")
        with mock.patch.multiple(E, INCLUIR=[("x", d)], SUELTOS=[]):
            self.assertEqual([n for n, _ in E.recoger()], [f"{E.PREFIJO}/x/ok.py"])

    def test_la_excepcion_de_fixture_esta_ligada_al_hash(self):
        parche, d = self._con("f.py", PEM + "\nVALOR_PRIVADO")
        nombre = f"{E.PREFIJO}/x/f.py"
        with parche, mock.patch.dict(E.FIXTURES_SINTETICAS, {nombre: hashlib.sha256((d / "f.py").read_bytes()).hexdigest()}):
            self.assertEqual(len(E.recoger()), 1)                              # mismo contenido: exceptuado
            (d / "f.py").write_text(PEM + "\nOTRO", encoding="utf-8")
            with self.assertRaisesRegex(E.Rechazo, "posible credencial"):
                E.recoger()                                                    # contenido distinto: vuelve a revisarse


class TestRutasPersonales(unittest.TestCase):
    """V3.1: ninguna ruta personal en el ZIP. Las rutas de prueba se construyen en tiempo de ejecución (como PEM):
    este archivo no puede contener ninguna literal, porque el empaquetado lo rechazaría."""
    OTRO_WIN = "C:" + "\\" + "Users" + "\\" + "maria" + "\\" + "proyecto" + "\\" + "a.py"
    OTRO_LINUX = "/" + "home" + "/" + "maria" + "/proyecto/a.py"

    @staticmethod
    def _recortada(ruta: Path) -> str:
        """Como aparece en una traza JSON recortada por el principio: sin unidad, sin barra inicial y con «\\»
        escapadas dos veces (visto en evidencias reales: «carpeta\\\\\\\\de\\\\\\\\trabajo\\\\\\\\…»)."""
        r = str(ruta)
        r = r[2:] if len(r) > 1 and r[1] == ":" else r
        return r.replace("\\", "\\\\\\\\").lstrip("\\/")

    def _arbol(self, destino, nombre, contenido):
        d = _tmp(self) / "arbol"
        d.mkdir()
        (d / nombre).write_text(contenido, encoding="utf-8")
        return mock.patch.multiple(E, INCLUIR=[(destino, d)], SUELTOS=[]), d

    def test_codigo_con_ruta_personal_se_rechaza(self):
        maquina = [str(Path.home() / "x.txt"), str(E.REPO.parent / "t" / "l5"),
                   str(E.REPO.parent / "t")[2:],                                 # recortada: sin la unidad
                   self._recortada(E.REPO.parent / "t")]                          # …y sin la barra, escapada dos veces
        for i, ruta in enumerate([self.OTRO_WIN, self.OTRO_LINUX, *maquina]):
            parche, _ = self._arbol("equipo_ia_v3/eq3", "m.py", f"# visto en {ruta}\nRUTA = {ruta!r}\n")
            with self.subTest(i=i), parche, self.assertRaisesRegex(E.Rechazo, "ruta personal"):
                E.recoger()

    def test_archivos_no_utf8_con_ruta_personal_se_rechazan(self):
        """2026-11-17: un PNG con la ruta en sus metadatos y un registro UTF-16 se colaban (no son UTF-8)."""
        ruta = str(Path.home() / "proyecto" / "escena.blend")
        casos = {"imagen.png": b"\x89PNG\r\n\x1a\n\x00\x00tEXtFile\x00" + ruta.encode("latin-1", "replace") + b"\xff\xfe",
                 "registro.log": ("aviso en " + ruta + "\n").encode("utf-16-le"),
                 "datos.bin": b"\xff\xfe\x00" + ruta.encode("utf-8") + b"\x80"}
        for nombre, datos in casos.items():
            d = _tmp(self) / ("arbol_" + nombre.replace(".", "_"))
            d.mkdir()
            (d / nombre).write_bytes(datos)
            with self.subTest(nombre=nombre), mock.patch.multiple(E, INCLUIR=[("equipo_ia_v3/evidencias", d)], SUELTOS=[]), \
                    self.assertRaisesRegex(E.Rechazo, "ruta personal"):
                E.recoger()

    def test_registro_no_utf8_en_evidencias_se_anonimiza_byte_a_byte(self):
        ruta = str(Path.home() / "proyecto" / "modelo.gguf")
        datos = b"llama: cargando " + ruta.encode("utf-8") + b" \xff\xfe fin\n"
        d = _tmp(self) / "arbol_log"
        d.mkdir()
        (d / "server.log").write_bytes(datos)
        with mock.patch.multiple(E, INCLUIR=[("equipo_ia_v3/evidencias", d)], SUELTOS=[]):
            entradas = E.recoger()                                               # no lanza Rechazo
            nombre = entradas[0][0]
            fuera = E.datos_para_zip(nombre, datos, E.rutas_de_esta_maquina())
        self.assertNotIn(ruta.encode("utf-8"), fuera)
        self.assertTrue(fuera.endswith(b" \xff\xfe fin\n"))                       # el resto, byte a byte
        self.assertEqual((d / "server.log").read_bytes(), datos)                  # el disco no se toca

    def test_binario_sin_rutas_sigue_entrando(self):
        d = _tmp(self) / "arbol_bin"
        d.mkdir()
        (d / "ok.png").write_bytes(b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 4)
        with mock.patch.multiple(E, INCLUIR=[("equipo_ia_v3/evidencias", d)], SUELTOS=[]):
            self.assertEqual(len(E.recoger()), 1)

    def test_rutas_genericas_y_relativas_no_se_rechazan(self):
        texto = ("/" + "home" + "/user/proyecto · C:" + "\\" + "Users" + "\\" + "Public" + "\\x · <CASA>/a · "
                 "sistema/src/eq2 · https://github.com/git-for-windows/git · ~/equipo-ia")
        parche, _ = self._arbol("equipo_ia_v3/eq3", "m.py", texto)
        with parche:
            self.assertEqual(len(E.recoger()), 1)

    def test_registros_se_anonimizan_dentro_del_zip_sin_tocar_el_disco(self):
        casa, trabajo = Path.home() / "AppData" / "x.log", E.REPO.parent / "t" / "l5" / "estados.json"
        texto = (f"nativa {casa} · posix {trabajo.as_posix()} · json {json.dumps(str(trabajo))} · "
                 f"recortada {str(trabajo)[2:]} · traza {self._recortada(trabajo)}\n")
        parche, d = self._arbol("equipo_ia_v3/evidencias", "registro.txt", texto)
        antes = (d / "registro.txt").read_bytes()
        salida = _tmp(self)
        with parche:
            r = E.empaquetar(salida)
        self.assertEqual((d / "registro.txt").read_bytes(), antes)               # el original no cambia
        with zipfile.ZipFile(r["zip"]) as z:
            dentro = z.read(f"{E.PREFIJO}/equipo_ia_v3/evidencias/registro.txt")
            man = json.loads(z.read(f"{E.PREFIJO}/MANIFIESTO_SHA256.json"))
        t = dentro.decode("utf-8")
        self.assertIsNone(E.ruta_personal(t, E.rutas_de_esta_maquina()))
        self.assertIn("<CASA>", t)
        self.assertEqual((t.count("<CASA>"), t.count("<TRABAJO>")), (1, 4))
        self.assertEqual(man["equipo_ia_v3/evidencias/registro.txt"], hashlib.sha256(dentro).hexdigest())

    def test_en_registros_se_anonimiza_cualquier_carpeta_personal(self):
        # También la de otro usuario (o la real, cuando la carpeta personal del proceso está redirigida).
        recortada = "\\" + "Users" + "\\" + "maria" + "\\" + "AppData" + "\\x"
        parche, d = self._arbol("equipo_ia_v3/docs", "nota.md",
                                f"{self.OTRO_WIN} · {self.OTRO_LINUX} · {json.dumps(self.OTRO_WIN)} · {recortada}\n")
        with parche:
            (nombre, p), = E.recoger()
        t = E.datos_para_zip(nombre, p.read_bytes(), E.rutas_de_esta_maquina()).decode("utf-8")
        self.assertNotIn("maria", t)
        self.assertEqual(t.count("<CASA>"), 4)
        self.assertIn("<CASA>\\proyecto\\a.py", t)                               # el resto de la ruta se conserva
        with mock.patch.object(E, "ANONIMIZABLES", ()), parche, self.assertRaisesRegex(E.Rechazo, "ruta personal"):
            E.recoger()                                                          # fuera de registros: se rechaza

    def test_el_arbol_real_se_empaqueta_sin_rutas_personales(self):
        pares = E.rutas_de_esta_maquina()
        for nombre, p in E.recoger():                                            # no lanza Rechazo
            try:
                texto = E.datos_para_zip(nombre, p.read_bytes(), pares).decode("utf-8")
            except UnicodeDecodeError:
                continue
            self.assertIsNone(E.ruta_personal(texto, pares), nombre)


class TestZip(unittest.TestCase):
    def test_reproducible_manifiesto_y_extraccion_segura(self):
        t = _tmp(self)
        a, b = t / "a", t / "b"
        a.mkdir()
        b.mkdir()
        ra, rb = E.empaquetar(a), E.empaquetar(b)
        self.assertEqual(ra["sha256"], rb["sha256"])                          # mismo contenido → mismo ZIP
        self.assertEqual((a / f"{E.PREFIJO}.zip.sha256").read_text().split()[0], ra["sha256"])
        with zipfile.ZipFile(ra["zip"]) as z:
            import json
            man = json.loads(z.read(f"{E.PREFIJO}/MANIFIESTO_SHA256.json"))
            n = "equipo_ia_v3/eq3/traza.py"
            self.assertEqual(man[n], hashlib.sha256(z.read(f"{E.PREFIJO}/{n}")).hexdigest())
        malo = t / "malo.zip"
        with zipfile.ZipFile(malo, "w") as z:
            z.writestr("../fuera.txt", "x")
        with self.assertRaisesRegex(E.Rechazo, "insegura"):
            E.extraer_seguro(malo, t / "x")
        self.assertFalse((t / "fuera.txt").exists())


if __name__ == "__main__":
    unittest.main()
