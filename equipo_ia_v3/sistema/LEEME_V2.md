# Equipo IA — Fase 2, V2 (una única petición real a Qwen) — ENTREGA PARA REVISIÓN

**Estado: NO se ha iniciado llama-server ni se ha probado el modelo real.** GPT-6 revisa primero este ZIP y autoriza los pasos de Termux uno por uno.

## Contenido
- `src/eq2/` código. Nuevo en V2: `config.py` (constantes V2), `modelo.py`, `cliente_http.py`, `monitor.py`, `servidor.py`, `backend_llama.py`. Modificados: `orquestador.py` (`run_una_llamada`), `memoria.py` (esquema sesión "2", estado `analisis_unico`), `rutas.py`. Sin cambios de comportamiento: `sanea.py`, `contexto.py`, `protocolo.py`, `vigilancia.py`, `inferencia.py`.
- `ejecutar_v2.py` ejecutor (`--modo comprobar` | `--modo una_llamada --iniciar-servidor-real`).
- `validar_estatico.py` validador estático. `tests/` pruebas (226 + 6 de CLI/modelo).
- Instalación sugerida: extraer en `$TMPDIR/equipo_f2/codigo_v2/`. Los datos van a `$TMPDIR/equipo_f2/datos_v2/` (bases SQLite NUEVAS: la de sesión usa esquema "2" y NO migra las de V1; `a1/a2/a3.db` siguen con esquema "1"). Nada se escribe en `~/equipo-ia`.

## Cómo cumple los 15 requisitos
1. Un solo hijo `llama-server`, `--host 127.0.0.1 --port 8089`; el cliente solo conecta a 127.0.0.1.
2. Modelo `~/equipo-ia/modelos/qwen-coder-3b.gguf`: solo lectura (huella parcial: tamaño, fecha, magic GGUF, SHA-256 del primer y último MiB; se compara al final). Enlace simbólico rechazado.
3. Argumentos: `-c 1024 -t 4 -np 1 --no-ui` (mmap por defecto; sin `--no-mmap`, `--mlock`, `--cache-ram`). Copiados de prueba3.py.
4. Una petición como máximo en curso, secuencial (`n_en_curso`), y esta versión hace UNA.
5. Plazo efectivo: cliente HTTP propio con recv de 0,5 s y plazo total, que comprueba parada/monitor/muerte del servidor entre lecturas.
6. Monitor en hilo (latido) + supervisión desde el hilo principal: 3 muestras seguidas con MemAvailable < 300.000 kB (o 3 sin medición) abortan.
7. Se detiene solo el hijo propio: terminate → 10 s → kill → 5 s. Nunca `pkill`; si ya hay un proceso `llama*` no arranca ni lo toca.
8. Puerto comprobado antes (bind + connect) y después del cierre.
9. No se lee `.env` ni otros archivos del proyecto (prueba con `sys.addaudithook`).
10. Sin APIs externas, root, ADB ni servicios de pago.
11. STOP, Ctrl+C/SIGTERM, registros y limpieza en `finally`.
12. La salida del modelo es texto no confiable: se sanea y se guarda, nunca se ejecuta (prueba con orden `touch` simulada).
13. Todo dentro de `$TMPDIR/equipo_f2`; no sobrescribe archivos actuales.
14. Pruebas simuladas con un llama-server FALSO (`tests/fake_llama_server.py`).
15. Solo una llamada: fase `analisis`, agente A2, `max_tokens` 160, temperatura 0, semilla 1.

## Plan de autorización paso a paso (en Termux)
1. `python3 -B -I validar_estatico.py` → esperado: 0 problemas.
2. `python3 -B -W error::ResourceWarning -X dev -m unittest discover -s tests -p "test_*.py"` (más lento que en la sandbox: lanza procesos hijos; los tests de backend tardan ~40 s en sandbox).
3. `python3 -B ejecutar_v2.py --modo comprobar` (no arranca nada, no escribe nada; ejecuta `llama-server --help` salvo `--sin-help`).
4. Solo tras autorización: `python3 -B ejecutar_v2.py --modo una_llamada --iniciar-servidor-real`. Parada de emergencia: Ctrl+C o crear el archivo `STOP` en la carpeta de datos.

## Qué se ejecutó de verdad y qué no
- **Ejecutado (sandbox Linux x86, no Termux):** validador (0 problemas), 232 pruebas con procesos hijos, sockets TCP y señales reales (SIGINT/SIGTERM/SIGKILL) contra el servidor FALSO: éxito, HTTP 500, JSON inválido, sin `choices`, respuesta enorme, servidor mudo/que gotea (timeout), muerte durante la petición o al arrancar, nunca listo, SIGTERM ignorado (→ SIGKILL), puerto ocupado, modelo ausente, `llama*` previo, memoria baja (en carga y en petición), sin medición, monitor bloqueado, STOP, wake-lock.
- **NO ejecutado:** llama-server real, Qwen, Termux/Android, `llama-server --help` real (los flags se comprueban contra una ayuda simulada), tiempos y memoria reales, la ruta de timeout con el modelo real.

## Decisiones para que GPT-6 confirme
- Parámetros de muestreo (temp 0, seed 1, `cache_prompt`) copiados de prueba3.py.
- Wake-lock activado por defecto (`--sin-wake-lock` lo desactiva); su fallo hace el resultado «incompleto».
- Respuesta HTTP no-200 / JSON inválido: no fatal (turno fallido). Plazo agotado, parada o muerte del servidor: fatal.
- Resultado `completo_no_concluyente` cuando faltan métricas del servidor, terminación anómala o mediciones críticas (VmRSS, majflt).
- `max_tokens` 160 y plazo de 240 s por llamada.

## Limitaciones conocidas
- Un SIGKILL al supervisor puede dejar vivo el hijo (RAM y puerto ocupados) y el candado `lock/`; la siguiente ejecución lo detecta y se niega, pero no lo mata (demostrado en una prueba).
- Estimación de tokens (len/3) provisional; V2 guarda estimado vs. real en `calibracion_tokens`.
- Ventana TOCTOU entre comprobar y usar rutas.
- Si la lectura de /proc se bloquea en el hilo monitor solo lo detecta el hilo principal; no hay tercera capa.
- Ruta de timeout con el modelo real sin probar; fuera de Termux las pruebas de tiempo pueden variar.
- Pruebas con servidor falso: no garantizan el comportamiento exacto de llama-server (formato de `timings`, `/health`, cierre).
