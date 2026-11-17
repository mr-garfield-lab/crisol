"""Algorithm-development fixtures, separate from the frozen evaluation corpus."""
from pathlib import Path
import tempfile
import unittest

from contexto_core.index import connect, scan
from contexto_core.retrieval import retrieve, retrieve_detailed


def pairs(rows):
    return [(row['path'], symbol['name']) for row in rows for symbol in row['symbols']]


class RetrievalV34Tests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / 'project'
        self.root.mkdir()
        self.db = connect(Path(self.temporary.name) / 'index.sqlite')
        self.addCleanup(self.db.close)

    def write(self, path, source):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source, encoding='utf-8')

    def billing(self):
        self.write('billing.py',
                   'def calculate_total(items):\n return sum(items)\n'
                   'def validate_invoice(invoice):\n return bool(invoice)\n'
                   'def format_invoice(invoice):\n return str(invoice)\n'
                   'def validate_profile(profile):\n return bool(profile)\n')
        self.write('accounts.py', 'def validate_invoice(invoice):\n return invoice\n')
        self.write('tests/test_billing.py', 'def test_calculate_total():\n assert calculate_total([1]) == 1\n')
        scan(self.root, self.db)

    def test_module_and_multiple_operations_select_specific_symbols(self):
        self.billing()
        details = retrieve_detailed(self.db, 'billing calculate total validate invoice')
        self.assertEqual(set(pairs(details['selected'])), {
            ('billing.py', 'calculate_total'), ('billing.py', 'validate_invoice')})
        self.assertTrue(details['omitted'])
        self.assertNotIn(('accounts.py', 'validate_invoice'), pairs(details['selected']))

    def test_recall_pool_retains_nonselected_candidates(self):
        self.billing()
        details = retrieve_detailed(self.db, 'billing calculate total validate invoice')
        self.assertTrue(set(pairs(details['selected'])).issubset(pairs(details['results'])))
        self.assertIn(('billing.py', 'format_invoice'), pairs(details['results']))

    def test_exact_qualified_identifier_overrides_cross_module_noise(self):
        self.write('service.py', 'class InvoiceService:\n def submitInvoice(self, data):\n  return data\n')
        for n in range(10):
            self.write(f'other_{n}.py', 'def submit_invoice(data):\n return data\n')
        scan(self.root, self.db)
        details = retrieve_detailed(self.db, 'InvoiceService.submitInvoice')
        self.assertEqual(pairs(details['selected'])[0], ('service.py', 'InvoiceService.submitInvoice'))

    def test_static_dependencies_precede_unrelated_lexical_fill(self):
        self.write('engine.py', 'def prepare_payload(value):\n return value\n'
                   'def submit_order(value):\n return prepare_payload(value)\n')
        for n in range(8):
            self.write(f'helper_{n}.py', 'def log_submit_order(value):\n return value\n')
        scan(self.root, self.db)
        details = retrieve_detailed(self.db, 'submit_order')
        self.assertIn(('engine.py', 'prepare_payload'), pairs(details['results'])[:3])
        self.assertNotIn(('engine.py', 'prepare_payload'), pairs(details['selected']))
        self.assertTrue(any(row['reason'] == 'static_dependency' for row in details['results']))

    def test_five_symbol_dependency_chain_precedes_lexical_fill(self):
        self.write('chain.py', 'def entry_api(value):\n return alpha(value)\n'
                   'def alpha(value):\n return bravo(value)\n'
                   'def bravo(value):\n return charlie(value)\n'
                   'def charlie(value):\n return delta(value)\n'
                   'def delta(value):\n return value\n')
        for number in range(8):
            self.write(f'logger_{number}.py', 'def log_entry_api(value):\n return value\n')
        scan(self.root, self.db)
        result = retrieve_detailed(self.db, 'entry_api')
        self.assertEqual(pairs(result['results'])[:5], [
            ('chain.py', name) for name in ('entry_api', 'alpha', 'bravo', 'charlie', 'delta')])
        self.assertEqual(result['limits']['dependency_depth'], 8)
        self.assertEqual(result['limits']['dependency_nodes'], 64)

    def test_dependency_cycle_is_finite_and_keeps_each_symbol_once(self):
        self.write('chain.py', 'def entry_api(value):\n return alpha(value)\n'
                   'def alpha(value):\n return bravo(value)\n'
                   'def bravo(value):\n return charlie(value)\n'
                   'def charlie(value):\n return delta(value)\n'
                   'def delta(value):\n return alpha(value)\n')
        scan(self.root, self.db)
        result = retrieve_detailed(self.db, 'entry_api', limit=100)
        found = pairs(result['results'])
        self.assertEqual(len(found), 5)
        self.assertEqual(len(set(found)), 5)
        self.assertEqual(result['dependency_candidates'], 4)

    def test_multimodule_query_preserves_both_explicit_operations(self):
        self.write('exports.py', 'def serialize_document(doc):\n return doc\n')
        self.write('storage.py', 'def persist_document(doc):\n return doc\n')
        scan(self.root, self.db)
        result = retrieve_detailed(self.db, 'exports storage serialize persist document')
        self.assertEqual(set(pairs(result['selected'])), {
            ('exports.py', 'serialize_document'), ('storage.py', 'persist_document')})

    def test_named_module_without_query_operation_keeps_its_best_entrypoint(self):
        self.write('orders.py', 'def submit_order(value):\n return value\n')
        self.write('cache.py', 'def restore(value):\n return value\n')
        self.write('policy.py', 'def allow(value):\n return verify(value)\n'
                   'def verify(value):\n return value\n')
        scan(self.root, self.db)
        details = retrieve_detailed(self.db, 'orders cache submit policy')
        selected_paths = {row['path'] for row in details['selected']}
        self.assertEqual(selected_paths, {'orders.py', 'cache.py', 'policy.py'})
        self.assertTrue(any(row['reason'] == 'module_anchor_fallback' for row in details['selected']))
        self.assertEqual(details['selection']['mode'], 'recall_fallback')

    def test_camelcase_entry_outside_named_module_remains_explicit(self):
        self.write('workflow.py', 'def submitOrder(value):\n return value\n')
        self.write('policy.py', 'def approve_order(value):\n return value\n')
        scan(self.root, self.db)
        details = retrieve_detailed(self.db, 'submitOrder policy approve_order')
        self.assertEqual(set(pairs(details['selected'])), {
            ('workflow.py', 'submitOrder'), ('policy.py', 'approve_order')})
        self.assertTrue(all(row['reason'] == 'explicit_identifier' for row in details['selected']))

    def test_unicode_camelcase_is_an_explicit_identifier(self):
        self.write('region.py', 'def revisarÁrea(value):\n return value\n')
        self.write('policy.py', 'def approve_order(value):\n return value\n')
        scan(self.root, self.db)
        details = retrieve_detailed(self.db, 'revisarÁrea policy approve_order')
        self.assertIn(('region.py', 'revisarÁrea'), pairs(details['selected']))

    def test_test_request_does_not_get_production_results_as_direct_answers(self):
        self.billing()
        result = retrieve_detailed(self.db, 'tests billing calculate total')
        self.assertEqual(pairs(result['selected']), [('tests/test_billing.py', 'test_calculate_total')])

    def test_module_request_mentioning_tests_keeps_production_operations(self):
        self.write('inspector.py', 'def analyze(package):\n return package\n'
                   'class StaticRunner:\n def execute(self, package):\n  return analyze(package)\n')
        self.write('tests/test_inspector.py', 'def test_no_execution():\n return True\n')
        scan(self.root, self.db)
        details = retrieve_detailed(self.db, 'inspector analyze modules and tests without execute')
        self.assertIn(('inspector.py', 'analyze'), pairs(details['selected']))
        self.assertIn(('inspector.py', 'StaticRunner.execute'), pairs(details['selected']))

    def test_class_anchor_preserves_other_operations_and_unnamed_methods(self):
        self.write('sandbox.py', 'class Unavailable:\n def autoverificar(self):\n  return False\n'
                   'class RealExecutor:\n def _execute(self, request):\n  raise RuntimeError("blocked")\n')
        scan(self.root, self.db)
        details = retrieve_detailed(self.db, 'sandbox autoverificar proveedor bloquear RealExecutor sin garantias')
        self.assertIn(('sandbox.py', 'Unavailable.autoverificar'), pairs(details['selected']))
        self.assertIn(('sandbox.py', 'RealExecutor._execute'), pairs(details['selected']))
        self.assertIn(('sandbox.py', 'RealExecutor'), pairs(details['selected']))

    def test_class_and_explicit_function_requests_are_both_preserved(self):
        self.write('sandbox.py', 'def verify_request(value):\n return value\n'
                   'class RealExecutor:\n def _execute(self, request):\n  return request\n')
        scan(self.root, self.db)
        details = retrieve_detailed(self.db, 'sandbox RealExecutor verify_request')
        self.assertIn(('sandbox.py', 'verify_request'), pairs(details['selected']))
        self.assertIn(('sandbox.py', 'RealExecutor._execute'), pairs(details['selected']))

    def test_class_container_requires_class_intent(self):
        self.write('ledger.py', 'class Ledger:\n def append_entry(self, entry):\n  return entry\n')
        scan(self.root, self.db)
        self.assertEqual(pairs(retrieve_detailed(self.db, 'clase Ledger')['selected']), [('ledger.py', 'Ledger')])
        self.assertEqual(pairs(retrieve_detailed(self.db, 'ledger append entry')['selected']), [('ledger.py', 'Ledger.append_entry')])

    def test_accent_and_camel_case_search(self):
        self.write('inventário.py', 'def calcularStock(entrada):\n return entrada\n'
                   'def revisarÁrea(area):\n return area\n')
        scan(self.root, self.db)
        result = retrieve_detailed(self.db, 'inventario calcular stock revisar area')
        self.assertEqual(set(pairs(result['selected'])), {
            ('inventário.py', 'calcularStock'), ('inventário.py', 'revisarÁrea')})

    def test_ambiguous_same_operation_is_not_silently_treated_as_unique(self):
        self.write('one.py', 'def decode_packet(data):\n return data\n')
        self.write('two.py', 'def decode_packet(data):\n return data\n')
        scan(self.root, self.db)
        result = retrieve_detailed(self.db, 'decode packet')
        self.assertEqual(len(result['selected']), 2)
        self.assertTrue(result['ambiguous'])

    def test_fts_fallback_preserves_selection_and_order(self):
        self.billing()
        query = 'billing calculate total validate invoice'
        first = retrieve_detailed(self.db, query)
        self.db.execute("UPDATE meta SET value='0' WHERE key='fts5'")
        self.assertEqual(retrieve_detailed(self.db, query), first)

    def test_retrieve_returns_direct_answers_and_dependencies_without_lexical_fill(self):
        self.write('processing.py', 'def helper(value):\n return value\n'
                   'def submit_order(value):\n return helper(value)\n')
        self.write('logger.py', 'def log_submit_order(value):\n return value\n')
        scan(self.root, self.db)
        details = retrieve_detailed(self.db, 'submit_order')
        self.assertIn(('logger.py', 'log_submit_order'), pairs(details['results']))
        self.assertEqual(pairs(details['answer_candidates']), [
            ('processing.py', 'submit_order'), ('processing.py', 'helper')])
        self.assertEqual(retrieve(self.db, 'submit_order'), details['answer_candidates'])
        self.assertEqual(details['selection']['mode'], 'focused_with_dependencies')

    def test_uncertain_module_query_retains_explicit_recall_fallback(self):
        self.write('storage.py', '\n'.join(f'def operation_{i}(value):\n return value\n' for i in range(8)))
        scan(self.root, self.db)
        details = retrieve_detailed(self.db, 'storage')
        self.assertEqual(details['selection']['mode'], 'recall_fallback')
        self.assertEqual(retrieve(self.db, 'storage'), details['results'])
        self.assertGreater(len(details['results']), len(details['answer_candidates']))

    def test_explicit_document_file_is_returned_without_invented_symbols(self):
        self.write('docs/deployment.md', '# Deployment\nContent never indexed as code.\n')
        self.write('irrelevant.py', 'def deployment_metadata():\n return 1\n')
        scan(self.root, self.db)
        details = retrieve_detailed(self.db, 'deployment.md')
        self.assertEqual([row['path'] for row in details['selected']], ['docs/deployment.md'])
        self.assertEqual(details['selected'][0]['symbols'], [])
        self.assertEqual(details['selected'][0]['reason'], 'explicit_file')
        self.assertEqual(retrieve(self.db, 'deployment.md'), details['answer_candidates'])
        self.assertEqual(details['results'], details['answer_candidates'])

    def test_explicit_file_basename_ambiguity_preserves_all_matches(self):
        self.write('one/guide.txt', 'first\n')
        self.write('two/guide.txt', 'second\n')
        scan(self.root, self.db)
        details = retrieve_detailed(self.db, 'guide.txt')
        self.assertEqual({row['path'] for row in details['selected']}, {'one/guide.txt', 'two/guide.txt'})
        self.assertTrue(details['ambiguous'])
        self.assertEqual(details['selection']['fallback_reasons'], ['ambiguous_file_name'])
        self.assertEqual([row['path'] for row in retrieve(self.db, 'one/guide.txt')], ['one/guide.txt'])

    def test_json_and_invalid_python_are_available_only_when_named(self):
        self.write('settings.json', '{"mode": "local"}\n')
        self.write('broken.py', 'def cannot_parse(\n')
        scan(self.root, self.db)
        self.assertEqual({row['path'] for row in retrieve(self.db, 'settings.json broken.py')},
                         {'settings.json', 'broken.py'})
        self.assertEqual(retrieve(self.db, '../settings.json'), [])
        self.assertEqual(retrieve(self.db, 'absent.json'), [])

    def test_request_words_that_are_real_module_or_operation_names_are_preserved(self):
        self.write('archivos.py', 'def revisar_etiqueta(valor):\n return valor\n')
        self.write('another.py', 'def revisar_etiqueta(valor):\n return valor\n')
        scan(self.root, self.db)
        result = retrieve_detailed(self.db, 'archivos revisar etiqueta')
        self.assertEqual(pairs(result['selected']), [('archivos.py', 'revisar_etiqueta')])
        self.assertEqual(result['named_modules'], ['archivos.py'])

    def test_duplicate_definitions_are_reported_as_ambiguous(self):
        self.write('decoder.py', 'def decode_packet(data):\n return data\ndef decode_packet(data):\n return data\n')
        scan(self.root, self.db)
        result = retrieve_detailed(self.db, 'decode packet')
        self.assertTrue(result['ambiguous'])
        self.assertEqual(len(result['selected']), 2)

    def test_boundaries_and_unknown_query(self):
        self.billing()
        self.assertEqual(retrieve(self.db, 'xyzzy_unfindable'), [])
        self.assertEqual(retrieve(self.db, '" OR *'), [])
        self.assertLessEqual(len(retrieve(self.db, 'invoice', 2)), 2)
        with self.assertRaises(ValueError):
            retrieve(self.db, 'invoice', 0)
        with self.assertRaises(ValueError):
            retrieve(self.db, 'x' * 8193)

    def test_scan_update_does_not_leave_stale_retrieval_state(self):
        self.write('billing.py', 'def calculate_total(items):\n return items\n')
        scan(self.root, self.db)
        self.assertTrue(retrieve(self.db, 'calculate_total'))
        self.write('billing.py', 'def replaced(items):\n return items\n')
        scan(self.root, self.db)
        self.assertEqual(retrieve(self.db, 'calculate_total'), [])


if __name__ == '__main__':
    unittest.main()
