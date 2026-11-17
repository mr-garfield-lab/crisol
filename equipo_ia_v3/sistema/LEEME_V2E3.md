# Equipo IA — V2-E.3 (incidencias integradas en el ciclo de A1, A2 y A3) — ENTREGA PARA AUDITORÍA

Versión independiente construida sobre V2-E.2. **V2-E.2 y las versiones anteriores no se han modificado.** Sus huellas SHA-256 coinciden con las de las entregas.
**No se ha ejecutado el modelo real ni nada en Termux con este código.** Todos los resultados proceden de la sandbox Linux, con agentes con guion o `BackendSimulado` (que no es Qwen) y ejecutor simulado.
**Superar estas pruebas no demuestra que el sistema sea seguro.** Solo comprueba las propiedades concretas enumeradas en la sección 9.

## 0. Qué cambia y qué no
- **Integración opcional.** Sin registro de incidencias, `fuente_incidencias` queda en `None` y los prompts son idénticos a los de V2-E.2. Una prueba lo compara byte a byte.
- **Sin llamadas nuevas al modelo.** El bloque de incidencias viaja dentro de las llamadas que ya existían (planificar, generar, revisar, evaluar y corregir). El número de llamadas con registro es igual o menor que sin él, porque el escalado puede acortar la ejecución.
- **Sin cambios en el resto:** el Modo B y la ejecución real siguen deshabilitados; los límites del motor (iteraciones, llamadas, tiempo y memoria) siguen igual; y «verificado» sigue exigiendo pruebas reales.

## 1. Qué recibe cada agente (`motor_incidencias.py`)
El **planificador** (`prioridad.planificar(..., ambito=<incidencias de esta ejecución>)`) se ejecuta tras cada comprobación y decide la ronda.
| Agente | Paso | Recibe |
|---|---|---|
| A2 | evaluar | incidencias **sin causa** o pendientes de **rediagnóstico** (`diagnosticar` / `rediagnosticar`) |
| A1 | corregir | incidencias con causa **confirmada** (`corregir`) o con **hipótesis vigente de A2** (`corregir_con_hipotesis`, marcada como NO confirmada), en orden de prioridad causal |
| A3 | revisar | correcciones **sin verificar**, **intentos recientes de A1** pendientes de comprobar y **bloqueos de A3** pendientes |

- **Lo que no recibe ningún agente:** las incidencias escaladas al usuario; las bloqueadas por otra, que esperan a su bloqueante; y las de otras tareas o ejecuciones, porque el ámbito es solo la ejecución en curso.
- **Diagnósticos de A2:** una línea `DIAGNOSTICO INC-xxxxxx: …` se guarda como **hipótesis**, y la incidencia se vuelve a planificar en el acto para A1. Un `DIAGNOSTICO:` sin identificador solo se asigna si A2 recibió una única incidencia.
- **Intentos de A1:** el de cada corrección se registra en la comprobación siguiente:
  - `supera_simulacion` o `supera_estatico` si el fallo ya no se reproduce (eso **no es verificación**);
  - `sin_efecto` si sigue o si no hubo versión nueva;
  - `pendiente` si no se pudo comprobar.
- **Límites:** con esos intentos funcionan los de V2-E.2 (rediagnóstico, 3 intentos, 8 tareas). Cuando **todas** las incidencias pendientes de la ejecución están escaladas, el motor termina con el nuevo estado final `escalado_al_usuario` en lugar de seguir corrigiendo. Ocurre también en ejecuciones posteriores, por la firma de la incidencia. Solo el usuario lo levanta (`auditar.py desbloquear`).

## 2. Gestión del contexto (`AgentesMotorLLM._pedir`)
1. Se construye **primero** el prompt esencial, exactamente igual que en V2-E.2: instrucciones de seguridad (sistema), instrucción del paso, tarea original, plan, código y diagnóstico.
2. El bloque de incidencias solo puede usar lo que **sobra**, con un tope del 25 % del contexto. Con menos de 1,5 GB de memoria disponible, el tope baja al 12,5 %.
3. Se reconstruye el prompt con el bloque al final, con la menor prioridad. Si cambia cualquier bloque esencial (omitido o recortado) o el propio bloque queda recortado, se **descarta el bloque** y se usa el prompt original. La prueba `test_nunca_desplaza_lo_esencial` lo comprueba en cada llamada: quitando el bloque y su instrucción, el prompt es idéntico al de la ejecución sin registro, con contexto 1024 y 2048.
4. **Cola persistente** (`ColaAgente` y la tabla `entregas`, de solo anexar):
   - lo ya entregado a ese agente en esa ejecución **no se repite**;
   - las evidencias largas se **reparten en fragmentos** (`[CONTINÚA]` / `(cont.)`) entre llamadas;
   - lo pendiente sigue en la base y se entrega en la siguiente llamada del mismo agente;
   - la cabecera compacta, con el respaldo de la causa y los criterios, se repite en cada llamada porque el modelo no recuerda las anteriores.
