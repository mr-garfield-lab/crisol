"""Presupuesto de contexto: reserva generación, acota bloques y RECHAZA lo que no cabe."""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field

from . import config, sanea


class ContextoExcedido(Exception):
    """La parte fija del prompt no cabe en el contexto disponible."""


def estimar_tokens(texto: str) -> int:
    """Estimación conservadora (len/3). NO es una medida; V2 la contrastará."""
    return int(math.ceil(len(texto) / config.CHARS_POR_TOKEN))


def _truncar(texto: str, n: int) -> str:
    if n <= 0:
        return ""
    return texto if len(texto) <= n else texto[: max(0, n - 1)].rstrip() + "…"


@dataclass(frozen=True)
class Bloque:
    nombre: str           # etiqueta válida para sanea.envolver (a-z0-9_)
    cuerpo: str           # texto NO confiable; se sanea y se envuelve aquí
    prioridad: int        # menor = más importante
    cap_chars: int
    codigo: bool = False  # V2-F.1: True = conserva la indentación (sanea.limpiar_codigo); por defecto, como antes


@dataclass
class Prompt:
    sistema: str
    usuario: str
    tokens_est: int
    max_gen: int
    omitidos: list = field(default_factory=list)
    recortados: list = field(default_factory=list)
    compresion: dict = field(default_factory=dict)   # V2-D: informe de compresión por bloque

    def mensajes(self):
        return [{"role": "system", "content": self.sistema},
                {"role": "user", "content": self.usuario}]

    def sha256(self) -> str:
        h = hashlib.sha256()
        h.update(self.sistema.encode("utf-8"))
        h.update(b"\x00")
        h.update(self.usuario.encode("utf-8"))
        return h.hexdigest()


MIN_BLOQUE_UTIL_CHARS = 60


def _render(nombre: str, cuerpo: str, codigo: bool = False) -> str:
    return (sanea.envolver_codigo if codigo else sanea.envolver)(nombre, cuerpo, 10 ** 6)   # V2-F.1: codigo


def construir(sistema: str, usuario_fijo: str, bloques, max_gen: int,
              ctx: int | None = None, sufijo: str = "") -> Prompt:
    """Construye el prompt. `bloques` es una lista en ORDEN DE RENDERIZADO.

    Se añaden por prioridad; cada cuerpo se sanea, se acota a su cap y a lo que
    quede, y se envuelve DESPUÉS de truncar (el delimitador de cierre nunca se
    pierde). Lanza ContextoExcedido si sistema + parte fija + generación no
    caben. Garantía: tokens_est + max_gen + MARGEN_CTX <= ctx (estimado).
    """
    ctx = config.CTX if ctx is None else ctx      # V2-D: se lee al llamar (--ctx en tiempo de ejecución)
    sobre = 2 * config.TOKENS_POR_MENSAJE
    # V2-E: `sufijo` va DESPUÉS de los bloques (p. ej. la identidad del votante), para que los
    # prompts de los tres votos compartan el prefijo y llama-server reutilice la caché.
    fijo = estimar_tokens(sistema) + estimar_tokens(usuario_fijo) + sobre + \
        (estimar_tokens(sufijo) + 1 if sufijo else 0)
    libre = ctx - config.MARGEN_CTX - max_gen - fijo
    if libre < 0:
        raise ContextoExcedido(
            f"fijo={fijo} + gen={max_gen} + margen={config.MARGEN_CTX} > ctx={ctx}")

    elegidos = {}
    omitidos, recortados = [], []
    for idx, b in sorted(enumerate(bloques), key=lambda p: (p[1].prioridad, p[0])):
        limpio = (sanea.limpiar_codigo if b.codigo else sanea.limpiar)(b.cuerpo, 10 ** 6)   # V2-F.1: codigo
        cuerpo = _truncar(limpio, b.cap_chars)
        coste = estimar_tokens(_render(b.nombre, cuerpo, b.codigo)) + 1
        if coste > libre:
            sobrecarga = len(_render(b.nombre, "", b.codigo))
            cuerpo = _truncar(limpio, (libre - 1) * config.CHARS_POR_TOKEN - sobrecarga)
            coste = estimar_tokens(_render(b.nombre, cuerpo, b.codigo)) + 1
        if len(cuerpo) < len(limpio):
            recortados.append(b.nombre)
        if not cuerpo or coste > libre or (
                len(cuerpo) < MIN_BLOQUE_UTIL_CHARS and len(limpio) >= MIN_BLOQUE_UTIL_CHARS):
            omitidos.append(b.nombre)
            if b.nombre in recortados:
                recortados.remove(b.nombre)
            continue
        elegidos[idx] = _render(b.nombre, cuerpo, b.codigo)
        libre -= coste

    partes = [usuario_fijo] + [elegidos[i] for i in sorted(elegidos)] + [sufijo]
    usuario = "\n\n".join(p for p in partes if p)
    tokens = estimar_tokens(sistema) + estimar_tokens(usuario) + sobre
    if tokens + max_gen + config.MARGEN_CTX > ctx:   # defensa final
        raise ContextoExcedido(f"tokens_est={tokens} no cabe tras ensamblar")
    return Prompt(sistema, usuario, tokens, max_gen, omitidos, recortados)
