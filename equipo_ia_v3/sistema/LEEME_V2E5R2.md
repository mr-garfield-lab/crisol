# Equipo IA — V2-E.5-r2: corrección del falso positivo, críticas medidas, laboratorios individuales y bases de personalidad

Copia independiente construida sobre V2-E.5. **V2-E.5 y las versiones anteriores no se han modificado**: sus huellas SHA-256 coinciden.
- El Modo B sigue **deshabilitado**.
- No se ejecuta código generado.
- No hay dependencias nuevas: solo la biblioteca estándar.
- **No se ha ejecutado nada en Termux, en Windows ni con Qwen.** Todos los resultados proceden de la sandbox Linux, con backends simulados.

## 1. Qué funciona de verdad y qué es solo diseño
| Parte | Estado |
|---|---|
| Corrección del falso positivo de Pillow | **Hecha y probada** (proceso aislado, controles positivos) |
| Tolerancia a formatos inesperados en las revisiones | **Implementada y probada** |
| Corpus etiquetado e informe comparativo de críticas | **Implementado.** 18 casos escritos a mano; **no** son salidas de Qwen |
| Cuadernos de A1, A2 y A3 sobre `incidencias.db` | **Implementados y probados (API).** El motor y la deliberación **aún no** escriben en ellos de forma automática |
| Elección de personalidad por cada agente | **Implementada.** Probada con backend **simulado** y con uno falso «no simulado»; **Qwen no la ha ejecutado**. **Desactivada por defecto** |
| Gestión del perfil, experiencias, propuestas graduales, aprobación y reversión | **Implementadas y probadas** |
| Uso del perfil en los prompts | **No implementado** (deliberadamente): el perfil no tiene efecto todavía |
| Adaptación automática, avatares, voces, diálogos y emociones | **No implementados** |
| Windows 10/11 y escritorio Linux | Sin cambios: siguen siendo diseño o sandbox (`PLATAFORMAS.md`) |

## 2. Corrección del falso positivo (`test_ningun_modulo_visual_se_carga`)
- **Causa.** La prueba de V2-E.5 miraba **todo** `sys.modules`. Si el entorno ya tenía Pillow cargado (p. ej. por un `sitecustomize`), acusaba al núcleo. `test_el_metodo_de_v2e5_daba_el_falso_positivo` lo reproduce.
- **Corrección.** Solo se ha tocado la prueba; el núcleo no cambia. El nuevo `tests/_sondeo_importaciones.py`:
  1. se ejecuta en un proceso aislado (`-I`);
  2. toma una **foto de `sys.modules` antes** de importar `eq2`;
  3. solo atribuye a Equipo IA los módulos gráficos que aparecen **después**.
- **Controles:**
  - un módulo precargado no se cuenta;
  - una importación gráfica **nueva** sí se detecta (paquetes falsos `PIL` y `pygame`);
  - un submódulo nuevo (`PIL.Image`) se detecta aunque el paquete estuviera precargado;
  - un módulo del núcleo que no se puede importar se informa, no se oculta.

## 3. Fiabilidad de las críticas
- **Formatos tolerados.** Tolerancia acotada y registrada, sin heurísticas semánticas:
  - «OBJECIÓN» con tilde;
  - «Objection» en inglés;
  - negritas, viñetas y `#`;
  - evidencia tras `;`, `—` o `(evidence: …)`, o en la línea siguiente;
  - «no hay objeciones» y «no objections».
- **Formato de la revisión.** Cada revisión informa `formato_revision` (`estandar` | `tolerado` | `no_reconocido` | `vacia`). Una revisión no reconocida o vacía es **incertidumbre**, nunca aprobación.
- **Requisito rebatido.** Una objeción que cita literalmente el **requisito** y que A1 rebate sin cambiar nada queda como `requisito_rebatido`:
  - se anota como incertidumbre;
  - avisa si A3 aprueba igualmente.

  Es la misma regla que ya existía para el código.
