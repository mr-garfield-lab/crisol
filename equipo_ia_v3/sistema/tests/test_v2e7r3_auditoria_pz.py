"""V2-E.7-r3: regresiones de la auditoría de A3 en tareas modlab_pz.

Reproducen las tres misiones reales (LAB-001, LAB-002, LAB-003; recreadas, los ZIP originales no se usan ni se
tocan) y los casos de evidencia incompleta, resultados contradictorios y herramientas no ejecutadas. Los textos de
A1/A2/A3 son un GUION (no Qwen): se comprueba qué EVIDENCIA recibe A3 y que la conclusión determinista no cambia."""
import json
import unittest
from pathlib import Path
from unittest import mock

import _comun
from eq2 import config, evidencia_pz, inferencia, modlab_pz_adaptador, motor, tareas

MARTILLO = ('ARCHIVO: escenario.json\n```json\n{"acciones": [{"accion": "agregar", "objeto": "Base.Hammer", "cantidad": 1},'
            ' {"accion": "consumir", "objeto": "Base.Hammer", "cantidad": 2},'
            ' {"accion": "comprobar", "objeto": "Base.Hammer", "cantidad": 1}]}\n```\nFIN')
VENDAS = ('ARCHIVO: escenario.json\n```json\n{"acciones": [{"accion": "agregar", "objeto": "Base.Bandage", "cantidad": 2},'
          ' {"accion": "consumir", "objeto": "Base.Bandage", "cantidad": 1},'
          ' {"accion": "comprobar", "objeto": "Base.Bandage", "cantidad": 1},'
          ' {"accion": "evento", "objeto": "OnPlayerUpdate"}]}\n```\nFIN')
SIMULAR = "SOLICITO: simular_escenario escenario.json"


class Base(unittest.TestCase):
    def correr(self, esperado, escenario, solicitud=SIMULAR, a3="AUDITORIA: conforme\nOBSERVACION: paso 2 coherente",
               autorizo=True, instr=None, tid="LAB-001"):
        tmp = _comun.carpeta_temporal()
        self.addCleanup(tmp.cleanup)
        d = Path(tmp.name)
        (d / "t.json").write_text(json.dumps({"id": tid, "tipo": "modlab_pz", "resultado_esperado": esperado,
                                              "instrucciones": instr or "Escenario de inventario de prueba."}))
        ts = tareas.Tareas(raiz=d / "equipo_f2")
        ts.importar(d / "t.json")
        recibido = []

        def guion(paso, n, **kw):
            if paso == "pz_auditar":
                recibido.append(kw["evidencia"])
            return {"pz_escenario": escenario, "pz_solicitar": solicitud, "pz_auditar": a3}[paso]
        r = ts.ejecutar(tid, motor.AgentesMotorSimulados(guion), autorizo_pruebas=autorizo, instalar_senales=False)
        e = ts.lab.ruta("tareas", tid, "ejecuciones", "E001")
        leer = lambda *p: json.loads((e.joinpath(*p)).read_text())
        self.ts, self.e = ts, e
        return r, (recibido[0] if recibido else None), leer("auditoria", "determinista.json"), \
            leer("auditoria", "evidencia_verificada.json")


