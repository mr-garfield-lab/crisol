# Verificador integral (`verificar.py`), V2-E.6

Un único comando ejecuta la batería completa, es decir, todo lo seguro que hay disponible:
```
python3 -B verificar.py
```

## Qué hace
1. **Prepara el entorno**, antes de la grabación:
   - comprueba las huellas de `MANIFIESTO_SHA256.txt` **sin importar** el núcleo;
   - importa el núcleo; si no puede, lo informa igualmente con las marcas y el resumen;
   - crea `$TMPDIR/equipo_f2/lab_v2e7r3/verificacion/<id>/`, con una carpeta de trabajo aislada (`HOME` y `TMPDIR` propios);
   - descubre todas las pruebas.
2. **Graba por fases.**
   - Muestra `*** INICIO DE GRABACIÓN / PRUEBAS ***` y recorre las fases. Cada una empieza y termina con una marca visible:
     ```
     ===== INICIO FASE 6/21 · STOP — STOP, cancelaciones, reanudación y recuperación (9 comprobaciones) =====
     [V-STOP-11] test_v2e5r3_stop.TestStopMotor (11 pruebas) ...
     [V-STOP-11] OK (6.31 s) [SIMULADA] — 11 pruebas
     ===== FIN FASE 6/21 · STOP — … · 9 OK · 41.20 s =====
     ```
   - Al final muestra `*** FIN DE GRABACIÓN / PRUEBAS ***`.
3. **Resume.** Da los totales, la naturaleza de las comprobaciones (REAL, SIMULADA, OMITIDA o NO VERIFICADA), las semillas, la duración y las rutas, y el **ESTADO GENERAL**.
4. **Código de salida.** 0 si no hay fallos, 1 si hay fallos y 2 si no se pudo preparar.

## Naturaleza de cada comprobación
| Naturaleza | Significado |
|---|---|
| **REAL** | Comprueba el árbol o la plataforma reales: huellas, validación estática, compilación, protecciones de configuración, material Zomboid, cumplimiento, diferencias con r3, procesos y temporales. En la fase QWEN, el modelo real. |
| **SIMULADA** | Pruebas con backend simulado, servidor FALSO (`tests/fake_llama_server.py`) o datos sintéticos, y demostraciones. **Nunca son pruebas de Qwen.** |
| **OMITIDA** | No se pidió (`--rapido`) o no hay nada que probar (por ejemplo, ningún paquete externo). |
| **NO VERIFICADA** | Requiere algo no autorizado o no disponible (Qwen real, una plataforma). Siempre lleva su motivo. |

## Fases (en orden)
| Fase | Contenido |
|---|---|
| INT | Integridad: huellas del manifiesto (incluida la evidencia de fábrica), limpieza, estructura y cobertura del catálogo. |
| EST | Validación estática y seguridad: también exige 4 hilos y NP=1. |
| UNI | Pruebas unitarias y regresiones. |
| CTX | Perfiles de contexto y límites de tokens. |
| MOT | Motor, estados y transiciones. |
| STOP | STOP, cancelaciones, reanudación y recuperación. |
| SRV | Inicio y cierre del servidor local. |
| PROC | Procesos, puertos y temporales. |
| AGT | Agentes: roles, independencia, deliberación y personalidad. |
| MEM | Memoria, SQLite, incidencias y auditoría. |
| LAB | Laboratorios y pendientes del coordinador. |
| CRI | Clasificación de críticas. |
| CON | Contratos y paquetes (auditoría y desafío). |
| APR | Aprendizaje: evaluación pre/post SIMULADA y auditoría de memoria por la CLI, en una carpeta aislada. |
| VAR | Pruebas variables: semillas fijas 11, 42 y 2026, más `--semilla N`; niveles 1–3; determinismo. Informe en `pruebas_variables.md`. |
| ZOM | Reto Zomboid: material íntegro, `generar_reto.py` sin ejecutar, puntuador, tubería y servidor falso. |
| REP | Repeticiones: STOP determinista, STOP heredado dependiente del reloj, servidor falso, y STOP en continuación y limpieza. |
| DEMO | Demostraciones por función (ver `--lista-demos`). La salida de cada una queda en `demos/<nombre>.txt`. |
| CUM | Cumplimiento: requisito → archivo → prueba → resultado en `cumplimiento_resultado.md`, y diferencias con r3 en `diff_r3.json`. |
| CIE | Cierre: procesos, temporales y `__pycache__` tras todo lo anterior. |
| QWEN | Modelo real, siempre lo último y solo con `--qwen-real --iniciar-servidor-real`. Comprende las comprobaciones previas, UNA llamada y el reto (1 caso, 3 llamadas). |

