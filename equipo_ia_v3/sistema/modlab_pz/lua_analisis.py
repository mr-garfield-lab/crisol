"""Análisis de Lua sin ejecución. No certifica compatibilidad PZ."""
import hashlib, re, shutil, subprocess
from pathlib import Path

def analizar_lua(datos: bytes, nombre: str = "script.lua") -> dict:
    texto=datos.decode("utf-8", errors="replace")
    eventos=sorted(set(re.findall(r"\bEvents\.([A-Za-z_][A-Za-z_0-9]*)\s*\.\s*(?:Add|Remove)\s*\(", texto)))
    llamadas=sorted(set(re.findall(r"\b(?:getPlayer|getSpecificPlayer|require|instanceof)\s*\(", texto)))
    riesgos=[]
    for patron, etiqueta in [(r"\bos\s*\.\s*execute\s*\(","os.execute"),(r"\bio\s*\.\s*popen\s*\(","io.popen"),(r"\bloadstring\s*\(","loadstring"),(r"\bpackage\s*\.\s*loadlib\s*\(","package.loadlib"),(r"\brequire\s*\(\s*['\"]socket", "socket")]:
        if re.search(patron,texto): riesgos.append(etiqueta)
    return {"nombre":nombre,"sha256":hashlib.sha256(datos).hexdigest(),"eventos":eventos,"llamadas":llamadas,"patrones_revision_manual":riesgos,"sintaxis":"no_comprobada","ejecutado":False,"advertencia":"Análisis de patrones, no ejecución de Lua ni certificación de compatibilidad"}

def comprobar_sintaxis_archivo(ruta: str) -> dict:
    """Usar luac -p SOLO con archivos propios/confiables. No ejecutar mods desconocidos."""
    exe=shutil.which("luac")
    if not exe:return {"estado":"no_disponible","motivo":"luac no instalado","ejecutado":False}
    p=Path(ruta)
    if not p.is_file() or p.suffix.lower()!='.lua':raise ValueError('Se requiere un archivo .lua')
    if p.stat().st_size>1024*1024:raise ValueError('Archivo demasiado grande')
    try:
        r=subprocess.run([exe,'-p',str(p)],capture_output=True,text=True,timeout=5,check=False)
        return {"estado":"sintaxis_valida" if r.returncode==0 else "sintaxis_invalida","salida":(r.stdout+r.stderr)[:4000],"codigo":r.returncode,"ejecutado":False,"advertencia":"luac comprueba sintaxis; no ejecuta mod ni valida APIs PZ"}
    except subprocess.TimeoutExpired:return {"estado":"tiempo_agotado","ejecutado":False}
