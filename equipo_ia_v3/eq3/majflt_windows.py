"""Equipo IA V3.1 F1 — fallos DUROS de página de Windows (`HardFaultCount`) donde V2-F.1 lee `majflt` (decisión D3).

QUÉ ES Y QUÉ NO ES. V2-F.1 exige, para dar una respuesta por concluyente, que `majflt` (fallos de página que
obligaron a leer del disco) se haya podido medir antes y después de la petición (`config.CRITICAS`). En Linux lo lee
de `/proc/<pid>/stat`. En Windows este módulo sirve en ese mismo formato el contador `HardFaultCount` del proceso:

- **No es el `majflt` de Linux.** Es un contador distinto de otro sistema: Windows agrupa las lecturas del disco
  (≈1 fallo duro por cada ~1 MiB leído en la medición del proyecto), así que SUS MAGNITUDES NO SON COMPARABLES con las
  de Linux ni deben compararse entre plataformas. Solo se usa con la semántica verificada: 0 = el proceso no tuvo que
  leer del disco para atender la petición; > 0 = sí tuvo que hacerlo.
- **Interfaz no documentada oficialmente.** `HardFaultCount` está en `SYSTEM_PROCESS_INFORMATION`
  (`NtQuerySystemInformation`, clase 5), en un campo que Microsoft declara reservado; el desplazamiento usado (0x10 en
  64 bits) es el de Windows 7 a 11, pero una versión futura podría cambiarlo sin aviso. Por eso:
- **Autocomprobación (sonda) al iniciar cada sesión** (`activar`): se escribe un archivo propio sin pasar por la
  caché y se lee dos veces con mmap. Solo si la lectura fría da fallos duros (> 0) y la caliente da 0, el contador se
  considera fiable EN ESTA SESIÓN y se sirve.
- **Fallo cerrado.** Si la sonda falla, o si el contador de un proceso no se puede leer, NO se sirve nada: `majflt`
  sigue ausente y V2-F.1 marca la respuesta como «no concluyente» (`medicion_critica_ausente:majflt`). La ausencia
  nunca se convierte en un cero.
- **Solo bajo petición.** El lanzador no lo activa: la línea base de F11 (donde `majflt` está ausente en Windows,
  causa WIN_SIN_MAJFLT) no cambia. Lo activa la evaluación de F1, que anota la etiqueta en cada sesión.
"""
from __future__ import annotations

import builtins
import io
import mmap
import os
import re
import time

ETIQUETA = ("majflt = HardFaultCount de Windows (fallos duros de página; agrupado, ≈1 por cada ~1 MiB leído del disco). "
            "NO es el majflt de Linux y sus magnitudes NO son comparables entre plataformas; interfaz no documentada "
            "oficialmente, usada solo tras superar la sonda de esta sesión")
MIB_SONDA = 128
_PROC_STAT = re.compile(r"^/proc/(\d{1,10})/stat$")
ESTADO = {"activo": False, "sonda": None}


def contadores_fallos(pid: int):
    """(HardFaultCount, PageFaultCount) del proceso `pid` según la tabla de procesos del sistema, o None si no se
    puede leer (API ausente, error, proceso inexistente, arquitectura no verificada)."""
    import ctypes
    if ctypes.sizeof(ctypes.c_void_p) != 8:                      # el desplazamiento solo está verificado en 64 bits
        return None
    try:
        ntdll = ctypes.WinDLL("ntdll")
    except (AttributeError, OSError):
        return None
    n = ctypes.c_ulong(0)
    buf = ctypes.create_string_buffer(1 << 20)
    for _ in range(8):
        st = ntdll.NtQuerySystemInformation(5, buf, len(buf), ctypes.byref(n)) & 0xFFFFFFFF
        if st == 0xC0000004:                                      # STATUS_INFO_LENGTH_MISMATCH: la tabla creció
            buf = ctypes.create_string_buffer(n.value + (1 << 16))
            continue
        if st != 0:
            return None
        break
    else:
        return None
    off = 0
    while True:
        if off + 0x88 > len(buf):
            return None
        siguiente = ctypes.c_ulong.from_buffer(buf, off).value
        if ctypes.c_size_t.from_buffer(buf, off + 0x50).value == pid:      # UniqueProcessId
            duros = ctypes.c_ulong.from_buffer(buf, off + 0x10).value      # HardFaultCount
            todos = ctypes.c_ulong.from_buffer(buf, off + 0x80).value      # VM_COUNTERS.PageFaultCount
            return duros, todos
        if not siguiente:
            return None
        off += siguiente


