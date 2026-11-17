"""V2-C: votos truncados/no verificables, validación estricta, contradicciones (advertencias),
truncados de todas las fases, esquema 3, recuento y fiabilidad separados.

Backends SIMULADOS (BackendGuion) y FALSO llama-server (procesos y sockets reales).
Nada de esto es Qwen ni mide el modelo real.
"""
import json
import os
import signal
import sqlite3
import threading
import unittest
from pathlib import Path

import _comun
from _v2 import EntornoV2
from eq2 import config, contexto, memoria, orquestador, prompts, protocolo, sanea, servidor, vigilancia, votos
from eq2.inferencia import BackendBase, ErrorInferencia, Respuesta

T = config.TAREA_V2B
_CLAVES = (("Vota sobre", "voto"), ("Analiza la tarea", "analisis"), ("Propón una solución", "propuesta"),
           ("Revisa la propuesta", "revision"), ("Responde a la revisión", "replica"))


class BackendGuion(BackendBase):
    """Backend SIMULADO que controla finish_reason. guion(n, fase, agente, mensajes, max_tokens)
    -> str | (texto, finish_reason) | Exception."""
    etiqueta = "SIMULADO"
    simulado = True

    def __init__(self, guion):
        self.guion, self.llamadas = guion, []

    def completar(self, mensajes, max_tokens, plazo_s):
        u, sis = mensajes[-1]["content"], mensajes[0]["content"]
        fase = next((f for c, f in _CLAVES if c in u), "?")
        agente = next((a for a in config.AGENTES if f"Eres {a}" in sis),          # CAMBIO V2-E
                      next((a for a in config.AGENTES if f"Eres {a}," in u), "?"))
        self.llamadas.append({"fase": fase, "agente": agente, "max_tokens": max_tokens,
                              "mensajes": mensajes})
        r = self.guion(len(self.llamadas), fase, agente, mensajes, max_tokens)
        if isinstance(r, Exception):
            raise r
        texto, fin = (r, "stop") if isinstance(r, str) else r
        return Respuesta(texto=texto, tokens_prompt=None, tokens_gen=None, finish_reason=fin)


def guion_base(voto=lambda n, ag: "VOTO: aprobar\nRAZON: correcto", otras=None):
    otras = otras or {}

    def g(n, fase, ag, m, mt):
        if fase == "voto":
            return voto(n, ag)
        return otras.get(fase, f"[simulado] {fase} con texto suficiente para el bloque")
    return g


class Lab(unittest.TestCase):
    def setUp(self):
        self.tmp = _comun.carpeta_temporal()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name) / "equipo_f2"

    def orq(self, be):
        v = vigilancia.Vigilante(lector_mem=lambda: 1_500_000, lector_bat=lambda: (80, False))
        return orquestador.Orquestador(self.base, be, v, reloj=_comun.Reloj(), raiz_laboratorio=self.base)

    def sql(self, q, p=()):
        con = sqlite3.connect(str(self.base / "datos" / "sesion.db"))
        try:
            return con.execute(q, p).fetchall()
        finally:
            con.close()

    def una(self, guion):
        be = BackendGuion(guion)
        r = self.orq(be).run_deliberacion([T])
        return r, r["tareas"][0], be


# ============================ 1. evaluador de votos (puro) ===============================
class TestEvaluarVoto(unittest.TestCase):
    def test_truncado_nunca_es_valido_aunque_la_linea_voto_sea_correcta(self):
        for texto in ("VOTO: aprobar\nRAZON: bien", "VOTO: rechazar\nRAZON: falla", "VOTO: aprobar"):
            e = votos.evaluar_voto(texto, "length")
            self.assertEqual((e["estado"], e["postura"], e["motivo"]), ("truncado", None, "voto_truncado"))

    def test_finish_reason_desconocido_o_ausente(self):
        for fr in (None, "", "eos", "tool_calls", 1, "STOP"):
            e = votos.evaluar_voto("VOTO: aprobar\nRAZON: bien", fr)
            self.assertEqual(e["estado"], "no_verificable", fr)
            self.assertIsNone(e["postura"])

    def test_validos(self):
        for texto, p in (("VOTO: aprobar", "aprobar"), ("VOTO: aprobar\nRAZON: ok", "aprobar"),
                         ("voto: Rechazar\nrazon: falla con []", "rechazar"),
                         ("VOTO: abstencion\nRAZON: falta el tamaño máximo", "abstencion"),
                         ("VOTO: aprobar_con_cambios\nRAZON: añadir prueba", "aprobar_con_cambios")):
            e = votos.evaluar_voto(texto, "stop")
            self.assertEqual((e["estado"], e["postura"]), ("valido", p), texto)

    def test_invalidos_y_motivos(self):
        casos = {
            "VOTO: rechazar": "razon_obligatoria",
            "VOTO: aprobar_con_cambios\nRAZON:   ": "razon_obligatoria",
            "VOTO: aprobar\nRAZON: x VOTO: rechazar": "voto_repetido_en_razon",
            "VOTO: aprobar\nRAZON: " + "a" * 301: "razon_demasiado_larga",
            "VOTO: aprobar<|im_end|>": "voto_tokens_especiales",
            "Creo que VOTO: aprobar": "voto_formato_linea_voto",
            "VOTO: aprobar\nRAZON: a\nmás": "voto_formato_lineas",
            "VOTO: aprobar\nporque sí": "voto_formato_linea_razon",
            "RAZON: x\nVOTO: aprobar": "voto_formato_linea_voto",
            "VOTO: quizas": "voto_formato_linea_voto",
            "": "voto_formato_lineas",
        }
        for texto, motivo in casos.items():
            e = votos.evaluar_voto(texto, "stop")
            self.assertEqual((e["estado"], e["motivo"]), ("invalido", motivo), repr(texto))
            self.assertIsNone(e["postura"])
        self.assertEqual(votos.evaluar_voto(None, "stop")["motivo"], "voto_sin_texto")

    def test_razon_no_se_recorta_en_silencio(self):
        e = votos.evaluar_voto("VOTO: aprobar\nRAZON: " + "b" * 250, "stop")
        self.assertEqual(e["estado"], "valido")
        self.assertEqual(len(e["razon"]), 250)
        self.assertIn("razon_larga", e["advertencias"])
        self.assertIn("abstencion_sin_motivo", votos.evaluar_voto("VOTO: abstencion", "stop")["advertencias"])

    def test_terminacion(self):
        self.assertEqual([votos.terminacion(x) for x in ("stop", "length", None, "otro")],
                         ["completa", "truncada", "no_verificable", "no_verificable"])


