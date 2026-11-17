#!/usr/bin/env python3
"""CLI Contexto Ligero V3.5; recuperación, evidencia y dependencias locales."""
import argparse
import json
import hashlib
import os
from pathlib import Path
import sqlite3
import sys

from contexto_core import __version__
from contexto_core.index import connect, scan, search, edge, allowed, root_guard, symbols_of, terms_of
from contexto_core.context import packet, build_packet, snippet, excerpt
from contexto_core.tokens import TokenCounter
from contexto_core.retrieval import retrieve, retrieve_detailed
from contexto_core.budget import PROFILES, generate_with_budget
from contexto_core.evidence import build_bundle
from contexto_core.safety import read_bounded


def _read_input(path, max_bytes=20_000_000):
    path = Path(path).absolute()
    return read_bounded(path.parent.resolve(strict=True), path.name, max_bytes).decode('utf-8')


def _join_inputs(paths, separator, max_bytes=20_000_000):
    remaining, pieces = max_bytes, []
    separator_size = len(separator.encode('utf-8'))
    for path in paths:
        if pieces:
            remaining -= separator_size
        if remaining < 0:
            raise ValueError('Texto concatenado excede límite de bytes')
        piece = _read_input(path, max_bytes=remaining)
        remaining -= len(piece.encode('utf-8'))
        pieces.append(piece)
    return separator.join(pieces)


