"""V2-D: límites por fase, continuación sin duplicar, truncamiento semántico, compresión sin
pérdida de lo esencial, integridad antes de votar, esquema 4, métricas comparables, y la
arquitectura del ciclo autónomo con ejecutor SIMULADO (nunca se ejecuta código del modelo).

Backends SIMULADOS y FALSO llama-server (procesos y sockets reales). Nada de esto es Qwen.
"""
import json
import os
import random
import signal
import sqlite3
import subprocess
import sys
import threading
import unittest
from pathlib import Path
from unittest import mock

import _comun
from _v2 import EntornoV2
from eq2 import (archivos, ciclo, compresion, config, ejecutor, integridad, memoria, metricas,
                 orquestador, plataforma, prompts, protocolo, rutas, servidor, vigilancia)
from eq2.inferencia import BackendBase, ErrorInferencia, Respuesta

T = config.TAREA_V2B
RAIZ = _comun.RAIZ
_CLAVES = (("Vota sobre", "voto"), ("Analiza la tarea", "analisis"), ("Propón una solución", "propuesta"),
           ("Revisa la propuesta", "revision"), ("Responde a la revisión", "replica"))
CORTE = "```python\ndef ordenar(xs):\n    return sor"
FINAL = "ted(xs)\n```\nCaso: ordenar([3, 1]) -> [1, 3]\nFIN"


class BackendCont(BackendBase):
    """SIMULADO con continuación. guion(n, fase, agente, mensajes, es_cont) ->
    str | (texto, fr) | (texto, fr, tokens_prompt, tokens_gen) | Exception."""
    etiqueta = "SIMULADO"
    simulado = True

    def __init__(self, guion, continuacion=True):
        self.guion, self.llamadas = guion, []
        self.soporta_continuacion = continuacion
        self.permitir_continuacion = continuacion

    def completar(self, mensajes, max_tokens, plazo_s):
        es_cont = mensajes[-1]["role"] == "assistant"
        u = mensajes[-2]["content"] if es_cont else mensajes[-1]["content"]
        fase = next((f for c, f in _CLAVES if c in u), "?")
        ag = next((a for a in config.AGENTES if f"Eres {a}" in mensajes[0]["content"]),   # CAMBIO V2-E
                  next((a for a in config.AGENTES if f"Eres {a}," in u), "?"))
        self.llamadas.append({"fase": fase, "agente": ag, "max_tokens": max_tokens, "cont": es_cont,
                              "mensajes": mensajes})
        r = self.guion(len(self.llamadas), fase, ag, mensajes, es_cont)
        if isinstance(r, Exception):
            raise r
        if isinstance(r, str):
            r = (r, "stop")
        texto, fr, tp, tg = (tuple(r) + (None, None))[:4]
        return Respuesta(texto=texto, tokens_prompt=tp, tokens_gen=tg, finish_reason=fr,
                         ms_prompt=100.0, ms_gen=200.0)


def guion(fases=None, cont=None, voto="VOTO: aprobar\nRAZON: correcto"):
    """fases: {fase: respuesta}; cont: {fase: respuesta de la continuación}."""
    fases, cont = fases or {}, cont or {}

    def g(n, fase, ag, m, es_cont):
        if es_cont:
            return cont.get(fase, ("", "stop"))
        if fase == "voto":
            return voto(n, ag) if callable(voto) else voto
        return fases.get(fase, f"Texto de {fase} suficiente.\nFIN" if fase in ("propuesta", "replica")
                         else f"Texto de {fase} suficiente.")
    return g


class Lab(unittest.TestCase):
    def setUp(self):
        self.tmp = _comun.carpeta_temporal()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name) / "equipo_f2"
        self.base = self.raiz / "datos_v2d"

    def orq(self, be):
        v = vigilancia.Vigilante(lector_mem=lambda: 1_500_000, lector_bat=lambda: (80, False))
        return orquestador.Orquestador(self.base, be, v, reloj=_comun.Reloj(), raiz_laboratorio=self.raiz)

    def sql(self, q, p=()):
        con = sqlite3.connect(str(self.base / "datos" / "sesion.db"))
        try:
            return con.execute(q, p).fetchall()
        finally:
            con.close()

    def una(self, g, continuacion=True):
        be = BackendCont(g, continuacion)
        r = self.orq(be).run_deliberacion([T])
        return r, r["tareas"][0], be


# ============================ 1. integridad (puro) =======================================
class TestIntegridad(unittest.TestCase):
    def test_marca_fin(self):
        for t in ("x\nFIN", "x\nFIN.", "x\n**FIN**\n\n", "x\n  fin  "):
            self.assertTrue(integridad.marca_fin_presente(t), repr(t))
        for t in ("x", "FIN x", "x\nFINAL", ""):
            self.assertFalse(integridad.marca_fin_presente(t), repr(t))
        self.assertEqual(integridad.quitar_marca_fin("a\nb\nFIN\n"), "a\nb")
        self.assertEqual(integridad.quitar_marca_fin("a\nb"), "a\nb")

    def test_evaluar(self):
        e = integridad.evaluar
        self.assertEqual(e("propuesta", "x\nFIN", "length")["terminacion"], "truncada")
        self.assertEqual(e("propuesta", "x\nFIN", None)["terminacion"], "no_verificable")
        self.assertEqual(e("propuesta", "x\nFIN", "stop", recortado_al_guardar=True)["terminacion"], "truncada")
        r = e("propuesta", "```python\nx = 1\nFIN", "stop")         # truncamiento SEMÁNTICO con stop
        self.assertEqual((r["terminacion"], r["motivos"]), ("truncada", ["bloque_codigo_abierto"]))
        r = e("replica", "```python\nx = 1\n```", "stop")
        self.assertEqual((r["terminacion"], r["avisos"], r["sin_fin"]), ("completa", ["fin_no_marcado"], True))
        r = e("revision", "OBJECION: x", "stop")                    # sin marca FIN obligatoria
        self.assertEqual((r["terminacion"], r["avisos"]), ("completa", []))
        self.assertEqual(e("analisis", "```\nabierto", "stop")["terminacion"], "truncada")

    def test_necesita_continuacion(self):
        n = integridad.necesita_continuacion
        self.assertTrue(n("propuesta", integridad.evaluar("propuesta", CORTE, "length")))
        self.assertTrue(n("replica", integridad.evaluar("replica", "x", "stop")))         # sin FIN
        self.assertFalse(n("replica", integridad.evaluar("replica", "x\nFIN", "stop")))
        self.assertFalse(n("revision", integridad.evaluar("revision", "x", "length")))    # fase sin continuación
        self.assertFalse(n("replica", integridad.evaluar("replica", "x", None)))          # no verificable
        self.assertFalse(n("replica", integridad.evaluar("replica", "x", "stop", True)))  # recortado al guardar

    def test_unir_sin_duplicar(self):
        u = integridad.unir
        self.assertEqual(u(CORTE, FINAL)["texto"], CORTE + FINAL)
        self.assertEqual(u(CORTE, CORTE + FINAL)["texto"], CORTE + FINAL)                  # eco completo
        self.assertEqual(u(CORTE, "return sorted(xs)\n```\nFIN")["texto"],
                         CORTE[:-len("return sor")] + "return sorted(xs)\n```\nFIN")      # solape
        r = u("Propuesta: usar sorted() para no mutar la lista original y devolver", "Propuesta: usar "
              "sorted() para no mutar la lista, versión nueva")
        self.assertEqual((r["ok"], r["problema"]), (False, "reinicio"))
        r = u("bloque uno con mucho texto repetido aqui\nsegunda línea", "bloque uno con mucho texto repetido aqui")
        self.assertFalse(r["ok"])
        self.assertEqual(u("abc", "")["problema"], "continuacion_vacia")
        self.assertEqual(u("abc", None)["problema"], "continuacion_sin_texto")

    def test_unir_propiedad_nunca_duplica_un_sufijo(self):
        rnd = random.Random(7)
        palabras = ["def", "ordenar", "(xs):", "return", "sorted", "lista", "copia", "nueva", "\n"]
        for _ in range(300):
            texto = " ".join(rnd.choice(palabras) for _ in range(rnd.randint(8, 40)))
            corte = rnd.randint(1, len(texto) - 1)
            parcial, resto = texto[:corte], texto[corte:]
            solape = parcial[-rnd.randint(0, min(len(parcial), 30)):] if rnd.random() < .5 else ""
            r = integridad.unir(parcial, solape + resto)
            if r["ok"]:
                self.assertTrue(r["texto"].startswith(parcial))
                self.assertLessEqual(len(r["texto"]), len(parcial) + len(solape + resto))


