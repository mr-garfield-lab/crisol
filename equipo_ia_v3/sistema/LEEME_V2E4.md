# Equipo IA — V2-E.4 (ciclo completo de investigación de incidencias) — ENTREGA PARA AUDITORÍA

> **Revisión r2:** este documento describe V2-E.4 r1. La revisión r2 (`LEEME_V2E4R2.md`) cierra los caminos por los que una causa podía confirmarse con una sola reproducción y convierte los tipos especializados en simples declaraciones. Las afirmaciones de r1 que r2 sustituye están marcadas con **[sustituido en r2]**.

Versión independiente construida sobre V2-E.3. **V2-E.3 y las versiones anteriores no se han modificado.** Sus huellas SHA-256 coinciden con las de las entregas.
**No se ha ejecutado el modelo real ni nada en Termux con este código.** Todos los resultados proceden de la sandbox Linux, con agentes con guion o `BackendSimulado` (que no es Qwen) y ejecutor simulado.
**Ningún resultado de este documento es una ejecución real de código generado.** Superar las pruebas no demuestra que el sistema sea seguro ni que una corrección funcione.

## 1. Qué se ha cerrado
Ciclo: **detección → registro → priorización → diagnóstico → experimento → evaluación de las evidencias → propuesta de corrección → revisión → regresión → seguimiento**. Funciona dentro del motor sin llamadas manuales y se detiene, correctamente, cuando faltan pruebas.

| Paso | Quién | Dónde |
|---|---|---|
| Detección y registro | motor | `motor_incidencias.al_comprobar` (V2-E.2) |
| Priorización y asignación | planificador | `prioridad.planificar` (V2-E.2/3) |
| Diagnóstico | A2 | `DIAGNOSTICO INC-…:` (hipótesis libre) y **`HIPOTESIS INC-…: ARCHIVO <ruta> PATRON <texto>`** (hipótesis localizada, nueva) |
| Experimento | laboratorio | `investigacion.Investigador`: **reproducción** en la versión que falla; **control** en una versión posterior que ya no falla |
| Evaluación | laboratorio | consistente / respaldada / refutada / ambigua (ver la sección 2) |
| Propuesta de corrección | A1 | recibe la incidencia, sus hipótesis con su estado y las evidencias de los experimentos |
| Revisión | A3 | recibe el intento de A1 y sus evidencias; su revisión queda en la tabla `revisiones` |
| Regresión | laboratorio | solo con la hipótesis respaldada y la causa confirmada; una por experimento de origen |
| Seguimiento | laboratorio | en cada versión nueva; si el patrón vuelve, hay evidencia fallida y la incidencia se reabre |

## 2. Política de evidencias (decisión técnica principal)
Un experimento aislado con una regla «si el archivo contiene X, la prueba falla» solo comprueba lo que la propia regla supone. **Por eso, en el ciclo automático, un experimento no basta.**
- **Reproducción refuta** (el patrón no está donde falla): la hipótesis queda **refutada** y su causa se retira.
- **Reproducción apoya, sin control**: queda **consistente**, sin confirmar. La incidencia sigue pendiente.
- **Control refuta** (el patrón sigue donde ya no falla): queda **refutada**.
- **Reproducción y control apoyan, y es la única hipótesis en ese caso**: queda **respaldada**. Entonces:
  - la causa se confirma con respaldo «**simulación**» (correlación entre versiones; no causalidad ni funcionamiento real);
  - se crea la regresión.
- **Dos o más hipótesis respaldadas a la vez**: todas quedan **ambiguas**, la causa vuelve a hipótesis y no se elige ninguna.
- **Una hipótesis respaldada que una versión posterior contradice**: queda **refutada**, la causa se retira y su regresión deja de aplicarse.

**Garantías impuestas por la base** (esquema 3):
- `respaldada` exige un experimento de reproducción **y** otro de control completados que la apoyen;
- una hipótesis nace `propuesta` y, una vez `refutada`, no vuelve atrás;
- un experimento terminado no se puede modificar ni borrar;
- las hipótesis y las revisiones no se borran.

**Trazabilidad:** cada evidencia guarda la incidencia, el experimento o la regresión, el tipo (estático, simulado o real), el resultado, la hipótesis evaluada, la versión, la confianza, las limitaciones, la fecha y el actor.

