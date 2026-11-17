"""V2-E.2: registro persistente de incidencias, priorización causal, reasignación, recuperación de
contexto, laboratorio de experimentos (solo estáticos/simulados), auditoría, interfaces futuras,
integración OPCIONAL con el motor y CLI auditar.py.

Todo es local, en directorios temporales; ningún backend es real, no se ejecuta código generado y
el Modo B sigue deshabilitado (hay pruebas que lo comprueban).
"""
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

import _comun
from eq2 import (auditoria, config, contexto, contexto_incidencias, ejecutor, extensiones, incidencias,
                 laboratorio, memoria, motor, prioridad, rutas)

RAIZ = _comun.RAIZ
Inc = incidencias


class BaseReg(unittest.TestCase):
    def setUp(self):
        self.tmp = _comun.carpeta_temporal()
        self.addCleanup(self.tmp.cleanup)
        self.t = Path(self.tmp.name)
        self.raiz = self.t / "equipo_f2"
        self.base = self.raiz / "datos_v2e2"
        self.lab = rutas.Laboratorio(self.raiz, self.base)
        self.reg = Inc.RegistroIncidencias(self.lab)
        self.addCleanup(self.reg.cerrar)

    def nueva(self, titulo="fallo", gravedad=3, impacto=3, **kw):
        kw.setdefault("categoria", "prueba")
        return self.reg.crear(titulo, gravedad=gravedad, impacto=impacto, **kw)

    def evidencia(self, iid, resultado="fallida", tipo="simulacion"):
        return self.reg.registrar_evidencia(iid, tipo, resultado, f"{tipo} {resultado}", "motor")

    def confirmar(self, iid):
        # CAMBIO V2-E.4-r2: antes «una evidencia + confirmar_causa»; la base ya no admite confirmar una
        # causa sin una hipótesis respaldada (reproducción y control observados).
        _comun.respaldar_causa(self.reg, iid)

    def a_corregida(self, iid):
        self.evidencia(iid, "superada")
        for e in ("en_analisis", "asignada", "en_correccion", "corregida_sin_verificar"):
            self.reg.cambiar_estado(iid, e, "motor")

    def dep_confirmada(self, a, b, tipo="causa"):
        ev = self.evidencia(a)
        self.reg.anadir_dependencia(a, b, tipo, "laboratorio", certeza="confirmada", evidencia_num=ev)


# ============================ 1. persistencia ==============================================
class TestPersistencia(BaseReg):
    def test_ubicacion_y_subcarpetas(self):
        d = self.base / "incidencias"
        self.assertTrue((d / "incidencias.db").is_file())
        for s in ("evidencias", "informes", "regresiones"):
            self.assertTrue((d / s).is_dir())

    def test_sobrevive_a_reabrir_y_los_ids_continuan(self):
        a = self.nueva("uno", criterios=["c1"], archivos=[{"ruta": "m.py", "sha256": "ab"}])
        self.evidencia(a)
        self.reg.registrar_intento(a, "A1", "cambio x", "sin_efecto", version=2)
        self.reg.cerrar()
        r2 = Inc.RegistroIncidencias(self.lab)
        self.addCleanup(r2.cerrar)
        i = r2.obtener(a)
        self.assertEqual((i["titulo"], i["criterios"], i["estado"]), ("uno", ["c1"], "abierta"))
        self.assertEqual(len(r2.evidencias(a)), 1)
        self.assertEqual(r2.intentos(a)[0]["resultado"], "sin_efecto")
        self.assertEqual(r2.con.execute("SELECT ruta FROM archivos_afectados").fetchone()[0], "m.py")
        self.assertEqual(r2.crear("dos", "c", 2, 2), "INC-000002")
        self.assertTrue(r2.quick_check())
        self.reg = r2

    def test_esquema_incompatible_se_rechaza(self):
        self.reg._meta_set("esquema", "99")
        self.reg.cerrar()
        with self.assertRaises(memoria.EsquemaIncompatible):
            Inc.RegistroIncidencias(self.lab)

    def test_ids_unicos_y_firma_deduplica(self):
        a = self.nueva(firma="f1")
        self.assertEqual(self.nueva("otro título", firma="f1"), a)
        b = self.nueva(firma="f2")
        self.assertNotEqual(a, b)
        self.assertRegex(a, r"^INC-\d{6}$")
        self.assertEqual(len(self.reg.listar()), 2)

    def test_evidencia_con_archivo_y_sha256(self):
        a = self.nueva()
        n = self.reg.registrar_evidencia(a, "analisis_estatico", "fallida", "sintaxis", "motor",
                                         contenido={"error": "sintaxis", "linea": 3})
        e = self.reg.evidencias(a)[0]
        self.assertEqual(e["num"], n)
        p = self.base / "incidencias" / e["archivo"]
        self.assertTrue(p.is_file())
        self.assertTrue(p.resolve().is_relative_to(self.base.resolve()))
        self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(), e["sha256"])
        self.assertEqual(list(self.base.rglob(".tmp_*")), [])

    def test_evidencias_mismo_contenido_no_colisionan(self):
        a = self.nueva()
        for _ in range(5):
            self.reg.registrar_evidencia(a, "observacion", "informativa", "x", "A3", contenido="igual")
        archivos = [e["archivo"] for e in self.reg.evidencias(a)]
        self.assertEqual(len(set(archivos)), 5)

    def test_historial_registra_cada_cambio(self):
        a = self.nueva()
        self.reg.asignar(a, "A2", "motor", "diagnóstico")
        self.reg.actualizar_diagnostico(a, "A2", gravedad=5, causa="índice fuera de rango")
        self.reg.cambiar_estado(a, "en_analisis", "A2")
        campos = [h["campo"] for h in self.reg.historial(a)]
        for c in ("creada", "asignado", "gravedad", "causa", "estado"):
            self.assertIn(c, campos)
        self.assertEqual(self.reg.historial(a)[-1]["actor"], "A2")

    def test_cambiar_la_causa_la_devuelve_a_hipotesis(self):
        a = self.nueva()
        self.confirmar(a)
        self.assertEqual(self.reg.obtener(a)["causa_estado"], "confirmada")
        self.reg.actualizar_diagnostico(a, "A2", causa="otra causa")
        self.assertEqual(self.reg.obtener(a)["causa_estado"], "hipotesis")


