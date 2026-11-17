# Equipo IA V3.1 F1 — estado (2026-11-11)

Orden oficial del 2026-11-11 (GPT-6): X1, preparación del modelo real, compatibilidad con V2-F.1, servidor gestionado por
Claude (D4), `majflt` (D3) y evaluación S1 / S1×3 / E3. SEG-01 sigue bloqueado: nada generado por los agentes se ejecuta.
Rama local `f1-v31` (sin remotos). `sistema/` y `fuentes/` sin cambios.

| Etapa | Estado | Evidencia |
|---|---|---|
| Base: ZIP de mantenimiento (SHA-256 f436eb65…), Git local, F0.5 intacta | HECHA | 760 archivos coinciden con el árbol |
| X1: pruebas inestables (V-CON-11) | HECHA | `docs/V31_F1_X1_INESTABLES.md`; fases F15 (16/16) y R13 |
| Descargas oficiales verificadas (llama.cpp b12110 CUDA 12.4 + cudart, Qwen2.5-Coder-7B Q4_K_M) | HECHA | `evidencias/v31_f1/externos/`, `eq3/externos_f1.json` |
| Compatibilidad con V2-F.1 (`--no-ui`, flags, ruta del modelo, hilos, puerto, detector de llama) | HECHA | 28 pruebas con el servidor falso; clases V-SRV con las mismas firmas que la línea base |
| STOP, memoria, puerto, integridad del modelo entre sesiones | VERIFICADOS con servidor falso y real | `test_eq3_servidor_pc.py`, `test_v2e5r3_stop` (15 OK), humo real |
| `majflt` (D3): HardFaultCount con sonda y fallo cerrado | HECHA | `eq3/majflt_windows.py`; fase F17 (8/8) |
| Prueba de humo con Qwen REAL por el ciclo de vida de V2-F.1 | HECHA | `evidencias/v31_f1/humo/humo_servidor_real_1.json` |
| Prerregistro de ≥ 10 tareas, oráculos y criterio | HECHO (versión 1, pendiente de revisión con GPT-6) | `docs/V31_F1_PLAN_EVALUACION.md`, `evaluacion_f1/PRERREGISTRO_F1.json`; fase F18 (12/12) |
| Ejecución S1 / S1×3 / E3 (2 veces cada una) | PENDIENTE | |
| Validación integral sin reutilizar, informes y ZIP | PENDIENTE | |

## Humo con el modelo real (1 petición, ctx 2048)

- Carga 3,6 s (modelo ya en la caché de disco); arranque y cierre por `BackendLlama`/`ServidorLlama` de V2-F.1.
- Respuesta concluyente: 46 tokens de prompt, 58 generados, `ok_stop`, 1,45 s; 734 tok/s de prompt y 41 tok/s de generación.
- VRAM: 1421 MiB (otras aplicaciones) → 5926 con el modelo cargado → 1421 tras el cierre. Queda justo bajo el tope de
  6144 MiB del AI Lab Coordinator (218 MiB de margen). RAM del proceso ≈ 4,7 GiB.
- `majflt` presente (HardFaultCount; 2297 en la petición, por paginar el modelo): la respuesta es concluyente. NO es
  comparable con el `majflt` de Linux.
- Cierre: proceso terminado, puerto libre, modelo sin cambios, VRAM liberada. En Windows `terminate()` equivale a
  TerminateProcess (código 1): no es un cierre «amable» (causa WIN_SIN_SIGKILL ya documentada).

## Variante experimental F1-VRAM-EXP (2026-11-11)

- **Qué es:**
  - tope de 6912 MiB, autorizado por el usuario tras el intento 1 de la estable, abortado por VRAM;
  - módulo aparte, `eq3/evaluar_f1_vram_exp.py`, con prerregistro V3 (`evaluacion_f1/PRERREGISTRO_F1_VRAM_EXP_v3.json`);
  - la estable (6144 MiB, prerregistro V2) sigue intacta;
  - detalle en `V31_F1_VRAM_EXP.md`.
- **Validada sin Qwen real:**
  - 19 pruebas;
  - F20: 17/17 mutaciones detectadas;
  - las pruebas de la estable siguen pasando: 30/30 en total.
- **No ejecutada con Qwen real:** el PC estaba en uso cuando se sondeó, con entrada reciente, una aplicación a pantalla
  completa, 2,3–2,4 GB de VRAM ajena y la GPU al 26–45 %. Con esa VRAM ajena, ni siquiera el tope de 6912 MiB deja
  margen: 2390 + 4780 = 7170.

## Riesgos pendientes (detalle en `V31_F1_PLAN_EVALUACION.md` §8)

- **Margen de VRAM escaso:** 218 MiB bajo el tope de 6144 MiB. Otra aplicación que use la GPU lo agota. Mitigación: la
  puerta G2 aborta antes y durante cada bloque.
- **STOP y límites de memoria SIN PROBAR con Qwen real**, solo con el servidor falso de V2-F.1. Las puertas G3 y G4 son
  obligatorias antes de la primera tarea.

## Límites de V2-F.1 que condicionan la evaluación (sin tocar `sistema/`)

- Contexto 1024/2048, no 8192; `MAX_TAREA_CHARS` = 600 caracteres por enunciado; 4 pasos de agente por ronda.
- El flujo E3 existente es `funcion_supervisada` (A1 escribe, A2 revisa, A3 casos y evidencia, decisión determinista):
  ahí se mide E3. S1 y S1×3 se construyen en la capa V3 con el mismo backend, el mismo tope de tokens y el mismo oráculo.
