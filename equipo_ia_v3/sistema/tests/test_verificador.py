"""V2-E.5-r3: pruebas del PROPIO verificador integral (verificar.py), incluido un fallo controlado.

Para no entrar en recursión, estas pruebas ejecutan el verificador solo con subconjuntos que no lanzan
grupos de pruebas unitarias (--solo V-INT, V-CON-01, V-CON-02, V-EST-03...)."""
import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

import _comun
from test_v2e5r3 import DATOS, manifiesto, zip_bytes

RAIZ = _comun.RAIZ
VER = RAIZ / "verificar.py"


def cargar_verificar():
    spec = importlib.util.spec_from_file_location("verificar_mod", str(VER))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = _comun.carpeta_temporal()
        self.addCleanup(self.tmp.cleanup)
        self.t = Path(self.tmp.name)
        self.env = dict(os.environ, HOME=str(self.t), TMPDIR=str(self.t), PYTHONDONTWRITEBYTECODE="1")

    def ver(self, *args, raiz=RAIZ, env=None):
        return subprocess.run([sys.executable, "-B", str(raiz / "verificar.py"), *args], capture_output=True,
                              text=True, timeout=300, env=env or self.env, cwd=raiz)

    def informe(self, salida):
        linea = next(l for l in salida.splitlines() if l.strip().startswith("Informes:"))
        return json.loads(Path(linea.split(":", 1)[1].split("|")[0].strip()).read_text())


class TestVerificador(Base):
    def test_marcas_formato_resumen_y_codigo_de_salida(self):
        r = self.ver("--solo", "V-INT-02", "--solo", "V-INT-03", "--solo", "V-EST-03")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        s = r.stdout
        i, f = s.index("*** INICIO DE GRABACIÓN / PRUEBAS ***"), s.index("*** FIN DE GRABACIÓN / PRUEBAS ***")
        self.assertLess(s.index("Preparando el entorno"), i)                 # preparar antes de grabar
        self.assertLess(i, s.index("[V-INT-02] OK ("))
        self.assertLess(s.index("[V-EST-03] OK ("), f)
        self.assertLess(f, s.index("RESUMEN"))
        for campo in ("Total de pruebas:", "Correctas:", "Fallidas:", "Omitidas:", "No verificadas:",
                      "Duración total:", "Informes:", "ESTADO GENERAL:"):
            self.assertIn(campo, s[f:])
        inf = self.informe(s)
        self.assertEqual(inf["resumen"]["total"], 3)
        self.assertEqual(inf["resumen"]["fallidas"], 0)
        self.assertTrue(inf["parcial"])
        self.assertIn("PARCIAL", inf["estado_general"])
        for x in inf["resultados"]:
            self.assertEqual(set(x) >= {"id", "descripcion", "estado", "duracion_s", "detalle"}, True)

    def test_fallo_controlado(self):
        r = self.ver("--solo", "V-INT-03", "--fallo-controlado")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("[V-AUTO-01] FALLO", r.stdout)
        inf = self.informe(r.stdout)
        self.assertEqual((inf["resumen"]["fallidas"], inf["estado_general"]), (1, "CON FALLOS"))
        auto = next(x for x in inf["resultados"] if x["id"] == "V-AUTO-01")
        self.assertIn("fallo introducido a propósito", Path(auto["traza"]).read_text())   # la traza se conserva

    def test_lista_no_ejecuta_y_sin_tmpdir_no_prepara(self):
        r = self.ver("--lista")
        self.assertEqual(r.returncode, 0)
        self.assertNotIn("INICIO DE GRABACIÓN", r.stdout)
        for area in ("V-INT-01", "V-STOP-", "V-REP-01", "V-QWEN-01", "V-CON-01", "V-LAB-", "V-CRI-", "V-MEM-",
                     "V-SRV-", "V-PROC-", "V-AGT-", "V-MOT-", "V-UNI-", "V-EST-01"):
            self.assertIn(area, r.stdout)
        env = {k: v for k, v in self.env.items() if k != "TMPDIR"}
        self.assertEqual(self.ver("--solo", "V-INT-03", env=env).returncode, 2)
        self.assertEqual(self.ver("--repeticiones", "0").returncode, 2)

    def test_qwen_real_no_se_ejecuta_sin_autorizacion(self):
        r = self.ver("--solo", "V-QWEN")
        self.assertEqual(r.returncode, 0)
        inf = self.informe(r.stdout)
        self.assertEqual({x["estado"] for x in inf["resultados"]}, {"NO_VERIFICADA"})
        self.assertFalse(any(x["real"] for x in inf["resultados"]))
        self.assertIn("Qwen real NO verificado", inf["estado_general"])

    def test_manifiesto_de_integridad(self):
        copia = self.t / "paquete"
        shutil.copytree(RAIZ, copia, ignore=shutil.ignore_patterns("__pycache__", "MANIFIESTO_SHA256.txt"))
        gen = subprocess.run([sys.executable, "-B", str(copia / "verificar.py"), "--generar-manifiesto"],
                             capture_output=True, text=True, timeout=120, env=self.env)
        (copia / "MANIFIESTO_SHA256.txt").write_text(gen.stdout)
        r = self.ver("--solo", "V-INT-01", raiz=copia)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("[V-INT-01] OK", r.stdout)
        cfg = copia / "src" / "eq2" / "config.py"
        cfg.write_text(cfg.read_text().replace("MODO_B_HABILITADO = False", "MODO_B_HABILITADO = True"))
        r = self.ver("--solo", "V-INT-01", raiz=copia)
        self.assertEqual(r.returncode, 1)
        self.assertIn("1 archivos distintos o ausentes", r.stdout)
        r = self.ver("--solo", "V-EST-03", raiz=copia)                       # y la protección lo detecta
        self.assertEqual(r.returncode, 1)
        self.assertIn("MODO_B_HABILITADO", r.stdout)
        (copia / "src" / "eq2" / "rutas.py").write_text("esto no es python (")    # núcleo dañado
        r = self.ver("--solo", "V-INT-03", raiz=copia)
        self.assertEqual(r.returncode, 1)
        for s in ("*** INICIO DE GRABACIÓN / PRUEBAS ***", "[V-INT-00] importar el núcleo eq2 ... FALLO",
                  "[V-INT-01] huellas SHA-256 del manifiesto de la versión ... FALLO", "*** FIN DE GRABACIÓN / PRUEBAS ***"):
            self.assertIn(s, r.stdout)

    def test_repeticiones_cuentan_fallos_intermitentes(self):
        vm = cargar_verificar()
        v = vm.Verificador(argparse.Namespace(), salida=lambda *_: None)
        rc = iter([0, 1, 0, 0, 1])
        v._python = lambda *a, **k: subprocess.CompletedProcess([], next(rc), "", "fallo simulado")
        v._traza = lambda *a: None
        estado, detalle = v.c_repetir({"id": "X", "objetivo": "x", "veces": 5})
        self.assertEqual((estado, detalle), ("FALLO", "2/5 repeticiones fallaron (error intermitente)"))
        v._python = lambda *a, **k: subprocess.CompletedProcess([], 0, "", "")
        self.assertIn("no demuestra ausencia de errores", v.c_repetir({"id": "X", "objetivo": "x", "veces": 3})[1])