**Ficha** (`RegistroIncidencias.ficha` / `etiqueta`): distingue *detectada · causa hipotética · causa respaldada · corrección propuesta · corrección revisada · comprobada con las pruebas disponibles · pendiente de validación real*. Las fases se miden desde la última reapertura. Nunca aparece «corregida» sin decir con qué se comprobó; por ejemplo: «corregida_sin_verificar · … · **comprobada solo con: simulación** · validación real: **pendiente (Modo B deshabilitado)**».

**[sustituido en r2]** ~~El camino manual de V2-E.2 (`Laboratorio.confirmar_causa_con`) se mantiene por compatibilidad: confirma con una sola reproducción.~~ En r2 ningún camino confirma sin una hipótesis respaldada (ver `LEEME_V2E4R2.md`).

## 3. Robustez y recuperación
- **Idempotencia:**
  - los experimentos tienen `firma` única: reintentar devuelve el mismo, y uno que quedó `planificado` se **reanuda**;
  - la evidencia de un experimento no se duplica;
  - las regresiones son únicas por experimento de origen, y si el archivo `.json` se perdió se regenera;
  - las hipótesis son únicas por (incidencia, archivo, patrón);
  - las revisiones son únicas por (ejecución, incidencia, versión).
- **Orden seguro ante interrupciones:** primero se guarda la evidencia y después se cierra el experimento. Si el proceso muere en medio, el experimento sigue `planificado` y se completa sin duplicar.
- **Aislamiento de fallos:**
  - un fallo de SQLite o de E/S **en la investigación** la desactiva para el resto de la ejecución, sin detener la tarea ni el resto del registro;
  - un fallo **del registro** desactiva el enlace, como en V2-E.3.
- **Corrección que arregla un fallo y provoca otro:** la incidencia nueva queda unida a la anterior por una dependencia `relacionada` con certeza `hipotesis`, más una observación. **Nunca** se crea una dependencia causal automáticamente.
- **Respuestas vacías o inválidas:**
  - las líneas `HIPOTESIS` con ruta no válida, patrón vacío o incidencia no recibida se rechazan con su motivo, sin llegar a la base;
  - una respuesta vacía no rompe el ciclo.
- **Corrección del motor encontrada en esta versión:** la detección de «sin progreso» comparaba la lista **ordenada** de estados de los criterios. Al pasar de «C1 falla, C2 pasa» a «C1 pasa, C2 falla», concluía «mismo fallo» y se detenía. Ahora compara cada criterio con su identificador. Ninguna de las 607 pruebas anteriores cambia por ello.

## 4. Presupuesto y control de ciclos
`investigacion.PresupuestoInvestigacion`, configurable con `Motor(..., presupuesto_investigacion=...)` y acotado por los máximos duros de `config.INVESTIGACION_MAXIMOS`.
| Límite | Por defecto | Máximo duro |
|---|---|---|
| hipótesis por incidencia | 3 | 5 |
| experimentos por incidencia (todas las ejecuciones) | 6 | 10 |
| experimentos por ejecución | 12 | 20 |
| regresiones por incidencia | 2 | 3 |
| segundos de investigación por ejecución | 30 | 120 |

- **Al alcanzar un límite:** queda una evidencia `registro` («límite de investigación: …»), la incidencia **sigue pendiente** y el motivo aparece en `incidencias_contexto.investigacion.limites_alcanzados`.
- **Otros límites, sin cambios:** intentos (3), tareas por incidencia (8), rediagnósticos (1), llamadas, tiempo, memoria y tokens del motor; el bloque de incidencias no supera el 25 % del contexto. El escalado al usuario (`escalado_al_usuario`) corta el bucle «diagnosticar → corregir → volver a diagnosticar».

## 5. Laboratorios especializados (base del futuro ModLab)
**[sustituido en r2]** En r2 el registro es **solo declarativo**: las funciones de un tipo son código no confiable y no se invocan nunca. Planificar o ejecutar un tipo especializado se rechaza. Lo que sigue describe r1.

`laboratorio.registrar_tipo(TipoExperimento(nombre, tipo_evidencia, validar, correr, especialidad=…))` añade un tipo de experimento **sin tocar el motor**.
- **Se rechaza** todo tipo que declare `ejecuta_codigo` o `usa_red`, que produzca evidencia distinta de `analisis_estatico` o `simulacion`, o que tenga un nombre repetido o inválido.
- **Los resultados** usan el mismo vocabulario cerrado de expectativas.
- **Lo que no hay:** analizadores de juegos, simuladores de FPS ni ejecución de mods. Una prueba registra un tipo de ejemplo (`conteo_patrones`) para comprobar la interfaz.
- **Limitación:** el registro **declara** las propiedades; no puede impedir que un tipo de terceros mal escrito ejecute código. Cada tipo futuro necesitará su propia revisión y sus pruebas.

