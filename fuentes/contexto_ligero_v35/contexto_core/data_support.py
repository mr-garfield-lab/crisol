"""Soporte de datos importados del proyecto, verificado y sin ejecutar Python.

Sigue bindings locales inequívocos, no sys.path ni importlib. Los imports externos,
atributos dinámicos, mutaciones y ciclos permanecen explícitamente sin resolver.
"""
import ast
import builtins
from collections import deque
from pathlib import PurePosixPath

from .dependencies import _module_name
from .index import lookup_symbol
from .safety import decode_source, read_verified, redact
from .support import _find_symbol, _loads, _module_bindings


def _attributes(nodes, name):
    found = set()
    for node in nodes:
        for child in ast.walk(node):
            if not isinstance(child, ast.Attribute):
                continue
            parts, item = [], child
            while isinstance(item, ast.Attribute):
                parts.append(item.attr)
                item = item.value
            if isinstance(item, ast.Name) and item.id == name:
                found.add(tuple(reversed(parts)))
    # Longer paths include their prefixes; the resolver handles the longest one.
    return sorted(p for p in found if not any(p != q and q[:len(p)] == p for q in found))


def imported_context(root, db, path, symbol, support, *, max_depth=8,
                     max_files=32, max_lines=200):
    """Return verified source ranges for data reached through used imports.

    The limits cover this whole request, not each imported file. Required symbols
    are returned separately so the evidence builder can fetch complete bodies.
    `complete` concerns this bounded static analysis, never runtime Python.
    """
    if (any(type(n) is not int or n < 1 for n in (max_files, max_lines)) or
            type(max_depth) is not int or not 0 <= max_depth <= 32):
        raise ValueError('Límites de soporte importado inválidos')
    if path.endswith('.java') or lookup_symbol(db, path, symbol).get('kind') == 'Assign':
        return {'files': [], 'required_symbols': [], 'edges': [], 'unresolved': [], 'omissions': [],
                'complete': True, 'runtime_complete': False,
                'scope': 'constante de módulo: sin soporte importado'}
    paths = [row[0] for row in db.execute('SELECT path FROM files WHERE path LIKE ?', ('%.py',))]
    modules = {}
    for rel in paths:
        modules.setdefault(_module_name(rel), []).append(rel)
    cache, ranges, queue, visited, required = {}, {}, deque(), set(), set()
    unresolved, omissions, edges = [], [], []
    used_lines = set()

    def doubt(rel, name, reason):
        item = {'path': rel, 'name': name, 'reason': reason}
        if item not in unresolved:
            unresolved.append(item)

    def load(rel):
        if rel not in cache:
            if len(cache) >= max_files:
                omissions.append({'path': rel, 'reason': 'import_support_file_limit'})
                return None
            raw, record = read_verified(root, db, rel)
            source = decode_source(raw, python=True)
            try:
                tree = ast.parse(source)
            except (SyntaxError, ValueError, RecursionError) as exc:
                raise ValueError('Soporte importado no analizable; reindexar') from exc
            bindings, mutations, _, dynamic = _module_bindings(tree)
            lines, _ = redact(source, python=True)
            cache[rel] = {'tree': tree, 'bindings': bindings, 'mutations': mutations,
                          'dynamic': dynamic, 'sha256': record[0], 'lines': lines}
        return cache[rel]

    def include(rel, node, name):
        indexes = {(rel, n) for n in range(node.lineno, node.end_lineno + 1)}
        if len(used_lines | indexes) > max_lines:
            omissions.append({'path': rel, 'name': name, 'start': node.lineno,
                              'end': node.end_lineno, 'reason': 'import_support_line_limit'})
            return False
        used_lines.update(indexes)
        ranges.setdefault(rel, {})[(node.lineno, node.end_lineno)] = name
        return True

    def schedule(rel, name, depth, ancestors, uses):
        key = rel, name
        if key in ancestors:
            doubt(rel, name, 'cyclic_data_binding')
        elif depth > max_depth:
            omissions.append({'path': rel, 'name': name, 'reason': 'import_support_depth_limit'})
        elif (rel, name, tuple(_attributes(uses, name))) not in visited:
            queue.append((rel, name, depth, ancestors, uses))

    def target(source_path, binding, full_name, depth, ancestors, uses):
        bits = full_name.split('.')
        for cut in range(len(bits), 0, -1):
            choices = modules.get('.'.join(bits[:cut]), [])
            if not choices:
                continue
            if len(choices) != 1:
                doubt(source_path, binding, 'ambiguous_imported_module')
                return
            if cut == len(bits):
                doubt(source_path, binding, 'module_value_without_static_attribute')
                return
            rel, name = choices[0], '.'.join(bits[cut:])
            if depth + 1 > max_depth:
                omissions.append({'path': rel, 'name': name, 'reason': 'import_support_depth_limit'})
                return
            try:
                found = lookup_symbol(db, rel, name)
            except ValueError:
                found = None
            if found is None or found.get('kind') == 'Assign':
                # A dict/object attribute needs its defining assignment; its
                # runtime attribute lookup is not asserted to be resolved.
                # Indexed module constants keep this assignment path so their
                # transitive values are still followed.
                if '.' in name:
                    doubt(rel, name, 'data_attribute_runtime')
                    name = name.partition('.')[0]
                schedule(rel, name, depth + 1, ancestors, uses)
            else:
                required.add((rel, name))
            edges.append({'src_path': source_path, 'binding': binding,
                          'dst_path': rel, 'name': name})
            return
        doubt(source_path, binding, 'external_import_not_in_project')

    def follow_import(rel, name, node, depth, ancestors, uses):
        alias = next((a for a in node.names if
                      (a.asname or (a.name.split('.')[0] if isinstance(node, ast.Import) else a.name)) == name), None)
        if alias is None:
            doubt(rel, name, 'wildcard_or_ambiguous_import')
            return
        attributes = _attributes(uses, name)
        if isinstance(node, ast.ImportFrom):
            package = _module_name(rel)
            if PurePosixPath(rel).stem != '__init__':
                package = package.rpartition('.')[0]
            prefix = package.split('.') if package else []
            if node.level:
                if node.level > len(prefix):
                    doubt(rel, name, 'relative_import_outside_project')
                    return
                base = prefix[:len(prefix) - node.level + 1] + ([node.module] if node.module else [])
            else:
                base = [node.module] if node.module else []
            base = '.'.join(base + [alias.name])
            # A from-import can be a value, callable, class or submodule.
            if base in modules and attributes:
                names = [base + '.' + '.'.join(parts) for parts in attributes]
            else:
                names = [base]
        else:
            if not attributes:
                doubt(rel, name, 'module_value_without_static_attribute')
                return
            base = alias.name if alias.asname else alias.name.split('.')[0]
            names = [base + '.' + '.'.join(parts) for parts in attributes]
        for full_name in names:
            target(rel, name, full_name, depth, ancestors, uses)

    initial = load(path)
    if initial['sha256'] != support['sha256']:
        raise ValueError('Hash cambió al leer soporte importado; reindexar')
    meta = lookup_symbol(db, path, symbol)
    selected = _find_symbol(initial['tree'], symbol, meta.get('def_line', meta['line']))
    used_names = set().union(*(set(r['names']) for r in support['ranges'])) if support['ranges'] else set()
    uses = [selected] + [n for n in initial['tree'].body if any(
        r['start'] <= n.lineno <= r['end'] for r in support['ranges'])]
    for name in sorted(used_names):
        options = initial['bindings'].get(name, [])
        if any(kind == 'import' for _, kind, _, _ in options):
            schedule(path, name, 0, (), uses)
    while queue:
        rel, name, depth, ancestors, uses = queue.popleft()
        visit_key = rel, name, tuple(_attributes(uses, name))
        if visit_key in visited:
            continue
        visited.add(visit_key)
        info = load(rel)
        if info is None:
            continue
        options = info['bindings'].get(name, [])
        if not options:
            if name not in dir(builtins):
                doubt(rel, name, 'imported_binding_not_defined')
            continue
        if len(options) != 1 or any(conditional for _, _, conditional, _ in options) or info['mutations'].get(name):
            doubt(rel, name, 'ambiguous_or_mutated_data_binding')
            # Preserve the relevant statements but do not assert a resolved value.
            for envelope, _, _, _ in options + info['mutations'].get(name, []):
                include(rel, envelope, name)
            continue
        if info['dynamic'] or info['bindings'].get('*'):
            doubt(rel, name, 'dynamic_module_data_binding')
        envelope, kind, _, node = options[0]
        trail = ancestors + ((rel, name),)
        if kind == 'definition':
            required.add((rel, name))
        elif kind == 'import':
            if rel != path and not include(rel, envelope, name):
                continue
            follow_import(rel, name, node, depth, trail, uses)
        elif kind == 'assignment':
            if not include(rel, envelope, name):
                continue
            if any(isinstance(n, ast.Call) for n in ast.walk(node)):
                doubt(rel, name, 'data_initializer_calls_code')
            for dependency in sorted(_loads(node)):
                schedule(rel, dependency, depth, trail, [node])
        else:
            include(rel, envelope, name)
            doubt(rel, name, 'unsupported_data_binding')
    files = []
    for rel, spans in sorted(ranges.items()):
        info = cache[rel]
        files.append({'path': rel, 'sha256': info['sha256'], 'ranges': [
            {'start': start, 'end': end, 'names': [name],
             'lines': info['lines'][start - 1:end], 'kind': 'imported_data_support'}
            for (start, end), name in sorted(spans.items())]})
    return {'files': files, 'required_symbols': [{'path': p, 'symbol': n} for p, n in sorted(required)],
            'edges': edges, 'unresolved': unresolved, 'omissions': omissions,
            'complete': not unresolved and not omissions, 'runtime_complete': False,
            'scope': 'bindings importados estáticos; no ejecución ni dependencias externas'}