- **Informe comparativo.** `auditar.py informe-criticas [--json] [--casos ARCHIVO.json]` compara la clasificación automática con la **corrección conocida** de cada caso.
  - **Por objeción:**
    - aciertos;
    - `falsa_no_detectada`: cita real, crítica falsa;
    - `verdadera_marcada_falsa`: cita parafraseada;
    - casos sin confirmar.
  - **Por deliberación:**
    - `alerta_justificada`;
    - `incorrecta_sin_alerta`: consenso erróneo no detectado;
    - `falsa_alarma`;
    - `correcta_sin_alerta`.
  - **Contradicciones:** reales o detectadas.
  - **Casos propios.** `--casos` admite casos etiquetados por el usuario, por ejemplo revisiones reales de Qwen, con el mismo formato y validación estricta.
- **Resultado sobre el corpus incluido** (es una línea base reproducible, **no** una medida de calidad):

  | Medida | Resultado |
  |---|---|
  | Objeciones | 6 fundamentadas correctas, 2 falsas detectadas, **2 falsas con cita real no detectadas**, **1 verdadera marcada como falsa**, 1 verdadera sin confirmar, 1 sin verdad conocida |
  | Deliberaciones | 3 alertas justificadas, **4 soluciones incorrectas sin alerta**, **4 falsas alarmas**, 7 correctas sin alerta |
  | Contradicciones | 5 reales detectadas, 0 reales sin detectar, 2 detectadas sin contradicción real |
  | Críticas implícitas | 2 escritas en prosa o JSON que no se extraen; ambas quedan señaladas como formato no reconocido |
- **Límites que el informe confirma.** Una cita existente no demuestra una crítica, y el consenso no demuestra una solución.
- **Advertencia metodológica.** El corpus y el clasificador los escribió el mismo autor. Para una evaluación independiente hacen falta casos de GPT-6, del usuario o de ejecuciones reales.
- No se añaden llamadas ni rondas de deliberación.

## 4. Laboratorios individuales (`LABORATORIOS.md`)
- Cuadernos por agente en la **misma** `incidencias.db`, con 2 tablas nuevas. El esquema 4 de incidencias **no cambia**.
  - **A1:** soluciones, alternativas, versiones candidatas y comparación de correcciones sin sobrescribir.
  - **A2:** investigaciones, causas raíz y comparación de las hipótesis existentes con sus reproducciones y controles.
  - **A3:** casos, objeciones clasificadas, contradicciones y pendientes.
- **Reglas que impone la base:**
  - solo anexar;
  - cada agente escribe solo en lo suyo y solo como declaración;
  - una simulación exige un experimento completado y la escribe el laboratorio;
  - no existe «prueba real»;
  - los resultados positivos y negativos se conservan;
  - el aislamiento entre agentes solo se rompe mediante el coordinador;
  - hay límites de entradas, tamaño, intercambios y escrituras por sesión.
- **Recuperación.**
  - Al reabrir, todo persiste.
  - El contenido alterado se detecta por su SHA-256.
  - Una base corrupta no se sobrescribe.

## 5. Personalidad (`PERSONALIDAD.md`)
Sigue el cambio pedido: **no se imponen personalidades**.
- **Elección propia.** Cada agente propone sus rasgos, su estilo y sus preferencias no críticas.
  - Elecciones independientes, secuenciales y con el modelo existente, a través de la sesión del orquestador.
  - Hay **máximo 2 llamadas por agente** y 4 al día.
- **Validación con esquema cerrado.** Las respuestas inválidas, fuera del esquema, contradictorias y maliciosas se rechazan y se registran.
- **Registro.**
  - Se guarda con **procedencia y versión**.
  - Queda **propuesta** hasta que el usuario la aprueba.
  - No se repite en cada reinicio.
- **Gestión.** Se puede consultar, editar, restablecer, revertir y pedir una nueva elección. El historial y las elecciones son de solo anexar.
- **Experiencias y propuestas.**
  - Experiencias verificadas frente a no verificadas, por agente.
  - Propuestas graduales, un paso cada vez, que **siempre** decide el usuario.
  - Límites de frecuencia, de propuestas pendientes, de experiencias y de tamaño.
- **Simulado frente a real.** Una elección simulada nunca puede quedar registrada como de Qwen: hay almacenes separados y la base rechaza el origen contrario.
- **Lo que la personalidad nunca toca:** permisos, función, seguridad, límites ni criterios de evaluación.
  - La lista de campos es cerrada y la impone la base.
  - El módulo no importa servidor, ejecutor, prompts, orquestador ni motor, y no asigna nada en `config`.
  - Una prueba comprueba que los prompts y los límites son idénticos antes y después de aprobar y editar perfiles.

