"""Flujo sintetico aislado: las cinco funciones son necesarias para completar la operacion."""

def normalizar_envio(datos):
    return datos + [0]

def validar_envio(datos):
    return datos + [1]

def cotizar_envio(datos):
    return datos + [2]

def registrar_envio(datos):
    return datos + [3]

def preparar_envio(datos):
    datos = normalizar_envio(datos)
    datos = validar_envio(datos)
    datos = cotizar_envio(datos)
    datos = registrar_envio(datos)
    return datos

def envio_estadisticas_historicas(datos):
    return len(datos)

def envio_mostrar_ayuda():
    return "solo interfaz de ayuda"

def envio_exportar_demostracion(datos):
    return str(datos)
