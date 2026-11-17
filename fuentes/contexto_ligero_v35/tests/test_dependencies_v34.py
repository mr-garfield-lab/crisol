import hashlib
from pathlib import Path
import tempfile
import unittest

from contexto_core.dependencies import dependency_plan
from contexto_core.index import connect, scan


class DependencyClosureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'project'
        self.root.mkdir()
        self.db = connect(Path(self.tmp.name) / 'index.sqlite3')
        self.addCleanup(self.db.close)

    def write(self, path, content):
        p = self.root / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding='utf-8')

    def index(self):
        scan(self.root, self.db)

    def keys(self, plan):
        return {(n['path'], n['symbol']) for n in plan['nodes']}

    def test_multiple_hops_and_builtin_are_not_silently_cut_at_four(self):
        self.write('chain.py', '\n'.join(
            f'def f{i}():\n    return f{i+1}()\n' for i in range(6)) + 'def f6():\n    return len([])\n')
        self.index()
        result = dependency_plan(self.db, [('chain.py', 'f0')], max_depth=6)
        self.assertEqual(self.keys(result), {('chain.py', f'f{i}') for i in range(1, 7)})
        self.assertEqual(len(result['edges']), 6)
        self.assertTrue(result['complete'])
        self.assertFalse(result['runtime_complete'])
        self.assertEqual(result['terminal_calls'][0]['call'], 'len')
        digest = hashlib.sha256((self.root / 'chain.py').read_bytes()).hexdigest()
        self.assertTrue(all(n['sha256'] == digest for n in result['nodes']))

    def test_depth_limit_reports_exact_missing_destination(self):
        self.write('chain.py', 'def a():\n    return b()\ndef b():\n    return c()\ndef c():\n    return 1\n')
        self.index()
        result = dependency_plan(self.db, [('chain.py', 'a')], max_depth=1)
        self.assertEqual(self.keys(result), {('chain.py', 'b')})
        self.assertEqual([(x['symbol'], x['reason']) for x in result['omitted']], [('c', 'depth_limit')])
        self.assertFalse(result['complete'])
        self.assertFalse(result['indexed_edges_complete'])

    def test_node_limit_reports_omissions_without_discarding_seed(self):
        self.write('branch.py', 'def start():\n    return a(), b(), c()\ndef a():\n    return 1\ndef b():\n    return 2\ndef c():\n    return 3\n')
        self.index()
        result = dependency_plan(self.db, [('branch.py', 'start')], max_nodes=1)
        self.assertEqual(self.keys(result), {('branch.py', 'a')})
        self.assertEqual({(x['symbol'], x['reason']) for x in result['omitted']}, {('b', 'node_limit'), ('c', 'node_limit')})
        self.assertEqual(result['seed_count'], 1)

    def test_cycle_and_shared_callee_are_deduplicated_with_all_parent_edges(self):
        self.write('graph.py', 'def a():\n    return shared()\ndef b():\n    return shared()\ndef shared():\n    return a()\n')
        self.index()
        result = dependency_plan(self.db, [('graph.py', 'a'), ('graph.py', 'b'), ('graph.py', 'a')])
        self.assertEqual(self.keys(result), {('graph.py', 'shared')})
        self.assertEqual(len(result['edges']), 3)
        self.assertEqual(len(result['nodes'][0]['via']), 2)
        self.assertTrue(result['complete'])

    def test_import_alias_and_relative_import_follow_unique_targets(self):
        self.write('src/pkg/__init__.py', '')
        self.write('src/pkg/helper.py', 'def verify():\n    return 1\n')
        self.write('src/pkg/main.py', 'from .helper import verify as check\ndef run():\n    return check()\n')
        self.index()
        result = dependency_plan(self.db, [('src/pkg/main.py', 'run')])
        self.assertEqual(self.keys(result), {('src/pkg/helper.py', 'verify')})
        self.assertEqual(result['edges'][0]['kind'], 'import_call')
        self.assertTrue(result['complete'])

    def test_dynamic_receiver_is_reported_not_promoted_to_proven_dependency(self):
        self.write('methods.py', 'class Service:\n    def run(self):\n        return self.work()\n    def work(self):\n        return 1\n')
        self.index()
        result = dependency_plan(self.db, [('methods.py', 'Service.run')])
        self.assertFalse(result['complete'])
        self.assertEqual(result['nodes'], [])
        self.assertEqual(result['unresolved'][0]['reason'], 'dynamic_dispatch')
        self.assertEqual(result['unresolved'][0]['candidate_targets'], [{'path': 'methods.py', 'symbol': 'Service.work'}])

    def test_external_import_and_reflective_builtin_are_explicit(self):
        self.write('external.py', 'import json\ndef parse(data):\n    return json.loads(data), getattr(data, "x")\n')
        self.index()
        result = dependency_plan(self.db, [('external.py', 'parse')])
        self.assertEqual({x['reason'] for x in result['unresolved']}, {'external_or_ambiguous_import', 'dynamic_builtin'})
        self.assertFalse(result['complete'])
        self.assertTrue(result['indexed_edges_complete'])

    def test_shadowed_builtin_and_duplicate_local_definition_are_not_assumed_safe(self):
        self.write('shadows.py', 'def target():\n    return 1\ndef target():\n    return 2\ndef run(len):\n    return target(), len([])\n')
        self.index()
        result = dependency_plan(self.db, [('shadows.py', 'run')])
        self.assertEqual(result['nodes'], [])
        self.assertEqual({x['reason'] for x in result['unresolved']}, {'ambiguous_local_target', 'shadowed_or_dynamic_binding'})

    def test_missing_or_ambiguous_seed_fails_instead_of_empty_complete(self):
        self.write('duplicate.py', 'def same():\n    pass\ndef same():\n    pass\n')
        self.index()
        with self.assertRaises(ValueError):
            dependency_plan(self.db, [('duplicate.py', 'same')])
        with self.assertRaises(ValueError):
            dependency_plan(self.db, [('missing.py', 'f')])

    def test_stale_graph_target_and_unknown_edge_kind_are_visible(self):
        self.write('one.py', 'def run():\n    pass\n')
        self.index()
        self.db.execute('INSERT INTO code_edges VALUES(?,?,?,?,?)', ('one.py', 'run', 'missing.py', 'x', 'local_call'))
        self.db.execute('INSERT INTO code_edges VALUES(?,?,?,?,?)', ('one.py', 'run', 'one.py', 'run', 'guessed_dynamic'))
        result = dependency_plan(self.db, [('one.py', 'run')])
        self.assertFalse(result['complete'])
        self.assertFalse(result['indexed_edges_complete'])
        self.assertEqual({x['reason'] for x in result['unresolved']}, {'missing_or_ambiguous_edge_target', 'unsupported_edge_kind'})

    def test_plan_is_deterministic_and_does_not_mutate_database(self):
        self.write('simple.py', 'def b():\n    return 1\ndef a():\n    return b()\n')
        self.index()
        before = self.db.total_changes
        one = dependency_plan(self.db, [('simple.py', 'a')])
        two = dependency_plan(self.db, [('simple.py', 'a')])
        self.assertEqual(one, two)
        self.assertEqual(self.db.total_changes, before)

    def test_invalid_limits_and_seed_format_are_rejected(self):
        self.index()
        for options in ({'max_depth': True}, {'max_depth': -1}, {'max_nodes': 0}, {'max_nodes': 1.5}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                dependency_plan(self.db, [], **options)
        with self.assertRaises(ValueError):
            dependency_plan(self.db, ['not a pair'])


if __name__ == '__main__':
    unittest.main()
