"""Auxiliar de test_eq3_servidor_pc.py y test_eq3_majflt.py (no es un módulo de pruebas: unittest no lo descubre).

    python -B [eq3/lanzador_eq2.py] pruebas/aux_servidor_pc.py ESCENARIO CARPETA_TMP

Ejecuta, en un proceso propio, el ciclo de vida REAL de V2-F.1 (`BackendLlama` + `ServidorLlama`) construido por
`eq3.servidor_pc.crear_backend`, contra el servidor FALSO de V2-F.1 (`sistema/tests/fake_llama_server.py`): procesos,
sockets y archivos reales; lo único simulado es el modelo. Imprime un JSON en la última línea.
"""
import json
import socket
import sys
import threading
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
from eq3 import majflt_windows, servidor_pc  # noqa: E402

servidor_pc.preparar_proceso()
from eq2 import config, inferencia, rutas, servidor  # noqa: E402

FAKE = RAIZ / "sistema" / "tests" / "fake_llama_server.py"
AYUDA = "--host --port --ctx-size --threads --parallel --no-ui"


def externos(t: Path) -> tuple:
    """Carpeta de externos de PRUEBA (archivos mínimos) y su registro."""
    ext = t / "ext"
    (ext / "llama_x").mkdir(parents=True)
    (ext / "modelos").mkdir()
    archivos = {"llama-server.exe": b"binario de prueba", "llama.dll": b"biblioteca de prueba"}
    for n, b in archivos.items():
        (ext / "llama_x" / n).write_bytes(b)
    modelo = b"GGUF" + bytes(4096)
    (ext / "modelos" / "m.gguf").write_bytes(modelo)
    import hashlib
    reg = {"llama": {"carpeta": "llama_x", "ejecutable": "llama-server.exe", "version": "prueba",
                     "archivos": {n: {"sha256": hashlib.sha256(b).hexdigest(), "bytes": len(b)}
                                  for n, b in archivos.items()}},
           "modelo": {"archivo": "modelos/m.gguf", "sha256": hashlib.sha256(modelo).hexdigest(), "bytes": len(modelo)}}
    return ext, reg


def puerto_aleatorio() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def main(escenario: str, tmp: str) -> dict:
    t = Path(tmp)
    config.MIN_MODELO_BYTES = 1
    ext, reg = externos(t)
    ver = servidor_pc.verificar_externos(ext, reg)
    raiz = t / "equipo_f2"
    lab = rutas.Laboratorio(raiz, raiz / "lab")
    lab.crear_base()
    lab.crear_dir("runs", "R1")
    puerto = puerto_aleatorio()
    pausa = 30.0 if escenario == "stop" else 0.0
    comando = [sys.executable, "-B", str(FAKE), "--fake-modo", "normal", "--fake-carga", "0.2",
               "--fake-pausa", str(pausa)]
    detector = {"llama_activo": lambda: "4242",
                "sin_lista": lambda: servidor_pc.detector_llama(listar=lambda: None)}.get(escenario, lambda: None)
    out = {"escenario": escenario, "verificacion_ok": ver["ok"]}
    if escenario == "externos_alterados":
        with open(ver["ejecutable"], "ab") as f:                 # cambia DESPUÉS de verificar
            f.write(b"!")
    if escenario == "majflt_activo":
        out["majflt"] = majflt_windows.activar(t)                 # sonda REAL
    elif escenario == "majflt_sonda_fallida":
        out["majflt"] = majflt_windows.activar(t, sondear=lambda c: {"ok": False, "motivo": "lectura_caliente_con_fallos_duros"})
    try:
        be = servidor_pc.crear_backend(
            ver, puerto=puerto, comando=comando, detector=detector, intervalo_monitor=0.05, espera_monitor=1,
            srv_kw=dict(ayuda_fn=lambda: AYUDA, gracia_term=3, gracia_kill=3, max_carga_s=20, sondeo_s=0.05))
    except servidor_pc.ExternosNoVerificados as e:
        return dict(out, error="ExternosNoVerificados", detalle=str(e))
    out["perfil"] = {"modelo": str(config.ruta_modelo()), "hilos": config.HILOS}
    bandera = threading.Event()
    if escenario == "stop":
        def vigilar():
            log = raiz / "lab" / "runs" / "R1" / "server.log"
            fin = time.monotonic() + 30
            while time.monotonic() < fin:
                try:
                    if any(l.startswith("REQ ") for l in log.read_text(encoding="utf-8", errors="replace").splitlines()):
                        bandera.set()
                        return
                except OSError:
                    pass
                time.sleep(0.01)
        threading.Thread(target=vigilar, daemon=True).start()
    try:
        try:
            be.iniciar({"lab": lab, "run_id": "R1", "parar": lambda: "stop_usuario" if bandera.is_set() else None})
            out["argv"] = [a for a in be.srv.argv[len(comando):]]
            t0 = time.monotonic()
            be.completar([{"role": "user", "content": "hola"}], 50, 60)
            p = be.peticiones[-1]
            out["peticion"] = {k: p.get(k) for k in ("concluyente", "motivos_no_concluyente", "criticas_ausentes",
                                                      "delta_fallos")}
        except inferencia.ErrorInferencia as e:
            out["error"] = e.motivo
            out["segundos_hasta_error"] = round(time.monotonic() - t0, 2) if "t0" in dir() else None
    finally:
        out["lanzado"] = be.srv.proc is not None
        det = be.detener()
        out["detencion"] = {"limpio": det["limpio"], "problemas": det["problemas"],
                            "servidor": det["pasos"].get("servidor"), "puerto_liberado": det["pasos"].get("puerto_liberado")}
        out["proceso_terminado"] = be.srv.proc is None or be.srv.proc.poll() is not None
        out["puerto_libre_despues"] = servidor.puerto_libre(puerto)
    return out


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1], sys.argv[2]), ensure_ascii=False, default=str))
