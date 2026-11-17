# Equipo IA V3 — Informe de cierre de la Etapa 0: auditoría y línea base

| | |
|---|---|
| Fecha | 2026-11-10 |
| Rama | `experimental/equipo-ia-v3` (desde `main` @ `1241ff9`) |
| Base auditada | `fuentes/claude_v2f1`, Equipo IA V2-F.1 (`VERSION = "f2-v2f1"`), copiada sin cambios en `equipo_ia_v3/sistema/` |
| Estado | **Etapa 0 terminada y pendiente de revisión del usuario.** La Etapa 1 no se ha iniciado. |

## 1. Alcance y aislamiento

- **Solo Equipo IA (A1, A2, A3).** GameAgentEngine, AURORA, ATLAS y AI Lab Coordinator quedan fuera:
  no se han modificado, movido, publicado ni incluido en commits, y no se reutiliza código de GameAgentEngine.
- **Archivos tocados:** solo hay cambios en `equipo_ia_v3/`. `fuentes/` es idéntico a `main`. Las pruebas se
  ejecutan sobre COPIAS, en directorios nuevos con `HOME`/`TMPDIR` propios.
- **Restos de GameAgentEngine:** en `GameAgentEngine/` quedan archivos no versionados de ese proyecto; el hook
  de parada los señala. Se informa del aviso, pero no se tocan ni se ocultan.
- **Sin coste ni instalaciones:** no se ha usado ninguna API de pago, ni se ha instalado o descargado software
  o modelos.

## 2. Base auditada y procedencia

- **Procedencia:** `fuentes/claude_v2f1` procede de `equipo_f2_v2f1.zip` (SHA-256 `11fc0837…`,
  `ORIGENES_SHA256.json`). Las demás ramas remotas no contienen una versión más reciente de Equipo IA.
- **Integridad de la copia:** `equipo_ia_v3/sistema/` tiene los mismos 234 blobs de Git que
  `fuentes/claude_v2f1`. Sus 233 archivos coinciden con el `MANIFIESTO_SHA256.txt` original y no hay archivos
  ajenos.
- **Material omitido:** la importación a GitHub omitió **71 archivos** del manifiesto:
  - 61 de `evidencias_claude/`;
  - 8 evidencias del reto `retos/zomboid_v1`;
  - 2 ZIP anidados (`auditoria_ejemplo.zip`, `desafio_zomboid_v1.zip`).
- **Otras fuentes:** `fuentes/codex_complementos` y `fuentes/contexto_ligero_v35` también son selecciones
  parciales; se omitieron `evaluador_anterior/`, `comparacion/` y `referencia_original/`.

## 3. Entorno y naturaleza de los resultados

| | |
|---|---|
| Entorno | Contenedor Linux x86_64 con Python 3.13 |
| No disponible | Windows 11, Android/Termux, Qwen, GGUF y llama-server |
| Naturaleza | REAL = código ejecutado de verdad en este entorno. SIMULADA = respuestas de A1, A2 y A3 desde un guion o un servidor falso. OMITIDA y NO VERIFICADA según el verificador |

Ningún resultado de este informe demuestra el funcionamiento en Android ni con Qwen real.

## 4. Batería de pruebas de la versión original

Orden: `python3 -B v3/linea_base.py` (ejecución B, 2026-11-10).

| Suite | Pruebas | OK | FALLO / ERROR | OMITIDA | NO VERIFICADA | Naturaleza | Duración |
|---|---|---|---|---|---|---|---|
| Verificador V2-F.1 (`sistema/verificar.py`) | 264 | 233 | 25 FALLO | 1 | 5 | REAL 14 · SIMULADA 244 · OMITIDA 1 · NO VERIFICADA 5 | 443,3 s |
| `codex_complementos/tests` con el `eq2` de V2-F.1 | 37 | 36 | 1 ERROR | 0 | — | lógica real, sin modelos | 1,0 s |
| `contexto_ligero_v35/tests` con el `eq2` de V2-F.1 | 202 | 193 | 5 ERROR | 4 | — | lógica real, sin modelos | 6,2 s |
| **Total** | **503** | **462** | **31** | **5** | **5** | | |

Las 41 pruebas que no están OK tienen una causa documentada en §5. Ninguna se atribuye a un defecto del código:
todas dependen de material omitido, de Qwen real, de una biblioteca opcional o de entradas externas.

