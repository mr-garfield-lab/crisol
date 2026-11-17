"""F1-V5 — DIAGNÓSTICO (no es una evaluación) del aborto por «fuga del oráculo» en T08, E3 qwen3+yi (equipo1, r1).

    python -B -X utf8 eq3/lanzador_eq2.py lab_vram/diagnostico_fuga_t08_v5.py EXTERNOS evidencias/v31_f1_v5/diagnostico_t08

Repite UNA vez T08 con el mismo código, cerebros, E2 y seguridad de V5 (verificación SHA-256, enfriamiento antes de cada
petición, vigías, persona, Wallpaper Engine en pausa, STOP) y registra, ANTES de decidir, cada prompt que llega al control
de fugas, su resultado y, si hay fuga, en qué bloque aparece el literal y si había una respuesta propia que lo contenía.
La lógica de protección NO cambia: si vuelve a detectar la fuga, aborta igual; aquí solo se guarda lo que la provocó.
Con temperatura 0 y semilla fija, F1 mostró repeticiones idénticas: se espera reproducir el mismo caso.
"""
import json
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))


def main(argv) -> int:
    from eq3 import evaluar_f1 as EV
    from eq3 import evaluar_f1_v5 as V
    from eq3 import servidor_pc
    B = V.B
    externos, salida = Path(argv[0]), Path(argv[1])
    if salida.exists():
        raise SystemExit(f"ya existe {salida}: no se sobrescribe")
    salida.mkdir(parents=True)
    servidor_pc.preparar_proceso()
    tareas, oraculos = EV.E.cargar()
    diario, original = [], B.fugas_con_procedencia

    def espiar(prompt, oraculos_, respuestas=(), configuracion=None):
        fugas, relevos = original(prompt, oraculos_, respuestas, configuracion)
        entrada = {"n": len(diario) + 1, "prompt": prompt, "fugas": fugas, "relevos": relevos,
                   "respuestas_previas_sha256": [r["sha256"] for r in respuestas]}
        if fugas:                                         # dónde está el literal y qué bloque lo contiene
            textos = B.textos_oraculo(oraculos_)
            entrada["bloques"] = [{"fuente": f, "contiene_literal": any(B._norm(t) in B._norm(c) for _, t in textos if t),
                                   "inicio": c[:400]} for f, c in B._BLOQUE.findall(prompt)]
            entrada["literal_en_respuestas_propias"] = [any(B._norm(t) in r["norm"] for _, t in textos if t) for r in respuestas]
        diario.append(entrada)
        (salida / "diario_control_fugas.json").write_text(json.dumps(diario, ensure_ascii=False, indent=1),
                                                          encoding="utf-8")
        return fugas, relevos
    res = {"inicio": time.strftime("%Y-%m-%dT%H:%M:%S"), "tarea": "T08", "cerebros": {"generador": "qwen3",
                                                                                     "revisor": "yi"}}
    B.fugas_con_procedencia = espiar
    B._STOP_GLOBAL = salida / "STOP"
    termica = B.nueva_termica(salida / "termica.jsonl")
    try:
        with V.entorno_v5(), B.termica_activa(termica.iniciar()), \
                B.fondo_gestionado(B.FondoAnimado(marca=salida / "fondo_detenido.marca")) as fondo:
            espera = B.esperar_v45(fondo, pausas=[])
            if not espera["ok"]:
                raise EV.Abortada(f"no se inicia: {espera['motivos']}")
            vers = {}
            for rol, m in (("generador", "qwen3"), ("revisor", "yi")):
                ok2, vers[rol] = V.g2(externos, m)
                if not ok2["ok"]:
                    raise EV.Abortada(f"G2 {m}: {ok2}")
            vigia = B.VigiaTermica(act=B.actividad_vigia).iniciar()
            try:
                fila = B.ejecutar_tarea_e2("E3", tareas["T08"], oraculos["T08"], oraculos, salida / "T08",
                                           V.fabrica_dos(vers["generador"], vers["revisor"]), vigia)
                res["resultado"] = {"categoria": fila["evaluacion"]["categoria"], "motivo": fila["evaluacion"]["motivo"]}
            finally:
                res["vigia"] = vigia.detener()
    except EV.FugaDeOraculo as e:
        res["resultado"] = {"fuga_reproducida": str(e)}
    except EV.Abortada as e:
        res["abortada"] = str(e)
    finally:
        B.fugas_con_procedencia = original
        termica.detener()
        B._STOP_GLOBAL = None
        res["termica"], res["llama_al_final"] = termica.resumen(), servidor_pc.procesos_llama()
        res["prompts_vistos"] = len(diario)
        res["fin"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        (salida / "diagnostico.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str),
                                                 encoding="utf-8")
    print(json.dumps({k: res.get(k) for k in ("resultado", "abortada", "prompts_vistos", "llama_al_final")},
                     ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
