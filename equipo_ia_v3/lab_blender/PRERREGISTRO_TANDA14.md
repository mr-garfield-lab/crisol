# Preregistro: banco de Blender, tanda 14 (componentes y biblioteca personal: F1 y kart)

Escrito ANTES de preguntar a ningún cerebro. Fecha: 2026-11-15.

## Pregunta
¿Pueden los cerebros diseñar componentes (rueda, alerones), guardarlos en su biblioteca personal con ficha, imagen y
versión, montar con ellos un Fórmula 1 (T15, 87 comprobaciones) y REUTILIZAR la rueda en un kart (T16, 43)?

## Cómo (`componentes.py`, sin cambios desde su comprobación)
1. Para cada componente de la tarea: si no lo tiene, escribe su **ficha** (para qué sirve, caja total que ocupará =
   su preregistro, piezas y relaciones). El programa lo construye en Blender y comprueba lo pedido + que cumple su
   ficha (`caja_total`) + que sus piezas están unidas (`conectado`). Aprobado → entra en su biblioteca (JSON + PNG,
   versión 1). Si ya lo tiene, decide **reutilizar** (se comprueba contra lo pedido) o **rediseñar** (versión nueva).
2. Montaje por fases (piezas → relaciones), con los componentes como piezas (instancias) más cuñas, tubos y cajas.
3. Cierre con todas las comprobaciones. 3 intentos por paso, 800 tokens, verificador estricto, `--permitir_uso`.
Orden: T15 (F1) y después T16 (kart), así que el kart encuentra la rueda ya en la biblioteca.
Cerebros: qwen25, ministral3 y gemma12 (equipo de tres desde hoy). Biblioteca nueva y vacía:
`evidencias/v31_lab_blender/tanda14_biblioteca/<modelo>/`.

## Comprobado antes (sin cerebro real)
`comprobar_componentes.py` 6/6 (F1 87/87; el kart reutiliza la rueda en 1 llamada; ficha mal declarada → avisada).

## Límite conocido
El montaje del F1 lleva 16 entradas en la fase de piezas; con 800 tokens puede cortarse (como T14 por fases). No se
trocea en esta tanda: si se corta, queda como dato para la siguiente.

## Reglas de decisión (fijadas antes de ver resultados)
1. **La biblioteca funciona** si cada cerebro que aprueba la rueda en T15 la reutiliza en T16 a la primera (o la
   rediseña con motivo) y su biblioteca queda con ficha, imagen y versión.
2. **Componentes**: se cuenta cuántos de los 3 componentes aprueba cada cerebro.
3. **Llega al montaje**: algún cerebro aprueba T15 o T16 completos.
4. Se informa: respuestas cortadas, intentos por componente y fase, y segundos por respuesta.

## Resultados (`tanda14`, 2026-11-15, 19:59–20:24, sin cortes del banco)

| | rueda | alerón delantero | alerón trasero | F1 (T15) | kart (T16) |
|---|---|---|---|---|---|
| qwen25 | ✗ (8/12) | ✗ (15/16) | ✗ (padre inexistente) | 0/87 | 0/43 |
| ministral3 | ✗ (9/12) | **✓ 16/16 → biblioteca v1** | ✗ (11/16) | 0/87 | 0/43 |
| gemma12 | ✗ (T15: 3 cortadas; T16: 11/12) | ✗ (15/16) | ✗ (15/16) | 0/87 | 0/43 |

1. **La biblioteca funciona: no se pudo comprobar.** Nadie aprobó la rueda, así que no hubo reutilización. Lo que sí
   funcionó: el alerón de ministral3 se guardó con ficha, imagen y versión 1.
2. **Componentes:** ministral3 1 de 3; qwen25 y gemma12 0 de 3.
3. **Llega al montaje: no.** Nadie llegó a montar (ver fallo de diseño 5).
4. Respuestas cortadas: 4, todas de gemma12. Repeticiones idénticas tras el aviso: frecuentes en los tres.

**Por qué (leído en las respuestas):**
1. **Cilindro tumbado:** con «eje»: "x" las medidas son [ancho, diámetro, diámetro]; los tres escriben [d, d, ancho]
   (como si estuviera de pie). El aviso dice «mide … se pide …» pero no explica el orden.
2. **Caja total de la ficha:** declaran la caja de la pieza principal y olvidan lo que sobresale (placas: 1.66 en vez
   de 1.60). Es lo que más falla a gemma12 (las tres piezas del alerón bien, solo la ficha mal: 15/16 en 5 intentos).
   El aviso no dice qué piezas marcan cada extremo.
3. **Padre fuera del componente:** ponen como padre «Aleron_T» (el nombre de la instancia en el coche); el aviso no
   explica que dentro de un componente el padre es una de sus piezas.
4. **Pregunta confusa:** el mensaje del componente empieza por el enunciado entero del coche; gemma12 respondió con el
   montaje del F1 completo en vez de la rueda (de ahí sus 3 cortes a 800 tokens).
5. **Fallo de diseño (mío):** si falla un componente, el montaje no se intenta y el coche queda en 0; así no se mide
   si saben montar.