Sin `eq2` en la ruta, 21 de las 37 pruebas de codex dan ERROR (`etapa0_preliminar/`): los complementos dependen
de Equipo IA. Las órdenes propias de codex y de Contexto Ligero (`ejecutar.py` y `EJECUTAR_PRUEBAS.py`) terminan
INCONCLUSAS porque falta su manifiesto o su carpeta de comparación, ambos omitidos.

## 5. Línea base reproducible

**Herramienta.** `v3/linea_base.py` y `v3/corredor_unittest.py`, una orden sin red ni instalación. Corregí el
error inicial: `test_complementos.py` hace `self.id = ...`, y el corredor anterior llamaba a `t.id()`. Ahora usa
`type(t).id(t)`; está cubierto por una prueba.

**Procedimiento:**

1. **Ejecución A:** `--proponer` escribe el estado y la firma de las 503 pruebas
   (`evidencias/etapa0/runA_propuesta.json`).
2. **Clasificación:** cada una de las 41 pruebas que no están OK recibe una causa EXPLÍCITA, prueba por prueba
   (`evidencias/etapa0/clasificar.py.txt`). Nada se clasifica por regla genérica: quedaron 0 sin clasificar y
   ninguna entrada sobrante.
3. **Ejecución B:** una ejecución independiente comparada con la línea base clasificada da IGUAL 503 de 503
   (código 0). Los estados y las firmas de A y B son idénticos.

**Línea base:** `v3/linea_base_esperada.json`, con SHA-256 `ef3fc69d728d0b8136e0f05ebbd79c286ea559aa411f3f40e708fa8971bc9972`.

| Causa | Pruebas | Explicación |
|---|---|---|
| OMITIDO_V2F1 | 25 | Los 71 archivos de `equipo_f2_v2f1.zip` omitidos al importar (V-INT-01/03, V-CON-01/03/17..20, V-ZOM-01/11..17, V-VAR-01/11, V-DEMO-03..06 y V-CUM-01..03). Comprobé V-CUM-02 por separado: sus 8 rutas sin documentar son todas archivos omitidos |
| OMITIDO_CONTEXTO | 5 | Faltan `comparacion/` y `referencia_original/` de Contexto Ligero |
| OMITIDO_CODEX | 1 | Falta `evaluador_anterior/` (módulo `evalua`) |
| REQUIERE_QWEN_REAL | 5 | V-QWEN-01..05: GGUF y llama-server en el dispositivo |
| DEPENDENCIA_OPCIONAL_AUSENTE | 4 | `tokenizers` no instalada; instalarla no está autorizado |
| SIN_ENTRADA_EXTERNA | 1 | V-CON-02: no hay paquetes de auditoría externos |

**Reproducir:** desde `equipo_ia_v3/`, `python3 -B v3/linea_base.py` debe terminar con «IGUAL A LA LÍNEA BASE» y
código 0. Para medir otra versión frente a esta línea base: `--sistema <copia>`.

## 6. Verificación del mecanismo de regresión

El riesgo de una puerta de regresión es que apruebe lo que no debe. Se verificó en cuatro niveles.

### 6.1 Diseño

- **Comparación exacta.** Se compara cada prueba con su estado exacto y, si no está OK, con una firma
  normalizada (tipo y mensaje, sin rutas temporales). No basta con que coincidan los totales.
- **Estados separados.** ERROR, OMITIDA, FALLO_ESPERADO y EXITO_INESPERADO son estados propios; ninguno se
  cuenta como OK.
- **Fallos conocidos vigilados.** Un fallo conocido que cambia de estado o de firma da CAMBIO: falla de otra
  manera o por otra causa. Una prueba que pasa a OMITIDA da REGRESION. Una que desaparece, AUSENTE. Una nueva
  que no está OK, REGRESION.
- **Causa obligatoria.** Una línea base con alguna prueba no OK sin causa clasificada y declarada se rechaza
  antes de ejecutar nada.
- **Sin aprobaciones silenciosas.** Una suite sin resultados, o una herramienta que falla, da el código 2. Un
  fallo conocido que pasa a OK da MEJORA (código 3), que obliga a revisar la línea base.

### 6.2 Pruebas propias (`v3/tests/test_linea_base.py`): 13 de 13 correctas

