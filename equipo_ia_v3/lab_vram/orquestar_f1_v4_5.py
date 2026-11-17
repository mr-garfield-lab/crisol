"""Laboratorio: encadena las PUERTAS de V4.5 y, si pasan, la F1 completa, respetando el uso del PC. No cambia V4.5.

    python -B -X utf8 lab_vram/orquestar_f1_v4_5.py EXTERNOS CARPETA_BASE [--ventanas 20:30,22:30-06:00]

- Ventana 1: desde ahora hasta las 20:30. Ventana 2: de 22:30 a 06:00 (orden del usuario del 2026-11-12). Si a las
  22:30 el PC está en uso, no vuelve a mirar hasta las 23:30 y desde ahí sondea como siempre.
- Dentro de una ventana, espera a que NO haya persona (`persona()` de V4.5, que falla cerrado) y lanza las puertas en
  una carpeta nueva (CARPETA_BASE/puertasN). Las puertas, a su vez, vuelven a comprobar todo.
- Si las puertas fallan SOLO porque apareció una persona (G6 y las de Qwen sin ejecutar) se reintenta, como mucho
  `MAX_INTENTOS` veces en total; cualquier otro fallo detiene el orquestador SIN lanzar F1.
- Si todas pasan, lanza `comparar` (F1, 90 ejecuciones) con esas puertas. No reintenta una F1 abortada.
- Todo queda en CARPETA_BASE/orquestador.jsonl. Para pararlo: crear CARPETA_BASE/STOP_ORQUESTADOR (y, durante F1, el
  STOP de V4.5 en la carpeta de F1).
"""
import json
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
from eq3 import evaluar_f1_vram_exp_v4_5 as V  # noqa: E402

MAX_INTENTOS = 4
SONDEO_S = 120
DEPENDIENTES = {"G3", "G4", "G8", "G9", "G12", "G14"}       # las de Qwen: no se ejecutan si G6 falla
MODULO = "eq3/evaluar_f1_vram_exp_v4_5.py"


def ventanas(ahora: datetime):
    hoy = ahora.date()
    v1 = (ahora, datetime.combine(hoy, datetime.strptime("20:30", "%H:%M").time()))
    ini2 = datetime.combine(hoy, datetime.strptime("22:30", "%H:%M").time())
    return [v for v in (v1, (max(ini2, ahora), ini2 + timedelta(hours=7, minutes=30))) if v[1] > v[0]]


def solo_por_persona(p: dict) -> bool:
    malas = {g for g in ("G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9", "G10", "G11", "G12", "G13", "G14")
             if not (p.get(g) or {}).get("ok")}
    return "G6" in malas and malas <= {"G6"} | DEPENDIENTES and bool((p.get("G6") or {}).get("persona", {}).get("hay")) \
        and all(str((p.get(g) or {}).get("motivo", "")).startswith("no se ejecuta") for g in malas - {"G6"})


def main(externos: str, base: str) -> int:
    base = Path(base)
    base.mkdir(parents=True, exist_ok=True)
    reg = base / "orquestador.jsonl"

    def anotar(**k):
        with reg.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"t": datetime.now().strftime("%Y-%m-%dT%H:%M:%S")} | k, ensure_ascii=False,
                               default=str) + "\n")
    parar = lambda: (base / "STOP_ORQUESTADOR").exists()
    intentos = 0
    anotar(evento="inicio", ventanas=[(a.strftime("%H:%M"), b.strftime("%d %H:%M")) for a, b in ventanas(datetime.now())])
    for ini, fin in ventanas(datetime.now()):
        while datetime.now() < ini:
            if parar():
                anotar(evento="stop_orquestador")
                return 3
            time.sleep(SONDEO_S)
        anotar(evento="ventana", desde=ini, hasta=fin)
        reintento = ini.replace(hour=23, minute=30, second=0, microsecond=0) if ini.hour == 22 else None
        while datetime.now() < fin and intentos < MAX_INTENTOS:
            if parar():
                anotar(evento="stop_orquestador")
                return 3
            if V.persona()["hay"]:
                if reintento and datetime.now() < reintento:      # ocupado a las 22:30: no sondear hasta las 23:30
                    anotar(evento="pc_en_uso", espera_hasta=reintento)
                    while datetime.now() < reintento:
                        if parar():
                            anotar(evento="stop_orquestador")
                            return 3
                        time.sleep(SONDEO_S)
                    reintento = None
                    continue
                time.sleep(SONDEO_S)
                continue
            intentos += 1
            carpeta = base / f"puertas{intentos + 1}"            # puertas1 ya existe (16:35, G6 por persona)
            anotar(evento="puertas_inicio", intento=intentos, carpeta=carpeta)
            subprocess.run([sys.executable, "-B", "-X", "utf8", MODULO, "puertas", externos, str(carpeta)], cwd=RAIZ)
            pj = carpeta / "puertas.json"
            p = json.loads(pj.read_text(encoding="utf-8")) if pj.is_file() else {}
            resumen = {g: (p.get(g) or {}).get("ok") for g in p if g.startswith("G")}
            anotar(evento="puertas_fin", intento=intentos, ok=p.get("ok"), puertas=resumen)
            if p.get("ok"):
                f1 = base / "f1_comparacion1"
                anotar(evento="f1_inicio", carpeta=f1)
                r = subprocess.run([sys.executable, "-B", "-X", "utf8", MODULO, "comparar", externos, str(f1),
                                    "--puertas", str(pj)], cwd=RAIZ)
                anotar(evento="f1_fin", rc=r.returncode)
                return r.returncode
            if not solo_por_persona(p):
                anotar(evento="detenido", motivo="una puerta falló por algo distinto de una persona: NO se lanza F1")
                return 2
        if intentos >= MAX_INTENTOS:
            break
    anotar(evento="sin_lanzar", motivo=f"sin PC libre en las ventanas o {intentos} intentos agotados")
    return 4


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
