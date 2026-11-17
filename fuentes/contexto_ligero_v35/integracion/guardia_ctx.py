"""Guardia opt-in de tokens reportados; importar requiere eq2 en PYTHONPATH.

La comprobación posterior no evita una petición excesiva ya enviada. Rechaza
su respuesta y conserva el débito de llamadas/tokens que hizo Equipo IA.
"""
from eq2 import config
from eq2.orquestador import Orquestador


class OrquestadorConGuardiaCTX(Orquestador):
    """Misma ejecución de Equipo IA, con rechazo central de desbordes reportados."""

    def _invocar(self, tid, orden, fase, agente, mensajes, max_gen, tipo, tokens_est=None):
        resultado = super()._invocar(tid, orden, fase, agente, mensajes, max_gen,
                                    tipo, tokens_est)
        resp, fallo, fatal, ini, fin, pared = resultado
        if fallo is not None:
            return resultado
        real = getattr(resp, "tokens_prompt", None)
        if real is None:
            return resultado   # No inventar tokens reales si el backend no los informa.
        if type(real) is not int or real < 0:
            motivo = "tokens_prompt_invalidos"
            detalle = "tipo=" + type(real).__name__
        elif real + max_gen > config.CTX:
            motivo = "contexto_real_excedido"
            detalle = f"reportados={real} + reserva={max_gen} > ctx={config.CTX}"
            self.calibracion.append({"fase": fase, "agente": agente,
                                     "tokens_est": tokens_est, "tokens_real": real,
                                     "max_gen": max_gen, "origen": "reportado_por_backend",
                                     "simulado": bool(self.backend.simulado)})
        else:
            return resultado
        self._ev(motivo, detalle)
        if self.metricas:
            self.metricas[-1]["fallo"] = motivo
        # Fallo fatal: no reintentar/votar/continuar sobre una respuesta inválida.
        # _registrar_fallo guarda el motivo y aplica el cierre original del orquestador.
        return resp, motivo, motivo, ini, fin, pared
