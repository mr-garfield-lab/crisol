"""Regresión de ranking y consistencia del índice por símbolo; sin umbrales de reloj."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from contexto_core import index


BASE = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'contexto_core._baseline_fast_index',
    BASE / 'comparacion/v33_validado/contexto_core/index.py')
BASELINE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BASELINE)


class FastIndexTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'project'
        self.root.mkdir()
        self.db = index.connect(Path(self.tmp.name) / 'current.sqlite')
        self.addCleanup(self.db.close)

    def write(self, rel, text):
        target = self.root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding='utf-8')
        return target

    def fill_corpus(self):
        self.write('src/cálculo.py', 'def calcularCosto(base):\n return base\ndef informeMensual():\n return calcularCosto(1)\n')
        self.write('src/contexto.py', 'class Mensajes:\n def __init__(self):\n  pass\n def construir(self):\n  return estimar_tokens("not_stored")\ndef estimar_tokens(texto):\n return len(texto)\n')
        self.write('src/memoria.py', 'class BancoMemoria:\n def buscar(self, consulta):\n  return recuperar(consulta)\ndef recuperar(x):\n return x\n')
        self.write('tests/test_calculo.py', 'def test_informeMensual():\n assert calcularCosto(1) == 1\n')
        self.write('manual/calculo.md', '# calcular costo\nTexto que no entra en el índice.\n')
        self.write('src/repetido.py', 'def duplicada(): pass\ndef duplicada(): pass\n')
        self.write('src/invalid.py', 'def broken(\n')
        for n in range(18):
            self.write(f'src/grupo_{n}.py', '\n'.join(
                f'def procesarLote_{i}(entrada):\n return validarEntrada(entrada)\n' for i in range(14)))

    def test_rankings_match_previous_version_for_diverse_queries_and_fts_fallback(self):
        self.fill_corpus()
        baseline_db = BASELINE.connect(Path(self.tmp.name) / 'baseline.sqlite')
        self.addCleanup(baseline_db.close)
        BASELINE.scan(self.root, baseline_db)
        index.scan(self.root, self.db)
        queries = ('calcular costo', 'informe mensual', 'test informe', 'contexto presupuesto',
                   'memoria recuperar', 'validar entrada', 'procesar lote', 'duplicada',
                   'manual calculo', 'invalid', 'missing', '" OR *')
        for fallback in (False, True):
            if fallback:
                for db in (self.db, baseline_db):
                    db.execute("UPDATE meta SET value='0' WHERE key='fts5'")
            for query in queries:
                with self.subTest(query=query, fallback=fallback):
                    self.assertEqual(index.search(self.db, query, 7), BASELINE.search(baseline_db, query, 7))

    def test_only_returned_symbol_payloads_are_decoded(self):
        self.fill_corpus()
        index.scan(self.root, self.db)
        with patch.object(index.json, 'loads', wraps=json.loads) as decoder:
            rows = index.search(self.db, 'procesar lote', limit=2)
        self.assertEqual(len(rows), 2)
        self.assertEqual(decoder.call_count, sum(len(row['symbols']) for row in rows))
        self.assertLessEqual(decoder.call_count, 6)

    def test_scan_replaces_symbols_without_stale_cache_or_payload(self):
        path = self.write('worker.py', 'def calcular():\n return 1\n')
        index.scan(self.root, self.db)
        self.assertEqual(index.lookup_symbol(self.db, 'worker.py', 'calcular')['line'], 1)
        path.write_text('def reemplazar():\n return 1\n')
        index.scan(self.root, self.db)
        self.assertEqual(index.search(self.db, 'calcular'), [])
        with self.assertRaisesRegex(ValueError, 'no encontrado'):
            index.lookup_symbol(self.db, 'worker.py', 'calcular')
        self.assertEqual(index.lookup_symbol(self.db, 'worker.py', 'reemplazar')['name'], 'reemplazar')
        path.write_text('#' * 101)
        index.scan(self.root, self.db, max_bytes=100)
        self.assertEqual(self.db.execute('SELECT count(*) FROM symbol_index').fetchone()[0], 0)

    def test_symbol_failure_rolls_back_file_and_normalized_index_together(self):
        path = self.write('worker.py', 'def original():\n return 1\n')
        index.scan(self.root, self.db)
        before_files = self.db.execute('SELECT * FROM files').fetchall()
        before_symbols = self.db.execute('SELECT * FROM symbol_index').fetchall()
        path.write_text('def changed():\n return 2\n')
        with patch.object(index, '_store_symbols', side_effect=RuntimeError('synthetic failure')):
            with self.assertRaises(RuntimeError):
                index.scan(self.root, self.db)
        self.assertEqual(self.db.execute('SELECT * FROM files').fetchall(), before_files)
        self.assertEqual(self.db.execute('SELECT * FROM symbol_index').fetchall(), before_symbols)

    def test_duplicate_definitions_stay_ambiguous(self):
        self.write('repeated.py', 'def repeated(): pass\ndef repeated(): pass\n')
        index.scan(self.root, self.db)
        self.assertEqual(self.db.execute('SELECT count(*) FROM symbol_index').fetchone()[0], 2)
        with self.assertRaisesRegex(ValueError, 'ambiguo'):
            index.lookup_symbol(self.db, 'repeated.py', 'repeated')

    def test_prior_schema_is_rejected_without_mutation(self):
        path = Path(self.tmp.name) / 'previous.sqlite'
        previous = BASELINE.connect(path)
        previous.close()
        original = path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'incompatible'):
            index.connect(path)
        self.assertEqual(path.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
