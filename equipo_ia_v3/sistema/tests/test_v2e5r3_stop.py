"""V2-E.5-r3: STOP determinista antes, durante y después de cada operación relevante.

Causa raíz demostrada (ver LEEME_V2E5R3.md §2): una parada PEDIDA que interrumpía la carga del servidor
o una petición HTTP llegaba al motor como ErrorInferencia y acababa en «error_critico». La prueba
heredada `test_stop_durante_la_tarea` escribía STOP con un temporizador de 1 s: según la velocidad
del equipo, el STOP caía entre dos pasos (→ detenido) o en mitad de la carga o de una petición
(→ error_critico). Aquí el STOP se coloca en el punto exacto con ganchos, sin depender del reloj.

Todo usa el servidor FALSO de las pruebas (tests/fake_llama_server.py), nunca el modelo real.
"""
import os
import threading
import unittest
from pathlib import Path
from unittest import mock

import _comun
from _v2 import EntornoV2
from eq2 import analisis_estatico, backend_llama, cliente_http, inferencia, motor, orquestador, servidor
from eq2.inferencia import ErrorInferencia, parada_de

T = "Escribe ordenar(xs) en Python sin modificar la lista de entrada."


class TestClasificacionDeMotivos(unittest.TestCase):
    def test_solo_las_formas_exactas_son_parada(self):
        self.assertEqual(parada_de("stop_usuario"), ("stop_usuario", "peticion_http"))
        self.assertEqual(parada_de("senal"), ("senal", "peticion_http"))
        self.assertEqual(parada_de("abortado_durante_carga:stop_usuario"), ("stop_usuario", "carga_servidor"))
        self.assertEqual(parada_de("parada_antes_de_lanzar:senal"), ("senal", "antes_de_lanzar"))
        for m in ("servidor_muerto", "plazo_agotado", "http_500", "timeout_carga", "abortado_durante_carga:presion",
                  "abortado_durante_carga:stop_usuario_x", "x:stop_usuario", "stop_usuario ", "", None,
                  "servidor_murio_al_arrancar_rc_1", "supervision_fallo", "conexion_perdida:ConnectionResetError"):
            with self.subTest(m=m):
                self.assertIsNone(parada_de(m))


class BaseStop(EntornoV2):
    carpeta_datos = "datos_v2e"

    def setUp(self):
        super().setUp()
        self.base = self.raiz / "datos_v2e"

    def stop(self):
        self.base.mkdir(parents=True, exist_ok=True)
        (self.base / "STOP").write_text("")

    def motor(self, be, **kw):
        return motor.Motor(self.base, motor.AgentesMotorLLM(be), analisis_estatico.EjecutorEstatico(), backend=be,
                           raiz_laboratorio=self.raiz, **kw)

    def sin_restos(self, be, inf=None):
        """STOP no deja procesos, puertos, candados ni temporales."""
        if be.srv.proc is not None:
            self.assertIsNotNone(be.srv.proc.poll(), "el servidor sigue vivo")
        self.assertTrue(servidor.puerto_libre(be.srv.puerto), "el puerto sigue ocupado")
        self.assertFalse((self.base / "lock").exists(), "queda el candado")
        restos = [p for p in self.base.rglob(".tmp_*")] if self.base.exists() else []
        self.assertEqual(restos, [], "quedan temporales")
        if inf is not None:
            self.assertTrue(inf["backend_informe"]["limpio"], inf["backend_informe"])

    def detenido(self, inf, punto, motivo="stop_usuario"):
        self.assertEqual((inf["estado_final"], inf["motivo"]), ("detenido", motivo), inf["errores"])
        p = inf["parada"]
        self.assertEqual((p["solicitada"], p["clasificacion"], p["fallos_independientes"]),
                         (True, "parada_limpia", []), p)
        self.assertTrue(p["punto"].startswith(punto), p)
        ordenes = [e["orden"] for e in p["traza"]]
        self.assertEqual(ordenes, list(range(1, len(ordenes) + 1)))
        ts = [e["t"] for e in p["traza"]]
        self.assertEqual(ts, sorted(ts))                                 # marcas monotónicas en orden
        self.assertEqual(p["traza"][-1]["evento"], "estado_final")
        return p


def en_peticion_post(accion, despues_de_comprobaciones=4):
    """Parchea cliente_http.peticion: en la petición POST ejecuta `accion()` cuando la petición ya se
    envió y el servidor falso la está atendiendo (n-ésima comprobación de parada)."""
    original = cliente_http.peticion

    def envoltura(puerto, metodo, ruta, cuerpo, plazo_s, deberia_parar=lambda: None, **kw):
        if metodo != "POST":
            return original(puerto, metodo, ruta, cuerpo, plazo_s, deberia_parar, **kw)
        n = [0]

        def dp():
            n[0] += 1
            if n[0] == despues_de_comprobaciones:
                accion()
            return deberia_parar()
        return original(puerto, metodo, ruta, cuerpo, plazo_s, dp, **kw)
    return mock.patch.object(cliente_http, "peticion", envoltura)