## 6. Cómo se garantiza que el modo real sigue deshabilitado
1. `config.MODO_B_HABILITADO = False`. Una prueba recorre con `ast` todo `src/eq2`, `auditar.py` y `ejecutar_v2.py`, y comprueba que esa constante solo se asigna en `config.py` y solo a `False`.
2. `registrar_evidencia(..., "prueba_real", ...)` lanza `PermisoDenegado` para cualquier actor mientras el Modo B esté deshabilitado. Sin evidencia `prueba_real`, la base impide el estado `verificada` y el respaldo `prueba_real`.
3. El laboratorio nunca declara `prueba_real`. Los tipos especializados no pueden producirla.
4. El motor rechaza cualquier resultado «real» que no venga del ejecutor aislado autorizado (sin cambios desde V2-E).
5. Un gancho de auditoría de Python comprueba, durante ciclos completos, que no hay `exec`, subprocesos, red ni `ctypes`. Los experimentos son reglas sobre texto.
6. `ConfiguracionModular` (V2-E.2) no puede activar la ejecución real.

Es una defensa en profundidad comprobada por pruebas, **no una demostración formal de seguridad**.

## 7. Archivos
- **Nuevos:**
  - `src/eq2/investigacion.py`;
  - `tests/test_v2e4.py` (42 pruebas);
  - `LEEME_V2E4.md`.
- **Modificados:**
  - `incidencias.py`: esquema 3, hipótesis, revisiones, trazabilidad, `ficha`, `etiqueta` y `retirar_causa`;
  - `laboratorio.py`: tipos registrables, experimentos idempotentes y reanudables, regresión idempotente;
  - `motor_incidencias.py`: investigación, revisión de A3, efectos secundarios y versión en las evidencias;
  - `motor.py`: texto de la versión, `presupuesto_investigacion` y la corrección de «sin progreso»;
  - `contexto_incidencias.py`: hipótesis en la cabecera;
  - `prioridad.py`: `causa_retirada`;
  - `auditoria.py`: fase, etiqueta, hipótesis y revisiones;
  - `auditar.py`: `demo-ciclo`, `hipotesis` y `ver` con ficha;
  - `config.py` y `__init__.py`: `datos_v2e4`, `VERSION = "f2-v2e4-r1"` e `INVESTIGACION_MAXIMOS`;
  - `ejecutar_v2.py` y `supervisar.py`: la carpeta.
- **Pruebas heredadas modificadas (CAMBIO V2-E.4), solo por la carpeta, la versión o el número de esquema:**
  - `test_v2b.test_sin_modelo_no_lanza_nada_y_sale_con_error`;
  - `test_v2d.test_ciclo_simulado`;
  - `test_v2d.test_deliberacion_sin_modelo_usa_datos_v2d_y_sale_con_error`;
  - `test_v2e.test_tarea_simulada_y_supervision`;
  - `test_v2e2.TestCLI.test_recorrido_completo`;
  - `test_v2e2.TestCLI.test_ejecutar_v2_registra_incidencias`;
  - `test_v2e2.TestVersionYCarpetas.test_version_y_carpetas`;
  - `test_v2e3.TestCLI.test_tarea_simulada_entregas_y_desbloqueo`;
  - `test_v2e3.TestVersion.test_version_y_esquema`.

## 8. Resultados ejecutados
| Comprobación | Resultado |
|---|---|
| Validador estático | 0 problemas |
| Suite completa **con** `os.link` | 649 pruebas (607 heredadas + 42 nuevas): **OK en 3 de 4 pasadas**; ver la nota |
| Suite completa **sin** `os.link` (simulación de Termux, incluidos los subprocesos) | **649/649 OK** |
| Mutaciones de las protecciones nuevas (contra `test_v2e4` + `test_v2e3` + `test_v2e2`) | **35/35 detectadas** (dos sobrevivieron en la primera ronda; se añadieron sus pruebas y se repitieron) |
| Demo `auditar.py demo-ciclo` | recorre todo el ciclo y, en la segunda ejecución, el seguimiento detecta que el patrón vuelve |
| V2-B … V2-E.3 sin cambios (`sha256sum -c`) | OK |
| Suite y validador desde el ZIP extraído | ver la respuesta de entrega |

