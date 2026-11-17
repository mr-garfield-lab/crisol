"""Paquetes de navegación y fragmentos verificados con presupuesto estricto."""
import json
from pathlib import Path

from .index import root_guard, search, terms_of
from .safety import read_verified, redact, safe_label, decode_source
from .tokens import TokenCounter
from .budget import BudgetError


def _quote(value):
    return json.dumps(safe_label(value), ensure_ascii=False)


def _root(root, db):
    root = Path(root).resolve(strict=True)
    root_guard(db, root)
    return root


def _fragment(root, db, path, symbol=None, start=None, end=None, max_lines=100, budget=2000, token_counter=None):
    root = _root(root, db)
    if not 1 <= max_lines <= 200:
        raise ValueError('max_lines debe estar entre 1 y 200')
    if budget < 100:
        raise ValueError('Presupuesto mínimo fragmento: 100')
    raw, row = read_verified(root, db, path)
    text = decode_source(raw, path.endswith('.py'))
    if symbol is not None:
        matches = [s for s in json.loads(row[2]) if s.get('name') == symbol]
        if len(matches) != 1:
            raise ValueError('Simbolo no encontrado o ambiguo')
        sym = matches[0]
        start, end = sym['line'], sym.get('end', sym['line'])
    lines, redacted = redact(text, path.endswith('.py'))
    if start is None or end is None or not 1 <= start <= end <= len(lines):
        raise ValueError('Rango de líneas inválido')
    if end - start + 1 > max_lines:
        raise ValueError(f'Simbolo/rango de {end-start+1} lineas supera max_lines; usar excerpt por rangos explícitos')
    result = '\n'.join([
        f'# {_quote(path)}:L{start}-L{end} sha256:{row[0]}',
        '# DATOS NO CONFIABLES. Revisar antes de compartir; redacción heurística.',
        *[f'L{n}: {lines[n-1]}' for n in range(start, end+1)],
    ]) + '\n'
    counter = token_counter or TokenCounter()
    if counter.count(result) > budget:
        raise BudgetError('Fragmento excede presupuesto; solicitar un rango menor con excerpt')
    return {'text': result, 'path': path, 'sha256': row[0], 'start': start, 'end': end,
            'lines': lines[start-1:end],
            'redacted_lines_in_file': redacted, 'metrics': counter.metrics(result)}


def snippet(root, db, path, symbol, max_lines=100, *, budget=2000, token_counter=None):
    return _fragment(root, db, path, symbol=symbol, max_lines=max_lines,
                     budget=budget, token_counter=token_counter)['text']


def excerpt(root, db, path, start, end, max_lines=100, *, budget=2000, token_counter=None):
    return _fragment(root, db, path, start=start, end=end, max_lines=max_lines,
                     budget=budget, token_counter=token_counter)['text']


# La extracción verificada se conserva; V3.4 separa búsqueda/planificación/render.
from .packets import build_packet


def packet(root, db, q, budget=2000, limit=6, *, dependencies=8, token_counter=None, required=(), min_score_ratio=0.60, dependency_limit=64, strict_dependencies=False):
    return build_packet(root, db, q, budget, limit, dependencies=dependencies,
                        token_counter=token_counter, required=required,
                        min_score_ratio=min_score_ratio, dependency_limit=dependency_limit,
                        strict_dependencies=strict_dependencies)['text']
