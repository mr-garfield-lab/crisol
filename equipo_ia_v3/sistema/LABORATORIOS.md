# Laboratorios individuales de A1, A2 y A3 (V2-E.5-r2)

Código: `src/eq2/laboratorios.py`. Lectura: `python3 -B auditar.py cuaderno [--agente A1]`.

Estado real:
- Se ha probado **solo en la sandbox Linux**, con experimentos **simulados**.
- **El motor y la deliberación todavía no escriben en los cuadernos de forma automática.** La API está lista y probada; integrarla en el flujo es un paso posterior.

## No es un sistema paralelo
- Los cuadernos viven en la **misma** `incidencias.db`, con claves foráneas a `incidencias`, `hipotesis` y `experimentos`.
- Se añaden **dos tablas** (`cuaderno` e `intercambios`) con su propia marca `esquema_cuaderno = 1`.
- El esquema 4 de incidencias **no cambia**.
- Las tablas se crean solo cuando se usa un cuaderno; una deliberación normal no las crea.

## Espacio lógico por agente
| Agente | Tipos de entrada | Ayudas |
|---|---|---|
| A1, programación | `solucion`, `alternativa`, `candidata`, `comparacion_correcciones` | `registrar_solucion`, `registrar_alternativa`, `nueva_version` (sustituye sin borrar), `comparar_correcciones` (diff y SHA-256, sin tocar los originales) |
| A2, análisis | `investigacion`, `causa_raiz`, `evidencia_analisis`, `comparacion_explicaciones` | `investigar`, `proponer_causa_raiz`, `comparar_explicaciones` (hipótesis de V2-E.4 con sus reproducciones y controles; «respaldada» no es causa demostrada) |
| A3, verificación | `caso_prueba`, `regresion_propuesta`, `objecion`, `contradiccion`, `evaluacion_pendiente` | `preparar_caso`, `registrar_objecion` (clasificada con `criticas.clasificar`), `registrar_contradiccion`, `pendientes` |

**Comunes a todos los agentes:**
- `entradas`;
- `entrada`, que lanza `AccesoDenegado` si no es propia ni compartida;
- `recibidas`;
- `versiones`;
- `comparar`;
- `anotar_resultado_de_experimento`, que guarda los resultados simulados, **positivos y negativos**;
- `verificar_integridad`.

## Reglas impuestas por la base
- **Solo anexar.** Las entradas y los intercambios no se modifican ni se borran: una versión nueva **sustituye** a otra del mismo agente y tipo.
- **Escritura propia.** Un agente solo escribe en su cuaderno y solo con respaldo `declaracion_agente`.
- **Simulación.** El respaldo `simulacion` exige un experimento **completado** y lo escribe el laboratorio o el motor. No existe `prueba_real`.
- **Aislamiento.** Un agente solo lee o relaciona entradas propias o **compartidas por el coordinador** (`Coordinador.compartir`, con un motivo obligatorio; cada entrada se comparte una sola vez con cada destinatario).
- **Coherencia.** Una hipótesis citada debe pertenecer a la incidencia citada.
- **Límites:**

  | Límite | Valor |
  |---|---|
  | Entradas por agente | 500 |
  | Caracteres por entrada | 4000 (se rechaza; no se recorta en silencio) |
  | Caracteres por título | 200 |
  | Intercambios | 300 |
  | Escrituras por cuaderno y proceso | 100 |
- **Recuperación.**
  - Una base corrupta se informa y no se sobrescribe.
  - Un contenido alterado a mano se detecta por su SHA-256.
  - Se comprueba que existen todos los disparadores sobre su tabla. Un nombre repetido con un disparador heredado (`int_no_borrar`, de la tabla `intentos`) dejaba los intercambios sin protección de borrado. Se detectó en las pruebas, se renombró y ahora se verifica al abrir.

**Alcance:** las mismas garantías y el mismo límite que el resto del registro. No protege frente a quien edite el SQLite a mano; eso se detecta pero no se impide.

## Ampliación V2-E.5-r3 (esquema del cuaderno 2)
- **Tipos comunes** a los tres agentes:
  - `hipotesis`;
  - `decision` (historial de decisiones: es una declaración, no demuestra que la decisión sea correcta);
  - `aprendizaje`.
- **Aprendizajes sustentados.** Un `aprendizaje` exige, por disparador, apoyarse (`relacionada`) en una entrada **visible** con respaldo del sistema: `simulacion`, `analisis_estatico` o `registro`. Una declaración de otro agente, o una propia, no basta. El contenido recuerda que se basa en un resultado simulado o estático, **no** en una prueba real.
- **`Coordinador.comparar([incidencia])`** compara los cuadernos **sin compartir nada** y detecta desacuerdos deterministas:

  | Desacuerdo | Cuándo |
  |---|---|
  | `resultados_opuestos` | mismo experimento o hipótesis, «positivo» frente a «negativo», entre agentes distintos |
  | `solucion_con_objecion_pendiente` | A1 da una solución por positiva mientras A3 mantiene una objeción pendiente |
  | `hipotesis_distintas` | causas o hipótesis con hipótesis registradas diferentes para la misma incidencia |
  | `decisiones_divergentes` | decisiones distintas sobre la misma entrada |

  Un desacuerdo **no** indica quién tiene razón. Las versiones sustituidas no cuentan.
- **Compatibilidad.** Un cuaderno con el esquema 1 se rechaza. Es la carpeta nueva `datos_v2e5r3`: no se mezcla con r2.

## V2-E.6: esquema de cuaderno 3
- **Artefactos** (`artefactos`):
  - Son textos con SHA-256, versiones (`sustituye`), procedencia y espacio (`A1`/`A2`/`A3` o `comun`, de solo lectura para todos).
  - Hay un máximo de 50 por espacio. Una alteración manual se detecta al leer.
- **Evidencia citada:**
  - `evidencia_citada`, `contraejemplo` y `perfilado_estatico` exigen fuente y líneas; lo impone la base.
  - Si la fuente es un artefacto (`AR-…`), se comprueba que sea visible, que las líneas existan y que la cita aparezca LITERALMENTE.
- **Falsación:** `hipotesis_competidora` y `falsacion` exigen una condición de falsación.
- **Rechazo y abstención:** `rechazo` y `abstencion` deben estar razonados, y el rechazo debe ir referido a lo que rechaza.
- **Comprobaciones declarativas:**
  - `comprobacion_declarativa` admite `contiene`, `no_contiene`, `cuenta_regex`, `lineas_existen` y `cita_literal`.
  - Las evalúa el LABORATORIO (procedencia `laboratorio`), nunca el agente.
- **Pendientes del coordinador** (`pendientes`):
  - Estados: propuesta → cambios_solicitados → aplicado / no_aplicado → verificado / no_verificable / rechazado_justificado.
  - La base impone las transiciones.
  - «verificado» exige una comprobación positiva del sistema relacionada con ESA propuesta.
  - `desde_deliberacion()` lleva `aprobada` → propuesta, `aprobada_con_cambios` → cambios_solicitados y `rechazada` → rechazado_justificado. **El consenso nunca es «verificado».**
- **Tipos nuevos:**
  - A1: `parche_texto`, `contrato`, `prueba_propuesta`, `supuesto`, `riesgo`.
  - A2: `perfilado_estatico`, `hipotesis_competidora`, `solicitud_datos`, `evidencia_citada`.
  - A3: `contraejemplo`, `comprobacion_declarativa`, `falsacion`, `rechazo`, `abstencion`.
- **Código:** soluciones, parches y contratos conservan la indentación (`sanea.limpiar_codigo`).