# ============================ 2. invariantes impuestas por la base ==========================
class TestDisparadores(BaseReg):
    """SQL directo (saltándose el código): la base debe negarse igualmente."""

    def sql(self, q, args=()):
        with self.assertRaises(sqlite3.IntegrityError):
            with self.reg.con:
                self.reg.con.execute(q, args)

    def test_no_se_borran_incidencias(self):
        self.nueva()
        self.sql("DELETE FROM incidencias")
        self.assertEqual(len(self.reg.listar()), 1)

    def test_verificada_exige_prueba_real(self):
        a = self.nueva()
        self.evidencia(a, "superada")                     # simulada superada: NO basta
        self.sql("UPDATE incidencias SET estado='verificada' WHERE id=?", (a,))

    def test_no_nace_verificada_ni_corregida(self):
        for est in ("verificada", "corregida_sin_verificar"):
            self.sql("INSERT INTO incidencias(id,creada,actualizada,titulo,categoria,gravedad,impacto,"
                     "dificultad,confianza,estado,origen) VALUES(?,'t','t','x','c',1,1,1,0.5,?,'sql')",
                     (f"INC-9{est[:3]}", est))

    def test_corregida_exige_evidencia_no_declarativa(self):
        a = self.nueva()
        self.reg.declaracion_de_agente(a, "A1", "¡corregido!")
        self.reg.registrar_evidencia(a, "observacion", "superada", "parece bien", "A3")
        self.sql("UPDATE incidencias SET estado='corregida_sin_verificar' WHERE id=?", (a,))

    def test_causa_confirmada_exige_evidencia(self):
        a = self.nueva()
        self.reg.declaracion_de_agente(a, "A2", "la causa es X")
        self.sql("UPDATE incidencias SET causa_estado='confirmada' WHERE id=?", (a,))
        with self.assertRaises(sqlite3.IntegrityError):
            self.reg.confirmar_causa(a, "laboratorio", "sin evidencias")

    def test_tablas_de_solo_anexar(self):
        a, b = self.nueva(), self.nueva()
        self.evidencia(a)
        self.reg.registrar_intento(a, "A1", "x")
        self.reg.anadir_dependencia(a, b, "causa", "A2")
        contexto_incidencias.Empaquetador(self.reg, 200).siguiente()
        self.sql("UPDATE evidencias SET resultado='superada'")
        self.sql("DELETE FROM evidencias")
        self.sql("UPDATE historial SET actor='usuario'")
        self.sql("DELETE FROM historial")
        self.sql("DELETE FROM intentos")
        self.sql("DELETE FROM dependencias")
        self.sql("DELETE FROM paquetes")

    def test_declaracion_siempre_informativa(self):
        a = self.nueva()
        self.sql("INSERT INTO evidencias(incidencia_id,creada,tipo,resultado,descripcion,actor) "
                 "VALUES(?,'t','declaracion_agente','superada','yo digo','A1')", (a,))
        self.reg.registrar_evidencia(a, "declaracion_agente", "superada", "yo digo", "A1")
        self.assertEqual(self.reg.evidencias(a)[0]["resultado"], "informativa")

    def test_dependencia_confirmada_exige_evidencia_y_no_reflexiva(self):
        a, b = self.nueva(), self.nueva()
        self.sql("INSERT INTO dependencias(origen,destino,tipo,certeza,creada) VALUES(?,?,'causa','confirmada','t')",
                 (a, b))
        self.sql("INSERT INTO dependencias(origen,destino,tipo,certeza,creada) VALUES(?,?,'causa','hipotesis','t')",
                 (a, a))


# ============================ 3. permisos y transiciones ====================================
class TestPermisos(BaseReg):
    def test_agentes_no_verifican_descartan_ni_dan_por_corregido(self):
        a = self.nueva()
        self.a_corregida(a)
        for ag in Inc.AGENTES:
            for est in ("verificada", "descartada", "corregida_sin_verificar"):
                with self.subTest(agente=ag, estado=est), self.assertRaises(Inc.PermisoDenegado):
                    self.reg.cambiar_estado(a, est, ag)

    def test_solo_el_usuario_descarta(self):
        a = self.nueva()
        for actor in ("motor", "laboratorio", "A2"):
            with self.assertRaises(Inc.PermisoDenegado):
                self.reg.cambiar_estado(a, "descartada", actor)
        self.reg.cambiar_estado(a, "descartada", "usuario", "duplicada")
        self.assertEqual(self.reg.obtener(a)["estado"], "descartada")

    def test_nadie_verifica_sin_prueba_real_ni_el_usuario(self):
        a = self.nueva()
        self.a_corregida(a)
        with self.assertRaises(sqlite3.IntegrityError):
            self.reg.cambiar_estado(a, "verificada", "usuario")
        self.assertEqual(self.reg.obtener(a)["estado"], "corregida_sin_verificar")

    def test_prueba_real_rechazada_con_modo_b_deshabilitado(self):
        self.assertFalse(config.MODO_B_HABILITADO)
        a = self.nueva()
        for actor in ("motor", "laboratorio", "usuario"):
            with self.assertRaises(Inc.PermisoDenegado):
                self.reg.registrar_evidencia(a, "prueba_real", "superada", "x", actor)
        self.assertEqual(self.reg.evidencias(a), [])

    def test_agentes_solo_aportan_observaciones_y_declaraciones(self):
        a = self.nueva()
        for tipo in Inc.NO_DECLARATIVAS:
            with self.assertRaises(Inc.PermisoDenegado):
                self.reg.registrar_evidencia(a, tipo, "superada", "x", "A1")
        self.reg.registrar_evidencia(a, "observacion", "informativa", "veo algo", "A3")

    def test_agentes_no_confirman_causas_ni_dependencias(self):
        a, b = self.nueva(), self.nueva()
        self.evidencia(a)
        with self.assertRaises(Inc.PermisoDenegado):
            self.reg.confirmar_causa(a, "A2", "estoy seguro")
        with self.assertRaises(Inc.PermisoDenegado):
            self.reg.anadir_dependencia(a, b, "causa", "A2", certeza="confirmada", evidencia_num=1)
        self.reg.anadir_dependencia(a, b, "causa", "A2")            # como hipótesis, sí
        self.assertEqual(self.reg.dependencias()[0]["certeza"], "hipotesis")

    def test_actor_desconocido_y_transicion_invalida(self):
        a = self.nueva()
        with self.assertRaises(Inc.PermisoDenegado):
            self.reg.cambiar_estado(a, "en_analisis", "intruso")
        with self.assertRaises(Inc.TransicionInvalida):
            self.reg.cambiar_estado(a, "en_correccion", "motor")      # abierta -> en_correccion
        with self.assertRaises(Inc.TransicionInvalida):
            self.reg.cambiar_estado(a, "inventado", "motor")
        with self.assertRaises(Inc.PermisoDenegado):
            self.reg.registrar_intento(a, "motor", "x")

    def test_reabrir_cuenta_reaperturas(self):
        a = self.nueva()
        self.a_corregida(a)
        self.reg.cambiar_estado(a, "reabierta", "motor", "reaparece")
        self.assertEqual(self.reg.reaperturas(a), 1)


class TestDependencias(BaseReg):
    def test_ciclos_rechazados(self):
        a, b, c = self.nueva(), self.nueva(), self.nueva()
        self.reg.anadir_dependencia(a, b, "causa", "A2")
        self.reg.anadir_dependencia(b, c, "bloquea", "A2")
        for o, d in ((c, a), (b, a), (a, a)):
            with self.subTest(o=o, d=d), self.assertRaises(Inc.CicloDependencias):
                self.reg.anadir_dependencia(o, d, "causa", "A2")
        self.reg.anadir_dependencia(c, a, "relacionada", "A2")      # «relacionada» no forma ciclos causales
        self.assertEqual(len(self.reg.dependencias()), 3)

    def test_incidencia_inexistente(self):
        a = self.nueva()
        with self.assertRaises(KeyError):
            self.reg.anadir_dependencia(a, "INC-999999", "causa", "A2")


