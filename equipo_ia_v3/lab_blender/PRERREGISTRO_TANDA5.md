# Preregistro: tanda 5 (manual de recetas en el prompt, 800 tokens)

Escrito ANTES de lanzar la tanda 5. Fecha: 2026-11-14.

## Pregunta
¿Dar a los modelos un manual de recetas de Blender 5.2 (primitivas, tamaños, jerarquías, animación, materiales,
armaduras) sube cuántas tareas aprueban gemma4, ministral3 y granite, con el mismo tope de 800 tokens?

## Por qué
Las tandas 1–3 muestran que los modelos fallan en partes del uso de la API (rechazos del filtro, nombres inventados) y
en tareas de varias piezas que no planifican. Un manual de recetas generales ataca lo primero. No sustituye la
planificación de las tareas largas, y eso se mide también.

## Qué NO cambia
- Las 12 tareas, el verificador sin IA, el filtro de seguridad, el límite de 3 intentos y el tope de 800 tokens.
- El PC: mismas condiciones de seguridad.
- Los tres cerebros: gemma4, ministral3 y granite (los mismos de las tandas 2 y 3).

## Qué cambia
- Se añade al prompt del sistema el manual `lab_blender/MANUAL_BLENDER.md`, con `--manual`.
- Huella del manual (SHA-256): 05ee4bf8074af57a5cc885dc897d0b55e55b22b4e82fa74f3b7780810597c252.
- Validación previa del manual: los 6 ejemplos de `lab_blender/MANUAL_BLENDER_BORRADOR.md` pasan el filtro y se ejecutan
  OK en Blender 5.2 (ese mismo texto, sin el encabezado).
- El manual no contiene la solución de ninguna tarea de `tareas.py`. Las referencias de `tareas.py` nunca entran en el
  prompt.

## Carpeta
`evidencias/v31_lab_blender/tanda5`. Se compara con la tabla de las tandas 2 y 3 (mismos cerebros, sin manual).

## Medidas
1. Aprobadas por cerebro, de 12.
2. Respuestas cortadas por longitud (tandas 2 y 3: gemma4 10, ministral3 9, granite 5).
3. Rechazos del filtro por cerebro (tandas 2 y 3: gemma4 9, ministral3 7, granite 8).

## Regla de decisión (fijada antes de ver resultados)
Diferencia de aprobadas respecto a su tanda anterior, sumada en los tres cerebros:
- **El manual ayuda** si la suma es de +3 o más y ningún cerebro baja.
- **El manual no ayuda** si la suma es de +1 o menos.
- En cualquier otro caso, "inconcluso".

Los rechazos del filtro y los cortes se reportan aparte; no cambian la regla.

Esta tanda cambia el prompt, así que sus resultados se reportan como efecto del manual, no se mezclan con la tabla general.
