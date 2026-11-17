"""Equipo IA V3.1 · LANZADOR de V2-F.1 en Windows (F0.5), sin modificar ningún archivo de `sistema/`.

    python -B -X utf8 eq3/lanzador_eq2.py <programa.py> [argumentos...]
    python -B -X utf8 eq3/lanzador_eq2.py -m <módulo> [argumentos...]
    python -B -X utf8 eq3/lanzador_eq2.py -c <código> [argumentos...]

**Problemas de V2-F.1 en Windows que corrige** (todos son diferencias con Linux y Termux, donde no ocurren):

1. *Finales de línea.* V2-F.1 escribe sus archivos en modo texto sin `newline`, y en Windows Python convierte «\\n»
   en «\\r\\n»; pero el SHA-256 que declara en sus eventos y manifiestos se calcula sobre el texto con «\\n». En
   Windows sus hashes declarados no coinciden con sus propios archivos, y eq3.ingesta rechaza (con razón) la
   importación por ErrorIntegridad.
2. *Codificación.* Sus procesos hijo de Python usan la codificación local (cp1252) para la salida estándar y para los
   archivos abiertos sin `encoding`, mientras el padre lee UTF-8: la lectura falla y el resultado se pierde.
3. *Procesos hijo.* Los dos problemas se repiten en cada Python que V2-F.1 lanza (verificador → pruebas → demos…),
   incluidos los que usan `-I`, que ignoran `PYTHONUTF8`.

**Qué hace.** Ejecuta el programa como `__main__`, igual que `python programa.py` / `-m` / `-c` (misma `sys.argv`, misma
primera entrada de `sys.path`, mismo código de salida), con tres ajustes que igualan Windows a Linux:

- `open()` en modo TEXTO de escritura sin `newline` explícito escribe «\\n». La lectura no cambia, el modo binario no
  cambia y un `newline` explícito se respeta. `sys.stdout` y `sys.stderr` también escriben «\\n».
- El intérprete se lanza con `-X utf8` (modo UTF-8 de Python).
- En Windows, `~` se toma de `HOME` si está definida (como en Linux y como en Windows hasta Python 3.7): V2-F.1 y sus
  pruebas fijan `HOME` para que `~/equipo-ia/...` sea una carpeta de laboratorio, y Python 3.8+ la ignoraría.
- En Windows, la vigilancia de memoria de V2-F.1 (que lee `/proc/meminfo` y `/proc/<pid>/status`) recibe mediciones
  REALES de Windows en ese formato (`con_proc`): MemAvailable, VmRSS y VmHWM. Lo que Windows no mide igual (majflt,
  RssAnon…) sigue ausente: nunca se inventa un valor. Sin esto, el monitor de V2-F.1 se queda ciego y aborta toda
  sesión con «sin_medicion_MemAvailable» (fallo cerrado), aunque haya memoria de sobra.
- En Windows, si el servidor muere a mitad de una petición, `BackendLlama.completar` informa «servidor_muerto» como en
  Linux en vez de «conexion_perdida:ConnectionResetError» (`con_servidor_muerto`), SOLO cuando el proceso del servidor
  ha terminado de verdad; si sigue vivo o no se puede saber, se conserva «conexion_perdida». El error es fatal en los
  dos casos: la parada de la sesión no cambia. Se aplica al importar `eq2.backend_llama`, sin tocar su archivo.
- `subprocess.Popen` adapta las órdenes que lanzan ESTE MISMO intérprete (`sys.executable`) para que pasen por este
  lanzador con `-X utf8`, conservando todas sus opciones (`-I`, `-B`, `-W`, `-X dev`…). Así los ajustes llegan a
  toda la cadena de procesos hijo.

**Qué NO hace** (límites de seguridad, comprobados por `pruebas/test_eq3_plataforma.py`):

- No cambia ninguna orden que no sea `sys.executable` (p. ej. `llama-server`), ni las que usan `shell=True` o
  `executable=`, ni un intérprete interactivo.
- No toca las órdenes con `-S`: es la marca del ejecutor restringido de V2-F.1 (`python -I -S -B corredor…`), cuyo
  proceso hijo debe ser exactamente el que V2-F.1 construye. El lanzador nunca se interpone ahí.
- No cambia el entorno, el directorio de trabajo, los descriptores ni las opciones de aislamiento de ninguna orden.
- No lee ni escribe archivos por su cuenta y no importa nada fuera de la biblioteca estándar.

Solo se usa en Windows (`eq3.plataforma.orden_eq2`); en el resto de sistemas V2-F.1 se ejecuta directamente.
"""
import builtins
import io
import os
import re
import runpy
import subprocess
import sys
import types

