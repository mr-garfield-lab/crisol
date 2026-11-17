# Estado de entrega — Contexto Ligero V3.5

**La precisión se acerca al 50% y el recall@10 de los conjuntos anteriores se conserva.** La evaluación inicial completa usa tres procesos por versión y conjunto; se mantiene el informe de cada tarea, sin modificar respuestas esperadas.

[Informe completo de tres repeticiones](resultados/20261029T221939_c9aac45b/report_v35.md) · [Datos crudos](resultados/20261029T221939_c9aac45b/report_v35.json) · [Guía V3.5](GUIA_V35.md) · [Metodología](benchmarks/METODOLOGIA_V35.md)

## Mejoras implementadas

- La recuperación distingue términos de módulo y clase de operaciones concretas. Los nombres compuestos no añaden por defecto módulos homónimos sin operación independiente. Los resultados alternativos y módulos descartados se pueden inspeccionar con `query --explain`.
- Se mantiene el límite de resultados y la ampliación de llamadas estáticas de los objetivos seleccionados. No se eliminan dependencias de esos objetivos para mejorar la cifra; si se selecciona otro objetivo, su clausura cambia y debe revisarse. Las alternativas y dudas dinámicas permanecen visibles.
- `bundle` agrupa rangos de código usando cercas adaptativas cuando reduce el presupuesto, conservando el orden y número de cada línea y los huecos. `--line-style numbered` conserva el formato anterior.
- Se permite, solo con `--max-symbol-lines`, incluir símbolos de hasta 1.000 líneas mediante lecturas verificadas por tramos de máximo 200. El límite por defecto permanece en 200; si código o soporte no caben, se rechaza el requisito.
- Se conservan controles de rutas, hashes, límites, redacción, clausura de llamadas, soporte de datos importados, integración optativa, snapshots y deltas. El código indexado no se ejecuta para recuperarlo.

## Recuperación y mapas

La precisión es aciertos / todos los símbolos devueltos, incluidas dependencias; la fórmula y consultas son las mismas para ambas versiones. El recall@10 usa todas las respuestas esperadas originales. Los oráculos reales son mínimos y pueden no etiquetar dependencias útiles.

| Conjunto | Precisión devuelta V3.4 → V3.5 | Recall@10 antes → después | Tokens GPT-2 de mapas antes → después |
|---|---:|---:|---:|
| Equipo IA: 12 originales | 39.78% → 47.72% | 100.00% → 100.00% | 4136 → 3618 |
| 8 sintéticas anteriores | 84.38% → 90.62% | 100.00% → 100.00% | 1962 → 1952 |
| 12 reales V3.4 | 37.36% → 37.36% | 100.00% → 100.00% | 5403 → 5403 |
| 6 flujos V3.4 | 90.28% → 100.00% | 100.00% → 100.00% | 1617 → 1554 |
| 8 reales nuevas V3.5 | 52.92% → 52.92% | 100.00% → 100.00% | 3558 → 3543 |
| 8 sintéticas nuevas V3.5 | 85.62% → 96.88% | 100.00% → 100.00% | 1986 → 1937 |

En las 12 tareas originales la precisión devuelta sube **39,78% → 47,72%**, mientras recall@10 permanece en **100%**. Se acerca al 50% sin alcanzar exactamente esa cifra; el usuario no exigió alcanzarla. La P@5 histórica permanece en 40%, su techo para esos oráculos, y no debe confundirse con la precisión devuelta.

El recall@10 y la cobertura de los mapas son 100% en las 54 tareas de estos seis conjuntos. Es cobertura de símbolos etiquetados, no una garantía de todas las dependencias de Python o de cualquier proyecto.

## Código completo y consumo

Para cada `bundle` se verifican, tras la redacción heurística, las líneas de los símbolos seleccionados y de sus soportes frente a las fuentes por hash. El siguiente cálculo incluye solo tareas emparejadas donde las dos versiones entregan todas las respuestas etiquetadas y pasan la comprobación de líneas. Los fallos, exclusiones y listas de símbolos permanecen en el informe.

| Conjunto | Tareas completas en ambas | Fallos V3.4 → V3.5 | Precisión de símbolos V3.4 → V3.5 | Tokens GPT-2 de bundles completos V3.4 → V3.5 |
|---|---:|---:|---:|---:|
| Equipo IA: 12 originales | 10/12 | 2 → 1 | 36.60% → 46.33% | 35342 → 26657 |
| 8 sintéticas anteriores | 8/8 | 0 → 0 | 87.50% → 93.75% | 2828 → 2784 |
| 12 reales V3.4 | 11/12 | 1 → 1 | 35.17% → 35.17% | 62043 → 55794 |
| 6 flujos V3.4 | 6/6 | 0 → 0 | 95.24% → 100.00% | 3289 → 3174 |
| 8 reales nuevas V3.5 | 6/8 | 2 → 2 | 41.65% → 41.65% | 16955 → 15657 |
| 8 sintéticas nuevas V3.5 | 8/8 | 0 → 0 | 85.62% → 96.88% | 3370 → 3198 |

