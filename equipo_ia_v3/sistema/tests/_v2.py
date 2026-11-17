"""Fixture común de las pruebas V2: HOME falso con modelo falso, laboratorio y servidor FALSO."""
import os
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import _comun
from eq2 import backend_llama, config, orquestador, rutas, servidor, vigilancia


MARCA_PETICION = "REQ "                              # el servidor FALSO ha recibido la petición (y espera su pausa)
MARCA_CARGA = "fake llama server listening"          # el proceso del servidor FALSO existe y escucha, aún sin estar listo


def al_ver_en_log(carpeta_datos, marca, accion, limite_s=60.0):
    """V2-F.1 (portado de V2-E.9-r2): sincronización por ESTADO VERIFICABLE, no por un tiempo fijo. Ejecuta `accion` en cuanto alguna
    línea de runs/*/server.log (la salida real del servidor falso) empieza por `marca`. Devuelve un Event que queda
    puesto SOLO si la acción llegó a ejecutarse; las pruebas lo comprueban (si no, la prueba no prueba lo que dice).
    El límite solo evita una espera infinita si el servidor nunca llega a ese estado."""
    hecho = threading.Event()

    def vigilar():
        fin = time.monotonic() + limite_s
        while time.monotonic() < fin and not hecho.is_set():
            for p in Path(carpeta_datos).glob("runs/*/server.log"):
                try:
                    lineas = p.read_text(encoding="utf-8", errors="replace").splitlines()
                except OSError:
                    continue
                if any(linea.startswith(marca) for linea in lineas):
                    accion()
                    hecho.set()
                    return
            time.sleep(0.01)                          # sondeo del estado, no una espera arbitraria
    threading.Thread(target=vigilar, daemon=True, name="eq2-prueba-disparador").start()
    return hecho


class EntornoV2(unittest.TestCase):
    def setUp(self):
        self.tmp = _comun.carpeta_temporal()
        self.t = Path(self.tmp.name)
        self.home = self.t / "home"
        self.proyecto = self.home / "equipo-ia"
        (self.proyecto / "modelos").mkdir(parents=True)
        self.modelo = self.proyecto / "modelos" / "qwen-coder-3b.gguf"
        self.modelo.write_bytes(b"GGUF" + b"\x00" * 4096)
        (self.proyecto / ".env").write_text("SECRETO=1")              # centinelas: NO deben leerse
        (self.proyecto / "coordinador.py").write_text("# prototipo")
        self.raiz = self.t / "tmpdir" / "equipo_f2"
        (self.t / "tmpdir").mkdir()
        parches = [mock.patch.dict(os.environ, {"HOME": str(self.home)}),
                   mock.patch.object(config, "MIN_MODELO_BYTES", 1)]
        for p in parches:
            p.start()
            self.addCleanup(p.stop)
        self.reloj_real = __import__("time").monotonic
        self.servidores = []

    def tearDown(self):
        for s in self.servidores:                 # red de seguridad: nada queda vivo
            try:
                if s.proc is not None and s.proc.poll() is None:
                    s.proc.kill()
                    s.proc.wait(5)
            except Exception:
                pass
        self.tmp.cleanup()

    def servidor(self, modo="normal", carga=0.3, pausa=0.0, puerto=None, en=0, **kw):
        kw.setdefault("detector_llama", lambda: None)
        kw.setdefault("ayuda_fn", lambda: _comun.AYUDA_COMPLETA)
        kw.setdefault("lector_mem", lambda: 2_000_000)
        kw.setdefault("gracia_term", 3)
        kw.setdefault("gracia_kill", 3)
        kw.setdefault("max_carga_s", 15)
        kw.setdefault("sondeo_s", 0.05)
        s = servidor.ServidorLlama(puerto or _comun.puerto_aleatorio(),
                                   comando=_comun.comando_fake(modo, carga, pausa, en), **kw)
        self.servidores.append(s)
        self.addCleanup(s.cerrar_log)
        return s

    def vigilante(self):
        return vigilancia.Vigilante(lector_mem=lambda: 1_500_000, lector_bat=lambda: (80, False))

    def backend(self, modo="normal", carga=0.3, pausa=0.0, srv_kw=None, en=0, **kw):
        srv = self.servidor(modo, carga, pausa, en=en, **(srv_kw or {}))
        kw.setdefault("intervalo_monitor", 0.05)
        kw.setdefault("espera_monitor", 1)
        return backend_llama.BackendLlama(srv, **kw)

    def orq(self, be, **kw):
        return orquestador.Orquestador(self.raiz / "datos_v2", be, self.vigilante(),
                                       raiz_laboratorio=self.raiz, **kw)

    def orq_b(self, be, carpeta=None, **kw):
        """Orquestador para deliberación (V2-C: ya sin subclase)."""
        return orquestador.Orquestador(self.raiz / (carpeta or self.carpeta_datos), be,
                                       self.vigilante(), raiz_laboratorio=self.raiz, **kw)

    def log(self, res, nombre="server.log"):
        p = self.raiz / self.carpeta_datos / "runs" / res["run_id"] / nombre
        return p.read_text(encoding="utf-8", errors="replace")

    carpeta_datos = "datos_v2"

    def sql(self, consulta, params=(), db="sesion"):
        import sqlite3
        con = sqlite3.connect(str(self.raiz / self.carpeta_datos / "datos" / f"{db}.db"))
        try:
            return con.execute(consulta, params).fetchall()
        finally:
            con.close()
