"""Pruebas sin gráficos para paquetes PZ: análisis estático y escenarios declarativos.
No ejecuta Lua, Java, mods ni comandos del paquete. NO certifica compatibilidad real.
"""
import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path

MAX_FILES=2000
MAX_TOTAL=60*1024*1024
MAX_ONE=5*1024*1024
EXT={'.lua','.txt','.json','.info','.md'}

def digest(data): return hashlib.sha256(data).hexdigest()

def inspect_zip(path):
    findings=[]; entries=[]; total=0
    with zipfile.ZipFile(path) as z:
        info=z.infolist()
        if len(info)>MAX_FILES: raise ValueError('Demasiados archivos')
        seen=set()
        for item in info:
            name=item.filename
            parts=Path(name.replace('\\','/')).parts
            if name.startswith(('/', '\\')) or '\\' in name or '..' in parts or ':' in name or not parts:
                findings.append({'tipo':'ruta_peligrosa','archivo':name}); continue
            if name in seen: findings.append({'tipo':'duplicado','archivo':name});continue
            seen.add(name)
            mode=(item.external_attr>>16)&0o170000
            if mode==0o120000:
                findings.append({'tipo':'enlace_simbolico','archivo':name});continue
            if item.is_dir(): continue
            total+=item.file_size
            if item.file_size>MAX_ONE or total>MAX_TOTAL: raise ValueError('Limite de tamaño excedido')
            suffix=Path(name).suffix.lower()
            if suffix not in EXT: continue
            data=z.read(item)
            entry={'ruta':name,'sha256':digest(data),'bytes':len(data)}
            if suffix in {'.lua','.txt','.info'}:
                txt=data.decode('utf-8',errors='replace')
                entry['eventos_lua']=sorted(set(re.findall(r'Events\.([A-Za-z_][A-Za-z_0-9]*)\s*\.\s*Add\s*\(',txt)))
                entry['referencias']=sorted(set(re.findall(r'\b(?:getPlayer|getSpecificPlayer|instanceof|require)\s*\(',txt)))
                if suffix=='.lua' and ('loadstring(' in txt or 'os.execute(' in txt):
                    findings.append({'tipo':'revision_manual','archivo':name,'detalle':'Llamada dinámica o de sistema detectada; no se ejecutó'})
            entries.append(entry)
    return {'formato':'pz-modlab-0.1','modo':'analisis_estatico_sin_ejecucion','archivo':Path(path).name,'sha256_zip':digest(Path(path).read_bytes()),'entradas':entries,'hallazgos':findings,'limites':['No se ejecuta Lua','No se emula el motor Java','No se valida compatibilidad con Build 42','No se miden FPS reales']}

def simulate(scenario):
    """Máquina de estados propia; no ejecuta código del mod ni replica PZ."""
    if not isinstance(scenario,dict): raise ValueError('Escenario inválido')
    actions=scenario.get('acciones',[])
    if not isinstance(actions,list) or len(actions)>1000: raise ValueError('Número de acciones inválido')
    inv={}; events=[]; results=[]
    for idx,a in enumerate(actions):
        if not isinstance(a,dict): raise ValueError('Acción inválida')
        op=a.get('accion'); item=a.get('objeto','')
        if op in ('agregar','consumir'):
            if not isinstance(item,str) or not item or len(item)>128: raise ValueError('Objeto inválido')
            n=a.get('cantidad',1)
            if type(n)!=int or not 1<=n<=10000: raise ValueError('Cantidad inválida')
            if op=='agregar': inv[item]=inv.get(item,0)+n;ok=True
            else:
                ok=inv.get(item,0)>=n
                if ok: inv[item]-=n
        elif op=='evento':
            if not isinstance(item,str) or len(item)>128: raise ValueError('Evento inválido')
            events.append(item);ok=True
        elif op=='comprobar':
            n=a.get('cantidad',0)
            if type(n)!=int or n<0: raise ValueError('Cantidad inválida')
            ok=inv.get(item,0)==n
        else: raise ValueError('Acción no admitida: '+str(op))
        results.append({'paso':idx+1,'accion':op,'ok':ok})
    return {'modo':'simulacion_declarativa_propia','pasos':results,'inventario_final':inv,'eventos':events,'todos_ok':all(x['ok'] for x in results),'advertencia':'No prueba que el mod funcione dentro de Project Zomboid'}

def main():
    p=argparse.ArgumentParser(description='Laboratorio PZ independiente (sin ejecutar mods)')
    p.add_argument('modo',choices=['inspeccionar','simular'])
    p.add_argument('archivo')
    p.add_argument('--salida',required=True,help='Directorio nuevo de resultados; no sobrescribe')
    a=p.parse_args(); dest=Path(a.salida)
    dest.mkdir(parents=True,exist_ok=False)
    try:
        if a.modo=='inspeccionar': result=inspect_zip(a.archivo)
        else: result=simulate(json.loads(Path(a.archivo).read_text(encoding='utf-8')))
        result['entrada_sha256']=digest(Path(a.archivo).read_bytes())
        data=json.dumps(result,ensure_ascii=False,indent=2).encode()
        (dest/'resultado.json').write_bytes(data)
        (dest/'MANIFIESTO_SHA256.txt').write_text(digest(data)+'  resultado.json\n',encoding='utf-8')
        print(json.dumps({'resultado':str(dest/'resultado.json'),'modo':result['modo']},ensure_ascii=False))
    except Exception:
        # Directorio y evidencia de error conservados, sin borrar nada
        import traceback
        (dest/'error.txt').write_text(traceback.format_exc(),encoding='utf-8')
        raise
if __name__=='__main__': main()
