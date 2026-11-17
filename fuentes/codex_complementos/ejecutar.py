#!/usr/bin/env python3
"""Única orden: python3 -B ejecutar.py. No modelos, red ni instalación."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import sqlite3
import stat
import subprocess
import sys
import traceback
import unittest
import zipfile

sys.dont_write_bytecode = True
RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))
SHA_V2F = 'ee73af5702e1d627707c8d289da0ca5e0126eba6bf34500f697f77676ee1e146'


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def guardar(p, obj):
    with p.open('x', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write('\n')


def integridad():
    esperado = json.loads((RAIZ / 'MANIFIESTO_SHA256.json').read_text())
    reales = {p.relative_to(RAIZ).as_posix() for p in RAIZ.rglob('*') if p.is_file()
              and not {'resultados', '__pycache__'} & set(p.relative_to(RAIZ).parts)
              and p != RAIZ / 'MANIFIESTO_SHA256.json'}
    if reales != set(esperado):
        raise ValueError('archivos añadidos o ausentes: ' + str(sorted(reales ^ set(esperado))))
    for nombre, h in esperado.items():
        p = RAIZ / nombre
        if p.is_symlink() or sha(p) != h:
            raise ValueError('archivo alterado: ' + nombre)


def referencia(salida):
    archivo = RAIZ / 'referencia/equipo_f2_v2f.zip'
    if sha(archivo) != SHA_V2F:
        raise ValueError('V2-F no coincide con el adjunto inspeccionado')
    with zipfile.ZipFile(archivo) as z:
        if z.testzip() is not None:
            raise ValueError('CRC de V2-F incorrecto')
        for i in z.infolist():
            p = PurePosixPath(i.filename)
            if p.is_absolute() or '..' in p.parts or stat.S_ISLNK(i.external_attr >> 16):
                raise ValueError('entrada ZIP insegura')
        z.extractall(salida / 'referencia_extraida')
    return salida / 'referencia_extraida/equipo_f2_v2f'


class Doble:
    def __init__(self, *salidas): self.salidas = salidas
    def write(self, t):
        for s in self.salidas: s.write(t); s.flush()
    def flush(self):
        for s in self.salidas: s.flush()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--salida', type=Path, help='Directorio NUEVO de evidencias; no se sobrescribe')
    args = ap.parse_args()
    salida = args.salida or RAIZ / 'resultados' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    print('=== INICIO COMPLEMENTOS EQUIPO IA V1 ===', flush=True)
    try:
        salida.parent.mkdir(parents=True, exist_ok=True)
        salida.mkdir(mode=0o700, exist_ok=False)
    except OSError as e:
        print('Salida rechazada:', e)
        print('=== FIN COMPLEMENTOS: INCONCLUSA ===')
        return 2
    with (salida / 'terminal.log').open('x', encoding='utf-8') as terminal:
        out = Doble(sys.stdout, terminal)
        print('=== INICIO COMPLEMENTOS EQUIPO IA V1 ===', file=out)
        try:
            integridad()
            fuente = referencia(salida)
            huellas_v2f = {p.relative_to(fuente).as_posix(): sha(p) for p in fuente.rglob('*') if p.is_file()}
            sys.path.insert(0, str(fuente / 'src'))
            antiguo = RAIZ / 'evaluador_anterior/evaluacion_multiagente_v1'
            sys.path.insert(0, str(antiguo))
            os.environ['COMPLEMENTOS_SALIDA'] = str(salida)
            guardar(salida / 'entorno.json', {'python': sys.version, 'plataforma': platform.platform(),
                    'sqlite': sqlite3.sqlite_version, 'v2f_sha256': SHA_V2F, 'dependencias_nuevas': []})
            suite = unittest.defaultTestLoader.discover(str(RAIZ / 'tests'), pattern='test_*.py')
            with (salida / 'unitarias.log').open('x', encoding='utf-8') as log:
                res = unittest.TextTestRunner(stream=Doble(out, log), verbosity=2).run(suite)
            unitarias = dict(ejecutadas=res.testsRun, fallidas=len(res.failures), errores=len(res.errors), omitidas=len(res.skipped))
            guardar(salida / 'unitarias.json', unitarias)
            with (salida / 'evaluador_anterior.log').open('x', encoding='utf-8') as log:
                old = subprocess.run([sys.executable, '-B', '-I', '-S', str(antiguo / 'ejecutar.py'),
                                      '--salida', str(salida / 'evaluador_anterior')], stdout=log, stderr=subprocess.STDOUT,
                                     timeout=120, check=False)
            print('Evaluador anterior completo, código de salida:', old.returncode, file=out)
            from evaluacion.componentes import ejecutar
            comparaciones = []
            for numero in (1, 2):
                carpeta = salida / ('componentes_' + str(numero)); carpeta.mkdir()
                comparaciones.append(ejecutar(RAIZ, carpeta))
            repite = comparaciones[0]['huella_decisiones'] == comparaciones[1]['huella_decisiones']
            from evaluacion.ocultos import comprobar_catalogo, evaluar_programacion
            from evalua import Demo
            catalogo, _ = comprobar_catalogo()
            guardar(salida / 'programacion_casos_ocultos.json', catalogo)
            # Guion explícito para validar el protocolo, no evidencia de inteligencia.
            def respuesta(letra):
                return dict(respuesta=letra, evidencias=['E1'], recuerdos=[], acciones=[], motivo='Guion de prueba')
            guion = {cid: {'solo': [respuesta('A')] * 3,
                           'equipo': [respuesta('A'), respuesta('A'), respuesta('A' if cid == 'PR02' else 'B')]}
                     for cid in ('PR01', 'PR02', 'PR03')}
            prog = evaluar_programacion(Demo(guion), salida / 'programacion_simulada')
            guardar(salida / 'guion_programacion.json', guion)
            preservado = huellas_v2f == {p.relative_to(fuente).as_posix(): sha(p)
                                       for p in fuente.rglob('*') if p.is_file()}
            integridad()
            pendientes = [
                {'prueba': 'Qwen real solo/equipo con y sin complementos', 'estado': 'OMITIDA', 'motivo': 'Sin modelo autorizado/conectado'},
                {'prueba': 'Termux/Android real', 'estado': 'OMITIDA', 'motivo': 'Entorno Linux; portabilidad no comprobada en dispositivo'},
                {'prueba': 'Generación libre de código', 'estado': 'OMITIDA', 'motivo': 'Requiere aislamiento y autorización; solo catálogo fijo'},
            ]
            codigo = 0 if (res.wasSuccessful() and not res.skipped and old.returncode == 0 and repite and preservado
                            and prog['estado'] == 'COMPLETA') else 1
            resumen = {'estado': 'COMPLETA_COMPONENTES' if codigo == 0 else 'FALLIDA', 'codigo_salida': codigo,
                       'unitarias': unitarias, 'evaluador_anterior_codigo': old.returncode, 'repeticion_identica': repite,
                       'v2f_extraida_intacta': preservado, 'memoria': comparaciones[0]['memoria'],
                       'herramientas': comparaciones[0]['herramientas'], 'programacion_simulada': prog['resumen'],
                       'pendientes': pendientes, 'estable': False}
            guardar(salida / 'resumen.json', resumen)
            print(json.dumps(resumen, ensure_ascii=False, indent=2), file=out)
            print('Registros completos:', salida.resolve(), file=out)
            print('=== FIN COMPLEMENTOS: ' + resumen['estado'] + ' ===', file=out)
            return codigo
        except Exception:
            traceback.print_exc(file=out)
            guardar(salida / 'inconclusa.json', {'estado': 'INCONCLUSA', 'codigo_salida': 2})
            print('=== FIN COMPLEMENTOS: INCONCLUSA ===', file=out)
            return 2


if __name__ == '__main__':
    sys.exit(main())
