"""Soporte local de un símbolo: imports y asignaciones, sin ejecutar el proyecto.

Los rangos son evidencia de bindings estáticos, no una reconstrucción del estado
de ejecución. Se señalan los bindings ambiguos, las closures y la introspección.
"""
import ast
import builtins
from collections import defaultdict, deque
from pathlib import Path
import symtable

from .index import lookup_symbol, root_guard
from .safety import decode_source, read_verified, redact

_DEFINITIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
_PROVIDED = set(dir(builtins)) | {
    '__name__', '__file__', '__package__', '__doc__', '__builtins__',
    '__annotations__', '__spec__', '__loader__',
}
_DYNAMIC = {'globals', 'locals', 'vars', 'eval', 'exec', '__import__'}


def _loads(node):
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}


def _target_names(node):
    if isinstance(node, ast.Name):
        return {node.id}
    if isinstance(node, (ast.Tuple, ast.List)):
        return set().union(*(_target_names(n) for n in node.elts))
    return set()


def _root_name(node):
    while isinstance(node, (ast.Attribute, ast.Subscript)):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None


def _mutation_roots(target):
    if isinstance(target, (ast.Attribute, ast.Subscript)):
        name = _root_name(target)
        return {name} if name else set()
    if isinstance(target, (ast.Tuple, ast.List)):
        return set().union(*(_mutation_roots(n) for n in target.elts))
    return set()


def _annotation_loads(node):
    result = set()
    for child in ast.walk(node):
        annotations = []
        if isinstance(child, (ast.arg, ast.AnnAssign)) and child.annotation:
            annotations.append(child.annotation)
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.returns:
            annotations.append(child.returns)
        for annotation in annotations:
            result.update(_loads(annotation))
            if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
                try:
                    result.update(_loads(ast.parse(annotation.value, mode='eval')))
                except (SyntaxError, ValueError, RecursionError):
                    pass
    return result


def _find_symbol(tree, name, def_line):
    found = []
    def walk(node, parents=()):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, _DEFINITIONS):
                chain = parents + (child.name,)
                if '.'.join(chain) == name and child.lineno == def_line:
                    found.append(child)
                walk(child, chain)
            else:
                walk(child, parents)
    walk(tree)
    if len(found) != 1:
        raise ValueError('Símbolo fuente inexistente o ambiguo; reindexar')
    return found[0]


def _find_table(table, name, line):
    matches = []
    for child in table.get_children():
        if child.get_name() == name and child.get_lineno() == line:
            matches.append((child, table))
        matches.extend(_find_table(child, name, line))
    return matches


def _header_loads(node):
    """Defaults/decoradores se evalúan en el scope exterior a la función."""
    expressions = list(node.decorator_list)
    annotations = []
    if isinstance(node, ast.ClassDef):
        expressions += list(node.bases) + [k.value for k in node.keywords]
    else:
        expressions += list(node.args.defaults) + [v for v in node.args.kw_defaults if v is not None]
        annotations += [a.annotation for a in node.args.posonlyargs + node.args.args + node.args.kwonlyargs
                        if a.annotation is not None]
        if node.args.vararg and node.args.vararg.annotation:
            annotations.append(node.args.vararg.annotation)
        if node.args.kwarg and node.args.kwarg.annotation:
            annotations.append(node.args.kwarg.annotation)
        if node.returns:
            annotations.append(node.returns)
    names = set().union(*(_loads(n) for n in expressions + annotations))
    for annotation in annotations:
        # Forward references are syntax only: parse without evaluating them.
        if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
            try:
                names.update(_loads(ast.parse(annotation.value, mode='eval')))
            except (SyntaxError, ValueError, RecursionError):
                pass
    return names


def _global_references(table):
    names, free = set(), set()
    for item in table.get_symbols():
        if item.is_referenced() and item.is_global():
            names.add(item.get_name())
        # A free variable passed through to a child still needs its outer scope.
        if item.is_free():
            free.add(item.get_name())
    # Child functions can use module globals even when their containing function
    # does not. Free names belonging to those children are provided by this scope.
    for child in table.get_children():
        child_names, _ = _global_references(child)
        names.update(child_names)
    return names, free


