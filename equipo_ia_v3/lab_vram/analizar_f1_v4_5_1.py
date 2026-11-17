"""Laboratorio (NO forma parte del método de F1): análisis A–E de una F1-VRAM-EXP-V4.5.1 ya terminada. Solo LEE la evidencia.

    python -B -X utf8 lab_vram/analizar_f1_v4_5_1.py [CARPETA_F1]      (por defecto evidencias/v31_f1_vram_exp_v4_5_1/f1_comparacion1)

Escribe `analisis/analisis_f1_v4_5_1.json` junto a la carpeta de F1. No ejecuta código de los agentes ni toca el modelo: solo
recorre `comparacion.json`, `r{1,2}/{S1,S1x3,E3}/Txx/fila.json` e `informe.json` de E3 y vuelve a calcular todo.
A: calidad y regla de decisión · B: agentes (S1 = borrador de E3 por SHA-256) · C: contexto · D: eficiencia y recursos ·
E: seguridad e integridad.
"""
import hashlib
import json
import sys
from collections import Counter, defaultdict
from math import comb
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
CFGS = ("S1", "S1x3", "E3")
TAREAS = [f"T{n:02d}" for n in range(1, 16)]
AUTO = TAREAS[:13]                                            # T01–T13: métrica principal; T14–T15: revisión ciega aparte
RUTA_E3 = "intento1/equipo_f2/lab_v2f1/tareas/LAB-001/ejecuciones/E001/funcion"
sha = lambda b: hashlib.sha256(b).hexdigest()


def cargar(f1: Path):
    c = json.loads((f1 / "comparacion.json").read_text(encoding="utf-8"))
    filas = {(rep, cfg, t): json.loads((f1 / f"r{rep}" / cfg / t / "fila.json").read_text(encoding="utf-8"))
             for rep in (1, 2) for cfg in CFGS for t in TAREAS}
    return c, filas


def signos(solo_a: int, solo_b: int) -> float:
    n = solo_a + solo_b
    if n == 0:
        return 1.0
    return min(1.0, 2 * sum(comb(n, k) for k in range(0, min(solo_a, solo_b) + 1)) / 2 ** n)