5. **Registro de lo que recibe cada agente:** se hace en dos fases. `preparar()` no escribe nada, y la entrega solo se registra cuando el agente ha respondido. `auditar.py entregas` muestra qué recibió cada agente, en qué paso y qué fragmento.
6. **Mínimos:** la cola necesita al menos 80 tokens; por debajo no se envía bloque y queda anotado en `incidencias_contexto.sin_espacio`.
   - **Consecuencia observada:** con contexto **1024**, el prompt de corrección de A1 suele estar lleno, así que A1 no recibe el bloque. Sí recibe el diagnóstico de A2, que ya nombra la incidencia.
   - Con **2048**, el valor por defecto del ejecutable, A1 sí recibe el bloque.
7. **Agentes simulados** (`tarea_simulada`): reciben el mismo bloque, con un tope del 25 % del contexto. Como no construyen prompt, no tienen la comprobación del espacio esencial.

## 3. Evidencias y verificación (`incidencias.py`, esquema 2)
- **Niveles de respaldo de la causa:**
  - `sin_causa`;
  - `hipotesis`;
  - `respaldada_estatico`;
  - `respaldada_simulacion`;
  - `confirmada_prueba_real` (inalcanzable: el Modo B está deshabilitado).
- **Dónde aparece:** en la cabecera que reciben los agentes, en el informe (JSON y Markdown) y en `respaldo_de_causas`.
- **Garantías impuestas por la base:**
  - un respaldo exige una evidencia de ese tipo;
  - el respaldo `prueba_real` exige esa prueba;
  - solo puede haber respaldo si la causa está confirmada;
  - `entregas` es de solo anexar.
- **El laboratorio** declara el tipo real de su experimento (estático o simulación) y **nunca** `prueba_real`.
- **Declaraciones de los agentes:** «CORREGIDO / VERIFICADO / RESUELTO / SOLUCIONADO: INC-…» de cualquier agente se guardan **solo como declaración informativa**, y solo para incidencias de la ejecución en curso. Ninguna declaración cambia el estado. Además, la base impide pasar a `corregida_sin_verificar` sin una evidencia no declarativa y a `verificada` sin una prueba real.

## 4. Robustez
- Un fallo de SQLite o de E/S del registro, también durante una llamada a un agente, **no detiene la tarea**: el enlace se desactiva, se anota en `errores` y en `informe["incidencias"]`, y la tarea sigue sin incidencias.
- Una base V2-E.2 (esquema 1) se rechaza. V2-E.3 usa su propia carpeta `datos_v2e3`.
- **No se crean dependencias causales automáticamente:** sin evidencia no hay causalidad.

## 5. Archivos cambiados
- **Nuevos:**
  - `tests/test_v2e3.py` (41 pruebas);
  - `LEEME_V2E3.md`.
- **Cambiados:**
  - `motor.py`: `fuente_incidencias`, `_con_incidencias`, el estado `escalado_al_usuario` y `incidencias_contexto` en el informe;
  - `motor_incidencias.py`: reescrito;
  - `contexto_incidencias.py`: `ColaAgente`, `diagnosticos_de` y declaraciones restringidas a la ejecución;
  - `prioridad.py`: `ambito`, `corregir_con_hipotesis` y `diagnostico_vigente`;
  - `incidencias.py`: esquema 2, `causa_respaldo`, `respaldo()` y `entregas`;
  - `laboratorio.py`: el respaldo declarado;
  - `auditoria.py`: el respaldo y las entregas por agente;
  - `auditar.py`: `entregas` y `desbloquear`;
  - `config.py`, `__init__.py`, `ejecutar_v2.py` y `supervisar.py`: `datos_v2e3` y `VERSION = "f2-v2e3-r1"`.
- **Pruebas heredadas modificadas (CAMBIO V2-E.3), solo por el nombre de la carpeta o la versión:**
  - `test_v2b.test_sin_modelo_no_lanza_nada_y_sale_con_error`;
  - `test_v2d.test_ciclo_simulado`;
  - `test_v2d.test_deliberacion_sin_modelo_usa_datos_v2d_y_sale_con_error`;
  - `test_v2e.test_tarea_simulada_y_supervision`;
  - `test_v2e2.TestCLI.test_recorrido_completo`;
  - `test_v2e2.TestCLI.test_ejecutar_v2_registra_incidencias`;
  - `test_v2e2.TestVersionYCarpetas.test_version_y_carpetas`.

## 6. Defectos encontrados por las pruebas nuevas, ya corregidos
1. **Un fragmento de evidencia podía superar el presupuesto:** con la última evidencia, la nota de pendientes no se reservaba (137 tokens con un presupuesto de 120).
2. **Con presupuestos de 40–60 tokens, la cola no avanzaba nunca:** la cabecera ocupaba todo. Ahora el mínimo es de 80 tokens y la nota se ha acortado.

