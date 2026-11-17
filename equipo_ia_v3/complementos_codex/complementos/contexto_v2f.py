"""Adaptación al constructor REAL de prompts V2-F: evita recuerdos cortados.

No cambia políticas, instrucciones, presupuestos ni el backend. Solo reduce el
bloque auxiliar de experiencias. Las tareas/código/plan conservan su prioridad.
"""
import json
import re

PATRON = re.compile(r'<<<DATOS_NO_CONFIABLES fuente=experiencias\n(.*?)\nDATOS_NO_CONFIABLES>>>', re.S)


def paquete(texto):
    def pares(ps):
        out = {}
        for k, v in ps:
            if k in out:
                raise ValueError('clave duplicada')
            out[k] = v
        return out
    d = json.loads(texto, object_pairs_hook=pares)
    if not isinstance(d, dict) or set(d) != {'aviso', 'recuerdos'} or not isinstance(d['recuerdos'], list):
        raise ValueError('paquete desconocido')
    for r in d['recuerdos']:
        if not isinstance(r, dict) or not {'id', 'estado', 'texto', 'ref', 'fecha'} <= set(r):
            raise ValueError('recuerdo incompleto')
    return d


def acotar(texto, max_chars):
    """Elimina registros enteros desde el final; no resume ni corta contenido."""
    try:
        d = paquete(texto)
    except (ValueError, TypeError):
        return ''
    while d['recuerdos']:
        t = json.dumps(d, ensure_ascii=False, separators=(',', ':'))
        if len(t) <= max_chars:
            return t
        d['recuerdos'].pop()
    return ''


def proteger_mensajes(mensajes):
    resultado, descartados = [], 0
    for mensaje in mensajes:
        m = dict(mensaje)
        if m.get('role') == 'user':
            def revisar(match):
                nonlocal descartados
                try:
                    paquete(match.group(1))
                    return match.group(0)
                except (ValueError, TypeError):
                    descartados += 1
                    return ''
            m['content'] = PATRON.sub(revisar, m['content'])
        resultado.append(m)
    return resultado, descartados


def crear_agentes(backend):
    """Crea AgentesMotorLLMV2F con protección del contexto; NO inicia el backend."""
    from eq2 import config
    from eq2.motor_v2f import AgentesMotorLLMV2F

    class AgentesConMemoriaEntera(AgentesMotorLLMV2F):
        def __init__(self, backend):
            super().__init__(backend)
            self.recortes_memoria = []

        def _pedir(self, paso, tarea, bloques):
            seguros = []
            for nombre, texto, cap in bloques:
                if nombre == 'experiencias' and texto:
                    entero = acotar(texto, int(cap * config.CTX / 1024))
                    if entero != texto:
                        self.recortes_memoria.append({'paso': paso, 'motivo': 'limite_del_bloque',
                                                     'antes_chars': len(texto), 'despues_chars': len(entero)})
                    texto = entero
                seguros.append((nombre, texto, cap))
            return super()._pedir(paso, tarea, seguros)

        def _llamar(self, paso, mensajes, max_gen, tipo):
            seguros, n = proteger_mensajes(mensajes)
            if n:
                self.recortes_memoria.append({'paso': paso, 'motivo': 'fragmento_por_contexto_total', 'bloques': n})
            return super()._llamar(paso, seguros, max_gen, tipo)

    return AgentesConMemoriaEntera(backend)
