"""V2-E.7-r2: integración de PZ ModLab 0.2 con el equipo. UNA demostración del escenario de FALLO INTENCIONAL:
A1 prepara el escenario, A2 solicita las pruebas (una permitida y una prohibida), la herramienta de lista blanca se
ejecuta de verdad y A3 audita; todo queda guardado y se exporta. Los textos de los agentes vienen de un GUION
(aquí no hay Qwen); la simulación, el guardado y la exportación son REALES."""
import ast
import json
import unittest
import zipfile
from pathlib import Path

import _comun
from eq2 import modlab_pz_adaptador, motor, tareas

RAIZ = _comun.RAIZ
ESC = ('ARCHIVO: escenario.json\n```json\n{"acciones": [{"accion": "agregar", "objeto": "Base.Hammer", "cantidad": 1},'
       ' {"accion": "consumir", "objeto": "Base.Hammer", "cantidad": 2},'
       ' {"accion": "comprobar", "objeto": "Base.Hammer", "cantidad": 1}]}\n```\nFIN')


def guion(paso, n, **kw):
    return {"pz_escenario": ESC,
            "pz_solicitar": "SOLICITO: simular_escenario escenario.json\nSOLICITO: ejecutar_lua_de_terceros escenario.json",
            "pz_auditar": "AUDITORIA: conforme\nOBSERVACION: el consumo de 2 con 1 en inventario falla como se esperaba"}[paso]  # CAMBIO V2-E.7-r3 (V2-E.7-r2: auditar)


class TestModlabPZ(unittest.TestCase):
    def test_fallo_intencional_a1_a2_a3_guardado_y_exportado(self):
        tmp = _comun.carpeta_temporal()
        self.addCleanup(tmp.cleanup)
        ts = tareas.Tareas(raiz=Path(tmp.name) / "equipo_f2")
        t = ts.importar(RAIZ / "ejemplos" / "tarea_pz_fallo_intencional.json")
        r = ts.ejecutar(t["id"], motor.AgentesMotorSimulados(guion), autorizo_pruebas=True, instalar_senales=False)
        self.assertEqual((r["estado_final"], r["resultado"], r["herramientas_ejecutadas"], r["auditoria_A3"]),
                         ("completada", "esperado_confirmado", 1, "conforme"), r)
        e = ts.lab.ruta("tareas", t["id"], "ejecuciones", "E001")
        regs = [json.loads((e / "herramientas" / h / "registro.json").read_text()) for h in ("H001", "H002")]
        self.assertEqual([(x["operacion"], x["estado"]) for x in regs],
                         [("simular_escenario", "ejecutada"), ("ejecutar_lua_de_terceros", "rechazada_por_contrato")])
        res = json.loads((e / "herramientas" / "H001" / "resultado.json").read_text())
        self.assertEqual([p["ok"] for p in res["pasos"]], [True, False, True])
        self.assertFalse(res["todos_ok"])
        self.assertTrue((e / "escenario" / "escenario.json").is_file())
        self.assertFalse((e / "herramientas" / "H002" / "resultado.json").exists())
        self.assertFalse((e / "lock").exists())
        # sin autorización: A2 puede pedir, pero nada se ejecuta y no hay conclusión
        r2 = ts.ejecutar(t["id"], motor.AgentesMotorSimulados(guion), autorizo_pruebas=False, instalar_senales=False)
        self.assertEqual((r2["resultado"], r2["herramientas_ejecutadas"]), ("sin_pruebas", 0))
        z = ts.exportar(t["id"])
        with zipfile.ZipFile(z) as zf:
            n = zf.namelist()
        for fin in ("E001/escenario/escenario.json", "E001/herramientas/H001/resultado.json",
                    "E001/auditoria/A3_auditoria.txt", "E001/agentes/A2_solicitudes.txt", "MANIFIESTO_SHA256.txt"):
            self.assertTrue(any(x.endswith(fin) for x in n), fin)

    def test_adaptador_solo_lista_blanca(self):
        with self.assertRaises(PermissionError):
            modlab_pz_adaptador.ejecutar("ejecutar_lua_de_terceros", RAIZ / "modlab_pz" / "fixtures" / "mod_ejemplo_propio.lua")
        arbol = ast.parse((RAIZ / "src" / "eq2" / "modlab_pz_adaptador.py").read_text(encoding="utf-8"))
        usados = {n.attr for n in ast.walk(arbol) if isinstance(n, ast.Attribute)}
        self.assertFalse(usados & {"comprobar_sintaxis_archivo", "main", "run", "Popen"}, usados)
        self.assertEqual(set(modlab_pz_adaptador.EXTENSION),
                         set(json.loads((RAIZ / "modlab_pz" / "contrato_agentes.json").read_text())["operaciones_permitidas"]))


if __name__ == "__main__":
    unittest.main()
