"""V3.3: metadata-only SQLite index and conservative static lookup.

No indexed project module is imported or executed. Call edges are static evidence,
not a claim about runtime dispatch. FTS5 is optional; fallback preserves ranking.
"""
import ast
import hashlib
from functools import lru_cache
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import unicodedata

VERSION = '3.3.1'
SKIP = {'venv', '.venv', '.git', '__pycache__', 'node_modules', 'dist', 'build',
        'site-packages', 'datos_v2c', 'evidencias', '.pytest_cache'}
EXT = {'.py', '.md', '.json', '.txt', '.java'}
SECRET_NAME = re.compile(r'(?i)(\.env|password|passwd|secret|api[_-]?key|private[_-]?key|credential|\.pem|\.key)')
WORDS = re.compile(r'[^\W_]+', re.UNICODE)
STOP = {'para', 'como', 'con', 'del', 'las', 'los', 'una', 'uno', 'que', 'por', 'the', 'and', 'for', 'with', 'from'}
CONCEPTS = {
    'contexto': {'contexto', 'construir', 'prompt', 'mensajes', 'estimar', 'tokens', 'presupuesto', 'perfil', 'bloque'},
    'memoria': {'memoria', 'recuperar', 'recuerdo', 'vigentes', 'memorias', 'aprendizaje'},
    'recuperar': {'recuperar', 'recuerdo', 'memoria', 'memorias'},
    'orquestador': {'orquestador', 'construir', 'recuperar', 'prompt', 'memoria', 'contexto'},
    'presupuesto': {'presupuesto', 'tokens', 'estimar', 'construir', 'perfil'},
}
SCHEMA = '''
CREATE TABLE files(path TEXT PRIMARY KEY,sha TEXT NOT NULL,size INTEGER NOT NULL,
 symbols TEXT NOT NULL,imports TEXT NOT NULL,search_text TEXT NOT NULL);
CREATE TABLE tasks(id TEXT PRIMARY KEY,title TEXT NOT NULL,status TEXT NOT NULL,criteria TEXT NOT NULL);
CREATE TABLE edges(src TEXT NOT NULL,dst TEXT NOT NULL,kind TEXT NOT NULL,PRIMARY KEY(src,dst,kind));
CREATE TABLE decisions(id TEXT PRIMARY KEY,task TEXT NOT NULL,detail TEXT NOT NULL,source TEXT NOT NULL);
CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE code_edges(src_path TEXT NOT NULL,src_symbol TEXT NOT NULL,dst_path TEXT NOT NULL,
 dst_symbol TEXT NOT NULL,kind TEXT NOT NULL,PRIMARY KEY(src_path,src_symbol,dst_path,dst_symbol,kind));
CREATE INDEX code_edges_source ON code_edges(src_path,src_symbol);
CREATE TABLE symbol_index(id INTEGER PRIMARY KEY,path TEXT NOT NULL,ordinal INTEGER NOT NULL,
 name TEXT NOT NULL,line INTEGER NOT NULL,end INTEGER NOT NULL,kind TEXT NOT NULL,
 name_words TEXT NOT NULL,operation_words TEXT NOT NULL,parent_words TEXT NOT NULL,
 ref_words TEXT NOT NULL,payload TEXT NOT NULL,UNIQUE(path,ordinal));
CREATE INDEX symbol_index_name ON symbol_index(path,name);
'''


def connect(path):
    """Open only a new database or our schema. Never migrate a previous version."""
    db = sqlite3.connect(str(path), timeout=10)
    try:
        names = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if names:
            row = db.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone() if 'meta' in names else None
            if not row or row[0] != VERSION:
                raise ValueError('Esquema incompatible: use otra --db nueva para V3.3')
            required = {'files', 'tasks', 'edges', 'decisions', 'meta', 'code_edges', 'symbol_index'}
            if not required.issubset(names):
                raise ValueError('Base incompleta: use otra --db y reindexar')
            return db
        db.executescript(SCHEMA)
        db.execute("INSERT INTO meta VALUES('schema_version',?)", (VERSION,))
        try:
            db.execute("CREATE VIRTUAL TABLE files_fts USING fts5(path,search_text,tokenize='unicode61')")
            db.execute("CREATE VIRTUAL TABLE symbol_fts USING fts5(words,tokenize='unicode61')")
            fts = '1'
        except sqlite3.OperationalError:
            fts = '0'
        db.execute("INSERT INTO meta VALUES('fts5',?)", (fts,))
        db.commit()
        return db
    except Exception:
        db.close()
        raise


def _normalize(text):
    # Split acronym/camelCase boundaries before case folding, then normalize accents.
    text = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1 \2', text)
    text = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', text)
    return ''.join(c for c in unicodedata.normalize('NFKD', text.casefold())
                   if not unicodedata.combining(c))


@lru_cache(maxsize=8192)
def _cached_words(text):
    return _uncached_words(text)


def _uncached_words(text):
    return frozenset(w for w in WORDS.findall(_normalize(text)) if len(w) > 1)


def _words(text):
    # Keep only small identifier strings, never raw source, in the bounded cache.
    if len(text) > 4096:
        return _uncached_words(text)
    return _cached_words(text)


def terms_of(q):
    return list(dict.fromkeys(w for w in WORDS.findall(_normalize(q))
                              if len(w) > 1 and w not in STOP))[:24]


