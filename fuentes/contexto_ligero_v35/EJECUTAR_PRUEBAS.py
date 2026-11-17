#!/usr/bin/env python3
"""Regresion y benchmark reproducibles, offline; cada ejecucion conserva sus resultados."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import sqlite3
import statistics
import subprocess
import sys
import time
import uuid

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent

LEGACY_BOOTSTRAP = r'''
import importlib.util, pathlib, sys, unittest
sys.dont_write_bytecode = True
engine_dir, tests_dir = map(pathlib.Path, sys.argv[1:3])
sys.path.insert(0, str(engine_dir))
import contexto_v3
suite = unittest.TestSuite()
for name in ('test_contexto_v3', 'test_contexto_v31', 'test_contexto_v32'):
    spec = importlib.util.spec_from_file_location(name, tests_dir / (name + '.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(mod))
result = unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(not result.wasSuccessful())
'''


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def original_integrity():
    manifest = json.loads((ROOT / "sha256_originales.json").read_text(encoding="utf-8"))
    base = ROOT / "referencia_original"
    missing, changed = [], []
    for rel, expected in manifest["archivos"].items():
        target = base / rel
        if not target.is_file():
            missing.append(rel)
        elif digest(target) != expected:
            changed.append(rel)
    actual = {p.relative_to(base).as_posix() for p in base.rglob("*") if p.is_file()}
    added = sorted(actual - set(manifest["archivos"]))
    return {"ok": not (missing or changed or added), "checked_files": len(manifest["archivos"]),
            "missing": missing, "changed": changed, "added": added,
            "input_zip_sha256": manifest["zip_sha256"]}


def baseline_integrity():
    base = ROOT / 'comparacion' / 'v331'
    manifest = json.loads((base / 'SHA256_BASELINE.json').read_text(encoding='utf-8'))
    missing = [rel for rel in manifest if not (base / rel).is_file()]
    changed = [rel for rel, sha in manifest.items() if (base / rel).is_file() and digest(base / rel) != sha]
    extras = sorted({p.relative_to(base).as_posix() for p in base.rglob('*') if p.is_file()}
                    - set(manifest) - {'SHA256_BASELINE.json'})
    return {'ok': not (missing or changed or extras), 'checked_files': len(manifest), 'missing': missing, 'changed': changed, 'extra': extras}


def independent_integrity():
    base = ROOT / 'benchmarks'
    manifest = json.loads((base / 'CONGELACION_INDEPENDIENTE.json').read_text(encoding='utf-8'))
    corpus = base / 'fixtures' / 'proyecto_independiente'
    changed = [rel for rel, sha in manifest['corpus_sha256'].items()
               if not (corpus / rel).is_file() or digest(corpus / rel) != sha]
    extras = sorted({p.relative_to(corpus).as_posix() for p in corpus.rglob('*') if p.is_file()}
                    - set(manifest['corpus_sha256']))
    tasks_ok = digest(base / 'tasks_independientes.json') == manifest['tasks_sha256']
    return {'ok': tasks_ok and not changed and not extras, 'tasks_ok': tasks_ok, 'changed': changed, 'extra': extras,
            'tasks_sha256': manifest['tasks_sha256']}


def frozen_v34_integrity():
    base = ROOT / 'benchmarks'
    manifest = json.loads((base / 'CONGELACION_V34.json').read_text(encoding='utf-8'))
    changed = [rel for rel, sha in manifest['files_sha256'].items()
               if not (base / rel).is_file() or digest(base / rel) != sha]
    corpus = base / 'fixtures' / 'flujos_v34'
    changed += ['corpus:' + rel for rel, sha in manifest['synthetic_corpus_sha256'].items()
                if not (corpus / rel).is_file() or digest(corpus / rel) != sha]
    extras = sorted({p.relative_to(corpus).as_posix() for p in corpus.rglob('*') if p.is_file()}
                    - set(manifest['synthetic_corpus_sha256']))
    return {'ok': not changed and not extras, 'changed': changed, 'extra': extras,
            'frozen_at': manifest['created_utc'], 'manifest_sha256': digest(base / 'CONGELACION_V34.json')}


def active_source_hashes():
    hashes = {}
    for path in sorted(ROOT.rglob('*.py')):
        rel = path.relative_to(ROOT)
        if not {'referencia_original', 'resultados', '__pycache__', 'comparacion', 'historial'}.intersection(rel.parts):
            hashes[rel.as_posix()] = digest(path)
    return hashes


def run(command, folder, label, timeout=300):
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    # Permite dependencias opcionales previamente autorizadas en un target local.
    env["PYTHONPATH"] = os.pathsep.join(filter(None, (str(ROOT), env.get('PYTHONPATH', ''))))
    start = time.perf_counter()
    try:
        completed = subprocess.run(command, cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, encoding="utf-8", errors="replace", timeout=timeout)
        output, code = completed.stdout, completed.returncode
    except subprocess.TimeoutExpired as exc:
        raw = exc.stdout or b""
        output = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
        output += "\nERROR: limite de tiempo excedido.\n"
        code = 124
    (folder / (label + ".log")).write_text(output, encoding="utf-8")
    result = {"label": label, "command": command, "command_shell_display": shlex.join(command),
              "returncode": code, "seconds": time.perf_counter() - start, "log": label + ".log"}
    print(f"{label}: {'OK' if code == 0 else 'FALLO'} ({result['seconds']:.3f} s)", flush=True)
    return result


def median(values):
    values = [x for x in values if x is not None]
    return statistics.median(values) if values else None


def complete_median(values):
    """No convertir mediciones parciales en un resultado aparentemente completo."""
    values = list(values)
    if not values or any(value is None for value in values):
        return None
    return statistics.median(values)


def aggregate(results):
    output = {}
    for version in ("V3.2", "V3.3-validada", "V3.3", "V3.3.1", "V3.4", "V3.5"):
        items = [result for result in results if result["version"] == version]
        if not items:
            continue
        tasks = {}
        for task in items[0]["tasks"]:
            samples = [next(x for x in result["tasks"] if x["id"] == task["id"]) for result in items]
            tasks[task["id"]] = {
                "query": task["query"],
                "precision_at_5": median(x["selection"]["precision_at_5"] for x in samples),
                "precision_at_5_ceiling": complete_median(x['selection'].get('precision_at_5_ceiling') for x in samples),
                "precision_returned": complete_median(x['selection'].get('precision_returned') for x in samples),
                "returned_symbols": complete_median(x['selection'].get('retrieved_symbols') for x in samples),
                "returned_true_positives": complete_median(x['selection'].get('true_positives_returned') for x in samples),
                "packet_precision": complete_median(x.get('package_selection', {}).get('packet_precision') for x in samples),
                "packet_symbols_count": complete_median(x.get('package_selection', {}).get('packet_symbols_count') for x in samples),
                "ranked_packet_precision": complete_median(x.get('package_selection', {}).get('ranked_packet_precision') for x in samples),
                "known_dependency_recall": complete_median(x.get('package_selection', {}).get('known_dependency_recall') for x in samples),
                "packet_file_recall": complete_median(x.get('package_selection', {}).get('packet_file_recall') for x in samples),
                "recall_at_10": median(x["selection"]["recall_at_10"] for x in samples),
                "reciprocal_rank": median(x["selection"]["reciprocal_rank"] for x in samples),
                "packet_recall": median(x["packet_recall"] for x in samples),
                "packet_characters": median(x["packet"]["characters"] for x in samples),
                "packet_estimated_tokens": median(x["packet"]["estimated_tokens"] for x in samples),
                "packet_measured_tokens": complete_median(x["packet"]["measured_tokens"] for x in samples),
                "packet_plus_snippet_characters": median(x["packet_plus_same_requested_snippet"]["characters"] for x in samples),
                "packet_plus_snippet_estimated_tokens": median(x["packet_plus_same_requested_snippet"]["estimated_tokens"] for x in samples),
                "packet_plus_snippet_measured_tokens": complete_median(x["packet_plus_same_requested_snippet"]["measured_tokens"] for x in samples),
                "query_median_ms": median(x["query_timing"]["median_seconds"] * 1000 for x in samples),
                "packet_median_ms": median(x["packet_timing"]["median_seconds"] * 1000 for x in samples),
                "budget_compliant_all_repetitions": all(x["packet_budget_compliant"] for x in samples),
                "snippet_errors": [x["snippet_error"] for x in samples if x["snippet_error"]],
            }
        values = list(tasks.values())
        output[version] = {
            "repetitions": len(items),
            "cold_scan_median_seconds": median(x["cold_scan"]["median_seconds"] for x in items),
            "warm_scan_median_seconds": median(x["warm_scan"]["median_seconds"] for x in items),
            "peak_process_rss_median_bytes": median(x["peak_process_rss_bytes"] for x in items),
            "database_median_bytes": median(x["database_bytes"] for x in items),
            "mean_query_median_ms": statistics.mean(x['query_median_ms'] for x in values),
            "mean_packet_median_ms": statistics.mean(x['packet_median_ms'] for x in values),
            "macro_precision_at_5": statistics.mean(x["precision_at_5"] for x in values),
            "macro_precision_at_5_ceiling": statistics.mean(x['precision_at_5_ceiling'] for x in values)
                if all(x['precision_at_5_ceiling'] is not None for x in values) else None,
            "macro_precision_returned": statistics.mean(x['precision_returned'] for x in values)
                if all(x['precision_returned'] is not None for x in values) else None,
            "macro_packet_precision": statistics.mean(x['packet_precision'] for x in values)
                if all(x['packet_precision'] is not None for x in values) else None,
            "macro_known_dependency_recall": statistics.mean(x['known_dependency_recall'] for x in values)
                if all(x['known_dependency_recall'] is not None for x in values) else None,
            "macro_packet_file_recall": statistics.mean(x['packet_file_recall'] for x in values)
                if all(x['packet_file_recall'] is not None for x in values) else None,
            "macro_recall_at_10": statistics.mean(x["recall_at_10"] for x in values),
            "mean_reciprocal_rank": statistics.mean(x["reciprocal_rank"] for x in values),
            "macro_packet_recall": statistics.mean(x["packet_recall"] for x in values),
            "total_packet_characters": sum(x["packet_characters"] for x in values),
            "total_packet_estimated_tokens": sum(x["packet_estimated_tokens"] for x in values),
            "total_packet_measured_tokens": sum(x["packet_measured_tokens"] for x in values)
                if all(x["packet_measured_tokens"] is not None for x in values) else None,
            "total_packet_plus_same_snippet_characters": sum(x["packet_plus_snippet_characters"] for x in values),
            "total_packet_plus_same_snippet_estimated_tokens": sum(x["packet_plus_snippet_estimated_tokens"] for x in values),
            "total_packet_plus_same_snippet_measured_tokens": sum(x["packet_plus_snippet_measured_tokens"] for x in values)
                if all(x["packet_plus_snippet_measured_tokens"] is not None for x in values) else None,
            "tasks": tasks,
        }
    return output


def pct_delta(before, after):
    return None if not before else (after / before - 1) * 100


def comparison_table(comparison, left='V3.3-validada', right='V3.3'):
    """Tabla adicional; V3.3 etiqueta la edición nueva para compatibilidad JSON."""
    a, b = comparison.get(left), comparison.get(right)
    if not a or not b:
        return []
    fields = [
        ('Recall@10', 'macro_recall_at_10'), ('Precision@5', 'macro_precision_at_5'),
        ('Cobertura paquete', 'macro_packet_recall'), ('Caracteres mapas', 'total_packet_characters'),
        ('Tokens ESTIMADOS mapas', 'total_packet_estimated_tokens'),
        ('Tokens MEDIDOS mapas', 'total_packet_measured_tokens'),
        ('Caracteres mapa + fragmento', 'total_packet_plus_same_snippet_characters'),
        ('Query ms, media de medianas por tarea', 'mean_query_median_ms'),
        ('Packet ms, media de medianas por tarea', 'mean_packet_median_ms'),
        ('Scan nuevo s, mediana', 'cold_scan_median_seconds'),
        ('Scan sin cambios s, mediana', 'warm_scan_median_seconds'),
        ('Pico RSS bytes, mediana', 'peak_process_rss_median_bytes'),
        ('Base SQLite bytes', 'database_median_bytes'),
    ]
    lines = [f'| Medida | {left} | {right} (3.3.1) | Cambio relativo |', '|---|---:|---:|---:|']
    for label, key in fields:
        x, y = a.get(key), b.get(key)
        fmt = lambda value: 'null' if value is None else f'{value:.6f}' if isinstance(value, float) else str(value)
        delta = pct_delta(x, y) if x is not None and y is not None else None
        lines.append(f'| {label} | {fmt(x)} | {fmt(y)} | {"n/a" if delta is None else f"{delta:+.2f}%"} |')
    return lines


def markdown(report):
    if 'V3.4' in report['comparison']:
        return markdown_v34(report)
    repetitions = report.get("repetitions_requested")
    command = "python EJECUTAR_PRUEBAS.py" + (f" --repeticiones {repetitions}" if repetitions is not None else "")
    if report.get('tokenizer_json'):
        command += ' --tokenizer-json ' + shlex.quote(report['tokenizer_json'])
    completed = "; ".join(f"{version}: {data['repetitions']}" for version, data in report["comparison"].items())
    lines = ["# Resultados reproducibles Contexto Ligero V3.3", "",
             f"Fecha UTC: {report['created_utc']}. Estado: **{report['status']}**.", "",
             f"Comando: `{command}`. Procesos nuevos completados: {completed or 'ninguno'}.",
             "", "## Verificacion", "",
             f"Originales intactos antes/despues: {report['integrity_before']['ok']} / {report['integrity_after']['ok']} "
             f"({report['integrity_after']['checked_files']} archivos).",
             "", "| Ejecucion | Codigo | Segundos | Log |", "|---|---:|---:|---|"]
    for item in report["commands"]:
        lines.append(f"| {item['label']} | {item['returncode']} | {item['seconds']:.3f} | [{item['log']}]({item['log']}) |")
    a, b = report["comparison"].get("V3.2"), report["comparison"].get("V3.3")
    if a and b:
        lines += ["", "## Comparacion con las mismas doce tareas", "",
                  "Oraculos minimos manuales en `benchmarks/tasks.json`, fijados antes de ejecutar el benchmark. "
                  "Precisión y recall miden recuperacion de simbolos, **no correccion de respuestas de Claude/Codex**. "
                  "El oraculo no es exhaustivo: un resultado fuera de el puede ser util.", "",
                  "| Medida | V3.2 | V3.3 |", "|---|---:|---:|"]
        fields = [("Precision@5 (macro)", "macro_precision_at_5"), ("Recall@10 (macro)", "macro_recall_at_10"),
                  ("MRR", "mean_reciprocal_rank"), ("Recall del paquete (macro)", "macro_packet_recall"),
                  ("Caracteres de mapas (suma)", "total_packet_characters"),
                  ("Tokens ESTIMADOS de mapas (suma ceil(chars/3))", "total_packet_estimated_tokens"),
                  ("Caracteres mapa + mismo snippet (suma)", "total_packet_plus_same_snippet_characters"),
                  ("Tokens ESTIMADOS mapa + mismo snippet", "total_packet_plus_same_snippet_estimated_tokens"),
                  ("Scan base nueva, segundos (mediana)", "cold_scan_median_seconds"),
                  ("Scan sin cambios, segundos (mediana)", "warm_scan_median_seconds"),
                  ("Pico RSS proceso, bytes (mediana)", "peak_process_rss_median_bytes"),
                  ("SQLite bytes (mediana)", "database_median_bytes")]
        if any(data["total_packet_measured_tokens"] is not None for data in (a, b)):
            fields.append(("Tokens MEDIDOS de mapas (suma)", "total_packet_measured_tokens"))
        if any(data.get("total_packet_plus_same_snippet_measured_tokens") is not None for data in (a, b)):
            fields.append(("Tokens MEDIDOS mapa + mismo snippet", "total_packet_plus_same_snippet_measured_tokens"))
        for label, field in fields:
            x, y = a[field], b[field]
            fmt = lambda z: "null" if z is None else f"{z:.6f}" if isinstance(z, float) else str(z)
            lines.append(f"| {label} | {fmt(x)} | {fmt(y)} |")
        change = pct_delta(a["total_packet_characters"], b["total_packet_characters"])
        complete_measurements = all(data["total_packet_measured_tokens"] is not None for data in (a, b))
        any_measurements = any(data["total_packet_measured_tokens"] is not None for data in (a, b))
        token_note = (
            "Tokens medidos de los mapas disponibles para todas las repeticiones. "
            "Tokenizador JSON local identificado por hash en metrics.json; texto sin plantilla chat/tokens especiales, "
            "no acredita equivalencia con Claude/Codex."
            if complete_measurements else
            "**Medicion de tokens incompleta.** Los agregados de una version permanecen en null si falta alguna muestra; "
            "consulte metrics.json para mediciones parciales. No acredita consumo de Claude/Codex."
            if any_measurements else
            "**Tokens medidos con tokenizador real: no disponibles para toda la comparacion (`null`).** "
            "Consulte metrics.json para cualquier muestra parcial. El comando no instala paquetes ni descarga vocabularios. "
            "La estimacion no es el consumo real de Claude, Codex u otros modelos."
        )
        lines += ["", f"Cambio de caracteres de mapas V3.3 frente a V3.2: {change:+.2f}%. "
                  "No se presenta como ahorro total en una tarea completada por un modelo.", "",
                  token_note, "",
                  "| Tarea | Recall@10 V32/V33 | P@5 V32/V33 | Recall paquete V32/V33 | Caracteres V32/V33 | Query ms V32/V33 | Packet ms V32/V33 |",
                  "|---|---:|---:|---:|---:|---:|---:|"]
        for key, x in a["tasks"].items():
            y = b["tasks"][key]
            pair = lambda field, digits=3: f"{x[field]:.{digits}f} / {y[field]:.{digits}f}"
            lines.append(f"| {key} | {pair('recall_at_10')} | {pair('precision_at_5')} | {pair('packet_recall')} | "
                         f"{pair('packet_characters', 0)} | {pair('query_median_ms')} | {pair('packet_median_ms')} |")
    if 'V3.3-validada' in report['comparison']:
        lines += ['', '## Edición nueva frente a la entrega validada', '',
                  '`V3.3` en los datos designa la edición 3.3.1; `V3.3-validada` es la entrega anterior intacta.', '']
        lines += comparison_table(report['comparison'])
    if report.get('independent_comparison'):
        lines += ['', '## Conjunto sintético complementario', '',
                  'Ocho tareas sobre doce archivos propios, declaradas y hasheadas antes de observar sus rankings. '
                  'Es evidencia complementaria de desarrollo, no un corpus externo real ni una evaluación de respuestas LLM.', '']
        lines += comparison_table(report['independent_comparison'])
        lines += ['', '| Versión | Recall@10 | Cobertura paquete | Caracteres mapas |', '|---|---:|---:|---:|']
        for version, values in report['independent_comparison'].items():
            lines.append(f"| {version} | {values['macro_recall_at_10']:.6f} | {values['macro_packet_recall']:.6f} | {values['total_packet_characters']} |")
    lines += ["", "## Alcance y limites", "",
              "- Se usa el corpus completo de referencia para indexar; cada motor aplica su filtro de rutas original.",
              "- Misma consulta, presupuesto de 2000 tokens estimados y limite de 12 archivos candidatos de busqueda. La expansion de dependencias V3.3 puede añadir archivos (hasta cuatro simbolos). Mismo simbolo solicitado para snippet (max_lines=200).",
              "- Cada proceso usa una base SQLite nueva, seguido de un scan sin cambios. La cache del SO no se vacia; base nueva no significa disco frio.",
              "- El orden de las tres versiones rota por repeticion. Los tiempos son perf_counter locales; las comparaciones no tienen significancia estadistica demostrada.",
              "- RSS usa resource.getrusage(RUSAGE_SELF).ru_maxrss: KiB en Linux/Termux y bytes en macOS, convertido a bytes. Es pico del proceso, no RAM incremental de una operacion.",
              "- Los tiempos de query y packet tienen tres muestras por tarea/proceso; se informa la mediana. Las muestras crudas estan en cada metrics.json.",
              "- Mapa + snippet representa una solicitud predefinida de evidencia, no una sesion de modificacion completada ni ahorro neto de inferencia.",
              "- Validacion local con backend simulado: no hay llamadas a modelos, API ni servicios de pago. Si se proporciona tokenizer JSON se cuentan tokens reales de ese vocabulario local. Termux/Samsung requiere ejecutar este comando en el dispositivo.",
              "- Cada corrida crea su propio directorio y conserva bases, textos, logs, hashes, comandos y JSON. Las pruebas limpian exclusivamente sus fixtures temporales.", ""]
    return "\n".join(lines)


def quality_targets(comparison):
    previous, current = comparison.get('V3.3.1'), comparison.get('V3.4')
    if not previous or not current:
        return {'evaluated': False}
    tasks = current['tasks']
    return {
        'evaluated': True,
        'historical_precision_at_5_target': 0.55,
        'precision_at_5_ceiling': current['macro_precision_at_5_ceiling'],
        'precision_at_5_target_feasible': current['macro_precision_at_5_ceiling'] >= 0.55,
        'precision_returned_target': 0.55,
        'precision_returned_achieved': current['macro_precision_returned'],
        'precision_returned_target_met': current['macro_precision_returned'] >= 0.55,
        'recall_at_10_target_met': all(x['recall_at_10'] >= 1.0 - 1e-12 for x in tasks.values()),
        'packet_recall_target_met': all(x['packet_recall'] >= 1.0 - 1e-12 for x in tasks.values()),
        'no_recall_regression_every_task': all(x['recall_at_10'] + 1e-12 >= previous['tasks'][key]['recall_at_10'] for key, x in tasks.items()),
        'no_packet_recall_regression_every_task': all(x['packet_recall'] + 1e-12 >= previous['tasks'][key]['packet_recall'] for key, x in tasks.items()),
        'context_characters_not_increased': current['total_packet_characters'] <= previous['total_packet_characters'],
    }


def markdown_v34(report):
    lines = ['# Comparacion reproducible V3.3.1 / V3.4', '',
             f"Fecha UTC: {report['created_utc']}. Verificaciones tecnicas: **{report['status']}**. Objetivos de calidad: **{report['quality_status']}**.", '',
             'El estado tecnico PASS significa que las pruebas, integridad y procesos terminaron correctamente. No significa que se hayan alcanzado todos los objetivos de precision/recall.', '',
             f"Comando: `python -B EJECUTAR_PRUEBAS.py --repeticiones {report['repetitions_requested']}`" + (' con `--tokenizer-json` local.' if report.get('tokenizer_json') else '.'), '',
             '## Denominadores inmutables', '',
             '**Precision@5 historica permanece intacta.** En las doce tareas originales hay de media dos simbolos relevantes: su techo macro es 2/5 = 40%. Un objetivo de 55% en esa misma metrica no es matematicamente alcanzable sin alterar las respuestas esperadas.', '',
             '**Precision de resultados devueltos** = aciertos contra el oraculo / todos los simbolos devueltos, o 0 si no devuelve ninguno. Se calcula con el mismo codigo para V3.3.1 y V3.4. Es una metrica adicional: sus valores no se comparan directamente con el antiguo 40% de Precision@5.', '',
             '**Precision del paquete** usa todos los simbolos realmente mostrados, incluidas dependencias. No se excluyen dependencias para mejorar el denominador. Los oraculos reales son minimos: resultados no etiquetados pueden ser utiles, por lo que esta precision puede infravalorar evidencia pertinente.', '',
             'La clasificacion uniforme `incluidos_en_ranking` es la interseccion entre paquete y ranking; lo añadido al paquete no se afirma automaticamente como dependencia ni como falso positivo. Las funciones esperadas como dependencias se evaluan solo cuando el conjunto declara un oraculo especifico.', '',
             '## Integridad y pruebas', '',
             '| Comprobacion | Resultado |', '|---|---|']
    for label, field in [('Originales','integrity_after'), ('V3.3.1 inmutable','baseline_integrity_after'), ('Conjunto anterior','independent_integrity_after'), ('Tareas nuevas congeladas','frozen_v34_integrity_after')]:
        lines.append(f"| {label} | {report[field]['ok']} |")
    lines += ['', '| Ejecucion | Codigo | Segundos | Evidencia |', '|---|---:|---:|---|']
    for command in report['commands']:
        lines.append(f"| {command['label']} | {command['returncode']} | {command['seconds']:.3f} | [{command['log']}]({command['log']}) |")
    for name, comparison in report['comparisons'].items():
        a, b = comparison.get('V3.3.1'), comparison.get('V3.4')
        lines += ['', '## Conjunto: ' + name, '',
                  'Tres muestras de consulta/paquete por proceso; las cifras agregan medianas entre procesos. Cada tarea tiene el mismo peso.', '',
                  '| Medida | V3.3.1 | V3.4 |', '|---|---:|---:|']
        if not a or not b:
            lines += ['| Procesos completos | no | no |']
            continue
        fields = [('Precision@5 (sin cambios)','macro_precision_at_5'), ('Techo Precision@5','macro_precision_at_5_ceiling'),
                  ('Precision de resultados devueltos','macro_precision_returned'), ('Recall@10','macro_recall_at_10'),
                  ('Precision del paquete completo','macro_packet_precision'), ('Recall del paquete','macro_packet_recall'),
                  ('Recall de archivos del paquete','macro_packet_file_recall'), ('Recall dependencias etiquetadas','macro_known_dependency_recall'),
                  ('Caracteres mapas, suma','total_packet_characters'), ('Tokens ESTIMADOS mapas','total_packet_estimated_tokens'),
                  ('Tokens MEDIDOS mapas','total_packet_measured_tokens'), ('Tokens MEDIDOS mapa + mismo snippet','total_packet_plus_same_snippet_measured_tokens'),
                  ('Consulta ms, media de medianas por tarea','mean_query_median_ms'), ('Paquete ms, media de medianas por tarea','mean_packet_median_ms'),
                  ('Indexacion nueva s','cold_scan_median_seconds'), ('Indexacion sin cambios s','warm_scan_median_seconds'),
                  ('Pico RSS proceso bytes','peak_process_rss_median_bytes'), ('SQLite bytes','database_median_bytes')]
        fmt = lambda value: 'null / no etiquetado' if value is None else f'{value:.6f}' if isinstance(value,float) else str(value)
        for label,key in fields:
            lines.append(f'| {label} | {fmt(a.get(key))} | {fmt(b.get(key))} |')
        lines += ['', '| Tarea | P@5 antes/despues | P.devuelta antes/despues | R@10 antes/despues | R.paquete antes/despues | Tokens medidos antes/despues |', '|---|---:|---:|---:|---:|---:|']
        for tid, x in a['tasks'].items():
            y = b['tasks'][tid]
            pair=lambda k: fmt(x[k])+' / '+fmt(y[k])
            lines.append(f"| {tid} | {pair('precision_at_5')} | {pair('precision_returned')} | {pair('recall_at_10')} | {pair('packet_recall')} | {pair('packet_measured_tokens')} |")
        target = report['quality_targets'][name]
        lines += ['', 'Objetivos y regresiones (se conservan los resultados desfavorables):', '', '```json', json.dumps(target,ensure_ascii=False,indent=2), '```']
    if report.get('bundle_comparison'):
        lines += ['', '## Evidencia completa: seis flujos congelados', '',
                  'Comparación suplementaria del código entregado por bundle, separada de los mapas. Tres muestras por tarea; mismos parámetros y oráculos. Los errores cuentan como cobertura cero, no como ahorro de tokens.', '',
                  '| Versión | Errores | Precisión símbolos | Recall símbolos | Tokens medidos | Tokens estimados | ms por bundle |',
                  '|---|---:|---:|---:|---:|---:|---:|']
        for item in report['bundle_comparison']:
            lines.append(f"| {item['version']} | {item['failures']} | {item['macro_precision']:.6f} | {item['macro_recall']:.6f} | {item['measured_tokens']} | {item['estimated_tokens']} | {item['mean_median_seconds'] * 1000:.3f} |")
        lines += ['', 'Datos y textos: `bundle_flujos_V331/` y `bundle_flujos_V34/`. No mide una modificación completada por un modelo ni cambia la evaluación principal.']
    lines += ['', '## Limites de la evidencia', '',
              '- Los oraculos historicos y nuevos se verifican por SHA256; no se modifican despues de observar resultados.',
              '- Los nuevos casos reales son juicios minimos manuales. Los seis flujos sinteticos declaran cinco funciones necesarias por flujo, incluyendo cuatro llamadas estaticas, y distractores; no representan un proyecto externo de produccion.',
              f"- Primera evaluacion registrada de las tareas nuevas congeladas en esta carpeta: {report.get('first_frozen_holdout_evaluation')}. Si se vuelve a modificar el motor despues, las reevaluaciones deben describirse como desarrollo, no como ciegas.",
              '- API de recuperacion: search en V3.3.1 y retrieve en V3.4. Se comparan la misma consulta, limite, presupuesto, corpus, oraculo y formula; search de V3.4 queda como compatibilidad historica, no se utiliza para atribuir mejoras a retrieve.',
              '- Presupuesto de seleccion identico de 2000 tokens ESTIMADOS en las tareas comparadas. El tokenizador opcional mide despues el texto exacto de ambas versiones sin cambiar ese criterio.',
              '- Los tokens medidos corresponden al JSON de tokenizacion local identificado por hash, sin plantilla chat implicita; no se afirma equivalencia exacta con Claude/Codex.',
              '- RSS es el pico del proceso entero, incluyendo tokenizador e importaciones; el sistema operativo no vacia su cache entre procesos. No se demuestra significancia estadistica.',
              '- Conservacion de simbolos etiquetados o clausura estatica no prueba que se conserven todas las dependencias dinamicas o que un modelo termine correctamente una tarea.',
              '- No se ejecutan los modulos indexados ni se usan modelos/APIs. Termux fisico y tareas LLM completas siguen pendientes.', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repeticiones', type=int, default=3)
    parser.add_argument('--salida', type=Path, default=ROOT / 'resultados')
    parser.add_argument('--tokenizer-json', type=Path, help='JSON local; nunca instala ni descarga')
    parser.add_argument('--solo-desarrollo', action='store_true', help='Ejecuta solo los dos conjuntos anteriores; no abre las tareas nuevas congeladas')
    args = parser.parse_args()
    if not 1 <= args.repeticiones <= 10:
        parser.error('--repeticiones debe estar entre1 y10')
    stamp=datetime.now(timezone.utc)
    folder=args.salida.resolve()/(stamp.strftime('%Y%m%dT%H%M%S')+'_'+uuid.uuid4().hex[:8])
    folder.mkdir(parents=True,exist_ok=False)
    print(f'Resultados: {folder}',flush=True)
    before=original_integrity(); baseline_before=baseline_integrity(); independent_before=independent_integrity(); frozen_before=frozen_v34_integrity()
    sources_before=active_source_hashes()
    if not all(x['ok'] for x in (before,baseline_before,independent_before,frozen_before)):
        (folder/'integridad_fallida.json').write_text(json.dumps({'original':before,'baseline':baseline_before,'anterior':independent_before,'nuevo':frozen_before},indent=2))
        print('ERROR: materiales congelados alterados; no se ejecutaran.',file=sys.stderr)
        return 1
    prior_holdout=[]
    for file in (ROOT/'resultados').glob('*/report.json'):
        try:
            old=json.loads(file.read_text())
            if 'nuevas_reales' in old.get('comparisons',{}): prior_holdout.append(str(file))
        except (OSError,ValueError):
            continue
    commands=[]
    legacy=ROOT/'referencia_original/motor_v32'; baseline=ROOT/'comparacion/v331'
    for label,engine in [('regresion_original_v32',legacy),('regresion_original_sobre_v331',baseline),('regresion_original_sobre_v34',ROOT)]:
        commands.append(run([sys.executable,'-B','-c',LEGACY_BOOTSTRAP,str(engine),str(legacy)],folder,label))
    commands.append(run([sys.executable,'-B','-m','unittest','discover','-s','tests','-p','test_*.py','-v'],folder,'regresion_v34_integracion'))
    demo_cmd=[sys.executable,'-B',str(ROOT/'benchmarks/demo_v331.py'),'--output',str(folder/'demo_v331')]
    if args.tokenizer_json: demo_cmd+=['--tokenizer-json',str(args.tokenizer_json.resolve())]
    commands.append(run(demo_cmd,folder,'presupuestos_evidencia_delta'))
    datasets=[('equipo_ia',ROOT/'referencia_original/equipo_ia_referencia',ROOT/'benchmarks/tasks.json'),
              ('sintetico_anterior',ROOT/'benchmarks/fixtures/proyecto_independiente',ROOT/'benchmarks/tasks_independientes.json')]
    if not args.solo_desarrollo:
        datasets += [('nuevas_reales',ROOT/'referencia_original/equipo_ia_referencia',ROOT/'benchmarks/tasks_v34_reales.json'),
                     ('flujos_nuevos',ROOT/'benchmarks/fixtures/flujos_v34',ROOT/'benchmarks/tasks_v34_flujos.json')]
    all_workers={name:[] for name,_,_ in datasets}
    for dataset,corpus,tasks_file in datasets:
        for repetition in range(args.repeticiones):
            versions=[('V3.3.1',baseline/'contexto_v3.py'),('V3.4',ROOT/'contexto_v3.py')]
            if repetition%2: versions.reverse()
            for version,source in versions:
                label=f'benchmark_{dataset}_{version.replace(".","")}_r{repetition+1}'
                dest=folder/label
                command=[sys.executable,'-B',str(ROOT/'benchmarks/worker.py'),'--engine',str(source),'--corpus',str(corpus),'--tasks',str(tasks_file),'--output',str(dest),'--version',version]
                if args.tokenizer_json: command+=['--tokenizer-json',str(args.tokenizer_json.resolve())]
                commands.append(run(command,folder,label,timeout=180))
                if (dest/'metrics.json').is_file(): all_workers[dataset].append(json.loads((dest/'metrics.json').read_text()))
    bundle_comparison = []
    if not args.solo_desarrollo:
        for version, source in [('V3.3.1', baseline/'contexto_v3.py'), ('V3.4', ROOT/'contexto_v3.py')]:
            label = 'bundle_flujos_' + version.replace('.', '')
            destination = folder / label
            command = [sys.executable, '-B', str(ROOT/'benchmarks/bundle_worker.py'),
                       '--engine', str(source), '--corpus', str(ROOT/'benchmarks/fixtures/flujos_v34'),
                       '--tasks', str(ROOT/'benchmarks/tasks_v34_flujos.json'), '--output', str(destination),
                       '--version', version]
            if args.tokenizer_json: command += ['--tokenizer-json', str(args.tokenizer_json.resolve())]
            commands.append(run(command, folder, label))
            if (destination/'metrics.json').is_file():
                bundle_comparison.append(json.loads((destination/'metrics.json').read_text()))
    after=original_integrity(); baseline_after=baseline_integrity(); independent_after=independent_integrity(); frozen_after=frozen_v34_integrity()
    comparisons={name:aggregate(workers) for name,workers in all_workers.items()}
    checks={'all_workers_completed':all(len(workers)==2*args.repeticiones for workers in all_workers.values()),
            'indexed_corpora_not_modified':all(worker.get('corpus_unchanged',False) for workers in all_workers.values() for worker in workers),
            'all_new_packet_budgets_compliant':all(all(t['packet_budget_compliant'] for t in worker['tasks']) for workers in all_workers.values() for worker in workers if worker['version']=='V3.4'),
            'all_new_requested_snippets_available':all(all(t['snippet_error'] is None for t in worker['tasks']) for workers in all_workers.values() for worker in workers if worker['version']=='V3.4')}
    source_hashes=active_source_hashes();checks['sources_unchanged_during_run']=source_hashes==sources_before
    if not args.solo_desarrollo:
        checks['bundle_workers_completed'] = len(bundle_comparison) == 2
        checks['bundle_corpora_unchanged'] = all(x['corpus_unchanged'] for x in bundle_comparison)
        checks['bundle_budgets_compliant'] = all(t['budget_compliant'] is not False for x in bundle_comparison for t in x['tasks'])
        checks['new_bundle_flows_complete'] = all(x['failures'] == 0 and x['macro_recall'] == 1.0
                                                  for x in bundle_comparison if x['version'] == 'V3.4')
    success=all(x['ok'] for x in (before,after,baseline_before,baseline_after,independent_before,independent_after,frozen_before,frozen_after)) and all(x['returncode']==0 for x in commands) and all(checks.values())
    targets={name:quality_targets(value) for name,value in comparisons.items()}
    achieved=all(value.get('precision_returned_target_met') and value.get('recall_at_10_target_met')
                 and value.get('packet_recall_target_met') and value.get('no_recall_regression_every_task')
                 and value.get('no_packet_recall_regression_every_task') and value.get('context_characters_not_increased')
                 for value in targets.values())
    workers=[worker for group in all_workers.values() for worker in group]
    report={'schema_version':2,'created_utc':stamp.isoformat(),'status':'PASS' if success else 'FAIL','quality_status':'ALL_ADDITIONAL_TARGETS_MET' if achieved else 'PARTIAL_OR_NOT_MET',
            'quality_targets':targets,'repetitions_requested':args.repeticiones,'development_only':args.solo_desarrollo,
            'first_frozen_holdout_evaluation':not prior_holdout if not args.solo_desarrollo else None,'prior_holdout_reports':prior_holdout,
            'python':sys.version,'platform':platform.platform(),'sqlite':sqlite3.sqlite_version,'cpu_count':os.cpu_count(),'run_directory':str(folder),
            'tasks_sha256':digest(ROOT/'benchmarks/tasks.json'),'source_sha256':source_hashes,'source_sha256_before':sources_before,
            'integrity_before':before,'integrity_after':after,'baseline_integrity_before':baseline_before,'baseline_integrity_after':baseline_after,
            'independent_integrity_before':independent_before,'independent_integrity_after':independent_after,'frozen_v34_integrity_before':frozen_before,'frozen_v34_integrity_after':frozen_after,
            'commands':commands,'benchmark_checks':checks,'comparisons':comparisons,'comparison':comparisons['equipo_ia'],'independent_comparison':comparisons['sintetico_anterior'],
            'bundle_comparison': bundle_comparison,
            'tokenizer_json':str(args.tokenizer_json.resolve()) if args.tokenizer_json else None,
            'version_labels':{'V3.3.1':'entrega previa intacta','V3.4':'nueva arquitectura'},'raw_metrics':[str(p.relative_to(folder)) for p in sorted(folder.glob('benchmark_*/metrics.json'))],
            'llm_accuracy_measured':False,'real_model_tokens_measured':bool(workers) and all(task['packet']['measured_tokens'] is not None for worker in workers for task in worker['tasks']),
            'termux_validated':sys.platform=='linux' and 'com.termux' in sys.executable}
    (folder/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    (folder/'report.md').write_text(markdown(report))
    print(f"{report['status']} / {report['quality_status']}: {folder/'report.md'}",flush=True)
    return 0 if success else 1


if __name__=='__main__':
    from benchmarks.validacion_v35 import main as main_v35
    raise SystemExit(main_v35())
