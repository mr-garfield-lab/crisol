# Preregistro: banco de Blender, tanda 13d (fases troceadas para T14)

Escrito ANTES de preguntar a ningún cerebro. Fecha: 2026-11-15.

## Pregunta
En la 13c, T14 (robot detallado de 14 piezas) se perdió por el límite de 800 tokens de respuesta: ministral3 cortó la
lista de piezas 3 veces y qwen25 cortó las relaciones 2 veces. ¿Lo aprueban si cada fase se pide por trozos?

## Cambio (solo `relacional2.py`; la 13c queda congelada en `relacional2_tanda13c.py`)
Condición nueva **`trozos`**: si la tarea tiene más de 8 piezas, las fases de piezas y de relaciones se piden en
trozos de 5 piezas, en el orden del enunciado (T14: Torso, Cabeza, Ojo_I, Ojo_D, Antena · Punta, Brazo_I, Brazo_D,
Mano_I, Mano_D · Pierna_I, Pierna_D, Pie_I, Pie_D), es decir 6 fases. Cada trozo ve lo ya aprobado, construye la
escena solo con las piezas hechas hasta ahí y se comprueba con las comprobaciones de esas piezas (las listas, como
«solo» o «sin_solapes», se recortan). Al final se comprueba todo junto con las 82. Si una respuesta trae piezas de
otro trozo, se avisa. Con 8 piezas o menos, «trozos» es igual que «fases». Resto igual que la 13c (calculadora con
posiciones, 800 tokens, 3 intentos por fase, verificador estricto, `--permitir_uso`).

## Comprobado antes (sin cerebro real)
`comprobar_relacional2.py` 23/23 (incluye la condición `trozos` en las cuatro tareas con un cerebro falso: T14 82/82
en 7 llamadas, con su fallo adrede arreglado) y `comprobar_componentes.py` 6/6.

## Qué se corre
Solo T14, condición `trozos`, qwen25 y ministral3. Referencia: T14 por `fases` en la 13c (qwen25 53/82, ministral3 0/82).

## Reglas de decisión (fijadas antes de ver resultados)
1. **El troceado quita los cortes** si ninguna respuesta de T14 termina cortada por el límite de tokens.
2. **Ayuda** si la suma final de T14 de los dos cerebros supera 53.
3. **Llega**: algún cerebro aprueba T14 (82/82).
4. Se informa en qué trozo se atasca cada cerebro y por qué.

## Resultados (`tanda13d`, 2026-11-15, 18:52–18:55, sin cortes)

| | 13c (fases) | 13d (trozos) | dónde se atasca |
|---|---|---|---|
| qwen25 | 53/82 | 53/82 | relaciones@1 (cabeza): los ojos; último intento 27/28 (ojo 0.15 m demasiado alto) |
| ministral3 | 0/82 | 53/82 | relaciones@1: quiere colocar «Punta», que es del trozo 2 |

1. **El troceado quita los cortes: sí.** Ninguna de las 14 respuestas se cortó (la más larga, 275 tokens de 800).
2. **Ayuda: sí en la cifra** (106 > 53): ministral3 ya no pierde la fase de piezas.
3. **Llega: no.** Nadie aprueba T14: los dos se atascan en el primer trozo de relaciones.
4. **Fallo de diseño (mío):** el trozo 1 termina en «Antena» y deja a su hija «Punta» para el trozo 2. ministral3
   la colocaba con la antena (lo natural) y el aviso decía «no está en piezas», que no le ayuda. Los trozos deberían
   no separar una pieza de sus hijas ni una pareja «_I»/«_D».