- **Corredor (sintético):** cada estado se registra con exactitud, incluido el caso que rompía la versión
  anterior (`self.id = ...`). Solo las dos pruebas que pasan de verdad quedan aprobadas, y las firmas son
  idénticas entre dos ejecuciones con rutas distintas.
- **Veredictos:** una tabla de 15 casos y los códigos de salida.
- **Validación de la línea base:** rechaza `SIN_CLASIFICAR` aunque esté declarada en el catálogo, y rechaza las
  causas no declaradas.
- **Errores de la herramienta:** una suite vacía da error, igual que una salida que ya existe.

### 6.3 Mutación de la propia herramienta: 5 de 5 detectadas

Introduje 5 defectos en una copia de la herramienta, cada uno una forma de ocultar fallos:

1. ignorar la firma;
2. tratar ERROR como OK;
3. tratar OMITIDA como OK;
4. ignorar AUSENTE;
5. aceptar `SIN_CLASIFICAR`.

Cada defecto hace fallar las pruebas. El quinto sobrevivió en el primer intento: una entrada `SIN_CLASIFICAR`
se seguía rechazando por otra regla (causa no declarada), así que ninguna prueba cubría el caso de que alguien
la declarase en el catálogo. Añadí esa prueba y lo detecta.

**Reproducir:** `python3 -B v3/mutacion.py v3/mutaciones/etapa0.json` es la herramienta reutilizable de mutación
de V3. Primero ejecuta un control sin mutación, que debe pasar; después aplica cada defecto en un espejo
temporal. Evidencia: `evidencias/etapa0/mutacion_de_pruebas/`.

### 6.4 Mutación de la suite real de codex (`TestMutacionSobreCodexReal`)

- **Control negativo:** la suite sin cambios frente a sí misma sale todo IGUAL, con código 0, y el ERROR
  conocido sigue siendo ERROR.
- **Mutaciones:** 4 mutaciones que deben dar 5 veredictos, y los dan:
  - una prueba OK que ahora lanza una excepción → REGRESION;
  - una prueba renombrada → AUSENTE más NUEVA;
  - el fallo conocido, ahora por otra causa (`LookupError`) → CAMBIO;
  - una prueba nueva que falla → REGRESION.

  El código de salida es 1.

### 6.5 Ejecución C: verificador real sobre una copia mutada de `sistema/`

Hice una copia de `sistema/` en el scratchpad (nunca la del repositorio) con dos defectos reales
(`evidencias/etapa0/runC_mutacion/mutaciones_aplicadas.txt`):

1. **Defecto de seguridad:** `MODO_B_HABILITADO = True`, es decir, la ejecución real activada.
2. **Material eliminado:** se borró `retos/zomboid_v1/material_original/MANIFIESTO.json`.

Orden: `linea_base.py --sistema <copia_mutada> --solo verificador`.

**Resultado: código 1.** De las 264 comprobaciones, 240 salen IGUAL, 17 REGRESION y 7 CAMBIO.

- **REGRESION (17):** comprobaciones que estaban OK y ahora fallan por Modo B activado, entre ellas V-EST-03,
  V-MOT-15/17, V-MEM-20/23/27/35/43/46, V-FUN-17/21, V-AGT-19, V-APR-20, V-CAP-24, V-CON-13/14 y V-UNI-48.
- **CAMBIO (7):** fallos conocidos que ahora fallan por otra causa (V-INT-01/03, V-ZOM-01, V-CON-19 y
  V-CUM-01..03). No se absorbieron como «ya fallaban».

La puerta detectó los dos defectos sin que yo le indicara dónde estaban.

## 7. Seguridad

### SEG-01 (prioridad alta): la lista blanca AST del ejecutor restringido se puede saltar

`src/eq2/ejecutor_restringido.py` debería rechazar, entre otros, dos accesos que acepta (`validar()` devuelve
`[]`):

- `g.gi_frame.f_globals['__builtins__']['__import__']('os')`: un escape por el marco de un generador;
- `json.codecs.open(...)`.

**Lo que sí bloquea el gancho de auditoría.** Ejecuté directamente el corredor (`corredor_pruebas.py`) con
8 sondas. El gancho bloqueó:

- leer y escribir fuera del espacio (el canario no se creó);
- `os.listdir('/')`;
- `os.system`.

Un bucle infinito lo cortó el límite de CPU.

**Lo que no bloquea.** El gancho permitió importar `os` y leer su entorno mínimo.

