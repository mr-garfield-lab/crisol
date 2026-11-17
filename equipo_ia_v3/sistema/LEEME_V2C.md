# Equipo IA — Fase 2, V2-C (fiabilidad de votos y respuestas truncadas) — ENTREGA PARA AUDITORÍA DE GPT-6

**Estado: NO se ha ejecutado el modelo real ni llama-server con este código.** Todo lo «ejecutado» fue en una
sandbox Linux (no Termux) con backends simulados y un llama-server FALSO.

## 1. Decisiones de GPT-6 aplicadas
| # | Decisión | Implementación |
|---|---|---|
| 1 | Modificar explícitamente orquestador/protocolo/memoria/prompts; sin subclase | Hecho. La subclase de V2-B (`deliberacion.py`) se **eliminó**: su parada por infraestructura y `run_deliberacion` viven ahora en `Orquestador`. |
| 2 | Voto truncado o `finish_reason` desconocido: 1 reintento; si persiste, abstención obligatoria; nunca concluyente | `votos.evaluar_voto` → `truncado` / `no_verificable` (postura `None`); `_votar` reintenta con recordatorio dirigido; luego `abstencion_forzada`. Doble barrera: `protocolo.contar` lanza `ValueError` si un voto no válido no es abstención, y la base lo impide con `CHECK`. |
| 3 | Contradicciones por frases = advertencias | `votos.contradicciones` solo añade advertencias; pruebas de verdaderos positivos, falsos positivos evitados y **falsos negativos conocidos**. |
| 4 | Réplica truncada: conservar recuento, propuesta no fiable | `propuesta_estado` = `incompleta`/`no_verificable` ⇒ fiabilidad `no_valida` (también `CHECK` en la base). Texto final y archivo de propuesta con advertencia. |
| 5 | Voto de A1 con aviso de sesgo | Se mantiene; aviso explícito en `fiabilidad.advertencias`. |
| 6 | 120 tokens por voto; resto de límites igual | `MAX_TOKENS["voto"] = 120`. `MAX_LLAMADAS_TAREA = 10`, `CTX = 1024`, tiempos, memoria, batería: sin cambios (comprobado en pruebas). |
| 7 | `datos_v2c`, esquema 3, sin migrar V2-B | Esquema de sesión `"3"`. El ejecutable rechaza `datos_v2` y `datos_v2b`. |
| 8 | Consenso y fiabilidad separados; salida ≠ 0 si no hay conclusión válida | `resultado` (consenso) y `fiabilidad` (procedimiento) por tarea; `conclusion_valida` y `fiabilidad_global` por sesión; el ejecutable sale con 1 si `conclusion_valida` es falso. |

## 2. Revisión de esquema y recuento (pedida por GPT-6): hallazgos
1. **Escritura antes de rechazar el esquema (corregido).** En V2-B, `_sesion` creaba el candado, `runs/` y copias de seguridad de las bases **antes** de abrir `sesion.db` y detectar el esquema. Una carpeta antigua se habría modificado. Ahora `memoria.esquema_sesion_de` lee el esquema en **solo lectura** (`mode=ro&immutable=1`: no crea `-wal`/`-shm`) **antes de cualquier escritura**; una prueba compara la carpeta byte a byte antes/después.
2. **Ninguna barrera en la base contra votos falsamente concluyentes (corregido).** Esquema 3 añade:
   - `votos`: `CHECK(estado_voto='valido' OR postura='abstencion')` y `CHECK(estado_voto='valido' OR motivo IS NOT NULL)`.
   - `conclusiones`: `CHECK(propuesta_estado='completa' OR fiabilidad='no_valida')`; valores por defecto conservadores (`no_verificable`, `no_valida`).
3. **Defecto de V2-B (corregido):** un fallo de inferencia **en un voto** se convertía en abstención y la tarea seguía, contra la decisión «fallo de infraestructura ⇒ detener la sesión». Ahora aborta la tarea como `inferencia_fallida` y detiene la sesión.
4. **Recorte silencioso de la razón (corregido):** `parsear_voto` recortaba `RAZON` a 200 caracteres. Ahora: >200 ⇒ advertencia `razon_larga`; >300 ⇒ voto inválido. Nunca se recorta en silencio.
5. **Riesgo nuevo encontrado (no resuelto; decisión para GPT-6):** por el contexto de 1024 el bloque `propuesta_final` se acota a `CAP_REPLICA = 400` caracteres en el prompt de voto. Si la réplica es más larga, **los votantes juzgan una propuesta parcial**. V2-C lo registra (`propuesta_final_recortada_para_votante:<agente>` ⇒ fiabilidad `reducida`) pero no cambia el límite.
6. **Compatibilidad:** `protocolo.contar(votos)` sin `estados` sigue funcionando igual (V1); `registrar_turno/voto/conclusion` aceptan los argumentos antiguos. El esquema 2 se rechaza siempre con `EsquemaIncompatible` (no hay migración).