class TestStopMotor(BaseStop):
    def test_antes_de_empezar(self):
        self.stop()
        be = self.backend("motor_ok")
        inf = self.motor(be).ejecutar(T)
        self.detenido(inf, "antes_de_lanzar")
        self.assertIsNone(be.srv.proc)                                     # nunca se lanzó
        self.assertEqual(inf["llamadas_agentes"], 0)
        self.sin_restos(be)

    def test_durante_la_carga_del_servidor(self):
        be = self.backend("motor_ok", carga=30)                           # tarda 30 s en estar listo
        orig = servidor.ServidorLlama.lanzar

        def lanzar(srv, lab, run_id):
            pid = orig(srv, lab, run_id)
            self.stop()                                                   # STOP con el hijo ya lanzado
            return pid
        with mock.patch.object(servidor.ServidorLlama, "lanzar", lanzar):
            inf = self.motor(be).ejecutar(T)
        p = self.detenido(inf, "carga_servidor")
        self.assertEqual(p["error_que_la_materializo"], "abortado_durante_carga:stop_usuario")
        self.assertEqual(inf["llamadas_agentes"], 0)
        self.sin_restos(be, inf)

    def test_durante_una_peticion_http(self):
        be = self.backend("motor_ok", pausa=30)                           # cada respuesta tarda 30 s
        with en_peticion_post(self.stop):
            inf = self.motor(be).ejecutar(T)
        p = self.detenido(inf, "peticion_http")
        self.assertEqual(p["error_que_la_materializo"], "stop_usuario")
        self.assertLess(inf["metricas"]["duracion_s"], 10)               # no esperó a la respuesta
        self.sin_restos(be, inf)

    def test_senal_durante_una_peticion_http(self):
        be = self.backend("motor_ok", pausa=30)
        m = self.motor(be)
        with en_peticion_post(m.solicitar_parada):
            inf = m.ejecutar(T)
        p = self.detenido(inf, "peticion_http", motivo="senal")
        self.assertEqual(p["traza"][0]["evento"], "parada_solicitada")
        self.sin_restos(be, inf)

    def test_entre_dos_pasos(self):
        be = self.backend("motor_ok")
        orig = motor.AgentesMotorLLM._llamar

        def llamar(ag, *a, **k):
            r = orig(ag, *a, **k)
            if ag.llamadas == 1:
                self.stop()                                               # tras la 1.ª respuesta completa
            return r
        with mock.patch.object(motor.AgentesMotorLLM, "_llamar", llamar):
            inf = self.motor(be).ejecutar(T)
        self.detenido(inf, "entre_pasos:")
        self.assertEqual(inf["llamadas_agentes"], 1)
        self.sin_restos(be, inf)

    def test_stop_borrado_justo_despues_de_detectarlo(self):
        """Carrera: el usuario borra STOP mientras la petición se interrumpe. La parada detectada se
        retiene: sigue siendo «detenido» (antes podía acabar en error_critico)."""
        be = self.backend("motor_ok", pausa=30)
        m = self.motor(be)
        orig = motor.Motor._motivo_parada

        def mp(self_):
            r = orig(self_)
            if r == "stop_usuario" and (self.base / "STOP").exists():
                (self.base / "STOP").unlink()
            return r
        with en_peticion_post(self.stop), mock.patch.object(motor.Motor, "_motivo_parada", mp):
            inf = m.ejecutar(T)
        self.detenido(inf, "peticion_http")
        self.assertFalse((self.base / "STOP").exists())
        self.sin_restos(be, inf)

    def test_parada_repetida(self):
        be = self.backend("motor_ok", pausa=30)
        m = self.motor(be)

        def doble():
            self.stop()
            m.solicitar_parada()
            m.solicitar_parada()
            self.stop()
        with en_peticion_post(doble):
            inf = m.ejecutar(T)
        p = self.detenido(inf, "peticion_http", motivo="senal")
        self.assertEqual(sum(e["evento"] == "parada_detectada" for e in p["traza"]), 1)
        self.sin_restos(be, inf)
        be2 = self.backend("motor_ok")                                    # STOP sigue ahí: otra ejecución
        inf2 = self.motor(be2).ejecutar(T)
        self.detenido(inf2, "antes_de_lanzar")
        self.sin_restos(be2)

    def test_despues_de_terminar_no_afecta_al_resultado(self):
        be = self.backend("motor_ok")
        inf = self.motor(be).ejecutar(T)
        self.stop()
        self.assertEqual(inf["estado_final"], "sin_verificar", inf["errores"])
        self.assertEqual(inf["parada"], {"solicitada": False, "clasificacion": "sin_parada"})
        self.sin_restos(be, inf)

    def test_fallo_de_limpieza_se_informa_sin_cambiar_la_parada(self):
        be = self.backend("motor_ok", pausa=30)
        orig = backend_llama.BackendLlama.detener

        def detener_que_falla(b):
            orig(b)                                                       # limpia de verdad...
            raise OSError("fallo simulado al cerrar")                     # ...pero informa un fallo
        with en_peticion_post(self.stop), mock.patch.object(backend_llama.BackendLlama, "detener",
                                                            detener_que_falla):
            inf = self.motor(be).ejecutar(T)
        p = inf["parada"]
        self.assertEqual((inf["estado_final"], p["clasificacion"]), ("detenido", "parada_con_fallo_de_limpieza"))
        self.assertIn("backend_detener:OSError", p["fallos_independientes"])
        self.assertIn("limpieza:detener_fallo", p["fallos_independientes"])
        self.sin_restos(be)

    def test_fallo_independiente_durante_la_parada_no_se_oculta(self):
        be = self.backend("motor_ok")
        orig = backend_llama.BackendLlama.completar

        def completar(b, *a, **k):
            self.stop()
            raise ErrorInferencia("servidor_muerto", fatal=True)          # fallo real, NO la parada
        with mock.patch.object(backend_llama.BackendLlama, "completar", completar):
            inf = self.motor(be).ejecutar(T)
        p = inf["parada"]
        self.assertEqual((inf["estado_final"], inf["motivo"]), ("error_critico", "inferencia:servidor_muerto"))
        self.assertEqual((p["solicitada"], p["clasificacion"]), (True, "fallo_independiente_durante_parada"))
        self.assertIn("error_critico:inferencia:servidor_muerto", p["fallos_independientes"])
        self.sin_restos(be, inf)
        self.assertIs(orig, backend_llama.BackendLlama.completar)

    def test_sin_stop_un_motivo_de_parada_falso_es_error_critico(self):
        """Un ErrorInferencia «stop_usuario» SIN parada detectada no se convierte en «detenido»."""
        be = self.backend("motor_ok")
        with mock.patch.object(backend_llama.BackendLlama, "completar",
                               lambda b, *a, **k: (_ for _ in ()).throw(ErrorInferencia("stop_usuario", True))):
            inf = self.motor(be).ejecutar(T)
        self.assertEqual((inf["estado_final"], inf["parada"]["solicitada"]), ("error_critico", False))
        self.sin_restos(be, inf)


