"""Demostración optativa de símbolo largo sin ejecutar código de Equipo IA."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from contexto_core.evidence import build_bundle
from contexto_core.index import connect, scan
from contexto_core.tokens import TokenCounter
from bundle_full_worker_v35 import source_coverage
from worker import corpus_hashes


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--tokenizer-json',type=Path)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    corpus=ROOT/'referencia_original/equipo_ia_referencia';before=corpus_hashes(corpus)
    db=connect(args.output/'index.sqlite3');counter=TokenCounter(args.tokenizer_json)
    try:
        scan(corpus,db)
        result=build_bundle(corpus,db,'prioridad puntuar planificar dependencias',budget=64000,limit=12,
                            required=[('src/eq2/prioridad.py','planificar')],max_evidence=100,
                            include_tests=False,max_symbol_lines=1000)
        coverage=source_coverage(corpus,db,result)
        long=[{'path':s['path'],'symbol':s['symbol'],'lines':s['end']-s['start']+1}
              for s in result['selected'] if s['end']-s['start']+1>200]
        if not coverage['ok'] or not long:
            raise ValueError('Demostración de símbolo largo incompleta')
        (args.output/'bundle.txt').write_text(result['text'])
        info={'status':'PASS','explicit_max_symbol_lines':1000,'budget_estimated':64000,
              'selected_symbols':len(result['selected']),'unique_source_lines':result['unique_source_lines'],
              'long_symbols':long,'source_coverage':coverage,'metrics':counter.metrics(result['text']),
              'corpus_unchanged':before==corpus_hashes(corpus),
              'scope':'Más de 200 líneas requiere la opción explícita; no acredita dependencias dinámicas ni ventana del modelo.'}
        (args.output/'metrics.json').write_text(json.dumps(info,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps(info,ensure_ascii=False))
        return 0 if info['corpus_unchanged'] else 1
    finally: db.close()


if __name__=='__main__':
    raise SystemExit(main())
