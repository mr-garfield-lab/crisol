"""Asesor puro: no ejecuta herramientas, no concede autorización, no abre rutas."""
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class Herramienta:
    nombre: str
    agentes: tuple
    contextos: tuple
    requiere_autorizacion: bool
    argumento: str


@dataclass(frozen=True)
class Contexto:
    agente: str
    flujo: str
    autorizado: bool  # Solo el controlador/CLI puede suministrarlo.


@dataclass(frozen=True)
class Solicitud:
    necesidad: str
    archivos: tuple = ()  # Nombres relativos; el despachador validará contenidos/rutas al usar.
    casos: int = 0
    lenguaje: str = 'python'
    huella_entrada: str = ''  # SHA-256 de argumentos/código; lo calcula el controlador.


@dataclass(frozen=True)
class Intento:
    herramienta: str
    huella_entrada: str
    categoria: str


def _ruta_valida(r):
    return (isinstance(r, str) and 0 < len(r) <= 240 and
            all(ord(c) >= 32 for c in r) and not any(c in r for c in '\\:%\x7f') and
            all(p not in ('', '.', '..') and not p.startswith('.') for p in r.split('/')))


def seleccionar(solicitud, contexto, registro, *, intentos=()):
    """Devuelve recomendación y descartes completos; jamás un permiso o un resultado de prueba.

    Los datos de memoria/diagnóstico no son argumentos de esta función. `registro`
    es una instantánea del REGISTRO de V2-F suministrada por código confiable.
    """
    s, c = solicitud, contexto
    if (c.agente not in ('A1', 'A2', 'A3', 'controlador', 'evaluador') or
            type(c.autorizado) is not bool or not isinstance(c.flujo, str)):
        raise ValueError('contexto de seguridad inválido')
    if (type(s.casos) is not int or not 0 <= s.casos <= 100 or len(s.archivos) > 100
            or any(not _ruta_valida(p) for p in s.archivos)
            or (s.huella_entrada and not re.fullmatch('[0-9a-f]{64}', s.huella_entrada))):
        raise ValueError('argumentos inválidos')
    nombres = [h.nombre for h in registro]
    if len(nombres) != len(set(nombres)):
        raise ValueError('registro ambiguo')
    py = s.lenguaje == 'python' and any(p.endswith('.py') for p in s.archivos)
    tests = py and any(p.rsplit('/', 1)[-1].startswith('test_') and p.endswith('.py') for p in s.archivos)
    lista = {
        'comprobar_sintaxis': [('analisis_estatico', py, True)],
        'comprobar_comportamiento': [('pruebas_python', tests, True), ('ejecutar_casos', py and s.casos > 0, True),
                                    ('analisis_estatico', py, False)],
        'ejecutar_casos': [('ejecutar_casos', py and s.casos > 0, True), ('analisis_estatico', py, False)],
        'analizar_lua': [('analizar_lua_estatico', s.lenguaje == 'lua' and any(p.endswith('.lua') for p in s.archivos), True)],
        'inspeccionar_zip': [('inspeccionar_zip', any(p.endswith('.zip') for p in s.archivos), True)],
        'simular_escenario': [('simular_escenario', any(p.endswith('.json') for p in s.archivos), True)],
    }.get(s.necesidad, [])
    mapa = {h.nombre: h for h in registro}
    descartes, elegibles = [], []
    for nombre, suficiente, satisface in lista:
        h = mapa.get(nombre)
        razon = None
        if h is None:
            razon = 'no_registrada'
        elif c.agente not in h.agentes:
            razon = 'agente_no_permitido'
        elif c.flujo not in h.contextos:
            razon = 'flujo_incompatible'
        elif h.requiere_autorizacion and not c.autorizado:
            razon = 'requiere_autorizacion_humana'
        elif not suficiente:
            razon = 'faltan_argumentos_o_lenguaje_incompatible'
        elif s.huella_entrada and any(i.herramienta == nombre and i.huella_entrada == s.huella_entrada
                                     and i.categoria != 'ok' for i in intentos):
            razon = 'mismo_intento_fallido'
        if razon:
            descartes.append({'herramienta': nombre, 'motivo': razon})
        else:
            elegibles.append((nombre, satisface))
    elegido = elegibles[0] if elegibles else (None, False)
    completa = elegido[1]
    return {'herramienta': elegido[0], 'satisface': completa,
            'estado': 'propuesta' if completa else 'parcial' if elegido[0] else 'abstencion',
            'alternativas': [n for n, _ in elegibles[1:]], 'descartes': descartes,
            'intervencion_humana': not completa,
            'nota': 'Revalidar en el despachador. Análisis estático no prueba comportamiento.',
            'ejecuciones': 0}
