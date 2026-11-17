# Equipo IA — V2-E.5: fiabilidad de las deliberaciones y preparación multiplataforma (fase 1)

Construida sobre V2-E.4-r2. **V2-E.4-r2 y las versiones anteriores no se han modificado**: sus huellas SHA-256 coinciden.
- No añade capacidades autónomas.
- El Modo B sigue **deshabilitado** (`MODO_B_HABILITADO = False`).
- **No se ha ejecutado nada en Termux, en Windows ni con el modelo real.** Todos los resultados proceden de la sandbox Linux, con backend y ejecutor **simulados**.

## 1. Qué funciona de verdad y qué es solo diseño
| Parte | Estado |
|---|---|
| Clasificación determinista de críticas, contradicciones, incertidumbre y problemas no resueltos | **Implementada y probada** (sandbox, backend simulado) |
| Aclaración acotada (`--solicitar-evidencia`) | **Implementada y probada** (sandbox, simulada). **Desactivada por defecto.** Sin probar con Qwen. |
| Registro de críticas en las revisiones de A3 del motor | **Implementado** (solo registro; el flujo del motor no cambia) |
| Adaptadores Linux y Termux | **Implementados**: envuelven las mismas funciones de antes; se ha comprobado que dan los mismos resultados |
| Adaptador Windows | **Solo diseño**: lanza `NoSoportado` |
| `auditar.py plataforma` | **Implementado** (solo lectura) |
| Plugins, migraciones, ModLab, AvatarLab, personalidades, GUI | **Solo documentación** (`EXTENSIONES_FUTURAS.md`) |

## 2. Fiabilidad de las deliberaciones (`src/eq2/criticas.py`, nuevo y puro)
Problema observado por el usuario: en la prueba real con Qwen2.5-Coder-3B hubo 7 llamadas y consenso, pero algunas críticas parecían incorrectas.

**Mecanismo:** sin modelo y sin ejecutar código. Solo comprueba **referencias en el texto**.
1. **Clasificación de cada objeción** de A3 (`OBJECION: … | EVIDENCIA: …`):
   - `fundamentada`: la cita (entre comillas o acentos graves, con 4 caracteres como mínimo) aparece literalmente en la propuesta (`codigo`) o en el enunciado (`requisito`), tras normalizar con NFKC, minúsculas y espacios;
   - `cita_no_encontrada`: cita algo que **no existe** en la propuesta ni en el enunciado → **posible crítica falsa**;
   - `linea_inexistente`: «línea N» fuera del código → **posible crítica falsa**;
   - `no_verificable`: hay referencia (un caso de prueba, una línea existente), pero no se puede comprobar en el texto;
   - `sin_evidencia`: no hay evidencia o es demasiado corta.
2. **Resolución** de las objeciones fundamentadas en código. Se compara con la propuesta final y con la respuesta de A1 en la réplica (asociadas por orden):
   - `pendiente`;
   - `rebatida_sin_cambio`, que se anota como incertidumbre;
   - `resuelta_en_texto`: el fragmento citado ya no está. **Eso no demuestra que el problema esté corregido.**
3. **Contradicciones detectadas:**
   - una revisión que dice «SIN OBJECIONES» y además contiene objeciones;
   - A1 dice ACEPTADA pero el fragmento sigue (`replica_acepta_pero_no_aplica`);
   - un agente aprueba con una objeción fundamentada pendiente;
   - A3 aprueba sin que se resuelvan sus propias objeciones;
   - votos opuestos (aprobar y rechazar);
   - en el motor, una versión posterior que omite una objeción fundamentada cuyo fragmento sigue en el código.
4. **Efecto en la fiabilidad.** El recuento de votos **no cambia**.
   - Las contradicciones y las posibles críticas falsas se anotan como **advertencias**.
   - Cuando el resultado es «aprobada» o «aprobada con cambios», dos contradicciones fuertes (aceptada pero no aplicada, y aprobar con una objeción fundamentada pendiente) bajan la fiabilidad a **«reducida»**.
5. **El consenso no es corrección.** Esa nota aparece en:
   - el resultado (`consenso_no_es_correccion: true`);
   - `fiabilidad_json` (SQLite);
   - la cabecera del archivo de propuesta (`CONSENSO: … NO demuestra …`), junto con las líneas `CRITICAS`, `CONTRADICCIONES`, `NO_RESUELTO` e `INCERTIDUMBRE`;
   - el informe de la CLI.
6. **Petición de referencias concretas.** Ocurre en dos niveles:
   - La instrucción de revisión ya pedía `EVIDENCIA`.
   - Con `--solicitar-evidencia`, si hay objeciones sin evidencia o con una cita inexistente, A3 recibe **una** petición de aclaración: debe citar exactamente o escribir `RETIRADA: n`.
     - Solo se aceptan respuestas a las objeciones pedidas; las objeciones nuevas se ignoran y se cuentan.
     - Tiene un máximo de 160 tokens.
     - Si falla, no aborta la tarea: se conserva la revisión original y se anota `aclaracion_no_valida`.
