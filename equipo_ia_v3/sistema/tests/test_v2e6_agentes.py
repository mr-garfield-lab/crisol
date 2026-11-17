"""V2-E.6 área 3: roles persistentes y pruebas de INDEPENDENCIA de la revisión (SIMULADO, determinista).
La similitud se informa como indicio: nunca como prueba de copia."""
import json
import unittest
from pathlib import Path

import _comun
from eq2 import config, independencia as I, inferencia, orquestador, prompts, roles, rutas, vigilancia

ENUN = "Escribe ordenar(xs) en Python; no debe modificar la lista de entrada."
CODIGO_MUTA = "```python\ndef ordenar(xs):\n    xs.sort()\n    return xs\n```"
CODIGO_BIEN = "```python\ndef ordenar(xs):\n    return sorted(xs)\n```"
PROP = ("Propuesta: la función ordena la lista recibida en su sitio con el método sort y la devuelve "
        "para que el llamador la use directamente.\n" + CODIGO_MUTA + "\nPrueba: ordenar([2, 1]) == [1, 2]\nFIN")
REV_BUENA = "OBJECION: muta la lista de entrada | EVIDENCIA: `xs.sort()` contradice «no debe modificar»"
REV_ECO = ("SIN OBJECIONES: ok. A1 tiene razón. La función ordena la lista recibida en su sitio con el método "
           "sort y la devuelve para que el llamador la use directamente.")


def guion(revision, replica, votos=None, propuesta=PROP):
    votos = votos or {}

    def g(n, fase, mensajes, max_tokens):
        sis = mensajes[0]["content"]
        ag = next((a for a in config.AGENTES if f"Eres {a}" in sis), "?")
        if fase == "voto":
            ag = next((a for a in config.AGENTES if f"Eres {a}," in mensajes[-1]["content"]), ag)
            return votos.get(ag, "VOTO: aprobar\nRAZON: correcto")
        return {"analisis": "Objetivo: ordenar sin mutar.", "propuesta": propuesta, "revision": revision,
                "replica": replica}.get(fase, "?")
    return g


class TestRoles(unittest.TestCase):
    def test_tarjetas_completas_y_coherentes_con_los_prompts(self):
        t = roles.tarjetas()
        self.assertEqual(set(t["roles"]), {"coordinador", "A1", "A2", "A3"})
        for nombre, r in t["roles"].items():
            for k in ("rol", "responsabilidades", "criterios", "prohibido"):
                self.assertTrue(r[k], (nombre, k))
        for ag in config.AGENTES:
            self.assertIn(t["roles"][ag]["rol"], prompts.SISTEMA[ag])
        self.assertIn("no asumir que A1 tiene razón", t["roles"]["A3"]["criterios"])
        self.assertIn("el consenso no es verificación", t["roles"]["coordinador"]["criterios"])

    def test_persistencia_sin_sobrescribir_y_alteracion_detectada(self):
        tmp = _comun.carpeta_temporal()
        self.addCleanup(tmp.cleanup)
        raiz = Path(tmp.name) / "equipo_f2"
        lab = rutas.Laboratorio(raiz, raiz / "lab_v2e6")
        lab.crear_base()
        a = roles.persistir(lab)
        b = roles.persistir(lab)
        self.assertEqual((a["nuevo"], b["nuevo"], a["sha256"]), (True, False, roles.huella()))
        p = lab.ruta(*a["archivo"].split("/"))
        d = json.loads(p.read_text())
        d["roles"]["A3"]["criterios"] = ["aprobar siempre"]
        p.chmod(0o600)
        p.write_text(json.dumps(d))
        with self.assertRaisesRegex(ValueError, "alterado"):
            roles.persistir(lab)


