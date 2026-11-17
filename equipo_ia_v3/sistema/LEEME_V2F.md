# Equipo IA — V2-F: capacidades verificables de A1, A2 y A3

**Estado: NO estable.** Pendiente de la revisión de GPT-6 y de las pruebas con Qwen en el S23. No sustituye a ninguna versión anterior.

**Base.** Copia de V2-E.7-r3, la única que venía en el material.
- Su LEEME la marca «NO estable»; la estable es r2, que no estaba disponible.
- Los 216 archivos recibidos coinciden byte a byte con el manifiesto de r3. Faltaban cinco archivos (ver §7).
- Los módulos nuevos no dependen del único cambio de r3, la evidencia de A3 en ModLab (`evidencia_pz.py`).

**Datos.** Todo va a `$TMPDIR/equipo_f2/lab_v2f/`. `lab_v2e7r3` y las carpetas anteriores no se tocan.

**Límites que se respetan:**
- No se migra a PC.
- No se usan APIs de pago ni dependencias nuevas: solo la biblioteca estándar de Python 3.11 o superior.
- No se modifican los pesos del modelo ni hay entrenamiento.
- No se amplía ningún permiso.

## 0. Una sola orden de pruebas

```
python3 -B verificar.py
```

Ejecuta la batería heredada más dos fases nuevas, con la misma salida, registros y códigos de salida de siempre:
- **CAP**: plan, debate, memoria, autocorrección y herramientas.
- **BAN**: banco comparativo simulado, ejecutado dos veces para comprobar que es reproducible.

Los resultados se guardan en `$TMPDIR/equipo_f2/lab_v2f/verificacion/<id>/`. Ahí está `demos/banco_simulado.md`, con la tabla comparativa.

Con Qwen real (solo con autorización), `python3 -B verificar.py --qwen-real --iniciar-servidor-real` añade **V-QWEN-04**: el banco real sobre una tarea, en modo individual y en modo equipo_debate.

## 1. Qué cambia, por prioridad

| Prioridad | Qué hace ahora el sistema | Dónde | Pruebas |
|---|---|---|---|
| 1. Razonamiento y planificación | A2 escribe `SUBTAREA` (dependencias y prioridad), `CRITERIO`, `FALTA` y `SUPUESTO`. El controlador valida el grafo (ciclos, referencias), calcula el ORDEN de trabajo y se lo da a A1. Una `FALTA` sin supuesto **detiene la tarea y pregunta** (`informacion_insuficiente` + `preguntas.md`), o se asume y se marca si la tarea lo pide. El plan se REVISA con evidencia: falta la prueba de un criterio, se repite el mismo fallo o A1 rebate una prueba. Si A2 retira TODOS los criterios, no queda nada verificable y la tarea se escala al usuario. | `planificacion.py`, `motor_v2f.py` | `test_v2f_componentes.TestPlanificacion`, `test_v2f_motor.TestPuertaDeInformacion`, `TestReplanificacion` |
| 2. Debate inteligente | **Tareas `debate_codigo`.** Se hacen tres propuestas independientes con estrategias distintas y una ejecución cruzada de todos los casos contra todas las candidatas. Después, objeciones, contraejemplos, impugnaciones y posiciones, y al final una **adjudicación determinista**: decide la evidencia, la mayoría nunca. Si la mayoría prefiere una candidata que la evidencia descarta, queda registrado (`mayoria_contra_evidencia`).<br>**Dentro del motor.** Los contraejemplos de A3 se ejecutan. A1 puede impugnarlos y A3 revisa de nuevo: si retira el caso, se acepta; si lo mantiene, la tarea termina en `disputa_sin_resolver`. A1 también puede rebatir una prueba de A2, que entonces revisa su plan. | `debate.py`, `motor_v2f.py`, `tareas.py` | `test_v2f_debate`, `test_v2f_motor.TestDisputaYAfirmaciones` |
| 3. Aprendizaje mediante memoria | El motor y el debate guardan experiencias en la memoria **individual** de cada agente (`aprendizaje/a1.db`, `a2.db`, `a3.db`):<br>- A1: errores y correcciones;<br>- A2: criterios útiles y planes corregidos;<br>- A3: contraejemplos confirmados, sin fallo, retirados o disputados.<br>Lo que observó el sistema es «hecho/observado», con la ruta y el SHA-256 del registro de la prueba. Lo que concluye un agente es «lección/opinión» (hipótesis). Se recuperan con metadatos, más una línea de CALIBRACIÓN contada por el sistema. | `experiencias.py` sobre `aprendizaje.py` | `test_v2f_componentes.TestExperiencias`, `test_v2f_tareas.TestMotorV2FComoTarea` |
| 4. Autocorrección | **Precomprobación estática.** Si el código no se puede analizar, el controlador diagnostica (archivo y línea) y se ahorran 3 llamadas.<br>**Historial de intentos.** A1 lo recibe en cada corrección.<br>**Contraejemplos ejecutables.** Bloquean la aceptación mientras fallen.<br>**Afirmaciones sin evidencia.** Se registran («todas las pruebas pasan» sin una ejecución que lo respalde).<br>**En el debate.** Un autor puede retirar su propio caso erróneo. | `autocorreccion.py`, `motor_v2f.py`, `debate.py` | `test_v2f_componentes.TestAutocorreccion`, `test_v2f_motor.TestPrecomprobacion` |
| 5. Uso de herramientas | Hay un **registro tipado e inmutable** (agentes, flujos, autorización, sustituta) que el DESPACHADOR aplica en cada uso.<br>Los agentes piden ejecuciones con `CASO: f(<literales>) == <literal>`: el controlador escribe la prueba con `repr()` de valores ya leídos, así que no hay inyección.<br>Cada error tiene su categoría y se le explica al agente en su siguiente prompt.<br>Sin autorización, el sistema pasa al análisis estático y lo marca como «no es una prueba». | `herramientas.py`, `casos.py` | `test_v2f_componentes.TestHerramientas`, `TestCasos`, `test_v2f_motor.TestUsoDeHerramientas` |
| 6. Medición de capacidades | Banco `capacidades_v1`: 8 tareas con ejemplos visibles y **oráculos ocultos**, que nunca entran en un prompt. Se comparan 4 modos: individual, individual con autoprueba, equipo_debate y equipo_motor.<br>Se mide calidad, falsas certezas, abstenciones, llamadas, tokens, tiempo, proyección al S23 y errores.<br>Hay modo simulado reproducible y modo Qwen real. | `banco_capacidades.py`, `banco.py`, `bancos/capacidades_v1/` | `test_v2f_banco`, fase BAN |