# ============================ 2. compresión ==============================================
class TestCompresion(unittest.TestCase):
    TXT = ("Introducción larga " * 6 + "\n" + "\n".join(f"prosa de relleno número {i} " * 3 for i in range(15))
           + "\nOBJECION: falla con [] | EVIDENCIA: ordenar([]) debe dar []\nFALTA: tamaño máximo\n"
           "```python\ndef ordenar(xs):\n    return sorted(xs)\n```\nassert ordenar([2, 1]) == [1, 2]\n"
           "ACEPTADA: añado la lista vacía\nconclusión en prosa")

    def test_conserva_lo_esencial_y_respeta_el_cap(self):
        r = compresion.comprimir(self.TXT, 420)
        self.assertTrue(r["comprimido"])
        self.assertTrue(r["completo"])
        self.assertLessEqual(len(r["texto"]), 420)
        for esencial in ("OBJECION: falla con [] | EVIDENCIA: ordenar([]) debe dar []", "FALTA: tamaño máximo",
                         "```python", "def ordenar(xs):", "    return sorted(xs)",
                         "assert ordenar([2, 1]) == [1, 2]", "ACEPTADA: añado la lista vacía"):
            self.assertIn(esencial, r["texto"].split("\n"))
        self.assertIn(compresion.HUECO, r["texto"])
        self.assertGreater(r["lineas_descartadas"], 0)

    def test_si_lo_esencial_no_cabe_se_informa(self):
        r = compresion.comprimir(self.TXT, 80)
        self.assertFalse(r["completo"])
        self.assertGreater(r["esenciales_descartadas"], 0)
        self.assertLessEqual(len(r["texto"]), 80)

    def test_sin_compresion_si_cabe(self):
        r = compresion.comprimir("corto", 100)
        self.assertEqual((r["texto"], r["comprimido"]), ("corto", False))

    def test_linea_unica_larga_conserva_un_prefijo(self):
        r = compresion.comprimir("p" * 2000, 500)
        self.assertTrue(r["texto"].startswith("ppp"))
        self.assertLessEqual(len(r["texto"]), 500)
        self.assertEqual(r["lineas_partidas"], 1)

    def test_propiedad_lo_esencial_nunca_se_corta_por_la_mitad(self):
        rnd = random.Random(11)
        for _ in range(200):
            ls = []
            for _ in range(rnd.randint(3, 25)):
                k = rnd.random()
                ls.append(f"OBJECION: fallo {rnd.randint(0, 99)} | EVIDENCIA: caso {rnd.randint(0, 9)}"
                          if k < .2 else "prosa " * rnd.randint(1, 12))
            t = "\n".join(ls)
            cap = rnd.randint(40, len(t) + 10)
            r = compresion.comprimir(t, cap)
            self.assertLessEqual(len(r["texto"]), max(cap, len(t)) if not r["comprimido"] else cap)
            salida = r["texto"].split("\n")
            for l in salida:
                if l.startswith("OBJECION"):
                    self.assertIn(l, ls)                    # nunca una objeción partida
            if r["completo"]:
                for l in ls:
                    if l.startswith("OBJECION"):
                        self.assertIn(l, salida)


# ============================ 3. prompts y límites =======================================
class TestPromptsV2D(unittest.TestCase):
    def test_limites_por_fase(self):
        self.assertEqual(config.MAX_TOKENS, {"analisis": 160, "propuesta": 320, "revision": 160,
                                             "replica": 240, "voto": 120})
        self.assertEqual(config.MAX_LLAMADAS_TAREA, 7 + 2 * config.MAX_CONTINUACIONES_POR_FASE + 3)
        self.assertEqual(config.CTX, 1024)
        self.assertLessEqual(max(config.MAX_TOKENS.values()), config.TOPE_MAX_TOKENS)

    def test_la_revision_ve_la_propuesta_entera(self):
        """V2-C cortaba a 400 caracteres; una propuesta de 1000 llega entera a la revisión."""
        prop = "Propuesta\n```python\n" + "\n".join(f"x{i} = {i}" for i in range(140)) + "\n```"
        self.assertGreater(len(prop), 900)
        p = prompts.construir("revision", "A3", T, {"propuesta": prop[:1050]}, [])
        self.assertEqual((p.recortados, p.omitidos, p.compresion), ([], [], {}))
        self.assertIn(prop[:1050].rstrip(), p.usuario)

    def test_marca_fin_pedida(self):
        for f in ("propuesta", "replica"):
            self.assertIn("FIN", prompts.INSTRUCCION[f])
        for clave, fase in _CLAVES:
            self.assertIn(clave, prompts.INSTRUCCION[fase])

    def test_presupuesto_con_historial_maximo_y_ctx_2048(self):
        hist = {f: "x" * config.MAX_TURNO_CHARS for f in prompts.FASES_HIST}
        for ctx in config.CTX_PERMITIDOS:
            with mock.patch.object(config, "CTX", ctx):
                for _o, fase, ag in config.PLAN:
                    p = prompts.construir(fase, ag, "t" * config.MAX_TAREA_CHARS, hist, ["m" * 200] * 3,
                                          truncados=tuple(prompts.FASES_HIST))
                    self.assertLessEqual(p.tokens_est + p.max_gen + config.MARGEN_CTX, ctx)
        with mock.patch.object(config, "CTX", 2048):
            self.assertEqual(config.cap_bloque("voto", "propuesta_final"), 2600)

    def test_compresion_en_el_prompt_se_informa(self):
        rev = "\n".join(["prosa " * 20] * 6 + ["OBJECION: falla | EVIDENCIA: caso"])
        p = prompts.construir("replica", "A1", T, {"revision": rev, "propuesta": "p"}, [])
        self.assertIn("revision", p.compresion)
        self.assertIn("OBJECION: falla | EVIDENCIA: caso", p.usuario)