## 7. Resultados
| Comprobación | Resultado |
|---|---|
| Validador estático | 0 problemas |
| Suite completa **con** `os.link` | **607/607 OK** (566 heredadas de V2-E.2 + 41 nuevas) |
| Suite completa **sin** `os.link` (simulación de Termux, incluidos los subprocesos) | **607/607 OK** |
| Mutaciones de las protecciones nuevas (contra `test_v2e3` + `test_v2e2`) | 36: **35 detectadas**, 1 equivalente |
| V2-B … V2-E.2 sin cambios (`sha256sum -c`) | OK |
| Suite y validador desde el ZIP extraído | ver la respuesta de entrega |

- **Mutación equivalente (M01):** quitar la comparación de bloques esenciales *recortados*. El bloque de incidencias tiene la prioridad más baja, así que si algo esencial se recortara, el propio bloque quedaría omitido, y eso ya se detecta.
- **Las 35 detectadas cubren:**
  - el cálculo del espacio libre y el descarte del bloque;
  - la entrega solo tras la respuesta;
  - el paso del bloque a los agentes simulados;
  - la desactivación del enlace ante un fallo;
  - el escalado que detiene el motor;
  - la deduplicación y las tres reservas de la cola;
  - el mínimo de 80 tokens;
  - las declaraciones limitadas a la ejecución, y que nunca cuenten como evidencia;
  - la regla del diagnóstico único;
  - el ámbito del planificador;
  - `corregir_con_hipotesis` y el reinicio de `diagnostico_vigente`;
  - la revisión de intentos por A3 y los bloqueos de A3;
  - el resultado de los intentos (`sin_efecto` cuando no hay versión nueva o el fallo sigue);
  - la fracción por memoria y el tope de contexto;
  - confirmar las entregas;
  - que un diagnóstico no confirme la causa;
  - la etiqueta de respaldo (incluida una causa confirmada sin texto);
  - los disparadores de respaldo y de `entregas` y el CHECK de respaldo;
  - el reinicio del respaldo al rediagnosticar;
  - el tipo declarado por el laboratorio;
  - el `desbloquear` de la CLI.

## 8. Validación en Termux
```
mkdir -p "$TMPDIR/equipo_f2/codigo_v2e3" && cd "$TMPDIR/equipo_f2/codigo_v2e3"
unzip /ruta/a/equipo_f2_v2e3.zip && cd equipo_f2_v2e3
python3 -B -I validar_estatico.py                                                      # TOTAL problemas: 0
python3 -B -W error::ResourceWarning -X dev -m unittest discover -s tests -p "test_*.py"     # todas OK
python3 -B -W error::ResourceWarning -X dev -m unittest discover -s tests -p "test_v2e3.py"  # solo las nuevas
python3 -B ejecutar_v2.py --modo tarea_simulada     # motor simulado con incidencias integradas
python3 -B auditar.py entregas                      # qué recibió A1, A2 y A3
python3 -B auditar.py listar
python3 -B auditar.py informe                       # columna «Respaldo de la causa»
ls "$TMPDIR/equipo_f2"                              # datos_v2e3 (las carpetas anteriores intactas)
```
Nada de esto inicia `llama-server`, usa la red, instala paquetes ni toca `~/equipo-ia`. La tarea real (`--modo tarea --iniciar-servidor-real`) es la única que usa Qwen. No se ha probado con esta versión.

## 9. Limitaciones conocidas
- **No se ha comprobado con Qwen.** No sabemos si el modelo de 3B respeta el formato `DIAGNOSTICO INC-…` ni si el bloque mejora sus correcciones. Las pruebas usan guiones.
- **Contexto 1024:** A1 casi nunca recibe el bloque (la regla de no desplazar lo esencial tiene prioridad). Con 2048 sí lo recibe.
- **Cabecera repetida:** se reenvía en cada llamada, porque el modelo no conserva memoria; solo se evita duplicar las evidencias.
- **Evidencias largas en poco espacio:** en una ejecución, que tiene pocas llamadas, pueden quedar fragmentos sin entregar. Constan como pendientes en `incidencias_contexto.pendientes_por_agente`.
- **«Corregida» no significa que funcione:** solo que el fallo no se reproduce en simulación o en análisis estático. Ninguna incidencia puede llegar a `verificada`.
- **Escalado entre ejecuciones:** si una incidencia de otra ejecución se escaló por la misma firma (el mismo nombre de prueba), las ejecuciones siguientes de **cualquier** tarea con esa firma terminan en `escalado_al_usuario` hasta que el usuario la desbloquea.
- **Estimaciones provisionales:** los tokens son una estimación (len/3) y los pesos de la prioridad son provisionales.
- **Seguridad no demostrada:** las pruebas cubren las propiedades enumeradas. No hay aislamiento real ni auditoría externa, y el texto de las incidencias, aunque va envuelto como datos no confiables, puede influir en el juicio del modelo.