## 3. Qué cambió (archivos)
| Archivo | Cambio |
|---|---|
| `src/eq2/votos.py` (nuevo) | `terminacion`, `evaluar_voto`, `contradicciones`, `analizar_revision`, `analizar_replica`, `senales_calidad`. Puro. |
| `src/eq2/orquestador.py` | `_Turno` con `finish_reason`/`terminacion`/`evaluacion`/recortes; `_llamar` registra terminación y motivo de **todas** las fases; `_votar` nuevo; `_tarea` con estados de voto, fiabilidad, notas de truncado; parada por infraestructura; `run_deliberacion`; pre-chequeo de esquema. |
| `src/eq2/protocolo.py` | `contar(votos, estados)`, `fiabilidad(...)`. |
| `src/eq2/memoria.py` | Esquema 3 (columnas y `CHECK`), `esquema_sesion_de`. |
| `src/eq2/prompts.py` | Instrucciones de objeciones con evidencia / `FALTA` / `ACEPTADA`-`REBATIDA` / abstención por falta de información; recordatorios dirigidos; nota de truncado fuera de los delimitadores. |
| `src/eq2/config.py` | `voto: 120`, `CARPETA_V2C`, `CARPETAS_ANTERIORES`. |
| `ejecutar_v2.py` | Deliberación y una_llamada en `datos_v2c`; rechaza carpetas anteriores y rutas no simples; informe con consenso, fiabilidad, motivos, advertencias y votos; salida según `conclusion_valida`. |
| `src/eq2/deliberacion.py` | **Eliminado** (subclase de V2-B). |
| Sin cambios | `backend_llama.py`, `servidor.py`, `cliente_http.py`, `monitor.py`, `rutas.py`, `modelo.py`, `vigilancia.py`, `sanea.py`, `contexto.py`, `inferencia.py`, `desbordes.py`. |

## 4. Hacia agentes que detecten errores (no solo que estén de acuerdo)
V2-C da el primer paso **dentro de lo permitido** (sin ejecutar código de los agentes):
- **Prompts:** el revisor (A3) debe escribir `OBJECION: <qué falla> | EVIDENCIA: <requisito, línea o caso>`, o `SIN OBJECIONES: <qué comprobó>`, o `FALTA: <dato>`. A1 debe contestar cada objeción con `ACEPTADA` o `REBATIDA` + razón. El voto se pide «según si cumple la tarea, no por acuerdo», con `abstencion` explícita para «no tengo información suficiente».
- **Señales deterministas** (advertencias, no veredictos): `objeciones_sin_evidencia`, `replica_no_responde_todas`, `A3_aprueba_con_objeciones_sin_resolver`, `unanimidad_pese_a_objeciones`, `revision_sin_formato_de_objeciones`, `informacion_insuficiente_senalada`, contradicciones postura/razón.
- **«No sabemos» es una conclusión válida:** tres abstenciones voluntarias razonadas dan `sin_consenso` con fiabilidad `normal`; tres abstenciones **forzadas** (truncados) dan `no_valida`.

Límite honesto: con un único modelo de 3B, estas señales miden si **siguen el formato** del debate, no si la objeción es cierta. Ver §8 (propuesta V2-D).

## 5. Pruebas
- **Resultado (sandbox, ejecutado):** validador estático 0 problemas; **324 pruebas OK** (270 heredadas + 54 nuevas en `tests/test_v2c.py`) con `-W error::ResourceWarning -X dev`; también desde el ZIP extraído.
- **Nuevas:** evaluador de votos (truncado, sin `finish_reason`, motivos de invalidez, razón larga), contradicciones (positivos, falsos positivos, **falsos negativos documentados**), señales de calidad, recuento con estados, fiabilidad, prompts (recordatorios distintos, nota fuera de los datos, presupuesto con historial máximo en todas las fases), esquema 3 (`CHECK`, lectura sin escribir, rechazo del esquema 2), carpeta antigua intacta byte a byte, orquestador simulado (reintento que corrige, truncado persistente, todos truncados con el tope de 10 llamadas, réplica truncada, otras fases truncadas, propuesta recortada para votantes, abstención voluntaria, fallo HTTP en un voto) y servidor falso con procesos reales (**regresión de la petición 7 real**, debate con objeciones, réplica truncada, STOP durante el reintento de un voto, SIGINT, un solo servidor y peticiones nunca simultáneas, proyecto y modelo intactos).
- **Pruebas heredadas que cambiaron (a propósito):**
  1. `test_orquestador.test_fallo_de_inferencia_aborta_tarea_no_sesion` → `test_fallo_de_inferencia_detiene_la_sesion`: la parada por infraestructura pasó de la subclase al orquestador.
  2. `test_v2b.test_el_orquestador_base_si_continuaria_con_la_tarea_siguiente` → `test_run_del_orquestador_tambien_se_detiene`: misma causa.
  3. `test_v2b.test_la_carpeta_es_siempre_datos_v2b` → `..._datos_v2c` (ahora prueba también `datos_v2b/`, `./datos_v2b`, `../x`).
  4. `test_v2b.test_sin_modelo_no_lanza_nada_y_sale_con_error`: espera `datos_v2c`, «CONCLUSIÓN VÁLIDA: NO» y que `datos_v2b` no se cree.
  5. `test_v2b` (2 pruebas): `informe_v2b.json` → `informe_deliberacion.json`.
  6. `tests/_v2.py`: `orq_b` crea un `Orquestador` (ya no la subclase). `fake_llama_server.py`: modos nuevos.
