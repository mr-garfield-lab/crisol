# Equipo IA — Fase 2, V2-D — ENTREGA PARA AUDITORÍA

**Estado: NO se ha ejecutado el modelo real, ni llama-server, ni nada en Termux con este código.**
Todo lo «ejecutado» fue en una sandbox Linux x86 con backends simulados y un llama-server FALSO.

## 1. Diagnóstico de V2-C (por qué falló la deliberación real)
La deliberación real terminó con propuesta y réplica truncadas, 3 abstenciones y `no_valida`. En el código hay **tres** recortes que se suman:
1. **El servidor corta por `length`** (220 tokens de propuesta, 160 de réplica). Es la causa confirmada.
2. **El orquestador recortaba el historial:** la revisión veía 400 caracteres de la propuesta (`CAP_PROPUESTA`) y los votantes 400 de la propuesta final (`CAP_REPLICA`). Los votantes juzgaban un texto parcial.
3. **`MAX_TURNO_CHARS = 1200` recortaba en silencio** al guardar el turno.

Además, el contexto de 1024 es el cuello de botella. Estimación (no medida): la caché KV de Qwen2.5-3B (36 capas, 2 cabezas KV, dimensión 128, f16) ocupa unos 36 KB por token, es decir unos 36 MB con 1024 y unos 72 MB con 2048, frente a 2,3 GB libres medidos. **No se cambia por defecto**; `--ctx 2048` queda como opción explícita para medir.

## 2. Nuevos límites de tokens (y por qué)
| Fase | V2-C | V2-D | Motivo |
|---|---|---|---|
| Análisis | 160 | 160 | No se truncó |
| Propuesta | 220 | **320** | Se truncó; debe contener código completo + caso de prueba |
| Revisión | 160 | 160 | No se truncó |
| Réplica | 160 | **240** | Se truncó; es la propuesta final que se vota |
| Voto | 120 | 120 | — |
| Continuación (nuevo) | — | ≤ 200, ajustado al espacio libre | `min(200, CTX − prompt_real − generados − 16)`; no se continúa si quedan < 48 |
| Llamadas por tarea | 10 | **12** | 7 + 2 continuaciones (1 por propuesta y 1 por réplica) + 3 reintentos de voto |
| `MAX_TURNO_CHARS` | 1200 | **2400** | Evitar el recorte silencioso; si aun así se supera, el turno cuenta como truncado |
| `TOPE_MAX_TOKENS` (backend) | 300 | 400 | La propuesta pide 320 |
| Contexto | 1024 | 1024 (opcional 2048) | — |

Recortes por bloque y fase (`config.CAPS_BLOQUE`, para 1024; se escalan con `CTX/1024`): la revisión ve **1100** caracteres de la propuesta (antes 400); la réplica 900 de la propuesta y 450 de la revisión; los votantes **1300** de la propuesta final (antes 400) y 250 de la revisión, que se descarta primero si no hay sitio.

