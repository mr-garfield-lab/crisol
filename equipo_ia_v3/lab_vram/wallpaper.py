"""Equipo IA V3.1 — LABORATORIO: control REVERSIBLE de Wallpaper Engine (autorizado SOLO para esta aplicación).

    python -B -X utf8 lab_vram/wallpaper.py experimento SALIDA_NUEVA [--sin-cierre]
    python -B -X utf8 lab_vram/wallpaper.py estado

Qué hace y qué no:
- Usa la interfaz OFICIAL de línea de órdenes (`wallpaper64.exe -control pause|stop|play`): la segunda instancia solo
  entrega la orden a la que ya está abierta y termina (se comprueba que no queda ninguna duplicada).
- Cierre: SOLO ordenado (WM_CLOSE con `taskkill /PID` SIN `/F`). Si no se cierra así, NO se fuerza: se registra.
- Restauración: si estaba abierto y se cerró, se vuelve a abrir con su MISMA orden (`-silent`) mediante WMI
  (Win32_Process.Create), para que no dependa de este proceso; si estaba en reproducción, `-control play`.
- Nunca toca la configuración de Wallpaper Engine, ni otras aplicaciones, ni nada global de Windows.
- Antes de CADA paso comprueba que nadie usa el PC; si aparece alguien, restaura y se detiene.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
from eq3 import evaluar_f1_vram_exp as X  # noqa: E402

NOMBRES = ("wallpaper64.exe", "wallpaper32.exe")
INACTIVIDAD_MIN_S = 600


def _ps(orden: str, timeout=30) -> str:
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", orden], capture_output=True,
                       text=True, timeout=timeout)
    return r.stdout.strip()


def procesos() -> list:
    """[{pid, nombre, ruta, orden, sesion}] de Wallpaper Engine (solo consulta)."""
    filtro = " or ".join(f"Name='{n}'" for n in NOMBRES)
    s = _ps(f"Get-CimInstance Win32_Process -Filter \"{filtro}\" | Select-Object ProcessId,Name,ExecutablePath,"
            "CommandLine,SessionId | ConvertTo-Json -Compress")
    if not s:
        return []
    d = json.loads(s)
    d = d if isinstance(d, list) else [d]
    return [{"pid": p["ProcessId"], "nombre": p["Name"], "ruta": p["ExecutablePath"], "orden": p["CommandLine"],
             "sesion": p["SessionId"]} for p in d]


def vram_por_proceso(pids) -> dict:
    """MiB dedicados de la GPU por pid (contadores de Windows «GPU Process Memory»)."""
    if not pids:
        return {}
    s = _ps("$c=(Get-Counter '\\GPU Process Memory(*)\\Dedicated Usage').CounterSamples; $c | ForEach-Object { "
            "if ($_.InstanceName -match 'pid_(\\d+)_') { \"$($matches[1]) $($_.CookedValue)\" } }")
    out = {}
    for linea in s.splitlines():
        pid, _, v = linea.partition(" ")
        if pid.isdigit() and int(pid) in pids:
            out[int(pid)] = round(out.get(int(pid), 0) + float(v) / 2**20)
    return out


def medir(segundos=8.0, intervalo=2.0, gpu=None, ram=None) -> dict:
    """VRAM total, libre, uso de GPU, RAM disponible, estado de notificación y VRAM propia de Wallpaper Engine."""
    from lab_vram import banco_vram as B
    gpu, ram = gpu or B.gpu, ram or B.memoria_sistema
    v, u = [], []
    for k in range(max(1, int(segundos / intervalo))):
        if k:
            time.sleep(intervalo)
        g = gpu()
        if g:
            v.append(g["vram_MiB"])
            u.append(g["uso_pct"])
    ps = procesos()
    return {"vram_total_MiB": round(sum(v) / len(v)) if v else None, "vram_min_max": [min(v), max(v)] if v else None,
            "vram_libre_MiB": 8192 - round(sum(v) / len(v)) if v else None,
            "uso_gpu_pct": round(sum(u) / len(u)) if u else None, "uso_gpu_min_max": [min(u), max(u)] if u else None,
            "ram_disponible_MiB": ram()["disponible_MiB"], "notificacion": X.notificacion(),
            "procesos": ps, "vram_wallpaper_MiB": vram_por_proceso({p["pid"] for p in ps})}


def nadie(act=X.actividad, inactividad_min=INACTIVIDAD_MIN_S) -> dict:
    """Actividad HUMANA (independiente de la carga de la GPU): entrada reciente, otra sesión, pantalla completa D3D o
    presentación. «aplicacion_ocupada» (la provoca el propio fondo animado) NO cuenta como persona."""
    a = act()
    motivos = [m for m in a["motivos"] if m not in ("aplicacion_ocupada", "notificacion_no_medible")]
    if a["inactividad_s"] is None or a["inactividad_s"] < inactividad_min:
        motivos.append(f"entrada_reciente_{a['inactividad_s']}")
    return {"ok": not motivos, "motivos": motivos, "inactividad_s": a["inactividad_s"]}


class Control:
    """Pausa / detención / cierre ordenado y restauración. Todo lo hecho queda en `self.registro`."""

    def __init__(self, ejecutar=subprocess.run, listar=procesos, crear=None, reloj=time.monotonic, dormir=time.sleep):
        self.ejecutar, self.listar, self.reloj, self.dormir = ejecutar, listar, reloj, dormir
        self.crear = crear or self._crear_wmi
        self.registro, self.inicial = [], None
        self.estado = "normal"                       # normal | pausado | detenido | cerrado

    def anotar(self, **k):
        self.registro.append({"t": time.strftime("%H:%M:%S")} | k)

    def capturar(self) -> dict:
        ps = self.listar()
        self.inicial = {"procesos": ps, "abierto": bool(ps)}
        self.anotar(paso="estado_inicial", procesos=ps)
        return self.inicial

    def _exe(self):
        return (self.inicial or {}).get("procesos", [{}])[0].get("ruta") if (self.inicial or {}).get("procesos") \
            else None

    def control(self, orden: str) -> bool:
        exe = self._exe()
        if not exe:
            self.anotar(paso=f"control_{orden}", ok=False, motivo="no estaba abierto")
            return False
        antes = {p["pid"] for p in self.listar()}
        r = self.ejecutar([exe, "-control", orden], capture_output=True, text=True, timeout=30)
        self.dormir(1.0)
        despues = {p["pid"] for p in self.listar()}
        duplicados = sorted(despues - antes)
        self.anotar(paso=f"control_{orden}", ok=r.returncode == 0 and not duplicados, rc=r.returncode,
                    duplicados=duplicados)
        if r.returncode == 0:
            self.estado = {"pause": "pausado", "stop": "detenido", "play": "normal"}.get(orden, self.estado)
        return r.returncode == 0 and not duplicados

    def cerrar_ordenado(self, espera_s=20) -> bool:
        """WM_CLOSE (taskkill SIN /F) a los procesos de Wallpaper Engine. No fuerza nunca."""
        ps = self.listar()
        for p in ps:
            r = self.ejecutar(["taskkill", "/PID", str(p["pid"])], capture_output=True, text=True, timeout=30)
            self.anotar(paso="cerrar_ordenado", pid=p["pid"], rc=r.returncode, salida=(r.stdout + r.stderr)[-300:])
        t0 = self.reloj()
        while self.reloj() - t0 < espera_s and self.listar():
            self.dormir(1.0)
        cerrado = not self.listar()
        self.anotar(paso="cerrar_ordenado_resultado", cerrado=cerrado, segundos=round(self.reloj() - t0, 1))
        if cerrado:
            self.estado = "cerrado"
        return cerrado

    def _crear_wmi(self, orden: str, carpeta: str) -> dict:
        o = orden.replace("'", "''")
        c = carpeta.replace("'", "''")
        s = _ps(f"$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{{CommandLine='{o}';"
                f"CurrentDirectory='{c}'}}; \"$($r.ReturnValue) $($r.ProcessId)\"")
        rv, _, pid = s.partition(" ")
        return {"rc": int(rv) if rv.lstrip("-").isdigit() else None, "pid": int(pid) if pid.isdigit() else None}

    def restaurar(self, espera_s=30) -> dict:
        """Deja Wallpaper Engine como estaba al capturar. Nunca abre una segunda instancia."""
        if not self.inicial or not self.inicial["abierto"]:
            self.anotar(paso="restaurar", ok=True, motivo="no estaba abierto: nada que hacer")
            return {"ok": True}
        ok = True
        if not self.listar():                                       # se cerró: volver a abrirlo con su misma orden
            p0 = self.inicial["procesos"][0]
            r = self.crear(p0["orden"], str(Path(p0["ruta"]).parent))
            t0 = self.reloj()
            while self.reloj() - t0 < espera_s and not self.listar():
                self.dormir(1.0)
            self.dormir(5.0)
            ok = bool(self.listar())
            self.anotar(paso="reabrir", ok=ok, creacion=r, procesos=self.listar())
        elif self.estado in ("pausado", "detenido"):
            ok = self.control("play")
        n = len(self.listar())
        if n > len(self.inicial["procesos"]):
            ok = False
            self.anotar(paso="restaurar", ok=False, motivo=f"hay {n} procesos (antes {len(self.inicial['procesos'])})")
        self.estado = "normal" if ok else self.estado
        self.anotar(paso="restaurado", ok=ok, procesos=self.listar())
        return {"ok": ok}


def lanzar_guardian(pid_equipo: int, marca: Path, exe: str) -> dict:
    """Lanza `guardian_fondo.py` con pythonw por WMI (fuera del árbol de procesos de Equipo IA, sin ventana)."""
    pyw = Path(sys.executable).with_name("pythonw.exe")
    guardian = Path(__file__).with_name("guardian_fondo.py")
    marca = Path(marca).resolve()                         # el guardián arranca en otra carpeta: ruta absoluta
    orden = f'"{pyw}" -B "{guardian}" --pid {pid_equipo} --marca "{marca}" --exe "{exe}"'
    o, c = orden.replace("'", "''"), str(guardian.parent).replace("'", "''")
    s = _ps(f"$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{{CommandLine='{o}';"
            f"CurrentDirectory='{c}'}}; \"$($r.ReturnValue) $($r.ProcessId)\"")
    rv, _, p = s.partition(" ")
    return {"rc": int(rv) if rv.lstrip("-").isdigit() else None, "pid": int(p) if p.isdigit() else None,
            "orden": orden}


def experimento(salida: Path, sin_cierre=False) -> dict:
    salida.mkdir(parents=True)
    res = {"inicio": time.strftime("%Y-%m-%dT%H:%M:%S"), "estados": {}}
    guardar = lambda: (salida / "wallpaper.json").write_text(json.dumps(res, ensure_ascii=False, indent=1,
                                                                        default=str), encoding="utf-8")
    h = nadie()
    res["humano_inicial"] = h
    if not h["ok"]:
        res["omitido"] = f"hay actividad humana: {h['motivos']}"
        guardar()
        return res
    c = Control()
    c.capturar()
    try:
        res["estados"]["A_normal"] = medir()
        pasos = [("B_pausado", lambda: c.control("pause")), ("A2_reanudado", lambda: c.control("play")),
                 ("B2_detenido", lambda: c.control("stop")), ("A3_reanudado", lambda: c.control("play"))]
        if not sin_cierre:
            pasos += [("C_cerrado", c.cerrar_ordenado), ("A4_reabierto", lambda: c.restaurar()["ok"])]
        for nombre, accion in pasos:
            h = nadie()
            if not h["ok"]:
                res["interrumpido"] = f"actividad humana antes de {nombre}: {h['motivos']}"
                break
            ok = accion()
            time.sleep(3.0)
            res["estados"][nombre] = medir() | {"accion_ok": ok}
            guardar()
            if not ok and nombre == "C_cerrado":
                res["cierre_ordenado"] = "no disponible: no se fuerza"
                break
    finally:
        res["restauracion"] = c.restaurar()
        res["estado_final"] = medir(4.0)
        res["registro"] = c.registro
        res["fin"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        guardar()
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("orden", choices=("experimento", "estado"))
    ap.add_argument("salida", nargs="?", type=Path)
    ap.add_argument("--sin-cierre", action="store_true")
    a = ap.parse_args(argv)
    if a.orden == "estado":
        print(json.dumps(medir(4.0) | {"humano": nadie()}, ensure_ascii=False, default=str))
        return 0
    if "lab_vram" not in str(a.salida).lower():
        print("la salida debe estar en una carpeta con «lab_vram» en el nombre")
        return 2
    r = experimento(a.salida, a.sin_cierre)
    resumen = {k: {c: v.get(c) for c in ("vram_total_MiB", "uso_gpu_pct", "notificacion", "vram_wallpaper_MiB",
                                          "accion_ok")} for k, v in r["estados"].items()}
    print(json.dumps({"estados": resumen, "restauracion": r.get("restauracion"), "interrumpido": r.get("interrumpido"),
                      "cierre": r.get("cierre_ordenado"), "omitido": r.get("omitido")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
