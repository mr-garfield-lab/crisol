"""Selección por operaciones, sin eliminar clausuras estáticas ni alternativas."""
from pathlib import Path
import tempfile
import unittest

from contexto_core.index import connect, scan
from contexto_core.retrieval import retrieve_detailed


def names(rows):
    return {(r['path'], s['name']) for r in rows for s in r['symbols']}


class SelectionV35Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'project'
        self.root.mkdir()
        self.db = connect(Path(self.tmp.name) / 'index.sqlite')
        self.addCleanup(self.db.close)

    def source(self, path, source):
        dest = self.root / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(source)

    def test_module_word_is_not_an_unrequested_operation_but_dependencies_survive(self):
        self.source('parcel.py', 'def validate_parcel(x):\n return x\n'
                    'def store_parcel(x):\n return x\n'
                    'def submit_parcel(x):\n return store_parcel(validate_parcel(x))\n'
                    'def parcel_show_help():\n return 4\n'
                    'def parcel_export_demo():\n return 5\n')
        scan(self.root, self.db)
        result = retrieve_detailed(self.db, 'parcel submit validate store')
        self.assertEqual(names(result['answer_candidates']), {('parcel.py','validate_parcel'),
                         ('parcel.py','store_parcel'), ('parcel.py','submit_parcel')})
        self.assertIn(('parcel.py','parcel_show_help'), names(result['results']))
        self.assertTrue(any(x['symbol'] == 'parcel_show_help' for x in result['omitted']))

    def test_broad_module_only_request_does_not_drop_possible_operations(self):
        self.source('parcel.py', 'def parcel_add(x):\n return x\n'
                    'def parcel_read(x):\n return x\n')
        scan(self.root, self.db)
        result = retrieve_detailed(self.db, 'parcel')
        self.assertTrue({('parcel.py','parcel_add'), ('parcel.py','parcel_read')}
                        <= names(result['results']))

    def test_compound_module_is_not_split_into_unrequested_module_anchors(self):
        self.source('account.py', 'def history(x):\n return x\n')
        self.source('profiles.py', 'def reset(x):\n return x\n')
        self.source('profiles_account.py', 'def choose(x):\n return x\n'
                    'def budget(x):\n return x\n')
        scan(self.root, self.db)
        result = retrieve_detailed(self.db, 'profiles account choose budget')
        self.assertEqual(names(result['selected']), {('profiles_account.py','choose'),
                                                      ('profiles_account.py','budget')})
        self.assertEqual({x['path'] for x in result['alternative_module_matches']},
                         {'account.py','profiles.py'})

    def test_compound_and_separate_module_with_own_operation_are_both_retained(self):
        self.source('account.py', 'def prepare(x):\n return x\n')
        self.source('profiles_account.py', 'def choose(x):\n return x\n')
        scan(self.root, self.db)
        result = retrieve_detailed(self.db, 'profiles_account choose account prepare')
        self.assertTrue({('profiles_account.py','choose'), ('account.py','prepare')}
                        <= names(result['selected']))

    def test_class_name_is_scope_when_matching_method_has_separate_operation(self):
        self.source('paths.py', 'class Vault:\n def check(self, x):\n  return x\n'
                    'def create_vault():\n return None\n')
        scan(self.root, self.db)
        result = retrieve_detailed(self.db, 'paths Vault check')
        self.assertIn(('paths.py','Vault.check'), names(result['selected']))
        self.assertNotIn(('paths.py','create_vault'), names(result['selected']))

    def test_exact_function_name_survives_class_name_context(self):
        self.source('platform.py', 'def adapter():\n return True\n'
                    'class AdapterMobile:\n def supports_lock(self):\n  return True\n')
        scan(self.root, self.db)
        result = retrieve_detailed(self.db, 'platform adapter Mobile supports_lock')
        self.assertIn(('platform.py','adapter'), names(result['selected']))
        self.assertIn(('platform.py','AdapterMobile.supports_lock'), names(result['selected']))

    def test_explicit_test_request_retains_related_negative_case(self):
        self.source('tests/test_invoice.py', 'def test_validate_invoice():\n return True\n'
                    'def test_reject_invoice_empty():\n return True\n')
        scan(self.root, self.db)
        result = retrieve_detailed(self.db, 'tests validate invoice')
        self.assertTrue({('tests/test_invoice.py','test_validate_invoice'),
                         ('tests/test_invoice.py','test_reject_invoice_empty')}
                        <= names(result['selected']))


if __name__ == '__main__':
    unittest.main()