- **Mutaciones (ejecutadas):** 13 protecciones desactivadas una a una; **12 detectadas**:
  voto truncado aceptado (6 pruebas fallan), `finish_reason` ausente aceptado (3), `contar` acepta voto no válido (1),
  réplica truncada no impide (4), sin pre-chequeo de esquema (1), fallo en voto → abstención (2), sin nota de truncado (3),
  sin `CHECK` de abstención forzada (1), sin `CHECK` de propuesta incompleta (1), sin reintento dirigido (3),
  `conclusion_valida` ignora la fiabilidad (5), contradicción que invalida (2).
  **No detectada:** quitar el filtro «cambios pendientes solo de votos válidos». Es una mutación equivalente: la barrera
  anterior (`contar` rechaza un voto no válido que no sea abstención) hace inalcanzable ese caso; el filtro queda como
  segunda defensa sin prueba propia que lo distinga.

## 6. Instalación (carpeta nueva; no toca V2-B ni `~/equipo-ia`)
```
mkdir -p "$TMPDIR/equipo_f2/codigo_v2c"
cd "$TMPDIR/equipo_f2/codigo_v2c"
unzip /ruta/a/equipo_f2_v2c.zip      # crea equipo_f2_v2c/ ; entrar en esa carpeta
```
Datos nuevos: `$TMPDIR/equipo_f2/datos_v2c/`. `datos_v2` y `datos_v2b` no se leen ni se escriben.

## 7. Plan de pasos en Termux (cada uno con autorización de GPT-6)
1. `python3 -B -I validar_estatico.py` → 0 problemas.
2. `python3 -B -W error::ResourceWarning -X dev -m unittest discover -s tests -p "test_*.py"` → 324 OK (más lento en el teléfono).
3. `python3 -B ejecutar_v2.py --modo comprobar`.
4. Solo tras autorización: `python3 -B ejecutar_v2.py --modo deliberacion --iniciar-servidor-real` (misma tarea que V2-B, para comparar).
5. Comprobación posterior: puerto 8089 libre, ningún proceso `llama*`, y `datos_v2b` sin cambios (por ejemplo `ls -la --time-style=full-iso` antes y después).

## 8. Limitaciones conocidas
- Las contradicciones y señales de calidad son **heurísticas de frases** sobre el formato pedido: hay falsos negativos documentados (p. ej. «falla si contiene None», «mutará la entrada», «está bien hecha») y no hay comprensión semántica.
- Con temperatura 0, el reintento de un voto puede repetir el mismo fallo aunque el recordatorio cambie el prompt.
- Más abstenciones forzadas ⇒ más `sin_consenso`/`no_valida`: más honesto, pero el sistema decide menos.
- Prompts más largos: menos espacio para el historial dentro de 1024 tokens; el recorte de `propuesta_final` para votantes (§2.5) sigue abierto.
- Un único modelo de 3B interpreta los tres papeles: la diversidad entre agentes es de prompt y memoria, no de modelo.
- Ningún resultado verifica que el código propuesto funcione: todo sigue siendo hipótesis sin verificar.
- Heredadas: SIGKILL del supervisor puede dejar vivo el hijo y el candado; estimación de tokens provisional; TOCTOU; monitor sin tercera capa; comportamiento real de llama-server ante desborde no probado.

## 9. Propuesta para V2-D (no implementada; requiere autorización)
Para que las objeciones puedan ser **comprobables** sin ejecutar código de los agentes:
- Análisis estático **sin ejecución** del código propuesto: `ast.parse` (detecta errores de sintaxis), y comprobaciones AST concretas para la tarea (p. ej. detectar `.sort()` sobre el parámetro ⇒ «modifica la lista original»). Riesgos: `ast.parse` sobre texto no confiable debe limitarse en tamaño y profundidad; el validador estático tendría que permitirlo explícitamente.
- Que la revisión cite evidencia que el orquestador pueda contrastar con ese análisis (objeción confirmada / no confirmada).
- La ejecución real de pruebas en un entorno aislado queda **fuera** hasta una decisión explícita de GPT-6 y tuya.