## 3. Protecciones contra truncamientos
1. **Truncamiento por `length` o `finish_reason` desconocido:** como en V2-C (votos: 1 reintento y abstención obligatoria).
2. **Truncamiento semántico con `stop`:** un bloque ` ``` ` sin cerrar se trata como truncado. La propuesta y la réplica deben terminar con una línea `FIN`; si falta, se intenta una continuación y, si aun así falta, queda el aviso `fin_no_marcado` (no bloquea).
3. **Continuación sin duplicar (`integridad.unir`):** se envía el prompt original + el texto parcial como mensaje `assistant` (*prefill*). Al unir: se quita el eco si el servidor repite el texto previo, se elimina el solape final/inicial, se **rechaza** un reinicio (la continuación vuelve a empezar) y una continuación ya contenida en el parcial. Se vuelve a verificar la integridad. Máximo 1 por fase. **Solo se activa si `llama-server --help` muestra `--no-prefill-assistant`** (indicio de que la versión soporta prefill; activo por defecto). `--sin-continuacion` la desactiva. Con `cache_prompt` el prefijo ya está en caché, así que la continuación debería costar poca evaluación de prompt (por verificar en el teléfono).
4. **Compresión extractiva y determinista (`compresion.py`):** nunca la hace el modelo. Conserva íntegros los bloques de código y las líneas `OBJECION`/`EVIDENCIA`/`FALTA`/`ACEPTADA`/`REBATIDA`/`SIN OBJECIONES`/casos de prueba; quita primero la prosa del medio y marca cada hueco con `[…]`; nunca parte una línea esencial. Si lo esencial no cabe, la fiabilidad pasa a `reducida` (`contexto_esencial_perdido`); si se comprime prosa, queda el aviso `contexto_comprimido`. La propuesta final de los votantes **no se comprime nunca**.
5. **Verificación de integridad antes de votar:** si la réplica no está `completa` o no cabe **entera** en el prompt de algún votante, **no se vota**: resultado `no_votada`, tarea `propuesta_incompleta`, fiabilidad `no_valida`. Se ahorran 3 llamadas inútiles.
   **Esto sustituye la decisión 4 de V2-C** («conservar el recuento de votos» con réplica truncada): con la verificación previa no hay votos que conservar. Si GPT-6 prefiere mantener la votación, hay que decidirlo.
6. **Defensa en profundidad en la base (esquema 4):** `CHECK(propuesta_estado='completa' OR resultado NOT IN ('aprobada','aprobada_con_cambios'))` y `CHECK(resultado<>'no_votada' OR fiabilidad='no_valida')`. Una prueba desactiva la verificación previa y comprueba que la base impide guardar una aprobación.
7. **Reintentos con límites verificables:** 1 continuación por fase (2 por tarea), 1 reintento por voto, 12 llamadas por tarea; las pruebas comprueban el peor caso exacto (7 + 2 + 3 = 12) y que nunca se supera.
8. **Sesgo de autoría:** se mantiene el aviso y, nuevo, si quitar el voto a favor de A1 cambia el resultado (`decision_depende_del_voto_del_autor`), la fiabilidad pasa a `reducida`.

## 4. Métricas comparables
- Cada llamada registra fase, agente, tipo (`normal`/`continuacion`/`reintento_voto`), `max_tokens`, tokens estimados y reales, `ms_prompt`, `ms_gen` y tiempo de pared. `summary.json` incluye `metricas` (total, por fase, por tipo), `tareas_sha256` y `config`.
- `comparar_metricas.py BASE/summary.json NUEVA/summary.json` (solo lectura) compara con un `summary.json` de V2-C y comprueba el objetivo de +30 % de tiempo. Avisa si las tareas no son equivalentes o si faltan medidas. El `summary.json` de V2-C no tiene `tareas_sha256`; el comparador lo dirá (la tarea es la misma: `config.TAREA_V2B`).
- **Estimación (no medida) del tiempo:** a ≈9 tok/s, 180 tokens más de generación en propuesta y réplica son ≈ +20 s si el modelo los usa; cada continuación, hasta +22 s; la revisión y la réplica reciben prompts más largos. Si no hay continuaciones, el incremento debería estar dentro del 30 %; si hay dos continuaciones, **probablemente lo supere**. A cambio, una propuesta incompleta ya no consume 3 votos. Solo la medida real en el teléfono lo decide.

## 5. Ejecución autónoma (arquitectura; sin ejecución real)
- `archivos.py`: extrae `ARCHIVO: nombre` + bloque de código; nombres simples, extensiones `.py .txt .md .json`, ≤ 5 archivos, ≤ 20 KB, sin duplicados ni bytes nulos ni nombres reservados de Windows.
- `ejecutor.py`: `Politica` (herramientas permitidas `pruebas_python`, tiempo, memoria, archivos, sin red, sin privilegios, **aislamiento real obligatorio**), `EspacioTrabajo` (directorio explícito `runs/<run>/ciclo/iter_<n>/`, validado por `rutas.Laboratorio`, nunca sobrescribe), `RegistroAcciones` (JSONL), `EjecutorNoDisponible` (por defecto) y `EjecutorSimulado` (resultados guionizados; no ejecuta).
- `ciclo.py`: plan (A2) → generar (A1) → revisar (A3) → ejecutar → retroalimentación → corregir, hasta cumplir criterios (pruebas superadas **y** sin objeciones) o agotar límites (iteraciones ≤ 3 duras, llamadas, tiempo, STOP, señal). Con el ejecutor no disponible el resultado es `sin_verificar`; con el simulado, `verificacion: simulada`. `AgentesLLM` construye los prompts con presupuesto y delimitadores; `AgentesSimulados` para pruebas.
- Garantía estructural: el validador estático prohíbe `subprocess`, `os.system`, `exec`, `eval`, `compile`, `__import__`, `runpy`, `code`, `importlib`... fuera de `servidor.py`. Una prueba con *audit hook* confirma que durante el ciclo no se crea ningún proceso ni se compila código, aunque el «código» generado lo intente.
- `--modo ciclo_simulado`: demostración sin modelo (la 1.ª versión muta la lista, A3 lo objeta, el ejecutor simulado falla, A1 corrige).
- **Un directorio no es un sandbox.** En Android/Termux sin root no hay aislamiento real; el ejecutor real queda para Windows 11 (ver `MIGRACION_WINDOWS.md`).

## 6. Registro de cambios respecto a V2-C
| Archivo | Cambio |
|---|---|
| `config.py` | Límites de §2, `CAPS_BLOQUE`, continuación, `CTX_PERMITIDOS`, `CARPETA_V2D`, límites del ejecutor. |
| `integridad.py` (nuevo) | Terminación semántica, marca FIN, unión de continuaciones. |
| `compresion.py` (nuevo) | Compresión extractiva. |
| `metricas.py` (nuevo) | Agregación y comparación de métricas. |
| `archivos.py`, `ejecutor.py`, `ciclo.py`, `plataforma.py` (nuevos) | Arquitectura de ejecución autónoma y portabilidad. |
| `orquestador.py` | `_invocar` (única vía al backend, métricas), `_clasificar`, `_continuar`, `_fase_completa`, `_integridad_para_votar`, `_no_votar`, sesgo decisivo, métricas en el resumen, `tareas_sha256`, `config`. |
| `prompts.py` | Marca FIN en propuesta y réplica; caps por fase; compresión. |
| `contexto.py` | `ctx` se lee al llamar (para `--ctx`); informe de compresión en `Prompt`. |
| `memoria.py` | Esquema 4 (`tipo`, `max_tokens`, `pared_s` en turnos; `no_votada`; estado `propuesta_incompleta`; dos `CHECK` nuevos). |
| `protocolo.py` | `depende_del_autor`. |
| `servidor.py` | `soporta_prefill` en las comprobaciones (solo lectura de `--help`). |
| `backend_llama.py` | `permitir_continuacion` / `soporta_continuacion`; `TOPE_MAX_TOKENS` 400. |
| `desbordes.py` | `ctx` se lee al llamar. |
| `ejecutar_v2.py` | `datos_v2d`, `--ctx`, `--sin-continuacion`, `--modo ciclo_simulado`, métricas en el informe, rechazo de `datos_v2`/`datos_v2b`/`datos_v2c`. |
| `comparar_metricas.py` (nuevo) | Comparador de solo lectura. |
| `validar_estatico.py` | Prohíbe además `runpy`, `code`, `codeop`, `pdb`, `imp`, `zipimport`; analiza `comparar_metricas.py`. |
| Sin cambios | `cliente_http.py`, `monitor.py`, `rutas.py`, `modelo.py`, `vigilancia.py`, `sanea.py`, `votos.py`, `inferencia.py`. |

### Pruebas heredadas que cambiaron (a propósito)
1. `test_v2c.test_replica_truncada_marca_propuesta_incompleta_y_conserva_el_recuento` → `..._y_no_se_vota` (ver §3.5).
2. `test_v2c.test_propuesta_final_recortada_para_los_votantes` → `..._que_no_cabe_para_los_votantes_no_se_vota` (977 caracteres ya caben; uno que no cabe ya no se vota).
3. `test_v2c.test_esquema_es_3` → `test_esquema_es_el_vigente` (4), y la lectura en solo lectura compara con el esquema vigente.
4. `test_v2c.test_conclusion_por_defecto_es_la_mas_conservadora`: ahora una `aprobada` con los valores por defecto ni siquiera se puede guardar.
5. `test_v2c.test_presupuesto...`: `MAX_LLAMADAS_TAREA` 12.
6. `test_v2c.test_todos_truncados...`: 10 llamadas (7 + 3) ≤ 12.
7. `test_memoria.test_conclusion_nace_como_hipotesis`: una `aprobada` debe declarar propuesta completa.
8. `test_v2b.test_sin_modelo_no_lanza_nada_y_sale_con_error`: carpeta `datos_v2d`.

## 7. Validaciones realizadas y pendientes
- **Realizadas (sandbox Linux, no Termux):** validador estático 0 problemas; suite completa (ver resultado en la entrega) con `-W error::ResourceWarning -X dev`, también desde el ZIP extraído; mutaciones (ver §8); `--modo ciclo_simulado` y `--modo comprobar` ejecutados con un HOME y TMPDIR temporales.
- **Pendientes en el dispositivo:** todo lo real: que `llama-server --help` muestre `--no-prefill-assistant`; que el prefill continúe de verdad sin repetir (el falso servidor solo lo imita); tiempos y tokens reales; comportamiento con `--ctx 2048`; que el modelo escriba la marca `FIN` y el formato `OBJECION | EVIDENCIA`.

## 8. Mutaciones (ejecutadas)
Se desactivó cada protección nueva, una a una, y se ejecutaron `test_v2c.py` + `test_v2d.py`. **18 de 18 detectadas** (entre paréntesis, pruebas que fallan):
sin verificación antes de votar (13) · sin CHECK aprobada+incompleta (3) · sin CHECK no_votada→no_valida (1) · continuaciones sin tope por fase (3) · unión sin quitar el eco (2) · unión sin detectar reinicio (3) · ignorar bloque de código abierto (1) · compresión que ignora lo esencial (3) · ignorar el recorte al guardar (3) · ignorar el sesgo decisivo (1) · continuar sin soporte del servidor (8) · continuación sin límite de espacio (2) · sin métricas (2) · ciclo sin tope duro de iteraciones (1) · espacio de trabajo sin validar nombres (1) · política que permite red (3) · `sin_fin` sin continuación (3) · ciclo que da por cumplido con objeciones de A3 (1).
La última **no se detectaba** en la primera ronda (todas las pruebas hacían coincidir objeciones y fallos); se añadió `test_pruebas_superadas_no_bastan_si_A3_objeta` y ahora se detecta.

## 9. Instalación (carpeta nueva; no toca V2-B, V2-C ni `~/equipo-ia`)
```
mkdir -p "$TMPDIR/equipo_f2/codigo_v2d"
cd "$TMPDIR/equipo_f2/codigo_v2d"
unzip /ruta/a/equipo_f2_v2d.zip      # crea equipo_f2_v2d/
cd equipo_f2_v2d
```
Datos: `$TMPDIR/equipo_f2/datos_v2d/` (esquema 4). `datos_v2`, `datos_v2b` y `datos_v2c` se rechazan y no se tocan (el esquema se lee en solo lectura antes de escribir nada).

## 10. Instrucciones para pruebas reales (cada paso con autorización)
1. `python3 -B -I validar_estatico.py` → 0 problemas.
2. `python3 -B -W error::ResourceWarning -X dev -m unittest discover -s tests -p "test_*.py"` → todo OK (tardará más que en la sandbox).
3. `python3 -B ejecutar_v2.py --modo ciclo_simulado` (sin modelo) → `criterios_cumplidos`, `verificación: simulada`.
4. `python3 -B ejecutar_v2.py --modo comprobar` → anotar `continuación (prefill) anunciada por --help`.
5. **Deliberación real** (misma tarea que V2-C): `python3 -B ejecutar_v2.py --modo deliberacion --iniciar-servidor-real`. Revisar en el informe: terminación por fase, continuaciones (`tipo continuacion`), `CONCLUSIÓN VÁLIDA`, métricas por fase; y en `datos_v2d/runs/<run>/propuestas/tarea_1.txt` que el texto unido no tenga repeticiones.
6. **Comparación:** `python3 -B comparar_metricas.py "$TMPDIR/equipo_f2/datos_v2c/runs/<run_v2c>/summary.json" "$TMPDIR/equipo_f2/datos_v2d/runs/<run_v2d>/summary.json"` (solo lectura).
7. Si la continuación repitiera o corrompiera texto: repetir con `--sin-continuacion` y comparar.
8. Opcional, como paso aparte: `--ctx 2048` (vigilar MemAvailable y tiempos).
9. Comprobación posterior: puerto 8089 libre, ningún `llama*`, `datos_v2b`/`datos_v2c` sin cambios.

## 11. Limitaciones conocidas
- El prefill depende de la versión de llama-server; el flag en `--help` es un indicio, no una prueba. Si el servidor no continúa sino que empieza un mensaje nuevo, la unión lo detecta como reinicio o lo acepta solo si no repite el principio; un texto nuevo que no repita el principio podría unirse mal (se reverifica la integridad, pero el sentido no).
- La detección de reinicio es conservadora: una continuación que legítimamente empiece igual que la propuesta se rechaza (la tarea queda `no_votada`).
- Si al modelo de 3B se le olvida `FIN`, habrá continuaciones de pocos tokens (coste en tiempo) y avisos `fin_no_marcado`.
- La compresión es por líneas y patrones; no entiende el contenido.
- Con 1024 de contexto, una réplica de más de ~1300 caracteres no cabe entera para los votantes y la tarea queda `no_votada`: honesto, pero reduce la utilidad; `--ctx 2048` lo resolvería (pendiente de medir).
- El objetivo de +30 % de tiempo no está garantizado (ver §4).
- El ciclo autónomo solo está probado con agentes y ejecutor simulados; no hay ejecución real de pruebas en V2-D.
- Heredadas: SIGKILL del supervisor; estimación de tokens provisional; TOCTOU; monitor sin tercera capa; un único modelo para tres papeles.