class TestContradicciones(unittest.TestCase):
    """Advertencias por frases: se prueban VERDADEROS positivos, falsos positivos evitados y
    falsos negativos CONOCIDOS (documentados, no ocultos)."""
    POSITIVOS = [
        ("aprobar", "tiene un error con listas vacías"), ("aprobar", "Es incorrecta"),
        ("aprobar", "no cumple el requisito"), ("aprobar", "modifica la lista original"),
        ("aprobar", "hay que corregir el bucle"), ("aprobar", "hay varios fallos"),
        ("rechazar", "es correcta"), ("rechazar", "cumple todos los requisitos"),
        ("rechazar", "funciona correctamente"), ("rechazar", "no hay errores"),
        ("aprobar_con_cambios", "no requiere cambios"),
    ]
    NEGATIVOS = [   # no deben marcarse (falsos positivos evitados)
        ("aprobar", "no hay errores"), ("aprobar", "no tiene errores"), ("aprobar", "sin errores"),
        ("aprobar", "no modifica la lista original"), ("aprobar", "es correcta"),
        ("rechazar", "no es correcta"), ("rechazar", "tiene un error"), ("rechazar", "no cumple"),
        ("rechazar", "no funciona correctamente"), ("abstencion", "es correcta pero falta info"),
        ("aprobar_con_cambios", "añadir prueba vacía"),
    ]
    FALSOS_NEGATIVOS_CONOCIDOS = [   # contradicciones reales que las frases NO detectan
        ("aprobar", "la función falla si la lista contiene None"),   # «falla» suelto no está
        ("aprobar", "mutará la entrada"),
        ("rechazar", "está bien hecha"),
    ]

    def test_positivos(self):
        for p, r in self.POSITIVOS:
            self.assertTrue(votos.contradicciones(p, r), (p, r))

    def test_negativos(self):
        for p, r in self.NEGATIVOS:
            self.assertEqual(votos.contradicciones(p, r), [], (p, r))

    def test_falsos_negativos_documentados(self):
        for p, r in self.FALSOS_NEGATIVOS_CONOCIDOS:
            self.assertEqual(votos.contradicciones(p, r), [], (p, r))

    def test_contradiccion_es_advertencia_no_invalida(self):
        e = votos.evaluar_voto("VOTO: aprobar\nRAZON: tiene un error grave", "stop")
        self.assertEqual((e["estado"], e["postura"]), ("valido", "aprobar"))
        self.assertTrue(any(a.startswith("contradiccion:aprobar") for a in e["advertencias"]))


class TestSenalesCalidad(unittest.TestCase):
    REV = ("OBJECION: no prueba la lista vacía | EVIDENCIA: ordenar([]) debe devolver []\n"
           "Objeción: no indica la complejidad")

    def test_revision(self):
        r = votos.analizar_revision(self.REV)
        self.assertEqual((r["objeciones"], r["objeciones_sin_evidencia"], r["estructurada"]), (2, 1, True))
        self.assertTrue(votos.analizar_revision("SIN OBJECIONES: probé [] y [3,1]")["sin_objeciones"])
        self.assertFalse(votos.analizar_revision("Todo bien, me gusta.")["estructurada"])
        self.assertEqual(votos.analizar_revision("FALTA: tamaño máximo")["falta_info"], 1)

    def test_senales(self):
        ok = {"estado": "valido", "postura": "aprobar"}
        s = votos.senales_calidad({"revision": self.REV, "replica": "ACEPTADA: añado prueba"},
                                  {"A1": ok, "A2": ok, "A3": ok})
        self.assertIn("objeciones_sin_evidencia:1", s)
        self.assertIn("replica_no_responde_todas:1/2", s)
        self.assertIn("A3_aprueba_con_objeciones_sin_resolver", s)
        self.assertIn("unanimidad_pese_a_objeciones", s)
        s2 = votos.senales_calidad({"revision": self.REV,
                                    "replica": "ACEPTADA: a\nREBATIDA: sorted es O(n log n)"},
                                   {"A1": ok, "A2": ok, "A3": ok})
        self.assertNotIn("A3_aprueba_con_objeciones_sin_resolver", s2)
        self.assertEqual(votos.senales_calidad({"revision": "texto libre"}, {}),
                         ["revision_sin_formato_de_objeciones"])
        self.assertIn("informacion_insuficiente_senalada",
                      votos.senales_calidad({"analisis": "FALTA: si hay None",
                                             "revision": "SIN OBJECIONES: x"}, {}))