# ============================ 4. priorización causal =======================================
class TestPriorizacionCausal(BaseReg):
    def ids(self):
        return [x["id"] for x in prioridad.puntuar(self.reg)]

    def test_raiz_confirmada_antes_que_su_efecto_mas_grave(self):
        raiz = self.nueva("config corrupta", 3, 3)
        efecto = self.nueva("pruebas fallan", 4, 4)
        self.dep_confirmada(raiz, efecto)
        p = {x["id"]: x for x in prioridad.puntuar(self.reg)}
        self.assertEqual(self.ids()[0], raiz)
        self.assertEqual(p[raiz]["afecta_a"], [efecto])
        self.assertTrue(p[efecto]["es_efecto_de_pendiente"])
        self.assertLess(p[efecto]["componentes"]["efecto"], 0)

    def test_hipotesis_pesa_menos_que_causa_confirmada(self):
        r1, e1 = self.nueva("r1", 3, 3), self.nueva("e1", 3, 3)
        r2, e2 = self.nueva("r2", 3, 3), self.nueva("e2", 3, 3)
        self.dep_confirmada(r1, e1)
        self.reg.anadir_dependencia(r2, e2, "causa", "A2")            # hipótesis
        p = {x["id"]: x for x in prioridad.puntuar(self.reg)}
        self.assertGreater(p[r1]["componentes"]["causal"], p[r2]["componentes"]["causal"])
        self.assertGreater(p[r1]["prioridad"], p[r2]["prioridad"])

    def test_cadena_transitiva_con_certeza_minima(self):
        a, b, c = self.nueva("a", 2, 2), self.nueva("b", 2, 2), self.nueva("c", 5, 5)
        self.dep_confirmada(a, b)
        self.reg.anadir_dependencia(b, c, "causa", "A2")              # hipótesis
        p = {x["id"]: x for x in prioridad.puntuar(self.reg)}
        self.assertEqual(p[a]["afecta_a"], [b, c])
        conf = self.reg.obtener(a)["confianza"]
        esperado = 6 * conf * (1.0 * (2 + 2) + 0.5 * (5 + 5)) / 10
        self.assertAlmostEqual(p[a]["componentes"]["causal"], round(esperado, 3))

    def test_bloqueada_se_atiende_despues(self):
        bloq = self.nueva("bloqueante", 2, 2)
        b = self.nueva("bloqueada", 5, 5)
        self.reg.anadir_dependencia(bloq, b, "bloquea", "A2")
        p = {x["id"]: x for x in prioridad.puntuar(self.reg)}
        self.assertTrue(p[b]["bloqueada"])
        self.assertEqual(p[b]["componentes"]["bloqueo"], -4.0)

    def test_la_dificultad_no_se_premia(self):
        facil = self.nueva("fácil", 3, 3, dificultad=1)
        dificil = self.nueva("difícil", 3, 3, dificultad=5)
        self.assertEqual(self.ids(), [facil, dificil])

    def test_recalculo_con_nuevos_errores_y_resultados(self):
        a = self.nueva("a", 3, 3)
        b = self.nueva("b", 4, 4)
        antes = prioridad.recalcular(self.reg, "inicio")
        self.assertEqual(antes[0]["id"], b)
        c = self.nueva("c", 4, 4)                                     # nuevo error causado por a
        self.dep_confirmada(a, b)
        self.dep_confirmada(a, c)
        despues = prioridad.recalcular(self.reg, "nuevo error")
        self.assertEqual(despues[0]["id"], a)
        self.assertEqual(self.reg.obtener(a)["prioridad"], despues[0]["prioridad"])
        self.assertEqual(self.reg.con.execute("SELECT count(*) FROM recalculos").fetchone()[0], 2)
        pa = despues[0]["prioridad"]
        self.a_corregida(b)                                           # cambia un resultado
        self.a_corregida(c)
        p3 = {x["id"]: x for x in prioridad.recalcular(self.reg, "b y c corregidas")}
        self.assertLess(p3[a]["prioridad"], pa)                       # ya no se le suma lo resuelto
        self.assertNotIn(b, p3)                                       # solo puntúan las pendientes

    def test_reaperturas_suben_la_prioridad(self):
        a, b = self.nueva("a"), self.nueva("b")
        self.a_corregida(b)
        self.reg.cambiar_estado(b, "reabierta", "motor")
        p = {x["id"]: x for x in prioridad.puntuar(self.reg)}
        self.assertEqual(p[b]["componentes"]["reaperturas"], 2.0)
        self.assertEqual(self.ids()[0], b)

    def test_componentes_suman_la_prioridad(self):
        self.nueva()
        x = prioridad.puntuar(self.reg)[0]
        self.assertAlmostEqual(sum(x["componentes"].values()), x["prioridad"], places=2)


# ============================ 5. planificación y reasignación ===============================
class TestPlanYReasignacion(BaseReg):
    def tarea(self, plan, iid):
        return next((t for t in plan["tareas"] if t["incidencia"] == iid), None)

    def test_hipotesis_a_A2_confirmada_a_A1_corregida_a_A3(self):
        h, c, k = self.nueva("h"), self.nueva("c"), self.nueva("k")
        self.confirmar(c)
        self.a_corregida(k)
        plan = prioridad.planificar(self.reg)
        self.assertEqual((self.tarea(plan, h)["agente"], self.tarea(plan, h)["accion"]), ("A2", "diagnosticar"))
        self.assertEqual((self.tarea(plan, c)["agente"], self.tarea(plan, c)["accion"]), ("A1", "corregir"))
        t = self.tarea(plan, k)
        self.assertEqual((t["agente"], t["accion"]), ("A3", "revisar"))
        self.assertIn("prueba real", t["motivo"])
        self.assertEqual(self.reg.obtener(c)["asignado"], "A1")

    def test_dos_intentos_sin_efecto_reasignan_a_A2_y_vuelve_a_hipotesis(self):
        a = self.nueva()
        self.confirmar(a)
        self.reg.registrar_intento(a, "A1", "i1", "sin_efecto")
        self.reg.registrar_intento(a, "A1", "i2", "empeora")
        t = self.tarea(prioridad.planificar(self.reg), a)
        self.assertEqual((t["agente"], t["accion"]), ("A2", "rediagnosticar"))
        i = self.reg.obtener(a)
        self.assertEqual((i["causa_estado"], i["asignado"]), ("hipotesis", "A2"))
        self.confirmar(a)                                             # tras rediagnosticar, A1 vuelve a intentarlo
        t = self.tarea(prioridad.planificar(self.reg), a)
        self.assertEqual((t["agente"], t["accion"]), ("A1", "corregir"))
        self.assertEqual(prioridad.contadores(self.reg, a)["sin_efecto_desde_rediagnostico"], 0)

    def test_limite_de_rediagnosticos_escala_aunque_queden_intentos(self):
        a = self.nueva()
        self.confirmar(a)
        with mock.patch.object(prioridad, "MAX_INTENTOS", 50):
            for n in range(2):
                self.reg.registrar_intento(a, "A1", f"i{n}", "sin_efecto")
            self.assertEqual(self.tarea(prioridad.planificar(self.reg), a)["accion"], "rediagnosticar")
            self.confirmar(a)
            for n in range(2):
                self.reg.registrar_intento(a, "A1", f"j{n}", "sin_efecto")
            p = prioridad.planificar(self.reg)
        self.assertEqual(p["escaladas_al_usuario"], [a])
        self.assertIsNone(self.tarea(p, a))

    def test_limite_de_intentos_escala_al_usuario_y_no_genera_mas_tareas(self):
        a = self.nueva()
        for n in range(prioridad.MAX_INTENTOS):
            self.reg.registrar_intento(a, "A1", f"i{n}", "parcial")
        p1 = prioridad.planificar(self.reg)
        self.assertEqual(p1["escaladas_al_usuario"], [a])
        self.assertIsNone(self.tarea(p1, a))
        i = self.reg.obtener(a)
        self.assertEqual((i["bloqueada_por_limite"], i["asignado"]), (1, "usuario"))
        p2 = prioridad.planificar(self.reg)
        self.assertEqual((p2["escaladas_al_usuario"], self.tarea(p2, a)), ([], None))

    def test_espera_a_su_bloqueante(self):
        bloq, b = self.nueva("bloqueante"), self.nueva("bloqueada", 5, 5)
        self.reg.anadir_dependencia(bloq, b, "bloquea", "A2")
        p = prioridad.planificar(self.reg)
        self.assertIn(b, p["esperando_bloqueante"])
        self.assertIsNone(self.tarea(p, b))
        self.a_corregida(bloq)
        p = prioridad.planificar(self.reg)
        self.assertIsNotNone(self.tarea(p, b))

    def test_tope_de_tareas_por_ronda(self):
        for n in range(10):
            self.nueva(f"i{n}")
        self.assertEqual(len(prioridad.planificar(self.reg, max_tareas=3)["tareas"]), 3)
        self.assertEqual(len(prioridad.planificar(self.reg, max_tareas=999)["tareas"]), prioridad.MAX_TAREAS_RONDA)
        self.assertEqual(len(prioridad.planificar(self.reg, max_tareas=0)["tareas"]), 1)

    def test_diagnostico_que_nunca_se_confirma_tambien_escala(self):
        a = self.nueva()
        for _ in range(prioridad.MAX_TAREAS_POR_INCIDENCIA + 5):
            if self.tarea(prioridad.planificar(self.reg), a) is None:
                break
        c = prioridad.contadores(self.reg, a)
        self.assertEqual(c["tareas"], prioridad.MAX_TAREAS_POR_INCIDENCIA)
        self.assertEqual(self.reg.obtener(a)["bloqueada_por_limite"], 1)

    def test_solo_el_usuario_desbloquea_y_reinicia_contadores(self):
        a = self.nueva()
        for n in range(prioridad.MAX_INTENTOS):
            self.reg.registrar_intento(a, "A1", f"i{n}", "sin_efecto")
        prioridad.planificar(self.reg)
        for actor in ("motor", "A1", "A2", "A3", "laboratorio"):
            with self.assertRaises(Inc.PermisoDenegado):
                self.reg.desbloquear(a, actor, "x")
        self.reg.desbloquear(a, "usuario", "nueva información")
        self.assertEqual(prioridad.contadores(self.reg, a)["intentos"], 0)
        self.assertIsNotNone(self.tarea(prioridad.planificar(self.reg), a))
        self.assertEqual(len(self.reg.intentos(a)), prioridad.MAX_INTENTOS)   # el historial no se pierde

    def test_vista_previa_no_escribe_nada(self):
        a = self.nueva()
        for n in range(prioridad.MAX_INTENTOS):
            self.reg.registrar_intento(a, "A1", f"i{n}", "sin_efecto")
        b = self.nueva("otra")
        hist = self.reg.con.execute("SELECT count(*) FROM historial").fetchone()[0]
        rec = self.reg.con.execute("SELECT count(*) FROM recalculos").fetchone()[0]
        p = prioridad.planificar(self.reg, aplicar=False)
        self.assertEqual((p["aplicado"], p["escaladas_al_usuario"]), (False, [a]))
        self.assertEqual(self.tarea(p, b)["agente"], "A2")
        self.assertEqual(self.reg.con.execute("SELECT count(*) FROM historial").fetchone()[0], hist)
        self.assertEqual(self.reg.con.execute("SELECT count(*) FROM recalculos").fetchone()[0], rec)
        self.assertEqual(self.reg.obtener(a)["bloqueada_por_limite"], 0)
        self.assertIsNone(self.reg.obtener(b)["asignado"])

    def test_bucle_de_rondas_termina_sin_ciclos_infinitos(self):
        """Agentes que nunca arreglan nada: el sistema debe escalar en un número acotado de rondas."""
        a = self.nueva()
        self.confirmar(a)
        rondas = 0
        for rondas in range(1, 20):
            plan = prioridad.planificar(self.reg)
            t = self.tarea(plan, a)
            if t is None:
                break
            if t["agente"] == "A1":
                self.reg.registrar_intento(a, "A1", f"ronda {rondas}", "sin_efecto")
            else:                                                     # A2 rediagnostica; se reconfirma
                self.confirmar(a)
        self.assertLessEqual(rondas, prioridad.MAX_INTENTOS + 3)
        self.assertEqual(self.reg.obtener(a)["bloqueada_por_limite"], 1)
        self.assertEqual(prioridad.contadores(self.reg, a)["rediagnosticos"], 1)
        self.assertNotEqual(self.reg.obtener(a)["estado"], "verificada")


