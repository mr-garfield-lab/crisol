> **Guía histórica V3.4. Para el motor actual consulte [GUIA_V35.md](GUIA_V35.md).**

# Contexto Ligero V3.4: uso e integración

Esta guía corresponde al motor V3.4. Las guías V3.3.1 conservadas describen la
entrega anterior; para selección, dependencias y evidencia prevalece esta guía.
Los resultados concretos, incluidos los objetivos incumplidos, están en
[ESTADO_ENTREGA.md](ESTADO_ENTREGA.md) y en el informe enlazado allí.

## Preparar y validar

Descomprima el ZIP en una carpeta nueva. El motor básico requiere Python 3.10 o
posterior, SQLite y un entorno POSIX; funciona sin paquetes externos, red ni APIs.
Ejecute desde la carpeta que contiene `contexto_v3.py`:

```sh
python -B EJECUTAR_PRUEBAS.py
```

Este único comando ejecuta regresiones, controles de integridad y comparación
V3.3.1/V3.4 sobre cuatro conjuntos: 12 tareas originales de Equipo IA, 8 sintéticas
anteriores, 12 tareas reales nuevas y 6 flujos sintéticos nuevos. Por defecto hace
tres procesos de medición por versión y conjunto. Guarda informes, textos,
comandos y datos crudos en una carpeta nueva de `resultados/`.

Un código de salida cero y `status=PASS` acreditan la ejecución técnica.
`quality_status` y `quality_targets` indican por separado si se cumplen los
objetivos de precisión y cobertura. Lea ambos: PASS no significa que todos los
objetivos de calidad estén alcanzados. `--solo-desarrollo` usa únicamente los dos
conjuntos antiguos; no sustituye la validación completa.

Para Termux, use una carpeta privada, por ejemplo bajo `$HOME`, y el mismo comando
con Python ya disponible. No se instala nada automáticamente. Las pruebas en el
entorno Linux de entrega no acreditan pruebas físicas en Android: quedan por
comprobar allí Python/SQLite, permisos y enlaces simbólicos, tiempos, RAM y cierre
normal del proceso. Las bases incluidas en los resultados son evidencia ligada a
las rutas originales; cree un índice nuevo en el dispositivo.

## Crear un índice y encontrar código

Estos ejemplos leen la referencia incluida sin modificar sus archivos:

```sh
python -B contexto_v3.py --db indice_v34_nuevo.sqlite3 scan referencia_original/equipo_ia_referencia
python -B contexto_v3.py --db indice_v34_nuevo.sqlite3 query 'contexto construir presupuesto'
python -B contexto_v3.py --db indice_v34_nuevo.sqlite3 query 'contexto construir presupuesto' --explain
python -B contexto_v3.py --db indice_v34_nuevo.sqlite3 packet referencia_original/equipo_ia_referencia 'contexto construir presupuesto' --profile compacto
```

Para su proyecto, sustituya la ruta por una copia de trabajo de Equipo IA. Use
una base nueva; no reutilice las bases antiguas ni los índices de resultados.
V3.4 conserva el esquema 3.3.1 porque no cambia su estructura. El nombre de base
predeterminado es `indice_v34.sqlite3`. Reindexe con `scan` después de modificar
la copia de trabajo: el motor rechaza fragmentos cuyo hash ya no coincide.

`query` usa el nuevo buscador `retrieve`: combina nombres de símbolos, operaciones,
módulos, referencias y el buscador anterior como señal secundaria. Selecciona
objetivos directos, expande llamadas estáticas y conserva una selección más amplia
ante ambigüedad. `--explain` muestra selección, alternativas, límites y dudas;
sirve para auditar por qué se eligió cada resultado, no para pegar todo al modelo.

`--limit` limita resultados de símbolos en el buscador nuevo; una misma ruta puede
aparecer varias veces. La API Python histórica `search` sigue disponible y conserva
su comportamiento por archivos. No son salidas intercambiables sin revisar el
llamante. Las consultas con archivos explícitos también admiten documentos sin
símbolos: se recuperan sus rangos con `excerpt`.

