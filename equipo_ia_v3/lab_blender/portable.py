"""Banco de Blender PORTABLE: el mismo bucle (cerebro → filtro → Blender → verificador → corrección) contra cualquier
servidor local compatible con la API de OpenAI (llama.cpp `llama-server`, Ollama, LM Studio…). Solo biblioteca estándar.

    python -B -X utf8 lab_blender/portable.py EVIDENCIA SALIDA_BLENDER --url http://localhost:8080/v1 --modelo NOMBRE
                                              [--tareas T01 T02 …] [--reanudar] [--videos]

- EVIDENCIA: carpeta donde quedan `peticiones.jsonl`, `INFORME.md` y `analisis.json`.
- SALIDA_BLENDER: carpeta de trabajo de Blender (una subcarpeta por intento, con el script, los hechos y el .blend).
- Para parar: crea un archivo `STOP` dentro de EVIDENCIA. Con `--reanudar` sigue donde se quedó sin repetir intentos.
- `--videos`: al terminar, renderiza el último script de cada tarea (necesita una GPU que Blender pueda usar).

No envía nada fuera: solo habla con la URL que le des (pensado para un servidor en tu propia máquina) y no usa claves.
A diferencia de `banco.py ejecutar`, aquí NO hay vigilancia de temperatura, VRAM ni de si alguien usa el PC.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

AQUI = Path(__file__).resolve().parent
if str(AQUI) not in sys.path:
    sys.path.insert(0, str(AQUI))
import banco as B  # noqa: E402
import ejecutor as EJ  # noqa: E402
import tareas as T  # noqa: E402

ESPERA_S = 600


def cliente(url: str, modelo: str, clave: str | None = None, espera_s: float = ESPERA_S):
    """Devuelve completar(mensajes, max_tokens) -> (texto, tokens generados, motivo de fin)."""
    destino = url.rstrip("/") + "/chat/completions"

    def completar(mensajes, max_tokens):
        cuerpo = json.dumps({"model": modelo, "messages": mensajes, "max_tokens": max_tokens, "temperature": 0,
                             "stream": False}).encode("utf-8")
        cabeceras = {"Content-Type": "application/json"}
        if clave:
            cabeceras["Authorization"] = f"Bearer {clave}"
        with urllib.request.urlopen(urllib.request.Request(destino, data=cuerpo, headers=cabeceras), timeout=espera_s) as r:
            d = json.loads(r.read().decode("utf-8"))
        op = d["choices"][0]
        return (op.get("message", {}).get("content") or "", (d.get("usage") or {}).get("completion_tokens"),
                op.get("finish_reason"))
    return completar


def correr(evidencia: Path, salida_blender: Path, url: str, modelo: str, ids=None, reanudar=False, clave=None,
           hacer_videos=False) -> dict:
    evidencia, salida_blender = Path(evidencia), Path(salida_blender)
    ids = list(ids or T.TAREAS)
    if not EJ.blender_exe():
        raise SystemExit("no encuentro Blender: define BLENDER_EXE con la ruta del ejecutable")
    if evidencia.exists() and not reanudar:
        raise SystemExit(f"{evidencia} ya existe: usa --reanudar para continuar, o elige otra carpeta")
    evidencia.mkdir(parents=True, exist_ok=True)
    res = {"inicio": time.strftime("%Y-%m-%dT%H:%M:%S"), "modo": "REAL", "modelo": modelo, "url": url, "tareas": ids,
           "intentos": B.INTENTOS, "tokens": B.TOKENS, "blender": str(EJ.blender_exe())}
    if any(T.TAREAS[i].get("base") and not B.base_de(T.TAREAS[i], salida_blender).is_file() for i in ids):
        v = B.validar(salida_blender)                        # crea los .blend de partida y comprueba las tareas
        res["validacion"] = {"ok": v["ok"], "fallos": v["fallos"]}
        if not v["ok"]:
            raise SystemExit(f"la validación de las tareas falla en este Blender: {v['fallos']}")
    try:
        res["fin_del_bucle"] = B.correr_modelo(modelo, ids, evidencia, salida_blender, cliente(url, modelo, clave),
                                               parar=lambda: (evidencia / "STOP").exists())
    except (urllib.error.URLError, TimeoutError, KeyError, ValueError) as e:
        res["abortada"] = f"{type(e).__name__}: {e}"
    res["fin"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    B.escribir(evidencia / "banco.json", res)
    B.informe(evidencia)
    if hacer_videos and not res.get("abortada"):
        res["videos"] = B.videos(evidencia, salida_blender)
        B.escribir(evidencia / "banco.json", res)
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("evidencia")
    ap.add_argument("salida_blender")
    ap.add_argument("--url", default="http://localhost:8080/v1", help="base de la API (termina en /v1)")
    ap.add_argument("--modelo", required=True, help="nombre del modelo tal como lo llama el servidor")
    ap.add_argument("--clave", help="solo si tu servidor local pide una (no se guarda)")
    ap.add_argument("--tareas", nargs="+")
    ap.add_argument("--reanudar", action="store_true")
    ap.add_argument("--videos", action="store_true")
    a = ap.parse_args(argv)
    r = correr(Path(a.evidencia), Path(a.salida_blender), a.url, a.modelo, a.tareas, a.reanudar, a.clave, a.videos)
    print((Path(a.evidencia) / "INFORME.md").read_text(encoding="utf-8"))
    if r.get("abortada"):
        print("ABORTADA:", r["abortada"])
    return 1 if r.get("abortada") else 0


if __name__ == "__main__":
    sys.exit(main())
