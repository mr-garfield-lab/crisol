#!/usr/bin/env python3
"""Prepara un paquete de transferencia de solo lectura para Codex desde Termux."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import hashlib, json, os, sys

HOME = Path.home()
DOWNLOADS = HOME / 'storage' / 'downloads'
MOTOR = HOME / 'contexto_ligero_v32' / 'contexto_ligero_v32'
PROYECTO = Path('/data/data/com.termux/files/usr/tmp/equipo_f2/codigo_v2e7r3/equipo_f2_v2e7r3')
LAB = HOME / 'lab_ctx_r3_experimental'
DEST = DOWNLOADS / 'TRANSFERENCIA_CODEX_EQUIPO_IA_V33.zip'
ARCHIVOS = [
 'CONTEXTO_LIGERO_EQUIPO_IA_V3_2.zip',
 'AUDITORIA_EQUIPO_IA_V32.zip',
 'AUDITORIA_COMPLEMENTO_V32.zip',
 'LAB_REGRESION_CTX_V32.zip',
 'PAQUETE_CONTEXTO_V32.txt',
]
EXCLUDED_DIRS = {'.git','__pycache__','.venv','venv','node_modules','.pytest_cache','.mypy_cache','build','dist'}
ALLOWED_SUFFIXES = {'.py','.md','.txt','.toml','.json','.yaml','.yml','.ini','.cfg','.sh','.sql','.rst'}
MAX_FILE = 2 * 1024 * 1024
MAX_TOTAL = 40 * 1024 * 1024

INSTRUCCIONES = '''# Misión para Codex — Contexto Ligero V3.3

## Objetivo
Entregar una V3.3 real, ejecutable y comprobada de Contexto Ligero, partiendo de V3.2, para que Claude pueda aprovecharla cuando vuelva a estar disponible. No detenerse en un informe: generar código, pruebas, ZIP autocontenido y guía de uso en Termux.

## Material
- `motor_v32/`: código del motor V3.2, fuente principal de desarrollo.
- `equipo_ia_referencia/`: código de Equipo IA V2-E.7-r3, referencia de integración.
- `laboratorio_ctx_experimental/`: experimento CTX, NO aprobado.
- `evidencias_previas/`: ZIP de auditoría y pruebas y paquete de contexto, si estaban disponibles.
- `MANIFIESTO.json`: inventario SHA256, ausencias y exclusiones.

## Prioridades
1. Indexación incremental SQLite, ranking AST, selección de dependencias y fragmentos bajo demanda.
2. Paquetes de contexto compactos con rutas, líneas y hashes; distinguir caracteres, estimación de tokens y tokens reales.
3. Comprobar si la modificación CTX es necesaria y correcta; realizar pruebas funcionales e integradas con backend simulado, sin llamadas a modelos reales.
4. Preparar `GUIA_PARA_CLAUDE.md` con instrucciones concretas para usar el motor desde el flujo de trabajo de Claude, sin afirmar integración automática no probada.
5. Comparar V3.2 y V3.3 en precisión de selección, tiempo, RAM y tamaño de contexto.

## Reglas obligatorias
- NO sobrescribir ni modificar originales; trabajar en directorio V3.3 nuevo.
- NO borrar archivos, bases de datos o versiones anteriores.
- NO instalar paquetes ni usar servicios externos, APIs o créditos sin autorización.
- NO modificar políticas de permisos ni reducir protecciones de Equipo IA.
- NO tratar pruebas simuladas como integración real; reportar lo que no pueda ejecutarse en tu entorno.
- Mantener un comando integral de pruebas con resultados y evidencias persistentes.
- Antes de modificar el código, inspeccionar brevemente el material y anunciar el plan. Después implementar V3.3 sin esperar nuevas instrucciones para cada paso de bajo riesgo.

## Entregables
- `CONTEXTO_LIGERO_V33.zip` autocontenido (dependencias excepcionales documentadas).
- Código completo, pruebas, comando único y resultados.
- `GUIA_PARA_CLAUDE.md`.
- Informe antes/después y limitaciones.
- Instrucciones de instalación y validación en Samsung/Termux.
'''


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def main():
    if not MOTOR.is_dir():
        sys.exit('ERROR: falta motor V3.2 en ' + str(MOTOR))
    if not PROYECTO.is_dir():
        sys.exit('ERROR: falta proyecto de referencia en ' + str(PROYECTO))
    if not DOWNLOADS.is_dir():
        sys.exit('ERROR: falta acceso a Descargas; ejecutar termux-setup-storage')
    if DEST.exists():
        sys.exit('SEGURIDAD: el ZIP ya existe; no se sobrescribe: ' + str(DEST))

    manifest = {'motor':str(MOTOR),'proyecto':str(PROYECTO),'laboratorio':str(LAB),
                'archivos':{},'faltantes':[],'excluidos':[]}
    total = 0
    def add(z, arc, data):
        nonlocal total
        if total + len(data) > MAX_TOTAL:
            manifest['excluidos'].append({'ruta':arc,'motivo':'limite global 40 MiB'})
            return
        z.writestr(arc,data)
        manifest['archivos'][arc]={'bytes':len(data),'sha256':sha256(data)}
        total += len(data)

    def add_tree(z, base, prefix):
        if not base.is_dir():
            manifest['faltantes'].append(str(base)); return
        for path in sorted(base.rglob('*')):
            if not path.is_file() or any(part in EXCLUDED_DIRS for part in path.relative_to(base).parts):
                continue
            rel = path.relative_to(base)
            arc = prefix + '/' + rel.as_posix()
            if path.suffix.lower() not in ALLOWED_SUFFIXES or path.stat().st_size > MAX_FILE:
                manifest['excluidos'].append({'ruta':arc,'motivo':'tipo o tamaño excluido'}); continue
            try:
                add(z,arc,path.read_bytes())
            except OSError as e:
                manifest['excluidos'].append({'ruta':arc,'motivo':str(e)})

    with ZipFile(DEST,'x',compression=ZIP_DEFLATED,compresslevel=6) as z:
        add_tree(z,MOTOR,'motor_v32')
        add_tree(z,PROYECTO,'equipo_ia_referencia')
        add_tree(z,LAB,'laboratorio_ctx_experimental')
        for name in ARCHIVOS:
            p = DOWNLOADS / name
            if p.is_file():
                if p.stat().st_size <= MAX_FILE * 10:
                    add(z,'evidencias_previas/'+name,p.read_bytes())
                else:
                    manifest['excluidos'].append({'ruta':name,'motivo':'ZIP demasiado grande'})
            else:
                manifest['faltantes'].append(name)
        add(z,'INSTRUCCIONES_PARA_CODEX.md',INSTRUCCIONES.encode('utf-8'))
        z.writestr('MANIFIESTO.json',json.dumps(manifest,indent=2,ensure_ascii=False).encode('utf-8'))
    with ZipFile(DEST) as z:
        corrupto = z.testzip()
    print('=== PAQUETE PARA CODEX ===')
    print('Archivo:',DEST)
    print('Tamaño:',DEST.stat().st_size,'bytes')
    print('Archivos:',len(manifest['archivos']))
    print('Faltantes:',len(manifest['faltantes']))
    for f in manifest['faltantes']:
        print('  FALTA:',f)
    print('Excluidos:',len(manifest['excluidos']))
    print('Integridad ZIP:', 'OK' if corrupto is None else 'ERROR '+corrupto)
    print('SHA256 ZIP:',sha256(DEST.read_bytes()))
    print('=== FIN ===')

if __name__=='__main__':
    main()
