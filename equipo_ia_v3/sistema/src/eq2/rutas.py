"""Confinamiento de rutas al laboratorio autorizado ($TMPDIR/equipo_f2).

Único módulo con permiso para crear/escribir/borrar archivos y carpetas
(lo comprueba validar_estatico.py). Reglas:
  * toda ruta se construye con nombres simples (sin '/', '..', vacíos ni NUL);
  * ningún componente existente entre la raíz del laboratorio y el destino puede
    ser un enlace simbólico;
  * la ruta real resuelta debe quedar dentro de la raíz real del laboratorio;
  * archivos nuevos con O_CREAT|O_EXCL|O_NOFOLLOW (nunca se sobrescribe).
Límite conocido: entre la comprobación y el uso existe una ventana (TOCTOU) que
solo podría aprovechar otro proceso con permisos sobre el mismo laboratorio.
"""
from __future__ import annotations

import errno
import os
from pathlib import Path

from . import config


class RutaInsegura(ValueError):
    pass


_NO_SEGUIR = getattr(os, "O_NOFOLLOW", 0)

# V2-E.1: errores de os.link que significan «este sistema de archivos no admite enlaces duros».
# Cualquier OTRO error (p. ej. EIO, ENOSPC) se propaga: no se oculta.
_ERRNO_SIN_ENLACE = frozenset(e for e in (
    errno.EPERM, errno.EACCES, errno.EXDEV, errno.EMLINK, errno.ENOSYS,
    getattr(errno, "ENOTSUP", None), getattr(errno, "EOPNOTSUPP", None)) if e is not None)


def hay_enlaces_duros() -> bool:
    """True si esta plataforma ofrece os.link. En Android/Termux (Python de Termux) NO existe.
    Se consulta en cada llamada (no al importar)."""
    return callable(getattr(os, "link", None))


def raiz_laboratorio(env=None) -> Path:
    env = os.environ if env is None else env
    tmp = env.get("TMPDIR")
    if not tmp or not os.path.isabs(tmp):
        raise RutaInsegura("TMPDIR no está definido como ruta absoluta")
    return Path(tmp) / "equipo_f2"


def _nombre_valido(n) -> bool:
    return (isinstance(n, str) and n not in ("", ".", "..")
            and "/" not in n and "\\" not in n and "\x00" not in n)


