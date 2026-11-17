> **Versión actual: V2-F.1** (candidata, no estable) — empieza por `LEEME_V2F1.md` (la función supervisada A1/A2/A3 sin ejecución dinámica, qué es real, simulado o pendiente, órdenes, recuperación y comparación con V2-F), `CAMBIOS_V2F1.md` e `INTERFACES_CODEX.md`. La orden única sigue siendo `python3 -B verificar.py`.
> **Versión actual: V2-F** — empieza por `LEEME_V2F.md` (capacidades nuevas, qué es real, simulado o pendiente, órdenes y límites) y `CAMBIOS_V2F.md`. La orden única sigue siendo `python3 -B verificar.py`.
> **Versión actual: V2-E.6** — empieza por `LEEME_V2E6.md` (instalación, orden única `python3 -B verificar.py`, novedades, límites y rollback). Este archivo describe la etapa V0–V1 original y se conserva como historia.

# Equipo IA — Fase 2, etapa V0–V1, revisión r2 (backend SIMULADO)

**Estado:** código preparado para auditoría. No inicia `llama-server`, no abre red,
no lanza procesos. El único backend es `BackendSimulado`. Nada de lo que produce es
una medida del modelo real.

## Contenido
```
equipo_f2/
  LEEME.md
  validar_estatico.py        validación estática (solo lee; no importa src)
  src/eq2/
    config.py       límites y constantes (CTX=1024, presupuesto por fase, guardia anti ~/equipo-ia)
    rutas.py        confinamiento al laboratorio $TMPDIR/equipo_f2; ÚNICO módulo que escribe en disco
    sanea.py        limpieza de texto, delimitadores de datos no confiables, parser estricto de votos
    contexto.py     presupuesto de contexto: reserva generación, acota bloques, RECHAZA lo que no cabe
    prompts.py      roles A1/A2/A3 y prompts por fase
    protocolo.py    recuento determinista de votos (sin azar)
    memoria.py      SQLite: sesion.db + a1/a2/a3.db, CHECKs, FTS5, aislamiento, respaldo verificado
    vigilancia.py   memoria/batería con lectores inyectables
    inferencia.py   interfaz de backend + BackendSimulado (único)
    orquestador.py  7 llamadas por tarea, límites, STOP, lock, cierre aislado, summary.json
  tests/            140 pruebas unitarias (backend simulado; las de enlaces y SIGKILL usan el sistema real donde se ejecuten)
```
Los datos de una ejecución se crean bajo `base` (`datos/`, `copias/`, `runs/<id>/`, `STOP`, `lock/`),
que debe estar DENTRO del laboratorio autorizado `$TMPDIR/equipo_f2` (por defecto; el argumento
`raiz_laboratorio` solo se usa en pruebas). Fuera de él, o dentro de `~/equipo-ia`, se lanza
`RutaInsegura` antes de crear nada.

## Validación estática (sin ejecutar nada de `src`)
Desde la carpeta `equipo_f2/`:
```
python3 -B -I validar_estatico.py
```
Comprueba con `ast`: sintaxis; sin imports de red/procesos/ctypes/pickle; sin
`eval/exec/compile`, `os.system/kill/remove`, `shutil.rmtree`; SQL solo literal o nombre
(nunca f-string, `+` o `%`); `open()` de escritura solo en `orquestador.py`/`memoria.py` y
nunca con `'w'`; la cadena `equipo-ia` solo en `config.py`. Imprime línea y SHA-256 por módulo.

Revisión manual sugerida: `grep -n "execute\|open(\|import " src/eq2/*.py`

## Pruebas unitarias (ejecutan código de `src`, pero solo con backend simulado y en carpetas temporales)
```
cd tests
python3 -B -m unittest discover -s . -p "test_*.py" -v
```
Tardan unos 8 s en un entorno de escritorio. **No** crean nada fuera de `$TMPDIR` ni tocan
`~/equipo-ia`, `prueba2.py` o `prueba3.py`. Si prefieres revisar antes de ejecutar nada, basta
con el validador estático y leer el código.

## Decisiones tomadas que GPT-6 debería confirmar
1. **Presupuesto con ctx=1024:** prompt máximo por fase = 1024 − max_tokens − 48 (propuesta: 756).
   Tokens estimados como `len/3` (conservador, **sin medir**). V2 debe contrastarlo con el
   tokenizador real o con `tokens_prompt` devuelto por el servidor.
2. **Tarea ≤ 600 caracteres** (antes 1500): con ctx 1024 no cabe más con historial.
3. **Votación:** abstenciones no cuentan; <2 votos válidos → sin_consenso; reparto
   aprobar/aprobar_con_cambios/rechazar (1-1-1) → sin_consenso; mayoría a favor con algún
   «con cambios» → `aprobada_con_cambios` (cambios pendientes guardados); sin sorteo.
   **Punto abierto:** qué hacer cuando las abstenciones deciden (p. ej. 1 aprobar + 2 abstenciones).
4. **Voto sin formato:** un reintento con recordatorio; si falla → `abstencion` registrada.
5. **Tarea abortada** (fallo de inferencia, contexto excedido, tiempo, límite de llamadas) deja la
   sesión en `abortada` / `resultado_global=incompleto`, aunque otras tareas terminen.
   «sin_consenso» no es fallo del sistema.
