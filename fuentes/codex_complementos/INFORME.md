# Resultados y veredicto

Candidata independiente lista para revisión de Claude. **No se declara estable ni se demuestra mejora de Qwen.** La utilidad medida corresponde a componentes ejecutados sobre fixtures sintéticos y a integración con las API reales de V2-F.

## Batería terminada

`python3 -B -I -S ejecutar.py --salida <carpeta nueva>` terminó con código 0 en Linux/Python 3.12.14. Las opciones -I -S adicionales comprueban que no se necesitan paquetes del entorno. El comando normal documentado es `python3 -B ejecutar.py`.

- 37 pruebas nuevas: 37 aprobadas, 0 fallidas, 0 errores, 0 omitidas.
- Evaluador anterior íntegro: 25 aprobadas, 0 fallidas, 0 errores, 0 omitidas; sus dos comparaciones guionizadas terminaron.
- Comparación de componentes repetida dos veces: mismas decisiones y métricas, excluyendo los tiempos variables.
- 3 tareas de programación, 9 candidatas fijas, 30 ejecuciones de casos: se detectan candidatas incorrectas, mutación del argumento y casos límite. Esto valida el catálogo y los oráculos; no es generación de código por Qwen.
- Roles y presupuesto del evaluador: mismo adaptador y tres llamadas por condición. A1 programador, A2 analista, A3 auditor; A1/A2 proponen independientemente. No se utiliza votación para declarar éxito.
- Qwen real, Android/Termux real y generación libre: **OMITIDAS** explícitas. No cuentan como aprobadas.

Los registros completos están en `evidencias/validacion_final/`. Se conservan también registros de desarrollo y de la primera validación. No hubo pruebas fallidas en esas ejecuciones; sí resultados desfavorables del banco, descritos abajo y conservados en JSON.

## Recuperación de memoria

Datos: 13 recuerdos sintéticos y 12 consultas predefinidas; 6 base y 6 de generalización. La segunda partición no es un conjunto ciego externo: sus etiquetas están en el paquete para auditoría; el algoritmo no las recibe. Hay 9 recuperaciones relevantes esperadas y 3 consultas cuya respuesta correcta es abstenerse. Mismo máximo de 4 recuerdos antes/después, sin reducir n para subir precisión.

Baseline: `AprendizajeAgente.recuperar(..., registrar_uso=False)` y renderizador de experiencias de Claude. Complemento: instantánea verificada, filtrado, clasificación y paquetes completos, con límite de 1800 bytes por consulta. El baseline mantiene su formato original sin ese límite total adicional. No hubo exclusiones por presupuesto en esta comparación: la reducción procede de los filtros y del contenido recuperado, no de bajar el número máximo permitido.

| Métrica, 12 consultas | V2-F antes | Complemento después |
|---|---:|---:|
| Relevantes recuperados (TP) | 5 | 5 |
| Irrelevantes recuperados (FP) | 6 | 2 |
| Relevantes perdidos (FN) | 4 | 4 |
| Precisión TP/(TP+FP) | 45,45 % | 71,43 % |
| Recall TP/(TP+FN) | 55,56 % | 55,56 % |
| Selección exactamente correcta | 5/12 | 6/12 |
| Bytes UTF-8 del contexto completo | 3119 | 2555 |
| Tokens reales del modelo | No medidos | No medidos |

Reducción de bytes: **18,08 %**. No equivale a una reducción demostrada de tokens. Los metadatos y el aviso también se incluyen en la medida. En base, precisión 42,86→60 % y recall 75→75 %. En generalización, precisión 50→100 % pero recall solo 40→40 %: ese 100 % NO significa resolver todas las consultas.

**Resultados desfavorables:** M01 recupera además un recuerdo de mediana y M06 añade uno de valores nulos; son dos falsos positivos nuevos. M02 y M08 pierden recuerdos útiles por el filtro de contaminación heredado. M11/M12, paráfrasis en inglés y sinónimos sin coincidencia léxica, no recuperan el recuerdo esperado en ninguno de los dos sistemas. No se ajustaron los oráculos ni se relajó el filtro para ocultarlo. La mejora está principalmente en excluir datos inseguros/contradictorios; no demuestra comprensión semántica general.

