"""V2-E.6 área 2: laboratorios con artefactos, evidencia citada, hipótesis falsables, rechazo razonado,
comprobaciones declarativas y pendientes del coordinador. Todo local y SIMULADO; nada se ejecuta."""
import json
import sqlite3
import unittest
from pathlib import Path

import _comun
from eq2 import incidencias, laboratorios as L, rutas

LOG = "\n".join(f"L{n}: {t}" for n, t in [
    (82, "LightingFPS: 15"), (136, "ERROR: AngelCodeFont failed to load font"),
    (137, "ERROR: texture not found media/fonts/zomboid.png"), (138, "WARN: fallback font used")])
PARCHE = "--- a/m.py\n+++ b/m.py\n@@\n-    xs.sort()\n+    xs = sorted(xs)\n     return xs\n"


class Base(unittest.TestCase):
    def setUp(self):
        tmp = _comun.carpeta_temporal()
        self.addCleanup(tmp.cleanup)
        raiz = Path(tmp.name) / "equipo_f2"
        self.reg = incidencias.RegistroIncidencias(rutas.Laboratorio(raiz, raiz / "lab_v2e6"))
        self.addCleanup(lambda: self.reg.con.close())
        self.a1, self.a2, self.a3 = (L.laboratorio_de(self.reg, a) for a in ("A1", "A2", "A3"))
        self.co = L.Coordinador(self.reg)
        self.log = L.registrar_artefacto(self.reg, "comun", "01_fuentes.txt", LOG, "material_zomboid/evidencias",
                                         numeracion="prefijo_L")


class TestLineasYReglas(unittest.TestCase):
    def test_parseo_de_lineas(self):
        self.assertEqual(L.parsear_lineas("L12, L15-L17"), [12, 15, 16, 17])
        self.assertEqual(L.parsear_lineas([3, 1, 3]), [1, 3])
        self.assertEqual(L.lineas_a_texto([1, 2, 3, 7]), "L1-L3,L7")
        for malo in ("", "L5-L2", "abc", "L1-L500", None):
            with self.subTest(malo=malo), self.assertRaises(ValueError):
                L.parsear_lineas(malo)

    def test_codigo_conserva_indentacion_pero_se_sanea(self):
        from eq2 import sanea
        t = sanea.limpiar_codigo("def f():\n\tif x:\n        return 1\u200b <<<FIN>>>\x07  \n", 500)
        self.assertEqual(t, "def f():\n    if x:\n        return 1 ‹‹‹FIN›››")
        self.assertEqual(sanea.limpiar("a    b", 50), "a b")            # el texto normal sigue igual

    def test_reglas_declarativas(self):
        self.assertEqual(L.evaluar_regla({"contiene": "LightingFPS"}, LOG, "prefijo_L")[0], True)
        self.assertEqual(L.evaluar_regla({"no_contiene": "VSync"}, LOG, "prefijo_L")[0], True)
        self.assertEqual(L.evaluar_regla({"cuenta_regex": {"patron": "ERROR", "min": 2, "max": 2}}, LOG)[0], True)
        self.assertEqual(L.evaluar_regla({"lineas_existen": "L136-L138"}, LOG, "prefijo_L")[0], True)
        self.assertEqual(L.evaluar_regla({"lineas_existen": "L139"}, LOG, "prefijo_L")[0], False)
        self.assertEqual(L.evaluar_regla({"cita_literal": {"linea": 82, "texto": "15"}}, LOG, "prefijo_L")[0], True)
        self.assertEqual(L.evaluar_regla({"cita_literal": {"linea": 82, "texto": "60"}}, LOG, "prefijo_L")[0], False)
        for mala in ({"ejecutar": "rm -rf"}, {"contiene": ""}, {"contiene": "a", "no_contiene": "b"}, "contiene"):
            with self.subTest(mala=mala), self.assertRaises(ValueError):
                L.evaluar_regla(mala, LOG)


