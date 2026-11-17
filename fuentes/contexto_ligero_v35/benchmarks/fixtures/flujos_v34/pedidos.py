"""Flujo sintetico aislado: las cinco funciones son necesarias para completar la operacion."""

def normalizar_pedido(datos):
    return datos + [0]

def validar_pedido(datos):
    return datos + [1]

def calcular_pedido(datos):
    return datos + [2]

def guardar_pedido(datos):
    return datos + [3]

def procesar_pedido(datos):
    datos = normalizar_pedido(datos)
    datos = validar_pedido(datos)
    datos = calcular_pedido(datos)
    datos = guardar_pedido(datos)
    return datos

def pedido_estadisticas_historicas(datos):
    return len(datos)

def pedido_mostrar_ayuda():
    return "solo interfaz de ayuda"

def pedido_exportar_demostracion(datos):
    return str(datos)
