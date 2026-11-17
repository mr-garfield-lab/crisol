#!/usr/bin/env python3
"""perfiles.py — personalidad de A1, A2 y A3 (V2-E.5-r2). Todas las decisiones son del USUARIO.

Uso (añade --simulada para el almacén de las elecciones SIMULADAS):
  python3 -B perfiles.py ver [--agente A1]                 perfil en uso, propuesta pendiente, origen
  python3 -B perfiles.py versiones --agente A1             todas las versiones con su procedencia
  python3 -B perfiles.py historial --agente A1             historial de solo anexar
  python3 -B perfiles.py elecciones --agente A1            intentos de elección (respuesta y validación)
  python3 -B perfiles.py aprobar-eleccion --agente A1      la propuesta pasa a vigente
  python3 -B perfiles.py rechazar-eleccion --agente A1
  python3 -B perfiles.py nueva-eleccion --agente A1        la próxima elección autorizada volverá a preguntar
  python3 -B perfiles.py editar --agente A1 --campo estilo.verbosidad --valor 2
  python3 -B perfiles.py restablecer --agente A1 --a base|inicial
  python3 -B perfiles.py revertir --agente A1              deshace el último cambio aplicado
  python3 -B perfiles.py experiencias --agente A1 [--todas]
  python3 -B perfiles.py anotar --agente A1 --tipo preferencia_usuario_mas_detalle --descripcion "..." --referencia "..."
  python3 -B perfiles.py archivar --num 3
  python3 -B perfiles.py importar --run RUN_ID             experiencias verificadas de una deliberación
  python3 -B perfiles.py proponer --agente A1              propuestas graduales (nunca se aplican solas)
  python3 -B perfiles.py cambios --agente A1 [--estado pendiente]
  python3 -B perfiles.py aprobar-cambio --num 4 | rechazar-cambio --num 4
  python3 -B perfiles.py verificar                         integridad (no modifica nada)
  python3 -B perfiles.py validar-contrato --archivo F.json  valida un documento del contrato v1 (V2-E.5-r3);
                                                           solo lee: no guarda ni activa nada

Datos: $TMPDIR/equipo_f2/lab_v2f1/personalidad/ (o personalidad_simulada/). La personalidad solo
describe estilo y preferencias no críticas: no cambia permisos, función, seguridad ni evaluación, y
en esta versión NO se usa en los prompts.
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
sys.dont_write_bytecode = True

from eq2 import config, memoria, personalidad as P, rutas  # noqa: E402

RUN = re.compile(r"^[0-9_]{8,40}$")


def _valor(campo, texto):
    if campo == "estilo.verbosidad":
        try:
            return int(texto)
        except ValueError:
            raise SystemExit("verbosidad: un entero de 1 a 5") from None
    if campo in ("preferencias.ejemplos", "preferencias.explicar_razonamiento"):
        if texto.lower() not in ("si", "sí", "no", "true", "false"):
            raise SystemExit("valor: si | no")
        return texto.lower() in ("si", "sí", "true")
    if campo == "rasgos":
        return [r.strip() for r in texto.split(",") if r.strip()]
    return texto


def _origen(o):
    return {"simulado": "SIMULADO (no es de Qwen)", "qwen": "QWEN (modelo local, sin verificar)",
            "base": "BASE neutral (sin elección)"}.get(o, o)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--simulada", action="store_true", help="usar el almacén de elecciones simuladas")
    sub = ap.add_subparsers(dest="orden", required=True)
    for n in ("ver", "versiones", "historial", "elecciones", "aprobar-eleccion", "rechazar-eleccion",
              "nueva-eleccion", "editar", "restablecer", "revertir", "experiencias", "anotar", "proponer",
              "cambios"):
        s = sub.add_parser(n)
        s.add_argument("--agente", choices=P.AGENTES, required=n != "ver")
        if n == "editar":
            s.add_argument("--campo", choices=P.CAMPOS, required=True)
            s.add_argument("--valor", required=True)
        if n == "restablecer":
            s.add_argument("--a", choices=("base", "inicial"), default="base")
        if n == "experiencias":
            s.add_argument("--todas", action="store_true")
        if n == "anotar":
            s.add_argument("--tipo", choices=P.TIPOS_EXPERIENCIA, required=True)
            s.add_argument("--descripcion", required=True)
            s.add_argument("--referencia", required=True, help="de dónde procede (p. ej. fecha o run)")
        if n == "cambios":
            s.add_argument("--estado", choices=("pendiente", "aplicado", "rechazado", "revertido"))
    for n in ("aprobar-cambio", "rechazar-cambio", "archivar"):
        sub.add_parser(n).add_argument("--num", type=int, required=True)
    sub.add_parser("importar").add_argument("--run", required=True)
    sub.add_parser("verificar")
    sub.add_parser("validar-contrato").add_argument("--archivo", required=True)
    a = ap.parse_args()
    if a.orden == "validar-contrato":                    # V2-E.5-r3: no abre ninguna base
        ruta = Path(a.archivo)
        try:
            if ruta.is_symlink() or not ruta.is_file() or ruta.stat().st_size > 64_000:
                raise ValueError("el archivo no existe, es un enlace o supera 64 kB")
            r = P.validar_contrato(json.loads(ruta.read_text(encoding="utf-8")))
        except (OSError, ValueError) as e:
            print("ERROR:", e, file=sys.stderr)
            return 2
        print(json.dumps(r, ensure_ascii=False, indent=1))
        return 0 if r["valida"] else 1
    raiz = rutas.raiz_laboratorio()
    base = raiz / config.CARPETA_ACTUAL
    lab = rutas.Laboratorio(raiz, base)
    try:
        reg = P.RegistroPersonalidad(lab, "simulado" if a.simulada else "real")
    except (P.DatosCorruptos, memoria.EsquemaIncompatible, ValueError, rutas.RutaInsegura) as e:
        print("ERROR:", e, file=sys.stderr)
        return 2
    try:
        return _orden(a, reg, lab)
    except (ValueError, KeyError, PermissionError, P.LimiteExcedido) as e:
        print("RECHAZADO:", e, file=sys.stderr)
        return 1
    finally:
        reg.cerrar()


def _orden(a, reg, lab) -> int:
    imp = lambda x: print(json.dumps(x, ensure_ascii=False, indent=1, default=str))  # noqa: E731
    o = a.orden
    if o == "ver":
        for ag in ([a.agente] if a.agente else P.AGENTES):
            p, pr = reg.perfil(ag), reg.propuesto(ag)
            print(f"== {ag} ({P.FUNCIONES[ag]}; función y permisos fijados por el sistema) ==")
            print(f"  en uso: {p['fuente']} v{p['version']} origen={_origen(p['origen'])}", p["avisos"] or "")
            print("  ", json.dumps(p["datos"], ensure_ascii=False))
            if pr:
                print(f"  PROPUESTA PENDIENTE de aprobación: v{pr['version']} origen={_origen(pr['origen'])}")
                print("  ", json.dumps(pr["datos"], ensure_ascii=False) if pr["datos"] else pr["problemas"])
        print("NOTA: en V2-E.5-r2 la personalidad no se usa en los prompts; solo se registra.")
    elif o == "versiones":
        imp([{k: v[k] for k in ("version", "origen", "estado", "ts", "datos", "problemas", "eleccion_num",
                                 "cambio_num")} for v in reg.versiones(a.agente)])
    elif o == "historial":
        imp(reg.historial(a.agente))
    elif o == "elecciones":
        imp(reg.elecciones(a.agente))
    elif o == "aprobar-eleccion":
        imp(reg.aprobar_eleccion(a.agente))
    elif o == "rechazar-eleccion":
        imp({"rechazado": reg.rechazar_eleccion(a.agente)})
    elif o == "nueva-eleccion":
        imp({"solicitud": reg.solicitar_nueva_eleccion(a.agente),
             "siguiente_paso": "python3 -B ejecutar_v2.py --modo personalidad --autorizar-eleccion-personalidad "
                               f"--iniciar-servidor-real --agente {a.agente}"})
    elif o == "editar":
        imp(reg.editar(a.agente, a.campo, _valor(a.campo, a.valor)))
    elif o == "restablecer":
        imp(reg.restablecer(a.agente, a.a))
    elif o == "revertir":
        imp(reg.revertir_ultimo(a.agente))
    elif o == "experiencias":
        imp(reg.experiencias(a.agente, activas=not a.todas))
    elif o == "anotar":
        imp({"experiencia": reg.registrar_experiencia(a.agente, a.tipo, a.descripcion, "usuario", a.referencia)})
    elif o == "archivar":
        reg.archivar_experiencia(a.num)
        imp({"archivada": a.num})
    elif o == "importar":
        if not RUN.match(a.run):
            raise ValueError("identificador de ejecución inválido")
        texto = lab.leer_texto(("runs", a.run, "summary.json"), 4_000_000)
        if texto is None:
            raise ValueError("no existe ese summary.json")
        imp(reg.importar_resumen(json.loads(texto), a.run))
    elif o == "proponer":
        imp(reg.proponer_adaptaciones(a.agente))
    elif o == "cambios":
        imp(reg.cambios(a.agente, a.estado))
    elif o == "aprobar-cambio":
        imp(reg.aprobar_cambio(a.num))
    elif o == "rechazar-cambio":
        reg.rechazar_cambio(a.num)
        imp({"rechazado": a.num})
    elif o == "verificar":
        pr = reg.verificar()
        imp({"problemas": pr})
        return 1 if pr else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
