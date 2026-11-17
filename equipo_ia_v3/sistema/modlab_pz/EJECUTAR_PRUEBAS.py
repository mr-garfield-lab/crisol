#!/usr/bin/env python3
"""Ejecuta solo tests propios, no mods descargados."""
import subprocess,sys
from pathlib import Path
p=Path(__file__).resolve().parent
print('=== INICIO PZ MODLAB PRUEBAS PROPIAS ===',flush=True)
r=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s',str(p),'-p','test_*.py','-v'],cwd=p,check=False)
print('=== FIN PZ MODLAB: '+('OK' if r.returncode==0 else 'ERROR')+' ===',flush=True)
raise SystemExit(r.returncode)
