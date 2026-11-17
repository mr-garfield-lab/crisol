"""Catálogo fijo de código revisable. Nunca se ejecuta texto recibido de agentes.

La elección de candidato permite evaluar programación básica con oráculos
ocultos sin habilitar ejecución de Python arbitrario. No mide generación libre.
"""
import inspect


def ordenar_a(xs):
    xs.sort()
    return xs


def ordenar_b(xs):
    return sorted(xs)


def ordenar_c(xs):
    return list(reversed(xs))


def pares_a(n):
    return sum(1 for x in range(n) if x % 2 == 0)


def pares_b(n):
    return n // 2


def pares_c(n):
    return sum(1 for x in range(n + 1) if x % 2 == 0)


def dedup_a(xs):
    return sorted(set(xs))


def dedup_b(xs):
    return list(dict.fromkeys(xs))


def dedup_c(xs):
    return list(xs)


CATALOGO = {
    'PR01': (ordenar_a, ordenar_b, ordenar_c),
    'PR02': (pares_a, pares_b, pares_c),
    'PR03': (dedup_a, dedup_b, dedup_c),
}
ENUNCIADOS = {
    'PR01': 'Ordenar una lista de enteros sin modificar la lista original.',
    'PR02': 'Contar enteros pares en el intervalo inclusivo 0..n, para n entero no negativo.',
    'PR03': 'Eliminar enteros duplicados preservando la primera aparición y sin modificar la lista original.',
}


def casos_publicos():
    return [{'id': cid, 'area': 'programacion', 'pregunta': ENUNCIADOS[cid],
             'opciones': {letra: inspect.getsource(fn) for letra, fn in zip('ABC', funciones)},
             'evidencias': {'E1': ENUNCIADOS[cid]}, 'memorias': [], 'acciones_permitidas': []}
            for cid, funciones in CATALOGO.items()]
