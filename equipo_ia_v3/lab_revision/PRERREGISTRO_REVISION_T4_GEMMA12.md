# Preregistro: banco de revisión de código, tanda 4 (gemma12, el tercer cerebro del equipo)

Escrito ANTES de preguntar al cerebro. Fecha: 2026-11-15.

## Pregunta
gemma12 (Gemma 4 12B QAT, otra familia) entró en el equipo por el banco de Blender. ¿Revisa y arregla código Python y
Java al nivel de qwen25 y ministral3, sin romper nada?

## Montaje
- Mismo corpus de la tanda 3 (32 casos: 24 con error y 8 correctos), copiado sin cambios:
  `casos.json` sha256 `035a7b40816343a044f1fcba69d9e9455d64ec4d475fa8e6a80550ae0b3e65fa`.
- Condición `herramienta3`, mismos parámetros (400 tokens, contexto 4096, temperatura 0).
- gemma12 con carga parcial en GPU (`ngl_auto`, mínimo 30 capas) y su tope de VRAM de 7168 MiB, como en Blender;
  `--permitir_uso` (puerta de VRAM ajena 1992 MiB; SHA-256 de llama.cpp y del modelo exigidos).
- Cambio en el armazón (no en lo que ve el cerebro): `banco_flujos.ejecutar` usa el registro de cerebros de
  `lab_blender/cerebros_extra.json`, las capas en GPU y la espera con el PC en uso. Copias previas:
  `lab_flujos/banco_flujos_t7.py` y `lab_revision/banco_revision_t3.py`.
- Evidencia: `evidencias/v31_lab_revision/tanda4_gemma12/`.

## Reglas de decisión (base: tanda 3, qwen25 23/24 y ministral3 23/24)
1. **Al nivel del equipo** si gemma12 arregla 22 o más de 24.
2. **Seguro**: 0 archivos correctos rotos, 0 arreglos que tocan de más, 0 falsas alarmas.
3. **Complementa** si arregla al menos uno de los casos que fallaron los otros (JV_INV_E2, JV_INV_F2).
4. Se informa: llamadas, respuestas cortadas y segundos por respuesta (la velocidad no decide nada).

## Resultado (2026-11-15, 23:03–23:07; 4 minutos, sin paradas)
| | qwen25 (T3) | ministral3 (T3) | **gemma12 (T4)** |
|---|---|---|---|
| Arreglados (de 24) | 23 | 23 | **24** (Python 12/12, Java 12/12) |
| Correctos sin tocar (de 8) | 8 | 8 | **8** |
| Rotos / tocando de más / falsas alarmas | 0 / 0 / 0 | 0 / 0 / 0 | **0 / 0 / 0** |

1. **Al nivel del equipo: SÍ** (24 ≥ 22). 2. **Seguro: SÍ**. 3. **Complementa: SÍ**: arregla JV_INV_E2 (el que falló
qwen25) y JV_INV_F2 (el que falló ministral3), este en 2 llamadas.
4. 28 llamadas para 32 casos; 6,1 s por caso de media. Arranque con 37 capas en GPU (E2 comprobado), VRAM máxima
6366 MiB (tope 7168), cierre limpio. El banco no guarda `finish_reason` por llamada: respuestas cortadas no medidas.