# ============================ 2. recuento y fiabilidad ===================================
class TestProtocolo(unittest.TestCase):
    V = {"A1": ("aprobar", "a"), "A2": ("aprobar_con_cambios", "cambio X"), "A3": ("rechazar", "r")}

    def test_un_voto_no_valido_no_puede_contar(self):
        for p in ("aprobar", "aprobar_con_cambios", "rechazar"):
            with self.assertRaises(ValueError):
                protocolo.contar({"A1": (p, ""), "A2": ("aprobar", ""), "A3": ("aprobar", "")},
                                 {"A1": "abstencion_forzada", "A2": "valido", "A3": "valido"})
        with self.assertRaises(ValueError):
            protocolo.contar(self.V, {"A1": "valido"})
        with self.assertRaises(ValueError):
            protocolo.contar(self.V, {"A1": "valido", "A2": "valido", "A3": "raro"})

    def test_compatible_sin_estados(self):
        self.assertEqual(protocolo.contar(self.V)["resultado"], protocolo.contar(
            self.V, {a: "valido" for a in self.V})["resultado"])

    def test_cambios_solo_de_votos_validos(self):
        v = {"A1": ("aprobar", "a"), "A2": ("aprobar", "b"), "A3": ("abstencion", "")}
        c = protocolo.contar(v, {"A1": "valido", "A2": "valido", "A3": "abstencion_forzada"})
        self.assertEqual(c["cambios_pendientes"], [])
        self.assertEqual(c["abstenciones_forzadas"], ["A3"])
        self.assertEqual(c["votos_validos"], 2)

    def term(self, **kw):
        t = {f: "completa" for f in ("analisis", "propuesta", "revision", "replica")}
        t.update(kw)
        return t

    def test_fiabilidad_normal_y_sesgo_como_aviso(self):
        c = protocolo.contar({"A1": ("aprobar", "x"), "A2": ("aprobar", "x"), "A3": ("aprobar", "x")})
        f = protocolo.fiabilidad(c, self.term(), {}, [])
        self.assertEqual((f["nivel"], f["impide_conclusion"], f["propuesta_estado"]),
                         ("normal", False, "completa"))
        self.assertTrue(f["advertencias"][0].startswith("sesgo_autoria"))
        self.assertEqual(c["resultado"], "aprobada")          # el recuento no cambia

    def test_replica_truncada_o_no_verificable_impide(self):
        c = protocolo.contar({"A1": ("aprobar", ""), "A2": ("aprobar", ""), "A3": ("aprobar", "")})
        for t, est in (("truncada", "incompleta"), ("no_verificable", "no_verificable"), (None, "no_verificable")):
            f = protocolo.fiabilidad(c, self.term(replica=t), {}, [])
            self.assertEqual((f["nivel"], f["impide_conclusion"], f["propuesta_estado"]),
                             ("no_valida", True, est), t)
            self.assertEqual(c["resultado"], "aprobada")      # se conserva el recuento

    def test_menos_de_dos_validos_por_forzadas_impide(self):
        v = {"A1": ("abstencion", ""), "A2": ("abstencion", ""), "A3": ("aprobar", "ok")}
        e = {"A1": "abstencion_forzada", "A2": "abstencion_forzada", "A3": "valido"}
        c = protocolo.contar(v, e)
        f = protocolo.fiabilidad(c, self.term(), {"A1": "voto_truncado", "A2": "voto_truncado"}, [])
        self.assertTrue(f["impide_conclusion"])
        self.assertEqual(c["resultado"], "sin_consenso")

    def test_abstenciones_voluntarias_no_impiden(self):
        v = {a: ("abstencion", "falta info") for a in config.AGENTES}
        c = protocolo.contar(v)
        f = protocolo.fiabilidad(c, self.term(), {}, [])
        self.assertEqual((c["resultado"], f["nivel"]), ("sin_consenso", "normal"))

    def test_reducida(self):
        c = protocolo.contar({"A1": ("aprobar", ""), "A2": ("aprobar", ""), "A3": ("abstencion", "")},
                             {"A1": "valido", "A2": "valido", "A3": "abstencion_forzada"})
        f = protocolo.fiabilidad(c, self.term(revision="truncada"), {"A3": "voto_truncado"}, [],
                                 motivos_extra=["propuesta_final_recortada_para_votante:A2"])
        self.assertEqual((f["nivel"], f["impide_conclusion"]), ("reducida", False))
        self.assertEqual(f["motivos"], ["revision_truncada", "abstencion_forzada:A3:voto_truncado",
                                        "propuesta_final_recortada_para_votante:A2"])