7. **Sin ciclos ilimitados.**
   - Como máximo hay **una** aclaración por tarea, y el tope pasa de 12 a **13** llamadas solo si la opción está activa.
   - Se analizan como mucho 20 objeciones; las restantes se registran como «no analizadas».
   - No hay más rondas de debate.

## 3. Multiplataforma, fase 1 (`PLATAFORMAS.md`)
- `plataforma.auditar_dependencias()` y `auditar.py plataforma`: inventario determinista de las dependencias de rutas, procesos, recursos, servidor y señales.
- `AdaptadorLinux`, `AdaptadorTermux` y `AdaptadorWindows`: un único punto para lo que depende del sistema. **No duplican el núcleo.**
- Único punto del núcleo que ya pasa por el adaptador: la comprobación del candado de sesión (`pid_vivo`).
  - En Linux y Termux, el mismo `/proc` de antes.
  - Si la plataforma no puede comprobarlo, el candado **no** se da por obsoleto.
- **No se declara compatibilidad con Windows ni con un escritorio Linux real.** Fases 2 y 3 en `PLATAFORMAS.md`.

## 4. Protecciones (sin cambios)
- `MODO_B_HABILITADO = False`.
- No se ejecuta código generado.
- `~/equipo-ia` no se toca (solo se lee el GGUF).
- Nada de borrado destructivo, root, ADB, `pkill`, red externa ni APIs de pago.
- Se mantienen la auditoría y los límites de recursos.
- La personalidad (futura) **nunca** modifica permisos: `ConfiguracionModular` rechaza `personalidad`, `avatar` y `gui`, y prohíbe `modo_b`, `ejecucion_real`, `red`, `privilegios` e `instalar_dependencias`.
- Carpeta de datos nueva, `datos_v2e5`, con la sesión en esquema **6** (fase `aclaracion`). Las incidencias siguen en esquema 4. No se escribe en carpetas de versiones anteriores.

## 5. Archivos
- **Nuevos:**
  - `src/eq2/criticas.py`;
  - `tests/test_v2e5.py` (37 pruebas);
  - `EXTENSIONES_FUTURAS.md`;
  - `PLATAFORMAS.md`;
  - `LEEME_V2E5.md`.
- **Modificados:**
  - `orquestador.py`: críticas, aclaración, tope por instancia, cabecera y candado vía adaptador;
  - `plataforma.py`: adaptadores y auditoría;
  - `motor.py`: `criticas_revisiones`, solo registro;
  - `memoria.py`: esquema 6;
  - `config.py`: `MAX_TOKENS_ACLARACION`, `max_tokens_fase`, `LLAMADAS_ACLARACION`, `CARPETA_V2E5`, `CAPS_BLOQUE["aclaracion"]`;
  - `prompts.py`: instrucción de aclaración;
  - `inferencia.py`: fase simulada `aclaracion`;
  - `__init__.py`: `VERSION = "f2-v2e5-r1"`;
  - `ejecutar_v2.py`: `--solicitar-evidencia` e informe de críticas;
  - `auditar.py`: subcomando `plataforma`;
  - `supervisar.py`: carpeta.
- **Pruebas heredadas modificadas** (marcadas `CAMBIO V2-E.5` en el código; **no se ha cambiado ninguna aserción de comportamiento**):
  - esquema 5 → 6: `test_v2c.TestEsquema3.test_esquema_es_el_vigente` y `test_v2d.TestEsquema4.test_esquema`;
  - solo la carpeta y la versión (20 líneas): `test_v2b`, `test_v2d`, `test_v2e`, `test_v2e2`, `test_v2e3`, `test_v2e4` y `test_v2e4r2`.

## 6. Resultados ejecutados (sandbox Linux, Python 3.13; NO en Termux)
| Comprobación | Resultado |
|---|---|
| Validador estático | 0 problemas |
| Suite completa **con** `os.link` | **711/711 OK** (674 heredadas + 37 nuevas) |
| Suite completa **sin** `os.link` (simulación de Termux en la sandbox) | **711/711 OK** |
| Mutaciones de las protecciones nuevas contra `test_v2e5` | **29/29 detectadas**; todos los mutantes compilan |
| V2-B … V2-E.4-r2 sin cambios (`sha256sum -c`) | OK |

