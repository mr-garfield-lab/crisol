# Equipo IA — Fase 2, V2-B (deliberación real A1/A2/A3) — ENTREGA PARA AUDITORÍA DE GPT-6

**Estado: NO se ha ejecutado ninguna deliberación real, no se ha iniciado llama-server ni se ha probado Qwen con este código.**
Todo lo «ejecutado» más abajo fue contra un llama-server FALSO en una sandbox Linux (no Termux).

## Qué añade V2-B respecto a V2-A
| Archivo | Cambio |
|---|---|
| `ejecutar_v2.py` | Nuevo `--modo deliberacion`. `comprobar` y `una_llamada` no cambian (solo se resuelve el valor por defecto de `--carpeta` por modo). |
| `src/eq2/deliberacion.py` (nuevo) | `OrquestadorV2B(Orquestador)`: reutiliza `run(tareas)`; solo sustituye `_trabajo_deliberacion`; añade `run_deliberacion`. |
| `src/eq2/desbordes.py` (nuevo) | Análisis puro de desbordamientos de contexto con las medidas reales del servidor. |
| `src/eq2/config.py` | Se AÑADEN `CARPETA_V2B`, `TAREA_V2B`, `MOTIVOS_TAREA_INFRAESTRUCTURA`. Ningún límite existente cambia (ctx 1024, tiempos, llamadas, tokens, memoria). |
| `tests/test_v2b.py` (nuevo), `tests/fake_llama_server.py`, `tests/_v2.py`, `tests/_comun.py` | 38 pruebas nuevas y modos nuevos del servidor falso. |

**`orquestador.py`, `backend_llama.py`, `servidor.py`, `memoria.py`, `rutas.py`, `cliente_http.py` y `monitor.py` son idénticos byte a byte a la entrega V2-A** (verificado con `cmp`).

### Incompatibilidad encontrada (y cómo se resolvió sin tocar el orquestador)
`Orquestador.run` ya aborta la SESIÓN ante fallos fatales del backend (servidor caído, timeout, memoria, STOP/señales), pero ante un fallo NO fatal de infraestructura (HTTP no-200, JSON inválido) o `tiempo_tarea` solo aborta la TAREA y sigue con la siguiente. GPT-6 decidió que esos casos detengan la sesión. Se resolvió con una subclase (`OrquestadorV2B._trabajo_deliberacion`): si una tarea termina `abortada` con motivo en `inferencia_fallida` o `tiempo_tarea`, lanza `SesionAbortada("infraestructura_<motivo>")`. Una prueba documenta que el orquestador base sí continuaría. Si GPT-6 prefiere modificar `orquestador.py` en vez de la subclase, hay que pedirlo.
Los votos inválidos siguen el protocolo existente (1 reintento, luego abstención). `limite_llamadas`, `respuesta_vacia` y `contexto_excedido` (local) no se consideran de infraestructura.

## Instalación (carpeta nueva; no sobrescribe V2-A)
```
mkdir -p "$TMPDIR/equipo_f2/codigo_v2b"
cd "$TMPDIR/equipo_f2/codigo_v2b"
unzip /ruta/a/equipo_f2_v2b.zip        # crea equipo_f2_v2/ ; entrar en esa carpeta
```
Datos: `$TMPDIR/equipo_f2/datos_v2b/` (fija; el ejecutable rechaza otra `--carpeta`). Nada se escribe en `~/equipo-ia`. Las bases de V2-B son nuevas (independientes de `datos_v2`).

## Plan de pasos (cada uno requiere autorización de GPT-6)
1. `python3 -B -I validar_estatico.py` → 0 problemas.
2. `python3 -B -W error::ResourceWarning -X dev -m unittest discover -s tests -p "test_*.py"` (270 pruebas; en sandbox ~80 s, en el teléfono tardará más).
3. `python3 -B ejecutar_v2.py --modo comprobar` (no arranca nada, no escribe).
4. **Solo tras autorización:** `python3 -B ejecutar_v2.py --modo deliberacion --iniciar-servidor-real` (una tarea fija: «Diseña una función Python que ordene una lista de enteros sin modificar la lista original.»). Parada: Ctrl+C o crear `STOP` en `datos_v2b`.
5. Comprobación posterior: puerto 8089 libre y ningún proceso `llama*` (el informe ya lo indica; verificarlo aparte).

Salida: 0 solo si `resultado_global == "completo"`, todas las tareas `completa` y sin desbordamiento efectivo. Se guardan `summary.json` e `informe_v2b.json` en `datos_v2b/runs/<run_id>/`, y la propuesta en `propuestas/tarea_N.txt` (texto plano no confiable; nunca se ejecuta).

## Desbordes de contexto (no se oculta nada; no se cambia el contexto)
`desbordes.analizar` usa `tokens_prompt` real y `predicted_n`: `desborde_efectivo` (grave, real+generado > 1024), `riesgo_desborde` (real+max_tokens > 1024), `corte_por_max_tokens`, `subestimacion_tokens` (real > estimado), `indicio_en_log`, `medida_ausente`. Se imprimen todos; un desborde efectivo hace que el ejecutable salga con código 1. Referencia de V2-A: prompt real 142 frente a 173 estimados (la estimación fue conservadora en esa llamada; no basta para generalizar).

## Qué se ejecutó de verdad y qué no
- **Ejecutado (sandbox, servidor FALSO):** validador (0 problemas) y 270 pruebas: 7 llamadas secuenciales con un único servidor (nunca dos peticiones activas), aislamiento de las 4 bases, reutilización de memoria, reintento y abstención de votos, tope de 10 llamadas, HTTP 500 / JSON inválido / servidor muerto / timeout / tiempo de tarea / tiempo de sesión / memoria baja a mitad, SIGKILL necesario, STOP, `solicitar_parada`, SIGINT y SIGTERM reales, sesión activa, auditoría con `sys.addaudithook` (solo se lee el modelo), orden peligrosa simulada no ejecutada, CLI. Tres mutaciones (quitar la parada por infraestructura, ignorar el desborde, no escribir el informe) hicieron fallar pruebas.
- **No ejecutado:** llama-server real, Qwen, Termux, una deliberación real, tiempos de evaluación de prompt de prompts largos, comportamiento real del servidor ante desborde de contexto (puede truncar, desplazar contexto o devolver error; el servidor falso no lo reproduce).

## Estimación (no medida) para la primera ejecución
Generación máxima 940 tokens a ≈9 tok/s → ≤ ~105 s de generación; falta añadir la evaluación de los prompts (no medida con prompts largos) y la carga (≈3 s). El límite de 20 min por tarea no debería alcanzarse salvo fallo.

## Limitaciones conocidas
- SIGKILL al supervisor puede dejar vivo el hijo (RAM y puerto) y el candado; la siguiente ejecución lo detecta y se niega, no lo mata.
- Estimación de tokens (len/3) provisional; se guarda estimado vs. real por llamada.
- Ventana TOCTOU entre comprobar y usar rutas.
- Si /proc se bloquea en el hilo monitor solo lo detecta el hilo principal.
- La ruta de timeout y de desborde no se ha probado con el modelo real; el servidor falso no garantiza el formato exacto de llama-server.
- Un modelo de 3B puede votar «aprobar» una propuesta incorrecta: todo resultado es hipótesis sin verificar; no se ejecuta ni se prueba el código propuesto.
- La calidad de A1/A2/A3 depende de un único modelo; no hay diversidad real entre agentes (solo cambian prompt y memoria).
- `informe_v2b.json` y el texto final se añaden después de `summary.json`, que por tanto no los contiene.