La comprobación adversarial de hash se ejecuta además como prueba separada: una base sintética con SHA incorrecto es recuperada por V2-F y rechazada por el complemento. En el banco, M04 ya era omitida por el sistema original; no se atribuye una mejora inexistente a esa consulta.

## Herramientas

| Conjunto | Selector original | Complemento |
|---|---:|---:|
| 7 casos con necesidades admitidas por la API original | 3/7 | 7/7 |
| 12 casos, incluyendo ModLab y abstenciones | 6/12 | 12/12 |

La tabla mide recomendación correcta de herramienta Y suficiencia, no éxito de ejecución. El original dispone de un despachador que rechaza después las propuestas incompatibles; no se ha descubierto aquí una ejecución sin permisos. La mejora consiste en anticipar esos rechazos, aprovechar casos literales cuando el agente no puede pedir una suite y señalar la falta de datos o autorización.

Se prueban A1/A2/A3, motor/debate/ModLab, lenguaje incompatible, casos ausentes, autorización falsa, rutas hostiles, registro inalterado y repetición del mismo intento fallido. La revalidación se contrasta con el despachador real y se ejecuta análisis estático real de una sintaxis incorrecta. No se ejecutan herramientas arbitrarias.

## Colaboración y programación

Se preservan los resultados desfavorables del evaluador anterior: en su guion, el equipo puede empeorar respuestas y llegar a consenso erróneo. El guion nuevo tiene 0/3 aciertos individuales y 2/3 de equipo; el equipo falla por consenso en PR02. Son decisiones pregrabadas para probar puntuación, trazas y aislamiento de los oráculos, NO una estimación de la ventaja de tres agentes.

Los casos ocultos comprueban listas vacías, duplicados, negativos, extremos inclusivos y ausencia de mutación. Son ocultos a los mensajes de agentes, no secretos frente a una persona que abre el ZIP. Ninguna salida del modelo se usa con eval/exec. Las funciones del catálogo son parte fija y auditable del módulo de evaluación. Se entrega un callback para repetir el protocolo con un modelo real autorizado.

## Seguridad y conservación

El ZIP V2-F y los 31 archivos del evaluador previo se mantienen byte a byte. Se comprobaron 933 archivos previos de los laboratorios y referencias sin alteraciones. Las bases de las pruebas son nuevas; incluyen alteraciones adversariales intencionales solo dentro de esas fixtures. Identidad incompatible, metadatos incompatibles y recuperación rechazada conservan los hashes de la base y archivos asociados comprobados.

La memoria nunca proporciona permisos al selector. Los complementos no inician servidores, instalan dependencias ni cambian políticas. La separación depende del supervisor de Claude: estos módulos Python no son una frontera de aislamiento frente a código arbitrario ejecutado en el mismo proceso.

## Pendientes para la siguiente integración

1. Medir tareas completas con Qwen real, mismo modelo/condiciones, con y sin módulos. Tokens reales, éxito final y menos intentos siguen sin comprobarse.
2. Ejecutar en Termux real; probar concurrencia, bloqueo prolongado y WAL con el ciclo de vida real de las memorias. Las pruebas actuales usan bases SQLite locales sintéticas.
3. Evaluar corpus de experiencias reales, otras paráfrasis y contradicciones semánticas. No ampliar la recuperación a hipótesis ni permisos para aumentar una cifra.
4. Revisar falsos positivos del detector heredado en una propuesta separada para Claude.
5. Integrar la protección de paquetes completos también en Debate y registrar sus descartes; el camino probado aquí es AgentesMotorLLMV2F.
6. Auditar el ciclo completo del supervisor y la inicialización/escritura de SQLite de V2-F. Este paquete no certifica ni corrige toda la base.

No se hizo una regresión integral de V2-F porque no se modifica su código. Sí se verificaron las interfaces utilizadas y se empaquetó la referencia exacta para reproducirlas. Los casos pequeños ofrecen evidencia local útil, sin garantía estadística de generalización ni certificación de producción.
