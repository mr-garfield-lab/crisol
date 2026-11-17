"""Equipo IA V3.1 · ADAPTADORES DE PLATAFORMA (F0.5): un solo motor para Linux/WSL2, Android/Termux y Windows.

Aquí está TODO lo que cambia entre sistemas para eq3, `pruebas/`, `v3/` y `verificar_v3.py`; el resto del código no
pregunta en qué sistema corre. `sistema/` (V2-F.1) no se modifica.

- **Procesos hijo** (`entorno_hijo`, `ejecutar`). Entorno mínimo con HOME/TMPDIR propios (en Linux y Termux, el
  mismo de V3), y la salida se lee siempre como UTF-8. En Windows se fuerza también UTF-8 en el hijo (antes escribía
  en cp1252 y el padre leía UTF-8), se añaden las variables sin las que Python no arranca (SYSTEMROOT...) y
  USERPROFILE/TEMP/TMP apuntan a la carpeta temporal: `Path.home()` y `~` usan USERPROFILE, no HOME, y sin esto una
  prueba escribiría en la carpeta real del usuario.
- **Enlaces** (`es_enlace`, `crear_enlace`). En Windows redirigen una ruta los symlinks y TAMBIÉN las uniones de
  directorio (junctions) y otros puntos de reanálisis; `Path.is_symlink()` no ve las uniones y `os.walk` entra en
  ellas aunque `followlinks=False` (comprobado en Windows 11 con Python 3.12). `es_enlace` las rechaza todas.
  Crear un symlink exige un privilegio (WinError 1314) que no siempre hay: `crear_enlace` usa entonces una unión
  para carpetas y, para archivos, lanza `EnlaceNoDisponible` (las pruebas lo convierten en OMITIDA explícita).
- **Lectura acotada sin seguir enlaces** (`leer_acotado`, `adaptar_contexto_ligero`). Contexto Ligero exige
  `dir_fd`/`O_NOFOLLOW`, que Windows no tiene, y falla cerrado: no indexa nada. Donde faltan, se instala una lectura
  con las mismas reglas (ver `leer_acotado`), sin modificar los archivos de Contexto Ligero.
- **Rutas en textos** (`variantes_ruta`, `barras_tras_marca`): para normalizar firmas de pruebas en cualquier sistema.
"""
from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path, PurePosixPath

WINDOWS = os.name == "nt"
# Imprescindibles para arrancar Python y resolver órdenes en Windows; no contienen datos del usuario.
VARIABLES_SISTEMA_WINDOWS = ("SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATHEXT", "NUMBER_OF_PROCESSORS",
                             "PROCESSOR_ARCHITECTURE", "OS")
_REANALISIS = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
_SIN_PRIVILEGIO_ENLACE = 1314                       # ERROR_PRIVILEGE_NOT_HELD
_ACCESO_DENEGADO = 5                                # ERROR_ACCESS_DENIED


class EnlaceNoDisponible(OSError):
    """Esta plataforma no permite crear el enlace pedido (Windows sin privilegio para symlinks de archivo)."""


def nombre() -> str:
    """windows · android (Termux) · linux · darwin…: solo informativo, para informes y evidencias."""
    if WINDOWS:
        return "windows"
    if hasattr(sys, "getandroidapilevel") or "ANDROID_ROOT" in os.environ:
        return "android"
    return sys.platform