# ============================ 6. recuperación de contexto ==================================
EV = re.compile(r"\bE(\d+) \[")


class TestContexto(BaseReg):
    def poblar(self, n=4, evs=3, largo=60):
        ids = []
        for k in range(n):
            iid = self.nueva(f"incidencia {k}", 2 + k % 3, 3, criterios=[f"criterio-{k}"])
            for j in range(evs):
                self.reg.registrar_evidencia(iid, "simulacion", "fallida", f"ev {k}.{j} " + "x" * largo, "motor")
            ids.append(iid)
        return ids

    def entregadas(self, paquetes):
        vistas = []
        for p in paquetes:
            vistas += [int(x) for x in EV.findall(p["texto"])]
        return vistas

    def test_nada_se_pierde_con_cualquier_presupuesto(self):
        ids = self.poblar()
        todas = {e["num"] for i in ids for e in self.reg.evidencias(i)}
        for pres in (40, 55, 80, 150, 400, 5000):
            with self.subTest(presupuesto=pres):
                paq = contexto_incidencias.Empaquetador(self.reg, pres).todos()
                self.assertTrue(paq)
                self.assertNotIn("tope_alcanzado_con_pendientes", paq[-1])
                self.assertEqual({i for p in paq for i in p["incluidas"]}, set(ids))
                self.assertEqual(set(self.entregadas(paq)), todas)
                for p in paq:
                    self.assertLessEqual(p["tokens_est"], pres)
                    self.assertLessEqual(contexto.estimar_tokens(p["texto"]), p["tokens_est"])

    def test_criticas_primero_y_criterios_siempre_presentes(self):
        baja = self.nueva("menor", 3, 5, criterios=["menor ok"])
        critica = self.nueva("crítica", 4, 1, criterios=["crítica ok"], dificultad=5)
        self.reg.anadir_dependencia(baja, self.nueva("otra", 3, 3), "causa", "A2")
        self.assertEqual(prioridad.puntuar(self.reg)[0]["id"], baja)        # por prioridad iría antes
        paq = contexto_incidencias.Empaquetador(self.reg, 60).todos()
        self.assertEqual(paq[0]["incluidas"][0], critica)
        for p in paq:
            for iid in p["incluidas"]:
                bloque = p["texto"].split(f"[{iid}]", 1)[1]
                if "(cont." not in bloque[:10]:
                    self.assertIn("CRITERIOS:", bloque)

    def test_omitidas_viajan_en_el_siguiente_paquete(self):
        a = self.poblar(1, 4, 120)[0]
        e = contexto_incidencias.Empaquetador(self.reg, 80)
        p1 = e.siguiente()
        self.assertIn(a, p1["evidencias_omitidas"])
        omit = p1["evidencias_omitidas"][a]
        self.assertIn("evidencias en el paquete siguiente", p1["texto"])
        resto = []
        while (p := e.siguiente()) is not None:
            resto += self.entregadas([p])
        self.assertTrue(set(omit) <= set(resto))

    def test_cabecera_enorme_conserva_id_y_criterios(self):
        a = self.nueva("T" * 200, descripcion="d", causa="C" * 400, criterios=["criterio clave"] + ["x" * 150] * 3)
        self.evidencia(a)
        paq = contexto_incidencias.Empaquetador(self.reg, 40).todos()
        self.assertEqual(paq[0]["cabeceras_recortadas"], [a])
        self.assertIn(f"[{a}] CRITERIOS: criterio clave", paq[0]["texto"])
        self.assertIn("CABECERA RECORTADA", paq[0]["texto"])
        for p in paq:
            self.assertLessEqual(p["tokens_est"], 40)
        self.assertEqual(set(self.entregadas(paq)), {e["num"] for e in self.reg.evidencias(a)})

    def test_progreso_garantizado_con_evidencia_enorme(self):
        a = self.nueva("enorme")
        self.reg.registrar_evidencia(a, "simulacion", "fallida", "Z" * 500, "motor")
        paq = contexto_incidencias.Empaquetador(self.reg, 40).todos(max_paquetes=10)
        self.assertLessEqual(len(paq), 3)
        self.assertTrue(any(p["evidencias_recortadas"] for p in paq))
        self.assertIn("RECORTADA", "".join(p["texto"] for p in paq))
        self.assertNotIn("tope_alcanzado_con_pendientes", paq[-1])

    def test_tope_de_paquetes_se_indica(self):
        self.poblar(6, 4, 200)
        paq = contexto_incidencias.Empaquetador(self.reg, 40).todos(max_paquetes=2)
        self.assertEqual(len(paq), 2)
        self.assertTrue(paq[-1]["tope_alcanzado_con_pendientes"])

    def test_paquetes_quedan_registrados(self):
        self.poblar(3, 2)
        paq = contexto_incidencias.Empaquetador(self.reg, 60, agente="A1").todos()
        filas = self.reg.con.execute("SELECT * FROM paquetes ORDER BY num").fetchall()
        self.assertEqual(len(filas), len(paq))
        self.assertEqual(json.loads(filas[0]["incluidas_json"]), paq[0]["incluidas"])
        self.assertEqual(filas[0]["agente"], "A1")

    def test_presupuesto_minimo(self):
        with self.assertRaises(ValueError):
            contexto_incidencias.Empaquetador(self.reg, 39)

    def test_incluye_corregidas_sin_verificar_y_excluye_descartadas(self):
        a, b = self.nueva("corr"), self.nueva("desc")
        self.a_corregida(a)
        self.reg.cambiar_estado(b, "descartada", "usuario")
        inc = {i for p in contexto_incidencias.Empaquetador(self.reg, 400).todos() for i in p["incluidas"]}
        self.assertEqual(inc, {a})

    def test_declaracion_del_agente_no_resuelve(self):
        a = self.nueva()
        hechas = contexto_incidencias.procesar_respuesta_agente(
            self.reg, "A1", f"He terminado. CORREGIDO: {a}\nresuelto: INC-999999")
        self.assertEqual(hechas, [a])
        self.assertEqual(self.reg.obtener(a)["estado"], "abierta")
        ev = self.reg.evidencias(a)
        self.assertEqual([(e["tipo"], e["resultado"], e["actor"]) for e in ev],
                         [("declaracion_agente", "informativa", "A1")])
        with self.assertRaises(sqlite3.IntegrityError):               # ni siquiera el motor puede pasarla a corregida
            for e in ("en_analisis", "asignada", "en_correccion", "corregida_sin_verificar"):
                self.reg.cambiar_estado(a, e, "motor")


