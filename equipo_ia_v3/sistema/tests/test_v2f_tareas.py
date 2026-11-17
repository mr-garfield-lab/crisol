"""V2-F: tareas LAB con el motor V2-F (memoria persistente entre tareas), debate por evidencias, casos-oráculo,
propiedades y política de información. Guion de agentes (no Qwen); ejecuciones REALES con el ejecutor restringido."""
import json
import unittest
import zipfile
from pathlib import Path

import _comun
from eq2 import debate as D, motor, motor_v2f as MV, tareas

BIEN = ("ARCHIVO: solucion.py\n```python\ndef dedup(xs):\n    vistos, out = set(), []\n    for x in xs:\n"
        "        if x not in vistos:\n            vistos.add(x)\n            out.append(x)\n    return out\n```\nFIN")
MAL = "ARCHIVO: solucion.py\n```python\ndef dedup(xs):\n    return sorted(set(xs))\n```\nFIN"


class Base(unittest.TestCase):
    def setUp(self):
        tmp = _comun.carpeta_temporal()
        self.addCleanup(tmp.cleanup)
        self.d = Path(tmp.name)
        self.ts = tareas.Tareas(raiz=self.d / "equipo_f2")

    def importar(self, **d):
        p = self.d / f"t{len(list(self.d.glob('t*.json')))}.json"
        p.write_text(json.dumps(d, ensure_ascii=False))
        return self.ts.importar(p)


class TestImportacion(Base):
    def test_campos_v2f_y_validacion(self):
        t = self.importar(instrucciones="Crea dedup(xs).", casos=["dedup([3, 1, 3]) == [3, 1]"],
                          propiedades=["no_muta_argumentos"], politica_falta="asumir_y_marcar", tipo="debate_codigo")
        self.assertEqual((t["tipo"], t["motor"], t["casos"], t["propiedades"], t["politica_falta"]),
                         ("debate_codigo", "v2f", ["dedup([3, 1, 3]) == [3, 1]"], ["no_muta_argumentos"],
                          "asumir_y_marcar"))
        for malo in ({"casos": ["dedup(x) == 1"]}, {"propiedades": ["rapido"]}, {"motor": "v3"},
                     {"politica_falta": "votar"}, {"casos": ["f(1) == 1"], "tipo": "modlab_pz"}, {"permisos": "root"}):
            with self.assertRaises(tareas.ErrorTarea, msg=malo):
                self.importar(instrucciones="x", **malo)

    def test_agentes_segun_tipo(self):
        from eq2 import inferencia
        be = inferencia.BackendSimulado()
        self.assertIsInstance(tareas.agentes_para({"tipo": "debate_codigo"}, be), D.AgentesDebateLLM)
        self.assertIsInstance(tareas.agentes_para({"tipo": "codigo", "motor": "v2f"}, be), MV.AgentesMotorLLMV2F)
        a = tareas.agentes_para({"tipo": "codigo", "motor": "v2e"}, be)
        self.assertIs(type(a), motor.AgentesMotorLLM)


class TestDebateComoTarea(Base):
    def test_debate_con_oraculo_del_usuario_y_exportacion(self):
        self.importar(id="LAB-001", tipo="debate_codigo", instrucciones="Crea dedup(xs) en solucion.py: quita "
                      "duplicados conservando el orden de la primera aparición.",
                      casos=["dedup([3, 1, 3, 2, 1]) == [3, 1, 2]"], propiedades=["no_muta_argumentos"])

        def g(paso, n, **kw):
            return {"propuesta_a1": MAL, "propuesta_a2": BIEN, "propuesta_a3": BIEN.replace("vistos", "visto"),
                    "cuestionar_a1": "POSICION: P1", "cuestionar_a3": "POSICION: P1 | MOTIVO: más corta",
                    "cuestionar_a2": "POSICION: P2"}.get(paso, "")
        r = self.ts.ejecutar("LAB-001", D.AgentesDebateSimulados(g), autorizo_pruebas=True)
        self.assertEqual((r["clase"], r["resultado"], r["elegida"]), ("debate_codigo", "cumple_oraculo", "P2"))
        self.assertTrue(r["mayoria_contra_evidencia"])
        e = self.ts.lab.ruta("tareas", "LAB-001", "ejecuciones", "E001")
        inf = json.loads((e / "debate" / "informe.json").read_text())
        self.assertEqual(inf["matriz"]["P1"]["U1"], "falla")
        self.assertTrue((e / "debate" / "solucion_final" / "solucion.py").is_file())
        self.assertTrue((e / "MANIFIESTO_SHA256.txt").is_file())
        z = self.ts.exportar("LAB-001")
        with zipfile.ZipFile(z) as zf:
            self.assertTrue(any(n.endswith("debate/informe.json") for n in zf.namelist()))
        # memoria individual persistente en el laboratorio (no en la carpeta de la ejecución)
        self.assertTrue(self.ts.lab.ruta("aprendizaje", "a2.db").is_file())

    def test_debate_sin_autorizacion(self):
        self.importar(id="LAB-002", tipo="debate_codigo", instrucciones="Crea dedup(xs).")
        r = self.ts.ejecutar("LAB-002", D.AgentesDebateSimulados(lambda p, n, **k: BIEN if p.startswith("prop") else
                                                                 "POSICION: P1"), autorizo_pruebas=False)
        self.assertEqual((r["resultado"], r["elegida"]), ("sin_pruebas", None))


