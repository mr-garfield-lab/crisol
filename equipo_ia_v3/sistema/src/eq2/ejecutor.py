"""V2-D: interfaz del EJECUTOR de pruebas. En esta versión NO existe ejecución real.

Implementaciones incluidas:
  * EjecutorNoDisponible: siempre responde 'no_disponible'. Es el ejecutor por defecto.
  * EjecutorSimulado: resultados GUIONIZADOS para probar el ciclo; NUNCA ejecuta código.

Garantías estructurales: este módulo no importa subprocess ni os.system ni exec (el validador
estático lo prohíbe fuera de servidor.py), y solo escribe a través de rutas.Laboratorio.

Un ejecutor REAL futuro deberá cumplir la Politica y además disponer de AISLAMIENTO REAL
(contenedor, máquina virtual, Windows Sandbox...). Un directorio NO es un sandbox: en Android/
Termux sin root no hay aislamiento adecuado, por eso aquí queda deshabilitado.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

from . import archivos, config, rutas, sanea

ESTADOS = ("ok", "fallos", "error", "rechazado", "no_disponible", "detenido")
TIPOS = ("simulado", "estatico", "real", "ninguno")


@dataclass(frozen=True)
class Politica:
    herramientas: tuple = config.EJECUTOR_HERRAMIENTAS
    seg_por_ejecucion: float = config.EJECUTOR_SEG_POR_EJECUCION
    mem_mb: int = config.EJECUTOR_MEM_MB
    max_archivos: int = config.EJECUTOR_MAX_ARCHIVOS
    max_bytes_archivo: int = config.EJECUTOR_MAX_BYTES_ARCHIVO
    extensiones: tuple = config.EJECUTOR_EXTENSIONES
    red: bool = False                 # siempre False: sin red
    privilegios: bool = False         # siempre False: sin permisos administrativos
    aislamiento_requerido: bool = True

    def problemas(self) -> list:
        p = []
        if self.red:
            p.append("la politica no puede permitir red")
        if self.privilegios:
            p.append("la politica no puede pedir privilegios")
        if not self.aislamiento_requerido:
            p.append("el aislamiento real es obligatorio")
        if not set(self.herramientas) <= set(config.EJECUTOR_HERRAMIENTAS):
            p.append("herramienta fuera de la lista permitida")
        if self.max_archivos > config.EJECUTOR_MAX_ARCHIVOS or \
                self.max_bytes_archivo > config.EJECUTOR_MAX_BYTES_ARCHIVO:
            p.append("limites por encima del maximo")
        return p


@dataclass
class Resultado:
    estado: str
    simulado: bool
    pruebas_total: int = 0
    pruebas_fallidas: int = 0
    salida: str = ""
    duracion_s: float = 0.0
    detalle: dict = field(default_factory=dict)
    # V2-E: qué clase de comprobación es. Una simulación NUNCA es 'real'.
    tipo: str = ""

    def __post_init__(self):
        if self.estado not in ESTADOS:
            raise ValueError("estado de ejecución inválido")
        if not self.tipo:
            self.tipo = "simulado" if self.simulado else "ninguno"
        if self.tipo not in TIPOS:
            raise ValueError("tipo de comprobación inválido")
        if self.simulado and self.tipo != "simulado":
            raise ValueError("un resultado simulado no puede declararse de otro tipo")
        self.salida = sanea.limpiar(self.salida, 2000)

    def a_dict(self):
        return asdict(self)


class RegistroAcciones:
    """Registro completo (JSONL, solo anexar) dentro del laboratorio."""

    def __init__(self, lab: rutas.Laboratorio, partes, reloj_iso):
        self.lab, self.partes, self.ahora = lab, tuple(partes), reloj_iso
        self.n = 0

    def anotar(self, tipo, **detalle):
        self.n += 1
        linea = json.dumps({"n": self.n, "ts": self.ahora(), "tipo": tipo, **detalle},
                           ensure_ascii=False, default=str)
        self.lab.anexar(self.partes, linea + "\n")


class EspacioTrabajo:
    """Directorio de trabajo EXPLÍCITO dentro del laboratorio: runs/<run>/ciclo/iter_<n>/.
    Las rutas se validan con rutas.Laboratorio (sin '..', sin enlaces, sin salir de la base)."""

    def __init__(self, lab: rutas.Laboratorio, run_id: str, iteracion: int):
        if not isinstance(iteracion, int) or iteracion < 1:
            raise ValueError("iteración inválida")
        self.lab = lab
        self.partes = ("runs", run_id, "ciclo", f"iter_{iteracion}")
        lab.crear_dir(*self.partes)
        self.archivos = {}

    def escribir(self, nombre: str, contenido: str, politica: Politica):
        if not archivos.nombre_valido(nombre):
            raise rutas.RutaInsegura(f"nombre de archivo no permitido: {nombre[:40]!r}")
        if len(self.archivos) >= politica.max_archivos:
            raise ValueError("demasiados archivos")
        if len(contenido.encode("utf-8")) > politica.max_bytes_archivo:
            raise ValueError("archivo demasiado grande")
        self.lab.crear_exclusivo(self.partes + (nombre,), contenido)   # nunca sobrescribe
        self.archivos[nombre] = contenido

    def ruta(self):
        return self.lab.ruta(*self.partes)


class EjecutorBase:
    nombre = "base"
    simulado = True
    aislamiento = "ninguno"

    def ejecutar(self, espacio: EspacioTrabajo, herramienta: str, politica: Politica) -> Resultado:
        pr = politica.problemas()
        if pr:
            return Resultado("rechazado", self.simulado, salida="; ".join(pr))
        if herramienta not in politica.herramientas:
            return Resultado("rechazado", self.simulado, salida=f"herramienta no permitida: {herramienta}")
        return self._ejecutar(espacio, herramienta, politica)

    def _ejecutar(self, espacio, herramienta, politica) -> Resultado:
        raise NotImplementedError


class EjecutorNoDisponible(EjecutorBase):
    """Por defecto: no hay aislamiento real disponible, así que no se ejecuta NADA."""
    nombre = "no_disponible"
    simulado = False

    def _ejecutar(self, espacio, herramienta, politica):
        return Resultado("no_disponible", False,
                         salida="ejecución deshabilitada: no hay aislamiento real en este entorno")


class EjecutorSimulado(EjecutorBase):
    """Resultados guionizados: guion(iteracion, archivos:{nombre: contenido}) -> dict de
    Resultado (sin 'simulado'). NO ejecuta, NO importa ni evalúa el contenido."""
    nombre = "simulado"
    simulado = True
    aislamiento = "simulado"

    def __init__(self, guion):
        self.guion = guion
        self.llamadas = 0

    def _ejecutar(self, espacio, herramienta, politica):
        self.llamadas += 1
        d = dict(self.guion(self.llamadas, dict(espacio.archivos)))
        d.pop("simulado", None)
        return Resultado(simulado=True, **d)
