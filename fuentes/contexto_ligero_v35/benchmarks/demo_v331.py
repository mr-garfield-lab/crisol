"""Escenarios reproducibles de presupuesto/evidencia/delta; no ejecuta el corpus."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.dont_write_bytecode = True
from contexto_v3 import connect, scan, build_packet, build_bundle
from contexto_core.budget import PROFILES, BudgetError, generate_with_budget
from contexto_core.delta import create_snapshot, make_delta, apply_delta, transport_text, transport_metrics
from contexto_core.tokens import TokenCounter


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--tokenizer-json')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    root = args.output / 'proyecto_sintetico'
    root.mkdir()
    # Función larga pero menor de 200 líneas. Contenido inventado, sin secretos.
    source = 'def construir_contexto():\n' + ''.join(
        f'    paso_{i} = "evidencia sintetica para conservar una funcion completa {i}"\n'
        for i in range(55)) + '    return paso_54\n'
    (root / 'contexto.py').write_text(source)
    db = connect(args.output / 'indice_demo.sqlite3')
    counter = TokenCounter(args.tokenizer_json)
    try:
        scan(root, db)
        required = [('contexto.py', 'construir_contexto')]
        profiles = {}
        for name, size in PROFILES.items():
            try:
                result = build_bundle(root, db, 'construir contexto', size, required=required, token_counter=counter)
                assert counter.count(result['text']) <= size
                assert 'return paso_54' in result['text']
                (args.output / (name + '.txt')).write_text(result['text'])
                profiles[name] = {'status': 'complete', 'metrics': result['metrics']}
            except BudgetError:
                profiles[name] = {'status': 'rejected_required_evidence_does_not_fit', 'budget': size}
        initial = 300
        adaptive = generate_with_budget(
            lambda size: build_bundle(root, db, 'construir contexto', size,
                                      required=required, token_counter=counter),
            initial, auto=True, maximum=16000,
            context_window=20000, reserve_output=2000, prompt_overhead=2000)
        assert adaptive['budget_policy']['effective'] > initial
        assert counter.count(adaptive['text']) <= 16000
        assert 'return paso_54' in adaptive['text']
        (args.output / 'adaptive.txt').write_text(adaptive['text'])
        # Dos snapshots de evidencia completa antes/después de editar nuestra fixture.
        first = create_snapshot(adaptive, origin='demo-local')
        changed = source.replace('return paso_54', 'return paso_53')
        (root / 'contexto.py').write_text(changed)
        scan(root, db)
        second_result = build_bundle(root, db, 'construir contexto', 16000,
                                     required=required, token_counter=counter)
        second = create_snapshot(second_result, origin='demo-local')
        envelope = make_delta(first, second, token_counter=counter)
        rebuilt = apply_delta(first, envelope, expected_base_sha256=first['sha256'])
        assert rebuilt == second
        assert 'return paso_53' in rebuilt['text']
        for name, value in [('base.json', first), ('actual.json', second)]:
            (args.output / name).write_text(json.dumps(value, ensure_ascii=False, separators=(',', ':')))
        (args.output / 'delta.json').write_text(transport_text(envelope))
        stats = {'status': 'PASS', 'profiles': profiles,
                 'adaptive': {'metrics': adaptive['metrics'], 'policy': adaptive['budget_policy']},
                 'delta': transport_metrics(first, second, envelope, token_counter=counter),
                 'roundtrip_exact': rebuilt == second, 'scope': 'escenario sintético, sin modelos ni código de producción ejecutados'}
        (args.output / 'metrics.json').write_text(json.dumps(stats, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps(stats, ensure_ascii=False, indent=2))
    finally:
        db.close()


if __name__ == '__main__':
    main()
