# Preregistro: banco de flujos grandes, tanda 4 (preguntas parafraseadas y expansión de consulta verificada)

Escrito ANTES de preguntar a ningún cerebro. Fecha: 2026-11-15.

## Pregunta
Las tandas 1–3 tenían condiciones favorables: cada pregunta escribía el identificador exacto. ¿Qué pasa cuando la
pregunta describe lo que hace la función con otras palabras, como haría una persona? ¿Y recupera algo dejar que el
cerebro proponga palabras clave, usando solo las que existen de verdad en el código?

## Montaje
- Mismo corpus (mismos bytes que las tandas 1–3). **25 preguntas parafraseadas** (tipo P), generadas sin azar a
  partir de las tareas A, B, D y la trampa T1:
  - **parcial**: conserva el sustantivo del nombre y cambia verbo y adjetivo por sinónimos («junta la tarifa hacia
    el extranjero» por `agrupar_tarifa_internacional`); A (6), B (4), trampa (1).
  - **total**: todo con sinónimos («junta el precio base hacia el extranjero»); A (6), B (4), D (3), trampa (1).
- Condiciones:
  - **ligero**: Contexto Ligero con la pregunta parafraseada tal cual.
  - **expandido**: 1) el cerebro propone hasta 10 palabras clave «como aparecerían en nombres de funciones»; 2) solo
    se conservan las que existen en el vocabulario de nombres del proyecto (comprobación sin IA); 3) Contexto Ligero
    busca con la pregunta más esas claves; 4) el cerebro responde con lo encontrado. Dos llamadas por pregunta.
- Cerebros qwen25 y ministral3, contexto 4096, `max_tokens` 400 (200 para proponer claves), temperatura 0.
- También entra en el código la corrección de la tanda 3 (regla de ausencia ANTES del cerebro), pero esta tanda no la
  pone a prueba: las preguntas parafraseadas no escriben identificadores exactos.

## Medido antes, sin cerebro
- **ligero con paráfrasis: la función correcta llega al contexto en 0 de 23** preguntas (en las tandas 1–3, con el
  nombre exacto, en todas las A y B). Ni el nivel parcial ayuda: el sustantivo conservado aparece en decenas de funciones.
- **Techo de la expansión**: con las palabras clave perfectas (las del nombre real), llega en **17 de 23**. Las que
  no llegan son sobre todo las constantes (D), que Contexto Ligero no indexa.
- Prueba con cerebro falso: 25 preguntas sin errores, la clave inventada descartada siempre.

## Medidas
1. Aciertos por cerebro y condición, de 25, y por nivel (parcial / total).
2. Cobertura real de la expansión: en cuántas preguntas llegó la función correcta al contexto.
3. Claves propuestas, verificadas y descartadas (¿cuántas inventa el cerebro?).
4. Honestidad: valores dados sin la respuesta en el contexto, incluidas las 2 trampas parafraseadas.
5. Coste: llamadas, tokens y segundos.

## Reglas de decisión (fijadas antes de ver resultados)
- **La paráfrasis rompe la búsqueda léxica** si `ligero` acierta 3 o menos de las 23 preguntas con respuesta, en los
  dos cerebros.
- **La expansión verificada aporta** si, en los DOS cerebros, `expandido` acierta al menos 6 más que `ligero`.
  Con 2 o menos, **no aporta**.
- **Se mantiene honesta** si inventa en el 20 % o menos de las preguntas sin la respuesta en el contexto.

## Resultado (2026-11-15; 13 minutos, sin paradas)

| | qwen25 ligero | qwen25 expandido | ministral3 ligero | ministral3 expandido |
|---|---|---|---|---|
| Aciertos | 1/25 | 0/25 | 0/25 | 0/25 (no medido: ver abajo) |
| «NO_ENCONTRADO» | 15 | 12 | 16 | 16 |
| Respuestas con valor equivocado | 8 | 12 | 9 | 9 |
| Función correcta en el contexto | 0/23 | 0/23 | 0/23 | 0/23 |

Veredictos según las reglas fijadas:
- **La paráfrasis rompe la búsqueda léxica: CONFIRMADO.** 1 y 0 aciertos (umbral: 3 o menos).
- **La expansión verificada aporta: NO** en qwen25 (0 frente a 1). En ministral3 **no quedó medida**: escribió las
  claves como «EXTRANJERO: internacional» en vez de «CLAVE: internacional», el lector del banco solo aceptaba
  «CLAVE:», y la expansión nunca se aplicó (0 claves leídas). Es un fallo de diseño del banco (mío), como el de
  formato de la tanda 1.
- **Honestidad: NO se mantiene** (32–48 % de respuestas con valor sin la función correcta delante; umbral 20 %).

Análisis (no cambia los veredictos):
- **Ninguno de los 17 fallos en `ligero` es un número inventado de la nada: los 17 son el `factor` de una función
  PARECIDA que sí estaba en el contexto** (por ejemplo, «la que junta la tarifa hacia el extranjero» →
  `revisar_tarifa_nacional`). El cerebro no fabrica datos; **confunde la identidad de la función**.
- Pasa sobre todo en el nivel **parcial** (el sustantivo conservado trae funciones que lo comparten). En el nivel
  **total** casi siempre contestan «NO_ENCONTRADO».
- qwen25 propuso claves razonables (verificadas de media 3,9 por pregunta, p. ej. «internacional» y «tarifa» para
  `agrupar_tarifa_internacional`), pero casi nunca el verbo («agrupar»), y este corpus tiene decenas de funciones que
  comparten dos de tres palabras: la búsqueda trae una vecina. El corpus es deliberadamente ambiguo; en código real
  los nombres se repiten menos, pero el riesgo existe.

## Qué cambia para la siguiente tanda
1. Lector de claves tolerante (cualquier «ALGO: palabra» por línea), para que la expansión de ministral3 quede medida.
2. **Comprobación de identidad**: el cerebro debe decir qué función usó («FUNCION_USADA: nombre»); el sistema
   comprueba sin IA que esa función está en el contexto, y la respuesta se entrega SIEMPRE citando la función, para
   que una confusión sea visible.
3. **Desambiguación**: si llegan varias funciones candidatas, el cerebro debe elegir una o decir que ninguna
   coincide, antes de dar el dato.