def _module_bindings(tree):
    """Bindings y mutaciones del módulo, sin entrar en cuerpos de funciones."""
    bindings, mutations = defaultdict(list), defaultdict(list)
    future = []
    dynamic_module = []
    def add(node, outer=None, conditional=False):
        envelope = outer or node
        def bind_targets(targets, kind):
            for target in targets:
                for name in _target_names(target):
                    bindings[name].append((envelope, kind, conditional, node))
                for name in _mutation_roots(target):
                    mutations[name].append((envelope, 'mutation', conditional, node))
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.ImportFrom) and node.module == '__future__':
                future.append(node)
            for alias in node.names:
                if alias.name == '*':
                    bindings['*'].append((envelope, 'wildcard_import', conditional, node))
                else:
                    name = alias.asname or (alias.name.split('.')[0] if isinstance(node, ast.Import) else alias.name)
                    bindings[name].append((envelope, 'import', conditional, node))
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            kind = 'annotation_only' if isinstance(node, ast.AnnAssign) and node.value is None else 'augmented_assignment' if isinstance(node, ast.AugAssign) else 'assignment'
            bind_targets(targets, kind)
        elif isinstance(node, _DEFINITIONS):
            bindings[node.name].append((envelope, 'definition', conditional, node))
            # Defaults/decorators can perform module-level walrus assignment;
            # the function/class body defines a separate namespace and is skipped.
            header = list(node.decorator_list)
            if isinstance(node, ast.ClassDef):
                header += list(node.bases) + [k.value for k in node.keywords]
            else:
                header += list(node.args.defaults) + [v for v in node.args.kw_defaults if v is not None]
            for value in header:
                add(value, envelope, conditional)
            return
        elif isinstance(node, ast.Delete):
            bind_targets(node.targets, 'deletion')
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            bind_targets([node.target], 'control_target')
        elif isinstance(node, ast.withitem) and node.optional_vars is not None:
            bind_targets([node.optional_vars], 'control_target')
        elif isinstance(node, ast.ExceptHandler) and node.name:
            bindings[node.name].append((envelope, 'exception_target', True, node))
        elif isinstance(node, ast.NamedExpr):
            bind_targets([node.target], 'named_expression')
        elif isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name:
            bindings[node.name].append((envelope, 'pattern_target', True, node))
        elif isinstance(node, ast.MatchMapping) and node.rest:
            bindings[node.rest].append((envelope, 'pattern_target', True, node))
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            if isinstance(node.value.func, ast.Attribute):
                name = _root_name(node.value.func.value)
                if name:
                    mutations[name].append((envelope, 'possible_mutation', conditional, node))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _DYNAMIC:
            dynamic_module.append(envelope)
        if isinstance(node, ast.Lambda):
            for value in list(node.args.defaults) + [v for v in node.args.kw_defaults if v is not None]:
                add(value, envelope, conditional)
            return
        # Traverse wrapper nodes such as ExceptHandler/match_case as well as
        # statements; never infer that a guarded binding is unconditional.
        guarded = conditional or isinstance(node, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try,
                                                    ast.With, ast.AsyncWith, ast.Match, ast.ExceptHandler))
        for child in ast.iter_child_nodes(node):
            add(child, envelope, guarded)
    for statement in tree.body:
        add(statement)

    return bindings, mutations, future, dynamic_module


