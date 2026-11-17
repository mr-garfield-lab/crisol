"""Validación integral reproducible V3.4/V3.5 sin instalaciones ni red."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import statistics
import sys
import uuid

import EJECUTAR_PRUEBAS as previous

ROOT = Path(__file__).resolve().parent.parent
FROZEN_MANIFESTS = {
    'benchmarks/CONGELACION_V35.json': 'f9b37a68ff24b92df6d9594dd4c93c5b4b2f9ceafe5863dcbd5efda9642590c3',
    'benchmarks/CONGELACION_V34.json': 'b7627868aa5b8fe27d94a56903a1137a7b0a8300af7653b0b978223067dbc2cd',
    'benchmarks/CONGELACION_INDEPENDIENTE.json': 'ec794dda0c4d5e274b8ebc80439b6c5c86228db138c45f4d6797cfa5a6400488',
    'comparacion/v34/SHA256_BASELINE_V34.json': 'fdf88448b931ff3835d497a81fcf9f033705fa9405fbc12163d0a4c88636873c',
    'comparacion/v331/SHA256_BASELINE.json': 'c83b95159b76aed9dd1b334f4a4d6ff2a0c826286df8f37e15bebb80c7d7888f',
    'sha256_originales.json': '32ad0a64e475ea006489019e2677a69c6a6806f1f9abef657521df129f5575a2',
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def v34_integrity():
    root = ROOT/'comparacion/v34'
    manifest = json.loads((root/'SHA256_BASELINE_V34.json').read_text())
    changed = [name for name, digest in manifest.items() if not (root/name).is_file() or sha(root/name) != digest]
    extra = sorted({p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
                   - set(manifest) - {'SHA256_BASELINE_V34.json'})
    return {'ok': not changed and not extra, 'checked_files':len(manifest), 'changed':changed, 'extra':extra}


def v35_corpus_integrity():
    base = ROOT/'benchmarks'
    manifest_path = base/'CONGELACION_V35.json'
    manifest = json.loads(manifest_path.read_text())
    changed = [name for name, digest in manifest['tasks_sha256'].items()
               if not (base/name).is_file() or sha(base/name) != digest]
    corpus = base/'fixtures/generalizacion_v35'
    changed += ['corpus:' + name for name, digest in manifest['corpus_sha256'].items()
                if not (corpus/name).is_file() or sha(corpus/name) != digest]
    extras = sorted({p.relative_to(corpus).as_posix() for p in corpus.rglob('*') if p.is_file()}
                    - set(manifest['corpus_sha256']))
    return {'ok':not changed and not extras, 'changed':changed, 'extra':extras,
            'manifest_sha256':sha(manifest_path), 'frozen_at':manifest['created_utc']}


def integrity():
    changed=[name for name,digest in FROZEN_MANIFESTS.items()
             if not (ROOT/name).is_file() or sha(ROOT/name)!=digest]
    return {'originales':previous.original_integrity(), 'baseline_v331':previous.baseline_integrity(),
            'baseline_v34':v34_integrity(), 'tareas_v331':previous.independent_integrity(),
            'tareas_v34':previous.frozen_v34_integrity(), 'tareas_v35':v35_corpus_integrity(),
            'manifiestos_congelados':{'ok':not changed, 'changed':changed}}


def quality(comparison):
    old, new = comparison['V3.4'], comparison['V3.5']
    regressions = []
    for task, current in new['tasks'].items():
        before = old['tasks'][task]
        for field in ('recall_at_10', 'packet_recall', 'packet_file_recall'):
            if current[field] is not None and before[field] is not None and current[field] + 1e-12 < before[field]:
                regressions.append({'task':task, 'metric':field, 'before':before[field], 'after':current[field]})
    return {'precision_returned_before':old['macro_precision_returned'],
            'precision_returned_after':new['macro_precision_returned'],
            'precision_returned_target':0.5, 'target_met':new['macro_precision_returned'] >= 0.5,
            'precision_at_5_before':old['macro_precision_at_5'], 'precision_at_5_after':new['macro_precision_at_5'],
            'recall_at_10_before':old['macro_recall_at_10'], 'recall_at_10_after':new['macro_recall_at_10'],
            'packet_precision_before':old['macro_packet_precision'], 'packet_precision_after':new['macro_packet_precision'],
            'packet_recall_before':old['macro_packet_recall'], 'packet_recall_after':new['macro_packet_recall'],
            'regressions':regressions}


def bundle_comparison(items):
    """Suma textos solo en tareas emparejadas con ambos oráculos recuperados."""
    versions = {item['version']:item for item in items}
    if set(versions) != {'V3.4','V3.5'}:
        return {'complete':False, 'versions':versions}
    before, after = versions['V3.4'], versions['V3.5']
    pairs = []
    right = {t['id']:t for t in after['tasks']}
    for left in before['tasks']:
        new = right[left['id']]
        comparable = (left['error'] is None and new['error'] is None and left['recall'] == 1 and new['recall'] == 1
                      and left['source_coverage']['ok'] and new['source_coverage']['ok'])
        pairs.append({'id':left['id'], 'comparable':comparable,
                      'before_error':left['error'], 'after_error':new['error'],
                      'before_recall':left['recall'], 'after_recall':new['recall'],
                      'before_precision':left['precision'], 'after_precision':new['precision'],
                      'before_tokens':left['text']['measured_tokens'] if left['text'] else None,
                      'after_tokens':new['text']['measured_tokens'] if new['text'] else None,
                      'before_estimated':left['text']['estimated_tokens'] if left['text'] else None,
                      'after_estimated':new['text']['estimated_tokens'] if new['text'] else None,
                      'before_symbols':left['symbols'], 'after_symbols':new['symbols'],
                      'before_static_calls_included':left['static_calls_included'],
                      'after_static_calls_included':new['static_calls_included']})
    comparable = [p for p in pairs if p['comparable']]
    def total(key):
        return sum(p[key] for p in comparable) if comparable and all(p[key] is not None for p in comparable) else None
    return {'complete':True, 'procedure':before['procedure'], 'total_tasks':len(pairs),
            'comparable_complete_tasks':len(comparable), 'task_results':pairs,
            'before_failures':before['failures'], 'after_failures':after['failures'],
            'before_line_integrity_failures':before['line_integrity_failures'],
            'after_line_integrity_failures':after['line_integrity_failures'],
            'before_macro_precision':before['macro_precision'], 'after_macro_precision':after['macro_precision'],
            'before_macro_recall':before['macro_recall'], 'after_macro_recall':after['macro_recall'],
            'before_measured_tokens_comparable':total('before_tokens'), 'after_measured_tokens_comparable':total('after_tokens'),
            'before_estimated_tokens_comparable':total('before_estimated'), 'after_estimated_tokens_comparable':total('after_estimated')}


def markdown(report):
    fmt = lambda x: 'no medido' if x is None else f'{x:.6f}' if isinstance(x,float) else str(x)
    out = ['# Evaluación reproducible V3.4 / V3.5', '',
           f"UTC: {report['created_utc']} · Integridad y pruebas: **{report['status']}** · Objetivos: **{report['quality_status']}**", '',
           'PASS técnico no significa que se haya alcanzado el 50% ni que Python dinámico esté resuelto.', '',
           'Mismas tareas, corpus, consultas, límites, presupuestos, oráculos y fórmulas para ambas versiones. P@5 permanece idéntica; precisión devuelta cuenta todos los símbolos. Oráculos reales mínimos pueden infravalorar dependencias útiles.', '',
           'Tres muestras de cada consulta/paquete por proceso; medianas de las repeticiones por versión. Los buscadores y benchmarks no ejecutan ni importan el proyecto indexado. Las pruebas de integración sí importan componentes de la referencia y usan un backend simulado.', '',
           '| Comprobación | Resultado |', '|---|---|']
    for k,v in report['integrity_after'].items(): out.append(f"| {k} | {v['ok']} |")
    out += ['', '| Ejecución | Código | Segundos | Log |', '|---|---:|---:|---|']
    for cmd in report['commands']: out.append(f"| {cmd['label']} | {cmd['returncode']} | {cmd['seconds']:.3f} | [{cmd['log']}]({cmd['log']}) |")
    fields=[('Precisión devuelta','macro_precision_returned'), ('Precision@5','macro_precision_at_5'),
            ('Recall@10','macro_recall_at_10'), ('Precisión mapa','macro_packet_precision'),
            ('Recall mapa','macro_packet_recall'), ('Recall archivos mapa','macro_packet_file_recall'),
            ('Recall dependencias etiquetadas','macro_known_dependency_recall'),
            ('Caracteres mapa','total_packet_characters'), ('Tokens ESTIMADOS mapa','total_packet_estimated_tokens'),
            ('Tokens MEDIDOS mapa','total_packet_measured_tokens'), ('Tokens MEDIDOS mapa + mismo snippet','total_packet_plus_same_snippet_measured_tokens'),
            ('Consulta ms, media de medianas','mean_query_median_ms'), ('Mapa ms, media de medianas','mean_packet_median_ms'),
            ('Indexación nueva s','cold_scan_median_seconds'), ('Indexación sin cambios s','warm_scan_median_seconds'),
            ('Pico RSS proceso bytes','peak_process_rss_median_bytes'), ('SQLite bytes','database_median_bytes')]
    for name,c in report['comparisons'].items():
        if not {'V3.4','V3.5'} <= set(c): continue
        a,b=c['V3.4'],c['V3.5']
        out += ['',f'## {name}','','| Medida | V3.4 | V3.5 |','|---|---:|---:|']
        for label,key in fields: out.append(f'| {label} | {fmt(a[key])} | {fmt(b[key])} |')
        out += ['', '| Tarea | Precisión devuelta antes/después | Recall@10 antes/después | Recall mapa antes/después | Tokens mapa medidos antes/después |', '|---|---:|---:|---:|---:|']
        for tid,x in a['tasks'].items():
            y=b['tasks'][tid]
            pair=lambda field: fmt(x[field])+' / '+fmt(y[field])
            out.append(f"| {tid} | {pair('precision_returned')} | {pair('recall_at_10')} | {pair('packet_recall')} | {pair('packet_measured_tokens')} |")
        out += ['', 'Regresiones de recall y archivo:', '', '```json',json.dumps(report['quality'][name]['regressions'],ensure_ascii=False,indent=2),'```']
    out += ['', '## Evidencia completa: bundle', '',
            'Una ejecución por versión y conjunto, tres muestras por tarea. Tokens solo se suman en tareas emparejadas donde ambas versiones devuelven todas las respuestas etiquetadas y sus líneas verificadas; se informan errores y exclusiones. Los fallos nunca cuentan como ahorro.', '',
            '| Conjunto | Completas emparejadas | Fallos V3.4/V3.5 | Precisión V3.4/V3.5 | Recall V3.4/V3.5 | Tokens MEDIDOS V3.4/V3.5 | Tokens ESTIMADOS V3.4/V3.5 |', '|---|---:|---:|---:|---:|---:|---:|']
    for name,b in report['bundles'].items():
        if not b.get('complete'): continue
        out.append(f"| {name} | {b['comparable_complete_tasks']}/{b['total_tasks']} | {b['before_failures']}/{b['after_failures']} | {fmt(b['before_macro_precision'])}/{fmt(b['after_macro_precision'])} | {fmt(b['before_macro_recall'])}/{fmt(b['after_macro_recall'])} | {fmt(b['before_measured_tokens_comparable'])}/{fmt(b['after_measured_tokens_comparable'])} | {fmt(b['before_estimated_tokens_comparable'])}/{fmt(b['after_estimated_tokens_comparable'])} |")
    for name,b in report['bundles'].items():
        if not b.get('complete'): continue
        out += ['',f'### {name}: resultados completos por tarea','','```json',json.dumps(b['task_results'],ensure_ascii=False,indent=2),'```']
    out += ['', '## Alcance y límites', '',
            f"- Primera evaluación de tareas congeladas V3.5 en esta copia: {report['first_new_tasks_evaluation']}. Las pruebas originales y V3.4 son desarrollo; si se modifica el motor después de ver tareas nuevas, una reevaluación ya no es ciega.",
            '- P@5 de Equipo IA tiene techo del 40%; el objetivo del 50% es de la métrica diferente precisión devuelta. No se altera ningún denominador ni se excluyen dependencias.',
            '- El nuevo conjunto real tiene juicios mínimos manuales; el sintético contiene responsabilidades, distractores y dependencias conocidas, no es un proyecto externo de producción.',
            '- GPT-2 es un tokenizador local real para el texto medido, no el consumo exacto de Claude/GPT. Sin biblioteca opcional solo se ofrecen estimaciones explícitas.',
            '- Completar las líneas de los símbolos y llamadas estáticas indexadas no prueba todas las dependencias dinámicas, los datos de ejecución ni la corrección de una tarea LLM.',
            '- El rendimiento depende de caché del SO. RSS incluye proceso completo y tokenizador. Termux físico e integración con modelos reales siguen pendientes.', '']
    return '\n'.join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--repeticiones',type=int,default=3)
    ap.add_argument('--salida',type=Path,default=ROOT/'resultados')
    ap.add_argument('--tokenizer-json',type=Path)
    ap.add_argument('--solo-desarrollo',action='store_true')
    args=ap.parse_args()
    if not 1 <= args.repeticiones <= 10: ap.error('repeticiones debe estar entre 1 y 10')
    stamp=datetime.now(timezone.utc)
    folder=args.salida.resolve()/(stamp.strftime('%Y%m%dT%H%M%S')+'_'+uuid.uuid4().hex[:8])
    folder.mkdir(parents=True,exist_ok=False)
    print(f'Resultados: {folder}',flush=True)
    before=integrity(); sources_before=previous.active_source_hashes()
    if not all(value['ok'] for value in before.values()):
        (folder/'integridad_fallida.json').write_text(json.dumps(before,ensure_ascii=False,indent=2))
        return 1
    prior=[]
    for path in (ROOT/'resultados').glob('*/report_v35.json'):
        try:
            if 'nuevas_reales_v35' in json.loads(path.read_text()).get('comparisons',{}): prior.append(str(path))
        except (ValueError,OSError): continue
    commands=[]
    for label,engine in [('regresion_original_v34',ROOT/'comparacion/v34'),('regresion_original_v35',ROOT)]:
        commands.append(previous.run([sys.executable,'-B','-c',previous.LEGACY_BOOTSTRAP,str(engine),
                                      str(ROOT/'referencia_original/motor_v32')],folder,label))
    commands.append(previous.run([sys.executable,'-B','-m','unittest','discover','-s','tests','-p','test_*.py','-v'],folder,'regresion_v35'))
    demo=[sys.executable,'-B',str(ROOT/'benchmarks/demo_v331.py'),'--output',str(folder/'demo_perfiles_delta')]
    if args.tokenizer_json: demo+=['--tokenizer-json',str(args.tokenizer_json.resolve())]
    commands.append(previous.run(demo,folder,'presupuestos_y_delta'))
    long_demo=[sys.executable,'-B',str(ROOT/'benchmarks/demo_simbolo_largo_v35.py'),
               '--output',str(folder/'demo_simbolo_largo')]
    if args.tokenizer_json: long_demo+=['--tokenizer-json',str(args.tokenizer_json.resolve())]
    commands.append(previous.run(long_demo,folder,'simbolo_largo_explicito'))
    datasets=[('equipo_ia',ROOT/'referencia_original/equipo_ia_referencia',ROOT/'benchmarks/tasks.json'),
              ('sintetico_anterior',ROOT/'benchmarks/fixtures/proyecto_independiente',ROOT/'benchmarks/tasks_independientes.json'),
              ('reales_v34',ROOT/'referencia_original/equipo_ia_referencia',ROOT/'benchmarks/tasks_v34_reales.json'),
              ('flujos_v34',ROOT/'benchmarks/fixtures/flujos_v34',ROOT/'benchmarks/tasks_v34_flujos.json')]
    if not args.solo_desarrollo:
        datasets += [('nuevas_reales_v35',ROOT/'referencia_original/equipo_ia_referencia',ROOT/'benchmarks/tasks_v35_reales.json'),
                     ('nuevas_sinteticas_v35',ROOT/'benchmarks/fixtures/generalizacion_v35',ROOT/'benchmarks/tasks_v35_sinteticas.json')]
    versions=[('V3.4',ROOT/'comparacion/v34/contexto_v3.py'),('V3.5',ROOT/'contexto_v3.py')]
    workers={name:[] for name,_,_ in datasets}; bundles={}
    for dataset, corpus, tasks in datasets:
        for repetition in range(args.repeticiones):
            for version,engine in (versions if repetition % 2 == 0 else list(reversed(versions))):
                label=f"mapas_{dataset}_{version.replace('.','')}_r{repetition+1}"
                dest=folder/label
                command=[sys.executable,'-B',str(ROOT/'benchmarks/worker.py'),'--engine',str(engine),
                         '--corpus',str(corpus),'--tasks',str(tasks),'--output',str(dest),'--version',version]
                if args.tokenizer_json: command+=['--tokenizer-json',str(args.tokenizer_json.resolve())]
                commands.append(previous.run(command,folder,label,timeout=300))
                if (dest/'metrics.json').is_file(): workers[dataset].append(json.loads((dest/'metrics.json').read_text()))
        bundled=[]
        for version,engine in versions:
            label=f"bundle_{dataset}_{version.replace('.','')}";dest=folder/label
            command=[sys.executable,'-B',str(ROOT/'benchmarks/bundle_full_worker_v35.py'),'--engine',str(engine),
                     '--corpus',str(corpus),'--tasks',str(tasks),'--output',str(dest),'--version',version]
            if dataset=='flujos_v34': command+=['--budget','4000','--dependencies','1','--max-evidence','32']
            if args.tokenizer_json: command+=['--tokenizer-json',str(args.tokenizer_json.resolve())]
            commands.append(previous.run(command,folder,label,timeout=300))
            if (dest/'metrics.json').is_file(): bundled.append(json.loads((dest/'metrics.json').read_text()))
        bundles[dataset]=bundle_comparison(bundled)
    after=integrity(); sources_after=previous.active_source_hashes()
    comparisons={name:previous.aggregate(values) for name,values in workers.items()}
    quality_report={name:quality(c) for name,c in comparisons.items() if {'V3.4','V3.5'}<=set(c)}
    old_names={'equipo_ia','sintetico_anterior','reales_v34','flujos_v34'}
    checks={'workers_complete':all(len(v)==2*args.repeticiones for v in workers.values()),
            'source_unchanged_during_run':sources_before==sources_after,
            'corpora_unchanged':all(w.get('corpus_unchanged',False) for values in workers.values() for w in values),
            'budgets_respected':all(t['packet_budget_compliant'] for values in workers.values() for w in values for t in w['tasks']),
            'snippets_available':all(t['snippet_error'] is None for values in workers.values() for w in values for t in w['tasks']),
            'bundle_workers_complete':all(b.get('complete',False) for b in bundles.values()),
            'bundle_source_lines_verified':all(b.get('before_line_integrity_failures',1)==0 and b.get('after_line_integrity_failures',1)==0 for b in bundles.values()),
            'old_bundle_no_recall_regressions':all(
                b.get('complete',False) and all(t['after_recall'] + 1e-12 >= t['before_recall']
                                                for t in b['task_results'])
                for n,b in bundles.items() if n in old_names),
            'old_recall_no_regressions':all(not quality_report.get(n,{}).get('regressions',[1]) for n in old_names)}
    passed=all(v['ok'] for v in before.values()) and all(v['ok'] for v in after.values()) and all(c['returncode']==0 for c in commands) and all(checks.values())
    met=(quality_report.get('equipo_ia',{}).get('target_met',False) and checks['old_recall_no_regressions'])
    report={'created_utc':stamp.isoformat(),'status':'PASS' if passed else 'FAIL',
            'quality_status':'GOAL_50_MET_AND_RECALL_PRESERVED' if met else 'PARTIAL_OR_NOT_MET',
            'first_new_tasks_evaluation':not prior if not args.solo_desarrollo else None,'prior_new_task_reports':prior,
            'repetitions_requested':args.repeticiones,'development_only':args.solo_desarrollo,
            'integrity_before':before,'integrity_after':after,'source_sha256_before':sources_before,'source_sha256':sources_after,
            'commands':commands,'checks':checks,'comparisons':comparisons,'quality':quality_report,'bundles':bundles,
            'python':sys.version,'platform':platform.platform(),'tokenizer_json':str(args.tokenizer_json.resolve()) if args.tokenizer_json else None,
            'llm_accuracy_measured':False,'termux_physically_validated':False}
    (folder/'report_v35.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    (folder/'report_v35.md').write_text(markdown(report))
    print(f"{report['status']} / {report['quality_status']}: {folder/'report_v35.md'}",flush=True)
    return 0 if passed else 1


if __name__=='__main__':
    raise SystemExit(main())
