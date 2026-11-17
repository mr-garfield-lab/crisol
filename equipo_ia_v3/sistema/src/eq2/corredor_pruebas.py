"""V2-E.7: corredor de pruebas del EJECUTOR RESTRINGIDO. Solo se ejecuta como proceso HIJO:

    python3 -I -S -B corredor_pruebas.py <espacio> <seg_cpu> <mem_mb>

No se importa desde el paquete. Antes de cargar una sola línea del código de los agentes:
  1. lee el «nonce» por stdin (los resultados solo valen si llevan ese nonce; el código probado no lo ve);
  2. fija límites del núcleo: CPU, memoria, tamaño de archivo, descriptores, sin núcleo y sin procesos nuevos;
  3. instala un gancho de auditoría (sys.addaudithook, imposible de quitar desde Python) que prohíbe:
     escribir fuera del espacio, leer fuera del espacio y de la biblioteca estándar, red, subprocesos,
     señales, ctypes, cambios de permisos, enlaces y la inspección de marcos;
  4. carga test_*.py del espacio (clases unittest y funciones test_* al estilo pytest) y las ejecuta.
El resultado sale por el descriptor 1 en una línea «EQ2RES <nonce> <json>». NO es un sandbox: es una
defensa en capas sobre un código que antes pasó la lista blanca AST de ejecutor_restringido.py.
"""
import sys