def support_context(root, db, path, symbol, max_lines=80):
    """Return complete redacted source statements needed by static global loads.

    `ranges` contain original line numbers and no synthetic code. Each range's
    `text` is numbered (`L<n>: ...`); `lines` contains the same redacted lines
    without prefixes for callers merging overlapping evidence. The cumulative
    line budget never truncates a statement: omitted statements remain explicit.
    `required_symbols` names local definitions which must be fetched separately.
    """
    if type(max_lines) is not int or not 1 <= max_lines <= 1000:
        raise ValueError('max_lines de soporte debe estar entre 1 y 1000')
    root = Path(root).resolve(strict=True)
    root_guard(db, root)
    if not path.endswith('.py'):
        raise ValueError('Soporte AST solo disponible para Python')
    raw, record = read_verified(root, db, path)
    meta = lookup_symbol(db, path, symbol)
    source = decode_source(raw, python=True)
    try:
        tree = ast.parse(source)
        tables = symtable.symtable(source, path, 'exec')
    except (SyntaxError, ValueError, RecursionError) as exc:
        raise ValueError('No se puede analizar el soporte sin alterar la fuente') from exc
    selected = _find_symbol(tree, symbol, meta.get('def_line', meta['line']))
    candidates = _find_table(tables, selected.name, selected.lineno)
    if len(candidates) != 1:
        raise ValueError('Scope de símbolo inexistente o ambiguo')
    selected_table, parent_table = candidates[0]
    globals_used, free = _global_references(selected_table)
    unresolved = [{'name': name, 'reason': 'enclosing_scope'} for name in sorted(free)]
    for name in sorted(_header_loads(selected)):
        if parent_table.get_type() == 'module':
            globals_used.add(name)
            continue
        try:
            binding = parent_table.lookup(name)
        except KeyError:
            # String annotations are not necessarily registered in symtable.
            # An absent enclosing binding may still refer to a module name.
            globals_used.add(name)
        else:
            if binding.is_global():
                globals_used.add(name)
            else:
                unresolved.append({'name': name, 'reason': 'enclosing_definition_scope'})
    if any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in _DYNAMIC
           for n in ast.walk(selected)):
        unresolved.append({'name': symbol, 'reason': 'dynamic_namespace'})

    bindings, mutations, future, dynamic_module = _module_bindings(tree)

    for name in _annotation_loads(selected):
        try:
            binding = selected_table.lookup(name)
        except KeyError:
            globals_used.add(name)
        else:
            if binding.is_global() or selected_table.get_type() == 'class':
                globals_used.add(name)
            else:
                unresolved.append({'name': name, 'reason': 'annotation_scope_ambiguous'})

    wanted = deque(sorted(globals_used))
    visited, chosen, required_symbols = set(), {}, set()
    for statement in future:
        chosen[(statement.lineno, statement.end_lineno)] = {
            'node': statement, 'kinds': {'future_import'}, 'names': set()}
    if globals_used and bindings.get('*'):
        unresolved.append({'name': '*', 'reason': 'wildcard_can_replace_bindings'})
        for envelope, kind, _, _ in bindings['*']:
            chosen[(envelope.lineno, envelope.end_lineno)] = {'node': envelope, 'kinds': {kind}, 'names': {'*'}}
    if globals_used and dynamic_module:
        unresolved.append({'name': '*', 'reason': 'dynamic_module_namespace'})
        for envelope in dynamic_module:
            chosen[(envelope.lineno, envelope.end_lineno)] = {'node': envelope, 'kinds': {'dynamic_namespace'}, 'names': set()}
    while wanted:
        name = wanted.popleft()
        if name in visited:
            continue
        visited.add(name)
        options = bindings.get(name, [])
        if not options:
            if name not in _PROVIDED:
                unresolved.append({'name': name, 'reason': 'wildcard_or_unbound_global' if bindings.get('*') else 'unbound_global'})
            continue
        if len(options) != 1:
            unresolved.append({'name': name, 'reason': 'ambiguous_module_binding'})
        options = options + mutations.get(name, [])
        for envelope, kind, conditional, node in options:
            if conditional:
                unresolved.append({'name': name, 'reason': 'conditional_module_binding'})
            if kind in ('mutation', 'possible_mutation'):
                unresolved.append({'name': name, 'reason': 'module_mutation'})
            if kind in ('annotation_only', 'augmented_assignment', 'deletion', 'control_target',
                        'exception_target', 'named_expression', 'pattern_target'):
                unresolved.append({'name': name, 'reason': kind})
            if kind == 'definition':
                # The graph/evidence layer should fetch these bodies. Do not
                # silently treat a decorator or referenced callable as a value.
                if node is not selected:
                    required_symbols.add((path, node.name))
                continue
            start, end = envelope.lineno, envelope.end_lineno
            item = chosen.setdefault((start, end), {'node': envelope, 'kinds': set(), 'names': set()})
            item['kinds'].add(kind)
            item['names'].add(name)
            if kind == 'assignment' and len(bindings.get(name, [])) == 1 and name in _loads(node):
                unresolved.append({'name': name, 'reason': 'self_dependent_binding'})
            wanted.extend(sorted(_loads(envelope) - visited))

    redacted, hidden = redact(source, python=True)
    omissions, accepted, used_lines = [], [], set()
    for (start, end), info in sorted(chosen.items()):
        if start >= meta['line'] and end <= meta['end']:
            continue
        additional = set(range(start, end + 1)) - used_lines
        if len(used_lines) + len(additional) > max_lines:
            omissions.append({'start': start, 'end': end, 'names': sorted(info['names']), 'reason': 'support_max_lines'})
            continue
        used_lines.update(additional)
        accepted.append({'start': start, 'end': end, 'kinds': sorted(info['kinds']), 'names': sorted(info['names'])})
    merged = []
    for item in accepted:
        if merged and item['start'] <= merged[-1]['end'] + 1:
            prior = merged[-1]
            prior['end'] = max(prior['end'], item['end'])
            prior['kinds'] = sorted(set(prior['kinds'] + item['kinds']))
            prior['names'] = sorted(set(prior['names'] + item['names']))
        else:
            merged.append(item)
    for item in merged:
        start, end = item['start'], item['end']
        item['kind'] = '+'.join(item['kinds'])
        item['lines'] = redacted[start - 1:end]
        item['text'] = '\n'.join(f'L{n}: {redacted[n-1]}' for n in range(start, end + 1)) + '\n'
    unresolved = [dict(name=name, reason=reason) for name, reason in sorted({(x['name'], x['reason']) for x in unresolved})]
    return {
        'path': path, 'symbol': symbol, 'sha256': record[0], 'ranges': merged,
        'omissions': omissions, 'unresolved': unresolved,
        'required_symbols': [{'path': p, 'symbol': n} for p, n in sorted(required_symbols)],
        'complete': not omissions and not unresolved,
        'scope': 'referencias globales/imports/asignaciones estáticas locales; no estado de ejecución',
        'redacted_lines_in_file': hidden, 'support_lines': len(used_lines),
    }
