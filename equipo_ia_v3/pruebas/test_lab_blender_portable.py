"""Pruebas del banco portable (lab_blender/portable.py) con un servidor de modelos SIMULADO en esta máquina (127.0.0.1).
La prueba completa usa el Blender real y se OMITE si no está."""
import json
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "lab_blender"))
import ejecutor as E  # noqa: E402
import portable as P  # noqa: E402
import tareas as T  # noqa: E402


class Servidor:
    """Servidor mínimo con la forma de /v1/chat/completions: responde lo que diga `responder(mensajes)`."""

    def __init__(self, responder):
        vistos = self.vistos = []

        class Manejador(BaseHTTPRequestHandler):
            def do_POST(self):
                cuerpo = json.loads(self.rfile.read(int(self.headers["Content-Length"])).decode("utf-8"))
                vistos.append({"ruta": self.path, "cuerpo": cuerpo, "autorizacion": self.headers.get("Authorization")})
                datos = json.dumps({"choices": [{"message": {"content": responder(cuerpo["messages"])},
                                                 "finish_reason": "stop"}], "usage": {"completion_tokens": 7}}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(datos)))
                self.end_headers()
                self.wfile.write(datos)

            def log_message(self, *a):
                pass
        self.http = HTTPServer(("127.0.0.1", 0), Manejador)
        self.url = f"http://127.0.0.1:{self.http.server_address[1]}/v1"
        self.hilo = threading.Thread(target=self.http.serve_forever, daemon=True)

    def __enter__(self):
        self.hilo.start()
        return self

    def __exit__(self, *a):
        self.http.shutdown()
        self.http.server_close()


class Cliente(unittest.TestCase):
    def test_peticion_y_respuesta(self):
        with Servidor(lambda msgs: "```python\nimport bpy\n```") as s:
            texto, tokens, fin = P.cliente(s.url, "mi-modelo")([{"role": "user", "content": "hola"}], 800)
        self.assertEqual((texto, tokens, fin), ("```python\nimport bpy\n```", 7, "stop"))
        v = s.vistos[0]
        self.assertEqual(v["ruta"], "/v1/chat/completions")
        self.assertEqual((v["cuerpo"]["model"], v["cuerpo"]["max_tokens"], v["cuerpo"]["temperature"]), ("mi-modelo", 800, 0))
        self.assertIsNone(v["autorizacion"])                            # sin clave no se manda cabecera de autorización

    def test_servidor_apagado_no_se_finge(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            if not E.blender_exe():
                self.skipTest("OMITIDO: no hay Blender instalado")
            r = P.correr(Path(d) / "ev", Path(d) / "bl", "http://127.0.0.1:9/v1", "m", ids=["T01"])
            self.assertIn("abortada", r)
            self.assertEqual(P.B.leer_filas(Path(d) / "ev"), [])


@unittest.skipUnless(E.blender_exe(), "OMITIDO: no hay Blender instalado")
class Completo(unittest.TestCase):
    """REAL en Blender; el «modelo» es el servidor simulado, que falla el primer intento y acierta el segundo."""

    def test_falla_corrige_y_aprueba(self):
        def responder(msgs):
            usuario = msgs[1]["content"]
            if "Tu script anterior" not in usuario:                      # primer intento: cubo del tamaño equivocado
                return "Aquí va:\n```python\nimport bpy\nbpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 1))\n" \
                       "bpy.context.active_object.name = \"Caja\"\n```"
            return "```python\n" + T.REFERENCIAS["T01"] + "```"

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d, Servidor(responder) as s:
            r = P.correr(Path(d) / "ev", Path(d) / "bl", s.url, "simulado", ids=["T01"])
            filas = P.B.leer_filas(Path(d) / "ev")
            self.assertNotIn("abortada", r)
            self.assertEqual([(f["intento"], f["estado"], f["aprobado"]) for f in filas], [(1, "OK", False), (2, "OK", True)])
            self.assertIn("mide (1.00, 1.00, 1.00)", s.vistos[1]["cuerpo"]["messages"][1]["content"])
            self.assertIn("✔ al intento 2", (Path(d) / "ev" / "INFORME.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