# --- procesos hijo -----------------------------------------------------------------------------------------
def entorno_hijo(tmp, extra: dict | None = None) -> dict:
    """Entorno mínimo y aislado para un proceso hijo: del usuario solo se conserva PATH; HOME y TMPDIR son `tmp`.

    En Linux y Termux es EXACTAMENTE el entorno de V3. En Windows se añaden las variables de sistema imprescindibles,
    USERPROFILE/TEMP/TMP/APPDATA/LOCALAPPDATA = `tmp` y UTF-8 forzado (sin él, el hijo escribe en cp1252)."""
    tmp = str(tmp)
    e = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8", "HOME": tmp, "TMPDIR": tmp,
         "PYTHONDONTWRITEBYTECODE": "1"}
    if WINDOWS:
        e.update({k: os.environ[k] for k in VARIABLES_SISTEMA_WINDOWS if k in os.environ})
        e.update({"USERPROFILE": tmp, "TEMP": tmp, "TMP": tmp, "APPDATA": tmp, "LOCALAPPDATA": tmp})
        e.update({"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
    e.update(extra or {})
    return e


def orden_eq2(programa: str, *args) -> list:
    """Orden para ejecutar un programa de V2-F.1 (cwd = `sistema/`). En Windows pasa por `eq3/lanzador_eq2.py`
    (escritura de texto con «\\n», ver su documentación); en el resto, `python -B programa`, exactamente como antes."""
    if WINDOWS:
        return [sys.executable, "-B", "-X", "utf8", str(Path(__file__).with_name("lanzador_eq2.py")), programa, *args]
    return [sys.executable, "-B", programa, *args]


def ejecutar(orden: list, **kw) -> subprocess.CompletedProcess:
    """`subprocess.run` con la salida capturada y decodificada SIEMPRE como UTF-8 (lo que no lo sea se sustituye,
    no se pierde la ejecución). Nunca usa shell."""
    return subprocess.run(orden, capture_output=True, encoding="utf-8", errors="replace", **kw)


# --- enlaces ---------------------------------------------------------------------------------------------------
def es_enlace(p) -> bool:
    """¿`p` redirige a otra ruta? Symlink en cualquier sistema; en Windows también uniones de directorio y cualquier
    otro punto de reanálisis (falla cerrado: lo que Windows marca como reanálisis no se sigue). Como
    `Path.is_symlink()`, devuelve False si `p` no existe."""
    try:
        st = os.lstat(p)
    except (OSError, ValueError):
        return False
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, "st_file_attributes", 0) & _REANALISIS)


def crear_enlace(destino, objetivo) -> str:
    """Crea `destino` → `objetivo` (para pruebas de seguridad). Devuelve «simbolico» o «union».

    En Windows sin privilegio de symlinks: unión de directorio si `objetivo` es una carpeta; si es un archivo, lanza
    `EnlaceNoDisponible`. Las uniones solo se crean hacia carpetas que existen."""
    destino, objetivo = Path(destino), Path(objetivo)
    try:
        destino.symlink_to(objetivo, target_is_directory=objetivo.is_dir())
        return "simbolico"
    except OSError as e:
        if not WINDOWS or getattr(e, "winerror", None) != _SIN_PRIVILEGIO_ENLACE:
            raise
    if objetivo.is_dir():
        import _winapi
        _winapi.CreateJunction(str(objetivo.resolve(strict=True)), str(destino))
        return "union"
    raise EnlaceNoDisponible("Windows sin privilegio para crear enlaces simbólicos a archivos (WinError 1314); "
                             "se puede habilitar con el modo de desarrollador")


def puede_enlazar_archivos(carpeta) -> bool:
    """¿Se puede crear aquí un symlink a un ARCHIVO? (Linux/Termux: sí; Windows: solo con privilegio)."""
    carpeta = Path(carpeta)
    objetivo, enlace = carpeta / ".eq3_sonda_objetivo", carpeta / ".eq3_sonda_enlace"
    objetivo.write_bytes(b"")
    try:
        crear_enlace(enlace, objetivo)
        return True
    except OSError:
        return False
    finally:
        for p in (enlace, objetivo):
            if es_enlace(p) or p.exists():
                p.unlink()


