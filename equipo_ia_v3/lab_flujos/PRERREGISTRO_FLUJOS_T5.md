# Preregistro: banco de flujos grandes, tanda 5 (arreglos: constantes, lector tolerante, flujo de identidad)

Escrito ANTES de preguntar a ningún cerebro. Fecha: 2026-11-15.

## Qué se arregló desde la tanda 4
1. **Contexto Ligero indexa las constantes de módulo** (`fuentes/contexto_ligero_v35/contexto_core/index.py`,
   `support.py`, `data_support.py`; copias `*.bak_2026-11-15_constantes`). Un nombre asignado una sola vez a nivel de
   módulo, y que no sea también función o clase, pasa a ser un símbolo de tipo `Assign`. Una primera versión rompió 8
   pruebas propias (las constantes importadas dejaban de seguir su valor encadenado); corregido: las pruebas rotas
   vuelven a ser las mismas 13 de antes, todas por permisos de symlinks de Windows, archivos ausentes de esta copia o
   codificación. Medido sin cerebro: la cobertura de las preguntas sobre constantes (D y R) pasa de 0/7 a 7/7.
2. **Lector de claves tolerante**: acepta cualquier «ALGO: palabra» (ministral3 escribía «EXTRANJERO: internacional»)
   y viñetas «- palabra».
3. **Flujo de identidad** (`lab_flujos/identidad.py`, condición `identidad`): claves verificadas → lista de TODOS los
   nombres del proyecto que contienen alguna clave → el cerebro elige uno o «NINGUNA» (solo vale un nombre de la
   lista) → código exacto de la elegida → respuesta citando «FUNCION_USADA» → comprobación sin IA: la función citada
   es la elegida o una que esta llama, y el valor está escrito literalmente en su código. Si no, se descarta.

## Comprobado antes (cerebro falso, sin tarjeta)
- Honrado: 45/45, con la correcta entre los candidatos en 40/40.
- Si da un número que no está en la función: 40/40 descartados. Si cita otra función: 40/40 descartados.
- Límite conocido: si el cerebro ELIGE una función vecina, su valor sí está en su código y pasa la comprobación
  literal; esa confusión solo la frena la elección. Por eso se mide aparte («elección correcta»).

## Montaje
- Mismo corpus (mismos bytes). 45 preguntas: las 25 parafraseadas de la tanda 4 (P) y 20 con el nombre exacto
  (A 6, B 4, D 3, R 4, trampas T 3).
- Condiciones: `ligero` (Contexto Ligero ya con constantes) e `identidad`. Cerebros qwen25 y ministral3, contexto
  4096, `max_tokens` 400 (200 para claves, 120 para elegir), temperatura 0.

## Reglas de decisión (fijadas antes de ver resultados)
- **Constantes arregladas** si `ligero` acierta D 3/3 y R 4/4 en los dos cerebros (en las tandas 1–3, D 0/3 y R 2/4).
- **La identidad aporta con paráfrasis** si, en los DOS cerebros, `identidad` acierta al menos 6 preguntas P más que
  `ligero`. Con 2 o menos, no aporta.
- **La identidad frena las confusiones** si las respuestas equivocadas con valor en las 25 P bajan a 5 o menos por
  cerebro (en la tanda 4 fueron 8–12).
- **Sin retroceso con nombres exactos**: en las 20 preguntas exactas, `identidad` acierta como mucho 1 menos que
  `ligero` en cada cerebro.
- Se informa además: la correcta entre los candidatos, elección correcta, «NINGUNA», respuestas descartadas por la
  comprobación, llamadas, tokens y segundos.

## Resultado (2026-11-15; 23 minutos, sin paradas)

| | qwen25 ligero | qwen25 identidad | ministral3 ligero | ministral3 identidad |
|---|---|---|---|---|
| Aciertos (de 45) | 20 | 10 | 22 | 11 |
| Exactas A / B / D / R / T | 6/6 · 4/4 · 3/3 · 4/4 · 2/3 | 1/6 · 0/4 · 2/3 · 2/4 · 1/3 | 6/6 · 4/4 · 3/3 · 4/4 · 3/3 | 0/6 · 0/4 · 1/3 · 3/4 · 2/3 |
| Parafraseadas P (de 25) | 1 | 4 | 2 | 5 |

Veredictos según las reglas fijadas:
- **Constantes arregladas: SÍ.** `ligero` acierta D 3/3 y R 4/4 en los dos cerebros (antes D 0/3 y R 2/4).
- **La identidad aporta con paráfrasis: NO** (+3 en los dos; umbral +6).
- **La identidad frena las confusiones: NO** (8 y 12 respuestas equivocadas con valor; umbral 5).
- **Sin retroceso con nombres exactos: NO, retrocede mucho** (A 0–1/6 y B 0/4 frente a 6/6 y 4/4).

Lectura: en este corpus, con cientos de nombres casi iguales, elegir de una lista confunde al cerebro (qwen25 eligió
«NINGUNA» 18 veces; la elección fue correcta en 10 de 45). La identidad no debe usarse siempre.
Cálculo posterior, NO prerregistrado: usar Contexto Ligero y solo si contesta «NO_ENCONTRADO» pasar a la identidad da
24/45 en los dos cerebros (+4 y +2), con 11–12 fallos (frente a 8–9).