# ============================ 4. esquema 4 y recuento ====================================
class TestEsquema4(unittest.TestCase):
    def setUp(self):
        self.tmp = _comun.carpeta_temporal()
        self.addCleanup(self.tmp.cleanup)
        self.db = memoria.SesionDB(Path(self.tmp.name) / "s.db")
        self.addCleanup(self.db.cerrar)
        self.tid = self.db.crear_tarea(self.db.crear_sesion(), "t")

    def test_esquema(self):
        self.assertEqual(memoria.ESQUEMA_SESION, "6")                # CAMBIO V2-E.5: 5 -> 6 (fase aclaracion); V2-E: 4 -> 5

    def test_aprobar_una_propuesta_incompleta_es_imposible_en_la_base(self):
        for res in ("aprobada", "aprobada_con_cambios"):
            for prop in ("incompleta", "no_verificable"):
                with self.assertRaises(sqlite3.IntegrityError):
                    self.db.registrar_conclusion(self.tid, res, "{}", "x", propuesta_estado=prop,
                                                 fiabilidad="no_valida", fiabilidad_json="{}")

    def test_no_votada_exige_no_valida(self):
        for fia in ("normal", "reducida"):
            with self.assertRaises(sqlite3.IntegrityError):
                self.db.registrar_conclusion(self.tid, "no_votada", "{}", "x", propuesta_estado="completa",
                                             fiabilidad=fia, fiabilidad_json="{}")
        self.db.registrar_conclusion(self.tid, "no_votada", "{}", "x", propuesta_estado="incompleta",
                                     fiabilidad="no_valida", fiabilidad_json="{}")

    def test_tipo_de_turno(self):
        self.db.registrar_turno(self.tid, 1, "propuesta", "A1", "ok", "x", None, tipo="continuacion",
                                max_tokens=100, pared_s=1.5)
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.registrar_turno(self.tid, 2, "propuesta", "A1", "ok", "x", None, tipo="otro")

    def test_esquema_3_rechazado_en_solo_lectura(self):
        p = Path(self.tmp.name) / "v3.db"
        con = sqlite3.connect(str(p))
        con.executescript("CREATE TABLE meta(clave TEXT PRIMARY KEY, valor TEXT NOT NULL);"
                          "INSERT INTO meta VALUES('esquema','3');")
        con.commit()
        con.close()
        antes = p.read_bytes()
        self.assertEqual(memoria.esquema_sesion_de(p), "3")
        with self.assertRaises(memoria.EsquemaIncompatible):
            memoria.SesionDB(p)
        self.assertEqual(p.read_bytes(), antes)


class TestSesgoDeAutoria(unittest.TestCase):
    def test_depende_del_autor(self):
        d = protocolo.depende_del_autor
        self.assertTrue(d({"A1": ("aprobar", "x"), "A2": ("aprobar", "x"), "A3": ("rechazar", "y")}))
        self.assertFalse(d({"A1": ("aprobar", "x"), "A2": ("aprobar", "x"), "A3": ("aprobar", "x")}))
        self.assertFalse(d({"A1": ("rechazar", "x"), "A2": ("aprobar", "x"), "A3": ("rechazar", "y")}))
        self.assertFalse(d({"A1": ("abstencion", ""), "A2": ("aprobar", "x"), "A3": ("rechazar", "y")},
                           {"A1": "abstencion_forzada", "A2": "valido", "A3": "valido"}))


