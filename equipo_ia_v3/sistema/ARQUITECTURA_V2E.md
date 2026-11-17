# Arquitectura de V2-E

```
                        ejecutar_v2.py (CLI)                supervisar.py (CLI, otra sesión)
                               │                                     │  lee estado_actual.json,
         ┌─────────────────────┼──────────────────────┐              │  eventos.jsonl, informe.json;
         │                     │                      │              │  escribe solo STOP y solicitudes
   orquestador.py         motor.py (V2-E)         ciclo.py (V2-D)    │  de asesoría
   deliberación y         máquina de estados      (compatibilidad)   │
   votación (V2-B..D)          │                                     │
         │        ┌────────────┼──────────────┬───────────────┐      │
         │   AgentesMotorLLM / Simulados   proyecto.py    ejecutores ▼
         │        │  (A1, A2, A3)          versiones,     ├─ EjecutorSimulado   (Modo A)
         │        │                        SHA-256,       ├─ EjecutorEstatico   (ast.parse; no ejecuta)
         │        │                        atómico        ├─ EjecutorNoDisponible
         │        │                                       └─ EjecutorReal       (Modo B: DESHABILITADO)
         └────────┴── backend_llama.py ── servidor.py (un llama-server hijo en 127.0.0.1) ── cliente_http.py
                         monitor.py (memoria)                       rutas.py (única vía de escritura)
                         plataforma.py (Linux/Termux | Windows pendiente)       memoria.py (SQLite)
```

## Motor de estados (`motor.py`)
| Estado | Agente | Qué hace | Salidas permitidas |
|---|---|---|---|
| PLANIFICAR | A2 | Plan, `ARCHIVOS:`, `CRITERIO: id \| descripción \| PRUEBA: test_x`, `FALTA:` | GENERAR, FINALIZAR |
| GENERAR | A1 | Archivos (`ARCHIVO: ruta` + bloque) → versión v1 | REVISAR, EVALUAR (sin archivos), FINALIZAR |
| REVISAR | A3 | `OBJECION \| EVIDENCIA`, `BLOQUEO:`, `FUERA_DE_ALCANCE:` | PROBAR, EVALUAR (bloqueo), FINALIZAR |
| PROBAR | — | Ejecutor (simulado / estático / no disponible) | EVALUAR, FINALIZAR |
| EVALUAR | código (+ A2) | Estado de criterios; decide fin o corrección; A2 escribe `DIAGNOSTICO:` | CORREGIR, FINALIZAR |
| CORREGIR | A1 | Nueva versión v(n+1) con `CAMBIOS:` | REVISAR, EVALUAR, FINALIZAR |
| FINALIZAR | — | Informe y estado final | — |

La tabla `TRANSICIONES` es explícita y cualquier otra transición lanza `ErrorTransicion` (error crítico). **Evalúa el código, no el modelo**: A2 solo diagnostica.

**Paradas** (se comprueban antes de cada estado): STOP o señal → `detenido`; tiempo global → `limite_tiempo`; llamadas → `limite_llamadas`; memoria (proveedor de plataforma) → `memoria_insuficiente`; fallo del backend o excepción → `error_critico`; iteraciones de corrección → `limite_iteraciones` o `bloqueado_por_revisor`; versión idéntica a la anterior, o el mismo fallo dos veces seguidas → `sin_progreso`.

**Presupuesto** (`Presupuesto`, inmutable): iteraciones (≤ 3), llamadas (≤ 14), tiempo total (≤ 30 min), tiempo por prueba (≤ 30 s), archivos (≤ 8), bytes por archivo (≤ 20 000) y totales (≤ 64 000). `acotado()` nunca supera los máximos de `config`.

## Verificación independiente (informe)
| Campo | Significado |
|---|---|
| `propuesta_generada` | Hay al menos una versión guardada |
| `revision_completada` | A3 revisó al menos una versión |
| `pruebas_simuladas` | Resultados del ejecutor SIMULADO |
| `analisis_estatico` | Resultados del análisis estático (no son pruebas) |
| `pruebas_reales_ejecutadas` | Siempre `false` en V2-E |
| `criterios_verificados` | Solo con pruebas REALES; vacío en V2-E |
| `criterios_superados_en_simulacion` | Superados en simulación (no cuentan como verificación) |
| `criterios_pendientes` | Todos los que no están verificados de verdad |
| `resultado` | `verificado` solo con pruebas reales que verifiquen todos los criterios; si no, `no_verificado` |

Estados de un criterio: `verificado` (inalcanzable en V2-E), `superado_en_simulacion`, `fallido_en_simulacion`, `prueba_presente_sin_ejecutar` (análisis estático) y `pendiente`.

## Seguridad
- El texto de los agentes y la salida de las herramientas son **datos**: van entre delimitadores `DATOS_NO_CONFIABLES`, nunca se ejecutan y no pueden cambiar `Presupuesto`, `Politica` ni `MODO_B_HABILITADO` (inmutables o constantes). Los intentos se detectan con patrones y se registran (`intentos_de_ampliar_permisos`).
- Escritura: solo `rutas.py`, confinado al laboratorio, sin seguir enlaces. Desde V2-E, `os.replace` y `os.link` también están permitidos **solo** en `rutas.py`, para las escrituras atómicas.
- Proyectos: rutas relativas validadas, versiones en carpetas nuevas y nunca sobrescritas, manifiesto SHA-256 y límites de tamaño.
- Validador estático: prohíbe `subprocess`, `socket` (salvo en servidor y cliente), `eval`, `exec`, `compile`, `__import__`, `runpy`, `code`, `importlib`, `os.system`... `ast.parse` (análisis estático) no ejecuta código.
- Modo B: tres barreras (interruptor en `config`, autoverificación del proveedor de aislamiento y ausencia deliberada de implementación).

## Observabilidad
- `datos_v2e/estado_actual.json` (reescritura atómica en cada transición): tarea, estado, agente activo, iteración, llamadas, presupuesto, última comprobación, errores, recursos.
- `runs/<run>/motor/eventos.jsonl` (solo anexar) y `runs/<run>/motor/informe.json`.
- `supervisar.py`: `estado`, `eventos`, `pruebas`, `errores`, `recursos`, `detener`, `informe`, `exportar-asesoria`, `validar-asesoria`.
- Una interfaz futura para Windows puede leer los mismos archivos JSON: no hace falta un servidor nuevo.

## Asesoría externa (GPT-6 / Claude)
Solo intercambio manual: `exportar-asesoria` escribe `asesoria/solicitud_<run>.md`; el usuario pega la respuesta en `asesoria/entrada/<nombre>.md` y lanza la tarea con `--asesoria <nombre>.md`. La respuesta solo llega a A2 como datos no confiables (máximo 4000 caracteres).
