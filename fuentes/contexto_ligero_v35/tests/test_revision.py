"""Regresiones de revisión independiente, con valores sensibles neutrales."""
from pathlib import Path
import tempfile
import unittest

from contexto_v3 import connect, scan, snippet, excerpt


class RevisionIndependienteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'project'
        self.root.mkdir()
        self.db = connect(Path(self.tmp.name) / 'index.sqlite')
        self.addCleanup(self.db.close)

    def test_subscript_sensitive_assignment_hides_multiline_value(self):
        (self.root / 'mod.py').write_text(
            'def configure():\n    settings["password"] = (\n'
            '        "valor_123456"\n    )\n    return True\n')
        scan(self.root, self.db)
        text = snippet(self.root, self.db, 'mod.py', 'configure')
        partial = excerpt(self.root, self.db, 'mod.py', 3, 3)
        self.assertNotIn('valor_123456', text + partial)
        self.assertIn('return True', text)

    def test_sensitive_argument_default_hides_multiline_value(self):
        (self.root / 'mod.py').write_text(
            'def configure(\n    password=(\n        "valor_123456"\n'
            '    ),\n    *, access_token=(\n        "valor_654321"\n    ),\n):\n    return True\n')
        scan(self.root, self.db)
        text = snippet(self.root, self.db, 'mod.py', 'configure')
        self.assertNotIn('valor_123456', text)
        self.assertNotIn('valor_654321', text)
        self.assertIn('return True', text)

    def test_pep263_encoding_preserves_source(self):
        (self.root / 'mod.py').write_bytes(
            b'# coding: latin-1\ndef mensaje():\n    return "Espa\xf1a"\n')
        scan(self.root, self.db)
        text = snippet(self.root, self.db, 'mod.py', 'mensaje')
        self.assertIn('return "España"', text)
        self.assertNotIn('\ufffd', text)

    def test_unicode_separator_does_not_shift_ast_line_numbers(self):
        (self.root / 'mod.py').write_text(
            'x = "a\u2028b"\ndef target():\n    return 13\n')
        scan(self.root, self.db)
        text = snippet(self.root, self.db, 'mod.py', 'target')
        self.assertIn('L2: def target():', text)
        self.assertIn('L3:     return 13', text)
        self.assertNotIn('L2: b"', text)

    def test_crlf_and_cr_have_ast_compatible_line_numbers(self):
        for i, ending in enumerate((b'\r\n', b'\r')):
            name = f'newline{i}.py'
            (self.root / name).write_bytes(ending.join([
                b'x = 1', b'def target():', b'    return 13', b'']))
            scan(self.root, self.db)
            text = snippet(self.root, self.db, name, 'target')
            self.assertIn('L2: def target():', text)
            self.assertIn('L3:     return 13', text)


if __name__ == '__main__':
    unittest.main()
