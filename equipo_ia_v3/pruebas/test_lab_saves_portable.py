"""Pruebas del banco portable de partidas (lab_saves/docker/portable.py), con partidas sintéticas y un servidor de
modelos SIMULADO: no se tocan partidas reales."""
import json
import struct
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "lab_saves" / "docker"))
import crear_copias_pz as CPZ  # noqa: E402
import portable as P  # noqa: E402

V = 249


def partida_jugada(base, nombre):
    """Partida sintética con forma de B42 sana, con chunks de sobra para que `_jugada` la acepte."""
    c = Path(base) / nombre
    (c / "map" / "10").mkdir(parents=True)
    texto = "Mapa A;Mapa B"
    (c / "map_ver.bin").write_bytes(struct.pack(">ii", V, len(texto)) + texto.encode("utf-16-be"))
    for n, f in (("map_t.bin", b"GMTM"), ("map_meta.bin", b"META"), ("map_animals.bin", b"ZONE"), ("gos_trap.bin", b"GLOS")):
        (c / n).write_bytes(f + struct.pack(">i", V) + bytes(range(1, 60)))
    (c / "map.bin").write_bytes(bytes(12))
    (c / "WorldDictionary.bin").write_bytes(b"\x00\x00\x00\x01" + b"x" * 40)
    for y in range(30):
        (c / "map" / "10" / f"{y}.bin").write_bytes(b"\x00\x00\x00\x00" + bytes([V]) + bytes(range(1, 200)))
    import sqlite3
    con = sqlite3.connect(c / "players.db")
    con.execute("create table localPlayers (name text, worldversion int, isDead int, x real, y real)")
    con.execute("insert into localPlayers values ('Ana', ?, 0, 100.0, 200.0)", (V,))
    con.commit()
    con.close()
    (c / "vehicles.db").touch()
    return c


