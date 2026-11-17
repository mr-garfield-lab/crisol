# Personalidad individual de A1, A2 y A3 (V2-E.5-r2)

Módulo **opcional y desactivado por defecto**:
- código: `src/eq2/personalidad.py`;
- gestión: `perfiles.py`;
- elección: `ejecutar_v2.py --modo personalidad`.

**Estado real:**
- Se ha probado **solo en la sandbox Linux**, con un backend **simulado** y con un backend falso marcado como «no simulado» para recorrer el camino de origen `qwen`.
- **Qwen no ha elegido ninguna personalidad todavía.**
- No se ha ejecutado en Termux.

## 1. Qué es y qué no es
- **Es:**
  - un perfil de **estilo de comunicación** y **preferencias no críticas** (tono, verbosidad, formato, ejemplos, explicar el razonamiento, pedir aclaraciones);
  - de 1 a 4 **rasgos** elegidos por el propio agente.
- **No es, y la base lo impide:**
  - permisos;
  - función o rol;
  - políticas de seguridad;
  - límites de recursos;
  - criterios de evaluación;
  - votos.

  El esquema es cerrado. La columna `cambios.campo` solo admite los 7 campos de estilo y preferencias.
- **No tiene efecto en esta versión.** El perfil **no se inyecta** en los prompts de deliberación ni del motor. Lo comprueba `test_la_personalidad_no_cambia_prompts_ni_limites`.
- **Fuera del alcance de esta versión:** avatares, voces, diálogos entre personajes y emociones.

## 2. Elección inicial propia
- **No se imponen rasgos.**
  - El prompt describe solo el **formato** JSON.
  - No sugiere ningún rasgo; una prueba busca en el prompt los rasgos propuestos en el encargo y no aparece ninguno.
  - Sin elección, el agente usa el **perfil base neutral**: sin rasgos, tono neutral, verbosidad 3.
- **Independencia.**
  - Hay una llamada por agente.
  - El prompt de A2 no contiene lo que eligió A1, y lo mismo entre los demás agentes.
  - Si hay reintento, se dicen los **códigos de error**, pero no se reenvía la respuesta anterior.
- **Un solo modelo, en secuencia.**
  - Usa el `llama-server` y el GGUF existentes a través de `Orquestador.run_eleccion_personalidad`.
  - Es la misma sesión que una deliberación: el mismo candado, la vigilancia de memoria y batería, los plazos y la parada por STOP o Ctrl+C.
  - Nunca hay tres copias del modelo.
- **Límites:**

  | Límite | Valor |
  |---|---|
  | Tokens por respuesta | 120 |
  | Llamadas por agente y elección | 2 (1 + 1 reintento) |
  | Llamadas por agente en 24 h | 4 |
  | Longitud de la respuesta | 1500 caracteres |
