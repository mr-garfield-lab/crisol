"""Revisión independiente de paquetes y evidencia; fixtures propias sin oráculos."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from contexto_v3 import connect, scan
from contexto_core.budget import BudgetError
from contexto_core.context import build_packet
from contexto_core.evidence import build_bundle
from contexto_core.support import support_context


class PacketV34ReviewTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / 'project'
        self.root.mkdir()
        self.db = connect(Path(self.temporary.name) / 'index.sqlite3')
        self.addCleanup(self.db.close)

    def source(self, path, text):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding='utf-8')
        return target

    @staticmethod
    def selected(result):
        return {(row['path'], sym['name']) for row in result['selected'] for sym in row['symbols']}

    def test_required_bundle_preserves_calls_imports_and_transitive_constants(self):
        self.source('logic.py', 'import math as rounding\nBASE = 3\nLIMIT = BASE * 2\n'
                    'def helper():\n    return rounding.floor(LIMIT)\n'
                    'def entry():\n    return helper()\n')
        scan(self.root, self.db)
        data = build_bundle(self.root, self.db, 'entry', required=[('logic.py', 'entry')],
                            strict_dependencies=False)
        for text in ('import math as rounding', 'BASE = 3', 'LIMIT = BASE * 2',
                     'return rounding.floor(LIMIT)', 'return helper()'):
            self.assertIn(text, data['text'])
        self.assertTrue(data['indexed_dependencies_included'])
        self.assertFalse(data['runtime_complete'])
        self.assertEqual(data['text'].count('sha256:'), 1)

    def test_support_redacts_neutral_credential_value_before_merging(self):
        self.source('logic.py', 'PASSWORD = (\n    "valor_azul_no_publico"\n)\n'
                    'def entry():\n    return PASSWORD\n')
        scan(self.root, self.db)
        data = build_bundle(self.root, self.db, 'entry', required=[('logic.py', 'entry')])
        self.assertNotIn('valor_azul_no_publico', data['text'])
        self.assertNotIn('valor_azul_no_publico', str(data['support']))
        self.assertIn('OCULTA', data['text'])

    def test_overlapping_class_and_method_are_emitted_once(self):
        self.source('logic.py', 'class Worker:\n    marker = 1\n    def execute(self):\n        return 7\n')
        scan(self.root, self.db)
        data = build_bundle(self.root, self.db, 'Worker execute',
                            required=[('logic.py', 'Worker'), ('logic.py', 'Worker.execute')])
        self.assertEqual(data['text'].count('L4:         return 7'), 1)
        self.assertEqual(data['unique_source_lines'], 4)
        self.assertEqual(data['text'].count('sha256:'), 1)

    def test_inferred_class_target_keeps_its_source_without_require(self):
        self.source('logic.py', 'class Worker:\n    def execute(self):\n        return 7\n')
        scan(self.root, self.db)
        data = build_bundle(self.root, self.db, 'clase Worker')
        self.assertIn(('logic.py', 'Worker'),
                      {(row['path'], row['symbol']) for row in data['selected']})
        self.assertIn('class Worker:', data['text'])
        self.assertIn('return 7', data['text'])
        self.assertNotIn('no hay evidencia', data['text'])

    def test_requested_test_is_evidence_even_when_extra_tests_are_disabled(self):
        self.source('logic.py', 'def calculate():\n    return 7\n')
        self.source('test_logic.py', 'from logic import calculate\n'
                    'def test_calculate():\n    assert calculate() == 7\n')
        scan(self.root, self.db)
        data = build_bundle(self.root, self.db, 'test_calculate pruebas', include_tests=False)
        selected = {(row['path'], row['symbol']) for row in data['selected']}
        self.assertIn(('test_logic.py', 'test_calculate'), selected)
        self.assertIn(('logic.py', 'calculate'), selected)
        self.assertIn('assert calculate() == 7', data['text'])
        self.assertTrue(data['indexed_dependencies_included'])
        self.assertFalse(data['tests_executed'])

    def test_auxiliary_test_requires_link_to_exact_target_not_homonymous_function(self):
        self.source('billing.py', 'def build():\n    return 7\n')
        self.source('shipping.py', 'def build():\n    return 11\n')
        self.source('tests/test_billing.py', 'from billing import build\n'
                    'def test_build_billing():\n    assert build() == 7\n')
        self.source('tests/test_shipping.py', 'from shipping import build\n'
                    'def test_build_shipping():\n    assert build() == 11\n')
        scan(self.root, self.db)
        data = build_bundle(self.root, self.db, 'billing build', required=[('billing.py', 'build')])
        candidates = {(row['path'], row['symbol']) for row in data['selected']
                      if row['role'] == 'prueba_candidata'}
        self.assertEqual(candidates, {('tests/test_billing.py', 'test_build_billing')})
        self.assertNotIn('assert build() == 11', data['text'])

    def chain(self, count=7, name_prefix='helper_'):
        names = ['entry'] + [name_prefix + str(i) for i in range(count - 1)]
        text = ''.join(f'def {name}():\n    return {names[i + 1]}()\n'
                       if i + 1 < len(names) else f'def {name}():\n    return 17\n'
                       for i, name in enumerate(names))
        self.source('chain.py', text)
        scan(self.root, self.db)
        return names

    def test_packet_keeps_more_than_four_proven_dependencies(self):
        names = self.chain()
        data = build_packet(self.root, self.db, 'entry', limit=1,
                            required=[('chain.py', 'entry')], strict_dependencies=True)
        self.assertEqual(self.selected(data), {('chain.py', name) for name in names})
        self.assertTrue(data['indexed_dependencies_included'])
        self.assertLessEqual(data['metrics']['tokens_estimated'], 2000)

    def test_depth_limit_is_visible_and_strict_mode_refuses_it(self):
        self.chain()
        data = build_packet(self.root, self.db, 'entry', limit=1, dependencies=1)
        self.assertFalse(data['indexed_dependencies_included'])
        self.assertTrue(any(item['reason'] == 'depth_limit' for item in data['omissions']))
        self.assertIn('fuera de límites', data['text'])
        with self.assertRaisesRegex(ValueError, 'incompleta'):
            build_packet(self.root, self.db, 'entry', limit=1, dependencies=1,
                         strict_dependencies=True)

    def test_budget_does_not_silently_hide_static_dependencies(self):
        self.chain(20, 'helper_with_long_unique_operation_name_')
        data = build_packet(self.root, self.db, 'entry', 300, limit=1, dependencies=32)
        self.assertLessEqual(len(data['text']), 900)
        self.assertFalse(data['indexed_dependencies_included'])
        self.assertIn('COBERTURA INCOMPLETA', data['text'])
        self.assertTrue(any(item['reason'].startswith('budget_dependency') for item in data['omissions']))
        with self.assertRaises(BudgetError):
            build_packet(self.root, self.db, 'entry', 300, limit=1, dependencies=32,
                         strict_dependencies=True)

    def test_explicit_requirement_keeps_its_closure_even_in_partial_bundle_mode(self):
        self.chain(7)
        with self.assertRaisesRegex(ValueError, 'max_evidence'):
            build_bundle(self.root, self.db, 'entry', required=[('chain.py', 'entry')],
                         strict_dependencies=False, max_evidence=2)

    def test_changed_file_cannot_satisfy_required_context(self):
        path = self.source('logic.py', 'def entry():\n    return 12\n')
        scan(self.root, self.db)
        path.write_text('def entry():\n    return 13\n')
        with self.assertRaisesRegex(ValueError, 'reindexar'):
            build_bundle(self.root, self.db, 'entry', required=[('logic.py', 'entry')])

    def test_symlinked_parent_after_scan_is_rejected(self):
        self.source('inside/logic.py', 'def entry():\n    return 12\n')
        scan(self.root, self.db)
        (self.root / 'inside').rename(self.root / 'saved')
        (self.root / 'inside').symlink_to(self.root / 'saved', target_is_directory=True)
        with self.assertRaises(ValueError):
            build_bundle(self.root, self.db, 'entry', required=[('inside/logic.py', 'entry')])

    def test_different_hash_between_fragment_and_support_is_rejected(self):
        self.source('logic.py', 'LIMIT = 3\ndef entry():\n    return LIMIT\n')
        scan(self.root, self.db)
        def stale_support(*args, **kwargs):
            result = support_context(*args, **kwargs)
            result['sha256'] = '0' * 64
            return result
        with patch('contexto_core.evidence.support_context', side_effect=stale_support):
            with self.assertRaisesRegex(ValueError, 'Hash'):
                build_bundle(self.root, self.db, 'entry', required=[('logic.py', 'entry')])

    def test_unknown_query_is_explicitly_insufficient(self):
        self.source('logic.py', 'def entry():\n    return 12\n')
        scan(self.root, self.db)
        data = build_packet(self.root, self.db, 'zxqvabcde')
        self.assertEqual(data['selected'], [])
        self.assertIn('contexto insuficiente', data['text'])

    def test_explicit_document_path_remains_available_without_python_symbols(self):
        self.source('deployment.md', '# Deployment\nUse a fresh configuration.\n')
        self.source('logic.py', 'def entry():\n    return 12\n')
        scan(self.root, self.db)
        data = build_packet(self.root, self.db, 'deployment.md')
        self.assertTrue(any(row['path'] == 'deployment.md' for row in data['selected']))
        self.assertIn('deployment.md', data['text'])
        self.assertNotIn('contexto insuficiente', data['text'])


if __name__ == '__main__':
    unittest.main()
