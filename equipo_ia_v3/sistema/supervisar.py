#!/usr/bin/env python3
"""supervisar.py — supervisión de la tarea del motor autónomo V2-E (CLI).

Uso (en otra sesión de Termux mientras corre la tarea, o después):
  python3 -B supervisar.py estado              tarea, fase, agente activo, iteración, llamadas
  python3 -B supervisar.py eventos [-n 20]     últimos eventos (registro de acciones)
  python3 -B supervisar.py pruebas             comprobaciones realizadas (simuladas/estáticas/reales)
  python3 -B supervisar.py errores             errores registrados
  python3 -B supervisar.py recursos            tiempo, llamadas, memoria
  python3 -B supervisar.py detener             crea el archivo STOP (parada limpia)
  python3 -B supervisar.py informe [--run ID]  informe final
  python3 -B supervisar.py exportar-asesoria [--run ID]   solicitud manual para GPT-6/Claude
  python3 -B supervisar.py validar-asesoria NOMBRE.md     comprueba una respuesta en asesoria/entrada/

Solo LEE los archivos del laboratorio lab_v2f1; las únicas escrituras son el archivo STOP y la
solicitud de asesoría. No envía nada a ningún servicio. No toca el proyecto existente.
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
sys.dont_write_bytecode = True

from eq2 import asesoria, config, rutas  # noqa: E402

RUN = re.compile(r"motor_[0-9_]{10,40}")
MAX_JSON = 2_000_000


def lab():
    raiz = rutas.raiz_laboratorio()
    return rutas.Laboratorio(raiz, raiz / config.CARPETA_ACTUAL)


def leer_json(l, partes):
    t = l.leer_texto(partes, MAX_JSON)
    if t is None:
        return None
    try:
        return json.loads(t)
    except ValueError:
        return None


def estado_actual(l):
    return leer_json(l, ("estado_actual.json",))


def run_de(l, args):
    rid = getattr(args, "run", None) or (estado_actual(l) or {}).get("run_id")
    if not rid or not RUN.fullmatch(rid):
        sys.exit("no hay ninguna tarea del motor (o el identificador no es válido)")
    return rid


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="orden", required=True)
    for n in ("estado", "pruebas", "errores", "recursos", "detener"):
        sub.add_parser(n)
    e = sub.add_parser("eventos")
    e.add_argument("-n", type=int, default=20)
    e.add_argument("--run")
    i = sub.add_parser("informe")
    i.add_argument("--run")
    x = sub.add_parser("exportar-asesoria")
    x.add_argument("--run")
    v = sub.add_parser("validar-asesoria")
    v.add_argument("nombre")
    a = ap.parse_args()
    l = lab()
    if not l.existe():
        print("todavía no existe el laboratorio lab_v2f1")
        return 1
    if a.orden == "detener":
        if l.existe("STOP"):
            print("STOP ya existe: la tarea se detendrá en el siguiente paso")
        else:
            l.crear_exclusivo(("STOP",), "")
            print("STOP creado: la tarea se detendrá limpiamente en el siguiente paso (borra STOP para la siguiente)")
        return 0
    if a.orden == "validar-asesoria":
        r = asesoria.importar(l, a.nombre)
        print({k: r[k] for k in ("nombre", "chars", "sha256", "intentos_de_permisos", "nota")})
        return 0
    ea = estado_actual(l) or {}
    if a.orden == "estado":
        if not ea:
            print("sin estado")
            return 1
        for k in ("run_id", "tarea", "estado", "agente_activo", "iteracion_correccion", "llamadas",
                  "versiones", "ejecutor", "terminado", "actualizado"):
            print(f"{k}: {ea.get(k)}")
        return 0
    if a.orden == "recursos":
        print({"transcurrido_s": ea.get("transcurrido_s"), "llamadas": ea.get("llamadas"),
               "recursos": ea.get("recursos"), "presupuesto": ea.get("presupuesto")})
        return 0
    if a.orden == "errores":
        print("errores (estado actual):", ea.get("errores") or "ninguno")
        return 0
    rid = run_de(l, a)
    if a.orden == "eventos":
        t = l.leer_texto(("runs", rid, "motor", "eventos.jsonl"), MAX_JSON) or ""
        for linea in t.splitlines()[-max(1, min(a.n, 500)):]:
            print(linea)
        return 0
    inf = leer_json(l, ("runs", rid, "motor", "informe.json"))
    if a.orden == "pruebas":
        if inf is None:
            print("tarea en curso; última comprobación:", ea.get("ultima_comprobacion"))
            return 0
        for r in inf.get("pruebas_simuladas", []) + inf.get("analisis_estatico", []):
            print(f"v{r.get('version')} [{r.get('tipo')}] {r.get('estado')} "
                  f"total={r.get('pruebas_total')} fallidas={r.get('pruebas_fallidas')} {r.get('salida', '')[:120]}")
        print("pruebas reales ejecutadas:", inf.get("pruebas_reales_ejecutadas"))
        return 0
    if inf is None:
        print("el informe todavía no existe (¿tarea en curso?)")
        return 1
    if a.orden == "exportar-asesoria":
        print("solicitud escrita en asesoria/" + asesoria.exportar(l, inf) + " (no se ha enviado a nadie)")
        return 0
    print("== INFORME", rid, "==")
    print("estado final:", inf["estado_final"], "| motivo:", inf.get("motivo"))
    print("RESULTADO:", inf["resultado"].upper().replace("_", " "))
    for k in ("propuesta_generada", "revision_completada", "pruebas_reales_ejecutadas",
              "criterios_verificados", "criterios_superados_en_simulacion", "criterios_pendientes",
              "bloqueos_revisor", "fuera_de_alcance", "intentos_de_ampliar_permisos",
              "iteraciones_correccion", "llamadas_agentes", "errores"):
        print(f"{k}: {inf.get(k)}")
    print("pruebas simuladas:", len(inf.get("pruebas_simuladas", [])),
          "| análisis estáticos:", len(inf.get("analisis_estatico", [])))
    for c in inf.get("criterios", []):
        print(f"  {c['id']} [{c['estado']}] {c['descripcion']} ({c['prueba']})")
    for m in inf.get("versiones", []):
        print(f"  versión {m['version']}: {[f['ruta'] for f in m['archivos']]} sha256={m['sha256_conjunto'][:12]}")
    print("nota:", inf.get("nota"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