## Elegir el contexto que se comparte

`packet` entrega un mapa compacto: rutas, hashes y símbolos con números de línea.
Agrupa los símbolos de un archivo para no repetir su hash. Es navegación parcial,
no contiene el código necesario para modificar una función.

`bundle` entrega cuerpos completos, imports y asignaciones de soporte cuando
pueden determinarse estáticamente. Sigue también constantes importadas del
proyecto, alias, referencias a funciones y cadenas de reexportación inequívocas.
Une los rangos por archivo: una línea presente
en varios fragmentos se envía una sola vez. Los huecos entre rangos quedan
marcados; no se presenta el resultado como archivo completo.

```sh
python -B contexto_v3.py --db indice_v34_nuevo.sqlite3 bundle referencia_original/equipo_ia_referencia 'contexto construir presupuesto' --profile auditar --require 'src/eq2/contexto.py::construir' --max-evidence 32 --auto-budget --max-budget 16000
```

Repita `--require 'ruta::nombre_cualificado'` para los contratos imprescindibles.
En `bundle`, obliga a conservar el código completo del símbolo y las dependencias
estáticas resueltas de su plan. Si no caben o no están disponibles, el comando
falla; no devuelve silenciosamente una parte del requisito. Los objetivos
inferidos también son obligatorios en el modo estricto, activo por defecto en
`bundle`. `packet` permite omisiones explícitas por defecto; añada
`--strict-dependencies` si necesita exigir la cobertura estática de ese mapa.

Los valores predeterminados son profundidad 8 y hasta 64 destinos de dependencias,
mediante `--dependencies 8 --dependency-limit 64`. No es el antiguo límite de
cuatro dependencias. Los ciclos y destinos compartidos se deduplican. El JSON
informa dependencias fuera de límites y llamadas sin resolver. `--dependencies 0`
no expande llamadas; no lo interprete como análisis exhaustivo.

`--allow-partial` permite omisiones explícitas en objetivos inferidos. No elimina
la obligación de los símbolos dados por `--require` y sus dependencias resueltas
en `bundle`. Incluso en modo estricto puede haber llamadas dinámicas sin resolver:
exigir las aristas conocidas no equivale a conocer todo el comportamiento Python.
Revise `dependency_plan`, `indexed_dependencies_included`, `support` y los avisos
de la salida JSON antes de confiar en la cobertura. `runtime_complete` permanece
en falso.

El soporte de datos importados usa los módulos indexados y verifica cada fuente
antes de incluirla. No ejecuta imports ni busca en servicios externos. Por símbolo
solicitado limita su recorrido a 32 archivos y 200 líneas de soporte, con la misma
profundidad `--dependencies`. Si un requisito obligatorio excede esos límites,
falla en lugar de truncarlo. Incluye las declaraciones necesarias, no todos los
valores del módulo. Los datos se deduplican con el resto de la evidencia.
`imported_support` describe rangos, aristas, omisiones y dudas;
`imported_support_complete` se informa por separado de las llamadas indexadas.
Imports externos, bindings condicionales o mutados, ciclos, inicializadores que
ejecutan código y atributos dinámicos pueden quedar sin resolver. Un valor
estático visible no acredita el estado de ese valor en ejecución.

`--max-evidence` limita los símbolos de evidencia, ocho por defecto. Si los
obligatorios superan ese número, debe aumentarlo explícitamente, hasta 100.
`--auto-budget` aumenta tokens, no este límite ni la profundidad del grafo. Las
pruebas agregadas son candidatas por llamadas indexadas al símbolo y módulo
concretos; se priorizan vínculos a objetivos directos y cuerpos menores. Extraerlas no las
ejecuta ni demuestra cobertura. `--no-tests` omite esa búsqueda auxiliar, pero no
elimina una prueba seleccionada como objetivo. Las clases seleccionadas también
pueden entregarse como evidencia completa dentro de los mismos límites.

