"""Prueba REAL y corta del guardián de Wallpaper Engine (sin modelo, sin GPU).

    python -B -X utf8 lab_vram/probar_guardian.py SALIDA_NUEVA

1. «muerte»: un proceso hijo PROPIO hace de Equipo IA; se detiene el fondo, se escribe la marca y se lanza el guardián;
   se termina el hijo (como un cierre inesperado) y se comprueba que el guardián reanuda el fondo y se retira.
2. «normal»: igual, pero Equipo IA restaura por sí mismo y retira la marca: el guardián debe irse sin actuar.
Antes de cada paso se comprueba que no hay nadie usando el PC; al final, el fondo se restaura pase lo que pase.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
from lab_vram import wallpaper as W  # noqa: E402


def guardianes():
    s = W._ps("Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe'\" | Where-Object { $_.CommandLine -like "
              "'*guardian_fondo.py*' } | Select-Object -ExpandProperty ProcessId")
    return [int(x) for x in s.split() if x.isdigit()]


def caso(nombre, salida, c, morir):
    out = {"caso": nombre}
    h = W.nadie()
    if not h["ok"]:
        return out | {"omitido": h["motivos"]}
    equipo = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"])
    marca = salida / f"fondo_detenido_{nombre}.marca"
    out["stop"] = c.control("stop")
    marca.write_text(str(equipo.pid), encoding="utf-8")
    out["vram_detenido"] = W.vram_por_proceso({p["pid"] for p in W.procesos()})
    out["guardian"] = W.lanzar_guardian(equipo.pid, marca, c._exe())
    time.sleep(3)
    out["guardianes_vivos_al_empezar"] = guardianes()
    t0 = time.monotonic()
    if morir:
        equipo.terminate()                                    # el proceso PROPIO que hace de Equipo IA
        equipo.wait(10)
    else:
        out["restaurado_por_equipo"] = c.control("play")
        marca.unlink()
        equipo.terminate()
        equipo.wait(10)
    while time.monotonic() - t0 < 30 and (marca.exists() or guardianes()):
        time.sleep(1)
    time.sleep(4)
    out.update(segundos=round(time.monotonic() - t0, 1), marca_existe=marca.exists(), guardianes_despues=guardianes(),
               vram_despues=W.vram_por_proceso({p["pid"] for p in W.procesos()}), procesos=W.procesos(),
               registro=(Path(str(marca) + ".log").read_text(encoding="utf-8")
                         if Path(str(marca) + ".log").exists() else None))
    c.estado = "normal"                                       # el guardián (o Equipo IA) ya mandó «play»
    return out


def main():
    salida = Path(sys.argv[1])
    if "vram_exp_v4" not in str(salida).lower():
        raise SystemExit("la salida debe estar en una carpeta con «vram_exp_v4»")
    salida.mkdir(parents=True)
    c = W.Control()
    c.capturar()
    res = {"inicio": time.strftime("%Y-%m-%dT%H:%M:%S"), "inicial": c.inicial}
    try:
        res["muerte"] = caso("muerte", salida, c, True)
        res["normal"] = caso("normal", salida, c, False)
    finally:
        c.estado = "detenido"                                 # por si acaso: «play» es inocuo si ya se reproduce
        res["restauracion_final"] = c.restaurar()
        res["final"] = W.medir(4.0)
        (salida / "guardian.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str),
                                              encoding="utf-8")
    for k in ("muerte", "normal"):
        r = res[k]
        print(k, {x: r.get(x) for x in ("stop", "vram_detenido", "segundos", "marca_existe", "guardianes_despues",
                                        "vram_despues", "omitido")})
        print("  ", (r.get("registro") or "").strip().replace("\n", " | "))
    print("final", res["restauracion_final"], res["final"]["vram_wallpaper_MiB"], res["final"]["uso_gpu_pct"])


if __name__ == "__main__":
    main()
