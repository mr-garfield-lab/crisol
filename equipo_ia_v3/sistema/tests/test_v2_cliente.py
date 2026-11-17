"""cliente_http contra servidores TCP guionizados en 127.0.0.1 (sockets reales, sin Qwen)."""
import time
import unittest

import _comun
from eq2 import cliente_http as ch, config


def leer_peticion(c):
    datos = b""
    while b"\r\n\r\n" not in datos:
        t = c.recv(4096)
        if not t:
            return datos
        datos += t
    cab, _, resto = datos.partition(b"\r\n\r\n")
    n = 0
    for l in cab.split(b"\r\n"):
        if l.lower().startswith(b"content-length:"):
            n = int(l.split(b":")[1])
    while len(resto) < n:
        resto += c.recv(4096)
    return datos


def resp(cuerpo=b'{"ok":true}', status=b"200 OK", extra=b""):
    return (b"HTTP/1.1 " + status + b"\r\nContent-Length: " + str(len(cuerpo)).encode()
            + b"\r\n" + extra + b"\r\n" + cuerpo)


class T(unittest.TestCase):
    def srv(self, guion):
        s = _comun.ServidorTCP(guion)
        self.addCleanup(s.cerrar)
        return s

    def test_respuesta_normal(self):
        s = self.srv(lambda c: (leer_peticion(c), c.sendall(resp())))
        r = ch.peticion(s.puerto, "POST", "/x", b'{"a":1}', 5)
        self.assertEqual((r.status, r.cuerpo), (200, b'{"ok":true}'))

    def test_cabeceras_enviadas(self):
        visto = {}

        def g(c):
            visto["p"] = leer_peticion(c)
            c.sendall(resp())
        s = self.srv(g)
        ch.peticion(s.puerto, "POST", "/v1/chat/completions", b'{"a":1}', 5)
        p = visto["p"].decode()
        self.assertTrue(p.startswith("POST /v1/chat/completions HTTP/1.1\r\n"))
        self.assertIn(f"Host: 127.0.0.1:{s.puerto}", p)
        self.assertIn("Content-Length: 7", p)
        self.assertIn("Connection: close", p)

    def test_chunked(self):
        def g(c):
            leer_peticion(c)
            c.sendall(b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n"
                      b"5\r\nhello\r\n6\r\n world\r\n0\r\n\r\n")
        s = self.srv(g)
        self.assertEqual(ch.peticion(s.puerto, "GET", "/h", None, 5).cuerpo, b"hello world")

    def test_chunked_incompleto_y_cierre(self):
        def g(c):
            leer_peticion(c)
            c.sendall(b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n5\r\nhel")
            c.close()
        s = self.srv(g)
        with self.assertRaises(ch.ErrorHTTP) as e:
            ch.peticion(s.puerto, "GET", "/h", None, 5)
        self.assertEqual(e.exception.motivo, "respuesta_truncada")

    def test_sin_content_length_lee_hasta_cierre(self):
        def g(c):
            leer_peticion(c)
            c.sendall(b"HTTP/1.1 200 OK\r\n\r\ncuerpo libre")
            c.close()
        s = self.srv(g)
        self.assertEqual(ch.peticion(s.puerto, "GET", "/h", None, 5).cuerpo, b"cuerpo libre")

    def test_status_no_200_se_devuelve(self):
        s = self.srv(lambda c: (leer_peticion(c), c.sendall(resp(b"x", b"503 Service Unavailable"))))
        self.assertEqual(ch.peticion(s.puerto, "GET", "/h", None, 5).status, 503)

    def test_malformadas(self):
        casos = {"estado_malformado": b"BASURA\r\n\r\n",
                 "content_length_invalido": b"HTTP/1.1 200 OK\r\nContent-Length: abc\r\n\r\n",
                 "respuesta_demasiado_grande": b"HTTP/1.1 200 OK\r\nContent-Length: 99999999\r\n\r\n",
                 "respuesta_truncada": b"HTTP/1.1 200 OK\r\nContent-Length: 10\r\n\r\nabc"}
        for esperado, datos in casos.items():
            with self.subTest(esperado):
                def g(c, d=datos):
                    leer_peticion(c)
                    c.sendall(d)
                    c.close()
                s = self.srv(g)
                with self.assertRaises(ch.ErrorHTTP) as e:
                    ch.peticion(s.puerto, "GET", "/h", None, 5)
                self.assertEqual(e.exception.motivo, esperado)
                self.assertFalse(e.exception.fatal)

    def test_cierra_sin_responder(self):
        s = self.srv(lambda c: (leer_peticion(c), c.close()))
        with self.assertRaises(ch.ErrorHTTP) as e:
            ch.peticion(s.puerto, "GET", "/h", None, 5)
        self.assertEqual(e.exception.motivo, "respuesta_truncada")

    def test_conexion_rechazada(self):
        p = _comun.puerto_aleatorio()
        with self.assertRaises(ch.ErrorHTTP) as e:
            ch.peticion(p, "GET", "/h", None, 5)
        self.assertTrue(e.exception.motivo.startswith("conexion_fallida"))

    # --- plazo efectivo: la operación bloqueada SE DETIENE ---------------------
    def test_servidor_mudo_plazo_efectivo(self):
        s = self.srv(lambda c: (leer_peticion(c), time.sleep(30)))
        t = time.monotonic()
        with self.assertRaises(ch.ErrorHTTP) as e:
            ch.peticion(s.puerto, "POST", "/x", b"{}", 1.0, intervalo=0.1)
        self.assertEqual(e.exception.motivo, "plazo_agotado")
        self.assertTrue(e.exception.fatal)
        self.assertLess(time.monotonic() - t, 2.5)

    def test_goteo_lento_no_evita_el_plazo(self):
        def g(c):
            leer_peticion(c)
            c.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 100000\r\n\r\n")
            for _ in range(200):
                c.sendall(b" ")
                time.sleep(0.1)
        s = self.srv(g)
        t = time.monotonic()
        with self.assertRaises(ch.ErrorHTTP) as e:
            ch.peticion(s.puerto, "POST", "/x", b"{}", 1.0, intervalo=0.1)
        self.assertEqual(e.exception.motivo, "plazo_agotado")
        self.assertLess(time.monotonic() - t, 2.5)

    def test_servidor_que_no_lee_el_cuerpo(self):
        s = self.srv(lambda c: time.sleep(30))          # acepta y no lee nada
        t = time.monotonic()
        with self.assertRaises(ch.ErrorHTTP) as e:
            ch.peticion(s.puerto, "POST", "/x", b"x" * 20_000_000, 1.0, intervalo=0.1)
        self.assertIn(e.exception.motivo, ("plazo_agotado",))
        self.assertLess(time.monotonic() - t, 3)

    def test_parada_solicitada_interrumpe(self):
        s = self.srv(lambda c: (leer_peticion(c), time.sleep(30)))
        t0 = time.monotonic()
        parar = lambda: "stop_usuario" if time.monotonic() - t0 > 0.5 else None
        with self.assertRaises(ch.ErrorHTTP) as e:
            ch.peticion(s.puerto, "POST", "/x", b"{}", 30, parar, intervalo=0.1)
        self.assertEqual(e.exception.motivo, "stop_usuario")
        self.assertLess(time.monotonic() - t0, 2)

    def test_parada_antes_de_conectar_no_abre_socket(self):
        s = self.srv(lambda c: None)
        with self.assertRaises(ch.ErrorHTTP):
            ch.peticion(s.puerto, "GET", "/h", None, 5, lambda: "senal")
        time.sleep(0.2)
        self.assertEqual(s.conexiones, [])

    def test_fallo_del_supervisor_aborta(self):
        s = self.srv(lambda c: (leer_peticion(c), time.sleep(30)))

        def malo():
            raise RuntimeError("x")
        with self.assertRaises(ch.ErrorHTTP) as e:
            ch.peticion(s.puerto, "GET", "/h", None, 5, malo, intervalo=0.1)
        self.assertEqual(e.exception.motivo, "supervision_fallo")

    def test_respuesta_enorme_se_corta(self):
        def g(c):
            leer_peticion(c)
            c.sendall(b"HTTP/1.1 200 OK\r\n\r\n")
            for _ in range(100):
                c.sendall(b"x" * 100_000)
        s = self.srv(g)
        with self.assertRaises(ch.ErrorHTTP) as e:
            ch.peticion(s.puerto, "GET", "/h", None, 10)
        self.assertEqual(e.exception.motivo, "respuesta_demasiado_grande")

    def test_argumentos_invalidos(self):
        for p in (0, 80, 1023, 70000, "8089", None):
            with self.assertRaises(ValueError):
                ch.peticion(p, "GET", "/h", None, 1)
        for m, r in (("DELETE", "/x"), ("GET", "x"), ("GET", "http://evil/")):
            with self.assertRaises(ValueError):
                ch.peticion(8089, m, r, None, 1)

    def test_solo_loopback(self):
        import inspect
        fuente = inspect.getsource(ch)
        self.assertIn("(config.HOST, puerto)", fuente)
        self.assertEqual(config.HOST, "127.0.0.1")
        self.assertNotIn("0.0.0.0", fuente)


if __name__ == "__main__":
    unittest.main()
