# Equipo IA — V2-F.1: función supervisada A1/A2/A3 e interfaces para Codex

**Estado: candidata, NO estable.** Pendiente de la revisión de GPT-6 y de la demostración con Qwen en el S23. No sustituye a V2-F ni a ninguna versión anterior.

**Base.** El ZIP de V2-F que adjuntaste (`equipo_f2_v2f.zip`, SHA-256 `ee73af5702e1d627707c8d289da0ca5e0126eba6bf34500f697f77676ee1e146`).
- Sus 271 archivos coinciden con su `MANIFIESTO_SHA256.txt`, copiado en `herramientas/manifiesto_v2f.txt`.
- Las evidencias de V2-F se conservan sin cambios en `evidencias_claude/v2f/`.

**Datos.** Todo va a `$TMPDIR/equipo_f2/lab_v2f1/`. `lab_v2f` y las carpetas anteriores no se tocan: están en `config.CARPETAS_ANTERIORES`.

**Límites que se respetan.**
- Solo la biblioteca estándar: ninguna dependencia ni API de pago.
- No se tocan los pesos del modelo.
- No se amplía ningún permiso. Los agentes no pueden cambiar sus propios permisos.
- Compatible con Termux.
- **El código generado no se ejecuta**: ejecución dinámica bloqueada (§6).

## 0. Una sola orden de pruebas

```
python3 -B verificar.py
```

Es la batería de V2-F más:
- una fase nueva, **FUN**: las pruebas `test_v2f1_*` y **V-FUN-01**, la demostración simulada ejecutada dos veces por la CLI, que exige las mismas decisiones, nada ejecutado y el manifiesto íntegro;
- tres demostraciones en la fase DEMO: `funcion_corregible`, `funcion_falta_informacion` y `funcion_sin_progreso`.

Con Qwen real, y solo con tu autorización, `python3 -B verificar.py --qwen-real --iniciar-servidor-real --solo V-QWEN-05` ejecuta la demostración real (§3).

## 1. La demostración que pediste, paso a paso

Tarea `ejemplos/tarea_funcion_demo.json`: `mediana(valores)`, con dos casos del usuario y un ejemplo en el enunciado.

| Paso pedido | Qué hace V2-F.1 | Dónde queda |
|---|---|---|
| 1. El usuario pide una función | `tarea importar` crea `LAB-NNN` (tipo `funcion_supervisada`; nunca sobrescribe) | `tareas/LAB-NNN/tarea_original.json`, `tarea.json` |
| 2. A1 la genera con Qwen local | `fs_generar`. Si le falta un dato imprescindible escribe `FALTA` y la tarea se detiene con preguntas, o sigue con un `SUPUESTO` marcado | `funcion/agentes/01_A1_fs_generar.txt`, `funcion/prompts/…`, `runs/E00n/proyecto/v1/` |
| — El controlador analiza sin ejecutar | Hechos numerados `EV1`…`EV7`: sintaxis, función y firma, lista blanca, riesgo, aplicabilidad de los casos del usuario, tamaño y «NO EJECUTADO». Si hay un bloqueo **replanifica**: no consulta a A2 ni a A3 y A1 corrige con el diagnóstico | `funcion/estatico/v<n>.json`, `decisiones.jsonl` (`replanificacion`) |
| 3. A2 revisa y propone mejoras | `MEJORA: Mn \| alta\|media\|baja \| cambio \| EVIDENCIA: EVn, línea n o caso`, `RESUELTA: Mn` y `VEREDICTO` | `funcion/agentes/…_A2_fs_revisar.txt`, `funcion/rondas/r<k>_v<n>.json` |
| 4. A3 propone casos y evalúa la evidencia | `CASO: f(…) == …` (literales validados; se comprueba si encajan con la firma), `PROBLEMA: Pn \| … \| EVIDENCIA`, `SOBRE: Mn \| confirma\|rechaza \| EVIDENCIA` y `EVALUACION` | ídem |
| — Decisión por evidencia, no por mayoría | Ver §4 | `decisiones.jsonl` (cada objeción con su regla) |
| 5. El equipo intenta corregir | A1 recibe lo que bloquea (con diagnóstico, errores REPETIDOS, historial de intentos y sus experiencias), corrige o rebate (`REBATIDA: id \| motivo`). Límites: `max_iteraciones`, pasos y 45 min. Sin progreso: escalada | versiones `v2`, `v3`…; `decisiones.jsonl` |
| 6. Se guardan código, intentos, decisiones y registros | Versión final (o la mejor, si no se aceptó), pruebas pendientes, eventos, decisiones, prompts y respuestas | `funcion/solucion_final/` o `funcion/mejor_version_no_aceptada/`, `funcion/pruebas_pendientes/`, `funcion/eventos.jsonl`, `MANIFIESTO_SHA256.txt` |
| 7. El usuario recibe un informe verificable | `informe.md` legible e `informe.json`, con: la naturaleza de cada resultado; versiones con SHA-256; rondas, objeciones y reglas; casos; pruebas pendientes; memoria; componentes; límites; y el SHA-256 de cada archivo. `tarea exportar` lo empaqueta todo en un ZIP | `funcion/informe.md`, `funcion/informe.json`, `exportaciones/` |