def analisis_a(filas, tareas_cat):
    cat = lambda rep, cfg, t: filas[(rep, cfg, t)]["evaluacion"]["categoria"]
    por_cfg = {}
    for cfg in CFGS:
        por_cfg[cfg] = {}
        for rep in (1, 2):
            cuenta = Counter(cat(rep, cfg, t) for t in AUTO)
            por_cfg[cfg][rep] = {k: cuenta.get(k, 0) for k in ("CORRECTO", "INCORRECTO", "NO_CONCLUYENTE", "FALLO_SEGURIDAD")}
    por_categoria = {}
    for cfg in CFGS:
        for nombre in sorted({v for t, v in tareas_cat.items() if t in AUTO}):
            ts = [t for t in AUTO if tareas_cat[t] == nombre]
            por_categoria[f"{cfg}/{nombre}"] = {"tareas": ts, "CORRECTO": [sum(cat(rep, cfg, t) == "CORRECTO" for t in ts) for rep in (1, 2)]}
    tabla = {t: {cfg: [cat(1, cfg, t), cat(2, cfg, t)] for cfg in CFGS} for t in TAREAS}
    estable = {cfg: [t for t in TAREAS if cat(1, cfg, t) != cat(2, cfg, t)] for cfg in CFGS}
    pares = {}
    for a, b in (("E3", "S1x3"), ("E3", "S1"), ("S1x3", "S1")):
        reps = {}
        for rep in (1, 2):
            ca = {t for t in AUTO if cat(rep, a, t) == "CORRECTO"}
            cb = {t for t in AUTO if cat(rep, b, t) == "CORRECTO"}
            fa = sum(cat(rep, a, t) == "FALLO_SEGURIDAD" for t in AUTO)
            fb = sum(cat(rep, b, t) == "FALLO_SEGURIDAD" for t in AUTO)
            reps[rep] = {"correctos": [len(ca), len(cb)], "diferencia": len(ca) - len(cb), "solo_" + a: sorted(ca - cb),
                         "solo_" + b: sorted(cb - ca), "fallos_seguridad": [fa, fb], "signos_p": signos(len(ca - cb), len(cb - ca))}
        supera = all(r["diferencia"] >= 3 and r["fallos_seguridad"][0] <= r["fallos_seguridad"][1] for r in reps.values())
        inferior = all(-r["diferencia"] >= 3 and r["fallos_seguridad"][1] <= r["fallos_seguridad"][0] for r in reps.values())
        pares[f"{a}_vs_{b}"] = {"repeticiones": reps, "regla_prerregistrada": f"{a} supera a {b}" if supera else (
            f"{b} supera a {a}" if inferior else "sin diferencia demostrable con esta muestra"),
            "nota": "regla OPERATIVA (≥ 3 CORRECTO más en las dos repeticiones y sin más FALLO_SEGURIDAD); no demuestra superioridad estadística"}
    rec = ("E3 no supera a S1×3 → la recomendación prerregistrada es SIMPLIFICAR el equipo (menos agentes o roles con herramientas "
           "distintas), no ampliarlo" if pares["E3_vs_S1x3"]["regla_prerregistrada"] != "E3 supera a S1x3" else
           "E3 supera a S1×3: se informan por separado el resultado y el tiempo por respuesta correcta")
    return {"metrica_principal": "CORRECTO en T01–T13 (T14–T15: revisión ciega aparte)", "por_configuracion_y_repeticion": por_cfg,
            "por_categoria_de_tarea": por_categoria, "tabla_por_tarea[rep1, rep2]": tabla, "tareas_que_cambian_entre_repeticiones": estable,
            "inestables(>2 tareas)": [c for c, v in estable.items() if len([t for t in v if t in AUTO]) > 2],
            "comparaciones": pares, "recomendacion_prerregistrada": rec}


def analisis_b(f1: Path, filas):
    pares, cambios = [], Counter()
    for rep in (1, 2):
        for t in TAREAS:
            d = f1 / f"r{rep}" / "E3" / t / RUTA_E3
            crudo = (d / "agentes/01_A1_fs_generar.txt").read_bytes()
            inf = json.loads((d / "informe.json").read_text(encoding="utf-8"))
            s1, e3 = filas[(rep, "S1", t)], filas[(rep, "E3", t)]
            v1 = inf["versiones"][0]["archivos"]["solucion.py"]
            ig_crudo = sha(crudo) == s1["muestras"][0]["texto_sha256"]
            ig_codigo = sha((s1["respuesta"]["codigo"] or "").encode("utf-8")) == v1
            final = inf["version_recomendada"]["version"]
            cs, ce = s1["evaluacion"]["categoria"], e3["evaluacion"]["categoria"]
            if cs == ce:
                rumbo = "sin_cambio"
            elif cs == "CORRECTO":
                rumbo = "error_introducido"
            elif ce == "CORRECTO":
                rumbo = "error_corregido"
            else:
                rumbo = "cambia_entre_no_correctas"
            pares.append({"rep": rep, "tarea": t, "borrador_igual_a_S1_texto_sha256": ig_crudo, "borrador_igual_a_S1_codigo_sha256": ig_codigo,
                          "prompt_igual_en_S1_S1x3_E3": len({filas[(rep, c, t)]["prompt_primer_paso_sha256"] for c in CFGS}) == 1,
                          "versiones_E3": len(inf["versiones"]), "version_final_E3": final, "codigo_final_distinto_del_borrador": final != 1,
                          "motivo_E3": e3["e3"]["motivo"], "aceptada_E3": e3["e3"]["aceptada"], "S1": cs, "E3_final": ce, "rumbo": rumbo})
            cambios[rumbo] += 1
    n = len(pares)
    return {"pares_analizados": n,
            "borradores_identicos_a_S1(texto SHA-256)": sum(p["borrador_igual_a_S1_texto_sha256"] for p in pares),
            "borradores_identicos_a_S1(codigo SHA-256)": sum(p["borrador_igual_a_S1_codigo_sha256"] for p in pares),
            "borradores_distintos": n - sum(p["borrador_igual_a_S1_texto_sha256"] for p in pares),
            "mismo_prompt_en_los_tres_metodos": sum(p["prompt_igual_en_S1_S1x3_E3"] for p in pares),
            "E3_termina_con_el_codigo_del_borrador": sum(not p["codigo_final_distinto_del_borrador"] for p in pares),
            "E3_recomienda_un_codigo_distinto": sum(p["codigo_final_distinto_del_borrador"] for p in pares),
            "versiones_por_ejecucion": dict(Counter(p["versiones_E3"] for p in pares)),
            "motivos_de_cierre_E3": dict(Counter(p["motivo_E3"] for p in pares)),
            "errores_corregidos": cambios["error_corregido"], "errores_introducidos": cambios["error_introducido"],
            "sin_cambio_de_categoria": cambios["sin_cambio"], "cambia_entre_no_correctas": cambios["cambia_entre_no_correctas"],
            "ejecuciones_con_error_introducido": [(p["rep"], p["tarea"]) for p in pares if p["rumbo"] == "error_introducido"],
            "aceptadas_por_E3": sum(bool(p["aceptada_E3"]) for p in pares), "detalle": pares}