# ============================ 7. laboratorio ===============================================
SIM = {"archivos": {"m.py": "def ordenar(xs):\n    xs.sort()\n    return xs\n"},
       "pruebas": ["test_no_muta"],
       "reglas": [{"archivo": "m.py", "si_contiene": ".sort()", "prueba": "test_no_muta", "resultado": "fallo"}]}
ARREGLADO = {"m.py": "def ordenar(xs):\n    return sorted(xs)\n"}


class _Vigia:
    """Gancho de auditoría de Python: registra exec/subprocesos/red mientras está activo."""
    EVENTOS = ("exec", "subprocess.Popen", "os.system", "os.posix_spawn", "os.exec", "os.fork",
               "os.spawn", "socket.connect", "ctypes.dlopen")
    activo, vistos, instalado = False, [], False

    @classmethod
    def instalar(cls):
        if not cls.instalado:
            sys.addaudithook(cls._gancho)
            cls.instalado = True

    @classmethod
    def _gancho(cls, ev, _args):
        if cls.activo and ev in cls.EVENTOS:
            cls.vistos.append(ev)


class TestLaboratorio(BaseReg):
    def setUp(self):
        super().setUp()
        self.lb = laboratorio.Laboratorio(self.reg)
        self.inc = self.nueva("ordenar muta", 4, 4)

    def test_simulacion_reproduce_confirma_y_crea_regresion(self):
        e = self.lb.planificar("xs.sort() rompe test_no_muta", "simulacion", SIM, {"prueba_falla": "test_no_muta"},
                               incidencia_id=self.inc)
        r = self.lb.ejecutar(e)
        self.assertEqual((r["estado"], r["conclusion"], r["evidencia"], r["ejecucion_real"]),
                         ("completado", "apoya", "fallida", False))
        ev = self.reg.evidencias(self.inc)[-1]
        self.assertEqual((ev["tipo"], ev["actor"], ev["experimento_id"]), ("simulacion", "laboratorio", e))
        # CAMBIO V2-E.4-r2: una sola reproducción YA NO confirma la causa ni permite una regresión.
        self.assertFalse(self.lb.confirmar_causa_con(e))
        self.assertEqual(self.reg.obtener(self.inc)["causa_estado"], "hipotesis")
        with self.assertRaises(Inc.PermisoDenegado):
            self.lb.crear_regresion(e)
        # Camino completo: hipótesis + reproducción y control sobre versiones observadas.
        hid = _comun.respaldar_causa(self.reg, self.inc, "m.py", ".sort()", SIM["archivos"]["m.py"],
                                     ARREGLADO["m.py"])
        self.assertEqual(self.reg.obtener(self.inc)["causa_estado"], "confirmada")
        rep = self.reg.con.execute("SELECT id FROM experimentos WHERE hipotesis_id=? AND rol='reproduccion'",
                                   (hid,)).fetchone()[0]
        self.assertTrue(self.lb.confirmar_causa_con(rep))
        rid = self.lb.crear_regresion(rep)
        p = self.base / "incidencias" / "regresiones" / f"{rid}.json"
        caso = json.loads(p.read_text())
        self.assertEqual(caso["nota"], "datos, no código")
        self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(), self.lb.regresiones()[0]["sha256"])
        self.assertTrue(self.lb.ejecutar_regresion(rid)["reproduce"])
        self.assertTrue(self.lb.ejecutar_regresion(rid, ARREGLADO)["supera"])
        self.assertFalse(self.lb.ejecutar_regresion(rid, SIM["archivos"])["supera"])
        with self.assertRaises(sqlite3.IntegrityError), self.reg.con:
            self.reg.con.execute("DELETE FROM regresiones")

    def test_refutada_no_confirma_ni_crea_regresion(self):
        e = self.lb.planificar("la versión arreglada falla", "simulacion", dict(SIM, archivos=ARREGLADO),
                               {"prueba_falla": "test_no_muta"}, incidencia_id=self.inc)
        r = self.lb.ejecutar(e)
        self.assertEqual((r["conclusion"], r["evidencia"]), ("refuta", "informativa"))
        self.assertFalse(self.lb.confirmar_causa_con(e))
        with self.assertRaises(Inc.PermisoDenegado):                    # causa sin confirmar
            self.lb.crear_regresion(e)

    def test_regresion_exige_que_el_experimento_reproduzca_el_fallo(self):
        e1 = self.lb.planificar("reproduce", "simulacion", SIM, {"prueba_falla": "test_no_muta"}, incidencia_id=self.inc)
        self.lb.ejecutar(e1)
        self.assertFalse(self.lb.confirmar_causa_con(e1))                # CAMBIO V2-E.4-r2: aislado no basta
        _comun.respaldar_causa(self.reg, self.inc)                       # CAMBIO V2-E.4-r2: camino completo
        e2 = self.lb.planificar("pasa", "simulacion", dict(SIM, archivos=ARREGLADO), {"prueba_pasa": "test_no_muta"},
                                incidencia_id=self.inc)
        self.assertEqual(self.lb.ejecutar(e2)["evidencia"], "superada")
        self.assertFalse(self.lb.confirmar_causa_con(e2))
        with self.assertRaises(ValueError):
            self.lb.crear_regresion(e2)
        with self.assertRaises(Inc.PermisoDenegado):                    # CAMBIO V2-E.4-r2: no es la reproducción
            self.lb.crear_regresion(e1)                                  # de la hipótesis que respalda la causa

    def test_no_concluyente_si_la_prueba_no_existe(self):
        e = self.lb.planificar("?", "simulacion", SIM, {"prueba_falla": "test_inexistente"}, incidencia_id=self.inc)
        self.assertEqual(self.lb.ejecutar(e)["conclusion"], "no_concluyente")

    def test_estatico_detecta_sintaxis(self):
        e = self.lb.planificar("sintaxis rota", "analisis_estatico", {"archivos": {"m.py": "def f(x)\n  return x\n"}},
                               {"tipo_error": "sintaxis"}, incidencia_id=self.inc)
        r = self.lb.ejecutar(e)
        self.assertEqual((r["conclusion"], r["resultado"]["tipo"]), ("apoya", "estatico"))
        self.assertEqual(self.reg.evidencias(self.inc)[-1]["tipo"], "analisis_estatico")
        e2 = self.lb.planificar("código válido tiene sintaxis rota", "analisis_estatico",
                                {"archivos": {"m.py": "def f(x):\n    return x\n"}}, {"tipo_error": "sintaxis"})
        self.assertEqual(self.lb.ejecutar(e2)["conclusion"], "refuta")
        e3 = self.lb.planificar("sin errores", "analisis_estatico", {"archivos": {"m.py": "x = 1\n", "test_m.py": "from m import x\ndef test_a():\n    assert x == 1\n"}},
                                {"sin_errores": True})
        self.assertEqual(self.lb.ejecutar(e3)["conclusion"], "apoya")

    def test_prueba_motor_simulada(self):
        for esc, esperado in (("demo_corrige", "criterios_superados_en_simulacion"),):
            e = self.lb.planificar(esc, "prueba_motor", {"escenario": esc}, {"estado_final": esperado})
            r = self.lb.ejecutar(e)
            self.assertEqual(r["conclusion"], "apoya", r)
            self.assertEqual(r["resultado"]["tipo"], "simulado")
        for esc in ("bloqueo_persistente", "sin_progreso"):
            e = self.lb.planificar(esc, "prueba_motor", {"escenario": esc},
                                   {"estado_final": "criterios_superados_en_simulacion"})
            r = self.lb.ejecutar(e)
            self.assertEqual((r["estado"], r["conclusion"]), ("completado", "refuta"), r)
            self.assertLessEqual(r["resultado"]["iteraciones"], self.lb.presupuesto.max_iteraciones_correccion)
        self.assertTrue((self.base / "incidencias" / "laboratorio").is_dir())

    def test_vocabulario_cerrado_y_entradas_validas(self):
        malos = [("simulacion", SIM, {"eval": "1+1"}), ("simulacion", SIM, {"prueba_falla": "a", "prueba_pasa": "b"}),
                 ("ejecucion_real", SIM, {"sin_errores": True}), ("prueba_motor", {"escenario": "rm -rf"},
                                                                    {"estado_final": "x"}),
                 ("analisis_estatico", {"archivos": {"m.py": 3}}, {"sin_errores": True}),
                 ("analisis_estatico", {"archivos": {"m.py": "x" * 70_000}}, {"sin_errores": True})]
        for tipo, ent, esp in malos:
            with self.subTest(tipo=tipo, esp=esp), self.assertRaises(ValueError):
                self.lb.planificar("h", tipo, ent, esp)
        self.assertEqual(self.reg.con.execute("SELECT count(*) FROM experimentos").fetchone()[0], 0)

    def test_regla_de_simulacion_invalida_aborta_sin_concluir(self):
        e = self.lb.planificar("h", "simulacion", dict(SIM, reglas=[{"archivo": "m.py", "si_contiene": "x",
                                                                    "prueba": "t", "resultado": "exec"}]),
                               {"prueba_falla": "t"}, incidencia_id=self.inc)
        r = self.lb.ejecutar(e)
        self.assertEqual((r["estado"], r["conclusion"]), ("abortado", "no_concluyente"))

    def test_no_se_repite_un_experimento_y_registra_limites(self):
        e = self.lb.planificar("h", "simulacion", SIM, {"prueba_falla": "test_no_muta"})
        self.lb.ejecutar(e)
        with self.assertRaises(ValueError):
            self.lb.ejecutar(e)
        x = self.lb.experimento(e)
        self.assertFalse(x["limites"]["ejecucion_real"])
        self.assertEqual(x["hipotesis"], "h")
        self.assertEqual(x["estado"], "completado")

    def test_presupuesto_segun_recursos_nunca_crece(self):
        base = motor.Presupuesto().acotado()
        casos = [({"mem_kB": None}, 1, 6), ({"mem_kB": 500_000}, 1, 6), ({"mem_kB": 1_500_000}, 2, None),
                 ({"mem_kB": 6_000_000}, None, None)]
        for rec, it, ll in casos:
            with self.subTest(rec=rec):
                p, motivos = laboratorio.ajustar_presupuesto(base, rec)
                self.assertLessEqual(p.max_iteraciones_correccion, it if it is not None else base.max_iteraciones_correccion)
                self.assertLessEqual(p.max_llamadas, ll if ll is not None else base.max_llamadas)
                for campo in base.__dataclass_fields__:
                    self.assertLessEqual(getattr(p, campo), getattr(base, campo))
                self.assertEqual(bool(motivos), rec["mem_kB"] is None or rec["mem_kB"] < 2_000_000)
        p, m = laboratorio.ajustar_presupuesto(base, {"mem_kB": 6_000_000, "bateria": (20, False)})
        self.assertLessEqual(p.seg_total, base.seg_total / 2)
        self.assertTrue(m)
        p, m = laboratorio.ajustar_presupuesto(base, {"mem_kB": 6_000_000, "bateria": (20, True)})
        self.assertEqual((p.seg_total, m), (base.seg_total, []))
        pequeno = motor.Presupuesto(max_iteraciones_correccion=0, max_llamadas=2)
        p, _ = laboratorio.ajustar_presupuesto(pequeno, {"mem_kB": 8_000_000})
        self.assertEqual((p.max_iteraciones_correccion, p.max_llamadas), (0, 2))

    def test_ningun_experimento_ejecuta_codigo(self):
        peligroso = {"archivos": {"m.py": "import os\nos.system('touch /tmp/NO')\nexec('1')\n",
                                  "test_m.py": "def test_a():\n    assert True\n"},
                     "pruebas": ["test_a"],
                     "reglas": [{"archivo": "m.py", "si_contiene": "os.system", "prueba": "test_a", "resultado": "fallo"}]}
        planes = [("analisis_estatico", peligroso, {"sin_errores": True}),
                  ("simulacion", peligroso, {"prueba_falla": "test_a"}),
                  ("prueba_motor", {"escenario": "demo_corrige"}, {"estado_final": "criterios_superados_en_simulacion"})]
        for tipo, ent, esp in planes:                                 # calentamiento: importaciones diferidas
            self.lb.ejecutar(self.lb.planificar("calentar", tipo, ent, esp))
        _Vigia.instalar()
        _Vigia.vistos = []
        _Vigia.activo = True
        try:
            for tipo, ent, esp in planes:
                self.lb.ejecutar(self.lb.planificar("vigilado", tipo, ent, esp, incidencia_id=self.inc))
        finally:
            _Vigia.activo = False
        self.assertEqual(_Vigia.vistos, [])
        self.assertFalse(any(e["tipo"] == "prueba_real" for e in self.reg.evidencias(self.inc)))


