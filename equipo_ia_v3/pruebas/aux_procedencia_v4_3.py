"""Auxiliar de test_eq3_procedencia_v4_3.py (no es un módulo de pruebas: unittest no lo descubre).

Un backend SIMULADO de guion (sin procesos ni red) que responde según el agente («Eres A1/A2/A3») para recorrer el flujo
REAL de `EV.ejecutar_tarea` (S1, S1×3 y E3 de V2-F.1). Nada generado se ejecuta.
"""
import hashlib
from types import SimpleNamespace

from eq2 import inferencia

A1_T10 = "ARCHIVO: solucion.py\n\n```python\ndef respuesta():\n    return ['a', 'b', 'c']\n```\n\nFIN"
A2_OK = "VEREDICTO: aceptable"
A3_OK = "SIN PROBLEMAS\nFIN"


class Guion(inferencia.BackendBase):
    etiqueta, simulado = "GUION_V4_3", True

    def __init__(self, respuestas=None):
        self.respuestas = {"A1": A1_T10, "A2": A2_OK, "A3": A3_OK} | (respuestas or {})
        self.peticiones, self.mon, self.carga_s, self.estado, self.detencion = [], None, 0.0, "nuevo", None
        self.srv = SimpleNamespace(proc=None, pid=lambda: None)
        self.prompts, self.salidas = [], []

    def iniciar(self, ctx=None):
        self.estado = "listo"

    def detener(self):
        self.estado = "detenido"
        self.detencion = {"ok": True, "limpio": True, "problemas": []}
        return self.detencion

    def completar(self, mensajes, max_tokens, plazo_s):
        sis = str(mensajes[0].get("content", "")) if mensajes else ""
        agente = next((a for a in ("A1", "A2", "A3") if f"Eres {a}" in sis), "A1")
        r = self.respuestas[agente]
        texto = r(mensajes) if callable(r) else r
        self.prompts.append("\n".join(str(m.get("content", "")) for m in mensajes))
        self.salidas.append(texto)
        self.peticiones.append({"status": 200, "metricas": {"prompt_n": 10, "predicted_n": 5},
                                "sha256": hashlib.sha256(texto.encode()).hexdigest()})
        return inferencia.Respuesta(texto=texto, tokens_prompt=10, tokens_gen=5, finish_reason="stop")
