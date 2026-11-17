"""Lectura limitada y redacción heurística; nunca ejecuta el proyecto."""
import ast
import hashlib
import io
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tokenize

SECRET_LINE = re.compile(
    r'(?i)(api[_-]?key|password|passwd|secret|authorization\s*:|bearer\s+|'
    r'private[_-]?key|token\s*[=:]|sk-[a-z0-9]{12,}|'
    r'gh[pousr]_[a-zA-Z0-9]{20,}|AKIA[A-Z0-9]{16}|'
    r'eyJ[a-zA-Z0-9_-]+\.eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+)')
SECRET_KEY = re.compile(r'(?i)(password|passwd|secret|credential|api_?key|private_?key|access_?token|refresh_?token|^token$|authorization)')
HIDDEN = '[LINEA POTENCIALMENTE SENSIBLE OCULTA]'


def _read_bounded_windows(root, rel, max_bytes):
    """Mejor esfuerzo SIN dir_fd/O_NOFOLLOW (Windows carece de ambos en `os.open`): se
    comprueba cada componente de la ruta contra symlinks con `Path.is_symlink()` ANTES de
    abrir el archivo final con `open()` normal.

    Aviso de seguridad (2026-11-15, añadido en la remodelación para Windows): esto deja una
    ventana TOCTOU entre la comprobación y la apertura que el modo POSIX de arriba evita por
    construcción (ahí la ruta se abre componente a componente con `dir_fd`, sin ese hueco).
    Es decir: en Windows la protección contra symlinks es de mejor esfuerzo, no atómica. Para
    el caso de uso real (indexar el propio proyecto del usuario, sin escritores adversarios
    compitiendo en el mismo instante) es un riesgo aceptado y documentado, no eliminado.
    """
    cursor = Path(root)
    for part in rel.parts[:-1]:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError('Componente de la ruta es symlink; rechazado')
    final = cursor / rel.name
    if final.is_symlink():
        raise ValueError('Componente de la ruta es symlink; rechazado')
    info = final.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > max_bytes:
        raise ValueError('Archivo no regular o excede el tamaño indexado; reindexar')
    parts, total = [], 0
    with open(final, 'rb') as f:
        while total <= max_bytes:
            chunk = f.read(min(65536, max_bytes + 1 - total))
            if not chunk:
                break
            parts.append(chunk)
            total += len(chunk)
    if total > max_bytes:
        raise ValueError('Archivo creció; reindexar')
    return b''.join(parts)