# ============================ 8. auditoría ==================================================
class TestAuditoria(BaseReg):
    def test_informe_separa_categorias_y_tipos(self):
        pend = self.nueva("pendiente")
        corr = self.nueva("corregida")
        reab = self.nueva("reabierta")
        self.a_corregida(corr)
        self.a_corregida(reab)
        self.reg.cambiar_estado(reab, "reabierta", "motor")
        desc = self.nueva("descartada")
        self.reg.cambiar_estado(desc, "descartada", "usuario")
        self.reg.registrar_evidencia(pend, "analisis_estatico", "fallida", "x", "motor")
        inf = auditoria.informe(self.reg)
        r = inf["resumen"]
        self.assertEqual((r["total"], r["pendientes"], r["atendidas_sin_verificar"], r["reabiertas"],
                          r["verificadas"], r["descartadas"]), (4, 2, 1, 1, 0, 1))
        self.assertEqual(inf["atendidas_sin_verificar"], [corr])
        self.assertEqual(inf["reabiertas"], [reab])
        self.assertIn(reab, inf["pendientes"])
        self.assertEqual(inf["declaracion"], "Ninguna solución se ha verificado con pruebas reales.")
        fila = next(f for f in inf["incidencias"] if f["id"] == pend)
        self.assertEqual(fila["evidencias"], {"analisis_estatico:fallida": 1})
        self.assertFalse(any(f["prueba_real"] for f in inf["incidencias"]))
        self.assertEqual(set(inf["tipos_de_comprobacion"]), {"analisis_estatico", "simulacion", "prueba_real"})
        self.assertIn("NO es ejecución", inf["tipos_de_comprobacion"]["simulacion"])

    def test_escribir_genera_json_y_markdown(self):
        self.nueva()
        r1 = auditoria.escribir(self.reg)
        r2 = auditoria.escribir(self.reg)
        self.assertNotEqual(r1["json"], r2["json"])                   # nunca sobrescribe
        self.assertEqual(json.loads(Path(r1["json"]).read_text())["resumen"]["total"], 1)
        md = Path(r1["md"]).read_text()
        self.assertIn("Ninguna solución se ha verificado con pruebas reales.", md)
        self.assertIn("INC-000001", md)
        self.assertEqual(Path(r1["md"]).parent, self.base / "incidencias" / "informes")