class Laboratorio:
    def __init__(self, raiz, base=None):
        raiz_abs = Path(os.path.abspath(str(raiz)))
        base_abs = Path(os.path.abspath(str(base if base is not None else raiz)))
        try:
            rel = base_abs.relative_to(raiz_abs)
        except ValueError:
            raise RutaInsegura("la carpeta de trabajo está fuera del laboratorio autorizado")
        # TMPDIR puede ser un enlace; el laboratorio y lo de debajo, no.
        self.raiz = Path(os.path.realpath(str(raiz_abs.parent))) / raiz_abs.name
        self.base = self.raiz.joinpath(*rel.parts)
        if not config.fuera_de_proyecto(self.base):
            raise RutaInsegura("la carpeta de trabajo está dentro del proyecto existente")
        self._comprobar(self.base)

    # --- comprobaciones ----------------------------------------------------
    def _comprobar(self, destino: Path):
        try:
            rel = destino.relative_to(self.raiz)
        except ValueError:
            raise RutaInsegura("ruta fuera del laboratorio")
        actual = self.raiz
        for parte in ("",) + rel.parts:
            if parte:
                actual = actual / parte
            if os.path.lexists(str(actual)) and os.path.islink(str(actual)):
                raise RutaInsegura(f"enlace simbólico no permitido: {actual.name}")
        if os.path.lexists(str(destino)):
            real = Path(os.path.realpath(str(destino)))
            if real != self.raiz and self.raiz not in real.parents:
                raise RutaInsegura("la ruta real queda fuera del laboratorio")

    def ruta(self, *partes) -> Path:
        for p in partes:
            if not _nombre_valido(p):
                raise RutaInsegura(f"nombre de ruta no válido: {p!r}")
        destino = self.base.joinpath(*partes)
        self._comprobar(destino)
        return destino

    def existe(self, *partes) -> bool:
        return os.path.lexists(str(self.ruta(*partes)))

    # --- creación / escritura ---------------------------------------------
    def crear_base(self):
        """Crea laboratorio y carpeta de trabajo nivel a nivel, sin seguir enlaces."""
        niveles = [self.raiz] + [self.raiz.joinpath(*self.base.relative_to(self.raiz).parts[:i])
                                 for i in range(1, len(self.base.relative_to(self.raiz).parts) + 1)]
        for n in niveles:
            if os.path.lexists(str(n)):
                if os.path.islink(str(n)) or not os.path.isdir(str(n)):
                    raise RutaInsegura(f"no es una carpeta real: {n.name}")
            else:
                os.mkdir(str(n), 0o700)

    def crear_dir(self, *partes) -> Path:
        for i in range(1, len(partes) + 1):
            p = self.ruta(*partes[:i])
            if os.path.lexists(str(p)):
                if os.path.islink(str(p)) or not os.path.isdir(str(p)):
                    raise RutaInsegura(f"no es una carpeta real: {p.name}")
            else:
                os.mkdir(str(p), 0o700)
        return self.ruta(*partes)

    def crear_dir_exclusivo(self, *partes) -> Path:
        """Como mkdir sin exist_ok: FileExistsError si ya existe (candado atómico)."""
        p = self.ruta(*partes)
        os.mkdir(str(p), 0o700)
        return p

    def crear_exclusivo(self, partes, texto: str) -> Path:
        """Archivo NUEVO (O_EXCL, sin seguir enlaces). Si la escritura falla, se borra el archivo
        parcial que ESTA llamada creó (V2-E.1) y se propaga el error."""
        p = self.ruta(*partes)
        self._escribir_nuevo(p, texto, sincronizar=False)
        return p

    @staticmethod
    def _escribir_nuevo(p: Path, texto: str, sincronizar: bool):
        fd = os.open(str(p), os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NO_SEGUIR, 0o600)
        completo = False
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                fd = None                                  # ahora lo cierra el objeto archivo
                f.write(texto)
                f.flush()
                if sincronizar:
                    os.fsync(f.fileno())
            completo = True
        finally:
            if fd is not None:                             # os.fdopen falló: cerrar el descriptor
                os.close(fd)
            if not completo and os.path.lexists(str(p)):
                os.remove(str(p))                          # lo creó esta llamada (O_EXCL)

    def anexar(self, partes, texto: str) -> Path:
        p = self.ruta(*partes)
        fd = os.open(str(p), os.O_WRONLY | os.O_CREAT | os.O_APPEND | _NO_SEGUIR, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as f:
            f.write(texto)
        return p

    # --- V2-E: escrituras atómicas -----------------------------------------
    def _temporal(self, partes, texto: str):
        """Crea un temporal NUEVO junto al destino (misma carpeta), lo escribe y hace fsync."""
        tmp = tuple(partes[:-1]) + (f".tmp_{os.getpid()}_{os.urandom(6).hex()}",)
        p = self.ruta(*tmp)
        self._escribir_nuevo(p, texto, sincronizar=True)    # si falla, no deja el temporal
        return p

    def escribir_atomico(self, partes, texto: str):
        """Escribe un archivo NUEVO SIN sobrescribir nunca. Devuelve (ruta, atomico: bool).

        * Con os.link disponible: temporal (O_EXCL) + fsync + os.link(temporal, destino), que
          falla si el destino existe; el contenido aparece COMPLETO de una vez (atómico).
        * Sin os.link (Android/Termux) o si el sistema de archivos no admite enlaces duros
          (errno en _ERRNO_SIN_ENLACE): creación EXCLUSIVA del destino (O_CREAT|O_EXCL|O_NOFOLLOW)
          + escritura + fsync. Nunca sobrescribe, pero NO es atómico: durante la escritura otro
          lector podría ver el archivo incompleto. Si la escritura falla, se borra el parcial.
        * Nunca se usa os.replace/rename aquí (sobrescribirían un destino existente).
        * Cualquier otro error se propaga; el temporal se borra siempre."""
        destino = self.ruta(*partes)
        if os.path.lexists(str(destino)):
            raise FileExistsError(str(destino))
        if hay_enlaces_duros():
            tmp = self._temporal(partes, texto)
            try:
                try:
                    os.link(str(tmp), str(destino))
                    return destino, True
                except FileExistsError:
                    raise
                except OSError as e:
                    if e.errno not in _ERRNO_SIN_ENLACE:
                        raise
            finally:
                if os.path.lexists(str(tmp)):
                    os.remove(str(tmp))
        self._escribir_nuevo(destino, texto, sincronizar=True)
        return destino, False

    def reemplazar_atomico(self, partes, texto: str) -> Path:
        """Sustituye (o crea) un archivo PROPIO del orquestador, p. ej. el estado actual para la
        supervisión: temporal + fsync + os.replace. El destino no puede ser un enlace."""
        destino = self.ruta(*partes)
        if os.path.lexists(str(destino)) and (os.path.islink(str(destino))
                                              or not os.path.isfile(str(destino))):
            raise RutaInsegura(f"no es un archivo normal: {destino.name}")
        tmp = self._temporal(partes, texto)
        try:
            os.replace(str(tmp), str(destino))
        finally:
            if os.path.lexists(str(tmp)):
                os.remove(str(tmp))
        return destino

    def abrir_binario_exclusivo(self, partes):
        """Abre un archivo NUEVO para escritura binaria (p. ej. el registro del servidor)."""
        p = self.ruta(*partes)
        fd = os.open(str(p), os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NO_SEGUIR, 0o600)
        return os.fdopen(fd, "wb")

    def leer_desde(self, partes, pos: int = 0, max_bytes: int = 200_000):
        """Lee bytes desde `pos`. Devuelve (bytes, nueva_pos) o (None, pos) si no se puede."""
        p = self.ruta(*partes)
        try:
            fd = os.open(str(p), os.O_RDONLY | _NO_SEGUIR)
        except OSError:
            return None, pos
        with os.fdopen(fd, "rb") as f:
            f.seek(max(0, int(pos)))
            datos = f.read(max_bytes)
        return datos, int(pos) + len(datos)

    def leer_texto(self, partes, max_bytes: int = 4096):
        p = self.ruta(*partes)
        try:
            fd = os.open(str(p), os.O_RDONLY | _NO_SEGUIR)
        except OSError:
            return None
        with os.fdopen(fd, "rb") as f:
            return f.read(max_bytes).decode("utf-8", "replace")

    def quitar_candado(self, nombre: str = "lock"):
        """Borra SOLO la carpeta de candado propia: archivo 'pid' y la carpeta vacía."""
        d = self.ruta(nombre)
        pid = self.ruta(nombre, "pid")
        if os.path.lexists(str(pid)):
            os.remove(str(pid))
        os.rmdir(str(d))
