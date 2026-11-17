"""Compara evidencia completa, verifica líneas y conserva fallos por tarea."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import statistics
import time

import worker


def parse_evidence(text):
    """Recupera posiciones de ambos formatos sin importar ni ejecutar el código."""
    lines, output, current, i = text.split('\n'), {}, None, 0
    while i < len(lines):
        line = lines[i]
        header = re.fullmatch(r'# (.*?) sha256:([0-9a-f]{64})', line)
        if header:
            current = header.group(1)
        elif current:
            numbered = re.fullmatch(r'L(\d+): (.*)', line)
            interval = re.fullmatch(r'L(\d+)-L(\d+):', line)
            if numbered:
                key = current, int(numbered.group(1))
                value = numbered.group(2)
                if key in output and output[key] != value:
                    raise ValueError('Línea duplicada con contenido distinto')
                output[key] = value
            elif interval and i + 1 < len(lines) and lines[i+1].endswith('python'):
                fence = lines[i+1][:-6]
                if len(fence) < 3 or len(set(fence)) != 1 or fence[0] not in '~`':
                    raise ValueError('Cerca inválida')
                start, end = int(interval.group(1)), int(interval.group(2))
                if end < start:
                    raise ValueError('Rango inverso')
                for number in range(start, end + 1):
                    i += 1
                    if i + 1 >= len(lines):
                        raise ValueError('Rango incompleto')
                    value = lines[i+1]
                    key = current, number
                    if key in output and output[key] != value:
                        raise ValueError('Línea duplicada con contenido distinto')
                    output[key] = value
                i += 2
                if i >= len(lines) or lines[i] != fence:
                    raise ValueError('Cerca no cerrada')
        i += 1
    return output


def source_coverage(root, db, result):
    """Compara con fuente verificada y redactada cada función y soporte emitido."""
    from contexto_core.safety import read_verified, decode_source, redact
    parsed, source_cache, missing = parse_evidence(result['text']), {}, []
    def check(path, start, end, expected_lines=None):
        if path not in source_cache:
            raw, record = read_verified(root, db, path)
            source_cache[path] = redact(decode_source(raw, python=path.endswith('.py')), python=path.endswith('.py'))[0]
        for number in range(start, end + 1):
            expected = source_cache[path][number-1]
            if expected_lines is not None and expected_lines[number-start] != expected:
                missing.append([path, number, 'support_mismatch'])
            if parsed.get((path, number)) != expected:
                missing.append([path, number, 'not_rendered_or_changed'])
    for item in result['selected']:
        check(item['path'], item['start'], item['end'])
    for item in result.get('support', []):
        for region in item['ranges']:
            check(item['path'], region['start'], region['end'], region['lines'])
    for item in result.get('imported_support', []):
        for source in item['files']:
            for region in source['ranges']:
                check(source['path'], region['start'], region['end'], region['lines'])
    return {'ok': not missing, 'missing_or_changed': missing, 'lines_parsed': len(parsed)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', type=Path, required=True)
    parser.add_argument('--corpus', type=Path, required=True)
    parser.add_argument('--tasks', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--tokenizer-json', type=Path)
    parser.add_argument('--budget', type=int, default=16000)
    parser.add_argument('--dependencies', type=int, default=8)
    parser.add_argument('--max-evidence', type=int, default=100)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    engine = worker.load_engine(args.engine.resolve())
    if args.tokenizer_json:
        from tokenizers import Tokenizer
        worker.TOKENIZER = Tokenizer.from_file(str(args.tokenizer_json))
        worker.TOKENIZER.no_padding(); worker.TOKENIZER.no_truncation()
        worker.TOKENIZER_INFO = {'library': 'tokenizers', 'sha256': hashlib.sha256(args.tokenizer_json.read_bytes()).hexdigest(),
                                 'scope': 'texto GPT-2, sin plantilla chat'}
    specification = json.loads(args.tasks.read_text())
    corpus = args.corpus.resolve()
    worker.validate_oracles(corpus, specification['tasks'])
    hashes_before = worker.corpus_hashes(corpus)
    db = engine.connect(args.output / 'index.sqlite3')
    tasks = []
    try:
        engine.scan(corpus, db)
        for task in specification['tasks']:
            samples, result, error = [], None, None
            for _ in range(3):
                start = time.perf_counter()
                try:
                    result = engine.build_bundle(corpus, db, task['query'], args.budget, limit=12,
                                                 required=[task['evidence']], dependencies=args.dependencies,
                                                 max_evidence=args.max_evidence, include_tests=False)
                except (ValueError, OSError) as exc:
                    error = type(exc).__name__ + ': ' + str(exc)
                    result = None
                    break
                finally:
                    samples.append(time.perf_counter() - start)
            symbols = {(row['path'], row['symbol']) for row in result['selected']} if result else set()
            expected = {tuple(x) for x in task['relevant']}
            coverage = source_coverage(corpus, db, result) if result else None
            text = result['text'] if result else ''
            if result:
                (args.output / (task['id'] + '.bundle.txt')).write_text(text)
            tasks.append({'id': task['id'], 'error': error, 'symbols': sorted(symbols),
                          'precision': len(symbols & expected) / len(symbols) if symbols else 0,
                          'recall': len(symbols & expected) / len(expected),
                          'missing_symbols': sorted(expected - symbols), 'text': worker.measure_text(text) if result else None,
                          'source_coverage': coverage, 'median_seconds': statistics.median(samples),
                          'budget_compliant': len(text) <= args.budget * 3 if result else None,
                          'static_calls_included': result.get('indexed_dependencies_included') if result else False,
                          'unresolved_count': len(result.get('dependency_plan', {}).get('unresolved', [])) if result else None,
                          'line_formats': result.get('source_line_formats') if result else None})
    finally:
        db.close()
    result = {'version': args.version, 'tasks_sha256': hashlib.sha256(args.tasks.read_bytes()).hexdigest(),
              'procedure': f'misma consulta y requisito; {args.budget} tokens estimados; limit12; '
                           f'depth{args.dependencies}; max_evidence{args.max_evidence}; sin pruebas auxiliares',
              'corpus_unchanged': hashes_before == worker.corpus_hashes(corpus), 'tasks': tasks,
              'macro_precision': statistics.mean(x['precision'] for x in tasks),
              'macro_recall': statistics.mean(x['recall'] for x in tasks),
              'failures': sum(x['error'] is not None for x in tasks),
              'line_integrity_failures': sum(x['source_coverage'] is not None and not x['source_coverage']['ok'] for x in tasks),
              'peak_process_rss_bytes': worker.rss_bytes()}
    (args.output/'metrics.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k != 'tasks'},ensure_ascii=False))
    return 0 if result['corpus_unchanged'] and result['line_integrity_failures'] == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
