"""V3.5 retrieval: global symbol ranking, focused seeds, explicit static expansion.

The immutable index remains a metadata index. This module neither reads source
files nor imports project code. Focus selection is separate from the recall pool:
discarded lexical candidates remain visible in diagnostics, and dependencies are
not mislabelled as direct answers to the query. No benchmark answers are consulted.
"""
from collections import Counter, defaultdict, deque
import json
import math
from pathlib import PurePosixPath
import re
import unicodedata

from .index import _words, search as legacy_search, terms_of


REQUEST_WORDS = frozenset({
    'donde', 'encuentra', 'encontrar', 'localiza', 'localizar', 'necesito', 'quiero',
    'revisar', 'revisa', 'analizar', 'analiza', 'mostrar', 'muestra', 'explicar',
    'explica', 'codigo', 'funcion', 'funciones', 'metodo', 'metodos', 'archivo',
    'archivos', 'modulo', 'modulos', 'find', 'where', 'show', 'explain', 'code',
    'function', 'functions', 'method', 'methods', 'module', 'modules', 'please',
})
TEST_WORDS = frozenset({'test', 'tests', 'prueba', 'pruebas', 'regresion', 'regression'})
CLASS_WORDS = frozenset({'clase', 'class', 'constructor'})
DEPENDENCY_DEPTH = 8
DEPENDENCY_NODES = 64


def _identifier(value):
    return ''.join(char for char in unicodedata.normalize('NFKD', value.casefold())
                   if not unicodedata.combining(char)).strip('_')


def _test_path(path):
    return any(part in ('test', 'tests') or part.startswith('test_')
               for part in PurePosixPath(path).parts)


def _lex_words(value):
    # str.isupper/islower also cover Á/Ü/Greek/Cyrillic camel-case boundaries.
    parts = []
    for index, char in enumerate(value):
        if index and char.isupper() and (value[index-1].islower() or value[index-1].isdigit()):
            parts.append(' ')
        parts.append(char)
    return set(_words(''.join(parts)))


def _stem_words(path):
    name = PurePosixPath(path).stem
    if name.startswith('test_'):
        name = name[5:]
    return _lex_words(name) - {'py', 'init'}


def _hit(words, term):
    if term in words:
        return 1.0
    if len(term) >= 4 and any(word.startswith(term) for word in words):
        return 0.78
    if len(term) >= 5 and term.endswith('s') and term[:-1] in words:
        return 0.90
    return 0.0


def _explicit_identifiers(query):
    # CamelCase is just as explicit as snake_case/qualification, including Unicode.
    # Ordinary natural-language words are not treated as exact contracts.
    identifiers = re.findall(r'[\w]+(?:\.[\w]+)*', query, flags=re.UNICODE)
    marked = []
    for value in identifiers:
        camel = any(value[i].isupper() and
                    (value[i-1].islower() or value[i-1].isdigit() or
                     (value[i-1].isupper() and i+1 < len(value) and value[i+1].islower()))
                    for i in range(1, len(value)))
        if not value.endswith('.py') and ('_' in value or '.' in value or camel):
            marked.append(value)
    return {_identifier(value) for value in marked}


def _explicit_files(db, query):
    """Resolve only filenames/rutas explicitly written by the caller, no content search."""
    pattern = r'(?<![\w])/?(?:[\w.\-]+/)*[\w.\-]+\.(?:py|md|json|txt)(?![\w])'
    requested = list(dict.fromkeys(re.findall(pattern, query, flags=re.UNICODE | re.IGNORECASE)))
    records = list(db.execute('SELECT path,sha FROM files ORDER BY path')) if requested else []
    rows, seen, ambiguity, missing = [], set(), [], []
    for written in requested:
        path = PurePosixPath(written)
        if path.is_absolute() or '..' in path.parts:
            missing.append(written)
            continue
        normalized = path.as_posix().casefold()
        matches = [(rel, sha) for rel, sha in records if
                   (rel.casefold() == normalized if '/' in normalized else
                    PurePosixPath(rel).name.casefold() == normalized)]
        if not matches:
            missing.append(written)
        if len(matches) > 1:
            ambiguity.append({'file_query': written, 'candidates': [rel for rel, _ in matches]})
        for rel, sha in matches:
            if rel not in seen:
                seen.add(rel)
                rows.append({'path': rel, 'sha256': sha, 'symbols': [], 'score': 200.0,
                             'reason': 'explicit_file', 'matched_terms': terms_of(written),
                             'retrieval_stage': 'direct'})
    return rows, requested, ambiguity, missing


