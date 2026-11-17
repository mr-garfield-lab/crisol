"""Integración opcional con tokenizers y vocabulario GPT-2 real, sin red.

Los casos se omiten expresamente si falta la biblioteca o el vocabulario.
No son pruebas de equivalencia con Claude/Codex ni de una plantilla de chat.
"""
import importlib.util
from pathlib import Path
import tempfile
import unittest

from contexto_core.tokens import TokenCounter


VOCABULARY = Path(__file__).resolve().parents[1] / 'tokenizadores/gpt2/tokenizer.json'


@unittest.skipUnless(importlib.util.find_spec('tokenizers'), 'tokenizers no instalado; prueba real no ejecutada')
@unittest.skipUnless(VOCABULARY.is_file(), 'vocabulario GPT-2 no disponible; prueba real no ejecutada')
class RealTokenizerTests(unittest.TestCase):
    def setUp(self):
        from tokenizers import Tokenizer
        self.reference = Tokenizer.from_file(str(VOCABULARY))
        self.reference.no_truncation()
        self.reference.no_padding()
        self.counter = TokenCounter(VOCABULARY)

    def test_gpt2_known_ids_and_empty_text(self):
        self.assertEqual(self.reference.encode('Hello world', add_special_tokens=False).ids, [15496, 995])
        self.assertEqual(self.counter.count('Hello world'), 2)
        self.assertEqual(self.counter.count(''), 0)
        self.assertEqual(self.counter.metrics('Hello world')['budget_unit'], 'measured')

    def test_unicode_spanish_code_count_and_roundtrip(self):
        samples = [
            'España: revisión de contexto, precisión y memoria.',
            '你好，世界 🌍\nПривет мир\nمرحبا بالعالم',
            '@decorador\ndef construir_contexto(datos):\n    return datos["líneas"]\n',
            'e\u0301 café\r\n\tfin',
        ]
        for text in samples:
            with self.subTest(text=text):
                ids = self.reference.encode(text, add_special_tokens=False).ids
                self.assertEqual(self.reference.decode(ids), text)
                self.assertEqual(self.counter.count(text), len(ids))
                self.assertEqual(self.counter.metrics(text)['tokens_measured'], len(ids))

    def test_estimate_does_not_masquerade_as_real_count(self):
        text = '你好，世界 🌍'
        metrics = self.counter.metrics(text)
        self.assertNotEqual(metrics['tokens_measured'], metrics['tokens_estimated'])
        self.assertEqual(metrics['characters'], len(text))
        self.assertEqual(len(metrics['tokenizer_sha256']), 64)

    def test_real_json_truncation_and_padding_are_disabled(self):
        text = 'Este texto completo no debe truncarse. ' * 20
        expected = len(self.reference.encode(text, add_special_tokens=False).ids)
        self.reference.enable_truncation(max_length=2)
        self.reference.enable_padding(length=16, pad_id=50256, pad_token='<|endoftext|>')
        self.assertEqual(len(self.reference.encode(text, add_special_tokens=False).ids), 16)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'configured.json'
            self.reference.save(str(path))
            counter = TokenCounter(path)
            self.assertEqual(counter.count(text), expected)
            self.assertGreater(expected, 16)


if __name__ == '__main__':
    unittest.main()
