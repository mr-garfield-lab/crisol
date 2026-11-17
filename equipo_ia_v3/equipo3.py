#!/usr/bin/env python3
"""Equipo IA V3 — orden de línea de comandos.

  traza   (Etapa 1) importar LAB-001 | listar | reconstruir LAB-001/E001 [--json] | verificar LAB-001/E001
          (Etapa 4) deliberacion LAB-001/E001 [--json]: citas de A1/A2/A3 contrastadas con los archivos reales
  grafo   (Etapa 2) indexar [RAIZ] | buscar CONSULTA | paquete CONSULTA [--presupuesto N] | importar-traza |
                    vecinos NODO | medir
  memoria (Etapa 5) consultar A1|A2|A3 "consulta" [--json] [--hipotesis] | evaluar (escenarios prerregistrados)
  pc      (Etapa 6) recomendar [--ctx N] | planificar MODELO [--ctx N] [--gguf RUTA] [--json]
          ESTIMACIONES para el PC del usuario; no lanza nada ni descarga modelos
  cambios (Etapa 3) proponer-desde-traza LAB-001/E001 --proyecto P --archivo A.py | listar | ver PROP-0001 |
                    autorizar PROP-0001 --sha PREFIJO [--minutos N] [--acepto-avisos] | aplicar PROP-0001 |
                    verificar

Cada grupo acepta --lab (por defecto el de V2-F.1: `$TMPDIR/equipo_f2/lab_v2f1`). Bases en el laboratorio:
`traza_v3.sqlite3`, `grafo_v3.sqlite3` (índice de `sistema/src` y grafo de tareas) y `cambios_v3.sqlite3`.
Registro estructurado: `<lab>/registro_v3.jsonl`.
AUTORIZAR es una operación del USUARIO: ningún agente tiene acceso a ella.
Códigos de salida: 0 correcto · 1 la verificación encontró problemas · 2 error de datos, integridad o rechazo ·
3 detenido por STOP.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

from eq3 import RAIZ, VERSION, cambios as C, ingesta as I, reconstruccion as R, registro as G, traza as T


def lab_por_defecto() -> Path:
    return Path(os.environ.get("TMPDIR", "/tmp")) / "equipo_f2" / "lab_v2f1"


def _texto(r: dict) -> str:
    e, o, res = r["ejecucion"], r["objetivo"], r["resultado"] or {}
    lineas = [f"EJECUCIÓN {e['id']}  ({e['naturaleza']}, backend {e['backend']}, {e['version_sistema']})",
              f"OBJETIVO   {o['titulo'] or o['id']}",
              f"AGENTES    " + ", ".join(f"{a['agente']}={a['rol']} [{a['naturaleza']}]" for a in r["agentes"]),
              f"ANÁLISIS   " + ", ".join(x["id"].split("/", 2)[-1] for x in r["analisis"])]
    lineas.append("ACCIONES")
    for a in r["acciones"]:
        lineas.append(f"  {a['tipo'][:4]} {a['n']:>3} {a['agente']:<11} {a['nombre']}"
                      + (f"  sha256 {a['sha256'][:12]}" if a["sha256"] else ""))
    lineas.append(f"DECISIONES {len(r['decisiones'])}: " + ", ".join(sorted({d['tipo'] for d in r['decisiones']})))
    for a in r["autorizaciones"]:
        lineas.append(f"AUTORIZACIÓN {a['accion']}: {'CONCEDIDA por ' + a['actor'] if a['concedida'] else 'NO concedida'}")
    for c in r["cambios"]:
        lineas.append(f"CAMBIO     v{c['version']} {c['archivo']} ({c['origen']}) "
                      f"{(c['sha256_antes'] or '—')[:12]} → {c['sha256_despues'][:12]}")
    estados = {}
    for p in r["pruebas"]:
        estados[p["estado"]] = estados.get(p["estado"], 0) + 1
    lineas.append(f"PRUEBAS    {estados or 'ninguna'}")
    lineas.append(f"RESULTADO  {res.get('estado_final')} / {res.get('resultado')} "
                  f"(versión recomendada {res.get('version_recomendada')})")
    lineas.append(f"EXPERIENCIAS {len(r['experiencias'])}: "
                  + ", ".join(f"{x['agente']}:{x['tipo']}/{x['estado']}" for x in r["experiencias"]))
    return "\n".join(lineas)


def _traza(a, lab: Path, reg) -> int:
    with T.Traza(a.db or lab / "traza_v3.sqlite3") as traza:
        if a.accion == "importar":
            nuevas = I.importar_tarea(traza, lab, a.tarea)
            reg.evento("info", "ingesta", "importada", tarea=a.tarea, ejecuciones=nuevas)
            print(json.dumps({"tarea": a.tarea, "importadas": nuevas}, ensure_ascii=False))
            return 0
        if a.accion == "listar":
            for e in traza.filas("ejecuciones"):
                print(f"{e['id']}  {e['naturaleza']}  {e['backend']}  {e['inicio']}")
            return 0
        if a.accion == "reconstruir":
            r = R.reconstruir(traza, a.ejecucion)
            print(json.dumps(r, ensure_ascii=False, indent=1) if a.json else _texto(r))
            return 0
        if a.accion == "deliberacion":
            from eq3 import citas as Q
            r = Q.deliberacion(traza, lab, a.ejecucion)
            malas = len(r["invalidas"]) + len(r["alterados"])
            reg.evento("info" if not malas else "aviso", "deliberacion", "analizada", ejecucion=a.ejecucion,
                       invalidas=len(r["invalidas"]), alterados=len(r["alterados"]))
            if a.json:
                print(json.dumps(r, ensure_ascii=False, indent=1))
            else:
                for ag, x in sorted(r["por_agente"].items()):
                    print(f"{ag}: {x['citas']} citas · {x['verificadas']} verificadas · {x['invalidas']} inválidas · "
                          f"{x['sin_base']} sin base · {x['afirmaciones_sin_evidencia']} afirmaciones sin evidencia")
                print(f"Objeciones: {r['objeciones']}")
                for c in r["invalidas"]:
                    print(f"CITA INVÁLIDA paso {c['n']} ({c['agente']}): {c['cita']} → {c['estado']} {c['detalle']}")
                for x in r["alterados"]:
                    print(f"TEXTO ALTERADO paso {x['n']} ({x['agente']}): {x['archivo']}")
            return 0 if not malas else 1
        problemas = R.verificar(traza, lab, a.ejecucion)
        reg.evento("info" if not problemas else "error", "verificacion", "verificada", ejecucion=a.ejecucion,
                   problemas=len(problemas))
        for p in problemas:
            print("PROBLEMA:", p)
        print(f"VERIFICACIÓN {a.ejecucion}: {'CORRECTA' if not problemas else f'{len(problemas)} PROBLEMAS'}")
        return 0 if not problemas else 1


def _grafo(a, lab: Path, reg) -> int:
    from eq3 import grafo as GR
    raiz = (a.raiz or RAIZ / "sistema" / "src").resolve()
    with GR.Grafo(a.db or lab / "grafo_v3.sqlite3") as g:
        if a.accion == "indexar":
            st = g.indexar(raiz)
            reg.evento("info", "grafo", "indexado", raiz=str(raiz), cambiados=st["changed"], sin_cambios=st["unchanged"],
                       eliminados=st["stale_removed"])
            print(json.dumps(st, ensure_ascii=False))
        elif a.accion == "buscar":
            for x in g.recuperar(a.consulta, a.limite):
                print(f"{x['ruta']}  {x['sha256'][:12]}  {', '.join(x['simbolos'][:6])}")
        elif a.accion == "paquete":
            p = g.paquete(raiz, a.consulta, a.presupuesto)
            print(p["texto"])
            print(f"\n[tokens ESTIMADOS: {p['metricas']['tokens_estimated']} de {a.presupuesto}; "
                  f"{p['metricas']['estimation_method']}]")
        elif a.accion == "importar-traza":
            with T.Traza(lab / "traza_v3.sqlite3") as traza:
                print(json.dumps(g.importar_traza(traza), ensure_ascii=False))
        elif a.accion == "vecinos":
            print(json.dumps(g.vecinos(a.nodo), ensure_ascii=False, indent=1))
        else:
            m = GR.medir(g, raiz)
            print(json.dumps({k: m[k] for k in ("tareas", "media")}, ensure_ascii=False)
                  + f"\n{len(m['descartados'])} pares descartados (no aplicables a esta versión)")
    return 0


def _cambios(a, lab: Path, reg) -> int:
    with C.Controlador(lab) as c:
        if a.accion == "proponer-desde-traza":
            with T.Traza(lab / "traza_v3.sqlite3") as traza:
                r = C.proponer_desde_traza(c, traza, a.ejecucion, a.proyecto, a.archivo)
            reg.evento("info", "cambios", "propuesta", id=r["id"], autorizable=r["autorizable"])
            print(json.dumps(r, ensure_ascii=False))
        elif a.accion == "listar":
            aut = {x["propuesta_id"] for x in c.cambios.filas("autorizaciones")}
            apl = {x["propuesta_id"] for x in c.cambios.filas("aplicaciones")}
            for p in c.cambios.filas("propuestas"):
                estado = "aplicada" if p["id"] in apl else "autorizada" if p["id"] in aut else "propuesta"
                print(f"{p['id']}  {p['proyecto_id']}/{p['archivo']}  {p['agente']}  {estado}  "
                      f"sha256 {p['sha256_despues'][:12]}  {p['origen'] or ''}")
        elif a.accion == "ver":
            p = c._propuesta(a.propuesta)
            print(f"{p['id']} · {p['proyecto_id']}/{p['archivo']} · agente {p['agente']} · origen {p['origen']}")
            print(f"SHA-256 del contenido propuesto: {p['sha256_despues']}")
            print(f"Análisis estático: {p['analisis']}\n{p['diff']}")
        elif a.accion == "autorizar":
            r = c.autorizar(a.propuesta, a.sha, a.minutos, a.acepto_avisos)
            reg.evento("info", "cambios", "autorizada", id=a.propuesta, caduca=r["caduca"])
            print(json.dumps(r, ensure_ascii=False))
        elif a.accion == "aplicar":
            r = c.aplicar(a.propuesta)
            reg.evento("info", "cambios", "aplicada", id=a.propuesta, sha256=r["sha256"])
            print(json.dumps(r, ensure_ascii=False))
        else:
            problemas = c.verificar()
            for p in problemas:
                print("PROBLEMA:", p)
            print(f"VERIFICACIÓN DE CAMBIOS: {'CORRECTA' if not problemas else f'{len(problemas)} PROBLEMAS'}")
            return 0 if not problemas else 1
    return 0


def _memoria(a, lab: Path, reg) -> int:
    from datetime import datetime, timezone
    from eq3 import memoria as MM
    if a.accion == "evaluar":
        import tempfile
        for nombre in ("escenarios_memoria.json", "escenarios_memoria_2.json"):
            with tempfile.TemporaryDirectory(prefix="eq3_mem_") as d:
                r = MM.evaluar(RAIZ / "v3" / nombre, Path(d))
            print(f"{nombre} (SHA-256 {r['escenarios_sha256'][:12]}…): "
                  + " · ".join(f"{m}: recall {v['recall_medio']}, falsos {v['falsos']}, prohibidos {v['prohibidos']}"
                               for m, v in r["resumen"].items())
                  + (f" · rechazados al escribir: {[x['etiqueta'] for x in r['rechazados_al_escribir']]}"
                     if r["rechazados_al_escribir"] else ""))
        print("Mide el MECANISMO de recuperación sobre escenarios propios prerregistrados; no mide un modelo.")
        return 0
    ahora = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    traza = T.Traza(lab / "traza_v3.sqlite3") if (lab / "traza_v3.sqlite3").exists() else None   # consultar no crea bases
    cambios = C.Cambios(lab / "cambios_v3.sqlite3") if (lab / "cambios_v3.sqlite3").exists() else None
    try:
        if a.hipotesis:
            r = {"individual": MM.individual(lab, a.agente, a.consulta, ahora, permitir_hipotesis=True)}
        else:
            r = MM.consultar(lab, a.agente, a.consulta, ahora, traza=traza, cambios=cambios)
    finally:
        for x in (traza, cambios):
            if x is not None:
                x.cerrar()
    reg.evento("info", "memoria", "consultada", agente=a.agente,
               individual=len(r["individual"]["seleccion"]), episodios=len(r.get("episodica", [])),
               proyecto=len(r.get("proyecto", [])))
    print(json.dumps(r, ensure_ascii=False, indent=1) if a.json else (r.get("bloque") or "(sin memoria relevante)"))
    return 0


def _pc(a) -> int:
    from eq3 import perfiles_pc as PC
    if a.accion == "recomendar":
        r = PC.recomendar(ctx=a.ctx)
        print(f"{r['equipo']} · contexto {r['ctx']} · recomendado: {r['recomendado']}")
        for k, p in r["planes"].items():
            print(f"  {k}: {p['capas_gpu']}/{p['capas']} capas en GPU · VRAM ≈{p['vram_estimada_mib']} MiB "
                  f"(tope {p['tope_vram_mib']}) · RAM ≈{p['ram_estimada_mib']} MiB · {'cabe' if p['cabe'] else 'NO cabe'}")
        print(r["naturaleza"])
        return 0
    if a.modelo not in PC.CATALOGO:
        print(f"modelo desconocido: {a.modelo} (catálogo: {', '.join(PC.CATALOGO)})")
        return 2
    m = PC.CATALOGO[a.modelo]
    if a.gguf:
        m = PC.con_archivo(m, a.gguf)
    p = PC.planificar(m, a.ctx, ruta_modelo=str(a.gguf or "<ruta al GGUF>"))
    if a.json:
        print(json.dumps(p, ensure_ascii=False, indent=1))
    else:
        print(f"{p['modelo']} ({p['fuente_tamano']}) · contexto {p['ctx']} · {p['capas_gpu']}/{p['capas']} capas en GPU")
        print(f"VRAM ≈{p['vram_estimada_mib']} MiB (tope {p['tope_vram_mib']}) · RAM ≈{p['ram_estimada_mib']} MiB · "
              f"{p['servidores']} servidor para {', '.join(p['agentes'])} ({p['turnos']})")
        for x in p["avisos"]:
            print("AVISO:", x)
        print("Orden propuesta (no se ejecuta):", " ".join(p["argv"]))
        print(p["naturaleza"])
    return 0 if p["cabe"] else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version=VERSION)
    sub = ap.add_subparsers(dest="grupo", required=True)
    grupos = {}
    for nombre, ayuda in (("traza", "traza unificada de las ejecuciones (Etapa 1)"),
                          ("grafo", "índice de código, contexto y grafo de tareas (Etapa 2)"),
                          ("cambios", "propuesta → autorización del usuario → aplicación (Etapa 3)"),
                          ("memoria", "memoria individual, episódica y de proyecto (Etapa 5)"),
                          ("pc", "planificación de recursos del PC del usuario: estimaciones (Etapa 6)")):
        g = sub.add_parser(nombre, help=ayuda)
        if nombre != "pc":
            g.add_argument("--lab", type=Path, default=None, help="laboratorio de V2-F.1")
        if nombre in ("traza", "grafo"):
            g.add_argument("--db", type=Path, default=None, help="base de datos alternativa")
        grupos[nombre] = g.add_subparsers(dest="accion", required=True)
    tz = grupos["traza"]
    tz.add_parser("importar").add_argument("tarea")
    tz.add_parser("listar")
    rec = tz.add_parser("reconstruir")
    rec.add_argument("ejecucion")
    rec.add_argument("--json", action="store_true")
    tz.add_parser("verificar").add_argument("ejecucion")
    de = tz.add_parser("deliberacion")
    de.add_argument("ejecucion")
    de.add_argument("--json", action="store_true")
    gr = grupos["grafo"]
    gr.add_parser("indexar").add_argument("raiz", nargs="?", type=Path, default=None)
    b = gr.add_parser("buscar")
    b.add_argument("consulta")
    b.add_argument("--limite", type=int, default=8)
    pq = gr.add_parser("paquete")
    pq.add_argument("consulta")
    pq.add_argument("--presupuesto", type=int, default=2000)
    gr.add_parser("importar-traza")
    gr.add_parser("vecinos").add_argument("nodo")
    gr.add_parser("medir")
    cb = grupos["cambios"]
    pt = cb.add_parser("proponer-desde-traza")
    pt.add_argument("ejecucion")
    pt.add_argument("--proyecto", required=True)
    pt.add_argument("--archivo", required=True)
    cb.add_parser("listar")
    cb.add_parser("ver").add_argument("propuesta")
    au = cb.add_parser("autorizar")
    au.add_argument("propuesta")
    au.add_argument("--sha", required=True, help="al menos 12 caracteres del SHA-256 del contenido propuesto")
    au.add_argument("--minutos", type=int, default=30)
    au.add_argument("--acepto-avisos", action="store_true")
    cb.add_parser("aplicar").add_argument("propuesta")
    cb.add_parser("verificar")
    me = grupos["memoria"]
    co = me.add_parser("consultar")
    co.add_argument("agente", choices=("A1", "A2", "A3"))
    co.add_argument("consulta")
    co.add_argument("--json", action="store_true")
    co.add_argument("--hipotesis", action="store_true", help="incluir hipótesis (solo memoria individual)")
    me.add_parser("evaluar")
    pcg = grupos["pc"]
    rc = pcg.add_parser("recomendar")
    rc.add_argument("--ctx", type=int, default=8192)
    pl = pcg.add_parser("planificar")
    pl.add_argument("modelo")
    pl.add_argument("--ctx", type=int, default=8192)
    pl.add_argument("--gguf", type=Path, default=None, help="GGUF existente: se usa su tamaño real (solo stat)")
    pl.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    for opcional in ("db", "raiz"):
        if not hasattr(a, opcional):
            setattr(a, opcional, None)
    if a.grupo == "pc":                                 # solo calcula: no necesita laboratorio
        try:
            return _pc(a)
        except ValueError as e:
            print(f"ERROR: {e}")
            return 2
    lab = (a.lab or lab_por_defecto()).resolve()
    if not lab.is_dir():
        print(f"no existe el laboratorio: {lab}")
        return 2
    reg = G.Registro(lab / "registro_v3.jsonl")
    try:
        return {"traza": _traza, "grafo": _grafo, "cambios": _cambios, "memoria": _memoria}[a.grupo](a, lab, reg)
    except I.Detenido as e:
        reg.evento("aviso", a.grupo, "detenido", motivo=str(e))
        print("DETENIDO:", e)
        return 3
    except (I.ErrorIngesta, T.ErrorTraza, C.ErrorCambio, sqlite3.Error, ValueError) as e:
        # sqlite3: base bloqueada, dañada o ilegible; ValueError: entradas rechazadas por Contexto Ligero
        reg.evento("error", a.grupo, type(e).__name__, motivo=str(e)[:300])
        print(f"ERROR ({type(e).__name__}): {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
