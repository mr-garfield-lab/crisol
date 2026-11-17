# Encargo mínimo de integración para Claude Pro

El núcleo V2-E.7 ya tiene `equipo.py tarea importar/ejecutar/estado/exportar`. No reescribirlo. Conectar `modlab_pz` como herramienta de lista blanca: inspeccionar ZIP, simular JSON y analizar Lua estáticamente. No ejecutar Lua de terceros ni Java. Respetar permisos, STOP, registros append-only y exportaciones existentes. A1 prepara escenarios, A2 ejecuta las herramientas permitidas, A3 audita solo lectura. Usar un ZIP con mod ficticio propio y escenario con fallo intencional para una demostración real. No declarar compatibilidad Build 42. Entregar prueba real con Qwen solo si se ejecutó y documentar lo pendiente. No tocar versiones previas. Priorizar un cambio pequeño y verificable.

## Comandos del laboratorio

`python3 -B modlab_pz/EJECUTAR_PRUEBAS.py`

`python3 -B modlab_pz/laboratorio.py simular modlab_pz/escenarios/inventario_error_intencional.json --salida /ruta/nueva`

El analizador Lua se usa por importación: `from modlab_pz.lua_analisis import analizar_lua`. `comprobar_sintaxis_archivo` usa luac opcional, solo con código propio/confiable; no es sandbox.
