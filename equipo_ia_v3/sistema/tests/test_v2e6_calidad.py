"""V2-E.6 área 8: STOP durante la CONTINUACIÓN y la LIMPIEZA (servidor FALSO), reanudación EXPLÍCITA,
sesiones y aprendizaje aislados, transacciones SQLite y fallos del modelo sin pérdida silenciosa de evidencia."""
import json
import sqlite3
import unittest
from pathlib import Path
from unittest import mock

import _comun
from _v2 import EntornoV2
from eq2 import aprendizaje as A, backend_llama, cliente_http, config, inferencia, orquestador, servidor, vigilancia
from eq2.inferencia import ErrorInferencia

T = "Escribe ordenar(xs) en Python sin modificar la lista de entrada."
AYUDA_PREFILL = _comun.AYUDA_COMPLETA + " --no-prefill-assistant"


class BaseFalso(EntornoV2):
    def setUp(self):
        super().setUp()
        self.base = self.raiz / "lab_v2e6"

    def stop(self):
        self.base.mkdir(parents=True, exist_ok=True)
        (self.base / "STOP").write_text("")

    def orq_(self, be):
        return orquestador.Orquestador(self.base, be, self.vigilante(), raiz_laboratorio=self.raiz)

    def sin_restos(self, be):
        if be.srv.proc is not None:
            self.assertIsNotNone(be.srv.proc.poll(), "el servidor sigue vivo")
        self.assertTrue(servidor.puerto_libre(be.srv.puerto))
        self.assertFalse((self.base / "lock").exists())
        self.assertEqual(list(self.base.rglob(".tmp_*")), [])


def en_continuacion(accion):
    """Ejecuta `accion()` dentro de la petición HTTP de CONTINUACIÓN (último mensaje «assistant»)."""
    original = cliente_http.peticion

    def envoltura(puerto, metodo, ruta, cuerpo, plazo_s, deberia_parar=lambda: None, **kw):
        datos = cuerpo if isinstance(cuerpo, dict) else json.loads(cuerpo or b"{}") if cuerpo else {}
        if metodo == "POST" and (datos.get("messages") or [{}])[-1].get("role") == "assistant":
            def dp():
                accion()
                return deberia_parar()
            return original(puerto, metodo, ruta, cuerpo, plazo_s, dp, **kw)
        return original(puerto, metodo, ruta, cuerpo, plazo_s, deberia_parar, **kw)
    return mock.patch.object(cliente_http, "peticion", envoltura)


