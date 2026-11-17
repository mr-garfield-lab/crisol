# Preregistro: tanda 4 (sensibilidad al tope de tokens)

Escrito ANTES de lanzar la tanda 4. Fecha: 2026-11-14.

## Pregunta
¿Subir el tope de tokens por respuesta de 800 a 1200 cambia cuántas tareas aprueban gemma4, ministral3 y granite?

## Por qué
En las tandas 2 y 3 hubo respuestas cortadas por longitud: gemma4 10, ministral3 9, granite 5. Un script cortado no
es un script malo: puede que el cerebro lo hubiera terminado con más espacio. Esta tanda mide si ese corte pesa.

## Qué NO cambia
- Las 12 tareas (T01–T10, B01–B02), el verificador sin IA, el filtro de seguridad y el límite de 3 intentos.
- El prompt y el procedimiento de corrección.
- El PC: mismas condiciones de seguridad (libre, VRAM, térmica, STOP, reanudación).

## Qué cambia
- Tope de tokens por respuesta: 1200 (antes 800). Se pasa con `--tokens 1200`; queda anotado en `banco.json` como `tokens`.
- Solo tres cerebros: los que tuvieron cortes. qwen25, qwen3 y yi no se repiten (no tenían cortes).

## Carpeta
`evidencias/v31_lab_blender/tanda4`. No se mezcla con las tandas 1–3 en las tablas principales.

## Medidas
1. Aprobadas por cerebro, de 12 (igual que antes).
2. Respuestas cortadas por longitud, con 1200 frente a 800 (tandas 2 y 3).
3. Número de intentos usados por cerebro.

## Regla de decisión (fijada antes de ver resultados)
- **El tope pesa** si: las cortadas bajan a 0–1 por cerebro Y cada cerebro aprueba al menos 2 tareas más que en su
  tanda anterior.
- **El tope no pesa** si: las cortadas bajan pero las aprobadas suben como mucho 1, o no suben.
- En cualquier otro caso, se declara "inconcluso", sin conclusión.

Esta tanda es un análisis de sensibilidad. Sus resultados no sustituyen la tabla de las tandas 1–3.