- **Validación estricta.** La respuesta debe ser **solo** un objeto JSON; se admite una valla ```` ```json ````. Cada rechazo queda registrado con su categoría:

  | Categoría | Ejemplos |
  |---|---|
  | `invalida` | no es JSON; tiene texto alrededor; tipos o rangos erróneos (verbosidad 0 o 6, `"3"`, `true`); rasgo con cifras, signos o demasiado largo; `NaN`; respuesta demasiado larga; llamada fallida |
  | `fuera_del_esquema` | claves desconocidas o que faltan |
  | `contradictoria` | claves duplicadas; rasgo repetido; rasgos opuestos (conciso/detallista, formal/informal…); rasgo contra estilo (conciso con verbosidad ≥ 4, formal con tono cercano…) |
  | `maliciosa` | claves o rasgos que tocan permisos, rol, función, seguridad, modo B, criterios o evaluación; marcas de inyección («ignora las instrucciones», `<\|im_start\|>`…) |

  La lista de opuestos es **heurística y corta**. Las raíces prohibidas pueden rechazar algún rasgo inocente (por ejemplo, «seguro»): se ha optado por ser conservador.
- **Origen claramente separado.** Hay dos almacenes: `personalidad/` (real) y `personalidad_simulada/`.
  - La base **rechaza** una elección `simulado` en el almacén real y una `qwen` en el simulado.
  - El origen `qwen` exige el nombre del modelo.
  - `perfiles.py ver` muestra «SIMULADO (no es de Qwen)» o «QWEN (modelo local, sin verificar)».

## 3. Registro, versiones y aprobación
- **Una elección válida queda `propuesto`.** Solo pasa a `vigente` cuando el **usuario** la aprueba (`aprobar-eleccion`).
  - Un disparador exige un cambio `aplicado` y `decidido_por = 'usuario'` para que cualquier perfil sea vigente.
  - Hay un único perfil vigente por agente.
- **Versiones.**
  - Cada perfil es una versión inmutable (`agente`, `version`, `sha256`, `origen`, `eleccion_num`, `cambio_num`).
  - Las versiones no se borran y su contenido no se modifica.
- **No se repite en cada reinicio.** La elección solo vuelve a hacerse:
  - si el agente **nunca** tuvo perfil;
  - o si el usuario la pide (`nueva-eleccion`).

  Rechazar una propuesta no relanza la elección.
- **Gestión, siempre por el usuario:**
  - `ver`, `versiones`, `elecciones` (respuesta bruta saneada y validación de cada intento), `historial`;
  - `editar` (con la misma validación);
  - `restablecer --a base|inicial`;
  - `revertir` (el último cambio, y solo si el perfil vigente es el que produjo ese cambio).
- **Historial y elecciones son de solo anexar.**

## 4. Experiencias y adaptación gradual
- Las **experiencias** se guardan por agente, con fuente, referencia y estado:
  - **Verificadas:** las aporta el sistema con una referencia comprobable, o el usuario con `anotar --referencia`.
  - **No verificadas:** lo que afirma un agente es *siempre* no verificado (CHECK de la base).
- **Importación desde una deliberación** (`importar --run`): solo hechos que el sistema registró.
  - Una cita no encontrada se registra como `critica_falsa_posible`, que **no** prueba que la crítica sea falsa.
  - También: objeción sin evidencia, formato no reconocido, «aceptada pero no aplicada» y respuesta truncada, atribuidas al agente de la fase.
  - Es idempotente.
  - Lo simulado no entra en el almacén real.
- **Propuestas** (`proponer`): reglas deterministas y **un paso cada vez**. Por ejemplo:
  - 3 respuestas truncadas verificadas: verbosidad −1;
  - 3 preferencias del usuario de más ejemplos: `ejemplos = true`;
  - en A3, 3 críticas sin evidencia: `explicar_razonamiento = true`.

  Reglas de las propuestas:
  - Solo cuentan las experiencias **verificadas**, **del mismo agente** y aún no usadas por otra propuesta (un disparador impide mezclar agentes).
  - Si hay experiencias contradictorias para un mismo campo, no se propone nada.
  - Como máximo 3 pendientes por agente y una propuesta de adaptación cada 24 h.
  - **Nunca se aplican solas:** `aprobar-cambio` o `rechazar-cambio` los decide el usuario. Si el perfil cambió desde la propuesta, aprobarla falla.
  - Los rasgos nunca se proponen automáticamente.
- **Límites de memoria:**
  - 200 experiencias activas por agente; las archivadas no cuentan;
  - 1000 en total por agente (tope duro de la base);
  - 2 MB para toda la base;
  - las experiencias se **archivan**, no se borran.

## 5. Recuperación
- **Base ilegible:** se informa con `DatosCorruptos` y **no se modifica**. Para empezar de cero, el usuario mueve el archivo.
- **Perfil alterado a mano** (SHA-256 distinto o fuera del esquema): se usa el perfil base, se avisa y `verificar` lo informa.
- **Esquema distinto** o etiqueta de almacén alterada: se rechaza.
- **Al abrir la base** se comprueba que existen **todos** los disparadores sobre su tabla. `CREATE TRIGGER IF NOT EXISTS` omite en silencio uno con nombre repetido; ese fallo se encontró al desarrollar los cuadernos.

**Alcance de la garantía:** protege frente a los caminos del sistema y frente al texto del modelo. No protege frente a quien edite a mano el SQLite; eso se detecta pero no se impide.

## 6. Órdenes
```
python3 -B ejecutar_v2.py --modo personalidad_simulada --autorizar-eleccion-personalidad   # sin modelo
python3 -B perfiles.py --simulada ver
# Real (solo con autorización explícita; un llama-server, en secuencia):
python3 -B ejecutar_v2.py --modo personalidad --autorizar-eleccion-personalidad --iniciar-servidor-real [--agente A1]
python3 -B perfiles.py ver
python3 -B perfiles.py elecciones --agente A1        # respuesta de Qwen y su validación
python3 -B perfiles.py aprobar-eleccion --agente A1  # o rechazar-eleccion
```