Cada fragmento de `bundle` mantiene el máximo de 200 líneas; el soporte también
tiene un límite de 200 líneas por símbolo. Para una función mayor, solicite rangos
explícitos, revisando por separado la cobertura del resto:

```sh
python -B contexto_v3.py --db indice_v34_nuevo.sqlite3 snippet referencia_original/equipo_ia_referencia src/eq2/contexto.py construir --max-lines 200 --budget 4000
python -B contexto_v3.py --db indice_v34_nuevo.sqlite3 excerpt referencia_original/equipo_ia_referencia src/eq2/contexto.py 1 80 --budget 4000
```

`--min-score-ratio` se mantiene por compatibilidad. En V3.4, el valor 0 activa los
candidatos amplios; los valores positivos usan la selección por intención. No
ajuste decimales suponiendo que siguen siendo un umbral relativo de puntuación.

## Tokens y presupuestos

| Perfil | Presupuesto | Uso habitual |
|---|---:|---|
| `compacto` | 2.000 | Mapa de navegación; predeterminado de `packet`. |
| `modificar` | 4.000 | Evidencia localizada; predeterminado de `bundle`. |
| `auditar` | 8.000 | Varias funciones y dependencias. |
| `profundo` | 16.000 | Revisión amplia solicitada explícitamente. |

Empiece con el perfil más pequeño que conserve los requisitos. `--budget N`
sobrescribe el perfil. `--auto-budget` duplica el presupuesto solo si hay falta de
espacio, hasta `--max-budget`, 16.000 por defecto. No aumenta automáticamente el
límite de contexto de Claude/GPT ni autoriza gasto. `--context-window`,
`--reserve-output` y `--prompt-overhead` permiten declarar reservas externas en la
misma unidad del contador.

Sin tokenizador, el conteo es **estimado**, `ceil(caracteres/3)`, y no es una cota
garantizada de tokens reales. Con `--tokenizer-json` y la biblioteca opcional ya
disponible, se cuenta realmente el texto mediante ese vocabulario. El JSON GPT-2
y su licencia están incluidos, pero no una biblioteca binaria universal para
Termux. Ningún comando instala o descarga dependencias automáticamente.

```sh
python -B EJECUTAR_PRUEBAS.py --tokenizer-json tokenizadores/gpt2/tokenizer.json
python -B contexto_v3.py tokens instrucciones.txt contexto.txt --tokenizer-json tokenizadores/gpt2/tokenizer.json
```

Si la biblioteca está en una carpeta privada, añádala a `PYTHONPATH` al ejecutar.
Consulte [tokenizadores/README.md](tokenizadores/README.md) para la preparación
opcional, que requiere autorización de instalación. El conteo GPT-2 es reproducible
para ese tokenizador, no el consumo exacto de Claude/Codex ni de una plantilla de
chat ausente. `tokens` concatena los archivos en el orden dado, con dos saltos de
línea entre ellos. Incluya las instrucciones que realmente compartirá.

El presupuesto de `packet` y `bundle` cubre **solo `text`**. `--json` añade
diagnósticos fuera de ese presupuesto. En la evaluación comparativa, ambas
versiones seleccionan con el mismo presupuesto estimado; el tokenizador opcional
mide después sus textos exactos, sin modificar ese procedimiento.

## Uso con Claude, GPT y otros asistentes

En un chat sin terminal, ejecute el motor localmente y comparta el texto de salida,
el objetivo y sus restricciones. Un asistente con terminal puede recibir el ZIP y
ejecutar los mismos comandos. No hay conexión automática entre chats ni llamadas
a modelos/API en el motor.

