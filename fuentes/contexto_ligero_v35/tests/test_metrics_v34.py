"""Contratos de evaluación: denominadores, techos y oráculos congelados."""
import importlib.util
import json
from pathlib import Path
import unittest

import EJECUTAR_PRUEBAS as runner

spec = importlib.util.spec_from_file_location('metrics_worker_v34', runner.ROOT / 'benchmarks/worker.py')
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


class MetricsV34Tests(unittest.TestCase):
    def test_historical_precision_at_5_has_exact_forty_percent_ceiling(self):
        tasks = json.loads((runner.ROOT / 'benchmarks/tasks.json').read_text())['tasks']
        ceilings = [worker.selection_metrics(task['relevant'], task['relevant'])['precision_at_5_ceiling'] for task in tasks]
        self.assertAlmostEqual(sum(ceilings) / len(ceilings), 0.4)
        self.assertLess(sum(ceilings) / len(ceilings), 0.55)

    def test_precision_returned_is_separate_from_unchanged_fixed_five_denominator(self):
        truth = [('module.py','a'), ('module.py','b')]
        compact = worker.selection_metrics(truth, truth)
        noisy = worker.selection_metrics(truth + [('noise.py','x'), ('noise.py','y')], truth)
        self.assertEqual(compact['precision_at_5'], noisy['precision_at_5'])
        self.assertEqual(compact['precision_at_5'], 0.4)
        self.assertEqual(compact['precision_returned'], 1.0)
        self.assertEqual(noisy['precision_returned'], 0.5)
        self.assertEqual(compact['recall_at_10'], noisy['recall_at_10'])

    def test_abstention_does_not_score_perfect_precision_or_recall(self):
        result = worker.selection_metrics([], [('a.py','a')])
        self.assertEqual(result['precision_returned'], 0.0)
        self.assertEqual(result['precision_at_5'], 0.0)
        self.assertEqual(result['recall_at_10'], 0.0)

    def test_duplicate_symbols_cannot_inflate_hits(self):
        result = worker.selection_metrics([('a.py','a')]*20, [('a.py','a')])
        self.assertEqual(result['retrieved_symbols'], 1)
        self.assertEqual(result['precision_at_5'], 0.2)
        self.assertEqual(result['recall_at_10'], 1.0)

    def test_packet_precision_counts_all_added_symbols(self):
        root, dependency, unjudged = ('a.py','run'), ('a.py','check'), ('b.py','extra')
        result = worker.packet_metrics([root,dependency,unjudged], [root], [root,dependency], [dependency])
        self.assertAlmostEqual(result['packet_precision'], 2/3)
        self.assertEqual(result['ranked_packet_precision'], 1.0)
        self.assertEqual(result['added_not_ranked_count'], 2)
        self.assertEqual(result['known_dependency_recall'], 1.0)
        self.assertEqual(result['packet_file_recall'], 1.0)

    def test_missing_dependency_reduces_recall_instead_of_disappearing_from_denominator(self):
        root, dependency = ('a.py','run'), ('a.py','check')
        result = worker.packet_metrics([root], [root], [root,dependency], [dependency])
        self.assertEqual(result['packet_precision'], 1.0)
        self.assertEqual(result['packet_recall'], 0.5)
        self.assertEqual(result['known_dependency_recall'], 0.0)

    def test_prior_and_new_oracles_are_frozen(self):
        self.assertTrue(runner.frozen_v34_integrity()['ok'])
        self.assertTrue(runner.independent_integrity()['ok'])
        self.assertTrue(runner.baseline_integrity()['ok'])

    def test_new_oracles_reference_real_ast_symbols_without_importing_corpus(self):
        datasets = [
            ('tasks_v34_reales.json', runner.ROOT / 'referencia_original/equipo_ia_referencia'),
            ('tasks_v34_flujos.json', runner.ROOT / 'benchmarks/fixtures/flujos_v34'),
        ]
        for filename, corpus in datasets:
            tasks = json.loads((runner.ROOT / 'benchmarks' / filename).read_text())['tasks']
            worker.validate_oracles(corpus, tasks)
        flows = json.loads((runner.ROOT / 'benchmarks/tasks_v34_flujos.json').read_text())['tasks']
        self.assertEqual(len(flows), 6)
        self.assertTrue(all(len(task['relevant']) == 5 for task in flows))
        self.assertTrue(all(len(task['dependency_relevant']) == 4 for task in flows))


if __name__ == '__main__':
    unittest.main()