## 2. Implementado, simulado y pendiente

| | Implementado y ejecutado aquí (sandbox Linux) | Solo simulado | Pendiente |
|---|---|---|---|
| Plan | Análisis, validación, orden, información que falta, revisión con detección de debilitamiento | Textos de A2 (guion) | Calidad de la descomposición de Qwen; generación incremental subtarea a subtarea (más llamadas: evaluar en PC) |
| Debate | Protocolo completo, ejecución REAL de candidatas y casos, adjudicación, reparación, registro | Propuestas y argumentos (guion o política parametrizada) | Diversidad real de Qwen con temperatura 0; debate de tareas no ejecutables (se mantiene la deliberación de V2-E.6) |
| Memoria | Escritura y recuperación por agente, metadatos, calibración, contaminación rechazada, persistencia entre tareas | Que el «agente» use la experiencia (guion) | Medir con Qwen si recordar cambia sus respuestas (banco real con `--memoria`); consolidar recuerdos al llegar a 400 por agente |
| Autocorrección | Precomprobación, historial, contraejemplos ejecutados, disputas, afirmaciones sin evidencia | Correcciones de A1 (guion) | Medición con Qwen |
| Herramientas | Registro, despachador, categorías, avisos al agente, sustitución, sin inyección | — | Herramientas de otros lenguajes (Modo B sigue deshabilitado) |
| Medición | Banco, oráculos ocultos, métricas, informes y comparación | Modo simulado (política con parámetros) | **Banco con Qwen real en el S23** |

## 3. Órdenes en Termux (una por mensaje)

Instalación aislada (ajusta la ruta del ZIP):
1. `mkdir -p "$TMPDIR/equipo_f2/codigo_v2f"`
2. `cd "$TMPDIR/equipo_f2/codigo_v2f"`
3. `sha256sum ~/storage/downloads/equipo_f2_v2f.zip` (compáralo con el de la entrega)
4. `python3 -m zipfile -e ~/storage/downloads/equipo_f2_v2f.zip .`
5. `cd equipo_f2_v2f`
6. `sha256sum -c --quiet MANIFIESTO_SHA256.txt && echo INTEGRO`
7. `python3 -B verificar.py`

Tareas con el motor V2-F (Qwen real; `--ctx 2048` por defecto, `--ctx 1024` como alternativa):
1. `python3 -B equipo.py tarea importar ejemplos/tarea_v2f_codigo.json`
2. `python3 -B equipo.py tarea ejecutar LAB-001 --autorizo-pruebas`
3. `python3 -B equipo.py tarea exportar ultima`

Debate por evidencias: `python3 -B equipo.py tarea importar ejemplos/tarea_v2f_debate.json` y después `ejecutar` igual. La tarea admite:
- `"casos"`: el oráculo del usuario;
- `"propiedades"`: `no_muta_argumentos`, `determinista`;
- `"politica_falta"`: `preguntar` o `asumir_y_marcar`;
- `"motor"`: `v2f` o `v2e`.