**Conclusión.** La defensa efectiva es una sola capa (el gancho, dentro del propio intérprete), sin aislamiento
del sistema operativo. El propio módulo lo declara: «NO es un sandbox». Evidencia:
`evidencias/etapa0_preliminar/sondas/`.

**Decisión.** La ejecución de código generado sigue DESHABILITADA. Hoy requiere `--autorizo-pruebas` por
ejecución, y Modo B (`config.MODO_B_HABILITADO = False`) está deshabilitado. La Etapa 3 no podrá activarla sin
un aislamiento del sistema operativo demostrado; en Termux sin root no existe.

### Otras observaciones (la base es sólida en estos puntos)

- **Procesos hijos.** Fuera de las pruebas, `subprocess` solo aparece en:
  - `servidor.py` (llama-server);
  - `ejecutor_restringido.py` (el corredor, con entorno mínimo, sesión propia y límites del núcleo);
  - el verificador;
  - `modlab_pz/`, incluido sin modificar: `lua_analisis.py` lanza `luac -p` (solo comprobación de sintaxis,
    5 s, archivos `.lua` de hasta 1 MiB, «nunca mods desconocidos») y `EJECUTAR_PRUEBAS.py` lanza unittest.

  No hay `shell=True`, ni `eval`/`exec` sobre texto de agentes, ni se importa `pickle`, `marshal` ni `shelve`.
- **Red.** Solo `cliente_http.py` y `servidor.py` importan `socket`, y solo se conectan o se enlazan a
  `config.HOST` (`127.0.0.1`).
- **Rutas y SQLite.** `rutas.py` confina las rutas al laboratorio `$TMPDIR/equipo_f2`. Las conexiones SQLite
  solo se abren en `memoria.py` (comprobado con `grep`), módulo que según su diseño solo usa el orquestador.
- **Texto no confiable.** El texto ajeno se envuelve como DATOS (`prompts.py`, `sanea.py`), y
  `contaminacion.py` analiza el contenido instructivo antes de que pase a la memoria.
- **STOP y decisiones.** STOP por archivo, con pruebas deterministas y de repetición (V-STOP y V-REP, todas
  correctas). La decisión final es determinista y basada en evidencias, no en votos.
- **Módulos opcionales.** La personalidad está desactivada por defecto.

## 8. Arquitectura existente

| Capa | Módulos (`src/eq2/`) | Función |
|---|---|---|
| Entrada | `equipo.py`, `ejecutar_v2.py`, `verificar.py`, `validar_estatico.py`, `auditar.py`, `banco.py`, `retos.py`, `supervisar.py` | CLI de tareas, demos, verificador integral, herramientas |
| Orquestación | `orquestador.py` (1.127 líneas), `motor.py` (máquina de estados, 970), `motor_v2f.py` (plan + autocorrección + experiencias, 620), `ciclo.py`, `tareas.py` | Sesiones, tareas LAB-NNN y estados; usa `memoria.py`, el único módulo que abre SQLite |
| Flujo A1/A2/A3 | `funcion_supervisada.py` (1.173), `debate.py`, `casos.py`, `planificacion.py`, `autocorreccion.py`, `criticas.py`, `independencia.py`, `roles.py`, `prompts.py` | A1 genera; análisis estático; A2 revisa; A3 propone casos y objeciones; decisión determinista; correcciones con límites |
| Decisión | `protocolo.py`, `votos.py`, `analisis_estatico.py`, `integridad.py` | Recuento y reglas deterministas; análisis estático sin ejecutar |
| Memoria y aprendizaje | `memoria.py` (sesión y una base por agente), `aprendizaje.py` (SQLite con disparadores y CHECK), `experiencias.py`, `compresion.py`, `contexto_incidencias.py` | Memoria persistente, aprendizaje acotado y auditable |
| Incidencias | `incidencias.py`, `investigacion.py`, `prioridad.py`, `auditoria.py`, `motor_incidencias.py`, `laboratorio.py`, `laboratorios.py` | Registro SQLite, causa raíz, prioridad explicable, experimentos |
| Inferencia | `inferencia.py` (interfaz y backend simulado), `backend_llama.py`, `cliente_http.py`, `servidor.py`, `monitor.py`, `vigilancia.py`, `desbordes.py`, `contexto.py`, `perfiles_contexto.py` | llama-server local (Qwen) con plazos, supervisión de memoria y batería, presupuesto de contexto |
| Seguridad | `rutas.py`, `sanea.py`, `contaminacion.py`, `config.py`, `aislamiento.py` (Modo B DESHABILITADO), `ejecutor.py`, `ejecutor_restringido.py`, `corredor_pruebas.py` | Confinamiento, texto no confiable, límites, ejecución bloqueada por defecto |
| Herramientas e integración | `herramientas.py` (registro tipado), `interfaces_codex.py`, `extensiones.py`, `asesoria.py`, `modlab_pz_adaptador.py`, `plataforma.py` | Contratos y puntos de extensión |

