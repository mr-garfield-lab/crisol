#!/usr/bin/env python3
"""ejecutar_v2.py — V2-E: comprobaciones, una llamada, deliberación, ciclo y motor autónomo.

NO inicia nada por sí solo. Modos:
  --modo comprobar      Comprobaciones previas SIN arrancar el servidor y SIN escribir archivos
                        (ejecuta `llama-server --help` salvo --sin-help).
  --modo deliberacion   Deliberación completa (7 llamadas + hasta 2 continuaciones + hasta 3 reintentos
                        de voto; tope 12 por tarea) con UN solo llama-server hijo, datos en la carpeta
                        fija datos_v2d (esquema 4). Exige --iniciar-servidor-real. Por defecto UNA
                        tarea fija; --tarea-delib la cambia. Informa consenso y fiabilidad por separado.
  --solicitar-evidencia (V2-E.5, opcional, desactivada por defecto) UNA llamada más por tarea:
                        A3 cita o retira sus objeciones sin evidencia comprobable (tope 13).
  --modo personalidad_simulada  (V2-E.5-r2) Elección de personalidad con backend SIMULADO (sin modelo),
                        en el almacén «personalidad_simulada». Exige --autorizar-eleccion-personalidad.
  --modo personalidad   (V2-E.5-r2) Elección REAL: cada agente propone su personalidad con el modelo
                        local, en secuencia y con UN llama-server (máx. 2 llamadas por agente). Exige
                        --iniciar-servidor-real y --autorizar-eleccion-personalidad. El resultado queda
                        PROPUESTO hasta que el usuario lo apruebe (python3 -B perfiles.py ...).
  --modo ciclo_simulado Ciclo plan -> generar -> revisar -> ejecutar -> corregir con agentes y ejecutor
                        SIMULADOS (sin modelo, sin ejecutar código). Demuestra la arquitectura.
  --modo tarea_simulada Motor autónomo (PLANIFICAR..FINALIZAR) con agentes y ejecutor SIMULADOS:
                        tarea completa de programación de ejemplo (varios archivos, un fallo y su
                        corrección). Sin modelo y sin ejecutar código.
  --modo tarea          Motor autónomo con el MODELO REAL (un llama-server hijo) y comprobación
                        ESTÁTICA (ast.parse; no ejecuta nada). Exige --iniciar-servidor-real.
                        El resultado es siempre NO VERIFICADO (no hay pruebas reales en V2-E).
  --modo reto_simulado  (V2-E.6) Reto Zomboid de diagnóstico ESTÁTICO: A2 -> A1 -> A3 con backend SIMULADO que
                        responde con las respuestas de referencia (--calidad buena|mala); puntúa 0-12.
  --modo reto           (V2-E.6) El mismo reto con el MODELO REAL (un llama-server hijo, 3 llamadas por caso).
                        Exige --iniciar-servidor-real. --semilla N elige los casos (generador propio seguro);
                        --caso fuentes|plantillas|viewpoint|inicio fija uno. Nunca ejecuta generar_reto.py.
  --ctx 2048|1024       Contexto. V2-E: 2048 por defecto (experimental principal); 1024 alternativa.
Todo se escribe en $TMPDIR/equipo_f2/lab_v2f1/ (V2-E.6 nunca escribe datos de versiones anteriores).
Supervisión en otra sesión: python3 -B supervisar.py estado | eventos | detener | informe
  --modo una_llamada    Arranca UN llama-server hijo (127.0.0.1), hace UNA petición (fase analisis, A2),
                        guarda en las bases SQLite del laboratorio y lo detiene. Exige además
                        --iniciar-servidor-real (confirmación explícita tras la revisión de GPT-6).
Todo lo que se escribe va a $TMPDIR/equipo_f2/<carpeta>/. Nunca se lee .env ni nada del proyecto
existente salvo el modelo (solo lectura). Ctrl+C o el archivo STOP detienen la ejecución.
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
sys.dont_write_bytecode = True

from eq2 import VERSION as VERSION_TXT  # noqa: E402
from eq2 import (analisis_estatico, asesoria, backend_llama, ciclo, config, ejecutor,  # noqa: E402
                 incidencias, inferencia, memoria, motor, orquestador, perfiles_contexto, personalidad,
                 plataforma, rutas, servidor)

TAREA_POR_DEFECTO = "Escribe una función en Python que sume dos números enteros."


def _guion_reto(calidad, material):
    """Backend SIMULADO del reto: cada rol devuelve su parte de la respuesta de REFERENCIA (no es Qwen)."""
    from eq2 import retos as R

    def g(n, fase, mensajes, max_tokens):
        rol = next((a for a in config.AGENTES if f"Eres {a}," in mensajes[0]["content"]), "A2")
        caso = next((cid for cid, c in material["casos"].items() if f"({c['titulo']})" in mensajes[-1]["content"]), None)
        return material["referencias"][caso][calidad][rol] if caso else "NOTA: caso no reconocido"
    return g


def reto(args, simulado: bool) -> int:
    """V2-E.6: reto Zomboid. Escribe solo en $TMPDIR/equipo_f2/lab_v2f1/retos/<run>/ (incidencias propias)."""
    from datetime import datetime
    from eq2 import retos as R
    material = R.cargar(Path(__file__).resolve().parent / "retos" / "zomboid_v1")
    print("material:", "ÍNTEGRO (MANIFIESTO.json verificado)" if material["integro"] else "PROBLEMAS: " + "; ".join(material["problemas"]))
    if not material["integro"]:
        return 2
    lista = R.generar(material, args.semilla, n=4)
    if args.caso:
        lista = [x for x in lista if x["caso_id"] == args.caso]
    lista = lista[: max(1, args.max_casos)]
    raiz = rutas.raiz_laboratorio()
    lab = rutas.Laboratorio(raiz, raiz / config.CARPETA_ACTUAL)
    lab.crear_base()
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f") + f"_{os.getpid()}"
    lab.crear_dir("runs")
    lab.crear_dir("runs", run_id)
    lab.crear_dir("retos")
    lab.crear_dir_exclusivo("retos", run_id)
    reg = incidencias.RegistroIncidencias(rutas.Laboratorio(raiz, lab.base / "retos" / run_id))
    if simulado:
        be = inferencia.BackendSimulado(_guion_reto(args.calidad, material))
    else:
        be = backend_llama.BackendLlama(servidor.ServidorLlama(args.puerto), usar_wake_lock=not args.sin_wake_lock)
    stop = lambda: "stop_usuario" if os.path.lexists(str(lab.base / "STOP")) else None  # noqa: E731
    resultados, informe_be, error = [], {}, None
    try:
        be.iniciar({"lab": lab, "run_id": run_id, "parar": stop})
        for r in lista:
            print(f"== INICIO caso {r['caso_id']} (semilla {r['semilla']}; reto: {r['reto']}) ==")
            res = R.ejecutar_reto(be, material, r, reg, max_gen=args.max_tokens_reto, parar=stop)
            resultados.append(res)
            pt = res.get("puntuacion")
            print(f"== FIN caso {r['caso_id']}: " + (f"{pt['total']}/12 (bruto {pt['bruto']}, penalización "
                  f"{pt['penalizacion_total']}){' INVÁLIDA' if pt['invalida'] else ''}" if pt else f"INCOMPLETO ({res['error']})")
                  + f" [{'SIMULADO' if simulado else 'REAL (Qwen)'}] ==")
            if res["error"]:
                break
    except inferencia.ErrorInferencia as e:
        error = e.motivo
        print("ERROR DEL BACKEND:", e.motivo)
    finally:
        try:
            informe_be = be.detener() or {}
        finally:
            reg.cerrar()
    inf = {"version": VERSION_TXT, "run_id": run_id, "real": not simulado, "semilla": args.semilla,
           "calidad_simulada": args.calidad if simulado else None, "error": error,
           "resultados": resultados, "backend": {k: v for k, v in informe_be.items() if k != "informe"},
           "nota": ("REAL: salidas de Qwen, texto NO CONFIABLE; la puntuación es heurística." if not simulado else
                    "SIMULADO: respuestas de referencia escritas a mano, no Qwen.")}
    lab.crear_exclusivo(("retos", run_id, "informe.json"), json.dumps(inf, ensure_ascii=False, indent=1, default=str))
    print("informe:", lab.ruta("retos", run_id, "informe.json"))
    ok = error is None and resultados and all(x["completo"] for x in resultados)
    return 0 if ok else 1


def comprobar(args) -> int:
    srv = servidor.ServidorLlama(args.puerto)
    r = srv.comprobaciones(verificar_flags=not args.sin_help)
    print("== Comprobaciones previas (no se inicia ningún servidor) ==")
    for k in ("host", "puerto", "puerto_libre", "llama_activo_pid", "mem_available_kb", "binario",
              "flags_faltantes"):
        print(f"{k}: {r.get(k)}")
    m = r["modelo"]
    print("modelo:", {k: m.get(k) for k in ("ruta", "size", "magic", "error") if k in m})
    print("ctx:", config.CTX, "| max_tokens:", config.MAX_TOKENS)
    print("continuación (prefill) anunciada por --help:", r.get("soporta_prefill"),
          "(indicación; el comportamiento real se verifica en la deliberación)")
    print("plataforma:", plataforma.capacidades())
    print("problemas:", r["problemas"] or "ninguno")
    print("RESULTADO:", "OK" if r["ok"] else "NO APTO")
    return 0 if r["ok"] else 1


def informe(res: dict) -> None:
    print("\n== RESULTADO (V2-A, una llamada) ==")
    print("resultado_global:", res.get("resultado_global"), "| estado:", res.get("estado"),
          "| motivo_fin:", res.get("motivo_fin"))
    print("errores_cierre:", res.get("errores_cierre") or "ninguno")
    bi = res.get("backend_informe") or {}
    print("limpieza backend:", {"limpio": bi.get("limpio"), "problemas": bi.get("problemas"),
                                "pasos": bi.get("pasos")})
    inf = bi.get("informe") or {}
    print("carga_s:", inf.get("carga_s"), "| puerto libre antes:", inf.get("puerto_libre_antes"),
          "| puerto libre después:", (bi.get("pasos") or {}).get("puerto_liberado"))
    for p in inf.get("peticiones", []):
        m = p.get("metricas") or {}
        print(f"petición {p.get('n')}: status={p.get('status')} fin={p.get('finish_reason')} "
              f"diag={p.get('diagnostico')} concluyente={p.get('concluyente')} "
              f"motivos={p.get('motivos_no_concluyente')} fallo={p.get('fallo')}")
        print("  ENTRADA n", m.get("prompt_n"), "cache", m.get("cache_n"), "ms", m.get("prompt_ms"),
              "tok/s", m.get("prompt_per_second"), "| GEN n", m.get("predicted_n"), "ms",
              m.get("predicted_ms"), "tok/s", m.get("predicted_per_second"))
        print("  memoria_kB [antes, después]:", p.get("memoria_kB"), "| delta fallos:",
              p.get("delta_fallos"), "| log_errores:", p.get("log_errores"))
    print("monitor:", {k: v for k, v in (inf.get("monitor") or {}).items() if k != "ultima_muestra"})
    for c in res.get("calibracion_tokens", []):
        print(f"calibración de tokens: estimados={c['tokens_est']} reales={c['tokens_real']} "
              f"(la estimación sigue siendo PROVISIONAL hasta revisar varios casos)")
    for t in res.get("tareas", []):
        txt = t.get("respuesta_texto_no_confiable")
        if txt:
            print("\n--- respuesta del modelo (TEXTO NO CONFIABLE, solo para leer) ---")
            print(txt[:600])
            print("--- fin ---")
        else:
            print("tarea:", {k: v for k, v in t.items() if k != "respuesta_texto_no_confiable"})
    print("\nlimitaciones conocidas:")
    for l in res.get("limitaciones", []):
        print(" -", l)
    print("run_id:", res.get("run_id"))


def una_llamada(args) -> int:
    raiz = rutas.raiz_laboratorio()
    base = raiz / args.carpeta
    srv = servidor.ServidorLlama(args.puerto)
    be = backend_llama.BackendLlama(srv, usar_wake_lock=not args.sin_wake_lock)
    orq = orquestador.Orquestador(base, be, instalar_senales=True, raiz_laboratorio=raiz)
    try:
        res = orq.run_una_llamada(args.tarea)
    except (orquestador.SesionActiva, memoria.EsquemaIncompatible) as e:
        print("NO SE INICIA:", e)
        return 2
    informe(res)
    print("\nResumen guardado en:", orq.base / "runs" / res["run_id"] / "summary.json")
    return 0 if res.get("resultado_global") == "completo" else 1


def informe_deliberacion(res: dict) -> None:
    print("\n== RESULTADO (V2-C, deliberación) ==")
    print("resultado_global (sistema):", res.get("resultado_global"), "| estado:", res.get("estado"),
          "| motivo_fin:", res.get("motivo_fin"), "| llamadas_total:", res.get("llamadas_total"))
    print("CONCLUSIÓN VÁLIDA:", "SÍ" if res.get("conclusion_valida") else "NO",
          "| fiabilidad global:", res.get("fiabilidad_global"))
    print("config:", res.get("config"))
    print("errores_cierre:", res.get("errores_cierre") or "ninguno")
    print("tareas no iniciadas:", res.get("tareas_no_iniciadas"))
    for t in res.get("tareas", []):
        print("\n-- tarea", t.get("tarea_id"), "| estado:", t.get("estado"),
              "| motivo:", t.get("motivo"), "| llamadas:", t.get("llamadas"))
        print("   CONSENSO:", t.get("resultado"), "| conteo:", t.get("conteo"),
              "| cambios pendientes:", t.get("cambios_pendientes"))
        f = t.get("fiabilidad") or {}
        print("   FIABILIDAD:", f.get("nivel"), "| impide conclusión:", f.get("impide_conclusion"),
              "| propuesta final:", f.get("propuesta_estado"))
        print("   motivos:", f.get("motivos") or "ninguno")
        print("   advertencias:", f.get("advertencias") or "ninguna")
        print("   terminación por fase:", t.get("terminaciones"))
        c = t.get("criticas") or {}
        if c:                                                                         # V2-E.5
            print("   CRÍTICAS (comprobación de referencias, determinista):", c.get("conteo"))
            print("   posibles críticas falsas (cita o línea inexistente):", c.get("posibles_criticas_falsas") or "ninguna")
            print("   contradicciones:", c.get("contradicciones") or "ninguna")
            print("   problemas no resueltos:", c.get("problemas_no_resueltos") or "ninguno señalado con cita")
            print("   incertidumbre:", c.get("incertidumbre") or "ninguna señalada")
            if c.get("aclaracion"):
                print("   aclaración de evidencia:", c.get("aclaracion"))
            print("   NOTA: el consenso de los agentes NO demuestra que la propuesta sea correcta.")
        ind = t.get("independencia")
        if ind:                                                                  # V2-E.6
            print("   INDEPENDENCIA:", ", ".join(ind.get("tipos") or []) or "sin señales",
                  "| revisión independiente:", ind.get("revision_independiente"), "| (la similitud no prueba copia)")
        for ag, v in (t.get("votos") or {}).items():
            print(f"   voto {ag}: {v.get('postura')} [{v.get('estado_voto')}] motivo={v.get('motivo')} "
                  f"intentos={v.get('intentos')} fallidos={v.get('intentos_fallidos')} "
                  f"fin={v.get('finish_reason')} avisos={v.get('advertencias')}")
        if t.get("texto_final_no_confiable"):
            print("--- texto final (TEXTO NO CONFIABLE: hipótesis; no se ejecuta) ---")
            print(t["texto_final_no_confiable"][:1500])
            print("--- fin ---")
    d = res.get("desbordes") or {}
    cfg = res.get("config") or {}                                                # V2-E.6
    print(f"\n== Presupuesto de tokens (perfil {cfg.get('perfil_contexto')}) ==\n  generación pedida en la sesión: "
          f"{res.get('tokens_pedidos_sesion')} de {cfg.get('tokens_sesion_max')} (máx. por tarea {cfg.get('tokens_tarea_max')})")
    for ag, a in (res.get("aprendizaje") or {}).items():
        print(f"  aprendizaje {ag}: {a.get('por_estado')} | fuentes {a.get('por_fuente')} | auditoría {'OK' if a.get('ok') else 'FALLO'}")
    print("\n== Contexto (límite", d.get("ctx"), ") ==")
    for f in d.get("llamadas", []):
        print(f"  llamada {f['n']}: estimado={f['tokens_est']} real={f['tokens_real']} "
              f"max_tokens={f['max_tokens']} generados={f['generados']} fin={f['finish_reason']} "
              f"real+gen={f['suma_real_mas_gen']}")
    print("DESBORDAMIENTO EFECTIVO:", "SÍ" if d.get("hay_desbordamiento") else "no detectado")
    for h in d.get("hallazgos", []):
        print("  hallazgo:", h)
    bi = res.get("backend_informe") or {}
    print("\nlimpieza backend:", {"limpio": bi.get("limpio"), "problemas": bi.get("problemas"),
                                  "pasos": bi.get("pasos")})
    inf = bi.get("informe") or {}
    print("carga_s:", inf.get("carga_s"), "| puerto libre antes:", inf.get("puerto_libre_antes"),
          "| puerto libre después:", (bi.get("pasos") or {}).get("puerto_liberado"))
    for p in inf.get("peticiones", []):
        m = p.get("metricas") or {}
        print(f"petición {p.get('n')}: status={p.get('status')} fin={p.get('finish_reason')} "
              f"diag={p.get('diagnostico')} concluyente={p.get('concluyente')} fallo={p.get('fallo')} "
              f"| prompt_n={m.get('prompt_n')} cache_n={m.get('cache_n')} "
              f"gen_n={m.get('predicted_n')} gen_tok/s={m.get('predicted_per_second')} "
              f"pared_s={p.get('pared_s')} MemAvail_kB={((p.get('memoria_kB') or {}).get('MemAvailable'))}")
    print("monitor:", {k: v for k, v in (inf.get("monitor") or {}).items() if k != "ultima_muestra"})
    print("continuación disponible en este servidor:", inf.get("soporta_continuacion"))
    me = res.get("metricas") or {}
    print("\n== Métricas (comparables con comparar_metricas.py) ==")
    print("total:", me.get("total"))
    for f, v in (me.get("por_fase") or {}).items():
        print(f"  fase {f}: {v}")
    for t, v in (me.get("por_tipo") or {}).items():
        print(f"  tipo {t}: {v}")
    print("\nlimitaciones conocidas:")
    for l in res.get("limitaciones", []):
        print(" -", l)
    print("run_id:", res.get("run_id"))


def deliberar(args) -> int:
    raiz = rutas.raiz_laboratorio()
    base = raiz / config.CARPETA_ACTUAL
    tareas = args.tarea_delib or [config.TAREA_V2B]
    srv = servidor.ServidorLlama(args.puerto)
    be = backend_llama.BackendLlama(srv, usar_wake_lock=not args.sin_wake_lock,
                                    permitir_continuacion=not args.sin_continuacion)
    orq = orquestador.Orquestador(base, be, instalar_senales=True, raiz_laboratorio=raiz,
                                  solicitar_evidencia=args.solicitar_evidencia)          # V2-E.5
    try:
        if args.reanudar:                                                    # V2-E.6: reanudación EXPLÍCITA
            pend = orq.pendientes_de(args.reanudar)
            print(f"reanudar {args.reanudar}: {len(pend['pendientes'])} de {pend['total']} tareas pendientes "
                  f"(estado anterior: {pend['estado_anterior']}, motivo: {pend['motivo_anterior']})")
            res = orq.run_reanudacion(args.reanudar)
            if res.get("estado") == "nada_que_reanudar":
                print("NADA QUE REANUDAR: todas las tareas de esa ejecución terminaron.")
                return 0
        else:
            res = orq.run_deliberacion(tareas)
    except (orquestador.SesionActiva, memoria.EsquemaIncompatible) as e:
        print("NO SE INICIA:", e)
        return 2
    except (ValueError, FileNotFoundError) as e:
        print("NO SE REANUDA:", e)
        return 2
    informe_deliberacion(res)
    print("\nResumen guardado en:", orq.base / "runs" / res["run_id"] / "summary.json")
    # Distinto de cero si algo impide una conclusión válida (sistema, tarea, fiabilidad o desborde).
    return 0 if res.get("conclusion_valida") else 1


def _guion_personalidad(n, fase, mensajes, max_tokens):
    """Respuestas SIMULADAS (no son de Qwen) para demostrar el mecanismo de elección."""
    ag = next((a for a in config.AGENTES if f"Eres {a}," in mensajes[0]["content"]), "A1")
    tono = {"A1": "cercano", "A2": "neutral", "A3": "formal"}[ag]
    return json.dumps({"rasgos": ["ejemplo simulado"], "estilo": {"tono": tono, "verbosidad": 3, "formato": "mixto"},
                       "preferencias": {"ejemplos": True, "explicar_razonamiento": True,
                                        "pedir_aclaraciones": "a_veces"}})


def elegir_personalidad(args, simulado: bool) -> int:
    """V2-E.5-r2: elección de personalidad (opcional). Nunca se invoca desde otros modos."""
    raiz = rutas.raiz_laboratorio()
    base = raiz / config.CARPETA_ACTUAL
    lab = rutas.Laboratorio(raiz, base)
    try:
        reg = personalidad.RegistroPersonalidad(lab, "simulado" if simulado else "real")
    except (personalidad.DatosCorruptos, memoria.EsquemaIncompatible, ValueError) as e:
        print("NO SE INICIA:", e)
        return 2
    if simulado:
        be = inferencia.BackendSimulado(_guion_personalidad)
    else:
        srv = servidor.ServidorLlama(args.puerto)
        be = backend_llama.BackendLlama(srv, usar_wake_lock=not args.sin_wake_lock, permitir_continuacion=False)
    orq = orquestador.Orquestador(base, be, instalar_senales=True, raiz_laboratorio=raiz)
    try:
        res = orq.run_eleccion_personalidad(reg, agentes=tuple(args.agente or config.AGENTES), autorizado=True)
    except (orquestador.SesionActiva, memoria.EsquemaIncompatible) as e:
        print("NO SE INICIA:", e)
        reg.cerrar()
        return 2
    p = res.get("personalidad") or {}
    print("\n== ELECCIÓN DE PERSONALIDAD (V2-E.5-r2) ==")
    print("ORIGEN:", "SIMULADO (no es una elección de Qwen)" if simulado else
          "QWEN (generada por el modelo local; sin verificar)")
    print("estado de la sesión:", res.get("estado"), "| motivo_fin:", res.get("motivo_fin"),
          "| llamadas:", res.get("llamadas_total"))
    for ag, r in (p.get("agentes") or {}).items():
        print(f"  {ag}: {r['estado']} (llamadas={r.get('llamadas')})", r.get("perfil") or r.get("errores") or "")
    print("NOTA:", p.get("nota", "sin resultado"))
    print("Las elecciones válidas quedan PROPUESTAS. Revísalas y decide: python3 -B perfiles.py ver"
          + (" --simulada" if simulado else ""))
    print("Resumen guardado en:", orq.base / "runs" / res["run_id"] / "summary.json")
    reg.cerrar()
    return 0 if res.get("resultado_global") == "completo" else 1


def _guion_demo(paso, n, **kw):
    """Agentes SIMULADOS de demostración: la 1.ª versión muta la lista; la 2.ª lo corrige."""
    if paso == "plan":
        return "Plan: ordenar.py con ordenar(xs) que devuelve una copia ordenada; test_ordenar.py."
    if paso == "revisar":
        return ("OBJECION: muta la lista original | EVIDENCIA: usa xs.sort()"
                if ".sort()" in kw.get("archivos", "") else "SIN OBJECIONES: devuelve sorted(xs)")
    cuerpo = "    xs.sort()\n    return xs" if not kw.get("retro") else "    return sorted(xs)"
    return ("ARCHIVO: ordenar.py\n```python\ndef ordenar(xs):\n" + cuerpo + "\n```\n"
            "ARCHIVO: test_ordenar.py\n```python\nfrom ordenar import ordenar\n"
            "def test_no_muta():\n    a = [3, 1]\n    assert ordenar(a) == [1, 3] and a == [3, 1]\n```")


def _ejecutor_demo(it, archivos):
    """Ejecutor SIMULADO: inspecciona el TEXTO (no lo ejecuta) y finge el resultado."""
    muta = ".sort()" in archivos.get("ordenar.py", "")
    return {"estado": "fallos" if muta else "ok", "pruebas_total": 1,
            "pruebas_fallidas": 1 if muta else 0,
            "salida": "SIMULADO: test_no_muta falló (la lista original cambió)" if muta
            else "SIMULADO: 1 prueba superada"}


def ciclo_simulado(args) -> int:
    raiz = rutas.raiz_laboratorio()
    c = ciclo.Ciclo(raiz / config.CARPETA_ACTUAL, ciclo.AgentesSimulados(_guion_demo),
                    ejecutor.EjecutorSimulado(_ejecutor_demo), raiz_laboratorio=raiz)
    try:
        inf = c.ejecutar(config.TAREA_V2B)
    except FileExistsError:
        print("NO SE INICIA: candado existente (otra sesión en curso o candado obsoleto)")
        return 2
    print("== CICLO SIMULADO (sin modelo; ningún código se ha ejecutado) ==")
    print("estado:", inf["estado"], "| verificación:", inf["verificacion"],
          "| iteraciones:", len(inf["iteraciones"]), "| llamadas de agentes:", inf["llamadas_agentes"])
    for f in inf["iteraciones"]:
        print(f"  iteración {f['n']}: archivos={[a['nombre'] for a in f.get('archivos', [])]} "
              f"objeciones={(f.get('revision') or {}).get('objeciones')} "
              f"ejecución={(f.get('ejecucion') or {}).get('estado')} criterios={f.get('criterios')}")
    print("informe:", c.base / "runs" / inf["run_id"] / "ciclo" / "informe.json")
    return 0 if inf["estado"] == "criterios_cumplidos" else 1


# --- V2-E: motor autónomo ------------------------------------------------------------------------
DEMO_TAREA = ("Crea un paquete Python 'pkg' con ordenar(xs) que devuelva una copia ordenada de una "
              "lista de enteros sin modificar la original, con sus pruebas.")


def _guion_motor(paso, n, **kw):
    """Agentes SIMULADOS de la tarea de demostración (varios archivos; la 1.ª versión tiene un fallo)."""
    if paso == "planificar":
        return ("ARCHIVOS: pkg/__init__.py, pkg/ordenar.py, tests/test_ordenar.py\n"
                "CRITERIO: C1 | devuelve la lista ordenada | PRUEBA: test_ordena\n"
                "CRITERIO: C2 | no modifica la lista original | PRUEBA: test_no_muta\n"
                "CRITERIO: C3 | acepta la lista vacía | PRUEBA: test_vacia")
    if paso == "revisar":
        return ("OBJECION: modifica la entrada | EVIDENCIA: xs.sort() en pkg/ordenar.py"
                if ".sort()" in kw.get("archivos", "") else "SIN OBJECIONES: usa sorted(xs) y hay 3 pruebas")
    if paso == "evaluar":
        return "DIAGNOSTICO: test_no_muta falla porque xs.sort() ordena en el sitio; usar sorted(xs)."
    cuerpo = "    xs.sort()\n    return xs" if paso == "generar" else "    return sorted(xs)"
    return ("ARCHIVO: pkg/__init__.py\n```python\nfrom pkg.ordenar import ordenar\n```\n"
            "ARCHIVO: pkg/ordenar.py\n```python\ndef ordenar(xs):\n" + cuerpo + "\n```\n"
            "ARCHIVO: tests/test_ordenar.py\n```python\nfrom pkg.ordenar import ordenar\n\n"
            "def test_ordena():\n    assert ordenar([3, 1, 2]) == [1, 2, 3]\n\n"
            "def test_no_muta():\n    a = [2, 1]\n    ordenar(a)\n    assert a == [2, 1]\n\n"
            "def test_vacia():\n    assert ordenar([]) == []\n```\n"
            + ("CAMBIOS: sorted(xs) en lugar de xs.sort()\n" if paso == "corregir" else "") + "FIN")


def _ejecutor_motor(it, archivos):
    """Ejecutor SIMULADO: inspecciona el TEXTO (no lo ejecuta) y finge los resultados de las pruebas."""
    muta = ".sort()" in archivos.get("pkg/ordenar.py", "")
    pr = {"test_ordena": "ok", "test_no_muta": "fallo" if muta else "ok", "test_vacia": "ok"}
    return {"estado": "fallos" if muta else "ok", "pruebas_total": 3, "pruebas_fallidas": int(muta),
            "salida": "SIMULADO: " + ", ".join(f"{k}={v}" for k, v in pr.items()), "detalle": {"pruebas": pr}}


def _informe_motor(inf, base) -> None:
    print("== MOTOR AUTÓNOMO V2-E ==")
    print("estado final:", inf["estado_final"], "| motivo:", inf.get("motivo"))
    print("RESULTADO:", inf["resultado"].upper().replace("_", " "),
          "(una simulación o un análisis estático NO son pruebas reales)")
    print("ejecutor:", inf["ejecutor"], "| pruebas reales ejecutadas:", inf["pruebas_reales_ejecutadas"])
    print("estados:", " -> ".join(["PLANIFICAR"] + [h["a"] for h in inf["historial_estados"]]))
    for c in inf["criterios"]:
        print(f"  criterio {c['id']} [{c['estado']}] {c['descripcion']} ({c['prueba']})")
    for m in inf["versiones"]:
        print(f"  versión {m['version']}: {[f['ruta'] for f in m['archivos']]} sha256={m['sha256_conjunto'][:12]}")
    print("diferencias:", inf["diferencias"])
    print("bloqueos:", inf["bloqueos_revisor"], "| fuera de alcance:", inf["fuera_de_alcance"],
          "| intentos de ampliar permisos:", inf["intentos_de_ampliar_permisos"])
    print("errores:", inf["errores"] or "ninguno")
    me = inf["metricas"]
    print("métricas:", {"llamadas": inf["llamadas_agentes"], "duracion_s": me.get("duracion_s"),
                        "por_agente": {a: v.get("pared_s") for a, v in me.get("por_agente", {}).items()}})
    bi = inf.get("backend_informe") or {}
    if bi:
        print("limpieza backend:", {"limpio": bi.get("limpio"), "pasos": bi.get("pasos")})
    print("informe:", base / "runs" / inf["run_id"] / "motor" / "informe.json")


def tarea_simulada(args) -> int:
    raiz = rutas.raiz_laboratorio()
    base = raiz / config.CARPETA_ACTUAL
    reg = incidencias.RegistroIncidencias(rutas.Laboratorio(raiz, base))      # V2-E.2
    m = motor.Motor(base, motor.AgentesMotorSimulados(_guion_motor),
                    ejecutor.EjecutorSimulado(_ejecutor_motor), raiz_laboratorio=raiz,
                    instalar_senales=True, proveedor=plataforma.proveedor(), incidencias=reg)
    try:
        inf = m.ejecutar(DEMO_TAREA)
    except FileExistsError:
        print("NO SE INICIA: candado existente (otra sesión en curso o candado obsoleto)")
        return 2
    _informe_motor(inf, m.base)
    print("incidencias registradas:", inf.get("incidencias"), "(consulta: python3 -B auditar.py informe)")
    reg.cerrar()
    return 0 if inf["estado_final"] == "criterios_superados_en_simulacion" else 1


def tarea_real(args) -> int:
    raiz = rutas.raiz_laboratorio()
    base = raiz / config.CARPETA_ACTUAL
    lab = rutas.Laboratorio(raiz, base)
    texto_ases = ""
    if args.asesoria:
        texto_ases = asesoria.importar(lab, args.asesoria)["texto"]
    srv = servidor.ServidorLlama(args.puerto)
    be = backend_llama.BackendLlama(srv, usar_wake_lock=not args.sin_wake_lock,
                                    permitir_continuacion=not args.sin_continuacion)
    pres = motor.Presupuesto(max_iteraciones_correccion=args.max_iteraciones)
    reg = incidencias.RegistroIncidencias(lab)                                  # V2-E.2
    m = motor.Motor(base, motor.AgentesMotorLLM(be), analisis_estatico.EjecutorEstatico(), presupuesto=pres,
                    backend=be, raiz_laboratorio=raiz, instalar_senales=True,
                    proveedor=plataforma.proveedor(), asesoria_txt=texto_ases, incidencias=reg)
    try:
        inf = m.ejecutar(args.tarea_motor or config.TAREA_V2B)
    except FileExistsError:
        print("NO SE INICIA: candado existente (otra sesión en curso o candado obsoleto)")
        return 2
    _informe_motor(inf, m.base)
    print("incidencias registradas:", inf.get("incidencias"), "(consulta: python3 -B auditar.py informe)")
    reg.cerrar()
    return 0 if inf["estado_final"] == "sin_verificar" else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--modo", choices=["comprobar", "una_llamada", "deliberacion", "ciclo_simulado",
                                       "tarea_simulada", "tarea", "personalidad_simulada", "personalidad",
                                       "reto_simulado", "reto"],
                    required=True)
    ap.add_argument("--ctx", type=int, choices=(1024, 2048), default=config.CTX_PRINCIPAL,
                    help="contexto clásico (1024 o 2048). Para 2560/3072 usa --perfil-contexto")
    ap.add_argument("--perfil-contexto", choices=perfiles_contexto.ORDEN, default=None,
                    help="V2-E.6: seguro (1024) | referencia (2048) | ampliado (2560) | experimental (3072). "
                         "Con retroceso automático si la RAM no alcanza o no se puede medir")
    ap.add_argument("--aceptar-experimental", action="store_true",
                    help="V2-E.6: aceptación explícita del perfil experimental (3072)")
    ap.add_argument("--tarea-motor", default=None, help="(solo tarea) enunciado de la tarea")
    ap.add_argument("--semilla", type=int, default=42, help="(reto) semilla del generador seguro de casos")
    ap.add_argument("--caso", choices=("fuentes", "plantillas", "viewpoint", "inicio"), default=None,
                    help="(reto) un solo caso")
    ap.add_argument("--max-casos", type=int, default=3, help="(reto) casos como máximo (3 llamadas cada uno)")
    ap.add_argument("--max-tokens-reto", type=int, default=400, help="(reto) tokens de salida por llamada (<= 800)")
    ap.add_argument("--calidad", choices=("buena", "mala"), default="buena",
                    help="(reto_simulado) respuesta de referencia que devuelve el backend simulado")
    ap.add_argument("--max-iteraciones", type=int, default=config.MOTOR_MAX_ITERACIONES_CORRECCION,
                    help="(solo tarea) iteraciones de corrección (máximo duro 3)")
    ap.add_argument("--asesoria", default=None,
                    help="(solo tarea) respuesta en asesoria/entrada/NOMBRE.md (datos no confiables)")
    ap.add_argument("--sin-continuacion", action="store_true",
                    help="no intentar continuar respuestas cortadas")
    ap.add_argument("--tarea", default=TAREA_POR_DEFECTO)
    ap.add_argument("--puerto", type=int, default=config.PUERTO)
    ap.add_argument("--tarea-delib", action="append", default=None, metavar="TEXTO",
                    help="(solo deliberacion) tarea; repetible hasta 3. Por defecto, la tarea fija de V2-B")
    ap.add_argument("--carpeta", default=None,
                    help="subcarpeta del laboratorio para los datos (por defecto datos_v2d; "
                         "en deliberacion es siempre datos_v2d; nunca las de versiones anteriores)")
    ap.add_argument("--sin-wake-lock", action="store_true")
    ap.add_argument("--reanudar", metavar="RUN_ID", default=None,
                    help="V2-E.6 (solo deliberacion): reanuda EXPLÍCITAMENTE las tareas que no terminaron en esa ejecución, "
                         "en una sesión nueva (la anterior no se modifica)")
    ap.add_argument("--solicitar-evidencia", action="store_true",
                    help="V2-E.5: en la deliberación, UNA llamada más como máximo para que A3 cite la evidencia "
                         "de sus objeciones o las retire")
    ap.add_argument("--autorizar-eleccion-personalidad", action="store_true",
                    help="V2-E.5-r2: autorización explícita para la elección de personalidad (desactivada por defecto)")
    ap.add_argument("--agente", action="append", choices=config.AGENTES, default=None,
                    help="(solo personalidad) agente que elige; repetible. Por defecto A1, A2 y A3")
    ap.add_argument("--sin-help", action="store_true", help="no ejecutar `llama-server --help`")
    ap.add_argument("--iniciar-servidor-real", action="store_true",
                    help="confirmación explícita para arrancar llama-server")
    args = ap.parse_args()
    if not (1024 <= args.puerto <= 65535):
        sys.exit("puerto fuera de rango")
    if not config.fuera_de_proyecto(Path(__file__).resolve()):
        sys.exit("este script no debe estar dentro del proyecto existente")
    if args.reanudar and (args.modo != "deliberacion" or args.tarea_delib):
        sys.exit("--reanudar solo se usa con --modo deliberacion y sin --tarea-delib")
    if args.tarea_delib and args.modo != "deliberacion":
        sys.exit("--tarea-delib solo se usa con --modo deliberacion")
    config.CTX = args.ctx                    # V2-E: 2048 por defecto; 1024 alternativa
    if args.perfil_contexto:                 # V2-E.6: perfiles con RAM medida y retroceso
        try:
            mem = plataforma.proveedor().mem_disponible_kb()
        except Exception:
            mem = None
        sel = perfiles_contexto.seleccionar(args.perfil_contexto, mem, aceptar_experimental=args.aceptar_experimental)
        perfiles_contexto.aplicar(sel["efectivo"])
        print(f"perfil de contexto: solicitado={sel['solicitado']} efectivo={sel['efectivo']} ctx={sel['ctx']} "
              f"RAM={'%s kB (medida)' % mem if mem is not None else 'no medible'}"
              + ("; RETROCESO: " + "; ".join(sel["motivos"]) if sel["retroceso"] else ""))
    else:
        perfiles_contexto.aplicar(perfiles_contexto.perfil_de_ctx(config.CTX))
    if args.agente and not args.modo.startswith("personalidad"):
        sys.exit("--agente solo se usa con los modos de personalidad")
    if args.modo.startswith("personalidad"):
        if not args.autorizar_eleccion_personalidad:
            sys.exit("la elección de personalidad está DESACTIVADA por defecto: añade "
                     "--autorizar-eleccion-personalidad para autorizarla explícitamente")
        if args.carpeta is not None:
            sys.exit(f"{args.modo} usa siempre {config.CARPETA_ACTUAL}")
        if args.modo == "personalidad_simulada":
            return elegir_personalidad(args, simulado=True)
        if not args.iniciar_servidor_real:
            sys.exit("falta --iniciar-servidor-real: no se arranca ningún servidor sin confirmación explícita")
        return elegir_personalidad(args, simulado=False)
    if args.modo == "comprobar":
        return comprobar(args)
    if args.modo in ("reto_simulado", "reto"):                               # V2-E.6
        if not 50 <= args.max_tokens_reto <= config.TOPE_MAX_TOKENS:
            sys.exit(f"--max-tokens-reto entre 50 y {config.TOPE_MAX_TOKENS}")
        if args.modo == "reto" and not args.iniciar_servidor_real:
            sys.exit("falta --iniciar-servidor-real: no se arranca ningún servidor sin confirmación explícita")
        return reto(args, simulado=args.modo == "reto_simulado")
    if args.modo in ("ciclo_simulado", "tarea_simulada"):
        if args.carpeta is not None:
            sys.exit(f"{args.modo} usa siempre {config.CARPETA_ACTUAL}")
        return ciclo_simulado(args) if args.modo == "ciclo_simulado" else tarea_simulada(args)
    if not args.iniciar_servidor_real:
        sys.exit("falta --iniciar-servidor-real: no se arranca ningún servidor sin confirmación explícita")
    if args.carpeta is not None:
        c = os.path.normpath(args.carpeta)
        if c in config.CARPETAS_ANTERIORES:
            sys.exit(f"{c} pertenece a una versión anterior: V2-E no la usa ni la modifica")
        if c.startswith((".", "/")) or os.sep in c:
            sys.exit("--carpeta debe ser un nombre simple dentro del laboratorio")
        args.carpeta = c
    if args.modo in ("deliberacion", "tarea"):
        if args.carpeta not in (None, config.CARPETA_ACTUAL):
            sys.exit(f"en {args.modo} la carpeta de datos es siempre {config.CARPETA_ACTUAL}")
        return deliberar(args) if args.modo == "deliberacion" else tarea_real(args)
    args.carpeta = args.carpeta or config.CARPETA_ACTUAL
    return una_llamada(args)


if __name__ == "__main__":
    sys.exit(main())
