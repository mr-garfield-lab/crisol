"""Flujo sintetico aislado: las cinco funciones son necesarias para completar la operacion."""

def normalizar_reserva(datos):
    return datos + [0]

def validar_reserva(datos):
    return datos + [1]

def comprobar_reserva(datos):
    return datos + [2]

def guardar_reserva(datos):
    return datos + [3]

def confirmar_reserva(datos):
    datos = normalizar_reserva(datos)
    datos = validar_reserva(datos)
    datos = comprobar_reserva(datos)
    datos = guardar_reserva(datos)
    return datos

def reserva_estadisticas_historicas(datos):
    return len(datos)

def reserva_mostrar_ayuda():
    return "solo interfaz de ayuda"

def reserva_exportar_demostracion(datos):
    return str(datos)