Un mismo modelo puede servir a los tres agentes, que se ejecutan por turnos con un solo backend: tres agentes
no implican tres modelos simultáneos.

## 9. Trazabilidad

**Lo que ya existe** (comprobado en una ejecución de `equipo.py demo funcion`):

- **Decisiones:** `decisiones.jsonl` con 23 decisiones tipadas (responsable, objeción, objeción cerrada,
  evaluación de A3, ejecución dinámica, replanificación, caso impugnado). Cada una registra autor, regla,
  evidencia, ronda y versión.
- **Pasos y herramientas:** `eventos.jsonl` guarda los pasos con agente, archivo, SHA-256, recortes y
  afirmaciones sin evidencia; `herramientas.jsonl`, las llamadas a herramientas con su estado y categoría.
- **Interacción con los agentes:** cada prompt y cada respuesta sin procesar se guardan en un archivo.
- **Informe de la ejecución:** `informe.json` incluye `huella_decisiones`, `archivos_sha256` y `tarea_sha256`.
- **Tarea:** su `eventos.jsonl` registra importada, iniciada y terminada, con el SHA-256 del manifiesto.
- **Aprendizaje:** una base SQLite por agente (recuerdos, evidencias con `actor`/`autorizado_por`,
  transiciones, contradicciones, usos, ejecuciones), con disparadores que exigen feedback humano autorizado
  para revocar una verificación.
- **Requisitos:** la tabla de cumplimiento (`CUMPLIMIENTO_V2E6.md` y V-CUM) enlaza cada requisito con su
  código, sus pruebas y sus comprobaciones del verificador.

**Huecos frente a la cadena pedida** (Objetivo → análisis → agente → decisión → autorización → acción →
cambio → prueba → resultado → experiencia):

1. **Registros dispersos.** La cadena está repartida entre varios JSONL por ejecución y una SQLite por agente.
   Se enlazan por referencias (`tarea_ref`, identificadores, hashes) sin claves foráneas comunes, así que
   reconstruir una acción exige leer varios archivos.
2. **Autorización.** Solo es un indicador booleano (`autorizo_pruebas_recibido`). No hay un registro de
   autorización (quién, qué alcance, cuándo, para qué acción), ni entidades separadas para propuesta,
   autorización y ejecución.
3. **Cambios.** Se conservan las versiones v1…vN de la solución, con su análisis estático y su SHA-256, pero no
   hay un registro del cambio (diff) enlazado con la decisión que lo motivó.
4. **Prueba y resultado.** La ejecución dinámica está bloqueada por diseño. Por eso el resultado es
   «aceptada_sin_ejecucion», y el propio sistema advierte que eso no equivale a «verificado».

## 10. Calidad del código y deuda técnica

**Medidas** (`src/eq2`):

- 68 módulos y 20.081 líneas; las pruebas suman 49 archivos y 16.575 líneas.
- 1.019 funciones, con una media de 13,8 líneas. 13 superan las 80; las mayores son
  `orquestador._sesion` (144), `corredor_pruebas.main` (137) y `orquestador._tarea_interna` (134).
- 47 `except Exception`/`BaseException` y 0 `except` desnudos.
- 44 documentos `.md` en la raíz del sistema: un LEEME y un CAMBIOS por cada revisión, desde V2 hasta V2-F.1.

**Puntos de deuda:**

- **Dos motores** (`motor.py` y `motor_v2f.py`) y dos módulos de laboratorio (`laboratorio.py` y
  `laboratorios.py`) conviven por compatibilidad. Antes de retirar nada hay que comprobar referencias
  dinámicas, compatibilidad y pruebas; no se ha eliminado nada.
- **Concentración de lógica.** Las funciones más largas acumulan la lógica de sesión y de tarea, lo que dificulta
  aislar fallos.