**Qué cubren las mutaciones:**
- búsqueda de la cita, línea fuera de rango, código sin comillas, evidencia vacía y normalización;
- la resolución pendiente;
- cada tipo de contradicción;
- la incertidumbre;
- el tope de 20 objeciones;
- la fusión de la aclaración: solo las pedidas y las retiradas;
- la contradicción entre versiones;
- el tope de 13 solo con la opción activa;
- la aclaración solo tras la revisión, solo si hace falta, tolerante a fallos y aplicada a la réplica;
- las advertencias, los motivos fuertes y `consenso_no_es_correccion`;
- el candado con `NoSoportado`;
- `pid_vivo`.

## 7. Validación en Termux
```
mkdir -p "$TMPDIR/equipo_f2/codigo_v2e5" && cd "$TMPDIR/equipo_f2/codigo_v2e5"
unzip /ruta/a/equipo_f2_v2e5.zip && cd equipo_f2_v2e5
python3 -B -I validar_estatico.py                                   # TOTAL problemas: 0
python3 -B -W error::ResourceWarning -X dev -m unittest discover -s tests -p "test_*.py"     # 711 OK esperado
python3 -B -W error::ResourceWarning -X dev -m unittest discover -s tests -p "test_v2e5.py"  # 37 OK esperado
python3 -B auditar.py plataforma        # esperado: "adaptador": "android_termux"; wake_lock según termux-api
ls "$TMPDIR/equipo_f2"                  # datos_v2e5 aparece solo tras una ejecución; las anteriores intactas
# Solo con autorización explícita (modelo real):
python3 -B ejecutar_v2.py --modo deliberacion --iniciar-servidor-real                         # 7 llamadas
python3 -B ejecutar_v2.py --modo deliberacion --iniciar-servidor-real --solicitar-evidencia   # máx. 13
```
En el informe, revisa estas líneas:
- `CRÍTICAS`;
- `posibles críticas falsas`;
- `contradicciones`;
- `problemas no resueltos`;
- `aclaración de evidencia`;
- `NOTA`.

Revisa también la cabecera de `datos_v2e5/runs/<run>/propuestas/*.txt`.

## 8. Riesgos y limitaciones
- **«Fundamentada» solo significa que la cita existe**, no que la objeción sea correcta. Una crítica verdadera sin cita queda como `sin_evidencia` y se anota como incertidumbre; **no se descarta**.
- **Una cita inexistente es una *posible* crítica falsa.** El modelo puede parafrasear algo que sí existe.
- **`resuelta_en_texto` puede ser falsa:** el fragmento cambió, pero el fallo puede seguir con otra forma.
- **Las respuestas de la réplica se asocian a las objeciones por orden.** Si A1 se salta una, la asociación se desplaza (esto solo afecta a las contradicciones de «aceptada pero no aplicada»).
- **Sin datos reales.** No se sabe con qué frecuencia Qwen2.5-Coder-3B sigue el formato `OBJECION | EVIDENCIA`. Si no lo sigue, la mayoría de las objeciones serán `sin_evidencia`. Hay que calibrarlo con ejecuciones reales.
- **Coste de la aclaración.** Añade una llamada (latencia y batería) y tiene el presupuesto de tokens más bajo (160). Su utilidad con el modelo real no está medida.
- **Multiplataforma.** Solo el candado pasa por el adaptador. `llama_activo`, el wake lock, el comando del servidor, la raíz temporal y la vigilancia siguen con llamadas directas (fase 2). Windows no funciona.
- **Riesgos que siguen abiertos:**
  - las limitaciones heredadas (`LEEME_V2E4.md` §10–11 y `LEEME_V2E4R2.md` §8);
  - el fallo intermitente sin explicar de `test_stop_durante_la_tarea`, dependiente del reloj; no ha aparecido en estas pasadas;
  - la última validación del usuario en Termux es la de V2-E.1.

## 9. Propuesta de siguiente etapa (V2-E.6, pequeña)
1. **Validación real en Termux de V2-E.5**, con autorización:
   - la suite, más tres deliberaciones con la misma tarea, con y sin `--solicitar-evidencia`;
   - guardar las revisiones de A3 y etiquetar a mano cada objeción como correcta o incorrecta;
   - medir la precisión de `posible crítica falsa` y de `fundamentada`.
2. **Calibración mínima** a partir de esos datos (solo si los datos lo justifican):
   - ajustar `MIN_CITA`, los patrones de evidencia o la instrucción de revisión;
   - nada de nuevos agentes ni de rondas.
3. **Multiplataforma, fase 2:**
   - pasar por el adaptador `servidor.llama_activo`, `wake_lock`, el comando del servidor, la raíz temporal y la vigilancia, con pruebas de equivalencia como las de la fase 1;
   - después, el usuario ejecuta la suite en un escritorio Linux real.
4. **Windows (fase 3)** queda para después, cuando la fase 2 esté validada en Linux.
