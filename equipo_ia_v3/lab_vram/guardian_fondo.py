"""Equipo IA V3.1 — LABORATORIO: guardián INDEPENDIENTE que reanuda Wallpaper Engine si Equipo IA termina de golpe.

    pythonw -B lab_vram/guardian_fondo.py --pid PID_EQUIPO --marca MARCA --exe RUTA\\wallpaper64.exe

Se lanza (por WMI, fuera del árbol de procesos de Equipo IA) justo cuando Equipo IA detiene el fondo animado y escribe
el archivo MARCA. Espera al proceso PID_EQUIPO (por su handle: inmune a la reutilización de pids):
- si MARCA desaparece (Equipo IA restauró el fondo por sí mismo) → termina sin hacer nada;
- si PID_EQUIPO termina y MARCA sigue → `wallpaper64.exe -control play` (la orden oficial; repetirla no hace daño),
  borra MARCA, deja constancia en MARCA.log y termina;
- como mucho vive 24 h. No es un servicio, no se registra en el inicio de Windows y no toca ningún otro proceso.
"""
import argparse
import ctypes
import os
import subprocess
import time

SYNCHRONIZE, WAIT_TIMEOUT = 0x00100000, 0x102
VIDA_MAX_S, PASO_MS = 24 * 3600, 3000


def anotar(marca, texto):
    try:                                                 # sin registro, el guardián sigue haciendo su trabajo
        with open(marca + ".log", "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%dT%H:%M:%S ") + texto + "\n")
    except OSError:
        pass


def reanudar(exe, marca, motivo):
    try:
        r = subprocess.run([exe, "-control", "play"], capture_output=True, timeout=60,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        anotar(marca, f"{motivo}: -control play rc={r.returncode}")
    except (OSError, subprocess.SubprocessError) as e:
        anotar(marca, f"{motivo}: FALLO al reanudar: {type(e).__name__}: {e}")
    try:
        os.remove(marca)
    except OSError:
        pass


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--pid", type=int, required=True)
    ap.add_argument("--marca", required=True)
    ap.add_argument("--exe", required=True)
    a = ap.parse_args(argv)
    if not os.path.isabs(a.marca):
        return 2                                         # una marca relativa no se puede vigilar con seguridad
    anotar(a.marca, f"guardián {os.getpid()} vigilando pid {a.pid}")
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenProcess.restype = ctypes.c_void_p
    k32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    h = k32.OpenProcess(SYNCHRONIZE, False, a.pid)
    if not h:                                            # Equipo IA ya no existe
        if os.path.exists(a.marca):
            reanudar(a.exe, a.marca, "pid inexistente al empezar")
        return 0
    t0 = time.monotonic()
    try:
        while time.monotonic() - t0 < VIDA_MAX_S:
            if not os.path.exists(a.marca):
                anotar(a.marca, "marca retirada por Equipo IA: nada que hacer")
                return 0
            if k32.WaitForSingleObject(h, PASO_MS) != WAIT_TIMEOUT:
                if os.path.exists(a.marca):
                    reanudar(a.exe, a.marca, f"Equipo IA (pid {a.pid}) terminó sin restaurar")
                return 0
        anotar(a.marca, "24 h sin terminar: el guardián se retira sin actuar")
        return 0
    finally:
        k32.CloseHandle(ctypes.c_void_p(h))


if __name__ == "__main__":
    raise SystemExit(main())