class TestStopOrquestador(BaseStop):
    def orq_(self, be):
        return orquestador.Orquestador(self.base, be, self.vigilante(), raiz_laboratorio=self.raiz)

    def test_durante_una_peticion_http(self):
        be = self.backend("normal", pausa=30)
        with en_peticion_post(self.stop):
            res = self.orq_(be).run_deliberacion([T])
        self.assertEqual((res["estado"], res["motivo_fin"]), ("interrumpida", "stop_usuario"))
        self.assertEqual(res["parada"]["clasificacion"], "parada_limpia", res["parada"])
        self.sin_restos(be)

    def test_durante_la_carga(self):
        be = self.backend("normal", carga=30)
        orig = servidor.ServidorLlama.lanzar

        def lanzar(srv, lab, run_id):
            pid = orig(srv, lab, run_id)
            self.stop()
            return pid
        with mock.patch.object(servidor.ServidorLlama, "lanzar", lanzar):
            res = self.orq_(be).run_deliberacion([T])
        self.assertEqual((res["estado"], res["motivo_fin"]), ("interrumpida", "stop_usuario"))
        self.assertEqual(res["parada"]["clasificacion"], "parada_limpia")
        self.sin_restos(be)

    def test_fallo_de_arranque_con_stop_presente_no_se_oculta(self):
        """Antes, «la parada pedida manda sobre el fallo» convertía cualquier fallo de arranque en
        interrumpida/stop_usuario si había un STOP: ocultaba el fallo real."""
        be = self.backend("normal")

        def iniciar(b, ctx=None):
            self.stop()
            raise ErrorInferencia("servidor_murio_al_arrancar_rc_1", fatal=True)
        with mock.patch.object(backend_llama.BackendLlama, "iniciar", iniciar):
            res = self.orq_(be).run_deliberacion([T])
        self.assertEqual(res["motivo_fin"], "backend_no_inicia:servidor_murio_al_arrancar_rc_1")
        self.assertEqual(res["parada"]["clasificacion"], "fallo_independiente_durante_parada")
        self.sin_restos(be)


if __name__ == "__main__":
    unittest.main()