**Resultado posible:** `aceptada_sin_ejecucion`, `aceptada_con_reservas_sin_ejecucion`, `escalada_al_usuario`, `informacion_insuficiente` o `sin_conclusion`. **Nunca «verificado»**: sin ejecución no hay verificación de comportamiento.

## 2. Real, simulado, omitido y fallido en esta entrega

| Elemento | En esta entrega (sandbox Linux de Claude) | En tu S23 |
|---|---|---|
| A1, A2 y A3 en la función supervisada | **SIMULADO**: un backend de guion recibe los prompts reales y responde con textos fijos | **PENDIENTE**: demostración con Qwen real (§3) |
| Camino de Qwen (`BackendLlama` + llama-server): arranque, peticiones, STOP durante una petición HTTP y cierre | **SIMULADO** con el servidor FALSO de las pruebas (`TestConServidorFalso`) | **PENDIENTE** con el binario y el GGUF reales |
| Análisis estático, lista blanca, firmas y aplicabilidad de casos | **REAL** (ejecutado aquí) | igual |
| Decisiones por evidencia, versiones, reproducibilidad | **REAL** (ejecutado aquí, dos veces) | igual |
| Archivo de pruebas a partir de los casos | **REAL**: generado y analizado; **no ejecutado** | igual |
| Ejecución de esas pruebas | **OMITIDO**: bloqueada a propósito (§6) | bloqueada |
| Memoria de experiencias entre tareas | **REAL**: SQLite, bases por agente, persistencia probada | igual |
| Interfaces para Codex | **REAL**: contratos, validación y adaptadores; componentes «externos» de prueba escritos para los tests | pendiente de los módulos de Codex |
| Prompts dentro de CTX 1024 y 2048 | **REAL** como estimación (len/3): ningún bloque esencial omitido; en 2048 no se omite nada | medir tokens reales con Qwen |

## 3. Órdenes en Termux (una por mensaje)

**Instalación aislada** (ajusta la ruta del ZIP):
1. `mkdir -p "$TMPDIR/equipo_f2/codigo_v2f1"`
2. `cd "$TMPDIR/equipo_f2/codigo_v2f1"`
3. `sha256sum ~/storage/downloads/equipo_f2_v2f1.zip` (compáralo con el de la entrega)
4. `python3 -m zipfile -e ~/storage/downloads/equipo_f2_v2f1.zip .`
5. `cd equipo_f2_v2f1`
6. `sha256sum -c --quiet MANIFIESTO_SHA256.txt && echo INTEGRO`
7. `python3 -B verificar.py`

**Demostración SIMULADA** (sin Qwen; segundos). Escenarios: `corregible`, `falta_informacion` y `sin_progreso`.
- `python3 -B equipo.py demo funcion`
- `python3 -B equipo.py demo funcion --escenario falta_informacion`

**Demostración REAL con Qwen** (pendiente de ejecutar en tu S23). Usa el GGUF original solo para lectura, con las mismas comprobaciones que siempre: modelo, memoria, puerto y llama ya activo.
1. `python3 -B equipo.py tarea importar ejemplos/tarea_funcion_demo.json` (anota el `"id"`, p. ej. `LAB-001`)
2. `python3 -B equipo.py tarea ejecutar LAB-001`
   - `--ctx 2048` por defecto; `--ctx 1024` como alternativa.
   - Son entre 3 y 9 llamadas al modelo. Tiempo **estimado, no medido**: entre 5 y 15 minutos, a unos 9 tok/s.