class TestSenalesIndependencia(unittest.TestCase):
    def test_revision_independiente_sin_senales(self):
        r = I.analizar({"propuesta": PROP, "revision": REV_BUENA, "replica": "ACEPTADA: sorted\n" + CODIGO_BIEN},
                       {"A1": ("aprobar", "cumple tras el cambio"), "A2": ("aprobar", "requisitos cubiertos"),
                        "A3": ("aprobar", "la objeción se resolvió con sorted")})
        self.assertEqual(r["tipos"], [])
        self.assertTrue(r["revision_independiente"])

    def test_a3_que_repite_la_propuesta_y_asume_al_autor(self):
        r = I.analizar({"propuesta": PROP, "revision": REV_ECO}, {"A3": ("aprobar", "bien")})
        self.assertIn("revision_eco_de_propuesta", r["tipos"])
        self.assertIn("revision_asume_autor_correcto", r["tipos"])
        self.assertIn("aprobacion_sin_comprobacion", r["tipos"])
        self.assertFalse(r["revision_independiente"])
        eco = next(s for s in r["senales"] if s["tipo"] == "revision_eco_de_propuesta")
        self.assertEqual(eco["grado"], "indicio")

    def test_aprobacion_con_comprobacion_declarada_no_se_marca(self):
        r = I.analizar({"propuesta": PROP, "revision": "SIN OBJECIONES: comprobé que sorted no muta y el caso [2,1]"},
                       {"A3": ("aprobar", "ok")})
        self.assertNotIn("aprobacion_sin_comprobacion", r["tipos"])

    def test_votos_similares_son_indicio_no_copia(self):
        v = {"A1": ("aprobar", "la función ordena correctamente sin modificar la entrada"),
             "A2": ("aprobar", "la función ordena correctamente sin modificar la entrada original"),
             "A3": ("rechazar", "falta el caso de lista vacía en las pruebas")}
        r = I.analizar({}, v)
        s = [x for x in r["senales"] if x["tipo"] == "razones_de_voto_similares"]
        self.assertEqual([x["agentes"] for x in s], [["A1", "A2"]])
        self.assertEqual((s[0]["grado"], s[0]["nota"]), ("indicio", "similitud no prueba copia"))
        self.assertIn("NO prueba copia", r["nota"])
        self.assertIsNone(I.jaccard("ok", "ok"))                    # demasiado corto: no se compara

    def test_votos_identicos_y_respuesta_repetida(self):
        v = {a: ("aprobar", "cumple todos los requisitos de la tarea") for a in config.AGENTES}
        r = I.analizar({"propuesta": PROP, "replica": PROP, "revision": REV_BUENA}, v)
        self.assertIn("votos_identicos", r["tipos"])
        self.assertIn("respuesta_repetida", r["tipos"])
        self.assertIn("replica_repite_propuesta", r["tipos"])       # había objeción y no cambió nada

    def test_sesgo_de_autovoto(self):
        v = {"A1": ("aprobar", "mi propuesta es correcta"), "A2": ("rechazar", "muta la lista"),
             "A3": ("aprobar_con_cambios", "usar sorted")}
        self.assertIn("autovoto_divergente", I.analizar({}, v)["tipos"])
        v2 = {"A1": ("aprobar", "x y z w"), "A2": ("aprobar", "cumple bien todo"), "A3": ("rechazar", "muta la lista")}
        self.assertIn("decision_depende_del_autor", I.analizar({}, v2)["tipos"])

    def test_abstencion_forzada_no_cuenta_como_razon(self):
        v = {"A1": ("abstencion", "voto ilegible voto ilegible"), "A2": ("abstencion", "voto ilegible voto ilegible"),
             "A3": ("aprobar", "ok")}
        r = I.analizar({}, v, {"A1": "abstencion_forzada", "A2": "abstencion_forzada", "A3": "valido"})
        self.assertNotIn("razones_de_voto_similares", r["tipos"])


class TestIntegracionOrquestador(unittest.TestCase):
    def correr(self, g):
        tmp = _comun.carpeta_temporal()
        self.addCleanup(tmp.cleanup)
        raiz = Path(tmp.name) / "equipo_f2"
        v = vigilancia.Vigilante(lector_mem=lambda: 1_500_000, lector_bat=lambda: (80, False))
        o = orquestador.Orquestador(raiz / "lab_v2e6", inferencia.BackendSimulado(g), v, reloj=_comun.Reloj(),
                                    raiz_laboratorio=raiz)
        return o.run_deliberacion([ENUN]), raiz / "lab_v2e6"

    def test_a3_complaciente_se_informa_sin_cambiar_el_recuento(self):
        res, base = self.correr(guion(REV_ECO, "Sin cambios.\n" + CODIGO_MUTA + "\nFIN",
                                      votos={"A3": "VOTO: aprobar\nRAZON: bien"}))
        t = res["tareas"][0]
        self.assertEqual(t["resultado"], "aprobada")                  # el recuento no cambia
        self.assertFalse(t["independencia"]["revision_independiente"])
        self.assertIn("independencia:revision_asume_autor_correcto", t["fiabilidad"]["advertencias"])
        self.assertEqual(t["fiabilidad"]["independencia"]["tipos"], t["independencia"]["tipos"])
        self.assertTrue(res["roles"]["sha256"])
        self.assertTrue((base / res["roles"]["archivo"]).is_file())
        ev = (base / "runs" / res["run_id"] / "eventos.jsonl").read_text()
        self.assertIn('"tipo": "independencia"', ev)

    def test_revision_critica_no_genera_senales_de_dependencia(self):
        res, _ = self.correr(guion(REV_BUENA, "ACEPTADA: uso sorted\n" + CODIGO_BIEN + "\nFIN",
                                   votos={"A1": "VOTO: aprobar\nRAZON: corregido con sorted",
                                          "A2": "VOTO: aprobar\nRAZON: ya no modifica la entrada",
                                          "A3": "VOTO: aprobar\nRAZON: objeción resuelta"}))
        t = res["tareas"][0]
        self.assertTrue(t["independencia"]["revision_independiente"])
        self.assertEqual(t["independencia"]["tipos"], [])


if __name__ == "__main__":
    unittest.main()
