# Adición experimental: PZ ModLab 0.1

Se incorporó `modlab_pz/` como carpeta independiente sin modificar los 195 miembros originales del ZIP. No se altera el ejecutor restringido, el backend, los agentes, el orquestador, los registros, el verificador ni los mecanismos STOP.

**No confundir con el objetivo final**: esta entrega únicamente permite inspeccionar archivos de mods y ejecutar escenarios declarativos propios sin gráficos. La emulación de código Lua real, APIs de PZ, interacciones entre mods y validación diferencial aún no existen.

No se ejecuta contenido del ZIP inspeccionado. Para cualquier integración futura en los agentes se requiere autorización y pruebas de seguridad adicionales.
