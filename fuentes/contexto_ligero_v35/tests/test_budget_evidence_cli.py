"""Presupuestos, evidencia obligatoria y transporte CLI verificable."""
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from contexto_v3 import main, connect, scan, _join_inputs, _read_input
from contexto_core.budget import BudgetError, generate_with_budget
from contexto_core.delta import create_snapshot
from contexto_core.evidence import build_bundle


class BudgetPolicyTests(unittest.TestCase):
    @staticmethod
    def result(omitted=False):
        return {'text': 'evidencia', 'metrics': {'budget_unit': 'estimated'},
                'omissions': [{'reason': 'budget_evidence'}] if omitted else []}

    def test_growth_requires_opt_in(self):
        attempts = []
        def builder(size):
            attempts.append(size)
            raise BudgetError('no cabe')
        with self.assertRaises(BudgetError):
            generate_with_budget(builder, 300, maximum=16000)
        self.assertEqual(attempts, [300])

    def test_growth_respects_context_window_and_both_reservations(self):
        attempts = []
        def builder(size):
            attempts.append(size)
            if size < 850:
                raise BudgetError('no cabe')
            return self.result()
        result = generate_with_budget(builder, 300, auto=True, maximum=16000,
                                      context_window=1500, reserve_output=400,
                                      prompt_overhead=200)
        self.assertEqual(attempts, [300, 600, 900])
        self.assertEqual(result['budget_policy']['maximum'], 900)
        self.assertEqual(result['budget_policy']['effective'], 900)

    def test_invalid_initial_window_rejects_before_builder(self):
        with self.assertRaises(BudgetError):
            generate_with_budget(lambda _: self.fail('builder no debe ejecutarse'), 1000,
                                 context_window=1200, reserve_output=400)

    def test_optional_omissions_stop_at_ceiling_and_remain_explicit(self):
        result = generate_with_budget(lambda _: self.result(True), 300, auto=True, maximum=700)
        self.assertEqual(result['budget_policy']['attempts'], [300, 600, 700])
        self.assertTrue(result['budget_policy']['budget_exhausted'])
        self.assertEqual(result['omissions'][0]['reason'], 'budget_evidence')

    def test_non_budget_failure_is_not_retried(self):
        attempts = []
        def builder(size):
            attempts.append(size)
            raise ValueError('hash cambiado')
        with self.assertRaisesRegex(ValueError, 'hash cambiado'):
            generate_with_budget(builder, 300, auto=True)
        self.assertEqual(attempts, [300])


class EvidenceAndCLITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.root = self.folder / 'project'
        self.root.mkdir()
        self.db_path = self.folder / 'index.sqlite3'
        self.db = connect(self.db_path)
        self.addCleanup(self.db.close)

    def write(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        return path

    def cli(self, *arguments):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(['--db', str(self.db_path), *map(str, arguments)])
        return code, out.getvalue(), err.getvalue()

    def test_bundle_required_contains_full_code_not_only_metadata(self):
        self.write('modulo.py', 'def objetivo():\n    valor = 19\n    return valor + 4\n')
        scan(self.root, self.db)
        result = build_bundle(self.root, self.db, 'objetivo', required=[('modulo.py', 'objetivo')])
        self.assertIn('L1: def objetivo():', result['text'])
        self.assertIn('L3:     return valor + 4', result['text'])
        self.assertEqual(len(result['selected']), 1)
        self.assertEqual(result['metrics']['characters'], len(result['text']))
        self.assertLessEqual(result['metrics']['tokens_estimated'], 4000)

    def test_bundle_adaptive_required_evidence_grows_without_truncation(self):
        self.write('modulo.py', 'def objetivo():\n    return "' + 'x' * 1500 + '"\n')
        scan(self.root, self.db)
        required = [('modulo.py', 'objetivo')]
        with self.assertRaises(BudgetError):
            build_bundle(self.root, self.db, 'objetivo', 300, required=required)
        result = generate_with_budget(
            lambda size: build_bundle(self.root, self.db, 'objetivo', size, required=required),
            300, auto=True, maximum=2000)
        self.assertGreater(result['budget_policy']['effective'], 300)
        self.assertIn('x' * 1500, result['text'])
        self.assertLessEqual(result['metrics']['tokens_estimated'], result['budget_policy']['effective'])

    def test_required_over_200_lines_rejects_without_partial_code(self):
        self.write('modulo.py', 'def objetivo():\n' + '    valor = 1\n' * 201 + '    return valor\n')
        scan(self.root, self.db)
        code, out, err = self.cli('bundle', self.root, 'objetivo', '--profile', 'profundo',
                                  '--require', 'modulo.py::objetivo')
        self.assertEqual(code, 1)
        self.assertEqual(out, '')
        self.assertIn('max_lines', err)

    def test_test_evidence_is_candidate_not_execution(self):
        self.write('modulo.py', 'def objetivo():\n    return 7\n')
        self.write('tests/test_modulo.py', 'from modulo import objetivo\ndef test_objetivo():\n    assert objetivo() == 7\n')
        scan(self.root, self.db)
        result = build_bundle(self.root, self.db, 'objetivo', required=[('modulo.py', 'objetivo')])
        self.assertFalse(result['tests_executed'])
        self.assertGreaterEqual(result['test_candidates_included'], 1)
        self.assertIn('prueba_candidata', result['text'])
        self.assertIn('no ejecutadas', result['text'])

    def test_bundle_plain_text_warns_stale_sources_and_no_evidence(self):
        path = self.write('modulo.py', 'def objetivo():\n    return 7\n')
        scan(self.root, self.db)
        path.write_text('def objetivo():\n    return 8\n')
        result = build_bundle(self.root, self.db, 'objetivo')
        self.assertTrue(result['stale'])
        self.assertEqual(result['selected'], [])
        self.assertIn('reindexar', result['text'])
        self.assertIn('no hay evidencia', result['text'].lower())

    def test_cli_snapshot_refuses_overwrite_and_preserves_existing_bytes(self):
        self.write('modulo.py', 'def objetivo():\n    return 7\n')
        scan(self.root, self.db)
        snapshot_path = self.folder / 'base.json'
        snapshot_path.write_bytes(b'NO_SOBRESCRIBIR')
        code, out, err = self.cli('packet', self.root, 'objetivo', '--snapshot-out', snapshot_path)
        self.assertEqual(code, 1)
        self.assertEqual(snapshot_path.read_bytes(), b'NO_SOBRESCRIBIR')
        self.assertEqual(out, '')

    def test_cli_profiles_and_json_budget_match_text(self):
        self.write('modulo.py', 'def objetivo():\n    return 7\n')
        scan(self.root, self.db)
        for profile, expected in [('compacto', 2000), ('modificar', 4000), ('auditar', 8000), ('profundo', 16000)]:
            code, out, err = self.cli('bundle', self.root, 'objetivo', '--profile', profile, '--json')
            self.assertEqual(code, 0, err)
            data = json.loads(out)
            self.assertEqual(data['budget_policy']['effective'], expected)
            self.assertEqual(data['metrics']['characters'], len(data['text']))

    def snapshots(self):
        text = ''.join(f'mod_{i}.py | sha256:{i:064x}\n  objetivo_{i}@L10-L20\n' for i in range(40))
        before = create_snapshot({'text': text}, origin='project')
        after = create_snapshot({'text': text.replace('objetivo_20@L10-L20', 'objetivo_20@L10-L21')}, origin='project')
        before_path, after_path = self.folder/'base.json', self.folder/'target.json'
        before_path.write_text(json.dumps(before))
        after_path.write_text(json.dumps(after))
        return before_path, after_path, before, after

    def test_delta_stdout_and_file_bytes_equal_reported_transport_size(self):
        before_path, after_path, before, after = self.snapshots()
        arguments = ['delta', before_path, after_path, '--expected-base', before['sha256'], '--stats']
        code, out, err = self.cli(*arguments)
        self.assertEqual(code, 0, err)
        measured = json.loads(err)['transmitted']
        self.assertEqual(len(out.encode('utf-8')), measured['utf8_bytes'])
        output = self.folder/'delta.json'
        code, out, err = self.cli(*arguments, '--output', output)
        self.assertEqual(code, 0, err)
        self.assertEqual(len(output.read_bytes()), json.loads(err)['transmitted']['utf8_bytes'])

    def test_delta_cli_roundtrip_and_wrong_base_rejection(self):
        before_path, after_path, before, after = self.snapshots()
        patch = self.folder/'delta.json'
        code, out, err = self.cli('delta', before_path, after_path, '--expected-base', before['sha256'], '--output', patch)
        self.assertEqual(code, 0, err)
        reconstructed = self.folder/'restored.json'
        code, out, err = self.cli('apply-delta', before_path, patch, '--expected-base', before['sha256'], '--output', reconstructed)
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(reconstructed.read_text()), after)
        denied = self.folder/'should_not_exist.json'
        code, out, err = self.cli('apply-delta', before_path, patch, '--expected-base', '0'*64, '--output', denied)
        self.assertEqual(code, 1)
        self.assertFalse(denied.exists())

    def test_tokens_command_counts_exact_concatenation(self):
        a,b = self.folder/'prompt.txt', self.folder/'fragment.txt'
        a.write_text('España\n', encoding='utf-8')
        b.write_text('日本😀', encoding='utf-8')
        code,out,err = self.cli('tokens', a, b, '--separator', '|')
        self.assertEqual(code, 0, err)
        data = json.loads(out)
        exact = 'España\n|日本😀'
        self.assertEqual(data['characters'], len(exact))
        self.assertEqual(data['utf8_bytes'], len(exact.encode('utf-8')))
        self.assertIsNone(data['tokens_measured'])

    def test_join_inputs_applies_utf8_byte_limit_to_spanish_and_separator(self):
        """Dos letras y un emoji son ocho bytes, aunque solo tres caracteres."""
        first, second = self.folder/'espanol_a.txt', self.folder/'espanol_b.txt'
        first.write_text('á', encoding='utf-8')
        second.write_text('ñ', encoding='utf-8')
        self.assertEqual(_join_inputs([first, second], '😀', max_bytes=8), 'á😀ñ')
        with self.assertRaises(ValueError):
            _join_inputs([first, second], '😀', max_bytes=7)

    def test_join_inputs_stops_reading_later_files_at_accumulated_limit(self):
        """No carga el tercer archivo cuando el segundo ya excede lo restante."""
        first, second, third = [self.folder/name for name in ('primero.txt', 'segundo.txt', 'tercero.txt')]
        first.write_text('uno!', encoding='utf-8')
        second.write_text('dos!', encoding='utf-8')
        third.write_bytes(b'\xffNO_DEBE_LEERSE')
        with patch('contexto_v3._read_input', wraps=_read_input) as reader:
            with self.assertRaises(ValueError):
                _join_inputs([first, second, third], '|', max_bytes=7)
        self.assertEqual([call.args[0] for call in reader.call_args_list], [first, second])
        self.assertEqual(reader.call_args_list[1].kwargs['max_bytes'], 2)


if __name__ == '__main__':
    unittest.main()
