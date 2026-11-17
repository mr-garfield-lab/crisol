"""Flujo sintetico aislado: las cinco funciones son necesarias para completar la operacion."""

def cargar_reembolso(datos):
    return datos + [0]

def validar_reembolso(datos):
    return datos + [1]

def calcular_reembolso(datos):
    return datos + [2]

def registrar_reembolso(datos):
    return datos + [3]

def tramitar_reembolso(datos):
    datos = cargar_reembolso(datos)
    datos = validar_reembolso(datos)
    datos = calcular_reembolso(datos)
    datos = registrar_reembolso(datos)
    return datos

def reembolso_estadisticas_historicas(datos):
    return len(datos)

def reembolso_mostrar_ayuda():
    return "solo interfaz de ayuda"

def reembolso_exportar_demostracion(datos):
    return str(datos)