Banco comparativo:
- **Simulado:** `python3 -B banco.py simular --autorizo-pruebas`. Opciones: `--correlacion 0.9`, `--p-acierto 0.3`, `--parametro p_reparar=0.2` (cualquier parámetro de `simulacion.json`), `--tareas mediana dedup`.
- **Real (S23):** `python3 -B banco.py real --autorizo-pruebas --iniciar-servidor-real --tareas mediana dedup --modos individual individual_autoprueba equipo_motor`.
  - Estos tres modos miden lo que más pesa según el banco simulado (§4): si Qwen corrige su código cuando la ejecución le enseña el fallo. Añade `equipo_debate` en una segunda ronda.
  - Mira antes la columna «Proyección S23» del banco simulado: los modos de equipo cuestan unas 6–9 llamadas por tarea, frente a 1–2 del individual.
  - Usa `--memoria` para medir el efecto de la memoria, aislada por modo.
- **Comparar:** `python3 -B banco.py comparar A/informe.json B/informe.json`.

## 4. Resultados del banco SIMULADO (evidencia de esta entrega)

> **SIMULADO.** Las respuestas de A1, A2 y A3 salen de una política con probabilidades fijadas a mano (`bancos/capacidades_v1/simulacion.json`), no de Qwen. Sí son REALES la ejecución de cada solución, de las pruebas y de los casos, y la evaluación contra los oráculos ocultos. Estas cifras validan el banco y el protocolo; **no dicen nada de cómo rinde Qwen**.

Órdenes ejecutadas, una por variante: `python3 -B banco.py simular --autorizo-pruebas`, con `--correlacion X`, `--p-acierto X` o `--parametro p_reparar=X` según la fila. Los informes completos están en `evidencias_claude/banco_simulado/`.

Parámetros base: `correlacion` 0.5 · `p_acierto` 0.5 · `p_reparar` 0.8 (el resto, en `simulacion.json`). Semillas [11, 42, 2026]: 8 tareas × 3 semillas = 24 ejecuciones por modo. Huella de decisiones `ff43a58de3c0e8c4`.

| Modo | Correctas | Calidad media | Falsas certezas | Abstenciones | Llamadas por tarea | Tokens por tarea (estimados) | Proyección S23 por tarea |
|---|---:|---:|---:|---:|---:|---:|---:|
| individual | 12/24 | 0.806 | 0 | 0 | 1.0 | 453 | 0.7 min |
| individual_autoprueba | 18/24 | 0.910 | 1 | 0 | 1.67 | 799 | 1.3 min |
| equipo_debate | 19/24 | 0.910 | 2 | 1 | 6.21 | 3.730 | 6.0 min |
| equipo_motor | 24/24 | 1.000 | 0 | 0 | 8.58 | 5.942 | 9.6 min |

**Sensibilidad** (cambia un parámetro cada vez; celdas: correctas de 24 · falsas certezas · abstenciones):

| Variante | individual | individual_autoprueba | equipo_debate | equipo_motor |
|---|---:|---:|---:|---:|
| base (correlacion 0.5) | 12 · 0 · 0 | 18 · 1 · 0 | 19 · 2 · 1 | 24 · 0 · 0 |
| correlacion 0.0 | 12 · 0 · 0 | 18 · 1 · 0 | 18 · 2 · 2 | 24 · 0 · 0 |
| correlacion 0.9 | 12 · 0 · 0 | 18 · 1 · 0 | 19 · 1 · 2 | 24 · 0 · 0 |
| p_acierto 0.3 | 7 · 0 · 0 | 14 · 2 · 0 | 16 · 3 · 2 | 24 · 0 · 0 |
| p_acierto 0.8 | 20 · 0 · 0 | 20 · 1 · 0 | 21 · 1 · 1 | 24 · 0 · 0 |
| p_reparar 0.5 | 12 · 0 · 0 | 14 · 1 · 0 | 18 · 2 · 2 | 20 · 1 · 0 |
| p_reparar 0.2 | 12 · 0 · 0 | 12 · 1 · 0 | 15 · 2 · 5 | 13 · 1 · 0 |

