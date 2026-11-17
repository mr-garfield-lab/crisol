"""Flujo sintetico aislado: las cinco funciones son necesarias para completar la operacion."""

def leer_inventario(datos):
    return datos + [0]

def validar_inventario(datos):
    return datos + [1]

def actualizar_inventario(datos):
    return datos + [2]

def persistir_inventario(datos):
    return datos + [3]

def sincronizar_inventario(datos):
    datos = leer_inventario(datos)
    datos = validar_inventario(datos)
    datos = actualizar_inventario(datos)
    datos = persistir_inventario(datos)
    return datos

def inventario_estadisticas_historicas(datos):
    return len(datos)

def inventario_mostrar_ayuda():
    return "solo interfaz de ayuda"

def inventario_exportar_demostracion(datos):
    return str(datos)
