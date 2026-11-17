#!/usr/bin/env python3
"""banco.py — V2-F: BANCO COMPARATIVO de un agente frente al equipo (mismas tareas, oráculos ocultos).

  python3 -B banco.py lista                                   tareas del banco (sin ejecutar nada)
  python3 -B banco.py simular --autorizo-pruebas              modo SIMULADO (política parametrizada, sin modelo)
        [--semilla N ...] [--solo-semillas] [--modos individual equipo_debate ...] [--tareas mediana dedup ...]
        [--correlacion 0.5] [--p-acierto 0.5] [--parametro p_reparar=0.2 ...]
  python3 -B banco.py real --autorizo-pruebas --iniciar-servidor-real   con Qwen REAL (un llama-server en 127.0.0.1)
        [--modos ...] [--tareas ...] [--ctx 1024|2048] [--memoria] [--puerto 8089]
  python3 -B banco.py comparar A/informe.json B/informe.json  compara dos informes (solo lectura)

Las soluciones finales se EJECUTAN contra los oráculos ocultos con el ejecutor restringido: por eso hace falta
--autorizo-pruebas (sin él no se puede medir la calidad y no se ejecuta nada). En modo simulado el código ejecutado
es el de bancos/capacidades_v1/simulacion.json y los archivos de prueba que escribe el controlador.
Resultados en $TMPDIR/equipo_f2/lab_v2f1/banco/<id>/: informe.json, informe.md, por_ejecucion.jsonl, runs/.
STOP: crea el archivo $TMPDIR/equipo_f2/lab_v2f1/STOP (o banco/<id>/STOP) para detener entre ejecuciones.
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ / "src"))
sys.dont_write_bytecode = True

from eq2 import VERSION, banco_capacidades as B, config, rutas  # noqa: E402

CARPETA_BANCO = RAIZ / "bancos" / "capacidades_v1"
MAX_INFORME = 20 * 1024 * 1024


def _lab():
    raiz = rutas.raiz_laboratorio()
    lab = rutas.Laboratorio(raiz, raiz / config.CARPETA_ACTUAL)
    lab.crear_base()
    lab.crear_dir("banco")
    return lab


def _parada(lab, ident):
    return lambda: ("stop_usuario" if lab.existe("STOP") or lab.existe("banco", ident, "STOP") else None)


def _guardar(lab, ident, inf):
    lab.crear_exclusivo(("banco", ident, "informe.json"), json.dumps(inf, ensure_ascii=False, indent=1, default=str))
    lab.crear_exclusivo(("banco", ident, "informe.md"), B.texto_md(inf))
    return lab.ruta("banco", ident, "informe.md")


def _imprimir_resumen(inf):
    print(f"{'modo':<24}{'correctas':>10}{'calidad':>9}{'falsas':>8}{'abst.':>7}{'llam.':>7}{'tok_in':>9}"
          f"{'tok_out':>9}{'S23_s':>9}")
    for m in B.MODOS:
        d = inf["por_modo"].get(m)
        if d:
            print(f"{m:<24}{d['correctas']:>4}/{d['ejecuciones']:<5}{d['calidad_media']:>9.3f}{d['falsas_certezas']:>8}"
                  f"{d['abstenciones']:>7}{d['llamadas_media']:>7}{d['tokens_prompt']:>9}{d['tokens_gen']:>9}"
                  f"{d['proyeccion_s23_s']:>9}")
    for n in inf["notas"][:2]:
        print("NOTA:", n)


def simular(a) -> int:
    banco = B.cargar(CARPETA_BANCO)
    params = dict(banco["simulacion"]["parametros"])
    params.pop("explicacion", None)
    if a.correlacion is not None:
        params["correlacion"] = a.correlacion
    if a.p_acierto is not None:
        params["p_acierto"] = a.p_acierto
    for texto in a.parametro or []:
        k, _, v = texto.partition("=")
        if k not in params:
            sys.exit(f"parámetro desconocido: {k!r} (válidos: {', '.join(sorted(params))})")
        try:
            params[k] = float(v)
        except ValueError:
            sys.exit(f"valor no numérico para {k}: {v!r}")
    for k, v in params.items():
        if not 0.0 <= v <= 1.0:
            sys.exit(f"{k} debe estar entre 0 y 1")
    semillas = list(a.semilla or []) if a.solo_semillas else list(B.SEMILLAS_FIJAS) + [
        s for s in (a.semilla or []) if s not in B.SEMILLAS_FIJAS]
    if not semillas:
        sys.exit("--solo-semillas exige al menos una --semilla")
    lab = _lab()
    ident = "sim_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f") + f"_{os.getpid()}"
    lab.crear_dir_exclusivo("banco", ident)
    filas = []
    for s in semillas:
        crear = (lambda semilla: lambda t, modo: B.BackendGuion(B.PoliticaSimulada(
            banco["simulacion"]["tareas"][t["id"]], t, semilla, modo, params)))(s)
        bc = B.Banco(lab, ("banco", ident, f"semilla_{s}"), banco, autorizado=a.autorizo_pruebas, crear_backend=crear,
                     simulado=True, semilla=s, parametros=params, parar=_parada(lab, ident))
        filas += bc.ejecutar(a.modos or B.MODOS, a.tareas)
    inf = B.informe(banco, filas, {"simulado": True, "parametros": params, "ctx": config.CTX,
                                   "modos": a.modos or list(B.MODOS), "tareas": a.tareas or "todas"})
    ruta = _guardar(lab, ident, inf)
    _imprimir_resumen(inf)
    print("informe:", ruta)
    return 0


def real(a) -> int:
    from eq2 import backend_llama, experiencias, perfiles_contexto, servidor
    if not a.iniciar_servidor_real:
        sys.exit("el modo real exige --iniciar-servidor-real (arranca llama-server con el GGUF, solo lectura)")
    config.CTX = a.ctx
    perfiles_contexto.aplicar(perfiles_contexto.perfil_de_ctx(config.CTX))
    banco = B.cargar(CARPETA_BANCO)
    lab = _lab()
    ident = "real_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f") + f"_{os.getpid()}"
    lab.crear_dir_exclusivo("banco", ident)
    be = backend_llama.BackendLlama(servidor.ServidorLlama(a.puerto), usar_wake_lock=not a.sin_wake_lock,
                                    permitir_continuacion=True)
    memorias = {}

    def memoria_por_modo(modo):
        if not a.memoria or modo not in ("equipo_debate", "equipo_motor"):
            return None
        if modo not in memorias:
            lab_m = rutas.Laboratorio(lab.raiz, lab.ruta("banco", ident, f"memoria_{modo}"))
            lab_m.crear_base()
            memorias[modo] = experiencias.MemoriaEquipo(lab_m)
        return memorias[modo]
    filas, error = [], None
    try:
        lab_b = rutas.Laboratorio(lab.raiz, lab.ruta("banco", ident))
        lab_b.crear_dir("runs", "servidor")                    # el servidor escribe runs/servidor/server.log
        be.iniciar({"lab": lab_b, "run_id": "servidor", "parar": _parada(lab, ident)})
        bc = B.Banco(lab, ("banco", ident), banco, autorizado=a.autorizo_pruebas, crear_backend=lambda t, modo: be,
                     simulado=False, memoria_por_modo=memoria_por_modo, parar=_parada(lab, ident),
                     supervisar=be.supervisar)
        try:
            filas = bc.ejecutar(a.modos or B.MODOS, a.tareas)
        except InterruptedError as e:
            filas, error = bc.filas, f"detenido: {e}"
    finally:
        informe_srv = be.detener()
        for m in memorias.values():
            m.cerrar()
    inf = B.informe(banco, filas, {"simulado": False, "ctx": config.CTX, "modelo": "Qwen2.5-Coder-3B (llama-server local)",
                                   "modos": a.modos or list(B.MODOS), "tareas": a.tareas or "todas",
                                   "memoria": bool(a.memoria), "interrupcion": error, "servidor": informe_srv})
    ruta = _guardar(lab, ident, inf)
    _imprimir_resumen(inf)
    print("informe:", ruta)
    return 0 if error is None else 1


def _leer(ruta):
    p = Path(ruta)
    if p.is_symlink() or not p.is_file() or p.stat().st_size > MAX_INFORME:
        sys.exit(f"no es un archivo normal o es demasiado grande: {ruta}")
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="orden", required=True)
    sub.add_parser("lista")
    for nombre in ("simular", "real"):
        s = sub.add_parser(nombre)
        s.add_argument("--autorizo-pruebas", action="store_true",
                       help="autoriza ejecutar las soluciones y los casos con el ejecutor restringido (no es un sandbox)")
        s.add_argument("--modos", nargs="+", choices=B.MODOS)
        s.add_argument("--tareas", nargs="+")
        if nombre == "simular":
            s.add_argument("--semilla", type=int, action="append")
            s.add_argument("--solo-semillas", action="store_true")
            s.add_argument("--correlacion", type=float)
            s.add_argument("--p-acierto", type=float)
            s.add_argument("--parametro", action="append", metavar="CLAVE=VALOR",
                           help="cualquier parámetro de bancos/capacidades_v1/simulacion.json (probabilidad 0-1)")
        else:
            s.add_argument("--iniciar-servidor-real", action="store_true")
            s.add_argument("--ctx", type=int, choices=(1024, 2048), default=config.CTX_PRINCIPAL)
            s.add_argument("--memoria", action="store_true", help="memoria de experiencias (aislada por modo y por banco)")
            s.add_argument("--puerto", type=int, default=config.PUERTO)
            s.add_argument("--sin-wake-lock", action="store_true")
    c = sub.add_parser("comparar")
    c.add_argument("a")
    c.add_argument("b")
    a = ap.parse_args(argv)
    if not config.fuera_de_proyecto(Path(__file__).resolve()):
        sys.exit("banco.py no puede ejecutarse desde dentro del proyecto existente")
    if a.orden == "lista":
        banco = B.cargar(CARPETA_BANCO)
        print(f"banco {banco['nombre']} · SHA-256 {banco['sha256'][:16]} · {len(banco['tareas'])} tareas")
        for t in banco["tareas"]:
            print(f"- {t['id']}: {t['instrucciones'][:90]}… ({len(banco['oraculos'][t['id']])} casos ocultos)")
        return 0
    if a.orden == "comparar":
        r = B.comparar_informes(_leer(a.a), _leer(a.b))
        print(json.dumps(r, ensure_ascii=False, indent=1))
        return 0
    if a.tareas:
        ids = {t["id"] for t in B.cargar(CARPETA_BANCO)["tareas"]}
        malas = [t for t in a.tareas if t not in ids]
        if malas:
            sys.exit(f"tareas desconocidas: {malas}")
    if not a.autorizo_pruebas:
        print("NO SE EJECUTA: el banco necesita --autorizo-pruebas para medir la calidad (ejecuta las soluciones con el "
              "ejecutor restringido).")
        return 2
    return simular(a) if a.orden == "simular" else real(a)


if __name__ == "__main__":
    print(f"Equipo IA {VERSION} — banco comparativo", file=sys.stderr)
    sys.exit(main())