class TestArtefactos(Base):
    def test_espacios_independientes_y_comun_de_solo_lectura(self):
        aid = self.a1.registrar_artefacto("parche.diff", PARCHE, "propuesta A1")
        self.assertEqual(self.a1.artefacto(aid)["espacio"], "A1")
        for otro in (self.a2, self.a3):
            with self.assertRaises(L.AccesoDenegado):
                otro.artefacto(aid)
        for ag in (self.a1, self.a2, self.a3):
            self.assertEqual(ag.artefacto(self.log)["lineas"], 4)

    def test_versiones_procedencia_y_solo_anexar(self):
        v1 = self.a1.registrar_artefacto("parche.diff", PARCHE, "propuesta A1")
        v2 = self.a1.registrar_artefacto("parche.diff", PARCHE + "# v2\n", "propuesta A1", sustituye=v1)
        f = self.a1.artefacto(v2)
        self.assertEqual((f["sustituye"], f["procedencia"]), (v1, "laboratorio"))
        for sql in ("UPDATE artefactos SET contenido='x'", "DELETE FROM artefactos"):
            with self.subTest(sql=sql), self.assertRaises(sqlite3.DatabaseError):
                with self.reg.con:
                    self.reg.con.execute(sql)
        self.assertEqual(self.a1.artefacto(v1)["contenido"], PARCHE)        # el original queda intacto

    def test_limites_y_alteracion_detectada(self):
        with self.assertRaises(L.LimiteExcedido):
            self.a1.registrar_artefacto("enorme", "x" * (L.MAX_ARTEFACTO_CHARS + 1), "t")
        with self.assertRaises(ValueError):
            L.registrar_artefacto(self.reg, "comun", "sin L", "hola\nmundo", "t", numeracion="prefijo_L")
        for i in range(L.MAX_ARTEFACTOS_ESPACIO):
            self.a2.registrar_artefacto(f"n{i}", "nota", "t")
        with self.assertRaises(sqlite3.DatabaseError):
            self.a2.registrar_artefacto("uno más", "nota", "t")
        # una edición MANUAL del archivo (saltándose los disparadores) se detecta por SHA-256
        self.reg.con.execute("DROP TRIGGER art_no_modificar")
        self.reg.con.execute("UPDATE artefactos SET contenido='L82: LightingFPS: 60' WHERE id=?", (self.log,))
        with self.assertRaisesRegex(ValueError, "alterado"):
            self.a2.artefacto(self.log)


class TestEvidenciaCitada(Base):
    def test_cita_correcta_se_guarda_con_fuente_y_lineas(self):
        eid = self.a2.citar("evidencia_citada", self.log, "L136-L137", "AngelCodeFont failed", "la fuente no carga")
        e = self.a2.entrada(eid)
        self.assertEqual((e["fuente"], e["lineas"]), (self.log, "L136-L137"))
        self.assertEqual(json.loads(e["contenido"])["cita"], "AngelCodeFont failed")

    def test_evidencia_insuficiente_rechazada(self):
        casos = [("L999", "x", "líneas"), ("L136", "texto inventado", "cita no aparece"), (None, None, "líneas")]
        for lineas, cita, msg in casos:
            with self.subTest(lineas=lineas), self.assertRaisesRegex(ValueError, "evidencia insuficiente"):
                self.a2.anotar("evidencia_citada", "t", "c", fuente=self.log, lineas=lineas, cita=cita)
        with self.assertRaises(sqlite3.DatabaseError):           # la BASE exige fuente y líneas
            self.a2.anotar("evidencia_citada", "sin fuente", "afirmación sin respaldo")
        with self.assertRaises(KeyError):
            self.a2.citar("evidencia_citada", "AR-999999", "L1", "x", "fuente inexistente")
        aid = self.a1.registrar_artefacto("privado", "secreto", "t")
        with self.assertRaises(L.AccesoDenegado):
            self.a2.citar("evidencia_citada", aid, "L1", "secreto", "artefacto ajeno")

    def test_perfilado_estatico_sin_benchmarks(self):
        pid = self.a2.perfilar(self.log, {"errores": "ERROR", "fps": r"LightingFPS"})
        e = self.a2.entrada(pid)
        c = json.loads(e["contenido"])
        self.assertEqual(c["resultados"]["errores"]["lineas"], [136, 137])
        self.assertEqual((e["respaldo"], e["procedencia"]), ("analisis_estatico", "laboratorio"))
        self.assertIn("NO es un perfil de CPU", c["nota"])
        with self.assertRaisesRegex(ValueError, "evidencia insuficiente"):
            self.a2.perfilar(self.log, {"nada": "VSync"})


