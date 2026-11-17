"""Regresiones de seguridad/presupuesto sin tocar la referencia entregada."""
import os
from pathlib import Path
import tempfile
import unittest

from contexto_v3 import connect, scan, search, packet, snippet, edge


class TestRegressionV33(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "proyecto"
        self.root.mkdir()
        self.source = self.root / "operaciones.py"
        self.source.write_text("def procesar_datos():\n    return 1\n", encoding="utf-8")
        self.db = connect(Path(self.tmp.name) / "indice.sqlite3")
        self.addCleanup(self.db.close)
        scan(self.root, self.db)

    def test_same_size_and_mtime_change_is_detected(self):
        old = self.source.stat()
        self.source.write_text("def procesar_datos():\n    return 9\n", encoding="utf-8")
        os.utime(self.source, ns=(old.st_atime_ns, old.st_mtime_ns))
        self.assertEqual(scan(self.root, self.db)["changed"], 1)
        self.assertIn("return 9", snippet(self.root, self.db, "operaciones.py", "procesar_datos"))

    def test_packet_never_exceeds_budget_with_many_matches(self):
        for i in range(60):
            (self.root / f"procesar_modulo_{i:03d}.py").write_text("def procesar_datos():\n    return 3\n", encoding="utf-8")
        scan(self.root, self.db)
        for budget in (300, 500, 2000):
            text = packet(self.root, self.db, "procesar datos", budget, 60)
            self.assertLessEqual(len(text), budget * 3)

    def test_unbounded_query_is_rejected_or_budgeted(self):
        try:
            text = packet(self.root, self.db, "procesar " * 10000, 300)
        except ValueError:
            return
        self.assertLessEqual(len(text), 900)

    def test_oversized_changed_file_cannot_produce_old_snippet(self):
        self.source.write_text("def procesar_datos():\n    return 9\n" + "#" * 130000, encoding="utf-8")
        scan(self.root, self.db)
        with self.assertRaises(ValueError):
            snippet(self.root, self.db, "operaciones.py", "procesar_datos")

    def test_scan_does_not_execute_project(self):
        marker = Path(self.tmp.name) / "would_have_been_created"
        (self.root / "malicioso.py").write_text(
            "from pathlib import Path\nPath(" + repr(str(marker)) + ").touch()\ndef observar():\n    return 1\n", encoding="utf-8")
        scan(self.root, self.db)
        self.assertFalse(marker.exists())
        self.assertTrue(search(self.db, "observar"))

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks no disponibles")
    def test_symlink_directory_to_external_file_is_not_read(self):
        external = Path(self.tmp.name) / "externo"
        external.mkdir()
        (external / "robo.py").write_text("def externo_sensible():\n    return 123\n", encoding="utf-8")
        try:
            (self.root / "enlace").symlink_to(external, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(str(exc))
        scan(self.root, self.db)
        self.assertFalse(search(self.db, "externo_sensible"))
        with self.assertRaises(ValueError):
            snippet(self.root, self.db, "enlace/robo.py", "externo_sensible")

    def test_dependency_cycle_rejection_keeps_previous_edges(self):
        edge(self.db, "a", "b", "depends_on")
        edge(self.db, "b", "c", "depends_on")
        with self.assertRaises(ValueError):
            edge(self.db, "c", "a", "depends_on")
        edges = set(self.db.execute("SELECT src,dst FROM edges"))
        self.assertEqual(edges, {("a", "b"), ("b", "c")})


if __name__ == "__main__":
    unittest.main()