class TestPaquetesEnElVerificador(Base):
    def paquete(self, datos=DATOS):
        entrada = self.t / "equipo_f2" / "lab_v2f1" / "auditoria" / "entrada"  # CAMBIO V2-E.6 (V2-E.5-r3: equipo_f2/auditoria)  # CAMBIO V2-E.6-r2 (V2-E.6: lab_v2e6)  # CAMBIO V2-E.6-r3 (V2-E.6-r2: lab_v2e6r2)  # CAMBIO V2-E.7 (V2-E.6-r3: lab_v2e6r3)  # CAMBIO V2-E.7-r2 (V2-E.7: lab_v2e7)  # CAMBIO V2-E.7-r3 (V2-E.7-r2: lab_v2e7r2)  # CAMBIO V2-F (V2-E.7-r3: lab_v2e7r3)  # CAMBIO V2-F.1 (V2-F: lab_v2f)
        entrada.mkdir(parents=True, exist_ok=True)
        z = entrada / "aud.zip"
        z.write_bytes(zip_bytes([("manifiesto.json", manifiesto(datos))] + datos))
        return z

    def test_ejemplo_incluido(self):
        r = self.ver("--solo", "V-CON-01")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("[ejemplo:EJ-06] NO_DISPONIBLE", r.stdout)

    def test_paquete_externo_solo_con_autorizacion_del_usuario(self):
        z = self.paquete()
        r = self.ver("--solo", "V-CON-02")
        self.assertIn("NO AUTORIZADO", r.stdout)
        self.assertIn("[V-CON-02] OMITIDA", r.stdout)
        a = self.ver("--autorizar-paquete", str(z))
        self.assertEqual(a.returncode, 0, a.stdout)
        self.assertIn("NO garantiza que el contenido sea seguro", a.stdout)
        r = self.ver("--solo", "V-CON-02")
        self.assertIn("[AUD-PRUEBA-1:P1] OK", r.stdout)
        self.assertIn("[V-CON-02] OK", r.stdout)
        reg = [json.loads(l) for l in (self.t / "equipo_f2" / "lab_v2f1" / "auditoria" / "registro.jsonl").read_text().splitlines()]  # CAMBIO V2-E.6  # CAMBIO V2-E.6-r2 (V2-E.6: lab_v2e6)  # CAMBIO V2-E.6-r3 (V2-E.6-r2: lab_v2e6r2)  # CAMBIO V2-E.7 (V2-E.6-r3: lab_v2e6r3)  # CAMBIO V2-E.7-r2 (V2-E.7: lab_v2e7)  # CAMBIO V2-E.7-r3 (V2-E.7-r2: lab_v2e7r2)  # CAMBIO V2-F (V2-E.7-r3: lab_v2e7r3)  # CAMBIO V2-F.1 (V2-F: lab_v2f)
        self.assertEqual([x["estado"] for x in reg], ["no_autorizado", "autorizado_por_el_usuario", "ejecutado"])
        otros = [("datos/p.json", json.dumps([{"motivo": "senal", "es_parada": True}]).encode())]
        z.write_bytes(zip_bytes([("manifiesto.json", manifiesto(otros))] + otros))   # cambiado tras autorizarlo
        r = self.ver("--solo", "V-CON-02")
        self.assertNotIn("[AUD-PRUEBA-1:P1] OK", r.stdout)
        self.assertIn("NO AUTORIZADO", r.stdout)                             # la autorización era de otro SHA-256

    def test_paquete_autorizado_con_criterio_incumplido_es_fallo(self):
        datos = [("datos/p.json", json.dumps([{"motivo": "servidor_muerto", "es_parada": True}]).encode())]
        z = self.paquete(datos)
        self.ver("--autorizar-paquete", str(z))
        r = self.ver("--solo", "V-CON-02")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("[AUD-PRUEBA-1:P1] FALLO", r.stdout)

    def test_paquete_peligroso_se_rechaza_y_no_se_puede_autorizar(self):
        entrada = self.t / "equipo_f2" / "lab_v2f1" / "auditoria" / "entrada"  # CAMBIO V2-E.6 (V2-E.5-r3: equipo_f2/auditoria)  # CAMBIO V2-E.6-r2 (V2-E.6: lab_v2e6)  # CAMBIO V2-E.6-r3 (V2-E.6-r2: lab_v2e6r2)  # CAMBIO V2-E.7 (V2-E.6-r3: lab_v2e6r3)  # CAMBIO V2-E.7-r2 (V2-E.7: lab_v2e7)  # CAMBIO V2-E.7-r3 (V2-E.7-r2: lab_v2e7r2)  # CAMBIO V2-F (V2-E.7-r3: lab_v2e7r3)  # CAMBIO V2-F.1 (V2-F: lab_v2f)
        entrada.mkdir(parents=True)
        z = entrada / "malo.zip"
        z.write_bytes(zip_bytes([("manifiesto.json", manifiesto(DATOS)), ("../fuera.json", b"{}")]))
        r = self.ver("--solo", "V-CON-02")
        self.assertIn("RECHAZADO", r.stdout)
        self.assertEqual(self.ver("--autorizar-paquete", str(z)).returncode, 1)
        self.assertFalse((self.t / "equipo_f2" / "fuera.json").exists())