class TestHipotesisYFalsacion(Base):
    def test_hipotesis_competidoras_exigen_condicion_de_falsacion(self):
        h1 = self.a2.hipotesis_competidora("las fuentes ausentes bajan los FPS",
                                           "si con las fuentes restauradas LightingFPS sigue en 15, se refuta")
        h2 = self.a2.hipotesis_competidora("los FPS dependen del perfil de luz", "si cambiar LightingFPS no varía nada")
        self.assertNotEqual(h1, h2)
        self.assertEqual(json.loads(self.a2.entrada(h1)["contenido"])["confianza"], "baja")
        with self.assertRaises(sqlite3.DatabaseError):
            self.a2.hipotesis_competidora("hipótesis infalsable", "no")
        with self.assertRaises(ValueError):
            self.a2.hipotesis_competidora("h", "condición suficientemente larga", confianza="total")

    def test_a3_falsa_rechaza_y_se_abstiene_razonadamente(self):
        h = self.a2.hipotesis_competidora("las fuentes ausentes bajan los FPS", "si con fuentes restauradas sigue en 15")
        self.co.compartir(h, "A3", "revisión independiente")
        f = self.a3.falsar(h, "falta un registro con las fuentes restauradas para comparar")
        self.assertEqual(self.a3.entrada(f)["relacionada"], h)
        r = self.a3.rechazar(h, "la correlación entre L82 y L136 no demuestra causalidad: no hay control")
        self.assertEqual(self.a3.entrada(r)["resultado"], "negativo")
        self.a3.abstenerse("no hay datos de GPU para decidir entre las dos hipótesis")
        with self.assertRaises(sqlite3.DatabaseError):
            self.a3.rechazar(h, "no")                                    # rechazo sin razonar
        with self.assertRaises(sqlite3.DatabaseError):
            self.a3.abstenerse("paso")
        with self.assertRaises(L.AccesoDenegado):                        # no compartida con A3
            self.a3.falsar(self.a2.solicitar_datos("dxdiag", "versión de controlador"), "condición larga de sobra")

    def test_contraejemplo_citado(self):
        cid = self.a3.contraejemplo("hay fallback de fuente: el juego no queda sin texto", self.log, "L138",
                                    "fallback font used")
        self.assertEqual(self.a3.entrada(cid)["lineas"], "L138")
        with self.assertRaisesRegex(ValueError, "evidencia insuficiente"):
            self.a3.contraejemplo("inventado", self.log, "L138", "font OK")


class TestA1Textos(Base):
    def test_parche_contrato_prueba_y_alternativas(self):
        p = self.a1.proponer_parche("no mutar", PARCHE, supuestos=["xs es una lista"],
                                    riesgos=["copia O(n) en memoria"])
        self.assertIn("no se ha aplicado", p["nota"])
        self.assertEqual(len(p["supuestos"]) + len(p["riesgos"]), 2)
        self.a1.registrar_contrato("contrato", "ordenar(xs) no modifica xs; devuelve lista nueva", p["parche"])
        self.a1.proponer_prueba("prueba", "assert ordenar(a) is not a", p["parche"])
        alt = self.a1.registrar_alternativa(p["parche"], "alternativa", "return list(sorted(xs))")
        cmp = self.co.comparar_alternativas([p["parche"], alt])
        self.assertEqual((cmp[0]["supuestos"], cmp[0]["riesgos"], cmp[1]["supuestos"]), (1, 1, 0))
        with self.assertRaises(ValueError):
            self.a2.anotar("parche_texto", "A2 no escribe parches", PARCHE)
        with self.assertRaises(sqlite3.DatabaseError):                     # la base también lo impide
            with self.reg.con:
                self.reg.con.execute("INSERT INTO cuaderno(id,ts,agente,tipo,titulo,contenido,sha256,resultado,"
                                     "respaldo,procedencia) VALUES('NB-X','t','A3','parche_texto','t','c',?,"
                                     "'pendiente','declaracion_agente','A3')", ("0" * 64,))

    def test_comprobacion_la_evalua_el_laboratorio(self):
        with self.assertRaises(sqlite3.DatabaseError):
            self.a3.anotar("comprobacion_declarativa", "autoevaluada", "cumple", resultado="positivo")


