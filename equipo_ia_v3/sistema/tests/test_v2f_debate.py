"""V2-F: debate por evidencias. La adjudicación es pura y se prueba sola; el protocolo completo usa agentes de
GUION (no Qwen) y la EJECUCIÓN REAL de las candidatas con el ejecutor restringido."""
import json
import unittest
from pathlib import Path

import _comun
from eq2 import casos as C, debate as D, experiencias, herramientas as H, rutas

TAREA = ("Implementa mediana(xs) en solucion.py: la mediana de una lista de números; con longitud par, la media de "
         "los dos centrales; con la lista vacía lanza ValueError. Ejemplos:\n"
         "mediana([1, 3, 2]) == 2\nmediana([1, 2, 3, 4]) == 2.5\nmediana([]) lanza ValueError")
BIEN = ("def mediana(xs):\n    if not xs:\n        raise ValueError('vacia')\n    s = sorted(xs)\n    n = len(s)\n"
        "    if n % 2:\n        return s[n // 2]\n    return (s[n // 2 - 1] + s[n // 2]) / 2\n")
SIN_PAR = "def mediana(xs):\n    if not xs:\n        raise ValueError('vacia')\n    s = sorted(xs)\n    return s[len(s) // 2]\n"
SIN_VACIA = ("def mediana(xs):\n    s = sorted(xs)\n    n = len(s)\n    if n % 2:\n        return s[n // 2]\n"
             "    return (s[n // 2 - 1] + s[n // 2]) / 2\n")
MUTA = ("def mediana(xs):\n    if not xs:\n        raise ValueError('vacia')\n    xs.sort()\n    n = len(xs)\n"
        "    if n % 2:\n        return xs[n // 2]\n    return (xs[n // 2 - 1] + xs[n // 2]) / 2\n")


def propuesta(codigo, casos=()):
    return "ARCHIVO: solucion.py\n```python\n" + codigo + "```\n" + "".join(f"CASO: {c}\n" for c in casos) + "FIN"


def caso(expr, fuente, i):
    return C.parsear_expresion(expr, fuente, i)


