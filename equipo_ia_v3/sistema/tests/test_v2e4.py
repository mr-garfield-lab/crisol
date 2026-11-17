"""V2-E.4: ciclo completo de investigación de incidencias (hipótesis localizadas, experimentos de
reproducción y control, confirmación o reversión, regresión, seguimiento), trazabilidad de las
evidencias, robustez y recuperación, límites de la investigación e interfaz de laboratorios
especializados.

Todo es SIMULADO y local: agentes con guion o BackendSimulado (no es Qwen), ejecutor simulado,
directorios temporales. Ningún experimento ejecuta código: son reglas declarativas sobre el TEXTO de
las versiones. Superar estas pruebas no demuestra que el sistema sea seguro ni que una corrección
funcione: solo comprueba las propiedades enumeradas.
"""
import ast
import json
import os
import sqlite3
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

import _comun
from eq2 import (auditoria, config, contexto_incidencias, ejecutor, incidencias, inferencia, investigacion,
                 laboratorio, motor, motor_incidencias, prioridad, rutas)
from eq2.inferencia import ErrorInferencia
from test_v2e import ejec_sim, guion_proyecto
from test_v2e2 import _Vigia

RAIZ = _comun.RAIZ
Inc = incidencias
T = config.TAREA_V2B
HIP = "DIAGNOSTICO: usar sorted\nHIPOTESIS INC-000001: ARCHIVO pkg/ordenar.py PATRON .sort()"
MUTA = "    xs.sort()\n    return xs"
BIEN = "    return sorted(xs)"


def salida_a1(cuerpo):
    return ("ARCHIVO: pkg/ordenar.py\n```python\ndef ordenar(xs):\n" + cuerpo + "\n```\n"
            "ARCHIVO: tests/test_ordenar.py\n```python\nfrom pkg.ordenar import ordenar\n"
            "def test_no_muta():\n    a = [2, 1]\n    ordenar(a)\n    assert a == [2, 1]\n"
            "def test_ordena():\n    assert ordenar([2, 1]) == [1, 2]\n```\nFIN")


def guion_ciclo(correcciones=(BIEN,), evaluar=HIP, generar=MUTA, revisar=None):
    cola = list(correcciones)

    def g(paso, n, **kw):
        if paso == "planificar":
            return guion_proyecto()(paso, n, **kw)
        if paso == "revisar":
            return revisar(kw) if revisar else guion_proyecto()(paso, n, **kw)
        if paso == "generar":
            return salida_a1(generar)
        if paso == "evaluar":
            return evaluar(n, kw) if callable(evaluar) else evaluar
        return salida_a1(cola.pop(0) if cola else MUTA + f"  # v{n}")
    return g


def ejec_dos_pruebas(i, arch):
    """test_no_muta falla con .sort(); test_ordena falla con reverse=True (efecto secundario)."""
    c = arch.get("pkg/ordenar.py", "")
    pr = {"test_no_muta": "fallo" if ".sort()" in c else "ok", "test_ordena": "fallo" if "reverse=True" in c else "ok"}
    f = sum(v == "fallo" for v in pr.values())
    return {"estado": "fallos" if f else "ok", "pruebas_total": 2, "pruebas_fallidas": f, "salida": "SIMULADO",
            "detalle": {"pruebas": pr}}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = _comun.carpeta_temporal()
        self.addCleanup(self.tmp.cleanup)
        self.t = Path(self.tmp.name)
        self.raiz = self.t / "equipo_f2"
        self.base = self.raiz / "datos_v2e4"
        self.lab = rutas.Laboratorio(self.raiz, self.base)
        self.reg = Inc.RegistroIncidencias(self.lab)
        self.addCleanup(lambda: self.reg.cerrar())

    def reabrir(self):
        self.reg.cerrar()
        self.reg = Inc.RegistroIncidencias(self.lab)

    def correr(self, g, ej=None, **kw):
        return motor.Motor(self.base, motor.AgentesMotorSimulados(g), ej or ejecutor.EjecutorSimulado(ejec_sim),
                           raiz_laboratorio=self.raiz, incidencias=self.reg, **kw).ejecutar(T)

    def n(self, tabla):
        return self.reg.con.execute(f"SELECT count(*) FROM {tabla}").fetchone()[0]   # nombre fijo en las pruebas

    def sql_falla(self, q, args=()):
        with self.assertRaises(sqlite3.IntegrityError), self.reg.con:
            self.reg.con.execute(q, args)


class BaseInv(Base):
    """Investigador con observaciones fabricadas: v1 falla con .sort(); v2 pasa sin él."""
    def setUp(self):
        super().setUp()
        self.inc = self.reg.crear("Prueba simulada test_no_muta falla", "simulacion", 3, 3)
        self.inv = investigacion.Investigador(self.reg, "r1")
        self.v_falla = {"pkg/ordenar.py": "def ordenar(xs):\n    xs.sort()\n    return xs\n"}
        self.v_pasa = {"pkg/ordenar.py": "def ordenar(xs):\n    return sorted(xs)\n"}

    def hip(self, patron=".sort()", archivo="pkg/ordenar.py", inv=None):
        return (inv or self.inv).proponer_desde_texto(
            f"HIPOTESIS {self.inc}: ARCHIVO {archivo} PATRON {patron}", [self.inc], version=1)[0]

    def ver(self, v, cont, presente, inv=None):
        (inv or self.inv).observar(v, cont, {self.inc} if presente else set(), {self.inc})

    def estado(self, hid):
        return self.reg.hipotesis(hid=hid)[0]["estado"]