## Archivos que deja cada verificación
Todos en `$TMPDIR/equipo_f2/lab_v2e7r3/verificacion/<id>/`:

| Archivo | Contenido |
|---|---|
| `informe.json` / `informe.md` | Resultados, fases, naturaleza, métricas, semillas y plataforma. |
| `terminal.log` | Copia persistente de todo lo mostrado en pantalla. |
| `eventos.jsonl` | Inicio y fin de cada fase y de cada comprobación. Lleva marcas de tiempo (de pared y monotónicas) y métricas: CPU propia y de los hijos (`getrusage`), máximo RSS de los hijos (acumulado) y `MemAvailable` antes y después (`/proc/meminfo`). En plataformas sin esos datos figura `medido: false`. |
| `trazas/<ID>.txt` | Salida de cada fallo y de las pruebas con Qwen real. |
| `cumplimiento_resultado.{json,md}`, `diff_r3.json`, `pruebas_variables.{json,md}`, `demos/` | Resultados de las fases CUM, VAR y DEMO. |

## Opciones
| Opción | Efecto |
|---|---|
| `--rapido` | Sin repeticiones. |
| `--repeticiones N` | Repeticiones para buscar intermitencias (1–50). |
| `--solo PREFIJO` | Filtra por identificador; se puede repetir (por ejemplo, `--solo V-ZOM --solo V-VAR`). |
| `--semilla N` | Semilla adicional para las pruebas variables y la demostración del reto. |
| `--demo` | Solo la fase de demostraciones. |
| `--lista-demos` | Muestra las órdenes de demostración, sin ejecutar nada. |
| `--lista` | Muestra el catálogo por fases, sin ejecutar nada. |
| `--fallo-controlado` | Añade una prueba que falla a propósito, para comprobar el propio verificador. |
| `--autorizar-paquete RUTA.zip` | El usuario autoriza un paquete de auditoría o de desafío por su SHA-256. |
| `--qwen-real --iniciar-servidor-real` | Activa la fase QWEN. |

## Evidencia de fábrica y manifiesto
- `MANIFIESTO_SHA256.txt` incluye **todos** los archivos del paquete, también `evidencias_claude/`. En r3 la evidencia quedó fuera y el verificador del usuario la vio como «no declarada»: era un falso fallo de integridad.
- V-INT-01 indica cuántos archivos de evidencia coinciden.

## V2-F: fases nuevas
- **CAP** — plan, debate por evidencias, memoria de experiencias, autocorrección y herramientas (`tests/test_v2f_*`).
  - Los agentes son de GUION.
  - Las ejecuciones de pruebas y de casos son REALES (ejecutor restringido).
- **BAN** — banco comparativo.
  - V-BAN-01 ejecuta `banco.py simular` dos veces con la misma semilla y exige un informe completo (4 modos), sin errores del sistema y con las mismas decisiones.
  - La tabla queda en `demos/banco_simulado.md`. Es SIMULADO: valida el banco y el protocolo, no mide a Qwen.
- **V-QWEN-04** — banco con Qwen real (tarea `mediana`, modos `individual` y `equipo_debate`).
  - Solo con `--qwen-real --iniciar-servidor-real`; si no, NO VERIFICADA.

## V2-F.1: fase nueva
- **FUN** — función supervisada A1/A2/A3 sin ejecución dinámica e interfaces para Codex (`tests/test_v2f1_*`).
  - Los agentes son de GUION. El análisis estático, las decisiones, la memoria y el informe son reales. El código generado no se ejecuta nunca.
  - V-FUN-01 ejecuta `equipo.py demo funcion` dos veces por la CLI y exige:
    - las mismas decisiones (huella), con el resultado `aceptada_sin_ejecucion`;
    - ninguna ejecución de pruebas;
    - el manifiesto de la ejecución íntegro.

    El informe queda en `demos/funcion_supervisada_informe.md`.
  - Tres demostraciones en la fase DEMO: `funcion_corregible`, `funcion_falta_informacion` y `funcion_sin_progreso`.
- **V-QWEN-05** — la misma tarea (`ejemplos/tarea_funcion_demo.json`) con Qwen real, en el laboratorio real del usuario.
  - Solo con `--qwen-real --iniciar-servidor-real`; si no, NO VERIFICADA.
  - Es OK si el flujo termina (`completada`) con un backend no simulado. El resultado puede ser aceptada o escalada: se informa tal cual.