6. **Vigilancia:** 3 muestras consecutivas con MemAvailable < 300000 kB, o 3 fallos consecutivos
   del monitor, abortan la sesión. Batería <20 % sin carga abortan solo si ambos datos se leen.
   En V0–V1 la vigilancia es entre llamadas desde el hilo principal; el hilo con latido de
   prueba3 se copiará en V2 junto al servidor.
7. **Memoria:** toda entrada nace `sin_verificar` (no existe parámetro para cambiarlo); tras cada
   tarea cada agente guarda una hipótesis generada por código con plantilla (incluye 120
   caracteres de la tarea y su propio voto). No se guardan textos libres del modelo salvo la
   razón de su voto, saneada y marcada como sin verificar.
8. **Sesgo de A1:** A1 puede votar su propuesta; se registra el evento `sesgo_autoria`.
9. `run_id` incluye microsegundos y PID (un fallo de colisión real apareció y se corrigió).

## Qué NO cubre esta etapa (no probado)
- Ningún comportamiento del modelo real, de `llama-server`, tokenización, velocidades ni RAM real.
- Lectura real de `/proc/meminfo` y batería en el teléfono (solo probada con lectores simulados
  y con rutas inexistentes).
- Caída del proceso por SIGKILL de Android (los candados `lock/` podrían quedar; hay que
  borrarlos a mano, es una carpeta vacía).
- Que FTS5 exista en el SQLite de Termux (hay respaldo con `LIKE`, probado en simulación).
- Las señales (`instalar_senales=True`) solo se probaron mediante `solicitar_parada()`.

## Cambios de la revisión r2 (correcciones pedidas por GPT-6)
1. **Rutas confinadas** (`rutas.py`): `base` debe estar dentro de `$TMPDIR/equipo_f2`; nombres de
   ruta simples (sin `/`, `..`, vacíos, NUL); ningún componente entre la raíz y el destino puede ser
   un enlace simbólico (aunque apunte dentro del laboratorio); la ruta real resuelta debe quedar
   dentro; archivos nuevos con `O_CREAT|O_EXCL|O_NOFOLLOW`. `$TMPDIR` en sí SÍ puede ser un enlace.
   Las bases SQLite y el respaldo también rechazan enlaces. El validador estático exige que solo
   `rutas.py` use `os.open/mkdir/rmdir/remove/fdopen`, `Path.mkdir/write_text…` o `open()` de escritura.
2. **Recuperación**: al iniciar, toda sesión `en_curso` pasa a `interrumpida`
   (`recuperada_tras_interrupcion`), sus tareas sin terminar a `abortada`, se registra un evento y
   aparece en `sesiones_recuperadas` del resumen. **Nunca se reanuda.** El candado `lock/` guarda
   el pid; si existe, `SesionActiva` indica si el pid sigue en `/proc` o si es **obsoleto**, pero
   **no se borra solo**: tras un SIGKILL hay que borrarlo a mano y ejecutar de nuevo.
3. **Timeout**: documentado en `LIMITACIONES` (copiado en cada `summary.json`): en V0–V1 el plazo
   solo se comprueba cuando el backend devuelve; no interrumpe una llamada bloqueada. V2 necesita
   plazo efectivo propio (socket + plazo total) y supervisión independiente. Hay una prueba que lo
   demuestra.
4. **Tamaño SQLite**: doble barrera. `PRAGMA max_page_count` fija un tope duro por conexión
   (SQLite falla con «database is full») y `agregar()` comprueba el tamaño tras insertar dentro de
   la misma transacción y la revierte si supera el límite (`MemoriaLlena`). La inserción fallida no
   deja rastro ni en la tabla ni en el índice FTS.
5. **Tokens**: `config.ESTIMACION_TOKENS` («provisional: len/3, sin validar contra el servidor
   real»); aparece en el docstring, en `params_json`, en `summary.json` y en `limitaciones`.
   Las columnas `tokens_*` de `turnos` quedan en NULL con backend simulado.
6. **Voto estricto**: solo `VOTO: <postura>` y, opcionalmente, una segunda línea `RAZON: <texto>`.
   Cualquier otra línea (previa, posterior, repetida, vallas de código, viñetas, continuaciones)
   invalida la respuesta → un reintento → abstención.
7. **Pruebas nuevas**: `tests/test_correcciones.py` (31) y una en `test_estatico.py`.

## Verificaciones: qué se ejecutó de verdad y dónde
Entorno: mi entorno de trabajo en la nube (Linux, Python 3.13.17), **no** tu teléfono ni Termux.
- Validador estático: 0 problemas (ejecutado).
- 140 pruebas unitarias: OK, con `-X dev` y `ResourceWarning` como error (ejecutado).
- **Reales (sistema operativo del entorno de pruebas):** creación de enlaces simbólicos y rechazo
  por el código; un proceso hijo recibe SIGKILL real a mitad de sesión y la siguiente ejecución lo
  detecta y recupera; el tope de páginas de SQLite se alcanza de verdad.
- **Simuladas:** todas las respuestas del «modelo», los lectores de memoria/batería y el reloj.
- Pruebas de mutación manuales (ejecutadas sobre copias): al desactivar la comprobación de
  enlaces, la recuperación o el voto estricto, las pruebas nuevas fallan.
- **No ejecutado:** nada en Termux/Android, nada con `llama-server`.
