# Preregistro: tanda 7 (manual v6 con la regla «import bpy», en qwen25 y yi, 800 tokens)

Escrito ANTES de lanzar la tanda 7. Fecha: 2026-11-14.

## Pregunta
¿El manual v6 (recetas + regla obligatoria `import bpy`), que subió +9 aprobadas a gemma4, ministral3 y granite en la
tanda 6, ayuda también a los dos cerebros que mejor iban sin él: qwen25 y yi?

## Hipótesis
En la tanda 1 casi no tuvieron fallos mecánicos: qwen25 1 rechazo del filtro (por `math`) y yi 4 (3 de sintaxis y 1
por guardar `bpy.ops`). Ninguno por falta de `import bpy`. Por tanto **se espera un efecto pequeño**: la regla no
tiene nada que arreglar, y el manual alarga el prompt. Puede ayudar en las recetas (jerarquía, animación, huesos) o
estorbar. Si suben claramente, el manual aporta algo más que la regla, y lo registramos.

## Qué cambia respecto a la tanda 1
- Manual: `lab_blender/MANUAL_BLENDER_V6.md`, el mismo de la tanda 6.
- Huella SHA-256: 20cc83d3b7f85acb659e2ba5d399cbbd8f85f03fbd11ce8601b0b4924496daa0

## Qué NO cambia
- Las 12 tareas, el verificador, el filtro, 3 intentos por tarea, 800 tokens, el PC y las condiciones de seguridad.
- El informe añade desde hoy una «puntuación parcial» (solo análisis: no cambia el aprobado ni lo que recibe el
  cerebro). La de la tanda 1 se calculó con sus datos guardados: qwen25 10,97/12, yi 9,20/12.

## Carpeta y orden
`evidencias/v31_lab_blender/tanda7`. Se compara con la tanda 1 (mismos cerebros, sin manual). Desde
`equipo_ia_v3`:

    py -B -X utf8 eq3/lanzador_eq2.py lab_blender/banco.py ejecutar <EXTERNOS> evidencias/v31_lab_blender/tanda7 <EXTERNOS>/blender_lab --modelos qwen25 yi --manual lab_blender/MANUAL_BLENDER_V6.md

Con los juegos cerrados: el banco espera si otra cosa ocupa más de 1,1 GB de VRAM.

Corrección de la orden (2026-11-15, antes de cualquier resultado): la primera versión omitía `eq3/lanzador_eq2.py`.
Sin él, Windows no da la lectura de memoria y el banco se detuvo al arrancar qwen25, con 0 intentos hechos. El diseño
no cambia; se reanuda en la misma carpeta con `--reanudar`.

## Medidas
1. Aprobadas por cerebro, de 12. Tanda 1: qwen25 9, yi 8 (base: 17).
2. Puntuación parcial. Tanda 1: qwen25 10,97, yi 9,20.
3. Rechazos del filtro (tanda 1: qwen25 1, yi 4) y respuestas cortadas por longitud (tanda 1: qwen25 0, yi 5).

## Regla de decisión (fijada antes de ver resultados)
Suma de aprobadas de los dos cerebros frente a la tanda 1 (base: 17):
- **El manual ayuda** si la suma sube +2 o más y ningún cerebro baja.
- **El manual estorba** si la suma baja −2 o más.
- En cualquier otro caso, **sin efecto claro**: con 12 tareas, ±1 está dentro del ruido.

Además: si las respuestas cortadas por longitud suben en 3 o más para un cerebro, se anota como posible coste del
prompt más largo, sea cual sea el resultado.

## Resultado (2026-11-15, tras terminar)

- qwen25: 9/12 (igual que la tanda 1). yi: 9/12 (sube +1 desde 8/12). Suma: 18 frente a la base de 17 → **+1**.
- **Veredicto según la regla fijada: sin efecto claro** (no llega a +2). Era lo esperado: ninguno de los dos tenía
  fallos por falta de `import bpy` en la tanda 1.
- yi aprobó T09 (esqueleto de tres huesos), que antes fallaba; es la única tarea que cambió de veredicto.
- Respuestas cortadas por longitud: qwen25 0 → 3, yi 5 → 4. Sin subida relevante.
- Rechazos del filtro: qwen25 1 → 2, yi 4 → 0.