## 6. Archivos (respecto a V2-E.5)
- **Nuevos:**
  - `src/eq2/personalidad.py`;
  - `src/eq2/laboratorios.py`;
  - `src/eq2/evaluacion_criticas.py`;
  - `src/eq2/corpus_criticas.py`;
  - `perfiles.py`;
  - `tests/_sondeo_importaciones.py`;
  - `tests/test_v2e5r2.py`;
  - `PERSONALIDAD.md`, `LABORATORIOS.md`, `LEEME_V2E5R2.md`.
- **Modificados:**
  - `criticas.py`: formatos tolerados, `formato_revision`, `requisito_rebatido`;
  - `orquestador.py`: `run_eleccion_personalidad`;
  - `inferencia.py`: fase simulada `personalidad`;
  - `config.py`: `CARPETA_ACTUAL = datos_v2e5r2`, límites de personalidad y laboratorios, `datos_v2e5` como carpeta anterior;
  - `__init__.py`: `f2-v2e5-r2`;
  - `ejecutar_v2.py`: modos `personalidad_simulada` y `personalidad`, `--autorizar-eleccion-personalidad`, `--agente`;
  - `auditar.py`: `informe-criticas` y `cuaderno`;
  - `supervisar.py`: carpeta;
  - `EXTENSIONES_FUTURAS.md`: sección 5.
- **Pruebas heredadas modificadas** (marcadas `CAMBIO V2-E.5-r2`):
  - `test_v2e5.TestExtensionesFuturas.test_ningun_modulo_visual_se_carga`: la corrección pedida;
  - 21 líneas, **solo** por la carpeta (`datos_v2e5` → `datos_v2e5r2`) y la versión, en `test_v2b`, `test_v2d`, `test_v2e`, `test_v2e2`, `test_v2e3`, `test_v2e4`, `test_v2e4r2` y `test_v2e5`.
- Ninguna aserción de comportamiento ha cambiado.
- Los esquemas no cambian: sesión 6 e incidencias 4.

## 7. Resultados ejecutados (sandbox Linux, Python 3.13; NO en Termux)
| Comprobación | Resultado |
|---|---|
| Validador estático | 0 problemas |
| Suite completa **con** `os.link` | **785/785 OK**: 711 heredadas de V2-E.5 + 74 nuevas en `test_v2e5r2` |
| Suite completa **sin** `os.link` (simulación de Termux en la sandbox) | **785/785 OK** |
| Suite y validador desde el ZIP extraído (HOME y TMPDIR temporales) | ver la respuesta de entrega |
| V2-B … V2-E.5 sin cambios (`sha256sum -c`) | OK |
| Mutaciones de las protecciones nuevas, contra `test_v2e5r2` y `test_v2e5` | **60/60 detectadas** en la pasada final |

**Sobre las mutaciones:**
- **Primera ronda.** Sobrevivieron 11 y una estaba mal definida. Se reforzaron las pruebas:
  - alerta por una objeción pendiente sin contradicción;
  - respaldos que un agente no puede declarar;
  - experimento sin completar;
  - emisor de un intercambio;
  - vínculo de experiencias de otro agente o no verificadas;
  - experiencias no verificadas que cambiarían el perfil;
  - reversión con un vigente ajeno;
  - alteración que respeta el esquema;
  - vigilancia de memoria durante la elección.
- **Mutante equivalente.** Uno era equivalente a una rama redundante de `validar_respuesta`; se eliminó esa rama.
- **Pasada final.** Se repitieron las 60 mutaciones: 60/60 detectadas. El contenedor se reinició a mitad de la pasada; se completó en dos tramos (M00–M18 y M19–M59) sobre el mismo árbol.
- **Qué cubren:**
  - el sondeo de importaciones;
  - los formatos tolerados;
  - el informe comparativo;
  - los disparadores y CHECK de los cuadernos y de la personalidad;
  - la validación del esquema (claves, rasgos prohibidos, contradicciones, duplicados, texto fuera del JSON, rangos);
  - origen simulado o real;
  - aprobación del usuario;
  - procedencia;
  - frecuencia, límites y reversión;
  - neutralidad del prompt;
  - base corrupta;
  - el paso por `_chequear` en el orquestador.

