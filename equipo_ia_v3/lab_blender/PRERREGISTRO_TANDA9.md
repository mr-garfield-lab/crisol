# Preregistro: banco de Blender, tanda 9 (robots por pasos)

Escrito ANTES de preguntar a ningún cerebro. Fecha: 2026-11-15.

## Pregunta
Ningún cerebro ha aprobado nunca los robots T05 (25 comprobaciones) ni T08 (32, con animación) pidiéndolos de una
vez. Lo más cerca: ministral3 con el manual, 22/25 (88 %) y 27/32 (84 %); qwen25 con el manual, 16/25 (64 %) y 20/32
(63 %). ¿Es un problema de planificar todo en un solo turno? Si se piden por partes, ¿los terminan?

## Montaje (`lab_blender/pasos.py`)
- Pasos: torso → cabeza → piernas → brazos (→ animación en T08). Instrucciones sacadas del enunciado original.
- En cada paso el cerebro ve el objetivo final, el script ya aprobado y el paso actual, y escribe SOLO el código nuevo,
  que se añade al final (no reescribe lo aprobado ni le corta el tope de 800 tokens).
- Verificación sin IA en Blender: comprobaciones del paso y de todos los anteriores. Hasta 3 intentos por paso con lo
  medido como respuesta; si un paso se agota, el robot queda sin terminar.
- Cierre: el script aprobado se verifica con TODAS las comprobaciones originales de la tarea.
- Cerebros qwen25 y ministral3, manual v6 (con la regla `import bpy`), 800 tokens, temperatura 0, mismo armazón de
  seguridad y mismo filtro de seguridad del banco de Blender.

## Comprobado antes (cerebro falso con el código de referencia; `comprobar_pasos.py`)
T05 25/25 y T08 32/32 aprobados por pasos en Blender real; un fallo adrede en la cabeza se rechaza y se arregla en el
segundo intento.

## Reglas de decisión (fijadas antes de ver resultados)
1. **Los pasos aportan** si cada cerebro aprueba al menos uno de los dos robots completos (todas las comprobaciones).
2. **Resultado fuerte** si los dos cerebros aprueban los dos robots.
3. **Sin retroceso**: en cada robot y cerebro, la fracción final de comprobaciones cumplidas no baja de su mejor
   resultado de una vez (ministral3 88 % y 84 %; qwen25 64 % y 63 %).
4. Se informa en qué paso se atasca cada uno y cuántos intentos necesita.

## Resultado (2026-11-15; 3 minutos, sin paradas)

| | T05 (robot) | T08 (robot animado) |
|---|---|---|
| qwen25 | 1/4 pasos · no (2/25) | 1/5 pasos · no (2/32) |
| ministral3 | **4/4 pasos · APROBADO (25/25)** | 1/5 pasos · no (2/32) |

**Primera vez que un cerebro aprueba un robot completo** (ministral3, T05; de una vez nunca pasó de 22/25).

Veredictos según las reglas fijadas:
1. **Los pasos aportan (cada cerebro aprueba al menos un robot): NO.** ministral3 sí (T05); qwen25, ninguno.
2. **Resultado fuerte: NO.**
3. **Sin retroceso: NO** en 3 de 4 casos. Por diseño, el resultado final es el script aprobado hasta el último paso
   superado: si se atasca en la cabeza, solo queda el torso (2/25, 2/32), muy por debajo del 63–88 % de una vez.

Dónde se atascan: **la cabeza (paso 2), en 3 de los 4 robots.**
- qwen25 crea la cabeza de 0,25 m en vez de 0,5 y la deja baja, y **repite exactamente el mismo código en los 3
  intentos** aunque el verificador le dice lo que mide (temperatura 0 y respuesta idéntica).
- ministral3 pone el centro de la cabeza a la altura de lo alto del torso (su base queda en z = 2,35 en vez de 2,60);
  cambia el código en cada intento, pero no da con la cuenta (en T05 lo consigue al tercero).

## Para la siguiente tanda (propuestas)
- **Aviso de código repetido** (como en el banco de revisión): si el código nuevo es idéntico al del intento anterior,
  decírselo y pedir otro distinto.
- **Más intentos en los pasos difíciles**, o una pista geométrica genérica en el aviso («para que un objeto apoye
  encima de otro, su base debe quedar en lo alto del otro: centro = alto del otro + media altura propia»), sin dar el
  número de la tarea.
- Medir aparte la fracción del último script intentado, para comparar con el resultado de una vez.

## CORRECCIÓN (2026-11-15, revisando el vídeo del robot animado)
El verificador tenía un hueco: «toca» daba por buena cualquier caja pegada o METIDA en el torso, y nada comprobaba
que los brazos estuvieran a los lados. Los robots «aprobados» tenían los brazos mal:
- tanda 9, ministral3 T05: brazos metidos 0,10 m en el torso y colgando casi enteros por debajo (z 0,5–1,5).
- tanda 11, ministral3 T05: brazos metidos 0,12 m en el torso.
- tanda 11, ministral3 T08: brazos DEBAJO del torso, metidos 0,23 m dentro de las piernas.
Se añaden a T05 y T08 tres comprobaciones (`a_un_lado` para cada brazo y `sin_solapes` entre todas las piezas); las
referencias siguen aprobando (28/28 y 35/35). Revisados con ellas, **ningún robot de ninguna tanda queda aprobado**:
los tres pasan a 25/28, 25/28 y 32/35. Las lecturas sobre la cabeza y las cuentas siguen valiendo; lo de «primer
robot aprobado» no.