class TestMisionesReales(Base):
    def test_lab001_fallo_intencional_detectado(self):
        r, ev, det, datos = self.correr("fallo_detectado", MARTILLO)
        self.assertEqual((det["conclusion"], det["obtenido"]), ("esperado_confirmado", "fallo_detectado"))
        for frag in ("RESULTADO_ESPERADO: fallo_detectado",
                     "CONCLUSIÓN DEL EVALUADOR DETERMINISTA: esperado_confirmado (obtenido: fallo_detectado)",
                     "OPERACIONES SOLICITADAS POR A2: 1 · EJECUTADAS: 1",
                     "paso 1: agregar Base.Hammer x1 -> ok [1. operación simulada exitosa]",
                     "paso 2: consumir Base.Hammer x2 -> RECHAZADO por el simulador [2. operación simulada fallida de manera esperada]",
                     "paso 3: comprobar Base.Hammer x1 -> ok",
                     'inventario final: {"Base.Hammer": 1}', "todos_ok: False", "evidencia verificada (SHA-256",
                     "EVIDENCIA SUFICIENTE: sí", "NO es Project Zomboid"):
            self.assertIn(frag, ev)
        self.assertEqual(datos["operaciones"][0]["categoria"], "fallo_esperado")
        self.assertEqual(ev, (self.e / "auditoria" / "A3_evidencia_recibida.txt").read_text())
        self.assertEqual(r["auditoria_A3"], "conforme")

    def test_lab002_inventario_correcto(self):
        r, ev, det, datos = self.correr("todos_ok", VENDAS, tid="LAB-002")
        self.assertEqual((det["conclusion"], det["obtenido"]), ("esperado_confirmado", "todos_ok"))
        self.assertEqual([p["categoria"] for p in datos["operaciones"][0]["pasos"]], ["simulada_exitosa"] * 4)
        self.assertIn('inventario final: {"Base.Bandage": 1}; eventos: ["OnPlayerUpdate"]; todos_ok: True', ev)
        self.assertNotIn("RECHAZADO", ev)

    def test_lab003_instrucciones_explicitas_y_a3_puede_discrepar(self):
        """El caso real: A3 dijo no_conforme sin pruebas. Ahora VE el rechazo; si aun así discrepa, se guarda su
        veredicto sin tocar la conclusión del código, y se anota que no citó ningún paso."""
        instr = ("Fallo intencional: agregar 1 Base.Hammer, consumir 2 Base.Hammer (imposible) y comprobar que queda 1. "
                 "El simulador debe rechazar el consumo. Solicita simular_escenario sobre escenario.json.")
        r, ev, det, _ = self.correr("fallo_detectado", MARTILLO, instr=instr, tid="LAB-003",
                                    a3="AUDITORIA: no_conforme\nOBSERVACION: el simulador no rechazó el consumo")
        self.assertIn("paso 2: consumir Base.Hammer x2 -> RECHAZADO por el simulador", ev)
        self.assertIn("OBJETIVO DE LA MISIÓN: " + instr, ev)
        self.assertEqual(det["conclusion"], "esperado_confirmado")
        self.assertEqual(r["auditoria_A3"], "no_conforme")
        a3 = (self.e / "auditoria" / "A3_auditoria.txt").read_text()
        self.assertIn("cita_pasos: False", a3)


class TestEvidenciaIncompletaYContradictoria(Base):
    def test_sin_solicitudes_y_sin_autorizacion(self):
        r, ev, det, datos = self.correr("fallo_detectado", MARTILLO, solicitud="no sé qué pedir",
                                        a3="AUDITORIA: evidencia_insuficiente")
        self.assertEqual((det["conclusion"], r["auditoria_A3"]), ("sin_pruebas", "evidencia_insuficiente"))
        self.assertIn("EJECUTADAS: 0", ev)
        self.assertIn("EVIDENCIA SUFICIENTE: NO", ev)
        r, ev, det, datos = self.correr("fallo_detectado", MARTILLO, autorizo=False)
        self.assertEqual(det["conclusion"], "sin_pruebas")
        self.assertIn("H001 simular_escenario escenario.json: no_autorizada -> 4. evidencia insuficiente", ev)

    def test_herramientas_rechazadas_y_error_del_laboratorio(self):
        sol = (SIMULAR + "\nSOLICITO: ejecutar_lua_de_terceros escenario.json\n"
               "SOLICITO: simular_escenario otro.json")
        r, ev, det, datos = self.correr("fallo_detectado", MARTILLO, solicitud=sol)
        cats = {o["id"]: (o["estado"], o["categoria"]) for o in datos["operaciones"]}
        self.assertEqual(cats, {"H001": ("ejecutada", "fallo_esperado"),
                                "H002": ("rechazada_por_contrato", "sin_evidencia"),
                                "H003": ("rechazada_archivo_desconocido", "sin_evidencia")})
        self.assertEqual(det["conclusion"], "esperado_confirmado")
        malo = MARTILLO.replace('"accion": "consumir"', '"accion": "teletransportar"')
        r, ev, det, datos = self.correr("fallo_detectado", malo)
        self.assertEqual(datos["operaciones"][0]["categoria"], "fallo_inesperado")
        self.assertIn("la herramienta no completó la operación", ev)
        self.assertEqual(det["conclusion"], "sin_pruebas")      # un error no es un «fallo detectado»

    def test_resultados_contradictorios_y_evidencia_alterada(self):
        real = modlab_pz_adaptador.ejecutar

        def contradictorio(op, ruta):
            x = real(op, ruta)
            x["todos_ok"] = True                                 # pasos con un fallo, pero todos_ok verdadero
            return x
        with mock.patch.object(modlab_pz_adaptador, "ejecutar", contradictorio):
            r, ev, det, datos = self.correr("fallo_detectado", MARTILLO)
        self.assertEqual(datos["operaciones"][0]["categoria"], "sin_evidencia")
        self.assertIn("resultados contradictorios", ev)
        self.assertIn("EVIDENCIA SUFICIENTE: NO", ev)
        # la conclusión determinista sigue la regla de r2 (todos_ok de la herramienta), sin cambios
        self.assertEqual((det["obtenido"], det["conclusion"]), ("todos_ok", "no_confirmado"))
        # evidencia alterada en disco después de la ejecución: la siguiente lectura la marca
        p = self.e / "herramientas" / "H001" / "resultado.json"
        rutas_lab = self.ts.lab.__class__(self.ts.raiz, self.e)
        p.write_text(p.read_text().replace('"ok": false', '"ok": true'))
        ev2 = evidencia_pz.construir(rutas_lab, self.ts.tarea("LAB-001"), det["herramientas"], det)
        self.assertEqual(ev2["datos"]["operaciones"][0]["categoria"], "sin_evidencia")
        self.assertIn("huellas", ev2["texto"])