# ============================ 9. interfaces futuras ==========================================
class TestExtensiones(unittest.TestCase):
    def test_complementos(self):
        self.assertEqual(set(extensiones.REGISTRO), {"python", "java", "cpp", "csharp", "javascript", "rust"})
        py = extensiones.plugin_para("pkg/m.py")
        self.assertEqual((py.nombre, py.estado), ("python", "estatico"))
        self.assertTrue(py.analizar_estatico({"m.py": "def f(:\n"})["errores"])
        for ruta, nombre in (("A.java", "java"), ("a.cpp", "cpp"), ("a.cs", "csharp"), ("a.js", "javascript"),
                             ("a.rs", "rust")):
            p = extensiones.plugin_para(ruta)
            self.assertEqual((p.nombre, p.estado), (nombre, "no_implementado"))
            with self.assertRaises(extensiones.NoImplementado):
                p.analizar_estatico({ruta: "x"})
        self.assertIsNone(extensiones.plugin_para("a.txt"))
        for p in extensiones.REGISTRO.values():
            with self.assertRaises(extensiones.EjecucionDeshabilitada):
                p.ejecutar_pruebas({"a": "b"})

    def test_configuracion_no_puede_activar_lo_prohibido(self):
        for k in extensiones.PROHIBIDAS:
            with self.subTest(k=k), self.assertRaises(PermissionError):
                extensiones.ConfiguracionModular.desde_dict({k: True})
        with self.assertRaises(ValueError):
            extensiones.ConfiguracionModular.desde_dict({"desconocida": 1})
        with self.assertRaises(ValueError):
            extensiones.ConfiguracionModular.desde_dict({"plugins": ["cobol"]})
        with self.assertRaises(ValueError):
            extensiones.ConfiguracionModular.desde_dict({"incidencias": "sí"})
        with self.assertRaises(extensiones.NoImplementado):
            extensiones.ConfiguracionModular.desde_dict({"interfaz": "gui"})
        c = extensiones.ConfiguracionModular.desde_dict({"plugins": ["python", "rust"], "laboratorio": False})
        self.assertEqual((c.plugins, c.laboratorio, c.ejecucion_real), (("python", "rust"), False, False))
        with self.assertRaises(TypeError):
            extensiones.ConfiguracionModular(ejecucion_real=True)

    def test_migracion_y_candidatos_son_interfaces(self):
        r = extensiones.EvaluadorMigracion().evaluar("python", "rust", {"a.py": "x"})
        self.assertEqual((r["estado"], r["viable"]), ("no_implementado", None))
        self.assertTrue(r["lista_de_comprobacion"])
        with self.assertRaises(ValueError):
            extensiones.EvaluadorMigracion().evaluar("python", "cobol", {})
        with self.assertRaises(ValueError):
            extensiones.Candidato("c1", "v2e2", "x", estado="publicado")
        rep = extensiones.RepositorioCandidatos()
        for f, a in ((rep.proponer, (extensiones.Candidato("c1", "v2e2", "x"),)), (rep.archivar, ("c1",)),
                     (rep.comparar, ("a", "b"))):
            with self.assertRaises(extensiones.NoImplementado):
                f(*a)


# ============================ 10. integración opcional con el motor ==========================
from test_v2e import ejec_sim, guion_proyecto  # noqa: E402


class TestMotorConIncidencias(BaseReg):
    def correr(self, guion, reg="propio", **kw):
        r = self.reg if reg == "propio" else reg
        return motor.Motor(self.base, motor.AgentesMotorSimulados(guion), ejecutor.EjecutorSimulado(ejec_sim),
                           raiz_laboratorio=self.raiz, incidencias=r, **kw).ejecutar(config.TAREA_V2B)

    def test_sin_registro_el_motor_no_cambia(self):
        tmp = _comun.carpeta_temporal()
        self.addCleanup(tmp.cleanup)
        raiz = Path(tmp.name) / "equipo_f2"
        inf = motor.Motor(raiz / "datos_v2e2", motor.AgentesMotorSimulados(guion_proyecto()),
                          ejecutor.EjecutorSimulado(ejec_sim), raiz_laboratorio=raiz).ejecutar(config.TAREA_V2B)
        self.assertEqual(inf["estado_final"], "criterios_superados_en_simulacion")
        self.assertIsNone(inf["incidencias"])
        self.assertFalse((raiz / "datos_v2e2" / "incidencias").exists())

    def test_fallo_simulado_registrado_y_corregido_sin_verificar(self):
        inf = self.correr(guion_proyecto())
        self.assertEqual(inf["estado_final"], "criterios_superados_en_simulacion", inf["errores"])
        self.assertNotEqual(inf["resultado"], "verificado")
        self.assertEqual(len(inf["incidencias"]), 1)
        iid = inf["incidencias"][0]["id"]
        i = self.reg.obtener(iid)
        self.assertEqual(i["estado"], "corregida_sin_verificar")
        self.assertIn("test_no_muta", i["titulo"])
        self.assertTrue(i["origen"].startswith("motor:"))
        tipos = [(e["tipo"], e["resultado"]) for e in self.reg.evidencias(iid)]
        self.assertEqual(tipos, [("simulacion", "fallida"), ("simulacion", "superada")])
        self.assertEqual(auditoria.informe(self.reg)["resumen"]["verificadas"], 0)
        self.assertGreater(self.reg.con.execute("SELECT count(*) FROM archivos_afectados").fetchone()[0], 0)

    def test_reaparece_en_otra_ejecucion_y_se_reabre(self):
        iid = self.correr(guion_proyecto())["incidencias"][0]["id"]
        inf = self.correr(guion_proyecto(arreglar=False))
        self.assertEqual(inf["incidencias"][0]["id"], iid)                  # misma firma: misma incidencia
        self.assertEqual(self.reg.obtener(iid)["estado"], "reabierta")
        self.assertEqual(self.reg.reaperturas(iid), 1)
        self.assertEqual(next(h["actor"] for h in self.reg.historial(iid) if h["despues"] == "reabierta"), "motor")
        self.assertEqual(len(self.reg.listar()), 1)

    def test_bloqueo_de_A3_queda_como_observacion_pendiente(self):
        self.correr(guion_proyecto(bloquear=True))
        bloq = [i for i in self.reg.listar() if i["categoria"] == "revision"]
        self.assertEqual(len(bloq), 1)
        self.assertIn(bloq[0]["estado"], Inc.PENDIENTES)
        evs = self.reg.evidencias(bloq[0]["id"])
        self.assertTrue(evs and all((e["tipo"], e["actor"]) == ("observacion", "A3") for e in evs))

    def test_fallo_del_registro_no_detiene_la_tarea(self):
        self.reg.cerrar()                                             # cualquier uso dará sqlite3.ProgrammingError
        inf = self.correr(guion_proyecto())
        self.assertEqual(inf["estado_final"], "criterios_superados_en_simulacion")
        self.assertTrue(any(e.startswith("incidencias_desactivadas:") for e in inf["errores"]))
        self.assertIn("desactivado_por_fallo", inf["incidencias"])
        r2 = Inc.RegistroIncidencias(self.lab)
        self.addCleanup(r2.cerrar)
        self.assertEqual(r2.listar(), [])                             # nada registrado a medias


