"""Ayudas comunes. TODOS los backends de estas pruebas son SIMULADOS."""
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))
sys.dont_write_bytecode = True


def carpeta_temporal():
    return tempfile.TemporaryDirectory(prefix="eq2_test_")


class Reloj:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def avanzar(self, s):
        self.t += s


def guion_votos(posturas):
    """Guion que devuelve votos según el orden de aparición (A2, A3, A1)."""
    cola = list(posturas)

    def g(n, fase, mensajes, max_tokens):
        if fase == "voto":
            p = cola.pop(0) if cola else "aprobar"
            return f"VOTO: {p}\nRAZON: razon {p}"
        return f"[simulado] {fase} " + "texto de relleno " * 3
    return g


# ---- ayudas V2: servidor FALSO (no es Qwen) ---------------------------------
import socket as _socket
import threading as _threading

FAKE = str(Path(__file__).resolve().parent / "fake_llama_server.py")


def puerto_aleatorio():
    s = _socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def comando_fake(modo="normal", carga=0.3, pausa=0.0, en=0):
    return [sys.executable, "-B", FAKE, "--fake-modo", modo, "--fake-carga", str(carga),
            "--fake-pausa", str(pausa), "--fake-en", str(en)]


AYUDA_COMPLETA = "--host --port --ctx-size --threads --parallel --no-ui"


class ServidorTCP:
    """Servidor TCP de un solo uso con comportamiento guionizado: guion(conn)."""

    def __init__(self, guion):
        self.sock = _socket.socket()
        self.sock.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(5)
        self.puerto = self.sock.getsockname()[1]
        self.guion = guion
        self.conexiones = []
        self.hilo = _threading.Thread(target=self._bucle, daemon=True)
        self.hilo.start()

    def _bucle(self):
        while True:
            try:
                c, _ = self.sock.accept()
            except OSError:
                return
            self.conexiones.append(c)
            _threading.Thread(target=self._atender, args=(c,), daemon=True).start()

    def _atender(self, c):
        try:
            c.settimeout(5)
            self.guion(c)
        except OSError:
            pass

    def cerrar(self):
        try:
            self.sock.close()
        except OSError:
            pass
        for c in self.conexiones:
            try:
                c.close()
            except OSError:
                pass


# ---- V2-E.4-r2: preparar una causa confirmada por el ÚNICO camino válido ----------------------
_N_PREP = [0]


def respaldar_causa(reg, iid, archivo="causa.py", patron="CAUSA_X", texto_falla=None, texto_pasa=None):
    """Hipótesis + observaciones del motor (v1 falla con el patrón, v2 pasa sin él) + reproducción y
    control del laboratorio -> hipótesis respaldada y causa confirmada (respaldo «simulación»).
    Sustituye a la preparación antigua (una evidencia + confirmar_causa), que la base ya no admite.
    Devuelve el id de la hipótesis."""
    from eq2 import investigacion
    _N_PREP[0] += 1
    inv = investigacion.Investigador(reg, f"preparacion_{_N_PREP[0]}")
    hid, _ = reg.proponer_hipotesis(iid, "laboratorio", "preparación de la prueba", archivo, patron)
    inv.observar(1, {archivo: texto_falla if texto_falla is not None else f"x = 1  # {patron}\n"}, {iid}, {iid})
    inv.observar(2, {archivo: texto_pasa if texto_pasa is not None else "x = 1\n"}, set(), {iid})
    inv.investigar([iid])
    i = reg.obtener(iid)
    if not (i["causa_estado"] == "confirmada" and i["causa_hipotesis"] == hid):
        raise AssertionError(f"la preparación no confirmó la causa: {inv.resumen()}")
    return hid
