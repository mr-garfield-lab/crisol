# Preregistro: banco de flujos grandes, tanda 8 (gemma12, el tercer cerebro del equipo)

Escrito ANTES de preguntar al cerebro. Fecha: 2026-11-15.

## Pregunta
¿Encuentra y usa gemma12 la información de un proyecto que no cabe en su contexto tan bien como qwen25 y ministral3?

## Montaje
- Mismas 69 preguntas y mismos contextos congelados de la tanda 7, copiados sin cambios (`contextos.json` sha256
  `50ee67f766aa5d0000a79fc8eda6c07c96c85f3fbe09973df17283891ef16f3a`, `tareas.json` sha256
  `dee69d4e8916d961940c9a086cc5e546add87bb4b4f61af92d243762920cf56c`).
- Condiciones `ligero` y `combinada`; contexto 4096; temperatura 0; mismo armazón de seguridad.
- gemma12 con carga parcial en GPU, tope de VRAM 7168 MiB y `--permitir_uso` (como en
  `lab_revision/PRERREGISTRO_REVISION_T4_GEMMA12.md`).
- Evidencia: `evidencias/v31_lab_flujos/tanda8_gemma12/`.

## Reglas de decisión (las mismas de la tanda 7, aplicadas a gemma12)
1. **Código real (24)**: la combinada se confirma en gemma12 si acierta 20 o más con 3 o menos valores equivocados.
2. **Sin retroceso en exactas** (A, B, D, R, X: 21): la combinada acierta como mucho 1 menos que `ligero`.
3. **Corpus sintético (45)**: aporta si la combinada acierta al menos 2 más que `ligero` sin sumar más de 4
   respuestas equivocadas.
4. **Al nivel del equipo**: la combinada en código real a no más de 2 aciertos de qwen25 (21) y ministral3 (22).
5. Se informa: llamadas, tokens, segundos y cuántas preguntas pasaron a la identidad.

## Resultado (2026-11-15, 23:07–23:48; 41 minutos, sin paradas)
| | qwen25 combinada (T7) | ministral3 combinada (T7) | **gemma12 ligero** | **gemma12 combinada** |
|---|---|---|---|---|
| **Código real** (de 24) | 21 | 22 | 15 | **21** |
| valor equivocado en código real | 3 | 2 | 1 | **1** |
| **Sintético** (de 45) | 22 | 23 | 23 | **25** |
| valor equivocado en sintético | 13 | 13 | 7 | **6** |
| Exactas (A, B, D, R, X: 21) | 21/21 | 21/21 | 21/21 | **21/21** |
| Llamadas / segundos | 141 / 332 | 142 / 672 | 69 / 934 | 137 / 1516 |

1. **Código real: CONFIRMADA** (21 ≥ 20, 1 valor equivocado ≤ 3).
2. **Sin retroceso en exactas: SÍ** (21/21 en las dos).
3. **Corpus sintético: SÍ aporta** (+2 aciertos y 1 equivocada menos). Es el primer cerebro que la cumple: qwen25 y
   ministral3 no la cumplieron en la tanda 7.
4. **Al nivel del equipo: SÍ** (21, igual que qwen25 y a 1 de ministral3).
5. Coste: 2,3 veces el tiempo de ministral3 y 4,6 el de qwen25. 30 preguntas pasaron a la identidad (la correcta
   estaba entre los candidatos en 15 de 24; eligió NINGUNA en 22). Trampas: 3/3 «no existe» en las dos condiciones.
   Arranque con 37 capas en GPU (E2 comprobado), cierre limpio.

Lectura: gemma12 acierta lo mismo que los otros en código real, pero se equivoca mucho menos cuando no sabe (6–7
valores inventados en el sintético frente a 13): contesta «no encontrado» en vez de inventar.
