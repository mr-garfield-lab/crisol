"""V2-E: Modo B (ejecución REAL aislada) — DESHABILITADO.

Antes de ejecutar código generado hay que DEMOSTRAR un aislamiento que limite todo esto:
"""
from __future__ import annotations

from . import config
from .ejecutor import EjecutorBase, Resultado

REQUISITOS = ("sistema_de_archivos", "red", "procesos", "cpu_memoria", "duracion",
              "archivos_personales", "instalaciones_con_permiso")


class Proveedor:
    nombre = "base"

    def autoverificar(self) -> dict:
        """{requisito: True (demostrado) | False (no se cumple) | None (no comprobable)}."""
        return {r: None for r in REQUISITOS}

    def disponible(self):
        v = self.autoverificar()
        faltan = [r for r in REQUISITOS if v.get(r) is not True]
        return (not faltan), faltan


class SinAislamiento(Proveedor):
    """Android/Termux sin root: no hay namespaces, cgroups ni seccomp configurables por el
    usuario; proot no es una barrera de seguridad. Una carpeta NO es un sandbox."""
    nombre = "ninguno"

    def autoverificar(self):
        return {r: False for r in REQUISITOS}


class MaquinaVirtualWindows(Proveedor):
    """Previsto para Windows 11 (Windows Sandbox o VM sin red, carpeta de entrada de solo lectura,
    carpeta de salida, límites de CPU/RAM/tiempo, destrucción tras cada ejecución). NO implementado."""
    nombre = "vm_windows"


class EjecutorReal(EjecutorBase):
    """Nunca ejecuta en V2-E. Tres barreras: config.MODO_B_HABILITADO, la autoverificación del
    proveedor y la ausencia deliberada de implementación de la ejecución."""
    nombre = "real_aislado"
    simulado = False

    def __init__(self, proveedor: Proveedor):
        self.proveedor = proveedor
        self.aislamiento = proveedor.nombre

    def _ejecutar(self, espacio, herramienta, politica):
        if not config.MODO_B_HABILITADO:
            return Resultado("no_disponible", False, salida="Modo B deshabilitado (config.MODO_B_HABILITADO)")
        ok, faltan = self.proveedor.disponible()
        if not ok:
            return Resultado("no_disponible", False,
                             salida="aislamiento no demostrado: " + ", ".join(faltan))
        return Resultado("no_disponible", False,
                         salida="ejecución real no implementada en V2-E (pendiente para Windows 11)")