# ============================ 3. prompts ================================================
class TestPrompts(unittest.TestCase):
    def test_recordatorios_dirigidos_y_distintos(self):
        textos = set()
        for r in (True, "formato", "truncado", "no_verificable", "razon"):
            p = prompts.construir("voto", "A2", "tarea", {"replica": "x" * 80}, [], recordatorio=r)
            textos.add(p.usuario)
        self.assertEqual(len(textos), 4)                      # True == "formato"
        with self.assertRaises(ValueError):
            prompts.construir("voto", "A2", "tarea", {}, [], recordatorio="otro")

    def test_nota_de_truncado_fuera_de_los_datos_no_confiables(self):
        p = prompts.construir("voto", "A3", "tarea", {"replica": "propuesta " * 10}, [],
                              truncados=("replica", "analisis"))
        u = p.usuario
        self.assertEqual(u.count("NOTA DEL ORQUESTADOR"), 1)   # analisis no está en el prompt de voto
        self.assertLess(u.index("NOTA DEL ORQUESTADOR"), u.index(sanea.DELIM_ABRE + " fuente=propuesta_final"))
        self.assertNotIn("NOTA", prompts.construir("voto", "A3", "t", {"replica": "x" * 80}, []).usuario)

    def test_instrucciones_piden_objeciones_evidencia_y_falta_de_informacion(self):
        self.assertIn("OBJECION", prompts.INSTRUCCION["revision"])
        self.assertIn("EVIDENCIA", prompts.INSTRUCCION["revision"])
        self.assertIn("FALTA", prompts.INSTRUCCION["revision"])
        self.assertIn("REBATIDA", prompts.INSTRUCCION["replica"])
        self.assertIn("abstencion", prompts.INSTRUCCION["voto"])
        self.assertIn("no por acuerdo", prompts.INSTRUCCION["voto"])
        # las claves de fase que usan los backends simulados siguen presentes
        for clave, fase in _CLAVES:
            self.assertIn(clave, prompts.INSTRUCCION[fase])

    def test_presupuesto_con_historial_maximo_en_todas_las_fases(self):
        largo = "x" * config.MAX_TURNO_CHARS
        hist = {f: largo for f in prompts.FASES_HIST}
        mem = ["m" * 200] * config.MEMORIAS_POR_PROMPT
        for _o, fase, ag in config.PLAN:
            for rec in (False, "truncado"):
                p = prompts.construir(fase, ag, "t" * config.MAX_TAREA_CHARS, hist, mem,
                                      recordatorio=rec if fase == "voto" else False,
                                      truncados=tuple(prompts.FASES_HIST))
                self.assertLessEqual(p.tokens_est + p.max_gen + config.MARGEN_CTX, config.CTX)
        self.assertEqual(config.MAX_TOKENS["voto"], 120)
        self.assertEqual(config.MAX_LLAMADAS_TAREA, 12)      # CAMBIO V2-D: 7 + 2 continuaciones + 3
        self.assertEqual(config.CTX, 1024)


