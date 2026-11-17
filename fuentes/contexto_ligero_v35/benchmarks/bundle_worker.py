"""Comparación suplementaria de evidencia completa en los seis flujos congelados."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import time

import worker


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', type=Path, required=True)
    parser.add_argument('--corpus', type=Path, required=True)
    parser.add_argument('--tasks', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--tokenizer-json', type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    engine = worker.load_engine(args.engine.resolve())
    if args.tokenizer_json:
        from tokenizers import Tokenizer
        worker.TOKENIZER = Tokenizer.from_file(str(args.tokenizer_json))
        worker.TOKENIZER.no_padding()
        worker.TOKENIZER.no_truncation()
        worker.TOKENIZER_INFO = {'library': 'tokenizers',
                                 'sha256': hashlib.sha256(args.tokenizer_json.read_bytes()).hexdigest(),
                                 'scope': 'texto GPT-2, no plantilla chat'}
    specification = json.loads(args.tasks.read_text())
    corpus = args.corpus.resolve()
    manifest = lambda: {p.relative_to(corpus).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in corpus.rglob('*') if p.is_file()}
    before = manifest()
    db = engine.connect(args.output / 'index.sqlite3')
    results = []
    try:
        engine.scan(corpus, db)
        for task in specification['tasks']:
            samples, result, error = [], None, None
            for _ in range(3):
                start = time.perf_counter()
                try:
                    result = engine.build_bundle(corpus, db, task['query'], 4000, limit=12,
                                                 required=[task['evidence']], dependencies=1,
                                                 max_evidence=32, include_tests=False)
                except (ValueError, OSError) as exc:
                    error = type(exc).__name__ + ': ' + str(exc)
                    result = None
                    break
                finally:
                    samples.append(time.perf_counter() - start)
            symbols = {(row['path'], row['symbol']) for row in result['selected']} if result else set()
            truth = {tuple(pair) for pair in task['relevant']}
            text = result['text'] if result else ''
            if result:
                (args.output / (task['id'] + '.txt')).write_text(text)
            results.append({'id': task['id'], 'error': error, 'symbols': sorted(symbols),
                            'precision': len(symbols & truth) / len(symbols) if symbols else 0,
                            'recall': len(symbols & truth) / len(truth),
                            'missing_symbols': sorted(truth - symbols),
                            'text': worker.measure_text(text) if result else None,
                            'median_seconds': statistics.median(samples),
                            'budget_compliant': len(text) <= 4000 * 3 if result else None})
    finally:
        db.close()
    report = {'version': args.version, 'tasks_sha256': hashlib.sha256(args.tasks.read_bytes()).hexdigest(),
              'procedure': 'mismas consultas y requisitos; 4000 tokens estimados, limit12, dependencies1, max_evidence32, sin tests auxiliares',
              'scope': 'seis flujos congelados, evidencia de sus cinco funciones; no tareas LLM ni estado dinámico',
              'corpus_unchanged': manifest() == before, 'tasks': results,
              'macro_precision': statistics.mean(t['precision'] for t in results),
              'macro_recall': statistics.mean(t['recall'] for t in results),
              'failures': sum(t['error'] is not None for t in results),
              'characters': sum(t['text']['characters'] for t in results if t['text']),
              'estimated_tokens': sum(t['text']['estimated_tokens'] for t in results if t['text']),
              'measured_tokens': sum(t['text']['measured_tokens'] for t in results if t['text']) if worker.TOKENIZER else None,
              'mean_median_seconds': statistics.mean(t['median_seconds'] for t in results),
              'peak_process_rss_bytes': worker.rss_bytes()}
    (args.output / 'metrics.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'tasks'}, ensure_ascii=False))
    return 0 if report['corpus_unchanged'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