def _load_features(db):
    columns = ('s.id,s.path,s.name,s.line,s.end,s.kind,s.name_words,'
               's.operation_words,s.parent_words,s.ref_words,f.sha')
    records = []
    for sid, path, name, line, end, kind, words, operation, parents, refs, sha in db.execute(
        'SELECT ' + columns + ' FROM symbol_index s JOIN files f ON f.path=s.path ORDER BY s.path,s.ordinal'
    ):
        records.append({'id': sid, 'path': path, 'name': name, 'line': line,
                        'end': end, 'kind': kind, 'words': _lex_words(name),
                        'operation': _lex_words(name.rsplit('.', 1)[-1]),
                        'parents': _lex_words(name.rpartition('.')[0]),
                        'refs': set(refs.split()), 'stem': _stem_words(path),
                        'sha256': sha, 'is_test': _test_path(path)})
    return records


def _named_modules(records, query, terms, wants_tests):
    """Resuelve nombres compuestos antes de tratar sus partes como módulos distintos.

    Una parte sigue siendo módulo si lleva una operación propia en la consulta,
    se nombra como archivo o se repite por separado. La alternativa permanece en
    el ranking amplio; esto no limita la clausura de dependencias estáticas.
    """
    wanted, ordered = set(terms), terms_of(query)
    paths = {r['path'] for r in records if r['stem'] and r['stem'] <= wanted
             and (wants_tests or not r['is_test'])}
    by_path = defaultdict(list)
    for record in records:
        by_path[record['path']].append(record)
    explicit = {PurePosixPath(x).name.casefold() for x in re.findall(
        r'(?<![\w])[\w.\-/]+\.py(?![\w])', query, flags=re.UNICODE | re.IGNORECASE)}
    suppressed = []
    for small in sorted(paths):
        small_words = by_path[small][0]['stem']
        if PurePosixPath(small).name.casefold() in explicit:
            continue
        if any(ordered.count(word) > 1 for word in small_words):
            continue
        if any((r['operation'] & wanted) - r['stem'] for r in by_path[small]
               if r['kind'] != 'ClassDef'):
            continue
        for large in sorted(paths):
            large_words = by_path[large][0]['stem']
            if not small_words < large_words:
                continue
            phrase = terms_of(PurePosixPath(large).stem)
            contiguous = len(phrase) > 1 and any(ordered[i:i+len(phrase)] == phrase
                                                   for i in range(len(ordered)-len(phrase)+1))
            if contiguous:
                suppressed.append({'path': small, 'reason': 'part_of_compound_module',
                                   'compound_path': large})
                break
    return paths - {x['path'] for x in suppressed}, suppressed


