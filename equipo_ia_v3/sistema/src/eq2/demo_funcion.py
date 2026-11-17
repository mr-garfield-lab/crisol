"""V2-F.1: DEMOSTRACIÓN SIMULADA de la función supervisada (sin Qwen).

Un backend de GUION (`BackendGuionFuncion`) recibe los prompts REALES que arma AgentesFuncionLLM (con el presupuesto de
contexto de verdad) y responde con textos fijos que imitan el formato pedido. Todo lo demás es real: análisis estático
del controlador, decisiones por evidencia, versiones, pruebas pendientes (sin ejecutar), memoria e informe. El informe
lo declara SIMULADO. Para la demostración con Qwen real: `equipo.py tarea importar ejemplos/tarea_funcion_demo.json`
y `equipo.py tarea ejecutar LAB-<n>` en el S23 (ver LEEME_V2F1.md).

Escenarios:
  corregible         mediana(): v1 con dos errores de lógica y una afirmación sin evidencia; A2 y A3 los detectan con
                     evidencia (A3 descarta una mejora de A2 y propone un caso que no encaja con la firma); v2 tiene un
                     error de sintaxis (el controlador replanifica: A2 y A3 no se consultan); v3 se acepta sin ejecución.
  falta_informacion  la tarea no dice qué redondeo usar: A1 pregunta (FALTA) y la tarea se detiene sin programar.
  sin_progreso       A1 devuelve el mismo código tras la revisión: sin progreso, escalada al usuario.
"""
from __future__ import annotations

from . import config, contexto
from .funcion_supervisada import INSTR_FS
from .inferencia import BackendBase, Respuesta

_V1 = """ARCHIVO: solucion.py
```python
def mediana(valores):
    valores.sort()
    n = len(valores)
    return valores[n // 2]
```
Esta versión funciona correctamente.
FIN"""
_V2_SINTAXIS = """ARCHIVO: solucion.py
```python
def mediana(valores)
    if not valores:
        raise ValueError("lista vacía")
    orden = sorted(valores)
    n = len(orden)
    medio = n // 2
    if n % 2 == 0:
        return (orden[medio - 1] + orden[medio]) / 2
    return orden[medio]
```
CAMBIOS: compruebo la lista vacía, uso sorted() para no modificar la entrada y promedio los dos centrales
FIN"""
_V3 = """ARCHIVO: solucion.py
```python
def mediana(valores):
    if not valores:
        raise ValueError("lista vacía")
    orden = sorted(valores)
    n = len(orden)
    medio = n // 2
    if n % 2 == 0:
        return (orden[medio - 1] + orden[medio]) / 2
    return orden[medio]
```
CAMBIOS: añadí los dos puntos que faltaban en la línea 1
REBATIDA: A3r1-3 | la tarea pide una función de un solo argumento (la lista); el segundo argumento no existe
FIN"""
_A2_R1 = """MEJORA: M1 | alta | con un número par de elementos debe devolver la media de los dos centrales | EVIDENCIA: línea 4, caso U1
MEJORA: M2 | alta | no debe modificar la lista de entrada: usa sorted(valores) | EVIDENCIA: línea 2
MEJORA: M3 | baja | añadir una docstring | EVIDENCIA: EV6
VEREDICTO: corregir"""
_A3_R1 = """CASO: mediana([5]) == 5
CASO: mediana([1, 2]) == 1.5
CASO: mediana([1, 2], 3) == 2
PROBLEMA: P1 | con la lista vacía lanza IndexError y no ValueError | EVIDENCIA: caso U2, línea 4
PROBLEMA: P2 | el código es lento | EVIDENCIA: rendimiento
SOBRE: M1 | confirma | EVIDENCIA: caso A3r1-2
SOBRE: M3 | rechaza | EVIDENCIA: EV6 (cuatro líneas no necesitan documentación para cumplir la tarea)
EVALUACION: insuficiente | sin ejecutar no se puede comprobar ningún caso"""
_A2_R2 = """RESUELTA: M1
RESUELTA: M2
MEJORA: M4 | baja | podría documentar en una docstring que lanza ValueError | EVIDENCIA: línea 3
VEREDICTO: aceptable"""
_A3_R2 = """CASO: mediana([7, 7, 7]) == 7
SOBRE: M4 | confirma | EVIDENCIA: línea 3
EVALUACION: insuficiente | la evidencia es estática; faltan por ejecutar las pruebas pendientes"""

