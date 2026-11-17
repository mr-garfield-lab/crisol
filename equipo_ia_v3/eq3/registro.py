"""Equipo IA V3 · REGISTRO estructurado (JSON Lines), solo para añadir.

Una línea por evento: {"ts", "nivel", "componente", "evento", ...datos}. Solo se registran identificadores,
recuentos y motivos breves; nunca textos de los agentes, prompts ni secretos (esos se referencian por SHA-256 en
la traza).
"""
from __future__ import annotations

import json
from pathlib import Path

from .traza import ahora

NIVELES = ("debug", "info", "aviso", "error")


class Registro:
    def __init__(self, ruta: Path):
        self.ruta = Path(ruta)

    def evento(self, nivel: str, componente: str, evento: str, **datos) -> dict:
        if nivel not in NIVELES:
            raise ValueError(f"nivel desconocido: {nivel}")
        linea = {"ts": ahora(), "nivel": nivel, "componente": componente, "evento": evento, **datos}
        with self.ruta.open("a", encoding="utf-8") as f:
            f.write(json.dumps(linea, ensure_ascii=False, sort_keys=True) + "\n")
        return linea