def _score_candidates(db, query, terms, records=None, module_diagnostics=None):
    records = _load_features(db) if records is None else records
    if not records:
        return [], set(), set()
    wanted = set(terms)
    wants_tests = bool(wanted & TEST_WORDS)
    identifiers = _explicit_identifiers(query)
    module_paths, suppressed = _named_modules(records, query, terms, wants_tests)
    if module_diagnostics is not None:
        module_diagnostics.extend(suppressed)
    # Binary document frequency is robust to identifier repetition in generated
    # methods. Length normalization below rewards specific names over long lists.
    frequencies = Counter()
    for record in records:
        vocabulary = record['operation'] | record['parents'] | record['stem'] | record['refs']
        frequencies.update(term for term in terms if _hit(vocabulary, term))
    idf = {term: 1.0 + math.log1p((len(records) + 1) / (frequencies[term] + 1)) for term in terms}
    # Existing concept retrieval is a low-weight recall channel, never an oracle.
    legacy_ranks = {}
    for row in legacy_search(db, query, limit=100):
        for symbol in row['symbols']:
            key = row['path'], symbol['name'], symbol['line']
            legacy_ranks.setdefault(key, len(legacy_ranks))
    scored = []
    for record in records:
        op_hits = {t for t in terms if _hit(record['operation'], t)}
        path_hits = {t for t in terms if _hit(record['stem'], t)}
        parent_hits = {t for t in terms if _hit(record['parents'], t)}
        reference_hits = {t for t in terms if _hit(record['refs'], t)}
        rank = legacy_ranks.get((record['path'], record['name'], record['line']))
        if not (op_hits or path_hits or parent_hits or reference_hits or rank is not None):
            continue
        op = sum(idf[t] * _hit(record['operation'], t) for t in op_hits)
        path = sum(idf[t] * _hit(record['stem'], t) for t in path_hits)
        parent = sum(idf[t] * _hit(record['parents'], t) for t in parent_hits)
        refs = sum(idf[t] * _hit(record['refs'], t) for t in reference_hits)
        extra_words = len(record['operation'] - op_hits)
        score = 9.0 * op / (1 + 0.13 * extra_words) + 3.5 * path + 1.6 * parent + 0.65 * refs
        if module_paths:
            score *= 1.55 if record['path'] in module_paths else 0.66
        leaf = record['name'].rsplit('.', 1)[-1]
        explicit = bool({_identifier(record['name']), _identifier(leaf)} & identifiers)
        if explicit:
            score += 150
        if _identifier(leaf) in wanted:
            score += 2.0 * op
        if rank is not None:
            score += 6.0 / (1 + rank / 4)
        if record['is_test']:
            score *= 1.30 if wants_tests else 0.18
        if record['kind'] == 'ClassDef':
            score *= 0.75 if wanted & CLASS_WORDS else 0.16
        if leaf.startswith('__') and not explicit:
            score *= 0.45
        if score <= 0:
            continue
        record.update(score=score, op_hits=op_hits, path_hits=path_hits,
                      parent_hits=parent_hits, reference_hits=reference_hits,
                      explicit=explicit,
                      support=op_hits - record['stem'] or op_hits,
                      channel='identifier' if op_hits else 'reference' if reference_hits else 'module_or_concept')
        scored.append(record)
    scored.sort(key=lambda r: (-r['score'], -len(r['op_hits']), r['path'], r['line'], r['name']))
    return scored, module_paths, wanted