Cómo leerlo:
- **Con los parámetros base**, el motor acierta 24/24 y el individual 12/24. El debate acierta casi lo mismo que la autoprueba (19 frente a 18), con más falsas certezas (2 frente a 1) y casi 4 veces más llamadas: en esta simulación el debate no supera con claridad a un solo agente que prueba su código. El coste sube con el equipo: 6–9 llamadas por tarea frente a 1–2.
- **La ventaja del motor depende casi entera de `p_reparar`**, la probabilidad de que un agente corrija un defecto cuando la ejecución se lo enseña. Con 0.2, el motor acierta 13/24 frente a 12/24 del individual y tarda unas 12 veces más. Ese es justo el dato que no tenemos de Qwen 3B: hay que medirlo en el S23 con `banco.py real`.
- **Cuando el motor falla, casi siempre lo dice.** Con `p_reparar` 0.2, 10 de sus 11 fallos terminan en `sin_progreso` y solo 1 afirma un éxito falso.
- **El individual nunca afirma éxito** (no ejecuta nada), así que sus 0 falsas certezas vienen de la construcción del modo, no de un mérito.
- **Las falsas certezas del equipo** son soluciones que cumplen los ejemplos visibles y los casos de los agentes, pero fallan un caso oculto que nadie planteó. El banco las cuenta aparte; no se diluyen en la media.
- **`correlacion`** (agentes que repiten la misma propuesta por ser el mismo modelo) apenas mueve el debate aquí, porque la ejecución cruzada y la reparación siguen funcionando. Con Qwen real puede pesar más.
- **Tokens y tiempos son ESTIMADOS**: longitud/3 de los textos del guion y velocidades medidas en prueba3 (9.3 tok/s generando y 10.5 tok/s leyendo). Las respuestas reales de Qwen son más largas que las del guion, así que los tiempos reales serán mayores.

## 5. Garantías que se conservan
- **El código decide «verificado», no un agente.** En V2-F, `resultado` concuerda siempre con el estado final. «verificado_con_reservas» y «disputa_sin_resolver» nunca se presentan como «verificado».
- **Los textos son datos.** Los textos de los agentes, los recuerdos, los casos y las experiencias no pueden cambiar `Presupuesto`, `Politica`, `MODO_B_HABILITADO`, el registro de herramientas ni la autorización.
  - Hay pruebas de que la memoria contaminada se rechaza o se pone en cuarentena.
  - Hay pruebas de que la huella del registro no cambia.
- **Solo la CLI autoriza la ejecución** (`--autorizo-pruebas`). La prueba de V2-E.7 que lo vigila sigue pasando con los módulos nuevos.
- **Ejecutor restringido sin cambios.** Lista blanca AST, proceso hijo limitado, gancho de auditoría y nonce. No es un sandbox.
- **Validador estático:** 0 problemas, incluidos los módulos nuevos y `banco.py`.

## 6. Límites conocidos
- **Mismo modelo.** Los tres agentes son el mismo Qwen y, con temperatura 0, propuestas «independientes» pueden ser idénticas. El debate lo mide (`independencia.diversidad_baja`) y el banco lo modela con el parámetro `correlacion`.
- **Coste del equipo.** Los modos de equipo multiplican las llamadas: unas 6–9 por tarea, frente a 1–2. Con ~9 tok/s en el S23 eso son minutos por tarea (ver la proyección del banco).
- **CTX 1024.** Con tareas de 600 caracteres, algunos bloques (código en `corregir`, propuestas en el cuestionamiento) apenas caben; ya pasaba en V2-E. V2-F usa 2048 por defecto en `equipo.py`; en V2-E.7 `equipo.py` no fijaba el contexto y quedaba en 1024.
- **Detector de pruebas debilitadas.** Es una heurística: cuenta aserciones y puede dar falsos positivos. Por eso no rechaza, pero impide «verificado» hasta que lo revises.
- **«cumple_oraculo»** significa que la solución cumple los casos disponibles. No es una demostración: con un solo ejemplo en el enunciado puede haber falsas certezas, y el banco las mide.
- **Memoria.** Tope de 400 recuerdos por agente (disparador de `aprendizaje.py`). Al llegar al tope, el registro falla y se informa; la tarea sigue.

## 7. Archivos de r3 que faltaban en el material recibido
- `auditoria_ejemplo/auditoria_ejemplo.zip` y `retos/zomboid_v1/paquete_desafio/desafio_zomboid_v1.zip`: se REGENERAN desde sus carpetas `fuente/` con `herramientas/construir_paquete.py`, con la versión V2-F (su contenido cambia en cada versión).
- `evidencias_claude/suite_unittest_normal.log` y `suite_unittest_sin_link.log` de r3: eran registros de esa versión y no se pueden reconstruir. El resto de evidencias de r3 está, sin cambios, en `evidencias_claude/v2e7r3/`; V2-F trae sus propios registros.
- `modlab_pz/fixtures/mod_ejemplo_propio.lua`: solo lo usaba la prueba propia de ModLab que lanza `luac` (no forma parte de `verificar.py`). La prueba del núcleo que lo nombra solo comprueba un rechazo y no lee el archivo.

## 8. Volver atrás
V2-F vive en su propia carpeta de código y de datos. Volver a r3 o a r2 es seguir usando su carpeta. No hace falta borrar ni migrar nada.