# ============================ 1. registro: hipótesis, revisiones, inmutabilidad ===============
class TestRegistroV2E4(Base):
    def test_hipotesis_idempotente_validada_y_con_autor(self):
        i = self.reg.crear("x", "c", 3, 3)
        h1, nueva = self.reg.proponer_hipotesis(i, "A2", "t", "a.py", ".sort()", version=2)
        h2, nueva2 = self.reg.proponer_hipotesis(i, "A2", "otro texto", "a.py", ".sort()", version=5)
        self.assertEqual((h1, nueva, h2, nueva2), (h1, True, h1, False))
        h = self.reg.hipotesis(hid=h1)[0]
        self.assertEqual((h["estado"], h["actor"], h["version"]), ("propuesta", "A2", 2))
        for args in (("a.py", "x"), ("", ".sort()"), ("a.py", "  ")):
            with self.subTest(args=args), self.assertRaises(ValueError):
                self.reg.proponer_hipotesis(i, "A2", "t", *args)
        with self.assertRaises(Inc.PermisoDenegado):
            self.reg.proponer_hipotesis(i, "motor", "t", "a.py", "patron")
        self.sql_falla("DELETE FROM hipotesis")
        self.sql_falla("INSERT INTO hipotesis(id,creada,actualizada,incidencia_id,actor,texto,archivo,patron,firma,estado) "
                       "VALUES('HIP-9','t','t',?,'A2','t','a.py','pp','f9','respaldada')", (i,))

    def test_solo_el_laboratorio_cambia_hipotesis_y_respaldada_exige_dos_experimentos(self):
        i = self.reg.crear("x", "c", 3, 3)
        h, _ = self.reg.proponer_hipotesis(i, "A2", "t", "a.py", ".sort()")
        for actor in ("A1", "A2", "A3", "motor", "usuario"):
            with self.assertRaises(Inc.PermisoDenegado):
                self.reg.cambiar_hipotesis(h, "consistente", actor, "x")
        with self.assertRaises(sqlite3.IntegrityError):                # sin experimentos
            self.reg.cambiar_hipotesis(h, "respaldada", "laboratorio", "x")
        lb = laboratorio.Laboratorio(self.reg)
        # CAMBIO V2-E.4-r2: reproducción y control solo con el método canónico (planificar() ya no acepta rol).
        e = lb.planificar_prueba_de_hipotesis(h, "reproduccion", "r", 1, "x.sort()")
        lb.ejecutar(e)
        with self.assertRaises(sqlite3.IntegrityError):                # solo reproducción: no basta
            self.reg.cambiar_hipotesis(h, "respaldada", "laboratorio", "x")
        self.reg.cambiar_hipotesis(h, "refutada", "laboratorio", "x")
        with self.assertRaises(Inc.TransicionInvalida):
            self.reg.cambiar_hipotesis(h, "consistente", "laboratorio", "x")
        self.sql_falla("UPDATE hipotesis SET estado='consistente' WHERE id=?", (h,))

    def test_experimentos_terminados_inmutables_y_revisiones_de_solo_anexar(self):
        i = self.reg.crear("x", "c", 3, 3)
        lb = laboratorio.Laboratorio(self.reg)
        e = lb.planificar("h", "analisis_estatico", {"archivos": {"m.py": "x = 1\n"}}, {"sin_errores": True})
        lb.ejecutar(e)
        self.sql_falla("UPDATE experimentos SET conclusion='apoya' WHERE id=?", (e,))
        self.sql_falla("DELETE FROM experimentos")
        self.assertTrue(self.reg.registrar_revision("r", i, 2, "sin_objeciones", ""))
        self.assertFalse(self.reg.registrar_revision("r", i, 2, "con_objeciones", "otra vez"))   # idempotente
        self.assertEqual(len(self.reg.revisiones(i)), 1)
        self.sql_falla("UPDATE revisiones SET resultado='con_objeciones'")
        self.sql_falla("DELETE FROM revisiones")

    def test_evidencias_con_trazabilidad(self):
        i = self.reg.crear("x", "c", 3, 3)
        n = self.reg.registrar_evidencia(i, "simulacion", "fallida", "d", "laboratorio", hipotesis_id="HIP-000001",
                                         version=3, confianza=0.4, limitaciones="solo simulación")
        e = self.reg.evidencias(i)[0]
        self.assertEqual((e["num"], e["hipotesis_id"], e["version"], e["confianza"], e["limitaciones"]),
                         (n, "HIP-000001", 3, 0.4, "solo simulación"))
        self.assertTrue(e["creada"])
        with self.assertRaises(sqlite3.IntegrityError):
            self.reg.registrar_evidencia(i, "simulacion", "fallida", "d", "laboratorio", confianza=1.5)


