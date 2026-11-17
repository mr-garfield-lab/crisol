"""Medición explícita. El modo predeterminado no depende de paquetes externos."""
import hashlib
from pathlib import Path


class TokenCounter:
    def __init__(self, tokenizer_json=None):
        self.tokenizer = None
        self.name = None
        self.sha256 = None
        if tokenizer_json is not None:
            try:
                from tokenizers import Tokenizer
            except ImportError as exc:
                raise ValueError('tokenizers no está instalado; no se instalará automáticamente') from exc
            path = Path(tokenizer_json)
            self.sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
            self.tokenizer = Tokenizer.from_file(str(path))
            # Un JSON puede activar truncamiento/padding: medir todo el texto,
            # sin recortarlo silenciosamente ni añadir relleno al conteo.
            self.tokenizer.no_truncation()
            self.tokenizer.no_padding()
            self.name = 'tokenizers local JSON (sin tokens especiales)'

    @property
    def unit(self):
        return 'measured' if self.tokenizer is not None else 'estimated'

    def measured(self, text):
        return len(self.tokenizer.encode(text, add_special_tokens=False).ids) if self.tokenizer else None

    def count(self, text):
        real = self.measured(text)
        return real if real is not None else (len(text) + 2) // 3

    def metrics(self, text):
        return {'characters': len(text), 'utf8_bytes': len(text.encode('utf-8')),
                'tokens_estimated': (len(text) + 2) // 3,
                'tokens_measured': self.measured(text), 'tokenizer': self.name,
                'tokenizer_sha256': self.sha256,
                'estimation_method': 'ceil(characters/3); no es cota de tokens reales',
                'budget_unit': self.unit}
