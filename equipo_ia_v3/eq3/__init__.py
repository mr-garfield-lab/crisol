"""Equipo IA V3: capacidades nuevas construidas SOBRE Equipo IA V2-F.1 (`sistema/src/eq2`), sin modificarlo.

`sistema/` se conserva idéntico a la base auditada en la Etapa 0, y la puerta de regresión (`v3/linea_base.py`)
lo mide. eq3 usa eq2 como biblioteca (por ejemplo, las tarjetas de rol) y lee lo que eq2 escribe en su
laboratorio.
"""
import sys
from pathlib import Path

VERSION = "v3.1-f0.5"                               # V3.1 F0.5: portabilidad (eq3/plataforma.py)
RAIZ = Path(__file__).resolve().parents[1]          # equipo_ia_v3/
SISTEMA_SRC = RAIZ / "sistema" / "src"
if str(SISTEMA_SRC) not in sys.path:
    sys.path.append(str(SISTEMA_SRC))               # al final: eq2 nunca tapa módulos de la biblioteca estándar
