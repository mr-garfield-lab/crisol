# Preregistro: banco de revisión de código, tanda 1 (Python y Java, sin código malicioso)

Escrito ANTES de preguntar a ningún cerebro. Fecha: 2026-11-15.

## Pregunta
¿Un cerebro local encuentra los errores que impiden compilar, señala la línea correcta y los arregla sin tocar lo que
estaba bien? ¿Mejora si primero una herramienta sin IA (compilador / analizador) le dice dónde está el error y se le
devuelve lo que siga fallando, hasta 3 intentos?

## Montaje
- **32 casos** (`lab_revision/corpus.py`, código original, determinista): dos programas por lenguaje (inventario y
  rutas de reparto), cada uno con 5 versiones de un error (sintaxis, nombre inexistente, import que falta, tipos
  incompatibles en Java o argumentos que no encajan), 2 versiones correctas (una con algo que PARECE un error y no lo
  es: constante definida más abajo, `nonlocal`, varargs, `var` con ternario) y 1 con dos errores de fases distintas
  (la sintaxis tapa un error de nombres). En total: 24 casos con error (29 líneas de error) y 8 correctos.
- **Herramientas sin IA** (`lab_revision/herramientas.py`): Python con `ast.parse` y un analizador propio de nombres y
  argumentos; Java con `javac` 21.0.13 (JDK portátil, `lab_flujos/JDK_EXTERNO.md`). **Validado antes**: encuentran
  exactamente los 32 oráculos (las dos fases en orden) y ninguna falsa alarma en los 8 correctos.
- **Condiciones**: `solo` (el cerebro revisa, un intento) y `herramienta` (errores del compilador → el cerebro explica
  y arregla → se recompila → si falla, los errores nuevos vuelven al cerebro; hasta 3 intentos; si la herramienta no
  ve errores, no se pregunta al cerebro).
- **Formato** de respuesta: `ERROR: línea N | tipo | explicación`, `SIN_ERRORES`, `ARREGLO N: <línea>`,
  `INSERTAR N: <línea>`, `ELIMINAR N`. Los arreglos se aplican sobre la numeración dada.
- **Nunca se ejecuta el código del cerebro**: solo se compila / analiza.
- Cerebros qwen25 y ministral3; contexto 4096; `max_tokens` 500; temperatura 0. Mismo armazón de seguridad que los
  otros bancos.

## Puntuación (sin IA)
- Caso con error: `arreglado` (compila y solo se tocaron las líneas del error ±1 o se añadió un import),
  `arreglado_tocando_mas` (compila pero cambió otras líneas), `no_compila`, `sin_cambios`.
- Caso correcto: `correcto` (nada que decir), `falsa_alarma` (dijo que había error o cambió algo y sigue compilando),
  `rompio` (lo dejó sin compilar).
- En `solo`: líneas de error bien señaladas (de 29) y falsas alarmas (líneas señaladas que no son error).

## Comprobado antes (cerebros falsos, sin tarjeta; `lab_revision/comprobar_sin_gpu.py`, 10/10)
Perfecto → 24 arreglados y 8 correctos en las dos condiciones, 29/29 líneas. Chapucero → 24 «tocando de más».
Alarmista → 8 falsas alarmas en `solo`, 0 en `herramienta`. Por fases → las dos fases arregladas en 2 llamadas.

## Reglas de decisión (fijadas antes de ver resultados)
1. **La herramienta aporta** si, en los DOS cerebros, `herramienta` arregla al menos 4 casos más (de 24) que `solo`.
2. **Revisión sin herramienta**: señalar bien el 70 % o más de las 29 líneas es «útil sola»; menos del 40 % es «no
   fiable sin herramienta».
3. **Falsas alarmas sin herramienta**: 2 o menos de 8 archivos correctos por cerebro es aceptable.
4. **No romper con herramienta**: 0 `rompio` y como mucho 3 `arreglado_tocando_mas` por cerebro.
5. **Dos fases con herramienta**: al menos 3 de los 4 arreglados por cerebro.

## Corrección del lector durante la tanda (2026-11-15, antes de ver resultados agregados)
Tras las primeras filas se vio que qwen25 escribe las órdenes como lista («- ERROR: línea 20 …») y el lector solo
aceptaba la orden al principio de la línea: 14 líneas de 17 respuestas se ignoraban. Se paró la tanda con STOP (17
casos de `solo` hechos), se corrigió el lector (acepta viñetas, números y negrita delante de la orden) y esas 17
filas se volvieron a puntuar desde el TEXTO guardado del cerebro (`recalificar`: un intento, recálculo exacto; copia
de las filas originales en `peticiones_antes_de_recalificar_*.jsonl`). La condición `herramienta` aún no había
empezado: se ejecuta entera con el lector corregido. Las reglas de decisión no cambian.

## Resultado (2026-11-15; 12 minutos tras la reanudación, sin paradas)

| | qwen25 solo | qwen25 herramienta | ministral3 solo | ministral3 herramienta |
|---|---|---|---|---|
| **Arreglados** (de 24 con error) | 10 | **19** | 10 | **21** |
| Python / Java | 4 · 6 | 10 · 9 | 8 · 2 | 12 · 9 |
| Líneas de error bien señaladas (de 29) | 21 (72 %) | – | 28 (97 %) | – |
| Líneas señaladas que NO eran error | 13 | – | 45 | – |
| Correctos sin falsa alarma (de 8) | 7 | 8 | 1 | 8 |
| Rompió un archivo correcto | 0 | 0 | 2 | 0 |
| Arreglos que tocan de más | 0 | 0 | 3 | 0 |
| Dos fases arregladas (de 4) | 1 | 3 | 1 | 3 |

Veredictos según las reglas fijadas:
1. **La herramienta aporta: SÍ** (+9 y +11 casos arreglados; umbral +4).
2. **Revisión sin herramienta**: qwen25 72 % y ministral3 97 % de líneas bien señaladas, los dos «útiles solos» por la
   regla. Pero ministral3 señala 45 líneas que no son error (dispara a todo) y qwen25 13.
3. **Falsas alarmas sin herramienta**: qwen25 aceptable (1 de 8); **ministral3 no** (6 de 8 mal, 2 de ellos rotos).
4. **No romper con herramienta: SÍ** en los dos (0 roto, 0 tocando de más).
5. **Dos fases con herramienta: SÍ** (3 de 4 en los dos).

Lectura: con la herramienta delante, los dos cerebros arreglan 19–21 de 24 sin estropear nada y sin una sola falsa
alarma (si el compilador no ve errores, no se pregunta). Solos, aciertan menos de la mitad y ministral3 «ve» errores
donde no los hay. La regla «la herramienta comprueba, el cerebro explica» queda confirmada.

## Fallos con herramienta, y su causa (para la tanda 2)
- **Import que falta en Java** (4 de los 6 fallos de Java): los dos cerebros insertan el `import` DENTRO de la clase
  en vez de al principio del archivo; `javac` solo dice «cannot find symbol». Propuesta sin IA: colocar
  automáticamente arriba (con los demás import) cualquier `import` que proponga el cerebro.
- **Arreglo repetido**: qwen25 propuso tres veces `total = totl` para `return totl`. El bucle no le dice que el
  arreglo anterior no funcionó. Propuesta: si el mismo error sigue en la misma línea, avisarlo y mostrarle cómo quedó.
- ministral3 / JV_INV_F2: al arreglar la sintaxis tocó la llave del `main` y dejó otro error de sintaxis.