ESCENARIOS = {
    "corregible": {"tarea": "tarea_funcion_demo.json",
                   "guion": {"fs_generar": [_V1], "fs_revisar": [_A2_R1, _A2_R2], "fs_casos": [_A3_R1, _A3_R2],
                             "fs_corregir": [_V2_SINTAXIS, _V3]},
                   "esperado": "aceptada_sin_ejecucion"},
    "falta_informacion": {"tarea": "tarea_funcion_falta_info.json",
                          "guion": {"fs_generar": ["FALTA: ¿qué normativa de redondeo usa la tienda (al céntimo, a "
                                                   "múltiplos de 0,05, siempre hacia arriba)?\nFIN"]},
                          "esperado": "informacion_insuficiente"},
    "sin_progreso": {"tarea": "tarea_funcion_demo.json",
                     "guion": {"fs_generar": [_V1], "fs_revisar": [_A2_R1], "fs_casos": [_A3_R1],
                               "fs_corregir": [_V1.replace("Esta versión funciona correctamente.",
                                                           "CAMBIOS: revisado")]},
                     "esperado": "escalada_al_usuario"},
}


def paso_de(mensajes) -> str | None:
    usuario = mensajes[-1]["content"] if mensajes else ""
    for paso, instr in INSTR_FS.items():
        if usuario.startswith(instr[:60]):
            return paso
    return None


class BackendGuionFuncion(BackendBase):
    """Backend SIMULADO: responde por paso con la lista del guion (repite la última si se acaba). Tokens ESTIMADOS."""
    etiqueta = "SIMULADO_GUION"
    simulado = True

    def __init__(self, guion: dict):
        self.guion = {k: list(v) for k, v in guion.items()}
        self.usadas = {}
        self.peticiones = []

    def completar(self, mensajes, max_tokens, plazo_s):
        paso = paso_de(mensajes)
        lista = self.guion.get(paso) or [""]
        i = self.usadas.get(paso, 0)
        self.usadas[paso] = i + 1
        texto = lista[min(i, len(lista) - 1)]
        tp = sum(contexto.estimar_tokens(m["content"]) for m in mensajes) + 2 * config.TOKENS_POR_MENSAJE
        self.peticiones.append({"paso": paso, "max_tokens": max_tokens, "tokens_prompt_est": tp})
        return Respuesta(texto=texto, tokens_prompt=tp, tokens_gen=min(max_tokens, contexto.estimar_tokens(texto)),
                         finish_reason="stop")


def ejecutar(ts, raiz_proyecto, escenario="corregible", autorizo_pruebas=False) -> dict:
    """Importa la tarea de ejemplo del escenario (nueva LAB-NNN; nunca sobrescribe) y la ejecuta con el guion."""
    from . import funcion_supervisada
    if escenario not in ESCENARIOS:
        raise ValueError(f"escenario desconocido: {escenario} (hay: {', '.join(ESCENARIOS)})")
    esc = ESCENARIOS[escenario]
    t = ts.importar(raiz_proyecto / "ejemplos" / esc["tarea"])
    be = BackendGuionFuncion(esc["guion"])
    ag = funcion_supervisada.AgentesFuncionLLM(be)
    r = ts.ejecutar(t["id"], ag, backend=be, autorizo_pruebas=autorizo_pruebas)
    return dict(r, escenario=escenario, esperado=esc["esperado"], coincide=r.get("resultado") == esc["esperado"])