class TestAdjudicacion(unittest.TestCase):
    def setUp(self):
        self.casos = [caso("mediana([1, 2, 3, 4]) == 2.5", "enunciado", "E-1"),
                      caso("mediana([5]) == 5", "A3", "A3-1")]
        self.cands = {"P1": {"valida": True, "bytes": 90}, "P2": {"valida": True, "bytes": 140},
                      "P3": {"valida": True, "bytes": 120}}

    def test_la_mayoria_no_vence_a_la_evidencia(self):
        m = {"P1": {"E-1": "falla", "A3-1": "pasa"}, "P2": {"E-1": "pasa", "A3-1": "pasa"},
             "P3": {"E-1": "falla", "A3-1": "pasa"}}
        r = D.adjudicar(self.cands, self.casos, m, {}, {"A1": "P1", "A2": "P2", "A3": "P1"}, True)
        self.assertEqual((r["decision"], r["elegida"], r["mayoria"]), ("cumple_oraculo", "P2", "P1"))
        self.assertTrue(r["mayoria_contra_evidencia"])

    def test_sin_oraculo_es_consistente_no_demostrada(self):
        casos = [caso("mediana([5]) == 5", "A1", "A1-1")]
        m = {"P1": {"A1-1": "pasa"}, "P2": {"A1-1": "falla"}, "P3": {"A1-1": "error"}}
        r = D.adjudicar(self.cands, casos, m, {}, {}, True)
        self.assertEqual((r["decision"], r["elegida"]), ("consistente_sin_oraculo", "P1"))
        self.assertIn("no es una demostración", r["motivo"])

    def test_casos_impugnados_contradictorios_y_en_conflicto_no_deciden(self):
        casos = self.casos + [caso("mediana([1, 2]) == 1", "A1", "A1-1"),                # impugnado
                              caso("mediana([1, 2, 3, 4]) == 3", "A2", "A2-1"),          # contradice al oráculo
                              caso("mediana([7, 9]) == 8", "A2", "A2-2"),                # en conflicto con A3-2
                              caso("mediana([7, 9]) == 7", "A3", "A3-2")]
        m = {"P1": {"E-1": "pasa", "A3-1": "pasa", "A1-1": "falla", "A2-1": "falla", "A2-2": "pasa", "A3-2": "falla"},
             "P2": {"E-1": "falla"}, "P3": {"E-1": "falla"}}
        r = D.adjudicar(self.cands, casos, m, {"A1-1": [("A2", "la media de 1 y 2 es 1.5")]}, {}, True)
        self.assertEqual(r["estados_casos"]["A1-1"], "impugnado")
        self.assertEqual(r["estados_casos"]["A2-1"], "contradice_oraculo")
        self.assertEqual((r["estados_casos"]["A2-2"], r["estados_casos"]["A3-2"]), ("en_conflicto", "en_conflicto"))
        self.assertEqual(r["grupos_en_conflicto"], [["A2-2", "A3-2"]])
        # P1 cumple el oráculo y una de las alternativas del grupo; incumple el caso impugnado: disputas ABIERTAS
        self.assertEqual((r["decision"], r["elegida"]), ("cumple_oraculo_con_disputas", "P1"))
        self.assertEqual(r["disputas_abiertas"], [{"tipo": "impugnado", "caso": "A1-1"},
                                                  {"tipo": "conflicto", "casos": ["A2-2", "A3-2"]}])

    def test_retirada_del_autor_no_es_disputa_y_un_grupo_puede_vetar(self):
        casos = self.casos + [caso("mediana([1, 2]) == 1", "A1", "A1-1"),
                              caso("mediana([]) == 0", "A2", "A2-1"), caso("mediana([]) lanza ValueError", "A3", "A3-1b")]
        m = {"P1": {"E-1": "pasa", "A3-1": "pasa", "A1-1": "falla", "A2-1": "falla", "A3-1b": "falla"},
             "P2": {"E-1": "pasa", "A3-1": "pasa", "A1-1": "falla", "A2-1": "falla", "A3-1b": "pasa"},
             "P3": {"E-1": "pasa", "A3-1": "pasa", "A1-1": "falla", "A2-1": "pasa", "A3-1b": "falla"}}
        r = D.adjudicar(self.cands, casos, m, {"A1-1": [("A1", "retiro")]}, {}, True)
        self.assertEqual(r["estados_casos"]["A1-1"], "retirado")
        # P1 no coincide con NINGUNA alternativa del grupo ([] -> ?): falla; P2 y P3 sí (cada una con una)
        self.assertFalse(r["puntuacion"]["P1"]["cumple_todo"])
        self.assertEqual(sorted(r["equivalentes"]), ["P2", "P3"])
        self.assertEqual(r["decision"], "cumple_oraculo_con_disputas")              # el conflicto sigue abierto
        self.assertNotIn({"tipo": "impugnado", "caso": "A1-1"}, r["disputas_abiertas"])

    def test_empate_en_evidencia_lo_resuelve_una_preferencia_etiquetada(self):
        m = {p: {"E-1": "pasa", "A3-1": "pasa"} for p in self.cands}
        r = D.adjudicar(self.cands, self.casos, m, {}, {"A1": "P3", "A2": "P3", "A3": "P1"}, True)
        self.assertEqual((r["elegida"], r["desempate"]), ("P3", "preferencia del equipo (no es prueba)"))
        r = D.adjudicar(self.cands, self.casos, m, {}, {}, True)
        self.assertEqual((r["elegida"], r["desempate"]), ("P1", "la más breve (equivalentes en evidencia)"))

    def test_sin_ejecucion_no_hay_conclusion_aunque_haya_mayoria(self):
        r = D.adjudicar(self.cands, self.casos, {}, {}, {"A1": "P1", "A2": "P1", "A3": "P1"}, False)
        self.assertEqual((r["decision"], r["elegida"], r["preferencia"]), ("sin_pruebas", None, "P1"))

    def test_ninguna_cumple_y_sin_casos(self):
        m = {p: {"E-1": "falla", "A3-1": "pasa"} for p in self.cands}
        m["P2"]["A3-1"] = "falla"
        r = D.adjudicar(self.cands, self.casos, m, {}, {}, True)
        self.assertEqual(r["decision"], "sin_solucion_valida")
        self.assertIn(r["mejor_parcial"], ("P1", "P3"))
        r = D.adjudicar(self.cands, [], {}, {}, {}, True)
        self.assertEqual(r["decision"], "sin_casos_que_decidan")