def read_bounded(root, path, max_bytes):
    """Abre cada componente sin seguir symlinks (POSIX); rechaza FIFO/dispositivos.

    No garantiza un snapshot frente a un escritor concurrente malicioso. El
    llamante valida SHA256 de los bytes antes de utilizarlos.

    Sin `dir_fd`/`O_NOFOLLOW` (Windows), usa `_read_bounded_windows`: mismas comprobaciones de
    forma, pero symlinks verificados antes de abrir en vez de durante la apertura (ver su aviso).
    """
    if not isinstance(path, str) or '\\' in path or '\x00' in path:
        raise ValueError('Ruta no permitida')
    rel = PurePosixPath(path)
    if rel.is_absolute() or '..' in rel.parts or not rel.parts:
        raise ValueError('Ruta no permitida')
    if not isinstance(max_bytes, int) or max_bytes < 0:
        raise ValueError('Límite de lectura inválido')
    if not hasattr(os, 'O_NOFOLLOW') or os.open not in os.supports_dir_fd:
        return _read_bounded_windows(root, rel, max_bytes)
    descriptors = []
    try:
        fd = os.open(str(root), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        descriptors.append(fd)
        for part in rel.parts[:-1]:
            fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            descriptors.append(fd)
        fd = os.open(rel.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        descriptors.append(fd)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > max_bytes:
            raise ValueError('Archivo no regular o excede el tamaño indexado; reindexar')
        parts, total = [], 0
        while total <= max_bytes:
            chunk = os.read(fd, min(65536, max_bytes + 1 - total))
            if not chunk:
                break
            parts.append(chunk)
            total += len(chunk)
        if total > max_bytes:
            raise ValueError('Archivo creció; reindexar')
        return b''.join(parts)
    finally:
        for fd in reversed(descriptors):
            os.close(fd)


def read_verified(root, db, path):
    from .index import allowed
    if not allowed(root, Path(root) / path):
        raise ValueError('Ruta no permitida o no disponible; reindexar')
    row = db.execute('SELECT sha,size,symbols FROM files WHERE path=?', (path,)).fetchone()
    if row is None:
        raise ValueError('Archivo no indexado; reindexar')
    raw = read_bounded(root, path, row[1])
    if hashlib.sha256(raw).hexdigest() != row[0]:
        raise ValueError('Hash cambiado: reindexar')
    return raw, row


def decode_source(raw, python=False):
    """Respeta PEP 263; nunca sustituye bytes ilegibles de la evidencia."""
    try:
        encoding = tokenize.detect_encoding(io.BytesIO(raw).readline)[0] if python else 'utf-8-sig'
        return raw.decode(encoding)
    except (UnicodeError, SyntaxError, LookupError) as exc:
        raise ValueError('Codificación no legible; no se entrega evidencia alterada') from exc


def redact(text, python=False):
    """Conserva número de líneas; oculta valores multilínea y PEM completos.

    Filtro de precaución, no detector completo de credenciales. Revisar siempre.
    """
    # AST cuenta CR/LF, no U+2028/U+2029 ni los otros separadores de splitlines().
    lines = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    if lines and lines[-1] == '':
        lines.pop()
    hidden = {i for i, line in enumerate(lines) if SECRET_LINE.search(line)}
    pem = False
    for i, line in enumerate(lines):
        if re.search(r'-----BEGIN .*PRIVATE KEY-----', line):
            pem = True
        if pem:
            hidden.add(i)
        if re.search(r'-----END .*PRIVATE KEY-----', line):
            pem = False
    if python:
        try:
            tree = ast.parse(text)
            for node in ast.walk(tree):
                targets = []
                if isinstance(node, ast.Assign):
                    targets = node.targets
                elif isinstance(node, (ast.AnnAssign, ast.NamedExpr)):
                    targets = [node.target]
                sensitive = any(SECRET_KEY.search(n.id if isinstance(n, ast.Name) else n.attr)
                                for target in targets for n in ast.walk(target)
                                if isinstance(n, (ast.Name, ast.Attribute)))
                sensitive = sensitive or any(
                    isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Constant)
                    and isinstance(n.slice.value, str) and SECRET_KEY.search(n.slice.value)
                    for target in targets for n in ast.walk(target)
                )
                if isinstance(node, ast.keyword) and node.arg and SECRET_KEY.search(node.arg):
                    sensitive = True
                if sensitive:
                    hidden.update(range(node.lineno - 1, node.end_lineno))
                if isinstance(node, ast.Dict):
                    for key, value in zip(node.keys, node.values):
                        if isinstance(key, ast.Constant) and isinstance(key.value, str) and SECRET_KEY.search(key.value):
                            hidden.update(range(key.lineno - 1, value.end_lineno))
                if isinstance(node, ast.arguments):
                    positional = node.posonlyargs + node.args
                    pairs = list(zip(positional[-len(node.defaults):], node.defaults)) if node.defaults else []
                    pairs += list(zip(node.kwonlyargs, node.kw_defaults))
                    for argument, value in pairs:
                        if value is not None and SECRET_KEY.search(argument.arg):
                            hidden.update(range(argument.lineno - 1, value.end_lineno))
            for tok in tokenize.generate_tokens(io.StringIO(text).readline):
                if tok.type == tokenize.STRING and (
                    SECRET_LINE.search(tok.string) or tok.start[0] - 1 in hidden
                ):
                    hidden.update(range(tok.start[0] - 1, tok.end[0]))
        except (SyntaxError, ValueError, tokenize.TokenError, IndentationError):
            if hidden:
                hidden.update(range(len(lines)))
    else:
        # Continuaciones indentadas de valores YAML/config y cadenas JSON.
        active_indent = None
        for i, line in enumerate(lines):
            indent = len(line) - len(line.lstrip())
            if i in hidden:
                active_indent = indent
            elif active_indent is not None and line.strip() and indent > active_indent:
                hidden.add(i)
            elif line.strip():
                active_indent = None
        try:
            for tok in tokenize.generate_tokens(io.StringIO(text).readline):
                if tok.type == tokenize.STRING and (SECRET_LINE.search(tok.string) or tok.start[0] - 1 in hidden):
                    hidden.update(range(tok.start[0] - 1, tok.end[0]))
        except (tokenize.TokenError, IndentationError, SyntaxError):
            pass
    return [HIDDEN if i in hidden else line for i, line in enumerate(lines)], len(hidden)


def safe_label(value):
    """Una sola línea, sin caracteres de control ni patrones sensibles conocidos."""
    value = str(value)
    if SECRET_LINE.search(value):
        return '[DATO POTENCIALMENTE SENSIBLE OCULTO]'
    return ''.join(c if c.isprintable() else ' ' for c in value)