# ============================ 2. investigación (unidad) ===================================
class TestInvestigacion(BaseInv):
    def test_parseo_y_rechazo_de_hipotesis_invalidas(self):
        self.assertEqual(investigacion.hipotesis_de("HIPOTESIS inc-000001: ARCHIVO `a/b.py` PATRON 'x.y()'"),
                         [("INC-000001", "a/b.py", "x.y()")])
        txt = (f"HIPOTESIS {self.inc}: ARCHIVO ../etc/passwd PATRON root\n"
               f"HIPOTESIS {self.inc}: ARCHIVO a.py PATRON x\n"
               "HIPOTESIS INC-000099: ARCHIVO a.py PATRON valido\n"
               "texto sin formato\n")
        self.assertEqual(self.inv.proponer_desde_texto(txt, [self.inc]), [])
        self.assertEqual(sorted(r["motivo"] for r in self.inv.rechazadas),
                         ["incidencia no recibida por el agente", "patrón vacío o demasiado largo", "ruta no válida"])
        self.assertEqual(self.reg.hipotesis(self.inc), [])

    def test_hipotesis_sin_evidencia_no_se_confirma(self):
        h = self.hip()
        self.inv.investigar([self.inc])                                # sin observaciones
        self.assertEqual(self.estado(h), "propuesta")
        self.assertEqual(self.n("experimentos"), 0)
        self.assertEqual(self.reg.obtener(self.inc)["causa_estado"], "hipotesis")

    def test_solo_reproduccion_queda_consistente_sin_confirmar(self):
        h = self.hip()
        self.ver(1, self.v_falla, True)
        self.inv.investigar([self.inc])
        i = self.reg.obtener(self.inc)
        self.assertEqual(self.estado(h), "consistente")
        self.assertEqual((i["causa_estado"], Inc.respaldo(i)), ("hipotesis", "sin_causa"))
        self.assertEqual(self.n("regresiones"), 0)

    def test_reproduccion_refuta(self):
        h = self.hip(patron="no_aparece")
        self.reg.actualizar_diagnostico(self.inc, "A2", causa=self.reg.hipotesis(hid=h)[0]["texto"])
        self.ver(1, self.v_falla, True)
        self.inv.investigar([self.inc])
        self.assertEqual(self.estado(h), "refutada")
        self.assertIsNone(self.reg.obtener(self.inc)["causa"])          # la causa refutada se retira
        self.assertFalse(prioridad.contadores(self.reg, self.inc)["diagnostico_vigente"])

    def test_control_refuta_si_el_patron_sigue_donde_ya_no_falla(self):
        h = self.hip(patron="def ordenar")
        self.ver(1, self.v_falla, True)
        self.ver(2, self.v_pasa, False)
        self.inv.investigar([self.inc])
        self.assertEqual(self.estado(h), "refutada")
        self.assertEqual(self.reg.obtener(self.inc)["causa_estado"], "hipotesis")
        self.assertEqual(self.n("regresiones"), 0)

    def test_reproduccion_y_control_respaldan_confirman_y_crean_una_regresion(self):
        h = self.hip()
        self.ver(1, self.v_falla, True)
        self.ver(2, self.v_pasa, False)
        self.inv.investigar([self.inc])
        i = self.reg.obtener(self.inc)
        self.assertEqual(self.estado(h), "respaldada")
        self.assertEqual((i["causa_estado"], i["causa_respaldo"], i["causa_hipotesis"]), ("confirmada", "simulacion", h))
        self.assertEqual(Inc.respaldo(i), "respaldada_simulacion")
        self.assertEqual(self.n("regresiones"), 1)
        ev = [e for e in self.reg.evidencias(self.inc) if e["hipotesis_id"] == h]
        self.assertEqual(len(ev), 2)
        self.assertTrue(all(e["version"] and e["limitaciones"] and e["confianza"] is not None for e in ev))
        antes = (self.n("experimentos"), self.n("evidencias"), self.n("regresiones"))
        for _ in range(3):                                             # reintentos: nada se duplica
            self.inv.investigar([self.inc])
            investigacion.Investigador(self.reg, "otro").investigar([self.inc])
        self.assertEqual((self.n("experimentos"), self.n("evidencias"), self.n("regresiones")), antes)

    def test_hipotesis_contradictorias_quedan_ambiguas_y_pendientes(self):
        h1, h2 = self.hip(".sort()"), self.hip("xs.sort")
        self.ver(1, self.v_falla, True)
        self.ver(2, self.v_pasa, False)
        self.inv.investigar([self.inc])
        self.assertEqual((self.estado(h1), self.estado(h2)), ("ambigua", "ambigua"))
        i = self.reg.obtener(self.inc)
        self.assertEqual(i["causa_estado"], "hipotesis")
        self.assertEqual(self.n("regresiones"), 0)
        # Una versión nueva que falla sin «xs.sort» (pero con «.sort()») deshace el empate.
        self.ver(3, {"pkg/ordenar.py": "def ordenar(ys):\n    ys.sort()\n    return ys\n"}, True)
        self.ver(4, self.v_pasa, False)
        self.inv.investigar([self.inc])
        self.assertEqual((self.estado(h1), self.estado(h2)), ("respaldada", "refutada"))
        self.assertEqual(self.reg.obtener(self.inc)["causa_hipotesis"], h1)

    def test_respaldada_que_luego_se_contradice_vuelve_a_pendiente(self):
        h = self.hip()
        self.ver(1, self.v_falla, True)
        self.ver(2, self.v_pasa, False)
        self.inv.investigar([self.inc])
        self.assertEqual(self.estado(h), "respaldada")
        self.ver(3, {"pkg/ordenar.py": "def ordenar(xs):\n    return list(reversed(xs))\n"}, True)   # falla sin el patrón
        self.inv.investigar([self.inc])
        i = self.reg.obtener(self.inc)
        self.assertEqual(self.estado(h), "refutada")
        self.assertEqual((i["causa_estado"], i["causa"], i["causa_hipotesis"]), ("hipotesis", None, None))
        self.assertEqual(self.inv.seguimiento(3, [self.inc]), [])       # su regresión ya no se aplica

    def test_regresion_de_hipotesis_refutada_deja_de_aplicarse(self):
        h = self.hip()
        self.ver(1, self.v_falla, True)
        self.ver(2, self.v_pasa, False)
        self.inv.investigar([self.inc])
        self.assertEqual(self.n("regresiones"), 1)
        # v3 NO falla pero contiene el patrón: el control la refuta y su regresión ya no se aplica.
        self.ver(3, {"pkg/ordenar.py": "def ordenar(xs):\n    ys = list(xs)\n    ys.sort()\n    return ys\n"}, False)
        self.inv.investigar([self.inc])
        self.assertEqual(self.estado(h), "refutada")
        self.assertEqual(self.inv.seguimiento(3, [self.inc]), [])
        self.assertFalse([e for e in self.reg.evidencias(self.inc) if e["experimento_id"] == "REG-000001"])

    def test_seguimiento_detecta_que_el_patron_vuelve_y_reabre(self):
        self.hip()
        self.ver(1, self.v_falla, True)
        self.ver(2, self.v_pasa, False)
        self.inv.investigar([self.inc])
        for e in ("en_analisis", "asignada", "en_correccion"):
            self.reg.cambiar_estado(self.inc, e, "motor")
        self.reg.registrar_evidencia(self.inc, "simulacion", "superada", "v2 ok", "motor", version=2)
        self.reg.cambiar_estado(self.inc, "corregida_sin_verificar", "motor")
        self.assertEqual(self.inv.seguimiento(2, [self.inc]), [])
        self.ver(3, self.v_falla, False)
        self.assertEqual(self.inv.seguimiento(3, [self.inc]), ["REG-000001"])
        self.inv.seguimiento(3, [self.inc])                            # sin duplicar la evidencia
        self.assertEqual(self.reg.obtener(self.inc)["estado"], "reabierta")
        det = [e for e in self.reg.evidencias(self.inc) if e["experimento_id"] == "REG-000001"]
        self.assertEqual(len(det), 1)
        self.assertEqual((det[0]["resultado"], det[0]["version"]), ("fallida", 3))

    def test_experimento_fallido_no_produce_falsa_correccion(self):
        h = self.hip()
        self.ver(1, self.v_falla, True)
        self.ver(2, self.v_pasa, False)
        with mock.patch.object(laboratorio, "_simular", side_effect=ValueError("regla rota")):
            self.inv.investigar([self.inc])
        exps = self.reg.con.execute("SELECT estado, conclusion FROM experimentos").fetchall()
        self.assertEqual([tuple(x) for x in exps], [("abortado", "no_concluyente")])
        i = self.reg.obtener(self.inc)
        self.assertEqual((self.estado(h), i["estado"], i["causa_estado"]), ("propuesta", "abierta", "hipotesis"))
        self.assertEqual(self.n("regresiones"), 0)
        self.assertTrue(self.reg.historial(self.inc))                    # el historial se conserva

    def test_experimento_interrumpido_se_reanuda_sin_duplicar(self):
        h = self.hip()
        self.ver(1, self.v_falla, True)
        with mock.patch.object(laboratorio.Laboratorio, "ejecutar", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.inv.investigar([self.inc])
        self.assertEqual([tuple(x) for x in self.reg.con.execute("SELECT estado FROM experimentos")], [("planificado",)])
        self.reabrir()
        inv2 = investigacion.Investigador(self.reg, "r2")
        self.ver(1, self.v_falla, True, inv=inv2)
        inv2.investigar([self.inc])
        self.assertEqual([tuple(x) for x in self.reg.con.execute("SELECT id, estado FROM experimentos")],
                         [("EXP-000001", "completado")])
        self.assertEqual(self.estado(h), "consistente")

    def test_interrupcion_entre_evidencia_y_cierre_no_duplica_evidencia(self):
        self.hip()
        self.ver(1, self.v_falla, True)
        with mock.patch.object(laboratorio.Laboratorio, "_cerrar", side_effect=OSError("disco")):
            with self.assertRaises(OSError):
                self.inv.investigar([self.inc])
        self.assertEqual(self.n("evidencias"), 1)
        investigacion.Investigador(self.reg, "r2")
        inv2 = investigacion.Investigador(self.reg, "r2")
        self.ver(1, self.v_falla, True, inv=inv2)
        inv2.investigar([self.inc])
        self.assertEqual(self.n("evidencias"), 1)
        e = self.reg.con.execute("SELECT estado, evidencia_num FROM experimentos").fetchone()
        self.assertEqual(tuple(e), ("completado", 1))

    def test_regresion_doble_y_archivo_perdido(self):
        self.hip()
        self.ver(1, self.v_falla, True)
        self.ver(2, self.v_pasa, False)
        self.inv.investigar([self.inc])
        lb = laboratorio.Laboratorio(self.reg)
        self.assertEqual(lb.crear_regresion("EXP-000001"), "REG-000001")
        self.assertEqual(lb.crear_regresion("EXP-000001"), "REG-000001")
        p = self.base / "incidencias" / "regresiones" / "REG-000001.json"
        sha = self.reg.con.execute("SELECT sha256 FROM regresiones").fetchone()[0]
        p.unlink()                                                     # «el proceso murió antes del archivo»
        self.assertEqual(lb.crear_regresion("EXP-000001"), "REG-000001")
        import hashlib
        self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(), sha)
        self.assertEqual(self.n("regresiones"), 1)
        with self.assertRaises(ValueError):                            # el control no reproduce el fallo
            lb.crear_regresion("EXP-000002")

    def test_limites_de_la_investigacion(self):
        pres = investigacion.PresupuestoInvestigacion(max_experimentos_por_ejecucion=1)
        inv = investigacion.Investigador(self.reg, "r", pres)
        h = self.hip(inv=inv)
        self.ver(1, self.v_falla, True, inv=inv)
        self.ver(2, self.v_pasa, False, inv=inv)
        inv.investigar([self.inc])
        inv.investigar([self.inc])
        self.assertEqual(self.n("experimentos"), 1)
        self.assertEqual(self.estado(h), "consistente")                 # queda pendiente, sin confirmar
        lim = [e for e in self.reg.evidencias(self.inc) if e["tipo"] == "registro"]
        self.assertEqual(len(lim), 1)
        self.assertIn("experimentos por ejecución", lim[0]["descripcion"])
        self.assertIn(f"{self.inc}: experimentos por ejecución", inv.resumen()["limites_alcanzados"])

    def test_limite_de_hipotesis_tiempo_y_regresiones(self):
        inv = investigacion.Investigador(self.reg, "r", investigacion.PresupuestoInvestigacion(
            max_hipotesis_por_incidencia=1, max_regresiones_por_incidencia=0))
        self.hip(".sort()", inv=inv)
        self.assertEqual(inv.proponer_desde_texto(f"HIPOTESIS {self.inc}: ARCHIVO pkg/ordenar.py PATRON xs.sort",
                                                  [self.inc]), [])
        self.assertEqual(inv.rechazadas[-1]["motivo"], "límite de hipótesis por incidencia")
        self.ver(1, self.v_falla, True, inv=inv)
        self.ver(2, self.v_pasa, False, inv=inv)
        inv.investigar([self.inc])
        self.assertEqual(self.n("regresiones"), 0)                      # límite de regresiones = 0
        reloj = [0.0]
        inv_t = investigacion.Investigador(self.reg, "r3", investigacion.PresupuestoInvestigacion(seg_max_investigacion=1),
                                           reloj=lambda: reloj[0])
        inv_t.t_usado = 5.0
        otra = self.reg.crear("otra", "x", 3, 3)
        inv_t.proponer_desde_texto(f"HIPOTESIS {otra}: ARCHIVO pkg/ordenar.py PATRON .sort()", [otra])
        inv_t.observar(1, self.v_falla, {otra}, {otra})
        inv_t.investigar([otra])
        self.assertEqual(self.reg.con.execute("SELECT count(*) FROM experimentos WHERE incidencia_id=?",
                                              (otra,)).fetchone()[0], 0)

    def test_presupuesto_acotado_por_maximos_duros(self):
        p = investigacion.PresupuestoInvestigacion(10 ** 6, 10 ** 6, 10 ** 6, 10 ** 6, 10 ** 9).acotado()
        for k, v in config.INVESTIGACION_MAXIMOS.items():
            self.assertEqual(getattr(p, k), v)
        self.assertEqual(investigacion.PresupuestoInvestigacion(-5, -5, -5, -5, -5).acotado().seg_max_investigacion, 0.0)


