# Entrega completa en un único ZIP

Este archivo reúne toda la entrega de complementos de Equipo IA V2-F. No necesitas descargar documentos ni evidencias por separado.

## Ejecutar

Tras descomprimir, entra en `complementos_equipo_ia_v1` y ejecuta:

```sh
python3 -B ejecutar.py
```

## Contenido integrado

- [Uso y requisitos](LEEME.md).
- [Informe de resultados, limitaciones y pruebas pendientes](INFORME.md).
- [Guía de integración para Claude](INTEGRACION_CLAUDE.md).
- [Inspección del V2-F recibido](INSPECCION.md) y [lista de cambios](CAMBIOS.md).
- Código completo de los complementos: `complementos/`.
- Evaluador anterior íntegro: `evaluador_anterior/evaluacion_multiagente_v1/`.
- Pruebas y evaluación nuevas: `tests/`, `evaluacion/` y `datos/`.
- ZIP de V2-F de Claude intacto: `referencia/equipo_f2_v2f.zip`.
- Registros y resultados completos de desarrollo y validación: `evidencias/`.
- ZIP de la entrega anterior, su SHA-256, informe de verificación, salida terminal y todos los archivos de la ejecución realizada desde ese ZIP: `evidencias/entrega_y_verificacion_del_zip/`.
- Manifiesto actualizado de esta recopilación: `MANIFIESTO_SHA256.json`.

## Estado

La entrega anterior terminó 37 pruebas nuevas y 25 del evaluador anterior, sin fallos. La ejecución desde su ZIP también terminó con código 0. Los resultados de memoria/herramientas proceden de datos sintéticos; las comparaciones entre agentes son simuladas. Qwen real y Termux real siguen pendientes. No se declara una versión estable ni una mejora demostrada del modelo.

Esta recopilación añade documentos y evidencias; no modifica el código, los conjuntos de evaluación ni los resultados anteriores. Los hashes de la entrega previa corresponden al ZIP previo incluido. El manifiesto de esta carpeta corresponde al contenido ampliado y excluye únicamente el propio manifiesto y futuras salidas generadas en `resultados/`.