# ============================ 11. CLI y carpetas ===========================================
class TestCLI(unittest.TestCase):
    def setUp(self):
        self.tmp = _comun.carpeta_temporal()
        self.addCleanup(self.tmp.cleanup)
        self.t = Path(self.tmp.name)
        (self.t / "home").mkdir()
        (self.t / "tmp").mkdir()
        self.env = dict(os.environ, HOME=str(self.t / "home"), TMPDIR=str(self.t / "tmp"))

    def py(self, *a, env=None):
        return subprocess.run([sys.executable, "-B", "-I", str(RAIZ / "auditar.py"), *a], capture_output=True,
                              text=True, timeout=180, env=env or self.env)

    def test_recorrido_completo(self):
        r = self.py("demo-laboratorio")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("NINGÚN experimento ha ejecutado código", r.stdout)
        db = self.t / "tmp" / "equipo_f2" / "lab_v2f1" / "incidencias" / "incidencias.db"  # CAMBIO V2-E.6 (V2-E.5-r3: datos_v2e5r3)  # CAMBIO V2-E.6-r2 (V2-E.6: lab_v2e6)  # CAMBIO V2-E.6-r3 (V2-E.6-r2: lab_v2e6r2)  # CAMBIO V2-E.7 (V2-E.6-r3: lab_v2e6r3)  # CAMBIO V2-E.7-r2 (V2-E.7: lab_v2e7)  # CAMBIO V2-E.7-r3 (V2-E.7-r2: lab_v2e7r2)  # CAMBIO V2-F (V2-E.7-r3: lab_v2e7r3)  # CAMBIO V2-F.1 (V2-F: lab_v2f)

        def filas():
            con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            try:
                return [con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
                        for t in ("historial", "recalculos", "incidencias")]
            finally:
                con.close()
        antes = filas()
        self.assertEqual(self.py("plan").returncode, 0)
        self.assertEqual(filas(), antes)                              # «plan» es solo una vista previa
        for args, texto in ((("listar",), "INC-000001"), (("ver", "INC-000001"), '"evidencias"'),
                            (("prioridades",), "INC-000001"), (("plan",), "PROPUESTO"),
                            (("paquetes", "--tokens", "80"), "paquete 1"),
                            (("informe",), "Ninguna solución se ha verificado con pruebas reales."),
                            (("regresiones",), "")):     # CAMBIO V2-E.4-r2: la demo ya no crea una regresión
                                                           # con una sola reproducción
            with self.subTest(args=args):
                r = self.py(*args)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertIn(texto, r.stdout)
        self.assertEqual(list((self.t / "home").iterdir()), [])
        self.assertEqual(sorted(p.name for p in (self.t / "tmp" / "equipo_f2").iterdir()), ["lab_v2f1"])  # CAMBIO V2-E.6 (V2-E.5-r3: datos_v2e5r3)  # CAMBIO V2-E.6-r2 (V2-E.6: lab_v2e6)  # CAMBIO V2-E.6-r3 (V2-E.6-r2: lab_v2e6r2)  # CAMBIO V2-E.7 (V2-E.6-r3: lab_v2e6r3)  # CAMBIO V2-E.7-r2 (V2-E.7: lab_v2e7)  # CAMBIO V2-E.7-r3 (V2-E.7-r2: lab_v2e7r2)  # CAMBIO V2-F (V2-E.7-r3: lab_v2e7r3)  # CAMBIO V2-F.1 (V2-F: lab_v2f)
        self.assertTrue(list((self.t / "tmp" / "equipo_f2" / "lab_v2f1" / "incidencias" / "informes").glob("*.md")))  # CAMBIO V2-E.6 (V2-E.5-r3: datos_v2e5r3)  # CAMBIO V2-E.6-r2 (V2-E.6: lab_v2e6)  # CAMBIO V2-E.6-r3 (V2-E.6-r2: lab_v2e6r2)  # CAMBIO V2-E.7 (V2-E.6-r3: lab_v2e6r3)  # CAMBIO V2-E.7-r2 (V2-E.7: lab_v2e7)  # CAMBIO V2-E.7-r3 (V2-E.7-r2: lab_v2e7r2)  # CAMBIO V2-F (V2-E.7-r3: lab_v2e7r3)  # CAMBIO V2-F.1 (V2-F: lab_v2f)

    def test_entradas_invalidas(self):
        self.assertEqual(self.py("paquetes", "--tokens", "10").returncode, 2)
        self.assertEqual(self.py("ver", "../etc").returncode, 2)
        r = self.py("ver", "INC-999999")
        self.assertEqual(r.returncode, 2)
        self.assertIn("no existe", r.stderr)
        env = {k: v for k, v in self.env.items() if k != "TMPDIR"}
        r = self.py("listar", env=env)
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("Traceback", r.stderr)

    def test_ejecutar_v2_registra_incidencias(self):
        r = subprocess.run([sys.executable, "-B", "-I", str(RAIZ / "ejecutar_v2.py"), "--modo", "tarea_simulada"],
                           capture_output=True, text=True, timeout=180, env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("incidencias registradas:", r.stdout)
        self.assertIn("corregida_sin_verificar", r.stdout)
        self.assertTrue((self.t / "tmp" / "equipo_f2" / "lab_v2f1" / "incidencias" / "incidencias.db").is_file())  # CAMBIO V2-E.6 (V2-E.5-r3: datos_v2e5r3)  # CAMBIO V2-E.6-r2 (V2-E.6: lab_v2e6)  # CAMBIO V2-E.6-r3 (V2-E.6-r2: lab_v2e6r2)  # CAMBIO V2-E.7 (V2-E.6-r3: lab_v2e6r3)  # CAMBIO V2-E.7-r2 (V2-E.7: lab_v2e7)  # CAMBIO V2-E.7-r3 (V2-E.7-r2: lab_v2e7r2)  # CAMBIO V2-F (V2-E.7-r3: lab_v2e7r3)  # CAMBIO V2-F.1 (V2-F: lab_v2f)


class TestVersionYCarpetas(unittest.TestCase):
    def test_version_y_carpetas(self):
        import eq2
        self.assertEqual(eq2.VERSION, "f2-v2f1")  # CAMBIO V2-E.6 (V2-E.5-r3: f2-v2e5-r3)  # CAMBIO V2-E.6-r2 (V2-E.6: f2-v2e6-r1)  # CAMBIO V2-E.6-r3 (V2-E.6-r2: f2-v2e6-r2)  # CAMBIO V2-E.7 (V2-E.6-r3: f2-v2e6-r3)  # CAMBIO V2-E.7-r2 (V2-E.7: f2-v2e7-r1)  # CAMBIO V2-E.7-r3 (V2-E.7-r2: f2-v2e7-r2)  # CAMBIO V2-F (V2-E.7-r3: f2-v2e7-r3)  # CAMBIO V2-F.1 (V2-F: f2-v2f)
        self.assertEqual(config.CARPETA_V2E2, "datos_v2e2")
        self.assertIn("datos_v2e1", config.CARPETAS_ANTERIORES)
        self.assertIn(config.CARPETA_V2E2, config.CARPETAS_ANTERIORES)   # CAMBIO V2-E.3 (V2-E.2: assertNotIn)
        self.assertNotIn(config.CARPETA_V2F1, config.CARPETAS_ANTERIORES)  # CAMBIO V2-E.6 (V2-E.5-r3: CARPETA_V2E5R3)  # CAMBIO V2-E.6-r2 (V2-E.6: CARPETA_V2E6)  # CAMBIO V2-E.6-r3 (V2-E.6-r2: CARPETA_V2E6R2)  # CAMBIO V2-E.7 (V2-E.6-r3: config.CARPETA_V2E6R3)  # CAMBIO V2-E.7-r2 (V2-E.7: CARPETA_V2E7)  # CAMBIO V2-E.7-r3 (V2-E.7-r2: config.CARPETA_V2E7R2)  # CAMBIO V2-F (V2-E.7-r3: config.CARPETA_V2E7R3)  # CAMBIO V2-F.1 (V2-F: CARPETA_V2F)
        self.assertFalse(config.MODO_B_HABILITADO)


if __name__ == "__main__":
    unittest.main()