- **Documentación por versión** extensa y difícil de seguir. Falta un documento único del estado vigente.

**Herramienta de la Etapa 0** (`v3/`): 3 archivos, sin dependencias y con 13 pruebas propias.

## 11. Clasificación de funcionalidades

| Clase | Componentes | Evidencia |
|---|---|---|
| **Funcional, verificada aquí con backend simulado** | Orquestador y motor de estados; función supervisada A1→estático→A2→A3→decisión; plan, autocorrección y debate por evidencias; memoria SQLite, aprendizaje y experiencias; incidencias; rutas, saneado, contaminación y presupuesto de contexto; STOP; registro tipado de herramientas; tareas LAB-NNN (importar, ejecutar, exportar); verificador integral | Fases V-UNI, MOT, AGT, MEM, APR, FUN, CAP, BAN, CRI, LAB, PROC, STOP, REP, SRV y CTX correctas; demos simuladas correctas |
| **Funcional, verificada aquí de verdad (REAL)** | Análisis estático del propio código; integridad del manifiesto; fallo honesto sin llama-server («sin_conclusion», sin inventar resultados) | Comprobaciones REAL del verificador; `tarea ejecutar` |
| **Experimental u opcional** | Personalidad (desactivada); ejecutor restringido (opt-in, SEG-01); banco comparativo (simulado); laboratorios individuales; pruebas variables; retos Zomboid (material omitido); adaptador de ModLab PZ | Banderas de `config.py` y docstrings; V-ZOM/V-VAR no evaluables |
| **Planificada o solo interfaz** | Modo B de ejecución aislada (deshabilitado); `extensiones.py`; `interfaces_codex.py` (los módulos de Codex no están integrados); asesoría externa (intercambio manual); Contexto Ligero (no conectado); migración a Windows (`plataforma.py` solo detecta) | Docstrings; `fuentes/codex_complementos` y `fuentes/contexto_ligero_v35` sin integrar |
| **No verificable en este entorno** | Qwen real con llama-server (`backend_llama.py` y `servidor.py` solo se prueban con un servidor falso); Android/Termux; Windows 11 | V-QWEN-01..05 NO VERIFICADA |

## 12. Rendimiento (Linux; no extrapolable a Android ni a Windows)

- **Verificador:** 443 s en la ejecución B; 397 s y 485 s en otras dos ejecuciones con distinta carga de la
  máquina. Por fases (B): UNI 86 s, REP 70 s, SRV 50 s, MEM 48 s, BAN 29 s y AGT 28 s.
- **Pruebas de codex y de Contexto Ligero:** 1,0 s y 6,2 s.
- **Demo de la función supervisada:** 0,25 s (escenario `falta_informacion`), con una RSS máxima de los
  procesos hijos de unos 29 MiB.
- **Lo que no se ha medido:** el rendimiento de inferencia, por falta de Qwen.

## 13. Riesgos priorizados

| # | Riesgo | Prioridad | Tratamiento |
|---|---|---|---|
| R1 | SEG-01: una sola capa protege la ejecución de código generado | Alta | Ejecución deshabilitada; aislamiento del sistema operativo como requisito de la Etapa 3 |
| R2 | Nada se ha validado en Android/Termux, Windows 11 ni con Qwen real | Alta (para producción) | No declarar producción; guías y pruebas específicas en las etapas 6 y 8 |
| R3 | 71 archivos omitidos: 25 comprobaciones no evaluables | Media | Fallos documentados con su causa; pedir el ZIP original |
| R4 | Trazabilidad dispersa y autorización como indicador booleano | Media | Objetivo de la Etapa 1 (§14) |
| R5 | Complejidad, duplicación y documentación por versión | Media | Refactorización con la puerta de regresión, sin borrar código no comprobado |
| R6 | Codex y Contexto Ligero sin integrar | Baja/media | Etapa 2 (índice y grafo) y Etapa 5 (memoria), tras revisar los contratos |

## 14. Propuesta de arquitectura y plan técnico

**Principio.** Se evoluciona `sistema/` sin reconstruirlo y sin perder funcionalidades. Cada cambio pasa la
puerta de regresión: `python3 -B v3/linea_base.py` debe dar IGUAL (código 0), o una MEJORA (código 3) revisada
y anotada en la línea base.