class TestMotorV2FComoTarea(Base):
    PLAN = ("SUBTAREA: S1 | quitar duplicados | CRITERIOS: C1 | DEPENDE: - | PRIORIDAD: alta\n"
            "ARCHIVOS: solucion.py, test_solucion.py\nCRITERIO: C1 | conserva el orden | PRUEBA: test_orden")
    PRUEBAS = ("ARCHIVO: test_solucion.py\n```python\nfrom solucion import dedup\n\ndef test_orden():\n"
               "    assert dedup([1, 1, 2]) == [1, 2]\n```\nFIN")

    def guion(self, registro):
        estado = {"rev": 0}

        def g(paso, n, **kw):
            registro.append((paso, kw))
            if paso == "revisar":
                estado["rev"] += 1
                return ("OBJECION: ordena en vez de conservar | EVIDENCIA: `sorted(set(xs))`\n"
                        "CASO: dedup([3, 1, 3]) == [3, 1]") if estado["rev"] == 1 else "SIN OBJECIONES: orden conservado"
            return {"planificar": self.PLAN, "generar": MAL, "pruebas": self.PRUEBAS, "evaluar": "DIAGNOSTICO: orden",
                    "corregir": BIEN.replace("FIN", "CAMBIOS: conservo el orden con un conjunto de vistos\nFIN"),
                    "auditar": "AUDITORIA: conforme"}[paso]
        return g

    def test_la_memoria_persiste_entre_tareas_y_llega_a_a3(self):
        for tid in ("LAB-010", "LAB-011"):
            self.importar(id=tid, instrucciones="Crea dedup(xs) en solucion.py: quita duplicados conservando el orden.")
        reg1, reg2 = [], []
        r1 = self.ts.ejecutar("LAB-010", MV.AgentesMotorSimuladosV2F(self.guion(reg1)), autorizo_pruebas=True,
                              instalar_senales=False)
        self.assertEqual((r1["motor"], r1["resultado"], r1["auditoria_A3"]), ("v2f", "verificado", "conforme"))
        self.assertGreater(r1["experiencias_guardadas"], 0)
        self.ts.ejecutar("LAB-011", MV.AgentesMotorSimuladosV2F(self.guion(reg2)), autorizo_pruebas=True,
                         instalar_senales=False)
        exp_a3 = [kw["experiencias"] for p, kw in reg2 if p == "revisar"][0]
        self.assertIn("dedup([3, 1, 3]) == [3, 1]", exp_a3)                       # lo aprendido en LAB-010
        self.assertIn("tarea/turno=LAB-010/E001", exp_a3)                        # procedencia en los metadatos
        det = json.loads(self.ts.lab.ruta("tareas", "LAB-010", "ejecuciones", "E001", "auditoria",
                                          "determinista.json").read_text())
        self.assertEqual((det["conclusion"], det["reservas"]), ("verificado", []))

    def test_motor_v2e_sigue_disponible_para_comparar(self):
        self.importar(id="LAB-020", motor="v2e", instrucciones="Crea dedup(xs) en solucion.py conservando el orden.")
        reg = []
        r = self.ts.ejecutar("LAB-020", motor.AgentesMotorSimulados(self.guion(reg)), autorizo_pruebas=True,
                             instalar_senales=False)
        self.assertNotIn("motor", r)
        self.assertFalse(self.ts.lab.ruta("aprendizaje").exists())                # V2-E no escribe experiencias

    def test_preguntas_al_usuario_desde_la_tarea(self):
        self.importar(id="LAB-030", instrucciones="Crea dedup(xs).")
        g = lambda paso, n, **kw: self.PLAN + "\nFALTA: ¿se distinguen mayúsculas?" if paso == "planificar" else ""
        r = self.ts.ejecutar("LAB-030", MV.AgentesMotorSimuladosV2F(g), autorizo_pruebas=True, instalar_senales=False)
        self.assertEqual((r["estado_final"], r["preguntas"]), ("informacion_insuficiente", ["¿se distinguen mayúsculas?"]))
        self.assertEqual(r["resultado"], "no_verificado")


if __name__ == "__main__":
    unittest.main()
