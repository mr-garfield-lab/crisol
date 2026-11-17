"""El empaquetado compacto debe conservar línea, posición y fronteras de datos."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from contexto_core.evidence import _render_source_lines, build_bundle
from contexto_core.index import connect, scan
from contexto_core.tokens import TokenCounter
from contexto_core.budget import BudgetError


class EvidenceV35Tests(unittest.TestCase):
    def test_ranges_are_lossless_and_keep_separate_gaps_and_fence_boundaries(self):
        source = {n: f'    item_{n} = {n}' for n in list(range(10, 36)) + list(range(41, 65))}
        source[20] = '    marker = "``` ~~~"'
        rendered, kind = _render_source_lines(source, TokenCounter())
        self.assertEqual(kind, 'fenced_ranges')
        decoded, i = {}, 1
        while i < len(rendered):
            start, end = (int(x[1:]) for x in rendered[i].rstrip(':').split('-'))
            fence = rendered[i + 1][:-len('python')]
            self.assertTrue(fence and len(set(fence)) == 1)
            for n, line in enumerate(rendered[i + 2:i + 2 + end - start + 1], start):
                self.assertNotIn(fence, line)
                decoded[n] = line
            i += 2 + end - start + 1
            self.assertEqual(rendered[i], fence)
            i += 1
        self.assertEqual(decoded, source)

    def test_unusual_line_separator_keeps_numbered_positions(self):
        source = {n: f'    x{n} = {n}' for n in range(1, 50)}
        source[20] += ' # \u2028'
        rendered, kind = _render_source_lines(source, TokenCounter())
        self.assertEqual(kind, 'numbered')
        self.assertEqual(rendered[19], 'L20: ' + source[20])

    def test_required_full_function_fits_compact_budget_without_losing_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'project'; root.mkdir()
            lines = ['def build():'] + [f'    value_{i} = {i}' for i in range(80)] + ['    return value_79']
            (root/'mod.py').write_text('\n'.join(lines) + '\n')
            db = connect(Path(tmp)/'index.sqlite')
            try:
                scan(root, db)
                auto = build_bundle(root, db, 'build', budget=4000,
                                    required=[('mod.py','build')], include_tests=False)
                numbered = build_bundle(root, db, 'build', budget=4000,
                                        required=[('mod.py','build')], include_tests=False,
                                        line_style='numbered')
            finally:
                db.close()
            self.assertEqual(auto['unique_source_lines'], len(lines))
            self.assertEqual(auto['source_line_formats']['mod.py'], 'fenced_ranges')
            self.assertLess(auto['metrics']['tokens_estimated'], numbered['metrics']['tokens_estimated'])
            self.assertEqual(auto['selected'], numbered['selected'])
            self.assertIn('    return value_79', auto['text'])
            self.assertTrue(auto['indexed_dependencies_included'])

    def test_long_symbol_requires_opt_in_and_is_complete_or_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)/'project';root.mkdir()
            lines = ['def build():'] + [f'    v_{i} = {i}' for i in range(220)] + ['    return v_219']
            (root/'mod.py').write_text('\n'.join(lines)+'\n')
            db = connect(Path(tmp)/'index.sqlite')
            try:
                scan(root, db)
                with self.assertRaisesRegex(ValueError,'max_lines'):
                    build_bundle(root, db, 'build', required=[('mod.py','build')])
                result = build_bundle(root, db, 'build', budget=8000, include_tests=False,
                                      required=[('mod.py','build')], max_symbol_lines=250)
                self.assertEqual(result['unique_source_lines'], len(lines))
                self.assertIn('    return v_219', result['text'])
                self.assertEqual(result['selected'][0]['end'], len(lines))
                with self.assertRaises(BudgetError):
                    build_bundle(root, db, 'build', budget=300, include_tests=False,
                                 required=[('mod.py','build')], max_symbol_lines=250)
            finally:
                db.close()

    def test_changed_source_between_long_symbol_chunks_is_rejected(self):
        from contexto_core.context import _fragment
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)/'project';root.mkdir()
            source = 'def build():\n' + ''.join(f'    v_{i} = {i}\n' for i in range(220)) + '    return v_219\n'
            path = root/'mod.py';path.write_text(source)
            db = connect(Path(tmp)/'index.sqlite')
            try:
                scan(root, db)
                calls = []
                def changing(*args, **kwargs):
                    value = _fragment(*args, **kwargs)
                    calls.append(value)
                    if len(calls) == 1:
                        path.write_text(source.replace('v_219 = 219', 'v_219 = 999'))
                    return value
                with patch('contexto_core.evidence._fragment', side_effect=changing):
                    with self.assertRaisesRegex(ValueError, 'Hash cambiado|reindexar'):
                        build_bundle(root, db, 'build', budget=8000, include_tests=False,
                                     required=[('mod.py','build')], max_symbol_lines=250)
            finally:
                db.close()


if __name__ == '__main__':
    unittest.main()
