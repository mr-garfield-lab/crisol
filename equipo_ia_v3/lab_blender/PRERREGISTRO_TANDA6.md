# Preregistro: tanda 6 (manual v6: regla «import bpy» obligatoria, 800 tokens)

Escrito ANTES de lanzar la tanda 6. Fecha: 2026-11-14.

## Pregunta
¿Exigir explícitamente la línea `import bpy` al principio del script sube las aprobadas de ministral3 y granite, que en
la tanda 5 rechazaron la mayoría de sus intentos por el filtro (la causa era que el script no importaba bpy)?

## Hipótesis
Si la falta de `import bpy` es la causa principal de los rechazos, al añadir la regla deberían desaparecer casi todos
los rechazos de ese tipo y subir las aprobadas. Si no sube, el problema es otro (razonamiento o API), y lo registramos.

## Qué cambia respecto a la tanda 5
- Manual: `lab_blender/MANUAL_BLENDER_V6.md`, igual que el de la tanda 5 más una regla al principio.
- Huella SHA-256 del manual v6: 20cc83d3b7f85acb659e2ba5d399cbbd8f85f03fbd11ce8601b0b4924496daa0
- Huella del manual de la tanda 5 (sin la regla): 05ee4bf8074af57a5cc885dc897d0b55e55b22b4e82fa74f3b7780810597c252

## Qué NO cambia
- Las 12 tareas, el verificador, el filtro, 3 intentos por tarea, 800 tokens, el PC y las condiciones de seguridad.
- Los cerebros: gemma4, ministral3 y granite (los de la tanda 5).

## Carpeta
`evidencias/v31_lab_blender/tanda6`. Se compara con la tanda 5 (mismos cerebros, mismo manual sin la regla).

## Medidas
1. Aprobadas por cerebro, de 12. Tanda 5: gemma4 8, ministral3 3, granite 2.
2. Rechazos del filtro por la causa «bpy no está permitido» / «.ops» (tanda 5: ministral3 19 de 33 intentos
   rechazados por filtro; granite 15 de 24). Se cuenta aparte del total de rechazos.
3. Respuestas cortadas por longitud.

## Regla de decisión (fijada antes de ver resultados)
Suma de aprobadas de los tres cerebros frente a la tanda 5 (base: 13):
- **La regla ayuda** si la suma sube +3 o más y ningún cerebro baja.
- **La regla no ayuda** si la suma sube +1 o menos.
- En cualquier otro caso, "inconcluso".

Además, si los rechazos por falta de `import bpy` no bajan casi a cero, la hipótesis queda descartada aunque las
aprobadas suban.