# ============================ 5. orquestador: continuación e integridad ==================
class TestContinuacion(Lab):
    def test_propuesta_cortada_se_continua_sin_duplicar(self):
        r, t, be = self.una(guion({"propuesta": (CORTE, "length")}, {"propuesta": (FINAL, "stop")}))
        self.assertEqual(t["terminaciones"]["propuesta"], "completa")
        self.assertEqual(r["llamadas_total"], 8)
        cont = [l for l in be.llamadas if l["cont"]]
        self.assertEqual(len(cont), 1)
        self.assertEqual(cont[0]["mensajes"][-1], {"role": "assistant", "content": CORTE})
        rev = [l for l in be.llamadas if l["fase"] == "revision"][0]["mensajes"][-1]["content"]
        self.assertIn("return sorted(xs)", rev)
        self.assertEqual(rev.count("def ordenar"), 1)                     # sin duplicados
        self.assertNotIn("\nFIN", rev)                                    # la marca no llega como contenido
        self.assertEqual(self.sql("SELECT fase, tipo, terminacion FROM turnos WHERE tipo='continuacion'"),
                         [("propuesta", "continuacion", "completa")])
        self.assertTrue(r["conclusion_valida"])
        self.assertEqual(t["resultado"], "aprobada")

    def test_replica_cortada_se_continua_y_se_vota(self):
        r, t, be = self.una(guion({"replica": (CORTE, "length")}, {"replica": (FINAL, "stop")}))
        self.assertEqual(t["terminaciones"]["replica"], "completa")
        self.assertEqual(len([l for l in be.llamadas if l["fase"] == "voto"]), 3)
        voto = [l for l in be.llamadas if l["fase"] == "voto"][0]["mensajes"][-1]["content"]
        self.assertIn("return sorted(xs)", voto)
        self.assertTrue(r["conclusion_valida"])

    def test_continuacion_que_vuelve_a_cortarse_impide_votar(self):
        r, t, be = self.una(guion({"replica": (CORTE, "length")}, {"replica": ("ted(xs) + [", "length")}))
        self.assertEqual(t["resultado"], "no_votada")
        self.assertEqual([l for l in be.llamadas if l["fase"] == "voto"], [])
        self.assertEqual(len([l for l in be.llamadas if l["cont"]]), config.MAX_CONTINUACIONES_POR_FASE)
        self.assertFalse(r["conclusion_valida"])
        self.assertEqual(self.sql("SELECT resultado, propuesta_estado, fiabilidad FROM conclusiones"),
                         [("no_votada", "incompleta", "no_valida")])
        self.assertEqual(self.sql("SELECT estado FROM tareas"), [("propuesta_incompleta",)])

    def test_reinicio_rechazado(self):
        larga = "Propuesta final: usar sorted() para no mutar la lista original y devolver una copia"
        r, t, _ = self.una(guion({"replica": (larga, "length")},
                                 {"replica": (larga[:40] + " versión distinta\nFIN", "stop")}))
        self.assertEqual(t["resultado"], "no_votada")
        self.assertTrue(any("continuacion_reinicio" in a for a in t["fiabilidad"]["advertencias"]))
        self.assertEqual(self.sql("SELECT motivo FROM turnos WHERE tipo='continuacion'"),
                         [("continuacion_reinicio",)])

    def test_sin_soporte_de_continuacion_no_se_continua(self):
        r, t, be = self.una(guion({"replica": (CORTE, "length")}), continuacion=False)
        self.assertEqual([l for l in be.llamadas if l["cont"]], [])
        self.assertEqual(t["resultado"], "no_votada")
        self.assertIn("continuacion_no_realizada:replica:backend_sin_continuacion",
                      t["fiabilidad"]["advertencias"])

    def test_sin_espacio_en_el_contexto_no_se_continua(self):
        r, t, be = self.una(guion({"replica": (CORTE, "length", 800, 200)}, {"replica": (FINAL, "stop")}))
        self.assertEqual([l for l in be.llamadas if l["cont"]], [])
        self.assertIn("continuacion_no_realizada:replica:sin_espacio_para_continuar",
                      t["fiabilidad"]["advertencias"])
        self.assertEqual(t["resultado"], "no_votada")

    def test_max_tokens_de_la_continuacion_se_ajusta_al_espacio(self):
        r, t, be = self.una(guion({"propuesta": (CORTE, "length", 600, 320)}, {"propuesta": (FINAL, "stop")}))
        c = [l for l in be.llamadas if l["cont"]][0]
        self.assertEqual(c["max_tokens"], min(config.MAX_TOKENS_CONTINUACION,
                                              config.CTX - 600 - 320 - config.MARGEN_CONTINUACION))

    def test_truncamiento_semantico_con_stop(self):
        r, t, be = self.una(guion({"propuesta": (CORTE + "ted(xs)", "stop")}, {"propuesta": ("\n```\nFIN", "stop")}))
        self.assertEqual(len([l for l in be.llamadas if l["cont"]]), 1)
        self.assertEqual(t["terminaciones"]["propuesta"], "completa")

    def test_sin_marca_fin_se_intenta_continuar_y_si_no_queda_aviso(self):
        r, t, be = self.una(guion({"propuesta": "```python\nx = 1\n```"}, {"propuesta": ("", "stop")}))
        self.assertEqual(len([l for l in be.llamadas if l["cont"] and l["fase"] == "propuesta"]), 1)
        self.assertEqual(t["terminaciones"]["propuesta"], "completa")
        self.assertIn("fin_no_marcado:propuesta", t["fiabilidad"]["advertencias"])

    def test_recortado_al_guardar_cuenta_como_truncado(self):
        r, t, be = self.una(guion({"replica": "a" * (config.MAX_TURNO_CHARS + 50) + "\nFIN"}))
        self.assertEqual(t["terminaciones"]["replica"], "truncada")
        self.assertEqual([l for l in be.llamadas if l["cont"]], [])
        self.assertEqual(t["resultado"], "no_votada")

    def test_limite_verificable_peor_caso_12_llamadas(self):
        """Propuesta y réplica cortadas + continuaciones cortadas... no: continuaciones que cierran,
        y los 3 votos truncados la primera vez: 7 + 2 + 3 = 12 = MAX_LLAMADAS_TAREA, nunca más."""
        intentos = {}

        def voto(n, ag):
            intentos[ag] = intentos.get(ag, 0) + 1
            return ("VOTO: aprobar\nRAZON: x", "length") if intentos[ag] == 1 else "VOTO: aprobar\nRAZON: ok"
        r, t, be = self.una(guion({"propuesta": (CORTE, "length"), "replica": (CORTE, "length")},
                                  {"propuesta": (FINAL, "stop"), "replica": (FINAL, "stop")}, voto))
        self.assertEqual(r["llamadas_total"], config.MAX_LLAMADAS_TAREA)
        self.assertEqual(len(be.llamadas), 12)
        self.assertEqual(t["estado"], "completa")
        tipos = [m["tipo"] for m in r["metricas"]["llamadas"]]
        self.assertEqual((tipos.count("normal"), tipos.count("continuacion"), tipos.count("reintento_voto")),
                         (7, 2, 3))

    def test_continuacion_nunca_mas_de_una_por_fase(self):
        r, t, be = self.una(guion({"propuesta": (CORTE, "length"), "replica": (CORTE, "length")},
                                  {"propuesta": ("ted(xs", "length"), "replica": ("ted(xs", "length")}))
        porfase = {}
        for l in be.llamadas:
            if l["cont"]:
                porfase[l["fase"]] = porfase.get(l["fase"], 0) + 1
        self.assertEqual(porfase, {"propuesta": 1, "replica": 1})
        self.assertEqual(t["resultado"], "no_votada")

    def test_fallo_en_la_continuacion_detiene_la_sesion(self):
        r, t, _ = self.una(guion({"replica": (CORTE, "length")}, {"replica": ErrorInferencia("http_500")}))
        self.assertEqual(r["motivo_fin"], "infraestructura_inferencia_fallida")

    def test_si_se_salta_la_verificacion_la_base_impide_aprobar(self):
        """Defensa en profundidad: aunque se votara una propuesta incompleta, la base NO deja
        guardar 'aprobada' (CHECK) y la sesión no presenta conclusión válida."""
        be = BackendCont(guion({"replica": (CORTE, "length")}), continuacion=False)
        o = self.orq(be)
        with mock.patch.object(orquestador.Orquestador, "_integridad_para_votar", return_value=[]):
            r = o.run_deliberacion([T])
        self.assertTrue(r["motivo_fin"].startswith("error_interno"))
        self.assertFalse(r["conclusion_valida"])
        self.assertEqual(self.sql("SELECT count(*) FROM conclusiones WHERE resultado LIKE 'aprobada%'"), [(0,)])

    def test_sesgo_de_autoria_decisivo_reduce_la_fiabilidad(self):
        def voto(n, ag):
            return "VOTO: rechazar\nRAZON: muta la lista" if ag == "A3" else "VOTO: aprobar\nRAZON: ok"
        r, t, _ = self.una(guion(voto=voto))
        self.assertEqual(t["resultado"], "aprobada")
        self.assertIn("decision_depende_del_voto_del_autor", t["fiabilidad"]["motivos"])
        self.assertEqual(t["fiabilidad"]["nivel"], "reducida")

    def test_metricas_y_resumen_comparables(self):
        r, t, _ = self.una(guion({"propuesta": (CORTE, "length", 100, 320)}, {"propuesta": (FINAL, "stop", 420, 20)}))
        m = r["metricas"]
        self.assertEqual(m["total"]["llamadas"], 8)
        self.assertEqual(m["por_tipo"]["continuacion"]["llamadas"], 1)
        self.assertEqual(set(m["por_fase"]), {"analisis", "propuesta", "revision", "replica", "voto"})
        self.assertIn("pared_s", m["total"])
        s = json.loads((self.base / "runs" / r["run_id"] / "summary.json").read_text())
        self.assertEqual(s["metricas"]["total"]["llamadas"], 8)
        self.assertEqual(len(s["tareas_sha256"][0]), 64)
        self.assertEqual(s["config"]["ctx"], 1024)
        self.assertEqual(self.sql("SELECT count(*) FROM turnos WHERE pared_s IS NULL"), [(0,)])

    def test_carpeta_v2c_intacta(self):
        d = self.raiz / "datos_v2c" / "datos"
        d.mkdir(parents=True)
        con = sqlite3.connect(str(d / "sesion.db"))
        con.executescript("CREATE TABLE meta(clave TEXT PRIMARY KEY, valor TEXT NOT NULL);"
                          "INSERT INTO meta VALUES('esquema','3');")
        con.commit()
        con.close()
        foto = lambda: sorted((str(p), p.stat().st_mtime_ns, p.read_bytes() if p.is_file() else b"")
                              for p in (self.raiz / "datos_v2c").rglob("*"))
        antes = foto()
        v = vigilancia.Vigilante(lector_mem=lambda: 1_500_000, lector_bat=lambda: (80, False))
        o = orquestador.Orquestador(self.raiz / "datos_v2c", BackendCont(guion()), v, raiz_laboratorio=self.raiz)
        with self.assertRaises(memoria.EsquemaIncompatible):
            o.run_deliberacion([T])
        self.assertEqual(foto(), antes)