def _focus(scored, modules, terms, query=''):
    """Select nonredundant operations; keep ambiguity explicit instead of guessing."""
    if not scored:
        return [], []
    wants_tests = bool(terms & TEST_WORDS)
    requested_classes = [r for r in scored if r['kind'] == 'ClassDef' and
                         ((terms & CLASS_WORDS and r['operation'] & (terms - CLASS_WORDS)) or
                          r['explicit'])]
    class_members = []
    if requested_classes:
        for record in requested_classes:
            record['focus_reason'] = 'explicit_class'
        class_words = set().union(*(r['operation'] | r['stem'] for r in requested_classes))
        other_intent = terms - class_words - CLASS_WORDS - REQUEST_WORDS - TEST_WORDS
        if not other_intent:
            return requested_classes[:3], []
        # A class name in a mixed request is an anchor, not permission to erase
        # the other operations. If no member is named, retain its methods rather
        # than guessing which one implements a natural-language responsibility.
        for cls in requested_classes:
            members = [r for r in scored if r['path'] == cls['path'] and
                       r['kind'] != 'ClassDef' and r['name'].rpartition('.')[0] == cls['name']]
            matching = [r for r in members if r['op_hits'] & other_intent]
            for record in matching or members:
                record['focus_reason'] = 'explicit_class_member'
                class_members.append(record)
    pool = [r for r in scored if r['kind'] != 'ClassDef' and (wants_tests or not r['is_test'])]
    request_terms = [term for term in terms_of(query) if term not in REQUEST_WORDS]
    tests_only = bool(request_terms and request_terms[0] in TEST_WORDS)
    # "tests billing ..." asks for tests. A module/operation request mentioning
    # tests later still needs production code; mere occurrence is not exclusion.
    if tests_only and any(r['is_test'] for r in pool):
        pool = [r for r in pool if r['is_test'] or r['explicit']]
    if not pool:
        pool = scored[:]
    exact = [r for r in pool if r['explicit']]
    for record in exact:
        record['focus_reason'] = 'explicit_identifier'
    scoped = [r for r in pool if r['path'] in modules] if modules else pool
    # A filename or class name gives scope, not an extra operation. When a
    # module has operation-specific matches, do not treat every unrelated
    # function containing only that topic word as another requested operation.
    class_context = set().union(*(r['operation'] for r in scored
                                  if r['kind'] == 'ClassDef' and r['path'] in modules
                                  and r['operation'] and r['operation'] <= terms))
    def specific_terms(record):
        specific = record['op_hits'] - record['stem'] - class_context - TEST_WORDS
        leaf = _identifier(record['name'].rsplit('.', 1)[-1])
        # An exact function name remains an operation even if it is also part
        # of a class name, e.g. adaptador and AdaptadorTermux.
        if leaf in terms and leaf not in record['stem']:
            specific = specific | {leaf}
        return specific
    specific_by_path = defaultdict(bool)
    for record in scoped:
        specific = specific_terms(record)
        if specific:
            specific_by_path[record['path']] = True
    operations = []
    for record in scoped:
        specific = specific_terms(record)
        if specific:
            record['support'] = specific
            operations.append(record)
        # Tests cover positive and negative cases, including names that do not
        # repeat the exact operation; retain these when tests are requested.
        elif record['support'] and (tests_only or not specific_by_path[record['path']]):
            operations.append(record)
    chosen = list(exact)
    for record in requested_classes + class_members:
        if record not in chosen:
            chosen.append(record)
    ambiguity = []
    if operations:
        groups = defaultdict(list)
        for record in operations:
            # Separate named modules preserve multimodule questions. Without
            # an explicit module, equal operation evidence remains ambiguous.
            scope = record['path'] if modules else ''
            groups[(scope, frozenset(record['support']))].append(record)
        for (scope, support), candidates in groups.items():
            if any(other_scope == scope and support < other_support
                   for other_scope, other_support in groups):
                continue
            best = candidates[0]
            if best not in chosen:
                best['focus_reason'] = 'operation_coverage'
                chosen.append(best)
            tied = [r for r in candidates[1:] if (r['path'], r['line']) != (best['path'], best['line']) and
                    ((r['operation'] == best['operation'] and r['parent_hits'] == best['parent_hits']
                      and r['explicit'] == best['explicit']) or r['score'] >= best['score'] * 0.97)]
            if tied:
                ambiguity.append({'operation_terms': sorted(support),
                                  'candidates': [[r['path'], r['name'], r['line']] for r in [best] + tied]})
                for record in tied[:1]:
                    if record not in chosen:
                        record['focus_reason'] = 'ambiguous_operation'
                        chosen.append(record)
        # A named module does not suppress an explicitly requested operation
        # that exists only elsewhere. Retain its best lexical representative.
        covered = set().union(*(r['op_hits'] for r in chosen)) if chosen else set()
        missing_pool = [r for r in pool if r['path'] not in modules and r['op_hits'] - covered]
        for record in missing_pool:
            if record['score'] >= scored[0]['score'] * 0.48 and record['op_hits'] - covered:
                record['focus_reason'] = 'uncovered_operation'
                chosen.append(record)
                covered.update(record['op_hits'])
    else:
        # Broad module/concept questions do not justify a confident tiny answer.
        # Keep a conservative recall-oriented nucleus and disclose uncertainty.
        fallback = scoped or pool
        for record in fallback[:3]:
            if record not in chosen:
                record['focus_reason'] = 'broad_fallback'
                chosen.append(record)
    # Preserve every explicitly named module even when its public entrypoint
    # does not repeat an operation named for another module in the same query.
    covered_modules = {record['path'] for record in chosen}
    for path in sorted(modules - covered_modules):
        candidate = next((record for record in pool if record['path'] == path), None)
        if candidate is not None:
            candidate['focus_reason'] = 'module_anchor_fallback'
            chosen.append(candidate)
    chosen.sort(key=lambda r: (-r['score'], r['path'], r['line'], r['name']))
    return chosen, ambiguity


