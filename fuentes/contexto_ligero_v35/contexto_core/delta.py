"""Contexto incremental local, verificable y sin asumir memoria del receptor.

Un snapshot guarda solo el texto que ya produjo el motor y un identificador de
origen opcional. No copia consultas/metadatos crudos que el render pudo ocultar.
Los hashes detectan cambios, no autentican al autor ni autorizan instrucciones.
"""
import difflib
import hashlib
import json
import re

from .safety import safe_label
from .tokens import TokenCounter

SNAPSHOT_SCHEMA = 'contexto.snapshot.v1'
TRANSPORT_SCHEMA = 'contexto.transport.v1'
MAX_TEXT_BYTES = 8 * 1024 * 1024
MAX_LINES = 100_000
MAX_CHANGES = 4096
_SHA = re.compile(r'[0-9a-f]{64}\Z')


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False)


def _bytes(text):
    if not isinstance(text, str):
        raise ValueError('El texto del contexto debe ser una cadena')
    try:
        raw = text.encode('utf-8')
    except UnicodeError as exc:
        raise ValueError('Texto con codificación Unicode inválida') from exc
    if len(raw) > MAX_TEXT_BYTES:
        raise ValueError('Contexto excede el límite local de 8 MiB')
    return raw


def _lines(text):
    _bytes(text)
    lines = text.splitlines(keepends=True)
    if len(lines) > MAX_LINES:
        raise ValueError('Contexto excede el límite local de líneas')
    return lines


def _origin(origin):
    if origin is not None and (not isinstance(origin, str) or len(origin) > 256):
        raise ValueError('origin debe ser nulo o un identificador de hasta 256 caracteres')
    if origin is not None:
        _bytes(origin)
    return origin


def _digest(text, origin):
    payload = {'schema': SNAPSHOT_SCHEMA, 'text': text, 'origin': origin}
    return hashlib.sha256(_json(payload).encode('utf-8')).hexdigest()


def _snapshot(text, origin):
    _lines(text)
    _origin(origin)
    return {'schema': SNAPSHOT_SCHEMA, 'sha256': _digest(text, origin),
            'text': text, 'origin': origin}


def create_snapshot(packet_details, *, origin=None):
    """Congela text exactamente; query/rutas/líneas/hashes permanecen en él.

    origin es opcional: conviene usar un hash de la raíz, no una ruta privada.
    No se leen archivos, ejecuta código ni se guarda otro campo de packet_details.
    """
    if not isinstance(packet_details, dict) or 'text' not in packet_details:
        raise ValueError('Se requiere un paquete con campo text')
    origin = _origin(origin)
    return _snapshot(packet_details['text'], safe_label(origin) if origin is not None else None)


def validate_snapshot(snapshot):
    """Valida esquema y digest; devuelve una copia normalizada independiente."""
    if not isinstance(snapshot, dict) or set(snapshot) != {'schema', 'sha256', 'text', 'origin'}:
        raise ValueError('Estructura de snapshot inválida')
    if snapshot['schema'] != SNAPSHOT_SCHEMA:
        raise ValueError('Esquema de snapshot incompatible')
    if not isinstance(snapshot['sha256'], str) or not _SHA.fullmatch(snapshot['sha256']):
        raise ValueError('Hash de snapshot inválido')
    expected = _snapshot(snapshot['text'], snapshot['origin'])
    if expected['sha256'] != snapshot['sha256']:
        raise ValueError('Hash de snapshot no coincide; recuperar contexto completo')
    return expected


def full_envelope(snapshot):
    """Transporte completo que puede recuperarse sin una base previa."""
    snap = validate_snapshot(snapshot)
    return {'schema': TRANSPORT_SCHEMA, 'mode': 'full', 'base_sha256': None,
            'target_sha256': snap['sha256'], 'text': snap['text'], 'origin': snap['origin']}


def _changes(before, after):
    """Diff por líneas limitado; textos grandes usan un reemplazo central lineal."""
    if len(before) <= MAX_CHANGES and len(after) <= MAX_CHANGES:
        matches = difflib.SequenceMatcher(a=before, b=after, autojunk=True)
        return [{'start': i, 'delete': j-i, 'insert': ''.join(after[k:l])}
                for op, i, j, k, l in matches.get_opcodes() if op != 'equal']
    left = 0
    while left < min(len(before), len(after)) and before[left] == after[left]:
        left += 1
    right = 0
    while (right < min(len(before), len(after)) - left
           and before[len(before)-1-right] == after[len(after)-1-right]):
        right += 1
    end_before, end_after = len(before)-right, len(after)-right
    if left == end_before and left == end_after:
        return []
    return [{'start': left, 'delete': end_before-left,
             'insert': ''.join(after[left:end_after])}]