# ============================ 6. servidor FALSO con prefill ==============================
AYUDA_PREFILL = _comun.AYUDA_COMPLETA + " --no-prefill-assistant"


class TestServidorFalsoV2D(EntornoV2):
    carpeta_datos = "datos_v2d"

    def run_(self, modo, prefill=True, **kw):
        srv_kw = kw.pop("srv_kw", {})
        if prefill:
            srv_kw.setdefault("ayuda_fn", lambda: AYUDA_PREFILL)
        be = self.backend(modo, srv_kw=srv_kw, **kw)
        res = self.orq_b(be).run_deliberacion([T])
        return be, res, (res["tareas"][0] if res["tareas"] else None)

    def reqs(self, res):
        return [json.loads(l[4:]) for l in self.log(res).splitlines() if l.startswith("REQ ")]

    def limpio(self, be):
        self.assertIsNotNone(be.srv.proc.poll())
        self.assertTrue(servidor.puerto_libre(be.srv.puerto))
        self.assertFalse((self.raiz / "datos_v2d" / "lock").exists())

    def test_continuacion_real_con_un_solo_servidor(self):
        be, res, t = self.run_("propuesta_y_replica_cortadas")
        self.assertTrue(res["backend_informe"]["informe"]["soporta_continuacion"])
        rq = self.reqs(res)
        cont = [r for r in rq if r["messages"][-1]["role"] == "assistant"]
        self.assertEqual(len(cont), 2)
        self.assertEqual(cont[0]["messages"][-1]["content"], CORTE)
        self.assertEqual((t["terminaciones"]["propuesta"], t["terminaciones"]["replica"]),
                         ("completa", "completa"))
        self.assertTrue(res["conclusion_valida"], t["fiabilidad"])
        log = self.log(res)
        self.assertEqual(log.count("ARGV "), 1)
        self.assertEqual({int(l.split()[1]) for l in log.splitlines() if l.startswith("ACTIVAS ")}, {1})
        self.limpio(be)

    def test_eco_del_servidor_no_duplica(self):
        be, res, t = self.run_("continuacion_eco")
        self.assertEqual(t["terminaciones"]["replica"], "completa")
        voto = [r for r in self.reqs(res) if "Vota sobre" in r["messages"][-1]["content"]][0]
        self.assertEqual(voto["messages"][-1]["content"].count("def ordenar"), 1)

    def test_reinicio_del_servidor_rechazado(self):
        be, res, t = self.run_("continuacion_reinicio")
        self.assertEqual(t["resultado"], "no_votada")
        self.limpio(be)

    def test_continuacion_cortada_no_se_vota(self):
        be, res, t = self.run_("continuacion_cortada")
        self.assertEqual(t["resultado"], "no_votada")
        self.assertFalse(res["conclusion_valida"])
        self.assertEqual([r for r in self.reqs(res) if "Vota sobre" in r["messages"][-1]["content"]], [])
        self.limpio(be)

    def test_http500_en_la_continuacion_detiene_y_limpia(self):
        be, res, t = self.run_("continuacion_http500")
        self.assertEqual(res["motivo_fin"], "infraestructura_inferencia_fallida")
        self.limpio(be)

    def test_sin_flag_de_prefill_no_se_envian_continuaciones(self):
        be, res, t = self.run_("replica_cortada", prefill=False)
        self.assertFalse(res["backend_informe"]["informe"]["soporta_continuacion"])
        self.assertEqual([r for r in self.reqs(res) if r["messages"][-1]["role"] == "assistant"], [])
        self.assertEqual(t["resultado"], "no_votada")
        self.limpio(be)

    def test_sin_continuacion_por_opcion(self):
        be = self.backend("replica_cortada", srv_kw={"ayuda_fn": lambda: AYUDA_PREFILL},
                          permitir_continuacion=False)
        res = self.orq_b(be).run_deliberacion([T])
        self.assertFalse(res["backend_informe"]["informe"]["soporta_continuacion"])

    def test_sin_fin_y_codigo_abierto(self):
        for modo in ("sin_fin", "codigo_abierto"):
            with self.subTest(modo):
                be, res, t = self.run_(modo)
                self.assertEqual(t["terminaciones"]["replica"], "completa")
                cont_rep = [r for r in self.reqs(res) if r["messages"][-1]["role"] == "assistant"
                            and "Responde a la revisión" in r["messages"][-2]["content"]]
                self.assertEqual(len(cont_rep), 1)

    def test_sigint_durante_la_continuacion(self):
        be = self.backend("replica_cortada", pausa=0.3, srv_kw={"ayuda_fn": lambda: AYUDA_PREFILL})
        orq = self.orq_b(be, instalar_senales=True)
        threading.Timer(1.2, lambda: os.kill(os.getpid(), signal.SIGINT)).start()
        res = orq.run_deliberacion([T])
        self.assertEqual(res["motivo_fin"], "senal")
        self.limpio(be)

    def test_proyecto_y_modelo_intactos(self):
        foto = lambda: sorted((str(p), p.stat().st_mtime_ns, p.read_bytes() if p.is_file() else b"")
                              for p in self.proyecto.rglob("*"))
        antes = foto()
        self.run_("propuesta_y_replica_cortadas")
        self.assertEqual(foto(), antes)


# ============================ 7. archivos, ejecutor y ciclo ===============================
class TestArchivos(unittest.TestCase):
    def test_extraer_validos(self):
        t = ("Texto\nARCHIVO: ordenar.py\n```python\ndef ordenar(xs):\n    return sorted(xs)\n```\n"
             "ARCHIVO: test_ordenar.py\n\n```\nassert True\n```")
        r = archivos.extraer(t)
        self.assertEqual([a["nombre"] for a in r["archivos"]], ["ordenar.py", "test_ordenar.py"])
        self.assertEqual(r["problemas"], [])
        self.assertEqual(r["archivos"][0]["contenido"], "def ordenar(xs):\n    return sorted(xs)\n")

    def test_rechazos(self):
        malos = ["../x.py", ".env", "a/b.py", "CON.py", "x.exe", "x.sh", "x", "nul.txt", "é.py",
                 "x.py.sh", "~x.py", "x" * 41 + ".py"]
        for n in malos:
            r = archivos.extraer(f"ARCHIVO: {n}\n```\nx\n```")
            self.assertEqual(r["archivos"], [], n)
            self.assertTrue(r["problemas"], n)
        r = archivos.extraer("ARCHIVO: a.py\n```\n" + "x" * (config.EJECUTOR_MAX_BYTES_ARCHIVO + 1) + "\n```")
        self.assertTrue(r["problemas"][0].startswith("demasiado_grande"))
        r = archivos.extraer("".join(f"ARCHIVO: a{i}.py\n```\nx\n```\n" for i in range(8)))
        self.assertEqual(len(r["archivos"]), config.EJECUTOR_MAX_ARCHIVOS)
        self.assertTrue(any(p.startswith("demasiados") for p in r["problemas"]))
        r = archivos.extraer("ARCHIVO: a.py\n```\nx\n```\nARCHIVO: A.py\n```\ny\n```")
        self.assertEqual(r["problemas"], ["duplicado:A.py"])
        self.assertEqual(archivos.extraer("ARCHIVO: a.py\n```\nx")["problemas"], ["bloque_sin_cerrar:a.py"])
        self.assertEqual(archivos.extraer("ARCHIVO: a.py\nsin bloque")["problemas"], ["sin_bloque_de_codigo:a.py"])
        self.assertEqual(archivos.extraer("ARCHIVO: a.py\n```\nx\x00\n```")["problemas"], ["byte_nulo:a.py"])
        self.assertEqual(archivos.extraer("nada")["problemas"], ["ningun_archivo"])