def allowed(root, p):
    """Reject traversal, hidden directories, secret names and every symlink component."""
    try:
        root = Path(root).absolute()
        p = Path(p).absolute()
        rel = p.relative_to(root)
        if not rel.parts or '..' in rel.parts or p.suffix.lower() not in EXT:
            return False
        if any(x in SKIP or x.startswith('.') for x in rel.parts[:-1]):
            return False
        if any(SECRET_NAME.search(x) for x in rel.parts):
            return False
        cursor = root
        if cursor.is_symlink():
            return False
        for part in rel.parts:
            cursor = cursor / part
            if cursor.is_symlink():
                return False
        return stat.S_ISREG(p.stat().st_mode) and p.resolve().is_relative_to(root.resolve())
    except (OSError, ValueError):
        return False


def read_source(root, path, max_bytes=120000):
    """Apply the index allowlist, then the shared fail-closed bounded reader."""
    from .safety import read_bounded
    if not allowed(root, Path(root) / path):
        raise ValueError('Ruta no permitida')
    return read_bounded(root, path, max_bytes)


def _dotted(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _dotted(node.value)
        return prefix + '.' + node.attr if prefix else ''
    return ''


def _imports(nodes):
    out = []
    for n in nodes:
        if isinstance(n, ast.Import):
            for alias in n.names:
                out.append({'alias': alias.asname or alias.name.split('.')[0],
                            'module': alias.name if alias.asname else alias.name.split('.')[0],
                            'symbol': '', 'level': 0})
        elif isinstance(n, ast.ImportFrom):
            for alias in n.names:
                if alias.name != '*':
                    out.append({'alias': alias.asname or alias.name, 'module': n.module or '',
                                'symbol': alias.name, 'level': n.level})
    return out


def _scope_nodes(node):
    """Yield this scope's nodes without borrowing nested function/class calls."""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            yield child
        else:
            yield child
            yield from _scope_nodes(child)


_JAVA_TIPO = re.compile(r'\b(class|interface|enum|record)\s+([A-Za-z_$][\w$]*)')
_JAVA_METODO = re.compile(r'([A-Za-z_$][\w$]*)\s*\(([^()]*(?:\([^()]*\)[^()]*)*)\)\s*(?:throws\s+[\w$.,\s]+)?\{')
_JAVA_PAQUETE = re.compile(r'^\s*package\s+([\w$.]+)\s*;', re.M)
_JAVA_IMPORT = re.compile(r'^\s*import\s+(static\s+)?([\w$.]+?)(\.\*)?\s*;', re.M)
_JAVA_LLAMADA = re.compile(r'(?:\b([A-Za-z_$][\w$]*)\s*\.\s*)?\b([A-Za-z_$][\w$]*)\s*\(')
_JAVA_ANOTACION = re.compile(r'@\s*([A-Za-z_$][\w$.]*)')
_JAVA_NO_METODO = {'if', 'for', 'while', 'switch', 'catch', 'synchronized', 'return', 'new', 'else', 'try',
                   'do', 'throw', 'super', 'this', 'assert', 'case', 'yield'}
_JAVA_MODIFICADORES = {'public', 'protected', 'private', 'static', 'final', 'abstract', 'transient', 'volatile',
                       'synchronized', 'native', 'default', 'sealed', 'non-sealed', 'strictfp'}


def _java_blanco(texto):
    """Comentarios y literales de texto/carácter -> espacios (conserva longitudes y saltos de línea)."""
    out, i, n = list(texto), 0, len(texto)
    while i < n:
        dos = texto[i:i + 2]
        if dos == '//':
            j = texto.find('\n', i)
            j = n if j < 0 else j
        elif dos == '/*':
            j = texto.find('*/', i + 2)
            j = n if j < 0 else j + 2
        elif texto[i] in '"\'':
            if texto[i:i + 3] == '"""':
                j = texto.find('"""', i + 3)
                j = n if j < 0 else j + 3
            else:
                j, q = i + 1, texto[i]
                while j < n and texto[j] != q and texto[j] != '\n':
                    j += 2 if texto[j] == '\\' else 1
                j = min(j + 1, n)
        else:
            i += 1
            continue
        for k in range(i, j):
            if out[k] != '\n':
                out[k] = ' '
        i = j
    return ''.join(out)


def _java_cierre(limpio, abre):
    """Posición de la llave que cierra la que está en `abre`, o None si no cierra."""
    nivel = 0
    for k in range(abre, len(limpio)):
        if limpio[k] == '{':
            nivel += 1
        elif limpio[k] == '}':
            nivel -= 1
            if nivel == 0:
                return k
    return None


def _java_anotaciones(limpio, inicio_linea):
    """Sube por las líneas anteriores mientras sean anotaciones (pueden ocupar varias líneas con paréntesis).
    Devuelve (posición del primer carácter de la primera anotación, nombres de las anotaciones)."""
    pos, nombres = inicio_linea, []
    while pos > 0:
        prev_fin = pos - 1
        prev_ini = limpio.rfind('\n', 0, prev_fin) + 1
        linea = limpio[prev_ini:prev_fin].strip()
        if not linea:
            break
        bloque_ini = prev_ini
        if linea.endswith(')') and not linea.startswith('@'):
            # anotación con argumentos en varias líneas: empareja el «)» final con su «(» y toma el «@Nombre»
            # que lo precede (no el «@At» interior más cercano)
            k, nivel = limpio.rfind(')', 0, prev_fin + 1), 0
            while k >= 0:
                if limpio[k] == ')':
                    nivel += 1
                elif limpio[k] == '(':
                    nivel -= 1
                    if nivel == 0:
                        break
                elif limpio[k] in '{};':
                    k = -1
                    break
                k -= 1
            m = re.search(r'@\s*[\w$.]+\s*$', limpio[max(0, k - 200):k]) if k > 0 else None
            if not m:
                break
            arroba = max(0, k - 200) + m.start()
            bloque_ini = limpio.rfind('\n', 0, arroba) + 1
            linea = limpio[bloque_ini:prev_fin].strip()
        if not linea.startswith('@'):
            break
        nombres = _JAVA_ANOTACION.findall(linea) + nombres
        pos = bloque_ini
    return pos, nombres


def _java_metadata(raw):
    """Símbolos de Java SIN compilador ni dependencias, pensado también para mods (Forge, Fabric, mixins):
    tipos (class/interface/enum/record, anidados), métodos y constructores con sus anotaciones, métodos abstractos
    de interfaces, campos, constantes, valores de enum, y llamadas con su receptor (`Clase.metodo`). Nombres
    calificados (`Clase.Interna.metodo`) y líneas exactas, anotaciones incluidas. Heurístico: no resuelve tipos,
    sobrecargas, herencia ni llamadas dinámicas; las llamadas entre archivos se resuelven después con
    `package`/`import` (`_java_edges`)."""
    texto = raw.decode('utf-8', 'replace') if isinstance(raw, bytes) else raw
    limpio = _java_blanco(texto)
    linea = lambda pos: limpio.count('\n', 0, pos) + 1
    m = _JAVA_PAQUETE.search(limpio)
    paquete = m.group(1) if m else ''
    imports = []
    for m in _JAVA_IMPORT.finditer(limpio):
        ruta = m.group(2)
        if m.group(3):                                   # import a.b.*: paquete entero, sin alias concreto
            imports.append({'alias': '*', 'module': ruta, 'symbol': '*', 'level': 0, 'blocked': True})
        else:
            imports.append({'alias': ruta.rsplit('.', 1)[-1], 'module': ruta.rpartition('.')[0],
                            'symbol': ruta.rsplit('.', 1)[-1], 'level': 0, 'static': bool(m.group(1))})
    tipos = []                                           # (inicio, llave_abre, llave_cierra, nombre, clase)
    for m in _JAVA_TIPO.finditer(limpio):
        if limpio[max(0, m.start() - 1):m.start()] == '.':
            continue                                     # «Foo.class» no declara nada
        abre = limpio.find('{', m.end())
        if abre < 0 or ';' in limpio[m.end():abre]:
            continue
        cierra = _java_cierre(limpio, abre)
        if cierra is not None:
            tipos.append((m.start(), abre, cierra, m.group(2), m.group(1)))
    # Valores de enum con cuerpo («OBSIDIANA(9) { … }»): contenedores propios, para que sus métodos se llamen
    # «Roca.OBSIDIANA.fundible» y no tapen al «Roca.fundible» del enum.
    for ini, abre, cierra, nombre, clase in list(tipos):
        if clase != 'enum':
            continue
        k = abre + 1
        while k < cierra:
            if limpio[k] == ';':
                break
            if limpio[k] == '{':
                fin = _java_cierre(limpio, k)
                if fin is None:
                    break
                m = re.search(r'([A-Za-z_$][\w$]*)\s*(?:\([^()]*(?:\([^()]*\)[^()]*)*\))?\s*$', limpio[abre + 1:k])
                if m:
                    tipos.append((abre + 1 + m.start(1), k, fin, m.group(1), 'valor_enum'))
                k = fin + 1
                continue
            k += 1

    def padres(pos):
        return [t[3] for t in sorted(tipos) if t[1] < pos < t[2]]

    def es_declaracion(m):
        """¿«nombre(…) {» declara un método? Si lo precede «,» o «{»/«;»/«}» sin tipo, solo si es el constructor."""
        antes = limpio[:m.start()].rstrip()
        previo = antes[-1:] if antes else ''
        if previo == ',':
            return False
        if previo in ('{', ';', '}', ''):
            contenedor = padres(m.start())
            return bool(contenedor) and m.group(1) == contenedor[-1]
        return True

    vacio = {'refs': [], 'calls': [], 'arguments': [], 'imports': [], 'shadowed': []}
    out, vistos = [], set()

    def anadir(nombre, ini, fin, tipo, **extra):
        if nombre in vistos:
            if tipo != 'FunctionDef':
                return
            n = 2                                        # sobrecarga: «Clase.metodo#2», «#3»…
            while f'{nombre}#{n}' in vistos:
                n += 1
            nombre = f'{nombre}#{n}'
        vistos.add(nombre)
        out.append({'name': nombre, 'line': linea(ini), 'def_line': linea(ini), 'end': linea(fin),
                    'kind': tipo, 'package': paquete, **{**vacio, **extra}})

    def llamadas(cuerpo):
        out_ = set()
        for recv, nombre in _JAVA_LLAMADA.findall(cuerpo):
            if nombre in _JAVA_NO_METODO:
                continue
            if recv and recv[:1].isupper():
                out_.add(f'{recv}.{nombre}')             # Clase.metodo (estático o de otra clase)
            elif not recv or recv == 'this':
                out_.add(nombre)                         # método de la propia clase
            else:
                out_.add(f'?.{nombre}')                  # sobre un objeto: tipo desconocido sin compilador
        return sorted(out_)[:100]

    for ini, abre, cierra, nombre, clase in sorted(tipos):
        if clase == 'valor_enum':
            continue
        inicio_linea = limpio.rfind('\n', 0, ini) + 1
        inicio, anot = _java_anotaciones(limpio, inicio_linea)
        cabecera = ' '.join(limpio[ini:abre].split())
        anadir('.'.join(padres(ini) + [nombre]), inicio, cierra, 'ClassDef', refs=anot + [clase],
               arguments=[w for w in re.findall(r'[A-Za-z_$][\w$]*', cabecera) if w not in
                          ('class', 'interface', 'enum', 'record', 'extends', 'implements', nombre)][:20])
    for m in _JAVA_METODO.finditer(limpio):
        nombre = m.group(1)
        if nombre in _JAVA_NO_METODO or not padres(m.start()):
            continue
        if re.search(r'\bnew\s+$', limpio[max(0, m.start() - 20):m.start()]):
            continue                                     # clase anónima: «new Runnable() {»
        if re.search(r'[.]\s*$', limpio[max(0, m.start() - 3):m.start()]) or not es_declaracion(m):
            continue                                     # «obj.metodo(…) {» o un valor de enum: no declara
        cierra = _java_cierre(limpio, m.end() - 1)
        if cierra is None:
            continue
        inicio_linea = limpio.rfind('\n', 0, m.start()) + 1
        inicio, anot = _java_anotaciones(limpio, inicio_linea)
        argumentos = [p.split()[-1] for p in _sin_genericos(m.group(2)).split(',') if p.split()]
        anadir('.'.join(padres(m.start()) + [nombre]), inicio, cierra, 'FunctionDef',
               calls=llamadas(limpio[m.end():cierra]), refs=anot, arguments=argumentos)
    # Miembros sin cuerpo a nivel de clase: campos, constantes, valores de enum y métodos abstractos/de interfaz.
    for ini, abre, cierra, nombre_tipo, clase in sorted(tipos):
        k, seg_ini, nivel_tipo = abre + 1, abre + 1, padres(abre + 1)
        primero = True
        while k < cierra:
            ch = limpio[k]
            if ch == '{':
                fin_bloque = _java_cierre(limpio, k)
                if fin_bloque is None:
                    break
                if '=' not in limpio[seg_ini:k] and not (clase == 'enum' and primero):
                    seg_ini = fin_bloque + 1             # cuerpo de método/clase interna: no es un campo
                k = fin_bloque + 1
                continue
            if ch == ';' or (clase == 'enum' and primero and ch == ';'):
                seg = limpio[seg_ini:k]
                plano = ' '.join(seg.split())
                if plano:
                    _java_miembro(plano, seg_ini, k, clase, primero, nivel_tipo, limpio, anadir, linea)
                primero = False
                seg_ini = k + 1
            k += 1
        if clase == 'enum' and primero:                  # enum sin «;»: solo valores
            plano = ' '.join(limpio[abre + 1:cierra].split())
            if plano:
                _java_miembro(plano, abre + 1, cierra, clase, True, nivel_tipo, limpio, anadir, linea)
    return out, imports


def _sin_genericos(s):
    while True:
        t = re.sub(r'<[^<>]*>', '', s)
        if t == s:
            return t
        s = t


def _java_miembro(plano, ini, fin, clase, primero, padres_, limpio, anadir, linea):
    """Un segmento «…;» a nivel de clase: valores de enum, método abstracto o campo(s)."""
    if clase == 'enum' and primero:                      # quita los cuerpos de los valores: «A(1) { … }, B»
        while True:
            sin_cuerpos = re.sub(r'\{[^{}]*\}', ' ', plano)
            if sin_cuerpos == plano:
                break
            plano = sin_cuerpos
    sin_anot = re.sub(r'@\s*[\w$.]+(\s*\([^()]*(\([^()]*\)[^()]*)*\))?', ' ', plano).strip()
    pos_ini = ini + (len(limpio[ini:fin]) - len(limpio[ini:fin].lstrip()))
    if clase == 'enum' and primero and not re.search(r'[=;]', sin_anot):
        for valor in re.findall(r'(?:^|,)\s*([A-Za-z_$][\w$]*)\s*(?:\([^()]*\))?', sin_anot):
            anadir('.'.join(padres_ + [valor]), pos_ini, fin, 'Assign', refs=['enum'])
        return
    if '(' in sin_anot and '=' not in sin_anot.split('(')[0]:
        m = re.search(r'([A-Za-z_$][\w$]*)\s*\(', sin_anot)
        if m and m.group(1) not in _JAVA_NO_METODO:
            anadir('.'.join(padres_ + [m.group(1)]), pos_ini, fin, 'FunctionDef', refs=['abstracto'])
        return
    declaracion = _sin_genericos(sin_anot.split('=')[0])
    palabras = [w for w in re.findall(r'[A-Za-z_$][\w$]*', declaracion) if w not in _JAVA_MODIFICADORES]
    if len(palabras) >= 2:                               # tipo nombre [, nombre2 …]
        nombres = [p.strip().split()[-1] for p in declaracion.split(',') if p.strip()]
        es_const = bool(re.search(r'\bstatic\b', plano) and re.search(r'\bfinal\b', plano))
        for n in nombres:
            n = n.strip('[] ')
            if re.fullmatch(r'[A-Za-z_$][\w$]*', n):
                anadir('.'.join(padres_ + [n]), pos_ini, fin, 'Assign',
                       refs=['constante' if es_const else 'campo'])


def _java_edges(db):
    """Llamadas entre símbolos Java: dentro de la clase (local_call) y a otras clases resueltas por `import` o por
    estar en el mismo `package` (import_call). Solo destinos inequívocos; lo demás se queda sin arista."""
    registros = {p: (json.loads(s), json.loads(i)) for p, s, i in
                 db.execute('SELECT path,symbols,imports FROM files') if p.endswith('.java')}
    por_fq, nombres_de = {}, {}
    for path, (syms, _) in registros.items():
        nombres_de[path] = {s['name'] for s in syms if 'name' in s}
        for s in syms:
            if s.get('kind') == 'ClassDef' and '.' not in s['name']:
                fq = (s.get('package') + '.' if s.get('package') else '') + s['name']
                por_fq.setdefault(fq, []).append(path)
    filas = set()
    for path, (syms, imports) in registros.items():
        alias = {e['alias']: e['module'] + '.' + e['symbol'] for e in imports
                 if not e.get('blocked') and not e.get('static')}
        estaticos = {e['alias']: e['module'] for e in imports if e.get('static')}   # import static a.b.C.metodo
        for s in syms:
            if s.get('kind') != 'FunctionDef' or not s.get('calls'):
                continue
            dueno = s['name'].split('.')[:-1]
            paquete = s.get('package', '')
            for llamada in s['calls']:
                if llamada.startswith('?.'):
                    continue
                if '.' in llamada:
                    clase, metodo = llamada.split('.', 1)
                    candidatos = []
                    if clase in alias:
                        candidatos = por_fq.get(alias[clase], [])
                    elif f'{clase}' in {n.split('.')[0] for n in nombres_de[path]}:
                        candidatos = [path]
                    else:
                        candidatos = por_fq.get((paquete + '.' if paquete else '') + clase, [])
                    if len(candidatos) == 1 and f'{clase}.{metodo}' in nombres_de[candidatos[0]]:
                        filas.add((path, s['name'], candidatos[0], f'{clase}.{metodo}',
                                   'local_call' if candidatos[0] == path else 'import_call'))
                    continue
                if llamada in estaticos:
                    candidatos = por_fq.get(estaticos[llamada], [])
                    destino = estaticos[llamada].rsplit('.', 1)[-1] + '.' + llamada
                    if len(candidatos) == 1 and destino in nombres_de[candidatos[0]]:
                        filas.add((path, s['name'], candidatos[0], destino, 'import_call'))
                    continue
                for corte in range(len(dueno), 0, -1):    # de la clase más interna hacia fuera
                    destino = '.'.join(dueno[:corte] + [llamada])
                    if destino in nombres_de[path] and destino != s['name']:
                        filas.add((path, s['name'], path, destino, 'local_call'))
                        break
    return filas


def _metadata(raw, suffix):
    if suffix.lower() == '.java':
        return _java_metadata(raw)
    if suffix.lower() != '.py':
        return [], []
    try:
        tree = ast.parse(raw)
    except (SyntaxError, ValueError, RecursionError) as exc:
        # SyntaxError.text can contain credentials: never persist it.
        return [{'error': type(exc).__name__, 'line': getattr(exc, 'lineno', None)}], []
    imports = _imports(tree.body)
    # A module-level assignment can replace a definition/import. Preserve only
    # its identifier, and refuse to claim a destination for that name.
    rebound = set()
    aliases = {entry['alias'] for entry in imports}
    for statement in tree.body:
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if statement.name in aliases:
                rebound.add(statement.name)
            continue
        for child in ast.walk(statement):
            if isinstance(child, ast.Name) and isinstance(child.ctx, (ast.Store, ast.Del)):
                rebound.add(child.id)
    imports.extend({'alias': name, 'module': '', 'symbol': '', 'level': 0,
                    'blocked': True} for name in sorted(rebound))
    out = []

    def walk(node, parents=()):
        for n in ast.iter_child_nodes(node):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = '.'.join((*parents, n.name))
                is_class = isinstance(n, ast.ClassDef)
                nodes = [] if is_class else list(_scope_nodes(n))
                calls = sorted({_dotted(sub.func) for sub in nodes if isinstance(sub, ast.Call)} - {''})
                refs = sorted({c.split('.')[-1] for c in calls})
                arguments = []
                shadowed = set()
                if not is_class:
                    arguments = [a.arg for a in n.args.posonlyargs + n.args.args + n.args.kwonlyargs]
                    if n.args.vararg:
                        arguments.append('*' + n.args.vararg.arg)
                    if n.args.kwarg:
                        arguments.append('**' + n.args.kwarg.arg)
                    shadowed.update(a.lstrip('*') for a in arguments)
                    for sub in nodes:
                        if isinstance(sub, ast.Name) and isinstance(sub.ctx, (ast.Store, ast.Del)):
                            shadowed.add(sub.id)
                        elif isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                            shadowed.add(sub.name)
                out.append({'name': name,
                            'line': min([n.lineno] + [d.lineno for d in n.decorator_list]),
                            'def_line': n.lineno, 'end': n.end_lineno,
                            'kind': type(n).__name__, 'refs': refs[:100],
                            'calls': calls[:100], 'arguments': arguments,
                            'imports': _imports(nodes), 'shadowed': sorted(shadowed)})
                walk(n, (*parents, n.name))
            else:
                walk(n, parents)
    try:
        walk(tree)
    except RecursionError:
        return [{'error': 'RecursionError', 'line': None}], []
    out.extend(_module_constants(tree, {s['name'] for s in out}))
    return out, imports


def _module_constants(tree, defined):
    """Module-level `NAME = ...` assigned exactly once, as searchable symbols of kind 'Assign'.

    Without this, a question about a module constant (`TOPE_MAX_TOKENS = 800`) never retrieves its
    definition. Names rebound more than once or shared with a def/class are skipped: one answer only.
    """
    seen = {}
    for st in tree.body:
        if isinstance(st, ast.Assign):
            targets = st.targets
        elif isinstance(st, ast.AnnAssign) and st.value is not None:
            targets = [st.target]
        else:
            continue
        for tg in targets:
            if isinstance(tg, ast.Name):
                seen.setdefault(tg.id, []).append(st)
    out = []
    for name, statements in seen.items():
        if len(statements) != 1 or name in defined:
            continue
        st = statements[0]
        out.append({'name': name, 'line': st.lineno, 'def_line': st.lineno, 'end': st.end_lineno,
                    'kind': 'Assign', 'refs': [], 'calls': [], 'arguments': [], 'imports': [], 'shadowed': []})
    return out


def symbols_of(raw, suffix):
    return _metadata(raw, suffix)[0]


def root_guard(db, root):
    current_path = Path(root).resolve(strict=True)
    if not current_path.is_dir():
        raise ValueError('La raiz debe ser un directorio')
    current = str(current_path)
    old = db.execute("SELECT value FROM meta WHERE key='root'").fetchone()
    if old and old[0] != current:
        raise ValueError('Base ligada a otro proyecto: use otra --db')
    if not old:
        db.execute("INSERT INTO meta VALUES('root',?)", (current,))
        db.commit()


def _has_fts(db):
    row = db.execute("SELECT value FROM meta WHERE key='fts5'").fetchone()
    return bool(row and row[0] == '1')


def _remove(db, path):
    row = db.execute('SELECT rowid FROM files WHERE path=?', (path,)).fetchone()
    if not row:
        return 0
    if _has_fts(db):
        db.execute('DELETE FROM files_fts WHERE rowid=?', (row[0],))
        db.execute('DELETE FROM symbol_fts WHERE rowid IN (SELECT id FROM symbol_index WHERE path=?)', (path,))
    db.execute('DELETE FROM files WHERE path=?', (path,))
    db.execute('DELETE FROM symbol_index WHERE path=?', (path,))
    return 1


def _store_symbols(db, path, symbols):
    """Normalize identifier features once at scan; preserve duplicate definitions.

    files.symbols remains for API compatibility. This table deliberately spends
    some disk space to avoid decoding each file's complete AST metadata per query.
    It contains no source, defaults, string literals or inferred runtime values.
    """
    if _has_fts(db):
        db.execute('DELETE FROM symbol_fts WHERE rowid IN (SELECT id FROM symbol_index WHERE path=?)', (path,))
    db.execute('DELETE FROM symbol_index WHERE path=?', (path,))
    rows = []
    for ordinal, sym in enumerate(symbols):
        if 'name' not in sym:
            continue
        # These features live in SQLite, so do not retain another cache copy.
        words = _uncached_words(sym['name'])
        operation = _uncached_words(sym['name'].split('.')[-1])
        refs = _uncached_words(' '.join(sym.get('refs', [])))
        features = [' '.join(sorted(group)) for group in (words, operation, words-operation, refs)]
        rows.append((path, ordinal, sym['name'], sym['line'], sym['end'], sym['kind'],
                     *features, json.dumps(sym, ensure_ascii=False, separators=(',', ':'))))
    db.executemany('INSERT INTO symbol_index(path,ordinal,name,line,end,kind,name_words,operation_words,parent_words,ref_words,payload) VALUES(?,?,?,?,?,?,?,?,?,?,?)', rows)
    if _has_fts(db):
        db.execute("INSERT INTO symbol_fts(rowid,words) SELECT id,name_words||' '||ref_words FROM symbol_index WHERE path=?", (path,))


def lookup_symbol(db, path, name):
    """Return exactly one symbol, rejecting missing/ambiguous definitions.

    Metadata only; source consumers must still validate the file hash themselves.
    """
    rows = db.execute('SELECT payload FROM symbol_index WHERE path=? AND name=? LIMIT 2',
                      (path, name)).fetchall()
    if len(rows) != 1:
        raise ValueError('Simbolo no encontrado o ambiguo')
    return json.loads(rows[0][0])


def _module_name(path):
    parts = list(Path(path).with_suffix('').parts)
    if parts and parts[0] == 'src':
        parts.pop(0)
    if parts and parts[-1] == '__init__':
        parts.pop()
    return '.'.join(parts)


def _rebuild_edges(db):
    """Resolve unique local/import bindings only; no guess for dynamic receivers."""
    records = {p: (json.loads(s), json.loads(i)) for p, s, i in db.execute('SELECT path,symbols,imports FROM files') if p.endswith('.py')}
    modules = {}
    for path in records:
        modules.setdefault(_module_name(path), []).append(path)
    rows = set()
    for path, (syms, imports) in records.items():
        module = _module_name(path)
        package = module if Path(path).stem == '__init__' else module.rpartition('.')[0]
        by_name = {}
        for sym in syms:
            if 'name' in sym:
                by_name.setdefault(sym['name'], []).append(sym)
        for sym in syms:
            if 'name' not in sym or sym['kind'] == 'ClassDef':
                continue
            bindings = {}
            blocked = {imp['alias'] for imp in imports if imp.get('blocked')}
            for imp in imports + sym.get('imports', []):
                if imp.get('blocked'):
                    continue
                base = imp['module']
                if imp['level']:
                    pkg = package.split('.') if package else []
                    if imp['level'] > len(pkg):
                        continue
                    prefix = pkg[:len(pkg) - imp['level'] + 1]
                    base = '.'.join(prefix + ([base] if base else []))
                target = '.'.join(x for x in (base, imp['symbol']) if x)
                bindings.setdefault(imp['alias'], []).append(target)
            for call in sym.get('calls', []):
                head = call.split('.')[0]
                if head in blocked or head in sym.get('shadowed', []):
                    continue
                if '.' not in call and len(by_name.get(call, [])) == 1 and head not in bindings:
                    rows.add((path, sym['name'], path, call, 'local_call'))
                    continue
                targets = set(bindings.get(head, []))
                if len(targets) != 1:
                    continue
                target = targets.pop() + call[len(head):]
                bits = target.split('.')
                for cut in range(len(bits) - 1, 0, -1):
                    target_paths = modules.get('.'.join(bits[:cut]), [])
                    if len(target_paths) != 1:
                        continue
                    dst = target_paths[0]
                    symbol = '.'.join(bits[cut:])
                    choices = [s for s in records[dst][0] if s.get('name') == symbol]
                    if len(choices) == 1:
                        rows.add((path, sym['name'], dst, symbol, 'import_call'))
                    break
    rows |= _java_edges(db)
    db.execute('DELETE FROM code_edges')
    db.executemany('INSERT INTO code_edges VALUES(?,?,?,?,?)', sorted(rows))


def scan(root, db, max_bytes=120000):
    if not isinstance(max_bytes, int) or not 1 <= max_bytes <= 10_000_000:
        raise ValueError('max_bytes debe estar entre 1 y 10000000')
    root = Path(root).resolve(strict=True)
    root_guard(db, root)
    stats = {'changed': 0, 'unchanged': 0, 'skipped': 0, 'stale_removed': 0,
             'bytes_read': 0, 'parse_count': 0}
    present = set()
    fts = _has_fts(db)
    try:
        for folder, dirs, files in os.walk(root, followlinks=False):
            dirs[:] = sorted(d for d in dirs if d not in SKIP and not d.startswith('.')
                             and not SECRET_NAME.search(d) and not (Path(folder) / d).is_symlink())
            for name in sorted(files):
                p = Path(folder) / name
                if not allowed(root, p):
                    continue
                rel = p.relative_to(root).as_posix()
                try:
                    raw = read_source(root, rel, max_bytes)
                except (OSError, ValueError):
                    stats['skipped'] += 1
                    continue
                present.add(rel)
                stats['bytes_read'] += len(raw)
                sha = hashlib.sha256(raw).hexdigest()
                old = db.execute('SELECT sha,rowid FROM files WHERE path=?', (rel,)).fetchone()
                if old and old[0] == sha:
                    stats['unchanged'] += 1
                    continue
                syms, imports = _metadata(raw, p.suffix)
                stats['parse_count'] += int(p.suffix.lower() == '.py')
                identifiers = [rel]
                for sym in syms:
                    identifiers.extend([sym.get('name', '')] + sym.get('refs', []) + sym.get('calls', []) + sym.get('arguments', []))
                for imp in imports:
                    identifiers.extend([imp['alias'], imp['module'], imp['symbol']])
                search_text = ' '.join(sorted(_words(' '.join(identifiers))))
                values = (sha, len(raw), json.dumps(syms, ensure_ascii=False, separators=(',', ':')),
                          json.dumps(imports, ensure_ascii=False, separators=(',', ':')), search_text)
                if old:
                    db.execute('UPDATE files SET sha=?,size=?,symbols=?,imports=?,search_text=? WHERE path=?', values + (rel,))
                    rid = old[1]
                    if fts:
                        db.execute('DELETE FROM files_fts WHERE rowid=?', (rid,))
                else:
                    cur = db.execute('INSERT INTO files(path,sha,size,symbols,imports,search_text) VALUES(?,?,?,?,?,?)', (rel,) + values)
                    rid = cur.lastrowid
                if fts:
                    db.execute('INSERT INTO files_fts(rowid,path,search_text) VALUES(?,?,?)', (rid, rel, search_text))
                _store_symbols(db, rel, syms)
                stats['changed'] += 1
        for (rel,) in db.execute('SELECT path FROM files').fetchall():
            if rel not in present:
                stats['stale_removed'] += _remove(db, rel)
        if stats['changed'] or stats['stale_removed']:
            _rebuild_edges(db)
        db.execute("INSERT OR REPLACE INTO meta VALUES('max_bytes',?)", (str(max_bytes),))
        db.commit()
    except Exception:
        db.rollback()
        raise
    stats['indexed_total'] = db.execute('SELECT count(*) FROM files').fetchone()[0]
    stats['edge_count'] = db.execute('SELECT count(*) FROM code_edges').fetchone()[0]
    stats['symbol_count'] = db.execute('SELECT count(*) FROM symbol_index').fetchone()[0]
    stats['fts5'] = fts
    return stats


def _matches(words, term):
    return term in words or (len(term) >= 4 and any(w.startswith(term) for w in words))


def _symbol_score(sym, terms):
    words = _words(sym['name'])
    operation = _words(sym['name'].split('.')[-1])
    refs = _words(' '.join(sym.get('refs', [])))
    return _feature_score(sym['name'], sym['line'], sym['end'], sym.get('kind', ''),
                          ' '.join(words), ' '.join(operation), ' '.join(words-operation),
                          ' '.join(refs), [(term, CONCEPTS.get(term, frozenset())) for term in terms])


def search(db, q, limit=12):
    """Rank normalized identifier metadata; no source/literal content is queried."""
    if not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError('limit debe estar entre 1 y 100')
    terms = terms_of(q)
    if not terms:
        return []
    expanded = sorted(set(terms).union(*(CONCEPTS.get(t, set()) for t in terms)))
    rows = None
    if _has_fts(db):
        expression = ' OR '.join('"' + w.replace('"', '') + '"*' for w in expanded)
        try:
            rows = db.execute('SELECT f.path,f.sha,f.search_text FROM files_fts JOIN files f ON f.rowid=files_fts.rowid WHERE files_fts MATCH ?', (expression,)).fetchall()
        except sqlite3.OperationalError:
            rows = None
    if rows is None:
        rows = db.execute('SELECT path,sha,search_text FROM files').fetchall()
    out = []
    wants_tests = any(t.startswith(('test', 'prueba', 'regres')) for t in terms)
    compiled_terms = [(term, CONCEPTS.get(term, frozenset())) for term in terms]
    candidates = []
    for path, sha, text in rows:
        all_words = set(text.split())
        if not any(_matches(all_words, t) for t in expanded):
            continue
        candidates.append((path, sha, all_words))
    # Symbol FTS excludes identifiers that cannot score; the fallback evaluates
    # all compact features and preserves exactly the same scoring/filter policy.
    rankings = _rank_symbols(db, {path for path, _, _ in candidates}, expanded, compiled_terms)
    for path, sha, all_words in candidates:
        ranked = rankings.get(path, [])
        path_words = _words(path)
        path_hits = sum(_matches(path_words, t) for t in terms)
        is_test = any(part in {'tests', 'test'} or part.startswith('test_') for part in Path(path).parts)
        penalty = 45 if is_test and not wants_tests else 0
        score = (ranked[0][0] if ranked else 0) + path_hits * 18 - penalty
        if score <= 0:
            continue
        out.append({'path': path, 'sha256': sha, '_symbol_ids': [r[3] for r in ranked[:3]],
                    'score': score, 'fts_rank': 0.0,
                    'matched_terms': [t for t in terms if _matches(all_words, t)]})
    out.sort(key=lambda row: (-row['score'], -len(row['matched_terms']), row['path']))
    result = out[:limit]
    for item in result:
        item['symbols'] = [json.loads(db.execute('SELECT payload FROM symbol_index WHERE id=?', (sid,)).fetchone()[0])
                           for sid in item.pop('_symbol_ids')]
    return result


def _rank_symbols(db, paths, expanded, compiled_terms):
    if not paths:
        return {}
    columns = 's.path,s.id,s.name,s.line,s.end,s.kind,s.name_words,s.operation_words,s.parent_words,s.ref_words'
    rows = None
    if _has_fts(db):
        expression = ' OR '.join('"' + w.replace('"', '') + '"*' for w in expanded)
        try:
            rows = db.execute('SELECT ' + columns + ' FROM symbol_fts JOIN symbol_index s ON s.id=symbol_fts.rowid WHERE symbol_fts MATCH ?', (expression,))
        except sqlite3.OperationalError:
            rows = None
    if rows is None:
        rows = db.execute('SELECT ' + columns + ' FROM symbol_index s')
    rankings = {}
    for row in rows:
        path, sid, name, line, end, kind, name_words, operation_words, parent_words, ref_words = row
        if path not in paths:
            continue
        score = _feature_score(name, line, end, kind, name_words, operation_words,
                               parent_words, ref_words, compiled_terms)
        if score > 0:
            top = rankings.setdefault(path, [])
            top.append((score, line, name, sid))
            top.sort(key=lambda x: (-x[0], x[1], x[2]))
            del top[3:]
    return rankings


def _feature_score(name, line, end, kind, name_words, operation_words, parent_words,
                   ref_words, compiled_terms):
    """Same ranking formula as _symbol_score, using persisted normalized words."""
    words = set(name_words.split())
    operation = set(operation_words.split())
    parents = set(parent_words.split())
    refs = set(ref_words.split())
    direct = op_hits = semantic_op = semantic_parent = ref_hits = concept_calls = 0
    for term, concepts in compiled_terms:
        direct += _matches(words, term)
        op_hits += _matches(operation, term)
        semantic_op += bool(operation & concepts)
        semantic_parent += bool(parents & concepts)
        ref_hits += _matches(refs, term)
        concept_calls += bool(refs & concepts)
    if not (direct or semantic_op or semantic_parent or ref_hits or concept_calls):
        return 0
    score = op_hits * 24 + (direct - op_hits) * 4 + semantic_op * 7 + semantic_parent
    score += min(ref_hits, 3) * 4 + min(concept_calls, 3) * 2
    score -= 40 if kind == 'ClassDef' else 0
    score -= 8 if end - line + 1 > 200 else 0
    if name.split('.')[-1].startswith('__') and not op_hits:
        score -= 7
    return score


def edge(db, src, dst, kind):
    if kind not in {'depends_on', 'relates_to'}:
        raise ValueError('Tipo de relacion no permitido')
    if src == dst:
        raise ValueError('dependencia reflexiva')
    if kind == 'depends_on':
        graph = {}
        for a, b in db.execute("SELECT src,dst FROM edges WHERE kind='depends_on'"):
            graph.setdefault(a, set()).add(b)
        stack, seen = [dst], set()
        while stack:
            node = stack.pop()
            if node == src:
                raise ValueError('ciclo de dependencias')
            if node not in seen:
                seen.add(node)
                stack.extend(graph.get(node, ()))
    db.execute('INSERT OR IGNORE INTO edges VALUES(?,?,?)', (src, dst, kind))
    db.commit()