def replicar_solo_lectura(origen, destino) -> str:
    """Pone `origen` (carpeta que el llamante solo LEE) en `destino`: symlink si se puede; si no (Windows sin
    privilegio), una COPIA, que protege el original aún mejor. Nunca una unión: borrar el espejo no debe poder
    alcanzar el original."""
    try:
        os.symlink(origen, destino, target_is_directory=True)
        return "simbolico"
    except OSError as e:
        # 1314: sin privilegio. 5 (acceso denegado): visto de forma esporádica en Windows al crear muchos enlaces
        # seguidos (F7 de --completo, 2026-11-11). En ambos casos no hay enlace y la copia es igual de segura.
        if not WINDOWS or getattr(e, "winerror", None) not in (_SIN_PRIVILEGIO_ENLACE, _ACCESO_DENEGADO):
            raise
        if os.path.lexists(destino):
            raise
    shutil.copytree(origen, destino, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    return "copia"


# --- lectura acotada sin seguir enlaces (Contexto Ligero en Windows) -------------------------------------------
def _parte_valida(parte: str) -> bool:
    # En Windows «a.py:flujo» abre un flujo alternativo, y «a.py.» o «a.py » alias de «a.py»: se rechazan.
    return parte not in ("", ".") and ":" not in parte and not parte.endswith((".", " "))


def leer_acotado(root, path, max_bytes):
    """Mismo contrato que `contexto_core.safety.read_bounded`, para sistemas sin `dir_fd`/`O_NOFOLLOW`.

    - Mismas validaciones de `path`: texto relativo POSIX, sin «\\», sin NUL, sin «..», sin rutas absolutas.
    - Además (Windows): sin «:» (flujos alternativos) ni componentes acabados en punto o espacio.
    - Ni `root` ni ningún componente puede ser un enlace o punto de reanálisis (`es_enlace`); solo archivos normales
      de como mucho `max_bytes`.
    - El archivo abierto debe ser el MISMO que se comprobó (inodo y dispositivo); si no, ValueError.
    Como el original, no garantiza un snapshot frente a un escritor concurrente malicioso; el llamante valida el
    SHA-256 de los bytes antes de usarlos."""
    if not isinstance(path, str) or "\\" in path or "\x00" in path:
        raise ValueError("Ruta no permitida")
    rel = PurePosixPath(path)
    if rel.is_absolute() or ".." in rel.parts or not rel.parts or not all(_parte_valida(x) for x in rel.parts):
        raise ValueError("Ruta no permitida")
    if not isinstance(max_bytes, int) or max_bytes < 0:
        raise ValueError("Límite de lectura inválido")
    actual = Path(root)
    if es_enlace(actual):
        raise ValueError("Ruta no permitida")
    for parte in rel.parts:
        actual = actual / parte
        if es_enlace(actual):
            raise ValueError("Ruta no permitida")
    previo = os.lstat(actual)
    if not stat.S_ISREG(previo.st_mode) or previo.st_size > max_bytes:
        raise ValueError("Archivo no regular o excede el tamaño indexado; reindexar")
    fd = os.open(actual, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    try:
        info = os.fstat(fd)
        if (info.st_ino, info.st_dev) != (previo.st_ino, previo.st_dev) or not stat.S_ISREG(info.st_mode):
            raise ValueError("Archivo cambiado durante la lectura; reindexar")
        partes, total = [], 0
        while total <= max_bytes:
            trozo = os.read(fd, min(65536, max_bytes + 1 - total))
            if not trozo:
                break
            partes.append(trozo)
            total += len(trozo)
        if total > max_bytes:
            raise ValueError("Archivo creció; reindexar")
        return b"".join(partes)
    finally:
        os.close(fd)


def lectura_posix_disponible() -> bool:
    return hasattr(os, "O_NOFOLLOW") and os.open in os.supports_dir_fd


def adaptar_contexto_ligero() -> bool:
    """Instala `leer_acotado` como `contexto_core.safety.read_bounded` SOLO si falta la lectura POSIX (Windows).
    En Linux y Termux no cambia nada. Devuelve si se instaló."""
    if lectura_posix_disponible():
        return False
    from contexto_core import safety
    safety.read_bounded = leer_acotado
    return True


# --- rutas dentro de textos ------------------------------------------------------------------------------------
def variantes_ruta(p) -> list:
    """Formas en que la ruta `p` puede aparecer en un mensaje: nativa, POSIX y con «\\» escapadas (repr de Windows)."""
    nativa = str(p)
    return list(dict.fromkeys([nativa, Path(p).as_posix(), nativa.replace("\\", "\\\\")]))


def barras_tras_marca(texto: str, marcas) -> str:
    """En Windows, «<MARCA>\\a\\b» → «<MARCA>/a/b» (también «\\\\» escapadas), para que una firma sea la misma en
    todos los sistemas. Fuera de Windows no cambia nada: las firmas de Linux siguen siendo byte a byte las mismas."""
    if not WINDOWS:
        return texto
    patron = "(" + "|".join(re.escape(m) for m in marcas) + r")([^\s'\"]*)"
    return re.sub(patron, lambda m: m.group(1) + m.group(2).replace("\\\\", "/").replace("\\", "/"), texto)