# ============================ 3. ficha y etiquetas ========================================
class TestFicha(BaseInv):
    def test_fases_y_etiquetas_dicen_que_se_comprobo(self):
        f = lambda: self.reg.ficha(self.inc)["fase"]
        self.assertEqual(f(), "detectada")
        self.hip()
        self.assertEqual(f(), "causa_hipotetica")
        self.ver(1, self.v_falla, True)
        self.ver(2, self.v_pasa, False)
        self.inv.investigar([self.inc])
        self.assertEqual(f(), "causa_respaldada")
        self.reg.registrar_intento(self.inc, "A1", "corrección", "pendiente", version=2)
        self.assertEqual(f(), "correccion_propuesta")
        self.reg.registrar_revision("r", self.inc, 2, "sin_objeciones", "")
        self.assertEqual(f(), "correccion_revisada")
        for e in ("en_analisis", "asignada", "en_correccion"):
            self.reg.cambiar_estado(self.inc, e, "motor")
        self.reg.registrar_evidencia(self.inc, "simulacion", "superada", "ok", "motor", version=2)
        self.reg.cambiar_estado(self.inc, "corregida_sin_verificar", "motor")
        self.assertEqual(f(), "comprobada_con_pruebas_disponibles")
        et = self.reg.etiqueta(self.inc)
        self.assertIn("comprobada solo con: simulación", et)
        self.assertIn("validación real: pendiente", et)
        self.assertNotIn("verificada con", et)
        self.reg.cambiar_estado(self.inc, "reabierta", "motor")
        self.assertEqual(f(), "causa_respaldada")                       # lo anterior a la reapertura no cuenta
        inf = auditoria.informe(self.reg)
        fila = inf["incidencias"][0]
        self.assertEqual(fila["hipotesis"], {"HIP-000001": "respaldada"})
        self.assertIn("validación real", fila["etiqueta"])
        self.assertEqual(inf["hipotesis_por_estado"]["respaldada"], 1)


