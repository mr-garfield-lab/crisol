"""Pruebas de la Etapa 3: programación controlada (propuesta → autorización → aplicación).

Ejecutar desde equipo_ia_v3/:   python3 -B -m unittest discover -s pruebas -t pruebas -v
"""
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import comun
from eq3 import cambios as C, ingesta as I, traza as T

CODIGO = "def doble(x):\n    return 2 * x\n"


class Base(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory(prefix="eq3_c_", dir=os.environ.get("TMPDIR"))
        self.addCleanup(d.cleanup)
        self.lab = Path(d.name) / "lab"
        self.lab.mkdir()
        self.hora = [datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)]
        self.c = C.Controlador(self.lab, reloj=lambda: self.hora[0])
        self.addCleanup(self.c.cerrar)

    def proponer(self, contenido=CODIGO, archivo="calc.py", agente="A1"):
        r = self.c.solicitar("demo", {"agente": agente, "herramienta": "proponer",
                                      "args": {"archivo": archivo, "contenido": contenido, "motivo": "prueba"}})
        self.assertEqual(r["estado"], "propuesta", r)
        return r

    def autorizar_y_aplicar(self, r, **kw):
        self.c.autorizar(r["id"], r["sha256_despues"][:12], **kw)
        return self.c.aplicar(r["id"])

    def rechazado(self, fn, *args, motivo, **kw):
        with self.assertRaisesRegex(C.ErrorCambio, motivo):
            fn(*args, **kw)


class TestSeparacion(Base):
    def test_ningun_agente_puede_autorizar_aplicar_ni_ejecutar(self):
        self.assertEqual(set(C.REGISTRO), {"leer", "listar", "buscar", "proponer", "ejecutar_pruebas"})
        self.assertTrue(all(h.efecto in ("lectura", "propuesta", "ninguno") for h in C.REGISTRO.values()))
        for herramienta in ("autorizar", "aplicar", "escribir", "ejecutar"):
            r = self.c.solicitar("demo", {"agente": "A1", "herramienta": herramienta, "args": {}})
            self.assertEqual(r["categoria"], "herramienta_desconocida", herramienta)
        with self.assertRaises(TypeError):
            C.REGISTRO["aplicar"] = C.REGISTRO["leer"]                      # registro inmutable
        self.assertEqual(self.c.solicitar("demo", {"agente": "A2", "herramienta": "ejecutar_pruebas", "args": {}})
                         ["estado"], "no_disponible")                         # SEG-01

    def test_permisos_y_validacion_de_solicitudes(self):
        mal = [({"agente": "A3", "herramienta": "proponer", "args": {"archivo": "x.py", "contenido": "", "motivo": ""}},
                "agente_no_permitido"),
               ({"agente": "A1", "herramienta": "leer", "args": {"ruta": 5}}, "argumentos"),
               ({"agente": "A1", "herramienta": "leer", "args": {"ruta": "a", "extra": "b"}}, "argumentos"),
               ({"agente": "A1", "herramienta": "leer"}, "formato"),
               ("no es un diccionario", "formato"),
               ({"agente": "A1", "herramienta": "leer", "args": {"ruta": "../../cambios_v3.sqlite3"}}, "validacion"),
               ({"agente": "A1", "herramienta": "proponer",
                 "args": {"archivo": "../fuera.py", "contenido": "x = 1\n", "motivo": "m"}}, "validacion"),
               ({"agente": "A1", "herramienta": "proponer",
                 "args": {"archivo": "notas.sh", "contenido": "rm -rf /\n", "motivo": "m"}}, "validacion")]
        for solicitud, categoria in mal:
            with self.subTest(solicitud=solicitud):
                self.assertEqual(self.c.solicitar("demo", solicitud)["categoria"], categoria)
        self.assertEqual(self.c.cambios.filas("propuestas"), [])

    def test_primera_capa_de_rutas(self):
        # Hay dos capas (esta y la de eq3.ingesta.leer); cada una se prueba por separado.
        for mala in ("../x.py", "/etc/x.py", "a/../../x.py", ".oculto/x.py", "a\\b.py", "",
                     "C:/Windows/x.py", "C:x.py", "a/b:flujo.py"):              # letra de unidad y flujos NTFS
            with self.subTest(ruta=mala), self.assertRaises(C.ErrorCambio):
                C._rel_segura(mala)
        self.assertEqual(C._rel_segura("paquete/modulo.py"), "paquete/modulo.py")

    def test_leer_listar_y_buscar_solo_dentro_del_proyecto(self):
        self.autorizar_y_aplicar(self.proponer())
        r = self.c.solicitar("demo", {"agente": "A3", "herramienta": "leer", "args": {"ruta": "calc.py"}})
        self.assertEqual(r["contenido"], CODIGO)
        r = self.c.solicitar("demo", {"agente": "A2", "herramienta": "listar", "args": {"ruta": ""}})
        self.assertEqual(r["entradas"], ["calc.py"])
        r = self.c.solicitar("demo", {"agente": "A2", "herramienta": "buscar", "args": {"consulta": "doble"}})
        self.assertEqual(r["resultados"][0]["ruta"], "calc.py")
        # 2026-11-18 (revisión de seguridad): «listar» no puede salir del proyecto con una letra de unidad
        for fuera in ("C:/Windows", "C:", "D:/"):
            with self.subTest(ruta=fuera):
                r = self.c.solicitar("demo", {"agente": "A2", "herramienta": "listar", "args": {"ruta": fuera}})
                self.assertNotEqual(r["estado"], "ok", r)
                self.assertNotIn("entradas", r)