class TestEjecutor(unittest.TestCase):
    def setUp(self):
        self.tmp = _comun.carpeta_temporal()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name) / "equipo_f2"
        self.lab = rutas.Laboratorio(self.raiz, self.raiz / "datos_v2d")
        self.lab.crear_base()

    def test_politica(self):
        self.assertEqual(ejecutor.Politica().problemas(), [])
        for kw in ({"red": True}, {"privilegios": True}, {"aislamiento_requerido": False},
                   {"herramientas": ("bash",)}, {"max_archivos": 99}):
            self.assertTrue(ejecutor.Politica(**kw).problemas(), kw)

    def test_espacio_de_trabajo_confinado(self):
        e = ejecutor.EspacioTrabajo(self.lab, "r1", 1)
        e.escribir("a.py", "x = 1\n", ejecutor.Politica())
        self.assertTrue((self.raiz / "datos_v2d" / "runs" / "r1" / "ciclo" / "iter_1" / "a.py").is_file())
        for n in ("../a.py", "/etc/passwd", "a/b.py", ".env", "a.sh"):
            with self.assertRaises(ValueError):
                e.escribir(n, "x", ejecutor.Politica())
        with self.assertRaises(FileExistsError):
            e.escribir("a.py", "otra", ejecutor.Politica())              # nunca sobrescribe
        with self.assertRaises(ValueError):
            ejecutor.EspacioTrabajo(self.lab, "r1", 0)
        with self.assertRaises(ValueError):
            ejecutor.EspacioTrabajo(self.lab, "../fuera", 1)

    def test_ejecutor_no_disponible_y_rechazo(self):
        e = ejecutor.EspacioTrabajo(self.lab, "r2", 1)
        r = ejecutor.EjecutorNoDisponible().ejecutar(e, "pruebas_python", ejecutor.Politica())
        self.assertEqual((r.estado, r.simulado), ("no_disponible", False))
        r = ejecutor.EjecutorNoDisponible().ejecutar(e, "bash", ejecutor.Politica())
        self.assertEqual(r.estado, "rechazado")
        r = ejecutor.EjecutorSimulado(lambda i, a: {"estado": "ok"}).ejecutar(
            e, "pruebas_python", ejecutor.Politica(red=True))
        self.assertEqual(r.estado, "rechazado")
        with self.assertRaises(ValueError):
            ejecutor.Resultado("inventado", True)


def guion_ciclo(arreglar_en=2, archivos_ok=True):
    def g(paso, n, **kw):
        if paso == "plan":
            return "Plan: ordenar.py y test_ordenar.py"
        if paso == "revisar":
            return ("OBJECION: muta la lista | EVIDENCIA: xs.sort()" if ".sort()" in kw["archivos"]
                    else "SIN OBJECIONES: usa sorted")
        it = (n + 1) // 2
        cuerpo = "    xs.sort()\n    return xs" if it < arreglar_en else "    return sorted(xs)"
        if not archivos_ok:
            return "Aquí tienes la solución sin formato de archivos."
        return f"ARCHIVO: ordenar.py\n```python\ndef ordenar(xs):\n{cuerpo}\n```"
    return g


def ejec_por_texto(it, arch):
    muta = ".sort()" in arch.get("ordenar.py", "")
    return {"estado": "fallos" if muta else "ok", "pruebas_total": 1, "pruebas_fallidas": int(muta),
            "salida": "SIMULADO"}