def _row(db, record, *, reason=None):
    raw = db.execute('SELECT payload FROM symbol_index WHERE id=?', (record['id'],)).fetchone()
    if raw is None:
        return None
    symbol = json.loads(raw[0])
    return {'path': record['path'], 'sha256': record['sha256'], 'symbols': [symbol],
            'score': round(record['score'], 6),
            'reason': reason or record.get('focus_reason', record.get('channel', 'static_dependency')),
            'matched_terms': sorted(record.get('op_hits', set()) | record.get('path_hits', set())),
            'retrieval_stage': 'direct' if reason != 'static_dependency' else 'dependency'}


def _static_dependencies(db, seeds, records, max_depth=DEPENDENCY_DEPTH, max_nodes=DEPENDENCY_NODES):
    by_pair = defaultdict(list)
    for record in records:
        by_pair[(record['path'], record['name'])].append(record)
    seen = {(r['path'], r['name']) for r in seeds}
    queue = deque((r['path'], r['name'], 0) for r in seeds)
    output = []
    while queue and len(output) < max_nodes:
        path, name, depth = queue.popleft()
        if depth >= max_depth:
            continue
        for dst, symbol in db.execute(
            'SELECT dst_path,dst_symbol FROM code_edges WHERE src_path=? AND src_symbol=? ORDER BY dst_path,dst_symbol',
            (path, name),
        ):
            pair = dst, symbol
            if pair in seen:
                continue
            seen.add(pair)
            matches = by_pair[pair]
            if len(matches) != 1:
                continue
            output.append(dict(matches[0], score=0.0))
            queue.append((dst, symbol, depth + 1))
            if len(output) >= max_nodes:
                break
    return output