En los 10 casos originales comparables, la evidencia pasa de **35.342 a 26.657 tokens GPT-2**, una reducción del **24,57%**. No se suman las dos tareas restantes para aparentar ahorro: V3.4 falla en dos y V3.5 en una con los límites normales.

En los seis flujos V3.4, la precisión del bundle recupera **95,24% → 100%**, el recall se mantiene en 100% y los tokens medidos pasan de **3.289 a 3.174**. En las ocho tareas reales nuevas, ambas versiones rechazan dos bundles por un símbolo de 440 líneas: no se afirma cobertura completa para ellos.

La demostración [de símbolo largo](resultados/20261029T221939_c9aac45b/demo_simbolo_largo/metrics.json) requiere explícitamente `--max-symbol-lines 1000` y presupuesto estimado 64.000. Recupera una clase de 440 líneas y verifica 1.143 líneas de evidencia; el resultado completo contiene 22.666 tokens estimados y 31.718 medidos con GPT-2. No implica que quepa en el modelo utilizado.

Los tokens medidos son del vocabulario GPT-2 local incluido y no incluyen plantilla de chat ni respuestas. No representan el consumo exacto de Claude, GPT o Codex. En ejecución básica el contador es una estimación, etiquetada como tal.

## Pruebas y rendimiento

Pasan **207 pruebas** con la biblioteca de tokenización ya disponible y las 18 regresiones originales sobre V3.4 y V3.5. Los cuatro conjuntos anteriores mantienen el recall por tarea, incluida la cobertura del paquete. En los 16 casos nuevos tampoco se observó una regresión de recall frente a V3.4.

| Equipo IA original | V3.4 | V3.5 |
|---|---:|---:|
| Consulta, media de medianas (ms) | 115.99 | 109.89 |
| Mapa, media de medianas (ms) | 118.73 | 112.25 |
| Indexación inicial, mediana (s) | 1.26 | 1.18 |
| Indexación sin cambios, mediana (s) | 0.07 | 0.07 |
| Pico RSS del proceso, mediana (MiB) | 63.34 | 63.38 |

Las mediciones son locales, incluyen el proceso y tokenizador completos y no vacían la caché del sistema operativo. No se demuestra significancia estadística ni se atribuye toda la RAM al motor.

Las 16 tareas V3.5 se congelaron antes de la primera evaluación. Esta primera corrida completa conserva el campo `first_new_tasks_evaluation=true`. Tras la corrida solo se corrigió una frase del generador del informe: las consultas no ejecutan el corpus, pero la prueba de integración sí importa componentes de Equipo IA con backend simulado. Se guardó el informe anterior y el código original del generador; no cambiaron buscador, selección, métricas, dependencias ni oráculos. La repetición posterior se identifica como tal.

La [repetición con el código final](resultados/20261029T222443_3d568c48/report_v35.md) terminó con PASS técnico. Su precisión, recall, precisión de mapa y tokens medidos son idénticos a los de la primera corrida en los seis conjuntos. Se emplea la corrida de tres procesos para la tabla de tiempos y RAM; la repetición final usó un proceso por versión y conjunto.

## Validación, integración y pendientes

```sh
python -B EJECUTAR_PRUEBAS.py
```

El comando básico es local y no instala nada. El ZIP contiene fuentes, baseline V3.4, pruebas, corpus, guías, informes y textos; omite bases SQLite de resultados regenerables para facilitar la descarga. Se descomprimió un ZIP candidato y se ejecutaron la suite y el comando integral sin la biblioteca opcional: 207 pruebas, cuatro omitidas por faltar el tokenizador. La [ejecución desde la copia extraída](resultados/verificacion_zip_v35/20261029T222604_e75f6291/report_v35.md) pasó en modo de desarrollo con una repetición. Esto verifica la portabilidad local, no sustituye una prueba física en Termux.

Los originales, el baseline V3.4 y los oráculos conservaron sus hashes. No se instalaron nuevas dependencias ni se usaron APIs o servicios de pago. La integración local con Equipo IA utiliza backend simulado; el puente opcional de metadatos y las instrucciones para Claude están en [GUIA_V35.md](GUIA_V35.md).

Queda pendiente validar en Termux físico y en conversaciones reales con Claude u otro modelo. El análisis estático no puede asegurar dependencias dinámicas, mutaciones ni el estado de ejecución. Revise las alternativas de `query --explain`, los avisos de `bundle --json` y la redacción de secretos antes de compartir el contexto.