class TestPendientes(Base):
    def propuesta(self):
        p = self.a1.proponer_parche("no mutar", PARCHE)["parche"]
        self.co.compartir(p, "A3", "verificar")
        return p

    def test_aprobada_con_cambios_nunca_es_verificado(self):
        p = self.propuesta()
        self.co.desde_deliberacion(p, "aprobada_con_cambios")
        self.assertEqual(self.co.estado_pendiente(p), "cambios_solicitados")
        with self.assertRaisesRegex(ValueError, "transición|comprobación positiva"):   # dos defensas
            self.co.pendiente(p, "verificado", "consenso del equipo")
        ok_temprana = self.a3.comprobar(p, {"contiene": "sorted"})
        with self.assertRaisesRegex(ValueError, "transición"):     # ni con evidencia: falta «aplicado»
            self.co.pendiente(p, "verificado", "comprobado pero no aplicado", evidencia_id=ok_temprana)
        self.co.pendiente(p, "aplicado", "el usuario aplicó el cambio a mano", actor="usuario")
        with self.assertRaisesRegex(ValueError, "comprobación positiva"):
            self.co.pendiente(p, "verificado", "A1 dice que está bien")       # sin evidencia
        voto = self.a3.registrar_decision("apruebo", "me parece correcto", relacionada=p)
        with self.assertRaisesRegex(ValueError, "comprobación positiva"):
            self.co.pendiente(p, "verificado", "voto", evidencia_id=voto)    # una declaración no verifica
        neg = self.a3.comprobar(p, {"contiene": "xs.sort()\n"})
        self.assertEqual(self.a3.entrada(neg)["resultado"], "positivo")      # contiene la línea vieja (-)
        mala = self.a3.comprobar(p, {"no_contiene": "sorted(xs)"})
        self.assertEqual(self.a3.entrada(mala)["resultado"], "negativo")
        with self.assertRaisesRegex(ValueError, "comprobación positiva"):
            self.co.pendiente(p, "verificado", "comprobación negativa", evidencia_id=mala)
        ok = self.a3.comprobar(p, {"contiene": "+    xs = sorted(xs)"})
        self.co.pendiente(p, "verificado", "comprobación declarativa positiva", evidencia_id=ok)
        self.assertEqual(self.co.estado_pendiente(p), "verificado")
        self.assertIn(p, self.co.pendientes()["verificado"])

    def test_evidencia_de_otra_propuesta_no_sirve(self):
        p, q = self.propuesta(), self.propuesta()
        for x in (p, q):
            self.co.pendiente(x, "propuesta", "inicial")
            self.co.pendiente(x, "aplicado", "aplicado por el usuario", actor="usuario")
        ok_q = self.a3.comprobar(q, {"contiene": "sorted"})
        with self.assertRaisesRegex(ValueError, "comprobación positiva"):
            self.co.pendiente(p, "verificado", "evidencia ajena", evidencia_id=ok_q)

    def test_transiciones_y_motivos(self):
        p = self.propuesta()
        self.co.desde_deliberacion(p, "rechazada", "A3 encontró un contraejemplo")
        self.assertEqual(self.co.estado_pendiente(p), "rechazado_justificado")
        with self.assertRaisesRegex(ValueError, "transición"):
            self.co.pendiente(p, "aplicado", "tras rechazo no se aplica")
        q = self.propuesta()
        self.co.desde_deliberacion(q, "aprobada")
        self.assertEqual(self.co.estado_pendiente(q), "propuesta")
        with self.assertRaisesRegex(ValueError, "motivo razonado"):
            self.co.pendiente(q, "no_verificable", "no")
        self.co.pendiente(q, "no_verificable", "no hay forma declarativa de comprobar el rendimiento")
        with self.assertRaises(ValueError):
            self.co.pendiente(q, "inventado", "x")
        for sql in ("UPDATE pendientes SET estado='verificado'", "DELETE FROM pendientes"):
            with self.subTest(sql=sql), self.assertRaises(sqlite3.DatabaseError):
                with self.reg.con:
                    self.reg.con.execute(sql)
        hist = [r[0] for r in self.reg.con.execute("SELECT estado FROM pendientes WHERE entrada_id=? ORDER BY num",
                                                   (q,))]
        self.assertEqual(hist, ["propuesta", "no_verificable"])

    def test_resultado_desconocido_queda_como_propuesta(self):
        p = self.propuesta()
        self.co.desde_deliberacion(p, "sin_decision")
        self.assertEqual(self.co.estado_pendiente(p), "propuesta")


if __name__ == "__main__":
    unittest.main()
