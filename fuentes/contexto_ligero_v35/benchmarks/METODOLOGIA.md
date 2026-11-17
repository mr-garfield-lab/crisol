# Metodologia de comparacion

`python EJECUTAR_PRUEBAS.py` reproduce regresiones, integracion simulada y la
comparacion. No necesita red, modelos ni dependencias adicionales. Usa procesos
nuevos y bases nuevas por version/repeticion; conserva todos los resultados en
directorios independientes. Cambiar `--repeticiones 3` solo cambia el muestreo.

Las doce tareas en `tasks.json` se fijaron antes de consultar el ranking V3.3,
por lectura manual de funciones de Equipo IA. Su SHA256 declarado inicialmente:
`2adc09e32ebd957a49faea7ce215b32873184971f14c8da404d5d1947c22fe72`.
El runner vuelve a registrar el hash para detectar alteraciones. El corpus y los
oraculos se incluyen en el ZIP; cada simbolo esperado se valida contra el AST.
No se debe adaptar el ranking a estas respuestas: al cambiar el ranking conviene
añadir una evaluacion externa con tareas nuevas, sin sustituir esta serie.

Para las versiones comparadas se usa la misma consulta, limite de doce archivos candidatos y
presupuesto de 2000 tokens **estimados**, calculados como ceil(caracteres/3).
El ranking de simbolos se aplana en orden de archivo y orden de simbolo retornado.
Precision@5 divide por cinco incluso si se recuperan menos de cinco simbolos.
Recall@10 cuenta los simbolos esperados presentes en las primeras diez posiciones.
MRR usa el inverso de la posicion del primer acierto, o cero si no hay aciertos.
Las medias entre tareas son macro: cada tarea pesa lo mismo.

Los oraculos enumeran el minimo relevante, no todos los simbolos que podrian
ayudar. Por tanto Precision@5 es una medida estricta frente a ese oraculo y
puede infravalorar dependencias pertinentes. Se guardan listas exactas de
resultados y fragmentos para inspeccion manual. La cobertura del paquete V3.3
usa su seleccion estructurada; V3.2 se reconoce por sus cabeceras de archivo.

El escenario de auditoria añade exactamente el mismo simbolo solicitado en
ambas versiones (`evidence`), con max_lines=200. Es un escenario de recuperacion
de evidencia, no una tarea completada por un modelo. No mide exactitud de
respuestas LLM, modificaciones correctas, coste de inferencia ni ahorro neto de
tokens de una conversacion. La fuente completa del mismo archivo se mide como
referencia de tamaño, pero no se equipara a un contexto semanticamente completo.

El scan inicial usa base nueva; el segundo scan no cambia archivos. Ambos hashean
contenido; solo los archivos cambiados necesitan parseo. No se vacia la cache del
SO y se alterna el orden V3.2/V3.3 por repeticion. Query y packet tienen tres
muestras de tiempo por tarea; la agregacion informa medianas. El pico RSS se
obtiene por proceso con resource.getrusage: es memoria residente maxima total,
no memoria exclusiva de una operacion. Se normaliza KiB a bytes en Linux/Termux
y se conservan bytes en macOS. Donde resource no existe se informa null.

Los tokens reales quedan en null cuando falta un tokenizador local. Opcionalmente:

```sh
python EJECUTAR_PRUEBAS.py --tokenizer-json /ruta/local/tokenizer.json
```

Requiere que `tokenizers` y un vocabulario compatible ya esten instalados por el
usuario. El runner no instala ni descarga nada. Se registra el hash del JSON.
El recuento es exacto para ese vocabulario y ese texto, sin plantilla de chat ni
tokens especiales; no acredita que ese vocabulario corresponda a Claude o Codex.
No se cambia el presupuesto de caracteres, para mantener el mismo criterio en
todas las versiones. En esta edición se ejecutó la vía opcional con tokenizers0.22.2 y el vocabulario GPT-2 incluido: los resultados reales están en la corrida vigente. Su equivalencia con Claude/Codex no está validada.

Los originales se verifican antes y despues mediante SHA256. Los tests originales
se ejecutan tanto contra V3.2 como contra V3.3; los originales no se reescriben ni
se generan pyc en ellos. Solo los fixtures temporales propios son limpiados por
unittest. Cambios de bytes, archivos faltantes o extras en la referencia hacen
fallar el runner. Tambien fallan regresiones, workers incompletos, desbordes del
presupuesto V3.3 o snippets esperados no disponibles. Las diferencias de velocidad
y precision se muestran sin convertirlas en umbrales arbitrarios de exito.

En la edición validada, un agregado de tokens medidos requiere todas sus muestras. El tokenizador opcional desactiva truncamiento y padding. La edición3.3.1 añade cuatro pruebas con biblioteca y vocabulario reales, además del doble local previo; no acredita consumo de Claude/Codex.

## Edición 3.3.1 y comparación contra la entrega anterior

El comando integral compara ahora tres implementaciones: `V3.2` original,
`V3.3-validada` (copia exacta de la entrega anterior bajo
`comparacion/v33_validado`) y `V3.3` (etiqueta compatible del JSON para la nueva
edición 3.3.1). Las tres reciben las mismas consultas, un límite de doce archivos
candidatos y presupuesto de 2000 estimados. La tabla adicional compara directamente
la entrega validada y la nueva. Los presupuestos ampliados y los paquetes de código
son funcionalidades adicionales; no se mezclan con este benchmark de mapas.

El orden de las tres versiones rota por repetición. Cada proceso y base son nuevos;
se comparan medianas de tres procesos por defecto. Para query/packet se añade la
media de las medianas por tarea: cada tarea pesa igual. Una reducción relativa de
esa media no equivale a reducción del tiempo total de una tarea real.

También se ejecuta un conjunto **sintético complementario** de ocho tareas sobre
doce archivos propios. El corpus y los oráculos están declarados en
`tasks_independientes.json` y sus hashes en `CONGELACION_INDEPENDIENTE.json`,
creados antes de consultar los rankings de esa serie. Incluye alias importados,
CamelCase, Unicode, contratos, selección de pruebas, consultas multimódulo y un
módulo que fallaría si se importase. Esto verifica recuperación/lectura, no que el
código de ejemplo sea una aplicación real. No se utiliza como señal para ajustar
el motor y no constituye validación externa sobre proyectos desconocidos.

Los resultados de esta serie se guardan en `independent_comparison`, separados de
los doce casos de Equipo IA. Puede haber coberturas inferiores al 100%; se informan
sin ocultarlas ni convertir arbitrariamente el oráculo parcial en una prueba de
éxito/fallo del motor. Los tests de regresión sí exigen sus invariantes concretos.

La referencia, la baseline validada y el conjunto sintético se verifican antes y
después. Además cada worker calcula hashes del corpus, sin ejecutar sus módulos,
y rechaza modificaciones. El runner verifica que sus fuentes Python no hayan
cambiado durante la corrida: no acepta una comparación mientras se editaba el motor.
Los resultados anteriores se conservan en directorios independientes.

Un tokenizer JSON local puede contar los textos de todas las versiones sin cambiar
el presupuesto estimado usado para seleccionar. `PYTHONPATH` conserva un directorio
de dependencias que el usuario haya autorizado previamente. El runner no instala
ni descarga paquetes ni vocabularios. Se desactivan truncamiento y relleno del
JSON para no subestimar ni inflar el conteo; la identidad/hash del vocabulario
permanece registrada. Su equivalencia con Claude/Codex debe verificarse por separado.