3. `python3 -B equipo.py tarea exportar LAB-001`, y después `cp` a Descargas con la orden que imprime.
4. O todo junto desde el verificador: `python3 -B verificar.py --qwen-real --iniciar-servidor-real --solo V-QWEN-05`

**Parar.** `touch "$TMPDIR/equipo_f2/lab_v2f1/tareas/LAB-001/STOP"`
- Se comprueba antes de cada paso y durante cada petición al servidor.
- La tarea termina `detenida`, con informe y con las versiones conservadas.

`--autorizo-pruebas` se acepta, pero en este tipo de tarea **se ignora** y el informe lo registra.

## 4. Capacidades nuevas por área

| Área | Qué hace ahora | Pruebas |
|---|---|---|
| **Planificación y autonomía** | **Plan del controlador** (`plan.json`): S1 A1 → S2 controlador → S3 A2 → S4 A3 → S5 A1 → S6 controlador, con responsable, dependencias y prioridad (orden topológico de `planificacion.py`).<br>**Replanificación.** Ante un bloqueo estático se omiten S3 y S4 y se adelanta S5.<br>**Información insuficiente.** `FALTA` sin supuesto → `informacion_insuficiente` + `preguntas.md`; con supuesto → sigue y lo marca como reserva.<br>**Sin bucles.** Correcciones ≤ `max_iteraciones` (≤ 3), pasos ≤ 3 + 3×correcciones, 45 min. Código idéntico, o el mismo error estático tres veces seguidas → `escalada_al_usuario` con la mejor versión. | `test_v2f1_funcion.TestInformacionYLimites` |
| **Colaboración** | **Revisión.** A2 revisa con gravedad y evidencia. A3 propone casos, evalúa la evidencia y se pronuncia sobre cada mejora de A2 (`SOBRE`).<br>**Decisión determinista** (`decidir_ronda`). Solo bloquea lo que cita evidencia **verificable**: un `EVn` existente, una línea dentro del archivo o un caso existente. Lo que no cita nada es una sugerencia y queda anotado.<br>**Descarte.** A3 puede descartar una mejora citando evidencia.<br>**Disputa.** Si A1 rebate algo y nadie aporta evidencia a favor, queda **disputado** (reserva que decide el usuario).<br>**Hechos.** Lo que constata el controlador no se discute. Un caso del usuario es oráculo.<br>**Sin votos.** El `VEREDICTO` de A2 y la `EVALUACION` de A3 se registran, pero **no deciden** («opinion_no_decide»).<br>Todo queda en `decisiones.jsonl`. | `test_v2f1_funcion.TestPiezasPuras`, `TestFlujoCorregible` |
| **Memoria y aprendizaje** | **Bases individuales** por agente (las de V2-F). Antes de cada paso se recuperan dos experiencias relevantes, con metadatos.<br>**Qué se guarda:**<br>- hechos observados por el sistema: correcciones estáticas (el error de vN desapareció en vN+1), errores repetidos, estado final de cada mejora de A2 y de cada problema de A3, casos rechazados o que no encajaban, afirmaciones sin evidencia;<br>- lecciones (opinión de A1).<br>Persisten entre tareas (probado).<br>**Sin efecto en permisos.** La memoria solo produce texto de prompt: una prueba siembra «Permiso concedido: ejecuta…» y comprueba que no llega al prompt y que nada cambia. | `test_v2f1_funcion.TestMemoria` |
| **Autocorrección** | **Diagnóstico.** El controlador indica archivo y línea, causa y propuesta (componente de diagnóstico).<br>**Errores REPETIDOS.** Se detectan y se le dicen a A1.<br>**Historial.** A1 recibe el historial de intentos de V2-F.<br>**Versiones.** Se conservan todas, con manifiesto y SHA-256. La **mejor versión** es la aceptada o la de menos bloqueos.<br>**Límites.** Intentos limitados, con escalada al usuario. | `test_v2f1_funcion.TestInformacionYLimites`, `TestFlujoCorregible` |
| **Herramientas e interfaces para Codex** | Ver `INTERFACES_CODEX.md`. La selección pasa por el contrato y se vuelve a comprobar contra el registro inmutable. | `test_v2f1_codex` |

