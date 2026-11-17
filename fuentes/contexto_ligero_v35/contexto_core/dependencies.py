"""Clausura conservadora de llamadas AST con límites y dudas explícitos.

Solo usa el índice local: no importa módulos, no lee literales ni ejecuta código.
Una arista es evidencia estática, no una prueba de la llamada en ejecución. Las
fuentes se deben volver a validar por SHA256 antes de compartir sus fragmentos.
"""
from collections import deque
import builtins
import json
from pathlib import PurePosixPath

from .index import lookup_symbol


_BUILTINS = frozenset(name for name in dir(builtins) if not name.startswith('_'))
_DYNAMIC_BUILTINS = frozenset({'eval', 'exec', 'getattr', 'globals', 'locals', 'vars', '__import__'})
_KINDS = frozenset({'local_call', 'import_call'})


def _module_name(path):
    parts = list(PurePosixPath(path).with_suffix('').parts)
    if parts and parts[0] == 'src':
        parts.pop(0)
    if parts and parts[-1] == '__init__':
        parts.pop()
    return '.'.join(parts)


def dependency_plan(db, seeds, *, max_depth=2, max_nodes=32):
    """Planifica dependencias para pares ``(path, nombre_cualificado)``.

    ``nodes`` excluye las semillas y deduplica destinos compartidos. Sus entradas
    tienen ``path``, ``symbol``, ``symbols`` (API de mapa), ``sha256``, ``depth`` y
    ``via``. ``edges`` incluye también ciclos y enlaces entre semillas. Ningún
    destino omitido por tamaño/profundidad se presenta como cubierto.

    ``complete`` significa: la clausura de llamadas indexadas solicitada no tiene
    omisiones ni llamadas no resueltas. No significa exhaustividad de Python en
    ejecución: despacho dinámico, reexportaciones y dependencias de datos siguen
    fuera del alcance. ``runtime_complete`` es siempre False.
    """
    if type(max_depth) is not int or not 0 <= max_depth <= 32:
        raise ValueError('max_depth debe estar entre 0 y 32')
    if type(max_nodes) is not int or not 1 <= max_nodes <= 10000:
        raise ValueError('max_nodes debe estar entre 1 y 10000')
    keys = []
    for pair in seeds:
        if (not isinstance(pair, (tuple, list)) or len(pair) != 2
                or not all(isinstance(value, str) and value for value in pair)):
            raise ValueError('Cada semilla debe ser un par (path, symbol) no vacío')
        key = tuple(pair)
        if key not in keys:
            keys.append(key)

    files = {path: {'sha256': sha, 'imports': json.loads(imports)}
             for path, sha, imports in db.execute('SELECT path,sha,imports FROM files')}
    modules = {}
    for path in files:
        if path.endswith('.py'):
            modules.setdefault(_module_name(path), []).append(path)
    symbols = {}

    def symbol_at(key):
        if key not in symbols:
            if key[0] not in files:
                raise ValueError('Archivo de dependencia no indexado')
            symbols[key] = lookup_symbol(db, *key)
        return symbols[key]

    for key in keys:
        symbol_at(key)  # Semillas inexistentes/ambiguas nunca producen un plan falso.

    unresolved, terminal_calls = [], []
    unresolved_seen = set()

    def doubt(key, call, reason, **extra):
        identity = (*key, call, reason)
        if identity not in unresolved_seen:
            unresolved_seen.add(identity)
            unresolved.append({'path': key[0], 'symbol': key[1], 'call': call,
                               'reason': reason, **extra})

    def imported_target(path, entry, call):
        module = _module_name(path)
        package = module if PurePosixPath(path).stem == '__init__' else module.rpartition('.')[0]
        base = entry['module']
        level = entry.get('level', 0)
        if level:
            package_parts = package.split('.') if package else []
            if level > len(package_parts):
                return None
            prefix = package_parts[:len(package_parts) - level + 1]
            base = '.'.join(prefix + ([base] if base else []))
        binding = '.'.join(value for value in (base, entry['symbol']) if value)
        target = binding + call[len(entry['alias']):]
        bits = target.split('.')
        for cut in range(len(bits) - 1, 0, -1):
            paths = modules.get('.'.join(bits[:cut]), [])
            if not paths:
                continue
            if len(paths) != 1:
                return None
            key = paths[0], '.'.join(bits[cut:])
            try:
                symbol_at(key)
            except ValueError:
                return None
            return key
        return None

    def classify_calls(key, adjacency):
        sym = symbol_at(key)
        source_imports = files[key[0]]['imports']
        blocked = {entry['alias'] for entry in source_imports if entry.get('blocked')}
        bindings = {}
        for entry in source_imports + sym.get('imports', []):
            if not entry.get('blocked'):
                bindings.setdefault(entry['alias'], []).append(entry)
        if sym.get('kind') == 'ClassDef':
            doubt(key, '', 'class_runtime_behaviour_not_traversed')
        calls = sym.get('calls', [])
        if len(calls) >= 100:
            doubt(key, '', 'call_metadata_may_be_truncated_at_100')
        for call in sorted(set(calls)):
            head = call.partition('.')[0]
            target = None
            candidates = []
            if head in {'self', 'cls'} and '.' in call and '.' in key[1]:
                candidate = key[0], key[1].rpartition('.')[0] + '.' + call.partition('.')[2]
                try:
                    symbol_at(candidate)
                    candidates.append({'path': candidate[0], 'symbol': candidate[1]})
                except ValueError:
                    pass
            if head in blocked or head in sym.get('shadowed', []):
                if candidates:
                    doubt(key, call, 'dynamic_dispatch', candidate_targets=candidates)
                else:
                    doubt(key, call, 'shadowed_or_dynamic_binding')
                continue
            if head in bindings:
                choices = {imported_target(key[0], entry, call) for entry in bindings[head]}
                if len(choices) == 1 and None not in choices:
                    target = next(iter(choices))
                else:
                    doubt(key, call, 'external_or_ambiguous_import')
                    continue
            elif '.' not in call:
                local = key[0], call
                try:
                    symbol_at(local)
                    target = local
                except ValueError:
                    count = db.execute('SELECT count(*) FROM symbol_index WHERE path=? AND name=?', local).fetchone()[0]
                    if count > 1:
                        doubt(key, call, 'ambiguous_local_target')
                        continue
                    if call in _DYNAMIC_BUILTINS:
                        doubt(key, call, 'dynamic_builtin')
                        continue
                    if call in _BUILTINS:
                        terminal_calls.append({'path': key[0], 'symbol': key[1], 'call': call,
                                               'reason': 'builtin_no_project_source'})
                        continue
                    doubt(key, call, 'unresolved_name_or_closure')
                    continue
            else:
                # A same-class method may be useful evidence, but self dispatch
                # can be overridden; do not silently turn the candidate into an edge.
                doubt(key, call, 'dynamic_dispatch', candidate_targets=candidates)
                continue
            if target not in adjacency:
                doubt(key, call, 'static_target_not_in_indexed_graph', candidate_targets=[{'path': target[0], 'symbol': target[1]}])

    selected = set(keys)
    queued = deque((key, 0) for key in keys)
    visited, nodes, edges, omitted = set(), {}, [], []
    edge_seen, omitted_seen = set(), set()

    def omit(source, destination, kind, depth, reason):
        identity = (*source, *destination, kind, reason)
        if identity not in omitted_seen:
            omitted_seen.add(identity)
            omitted.append({'src_path': source[0], 'src_symbol': source[1],
                            'path': destination[0], 'symbol': destination[1],
                            'kind': kind, 'depth': depth, 'reason': reason})

    while queued:
        key, depth = queued.popleft()
        if key in visited:
            continue
        visited.add(key)
        adjacency = list(db.execute(
            'SELECT dst_path,dst_symbol,kind FROM code_edges WHERE src_path=? AND src_symbol=? ORDER BY dst_path,dst_symbol,kind', key))
        classify_calls(key, {(p, s) for p, s, kind in adjacency if kind in _KINDS})
        for path, symbol, kind in adjacency:
            destination = path, symbol
            if kind not in _KINDS:
                doubt(key, '', 'unsupported_edge_kind', edge_kind=kind,
                      candidate_targets=[{'path': path, 'symbol': symbol}])
                continue
            try:
                target = symbol_at(destination)
            except ValueError:
                doubt(key, '', 'missing_or_ambiguous_edge_target', candidate_targets=[{'path': path, 'symbol': symbol}])
                continue
            if destination not in selected:
                if depth >= max_depth:
                    omit(key, destination, kind, depth + 1, 'depth_limit')
                    continue
                if len(nodes) >= max_nodes:
                    omit(key, destination, kind, depth + 1, 'node_limit')
                    continue
                selected.add(destination)
                nodes[destination] = {
                    'path': path, 'symbol': symbol, 'symbols': [target],
                    'sha256': files[path]['sha256'], 'depth': depth + 1,
                    'kind': 'static_resolved', 'reason': 'dependencia_estatica',
                    'required_for_static_closure': True, 'score': 0, 'via': [],
                }
                queued.append((destination, depth + 1))
            identity = (*key, *destination, kind)
            if identity not in edge_seen:
                edge_seen.add(identity)
                edge = {'src_path': key[0], 'src_symbol': key[1],
                        'dst_path': path, 'dst_symbol': symbol, 'kind': kind}
                edges.append(edge)
                if destination in nodes:
                    nodes[destination]['via'].append({'path': key[0], 'symbol': key[1], 'kind': kind})

    # If a node was initially beyond one route's depth but then reached through
    # a shorter route, it is covered. Keep the edge evidence instead of a false omission.
    still_omitted = []
    for entry in omitted:
        destination = entry['path'], entry['symbol']
        if destination not in selected:
            still_omitted.append(entry)
            continue
        identity = (entry['src_path'], entry['src_symbol'], *destination, entry['kind'])
        if identity not in edge_seen:
            edge_seen.add(identity)
            edges.append({'src_path': entry['src_path'], 'src_symbol': entry['src_symbol'],
                          'dst_path': destination[0], 'dst_symbol': destination[1], 'kind': entry['kind']})
            if destination in nodes:
                nodes[destination]['via'].append({'path': entry['src_path'], 'symbol': entry['src_symbol'], 'kind': entry['kind']})
    for node in nodes.values():
        node['via'].sort(key=lambda item: (item['path'], item['symbol'], item['kind']))
    return {
        'nodes': sorted(nodes.values(), key=lambda node: (node['depth'], node['path'], node['symbol'])),
        'edges': sorted(edges, key=lambda item: (item['src_path'], item['src_symbol'], item['dst_path'], item['dst_symbol'], item['kind'])),
        'unresolved': sorted(unresolved, key=lambda item: (item['path'], item['symbol'], item['call'], item['reason'])),
        'omitted': sorted(still_omitted, key=lambda item: (item['depth'], item['path'], item['symbol'], item['src_path'], item['src_symbol'])),
        'terminal_calls': sorted(terminal_calls, key=lambda item: (item['path'], item['symbol'], item['call'])),
        'complete': not (still_omitted or unresolved),
        'indexed_edges_complete': not still_omitted and not any(
            item['reason'] in {'unsupported_edge_kind', 'missing_or_ambiguous_edge_target',
                               'static_target_not_in_indexed_graph'} for item in unresolved),
        'runtime_complete': False,
        'scope': 'indexed_static_call_closure; not dynamic dispatch or data dependencies',
        'max_depth': max_depth, 'max_nodes': max_nodes,
        'seed_count': len(keys), 'visited_count': len(visited),
    }
