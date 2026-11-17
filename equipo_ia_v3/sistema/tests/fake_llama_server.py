#!/usr/bin/env python3
"""FALSO llama-server para pruebas. NO es Qwen ni llama.cpp: solo imita /health y
/v1/chat/completions con distintos comportamientos (modos) para probar el código
de cierre, errores HTTP, timeouts y procesos bloqueados. Solo escucha en 127.0.0.1."""
import argparse
import json
import os
import signal
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ap = argparse.ArgumentParser()
ap.add_argument("--fake-modo", default="normal")
ap.add_argument("--fake-carga", type=float, default=0.3)
ap.add_argument("--fake-pausa", type=float, default=0.0, help="segundos antes de responder")
ap.add_argument("--fake-en", type=int, default=0,
                help="si >0, el modo (salvo contexto/votos) solo se aplica a la petición número N")
ap.add_argument("-m")
ap.add_argument("--host")
ap.add_argument("--port", type=int)
ap.add_argument("-c")
ap.add_argument("-t")
ap.add_argument("-np")
ap.add_argument("--no-ui", action="store_true")
a = ap.parse_args()
T0 = time.time()
print("ARGV " + json.dumps(sys.argv[1:]), flush=True)
print("CWD " + os.getcwd(), flush=True)
print("ENV_SENSIBLES " + json.dumps(sorted(k for k in os.environ if any(
    w in k.upper() for w in ("KEY", "TOKEN", "SECRET", "PASSWORD", "ANTHROPIC", "OPENAI")))), flush=True)
if a.fake_modo == "muere_al_arrancar":
    print("error: simulated crash at startup", flush=True)
    sys.exit(3)
if a.fake_modo == "ignora_sigterm":
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
if a.fake_modo == "tarda_en_cerrar":
    def _lento(*_):
        time.sleep(1.5)
        os._exit(0)
    signal.signal(signal.SIGTERM, _lento)

NORMAL = {"choices": [{"finish_reason": "stop", "index": 0,
                       "message": {"role": "assistant", "content": "Respuesta simulada del falso servidor."}}],
          "usage": {"completion_tokens": 12, "prompt_tokens": 88, "total_tokens": 100},
          "timings": {"cache_n": 0, "prompt_n": 88, "prompt_ms": 1000.0, "prompt_per_second": 88.0,
                      "predicted_n": 12, "predicted_ms": 1200.0, "predicted_per_second": 10.0}}


NREQ = 0
ACTIVAS = 0
VOTOS = 0
_LOCK = __import__("threading").Lock()


MODOS_SIEMPRE = ("votos_mal", "voto_invalido_1", "contexto", "voto_truncado", "voto_truncado_1",
                 "voto_truncado_A1", "voto_sin_fin", "voto_sin_fin_1", "votos_contradictorios",
                 "rechazar_sin_razon_1", "abstencion_info", "voto_cambios", "voto_cambios_truncado",
                 "replica_length", "replica_sin_fin", "replica_larga", "revision_length", "debate",
                 "debate_completo", "analisis_falta", "razon_larga",
                 # V2-D: continuación (prefill del último mensaje 'assistant')
                 "propuesta_cortada", "replica_cortada", "continuacion_eco", "continuacion_reinicio",
                 "continuacion_cortada", "sin_fin", "codigo_abierto", "propuesta_y_replica_cortadas",
                 "continuacion_http500",
                 # V2-E: motor autónomo
                 "motor_ok", "motor_sintaxis", "motor_bloqueo", "motor_cortado")
_CLAVES = (("Vota sobre", "voto"), ("Analiza la tarea", "analisis"), ("Propón una solución", "propuesta"),
           ("Revisa la propuesta", "revision"), ("Responde a la revisión", "replica"))


_CLAVES_MOTOR = (("Descompón la tarea", "m_planificar"), ("Escribe los archivos del plan", "m_generar"),
                 ("Corrige los archivos", "m_corregir"), ("Analiza los resultados", "m_evaluar"),
                 ("FUERA_DE_ALCANCE", "m_revisar"))