class TestStopContinuacionYLimpieza(BaseFalso):
    def test_stop_durante_la_continuacion(self):
        be = self.backend("propuesta_y_replica_cortadas", srv_kw={"ayuda_fn": lambda: AYUDA_PREFILL})
        with en_continuacion(self.stop):
            res = self.orq_(be).run_deliberacion([T])
        self.assertEqual((res["estado"], res["motivo_fin"]), ("interrumpida", "stop_usuario"))
        self.assertEqual(res["parada"]["clasificacion"], "parada_limpia", res["parada"])
        self.assertEqual(res["tareas"][0]["estado"], "abortada")
        con = sqlite3.connect(str(self.base / "datos" / "sesion.db"))
        try:
            turnos = [tuple(r) for r in con.execute("SELECT fase, tipo, estado FROM turnos ORDER BY id")]
            ev = [r[0] for r in con.execute("SELECT tipo FROM eventos ORDER BY id")]
        finally:
            con.close()
        self.assertIn(("propuesta", "normal", "ok"), turnos)                 # la propuesta cortada quedó
        self.assertTrue(any(t[1] == "continuacion" for t in turnos), turnos)  # y el intento de continuarla
        self.assertIn("sesion_abortada", ev)
        self.sin_restos(be)

    def test_stop_durante_la_limpieza_no_cambia_un_resultado_terminado(self):
        be = self.backend("normal")
        original = backend_llama.BackendLlama.detener

        def detener(b):
            self.stop()                                    # el STOP llega cuando el trabajo ya terminó
            return original(b)
        with mock.patch.object(backend_llama.BackendLlama, "detener", detener):
            res = self.orq_(be).run_deliberacion([T])
        self.assertEqual(res["estado"], "completa")
        self.assertEqual(res["parada"]["clasificacion"], "sin_parada")
        self.assertTrue((self.base / "STOP").exists())     # no se borra en silencio: lo verá la próxima sesión
        self.sin_restos(be)

    def test_stop_y_fallo_de_limpieza_se_distinguen(self):
        be = self.backend("normal", pausa=30)
        original = backend_llama.BackendLlama.detener

        def detener(b):
            inf = original(b)
            inf = dict(inf, limpio=False, problemas=list(inf.get("problemas", [])) + ["puerto_ocupado_simulado"])
            return inf
        from test_v2e5r3_stop import en_peticion_post
        with en_peticion_post(self.stop), mock.patch.object(backend_llama.BackendLlama, "detener", detener):
            res = self.orq_(be).run_deliberacion([T])
        self.assertEqual(res["motivo_fin"], "stop_usuario")
        self.assertEqual(res["parada"]["clasificacion"], "parada_con_fallo_de_limpieza", res["parada"])
        self.assertTrue(any("puerto_ocupado_simulado" in f for f in res["parada"]["fallos_independientes"]))
        self.assertEqual(res["resultado_global"], "incompleto")

    def test_fallo_del_modelo_a_mitad_no_pierde_evidencia(self):
        be = self.backend("http500", en=3)
        res = self.orq_(be).run_deliberacion([T])
        self.assertNotEqual(res["resultado_global"], "completo")
        run = self.base / "runs" / res["run_id"]
        for f in ("summary.json", "eventos.jsonl", "tareas.json", "server.log"):
            self.assertTrue((run / f).is_file(), f)
        con = sqlite3.connect(str(self.base / "datos" / "sesion.db"))
        try:
            n = con.execute("SELECT COUNT(*) FROM turnos").fetchone()[0]
            estados = [r[0] for r in con.execute("SELECT estado FROM turnos ORDER BY id")]
        finally:
            con.close()
        self.assertGreaterEqual(n, 3)
        self.assertIn("fallido", estados)                  # el fallo queda registrado, no se oculta
        self.sin_restos(be)