def retrieve_detailed(db, query, limit=12):
    """Return global recall ranking plus a focused direct-symbol selection.

    limit counts symbols, not files. `selected` never claims dependency closure;
    callers must use the dependency planner and validate current source hashes.
    """
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('limit debe estar entre 1 y 100 símbolos')
    if not isinstance(query, str) or len(query) > 8192:
        raise ValueError('Consulta inválida o mayor de 8192 caracteres')
    original_terms = terms_of(query)
    file_rows, requested_files, file_ambiguity, missing_files = _explicit_files(db, query)
    file_terms = set().union(*(set(terms_of(path)) for path in requested_files)) if requested_files else set()
    if requested_files and set(original_terms) <= file_terms | REQUEST_WORDS:
        # A filename-only request must not turn into unrelated code matches for
        # its extension or stem. Files with parse errors are still explicit data.
        selected_files = file_rows[:limit]
        return {'results': selected_files, 'selected': selected_files,
                'answer_candidates': selected_files, 'omitted': [],
                'ambiguous': file_ambiguity, 'coverage': 'explicit_file_metadata_only',
                'candidate_count': len(file_rows), 'missing_explicit_files': missing_files,
                'selection': {'mode': 'recall_fallback' if file_ambiguity else 'focused_with_dependencies',
                              'fallback_reasons': ['ambiguous_file_name'] if file_ambiguity else [],
                              'answer_candidates_total': len(file_rows),
                              'answer_candidates_omitted_by_limit': max(0, len(file_rows)-limit)}}
    records = _load_features(db)
    vocabulary = set().union(*(r['operation'] | r['parents'] | r['stem'] for r in records)) if records else set()
    # A common request word may itself be an explicitly named module/function.
    # Corpus evidence takes precedence over the natural-language stop list.
    terms = [term for term in original_terms if term != 'py' and
             (term not in REQUEST_WORDS or term in vocabulary or len(original_terms) <= 2)]
    if not terms:
        return {'results': [], 'selected': [], 'answer_candidates': [], 'omitted': [], 'ambiguous': [],
                'coverage': 'no_identifier_terms', 'candidate_count': 0,
                'selection': {'mode': 'empty', 'fallback_reasons': ['no_identifier_terms']}}
    module_diagnostics = []
    ranked, modules, wanted = _score_candidates(db, query, terms, records, module_diagnostics)
    selected, ambiguous = _focus(ranked, modules, wanted, query)
    ambiguous.extend(file_ambiguity)
    # Load even non-lexical dependency destinations; source verification remains
    # the packet builder's responsibility. Only existing unambiguous edges count.
    dependency_records = _static_dependencies(db, selected, records)
    answers, seen = [], set()
    for record, reason in [(r, None) for r in selected] + [(r, 'static_dependency') for r in dependency_records]:
        key = record['path'], record['name'], record['line']
        if key in seen:
            continue
        seen.add(key)
        answers.append((record, reason))
    ordered = answers[:]
    for record in ranked:
        key = record['path'], record['name'], record['line']
        if key not in seen:
            seen.add(key)
            ordered.append((record, None))
    result = [_row(db, record, reason=reason) for record, reason in ordered[:limit]]
    answer_rows = [_row(db, record, reason=reason) for record, reason in answers[:limit]]
    fallback_reasons = []
    if ambiguous:
        fallback_reasons.append('ambiguous_identifiers')
    if any(record.get('focus_reason') in ('broad_fallback', 'module_anchor_fallback') for record in selected):
        fallback_reasons.append('broad_module_or_concept_query')
    if ranked and not selected:
        fallback_reasons.append('no_direct_selection')
    selected = selected[:limit]
    direct_rows = [_row(db, record) for record in selected]
    direct_paths = {row['path'] for row in direct_rows if row}
    additional_files = [row for row in file_rows if row['path'] not in direct_paths]
    result = (additional_files + result)[:limit]
    direct_rows = (additional_files + direct_rows)[:limit]
    answer_rows = (additional_files + answer_rows)[:limit]
    focused_ids = {r['id'] for r in selected}
    omitted = [{'path': r['path'], 'symbol': r['name'], 'reason': 'outside_focused_selection'}
               for r in ranked if r['id'] not in focused_ids]
    return {'results': [row for row in result if row], 'selected': [row for row in direct_rows if row],
            'answer_candidates': [row for row in answer_rows if row],
            'selection': {'mode': 'recall_fallback' if fallback_reasons else 'focused_with_dependencies',
                          'fallback_reasons': fallback_reasons,
                          'answer_candidates_total': len(answers)+len(additional_files),
                          'answer_candidates_omitted_by_limit': max(0, len(answers)+len(additional_files)-limit)},
            'omitted': omitted, 'ambiguous': ambiguous, 'candidate_count': len(ranked),
            'missing_explicit_files': missing_files,
            'coverage': 'heuristic_identifiers_static_dependencies_partial',
            'named_modules': sorted(modules), 'dependency_candidates': len(dependency_records),
            'alternative_module_matches': module_diagnostics,
            'limits': {'ranked_symbols': limit, 'dependency_depth': DEPENDENCY_DEPTH,
                       'dependency_nodes': DEPENDENCY_NODES},
            'unresolved_terms': [term for term in terms if not any(
                term in r['op_hits'] | r['path_hits'] | r['parent_hits'] | r['reference_hits'] for r in ranked)]}


def retrieve(db, query, limit=12):
    details = retrieve_detailed(db, query, limit)
    key = 'results' if details['selection']['mode'] == 'recall_fallback' else 'answer_candidates'
    return details[key]