def _validate_envelope(envelope):
    if not isinstance(envelope, dict) or envelope.get('schema') != TRANSPORT_SCHEMA:
        raise ValueError('Esquema de transporte incompatible')
    shared = {'schema', 'mode', 'base_sha256', 'target_sha256', 'origin'}
    mode = envelope.get('mode')
    if mode not in ('full', 'delta') or set(envelope) != shared | ({'text'} if mode == 'full' else {'changes'}):
        raise ValueError('Estructura de transporte inválida')
    _origin(envelope['origin'])
    if not isinstance(envelope['target_sha256'], str) or not _SHA.fullmatch(envelope['target_sha256']):
        raise ValueError('Hash de destino inválido')
    if mode == 'full':
        if envelope['base_sha256'] is not None:
            raise ValueError('El transporte completo no requiere una base')
        _lines(envelope['text'])
        return
    if not isinstance(envelope['base_sha256'], str) or not _SHA.fullmatch(envelope['base_sha256']):
        raise ValueError('Hash de base inválido')
    changes = envelope['changes']
    if not isinstance(changes, list) or len(changes) > MAX_CHANGES:
        raise ValueError('Lista de cambios inválida o demasiado grande')
    previous_start, previous_end = -1, 0
    inserted_bytes = 0
    for change in changes:
        if not isinstance(change, dict) or set(change) != {'start', 'delete', 'insert'}:
            raise ValueError('Cambio inválido')
        start, count = change['start'], change['delete']
        if type(start) is not int or type(count) is not int or start < 0 or count < 0:
            raise ValueError('Los rangos deben ser enteros no negativos')
        if start <= previous_start or start < previous_end:
            raise ValueError('Cambios duplicados, solapados o desordenados')
        inserted_bytes += len(_bytes(change['insert']))
        if inserted_bytes > MAX_TEXT_BYTES:
            raise ValueError('Cambios exceden el límite local de tamaño')
        if count == 0 and not change['insert']:
            raise ValueError('Cambio vacío inválido')
        previous_start, previous_end = start, start + count


def transport_text(envelope):
    """JSON compacto exacto que se transmite; métricas se calculan sobre él."""
    _validate_envelope(envelope)
    return _json(envelope)


def apply_delta(base, envelope, *, expected_base_sha256=None):
    """Reconstruye y verifica el destino sin interpretar su contenido.

    Un delta exige el snapshot exacto. expected_base_sha256 permite además
    confirmar el estado que el receptor declara poseer. Para recuperar un
    transporte completo, base puede ser None. Nunca se aplica sobre otra base.
    """
    _validate_envelope(envelope)
    if expected_base_sha256 is not None:
        if base is None or validate_snapshot(base)['sha256'] != expected_base_sha256:
            raise ValueError('La base declarada no coincide; recuperar contexto completo')
    if envelope['mode'] == 'full':
        target = _snapshot(envelope['text'], envelope['origin'])
    else:
        if base is None:
            raise ValueError('Falta base para delta; recuperar contexto completo')
        snap = validate_snapshot(base)
        if snap['sha256'] != envelope['base_sha256']:
            raise ValueError('Hash de base no coincide; recuperar contexto completo')
        if snap['origin'] != envelope['origin']:
            raise ValueError('Origen del delta distinto; recuperar contexto completo')
        lines = _lines(snap['text'])
        pieces, cursor, size = [], 0, 0
        for change in envelope['changes']:
            start, end = change['start'], change['start'] + change['delete']
            if start > len(lines) or end > len(lines):
                raise ValueError('Cambio fuera del rango de la base')
            unchanged = ''.join(lines[cursor:start])
            size += len(unchanged.encode('utf-8')) + len(change['insert'].encode('utf-8'))
            if size > MAX_TEXT_BYTES:
                raise ValueError('Destino excede el límite local de tamaño')
            pieces.extend((unchanged, change['insert']))
            cursor = end
        pieces.append(''.join(lines[cursor:]))
        target = _snapshot(''.join(pieces), envelope['origin'])
    if target['sha256'] != envelope['target_sha256']:
        raise ValueError('Hash del destino no coincide; cambios alterados o incompletos')
    return target


def make_delta(base_snapshot, current_snapshot, *, token_counter=None):
    """Elige delta solo si ahorra unidades del contador Y bytes frente al completo.

    No incluye métricas en el transporte, evitando que ese diagnóstico anule el
    ahorro. Sin un tokenizador real, la unidad de selección sigue siendo estimada.
    """
    base = validate_snapshot(base_snapshot)
    target = validate_snapshot(current_snapshot)
    full = full_envelope(target)
    # Una base de otro origen no sirve como contexto previo de este proyecto.
    if base['origin'] != target['origin']:
        return full
    patch = {'schema': TRANSPORT_SCHEMA, 'mode': 'delta',
             'base_sha256': base['sha256'], 'target_sha256': target['sha256'],
             'origin': target['origin'], 'changes': _changes(_lines(base['text']), _lines(target['text']))}
    # Defensa: ningún algoritmo de diff puede producir evidencia sin verificarla.
    if apply_delta(base, patch) != target:
        raise ValueError('La reconstrucción incremental no es exacta')
    counter = token_counter or TokenCounter()
    patch_text, full_text = transport_text(patch), transport_text(full)
    if (counter.count(patch_text) < counter.count(full_text)
            and len(patch_text.encode('utf-8')) < len(full_text.encode('utf-8'))):
        return patch
    return full


def transport_metrics(base_snapshot, current_snapshot, envelope, *, token_counter=None):
    """Cuenta JSON completo, hashes y sintaxis; nunca solo los fragmentos nuevos."""
    base = validate_snapshot(base_snapshot) if base_snapshot is not None else None
    target = validate_snapshot(current_snapshot)
    if apply_delta(base, envelope) != target:
        raise ValueError('El transporte no reconstruye el snapshot solicitado')
    counter = token_counter or TokenCounter()
    full_text = transport_text(full_envelope(target))
    sent_text = transport_text(envelope)
    full_count, sent_count = counter.count(full_text), counter.count(sent_text)
    return {'mode': envelope['mode'], 'full': counter.metrics(full_text),
            'transmitted': counter.metrics(sent_text), 'saved_count': full_count-sent_count,
            'plain_text_measure': counter.metrics(target['text']),
            'saved_vs_plain_text_count': counter.count(target['text'])-sent_count,
            'saving_fraction': (full_count-sent_count)/full_count if full_count else 0.0,
            'budget_unit': counter.unit, 'base_required': envelope['mode'] == 'delta',
            'scope': 'JSON completo; no incluye plantilla de chat ni instrucciones externas'}