def main():
    import io
    import json
    import os
    import resource
    import unittest

    espacio = os.path.realpath(sys.argv[1])
    seg, mem = int(sys.argv[2]), int(sys.argv[3])
    nonce = sys.stdin.buffer.read(32).decode("ascii", "replace")
    sys.stdin = io.StringIO("")
    biblioteca = os.path.realpath(os.path.dirname(os.__file__))

    limites = {}
    pedidos = [("cpu_s", "RLIMIT_CPU", seg), ("memoria_bytes", "RLIMIT_AS", mem * 1024 * 1024),
               ("archivo_bytes", "RLIMIT_FSIZE", 1 << 20), ("descriptores", "RLIMIT_NOFILE", 64),
               ("core", "RLIMIT_CORE", 0), ("procesos_nuevos", "RLIMIT_NPROC", 0)]
    for clave, nombre, valor in pedidos:
        r = getattr(resource, nombre, None)
        try:
            resource.setrlimit(r, (valor, valor))
            limites[clave] = valor
        except (ValueError, OSError, TypeError) as e:
            limites[clave] = "no_aplicado: " + type(e).__name__

    escritura = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
    lectura_ok = ("/dev/null", "/dev/urandom")
    prohibidos = ("socket.", "subprocess.", "os.system", "os.exec", "os.posix_spawn", "os.spawn",
                  "os.fork", "os.forkpty", "os.kill", "os.killpg", "os.chmod", "os.chown", "os.lchown",
                  "os.chflags", "os.link", "os.symlink", "os.setxattr", "os.removexattr", "os.putenv",
                  "os.unsetenv", "os.startfile", "shutil.", "ctypes.", "urllib.", "webbrowser.",
                  "sys._getframe", "sys._current_frames", "sys.setprofile", "sys.settrace",
                  "builtins.input", "marshal.", "pickle.", "code.__new__", "function.__new__",
                  "resource.setrlimit", "fcntl.", "mmap.", "signal.", "sqlite3.", "ftplib.",
                  "smtplib.", "http.client.", "cpython.remote_debugger")
    mod_prohibidos = {"ctypes", "_ctypes", "socket", "_socket", "subprocess", "_posixsubprocess",
                      "multiprocessing", "_multiprocessing", "mmap", "fcntl", "resource", "pty",
                      "termios", "asyncio", "concurrent", "ssl", "_ssl", "select", "selectors", "http",
                      "urllib", "ftplib", "smtplib", "sqlite3", "_sqlite3", "webbrowser", "pickle",
                      "_pickle", "marshal", "shelve", "dbm", "runpy", "code", "codeop", "pdb", "signal",
                      "threading", "_thread"}

    def dentro(p, raiz):
        return p == raiz or p.startswith(raiz + os.sep)

    def ruta_de(x):
        if x is None:
            return os.path.realpath(".")
        if isinstance(x, int):
            return None
        return os.path.realpath(os.fsdecode(x))

    def gancho(evento, args):
        if evento == "open":
            ruta, modo, flags = (list(args) + [None, None, None])[:3]
            p = ruta_de(ruta)
            if p is None:
                return
            esc = (isinstance(modo, str) and any(c in modo for c in "wax+")) or \
                (isinstance(flags, int) and bool(flags & escritura))
            if esc and not dentro(p, espacio):
                raise PermissionError("EQ2: escritura fuera del espacio: " + p)
            if not esc and not (dentro(p, espacio) or dentro(p, biblioteca) or p in lectura_ok):
                raise PermissionError("EQ2: lectura fuera del espacio: " + p)
            return
        if evento == "import":
            if str(args[0]).split(".")[0] in mod_prohibidos:
                raise ImportError("EQ2: módulo prohibido: " + str(args[0]))
            return
        if evento in ("os.remove", "os.rmdir", "os.mkdir", "os.truncate", "os.utime", "os.listdir",
                      "os.scandir", "os.rename"):
            for x in args[:2] if evento == "os.rename" else args[:1]:
                p = ruta_de(x)
                if p is not None and not dentro(p, espacio) and not (
                        evento in ("os.listdir", "os.scandir") and dentro(p, biblioteca)):
                    raise PermissionError(f"EQ2: {evento} fuera del espacio: {p}")
            return
        for pre in prohibidos:
            if evento.startswith(pre):
                raise PermissionError("EQ2: operación prohibida: " + evento)

    sys.addaudithook(gancho)
    sys.path[:] = [espacio] + [p for p in sys.path if p and dentro(os.path.realpath(p), biblioteca)]
    os.chdir(espacio)

    estados = {}

    def anotar(prueba, estado):
        nombre = str(getattr(prueba, "_eq2_nombre", None) or prueba.id().split(".")[-1])
        peor = {"ok": 0, "omitida": 1, "fallo": 2, "error": 3}
        if peor.get(estado, 3) >= peor.get(estados.get(nombre, "ok"), 0):
            estados[nombre] = estado

    class Resultado(unittest.TextTestResult):
        def addSuccess(self, t):
            super().addSuccess(t)
            anotar(t, "ok")

        def addFailure(self, t, e):
            super().addFailure(t, e)
            anotar(t, "fallo")

        def addError(self, t, e):
            super().addError(t, e)
            anotar(t, "error")

        def addSkip(self, t, r):
            super().addSkip(t, r)
            anotar(t, "omitida")

    cargador = unittest.TestLoader()
    suite = unittest.TestSuite()
    errores_carga = []
    for nombre in sorted(os.listdir(espacio)):
        if not (nombre.startswith("test") and nombre.endswith(".py")):
            continue
        mod = nombre[:-3]
        try:
            suite.addTests(cargador.loadTestsFromName(mod))
            m = sys.modules[mod]
            for clave, fn in sorted(vars(m).items()):
                if clave.startswith("test") and callable(fn) and not isinstance(fn, type) \
                        and getattr(fn, "__module__", None) == mod:
                    caso = unittest.FunctionTestCase(fn, description=clave)
                    caso._eq2_nombre = clave
                    suite.addTest(caso)
        except Exception as e:                        # el código probado no puede tumbar el informe
            errores_carga.append(f"{mod}: {type(e).__name__}: {str(e)[:300]}")
            estados["importar:" + mod] = "error"
    texto = io.StringIO()
    sys.stdout = sys.stderr = io.StringIO()          # nada del código probado llega al descriptor 1
    r = unittest.TextTestRunner(stream=texto, verbosity=2, buffer=True, resultclass=Resultado).run(suite)
    datos = {"total": r.testsRun, "fallos": len(r.failures), "errores": len(r.errors) + len(errores_carga),
             "omitidas": len(r.skipped), "pruebas": estados, "errores_carga": errores_carga,
             "limites": limites, "texto": texto.getvalue()[-200_000:]}
    os.write(1, ("\nEQ2RES " + nonce + " " + json.dumps(datos, ensure_ascii=False) + "\n").encode("utf-8"))
    return 0 if (r.testsRun > 0 and r.wasSuccessful() and not errores_carga) else 1


if __name__ == "__main__":
    sys.exit(main())
