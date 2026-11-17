"""V4.3 (laboratorio). Uso: python -B -X utf8 lab_vram/repetir_prompts_f1_v4_3.py [CARPETA_TMP]

Repite, SIN modelo, los prompts reales de E3 guardados en la F1 abortada (V4.2) con el detector estable y el de V4.3.
Para T10 reconstruye el prompt bloqueado del paso 2 con el mismo armado de V2-F.1 (no se guardó: no se llegó a enviar)."""
import json, sys
from pathlib import Path
R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "pruebas"))
import comun  # noqa
from eq3 import evaluar_f1 as EV
from eq3 import evaluar_f1_vram_exp_v4_3 as V

_, oraculos = EV.E.cargar()
base = R / "evidencias/v31_f1_vram_exp_v4/f1_comparacion1/r1/E3"
filas = []
for tdir in sorted(base.iterdir()):
    for f in sorted(tdir.glob("intento*/equipo_f2/lab_v2f1/tareas/*/ejecuciones/*/funcion")):
        respuestas = []
        for p in sorted((f / "prompts").glob("*.txt")):
            texto = p.read_text(encoding="utf-8")
            est = EV.E.fugas_de_oraculo(texto, oraculos)
            v43, relevos = V.fugas_con_procedencia(texto, oraculos, respuestas, "E3")
            filas.append({"tarea": tdir.name, "prompt": p.name, "estable": est, "v4_3": v43,
                          "relevos": [(r["etiqueta"], r["fuente"], r["respuesta"]) for r in relevos]})
            a = f / "agentes" / p.name
            if a.is_file():
                s = a.read_text(encoding="utf-8")
                respuestas.append({"norm": V._norm(s), "sha256": __import__("hashlib").sha256(s.encode()).hexdigest()})
out = {"prompts_reales": len(filas),
       "con_fuga_estable": [f for f in filas if f["estable"]],
       "con_fuga_v4_3": [f for f in filas if f["v4_3"]],
       "relevos_verificados": [f for f in filas if f["relevos"]],
       "v4_3_igual_a_estable_si_no_hay_relevo": all(f["estable"] == f["v4_3"] for f in filas if not f["relevos"])}
import hashlib, tempfile
import aux_procedencia_v4_3 as A
tareas, _ = EV.E.cargar()
real_a1 = next(base.glob("T10/intento1/equipo_f2/lab_v2f1/tareas/*/ejecuciones/*/funcion/agentes/01_A1_fs_generar.txt"))
a1 = real_a1.read_text(encoding="utf-8")
out["T10_salida_real_A1_sha256"] = hashlib.sha256(a1.encode()).hexdigest()
out["T10_igual_que_la_prueba"] = a1 == A.A1_T10
EV.preparar_contexto()
for modo in ("estable", "v4_3"):
    be = A.Guion({"A1": a1})
    vig = EV.Vigia(medir=lambda: None, intervalo=0.05).iniciar()
    try:
        t = Path(tempfile.mkdtemp(dir=sys.argv[1] if len(sys.argv) > 1 else None))
        if modo == "v4_3":
            with V._protector_v43("E3"):
                f = EV.ejecutar_tarea("E3", tareas["T10"], oraculos["T10"], oraculos, t / "E3", lambda: be, vig)
        else:
            f = EV.ejecutar_tarea("E3", tareas["T10"], oraculos["T10"], oraculos, t / "E3", lambda: be, vig)
        out[f"T10_{modo}"] = {"fuga": None, "prompts_enviados": len(be.prompts),
                              "categoria": f["evaluacion"]["categoria"],
                              "relevos": [r for p in f["metricas"]["peticiones"] for r in p.get("relevos_verificados", [])]}
    except EV.FugaDeOraculo as e:
        out[f"T10_{modo}"] = {"fuga": str(e), "prompts_enviados": len(be.prompts)}
    finally:
        vig.detener()
print(json.dumps(out, ensure_ascii=False, indent=1))