class TestDeterminismoIntacto(Base):
    def test_a3_no_altera_la_conclusion(self):
        _, _, det1, _ = self.correr("fallo_detectado", MARTILLO, a3="AUDITORIA: conforme")
        _, _, det2, _ = self.correr("fallo_detectado", MARTILLO, a3="AUDITORIA: no_conforme\nOBSERVACION: paso 2")
        clave = lambda d: (d["conclusion"], d["esperado"], d["obtenido"],
                           [(h["operacion"], h["estado"], h["todos_ok"]) for h in d["herramientas"]])
        self.assertEqual(clave(det1), clave(det2))
        self.assertEqual(clave(det1)[:3], ("esperado_confirmado", "fallo_detectado", "fallo_detectado"))
        self.assertNotIn("categoria", json.dumps(det1))          # la clasificación no entra en determinista.json


class TestEvidenciaCabeEnElPrompt(unittest.TestCase):
    def test_prompt_real_de_a3_con_ctx_1024_y_2048(self):
        """Agentes LLM reales del motor (backend SIMULADO, no Qwen): cada línea de la evidencia llega al prompt de A3."""
        for ctx in (1024, 2048):
            with self.subTest(ctx=ctx), mock.patch.object(config, "CTX", ctx):
                resp = [MARTILLO, SIMULAR, "AUDITORIA: conforme\nOBSERVACION: paso 2 rechazado como se esperaba"]
                be = inferencia.BackendSimulado(lambda n, fase, m, mt: resp[min(n - 1, 2)])
                tmp = _comun.carpeta_temporal()
                self.addCleanup(tmp.cleanup)
                d = Path(tmp.name)
                (d / "t.json").write_text(json.dumps({"id": "LAB-003", "tipo": "modlab_pz",
                                                      "resultado_esperado": "fallo_detectado",
                                                      "instrucciones": "Agregar 1 Base.Hammer y consumir 2 (imposible)."}))
                ts = tareas.Tareas(raiz=d / "equipo_f2")
                ts.importar(d / "t.json")
                r = ts.ejecutar("LAB-003", motor.AgentesMotorLLM(be), autorizo_pruebas=True, instalar_senales=False)
                ev = (ts.lab.ruta("tareas", "LAB-003", "ejecuciones", "E001", "auditoria",
                                  "A3_evidencia_recibida.txt")).read_text()
                prompt = be.llamadas[-1]["mensajes"][-1]["content"]
                self.assertEqual([x for x in ev.splitlines() if x.strip() not in prompt], [])
                self.assertIn("NO es Project Zomboid", prompt)
                self.assertEqual((r["resultado"], r["auditoria_A3"]), ("esperado_confirmado", "conforme"))


if __name__ == "__main__":
    unittest.main()