def escribir_sin_cache(ruta: str, mib: int) -> None:
    """Archivo NUEVO de `mib` MiB escrito sin pasar por la caché de Windows (para que leerlo obligue a ir al disco)."""
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateFileW.restype = wintypes.HANDLE
    k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
                                wintypes.DWORD, wintypes.HANDLE]
    k32.WriteFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
                              ctypes.c_void_p]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    # GENERIC_WRITE, sin compartir, CREATE_NEW, FILE_FLAG_NO_BUFFERING | FILE_FLAG_WRITE_THROUGH
    h = k32.CreateFileW(ruta, 0x40000000, 0, None, 1, 0x20000000 | 0x80000000, None)
    if h in (None, wintypes.HANDLE(-1).value):
        raise OSError(ctypes.get_last_error(), "CreateFileW")
    bloque = mmap.mmap(-1, 1 << 20)                               # memoria alineada a página, como exige NO_BUFFERING
    bloque.write(os.urandom(1 << 20))
    buf = (ctypes.c_char * (1 << 20)).from_buffer(bloque)
    escritos = wintypes.DWORD()
    try:
        for _ in range(mib):
            if not k32.WriteFile(h, buf, 1 << 20, ctypes.byref(escritos), None) or escritos.value != 1 << 20:
                raise OSError(ctypes.get_last_error(), "WriteFile")
    finally:
        del buf
        k32.CloseHandle(h)
        bloque.close()


def leer_con_mmap(ruta: str) -> None:
    with open(ruta, "rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as m:
        for i in range(0, len(m), 4096):
            m[i]


def sonda(carpeta, mib: int = MIB_SONDA, contadores=contadores_fallos, escribir=escribir_sin_cache,
          leer=leer_con_mmap) -> dict:
    """Autocomprobación: ¿distingue el contador, AHORA y en este sistema, una lectura que va al disco de una que no?
    {ok, fria, caliente, motivo, mib, segundos}. `ok` SOLO si fría > 0 y caliente == 0. Nunca lanza."""
    res = {"ok": False, "fria": None, "caliente": None, "motivo": None, "mib": mib, "segundos": None}
    t0 = time.monotonic()
    ruta = os.path.join(str(carpeta), f"eq3_sonda_majflt_{os.getpid()}_{time.monotonic_ns()}.bin")
    pid = os.getpid()
    try:
        escribir(ruta, mib)
        try:
            c0 = contadores(pid)
            leer(ruta)
            c1 = contadores(pid)
            leer(ruta)
            c2 = contadores(pid)
        finally:
            try:
                os.remove(ruta)
            except OSError:
                pass
        if not (c0 and c1 and c2):
            res["motivo"] = "contador_no_disponible"
        else:
            res["fria"], res["caliente"] = c1[0] - c0[0], c2[0] - c1[0]
            if res["fria"] <= 0:
                res["motivo"] = "lectura_fria_sin_fallos_duros"
            elif res["caliente"] != 0:
                res["motivo"] = "lectura_caliente_con_fallos_duros"
            else:
                res["ok"] = True
    except Exception as e:                                        # la sonda nunca rompe la sesión: sin sonda, sin dato
        res["motivo"] = f"sonda_fallida:{type(e).__name__}"
    res["segundos"] = round(time.monotonic() - t0, 2)
    return res


def con_majflt(abrir, contadores=contadores_fallos):
    """`open` que, SOLO en lectura de texto y SOLO para «/proc/<pid>/stat», devuelve una línea con el formato de Linux
    en la que `majflt` = HardFaultCount y `minflt` = PageFaultCount − HardFaultCount. Si el contador no se puede leer,
    abre la ruta real (que no existe): el dato queda AUSENTE, nunca a cero."""
    def abrir_stat(file, mode="r", *resto, **kw):
        if isinstance(file, (str, os.PathLike)) and "r" in mode and "b" not in mode and not any(c in mode for c in "wax+"):
            m = _PROC_STAT.match(os.fspath(file).replace("\\", "/"))
            if m:
                c = contadores(int(m.group(1)))
                if c is not None and c[1] >= c[0] >= 0:
                    duros, todos = c
                    # pid (comm) estado ppid pgrp sesión tty tpgid flags minflt cminflt majflt cmajflt
                    return io.StringIO(f"{m.group(1)} (windows) R 0 0 0 0 0 0 {todos - duros} 0 {duros} 0\n")
        return abrir(file, mode, *resto, **kw)
    abrir_stat.__wrapped__ = abrir
    abrir_stat.es_majflt = True
    return abrir_stat


def _instalado() -> bool:
    f = builtins.open
    while f is not None:
        if getattr(f, "es_majflt", False):
            return True
        f = getattr(f, "__wrapped__", None)
    return False


def activar(carpeta, sondear=sonda) -> dict:
    """Ejecuta la sonda y, SOLO si la supera, empieza a servir el contador en este proceso. Devuelve
    {activo, etiqueta, sonda}. Si la sonda falla no instala nada (fallo cerrado). Solo en Windows."""
    if os.name != "nt":
        return {"activo": False, "etiqueta": None, "sonda": None, "motivo": "no_es_windows (se usa /proc real)"}
    s = sondear(carpeta)
    ESTADO.update(sonda=s)
    if s.get("ok") is True:
        if not _instalado():
            builtins.open = io.open = con_majflt(io.open)
        ESTADO["activo"] = True
    return {"activo": ESTADO["activo"], "etiqueta": ETIQUETA if ESTADO["activo"] else None, "sonda": s}


def desactivar() -> None:
    """Deja de servir el contador (para las pruebas): quita el envoltorio si es el más externo."""
    if getattr(builtins.open, "es_majflt", False):
        builtins.open = io.open = builtins.open.__wrapped__
    ESTADO.update(activo=False, sonda=None)
