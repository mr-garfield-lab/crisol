# Equipo IA V3 — Inventario de funciones y naturaleza de su verificación

Naturaleza:

- **REAL:** código ejecutado de verdad en el contenedor Linux.
- **SIMULADO:** respuestas de A1/A2/A3 desde un guion o un servidor falso de V2-F.1.
- **ESTIMACIÓN:** cálculo sin hardware real.
- **NO VERIFICADO:** requiere Qwen real, Android o Windows.

**Ninguna función se ha verificado con un modelo real.**

## V2-F.1 (base, `sistema/`, sin cambios)

| Función | Naturaleza | Evidencia |
|---|---|---|
| Función supervisada A1→estático→A2→A3→decisión determinista; plan, debate, memoria, STOP, herramientas tipadas | REAL (lógica) con agentes SIMULADOS | Línea base: 233 OK de 264 en el verificador de V2-F.1 |
| Análisis estático e integridad del manifiesto | REAL | Comprobaciones REAL del verificador |
| Backend Qwen con llama-server (V-QWEN-01..05) | NO VERIFICADO | Sin GGUF ni llama-server |
| Retos Zomboid y paquetes de auditoría | No evaluables | Material omitido en la importación (25 comprobaciones) |
| Ejecución de pruebas del código generado | DESHABILITADA | SEG-01: sin aislamiento del sistema operativo |

## V3 (`eq3/`, herramientas de `v3/`)

| Etapa | Función | Naturaleza | Pruebas · mutaciones |
|---|---|---|---|
| 0 | Línea base exacta por prueba y puerta de regresión (`v3/linea_base.py`) | REAL | 13 · 9/9; ejecución C sobre un sistema mutado detectada |
| 0/7 | Pruebas de mutación con la especificación tratada como dato (`v3/mutacion.py`) | REAL | 4 (AUD-01/02) · incluidas en E0 |
| 1 | Traza unificada de solo añadir con cadena de hashes, ingesta segura, reconstrucción y verificación (`traza`, `ingesta`, `reconstruccion`) | REAL sobre ejecuciones de V2-F.1 con agentes SIMULADOS | 23 · 12/12 |
| 2 | Índice incremental, contexto, dependencias y grafo de tareas y decisiones (`grafo`, Contexto Ligero reutilizado) | REAL | 8 · 6/6; recall@3 de 1,00 frente a 0,55 de la línea ingenua (20 tareas con oráculos prerregistrados) |
| 3 | Propuesta → autorización del usuario → aplicación atómica (`cambios`) | REAL; propuestas desde la traza SIMULADA | 12 · 12/12 |
| 4 | Verificador de citas y calidad de la deliberación (`citas`) | REAL sobre textos SIMULADOS | 10 · 10/10 |
| 5 | Memoria individual, episódica y de proyecto; evaluación prerregistrada (`memoria`, complementos de Codex reutilizados) | REAL (mecanismo); no mide un modelo | 9 · 9/9; recall 1,0 con 0 falsos y 0 prohibidos en 2 conjuntos |
| 6 | Planificación de recursos del PC (`perfiles_pc`) | ESTIMACIÓN, NO VALIDADA en el PC | 11 · 9/9 |
| — | Verificador integral (`verificar_v3.py`, F0–F10) | REAL | Ver los informes de cada etapa |

## Lo que falta validar en el mundo real

1. **Qwen real:** en el teléfono con Termux y en el PC con GPU.
2. **Plataformas:** la suite completa en Android/Termux y en Windows 11 (en Windows, cuidado con los enlaces
   simbólicos).
3. **Hardware y rendimiento:** la VRAM, la RAM y los tokens/s reales frente a las estimaciones de la Etapa 6.
4. **Efecto de la memoria y del contexto:** si mejoran las respuestas de un modelo real. Requiere Qwen.