class TestFlujo(Base):
    def test_propuesta_autorizacion_aplicacion_y_verificacion(self):
        r = self.proponer()
        destino = self.lab / "proyectos_v3/demo/calc.py"
        self.assertFalse(destino.exists())                                   # proponer no escribe nada
        self.rechazado(self.c.aplicar, r["id"], motivo="sin autorización")
        self.rechazado(self.c.autorizar, r["id"], "0" * 12, motivo="confirmación incorrecta")
        self.rechazado(self.c.autorizar, r["id"], r["sha256_despues"][:6], motivo="confirmación incorrecta")
        self.c.autorizar(r["id"], r["sha256_despues"][:12])
        self.assertEqual(self.c.aplicar(r["id"])["sha256"], r["sha256_despues"])
        self.assertEqual(destino.read_text(encoding="utf-8"), CODIGO)
        self.rechazado(self.c.aplicar, r["id"], motivo="un solo uso")
        self.rechazado(self.c.autorizar, r["id"], r["sha256_despues"][:12], motivo="ya tiene una autorización")
        self.assertEqual(self.c.verificar(), [])
        self.assertEqual(len(self.c.cambios.filas("rechazos")), 5)           # cada rechazo queda registrado

    def test_toctou_el_archivo_cambio_desde_la_propuesta(self):
        self.autorizar_y_aplicar(self.proponer())
        r = self.proponer(CODIGO + "\n\ndef triple(x):\n    return 3 * x\n")
        (self.lab / "proyectos_v3/demo/calc.py").write_text("def doble(x):\n    return x + x\n", encoding="utf-8")
        self.c.autorizar(r["id"], r["sha256_despues"][:12])
        self.rechazado(self.c.aplicar, r["id"], motivo="TOCTOU")
        self.assertIn("x + x", (self.lab / "proyectos_v3/demo/calc.py").read_text(encoding="utf-8"))
        self.assertTrue(any("FUERA del flujo" in p for p in self.c.verificar()))

    def test_caducidad(self):
        r = self.proponer()
        self.c.autorizar(r["id"], r["sha256_despues"][:12], minutos=5)
        self.hora[0] += timedelta(minutes=6)
        self.rechazado(self.c.aplicar, r["id"], motivo="caducada")
        self.assertFalse((self.lab / "proyectos_v3/demo/calc.py").exists())

    def test_sintaxis_invalida_no_se_puede_autorizar(self):
        r = self.proponer("def roto(:\n")
        self.assertFalse(r["autorizable"])
        self.rechazado(self.c.autorizar, r["id"], r["sha256_despues"][:12], motivo="errores de sintaxis")

    def test_avisos_de_riesgo_exigen_aceptacion_explicita(self):
        r = self.proponer("import subprocess\n\ndef f():\n    return subprocess.run(['ls'])\n")
        self.assertTrue(r["avisos"])
        self.rechazado(self.c.autorizar, r["id"], r["sha256_despues"][:12], motivo="avisos de riesgo")
        self.c.autorizar(r["id"], r["sha256_despues"][:12], acepto_avisos=True)
        self.assertEqual(self.c.aplicar(r["id"])["estado"], "aplicada")      # se escribe; NO se ejecuta nunca

    def test_enlace_simbolico_en_el_proyecto_rechazado(self):
        self.c.proyecto("demo")
        fuera = self.lab.parent / "fuera.py"
        fuera.write_text("x = 1\n", encoding="utf-8")
        comun.enlazar_o_omitir(self, self.lab / "proyectos_v3/demo/calc.py", fuera)
        r = self.c.solicitar("demo", {"agente": "A1", "herramienta": "proponer",
                                      "args": {"archivo": "calc.py", "contenido": CODIGO, "motivo": "m"}})
        self.assertEqual(r["categoria"], "validacion")
        self.assertEqual(fuera.read_text(encoding="utf-8"), "x = 1\n")

    def test_carpeta_enlazada_en_el_proyecto_rechazada(self):
        # Una carpeta enlazada (symlink; en Windows sin privilegio, una UNIÓN) haría escribir fuera del laboratorio.
        self.c.proyecto("demo")
        fuera = self.lab.parent / "fuera"
        fuera.mkdir()
        comun.enlazar_o_omitir(self, self.lab / "proyectos_v3/demo/pkg", fuera)
        for h, args in (("proponer", {"archivo": "pkg/calc.py", "contenido": CODIGO, "motivo": "m"}),
                        ("leer", {"ruta": "pkg/calc.py"}), ("listar", {"ruta": "pkg"})):
            with self.subTest(herramienta=h):
                r = self.c.solicitar("demo", {"agente": "A1" if h == "proponer" else "A2", "herramienta": h,
                                              "args": args})
                self.assertEqual(r["categoria"], "validacion", r)
        self.assertEqual(list(fuera.iterdir()), [])
        self.assertNotIn("pkg/", self.c.solicitar("demo", {"agente": "A2", "herramienta": "listar",
                                                           "args": {"ruta": ""}})["entradas"])

    def test_union_de_windows_como_proyecto_rechazada(self):
        fuera = self.lab.parent / "fuera_union"
        fuera.mkdir()
        (self.lab / "proyectos_v3").mkdir()
        comun.union_o_omitir(self, self.lab / "proyectos_v3/demo", fuera)
        r = self.c.solicitar("demo", {"agente": "A1", "herramienta": "proponer",
                                      "args": {"archivo": "calc.py", "contenido": CODIGO, "motivo": "m"}})
        self.assertEqual(r["categoria"], "validacion", r)
        self.assertEqual(list(fuera.iterdir()), [])

    def test_el_almacen_solo_admite_anadir(self):
        r = self.proponer()
        self.rechazado(self.c.aplicar, r["id"], motivo="sin autorización")    # deja una fila en `rechazos`
        # Los disparadores de SQLite actúan por fila: cada tabla atacada debe tener filas.
        for sql in ("UPDATE propuestas SET contenido = 'import os'", "DELETE FROM rechazos",
                    "INSERT INTO autorizaciones VALUES ('x', 'PROP-0001', 'A1', 'h', 0, 'c', 't')"):
            with self.subTest(sql=sql), self.assertRaises(sqlite3.IntegrityError):
                self.c.cambios.con.execute(sql)                               # el último: solo actor 'usuario'
        con = sqlite3.connect(self.lab / "cambios_v3.sqlite3")
        con.execute("DROP TRIGGER no_update_propuestas")
        con.execute("UPDATE propuestas SET contenido = 'import os' WHERE id = ?", (r["id"],))
        con.commit()
        con.close()
        self.assertTrue(any("contenido distinto del registrado" in p for p in self.c.verificar()))