**Nota sobre el fallo intermitente:** en una de las cuatro pasadas con `os.link` falló **una** prueba heredada de V2-E, `test_v2e.TestMotorServidorFalso.test_stop_durante_la_tarea`.
- **Qué hace:** crea el archivo STOP con un temporizador de 1 s mientras el servidor falso tarda 0,4 s por llamada, así que depende del reloj. Además, **no usa el registro de incidencias**.
- **Reproducción:** no se ha reproducido en 20 ejecuciones posteriores (8 aisladas y 12 de la clase completa, 6 en V2-E.4 y 6 en V2-E.3) ni en otras dos pasadas completas.
- **Estado:** no se ha identificado la causa. Se documenta como **intermitente y sin explicar**, no como resuelto. Si aparece en Termux, conviene enviar el mensaje completo.

## 9. Validación en Termux
```
mkdir -p "$TMPDIR/equipo_f2/codigo_v2e4" && cd "$TMPDIR/equipo_f2/codigo_v2e4"
unzip /ruta/a/equipo_f2_v2e4.zip && cd equipo_f2_v2e4
python3 -B -I validar_estatico.py                                                      # TOTAL problemas: 0
python3 -B -W error::ResourceWarning -X dev -m unittest discover -s tests -p "test_*.py"     # todas OK
python3 -B -W error::ResourceWarning -X dev -m unittest discover -s tests -p "test_v2e4.py"  # solo las nuevas
python3 -B auditar.py demo-ciclo            # ciclo completo, TODO SIMULADO
python3 -B auditar.py hipotesis             # hipótesis y sus experimentos de reproducción y control
python3 -B auditar.py ver INC-000001        # ficha: qué se comprobó y con qué
python3 -B auditar.py regresiones
python3 -B auditar.py informe               # sección «Qué se comprobó realmente»
python3 -B ejecutar_v2.py --modo tarea_simulada
ls "$TMPDIR/equipo_f2"                      # datos_v2e4 (las carpetas anteriores intactas)
```
Nada de esto inicia `llama-server`, usa la red, instala paquetes ni toca `~/equipo-ia`.

## 10. Limitaciones conocidas
- **No se ha comprobado con Qwen.** No sabemos si el modelo de 3B escribirá `HIPOTESIS … ARCHIVO … PATRON …` con un patrón exacto. Si no lo hace, el ciclo se queda en «causa hipotética» (es correcto, pero no avanza).
- **«Respaldada» es una correlación textual entre versiones**, no causalidad: con pocas versiones, una coincidencia puede respaldar una hipótesis equivocada. Por eso se llama «respaldada por simulación» y la validación real sigue pendiente.
- **El control necesita una versión posterior sin el fallo.** Si A1 nunca lo corrige en simulación, la hipótesis queda «consistente» para siempre.
- **Las observaciones viven en memoria durante una ejecución:** el texto de cada versión. Tras un reinicio, la investigación continúa con las versiones de la nueva ejecución. Las hipótesis, experimentos, evidencias y regresiones sí persisten, y la reproducción de una versión idéntica se reutiliza.
- **Seguimiento limitado:** solo se aplica a las incidencias de la ejecución en curso.
- **Escrituras parciales con SQLite lleno:** las filas pequeñas aún pueden caber en páginas con hueco. Las pruebas comprueban que, aun así, nada se afirma sin su evidencia.
- **Lo heredado sigue igual:** la cabecera se repite en cada llamada, los tokens se estiman, los pesos de la prioridad son provisionales y, con contexto 1024, A1 casi nunca recibe el bloque.

## 11. Riesgos pendientes
- **[resuelto en r2]** ~~Camino manual más débil: `confirmar_causa_con` confirma con una sola reproducción.~~
- **Tipos especializados de terceros:** la interfaz no puede verificar que no ejecuten código. Cada tipo de ModLab necesitará revisión y pruebas antes de registrarse.
- **El texto de las incidencias y de las hipótesis puede influir en el modelo,** aunque viaje marcado como datos.
- **Sin aislamiento real (Modo B):** «corregida» significa «no se reproduce en simulación».
- **La firma por nombre de prueba** puede mezclar tareas distintas que usan una prueba con el mismo nombre (escalado y seguimiento).
