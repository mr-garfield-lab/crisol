"""Diagnóstico auxiliar de registros: hipótesis, nunca instrucciones ejecutables."""
import hashlib
import re

REGLAS = (
    ('permisos', r'(?m)^(?:PermissionError|no_autorizada|rechazada_lista_blanca)\b',
     'Comprobar la política y solicitar revisión humana; no ampliar permisos.'),
    ('sintaxis', r'(?m)^(?:SyntaxError|IndentationError|TabError)\b',
     'Revisar archivo y línea con el analizador estático antes de repetir pruebas.'),
    ('dependencias', r'(?m)^(?:ModuleNotFoundError|ImportError)\b',
     'Comprobar nombre, ruta y dependencias declaradas; no instalar automáticamente.'),
    ('logica', r'(?m)^AssertionError\b',
     'Comparar esperado y obtenido; conservar el caso que falla y buscar un contraejemplo.'),
    ('recursos', r'(?m)^(?:TimeoutError|MemoryError|tiempo_excedido)\b',
     'Revisar tamaño de entrada y complejidad; no aumentar el presupuesto automáticamente.'),
    ('ejecucion', r'(?m)^(?:TypeError|ValueError|IndexError|KeyError|ZeroDivisionError|sqlite3\.\w+Error)\b',
     'Reducir el caso que reproduce el fallo y comprobar tipos, límites y estado.'),
)


def diagnosticar(registro, huella_codigo, *, anteriores=()):
    if not isinstance(registro, str) or len(registro) > 1_000_000:
        raise ValueError('registro inválido o excesivo')
    if not re.fullmatch('[0-9a-f]{64}', huella_codigo):
        raise ValueError('falta huella de los argumentos/código')
    encontrados = [(cat, m.group(0), estrategia) for cat, patron, estrategia in REGLAS
                   if (m := re.search(patron, registro))]
    categoria, evidencia, estrategia = encontrados[0] if encontrados else (
        'desconocido', '', 'Solicitar el registro completo y una reproducción; no adivinar la causa.')
    firma = hashlib.sha256((huella_codigo + '\n' + categoria + '\n' + registro).encode()).hexdigest()
    repetido = firma in anteriores
    return {'categoria': categoria, 'evidencia': evidencia, 'estrategia': estrategia,
            'naturaleza': 'hipotesis_desde_registro', 'firma': firma, 'repetido': repetido,
            'recomendar_reintento_identico': False, 'intervencion_humana': repetido or categoria in ('permisos', 'desconocido'),
            'cambios_aplicados': 0}
