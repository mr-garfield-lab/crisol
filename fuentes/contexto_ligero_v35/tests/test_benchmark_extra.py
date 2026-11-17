"""Invariantes del harness, sin usar ni ajustar resultados del ranking."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import EJECUTAR_PRUEBAS as runner

SPEC = importlib.util.spec_from_file_location('benchmark_worker_for_test', runner.ROOT / 'benchmarks' / 'worker.py')
worker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(worker)


class ExtendedBenchmarkTests(unittest.TestCase):
    def test_frozen_new_tasks_and_original_baseline_are_intact(self):
        self.assertTrue(runner.independent_integrity()['ok'])
        self.assertTrue(runner.baseline_integrity()['ok'])

    def test_synthetic_oracles_validate_without_importing_project(self):
        tasks = json.loads((runner.ROOT / 'benchmarks/tasks_independientes.json').read_text())['tasks']
        self.assertEqual(len(tasks), 8)
        # readonly_guard.py raises at import; AST validation must not execute it.
        worker.validate_oracles(runner.ROOT / 'benchmarks/fixtures/proyecto_independiente', tasks)
        self.assertNotIn('commerce.readonly_guard', sys.modules)

    def test_corpus_manifest_detects_same_size_mtime_change(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'sample.py'
            path.write_text('value = 1\n')
            info = path.stat()
            first = worker.corpus_hashes(root)
            path.write_text('value = 2\n')
            os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns))
            self.assertNotEqual(first, worker.corpus_hashes(root))

    def test_runner_preserves_optional_dependency_path(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            deps = folder / 'deps'
            deps.mkdir()
            (deps / 'local_optional_fixture.py').write_text('VALUE = "loaded"\n')
            with patch.dict(os.environ, {'PYTHONPATH': str(deps)}):
                result = runner.run([sys.executable, '-B', '-c',
                    'import local_optional_fixture; print(local_optional_fixture.VALUE)'], folder, 'optional_path')
            self.assertEqual(result['returncode'], 0)
            self.assertIn('loaded', (folder / 'optional_path.log').read_text())


if __name__ == '__main__':
    unittest.main()