if __name__ == "__main__":
    unittest.main()


class TestVerificadorV2E6(Base):
    """V2-E.6: fases con INICIO/FIN, naturaleza REAL/SIMULADA, registro de terminal, eventos JSON con métricas,
    demostraciones, semillas y cumplimiento."""

    def test_fases_naturaleza_registros_y_metricas(self):
        r = self.ver("--solo", "V-INT-02", "--solo", "V-EST-03", "--solo", "V-CTX-01", "--solo", "V-ZOM-01",
                     "--semilla", "7")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        s = r.stdout
        for fase in ("INT", "EST", "CTX", "ZOM"):
            self.assertRegex(s, rf"===== INICIO FASE \d+/4 · {fase} — ")
            self.assertRegex(s, rf"===== FIN FASE \d+/4 · {fase} — .* · \d+\.\d\d s =====")
        self.assertLess(s.index("INICIO FASE 1/4 · INT"), s.index("[V-INT-02] OK ("))
        self.assertIn("[V-INT-02] OK (", s)
        self.assertRegex(s, r"\[V-INT-02\] OK \(\d+\.\d\d s\) \[REAL\]")
        self.assertRegex(s, r"\[V-CTX-01\] OK \(\d+\.\d\d s\) \[SIMULADA\]")
        inf = self.informe(s)
        self.assertEqual(inf["semillas"], {"fijas": [11, 42, 2026], "opcional": 7})
        self.assertEqual([f["fase"] for f in inf["fases"]], ["INT", "EST", "CTX", "ZOM"])
        x = inf["resultados"][0]
        self.assertIn("naturaleza", x)
        self.assertIn("cpu_hijos_s", x["metricas"])
        carpeta = Path(inf["carpeta"])
        log = (carpeta / "terminal.log").read_text()
        self.assertIn("INICIO DE GRABACIÓN", log)
        self.assertIn("Preparando el entorno", log)
        self.assertIn("ESTADO GENERAL", log)
        ev = [json.loads(l) for l in (carpeta / "eventos.jsonl").read_text().splitlines()]
        tipos = {e["tipo"] for e in ev}
        self.assertTrue({"inicio_verificacion", "inicio_fase", "inicio", "fin", "fin_fase"} <= tipos)
        fin = next(e for e in ev if e["tipo"] == "fin")
        self.assertIn("mem_disponible_kB", fin["metricas"])

    def test_lista_por_fases_y_demos(self):
        r = self.ver("--lista")
        for fase in ("FASE CTX", "FASE APR", "FASE VAR", "FASE ZOM", "FASE DEMO", "FASE CUM", "FASE CIE", "FASE QWEN"):
            self.assertIn(fase, r.stdout)
        self.assertLess(r.stdout.index("FASE CIE"), r.stdout.index("FASE QWEN"))      # Qwen, lo último
        d = self.ver("--lista-demos")
        self.assertEqual(d.returncode, 0)
        for n in ("aprendizaje_pre_post", "reto_simulado", "pruebas_variables", "tarea_simulada"):
            self.assertIn(n, d.stdout)
        self.assertNotIn("INICIO DE GRABACIÓN", d.stdout)

    def test_una_demo_y_cumplimiento_estatico(self):
        r = self.ver("--solo", "V-DEMO-03", "--solo", "V-CUM-01", "--solo", "V-CUM-02")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("[V-DEMO-03] OK", r.stdout)
        inf = self.informe(r.stdout)
        self.assertTrue((Path(inf["carpeta"]) / "demos" / "reto_referencias.txt").is_file())
        self.assertTrue((Path(inf["carpeta"]) / "diff_r3.json").is_file())

    def test_resultado_por_requisito(self):
        vm = cargar_verificar()
        v = vm.Verificador(argparse.Namespace(), salida=lambda *_: None)

        class Lab:
            def crear_exclusivo(self, *a):
                pass
        v.lab, v.id_ejec = Lab(), "x"
        v._cumplimiento = lambda: {"requisitos": [
            {"id": "R1", "requisito": "a", "pruebas": ["m.C"]},
            {"id": "R2", "requisito": "b", "pruebas": ["m.D"]},
            {"id": "R3", "requisito": "c", "pruebas": ["m.C"], "no_verificable": "parte real sin ejecutar"},
            {"id": "R4", "requisito": "d", "pruebas": ["m.E"]}]}
        v.resultados = [{"id": "V1", "objetivo": "m.C", "estado": "OK"}, {"id": "V2", "objetivo": "m.D", "estado": "FALLO"}]
        estado, det = v.c_cumplimiento_resultado({"id": "V-CUM-03"})
        self.assertEqual(estado, "FALLO")
        for t in ("1 FALLO", "1 OK,", "1 OK PARCIAL", "1 NO VERIFICADA"):
            self.assertIn(t, det)

    def test_qwen_reto_no_se_ejecuta_sin_autorizacion(self):
        r = self.ver("--solo", "V-QWEN-03")
        self.assertIn("[V-QWEN-03] NO_VERIFICADA", r.stdout)
        self.assertIn("[NO VERIFICADA]", r.stdout)