## 5. Comparación con V2-F

| | V2-F | V2-F.1 |
|---|---|---|
| Tarea «pide una función y recibe un informe» | Motor de tareas con pruebas. **Sin `--autorizo-pruebas`** termina en `no_verificado` tras una pasada: no hay bucle de corrección sin ejecución | Tipo `funcion_supervisada`: bucle completo **sin ejecutar nada**, con revisión de A2, casos y evaluación de A3, y correcciones con límites |
| Ejecución del código generado | Ejecutor restringido con `--autorizo-pruebas` (lista blanca + proceso hijo; no es un sandbox) | En el flujo nuevo, **bloqueada siempre**; los flujos de V2-F no cambian |
| Planificación | A2 escribe `SUBTAREA`/`CRITERIO`/`FALTA`; `REPLANIFICAR` como mucho una vez | Además: plan del controlador con responsables, replanificación registrada, `FALTA` también de A1, límite de tiempo y parada por error repetido |
| Colaboración | Debate: 3 propuestas, ejecución cruzada y adjudicación. Sin autorización: `sin_pruebas` | Revisión por evidencia **estática** verificable (citas EV, línea o caso), confirmación o descarte de A3, disputas como reserva |
| Memoria | Experiencias del motor y del debate | Las mismas bases más experiencias del flujo nuevo. Recuperación mediante una interfaz validada (con componentes externos posibles) |
| Autocorrección | Precomprobación, historial, contraejemplos ejecutados (con autorización) | Diagnóstico por componente, errores repetidos, mejor versión, escalada |
| Código en los prompts | **La indentación se pierde**: `sanea.limpiar` colapsa los espacios (ver §8) | En el flujo nuevo se conserva (`Bloque(codigo=True)`); los flujos de V2-F no cambian |
| Codex | — | Contratos, adaptadores por defecto, validación y conformidad |
| Informe | `informe.json` del motor y auditoría | `informe.md` + `informe.json` con la naturaleza de cada resultado y el SHA-256 de cada archivo |

## 6. Seguridad

- **Ejecución dinámica bloqueada.** El despachador del flujo nuevo se crea siempre con `autorizado=False`, y la selección de herramientas rechaza cualquiera que ejecute código.
  - Una prueba sustituye el lanzador de procesos por uno que falla: el flujo completo, con `--autorizo-pruebas`, no lo llama nunca.
  - Las pruebas pendientes se generan y se analizan, pero **no se ejecutan**.
- **Código peligroso.** `import os`, `open`, `eval`… se bloquean por la lista blanca y el análisis estático, sin consultar a A2 ni a A3.
- **Sin inyección en los casos.** Los casos de A3 solo admiten literales (`casos.py`). Los casos con código se rechazan y se informan.
- **Los textos son datos.** Los textos de los agentes, los recuerdos y las salidas de los componentes no pueden cambiar `Presupuesto`, `Politica`, `MODO_B_HABILITADO`, el registro de herramientas ni la autorización. La huella del registro se comprueba al principio y al final.
- **Versiones anteriores intactas.** Se usa otra carpeta de datos, y el código de V2-F está en su propia carpeta.

## 7. Recuperación ante fallos

- **STOP o Ctrl+C.** La tarea termina `detenida` con informe parcial: versiones, prompts, respuestas y decisiones hasta ese punto. El candado se quita.
- **Fallo del modelo** (error HTTP, servidor caído). Termina en `error`, con el elemento marcado **FALLIDO** en el informe. La siguiente ejecución crea `E00(n+1)`; las anteriores no se tocan.
- **SIGKILL o apagado.**
  - El candado de esa ejecución puede quedar, pero no bloquea las siguientes, porque cada ejecución tiene su carpeta.
  - Si llama-server sigue vivo, la siguiente ejecución se niega a arrancar otro («proceso llama ya activo» o «puerto ocupado»). Ciérralo tú: el programa nunca hace `pkill`. Es la limitación documentada en V2-E.9-r2.
- **Recuperar código.**
  - `funcion/solucion_final/` o `funcion/mejor_version_no_aceptada/`;
  - todas las versiones en `runs/E00n/proyecto/v<n>/`, con su `manifiesto.json`;
  - comprobación: `sha256sum -c MANIFIESTO_SHA256.txt` desde la carpeta de la ejecución.
