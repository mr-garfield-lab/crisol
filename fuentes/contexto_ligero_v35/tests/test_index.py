import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from contexto_core.index import allowed, connect, scan, search, symbols_of


class IndexTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / 'code'
        self.root.mkdir()
        self.db = connect(self.base / 'index.sqlite')
        self.addCleanup(self.db.close)

    def write(self, path, text):
        p = self.root / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding='utf-8')
        return p

    def test_calls_are_searchable_and_nested_calls_are_not_borrowed(self):
        self.write('worker.py', 'def execute():\n return calculateCost()\ndef parent():\n def child():\n  return remoteRequest()\n return child()\n')
        scan(self.root, self.db)
        result = search(self.db, 'calculate cost')
        self.assertEqual(result[0]['symbols'][0]['name'], 'execute')
        syms = json.loads(self.db.execute('SELECT symbols FROM files').fetchone()[0])
        self.assertNotIn('remoteRequest', next(x for x in syms if x['name'] == 'parent')['refs'])
        self.assertIn('remoteRequest', next(x for x in syms if x['name'] == 'parent.child')['refs'])

    def test_decorator_and_no_literal_or_syntax_error_content(self):
        syms = symbols_of(b'@wrapper("not_saved")\ndef decorated(x="not_saved"):\n return "not_saved"\n', '.py')
        self.assertEqual((syms[0]['line'], syms[0]['def_line'], syms[0]['end']), (1, 2, 3))
        self.assertNotIn('not_saved', json.dumps(syms))
        self.assertNotIn('not_saved', json.dumps(symbols_of(b'def not_valid(: "not_saved"', '.py')))

    def test_import_alias_graph_and_shadowing(self):
        self.write('src/pkg/engine.py', 'def calculate():\n return 1\n')
        self.write('src/pkg/worker.py', 'from .engine import calculate as go\ndef execute():\n return go()\ndef shadow(go):\n return go()\ndef local():\n return execute()\ndef dynamic(obj):\n return obj.calculate()\n')
        scan(self.root, self.db)
        edges = self.db.execute('SELECT * FROM code_edges ORDER BY src_symbol').fetchall()
        self.assertEqual(edges, [
            ('src/pkg/worker.py', 'execute', 'src/pkg/engine.py', 'calculate', 'import_call'),
            ('src/pkg/worker.py', 'local', 'src/pkg/worker.py', 'execute', 'local_call'),
        ])

    def test_full_hash_detects_same_size_mtime_edit(self):
        p = self.write('code.py', 'def uno():\n return 1\n')
        scan(self.root, self.db)
        before = p.stat()
        p.write_text('def dos():\n return 2\n')
        os.utime(p, ns=(before.st_atime_ns, before.st_mtime_ns))
        stats = scan(self.root, self.db)
        self.assertEqual(stats['changed'], 1)
        self.assertEqual(search(self.db, 'dos')[0]['symbols'][0]['name'], 'dos')
        again = scan(self.root, self.db)
        self.assertEqual(again['parse_count'], 0)
        self.assertEqual(again['unchanged'], 1)

    def test_oversize_invalidates_old_metadata(self):
        p = self.write('code.py', 'def small():\n return 1\n')
        scan(self.root, self.db, 100)
        p.write_text('#' * 101)
        stats = scan(self.root, self.db, 100)
        self.assertEqual(stats['stale_removed'], 1)
        self.assertEqual(search(self.db, 'small'), [])
        self.assertTrue(p.exists())

    def test_symlink_parent_hidden_and_fifo_are_denied(self):
        self.write('real/file.py', 'def x(): pass\n')
        (self.root / 'alias').symlink_to(self.root / 'real', target_is_directory=True)
        self.assertFalse(allowed(self.root, self.root / 'alias/file.py'))
        self.write('.hidden/file.py', 'def x(): pass\n')
        self.assertFalse(allowed(self.root, self.root / '.hidden/file.py'))
        os.mkfifo(self.root / 'pipe.py')
        self.assertFalse(allowed(self.root, self.root / 'pipe.py'))
        self.assertFalse(allowed(self.root, self.root / 'real/../real/file.py'))
        self.assertEqual(scan(self.root, self.db)['indexed_total'], 1)

    def test_old_schema_is_rejected_without_modifying_it(self):
        p = self.base / 'old.sqlite'
        db = sqlite3.connect(p)
        db.execute('CREATE TABLE files(path TEXT)')
        db.commit(); db.close()
        before = p.read_bytes()
        with self.assertRaisesRegex(ValueError, 'incompatible'):
            connect(p)
        self.assertEqual(before, p.read_bytes())

    def test_fallback_and_fts_produce_same_search(self):
        self.write('métrica.py', 'def calcularCosto():\n return 1\ndef información():\n return calcularCosto()\n')
        scan(self.root, self.db)
        fts_results = search(self.db, 'informacion calcular costo')
        self.db.execute("UPDATE meta SET value='0' WHERE key='fts5'")
        fallback = search(self.db, 'informacion calcular costo')
        self.assertEqual(fts_results, fallback)

    def test_atomic_transaction_on_parse_failure(self):
        self.write('valid.py', 'def valid():\n return 1\n')
        self.write('broken.py', 'def broken(\n')
        stats = scan(self.root, self.db)
        self.assertEqual(stats['indexed_total'], 2)
        self.assertEqual(search(self.db, 'valid')[0]['path'], 'valid.py')
        stats = scan(self.root, self.db)
        self.assertEqual(stats['unchanged'], 2)

    def test_imported_module_and_absolute_import(self):
        self.write('src/pkg/engine.py', 'def calculate():\n return 1\n')
        self.write('src/pkg/worker.py', 'import pkg.engine as en\nimport pkg.engine\nfrom . import engine\ndef a():\n return en.calculate()\ndef b():\n return pkg.engine.calculate()\ndef c():\n return engine.calculate()\n')
        scan(self.root, self.db)
        edges = self.db.execute('SELECT src_symbol,dst_symbol FROM code_edges ORDER BY src_symbol').fetchall()
        self.assertEqual(edges, [('a', 'calculate'), ('b', 'calculate'), ('c', 'calculate')])

    def test_duplicate_symbols_not_resolved(self):
        self.write('a.py', 'def helper(): pass\ndef helper(): pass\ndef caller():\n return helper()\n')
        scan(self.root, self.db)
        self.assertEqual(self.db.execute('SELECT count(*) FROM code_edges').fetchone()[0], 0)

    def test_module_rebinding_does_not_claim_static_destination(self):
        self.write('engine.py', 'def calculate(): pass\n')
        self.write('worker.py', 'from engine import calculate as go\ngo = replacement\ndef helper(): pass\nhelper = other\ndef caller():\n go()\n helper()\n')
        scan(self.root, self.db)
        self.assertEqual(self.db.execute('SELECT count(*) FROM code_edges').fetchone()[0], 0)

    def test_empty_and_malicious_fts_queries(self):
        self.write('worker.py', 'def retrieve(): pass\n')
        scan(self.root, self.db)
        self.assertEqual(search(self.db, ''), [])
        self.assertEqual(search(self.db, '" OR * :'), [])
        with self.assertRaises(ValueError):
            search(self.db, 'retrieve', limit=-1)


if __name__ == '__main__':
    unittest.main()
