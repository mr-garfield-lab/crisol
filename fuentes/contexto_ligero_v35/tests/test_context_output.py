import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

from contexto_v3 import connect, scan, packet, build_packet, snippet, excerpt
from contexto_core.safety import read_bounded
from contexto_core.tokens import TokenCounter


class ContextOutputTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'project'
        self.root.mkdir()
        self.db = connect(Path(self.tmp.name) / 'new.sqlite')
        self.addCleanup(self.db.close)

    def write(self, path, text):
        p = self.root / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding='utf-8')

    def test_exact_budget_with_many_omissions_and_stale_sources(self):
        for i in range(35):
            self.write(f'modulo_contexto_largo_{i}.py', 'def construir_contexto():\n    return 1\n')
        scan(self.root, self.db)
        for i in range(0, 35, 2):
            self.write(f'modulo_contexto_largo_{i}.py', 'def construir_contexto():\n    return 2\n')
        for budget in (300, 450, 600, 2000):
            result = build_packet(self.root, self.db, 'construir contexto', budget, limit=100)
            self.assertLessEqual(result['metrics']['tokens_estimated'], budget)
            self.assertLessEqual(len(result['text']), 3 * budget)
            self.assertTrue(result['stale'])
            self.assertIn('reindexar', result['text'])
            self.assertIsNone(result['metrics']['tokens_measured'])

    def test_no_silent_query_truncation(self):
        scan(self.root, self.db)
        with self.assertRaisesRegex(ValueError, 'presupuesto'):
            packet(self.root, self.db, 'contexto ' * 600, 300)

    def test_decorators_and_full_hash_in_snippet(self):
        source = '@decorador(1)\ndef funcion():\n    return 9\n'
        self.write('mod.py', source)
        scan(self.root, self.db)
        text = snippet(self.root, self.db, 'mod.py', 'funcion')
        self.assertIn('L1: @decorador(1)', text)
        self.assertIn(hashlib.sha256(source.encode()).hexdigest(), text)

    def test_multiline_secrets_not_disclosed_even_partial_excerpt(self):
        self.write('mod.py', 'def leer():\n    password = (\n        "VALOR_NO_PUBLICAR"\n    )\n    datos = {"api_key": (\n        "OTRO_VALOR_NO_PUBLICAR"\n    )}\n    return 3\n')
        scan(self.root, self.db)
        text = snippet(self.root, self.db, 'mod.py', 'leer')
        partial = excerpt(self.root, self.db, 'mod.py', 3, 3)
        self.assertNotIn('VALOR_NO_PUBLICAR', text + partial)
        self.assertIn('OCULTA', partial)
        self.assertIn('return 3', text)

    def test_pem_and_bearer_multiline(self):
        self.write('documento.md', '-----BEGIN PRIVATE KEY-----\nVALOR_PRIVADO\n-----END PRIVATE KEY-----\nAuthorization: Bearer otrovalor\n')
        scan(self.root, self.db)
        text = excerpt(self.root, self.db, 'documento.md', 2, 4)
        self.assertNotIn('VALOR_PRIVADO', text)
        self.assertNotIn('otrovalor', text)

    def test_excerpt_enables_long_functions_without_silent_truncation(self):
        self.write('mod.py', 'def larga():\n' + '    x = 1\n' * 110 + '    return x\n')
        scan(self.root, self.db)
        with self.assertRaisesRegex(ValueError, 'max_lines'):
            snippet(self.root, self.db, 'mod.py', 'larga')
        text = excerpt(self.root, self.db, 'mod.py', 100, 112)
        self.assertIn('L112:     return x', text)
        with self.assertRaises(ValueError):
            excerpt(self.root, self.db, 'mod.py', 100, 500)

    def test_fragment_rejects_budget_instead_of_truncating(self):
        self.write('mod.py', 'def larga():\n    return "' + 'x' * 2000 + '"\n')
        scan(self.root, self.db)
        with self.assertRaisesRegex(ValueError, 'presupuesto'):
            snippet(self.root, self.db, 'mod.py', 'larga', budget=100)

    def test_symlink_changed_after_index_rejected(self):
        self.write('original.py', 'def objetivo():\n    return 1\n')
        scan(self.root, self.db)
        os.rename(self.root / 'original.py', self.root / 'reserva.py')
        (self.root / 'original.py').symlink_to(self.root / 'reserva.py')
        with self.assertRaises(ValueError):
            snippet(self.root, self.db, 'original.py', 'objetivo')

    def test_reader_limits_and_parent_traversal(self):
        self.write('mod.py', 'abcde')
        with self.assertRaises(ValueError):
            read_bounded(self.root, 'mod.py', 4)
        with self.assertRaises(ValueError):
            read_bounded(self.root, '../mod.py', 100)

    def test_resolved_dependency_in_packet(self):
        self.write('auxiliar.py', 'def ayudar():\n    return 1\n')
        self.write('main.py', 'from auxiliar import ayudar as alias\ndef objetivo():\n    return alias()\n')
        scan(self.root, self.db)
        result = build_packet(self.root, self.db, 'objetivo', limit=1)
        self.assertIn('ayudar@', result['text'])
        self.assertIn('dependencia estática', result['text'])
        self.assertNotIn('ayudar@', packet(self.root, self.db, 'objetivo', limit=1, dependencies=0))

    def test_task_decision_scope_and_redaction(self):
        scan(self.root, self.db)
        self.db.execute('INSERT INTO tasks VALUES(?,?,?,?)', ('CTX', 'contexto', 'pending', 'mantener hash'))
        self.db.execute('INSERT INTO decisions VALUES(?,?,?,?)', ('d1', 'CTX', 'no ejecutar', 'revision local'))
        self.db.execute('INSERT INTO tasks VALUES(?,?,?,?)', ('billing', 'facturas', 'pending', 'no relevante'))
        self.db.commit()
        text = packet(self.root, self.db, 'contexto')
        self.assertIn('no ejecutar', text)
        self.assertNotIn('no relevante', text)

    def test_estimation_not_measurement(self):
        m = TokenCounter().metrics('á😀中')
        self.assertEqual(m['characters'], 3)
        self.assertEqual(m['tokens_estimated'], 1)
        self.assertGreater(m['utf8_bytes'], m['characters'])
        self.assertIsNone(m['tokens_measured'])

    def test_required_symbols_preserved_or_fail_explicitly(self):
        self.write('reglas.py', 'def autorizar():\n    return False\n')
        scan(self.root, self.db)
        result = build_packet(self.root, self.db, 'sin coincidencia', required=[('reglas.py', 'autorizar')])
        self.assertIn('autorizar@', result['text'])
        with self.assertRaisesRegex(ValueError, 'requerido'):
            build_packet(self.root, self.db, 'consulta', required=[('reglas.py', 'inexistente')])
        for i in range(10):
            self.write(f'modulo_{i}.py', 'def importante():\n    pass\n')
        scan(self.root, self.db)
        with self.assertRaisesRegex(ValueError, 'requeridos'):
            build_packet(self.root, self.db, 'consulta', budget=300,
                         required=[(f'modulo_{i}.py', 'importante') for i in range(10)])


if __name__ == '__main__':
    unittest.main()