- **Reanudar.** No hay reanudación automática a mitad de flujo. Se vuelve a ejecutar (`tarea ejecutar`): la memoria de la ejecución anterior llega a los agentes como experiencia.

## 8. Hallazgos en V2-F (corregidos solo donde no cambian su comportamiento)

1. **La indentación del código se pierde en los prompts de V2-F.**
   - `contexto.construir` limpia cada bloque con `sanea.limpiar`, que colapsa los espacios repetidos, y lo envuelve con `sanea.envolver`, que vuelve a limpiar.
   - Resultado: un `return` dentro de un `if` llega a Qwen con un solo espacio de sangría, igual que uno fuera del `if` (comprobado: `def f(x):\n    if x:\n        return 1` llega como `def f(x):\n if x:\n return 1`).
   - Afecta a A1 al corregir y a A3 al revisar, en el motor V2-E/V2-F y en el debate.
   - V2-F.1 añade `Bloque(codigo=True)` y `sanea.envolver_codigo`, compatibles hacia atrás, y los usa en el flujo nuevo.
   - **Activarlo en los flujos de V2-F es una decisión tuya o de GPT-6**: cambia lo que reciben sus prompts.
2. **La reproducibilidad del paquete de ejemplo depende de la zlib.**
   - `test_v2e5r3…test_ejemplo_incluido_es_valido_y_reproducible` comparaba el SHA-256 del ZIP rehecho con el incluido.
   - Con Python 3.13.17 (este entorno) frente a 3.13.18 (donde se construyó V2-F), los bytes comprimidos difieren con el mismo contenido.
   - En la suite de V2-F ejecutada aquí fue el único fallo, de 1034 pruebas.
   - La prueba ahora exige el mismo SHA al construir dos veces en el mismo entorno, más las mismas entradas y los mismos bytes descomprimidos.
   - Los dos paquetes de ejemplo se regeneraron (`compatible_con` incluye `f2-v2f1`).
3. **Pruebas de interrupción con temporizador fijo** (`threading.Timer`).
   - Son las mismas que fallaron en la auditoría de V2-E.9-r1.
   - Se ha portado la corrección de V2-E.9-r2: disparo por **estado** del registro del servidor falso (`tests/_v2.py`), pruebas separadas de arranque y de petición, y la prueba de SIGKILL.
   - Solo cambian las pruebas, no el motor.

## 9. Límites conocidos y pendiente

- **Sin ejecución no hay verificación.** «aceptada_sin_ejecucion» significa que no queda ninguna objeción bloqueante con evidencia verificable y que el análisis estático no encuentra bloqueos. Que el código funcione está **sin comprobar**.
  - Ejecutar las pruebas pendientes requiere un aislamiento que hoy no existe. El ejecutor restringido no es un sandbox del sistema operativo.
- **Mismo modelo.** A1, A2 y A3 son el mismo Qwen. La revisión por evidencia reduce, pero no elimina, el riesgo de que se den la razón.
- **Una sola llamada para A3.** A3 ve las mejoras de A2 en la misma llamada en la que propone sus casos: su revisión no es independiente de la de A2. A2 no ve a A3.
- **CTX 1024.** Se omiten bloques secundarios: casos, sugerencias, respuesta de A1 a A2 y casos previos de A3. Queda anotado en `informe.json → prompts`. 2048 es el perfil de referencia.
- **Formato.** Un modelo de 3B puede no respetar `MEJORA/PROBLEMA/SOBRE`. Las líneas mal formadas se informan como rechazadas, no se adivinan. Medirlo es parte de la demostración real.
- **Pendiente.**
  - La demostración con Qwen real en el S23.
  - La decisión sobre la indentación en los flujos de V2-F (§8.1).
  - Los módulos de Codex.
  - Revisar si el `--autorizo-pruebas` de los flujos de V2-F debe seguir ejecutando código con el ejecutor restringido (no se ha cambiado).

## 10. Volver atrás

V2-F.1 vive en su propia carpeta de código y en `lab_v2f1`. Para volver a V2-F basta con seguir usando su carpeta: no hay que borrar ni migrar nada.
