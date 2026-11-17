# Evaluación V3.3.1 / V3.4 sin cambiar los oráculos

`python -B EJECUTAR_PRUEBAS.py` ejecuta pruebas, verifica integridad y compara
ambas versiones en cuatro conjuntos, con tres procesos nuevos por versión y
conjunto. `--solo-desarrollo` limita la ejecución a los dos conjuntos anteriores;
no consulta las tareas nuevas. El modo completo registra si había evaluaciones
previas de las tareas nuevas en esta carpeta.

Se conservan byte a byte `tasks.json` y `tasks_independientes.json`. Los archivos
`tasks_v34_reales.json` y `tasks_v34_flujos.json` se fijaron antes de observar
cualquier salida del buscador V3.4; sus hashes y los del corpus sintético se
registran en `CONGELACION_V34.json`. No se reescriben respuestas para mejorar una
cifra. Los resultados desfavorables y las corridas previas permanecen guardados.

## Techo matemático de la métrica anterior

Precision@5 conserva exactamente la definición histórica:

`P@5 = símbolos esperados presentes en las primeras cinco posiciones / 5`.

El máximo para una tarea con R respuestas esperadas distintas es
`min(R, 5) / 5`. En las doce tareas originales el promedio de esos máximos es
**0,40**. Por tanto, **55% no es alcanzable en esa misma métrica** sin cambiar el
denominador o los oráculos. Este límite se calcula y se prueba automáticamente;
no se oculta la métrica anterior ni se compara su40% con una precisión diferente.

## Métricas adicionales, idénticas antes y después

- Precisión de resultados devueltos: aciertos / todos los símbolos distintos
  devueltos por la consulta. Si no devuelve ninguno, precisión0. No se premia
  abstenerse con precisión perfecta.
- Recall@10: símbolos esperados presentes en las primeras diez posiciones /
  todos los símbolos esperados. La fórmula y el orden devuelto se conservan.
- Precisión del paquete: aciertos / todos los símbolos mostrados en el paquete,
  incluidas dependencias. No se quitan dependencias del denominador para mejorar
  la cifra. Recall del paquete usa el mismo oráculo completo.
- Recall de archivos: archivos esperados presentes entre los símbolos del
  paquete / archivos esperados. No demuestra que se haya entregado todo su código.
- Recall de dependencias etiquetadas: se calcula solo para conjuntos que declaran
  `dependency_relevant`; de lo contrario permanece null, no se inventa un oráculo.

Los resultados mínimos manuales de Equipo IA no etiquetan todos los posibles
resultados útiles. Una función no etiquetada no es necesariamente irrelevante;
las precisiones calculadas contra esos oráculos pueden infravalorar dependencias
pertinentes. Se guardan listas completas para revisión.

La intersección entre ranking y paquete se denomina `incluidos_en_ranking`.
El resto se denomina `añadidos_no_en_ranking`; esta clasificación reproducible
se aplica igual a ambas versiones y no afirma que los añadidos sean dependencias.
Las etiquetas directas/dependencias declaradas por V3.4 son diagnósticos adicionales,
no una forma exclusiva de calcular la comparación principal.

## Conjuntos y alcance

1. Doce tareas originales de Equipo IA, usadas durante el desarrollo previo.
2. Ocho tareas sintéticas anteriores, también conservadas sin cambios.
3. Doce tareas nuevas reales, escogidas por lectura de responsabilidades,
   docstrings y cuerpos AST de módulos de Equipo IA. Oráculos mínimos manuales.
4. Seis flujos sintéticos aislados: cada entrada llama cuatro funciones necesarias,
   hay tres funciones distractoras por módulo y un archivo que fallaría si se
   importara. Los cinco símbolos necesarios permiten un techo P@5 de100% sin
   cambiar las tareas históricas. Este conjunto tiene un oráculo exhaustivo para
   cada flujo declarado, no para aplicaciones reales ni dependencias dinámicas.

La nueva serie es independiente del ajuste inicial del motor. Si se cambia el
motor después de abrir sus resultados, las rondas posteriores deben describirse
como reevaluación de desarrollo; no como evaluación ciega. No constituye un corpus
externo de producción.

## Procedimiento común

La consulta, corpus, presupuesto de2000 tokens estimados, límite de12 candidatos,
oráculo, fórmulas y símbolo solicitado como evidencia son iguales para ambas
versiones. Se compara `search` de V3.3.1 con `retrieve` de V3.4, su buscador nuevo;
`search` de V3.4 queda como compatibilidad histórica y no se usa para atribuir
mejoras a la arquitectura nueva.

El presupuesto sigue siendo estimado para seleccionar en igualdad de condiciones.
El valor numérico del límite es el mismo, pero la API anterior cuenta archivos y
la nueva cuenta símbolos: la anterior puede devolver más de 12 símbolos en esos
archivos. Se conserva esa salida completa al medir precisión devuelta; no se
recorta retrospectivamente para alterar el resultado. Esta métrica compara el
producto entregado por cada buscador, no rankings de longitud idéntica. P@5 y
recall@10 sí conservan exactamente sus posiciones y denominadores originales.

Opcionalmente `--tokenizer-json tokenizadores/gpt2/tokenizer.json` mide después el
texto exacto de ambas versiones con la misma biblioteca local. No se descarga ni
instala nada. Es medición real para ese vocabulario; no consumo exacto de Claude,
Codex ni una plantilla de chat no incluida.

Cada proceso crea una base nueva y luego hace un scan sin cambios. El orden de las
versiones alterna. Se miden tres consultas/paquetes por tarea y se agregan medianas
por proceso. No se vacía la caché del SO ni se demuestra significancia estadística.
RSS incluye el proceso entero, tokenizador e importaciones.

Los hashes de originales, V3.3.1, corpus, tareas congeladas y fuentes activas se
comprueban antes/después. El código indexado nunca se importa ni ejecuta. El
runner conserva comandos, logs, bases, mapas, fragmentos y JSON crudo.

## Estado técnico y objetivos de calidad

`status=PASS` indica regresiones, integridad, presupuestos y ejecución técnica
correctos. `quality_status` y `quality_targets` indican por separado si se cumplen
55% de precisión devuelta,100% de recall@10 y cobertura del paquete, y si hay
regresiones tarea a tarea. Un PASS técnico no oculta un objetivo incumplido.

No se mide corrección de respuestas LLM ni ahorro neto al terminar una modificación.
La clausura estática no acredita dependencias dinámicas exhaustivas. Termux físico
y modelos reales siguen pendientes de validación independiente.

## Comparación suplementaria de código

`bundle_worker.py` compara los seis flujos ya congelados, sin cambiar sus respuestas
esperadas. Ambas versiones reciben la misma consulta, símbolo obligatorio, 4.000
tokens estimados, límite 12, profundidad 1, máximo de 32 evidencias y sin pruebas
auxiliares. Cada tarea tiene tres muestras en un proceso por versión. Guarda el
texto exacto, precisión/recall de los símbolos entregados, tiempo y pico RSS.

Este suplemento se añadió después de la primera evaluación nueva y se identifica
como tal; no es un nuevo conjunto ciego. Un error cuenta como cobertura cero, con
tokens ausentes: no se atribuye ahorro a una salida fallida. Los cinco símbolos
de cada flujo permiten comparar evidencia funcional completa dentro de ese
escenario. No acredita comprensión LLM, configuraciones dinámicas ni corrección
de una modificación real. No sustituye las métricas principales de mapas.