LANZADOR = os.path.abspath(__file__)
USO = "uso: lanzador_eq2.py (<programa.py> | -m <módulo> | -c <código>) [argumentos...]"
BANDERAS_SIMPLES = frozenset("bBdEIOPqRsuv")      # opciones del intérprete sin valor que se conservan tal cual
CON_VALOR = ("-W", "-X")


def con_lf(abrir):
    """`open` cuya escritura en modo texto sin `newline` explícito usa «\\n» (como en Linux)."""
    def abrir_lf(file, mode="r", buffering=-1, encoding=None, errors=None, newline=None, *resto, **kw):
        if newline is None and "b" not in mode and any(c in mode for c in "wax+"):
            newline = "\n"
        return abrir(file, mode, buffering, encoding, errors, newline, *resto, **kw)
    abrir_lf.__wrapped__ = abrir
    return abrir_lf


def con_home(expandir):
    """`os.path.expanduser` que, como en Linux (y en Windows hasta Python 3.7), toma `~` de `HOME` si está definida.

    V2-F.1 y sus pruebas fijan `HOME` (a veces dentro del propio proceso) para que `~` sea una carpeta de laboratorio;
    en Windows, Python 3.8+ usa `USERPROFILE` y la ignoraría. Solo afecta a «~» y «~/…» (no a «~usuario»)."""
    def expandir_home(ruta):
        texto = os.fspath(ruta)
        tilde = "~" if isinstance(texto, str) else b"~"
        seps = ("/", "\\") if isinstance(texto, str) else (b"/", b"\\")
        casa = os.environ.get("HOME")
        if casa and texto[:1] == tilde and (len(texto) == 1 or texto[1:2] in seps):
            return (casa if isinstance(texto, str) else os.fsencode(casa)) + texto[1:]
        return expandir(ruta)
    expandir_home.__wrapped__ = expandir
    return expandir_home


def memoria_disponible_kb():
    """MemAvailable REAL de Windows (GlobalMemoryStatusEx.ullAvailPhys, en kB) o None si la API falla."""
    import ctypes

    class Estado(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
    e = Estado()
    e.dwLength = ctypes.sizeof(e)
    try:
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(e)):
            return None
    except (AttributeError, OSError):
        return None
    return e.ullAvailPhys // 1024