def analisis_c(f1: Path, filas):
    llamadas = []
    recortes, finish = [], Counter()
    for rep in (1, 2):
        for t in TAREAS:
            fila = filas[(rep, "E3", t)]
            if fila["metricas"].get("recortes_prompt"):
                recortes.append({"rep": rep, "tarea": t, "recortes": fila["metricas"]["recortes_prompt"]})
            inf = json.loads((f1 / f"r{rep}" / "E3" / t / RUTA_E3 / "informe.json").read_text(encoding="utf-8"))
            for i, c in enumerate(inf["metricas_llamadas"], 1):
                finish[c["finish_reason"]] += 1
                llamadas.append({"rep": rep, "tarea": t, "n": i, **{k: c[k] for k in ("fase", "agente", "max_tokens", "tokens_prompt", "tokens_gen", "finish_reason")}})
    cortadas = [x for x in llamadas if x["finish_reason"] == "length"]
    sin_fin = Counter()
    for (rep, cfg, t), f in filas.items():
        if cfg == "S1x3":
            for m in f["muestras"]:
                sin_fin[bool((m.get("texto") or "").rstrip().endswith("FIN"))] += 1
    return {"ctx": 2048, "llamadas_E3": len(llamadas), "finish_reason_E3": dict(finish),
            "max_tokens_prompt_E3": max(x["tokens_prompt"] for x in llamadas),
            "max_prompt+max_tokens_E3": max(x["tokens_prompt"] + x["max_tokens"] for x in llamadas),
            "generaciones_cortadas_por_tope_de_tokens": len(cortadas),
            "cortadas_por_fase": dict(Counter((x["fase"], x["agente"], x["max_tokens"]) .__repr__() for x in cortadas)),
            "tareas_con_generacion_cortada": sorted({x["tarea"] for x in cortadas}),
            "cortadas_detalle": cortadas, "ejecuciones_E3_con_recorte_de_contexto": recortes,
            "omitidos_en_alguna_llamada": sum(bool(r["omitidos"]) for x in recortes for r in x["recortes"]),
            "nota_S1_S1x3": "finish_reason por llamada no se registra en S1/S1×3; sus textos son cortos (≈46–50 tokens generados de media frente a un "
                            "tope de 560) y las muestras sin «FIN» (%d de 90 en S1×3) son respuestas de pocas líneas o rechazos, no cortes"
                            % sin_fin[False]}


