"""Interfaz de inferencia y backend SIMULADO.

V0-V1: NO hay cliente HTTP ni proceso hijo. BackendSimulado devuelve texto
guionizado; sirve solo para probar la lógica. Nada de lo que produce es una
medida del modelo real. El backend real (cliente a 127.0.0.1) se escribirá en
V2 copiando, no importando, los mecanismos revisados de prueba3.py.
"""
from __future__ import annotations

from dataclasses import dataclass


class ErrorInferencia(Exception):
    """Fallo de un backend. `fatal=True` => el servidor puede seguir ocupado o en mal
    estado (plazo agotado, parada, muerte del proceso...): la sesión debe terminar."""

    def __init__(self, motivo="error", fatal=False):
        super().__init__(motivo)
        self.motivo = str(motivo)
        self.fatal = bool(fatal)


# V2-E.5-r3: motivos de parada PEDIDA (STOP del usuario o señal) y forma exacta en que el backend los
# devuelve cuando la parada interrumpe una operación. Cualquier otro motivo es un fallo distinto.
MOTIVOS_PARADA = ("stop_usuario", "senal")
_PREFIJOS_PARADA = (("abortado_durante_carga:", "carga_servidor"), ("parada_antes_de_lanzar:", "antes_de_lanzar"))


def parada_de(motivo):
    """(motivo_de_parada, punto) si `motivo` es EXACTAMENTE la materialización de una parada pedida
    (petición HTTP interrumpida, carga del servidor abortada o parada antes de lanzarlo); si no, None.
    No reconoce por subcadenas: «servidor_muerto», «plazo_agotado», «http_500»... nunca son paradas."""
    m = str(motivo)
    if m in MOTIVOS_PARADA:
        return m, "peticion_http"
    for prefijo, punto in _PREFIJOS_PARADA:
        if m.startswith(prefijo) and m[len(prefijo):] in MOTIVOS_PARADA:
            return m[len(prefijo):], punto
    return None


@dataclass
class Respuesta:
    texto: str
    tokens_prompt: int | None = None
    tokens_gen: int | None = None
    cache_n: int | None = None
    ms_prompt: float | None = None
    ms_gen: float | None = None
    finish_reason: str | None = None


class BackendBase:
    etiqueta = "base"
    simulado = False

    # Ciclo de vida. Los backends simulados no hacen nada.
    def iniciar(self, ctx=None) -> None:
        """ctx = {"lab": Laboratorio, "run_id": str, "parar": callable -> motivo|None}."""

    def supervisar(self):
        """Devuelve un motivo de aborto (str) o None. Se llama entre llamadas."""
        return None

    def detener(self) -> dict:
        """Idempotente y sin lanzar. {"ok": bool, "limpio": bool, "problemas": [...]}."""
        return {"ok": True, "limpio": True, "problemas": []}

    def completar(self, mensajes, max_tokens: int, plazo_s: float) -> Respuesta:
        raise NotImplementedError


class BackendSimulado(BackendBase):
    """Backend de pruebas. `guion(llamada, fase_hint, mensajes, max_tokens)` -> str.

    Si no se da guion, responde con textos fijos y votos 'aprobar'.
    """
    etiqueta = "SIMULADO"
    simulado = True

    def __init__(self, guion=None):
        self.guion = guion
        self.llamadas = []      # lista de dicts para que los tests inspeccionen

    @staticmethod
    def _fase(mensajes) -> str:
        u = mensajes[-1]["content"]
        for clave, fase in (("Aclara tus objeciones", "aclaracion"),     # V2-E.5
                            ("Elige tu personalidad inicial", "personalidad"),   # V2-E.5-r2
                            ("Vota sobre", "voto"), ("Analiza la tarea", "analisis"),
                            ("Propón una solución", "propuesta"),
                            ("Revisa la propuesta", "revision"),
                            ("Responde a la revisión", "replica")):
            if clave in u:
                return fase
        return "desconocida"

    def completar(self, mensajes, max_tokens: int, plazo_s: float) -> Respuesta:
        fase = self._fase(mensajes)
        n = len(self.llamadas) + 1
        self.llamadas.append({"n": n, "fase": fase, "mensajes": mensajes,
                              "max_tokens": max_tokens, "plazo_s": plazo_s})
        if self.guion is not None:
            texto = self.guion(n, fase, mensajes, max_tokens)
            if isinstance(texto, Exception):
                raise texto
        elif fase == "voto":
            texto = "VOTO: aprobar\nRAZON: simulado"
        else:
            texto = f"[simulado] texto de {fase}"
        return Respuesta(texto=texto, tokens_prompt=None, tokens_gen=None,
                         finish_reason="stop")