class TestDesdeLaTraza(unittest.TestCase):
    def test_version_recomendada_de_una_ejecucion_real_hasta_el_proyecto(self):
        d = tempfile.TemporaryDirectory(prefix="eq3_ct_", dir=os.environ.get("TMPDIR"))
        self.addCleanup(d.cleanup)
        lab = comun.demo(Path(d.name) / "demo")
        with T.Traza(lab / "traza_v3.sqlite3") as t, C.Controlador(lab) as c:
            I.importar_tarea(t, lab, "LAB-001")
            v3 = [x for x in t.filas("cambios", ejecucion_id="LAB-001/E001") if x["version"] == 3][0]
            r = C.proponer_desde_traza(c, t, "LAB-001/E001", "demo", "mediana.py")
            self.assertEqual(r["sha256_despues"], v3["sha256_despues"])          # el mismo código que en la traza
            p = c.cambios.filas("propuestas", id=r["id"])[0]
            self.assertEqual((p["agente"], p["origen"]), ("A1", "traza:LAB-001/E001:v3"))
            c.autorizar(r["id"], r["sha256_despues"][:12])
            c.aplicar(r["id"])
            self.assertEqual(c.verificar(), [])
            (lab / v3["ruta"]).write_text("alterado", encoding="utf-8")
            with self.assertRaisesRegex(C.ErrorCambio, "no coincide con la traza"):
                C.proponer_desde_traza(c, t, "LAB-001/E001", "demo", "otra.py")


if __name__ == "__main__":
    unittest.main()
