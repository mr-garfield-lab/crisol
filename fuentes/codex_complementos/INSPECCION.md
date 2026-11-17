# Referencia inspeccionada

Adjunto: `equipo_f2_v2f.zip`, SHA-256 `ee73af5702e1d627707c8d289da0ca5e0126eba6bf34500f697f77676ee1e146`. CRC correcto, 272 entradas, 271 archivos declarados por su manifiesto interno sin discrepancias. El código declara `f2-v2f`. Su documentación dice que parte de V2-E.7-r3; no se ha confundido con la copia V2-E.9-r3 anterior del usuario.

## Funciones existentes que se reutilizan

| Componente V2-F | Función existente | Complemento acotado |
|---|---|---|
| `aprendizaje.py`, `experiencias.py` | SQLite por agente, estados, evidencias, caducidad, cuarentena, contradicciones de polaridad, recuperación Jaccard, calibración | Leer una instantánea, verificar integridad/procedencia, separar conflictos, ordenar y limitar el contexto completo |
| `herramientas.py` | Registro congelado, selección de tres necesidades, permisos y despachador | Selección previa que recibe agente, flujo, argumentos disponibles e intentos fallidos |
| `autocorreccion.py` | Precomprobación, historial de cambios, contraejemplos y afirmaciones sin evidencia | Clasificación breve de excepciones y firma del intento; no se reconstruye la autocorrección |
| `motor_v2f.py`, `planificacion.py`, `debate.py` | Planificación, debate, revisión, ejecución de casos, adjudicación por evidencia | Sin cambios; se ofrecen objetos compatibles por composición y una subclase mínima para contexto |
| `contexto.py`, `motor.py` | Presupuesto total y recorte por caracteres | Mantener registros completos; retirar fragmentos antes de llamar al backend |
| `banco_capacidades.py` | Banco de Claude con modos simulados/reales | Se conserva aparte; se reutiliza el evaluador independiente previo sin modificarlo |

## Hallazgos comprobados relevantes

1. `AprendizajeAgente.recuperar(..., registrar_uso=True)` escribe usos por defecto. El complemento no llama a esa vía para seleccionar ni crea objetos de almacenamiento: recibe una conexión existente, valida identidad/esquema, copia SQLite a RAM y consulta esa copia. El baseline de evaluación usa explícitamente `registrar_uso=False`.
2. La recuperación heredada no comprueba el SHA de cada texto. Una prueba nueva altera solo el hash de una base sintética: V2-F devuelve el recuerdo; el complemento lo excluye. No se ha manipulado ninguna memoria original.
3. `herramientas.seleccionar(necesidad, autorizado)` no recibe agente/flujo. El despachador sí comprueba ambos. No es una afirmación de ejecución sin permisos: el asesor nuevo evita propuestas que el despachador rechazaría.
4. `contexto.construir` puede recortar el bloque de experiencias. Se reprodujo ese recorte, y el adaptador retira el fragmento antes del backend. Conserva los límites y prioridades existentes.
5. El filtro de contaminación heredado bloquea dos recuerdos útiles del banco (M02/M08); ambos se conservan como falsos negativos. No se ha debilitado ese filtro.

## Fuera del alcance de esta entrega

No se ha realizado una auditoría integral de V2-F ni ejecutado su batería completa. El constructor de aprendizaje sigue conteniendo DDL antes de comprobar metadatos: el puente evita invocarlo, pero no corrige el inicializador de Claude. La política del despachador existente sobre registrar solicitudes rechazadas tampoco se modifica. El ejecutor restringido de Claude declara que no es un sandbox; aquí no se utiliza para ejecutar respuestas de agentes. Estos puntos requieren la revisión e integración posterior correspondiente.
