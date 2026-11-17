"""Ejecuta algoritmos reales sobre datos sintéticos; no simula aciertos de un LLM."""
from pathlib import Path
import hashlib
import json
import time
from datetime import datetime
from complementos.v2f import capturar, registro_actual
from complementos.memoria import recuperar
from complementos.herramientas import Contexto, Solicitud, seleccionar


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def crear_memoria(path, datos):
    from eq2.aprendizaje import AprendizajeAgente
    apr = AprendizajeAgente(path, 'A1', ahora=lambda: datos['ahora'])
    claves = {}
    for r in datos['registros']:
        rid = apr.recordar('hipotesis' if r['estado'] == 'hipotesis' else 'hecho', r['texto'],
                          'opinion' if r['estado'] == 'hipotesis' else 'observado',
                          estado='hipotesis' if r['estado'] == 'hipotesis' else 'sin_verificar',
                          ambito=r['ambito'], dias=(datetime.fromisoformat(r['caduca']) -
                              datetime.fromisoformat(datos['ahora'])).days if r.get('caduca') else None,
                          fuente_ref='fixture:' + r['clave'])['id']
        claves[r['clave']] = rid
        if r['estado'] == 'verificada':
            apr.feedback_humano(rid, 'apoya', 'Fixture sintético, no experiencia real', 'fixture_de_prueba')
        if r.get('alterar_sha'):
            # Adversario solo sobre la base sintética recién creada.
            apr.con.execute('DROP TRIGGER apr_rec_no_modificar')
            apr.con.execute('UPDATE recuerdos SET sha256=? WHERE id=?', ('0' * 64, rid))
            apr.con.commit()
            from eq2.aprendizaje import DDL
            apr.con.executescript(DDL)
    return apr, claves


def metricas(filas, modo):
    tp = fp = fn = exactas = total_bytes = 0
    for f in filas:
        esperado, real = set(f['relevantes']), set(f[modo]['ids'])
        tp += len(esperado & real)
        fp += len(real - esperado)
        fn += len(esperado - real)
        exactas += real == esperado
        total_bytes += f[modo]['bytes_utf8']
    return {'consultas': len(filas), 'tp': tp, 'fp': fp, 'fn': fn,
            'precision': tp / (tp + fp) if tp + fp else None,
            'recall': tp / (tp + fn) if tp + fn else None,
            'selecciones_exactas': exactas, 'bytes_contexto': total_bytes,
            'tokens_modelo': None}


def ejecutar(raiz, salida):
    from eq2 import aprendizaje as A, experiencias as E, herramientas as H
    datos = json.loads((raiz / 'datos/memoria.json').read_text())
    apr, claves = crear_memoria(salida / 'memoria_a1.db', datos)
    filas = []
    t0 = time.perf_counter()
    try:
        antes = sha(apr.ruta)
        snap = capturar(apr, 'A1')
        for q in datos['consultas']:
            oro = [claves[k] for k in q['relevantes']]
            previo = apr.recuperar(q['consulta'], n=4, registrar_uso=False)
            texto = '\n'.join([E.AVISO] + [A.formatear_para_prompt(r) for r in previo]) if previo else ''
            nuevo = recuperar(snap, q['consulta'], ahora=datos['ahora'], n=4, limite_bytes=1800)
            filas.append({'id': q['id'], 'grupo': q['grupo'], 'consulta': q['consulta'], 'relevantes': oro,
                          'antes': {'ids': [r['id'] for r in previo], 'contexto': texto,
                                    'bytes_utf8': len(texto.encode())},
                          'despues': dict(nuevo, ids=[r['id'] for r in nuevo['seleccion']])})
        despues = sha(apr.ruta)
        if antes != despues:
            raise AssertionError('la recuperación modificó la base')
    finally:
        apr.cerrar()
    tiempos = {'memoria_s': time.perf_counter() - t0}
    herramientas = []
    reg = registro_actual()
    huella_registro = H.huella_registro()
    t0 = time.perf_counter()
    for q in json.loads((raiz / 'datos/herramientas.json').read_text()):
        s = Solicitud(q['necesidad'], tuple(q['archivos']), q['casos'], q['lenguaje'])
        c = Contexto(q['agente'], q['flujo'], q['autorizado'])
        try:
            previo = H.seleccionar(q['necesidad'], q['autorizado'])
            previo['decision'] = [previo['herramienta'], not previo['sustituida']]
            previo['compatible_api'] = True
        except ValueError as e:
            previo = {'decision': [None, False], 'compatible_api': False, 'error': str(e)}
        nuevo = seleccionar(s, c, reg)
        nuevo['decision'] = [nuevo['herramienta'], nuevo['satisface']]
        herramientas.append(dict(q, antes=previo, despues=nuevo))
    tiempos['herramientas_s'] = time.perf_counter() - t0
    if H.huella_registro() != huella_registro:
        raise AssertionError('registro alterado')
    resumen = {'naturaleza': 'REAL_COMPONENTES_DATOS_SINTETICOS', 'modelo': 'OMITIDA',
               'memoria': {grupo: {m: metricas([f for f in filas if grupo == 'todas' or f['grupo'] == grupo], m)
                                   for m in ('antes', 'despues')} for grupo in ('todas', 'base', 'reservado')},
               'herramientas': {grupo: {m: {'correctas': sum(f[m]['decision'] == f['esperado'] for f in herramientas
                                             if grupo == 'todas' or f['antes']['compatible_api']),
                                          'total': sum(grupo == 'todas' or f['antes']['compatible_api'] for f in herramientas)}
                                      for m in ('antes', 'despues')} for grupo in ('todas', 'api_original')},
               'preservacion_sqlite': {'antes': antes, 'despues': despues, 'identica': antes == despues},
               'registro_herramientas_sha256': huella_registro,
               'tiempos': tiempos, 'memoria_detalle': filas, 'herramientas_detalle': herramientas}
    determinista = dict(resumen)
    determinista.pop('tiempos')
    determinista.pop('preservacion_sqlite')  # SQLite contiene registros de prueba; se prueba igualdad por run.
    resumen['huella_decisiones'] = hashlib.sha256(json.dumps(determinista, sort_keys=True).encode()).hexdigest()
    (salida / 'comparacion.json').write_text(json.dumps(resumen, ensure_ascii=False, indent=2) + '\n')
    return resumen