ARCH_OK = ("ARCHIVO: ordenar.py\n```python\ndef ordenar(xs):\n    return sorted(xs)\n```\n"
           "ARCHIVO: test_ordenar.py\n```python\nfrom ordenar import ordenar\n\n"
           "def test_no_muta():\n    a = [2, 1]\n    ordenar(a)\n    assert a == [2, 1]\n```\nFIN")


def _respuesta_normal(cuerpo, modo):
    """Respuesta que depende de la fase y del agente (detectados como en BackendSimulado)."""
    global VOTOS
    d = json.loads(json.dumps(NORMAL))
    ch = d["choices"][0]
    try:
        msgs = json.loads(cuerpo)["messages"]
        es_cont = msgs[-1].get("role") == "assistant"          # prefill = continuación
        u = msgs[-2]["content"] if es_cont else msgs[-1]["content"]
        sis = msgs[0]["content"]
        previo = msgs[-1]["content"] if es_cont else ""
    except Exception:
        u, sis, es_cont, previo = "", "", False, ""
    fase = next((f for c, f in _CLAVES_MOTOR if c in u), None) or next((f for c, f in _CLAVES if c in u), "?")
    # V2-E: en los votos la identidad del votante va al final del mensaje de usuario
    agente = next((a for a in ("A1", "A2", "A3") if f"Eres {a}" in sis),
                  next((a for a in ("A1", "A2", "A3") if f"Eres {a}," in u), "?"))

    def poner(texto, fin="stop", gen=12):
        ch["message"]["content"] = texto
        if fin is None:
            ch.pop("finish_reason", None)
        else:
            ch["finish_reason"] = fin
        d["timings"]["predicted_n"] = gen
        d["usage"]["completion_tokens"] = gen

    if fase.startswith("m_") and modo.startswith("motor"):
        if fase == "m_planificar":
            poner("ARCHIVOS: ordenar.py, test_ordenar.py\nCRITERIO: C1 | no muta | PRUEBA: test_no_muta")
        elif fase == "m_generar":
            if modo == "motor_sintaxis":
                poner(ARCH_OK.replace("def ordenar(xs):", "def ordenar(xs)"))
            elif modo == "motor_cortado" and not es_cont:
                poner(ARCH_OK[:60], "length", 640)
            elif modo == "motor_cortado":
                poner(ARCH_OK[60:], "stop", 60)
            else:
                poner(ARCH_OK)
        elif fase == "m_corregir":
            poner(ARCH_OK.replace("FIN", "CAMBIOS: añado los dos puntos\nFIN"))
        elif fase == "m_revisar":
            poner("BLOQUEO: falta validar la entrada" if modo == "motor_bloqueo" else "SIN OBJECIONES: correcto")
        elif fase == "m_evaluar":
            poner("DIAGNOSTICO: corregir el error de sintaxis de ordenar.py")
        return d
    CORTE = "```python\ndef ordenar(xs):\n    return sor"
    if fase in ("propuesta", "replica") and modo in (
            "propuesta_cortada", "replica_cortada", "continuacion_eco", "continuacion_reinicio",
            "continuacion_cortada", "sin_fin", "codigo_abierto", "propuesta_y_replica_cortadas",
            "continuacion_http500"):
        objetivo = {"propuesta_cortada": ("propuesta",), "replica_cortada": ("replica",),
                    "propuesta_y_replica_cortadas": ("propuesta", "replica")}.get(modo, ("replica",))
        if fase in objetivo:
            if not es_cont:
                if modo == "sin_fin":
                    poner("```python\ndef ordenar(xs):\n    return sorted(xs)\n```", "stop", 40)
                elif modo == "codigo_abierto":
                    poner(CORTE + "ted(xs)", "stop", 40)
                else:
                    poner(CORTE, "length", 320 if fase == "propuesta" else 240)   # = max_tokens
            elif modo == "continuacion_http500":
                d["__http500__"] = True
            elif modo == "continuacion_eco":
                poner(previo + "ted(xs)\n```\nFIN", "stop", 20)
            elif modo == "continuacion_reinicio":
                poner(CORTE[:30] + " -- otra versión distinta\n```\nFIN", "stop", 30)
            elif modo == "continuacion_cortada":
                poner("ted(xs) + [", "length", 200)
            elif modo == "sin_fin":
                poner("\nFIN", "stop", 2)
            elif modo == "codigo_abierto":
                poner("\n```\nFIN", "stop", 4)
            else:
                poner("ted(xs)\n```\nCaso: ordenar([3,1]) -> [1, 3]\nFIN", "stop", 20)
            return d
    if fase == "voto":
        with _LOCK:
            VOTOS += 1
            v = VOTOS
        bien = "VOTO: aprobar\nRAZON: simulado"
        corte = "VOTO: aprobar\nRAZON: cumple la tarea porque usa sorted y devuelve una lista"
        if modo == "votos_mal" or (modo == "voto_invalido_1" and v == 1):
            poner("no tengo claro qué votar")
        elif modo == "voto_truncado" or (modo == "voto_truncado_1" and v == 1) \
                or (modo == "voto_truncado_A1" and agente == "A1"):
            poner(corte, "length", 120)
        elif modo == "voto_sin_fin" or (modo == "voto_sin_fin_1" and v == 1):
            poner(bien, None)
        elif modo == "votos_contradictorios" and agente == "A2":
            poner("VOTO: aprobar\nRAZON: tiene un error con listas vacías")
        elif modo == "rechazar_sin_razon_1" and v == 1:
            poner("VOTO: rechazar")
        elif modo == "abstencion_info":
            poner("VOTO: abstencion\nRAZON: falta saber si debe aceptar valores None")
        elif modo == "voto_cambios" and agente == "A3":
            poner("VOTO: aprobar_con_cambios\nRAZON: añadir un caso de prueba con lista vacía")
        elif modo == "voto_cambios_truncado" and agente == "A3":
            poner("VOTO: aprobar_con_cambios\nRAZON: añadir el caso de", "length", 120)
        elif modo == "razon_larga":
            poner("VOTO: aprobar\nRAZON: " + "bien " * 50)
        else:
            poner(bien)
    elif fase == "replica":
        if modo == "replica_length":
            poner("Propuesta final: def ordenar(xs): return sor", "length", 160)
        elif modo == "replica_sin_fin":
            poner("Propuesta final: def ordenar(xs): return sorted(xs)", None)
        elif modo == "replica_larga":
            poner("Propuesta final: " + "def ordenar(xs): return sorted(xs). " * 20)
        elif modo == "debate":
            poner("ACEPTADA: añado el caso de lista vacía\nPropuesta final: def ordenar(xs): return sorted(xs)")
        elif modo == "debate_completo":
            poner("ACEPTADA: añado el caso de lista vacía\nREBATIDA: sorted ya es O(n log n)\n"
                  "Propuesta final: def ordenar(xs): return sorted(xs)")
    elif fase == "revision":
        if modo == "revision_length":
            poner("OBJECION: no trata la lista", "length", 160)
        elif modo in ("debate", "debate_completo"):
            poner("OBJECION: no prueba la lista vacía | EVIDENCIA: ordenar([]) debe devolver []\n"
                  "OBJECION: no indica la complejidad")
    elif fase == "analisis" and modo == "analisis_falta":
        poner("Objetivo: ordenar sin mutar.\nFALTA: si se admiten valores None")
    if modo == "contexto":
        d["usage"]["prompt_tokens"] = 1000
        d["timings"]["prompt_n"] = 1000
        d["timings"]["predicted_n"] = 80
    return d


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_):
        pass

    def _enviar(self, codigo, cuerpo: bytes, extra=()):
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(cuerpo)))
        for k, v in extra:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(cuerpo)
        self.wfile.flush()

    def do_GET(self):
        if self.path != "/health":
            return self._enviar(404, b"{}")
        if a.fake_modo == "nunca_listo" or time.time() - T0 < a.fake_carga:
            return self._enviar(503, b'{"error":{"message":"Loading model","code":503}}')
        self._enviar(200, b'{"status":"ok"}')

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        cuerpo = self.rfile.read(n)
        global NREQ, ACTIVAS
        with _LOCK:
            NREQ += 1
            ACTIVAS += 1
            nreq, activas = NREQ, ACTIVAS
        print(f"ACTIVAS {activas}", flush=True)
        print("REQ " + cuerpo.decode("utf-8", "replace")[:3000], flush=True)
        m = a.fake_modo
        if a.fake_en and nreq != a.fake_en and m not in MODOS_SIEMPRE:
            m = "normal"
        try:
            self._atender(cuerpo, m)
        finally:
            with _LOCK:
                ACTIVAS -= 1

    def _atender(self, cuerpo, m):
        if a.fake_pausa:
            time.sleep(a.fake_pausa)
        if m == "cuelga":
            time.sleep(3600)
        elif m == "gotea":
            self.wfile.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 100000\r\n\r\n")
            self.wfile.flush()
            while True:
                self.wfile.write(b" ")
                self.wfile.flush()
                time.sleep(0.2)
        elif m == "muere_en_peticion":
            os._exit(9)
        elif m == "http500":
            self._enviar(500, b'{"error":"boom"}')
        elif m == "json_invalido":
            self._enviar(200, b"esto no es json")
        elif m == "sin_choices":
            self._enviar(200, b'{"x":1}')
        elif m == "content_no_texto":
            d = json.loads(json.dumps(NORMAL))
            d["choices"][0]["message"]["content"] = 42
            self._enviar(200, json.dumps(d).encode())
        elif m == "cierra_sin_responder":
            self.connection.close()
        elif m == "especiales":
            d = json.loads(json.dumps(NORMAL))
            d["choices"][0]["message"]["content"] = "hola <|im_end|>"
            self._enviar(200, json.dumps(d).encode())
        elif m == "peligro":
            marca = os.environ.get("FAKE_MARCA", "/nonexistent/marca")
            d = json.loads(json.dumps(NORMAL))
            d["choices"][0]["message"]["content"] = f"$(touch {marca}); `touch {marca}`; rm -rf ~; ../../x"
            self._enviar(200, json.dumps(d).encode())
        elif m == "length":
            d = json.loads(json.dumps(NORMAL))
            d["choices"][0]["finish_reason"] = "length"
            d["timings"]["predicted_n"] = 160
            self._enviar(200, json.dumps(d).encode())
        elif m == "sin_metricas":
            d = json.loads(json.dumps(NORMAL))
            del d["timings"]
            del d["usage"]
            self._enviar(200, json.dumps(d).encode())
        elif m == "chunked":
            c = json.dumps(NORMAL).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            for i in range(0, len(c), 50):
                t = c[i:i + 50]
                self.wfile.write(f"{len(t):x}\r\n".encode() + t + b"\r\n")
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
        elif m == "enorme":
            self.send_response(200)
            self.send_header("Content-Length", str(50_000_000))
            self.end_headers()
            try:
                for _ in range(500):
                    self.wfile.write(b"x" * 100_000)
            except OSError:
                pass
        else:
            d = _respuesta_normal(cuerpo, m)
            if d.pop("__http500__", False):
                self._enviar(500, b'{"error":"boom en continuacion"}')
            else:
                self._enviar(200, json.dumps(d).encode())


class S(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


try:
    srv = S(("127.0.0.1", a.port), H)
except OSError as e:
    print("error: no se pudo enlazar", e, flush=True)
    sys.exit(1)
print("fake llama server listening", flush=True)
srv.serve_forever()
