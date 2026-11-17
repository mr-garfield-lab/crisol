import tempfile
import unittest
from pathlib import Path

from contexto_core.data_support import imported_context
from contexto_core.index import connect, scan
from contexto_core.support import support_context
from contexto_core.evidence import build_bundle
from contexto_core.budget import BudgetError


class ImportedSupportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'project'
        self.root.mkdir()
        self.db = connect(Path(self.temp.name) / 'index.sqlite')
        self.addCleanup(self.db.close)

    def source(self, path, code):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(code)

    def result(self, path='logic.py', **options):
        scan(self.root, self.db)
        support = support_context(self.root, self.db, path, 'entry', max_lines=200)
        return imported_context(self.root, self.db, path, 'entry', support, **options)

    @staticmethod
    def text(result):
        return '\n'.join(line for f in result['files'] for r in f['ranges'] for line in r['lines'])

    def test_imported_constant_keeps_transitive_values_without_unrelated_code(self):
        self.source('settings.py', 'BASE = 7\nLIMIT = BASE * 3\nUNRELATED = "omit_me"\n')
        self.source('logic.py', 'from settings import LIMIT as maximum\ndef entry():\n    return maximum\n')
        result = self.result()
        self.assertIn('LIMIT = BASE * 3', self.text(result))
        self.assertIn('BASE = 7', self.text(result))
        self.assertNotIn('omit_me', self.text(result))
        self.assertTrue(result['complete'])

    def test_relative_reexport_chain(self):
        self.source('pkg/__init__.py', 'from .settings import LIMIT as CEILING\n')
        self.source('pkg/settings.py', 'LIMIT = 19\n')
        self.source('pkg/logic.py', 'from . import CEILING\ndef entry():\n    return CEILING\n')
        result = self.result('pkg/logic.py')
        self.assertIn('LIMIT = 19', self.text(result))
        self.assertIn('from .settings import LIMIT', self.text(result))
        self.assertTrue(result['complete'])

    def test_module_attributes_from_shared_alias_do_not_lose_second_use(self):
        self.source('settings.py', 'LEFT = 2\nRIGHT = 9\nUNRELATED = 444\n')
        self.source('values.py', 'import settings as cfg\nA = cfg.LEFT\nB = cfg.RIGHT\nTOTAL = A + B\n')
        self.source('logic.py', 'from values import TOTAL\ndef entry():\n    return TOTAL\n')
        result = self.result()
        self.assertIn('LEFT = 2', self.text(result))
        self.assertIn('RIGHT = 9', self.text(result))
        self.assertNotIn('UNRELATED', self.text(result))

    def test_imported_callable_reference_is_mandatory_without_executing_it(self):
        self.source('callbacks.py', 'raise RuntimeError("must_not_run")\ndef handler():\n    return 3\n')
        self.source('logic.py', 'from callbacks import handler\ndef entry():\n    return handler\n')
        result = self.result()
        self.assertIn({'path': 'callbacks.py', 'symbol': 'handler'}, result['required_symbols'])

    def test_mutated_and_conditional_bindings_are_explicitly_unresolved(self):
        self.source('settings.py', 'LIMIT = 7\nif __name__ == "test":\n    LIMIT = 9\n')
        self.source('logic.py', 'from settings import LIMIT\ndef entry():\n    return LIMIT\n')
        result = self.result()
        self.assertFalse(result['complete'])
        self.assertIn('LIMIT = 7', self.text(result))
        self.assertIn('LIMIT = 9', self.text(result))

    def test_secret_value_redacted_in_imported_file(self):
        self.source('settings.py', 'password = "never_share_this_value"\n')
        self.source('logic.py', 'from settings import password\ndef entry():\n    return password\n')
        result = self.result()
        self.assertNotIn('never_share_this_value', self.text(result))
        self.assertIn('OCULTA', self.text(result))

    def test_limits_omit_whole_statements_and_report_depth(self):
        self.source('settings.py', 'VALUES = [\n    1,\n    2,\n]\n')
        self.source('logic.py', 'from settings import VALUES\ndef entry():\n    return VALUES\n')
        result = self.result(max_lines=2)
        self.assertFalse(result['files'])
        self.assertEqual(result['omissions'][0]['reason'], 'import_support_line_limit')
        result = self.result(max_depth=0)
        self.assertEqual(result['omissions'][0]['reason'], 'import_support_depth_limit')

    def test_changed_or_symlinked_imported_file_rejected(self):
        self.source('settings.py', 'LIMIT = 3\n')
        self.source('logic.py', 'from settings import LIMIT\ndef entry():\n    return LIMIT\n')
        scan(self.root, self.db)
        support = support_context(self.root, self.db, 'logic.py', 'entry')
        (self.root / 'settings.py').write_text('LIMIT = 4\n')
        with self.assertRaises(ValueError):
            imported_context(self.root, self.db, 'logic.py', 'entry', support)

    def test_ambiguous_module_never_claims_complete(self):
        self.source('settings.py', 'LIMIT = 3\n')
        self.source('src/settings.py', 'LIMIT = 4\n')
        self.source('logic.py', 'from settings import LIMIT\ndef entry():\n    return LIMIT\n')
        result = self.result()
        self.assertFalse(result['complete'])
        self.assertEqual(result['unresolved'][0]['reason'], 'ambiguous_imported_module')

    def test_cyclic_reexport_is_not_claimed_complete(self):
        self.source('a.py', 'from b import LIMIT\n')
        self.source('b.py', 'from a import LIMIT\n')
        self.source('logic.py', 'from a import LIMIT\ndef entry():\n    return LIMIT\n')
        result = self.result()
        self.assertFalse(result['complete'])
        self.assertTrue(any(x['reason'] == 'cyclic_data_binding' for x in result['unresolved']))

    def test_bundle_merges_data_once_and_keeps_imported_callable_closure(self):
        self.source('settings.py', 'BASE = 5\nLIMIT = BASE * 2\n')
        self.source('callbacks.py', 'from settings import LIMIT\ndef helper():\n    return LIMIT\ndef handler():\n    return helper()\n')
        self.source('logic.py', 'from callbacks import handler\ndef entry():\n    return handler\n')
        scan(self.root, self.db)
        result = build_bundle(self.root, self.db, 'entry', required=[('logic.py', 'entry')],
                              strict_dependencies=False, include_tests=False)
        for source in ('LIMIT = BASE * 2', 'BASE = 5', 'def helper():', 'def handler():'):
            self.assertEqual(result['text'].count(source), 1)
        self.assertTrue(result['imported_support_complete'])
        self.assertFalse(result['runtime_complete'])

    def test_required_imported_data_cannot_be_silently_dropped_for_budget(self):
        self.source('settings.py', 'VALUES = ' + repr(list(range(120))) + '\n')
        self.source('logic.py', 'from settings import VALUES\ndef entry():\n    return VALUES\n')
        scan(self.root, self.db)
        with self.assertRaises(BudgetError):
            build_bundle(self.root, self.db, 'entry', budget=300,
                         required=[('logic.py', 'entry')], strict_dependencies=False)

    def test_symlinked_imported_source_is_rejected(self):
        self.source('settings.py', 'LIMIT = 3\n')
        self.source('logic.py', 'from settings import LIMIT\ndef entry():\n    return LIMIT\n')
        scan(self.root, self.db)
        support = support_context(self.root, self.db, 'logic.py', 'entry')
        original = self.root / 'settings.py'
        original.rename(self.root / 'settings_saved.py')
        original.symlink_to('settings_saved.py')
        with self.assertRaises(ValueError):
            imported_context(self.root, self.db, 'logic.py', 'entry', support)


if __name__ == '__main__':
    unittest.main()
