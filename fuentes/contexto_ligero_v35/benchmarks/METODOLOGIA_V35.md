# Metodología de evaluación V3.5

`python -B EJECUTAR_PRUEBAS.py` compara V3.4 y V3.5 sin servicios externos.
Las fuentes V3.4 copiadas en `comparacion/v34` se fijaron mediante SHA256 antes de
los cambios. La integridad de los originales, las fuentes activas, las versiones
anteriores, los manifiestos y los corpus se comprueba antes y después. Los
resultados anteriores, también los desfavorables, permanecen bajo `resultados/`.

## Conjuntos congelados

- 12 tareas originales reales de Equipo IA y 8 sintéticas anteriores.
- 12 tareas reales y 6 flujos sintéticos creados en la evaluación V3.4.
- 8 tareas reales adicionales y 8 sintéticas V3.5, congeladas mediante
  `CONGELACION_V35.json` antes de consultar los resultados de V3.5 sobre ellas.
  Las reales se eligieron por lectura de fuentes y AST; sus juicios son mínimos,
  no exhaustivos. Las sintéticas incluyen módulos homónimos, múltiples pasos,
  distractores, métodos, imports y constantes. Son artificiales; no representan
  un corpus externo de producción ni evalúan una respuesta de un modelo.

Los oráculos anteriores no se modifican. Si después de ver las tareas nuevas se
ajusta el motor, la primera ejecución queda guardada y las posteriores se declaran
reevaluación de desarrollo. `first_new_tasks_evaluation` registra esta distinción.
La congelación verifica tanto los hashes de las tareas/corpus como el hash del
propio manifiesto. Los buscadores y benchmarks de recuperación no importan ni
ejecutan el proyecto indexado. La suite de integración sí importa componentes de
la copia de Equipo IA y ejecuta un backend simulado, sin llamadas a modelos.

## Métricas idénticas

- **Precisión de resultados devueltos**: símbolos etiquetados acertados / todos
  los símbolos distintos devueltos por `retrieve`. Se calcula por tarea y se
  promedia. Las dependencias y símbolos adicionales permanecen en el denominador.
- **P@5**: aciertos entre las primeras cinco posiciones / 5. En las 12 tareas
  históricas el techo es 40%; no confundirla con el objetivo aproximado del 50%
  para la precisión devuelta, que es otra métrica.
- **Recall@10**: símbolos esperados entre las primeras 10 posiciones / todos los
  símbolos esperados. Recall del mapa, recall de archivos y de dependencias
  etiquetadas se miden con los mismos denominadores de V3.4.
- **Precisión del mapa**: aciertos / todos los símbolos mostrados, incluidas
  dependencias. Se muestran métricas agregadas y por tarea para ambas versiones.

Un oráculo mínimo no marca todas las dependencias posiblemente útiles; un símbolo
no etiquetado no es necesariamente irrelevante. Por tanto la precisión contra esos
oráculos tiene esa limitación. No se cambian respuestas ni se descartan dependencias
para aumentar un porcentaje. Se observan todas las tareas, incluidas regresiones.

## Mapas, snippets y ejecución

Para cada tarea se usan exactamente la misma consulta, límite de 12 símbolos,
presupuesto de 2.000 tokens estimados, corpus, oráculo y símbolo de snippet. Cada
versión crea una base nueva y escanea el mismo corpus; el orden se alterna. Se
miden tres muestras por tarea/proceso y, por defecto, tres procesos por versión y
conjunto. Los agregados usan medianas entre procesos y macro-promedios por tarea.
Se conservan rankings, mapas, snippets, tiempos y JSON por cada ejecución.

El presupuesto sigue siendo estimado para seleccionar igual en ambas versiones.
Con `--tokenizer-json` y la biblioteca ya instalada se cuenta después cada texto
exacto con el vocabulario local. GPT-2 es una medida real de ese tokenizador; no
incluye plantilla de chat ni equivale necesariamente a Claude/Codex. Sin esa
biblioteca los tokens medidos son `null` y se reporta la estimación, no una medida.

Se informa indexación fría y sin cambios, tiempo de consulta/paquete, tamaño de
SQLite y pico RSS del proceso entero. La caché del sistema operativo no se vacía;
no se afirma significancia estadística ni RAM atribuible a una sola función.

## Código completo: bundle

Ambas versiones reciben la misma consulta, `--require`, límite 12, presupuesto,
profundidad, límite de evidencias y `include_tests=False`. En los seis flujos
V3.4 se mantienen los parámetros históricos: 4.000 tokens estimados, profundidad
1 y máximo 32 evidencias. En los demás conjuntos: 16.000, profundidad 8 y máximo
100 evidencias. Se miden tres muestras por tarea en un proceso por versión.

El validador independiente reconstruye los rangos numerados o compactos y compara
cada línea de los símbolos, imports y datos de soporte con la fuente indexada,
verificada y redactada. Los errores, omisiones, faltas de oráculo y líneas se
registran por tarea. Un fallo cuenta como recall cero, no como ahorro de tokens.
Para comparar tokens se usa solo el mismo subconjunto de tareas donde ambas
versiones devuelven todas las respuestas etiquetadas y pasan la verificación de
líneas; el informe enumera el total, el subconjunto, los fallos y los símbolos.
El cálculo no acredita que las funciones no etiquetadas sean innecesarias, ni que
se hayan resuelto dependencias dinámicas o ejecutado una tarea real con un modelo.

La demostración adicional de símbolo largo activa explícitamente el límite de
1.000 líneas y un presupuesto estimado de 64.000; verifica sus rangos y su fuente.
Es un ejemplo optativo, no una comparación directa ni una promesa de ventana del
modelo. El límite normal continúa siendo de 200 líneas por símbolo.

Las regresiones de recall y de archivos en los conjuntos antiguos se muestran y
hacen fallar la validación técnica. Los objetivos de calidad se reportan por
separado; un PASS técnico no equivale a alcanzar una precisión determinada.
