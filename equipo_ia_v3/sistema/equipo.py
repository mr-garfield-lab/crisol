#!/usr/bin/env python3
"""equipo.py — Equipo IA V2-F.1: tareas para A1 (código), A2 (plan, pruebas, revisión) y A3 (casos, revisión, auditoría).

  python3 -B equipo.py tarea importar /ruta/tarea.json      guarda la tarea (LAB-NNN); nunca sobrescribe
  python3 -B equipo.py tarea ejecutar LAB-001 --autorizo-pruebas
                                                            A2 planifica y escribe pruebas, A1 programa, A3 revisa;
                                                            el ejecutor restringido ejecuta las pruebas; A3 audita
  python3 -B equipo.py tarea estado LAB-001|ultima
  python3 -B equipo.py tarea exportar LAB-001|ultima        ZIP en .../lab_v2f1/exportaciones/ (no sobrescribe)
  python3 -B equipo.py tarea lista
  python3 -B equipo.py demo funcion [--escenario corregible|falta_informacion|sin_progreso]
                                                            V2-F.1: función supervisada con un GUION (SIMULADO, sin
                                                            Qwen); todo lo demás es real; nunca ejecuta el código

`ejecutar` usa Qwen REAL: arranca llama-server con el GGUF (solo lectura) igual que `ejecutar_v2.py --modo
tarea_real`, con todas sus comprobaciones (modelo, memoria, puerto, proceso llama ya activo, STOP). No hay modo
simulado en esta orden. Sin --autorizo-pruebas, las pruebas NO se ejecutan y el resultado queda «no_verificado».
Formato de tarea.json: {"id": "LAB-001" (opcional), "titulo": "...", "instrucciones": "...", "max_iteraciones": 2}
V2-F (opcionales): "tipo": "codigo" | "debate_codigo" | "modlab_pz"; "motor": "v2f" (por defecto) | "v2e";
  "casos": ["f(1) == 2", ...] (oráculo del usuario); "propiedades": ["no_muta_argumentos", "determinista"];
  "politica_falta": "preguntar" (por defecto) | "asumir_y_marcar". Ver LEEME_V2F.md.
V2-F.1: "tipo": "funcion_supervisada" (+ "funcion": "nombre" opcional): A1 escribe, A2 revisa, A3 propone casos y
  evalúa la evidencia, el equipo corrige con límites; la EJECUCIÓN DINÁMICA ESTÁ BLOQUEADA (--autorizo-pruebas se
  ignora) y el resultado es como mucho «aceptada_sin_ejecucion». Ver LEEME_V2F1.md.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
sys.dont_write_bytecode = True

from eq2 import VERSION, backend_llama, config, perfiles_contexto, servidor, tareas  # noqa: E402


def _imprimir(d):
    print(json.dumps(d, ensure_ascii=False, indent=1, default=str))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="grupo", required=True)
    t = sub.add_parser("tarea").add_subparsers(dest="orden", required=True)
    t.add_parser("importar").add_argument("ruta")
    e = t.add_parser("ejecutar")
    e.add_argument("id")
    e.add_argument("--autorizo-pruebas", action="store_true",
                   help="autoriza ejecutar las pruebas con el ejecutor restringido (lista blanca + límites; no es un sandbox)")
    e.add_argument("--puerto", type=int, default=config.PUERTO)
    e.add_argument("--sin-wake-lock", action="store_true")
    e.add_argument("--sin-continuacion", action="store_true")
    e.add_argument("--ctx", type=int, choices=(1024, 2048), default=config.CTX_PRINCIPAL,
                   help="V2-F: contexto del servidor (2048 por defecto, el perfil de referencia; en V2-E.7 quedaba en 1024)")
    t.add_parser("estado").add_argument("id")
    t.add_parser("exportar").add_argument("id")
    t.add_parser("lista")
    d = sub.add_parser("demo").add_subparsers(dest="orden", required=True)            # V2-F.1
    df = d.add_parser("funcion", help="función supervisada con respuestas de GUION (SIMULADO)")
    df.add_argument("--escenario", default="corregible", choices=("corregible", "falta_informacion", "sin_progreso"))
    df.add_argument("--ctx", type=int, choices=(1024, 2048), default=config.CTX_PRINCIPAL)
    a = ap.parse_args(argv)
    try:
        ts = tareas.Tareas()
        if a.grupo == "demo":                                                     # V2-F.1
            from eq2 import demo_funcion
            config.CTX = a.ctx
            perfiles_contexto.aplicar(perfiles_contexto.perfil_de_ctx(config.CTX))
            print(f"contexto: {config.CTX} · DEMOSTRACIÓN SIMULADA (guion, no Qwen)", file=sys.stderr)
            r = demo_funcion.ejecutar(ts, Path(__file__).resolve().parent, a.escenario)
            _imprimir(r)
            inf = ts.lab.ruta("tareas", r["tarea"], *r["informe"].split("/"))
            print(f"SIMULADO: las respuestas de A1, A2 y A3 son de un guion. Informe: {inf}")
            print(f"escenario {a.escenario}: resultado {r['resultado']} (esperado {r['esperado']})")
            return 0 if r["coincide"] else 1
        if a.orden == "importar":
            _imprimir(ts.importar(a.ruta))
        elif a.orden == "ejecutar":
            config.CTX = a.ctx                                                    # V2-F: contexto explícito
            perfiles_contexto.aplicar(perfiles_contexto.perfil_de_ctx(config.CTX))
            print(f"contexto: {config.CTX}", file=sys.stderr)
            srv = servidor.ServidorLlama(a.puerto)
            be = backend_llama.BackendLlama(srv, usar_wake_lock=not a.sin_wake_lock,
                                            permitir_continuacion=not a.sin_continuacion)
            ag = tareas.agentes_para(ts.tarea(ts.resolver(a.id)), be)             # V2-F: según el tipo de tarea
            r = ts.ejecutar(a.id, ag, backend=be, autorizo_pruebas=a.autorizo_pruebas)
            _imprimir(r)
            if r.get("clase") == "funcion_supervisada":                         # V2-F.1
                print("AVISO: función supervisada: la ejecución dinámica está BLOQUEADA" +
                      (" (--autorizo-pruebas se ignoró)" if a.autorizo_pruebas else "") +
                      f"; informe: {ts.lab.ruta('tareas', r['tarea'], *r['informe'].split('/'))}")
                return 0 if r["resultado"] in ("aceptada_sin_ejecucion", "aceptada_con_reservas_sin_ejecucion") else 1
            if not a.autorizo_pruebas:
                print("AVISO: sin --autorizo-pruebas no se ejecutó ninguna prueba; el resultado no puede ser «verificado».")
            return 0 if r["resultado"] in ("verificado", "esperado_confirmado", "cumple_oraculo") else 1
        elif a.orden == "estado":
            _imprimir(ts.estado(a.id))
        elif a.orden == "exportar":
            p = ts.exportar(a.id)
            print(p)
            print(f"Para copiarlo a Descargas: cp '{p}' ~/storage/downloads/")
        elif a.orden == "lista":
            _imprimir([ts.estado(i) | {"eventos": None} for i in ts._ids()])
        return 0
    except (tareas.ErrorTarea, OSError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    print(f"Equipo IA {VERSION}", file=sys.stderr)
    sys.exit(main())