# ============================ 4. integración con el motor ===================================
class TestCicloMotor(Base):
    def test_ciclo_completo_automatico(self):
        vistos = []

        def g(paso, n, **kw):
            vistos.append((paso, kw.get("incidencias") or ""))
            return guion_ciclo()(paso, n, **kw)
        inf = self.correr(g)
        self.assertEqual(inf["estado_final"], "criterios_superados_en_simulacion", inf["errores"])
        self.assertEqual(inf["resultado"], "no_verificado")
        i = self.reg.obtener("INC-000001")
        h = self.reg.hipotesis("INC-000001")
        self.assertEqual([x["estado"] for x in h], ["respaldada"])
        self.assertEqual((i["estado"], i["causa_respaldo"], i["causa_hipotesis"]),
                         ("corregida_sin_verificar", "simulacion", h[0]["id"]))
        self.assertEqual(self.n("regresiones"), 1)
        self.assertEqual([x["rol"] for x in self.reg.con.execute("SELECT rol FROM experimentos ORDER BY num")],
                         ["reproduccion", "control"])
        estados = [x["despues"] for x in self.reg.historial("INC-000001") if x["campo"] == "estado"]
        self.assertEqual(estados, ["en_analisis", "asignada", "en_correccion", "corregida_sin_verificar"])
        corr = next(b for p, b in vistos if p == "corregir")
        self.assertIn("HIP-000001 [consistente (falta control)]", corr)        # A1 recibe la hipótesis
        self.assertIn("EXP-000001", corr)                                        # y la evidencia del experimento
        self.assertIn("tarea revisar_intento", [b for p, b in vistos if p == "revisar"][-1])
        self.assertEqual(self.reg.revisiones("INC-000001")[0]["resultado"], "sin_objeciones")
        ficha = self.reg.ficha("INC-000001")
        self.assertEqual(ficha["fase"], "comprobada_con_pruebas_disponibles")
        self.assertEqual(ficha["correccion"]["validacion_real"], Inc.VALIDACION_REAL_PENDIENTE)
        self.assertIn("comprobada solo con: simulación", inf["incidencias"][0]["etiqueta"])
        acc = inf["incidencias_contexto"]["investigacion"]["acciones"]
        self.assertTrue(any("REG-000001 creada" in a for a in acc))

    def test_hipotesis_sin_diagnostico_tambien_llega_a_A1(self):
        vistos = []

        def g(paso, n, **kw):
            vistos.append((paso, kw.get("incidencias") or ""))
            return guion_ciclo(evaluar="HIPOTESIS INC-000001: ARCHIVO pkg/ordenar.py PATRON .sort()")(paso, n, **kw)
        self.correr(g)
        corr = next(b for p, b in vistos if p == "corregir")
        self.assertIn("tarea corregir_con_hipotesis", corr)
        self.assertIn("HIP-000001", corr)
        self.assertEqual(self.reg.hipotesis("INC-000001")[0]["estado"], "respaldada")

    def test_hipotesis_falsa_de_A2_se_refuta_y_no_se_confirma(self):
        inf = self.correr(guion_ciclo(evaluar="HIPOTESIS INC-000001: ARCHIVO pkg/ordenar.py PATRON reversed("))
        self.assertEqual(inf["estado_final"], "criterios_superados_en_simulacion")
        self.assertEqual([h["estado"] for h in self.reg.hipotesis("INC-000001")], ["refutada"])
        i = self.reg.obtener("INC-000001")
        self.assertNotEqual(i["causa_estado"], "confirmada")
        self.assertEqual(self.n("regresiones"), 0)

    def test_respuestas_vacias_o_invalidas_de_los_agentes(self):
        for evaluar in ("", "   ", "HIPOTESIS INC-000001: ARCHIVO PATRON", "\x00\x01 basura",
                        "HIPOTESIS INC-000001: ARCHIVO /etc/passwd PATRON root"):
            with self.subTest(evaluar=evaluar):
                tmp = _comun.carpeta_temporal()
                self.addCleanup(tmp.cleanup)
                raiz = Path(tmp.name) / "equipo_f2"
                reg = Inc.RegistroIncidencias(rutas.Laboratorio(raiz, raiz / "d"))
                self.addCleanup(reg.cerrar)
                inf = motor.Motor(raiz / "d", motor.AgentesMotorSimulados(guion_ciclo(evaluar=evaluar)),
                                  ejecutor.EjecutorSimulado(ejec_sim), raiz_laboratorio=raiz,
                                  incidencias=reg).ejecutar(T)
                self.assertNotEqual(inf["estado_final"], "error_critico", inf["errores"])
                self.assertEqual(reg.hipotesis(), [])
                self.assertNotEqual(reg.obtener("INC-000001")["causa_estado"], "confirmada")

    def test_correccion_que_arregla_un_fallo_pero_provoca_otro(self):
        inf = self.correr(guion_ciclo(correcciones=("    return sorted(xs, reverse=True)", BIEN)),
                          ejecutor.EjecutorSimulado(ejec_dos_pruebas))
        a = self.reg.obtener("INC-000001")
        b = next(i for i in self.reg.listar() if "test_ordena" in i["titulo"])
        self.assertEqual(a["estado"], "corregida_sin_verificar")
        deps = [d for d in self.reg.dependencias() if d["origen"] == a["id"] and d["destino"] == b["id"]]
        self.assertEqual([(d["tipo"], d["certeza"]) for d in deps], [("relacionada", "hipotesis")])   # sin causalidad
        self.assertTrue(any("relación sin confirmar" in e["descripcion"] for e in self.reg.evidencias(b["id"])))
        self.assertEqual([x["resultado"] for x in self.reg.intentos(a["id"])][0], "supera_simulacion")
        self.assertEqual(inf["estado_final"], "criterios_superados_en_simulacion", inf["errores"])
        self.assertEqual(self.reg.obtener(b["id"])["estado"], "corregida_sin_verificar")

    def test_cambio_de_fallo_no_es_falta_de_progreso_sin_registro(self):
        """Corrección del motor: «C1 falla, C2 pasa» -> «C1 pasa, C2 falla» no es «el mismo fallo»."""
        inf = motor.Motor(self.raiz / "sin_registro", motor.AgentesMotorSimulados(guion_ciclo(
            correcciones=("    return sorted(xs, reverse=True)", BIEN))), ejecutor.EjecutorSimulado(ejec_dos_pruebas),
            raiz_laboratorio=self.raiz).ejecutar(T)
        self.assertEqual(inf["estado_final"], "criterios_superados_en_simulacion", inf["motivo"])
        self.assertEqual(len(inf["versiones"]), 3)
        g = guion_ciclo(correcciones=(MUTA + "  # 1", MUTA + "  # 2"))
        inf = motor.Motor(self.raiz / "sin_registro2", motor.AgentesMotorSimulados(g), ejecutor.EjecutorSimulado(ejec_sim),
                          raiz_laboratorio=self.raiz).ejecutar(T)
        self.assertEqual((inf["estado_final"], inf["motivo"]), ("sin_progreso", "mismo fallo en dos iteraciones consecutivas"))

    def test_sin_solucion_dentro_del_presupuesto(self):
        finales = []
        for _ in range(5):
            inf = self.correr(guion_ciclo(correcciones=()), ejecutor.EjecutorSimulado(
                lambda i, a: {"estado": "fallos", "pruebas_total": 1, "pruebas_fallidas": 1, "salida": f"f{i}",
                              "detalle": {"pruebas": {"test_no_muta": "fallo"}}}))
            finales.append(inf["estado_final"])
        self.assertEqual(finales[-1], "escalado_al_usuario")
        self.assertEqual(len(self.reg.hipotesis("INC-000001")), 1)       # A2 repite: no se duplica
        self.assertLessEqual(self.reg.con.execute("SELECT count(*) FROM experimentos WHERE rol IS NOT NULL")
                             .fetchone()[0], investigacion.PresupuestoInvestigacion().max_experimentos_por_incidencia)
        h = self.reg.hipotesis("INC-000001")[0]
        self.assertEqual(h["estado"], "consistente")                      # nunca hubo versión de control
        self.assertNotEqual(self.reg.obtener("INC-000001")["causa_estado"], "confirmada")
        self.assertIn(self.reg.obtener("INC-000001")["estado"], Inc.PENDIENTES)

    def test_presupuesto_de_investigacion_configurable_desde_el_motor(self):
        inf = self.correr(guion_ciclo(), presupuesto_investigacion=investigacion.PresupuestoInvestigacion(
            max_experimentos_por_ejecucion=1))
        inv = inf["incidencias_contexto"]["investigacion"]
        self.assertEqual(inv["experimentos_en_esta_ejecucion"], 1)
        self.assertTrue(inv["limites_alcanzados"])
        self.assertEqual(self.reg.hipotesis("INC-000001")[0]["estado"], "consistente")
        self.assertNotEqual(self.reg.obtener("INC-000001")["causa_estado"], "confirmada")


