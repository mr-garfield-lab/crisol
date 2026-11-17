"""Cliente HTTP mínimo hacia 127.0.0.1 con PLAZO TOTAL EFECTIVO.

No usa http.client: cada recv() tiene un timeout corto (0,5 s) y entre recv se
comprueba el plazo total y la función `deberia_parar` (parada del usuario, monitor
de memoria, muerte del servidor...). Así una operación bloqueada se detiene aunque
el servidor no conteste ni gotee bytes. El destino es SIEMPRE config.HOST.
"""
from __future__ import annotations

import socket
import time
from dataclasses import dataclass

from . import config


class ErrorHTTP(Exception):
    """`fatal=True`: el servidor puede quedar ocupado/inconsistente; no seguir usándolo."""

    def __init__(self, motivo, fatal=True):
        super().__init__(motivo)
        self.motivo, self.fatal = str(motivo), bool(fatal)


@dataclass
class RespuestaHTTP:
    status: int
    headers: dict
    cuerpo: bytes
    duracion_s: float


def _dechunk(datos: bytes):
    """Devuelve el cuerpo reensamblado, o None si aún está incompleto."""
    i, out = 0, bytearray()
    while True:
        j = datos.find(b"\r\n", i)
        if j < 0:
            return None
        try:
            n = int(datos[i:j].split(b";")[0].strip() or b"x", 16)
        except ValueError:
            raise ErrorHTTP("chunk_malformado", fatal=False)
        i = j + 2
        if n == 0:
            # tras el trozo final puede haber trailers; basta ver el CRLF que cierra el bloque
            return bytes(out) if datos.find(b"\r\n", i) >= 0 else None
        if len(datos) < i + n + 2:
            return None
        out += datos[i:i + n]
        i += n + 2
        if len(out) > config.MAX_RESP_BYTES:
            raise ErrorHTTP("respuesta_demasiado_grande", fatal=False)


def _parsear(buf: bytes, eof: bool):
    """(status, headers, cuerpo) si la respuesta está completa; None si falta; ErrorHTTP si es inválida."""
    fin = buf.find(b"\r\n\r\n")
    if fin < 0:
        if len(buf) > config.MAX_CABECERAS_BYTES:
            raise ErrorHTTP("cabeceras_demasiado_grandes", fatal=False)
        if eof:
            raise ErrorHTTP("respuesta_truncada", fatal=False)
        return None
    lineas = buf[:fin].decode("latin-1").split("\r\n")
    partes = lineas[0].split(" ", 2)
    if len(partes) < 2 or not partes[0].startswith("HTTP/") or not partes[1].isdigit():
        raise ErrorHTTP("estado_malformado", fatal=False)
    status = int(partes[1])
    headers = {}
    for l in lineas[1:]:
        k, sep, v = l.partition(":")
        if sep:
            headers[k.strip().lower()] = v.strip()
    cuerpo = bytes(buf[fin + 4:])
    if "chunked" in headers.get("transfer-encoding", "").lower():
        r = _dechunk(cuerpo)
        if r is None:
            if eof:
                raise ErrorHTTP("respuesta_truncada", fatal=False)
            return None
        return status, headers, r
    if "content-length" in headers:
        n = headers["content-length"]
        if not n.isdigit():
            raise ErrorHTTP("content_length_invalido", fatal=False)
        n = int(n)
        if n > config.MAX_RESP_BYTES:
            raise ErrorHTTP("respuesta_demasiado_grande", fatal=False)
        if len(cuerpo) < n:
            if eof:
                raise ErrorHTTP("respuesta_truncada", fatal=False)
            return None
        return status, headers, cuerpo[:n]
    if eof:
        return status, headers, cuerpo
    return None


def peticion(puerto: int, metodo: str, ruta: str, cuerpo: bytes | None, plazo_s: float,
             deberia_parar=lambda: None, intervalo: float = 0.5) -> RespuestaHTTP:
    """Una petición con plazo TOTAL `plazo_s` (conexión + envío + respuesta)."""
    if not (isinstance(puerto, int) and 1024 <= puerto <= 65535):
        raise ValueError("puerto fuera de rango")
    if metodo not in ("GET", "POST") or not ruta.startswith("/"):
        raise ValueError("método o ruta inválidos")
    t0 = time.monotonic()

    def comprobar():
        try:
            m = deberia_parar()
        except Exception:
            raise ErrorHTTP("supervision_fallo")
        if m:
            raise ErrorHTTP(str(m))
        if time.monotonic() - t0 > plazo_s:
            raise ErrorHTTP("plazo_agotado")

    comprobar()
    try:
        s = socket.create_connection((config.HOST, puerto),
                                     timeout=max(0.1, min(3.0, plazo_s)))
    except OSError as e:
        raise ErrorHTTP("conexion_fallida:" + type(e).__name__, fatal=False)
    try:
        s.settimeout(intervalo)
        cab = [f"{metodo} {ruta} HTTP/1.1", f"Host: {config.HOST}:{puerto}",
               "Accept: application/json", "Connection: close", "User-Agent: eq2"]
        if cuerpo is not None:
            cab += ["Content-Type: application/json", f"Content-Length: {len(cuerpo)}"]
        datos = memoryview(("\r\n".join(cab) + "\r\n\r\n").encode("ascii") + (cuerpo or b""))
        while len(datos):
            comprobar()
            try:
                n = s.send(datos)
            except TimeoutError:
                continue
            except OSError as e:
                raise ErrorHTTP("envio_fallido:" + type(e).__name__)
            datos = datos[n:]
        buf = bytearray()
        while True:
            comprobar()
            eof = False
            try:
                trozo = s.recv(65536)
                if not trozo:
                    eof = True
                else:
                    buf += trozo
                    if len(buf) > config.MAX_RESP_BYTES + config.MAX_CABECERAS_BYTES:
                        raise ErrorHTTP("respuesta_demasiado_grande", fatal=True)
            except TimeoutError:
                continue
            except ConnectionError as e:
                raise ErrorHTTP("conexion_perdida:" + type(e).__name__)
            except OSError as e:
                raise ErrorHTTP("lectura_fallida:" + type(e).__name__)
            r = _parsear(bytes(buf), eof)
            if r is not None:
                return RespuestaHTTP(r[0], r[1], r[2], round(time.monotonic() - t0, 3))
            if eof:
                raise ErrorHTTP("respuesta_truncada", fatal=False)
    finally:
        try:
            s.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            s.close()
        except OSError:
            pass