class TestProtocolo(unittest.TestCase):
    def setUp(self):
        tmp = _comun.carpeta_temporal()
        self.addCleanup(tmp.cleanup)
        raiz = Path(tmp.name) / "equipo_f2"
        raiz.mkdir()
        self.lab = rutas.Laboratorio(raiz, raiz / "lab_v2f1")  # CAMBIO V2-F.1 (V2-F: lab_v2f)
        self.lab.crear_base()
        self.mem = experiencias.MemoriaEquipo(self.lab)
        self.addCleanup(self.mem.cerrar)
        self.n = 0

    def correr(self, respuestas, autorizado=True, propiedades=(), casos_usuario=(), reparacion=True):
        self.n += 1
        partes = (f"debate{self.n}",)
        desp = H.Despachador(self.lab, partes, autorizado=autorizado)
        registro = []

        def g(paso, n, **kw):
            registro.append((paso, kw))
            r = respuestas.get(paso, "")
            return r(kw) if callable(r) else r
        ag = D.AgentesDebateSimulados(g)
        res = D.Debate(self.lab, partes, ag, desp, memoria=self.mem, reparacion=reparacion).ejecutar(
            TAREA, casos_usuario, propiedades)
        return res, registro, ag

    def test_evidencia_elige_la_correcta_aunque_dos_prefieran_otra(self):
        r = {"propuesta_a1": propuesta(SIN_PAR, ["mediana([3, 1, 2]) == 2"]),
             "propuesta_a2": propuesta(BIEN, ["mediana([4, 1, 3, 2]) == 2.5"]),
             "propuesta_a3": propuesta(SIN_VACIA, ["mediana([7]) == 7"]),
             "cuestionar_a1": "POSICION: P1 | MOTIVO: es la más simple",
             "cuestionar_a2": "OBJECION: P1 | EVIDENCIA: E-2\nPOSICION: P2 | MOTIVO: cumple todo",
             "cuestionar_a3": "POSICION: P1 | MOTIVO: me gusta"}
        res, reg, ag = self.correr(r)
        self.assertEqual((res["decision"], res["elegida"]), ("cumple_oraculo", "P2"), res["adjudicacion"])
        self.assertTrue(res["adjudicacion"]["mayoria_contra_evidencia"])
        self.assertEqual(res["matriz"]["P1"]["E-2"], "falla")
        self.assertEqual(res["obtenidos"]["P1"]["E-2"], "OBTENIDO=3")
        self.assertEqual(res["matriz"]["P3"]["E-3"], "falla")                          # IndexError, no ValueError
        self.assertTrue(res["obtenidos"]["P3"]["E-3"].startswith("OBTENIDO=excepcion IndexError"))
        self.assertEqual(ag.registro, ["propuesta_a1", "propuesta_a2", "propuesta_a3",
                                       "cuestionar_a1", "cuestionar_a2", "cuestionar_a3"])    # 6 llamadas, sin reparar
        # las propuestas son independientes: ningún prompt de propuesta contiene otra propuesta
        for paso, kw in reg[:3]:
            self.assertNotIn("def mediana", json.dumps(kw))
        # el cuestionamiento ve la matriz con el valor obtenido
        ev = [kw for p, kw in reg if p == "cuestionar_a1"][0]["evidencia"]
        self.assertIn("P1 (A1): cumple", ev)
        self.assertIn("E-2->OBTENIDO=3", ev)
        self.assertTrue(self.lab.ruta("debate1", "solucion_final", "solucion.py").is_file())
        inf = json.loads(self.lab.ruta("debate1", "informe.json").read_text())
        self.assertEqual(inf["decision"], "cumple_oraculo")
        etq = {(x["agente"], x["etiqueta"]) for x in self.mem.registrados}
        self.assertIn(("A2", "debate:posicion_acertada"), etq)
        self.assertIn(("A1", "debate:posicion_fallida"), etq)

    def test_contraejemplo_nuevo_del_cuestionamiento_se_ejecuta(self):
        r = {"propuesta_a1": propuesta(BIEN), "propuesta_a2": propuesta(MUTA), "propuesta_a3": propuesta(BIEN),
             "cuestionar_a3": "CASO: mediana([2, 2, 2]) == 2\nPOSICION: P3"}
        res, _, _ = self.correr(r, propiedades=("no_muta_argumentos",))
        self.assertIn("A3c-1", res["matriz"]["P1"])
        self.assertEqual(res["matriz"]["P2"]["PROP:no_muta_argumentos:E-1"], "falla")      # muta la entrada
        self.assertNotEqual(res["elegida"], "P2")
        self.assertEqual(res["decision"], "cumple_oraculo")
        self.assertIn("P1=P3", res["independencia"]["identicas"])
        self.assertTrue(res["independencia"]["diversidad_baja"])

    def test_reparacion_por_su_autor_con_la_evidencia(self):
        # P1 y P3 empatan (2/3 del oráculo); la mejor parcial es la más breve (P1): la repara SU autor, A1
        r = {"propuesta_a1": propuesta(SIN_PAR), "propuesta_a2": propuesta(SIN_PAR + "\n"), "propuesta_a3": propuesta(SIN_VACIA),
             "reparar_a1": lambda kw: (propuesta(BIEN) + "\nCAMBIOS: promedio con longitud par"
                                       if "E-2" in kw["evidencia"] and "OBTENIDO=3" in kw["evidencia"] else "sin evidencia")}
        res, reg, ag = self.correr(r)
        self.assertEqual(ag.registro[-1], "reparar_a1")
        self.assertEqual((res["decision"], res["elegida"]), ("cumple_oraculo", "P1r"))
        self.assertEqual(res["reparacion"], {"candidata": "P1", "autor": "A1", "resultado": "cumple",
                                             "cambios": "promedio con longitud par"})

    def test_sin_autorizacion_no_hay_conclusion(self):
        r = {"propuesta_a1": propuesta(BIEN), "propuesta_a2": propuesta(BIEN), "propuesta_a3": propuesta(BIEN),
             "cuestionar_a1": "POSICION: P1", "cuestionar_a2": "POSICION: P1", "cuestionar_a3": "POSICION: P1"}
        res, _, ag = self.correr(r, autorizado=False)
        self.assertEqual((res["decision"], res["elegida"], res["ejecutado"]), ("sin_pruebas", None, False))
        self.assertEqual(res["adjudicacion"]["preferencia"], "P1")
        self.assertFalse(list(self.lab.base.rglob("espacio")))
        self.assertNotIn("reparar_a1", ag.registro)

    def test_casos_mal_formados_se_rechazan_y_se_le_dice_al_agente(self):
        r = {"propuesta_a1": propuesta(BIEN, ["mediana(x) == 1", "import os"]),
             "propuesta_a2": propuesta(BIEN), "propuesta_a3": "no sé programar esto"}
        res, reg, _ = self.correr(r)
        self.assertFalse(res["candidatas"]["P3"]["valida"])
        motivos = [x["motivo"] for x in res["casos_rechazados"] if x["agente"] == "A1"]
        self.assertTrue(any("literal" in m for m in motivos), res["casos_rechazados"])
        ev = [kw for p, kw in reg if p == "cuestionar_a1"][0]["evidencia"]
        self.assertIn("TUS CASOS RECHAZADOS", ev)
        self.assertIn(("A1", "herramienta:rechazo"), {(x["agente"], x["etiqueta"]) for x in self.mem.registrados})

    def test_caso_del_usuario_es_oraculo(self):
        u = C.casos_del_usuario(["mediana([10, 20]) == 15"])
        r = {"propuesta_a1": propuesta(SIN_PAR), "propuesta_a2": propuesta(BIEN), "propuesta_a3": propuesta(BIEN)}
        res, _, _ = self.correr(r, casos_usuario=u)
        self.assertEqual(res["adjudicacion"]["estados_casos"]["U1"], "oraculo")
        self.assertEqual(res["matriz"]["P1"]["U1"], "falla")
        self.assertEqual(res["decision"], "cumple_oraculo")


if __name__ == "__main__":
    unittest.main()
