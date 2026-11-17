# Preregistro: banco de flujos grandes en JAVA, tanda 1

Escrito ANTES de preguntar a ningún cerebro. Fecha: 2026-11-15.

## Pregunta
Contexto Ligero ya lee Java (comprobado sin cerebros: 51/51 con un mod de ejemplo). ¿Aciertan de verdad qwen25 y
ministral3 cuando se les da código Java de un proyecto mucho mayor que su contexto? ¿Funciona igual la combinación
que en Python (búsqueda y, si no encuentra, identidad)?

## Montaje
- Proyecto sintético en Java (`lab_flujos/generar_java.py`, semilla 20261116, determinista): 64 clases del mismo
  paquete, ~657.000 caracteres (~219.000 tokens, unas 53 veces el contexto). **Compila con javac sin errores**
  (comprobado en `preparar`; si no compila, no se sigue).
- 38 preguntas: A datos escondidos en métodos (6), B dos saltos entre clases (4), D constantes `static final` (3),
  T trampas (3: método inexistente, constante casi igual a otra que sí existe, variable que el método no tiene) y
  P las búsquedas A, B y la trampa del método parafraseadas, en nivel parcial y total (22).
- Sin recuentos en esta versión (el troceado del banco todavía solo sabe partir Python).
- Condiciones: `ligero` y `combinada` (identidad sobre un catálogo de Java hecho con el analizador de Java de
  Contexto Ligero; prompts iguales que en Python cambiando «Python» por «Java»).
- Cerebros qwen25 y ministral3; contexto 4096; temperatura 0; mismo armazón de seguridad.

## Medido antes, sin cerebro
Cobertura de `ligero`: A 6/6, B 4/4, D 3/3, P 0/22. Cerebro falso perfecto con `combinada`: 38/38, la comprobación
literal verificada en Java y la elección de la identidad correcta en las 25 que pasan por ella.

## Reglas de decisión (fijadas antes de ver resultados)
1. **Java se lee bien** si `ligero` acierta al menos 11 de las 13 preguntas exactas (A, B, D) en los DOS cerebros.
2. **La combinada aporta en Java** si acierta al menos 3 preguntas parafraseadas (P) más que `ligero` en los dos.
3. **Honestidad con trampas**: la combinada contesta «no existe» en las 3 trampas en los dos cerebros (se permite 1
   fallo por cerebro).
4. Se compara además con Python (tanda 7, corpus sintético): exactas 21/21 y parafraseadas 4/25 con la combinada.

## Resultado (2026-11-15; 13 minutos, sin paradas)

| | qwen25 ligero | qwen25 combinada | ministral3 ligero | ministral3 combinada |
|---|---|---|---|---|
| Total (de 38) | 16 | 16 | 17 | 15 |
| **Exactas** A / B / D | **6/6 · 4/4 · 3/3** | 6/6 · 4/4 · 3/3 | **6/6 · 4/4 · 3/3** | 6/6 · 4/4 · 3/3 |
| Parafraseadas P (de 22) | 1 | 1 | 1 | 0 |
| Trampas T (de 3) | 2 | 2 | 3 | 2 |
| Respuestas con valor equivocado | 5 | 10 | 4 | 9 |

Veredictos según las reglas fijadas:
1. **Java se lee bien: SÍ.** 13 de 13 exactas en los dos cerebros (umbral 11), incluidos los dos saltos entre clases y
   las constantes `static final`. Igual que Python (21/21 en la tanda 7).
2. **La combinada aporta en Java: NO** (+0 y −1 parafraseadas). Igual que en el corpus sintético de Python (tanda 7):
   con cientos de nombres casi iguales, la identidad elige vecinos y suma confusiones (de 5 a 10 y de 4 a 9).
3. **Honestidad con trampas: SÍ** dentro del margen (2 de 3 en la combinada en los dos; se permitía 1 fallo).

Lectura: con el nombre exacto, los cerebros leen Java tan bien como Python. Las paráfrasis siguen siendo el límite en
corpus ambiguos, en los dos lenguajes. En código real de Python la combinada sí ayudó (tanda 7: +5 y +6); para saber
si pasa lo mismo en Java hace falta un proyecto Java real (por ejemplo, un mod propio del usuario o de su amigo).
Mejora pendiente: aplicar la regla de ausencia (si el nombre pedido no existe en ningún archivo, «no existe» sin
preguntar al cerebro) también en la combinada; habría evitado el fallo de JT1.
