# Preregistro: banco de flujos grandes, tanda 3 (verificación estricta, formato por turno, trampas y parada real)

Escrito ANTES de preguntar a ningún cerebro. Fecha: 2026-11-15. Contextos y trozos congelados en `preparar`.

## Preguntas
1. ¿La verificación estricta deja exactos los recuentos con cerebros reales (en la tanda 2 se calculó después, sin
   prerregistro, sobre datos guardados)?
2. ¿Repetir la instrucción de formato en cada turno arregla las segundas rondas de qwen25?
3. ¿Los cerebros se inventan respuestas cuando tienen delante algo MUY parecido a lo que se pregunta?
4. ¿Con cerebros reales, una parada a mitad del troceado y su reanudación pierden o repiten trabajo?

## Qué cambia respecto a la tanda 2
- **Verificación estricta** en los recuentos: un nombre de función solo cuenta si el trozo la define Y su cuerpo
  contiene literalmente lo que nombra la pregunta (`registrar_auditoria` y la categoría entre comillas).
- **Formato en cada turno**: cada pregunta, también las de segunda ronda, recuerda terminar con «RESPUESTA: …».
- **3 preguntas trampa** (respuesta correcta: «no existe»), con su propio generador aleatorio; el corpus sigue siendo
  byte a byte el de las tandas 1 y 2 (comprobado con `diff`):
  - T1: una función que no existe en el proyecto.
  - T2: una constante que no existe, en un módulo que tiene otra casi igual (`LIMITE_LOTE_FRAGIL` frente a la pedida
    `LIMITE_LOTE_REFRIGERADO`).
  - T3: una variable `limite_diario` en una función real que no la tiene (sí tiene `factor = 465`).
- **Regla de ausencia (sin IA)** en `hibrida`: si la pregunta nombra entre acentos graves un identificador que no
  aparece en ningún archivo, la respuesta es «NO_ENCONTRADO» sin recorrer nada. Solo se aplica después de que el
  cerebro, con Contexto Ligero, no lo haya encontrado: si el cerebro inventa en ese primer paso, su invención queda.
- **Diagnóstico en las trampas**: el troceado se ejecuta igualmente y se registra qué habría contestado el cerebro
  leyendo los trozos con lo parecido delante. No decide la respuesta; mide la tentación de inventar.
- **Parada real**: durante el troceado del primer cerebro se creará el archivo STOP; después se borrará y se
  reanudará con `--reanudar`.
- Resto igual: mismos cerebros (qwen25, ministral3), condiciones `ligero` e `hibrida`, contexto 4096, `max_tokens`
  400, temperatura 0, 25 tareas y 27 preguntas.

## Comprobado antes (cerebro falso y tramposo, sin tarjeta)
Añadía en cada lista una función que existe pero no cumple, y se inventaba el número en T3: recuentos 3/3 exactos
(todas las intrusas descartadas), trampas 3/3 correctas, el invento de T3 registrado en el diagnóstico, y tras parar
y reanudar 102 trozos con 0 repetidos.

## Reglas de decisión (fijadas antes de ver resultados)
- **Verificación estricta confirmada** si los 3 recuentos (C) son exactos en los DOS cerebros.
- **Formato arreglado** si qwen25 acierta 4/4 en las preguntas E con la regla estricta, en las dos condiciones.
- **Resistencia a trampas**: por cerebro hay 5 lecturas con la trampa delante (las 3 respuestas del primer paso con
  Contexto Ligero, más los diagnósticos de T2 y T3; el de T1 se descarta si llega al tope de 40 trozos). El cerebro
  **resiste** si inventa en 1 o menos; **no es fiable con lo parecido** si inventa en 3 o más.
- **Reanudación real sin pérdidas**: 0 trozos repetidos, 0 tareas cerradas con trozos sin hacer y la tanda completa
  tras reanudar. Cualquier otra cosa es un fallo del mecanismo.
- **Resultado global esperado** en `hibrida`: al menos 25 de 27 por cerebro.

## Resultado (2026-11-15; con una parada real a mitad y su reanudación)

| | qwen25 ligero | qwen25 híbrida | ministral3 ligero | ministral3 híbrida |
|---|---|---|---|---|
| Aciertos | 18/27 | **26/27** | 19/27 | **27/27** |
| Inventadas | 1 (T1) | 1 (T1) | 0 | 0 |
| Recuentos C exactos | – | 3/3 | – | 3/3 |
| Llamadas / tokens de prompt | 27 / 31.116 | 57 / 108.459 | 27 / 31.550 | 57 / 112.369 |

Veredictos según las reglas fijadas:
- **Verificación estricta confirmada**: los 3 recuentos exactos en los dos cerebros (descartó 6 funciones que no
  cumplían en qwen25 y 1 en ministral3).
- **Formato arreglado**: qwen25 acierta 4/4 en E en las dos condiciones (en la tanda 2, 2/4).
- **Resistencia a trampas**: qwen25 inventa en 1 de 5 lecturas (resiste, en el límite); ministral3 en 0 de 4 (el
  diagnóstico de T1 llegó al tope de 40 trozos y se descarta, como estaba previsto).
- **Reanudación real sin pérdidas**: el STOP llegó con C2 en el trozo 5 de 7; C2 NO se cerró. Al reanudar se hicieron
  solo los que faltaban: 114 trozos, 0 repetidos, y los 15 guardados antes de la parada siguen idénticos.
- **Global**: 26/27 y 27/27 en `hibrida` (umbral 25).

El único invento, explicado: T1 pregunta por `ajustar_peso_express`, que no existe. Contexto Ligero trajo funciones
de nombre parecido, entre ellas `ajustar_peso_nocturno` (dos de tres palabras iguales, `factor = 7045`), y qwen25
contestó 7045. La regla de ausencia lo habría evitado, pero en esta tanda iba DESPUÉS del cerebro. Corrección para
la tanda 4: la regla va ANTES (si un identificador nombrado no existe en ningún archivo, no se pregunta al cerebro).