# ============================ 5. robustez y recuperación ===================================
class TestRecuperacion(Base):
    def test_reinicio_del_proceso_durante_una_incidencia(self):
        self.correr(guion_ciclo(correcciones=(MUTA + "  # a",)),
                    presupuesto=motor.Presupuesto(max_iteraciones_correccion=1))
        h1 = self.reg.hipotesis("INC-000001")
        self.assertEqual([h["estado"] for h in h1], ["consistente"])
        exps = self.n("experimentos")
        hist = len(self.reg.historial("INC-000001"))
        self.reabrir()                                                   # «el proceso se reinicia»
        self.assertEqual(self.reg.hipotesis("INC-000001"), h1)
        self.assertEqual(len(self.reg.historial("INC-000001")), hist)
        inf = self.correr(guion_ciclo())
        self.assertEqual(inf["estado_final"], "criterios_superados_en_simulacion")
        h2 = self.reg.hipotesis("INC-000001")
        self.assertEqual((len(h2), h2[0]["id"], h2[0]["estado"]), (1, h1[0]["id"], "respaldada"))
        reps = self.reg.con.execute("SELECT count(*) FROM experimentos WHERE rol='reproduccion'").fetchone()[0]
        self.assertEqual(reps, exps)                                     # la reproducción de v1 se reutilizó
        self.assertTrue(self.reg.quick_check())

    def test_sqlite_lleno_a_mitad_de_la_ejecucion(self):
        reg, lleno = self.reg, []

        def g(paso, n, **kw):
            if paso == "corregir" and not lleno:
                pc = reg.con.execute("PRAGMA page_count").fetchone()[0]
                reg.con.execute(f"PRAGMA max_page_count = {int(pc)}")    # la base ya no puede crecer...
                try:
                    for k in range(10_000):                              # ...y se ocupa el hueco que quedaba
                        with reg.con:
                            reg.con.execute("INSERT INTO meta(clave, valor) VALUES(?, ?)", (f"relleno{k}", "x" * 2000))
                except sqlite3.OperationalError as e:
                    lleno.append(str(e))
            return guion_ciclo()(paso, n, **kw)
        inf = self.correr(g)
        self.assertIn("full", lleno[0])                                  # error REAL de SQLite
        self.assertEqual(inf["estado_final"], "criterios_superados_en_simulacion")
        self.reabrir()
        self.assertTrue(self.reg.quick_check())
        self.comprobar_invariantes()

    def comprobar_invariantes(self):
        """Pase lo que pase con las escrituras, nada se afirma sin su evidencia."""
        for i in self.reg.listar():
            evs = self.reg.evidencias(i["id"])
            self.assertNotEqual(i["estado"], "verificada")
            if i["estado"] == "corregida_sin_verificar":
                self.assertTrue(any(e["resultado"] == "superada" and e["tipo"] in Inc.NO_DECLARATIVAS for e in evs))
            if i["causa_estado"] == "confirmada":
                self.assertTrue(any(e["tipo"] == i["causa_respaldo"] for e in evs))
            for h in self.reg.hipotesis(i["id"]):
                if h["estado"] == "respaldada":
                    roles = {r[0] for r in self.reg.con.execute(
                        "SELECT rol FROM experimentos WHERE hipotesis_id=? AND conclusion='apoya'", (h["id"],))}
                    self.assertEqual(roles, {"reproduccion", "control"})
            self.assertTrue(self.reg.historial(i["id"]))

    def test_base_en_solo_lectura_a_mitad_de_la_ejecucion(self):
        reg = self.reg

        def g(paso, n, **kw):
            if paso == "corregir":
                reg.con.execute("PRAGMA query_only = ON")                # toda escritura falla desde aquí
            return guion_ciclo()(paso, n, **kw)
        inf = self.correr(g)
        self.assertEqual(inf["estado_final"], "criterios_superados_en_simulacion")
        self.assertTrue(any(e.startswith("incidencias_desactivadas:") for e in inf["errores"]), inf["errores"])
        self.assertIn("desactivado_por_fallo", inf["incidencias"])
        self.reabrir()
        self.assertTrue(self.reg.quick_check())
        i = self.reg.obtener("INC-000001")
        self.assertIn(i["estado"], Inc.PENDIENTES)                       # no se afirma una corrección
        self.assertNotEqual(i["causa_estado"], "confirmada")
        self.assertEqual(self.n("regresiones"), 0)
        self.assertEqual([h["estado"] for h in self.reg.hipotesis("INC-000001")], ["consistente"])   # se conserva
        self.comprobar_invariantes()

    def test_fallo_de_la_investigacion_no_detiene_la_tarea_ni_el_registro(self):
        with mock.patch.object(laboratorio.Laboratorio, "planificar_prueba_de_hipotesis",   # CAMBIO V2-E.4-r2
                               side_effect=sqlite3.OperationalError("disk I/O")):
            inf = self.correr(guion_ciclo())
        self.assertEqual(inf["estado_final"], "criterios_superados_en_simulacion")
        self.assertIn("disk I/O", inf["incidencias_contexto"]["investigacion"]["fallo"])
        self.assertEqual(self.reg.obtener("INC-000001")["estado"], "corregida_sin_verificar")   # el resto sigue
        self.assertNotEqual(self.reg.obtener("INC-000001")["causa_estado"], "confirmada")

    def test_paquete_incompleto_si_el_modelo_falla(self):
        ll = []

        def h(n, fase, mensajes, max_tokens):
            u = mensajes[-1]["content"]
            paso = next(k for k, v in motor.INSTR.items() if u.startswith(v[:40]))
            ll.append(paso)
            if paso == "corregir":
                raise ErrorInferencia("caida_simulada")
            m = __import__("re").search(r"fuente=archivos\n(.*?)\nDATOS_NO_CONFIABLES>>>", u, __import__("re").S)
            return guion_ciclo()(paso, n, archivos=m.group(1) if m else "")
        with mock.patch.object(config, "CTX", 2048):
            inf = motor.Motor(self.base, motor.AgentesMotorLLM(inferencia.BackendSimulado(h)),
                              ejecutor.EjecutorSimulado(ejec_sim), raiz_laboratorio=self.raiz,
                              incidencias=self.reg).ejecutar(T)
        self.assertEqual(inf["estado_final"], "error_critico")
        self.assertIn("corregir", ll)
        self.assertEqual(self.reg.entregas(agente="A1"), [])            # no consta como entregado
        pend = contexto_incidencias.ColaAgente(self.reg, inf["run_id"], "A1").pendientes(["INC-000001"])
        self.assertTrue(pend["INC-000001"])
        self.assertIn(self.reg.obtener("INC-000001")["estado"], Inc.PENDIENTES)