class TestCiclo(unittest.TestCase):
    def setUp(self):
        self.tmp = _comun.carpeta_temporal()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name) / "equipo_f2"
        self.base = self.raiz / "datos_v2d"

    def ciclo(self, agentes, ej, **kw):
        return ciclo.Ciclo(self.base, agentes, ej, raiz_laboratorio=self.raiz, **kw)

    def test_corrige_y_cumple_criterios(self):
        c = self.ciclo(ciclo.AgentesSimulados(guion_ciclo(2)), ejecutor.EjecutorSimulado(ejec_por_texto))
        inf = c.ejecutar(T)
        self.assertEqual(inf["estado"], "criterios_cumplidos")
        self.assertEqual(inf["verificacion"], "simulada")
        self.assertEqual(len(inf["iteraciones"]), 2)
        self.assertFalse(inf["iteraciones"][0]["criterios"])
        d = self.base / "runs" / inf["run_id"] / "ciclo"
        self.assertTrue((d / "iter_1" / "ordenar.py").is_file())
        self.assertIn("sorted(xs)", (d / "iter_2" / "ordenar.py").read_text())
        tipos = [json.loads(l)["tipo"] for l in (d / "acciones.jsonl").read_text().splitlines()]
        self.assertEqual(tipos[0], "inicio")
        self.assertEqual(tipos[-1], "fin")
        self.assertEqual(tipos.count("ejecutar"), 2)
        self.assertEqual(json.loads((d / "informe.json").read_text())["estado"], "criterios_cumplidos")
        self.assertFalse((self.base / "lock").exists())

    def test_pruebas_superadas_no_bastan_si_A3_objeta(self):
        """Criterio doble: el ejecutor dice 'ok' pero A3 mantiene una objeción -> no se cumple."""
        retros = []

        def g(paso, n, **kw):
            if paso == "revisar":
                return "OBJECION: no valida tipos | EVIDENCIA: ordenar(None)"
            if paso == "generar":
                retros.append(kw["retro"])
            return "plan" if paso == "plan" else "ARCHIVO: ordenar.py\n```python\nx = 1\n```"
        inf = self.ciclo(ciclo.AgentesSimulados(g), ejecutor.EjecutorSimulado(
            lambda i, a: {"estado": "ok", "pruebas_total": 3, "pruebas_fallidas": 0})).ejecutar(T)
        self.assertEqual(inf["estado"], "limite_iteraciones")
        self.assertTrue(all(f["criterios"] is False for f in inf["iteraciones"]))
        self.assertIn("OBJECION: no valida tipos", retros[1])     # la objeción vuelve a A1

    def test_cero_pruebas_no_cuenta_como_exito(self):
        inf = self.ciclo(ciclo.AgentesSimulados(guion_ciclo(1)), ejecutor.EjecutorSimulado(
            lambda i, a: {"estado": "ok", "pruebas_total": 0})).ejecutar(T)
        self.assertNotEqual(inf["estado"], "criterios_cumplidos")

    def test_limite_de_iteraciones_duro(self):
        c = self.ciclo(ciclo.AgentesSimulados(guion_ciclo(99)), ejecutor.EjecutorSimulado(ejec_por_texto),
                       max_iteraciones=99)
        inf = c.ejecutar(T)
        self.assertEqual(inf["estado"], "limite_iteraciones")
        self.assertEqual(len(inf["iteraciones"]), config.EJECUTOR_MAX_ITERACIONES)
        self.assertEqual(inf["llamadas_agentes"], 1 + 2 * config.EJECUTOR_MAX_ITERACIONES)

    def test_limite_de_llamadas(self):
        c = self.ciclo(ciclo.AgentesSimulados(guion_ciclo(99)), ejecutor.EjecutorSimulado(ejec_por_texto),
                       max_llamadas=3)
        inf = c.ejecutar(T)
        self.assertEqual(inf["estado"], "limite_llamadas")
        self.assertLessEqual(inf["llamadas_agentes"], 3)

    def test_limite_de_tiempo(self):
        reloj = _comun.Reloj()

        class Lentos(ciclo.AgentesSimulados):
            def generar(s, *a, **k):
                reloj.avanzar(100)
                return super().generar(*a, **k)
        c = self.ciclo(Lentos(guion_ciclo(99)), ejecutor.EjecutorSimulado(ejec_por_texto),
                       seg_total=150, reloj=reloj)
        self.assertEqual(c.ejecutar(T)["estado"], "limite_tiempo")

    def test_sin_ejecutor_real_queda_sin_verificar(self):
        c = self.ciclo(ciclo.AgentesSimulados(guion_ciclo(1)), ejecutor.EjecutorNoDisponible())
        inf = c.ejecutar(T)
        self.assertEqual((inf["estado"], inf["motivo"], inf["verificacion"]),
                         ("sin_verificar", "ejecutor_no_disponible", "ninguna"))
        self.assertEqual(len(inf["iteraciones"]), 1)

    def test_salida_sin_archivos_cuenta_y_se_reintenta(self):
        c = self.ciclo(ciclo.AgentesSimulados(guion_ciclo(1, archivos_ok=False)),
                       ejecutor.EjecutorSimulado(ejec_por_texto))
        inf = c.ejecutar(T)
        self.assertEqual(inf["estado"], "limite_iteraciones")
        self.assertTrue(all(f["resultado"] == "sin_archivos" for f in inf["iteraciones"]))

    def test_stop_y_parada(self):
        (self.base).mkdir(parents=True)
        (self.base / "STOP").write_text("")
        inf = self.ciclo(ciclo.AgentesSimulados(guion_ciclo(2)), ejecutor.EjecutorSimulado(ejec_por_texto)).ejecutar(T)
        self.assertEqual((inf["estado"], inf["motivo"]), ("detenido", "stop_usuario"))
        (self.base / "STOP").unlink()
        c = self.ciclo(ciclo.AgentesSimulados(guion_ciclo(99)), ejecutor.EjecutorSimulado(ejec_por_texto))
        orig = c.agentes.revisar

        def revisar(*a, **k):
            c.solicitar_parada()
            return orig(*a, **k)
        c.agentes.revisar = revisar
        self.assertEqual(c.ejecutar(T)["estado"], "detenido")

    def test_candado_impide_dos_sesiones(self):
        (self.base / "lock").mkdir(parents=True)
        with self.assertRaises(FileExistsError):
            self.ciclo(ciclo.AgentesSimulados(guion_ciclo(1)), ejecutor.EjecutorSimulado(ejec_por_texto)).ejecutar(T)

    def test_politica_rechazada(self):
        inf = self.ciclo(ciclo.AgentesSimulados(guion_ciclo(1)), ejecutor.EjecutorSimulado(ejec_por_texto),
                         politica=ejecutor.Politica(red=True)).ejecutar(T)
        self.assertEqual(inf["estado"], "politica_rechazada")
        self.assertEqual(inf["iteraciones"], [])

    def test_carpeta_fuera_del_laboratorio(self):
        with self.assertRaises(ValueError):
            ciclo.Ciclo(Path(self.tmp.name) / "fuera", ciclo.AgentesSimulados(guion_ciclo(1)),
                        ejecutor.EjecutorNoDisponible(), raiz_laboratorio=self.raiz)

    def test_codigo_generado_nunca_se_ejecuta(self):
        """El «código» de los agentes intenta crear un archivo marcador y lanzar procesos: nada de
        eso ocurre. Un audit hook comprueba que no hay ni procesos ni exec/compile durante el ciclo."""
        marca = Path(self.tmp.name) / "PWNED"
        malicioso = (f"ARCHIVO: ordenar.py\n```python\nimport os\nos.system('touch {marca}')\n"
                     f"open({str(marca)!r}, 'w').write('x')\n__import__('subprocess').run(['touch', {str(marca)!r}])\n```")
        eventos, activo = [], {"on": True}

        def hook(ev, args):
            if activo["on"] and ev in ("subprocess.Popen", "os.system", "os.exec", "os.posix_spawn",
                                       "os.spawn", "exec", "compile"):
                eventos.append(ev)
        sys.addaudithook(hook)
        try:
            for ej in (ejecutor.EjecutorSimulado(lambda i, a: {"estado": "ok", "pruebas_total": 1}),
                       ejecutor.EjecutorNoDisponible()):
                c = self.ciclo(ciclo.AgentesSimulados(lambda p, n, **k: "SIN OBJECIONES: x" if p == "revisar"
                                                      else "plan" if p == "plan" else malicioso), ej)
                c.ejecutar(T)
        finally:
            activo["on"] = False
        self.assertFalse(marca.exists())
        self.assertEqual(eventos, [])

    def test_agentes_llm_con_backend_simulado(self):
        def g(n, fase, ag, m, es_cont):
            u = m[-1]["content"]
            if "plan breve" in u:
                return "Plan: ordenar.py"
            if "Escribe los archivos" in u:
                return "ARCHIVO: ordenar.py\n```python\ndef ordenar(xs):\n    return sorted(xs)\n```"
            return "SIN OBJECIONES: correcto"
        be = BackendCont(g, continuacion=False)
        inf = self.ciclo(ciclo.AgentesLLM(be), ejecutor.EjecutorSimulado(ejec_por_texto)).ejecutar(T)
        self.assertEqual(inf["estado"], "criterios_cumplidos")
        self.assertEqual(len(be.llamadas), 3)
        self.assertIn("DATOS_NO_CONFIABLES", be.llamadas[2]["mensajes"][-1]["content"])
        self.assertLessEqual(max(l["max_tokens"] for l in be.llamadas), config.TOPE_MAX_TOKENS)

    def test_error_de_inferencia(self):
        be = BackendCont(lambda *a: ErrorInferencia("http_500"), continuacion=False)
        inf = self.ciclo(ciclo.AgentesLLM(be), ejecutor.EjecutorSimulado(ejec_por_texto)).ejecutar(T)
        self.assertEqual((inf["estado"], inf["motivo"]), ("error_inferencia", "http_500"))
        self.assertFalse((self.base / "lock").exists())