## 8. Validación en Termux (cuando GPT-6 y el usuario lo autoricen)
```
mkdir -p "$TMPDIR/equipo_f2/codigo_v2e5r2" && cd "$TMPDIR/equipo_f2/codigo_v2e5r2"
unzip /ruta/a/equipo_f2_v2e5r2.zip && cd equipo_f2_v2e5r2
python3 -B -I validar_estatico.py                                                            # 0 problemas
python3 -B -W error::ResourceWarning -X dev -m unittest discover -s tests -p "test_*.py"     # todas OK
python3 -B -W error::ResourceWarning -X dev -m unittest discover -s tests -p "test_v2e5r2.py"
python3 -B auditar.py informe-criticas            # mismo resumen que en la sección 3
python3 -B ejecutar_v2.py --modo personalidad_simulada --autorizar-eleccion-personalidad
python3 -B perfiles.py --simulada ver             # origen SIMULADO; el almacén real sigue vacío:
python3 -B perfiles.py ver
ls "$TMPDIR/equipo_f2"                            # datos_v2e5r2 nueva; las carpetas anteriores intactas
# Solo con autorización explícita (modelo real, un llama-server, en secuencia):
python3 -B ejecutar_v2.py --modo personalidad --autorizar-eleccion-personalidad --iniciar-servidor-real
python3 -B perfiles.py elecciones --agente A1     # respuesta de Qwen y su validación
python3 -B perfiles.py ver                        # PROPUESTA pendiente; aprobar-eleccion / rechazar-eleccion
```

## 9. Limitaciones conocidas
- **Clasificador de críticas.** Una crítica falsa con una cita real no se detecta, y una crítica verdadera con una cita parafraseada se marca como posible falsa.
- **Consensos erróneos.** Cuando nadie objeta (o se objeta sin evidencia), un consenso erróneo no se detecta sin ejecutar código.
- **Corpus.** Es pequeño y no es independiente.
- **Personalidad con Qwen.** No se sabe si Qwen-3B produce JSON válido con regularidad. El reintento único y el límite diario evitan bucles, pero no lo garantizan.
- **Validación de la personalidad.** Las listas de opuestos y de raíces prohibidas son heurísticas: pueden rechazar un rasgo inocente y no cubren todas las contradicciones posibles.
- **Uso del perfil.** El perfil aprobado **no se usa** todavía. Medir su efecto exigirá una etapa propia, con pruebas de que no altera votos ni criterios.
- **Cuadernos.** Los agentes no escriben aún en ellos durante una deliberación o una tarea: es una API probada, no un flujo.
- **Alcance de las garantías.** Todas protegen frente a los caminos del sistema y el texto de los modelos, no frente a quien edite a mano los archivos SQLite. Eso se detecta (SHA-256, disparadores ausentes), pero no se impide.
- **Limitaciones heredadas.** Siguen vigentes las de `LEEME_V2E5.md` §8, incluido el fallo intermitente sin explicar de `test_stop_durante_la_tarea`.

## 10. Recomendaciones para V2-E.6
1. **Validación real autorizada en Termux.**
   - Primero la suite.
   - Después una elección de personalidad real.
   - Guardar las respuestas de Qwen (`perfiles.py elecciones`) para ver la tasa de JSON válido.
2. **Calibración con datos reales.**
   - Etiquetar a mano 20–30 revisiones reales de A3.
   - Evaluarlas con `informe-criticas --casos`.
   - Ajustar solo lo que los datos justifiquen.
   - Pedir a GPT-6 casos adversarios propios para que el corpus sea independiente.
3. **Integración mínima de los cuadernos.** Que el motor registre en A3 las objeciones clasificadas y, en A2, los resultados de sus experimentos simulados: solo registro, sin cambiar el flujo.
4. **Uso del perfil en los prompts: decisión aparte.**
   - Solo con autorización, en una única frase de estilo saneada.
   - Con pruebas de que no cambia votos, criterios ni límites.
5. **Multiplataforma, fase 2**, según `PLATAFORMAS.md`.
