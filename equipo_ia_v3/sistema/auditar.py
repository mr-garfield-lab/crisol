#!/usr/bin/env python3
"""auditar.py — registro de incidencias, prioridades, contexto, laboratorio y auditoría (V2-E.2/3/4).

Uso:
  python3 -B auditar.py listar [--estado E]       incidencias (todas o de un estado)
  python3 -B auditar.py ver INC-000001            detalle, evidencias, intentos, historial
  python3 -B auditar.py prioridades               orden causal explicable (con componentes)
  python3 -B auditar.py plan                      tareas propuestas para A1/A2/A3 (no las ejecuta)
  python3 -B auditar.py paquetes --tokens 300     paquetes de contexto (qué cabe y qué queda pendiente)
  python3 -B auditar.py informe                   informe de auditoría (JSON + Markdown)
  python3 -B auditar.py demo-laboratorio          experimentos de ejemplo (estático, simulado, motor)
  python3 -B auditar.py regresiones               casos de regresión: ¿siguen reproduciendo el fallo?
  python3 -B auditar.py entregas [--agente A1]    qué recibió cada agente (V2-E.3)
  python3 -B auditar.py desbloquear INC-000001 --motivo "..."   el USUARIO levanta un escalado (V2-E.3)
  python3 -B auditar.py hipotesis [INC-000001]    hipótesis, experimentos de reproducción/control (V2-E.4)
  python3 -B auditar.py demo-ciclo                ciclo completo de investigación, TODO SIMULADO (V2-E.4)
  python3 -B auditar.py plataforma                adaptador, verificación y dependencias del sistema (V2-E.5)
  python3 -B auditar.py informe-criticas [--json] [--casos ARCHIVO.json]
                                                  clasificación automática de críticas frente a la corrección
                                                  conocida (corpus incluido o casos propios) (V2-E.5-r2)
  python3 -B auditar.py cuaderno [--agente A1]     laboratorios individuales: entradas e intercambios (V2-E.5-r2)

Solo usa $TMPDIR/equipo_f2/lab_v2f1/incidencias/. No ejecuta código generado, no usa red ni
servicios externos y no toca el proyecto existente.
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
sys.dont_write_bytecode = True

from eq2 import (auditoria, config, contexto_incidencias, corpus_criticas, ejecutor,  # noqa: E402
                 evaluacion_criticas, incidencias, laboratorio, laboratorios, motor, plataforma, prioridad, rutas)

ID = re.compile(r"INC-\d{6}")


def registro():
    raiz = rutas.raiz_laboratorio()
    return incidencias.RegistroIncidencias(rutas.Laboratorio(raiz, raiz / config.CARPETA_ACTUAL))


def demo_laboratorio(reg) -> None:
    prov = plataforma.proveedor()
    try:
        mem = prov.mem_disponible_kb()
    except plataforma.NoSoportado:
        mem = None
    lab = laboratorio.Laboratorio(reg, recursos={"mem_kB": mem})
    print("presupuesto ajustado:", lab.presupuesto, "| ajustes:", lab.ajustes or "ninguno")
    iid = reg.crear("Demo: ordenar() muta la lista", "simulacion", 4, 4, dificultad=2, confianza=0.6,
                    criterios=["test_no_muta pasa"], origen="demo", firma="demo-muta")
    e1 = lab.planificar("La versión con xs.sort() hace fallar test_no_muta", "simulacion",
                        {"archivos": {"m.py": "def ordenar(xs):\n    xs.sort()\n    return xs\n"},
                         "pruebas": ["test_no_muta"],
                         "reglas": [{"archivo": "m.py", "si_contiene": ".sort()", "prueba": "test_no_muta",
                                     "resultado": "fallo"}]},
                        {"prueba_falla": "test_no_muta"}, incidencia_id=iid)
    print(e1, lab.ejecutar(e1)["conclusion"], "| causa confirmada:", lab.confirmar_causa_con(e1),
          "(un experimento aislado NO basta: hacen falta reproducción y control sobre versiones observadas;"
          " ver demo-ciclo)")
    try:
        rid = lab.crear_regresion(e1)
        print("regresión", rid)
    except (ValueError, incidencias.PermisoDenegado) as ex:
        print("regresión no creada:", ex)
    e2 = lab.planificar("Detecta la sintaxis rota", "analisis_estatico",
                        {"archivos": {"m.py": "def f(x)\n    return x\n", "test_m.py": "def test_a():\n    assert True\n"}},
                        {"tipo_error": "sintaxis"})
    print(e2, lab.ejecutar(e2)["conclusion"])
    e3 = lab.planificar("El motor corrige la demo en simulación", "prueba_motor", {"escenario": "demo_corrige"},
                        {"estado_final": "criterios_superados_en_simulacion"})
    print(e3, lab.ejecutar(e3)["conclusion"])
    print("NINGÚN experimento ha ejecutado código: análisis estático, reglas declarativas y motor simulado.")


def _salida_a1(cuerpo):
    return ("ARCHIVO: pkg/ordenar.py\n```python\ndef ordenar(xs):\n" + cuerpo + "\n```\n"
            "ARCHIVO: tests/test_ordenar.py\n```python\nfrom pkg.ordenar import ordenar\n"
            "def test_no_muta():\n    a = [2, 1]\n    ordenar(a)\n    assert a == [2, 1]\n```\nFIN")


def _guion_demo(arreglar):
    """Agentes SIMULADOS (no es Qwen): A2 propone una hipótesis localizada; A1 corrige o no."""
    def g(paso, n, **kw):
        if paso == "planificar":
            return "ARCHIVOS: pkg/ordenar.py, tests/test_ordenar.py\nCRITERIO: C1 | no muta la entrada | PRUEBA: test_no_muta"
        if paso == "generar":
            return _salida_a1("    xs.sort()\n    return xs")
        if paso == "revisar":
            return ("OBJECION: muta la lista | EVIDENCIA: .sort()" if ".sort()" in kw.get("archivos", "")
                    else "SIN OBJECIONES: no muta")
        if paso == "evaluar":
            ids = ID.findall(kw.get("incidencias") or "")
            return (f"DIAGNOSTICO {ids[0]}: ordena la lista en el sitio\n"
                    f"HIPOTESIS {ids[0]}: ARCHIVO pkg/ordenar.py PATRON .sort()") if ids else "DIAGNOSTICO: revisar"
        return _salida_a1("    return sorted(xs)" if arreglar else "    xs.sort()\n    return xs")
    return g


def _ejecutor_demo(_i, arch):
    muta = ".sort()" in arch.get("pkg/ordenar.py", "")
    return {"estado": "fallos" if muta else "ok", "pruebas_total": 1, "pruebas_fallidas": int(muta),
            "salida": "SIMULADO", "detalle": {"pruebas": {"test_no_muta": "fallo" if muta else "ok"}}}


def demo_ciclo(reg) -> int:
    raiz = rutas.raiz_laboratorio()
    print("DEMOSTRACIÓN TOTALMENTE SIMULADA: agentes con guion, ejecutor simulado, ningún código ejecutado.")
    for n, (arreglar, titulo) in enumerate(((True, "ejecución 1: A1 corrige"),
                                            (False, "ejecución 2: el patrón vuelve (seguimiento)")), 1):
        m = motor.Motor(raiz / config.CARPETA_ACTUAL, motor.AgentesMotorSimulados(_guion_demo(arreglar)),
                        ejecutor.EjecutorSimulado(_ejecutor_demo), raiz_laboratorio=raiz, incidencias=reg)
        try:
            inf = m.ejecutar("Demo V2-E.4: ordenar() no debe modificar la lista de entrada.")
        except FileExistsError:
            print("NO SE INICIA: candado existente (otra sesión en curso o candado obsoleto)")
            return 2
        print(f"\n== {titulo}: estado final {inf['estado_final']} | resultado {inf['resultado']}")
        for x in inf["incidencias"] or []:
            print(f"  {x['id']}: {x['etiqueta']}")
        for acc in (inf.get("incidencias_contexto") or {}).get("investigacion", {}).get("acciones", []):
            print("   ·", acc)
    print("\nNinguna incidencia está verificada con pruebas reales (Modo B deshabilitado).")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="orden", required=True)
    l = sub.add_parser("listar")
    l.add_argument("--estado", choices=incidencias.ESTADOS)
    v = sub.add_parser("ver")
    v.add_argument("id")
    for n in ("prioridades", "plan", "informe", "demo-laboratorio", "regresiones", "demo-ciclo", "plataforma"):
        sub.add_parser(n)
    hp = sub.add_parser("hipotesis")
    hp.add_argument("id", nargs="?")
    e = sub.add_parser("entregas")
    e.add_argument("--agente", choices=incidencias.AGENTES)
    e.add_argument("--run")
    d = sub.add_parser("desbloquear")
    d.add_argument("id")
    d.add_argument("--motivo", required=True)
    p = sub.add_parser("paquetes")
    p.add_argument("--tokens", type=int, default=300)
    ic = sub.add_parser("informe-criticas")                     # V2-E.5-r2
    ic.add_argument("--json", action="store_true")
    ic.add_argument("--casos", default=None, help="JSON con casos etiquetados (mismo formato que el corpus)")
    cu = sub.add_parser("cuaderno")                             # V2-E.5-r2
    cu.add_argument("--agente", choices=incidencias.AGENTES)
    a = ap.parse_args()
    if a.orden == "paquetes" and a.tokens < 40:
        ap.error("--tokens debe ser al menos 40")
    if (a.orden in ("ver", "desbloquear") or (a.orden == "hipotesis" and a.id)) and not ID.fullmatch(a.id):
        ap.error("identificador inválido (formato INC-000001)")
    if a.orden == "informe-criticas":              # V2-E.5-r2: puro; no abre el registro ni escribe
        casos = corpus_criticas.CASOS
        if a.casos:
            ruta = Path(a.casos)
            try:
                if ruta.is_symlink() or not ruta.is_file() or ruta.stat().st_size > 2_000_000:
                    raise ValueError("el archivo de casos no existe, es un enlace o supera 2 MB")
                casos = evaluacion_criticas.validar_casos(json.loads(ruta.read_text(encoding="utf-8")))
            except (OSError, ValueError) as e:
                print("ERROR:", e, file=sys.stderr)
                return 2
        inf = evaluacion_criticas.informe(casos)
        print(json.dumps(inf, ensure_ascii=False, indent=1) if a.json else evaluacion_criticas.texto_informe(inf))
        return 0
    if a.orden == "plataforma":                    # V2-E.5: solo lectura; no abre el registro
        ad = plataforma.adaptador()
        print(json.dumps({"capacidades": plataforma.capacidades(), "adaptador": ad.informe(),
                          "problemas": plataforma.problemas_para_esta_version()}, ensure_ascii=False, indent=1))
        print("dependencias del sistema operativo (archivo: líneas):")
        for cat, arch in plataforma.auditar_dependencias().items():
            print(f"  {cat}: " + "; ".join(f"{f}: {ls[:8]}" for f, ls in arch.items()))
        print("NOTA: solo Linux (sandbox) y Termux (usuario, hasta V2-E.1) tienen pruebas ejecutadas; Windows es diseño.")
        return 0
    try:
        reg = registro()
    except rutas.RutaInsegura as e:
        print("ERROR:", e, file=sys.stderr)
        return 2
    try:
        if a.orden == "listar":
            for i in reg.listar((a.estado,) if a.estado else None):
                print(f"{i['id']} [{i['estado']}] grav {i['gravedad']} causa {i['causa_estado']} "
                      f"prioridad {i['prioridad']} asignado {i['asignado']} :: {i['titulo']}")
        elif a.orden == "ver":
            try:
                reg.obtener(a.id)
            except KeyError:
                print("ERROR: no existe", a.id, file=sys.stderr)
                return 2
            print(json.dumps({"incidencia": reg.obtener(a.id), "ficha": reg.ficha(a.id),
                              "etiqueta": reg.etiqueta(a.id), "hipotesis": reg.hipotesis(a.id),
                              "revisiones_A3": reg.revisiones(a.id), "evidencias": reg.evidencias(a.id),
                              "intentos": reg.intentos(a.id), "historial": reg.historial(a.id)},
                             ensure_ascii=False, indent=1, default=str))
        elif a.orden == "prioridades":
            for x in prioridad.recalcular(reg, "auditar prioridades"):
                print(f"{x['id']} {x['prioridad']:>7} {x['componentes']} afecta a {x['afecta_a']}")
        elif a.orden == "plan":
            print(json.dumps(prioridad.planificar(reg, aplicar=False), ensure_ascii=False, indent=1))
            print("(plan PROPUESTO, vista previa: no se ejecuta ni se asigna nada desde aquí)")
        elif a.orden == "paquetes":
            for n, pq in enumerate(contexto_incidencias.Empaquetador(reg, a.tokens).todos(), 1):
                print(f"--- paquete {n} ({pq['tokens_est']} tokens est.) incluidas={pq['incluidas']} "
                      f"omitidas={pq['evidencias_omitidas']} pendientes={pq['pendientes']}")
        elif a.orden == "informe":
            r = auditoria.escribir(reg)
            print(r["informe"]["declaracion"], r["informe"]["resumen"])
            print("informe:", r["md"])
        elif a.orden == "demo-laboratorio":
            demo_laboratorio(reg)
        elif a.orden == "entregas":
            for x in reg.entregas(run_id=a.run, agente=a.agente):
                ev = "cabecera" if x["evidencia_num"] is None else (
                    f"E{x['evidencia_num']} [{x['desde']}:{x['hasta']}]" + ("" if x["completa"] else " (fragmento)"))
                print(f"{x['ts']} {x['run_id']} {x['agente']} {x['paso']:<10} {x['incidencia_id']} {ev}")
        elif a.orden == "desbloquear":
            try:
                inc = reg.obtener(a.id)
            except KeyError:
                print("ERROR: no existe", a.id, file=sys.stderr)
                return 2
            if not inc["bloqueada_por_limite"]:
                print(a.id, "no estaba escalada; no se cambia nada")
                return 0
            reg.desbloquear(a.id, "usuario", a.motivo)
            print(a.id, "desbloqueada por el usuario (los contadores de intentos y tareas se reinician)")
        elif a.orden == "demo-ciclo":
            return demo_ciclo(reg)
        elif a.orden == "hipotesis":
            for h in reg.hipotesis(a.id):
                print(f"{h['id']} {h['incidencia_id']} [{h['estado']}] patrón {h['patron']!r} en {h['archivo']} "
                      f"(propuesta por {h['actor']}, v{h['version']}) {h['motivo'] or ''}")
                for e in reg.con.execute("SELECT id, rol, version, estado, conclusion FROM experimentos "
                                         "WHERE hipotesis_id=? ORDER BY num", (h["id"],)).fetchall():
                    print(f"    {e['id']} {e['rol']} v{e['version']}: {e['estado']} / {e['conclusion']}")
        elif a.orden == "regresiones":
            lab = laboratorio.Laboratorio(reg)
            for x in lab.regresiones():
                print(x["id"], x["incidencia_id"], lab.ejecutar_regresion(x["id"]))
        elif a.orden == "cuaderno":                       # V2-E.5-r2: lectura de los laboratorios
            for ag in ([a.agente] if a.agente else incidencias.AGENTES):
                c = laboratorios.laboratorio_de(reg, ag)
                print(f"== cuaderno de {ag} ==")
                for e in c.entradas():
                    print(f"  {e['id']} {e['tipo']} [{e['resultado']}; respaldo={e['respaldo']}; "
                          f"procedencia={e['procedencia']}] {e['titulo'][:80]}"
                          + (f" (sustituye a {e['sustituye']})" if e["sustituye"] else ""))
                for e in c.recibidas():
                    print(f"  recibida de {e['de_agente']} vía coordinador: {e['id']} {e['tipo']} — "
                          f"{e['motivo_intercambio'][:60]}")
                mal = c.verificar_integridad()
                if mal:
                    print("  INTEGRIDAD: contenido alterado en", mal)
            print(json.dumps(laboratorios.Coordinador(reg).resumen(), ensure_ascii=False))
    finally:
        reg.cerrar()
    return 0


if __name__ == "__main__":
    sys.exit(main())
