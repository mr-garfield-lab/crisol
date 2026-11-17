"""Prueba de configuración con doble local, NO medición con tokenizador real."""
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

from contexto_core.tokens import TokenCounter


class TruncatingTokenizer:
    def __init__(self):
        self.truncate = True
        self.pad = True

    def no_truncation(self):
        self.truncate = False

    def no_padding(self):
        self.pad = False

    def encode(self, text, add_special_tokens):
        assert add_special_tokens is False
        ids = list(range(len(text)))
        if self.truncate:
            ids = ids[:2]
        if self.pad:
            ids += [0] * 10
        return types.SimpleNamespace(ids=ids)


class TokenizerConfigurationTests(unittest.TestCase):
    def test_json_configuration_cannot_truncate_or_pad_counted_text(self):
        fake = TruncatingTokenizer()
        module = types.SimpleNamespace(Tokenizer=types.SimpleNamespace(from_file=lambda path: fake))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'tokenizer.json'
            path.write_text('{}')
            with patch.dict('sys.modules', {'tokenizers': module}):
                counter = TokenCounter(path)
            self.assertFalse(fake.truncate)
            self.assertFalse(fake.pad)
            self.assertEqual(counter.count('texto completo'), len('texto completo'))


if __name__ == '__main__':
    unittest.main()