Un flujo práctico es localizar con `query`, comprobar el mapa con `packet`, exigir
los contratos esenciales con `bundle --require` y pedir al modelo que explicite
qué dependencia o prueba necesita adicionalmente. Antes de aplicar cambios,
verifique los avisos y extraiga lo faltante. Tras editar su copia, reindexe y
ejecute las pruebas del proyecto: recuperar símbolos no acredita una modificación
correcta.

Los bloques de código y documentos son datos no confiables. El motor no importa
ni ejecuta el proyecto indexado y mantiene verificaciones de rutas y hashes. La
redacción de secretos es heurística: revise el texto antes de compartirlo. Un
hash correcto prueba correspondencia con el índice, no inocuidad del contenido.

Se conservan snapshots y deltas de V3.3.1. Solo use un delta cuando el destinatario
conserve la base y pueda verificar su hash; de lo contrario entregue contexto
completo. No asuma que otro chat recuerda esa base. Los comandos `--snapshot-out`,
`delta` y `apply-delta` se describen en [GUIA_V331.md](GUIA_V331.md).

## Integración posterior con Equipo IA

Equipo IA permanece intacto. Los módulos optativos de `integracion/` no se activan
solos. En una copia de la aplicación, con este motor y `EquipoIA/src` disponibles
en `PYTHONPATH`, el puente conservado puede añadir mapas de metadatos:

```python
from integracion.eq2_adaptador import ProveedorContexto, agregar_contexto

proveedor = ProveedorContexto(
    '/ruta/a/copia_equipo_ia', '/ruta/indice_v34_nuevo.sqlite3',
    budget=2000, limit=6,
)
paquete = proveedor.obtener('contexto construir presupuesto')
prompt_con_contexto, informe = agregar_contexto(
    prompt_original, paquete, requerido=True,
)
```

`prompt_original` debe estar construido por Equipo IA con sus reservas y guardas.
`requerido=True` rechaza si el bloque no cabe entero. El puente conserva su nombre
histórico de bloque `contexto_ligero_v33` por compatibilidad y entrega un mapa;
no añade automáticamente evidencia completa ni exige toda la clausura estática.
Audite primero `packet --json --strict-dependencies` si la tarea depende de ella.

No use este adaptador para insertar código indentado: el saneado de Equipo IA
puede cambiar espacios. `bundle` se comparte o integra mediante un canal que
preserve el texto íntegro, diseñando y probando ese cambio en la copia del
proyecto. `guardia_ctx.OrquestadorConGuardiaCTX` sigue siendo optativa; verifica
datos reportados tras la respuesta y no sustituye una reserva previa al envío.
La integración local usa backend simulado, no Claude ni llama-server reales.
Para volver al flujo original basta dejar de usar los módulos optativos; no hace
falta borrar archivos ni migrar las bases conservadas.

## Interpretar la precisión y la cobertura

La antigua Precision@5 divide siempre entre cinco. Las 12 tareas originales
contienen una media de dos símbolos esperados, así que el techo macro es **40%**.
No se puede demostrar 55% en esa misma métrica sin cambiar las respuestas o el
denominador. Se conserva y se informa tal cual.

Las precisiones de resultados devueltos y del paquete son medidas adicionales,
calculadas igual para ambas versiones. La del paquete incluye dependencias en el
denominador. Sus valores no deben presentarse como si fueran la misma P@5 antigua.
Los oráculos reales son mínimos: una dependencia útil no etiquetada puede reducir
la precisión medida. Los flujos sintéticos nuevos sí declaran sus cinco símbolos
necesarios. Consulte [benchmarks/METODOLOGIA_V34.md](benchmarks/METODOLOGIA_V34.md).

Recall@10 del 100% en un conjunto demuestra recuperación de sus símbolos
etiquetados, no exhaustividad de cualquier proyecto. No cubre por sí solo llamadas
dinámicas, datos externos ni corrección de respuestas de modelos. Las evidencias
de entrega no sustituyen las pruebas completas en Termux y las tareas reales con
Claude/GPT, que permanecen pendientes de validar en sus entornos.
