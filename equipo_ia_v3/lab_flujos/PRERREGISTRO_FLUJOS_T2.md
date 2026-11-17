# Preregistro: banco de flujos grandes, tanda 2 (condición híbrida con troceado y puntos de guardado)

Escrito ANTES de preguntar a ningún cerebro. Fecha: 2026-11-15. Contextos y trozos congelados en `preparar`.

## Pregunta
¿Un flujo híbrido (buscar primero con Contexto Ligero y, si no basta, recorrer por trozos con puntos de guardado)
alcanza lo que la búsqueda sola no alcanza (contar en todo el proyecto, constantes de módulo) sin inventar datos y
sin dejar tareas a medias? ¿Cuánto cuesta en llamadas y tokens?

## Qué cambia respecto a la tanda 1
- Condiciones: `ligero` (igual que en la tanda 1) y **`hibrida`** (nueva). La `ingenua` no se repite: ya dio 0/24.
- Corregidos dos fallos del banco de la tanda 1: la pregunta E ya no dice «responde solo con su nombre» (chocaba
  con la línea «RESPUESTA:»), y la cobertura de E cuenta también la línea `import` que nombra la función.
- Mismo corpus (misma semilla, mismos bytes), mismas 22 tareas y 24 preguntas, mismos cerebros (qwen25 y ministral3),
  contexto 4096, `max_tokens` 400, temperatura 0.

## Cómo funciona `hibrida` (todo sin IA salvo las respuestas del cerebro)
1. **Enrutador:** las preguntas de contar en todo el proyecto («¿cuántas…?») van directas al troceado. El resto
   pregunta primero con Contexto Ligero; solo si el cerebro contesta «NO_ENCONTRADO» (o sin formato) pasa al troceado.
   Las de dos rondas (E) se quedan en Contexto Ligero.
2. **Filtro léxico:** de los archivos, se leen los que contienen el término más raro que la pregunta nombra
   literalmente (entre acentos graves o comillas), como haría un buscador de texto. Sin términos: todos.
3. **Troceado:** esos archivos se parten en trozos de ≤ 7.800 caracteres que nunca cortan una función a la mitad.
   Tope de 40 trozos por tarea; si no bastan, la tarea queda «incompleta», no se da por buena.
4. **Puntos de guardado:** cada trozo se guarda en `trozos.jsonl` al terminar. Si se para (temperatura, STOP), al
   reanudar no se repite ninguno, y la respuesta final solo se calcula cuando están TODOS hechos.
5. **Verificación y combinación:** en los recuentos, un nombre de función que diga el cerebro solo cuenta si ese trozo
   la define de verdad; el total es la unión sin duplicados. En las búsquedas gana el valor más votado entre trozos.

## Comprobado antes (sin cerebro real)
- Prueba con un cerebro falso que además inventa un nombre en cada trozo: parado a mitad y reanudado, 58 trozos
  únicos de 58 guardados (ninguno repetido), 24 tareas sin duplicar, el nombre inventado descartado siempre.
- Cobertura: `ligero` 14/22 tareas; el troceado de `hibrida` cubre C, D y R (incluidas R1–R2); los dos saltos (B)
  los cubre el primer paso de Contexto Ligero. Techo de `hibrida`: 24/24. Coste previsto del troceado: 1–10 trozos
  por tarea gracias al filtro (unos 37 trozos en total por cerebro si todo lo no encontrado pasa al troceado).

## Medidas
1. Aciertos por cerebro y condición, de 24.
2. Recuentos (C): número exacto, y funciones halladas frente a las reales (sobran, faltan, descartadas por la
   verificación).
3. Honestidad: respuestas con valor cuando el dato no estaba en lo que leyó.
4. Coste: llamadas al cerebro, tokens de prompt reales y segundos, por condición.
5. Tareas incompletas y, si hay paradas, trozos repetidos al reanudar (debe ser 0).

## Reglas de decisión (fijadas antes de ver resultados)
- **El híbrido aporta** si, en los DOS cerebros, `hibrida` acierta al menos 5 preguntas más que `ligero`
  (hay 8 que `ligero` no puede alcanzar). Con 2 o menos, **no aporta** para ese cerebro.
- **Recuentos fiables** si el número es exacto en al menos 2 de las 3 tareas C en cada cerebro.
- **Sigue siendo honesto** si inventa en el 20 % o menos de las preguntas sin el dato.
- **Sin trabajos a medias:** cualquier trozo repetido tras una reanudación, o una tarea cerrada con trozos sin
  hacer, se considera un fallo del mecanismo, aunque los aciertos sean altos.

## Resultado (2026-11-15, tras terminar; 9,5 minutos, sin paradas)

| | qwen25 ligero | qwen25 híbrida | ministral3 ligero | ministral3 híbrida |
|---|---|---|---|---|
| Aciertos (regla estricta) | 14/24 | **21/24** | 16/24 | **23/24** |
| Inventadas | 0 | 0 | 0 | 0 |
| Incompletas | 0 | 0 | 0 | 0 |
| Llamadas al cerebro | 24 | 54 | 24 | 54 |
| Tokens de prompt (total) | 26.175 | 103.301 | 26.252 | 106.809 |
| Segundos (total) | 44 | 166 | 75 | 248 |

Veredictos según las reglas fijadas:
- **El híbrido aporta** en los dos cerebros: +7 y +7 (umbral +5). Contar (C), constantes de módulo (D) y código real
  (R1–R2) pasan de 0 a acertarse.
- **Recuentos fiables**: exactos en 2 de 3 tareas C en cada cerebro (umbral 2 de 3).
- **Sigue siendo honesto**: 0 inventadas.
- **Sin trabajos a medias**: 66 trozos guardados, 0 repetidos, 0 tareas incompletas. No hubo paradas en esta tanda,
  así que la reanudación con cerebros reales no se puso a prueba aquí; sí con el cerebro falso (0 repetidos).
- **Coste**: el híbrido usa ~2,25 veces más llamadas, ~4 veces más tokens y ~3,5 veces más tiempo que solo
  Contexto Ligero, a cambio de +7 aciertos. Solo paga ese coste en las 8 preguntas que lo necesitan.

Anotaciones (no cambian los veredictos):
- **Los dos recuentos inexactos son sobreconteo**, no olvidos (0 faltan en las 6): qwen25 añadió en C2 cuatro
  funciones que no llaman a `registrar_auditoria`; ministral3 añadió en C1 una que la llama con otra categoría. La
  verificación solo comprobaba que la función EXISTE en el trozo, no que haga lo que se pregunta.
- **Cálculo posterior, NO prerregistrado**, sobre los mismos `trozos.jsonl`: si la verificación exige además que el
  cuerpo de la función contenga literalmente lo que nombra la pregunta (`registrar_auditoria` y la categoría entre
  comillas), los 6 recuentos salen exactos. Se prerregistrará como cambio de la tanda 3.
- **qwen25, «sin formato» en las segundas rondas de E**: contesta bien («…es `pagos_030`») pero sin la línea
  «RESPUESTA:». En la segunda ronda la instrucción de formato queda lejos (solo en el mensaje de sistema). Por
  contenido, qwen25 acierta 23/24 en `hibrida`. Propuesta para la tanda 3: repetir la instrucción de formato en
  cada turno.
