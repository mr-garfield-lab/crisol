"""Reconstrucción exacta y rechazo de bases/operaciones alteradas."""
from copy import deepcopy
import json
import random
import unittest

from contexto_core.delta import (
    create_snapshot, validate_snapshot, full_envelope, make_delta,
    apply_delta, transport_text, transport_metrics,
)


def snapshot(text, origin='proyecto-1'):
    return create_snapshot({'text': text}, origin=origin)


def large_text():
    return ''.join(f'archivo_{i}.py | sha256:{i:064x}\n  funcion_{i}@L10-L30\n' for i in range(80))


class DeltaTests(unittest.TestCase):
    def setUp(self):
        self.before = snapshot(large_text())
        self.after = snapshot(large_text().replace('funcion_35@L10-L30', 'funcion_35@L10-L31'))

    def test_changed_map_roundtrips_exactly_and_json_overhead_is_counted(self):
        envelope = make_delta(self.before, self.after)
        self.assertEqual(envelope['mode'], 'delta')
        self.assertEqual(apply_delta(self.before, envelope), self.after)
        wire = transport_text(envelope)
        self.assertEqual(json.loads(wire), envelope)
        metrics = transport_metrics(self.before, self.after, envelope)
        self.assertEqual(metrics['transmitted']['characters'], len(wire))
        self.assertEqual(metrics['transmitted']['tokens_estimated'], (len(wire)+2)//3)
        self.assertIsNone(metrics['transmitted']['tokens_measured'])
        self.assertEqual(metrics['plain_text_measure']['characters'], len(self.after['text']))
        self.assertGreater(metrics['saved_count'], 0)

    def test_no_raw_query_or_hidden_metadata_is_added_to_snapshot(self):
        packet = {'text': 'Tarea: [OCULTA]\n', 'query': 'password=valor_no_enviar',
                  'selected': [{'source': 'NO_ENVIAR'}], 'metrics': {'private': 'OTRO_DATO'}}
        wire = json.dumps(create_snapshot(packet))
        self.assertNotIn('valor_no_enviar', wire)
        self.assertNotIn('NO_ENVIAR', wire)
        self.assertNotIn('OTRO_DATO', wire)

    def test_unchanged_large_map_has_empty_patch(self):
        envelope = make_delta(self.before, self.before)
        self.assertEqual(envelope['mode'], 'delta')
        self.assertEqual(envelope['changes'], [])
        self.assertEqual(apply_delta(self.before, envelope), self.before)

    def test_full_fallback_when_patch_is_not_smaller(self):
        before, after = snapshot('a\n'), snapshot('b\n')
        envelope = make_delta(before, after)
        self.assertEqual(envelope['mode'], 'full')
        self.assertEqual(apply_delta(None, envelope), after)
        self.assertEqual(transport_metrics(None, after, envelope)['saved_count'], 0)

    def test_different_origin_requires_full_context(self):
        after = snapshot(self.after['text'], origin='otro-proyecto')
        envelope = make_delta(self.before, after)
        self.assertEqual(envelope['mode'], 'full')
        self.assertEqual(apply_delta(None, envelope), after)
        altered = make_delta(self.before, self.after)
        altered['origin'] = after['origin']
        altered['target_sha256'] = after['sha256']
        with self.assertRaisesRegex(ValueError, 'Origen'):
            apply_delta(self.before, altered)

    def test_rejects_missing_wrong_and_declared_mismatching_base(self):
        envelope = make_delta(self.before, self.after)
        for base in (None, snapshot('otra base')):
            with self.assertRaisesRegex(ValueError, 'base'):
                apply_delta(base, envelope)
        with self.assertRaisesRegex(ValueError, 'base declarada'):
            apply_delta(self.before, envelope, expected_base_sha256='0'*64)
        self.assertEqual(apply_delta(self.before, envelope, expected_base_sha256=self.before['sha256']), self.after)

    def test_rejects_snapshot_and_patch_tampering(self):
        wrong = deepcopy(self.before)
        wrong['text'] += 'alterado'
        with self.assertRaisesRegex(ValueError, 'Hash'):
            validate_snapshot(wrong)
        envelope = make_delta(self.before, self.after)
        envelope['changes'][0]['insert'] += 'alterado'
        with self.assertRaisesRegex(ValueError, 'Hash del destino'):
            apply_delta(self.before, envelope)
        full = full_envelope(self.after)
        full['text'] += 'alterado'
        with self.assertRaisesRegex(ValueError, 'Hash del destino'):
            apply_delta(None, full)

    def test_rejects_duplicate_overlap_out_of_range_and_noninteger_changes(self):
        envelope = make_delta(self.before, self.after)
        patch = envelope['changes'][0]
        invalid_lists = [
            [patch, deepcopy(patch)],
            [{'start': 0, 'delete': 4, 'insert': ''}, {'start': 2, 'delete': 1, 'insert': ''}],
            [{'start': 100000, 'delete': 1, 'insert': 'x'}],
            [{'start': -1, 'delete': 1, 'insert': 'x'}],
            [{'start': True, 'delete': 1, 'insert': 'x'}],
            [{'start': 0.0, 'delete': 1, 'insert': 'x'}],
            [{'start': 0, 'delete': 0, 'insert': ''}],
        ]
        for changes in invalid_lists:
            with self.subTest(changes=changes):
                malformed = dict(envelope, changes=changes)
                with self.assertRaises(ValueError):
                    apply_delta(self.before, malformed)

    def test_roundtrip_insert_delete_unicode_crlf_and_missing_final_newline(self):
        cases = [('', ''), ('', 'nueva\n'), ('anterior\n', ''),
                 ('a\r\nb\r\nc', 'a\r\nñ😀\r\nc'),
                 ('a\nb\nc\n', 'a\nc\n'), ('a\u2028b\n', 'a\u2028c\n')]
        for before, after in cases:
            with self.subTest(before=before, after=after):
                original, target = snapshot(before), snapshot(after)
                self.assertEqual(apply_delta(original, make_delta(original, target)), target)

    def test_large_line_count_uses_bounded_diff_and_preserves_text(self):
        text = ''.join(f'linea {i}\n' for i in range(6000))
        before, after = snapshot(text), snapshot(text.replace('linea 3000\n', 'linea modificada\n'))
        envelope = make_delta(before, after)
        self.assertEqual(envelope['mode'], 'delta')
        self.assertEqual(apply_delta(before, envelope), after)

    def test_schema_rejects_unknown_fields_and_malformed_origin(self):
        wrong = dict(self.before, extra='dato')
        with self.assertRaises(ValueError):
            validate_snapshot(wrong)
        with self.assertRaises(ValueError):
            create_snapshot({'text': 'x'}, origin=123)
        envelope = dict(full_envelope(self.before), changes=[])
        with self.assertRaises(ValueError):
            apply_delta(None, envelope)

    def test_deterministic_snapshot_and_transport(self):
        self.assertEqual(snapshot(self.before['text']), self.before)
        self.assertEqual(transport_text(make_delta(self.before, self.after)),
                         transport_text(make_delta(self.before, self.after)))

    def test_seeded_edit_sequences_always_reconstruct_exact_text(self):
        generator = random.Random(331)
        for _ in range(100):
            lines = [f'dato_{generator.randrange(30)}\n' for _ in range(generator.randrange(40))]
            before = snapshot(''.join(lines))
            for _ in range(generator.randrange(1, 8)):
                start = generator.randrange(len(lines)+1)
                end = generator.randrange(start, len(lines)+1)
                replacement = [f'nuevo_{generator.randrange(9)}😀\r\n' for _ in range(generator.randrange(4))]
                lines[start:end] = replacement
            after = snapshot(''.join(lines))
            self.assertEqual(apply_delta(before, make_delta(before, after)), after)


if __name__ == '__main__':
    unittest.main()
