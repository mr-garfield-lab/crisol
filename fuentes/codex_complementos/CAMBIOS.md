# Comparación de archivos

**V2-F de Claude: 0 archivos modificados. Evaluador anterior: 0 archivos modificados.** Tampoco se modifica la copia anterior de Equipo IA. No hay parches que aplicar sobre sus árboles.

Archivos añadidos en este paquete:

| Archivo | Motivo |
|---|---|
| `complementos/memoria.py` | Selección pura con hash, procedencia, conflictos, estados y presupuesto del paquete completo |
| `complementos/v2f.py` | Adaptador a SQLite/API existentes sin inicialización ni migración, y proxy compatible |
| `complementos/herramientas.py` | Selección previa por identidad, flujo, autorización, formato e historial |
| `complementos/contexto_v2f.py` | Conservación de recuerdos enteros en el constructor real de prompts |
| `complementos/diagnostico.py` | Clasificación orientativa de errores y detección de repetición exacta |
| `evaluacion/componentes.py` | Comparación reproducible contra funciones originales |
| `evaluacion/programas.py`, `evaluacion/ocultos.py` | Catálogo fijo y pruebas ocultas al callback, reutilizando el motor previo |
| `datos/*.json` | Corpus sintético y resultados esperados visibles para auditoría |
| `tests/test_complementos.py` | 37 pruebas de contrato, integración y casos adversariales |
| `ejecutar.py` | Comando único, integridad, repetición, logs íntegros, resumen y códigos de salida |
| `LEEME.md`, `INSPECCION.md`, `INTEGRACION_CLAUDE.md`, `INFORME.md` | Uso, inspección, contratos y límites |
| `evidencias/*`, `MANIFIESTO_SHA256.json` | Registros, conservación y hashes verificables |

`referencia/equipo_f2_v2f.zip` es una copia exacta del adjunto. `evaluador_anterior/evaluacion_multiagente_v1/` contiene los 31 archivos del ZIP previo sin reescritura. La comprobación byte a byte y las huellas están en `evidencias/preservacion.json`. `evidencias/codigo_evaluado.json` identifica las fuentes usadas en la batería final. El manifiesto exterior incluye las evidencias como archivos ordinarios; no las presenta como pruebas nuevas de V2-F.
