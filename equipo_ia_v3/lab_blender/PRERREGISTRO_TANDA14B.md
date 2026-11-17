# Preregistro: banco de Blender, tanda 14b (componentes con avisos arreglados y préstamo)

Escrito ANTES de preguntar a ningún cerebro. Fecha: 2026-11-15.

## Pregunta
En la 14 nadie montó el F1 ni el kart: solo ministral3 aprobó un componente (alerón delantero). ¿Mejoran con avisos
que explican sus fallos, y saben MONTAR si se les presta el componente que no consiguieron?

## Cambios (solo `componentes.py`; la 14 queda congelada en `componentes_tanda14.py`)
1. Sistema: reglas de los componentes (orden de medidas según el eje; la caja total incluye lo que sobresale; el padre
   es una pieza del componente).
2. Aviso de medidas en otro orden (los números bien, el orden mal): dice el orden correcto.
3. Aviso de la caja total: qué pieza marca cada borde en x, y, z y la caja que sale.
4. Aviso del padre fuera del componente.
5. La pregunta del componente va primero y sola («AHORA SOLO el componente…»), con una sola línea de contexto.
6. **Préstamo**: si un componente se agota (3 intentos), el montaje sigue con la ficha de referencia del programa,
   marcada «PRESTADO»; no entra en su biblioteca y el final lo anota en `prestados`.
7. La imagen de la biblioteca se renderiza en una carpeta única (antes podía chocar con una tanda anterior).
Resto igual que la 14: T15 (F1, 87) y T16 (kart, 43), qwen25, ministral3, gemma12, 3 intentos, 800 tokens,
`--permitir_uso`. Biblioteca nueva y vacía: `evidencias/v31_lab_blender/tanda14b_biblioteca/`.

## Comprobado antes (sin cerebro real)
`comprobar_componentes.py` 8/8 (dos nuevas: el aviso del orden de medidas y el montaje con rueda prestada, 87/87,
sin guardarla en la biblioteca).

## Reglas de decisión (fijadas antes de ver resultados)
1. **Los avisos ayudan** si los componentes aprobados en total suben respecto a la 14 (1 de 9 en T15).
2. **Saben montar**: algún cerebro aprueba T15 o T16 (con o sin préstamo; se informa cuál).
3. **Diseño propio completo**: algún cerebro aprueba T15 o T16 sin ningún préstamo.
4. **La biblioteca funciona** si quien aprueba la rueda en T15 la reutiliza en T16 a la primera.
5. Se informa: respuestas cortadas, repeticiones idénticas tras un aviso y segundos por respuesta.

## Incidencia durante la tanda (2026-11-15, 20:48)
gemma12 aprobó sus tres componentes y el banco lo cortó por VRAM (7414 MiB > su tope de 7168): la imagen de cada
componente aprobado se renderizaba en Blender (EEVEE, GPU) MIENTRAS gemma12 seguía cargado. Fallo mío: el banco dice
que con un cerebro en la GPU Blender solo mide. Arreglo: durante la tanda las imágenes se dejan pendientes y se hacen al
terminar (`imagenes()`); `comprobar_componentes.py` sigue 8/8. Se reanuda solo gemma12 (`--reanudar`): lo ya hecho
(componentes aprobados y guardados) no se repite; no cambia nada de lo que ven los cerebros.

## Resultados (2026-11-15, fin 22:45; informe en `evidencias/v31_lab_blender/tanda14b/INFORME.md`)
| modelo | T15 (F1) | T16 (kart) | componentes aprobados en T15 | prestados |
|---|---|---|---|---|
| qwen25 | 0/87 | 0/43 | aleron_delantero, aleron_trasero (2/3) | rueda |
| ministral3 | 0/87 | 29/43 | aleron_trasero (1/3) | rueda, aleron_delantero |
| gemma12 | 0/87 | 29/43 | rueda, aleron_delantero, aleron_trasero (3/3, cada uno al 2.º intento) | ninguno |

1. **Los avisos ayudan: SÍ.** 6 de 9 componentes aprobados en T15 (frente a 1 de 9 en la 14).
2. **Saben montar: NO.** Nadie aprueba T15 ni T16. En T15 nadie pasa de la fase de piezas (gemma12 llega a 41/45:
   las suspensiones sin "padre" Chasis; una respuesta cortada). En T16 ministral3 y gemma12 pasan las piezas (19/19) y
   se atascan en relaciones (conflictos coordenada fija + relación, pieza de referencia sin posición).
3. **Diseño propio completo: NO** (consecuencia de la 2).
4. **La biblioteca funciona: SÍ.** gemma12 aprobó la rueda en T15 y en T16 la reutilizó a la primera (1 intento).
5. Cortadas: qwen25 1, ministral3 0, gemma12 1. Repeticiones idénticas tras aviso: ministral3 2, resto 0.
   Segundos por respuesta (media): qwen25 11,0 · ministral3 18,2 · gemma12 36,7.

Lectura: el cuello de botella ya no son los componentes sino el montaje del coche entero (muchas piezas y relaciones a
la vez). Siguiente paso candidato (no decidido): montaje por trozos/familias como en 13d/13e y avisos de tubos.