# ============================ 6. seguridad =================================================
class TestSeguridadV2E4(Base):
    def test_no_ejecuta_codigo_ni_abre_procesos_ni_red(self):
        self.correr(guion_ciclo())                                       # calentamiento (importaciones)
        _Vigia.instalar()
        _Vigia.vistos = []
        _Vigia.activo = True
        try:
            self.correr(guion_ciclo(correcciones=("    return sorted(xs, reverse=True)", BIEN)),
                        ejecutor.EjecutorSimulado(ejec_dos_pruebas))
            self.correr(guion_ciclo(correcciones=()))
        finally:
            _Vigia.activo = False
        self.assertEqual(_Vigia.vistos, [])

    def test_modo_real_desactivado_en_todo_el_codigo(self):
        self.assertFalse(config.MODO_B_HABILITADO)
        for py in sorted((RAIZ / "src" / "eq2").glob("*.py")) + [RAIZ / "auditar.py", RAIZ / "ejecutar_v2.py"]:
            arbol = ast.parse(py.read_text(encoding="utf-8"))
            for nodo in ast.walk(arbol):
                if isinstance(nodo, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
                    objetivos = nodo.targets if isinstance(nodo, ast.Assign) else [nodo.target]
                    for t in objetivos:
                        nombre = t.attr if isinstance(t, ast.Attribute) else getattr(t, "id", None)
                        if nombre == "MODO_B_HABILITADO":
                            self.assertEqual(py.name, "config.py", py)
                            self.assertIs(nodo.value.value, False)
        i = self.reg.crear("x", "c", 3, 3)
        with self.assertRaises(Inc.PermisoDenegado):
            self.reg.registrar_evidencia(i, "prueba_real", "superada", "x", "laboratorio")
        inf = self.correr(guion_ciclo())
        self.assertFalse(inf["pruebas_reales_ejecutadas"])
        self.assertTrue(inf["ejecutor"]["simulado"])
        self.assertFalse(any(e["tipo"] == "prueba_real" for x in self.reg.listar() for e in self.reg.evidencias(x["id"])))
        self.assertEqual(auditoria.informe(self.reg)["resumen"]["verificadas"], 0)

    def test_solo_escribe_en_el_laboratorio(self):
        self.correr(guion_ciclo())
        self.assertEqual([p for p in self.t.rglob("*") if not p.is_relative_to(self.raiz)], [])


# ============================ 7. laboratorios especializados (base de ModLab) ===============
class TestTiposEspecializados(Base):
    def setUp(self):
        super().setUp()
        self.addCleanup(laboratorio.retirar_tipo, "conteo_patrones")

    @staticmethod
    def tipo(**kw):
        def validar(e):
            if not isinstance(e.get("texto"), str):
                raise ValueError("texto")

        def correr(e):                                                 # solo cuenta subcadenas: no ejecuta nada
            n = e["texto"].count(e.get("patron", ""))
            return {"pruebas": {"umbral": "fallo" if n > e.get("max", 0) else "ok"}, "errores": []}
        base = dict(nombre="conteo_patrones", tipo_evidencia="simulacion", validar=validar, correr=correr,
                    especialidad="modlab_ejemplo")
        base.update(kw)
        return laboratorio.TipoExperimento(**base)

    def test_registrar_es_solo_una_declaracion_y_nada_se_ejecuta(self):
        # CAMBIO V2-E.4-r2: antes el tipo se ejecutaba; ahora su código es NO CONFIABLE y nunca se invoca.
        llamadas = []
        t = self.tipo(validar=lambda e: llamadas.append("validar"), correr=lambda e: llamadas.append("correr"))
        laboratorio.registrar_tipo(t)
        i = self.reg.crear("x", "c", 3, 3)
        lb = laboratorio.Laboratorio(self.reg)
        with self.assertRaises(laboratorio.TipoNoEjecutable):
            lb.planificar("h", "conteo_patrones", {"texto": "a a a", "patron": "a", "max": 2},
                          {"prueba_falla": "umbral"}, incidencia_id=i)
        self.assertEqual(llamadas, [])                                   # ni validar ni correr
        self.assertEqual(self.n("experimentos"), 0)
        self.assertEqual(self.reg.evidencias(i), [])
        with self.assertRaises(laboratorio.TipoNoEjecutable):            # defensa en el propio _correr
            lb._correr("conteo_patrones", {}, "EXP-000999")
        self.assertEqual(llamadas, [])
        self.assertIn("NO es un aislamiento de seguridad", laboratorio.TipoExperimento.__doc__)

    def test_tipos_peligrosos_o_mal_formados_se_rechazan(self):
        for kw, exc in (({"ejecuta_codigo": True}, PermissionError), ({"usa_red": True}, PermissionError),
                        ({"tipo_evidencia": "prueba_real"}, PermissionError), ({"nombre": "simulacion"}, ValueError),
                        ({"nombre": "Mal-Nombre"}, ValueError), ({"correr": "no invocable"}, TypeError)):
            with self.subTest(kw=kw), self.assertRaises(exc):
                laboratorio.registrar_tipo(self.tipo(**kw))
        laboratorio.registrar_tipo(self.tipo())
        with self.assertRaises(ValueError):
            laboratorio.registrar_tipo(self.tipo())                    # repetido
        with self.assertRaises(TypeError):
            laboratorio.registrar_tipo({"nombre": "x"})


# ============================ 8. CLI y versión =============================================
class TestCLIV2E4(unittest.TestCase):
    def setUp(self):
        self.tmp = _comun.carpeta_temporal()
        self.addCleanup(self.tmp.cleanup)
        self.t = Path(self.tmp.name)
        (self.t / "home").mkdir()
        (self.t / "tmp").mkdir()
        self.env = dict(os.environ, HOME=str(self.t / "home"), TMPDIR=str(self.t / "tmp"))

    def py(self, *a):
        return subprocess.run([sys.executable, "-B", "-I", str(RAIZ / "auditar.py"), *a], capture_output=True,
                              text=True, timeout=180, env=self.env)

    def test_demo_ciclo_y_consultas(self):
        r = self.py("demo-ciclo")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("TOTALMENTE SIMULADA", r.stdout)
        self.assertIn("HIP-000001 respaldada (simulación)", r.stdout)
        self.assertIn("REG-000001 creada", r.stdout)
        self.assertIn("REG-000001 detecta el patrón", r.stdout)
        self.assertIn("validación real: pendiente", r.stdout)
        self.assertNotIn("Traceback", r.stderr)
        h = self.py("hipotesis")
        self.assertIn("[respaldada]", h.stdout)
        self.assertIn("reproduccion v1: completado / apoya", h.stdout)
        self.assertIn("control v2: completado / apoya", h.stdout)
        v = json.loads(self.py("ver", "INC-000001").stdout)
        self.assertEqual(v["ficha"]["hipotesis"][0]["estado"], "respaldada")
        self.assertEqual(v["incidencia"]["estado"], "reabierta")
        self.assertEqual(self.py("hipotesis", "../x").returncode, 2)
        inf = self.py("informe")
        self.assertEqual(inf.returncode, 0)
        md = next((self.t / "tmp" / "equipo_f2" / "lab_v2f1" / "incidencias" / "informes").glob("*.md")).read_text()  # CAMBIO V2-E.6 (V2-E.5-r3: datos_v2e5r3)  # CAMBIO V2-E.6-r2 (V2-E.6: lab_v2e6)  # CAMBIO V2-E.6-r3 (V2-E.6-r2: lab_v2e6r2)  # CAMBIO V2-E.7 (V2-E.6-r3: lab_v2e6r3)  # CAMBIO V2-E.7-r2 (V2-E.7: lab_v2e7)  # CAMBIO V2-E.7-r3 (V2-E.7-r2: lab_v2e7r2)  # CAMBIO V2-F (V2-E.7-r3: lab_v2e7r3)  # CAMBIO V2-F.1 (V2-F: lab_v2f)
        self.assertIn("Qué se comprobó realmente", md)
        self.assertEqual(sorted(p.name for p in (self.t / "tmp" / "equipo_f2").iterdir()), ["lab_v2f1"])  # CAMBIO V2-E.6 (V2-E.5-r3: datos_v2e5r3)  # CAMBIO V2-E.6-r2 (V2-E.6: lab_v2e6)  # CAMBIO V2-E.6-r3 (V2-E.6-r2: lab_v2e6r2)  # CAMBIO V2-E.7 (V2-E.6-r3: lab_v2e6r3)  # CAMBIO V2-E.7-r2 (V2-E.7: lab_v2e7)  # CAMBIO V2-E.7-r3 (V2-E.7-r2: lab_v2e7r2)  # CAMBIO V2-F (V2-E.7-r3: lab_v2e7r3)  # CAMBIO V2-F.1 (V2-F: lab_v2f)
        self.assertEqual(list((self.t / "home").iterdir()), [])


class TestVersionV2E4(unittest.TestCase):
    def test_version_esquema_y_carpetas(self):
        import eq2
        self.assertEqual(eq2.VERSION, "f2-v2f1")  # CAMBIO V2-E.6 (V2-E.5-r3: f2-v2e5-r3)  # CAMBIO V2-E.6-r2 (V2-E.6: f2-v2e6-r1)  # CAMBIO V2-E.6-r3 (V2-E.6-r2: f2-v2e6-r2)  # CAMBIO V2-E.7 (V2-E.6-r3: f2-v2e6-r3)  # CAMBIO V2-E.7-r2 (V2-E.7: f2-v2e7-r1)  # CAMBIO V2-E.7-r3 (V2-E.7-r2: f2-v2e7-r2)  # CAMBIO V2-F (V2-E.7-r3: f2-v2e7-r3)  # CAMBIO V2-F.1 (V2-F: f2-v2f)
        self.assertEqual(Inc.ESQUEMA_INCIDENCIAS, "4")                # CAMBIO V2-E.4-r2 (r1: "3")
        self.assertEqual(config.CARPETA_V2E4, "datos_v2e4")
        self.assertIn("datos_v2e3", config.CARPETAS_ANTERIORES)
        self.assertIn(config.CARPETA_V2E4, config.CARPETAS_ANTERIORES)   # CAMBIO V2-E.4-r2 (r1: assertNotIn)


if __name__ == "__main__":
    unittest.main()