def memoria_proceso_kb(pid: int):
    """(VmRSS, VmHWM) REALES de un proceso de Windows: WorkingSetSize y PeakWorkingSetSize (GetProcessMemoryInfo), en
    kB, o None si no se puede consultar (proceso inexistente, sin permiso, API no disponible)."""
    import ctypes
    from ctypes import wintypes

    class Contadores(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
    try:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
    except (AttributeError, OSError):
        return None
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
    h = k32.OpenProcess(0x1000, False, pid)                     # PROCESS_QUERY_LIMITED_INFORMATION: solo lectura
    if not h:
        return None
    try:
        c = Contadores()
        c.cb = ctypes.sizeof(c)
        if not psapi.GetProcessMemoryInfo(h, ctypes.byref(c), c.cb):
            return None
        return c.WorkingSetSize // 1024, c.PeakWorkingSetSize // 1024
    finally:
        k32.CloseHandle(h)


_PROC_STATUS = re.compile(r"^/proc/(\d{1,10})/status$")


def con_proc(abrir, medir_sistema=memoria_disponible_kb, medir_proceso=memoria_proceso_kb):
    """`open` que, SOLO en lectura de texto y SOLO para «/proc/meminfo» y «/proc/<pid>/status» (rutas que no existen en
    Windows), devuelve el texto con las mediciones REALES de Windows en el formato de Linux:

    - /proc/meminfo → `MemAvailable` (memoria física disponible);
    - /proc/<pid>/status → `VmRSS` y `VmHWM` (conjunto de trabajo actual y máximo del proceso).

    Lo que Windows no mide igual (RssAnon, RssFile, SwapFree, y majflt/minflt de /proc/<pid>/stat) NO se inventa: sigue
    ausente, y V2-F.1 lo trata como ausente (respuesta «no concluyente»). Si la medición falla, se abre la ruta real, que
    no existe: el resultado es el mismo que sin adaptador (V2-F.1 se queda sin medición y aborta por seguridad)."""
    def abrir_proc(file, mode="r", *resto, **kw):
        if isinstance(file, (str, os.PathLike)) and "r" in mode and "b" not in mode and not any(c in mode for c in "wax+"):
            ruta = os.fspath(file).replace("\\", "/")
            if ruta == "/proc/meminfo":
                kb = medir_sistema()
                if kb is not None:
                    return io.StringIO(f"MemAvailable:   {kb} kB\n")
            else:
                m = _PROC_STATUS.match(ruta)
                if m:
                    v = medir_proceso(int(m.group(1)))
                    if v is not None:
                        return io.StringIO(f"VmHWM:\t{v[1]} kB\nVmRSS:\t{v[0]} kB\n")
        return abrir(file, mode, *resto, **kw)
    abrir_proc.__wrapped__ = abrir
    return abrir_proc


MODULO_BACKEND = "eq2.backend_llama"
MOTIVO_CORTE = "conexion_perdida:"            # como lo escribe eq2.cliente_http al perder la conexión leyendo
ESPERA_FIN_SERVIDOR_S = 0.5                   # la misma espera que usa V2-F.1 (`servidor.murio_pronto`)


def servidor_terminado(backend, espera=ESPERA_FIN_SERVIDOR_S) -> bool:
    """True SOLO si hay evidencia de que el proceso del servidor de `backend` ha terminado (tiene código de salida).

    False si sigue vivo tras `espera` segundos, si no hay proceso, o si su estado no se puede determinar (cualquier
    error al consultarlo): ante la duda, no se afirma que murió."""
    try:
        proc = backend.srv.proc
        if proc is None:
            return False
        try:
            proc.wait(espera)
        except subprocess.TimeoutExpired:
            return False
        return proc.poll() is not None
    except Exception:
        return False


def con_servidor_muerto(completar, error, terminado=servidor_terminado):
    """`BackendLlama.completar` que, en Windows, etiqueta igual que en Linux la muerte del servidor a mitad de petición.

    Si el servidor muere mientras se lee su respuesta, Linux entrega fin de datos («respuesta_truncada», no fatal) y
    V2-F.1 comprueba si el proceso murió («servidor_muerto»). Windows entrega ConnectionResetError
    («conexion_perdida:…», fatal) y V2-F.1 no llega a esa comprobación. Aquí se hace esa MISMA comprobación:

    - solo para el motivo «conexion_perdida:…» (nunca una parada, un plazo agotado ni otro fallo);
    - solo si el proceso del servidor HA TERMINADO (`servidor_terminado`); si vive o no se sabe, no cambia nada.

    Solo cambia la etiqueta: el error era fatal y sigue siéndolo, así que la sesión se detiene exactamente igual."""
    def completar_adaptado(self, *args, **kw):
        try:
            return completar(self, *args, **kw)
        except error as e:
            motivo = getattr(e, "motivo", None)
            if not (isinstance(motivo, str) and motivo.startswith(MOTIVO_CORTE) and terminado(self)):
                raise
            peticiones = getattr(self, "peticiones", None)
            reg = peticiones[-1] if isinstance(peticiones, list) and peticiones else None
            if isinstance(reg, dict) and reg.get("fallo") == motivo:
                reg["fallo"] = "servidor_muerto"
            raise error("servidor_muerto", fatal=True) from e
    completar_adaptado.__wrapped__ = completar
    return completar_adaptado


def adaptar_backend(modulo) -> bool:
    """Aplica `con_servidor_muerto` a `BackendLlama` del módulo recién importado. Si el módulo no tiene la forma
    esperada no toca nada (V2-F.1 se comporta como sin adaptador)."""
    clase, error = getattr(modulo, "BackendLlama", None), getattr(modulo, "ErrorInferencia", None)
    completar = getattr(clase, "completar", None)
    if not (isinstance(clase, type) and isinstance(error, type) and issubclass(error, Exception) and callable(completar)):
        return False
    if getattr(completar, "__wrapped__", None) is not None:
        return False
    clase.completar = con_servidor_muerto(completar, error)
    return True


class _CargadorBackend:
    """Cargador que ejecuta el módulo con su cargador real (el archivo de `sistema/`, sin cambios) y después lo adapta."""

    def __init__(self, cargador):
        self.cargador = cargador

    def create_module(self, spec):
        return self.cargador.create_module(spec)

    def exec_module(self, modulo):
        self.cargador.exec_module(modulo)
        adaptar_backend(modulo)

    def __getattr__(self, nombre):                              # get_source, get_code…: los del cargador real
        return getattr(self.__dict__["cargador"], nombre)


class BuscadorBackend:
    """Buscador de importación que solo reconoce `eq2.backend_llama`: lo localiza con los buscadores normales y le
    pone `_CargadorBackend`. No importa nada por su cuenta ni afecta a ningún otro módulo."""

    def find_spec(self, nombre, ruta=None, destino=None):
        if nombre != MODULO_BACKEND:
            return None
        for buscador in sys.meta_path:
            buscar = getattr(buscador, "find_spec", None)
            # por NOMBRE de clase: otra copia de este módulo (p. ej. la de un espejo de mutación) tiene otra clase
            if buscador is self or type(buscador).__name__ == "BuscadorBackend" or buscar is None:
                continue
            spec = buscar(nombre, ruta, destino)
            if spec is not None:
                if spec.loader is not None and hasattr(spec.loader, "exec_module"):
                    spec.loader = _CargadorBackend(spec.loader)
                return spec
        return None


def _misma_ruta(a: str, b: str) -> bool:
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def adaptar_orden(args):
    """Orden adaptada (lista nueva) o el MISMO objeto `args` si no es un Python hijo que se pueda adaptar con seguridad.

    Solo se adapta `[sys.executable, <opciones conocidas>..., (programa.py | -m módulo | -c código), ...]`. Ante
    cualquier duda (opción desconocida, `-S`, `-i`, `-`, sin programa, ya adaptada...) se devuelve `args` sin tocar."""
    if not isinstance(args, (list, tuple)) or not args:
        return args
    try:
        orden = [os.fspath(a) for a in args]
    except TypeError:
        return args
    if any(not isinstance(a, str) for a in orden) or not _misma_ruta(orden[0], sys.executable):
        return args
    opciones, i = [], 1
    while i < len(orden):
        a = orden[i]
        if a in ("-c", "-m"):
            if i + 1 >= len(orden):
                return args
            break
        if a in CON_VALOR:
            if i + 1 >= len(orden):
                return args
            opciones += [a, orden[i + 1]]
            i += 2
        elif a.startswith(CON_VALOR):                          # -Wd, -Xdev
            opciones.append(a)
            i += 1
        elif a.startswith("-"):
            if len(a) < 2 or not set(a[1:]) <= BANDERAS_SIMPLES:   # -S, -i, -h, -x, -, --opción…: no se toca
                return args
            opciones.append(a)
            i += 1
        else:
            # ya pasa por un lanzador: este u OTRA copia (un espejo de mutación); envolverlo lo instalaría dos veces
            if not a.lower().endswith(".py") or _misma_ruta(a, LANZADOR) or \
                    os.path.basename(a).lower() == os.path.basename(LANZADOR).lower():
                return args
            break
    else:
        return args                                             # intérprete sin programa
    return [orden[0], *opciones, "-X", "utf8", LANZADOR, *orden[i:]]


class PopenAdaptado(subprocess.Popen):
    """`subprocess.Popen` que adapta las órdenes de Python hijo (ver `adaptar_orden`); el resto pasa sin cambios."""

    def __init__(self, args, *resto, **kw):
        if not resto and not kw.get("shell") and kw.get("executable") is None:
            args = adaptar_orden(args)
        super().__init__(args, *resto, **kw)


def instalar() -> None:
    """Instala los ajustes en ESTE proceso (idempotente)."""
    if getattr(builtins.open, "__wrapped__", None) is None:
        builtins.open = io.open = con_lf(io.open)        # `os.fdopen` y `Path.open` pasan por `io.open`
        if os.name == "nt":
            builtins.open = io.open = con_proc(io.open)  # memoria REAL de Windows donde V2-F.1 lee /proc
    if os.name == "nt" and getattr(os.path.expanduser, "__wrapped__", None) is None:
        os.path.expanduser = con_home(os.path.expanduser)  # `Path.home()` y `Path.expanduser()` pasan por aquí
    if os.name == "nt" and not any(type(b).__name__ == "BuscadorBackend" for b in sys.meta_path):
        sys.meta_path.insert(0, BuscadorBackend())       # «servidor_muerto» cuando Windows corta la conexión
    if subprocess.Popen is not PopenAdaptado and not issubclass(subprocess.Popen, PopenAdaptado):
        subprocess.Popen = PopenAdaptado
    for flujo in (sys.stdout, sys.stderr):
        if isinstance(flujo, io.TextIOWrapper):
            flujo.reconfigure(newline="\n")


def _primera_ruta(valor: str) -> None:
    """Deja la primera entrada de `sys.path` como la dejaría Python sin el lanzador (nunca la carpeta de eq3)."""
    if getattr(sys.flags, "safe_path", False):              # -P / -I: Python no añade la carpeta del programa
        return
    if sys.path and _misma_ruta(sys.path[0] or os.getcwd(), os.path.dirname(LANZADOR)):
        sys.path[0] = valor


def main(argv) -> None:
    if not argv:
        raise SystemExit(USO)
    modo, resto = argv[0], argv[1:]
    if modo in ("-c", "-m"):
        if not resto:
            raise SystemExit(USO)
    elif modo.startswith("-") or not modo.lower().endswith(".py") or not os.path.isfile(modo):
        raise SystemExit(USO)
    instalar()
    if modo == "-c":
        sys.argv = ["-c", *resto[1:]]
        _primera_ruta("")
        principal = types.ModuleType("__main__")
        principal.__dict__["__builtins__"] = builtins
        sys.modules["__main__"] = principal
        exec(compile(resto[0], "<string>", "exec"), principal.__dict__)
    elif modo == "-m":
        sys.argv = [resto[0], *resto[1:]]
        _primera_ruta(os.getcwd())
        runpy.run_module(resto[0], run_name="__main__", alter_sys=True)
    else:
        sys.argv = [modo, *resto]
        _primera_ruta(os.path.dirname(os.path.realpath(modo)))
        runpy.run_path(modo, run_name="__main__")                # sys.argv[0] y __file__ como los pasó el llamante


if __name__ == "__main__":
    main(sys.argv[1:])