def _write_new(path, value):
    """Artefacto privado y nuevo: nunca sobrescribe índices, código o snapshots."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        stream.write(value)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--version', action='version', version=__version__)
    ap.add_argument('--db', default='indice_v35.sqlite3', help='Base nueva recomendada V3.5; mantener anteriores intactas')
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('scan'); p.add_argument('root'); p.add_argument('--max-bytes', type=int, default=120000)
    p = sub.add_parser('query'); p.add_argument('text'); p.add_argument('--limit', type=int, default=12)
    p.add_argument('--explain', action='store_true', help='Muestra núcleo, alternativas, ambigüedades y motivos de selección')
    for command in ('packet', 'bundle'):
        p = sub.add_parser(command); p.add_argument('root'); p.add_argument('text')
        p.add_argument('--profile', choices=tuple(PROFILES), default='compacto' if command == 'packet' else 'modificar')
        p.add_argument('--budget', type=int, help='Sobrescribe presupuesto del perfil')
        p.add_argument('--auto-budget', action='store_true', help='Amplía solo si falta espacio, hasta --max-budget')
        p.add_argument('--max-budget', type=int, default=16000)
        p.add_argument('--context-window', type=int, help='Ventana externa; no modifica configuración de un modelo')
        p.add_argument('--reserve-output', type=int, default=0)
        p.add_argument('--prompt-overhead', type=int, default=0)
        p.add_argument('--limit', type=int, default=6)
        p.add_argument('--dependencies', type=int, choices=range(33), default=8)
        p.add_argument('--dependency-limit', type=int, default=64)
        p.add_argument('--strict-dependencies', action='store_true', default=command == 'bundle', help='Falla si no cubre todas las llamadas estáticas indexadas dentro del plan')
        p.add_argument('--allow-partial', action='store_false', dest='strict_dependencies', help='Permite omisiones explícitas de dependencias; no usar como contexto completo')
        p.add_argument('--min-score-ratio', type=float, default=0.60, help='Compatibilidad: 0 usa candidatos amplios; valores positivos usan selección por intención')
        p.add_argument('--require', action='append', default=[], metavar='PATH::SYMBOL', help='Repetible; en bundle exige también código completo')
        p.add_argument('--json', action='store_true', help='Diagnóstico fuera del presupuesto; enviar solo campo text al modelo')
        p.add_argument('--tokenizer-json', help='Tokenizador local; nunca instala ni descarga')
        p.add_argument('--snapshot-out', help='Guarda snapshot nuevo verificable para delta; no sobrescribe')
        if command == 'bundle':
            p.add_argument('--no-tests', action='store_true')
            p.add_argument('--max-evidence', type=int, default=8)
            p.add_argument('--line-style', choices=('auto', 'numbered'), default='auto',
                           help='auto compacta rangos de código solo si ahorra; numbered numera cada línea')
            p.add_argument('--max-symbol-lines', type=int, default=200,
                           help='Límite explícito por símbolo: 200 por defecto, máximo 1000; lecturas verificadas de hasta 200')
    for command in ('snippet', 'excerpt'):
        p = sub.add_parser(command); p.add_argument('root'); p.add_argument('path')
        if command == 'snippet':
            p.add_argument('symbol')
        else:
            p.add_argument('start', type=int); p.add_argument('end', type=int)
        p.add_argument('--max-lines', type=int, default=100); p.add_argument('--budget', type=int, default=2000)
        p.add_argument('--tokenizer-json')
    p = sub.add_parser('task'); p.add_argument('id'); p.add_argument('title')
    p.add_argument('--criteria', default=''); p.add_argument('--status', choices=('pending','active','done'), default='pending')
    p = sub.add_parser('edge'); p.add_argument('src'); p.add_argument('dst')
    p.add_argument('--kind', choices=('depends_on', 'relates_to'), default='depends_on')
    p = sub.add_parser('decision'); p.add_argument('id'); p.add_argument('task'); p.add_argument('detail'); p.add_argument('--source', required=True)
    p = sub.add_parser('tokens', help='Cuenta archivos concatenados: prompt, mapa y fragmentos')
    p.add_argument('files', nargs='+'); p.add_argument('--tokenizer-json'); p.add_argument('--separator', default='\n\n')
    p = sub.add_parser('delta', help='Transporte verificable desde una base conocida')
    p.add_argument('base'); p.add_argument('target'); p.add_argument('--expected-base', required=True)
    p.add_argument('--output'); p.add_argument('--stats', action='store_true'); p.add_argument('--tokenizer-json')
    p = sub.add_parser('apply-delta', help='Reconstruye snapshot, verificando hashes; base - para sobre completo')
    p.add_argument('base'); p.add_argument('patch'); p.add_argument('--expected-base', required=True); p.add_argument('--output', required=True)
    args = ap.parse_args(argv)
    db = None
    try:
        if args.cmd == 'tokens':
            combined = _join_inputs(args.files, args.separator)
            result = TokenCounter(args.tokenizer_json).metrics(combined)
            result.update(files=len(args.files), scope='texto concatenado exacto; sin plantilla de chat implícita')
        elif args.cmd in ('delta', 'apply-delta'):
            from contexto_core.delta import validate_snapshot, make_delta, apply_delta, transport_text, transport_metrics
            base = None if args.base == '-' else json.loads(_read_input(args.base))
            if base is not None:
                validate_snapshot(base)
                if base['sha256'] != args.expected_base:
                    raise ValueError('Hash base no coincide; recuperar snapshot completo')
            if args.cmd == 'delta':
                if base is None:
                    raise ValueError('delta requiere snapshot base')
                target = json.loads(_read_input(args.target))
                counter = TokenCounter(args.tokenizer_json)
                envelope = make_delta(base, target, token_counter=counter)
                result = transport_text(envelope)
                if args.stats:
                    print(json.dumps(transport_metrics(base, target, envelope, token_counter=counter), ensure_ascii=False), file=sys.stderr)
            else:
                envelope = json.loads(_read_input(args.patch))
                result = json.dumps(apply_delta(base, envelope, expected_base_sha256=args.expected_base), ensure_ascii=False, separators=(',', ':'))
            if args.output:
                _write_new(args.output, result)
                result = 'Guardado: ' + args.output
        else:
            db = connect(args.db)
        if args.cmd == 'scan':
            result = scan(Path(args.root), db, args.max_bytes)
        elif args.cmd == 'query':
            result = (retrieve_detailed if args.explain else retrieve)(db, args.text, args.limit)
        elif args.cmd in ('packet', 'bundle'):
            required = []
            for value in args.require:
                if '::' not in value:
                    raise ValueError('--require requiere PATH::SYMBOL')
                required.append(tuple(value.rsplit('::', 1)))
            counter = TokenCounter(args.tokenizer_json)
            builder = build_packet if args.cmd == 'packet' else build_bundle
            options = dict(dependencies=args.dependencies, token_counter=counter, required=required,
                           min_score_ratio=args.min_score_ratio, dependency_limit=args.dependency_limit,
                           strict_dependencies=args.strict_dependencies)
            if args.cmd == 'bundle':
                options.update(include_tests=not args.no_tests, max_evidence=args.max_evidence,
                               line_style=args.line_style, max_symbol_lines=args.max_symbol_lines)
            budget = args.budget if args.budget is not None else PROFILES[args.profile]
            result = generate_with_budget(lambda size: builder(Path(args.root), db, args.text, size, args.limit, **options),
                                          budget, auto=args.auto_budget, maximum=args.max_budget,
                                          context_window=args.context_window, reserve_output=args.reserve_output,
                                          prompt_overhead=args.prompt_overhead)
            if args.snapshot_out:
                from contexto_core.delta import create_snapshot
                origin = hashlib.sha256(str(Path(args.root).resolve()).encode()).hexdigest()
                snapshot = create_snapshot(result, origin=origin)
                _write_new(args.snapshot_out, json.dumps(snapshot, ensure_ascii=False, separators=(',', ':')) + '\n')
                result['snapshot_sha256'] = snapshot['sha256']
            if not args.json:
                result = result['text']
        elif args.cmd in ('snippet', 'excerpt'):
            fn = snippet if args.cmd == 'snippet' else excerpt
            selection = (args.symbol,) if args.cmd == 'snippet' else (args.start, args.end)
            result = fn(Path(args.root), db, args.path, *selection, max_lines=args.max_lines,
                        budget=args.budget, token_counter=TokenCounter(args.tokenizer_json))
        elif args.cmd == 'task':
            db.execute('INSERT OR REPLACE INTO tasks VALUES(?,?,?,?)', (args.id,args.title,args.status,args.criteria)); db.commit(); result = 'OK'
        elif args.cmd == 'edge':
            edge(db,args.src,args.dst,args.kind); result = 'OK'
        elif args.cmd == 'decision':
            db.execute('INSERT OR REPLACE INTO decisions VALUES(?,?,?,?)', (args.id,args.task,args.detail,args.source)); db.commit(); result = 'OK'
        output = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, indent=2)
        # delta cuenta exactamente el JSON transportado, sin newline oculto.
        terminator = '' if args.cmd == 'delta' and not args.output else ('\n' if not output.endswith('\n') else '')
        print(output, end=terminator)
        return 0
    except (ValueError, OSError, sqlite3.Error) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1
    finally:
        if db is not None:
            db.close()


if __name__ == '__main__':
    raise SystemExit(main())
