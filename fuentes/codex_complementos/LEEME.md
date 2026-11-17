# Complementos Equipo IA V2-F — v1.0.0 candidata

Paquete independiente para revisión e integración por Claude. No reemplaza Equipo IA ni es una versión estable. Python 3.11+ y biblioteca estándar; no instala nada, no usa red ni APIs y no inicia modelos.

Descomprime en una carpeta nueva, entra en `complementos_equipo_ia_v1` y ejecuta:

```sh
python3 -B ejecutar.py
```

En Termux usa el almacenamiento privado de Termux, con Python ya disponible. La ejecución en Android queda pendiente; las verificaciones entregadas se realizaron en Linux. No hace falta un GGUF para esta batería.

La orden comprueba hashes, extrae una copia del ZIP de referencia, ejecuta las pruebas nuevas, ejecuta íntegramente el evaluador anterior, compara los componentes dos veces y evalúa un catálogo fijo de programación. Muestra INICIO/FIN y guarda registros completos en `resultados/<fecha UTC>/`, sin sobrescribir ejecuciones anteriores. Códigos: 0 = controles locales completos; 1 = fallo; 2 = error/inconclusa. Un 0 no significa que Qwen o Termux hayan sido evaluados.

Contenido:

- `complementos/`: memoria, puente para V2-F, protección del contexto, asesor de herramientas y diagnóstico auxiliar.
- `evaluador_anterior/evaluacion_multiagente_v1/`: los 31 archivos del evaluador previo, idénticos byte a byte, incluido código, pruebas y evidencias.
- `referencia/equipo_f2_v2f.zip`: adjunto de Claude íntegro, para reproducir las pruebas contra sus API reales. No se instala ni sustituye ninguna copia.
- `evaluacion/`, `datos/`, `tests/`: comparaciones y pruebas adversariales nuevas.
- `evidencias/`: registros, resultados y bases SINTÉTICAS de prueba. No son memorias de los agentes del usuario.
- `INTEGRACION_CLAUDE.md`, `INSPECCION.md`, `INFORME.md`, `CAMBIOS.md`: contrato, hallazgos, resultados y límites.
- `MANIFIESTO_SHA256.json`: hashes de todos los archivos distribuidos salvo el propio manifiesto. Las salidas nuevas en `resultados/` quedan fuera de ese manifiesto.

Para revisar resultados: `evidencias/validacion_final/resumen.json`, `unitarias.log`, `evaluador_anterior.log`, `componentes_1/comparacion.json` y `programacion_casos_ocultos.json`. La comparación contiene todas las consultas y decisiones, incluidos errores y falsos positivos.

Rollback: dejar de importar estos módulos y volver a suministrar a MotorV2F los objetos originales de Claude. No se requieren migraciones ni restauraciones de bases. No borres evidencias para volver atrás.