| Etapa | Primer núcleo operativo | Puerta |
|---|---|---|
| 1. Núcleo, trazabilidad y calidad | Una SQLite de trazas por laboratorio, con entidades enlazadas (objetivo, análisis, agente, decisión, autorización, acción, cambio, prueba, resultado, experiencia) que se alimentan de los registros existentes. La autorización pasa a ser un registro con actor, alcance y caducidad, y la propuesta, la autorización y la ejecución quedan separadas. Logs estructurados y STOP intactos | Reconstrucción verificable de una ejecución completa desde la base; pruebas de seguridad y regresión |
| 2. Grafo y contexto | Reutilizar Contexto Ligero (índice, dependencias, paquetes de contexto) mediante un adaptador de solo lectura | Recuperación medida en tareas reales, invalidación correcta |
| 3. Programación controlada | Herramientas tipadas para Python. La ejecución sigue deshabilitada mientras no haya aislamiento del sistema operativo (R1) | Ninguna ejecución arbitraria; pruebas adversariales |
| 4–5. Coordinación y memoria | Planificación y debate sobre la traza; comparar con y sin memoria en escenarios nuevos (sin afirmar que cambian pesos) | Mejora medida frente a la línea base |
| 6–8. PC, auditoría y paquete | Perfiles para Ryzen 5 5600, 32 GB y RTX 3050 sin descargar modelos; auditoría integral; ZIP con manifiesto y guías para Windows y Termux | Validación en cada plataforma real por parte del usuario |

## 15. Criterios de aceptación de la Etapa 0

| Criterio | Evidencia | Cumple |
|---|---|---|
| Arquitectura comprendida | §8, §9, §11 | Sí |
| Pruebas reproducibles | §5: A = B en 503 de 503. §6: la puerta no oculta fallos (13 pruebas propias, 5 de 5 mutaciones, la mutación de codex y la ejecución C) | Sí |
| Riesgos documentados | §7, §13, §16 | Sí |
| Ningún defecto crítico abierto sin tratar | SEG-01 tratado con la ejecución deshabilitada; los 25 fallos se deben a material omitido | Sí, con limitaciones (§16) |

## 15 bis. Corrección posterior al cierre (encontrada en la Etapa 1)

El verificador integral de la Etapa 1 detectó un defecto en `v3/corredor_unittest.py`: la firma de un fallo
dependía de la longitud de la carpeta de salida, porque se recortaba antes de normalizar las rutas.

- **Corrección:** normalizar primero y recortar después.
- **Cobertura:** una prueba con carpetas de longitud muy distinta y la mutación M6.
- **Línea base:** `v3/linea_base_esperada.json` NO cambia; su SHA-256 sigue siendo `ef3fc69d…`.

Detalle en `docs/ETAPA1_TRAZA.md`, §4.5.

## 16. Limitaciones y bloqueos reales

1. **Plataformas no validadas:** Windows 11, Android/Termux y Qwen real requieren validación del usuario en
   cada plataforma.
2. **Comprobaciones no evaluables:** 25 comprobaciones del verificador, 1 prueba de codex y 5 de Contexto
   Ligero dependen de material omitido. Para recuperarlas hace falta el ZIP original.
3. **Dependencia opcional:** las 4 pruebas del tokenizador real se omiten porque falta `tokenizers` (instalarlo
   no está autorizado).
4. **Clasificación de funcionalidades:** se basa en el código, las banderas y el verificador; no se ha hecho un
   análisis de cobertura línea a línea.

## 17. Evidencias

Todo está en `equipo_ia_v3/evidencias/`; cada carpeta tiene su `LEEME.md`.

**`etapa0/`:**
- `runA_propuesta.json` y `clasificar.py.txt`: la propuesta de línea base y la clasificación explícita de sus
  causas.
- `runA/`, `runB/` y `runC_mutacion/`: estados por prueba, registros, `informe.json` del verificador y, en B y
  C, `resultado.json` con la comparación.
- `tests_linea_base.log.txt` y `mutacion_de_pruebas/`: la verificación de la propia herramienta.
- `traza_demo_funcion_LAB-002/`: los registros de trazabilidad de una ejecución SIMULADA (§9).

**`etapa0_preliminar/`:** la primera ejecución del verificador, las pruebas de codex y de Contexto Ligero sin
y con `eq2`, las sondas de SEG-01 y el fallo original de `linea_base.py`.

Los ZIP originales no están en el repositorio. Sus SHA-256 están en `ORIGENES_SHA256.json`, en la raíz.
