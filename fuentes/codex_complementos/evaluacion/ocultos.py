"""Solo evaluador: casos reservados que NO se envían al adaptador de agentes."""
from copy import deepcopy
from .programas import CATALOGO

CASOS = {
    'PR01': [([], []), ([2, 1], [1, 2]), ([3, -1, 3, 0], [-1, 0, 3, 3])],
    'PR02': [(0, 1), (1, 1), (2, 2), (8, 5)],
    'PR03': [([], []), ([2, 1, 2, 0, 1], [2, 1, 0]), ([4, 4, 4], [4])],
}


def comprobar_catalogo():
    resultados, oro = [], {}
    for cid, funciones in CATALOGO.items():
        validas = []
        for letra, fn in zip('ABC', funciones):
            casos = []
            for entrada, esperado in CASOS[cid]:
                arg = deepcopy(entrada)
                obtenido = fn(arg)  # Función fija del propio módulo, nunca eval/exec/import de respuestas.
                casos.append({'entrada': entrada, 'esperado': esperado, 'obtenido': obtenido,
                              'sin_mutacion': arg == entrada,
                              'ok': obtenido == esperado and arg == entrada})
            ok = all(c['ok'] for c in casos)
            if ok:
                validas.append(letra)
            resultados.append({'tarea': cid, 'candidata': letra, 'casos': casos, 'ok': ok})
        if len(validas) != 1:
            raise ValueError('oráculo no discrimina una candidata: ' + cid)
        oro[cid] = {'respuesta': validas[0], 'evidencias': ['E1'],
                    'recuerdos_relevantes': [], 'recuerdos_incorrectos': []}
    return resultados, oro


def evaluar_programacion(adaptador, salida):
    """Usa ÍNTEGRO el motor previo, con sus presupuestos equivalentes y métricas.

    El integrador debe colocar evaluador_anterior/evaluacion_multiagente_v1 en
    sys.path. El callback del modelo recibe exclusivamente casos_publicos().
    """
    from evalua import ejecutar
    from .programas import casos_publicos
    _, oro = comprobar_catalogo()
    return ejecutar(adaptador, casos_publicos(), oro, salida)
