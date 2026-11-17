#!/usr/bin/env python3
"""retos.py — retos de diagnóstico estático y pruebas variables con semillas (V2-E.6).

Uso:
  python3 -B retos.py material                         verifica el material Zomboid (MANIFIESTO.json, SHA-256)
  python3 -B retos.py generar --semilla 42 [--n 3]     casos y modificadores (generador PROPIO y seguro)
  python3 -B retos.py prompt --semilla 42 --rol A2     el prompt que vería un agente (sin oráculos ni criterios)
  python3 -B retos.py puntuar --caso fuentes RESPUESTA.txt   puntúa una respuesta (0-12 + penalizaciones)
  python3 -B retos.py referencias                      puntúa las respuestas de referencia buena/mala
  python3 -B retos.py tuberia --caso fuentes [--calidad buena]   A2 -> A1 -> A3 sobre los laboratorios (SIMULADO)
  python3 -B retos.py variables [--semilla N] [--niveles 1,2,3] [--repeticiones 2] [--n 4]
                                                       pruebas variables (semillas fijas 11, 42, 2026 + la opcional)
Con el modelo real: python3 -B ejecutar_v2.py --modo reto --iniciar-servidor-real [--semilla N] [--caso X]

Nunca ejecuta retos/zomboid_v1/material_original/generar_reto.py (NO CONFIABLE). Escribe solo en
$TMPDIR/equipo_f2/lab_v2f1/ (retos/ y pruebas_variables/). Todo lo de este script es SIMULADO.
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ / "src"))
sys.dont_write_bytecode = True

from eq2 import config, incidencias, pruebas_variables as PV, retos as R, rutas  # noqa: E402

MATERIAL = RAIZ / "retos" / "zomboid_v1"


def lab():
    raiz = rutas.raiz_laboratorio()
    lb = rutas.Laboratorio(raiz, raiz / config.CARPETA_ACTUAL)
    lb.crear_base()
    return raiz, lb


def sello():
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def informe_variables_md(inf) -> str:
    md = ["# Pruebas variables (SIMULADAS)", "", inf["nota"], "",
          f"Semillas: {inf['semillas']} · niveles: {inf['niveles']} · determinista: **{inf['determinista']}** · "
          f"superado: **{inf['superado']}**", "",
          "| semilla | nivel | casos zomboid | zomboid ok | deliberaciones ok | abstención A1/A2/A3 | repeticiones | determinista |",
          "|---|---|---|---|---|---|---|---|"]
    for i in inf["informes"]:
        pa = i["deliberacion"]["por_agente"]
        md.append(f"| {i['semilla']} | {i['nivel']} | {', '.join(i['zomboid']['casos'])} | {i['zomboid']['aciertos']}/"
                  f"{i['zomboid']['total']} | {i['deliberacion']['aciertos']}/{i['deliberacion']['deliberaciones']} | "
                  + "/".join(str(pa[a]["tasa_abstencion"]) for a in config.AGENTES)
                  + f" | {i['repeticiones']} | {i['determinista']} |")
    md += ["", "Distribución de comportamientos sorteados (deliberación) por semilla y nivel:", ""]
    for i in inf["informes"]:
        md.append(f"- semilla {i['semilla']}, nivel {i['nivel']}: " + ", ".join(
            f"{k}={v}" for k, v in i["deliberacion"]["distribucion"].items()))
    return "\n".join(md) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Retos y pruebas variables (V2-E.6)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("material")
    g = sub.add_parser("generar")
    g.add_argument("--semilla", type=int, default=42)
    g.add_argument("--n", type=int, default=3)
    pr = sub.add_parser("prompt")
    pr.add_argument("--semilla", type=int, default=42)
    pr.add_argument("--rol", choices=config.AGENTES, default="A2")
    pr.add_argument("--caso", default=None)
    pu = sub.add_parser("puntuar")
    pu.add_argument("--caso", required=True, choices=("fuentes", "plantillas", "viewpoint", "inicio"))
    pu.add_argument("archivo")
    sub.add_parser("referencias")
    tu = sub.add_parser("tuberia")
    tu.add_argument("--caso", required=True, choices=("fuentes", "plantillas", "viewpoint", "inicio"))
    tu.add_argument("--calidad", choices=("buena", "mala"), default="buena")
    va = sub.add_parser("variables")
    va.add_argument("--semilla", type=int, action="append", default=None, help="semilla adicional (repetible)")
    va.add_argument("--niveles", default="1,2,3")
    va.add_argument("--repeticiones", type=int, default=2)
    va.add_argument("--n", type=int, default=4, help="deliberaciones por semilla y nivel")
    va.add_argument("--solo-semillas", action="store_true", help="usar SOLO las semillas dadas (sin las fijas)")
    a = ap.parse_args(argv)

    m = R.cargar(MATERIAL)
    if a.cmd == "material":
        print(json.dumps({"integro": m["integro"], "problemas": m["problemas"], "huellas": m["huellas"],
                          "generar_reto_original": m["generar_reto_original"]}, ensure_ascii=False, indent=1))
        return 0 if m["integro"] else 1
    if not m["integro"]:
        print("MATERIAL NO ÍNTEGRO:", "; ".join(m["problemas"]))
        return 2
    if a.cmd == "generar":
        for r in R.generar(m, a.semilla, a.n):
            print(json.dumps(r, ensure_ascii=False))
        return 0
    if a.cmd == "prompt":
        lista = R.generar(m, a.semilla, 4)
        reto = next((x for x in lista if a.caso in (None, x["caso_id"])), lista[0])
        p = R.prompt_reto(m, reto, a.rol)
        print("[SISTEMA]\n" + p["sistema"] + "\n\n[USUARIO]\n" + p["usuario"])
        return 0
    if a.cmd == "puntuar":
        ruta = Path(a.archivo)
        if ruta.is_symlink() or not ruta.is_file() or ruta.stat().st_size > 200_000:
            print("ERROR: archivo no válido (enlace, inexistente o > 200 kB)")
            return 2
        r = R.puntuar(m, a.caso, ruta.read_text(encoding="utf-8", errors="replace"))
        print(json.dumps(r, ensure_ascii=False, indent=1))
        return 0
    if a.cmd == "referencias":
        fallo = False
        for cid in m["casos"]:
            for q in ("buena", "mala"):
                r = R.puntuar(m, cid, R.respuesta_de_referencia(m, cid, q))
                esperado = r["total"] >= 10 if q == "buena" else r["total"] <= 3
                fallo |= not esperado
                print(f"{cid:<11} {q:<6} {r['total']:>2}/12  bruto={r['bruto']:>2} penalización={r['penalizacion_total']:>2}"
                      f"  {'OK' if esperado else 'FALLO'}  {', '.join(x['tipo'] for x in r['penalizaciones'])}")
        return 1 if fallo else 0
    raiz, lb = lab()
    if a.cmd == "tuberia":
        lb.crear_dir("retos")
        d = lb.crear_dir_exclusivo("retos", "tuberia_" + sello())
        reg = incidencias.RegistroIncidencias(rutas.Laboratorio(raiz, d))
        try:
            info = R.tuberia(m, a.caso, reg, m["referencias"][a.caso][a.calidad])
        finally:
            reg.cerrar()
        rel = tuple(d.relative_to(lb.base).parts)
        lb.crear_exclusivo(rel + ("informe.json",), json.dumps(info, ensure_ascii=False, indent=1, default=str))
        pt = info["puntuacion"]
        print(f"[SIMULADO: respuestas de referencia «{a.calidad}», no Qwen] caso {a.caso}: {pt['total']}/12")
        print(f"citas aceptadas por el laboratorio: {len(info['citas_aceptadas'])}; rechazadas: {len(info['citas_rechazadas'])}")
        print(f"hipótesis: {len(info['hipotesis'])}; faltantes: {len(info['faltas'])}; comprobaciones de A3: "
              f"{[c['resultado'] for c in info['comprobaciones']]}; rechazos de A3: {len(info['rechazos'])}")
        print(f"pendiente del plan: {info['pendiente']} (nunca «verificado»: exigiría ejecutar el juego)")
        print("informe:", d / "informe.json")
        return 0
    if a.cmd == "variables":
        semillas = tuple(a.semilla or ()) if a.solo_semillas else PV.SEMILLAS_FIJAS + tuple(
            s for s in (a.semilla or ()) if s not in PV.SEMILLAS_FIJAS)
        niveles = tuple(int(x) for x in a.niveles.split(",") if x.strip())
        if not semillas or any(n not in PV.NIVELES for n in niveles):
            print("ERROR: semillas vacías o nivel desconocido (1, 2, 3)")
            return 2
        lb.crear_dir("pruebas_variables")
        d = lb.crear_dir_exclusivo("pruebas_variables", sello())
        inf = PV.bateria(d, m, semillas, niveles, a.repeticiones, a.n)
        rel = tuple(d.relative_to(lb.base).parts)
        lb.crear_exclusivo(rel + ("informe.json",), json.dumps(inf, ensure_ascii=False, indent=1, default=str))
        lb.crear_exclusivo(rel + ("informe.md",), informe_variables_md(inf))
        print(informe_variables_md(inf))
        print("informes:", d / "informe.json", "y", d / "informe.md")
        return 0 if inf["superado"] else 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