# ============================ 4. esquema 3 ==============================================
class TestEsquema3(unittest.TestCase):
    def setUp(self):
        self.tmp = _comun.carpeta_temporal()
        self.addCleanup(self.tmp.cleanup)
        self.d = Path(self.tmp.name)
        self.db = memoria.SesionDB(self.d / "s.db")
        self.addCleanup(self.db.cerrar)
        sid = self.db.crear_sesion()
        self.tid = self.db.crear_tarea(sid, "t")
        self.turno = self.db.registrar_turno(self.tid, 1, "voto", "A1", "invalido", "x", None,
                                             terminacion="truncada", motivo="voto_truncado")

    def test_esquema_es_el_vigente(self):
        """CAMBIO V2-D (antes test_esquema_es_3): el esquema vigente es el 4."""
        self.assertEqual(memoria.ESQUEMA_SESION, "6")                # CAMBIO V2-E.5: 5 -> 6 (fase aclaracion); V2-E: 4 -> 5
        self.assertEqual(memoria.esquema_sesion_de(self.d / "s.db"), "6")   # CAMBIO V2-E.5: 5 -> 6
        self.assertIsNone(memoria.esquema_sesion_de(self.d / "no.db"))

    def test_check_abstencion_forzada_exige_postura_abstencion_y_motivo(self):
        for p in ("aprobar", "aprobar_con_cambios", "rechazar"):
            with self.assertRaises(sqlite3.IntegrityError):
                self.db.registrar_voto(self.tid, "A1", self.turno, p, "", estado_voto="abstencion_forzada",
                                       motivo="voto_truncado")
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.registrar_voto(self.tid, "A1", self.turno, "abstencion", "", estado_voto="abstencion_forzada")
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.registrar_voto(self.tid, "A1", self.turno, "abstencion", "", estado_voto="raro")
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.registrar_voto(self.tid, "A1", self.turno, "abstencion", "", intentos=0)
        self.db.registrar_voto(self.tid, "A1", self.turno, "abstencion", "", estado_voto="abstencion_forzada",
                               motivo="voto_truncado", intentos=2, finish_reason="length")

    def test_check_propuesta_incompleta_obliga_no_valida(self):
        for est in ("incompleta", "no_verificable"):
            for fia in ("normal", "reducida"):
                with self.assertRaises(sqlite3.IntegrityError):
                    self.db.registrar_conclusion(self.tid, "aprobada", "{}", "x", propuesta_estado=est,
                                                 fiabilidad=fia, fiabilidad_json="{}")

    def test_conclusion_por_defecto_es_la_mas_conservadora(self):
        """CAMBIO V2-D: con los valores por defecto (propuesta no verificable) una conclusión
        'aprobada' ya ni siquiera se puede guardar (CHECK del esquema 4)."""
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.registrar_conclusion(self.tid, "aprobada", "{}", "x")
        self.db.registrar_conclusion(self.tid, "sin_consenso", "{}", "x")
        r = self.db.con.execute("SELECT propuesta_estado, fiabilidad FROM conclusiones").fetchone()
        self.assertEqual(tuple(r), ("no_verificable", "no_valida"))

    def test_terminacion_invalida_rechazada(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.registrar_turno(self.tid, 2, "voto", "A1", "ok", "x", None, terminacion="cortada")

    def test_base_de_esquema_2_rechazada(self):
        p = self.d / "v2.db"
        con = sqlite3.connect(str(p))
        con.executescript("CREATE TABLE meta(clave TEXT PRIMARY KEY, valor TEXT NOT NULL);"
                          "INSERT INTO meta VALUES('esquema','2');")
        con.commit()
        con.close()
        with self.assertRaises(memoria.EsquemaIncompatible):
            memoria.SesionDB(p)
        self.assertEqual(memoria.esquema_sesion_de(p), "2")

    def test_lectura_de_esquema_en_solo_lectura(self):
        p = self.d / "s.db"
        self.db.cerrar()
        antes = {q.name: (q.stat().st_size, q.stat().st_mtime_ns, q.read_bytes())
                 for q in self.d.iterdir()}
        self.assertEqual(memoria.esquema_sesion_de(p), memoria.ESQUEMA_SESION)   # CAMBIO V2-D
        despues = {q.name: (q.stat().st_size, q.stat().st_mtime_ns, q.read_bytes())
                   for q in self.d.iterdir()}
        self.assertEqual(antes, despues)                      # ni -wal ni -shm ni cambios
        self.db = memoria.SesionDB(p)
        self.addCleanup(self.db.cerrar)
        enlace = self.d / "enlace.db"
        enlace.symlink_to(p)
        with self.assertRaises(memoria.RutaInsegura):
            memoria.esquema_sesion_de(enlace)


class TestCarpetaAnteriorIntacta(Lab):
    """Una carpeta de V2-B (esquema 2) se rechaza ANTES de escribir nada (ni candado ni copias)."""

    def test_no_se_escribe_nada_en_una_carpeta_de_esquema_2(self):
        (self.base / "datos").mkdir(parents=True)
        p = self.base / "datos" / "sesion.db"
        con = sqlite3.connect(str(p))
        con.executescript("CREATE TABLE meta(clave TEXT PRIMARY KEY, valor TEXT NOT NULL);"
                          "INSERT INTO meta VALUES('esquema','2');")
        con.commit()
        con.close()
        (self.base / "datos" / "a1.db").write_bytes(b"")

        def foto():
            return sorted((str(q.relative_to(self.base)), q.stat().st_mtime_ns,
                           q.read_bytes() if q.is_file() else b"") for q in self.base.rglob("*"))
        antes = foto()
        be = BackendGuion(guion_base())
        for llamar in (lambda o: o.run_deliberacion([T]), lambda o: o.run([T]),
                       lambda o: o.run_una_llamada(T)):
            with self.assertRaises(memoria.EsquemaIncompatible):
                llamar(self.orq(be))
        self.assertEqual(foto(), antes)
        self.assertEqual(be.llamadas, [])


# ============================ 5. orquestador (simulado) =================================
class TestVotosEnElOrquestador(Lab):
    def test_voto_truncado_reintenta_con_recordatorio_y_luego_cuenta(self):
        def voto(n, ag):
            if ag == "A2" and not hasattr(voto, "hecho"):
                voto.hecho = True
                return ("VOTO: aprobar\nRAZON: cumple la tarea porque", "length")
            return "VOTO: aprobar\nRAZON: correcto"
        r, t, be = self.una(guion_base(voto))
        self.assertEqual(r["llamadas_total"], 8)
        self.assertEqual(t["votos"]["A2"]["estado_voto"], "valido")
        self.assertEqual(t["votos"]["A2"]["intentos"], 2)
        self.assertEqual(t["votos"]["A2"]["intentos_fallidos"], ["voto_truncado"])
        reintento = [l for l in be.llamadas if l["fase"] == "voto"][1]
        self.assertIn("se cortó por exceso de longitud", reintento["mensajes"][-1]["content"])
        self.assertEqual(t["fiabilidad"]["nivel"], "normal")
        self.assertTrue(r["conclusion_valida"])

    def test_voto_truncado_persistente_es_abstencion_obligatoria(self):
        def voto(n, ag):
            if ag == "A3":
                return ("VOTO: aprobar_con_cambios\nRAZON: añadir el caso de", "length")
            return "VOTO: aprobar\nRAZON: correcto"
        r, t, _ = self.una(guion_base(voto))
        v = t["votos"]["A3"]
        self.assertEqual((v["postura"], v["estado_voto"], v["motivo"], v["intentos"]),
                         ("abstencion", "abstencion_forzada", "voto_truncado", 2))
        self.assertEqual(t["cambios_pendientes"], [])          # el cambio truncado NO se cuenta
        self.assertEqual(t["resultado"], "aprobada")
        self.assertEqual(t["conteo"]["abstencion"], 1)
        self.assertEqual(t["fiabilidad"]["nivel"], "reducida")
        self.assertIn("abstencion_forzada:A3:voto_truncado", t["fiabilidad"]["motivos"])
        self.assertEqual(self.sql("SELECT postura, estado_voto, motivo, intentos, finish_reason "
                                  "FROM votos WHERE agente='A3'"),
                         [("abstencion", "abstencion_forzada", "voto_truncado", 2, "length")])
        self.assertEqual(self.sql("SELECT count(*) FROM turnos WHERE fase='voto' AND agente='A3' "
                                  "AND estado='invalido' AND terminacion='truncada' AND motivo='voto_truncado'"),
                         [(2,)])
        self.assertTrue(self.sql("SELECT 1 FROM eventos WHERE tipo='abstencion_forzada'"))

    def test_todos_truncados_impide_conclusion_y_respeta_el_limite(self):
        r, t, _ = self.una(guion_base(lambda n, ag: ("VOTO: aprobar\nRAZON: x", "length")))
        # CAMBIO V2-D: 7 + 3 reintentos = 10 (el tope por tarea es ahora 12 por las continuaciones)
        self.assertEqual(r["llamadas_total"], 7 + 3 * config.MAX_REINTENTOS_VOTO)
        self.assertLessEqual(r["llamadas_total"], config.MAX_LLAMADAS_TAREA)
        self.assertEqual(t["resultado"], "sin_consenso")
        self.assertTrue(t["fiabilidad"]["impide_conclusion"])
        self.assertFalse(r["conclusion_valida"])
        self.assertEqual(r["fiabilidad_global"], "no_valida")
        self.assertEqual(r["resultado_global"], "completo")     # el SISTEMA funcionó; la conclusión no vale

    def test_finish_reason_ausente_se_reintenta(self):
        r, t, _ = self.una(guion_base(lambda n, ag: ("VOTO: aprobar\nRAZON: ok", None)))
        self.assertTrue(all(v["motivo"] == "voto_no_verificable" for v in t["votos"].values()))
        self.assertFalse(r["conclusion_valida"])

    def test_rechazar_sin_razon_reintenta_con_recordatorio_de_razon(self):
        estado = {"n": 0}

        def voto(n, ag):
            estado["n"] += 1
            return "VOTO: rechazar" if estado["n"] == 1 else "VOTO: rechazar\nRAZON: muta la lista"
        r, t, be = self.una(guion_base(voto))
        self.assertEqual(t["votos"]["A2"]["intentos_fallidos"], ["razon_obligatoria"])
        self.assertIn("RAZON es obligatoria", [l for l in be.llamadas if l["fase"] == "voto"][1]
                      ["mensajes"][-1]["content"])
        self.assertEqual(t["resultado"], "rechazada")

    def test_contradiccion_solo_advierte(self):
        def voto(n, ag):
            return ("VOTO: aprobar\nRAZON: tiene un error con listas vacías" if ag == "A2"
                    else "VOTO: aprobar\nRAZON: correcto")
        r, t, _ = self.una(guion_base(voto))
        self.assertEqual(t["resultado"], "aprobada")
        self.assertEqual(t["votos"]["A2"]["estado_voto"], "valido")
        self.assertTrue(any(a.startswith("A2:contradiccion") for a in t["fiabilidad"]["advertencias"]))
        self.assertEqual(t["fiabilidad"]["nivel"], "normal")
        self.assertTrue(r["conclusion_valida"])
        adv = json.loads(self.sql("SELECT advertencias_json FROM votos WHERE agente='A2'")[0][0])
        self.assertTrue(adv)

    def test_fallo_de_inferencia_en_un_voto_detiene_la_sesion(self):
        """Defecto de V2-B corregido: antes se convertía en abstención y la tarea seguía."""
        def voto(n, ag):
            return ErrorInferencia("http_500") if ag == "A3" else "VOTO: aprobar\nRAZON: ok"
        be = BackendGuion(guion_base(voto))
        r = self.orq(be).run_deliberacion([T, "otra tarea"])
        self.assertEqual(r["motivo_fin"], "infraestructura_inferencia_fallida")
        self.assertEqual(r["tareas"][0]["estado"], "abortada")
        self.assertEqual(r["tareas_no_iniciadas"], 1)
        self.assertEqual(self.sql("SELECT count(*) FROM votos"), [(0,)])
        self.assertFalse(r["conclusion_valida"])


class TestTruncadosEnFases(Lab):
    def test_replica_truncada_marca_propuesta_incompleta_y_no_se_vota(self):
        """CAMBIO V2-D (antes ..._y_conserva_el_recuento): con la verificación de integridad
        previa, una propuesta final incompleta NO se vota (V2-C votaba y marcaba no_valida)."""
        r, t, be = self.una(guion_base(otras={"replica": ("Propuesta final: def ordenar(xs): return sor",
                                                         "length")}))
        f = t["fiabilidad"]
        self.assertEqual((f["propuesta_estado"], f["nivel"], f["impide_conclusion"]),
                         ("incompleta", "no_valida", True))
        self.assertEqual(t["resultado"], "no_votada")
        self.assertFalse(r["conclusion_valida"])
        self.assertEqual(self.sql("SELECT resultado, propuesta_estado, fiabilidad FROM conclusiones"),
                         [("no_votada", "incompleta", "no_valida")])
        texto = self.sql("SELECT texto_final FROM conclusiones")[0][0]
        self.assertTrue(texto.startswith("ADVERTENCIA: NO SE VOTÓ"))
        cab = t["texto_final_no_confiable"]
        self.assertIn("FIABILIDAD: no_valida", cab)
        self.assertIn("PROPUESTA_FINAL: incompleta", cab)
        self.assertEqual([l for l in be.llamadas if l["fase"] == "voto"], [])
        self.assertEqual(self.sql("SELECT count(*) FROM votos"), [(0,)])

    def test_replica_sin_finish_reason_es_no_verificable(self):
        r, t, _ = self.una(guion_base(otras={"replica": ("Propuesta final: sorted(xs)", None)}))
        self.assertEqual(t["fiabilidad"]["propuesta_estado"], "no_verificable")
        self.assertFalse(r["conclusion_valida"])

    def test_otras_fases_truncadas_reducen_y_se_registran(self):
        r, t, be = self.una(guion_base(otras={"analisis": ("Objetivo: ordenar", "length"),
                                              "revision": ("OBJECION: no trata", "length")}))
        self.assertEqual(t["terminaciones"], {"analisis": "truncada", "propuesta": "completa",
                                              "revision": "truncada", "replica": "completa"})
        self.assertEqual(t["fiabilidad"]["nivel"], "reducida")
        self.assertTrue(r["conclusion_valida"])
        self.assertEqual(self.sql("SELECT fase, motivo FROM turnos WHERE terminacion='truncada' ORDER BY orden"),
                         [("analisis", "respuesta_truncada"), ("revision", "respuesta_truncada")])
        prop = [l for l in be.llamadas if l["fase"] == "propuesta"][0]["mensajes"][-1]["content"]
        self.assertIn("el texto de 'analisis' se cortó", prop)
        self.assertEqual(self.sql("SELECT count(*) FROM eventos WHERE tipo='respuesta_truncada'"), [(2,)])

    def test_todas_las_fases_registran_terminacion(self):
        r, t, _ = self.una(guion_base())
        self.assertEqual(self.sql("SELECT count(*) FROM turnos WHERE terminacion IS NULL"), [(0,)])
        self.assertEqual(self.sql("SELECT DISTINCT terminacion FROM turnos"), [("completa",)])
        self.assertEqual(t["fiabilidad"]["nivel"], "normal")

    def test_propuesta_final_que_no_cabe_para_los_votantes_no_se_vota(self):
        """CAMBIO V2-D (antes ..._recortada_para_los_votantes -> reducida): 977 caracteres ya caben
        enteros (cap 400 -> 1300); una réplica que no cabe entera ya no se vota recortada."""
        r, t, _ = self.una(guion_base(otras={"replica": "Propuesta final. " + "detalle " * 120}))
        self.assertNotEqual(t["resultado"], "no_votada")
        r, t, be = self.una(guion_base(otras={"replica": "Propuesta final. " + "detalle " * 280}))
        self.assertEqual(t["resultado"], "no_votada")
        self.assertTrue(any(m.startswith("propuesta_final_no_cabe_para_votante")
                            for m in t["fiabilidad"]["motivos"]))
        self.assertEqual(t["fiabilidad"]["nivel"], "no_valida")

    def test_abstencion_voluntaria_por_falta_de_informacion_es_legitima(self):
        r, t, _ = self.una(guion_base(lambda n, ag: "VOTO: abstencion\nRAZON: falta saber si hay None"))
        self.assertEqual(t["resultado"], "sin_consenso")
        self.assertEqual(t["fiabilidad"]["nivel"], "normal")
        self.assertTrue(r["conclusion_valida"])               # «no sabemos» es una conclusión válida
        self.assertTrue(all(v["estado_voto"] == "valido" for v in t["votos"].values()))


# ============================ 6. servidor FALSO (procesos reales) ========================
class TestServidorFalsoV2C(EntornoV2):
    carpeta_datos = "datos_v2c"

    def run_(self, modo, tareas=(T,), **kw):
        be = self.backend(modo, **kw)
        res = self.orq_b(be).run_deliberacion(list(tareas))
        return be, res, (res["tareas"][0] if res["tareas"] else None)

    def limpio(self, be):
        self.assertIsNotNone(be.srv.proc.poll())
        self.assertTrue(servidor.puerto_libre(be.srv.puerto))
        self.assertFalse((self.raiz / "datos_v2c" / "lock").exists())

    def test_regresion_ejecucion_real_peticion_7_voto_de_A1_truncado(self):
        """Reproduce la 1.ª deliberación real: el voto de A1 (petición 7) terminó en 'length'.
        En V2-B contó; en V2-C se reintenta y, si persiste, es abstención obligatoria."""
        be, res, t = self.run_("voto_truncado_A1")
        self.assertEqual(res["llamadas_total"], 8)
        v = t["votos"]["A1"]
        self.assertEqual((v["postura"], v["estado_voto"], v["motivo"]),
                         ("abstencion", "abstencion_forzada", "voto_truncado"))
        self.assertFalse(t["sesgo_autoria"])                   # A1 no votó a favor de sí mismo
        self.assertEqual(t["resultado"], "aprobada")
        self.assertEqual(t["fiabilidad"]["nivel"], "reducida")
        self.assertTrue(res["conclusion_valida"])
        reqs = [json.loads(l[4:]) for l in self.log(res).splitlines() if l.startswith("REQ ")]
        self.assertEqual([r["max_tokens"] for r in reqs][-4:], [120, 120, 120, 120])
        self.limpio(be)

    def test_debate_con_objeciones_sin_resolver_genera_advertencias(self):
        be, res, t = self.run_("debate")
        adv = t["fiabilidad"]["advertencias"]
        for a in ("objeciones_sin_evidencia:1", "replica_no_responde_todas:1/2",
                  "A3_aprueba_con_objeciones_sin_resolver", "unanimidad_pese_a_objeciones",
                  "sesgo_autoria: A1 votó a favor de su propia propuesta"):
            self.assertIn(a, adv)
        self.assertEqual(t["resultado"], "aprobada")           # advertencias: no cambian el recuento
        _, res2, t2 = self.run_("debate_completo")
        self.assertNotIn("A3_aprueba_con_objeciones_sin_resolver", t2["fiabilidad"]["advertencias"])

    def test_replica_truncada_real(self):
        be, res, t = self.run_("replica_length")
        self.assertEqual(t["fiabilidad"]["propuesta_estado"], "incompleta")
        self.assertFalse(res["conclusion_valida"])
        en_disco = json.loads((self.raiz / "datos_v2c" / "runs" / res["run_id"]
                               / "informe_deliberacion.json").read_text())
        self.assertFalse(en_disco["conclusion_valida"])
        self.assertEqual(en_disco["fiabilidad_global"], "no_valida")
        self.limpio(be)

    def test_voto_sin_finish_reason_real(self):
        be, res, t = self.run_("voto_sin_fin")
        self.assertEqual(res["llamadas_total"], 10)
        self.assertFalse(res["conclusion_valida"])
        self.limpio(be)

    def test_http500_en_un_voto_detiene_la_sesion(self):
        be, res, t = self.run_("http500", (T, "otra"), en=6)
        self.assertEqual(res["motivo_fin"], "infraestructura_inferencia_fallida")
        self.assertEqual(res["tareas_no_iniciadas"], 1)
        self.limpio(be)

    def test_stop_durante_el_reintento_de_un_voto(self):
        be = self.backend("voto_truncado", pausa=0.3)
        orq = self.orq_b(be)
        n = {"i": 0}
        original = orq._votar

        def votar(*a, **kw):                                   # parar justo al empezar a votar
            n["i"] += 1
            if n["i"] == 1:
                tm = threading.Timer(0.45, lambda: (self.raiz / "datos_v2c" / "STOP").write_text(""))
                tm.start()
                self.addCleanup(tm.cancel)
            return original(*a, **kw)
        orq._votar = votar
        res = orq.run_deliberacion([T])
        self.assertEqual((res["estado"], res["motivo_fin"]), ("interrumpida", "stop_usuario"))
        self.assertEqual(self.sql("SELECT count(*) FROM votos"), [(0,)])
        self.assertEqual(self.sql("SELECT count(*) FROM conclusiones"), [(0,)])
        self.assertFalse(res["conclusion_valida"])
        self.limpio(be)

    def test_sigint_durante_la_deliberacion(self):
        be = self.backend("voto_truncado", pausa=0.3)
        orq = self.orq_b(be, instalar_senales=True)
        threading.Timer(1.0, lambda: os.kill(os.getpid(), signal.SIGINT)).start()
        res = orq.run_deliberacion([T])
        self.assertEqual(res["motivo_fin"], "senal")
        self.assertFalse(res["conclusion_valida"])
        self.limpio(be)

    def test_un_solo_servidor_y_secuencial_con_reintentos(self):
        be, res, t = self.run_("voto_truncado")
        log = self.log(res)
        self.assertEqual(log.count("ARGV "), 1)
        self.assertEqual([int(l.split()[1]) for l in log.splitlines() if l.startswith("ACTIVAS ")],
                         [1] * 10)

    def test_el_proyecto_y_el_modelo_no_se_tocan(self):
        antes = sorted((str(p), p.stat().st_mtime_ns, p.read_bytes() if p.is_file() else b"")
                       for p in self.proyecto.rglob("*"))
        self.run_("debate")
        despues = sorted((str(p), p.stat().st_mtime_ns, p.read_bytes() if p.is_file() else b"")
                         for p in self.proyecto.rglob("*"))
        self.assertEqual(antes, despues)


if __name__ == "__main__":
    unittest.main()
