# Preregistro: banco de flujos grandes, tanda 7 (combinada: Contexto Ligero y, si no encuentra, identidad)

Escrito ANTES de preguntar a ningún cerebro. Fecha: 2026-11-15.

## Pregunta
En las tandas 5 y 6, un cálculo POSTERIOR (no prerregistrado) sobre los datos guardados indicó que lo mejor es usar
Contexto Ligero y, solo si contesta «NO_ENCONTRADO», pasar al flujo de identidad: en el código real, qwen25 21/24
(3 fallos) y ministral3 23/24 (1 fallo). Esta tanda lo comprueba ejecutándolo de verdad.

## Montaje
- Mismo corpus y mismas 69 preguntas: las 45 de la tanda 5 (sintético: A 6, B 4, D 3, R 4, T 3, P 25) y las 24 de
  la tanda 6 (código real `sistema/src/eq2`: N 18, X 4, U 2).
- Condiciones: `ligero` (se repite, para comparar en la misma ejecución) y **`combinada`**: primero Contexto Ligero; si
  la respuesta es «NO_ENCONTRADO» o no tiene formato, flujo de identidad (claves verificadas → lista de nombres →
  elección o NINGUNA → código exacto → cita y comprobación literal).
- Cerebros qwen25 y ministral3; contexto 4096; temperatura 0; mismo armazón de seguridad.
- Probado antes con un cerebro falso: 49/49, y cada pregunta por la ruta esperada.

## Reglas de decisión (fijadas antes de ver resultados)
- **Código real (24 preguntas)**: la combinada se confirma si acierta **20 o más** en los DOS cerebros con **3 o menos**
  respuestas de valor equivocado en cada uno.
- **Corpus sintético (45)**: la combinada aporta si acierta al menos 2 más que `ligero` en los dos cerebros, sin
  sumar más de 4 respuestas equivocadas respecto a `ligero`.
- **Sin retroceso en exactas** (A, B, D, R, X): la combinada acierta como mucho 1 menos que `ligero` por cerebro.
- Se informa además del coste (llamadas, tokens, segundos) y de cuántas preguntas pasaron a la identidad.

## Resultado (2026-11-15; 26 minutos, sin paradas)

| | qwen25 ligero | qwen25 combinada | ministral3 ligero | ministral3 combinada |
|---|---|---|---|---|
| **Código real** (de 24) | 16 | **21** | 16 | **22** |
| valor equivocado en código real | 1 | 3 | 0 | 2 |
| **Sintético** (de 45) | 20 | 22 | 22 | 23 |
| valor equivocado en sintético | 9 | 13 | 8 | 13 |
| Exactas (A, B, D, R, X: 21) | 21/21 | 21/21 | 21/21 | 21/21 |
| Llamadas al cerebro / segundos | 69 / 117 | 141 / 332 | 69 / 365 | 142 / 672 |
| Pasaron a identidad | – | 28 de 69 | – | 28 de 69 |

Veredictos según las reglas fijadas:
- **Código real: CONFIRMADA.** 21 y 22 de 24 (umbral 20) con 3 y 2 valores equivocados (umbral 3). Coincide con el
  cálculo posterior de las tandas 5 y 6 (21 y 23).
- **Corpus sintético: NO aporta.** qwen25 +2 (cumple) pero ministral3 +1 (umbral +2), y las respuestas equivocadas
  suben +4 y +5 (umbral +4). En las paráfrasis (P) la identidad rescata muy poco (qwen25 de 1 a 4 aciertos,
  ministral3 de 2 a 4 de 25) y añade 3–4 confusiones con funciones vecinas.
- **Sin retroceso en exactas: SÍ.** 21/21 en las dos condiciones y cerebros.
- Coste: el doble de llamadas, 2,8 veces el tiempo en qwen25 y 1,8 en ministral3.

Lectura: la combinada es buena donde los nombres son descriptivos (código real: +5 y +6 preguntas, y no se estropea
nada de lo que ya acertaba). En el corpus sintético, hecho a propósito con cientos de nombres casi idénticos, no
ayuda: ahí manda la ambigüedad, no el método.