class TestReanudacion(unittest.TestCase):
    def setUp(self):
        tmp = _comun.carpeta_temporal()
        self.addCleanup(tmp.cleanup)
        self.raiz = Path(tmp.name) / "equipo_f2"
        self.base = self.raiz / "lab_v2e6"

    def orq(self, be):
        v = vigilancia.Vigilante(lector_mem=lambda: 1_500_000, lector_bat=lambda: (80, False))
        return orquestador.Orquestador(self.base, be, v, reloj=_comun.Reloj(), raiz_laboratorio=self.raiz)

    def test_reanuda_solo_lo_pendiente_en_una_sesion_nueva(self):
        stop = self.base / "STOP"

        def g(n, fase, mensajes, max_tokens):
            if n == 9:                                     # a mitad de la 2ª tarea
                stop.write_text("")
            return "VOTO: aprobar\nRAZON: simulado" if fase == "voto" else f"[simulado] {fase}"
        tareas = [T, T + " (dos)", T + " (tres)"]
        r1 = self.orq(inferencia.BackendSimulado(g)).run_deliberacion(tareas)
        self.assertEqual((r1["estado"], r1["motivo_fin"]), ("interrumpida", "stop_usuario"))
        antes = sorted(p.name for p in (self.base / "runs" / r1["run_id"]).iterdir())
        stop.unlink()
        o = self.orq(inferencia.BackendSimulado())
        pend = o.pendientes_de(r1["run_id"])
        self.assertEqual((pend["completas"], pend["indices_pendientes"]), ([0], [1, 2]))
        r2 = o.run_reanudacion(r1["run_id"])
        self.assertEqual(r2["estado"], "completa")
        self.assertEqual(len(r2["tareas"]), 2)
        self.assertEqual(r2["reanuda"]["run_id"], r1["run_id"])
        self.assertNotEqual(r2["sesion_id"], r1["sesion_id"])
        self.assertEqual(sorted(p.name for p in (self.base / "runs" / r1["run_id"]).iterdir()), antes)  # intacta
        ev = (self.base / "runs" / r2["run_id"] / "eventos.jsonl").read_text()
        self.assertIn('"tipo": "reanudacion"', ev)
        self.assertEqual(self.orq(inferencia.BackendSimulado()).run_reanudacion(r2["run_id"])["estado"],
                         "nada_que_reanudar")

    def test_reanudacion_rechaza_entradas_no_validas(self):
        r = self.orq(inferencia.BackendSimulado()).run_deliberacion([T])
        o = self.orq(inferencia.BackendSimulado())
        for mal in ("../x", "abc", r["run_id"] + "/..", None):
            with self.subTest(mal=mal), self.assertRaises(ValueError):
                o.pendientes_de(mal)
        with self.assertRaises(FileNotFoundError):
            o.pendientes_de("20200101_000000_000000_1")
        p = self.base / "runs" / r["run_id"] / "tareas.json"
        d = json.loads(p.read_text())
        d["tareas"][0] = "otra tarea"
        p.chmod(0o600)
        p.write_text(json.dumps(d))
        with self.assertRaisesRegex(ValueError, "huellas"):
            o.pendientes_de(r["run_id"])


class TestAislamientoYTransacciones(unittest.TestCase):
    def test_bases_de_aprendizaje_aisladas_por_agente_y_transaccion(self):
        tmp = _comun.carpeta_temporal()
        self.addCleanup(tmp.cleanup)
        d = Path(tmp.name)
        a1 = A.AprendizajeAgente(d / "a1.db", "A1")
        self.addCleanup(a1.cerrar)
        rid = a1.recordar("hecho", "sorted devuelve una copia", "observado")["id"]
        n_ev = a1.con.execute("SELECT COUNT(*) FROM evidencias").fetchone()[0]
        # una transición rechazada no deja evidencia a medias ni cambia el estado
        with self.assertRaises(ValueError):
            a1.transicion(rid, "refutada", "sin evidencia")
        self.assertEqual((a1.estado(rid), a1.con.execute("SELECT COUNT(*) FROM evidencias").fetchone()[0]),
                         ("hipotesis", n_ev))
        with self.assertRaises(A.EsquemaIncompatible):
            A.AprendizajeAgente(d / "a1.db", "A3")                     # un agente no abre la base de otro

    def test_limite_de_recuerdos(self):
        tmp = _comun.carpeta_temporal()
        self.addCleanup(tmp.cleanup)
        a = A.AprendizajeAgente(Path(tmp.name) / "a.db", "A2")
        self.addCleanup(a.cerrar)
        with a.con:
            a.con.execute("DROP TRIGGER apr_rec_limite")
            a.con.execute("CREATE TRIGGER apr_rec_limite BEFORE INSERT ON recuerdos WHEN (SELECT COUNT(*) FROM "
                          "recuerdos) >= 2 BEGIN SELECT RAISE(ABORT, 'límite de recuerdos del agente'); END")
        a.recordar("hecho", "uno distinto del resto", "observado")
        a.recordar("hecho", "dos diferente a los demás", "observado")
        with self.assertRaises(sqlite3.DatabaseError):
            a.recordar("hecho", "tres que ya no cabe aquí", "observado")
        self.assertEqual(len(a.vigentes()), 2)                         # la transacción se revirtió entera
        self.assertEqual(a.con.execute("SELECT COUNT(*) FROM transiciones").fetchone()[0], 2)


if __name__ == "__main__":
    unittest.main()
