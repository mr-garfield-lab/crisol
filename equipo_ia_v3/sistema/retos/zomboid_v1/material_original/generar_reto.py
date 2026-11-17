#!/usr/bin/env python3
import argparse,random,json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--seed',type=int,default=42);a=p.parse_args()
r=random.Random(a.seed)
cases=[('Fuentes y texturas','01_fuentes.txt'),('Plantillas y piezas','02_plantillas.txt'),('Carga visual Viewpoint','03_viewpoint.txt'),('Inicio y configuración','04_inicio.txt')]
r.shuffle(cases)
modifiers=['Distinguir error funcional de problema de FPS','Priorizar 3 comprobaciones sin alterar el juego','Señalar hipótesis alternativas','Diseñar un experimento A/B controlado','Definir evidencia que refutaría tu hipótesis']
for n,(title,file) in enumerate(cases[:3],1):
 print(json.dumps({'caso':n,'semilla':a.seed,'titulo':title,'evidencia':'evidencias/'+file,'reto':r.choice(modifiers),'exigir_citas':True,'ejecucion_permitida':False},ensure_ascii=False))
