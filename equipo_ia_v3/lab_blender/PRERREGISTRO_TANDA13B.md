# Preregistro: banco de Blender, tanda 13b (calculadora y avisos exactos)

Escrito ANTES de preguntar a ningún cerebro. Fecha: 2026-11-15.

## Pregunta
En la tanda 13 los cerebros fallaron al describir la escena: piernas sin x (una dentro de otra), piezas colocadas dos
veces (un número suelto + una relación) que en el reintento solo cambiaban el número, y argumentos inventados. ¿Mejoran
si pueden escribir fórmulas en vez de hacer cuentas y si el aviso dice exactamente qué borrar?

## Cambios respecto a la tanda 13 (solo el resolvedor y el sistema; `relacional2.py`)
1. **Calculadora**: cualquier número puede ser una fórmula «= …» con las medidas de las piezas (alto, ancho, fondo,
   mitad, mitad_x, mitad_y; + − × ÷, paréntesis, sqrt, sin, cos en grados). Se evalúa recorriendo el árbol, sin
   ejecutar código (un intento de meter `__import__` se rechaza).
2. **Conflicto**: el aviso dice qué relación BORRAR y cuál dejar (antes: «quita una de las dos»).
3. **Pareja «_I»/«_D» en el mismo sitio**: se detecta antes de Blender y se dice qué fijar y usar `espejo_x`.
4. **Relación mal escrita**: el aviso enseña cómo se escribe (y propone `mover` si sobran números).
Todo lo demás igual: tareas T05, T08, T13 y T14, solo la condición `fases` (la mejor de la tanda 13), qwen25 y
ministral3, 800 tokens, 3 intentos por fase, verificador estricto. Se corre con `--permitir_uso` (el PC se usa a la
vez; VRAM, GPU, térmica y pausas de enfriamiento siguen).

## Comprobado antes (sin cerebro real)
`comprobar_relacional2.py` 16/16 y `comprobar_componentes.py` 6/6 con el resolvedor nuevo; pruebas sueltas de la
calculadora (x de la pierna = −0,30 con una fórmula), del aviso BORRA, de la pareja en el mismo sitio y del rechazo de
código en una fórmula.

## Reglas de decisión (fijadas antes de ver resultados)
1. **Los cambios ayudan** si la suma de comprobaciones finales de las 8 combinaciones supera a la de la tanda 13 por
   fases (119 + 84 = 203 de 390).
2. **Llega a lo complicado** si cada cerebro aprueba T13 o T14.
3. **Sin retroceso**: los dos cerebros vuelven a aprobar T05.
4. Se informa cuántas respuestas usan fórmulas, cuántos conflictos se arreglan tras el aviso BORRA y cuántas parejas
   en el mismo sitio se detectan y se arreglan.

## Primer intento: ANULADO (2026-11-15, 15:01–15:08)
1. **Fallo del resolvedor (mío)**: una coordenada que una relación rellena por defecto (la x de «Pierna_D» copiada del
   torso por `debajo`) contaba como fijada, así que un `espejo_x` posterior daba «conflicto» y el aviso BORRA proponía
   borrar el `espejo_x`, que era lo correcto. Afectó a 3 de 24 intentos de este arranque (y a 1 de 54 en la tanda 13:
   qwen25 · fases · T08 · relaciones · intento 3). Arreglado: lo puesto por defecto se puede cambiar con una relación
   explícita; los conflictos reales siguen avisándose. Además ministral3 escribió `mitad_z(…)`: se añade como sinónimo
   (y una función desconocida ahora propone la parecida).
2. Cortado por el **freno térmico de hardware** (78 °C, GPU al 95 %) con Roblox abierto en segundo plano.
Lo que sí se vio: el detector de pareja en el mismo sitio hizo que qwen25 usara `espejo_x` (y el fallo de arriba se lo
rechazó); qwen25 aprobó T08 por primera vez (35/35). Este arranque queda en `evidencias/v31_lab_blender/tanda13b`
como anulado; la tanda se repite entera en `tanda13b_2` con el resolvedor arreglado.

## Resultados del segundo arranque (`tanda13b_2`, 2026-11-15, 18:13–18:22, sin cortes)

| | T05 | T08 | T13 | T14 | suma |
|---|---|---|---|---|---|
| qwen25 (tanda 13 → 13b) | 28 ✓ → 28 ✓ | 17 → 28 | 21 → 21 | 53 → 53 | 119 → 130 |
| ministral3 (tanda 13 → 13b) | 28 ✓ → 17 | 35 ✓ → 17 | 21 → 21 | 0 → 53 | 84 → 108 |

1. **Los cambios ayudan: sí en la cifra (238 > 203), pero con matiz.** De los +35, +53 vienen de que ministral3 esta
   vez no cortó la fase de piezas de T14 (no es efecto de la calculadora ni de los avisos); quitando eso, la suma baja.
2. **Llega a lo complicado: no.** Nadie aprueba T13 ni T14.
3. **Sin retroceso: NO se cumple.** ministral3 deja de aprobar T05 (y T08).
4. Recuentos:
   - **Fórmulas**: ministral3 las usó en sus 12 respuestas de relaciones; qwen25 en ninguna. ministral3 las usó mal:
     calcula una distancia relativa («= alto(Torso)/2 + mitad(Cabeza)») y la pone como posición absoluta en un
     `centro`, a la vez que una relación (`encima`) coloca la misma pieza. Así provocó 7 conflictos.
   - **Aviso BORRA**: 10 conflictos. ministral3 resolvió el conflicto concreto en 2 de sus 3 tareas, pero creando
     otro o dejando piezas separadas. qwen25 repitió el mismo error de T14 3 veces seguidas: no hizo caso al aviso.
   - **Pareja en el mismo sitio**: 4 detecciones, todas de qwen25. Arregló la pareja en sus 3 tareas (T05, T08, T13);
     T08 es la mejora de qwen25.
   - ministral3 · T14 · relaciones: las 3 respuestas cortadas a 800 tokens (JSON sin terminar).

**Lectura:** el aviso de la pareja funciona. La calculadora, tal y como está, confunde a ministral3: le da distancias
y él las usa como posiciones. Si se mantiene, debería dar posiciones (p. ej. `arriba(Torso)`) o no aceptarse en
`centro` de una pieza que ya coloca una relación. Lo que falla en T14 es el límite de tokens en la fase de relaciones
(proponer: relaciones por tandas).