# ============================ 8. métricas, plataforma y CLI ===============================
class TestMetricasYPlataforma(unittest.TestCase):
    def summary(self, version, pared, gen, sha=("a" * 64,)):
        return {"version": version, "tareas_sha256": list(sha) if sha else None,
                "backend_informe": {"informe": {"carga_s": 3.0, "peticiones": [
                    {"pared_s": p, "metricas": {"prompt_n": 100, "predicted_n": g, "prompt_ms": 1000,
                                                "predicted_ms": 9000}} for p, g in zip(pared, gen)]}}}

    def test_comparar(self):
        b = metricas.desde_summary(self.summary("f2-v2c-r1", [10] * 7, [100] * 7))
        n = metricas.desde_summary(self.summary("f2-v2d-r1", [11] * 8, [110] * 8))
        c = metricas.comparar(b, n)
        self.assertEqual(c["variacion_pct"]["pared_s"], round(100 * (88 - 70) / 70, 1))
        self.assertTrue(c["dentro_del_objetivo"])
        n2 = metricas.desde_summary(self.summary("f2-v2d-r1", [20] * 8, [110] * 8, sha=("b" * 64,)))
        c2 = metricas.comparar(b, n2)
        self.assertFalse(c2["dentro_del_objetivo"])
        self.assertTrue(any("NO son las mismas" in a for a in c2["avisos"]))
        c3 = metricas.comparar(metricas.desde_summary(self.summary("v", [1], [1], sha=None)), n)
        self.assertTrue(any("no se puede verificar" in a for a in c3["avisos"]))

    def test_agregar(self):
        a = metricas.agregar([{"fase": "voto", "tipo": "normal", "pared_s": 1, "tokens_gen": None}])
        self.assertEqual(a["total"]["llamadas"], 1)
        self.assertEqual(a["total"]["tokens_gen_ausentes"], 1)

    def test_comparar_metricas_cli_solo_lectura(self):
        tmp = _comun.carpeta_temporal()
        self.addCleanup(tmp.cleanup)
        d = Path(tmp.name)
        (d / "b.json").write_text(json.dumps(self.summary("f2-v2c-r1", [10] * 7, [100] * 7)))
        (d / "n.json").write_text(json.dumps(self.summary("f2-v2d-r1", [11] * 8, [110] * 8)))
        antes = sorted((p.name, p.read_bytes()) for p in d.iterdir())
        r = subprocess.run([sys.executable, "-B", "-I", str(RAIZ / "comparar_metricas.py"),
                            str(d / "b.json"), str(d / "n.json")], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("CUMPLIDO", r.stdout)
        self.assertEqual(sorted((p.name, p.read_bytes()) for p in d.iterdir()), antes)
        (d / "enlace.json").symlink_to(d / "b.json")
        r = subprocess.run([sys.executable, "-B", "-I", str(RAIZ / "comparar_metricas.py"),
                            str(d / "enlace.json"), str(d / "n.json")], capture_output=True, text=True, timeout=60)
        self.assertNotEqual(r.returncode, 0)

    def test_plataforma(self):
        self.assertEqual(plataforma.nombre({"PREFIX": "/data/data/com.termux/files/usr"}), "android_termux")
        c = plataforma.capacidades()
        for k in ("plataforma", "proc", "o_nofollow", "aislamiento_real"):
            self.assertIn(k, c)
        self.assertIsNone(c["aislamiento_real"])


class TestEjecutableV2D(unittest.TestCase):
    RUN = str(RAIZ / "ejecutar_v2.py")

    def setUp(self):
        self.tmp = _comun.carpeta_temporal()
        self.addCleanup(self.tmp.cleanup)
        self.t = Path(self.tmp.name)
        (self.t / "home").mkdir()
        (self.t / "tmp").mkdir()
        self.env = dict(os.environ, HOME=str(self.t / "home"), TMPDIR=str(self.t / "tmp"))

    def ej(self, *a):
        return subprocess.run([sys.executable, "-B", "-I", self.RUN, *a], capture_output=True, text=True,
                              timeout=120, env=self.env)

    def test_ciclo_simulado(self):
        r = self.ej("--modo", "ciclo_simulado")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("criterios_cumplidos", r.stdout)
        self.assertIn("ningún código se ha ejecutado", r.stdout)
        # CAMBIO V2-E: la carpeta de datos es datos_v2e (V2-E nunca escribe en datos_v2d)
        # CAMBIO V2-E.4: datos_v2e4 (V2-E.3: datos_v2e3)
        self.assertTrue(list((self.t / "tmp" / "equipo_f2" / "lab_v2f1" / "runs").glob("ciclo_*/ciclo/informe.json")))  # CAMBIO V2-E.6 (V2-E.5-r3: datos_v2e5r3)  # CAMBIO V2-E.6-r2 (V2-E.6: lab_v2e6)  # CAMBIO V2-E.6-r3 (V2-E.6-r2: lab_v2e6r2)  # CAMBIO V2-E.7 (V2-E.6-r3: lab_v2e6r3)  # CAMBIO V2-E.7-r2 (V2-E.7: lab_v2e7)  # CAMBIO V2-E.7-r3 (V2-E.7-r2: lab_v2e7r2)  # CAMBIO V2-F (V2-E.7-r3: lab_v2e7r3)  # CAMBIO V2-F.1 (V2-F: lab_v2f)
        self.assertEqual(list((self.t / "home").iterdir()), [])

    def test_carpetas_anteriores_y_ctx(self):
        for c in ("datos_v2", "datos_v2b", "datos_v2c", "datos_v2c/", "./datos_v2c"):
            r = self.ej("--modo", "deliberacion", "--iniciar-servidor-real", "--carpeta", c)
            self.assertNotEqual(r.returncode, 0, c)
        self.assertEqual(list((self.t / "tmp").iterdir()), [])
        self.assertNotEqual(self.ej("--modo", "comprobar", "--ctx", "4096").returncode, 0)
        r = self.ej("--modo", "comprobar", "--sin-help", "--ctx", "2048")
        self.assertIn("ctx: 2048", r.stdout)
        self.assertEqual(list((self.t / "tmp").iterdir()), [])

    def test_deliberacion_sin_modelo_usa_datos_v2d_y_sale_con_error(self):
        r = self.ej("--modo", "deliberacion", "--iniciar-servidor-real", "--sin-wake-lock")
        self.assertEqual(r.returncode, 1)
        self.assertIn("lab_v2f1", r.stdout)  # CAMBIO V2-E.6 (V2-E.5-r3: datos_v2e5r3)  # CAMBIO V2-E.6-r2 (V2-E.6: lab_v2e6)  # CAMBIO V2-E.6-r3 (V2-E.6-r2: lab_v2e6r2)  # CAMBIO V2-E.7 (V2-E.6-r3: lab_v2e6r3)  # CAMBIO V2-E.7-r2 (V2-E.7: lab_v2e7)  # CAMBIO V2-E.7-r3 (V2-E.7-r2: lab_v2e7r2)  # CAMBIO V2-F (V2-E.7-r3: lab_v2e7r3)  # CAMBIO V2-F.1 (V2-F: lab_v2f)
        self.assertIn("CONCLUSIÓN VÁLIDA: NO", r.stdout)
        self.assertEqual(sorted(p.name for p in (self.t / "tmp" / "equipo_f2").iterdir()), ["lab_v2f1"])  # CAMBIO V2-E.6 (V2-E.5-r3: datos_v2e5r3)  # CAMBIO V2-E.6-r2 (V2-E.6: lab_v2e6)  # CAMBIO V2-E.6-r3 (V2-E.6-r2: lab_v2e6r2)  # CAMBIO V2-E.7 (V2-E.6-r3: lab_v2e6r3)  # CAMBIO V2-E.7-r2 (V2-E.7: lab_v2e7)  # CAMBIO V2-E.7-r3 (V2-E.7-r2: lab_v2e7r2)  # CAMBIO V2-F (V2-E.7-r3: lab_v2e7r3)  # CAMBIO V2-F.1 (V2-F: lab_v2f)


if __name__ == "__main__":
    unittest.main()
