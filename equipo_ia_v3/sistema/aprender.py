#!/usr/bin/env python3
"""aprender.py — aprendizaje acotado y auditable por agente (V2-E.6).

Uso:
  python3 -B aprender.py listar --agente A1 [--todos]        recuerdos (vigentes o todos) con estado y fuente
  python3 -B aprender.py historial --agente A1 RC-000001      evidencias, transiciones y contradicciones
  python3 -B aprender.py feedback --agente A1 RC-000001 --efecto apoya|refuta --motivo "..." \\
                         --autorizo --nombre "tu nombre"       validación HUMANA explícita (sin --autorizo no hace nada)
  python3 -B aprender.py revocar --agente A1 RC-000001 --motivo "..." --autorizo --nombre "..."
                                                              devuelve un verificado a sin_verificar
  python3 -B aprender.py auditar                              integridad y reglas de las tres bases
  python3 -B aprender.py exportar --agente A1                 JSON completo (para auditoría externa)
  python3 -B aprender.py evaluar [--repeticiones 3]           evaluación PRE/POST SIMULADA en una carpeta NUEVA
  python3 -B aprender.py recuperar --agente A1 "texto"        qué recuerdos llegarían al prompt (sin registrar uso)

Solo usa $TMPDIR/equipo_f2/lab_v2f1/aprendizaje/. No ejecuta código, no usa red y no modifica código,
permisos ni configuración. Un voto, una opinión o el consenso nunca verifican un recuerdo.
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
sys.dont_write_bytecode = True

from eq2 import aprendizaje as A, config, evaluacion_aprendizaje as E, rutas  # noqa: E402


def lab():
    raiz = rutas.raiz_laboratorio()
    lb = rutas.Laboratorio(raiz, raiz / config.CARPETA_ACTUAL)
    lb.crear_base()
    lb.crear_dir("aprendizaje")
    return lb


def base(agente):
    if agente not in config.AGENTES:
        raise SystemExit(f"agente desconocido: {agente!r} (A1, A2 o A3)")
    return A.AprendizajeAgente(lab().ruta("aprendizaje", f"{agente.lower()}.db"), agente)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Aprendizaje acotado y auditable (V2-E.6)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for nombre in ("listar", "historial", "feedback", "revocar", "exportar", "recuperar"):
        s = sub.add_parser(nombre)
        s.add_argument("--agente", required=True)
        if nombre in ("historial", "feedback", "revocar"):
            s.add_argument("recuerdo")
        if nombre == "listar":
            s.add_argument("--todos", action="store_true")
        if nombre == "recuperar":
            s.add_argument("consulta")
        if nombre in ("feedback", "revocar"):
            if nombre == "feedback":
                s.add_argument("--efecto", required=True, choices=("apoya", "refuta"))
            s.add_argument("--motivo", required=True)
            s.add_argument("--autorizo", action="store_true", help="confirmación EXPLÍCITA del usuario")
            s.add_argument("--nombre", default="")
    sub.add_parser("auditar")
    ev = sub.add_parser("evaluar")
    ev.add_argument("--repeticiones", type=int, default=3)
    a = ap.parse_args(argv)

    if a.cmd == "auditar":
        fallo = False
        for ag in config.AGENTES:
            b = base(ag)
            try:
                r = b.auditar()
            finally:
                b.cerrar()
            fallo |= not r["ok"]
            print(json.dumps(r, ensure_ascii=False))
        print("RESULTADO:", "FALLO" if fallo else "OK")
        return 1 if fallo else 0
    if a.cmd == "evaluar":
        lb = lab()
        carpeta = lb.crear_dir_exclusivo("aprendizaje", "evaluacion_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f"))
        con = A.AprendizajeAgente(carpeta / "con_memoria.db", "A1")
        sin = A.AprendizajeAgente(carpeta / "sin_memoria.db", "A1")
        try:
            r = E.evaluar(con, sin, a.repeticiones)
        finally:
            con.cerrar()
            sin.cerrar()
        rel = carpeta.relative_to(lb.base)
        lb.crear_exclusivo(tuple(rel.parts) + ("informe.json",), json.dumps(r, ensure_ascii=False, indent=1))
        print(f"[{r['etiqueta']}]")
        for k, v in r["metricas"].items():
            print(f"  {k:<36} {v}")
        print("  determinista:", r["determinista"], f"({r['repeticiones']} repeticiones)")
        print("RESULTADO:", "SUPERADO" if r["superado"] else "NO SUPERADO", "| informe:", carpeta / "informe.json")
        print(r["conclusion"])
        return 0 if r["superado"] else 1

    b = base(a.agente)
    try:
        if a.cmd == "listar":
            filas = ([b.recuerdo(r[0]) for r in b.con.execute("SELECT id FROM recuerdos ORDER BY num")]
                     if a.todos else b.vigentes())
            for r in filas:
                print(f"{r['id']}  {r['estado']:<22} {r['tipo']:<9} fuente={r['fuente']:<19} conf={r['confianza']:<5} "
                      f"{r['texto'][:90]}")
            print(f"({len(filas)} recuerdos)")
        elif a.cmd == "historial":
            print(json.dumps(b.historial(a.recuerdo), ensure_ascii=False, indent=1, default=str))
        elif a.cmd == "exportar":
            print(A.exportar(b))
        elif a.cmd == "recuperar":
            for m in b.recuperar(a.consulta, registrar_uso=False):
                print(A.formatear_para_prompt(m))
        elif a.cmd in ("feedback", "revocar"):
            if not a.autorizo or not a.nombre.strip():
                print("NO SE HA HECHO NADA: el feedback humano exige --autorizo y --nombre (confirmación explícita).")
                return 2
            r = (b.feedback_humano(a.recuerdo, None, a.motivo, a.nombre.strip(), revocar=True) if a.cmd == "revocar"
                 else b.feedback_humano(a.recuerdo, a.efecto, a.motivo, a.nombre.strip()))
            print(json.dumps(r, ensure_ascii=False))
    except (KeyError, ValueError, PermissionError) as e:
        print("ERROR:", e)
        return 1
    finally:
        b.cerrar()
    return 0


if __name__ == "__main__":
    sys.exit(main())
