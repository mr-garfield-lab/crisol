"""Puente para las API INSPECCIONADAS de V2-F. Importaciones diferidas.

No abre rutas ni construye AprendizajeAgente. Usa una conexión YA ABIERTA por el
controlador y copia a RAM mediante backup SQLite. Nada se migra ni se registra.
"""
import sqlite3
import time
import json
from .memoria import Instantanea, Recuerdo


def capturar(apr, agente):
    from eq2 import aprendizaje as A
    if agente not in ('A1', 'A2', 'A3') or apr.agente != agente:
        raise ValueError('identidad incompatible')
    def comprobar(con):
        meta = dict(con.execute('SELECT clave,valor FROM meta'))
        if meta.get('agente') != agente or meta.get('esquema_aprendizaje') != A.ESQUEMA_APRENDIZAJE:
            raise ValueError('identidad o esquema incompatible')
    comprobar(apr.con)
    if apr.con.in_transaction:
        raise ValueError('capturar requiere transacción finalizada')
    con = sqlite3.connect(':memory:')
    try:
        inicio = time.monotonic()
        def progreso(estado, restantes, total):
            if total > 16384 or time.monotonic() - inicio > 2:
                raise TimeoutError('instantánea demasiado grande o bloqueada')
        apr.con.backup(con, pages=128, progress=progreso, sleep=0.01)
        con.row_factory = sqlite3.Row
        con.execute('PRAGMA query_only=ON')
        comprobar(con)
        # Reutiliza lectores y validadores de Claude sobre la copia, sin __init__/DDL.
        lector = object.__new__(A.AprendizajeAgente)
        lector.con, lector.agente, lector.ahora = con, agente, apr.ahora
        filas = con.execute('SELECT id FROM recuerdos ORDER BY num LIMIT 401').fetchall()
        if len(filas) > 400:
            raise ValueError('demasiados recuerdos')
        salida = []
        for (rid,) in filas:
            h = lector.historial(rid)
            r = h['recuerdo']
            if r['agente'] != agente:
                raise ValueError('fila de otro agente')
            bloqueado = 'cuarentena' if r['cuarentena'] else None
            if not r['integro']:
                bloqueado = 'texto_alterado'
            texto = '\n'.join(str(r.get(k) or '') for k in ('texto', 'ambito', 'fuente_ref'))
            if A.analizar_contenido(texto)['veredicto'] != 'aceptado':
                bloqueado = 'contenido_instructivo'
            respaldo = None
            if r['estado'] == 'verificada_por_prueba':
                t = h['transiciones'][-1]
                ev = next((e for e in h['evidencias'] if e['id'] == t['evidencia_id']), {})
                if ev.get('recuerdo_id') == rid and ev.get('efecto') == 'apoya':
                    if ev.get('tipo') == 'feedback_humano' and ev.get('actor') == 'usuario' and ev.get('autorizado_por'):
                        respaldo = 'feedback_humano'
                    elif ev.get('tipo') == 'prueba_estatica':
                        ej = next((e for e in h['ejecuciones'] if e['id'] == ev.get('ejecucion_id')), {})
                        # Solo el verificador declarativo ya disponible; ninguno aportado por recuerdos.
                        if ej.get('verificador') == 'regla_declarativa':
                            try:
                                regla = json.loads(ej['parametros']).get('regla', {})
                                # No reevaluar regex de una base no confiable en el proceso anfitrión.
                                if not isinstance(regla, dict) or set(regla) not in (
                                        {'contiene'}, {'no_contiene'}, {'lineas_existen'}, {'cita_literal'}):
                                    raise ValueError('regla no apta para recuperación en línea')
                                real = lector._comprobar_ejecucion(ej['id'])
                                if real['recuerdo_id'] == rid and real['resultado'] == real['esperado']:
                                    respaldo = 'prueba_registrada'
                            except (ValueError, KeyError, TypeError):
                                bloqueado = 'evidencia_alterada'
            salida.append(Recuerdo(rid, agente, r['texto'], r['sha256'], r['estado'], r['creado'],
                                   r['caduca'], r['ambito'], r['fuente'], r['fuente_ref'], respaldo,
                                   bloqueado, tuple(h['contradicciones']), r['sustituye']))
        return Instantanea(agente, tuple(salida))
    finally:
        con.close()


def registro_actual():
    from eq2.herramientas import REGISTRO
    from .herramientas import Herramienta
    return tuple(Herramienta(h.nombre, tuple(h.agentes), tuple(h.contextos),
                            h.requiere_autorizacion, h.argumento) for h in REGISTRO.values())


class MemoriaComplementada:
    """Proxy explícito compatible con MotorV2F y Debate. Escrituras delegadas sin cambios.

    La recuperación no registra usos persistentes; entrega el informe al callback
    de confianza `informar`, opcional. No cierra ni crea la memoria prestada.
    """
    def __init__(self, memoria_existente, *, limite_bytes=1800, informar=None):
        self.base = memoria_existente
        self.limite_bytes = limite_bytes
        self.informar = informar

    def bloque_prompt(self, agente, consulta, n=None, tarea_ref=None):
        from .memoria import recuperar
        res = recuperar(capturar(self.base.apr[agente], agente), consulta, ahora=self.base.ahora(),
                        n=4 if n is None else n, limite_bytes=self.limite_bytes)
        if self.informar is not None:
            self.informar(res)
        return res['contexto']

    def registrar(self, *args, **kwargs):
        return self.base.registrar(*args, **kwargs)

    def resumen(self):
        return self.base.resumen()