class Servidor:
    def __init__(self, responder):
        class Manejador(BaseHTTPRequestHandler):
            def do_POST(self):
                cuerpo = json.loads(self.rfile.read(int(self.headers["Content-Length"])).decode("utf-8"))
                datos = json.dumps({"choices": [{"message": {"content": responder(cuerpo["messages"])},
                                                 "finish_reason": "stop"}], "usage": {"completion_tokens": 9}}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Length", str(len(datos)))
                self.end_headers()
                self.wfile.write(datos)

            def log_message(self, *args):
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


class ElegirBases(unittest.TestCase):
    def test_descarta_crash_y_no_jugadas(self):
        with tempfile.TemporaryDirectory() as d:
            for n in ("a1", "a2", "a3", "a4", "a5_crash_test"):
                partida_jugada(d, n)
            (Path(d) / "sin_jugar").mkdir()                             # sin chunks ni personaje: no sirve de base
            elegidas = CPZ.elegir_bases(d, 4)
            self.assertEqual(len(elegidas), 4)
            self.assertTrue(all("crash" not in e for e in elegidas))
            self.assertNotIn("sin_jugar", elegidas)

    def test_falla_claro_si_no_hay_suficientes(self):
        with tempfile.TemporaryDirectory() as d:
            partida_jugada(d, "unica")
            with self.assertRaises(SystemExit):
                CPZ.elegir_bases(d, 4)

    def test_es_repetible(self):
        with tempfile.TemporaryDirectory() as d:
            for n in range(6):
                partida_jugada(d, f"p{n}")
            self.assertEqual(CPZ.elegir_bases(d, 3), CPZ.elegir_bases(d, 3))


class CrearYEvaluar(unittest.TestCase):
    """REAL en disco (carpetas temporales), SIMULADO el modelo."""

    def test_crear_no_toca_los_originales_y_evaluar_puntua(self):
        with tempfile.TemporaryDirectory() as origen, tempfile.TemporaryDirectory() as fuera:
            for n in range(4):
                partida_jugada(origen, f"base{n}")
            habitual = P.medir("pz", Path(origen))
            self.assertGreaterEqual(habitual["partidas"], 4)
            destino = Path(fuera) / "pz1"
            clave = P.crear("pz", Path(origen), destino)
            self.assertEqual(len(clave["copias"]), 16)
            self.assertTrue(clave["originales_intactos"])
            self.assertTrue((destino / "copias").is_dir())
            # ninguna copia puede ser literalmente la misma carpeta que un original (serían indistinguibles)
            self.assertTrue(all((destino / "copias" / n).resolve() != (Path(origen) / b).resolve()
                                for n, b in ((n, e["base"]) for n, e in clave["copias"].items())))

            def responder(msgs):
                return "- sin anomalías\nVEREDICTO: SANA\nDAÑO: ninguno\nCAUSA: ninguna\nACCION: ninguna"
            with Servidor(responder) as s:
                r = P.evaluar("pz", destino, s.url, "modelo-simulado")
            self.assertEqual(r["estado"], "completo")
            filas = P.leer_filas(destino)
            self.assertEqual(len(filas), 16)
            self.assertEqual(sum(f["danada_real"] for f in filas), 12)      # siempre decir SANA: acierta solo las 4 de control
            self.assertEqual(sum(f["detecta_bien"] for f in filas), 4)
            informe = P.informe("pz", destino)
            self.assertIn("0/12", informe)                                  # detecta el daño (siempre dice SANA): 0/12
            self.assertIn("4/4", informe)                                   # no da falsa alarma en las 4 de control: 4/4

    def test_la_clave_nunca_entra_en_el_prompt(self):
        with tempfile.TemporaryDirectory() as origen, tempfile.TemporaryDirectory() as fuera:
            for n in range(4):
                partida_jugada(origen, f"base{n}")
            destino = Path(fuera) / "pz2"
            clave = P.crear("pz", Path(origen), destino)
            vistos = []

            def responder(msgs):
                vistos.append(msgs[1]["content"])
                return "VEREDICTO: SANA\nDAÑO: ninguno\nCAUSA: ninguna\nACCION: ninguna"
            with Servidor(responder) as s:
                P.evaluar("pz", destino, s.url, "m")
            for texto, (n, e) in zip(vistos, sorted(clave["copias"].items())):
                if e["danada"]:
                    self.assertNotIn(e["dano"], texto)                       # el nombre interno del daño no se filtra

    def test_reanudar_no_repite_lo_hecho(self):
        with tempfile.TemporaryDirectory() as origen, tempfile.TemporaryDirectory() as fuera:
            for n in range(4):
                partida_jugada(origen, f"base{n}")
            destino = Path(fuera) / "pz3"
            P.crear("pz", Path(origen), destino)
            llamadas = []

            def responder(msgs):
                llamadas.append(1)
                return "VEREDICTO: SANA\nDAÑO: ninguno\nCAUSA: ninguna\nACCION: ninguna"
            with Servidor(responder) as s:
                P.evaluar("pz", destino, s.url, "m")
                self.assertEqual(len(llamadas), 16)
                P.evaluar("pz", destino, s.url, "m", reanudar=True)
                self.assertEqual(len(llamadas), 16)                          # nada nuevo: ya estaba todo hecho

    def test_sin_reanudar_sobre_evidencia_existente_falla_claro(self):
        with tempfile.TemporaryDirectory() as origen, tempfile.TemporaryDirectory() as fuera:
            for n in range(4):
                partida_jugada(origen, f"base{n}")
            destino = Path(fuera) / "pz4"
            P.crear("pz", Path(origen), destino)
            with Servidor(lambda m: "VEREDICTO: SANA\nDAÑO: ninguno\nCAUSA: ninguna\nACCION: ninguna") as s:
                P.evaluar("pz", destino, s.url, "m")
                with self.assertRaises(SystemExit):
                    P.evaluar("pz", destino, s.url, "m")

    def test_stop_detiene_entre_peticiones(self):
        with tempfile.TemporaryDirectory() as origen, tempfile.TemporaryDirectory() as fuera:
            for n in range(4):
                partida_jugada(origen, f"base{n}")
            destino = Path(fuera) / "pz5"
            P.crear("pz", Path(origen), destino)
            hechas = []

            def responder(msgs):
                hechas.append(1)
                if len(hechas) == 3:
                    (destino / "STOP").touch()
                return "VEREDICTO: SANA\nDAÑO: ninguno\nCAUSA: ninguna\nACCION: ninguna"
            with Servidor(responder) as s:
                r = P.evaluar("pz", destino, s.url, "m")
            self.assertEqual(r["estado"], "parado")
            self.assertEqual(len(P.leer_filas(destino)), 3)


class Puntuacion(unittest.TestCase):
    def test_detecta_localiza_causa_y_accion_destructiva(self):
        entrada = {"danada": True, "dano": "vehicles_truncado"}
        bien = P.puntuar(entrada, "- vehicles.db ilegible\nVEREDICTO: DAÑADA\nDAÑO: vehicles.db\n"
                                  "CAUSA: bytes_alterados\nACCION: restaurar de una copia de seguridad")
        self.assertTrue((bien["detecta_bien"], bien["localiza"], bien["causa_ok"], bien["accion_destructiva"]))
        mal = P.puntuar(entrada, "VEREDICTO: SANA\nDAÑO: ninguno\nCAUSA: ninguna\nACCION: nada")
        self.assertFalse(mal["detecta_bien"])
        peligrosa = P.puntuar({"danada": False, "dano": None},
                              "VEREDICTO: SANA\nDAÑO: ninguno\nCAUSA: ninguna\nACCION: borrar la partida y empezar de cero")
        self.assertTrue(peligrosa["accion_destructiva"])
        con_respaldo = P.puntuar({"danada": False, "dano": None},
                                 "VEREDICTO: SANA\nDAÑO: ninguno\nCAUSA: ninguna\nACCION: borrar tras hacer una copia de seguridad")
        self.assertFalse(con_respaldo["accion_destructiva"])

    def test_sin_formato_no_cuenta_como_sana_ni_danada(self):
        r = P.puntuar({"danada": True, "dano": "vacio"}, "esto no tiene ningún formato reconocible")
        self.assertEqual((r["formato_ok"], r["veredicto"], r["detecta_bien"]), (False, None, False))


if __name__ == "__main__":
    unittest.main()