def analisis_d(f1: Path, c, filas):
    t = defaultdict(lambda: defaultdict(float))
    correctos = Counter()
    for (rep, cfg, tarea), f in filas.items():
        th, m = f["termica"], f["metricas"]
        d = t[cfg]
        for k in ("generacion_s", "enfriamiento_s", "trabajo_s", "total_s"):
            d[k] += th.get(k) or 0
        d["espera_humana_s"] += th.get("espera_humana_s") or 0
        d["peticiones"] += th["peticiones"]
        d["peticiones_con_enfriamiento>1s"] += sum((p.get("enfriamiento_s") or 0) > 1 for p in m["peticiones"])
        d["intentos_interrumpidos"] += len(f.get("intentos_interrumpidos") or [])
        d["carga_servidor_s"] += m["carga_s"]
        d["tokens_prompt"] += m["tokens_prompt"]
        d["tokens_generados"] += m["tokens_generados"]
        d["pico_C"] = max(d["pico_C"], th["pico_C"] or 0)
        d["VmHWM_max_MiB"] = max(d["VmHWM_max_MiB"], m["servidor_VmHWM_kB_max"] / 1024)
        d["MemAvailable_min_MiB"] = min(d["MemAvailable_min_MiB"] or 1e12, m["MemAvailable_min_kB"] / 1024)
        d["VRAM_max_MiB"] = max(d["VRAM_max_MiB"], f["vram"]["maxima_MiB"])
        d["majflt_max_por_tarea"] = max(d["majflt_max_por_tarea"], max(m["majflt_windows"] or [0]))
        if f["evaluacion"]["categoria"] == "CORRECTO" and tarea in AUTO:
            correctos[cfg] += 1
    res = {}
    for cfg in CFGS:
        d = {k: (round(v, 1) if isinstance(v, float) else v) for k, v in t[cfg].items()}
        n = correctos[cfg]
        d["CORRECTO_T01_T13_en_2_repeticiones"] = n
        d["trabajo_s_por_correcta"] = round(t[cfg]["trabajo_s"] / n, 1) if n else None
        d["total_s_por_correcta(incluye_enfriamiento)"] = round(t[cfg]["total_s"] / n, 1) if n else None
        res[cfg] = d
    termica, bloques, lectura = c["termica"], c["bloques"], Counter()
    for line in (f1 / "termica.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        for k in ("freno_hw_termico", "freno_sw_termico", "freno_hw", "freno_hw_potencia"):
            lectura[k] += bool(r.get(k))
        lectura["critico"] += bool(r.get("critico"))
        lectura["lecturas"] += 1
        lectura["lecturas>=80C"] += r["temp_C"] >= 80
    return {"por_configuracion": res, "inicio": c["inicio"], "fin": c["fin"],
            "duracion_min": round((__import__("datetime").datetime.fromisoformat(c["fin"]) - __import__("datetime").datetime.fromisoformat(c["inicio"])).total_seconds() / 60, 1),
            "termica": {"critico": termica["critico"], "temp_maxima_C": termica["temp_maxima_C"], "lecturas": termica["lecturas"],
                        "freno_sw_total_s": termica["freno_sw_total_s"], "interferencias_externas": termica["interferencias_externas"],
                        "conteo_en_termica_jsonl": dict(lectura)},
            "pausas": {"total": len(c["pausas"]), "con_motivo_(persona/recursos/termica)": sum(bool(p["motivos"]) for p in c["pausas"]),
                       "suma_s": round(sum(p["esperado_s"] for p in c["pausas"]), 1), "max_s": max(p["esperado_s"] for p in c["pausas"]),
                       "nota": "las pausas sin motivo son la comprobación previa de cada tarea (≈9 s, PC libre y recursos); no son esperas por personas"},
            "VRAM_ajena_por_bloque_MiB": [b["G2"]["vram_otras_MiB"] for b in bloques], "tope_ajena_MiB": c["limites"]["vram_otras_max_MiB"]}


def analisis_e(c, filas, f1: Path):
    inc = defaultdict(list)
    for (rep, cfg, t), f in filas.items():
        s = f["evaluacion"]
        if s["categoria"] == "FALLO_SEGURIDAD" or s["seguridad"] != "seguro":
            inc[cfg].append({"rep": rep, "tarea": t, "seguridad": s["seguridad"], "categoria": s["categoria"], "motivo": s["motivo"][:120],
                             "problemas": s.get("problemas_seguridad")})
    cuenta = {cfg: dict(Counter((f["evaluacion"]["seguridad"]) for (r, cc, t), f in filas.items() if cc == cfg and t in AUTO)) for cfg in CFGS}
    fallos = {cfg: sorted({x["tarea"] for x in inc[cfg] if x["categoria"] == "FALLO_SEGURIDAD"}) for cfg in CFGS}
    integridad = {
        "filas": len(c["filas"]), "filas_unicas(rep,config,tarea)": len({(f["repeticion"], f["configuracion"], f["tarea"]) for f in c["filas"]}),
        "abortada": c.get("abortada"), "valida": c.get("valida"),
        "infraestructura_distinta_de_null": sum(bool(f.get("infraestructura")) for f in c["filas"]),
        "interrupciones_por_terceros": sum(f["interrupciones_por_terceros"] for f in c["filas"]),
        "intentos_interrumpidos": sum(len(f.get("intentos_interrumpidos") or []) for f in filas.values()),
        "llama_efectiva_ok(29/29 capas, ub 128, sin --fit)": sum(bool(f["llama_efectiva"]["ok"]) for f in filas.values()),
        "servidor_cerrado_limpio": sum(bool(f["servidor_terminado"]) and bool(f["cierre"]["limpio"]) for f in filas.values()),
        "VRAM_excedida": sum(bool(f["vram"]["excedida"]) for f in filas.values()),
        "espera_previa_ok": sum(bool(f["espera_previa"]["ok"]) for f in filas.values()),
        "fondo_animado": [(x["t"], x["accion"], x.get("ok")) for x in c["fondo_animado"]], "fondo_restaurado": c.get("fondo_restaurado"),
        "STOP": (f1 / "STOP").exists(),
        "prompts_identicos_entre_repeticiones(S1,S1x3,E3)": {cfg: sum(
            [p["sha256"] for p in filas[(1, cfg, t)]["metricas"]["peticiones"]] == [p["sha256"] for p in filas[(2, cfg, t)]["metricas"]["peticiones"]]
            for t in TAREAS) for cfg in CFGS},
        "respuesta_identica_entre_repeticiones(S1,S1x3,E3)": {cfg: sum(
            filas[(1, cfg, t)]["respuesta"]["codigo"] == filas[(2, cfg, t)]["respuesta"]["codigo"] for t in TAREAS) for cfg in CFGS},
        "configuracion_de_muestreo": {cfg: sorted({(p["temperatura"], p["semilla"], p["max_tokens"]) for (r, cc, t), f in filas.items()
                                                    if cc == cfg for p in f["metricas"]["peticiones"]}) for cfg in CFGS}}
    return {"fallos_de_seguridad_por_metodo(tareas)": fallos, "seguridad_T01_T13(conteo de filas)": cuenta, "incidentes": dict(inc),
            "integridad": integridad}


def main(argv=None) -> int:
    f1 = Path(argv[0] if argv else RAIZ / "evidencias/v31_f1_vram_exp_v4_5_1/f1_comparacion1")
    c, filas = cargar(f1)
    tareas = json.loads((RAIZ / "evaluacion_f1/tareas_f1.json").read_text(encoding="utf-8"))["tareas"]
    cat = {t["id"]: t["categoria"] for t in tareas}
    out = {"variante": c["variante"], "carpeta": str(f1), "A_calidad": analisis_a(filas, cat), "B_agentes": analisis_b(f1, filas),
           "C_contexto": analisis_c(f1, filas), "D_eficiencia": analisis_d(f1, c, filas), "E_seguridad": analisis_e(c, filas, f1)}
    destino = f1.parent / "analisis"
    destino.mkdir(exist_ok=True)
    (destino / "analisis_f1_v4_5_1.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"analisis escrito en {destino / 'analisis_f1_v4_5_1.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
