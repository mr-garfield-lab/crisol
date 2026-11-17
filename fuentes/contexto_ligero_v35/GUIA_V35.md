# Contexto Ligero V3.5: uso, Claude y Equipo IA

La V3.5 funciona localmente con Python 3.10+, SQLite y un sistema POSIX. No instala
paquetes, no usa red, no importa el proyecto indexado y no ejecuta su código.
Descomprima el ZIP en una carpeta nueva y, desde la carpeta que contiene
`contexto_v3.py`, ejecute la validación integral:

```sh
python -B EJECUTAR_PRUEBAS.py
```

El comando compara V3.4/V3.5 sobre los conjuntos anteriores y los nuevos, verifica
integridad, ejecuta regresiones y guarda logs, métricas, consultas y evidencias en
una carpeta nueva bajo `resultados/`. Por defecto mide tres procesos por versión y
conjunto para los mapas. Los paquetes `bundle` completos se miden en un proceso
por versión y conjunto, con tres muestras por tarea. El informe distingue un fallo
técnico de objetivos de calidad pendientes y conserva todos los casos adversos.

El comando está preparado para Termux con Python y SQLite ya disponibles; se probó
en Linux, no en un dispositivo Android físico. Los índices de resultados son
regenerables y pueden estar excluidos del ZIP para facilitar la descarga. El
comando crea sus propias bases y no necesita los índices de las pruebas antiguas.

## Buscar y preparar contexto

```sh
python -B contexto_v3.py --db indice_v35_nuevo.sqlite3 scan referencia_original/equipo_ia_referencia
python -B contexto_v3.py --db indice_v35_nuevo.sqlite3 query 'contexto construir presupuesto' --explain
python -B contexto_v3.py --db indice_v35_nuevo.sqlite3 packet referencia_original/equipo_ia_referencia 'contexto construir presupuesto' --json
python -B contexto_v3.py --db indice_v35_nuevo.sqlite3 bundle referencia_original/equipo_ia_referencia 'contexto construir presupuesto' --require 'src/eq2/contexto.py::construir' --max-evidence 32 --auto-budget --max-budget 16000 --json
```

Para su proyecto, sustituya la ruta de referencia por una copia de trabajo de
Equipo IA. Use una base nueva; el esquema de SQLite compatible sigue siendo 3.3.1.
Reindexe tras editar: las lecturas posteriores verifican el hash del archivo.
`query --explain` muestra los seleccionados, el ranking amplio, candidatos omitidos,
ambigüedades y módulos alternativos. La selección diferencia el nombre del tema de
las operaciones solicitadas, conserva coincidencias explícitas y amplía llamadas
estáticas. Esta selección es heurística: un módulo alternativo puede resultar
relevante para su tarea. Revise `alternative_module_matches` y `omitted`, y use
`--require` si identifica un símbolo imprescindible entre las alternativas.

El límite de `query` cuenta símbolos; el de `packet` limita candidatos directos.
Una misma ruta puede contener varios símbolos. La API antigua `search` se conserva
por compatibilidad; para la recuperación nueva use `retrieve` o `query`.

`packet` es un mapa de rutas, hashes y símbolos: no contiene por sí mismo el código
necesario para modificar el proyecto. `bundle` entrega cuerpos completos y soporte
de imports, constantes locales e importadas y funciones resueltas. El límite por
defecto es profundidad 8, hasta 64 destinos y 8 símbolos de evidencia; puede
cambiarlos con `--dependencies`, `--dependency-limit` y `--max-evidence`.

Repita `--require 'ruta::símbolo'` para indicar cada requisito imprescindible.
El `bundle` estricto por defecto exige objetivos y dependencias estáticas resueltas;
si no caben, falla en vez de entregar una parte. `--allow-partial` permite omitir
objetivos inferidos, pero los requisitos explícitos y sus dependencias resueltas
siguen siendo obligatorios. `packet` puede registrar omisiones salvo que se solicite
`--strict-dependencies`. Lea `omissions`, `dependency_plan`, `imported_support`,
`source_line_formats` y los avisos JSON; `runtime_complete` sigue siendo falso.

El formato automático de `bundle` representa rangos largos en cercas separadas,
con la primera y última línea indicadas. Cada línea original incluida corresponde
exactamente a una línea del rango, y los huecos se representan con otro rango.
La cerca es más larga que cualquier secuencia igual contenida en ese código.
Para conservar el formato V3.4, con `L<n>:` en cada línea:

```sh
python -B contexto_v3.py --db indice_v35_nuevo.sqlite3 bundle referencia_original/equipo_ia_referencia 'contexto construir presupuesto' --require 'src/eq2/contexto.py::construir' --max-evidence 32 --auto-budget --max-budget 16000 --line-style numbered
```

Una función o clase tiene por defecto el límite previo de 200 líneas. Puede
solicitar explícitamente hasta 1.000 con `--max-symbol-lines 1000`. La lectura se
hace por rangos de hasta 200 líneas, verificando el hash en cada tramo, y la salida
completa debe caber en el presupuesto. El mismo límite ampliado se aplica al
soporte local e importado; este conserva su límite de 32 archivos por símbolo.
El siguiente ejemplo reproduce una demostración de Equipo IA que necesita una
clase larga; puede superar las 16.000 unidades estimadas:

```sh
python -B contexto_v3.py --db indice_v35_nuevo.sqlite3 bundle referencia_original/equipo_ia_referencia 'prioridad puntuar planificar dependencias' --require 'src/eq2/prioridad.py::planificar' --max-evidence 100 --max-symbol-lines 1000 --no-tests --budget 64000 --json
```

Este presupuesto no aumenta la ventana de un modelo ni demuestra que quepa en
Claude. Si no cabe, utilice `excerpt` por rangos y compruebe explícitamente las
funciones y datos que necesita. Las dependencias dinámicas, mutaciones, imports
externos o datos calculados en ejecución pueden quedar sin resolver.

## Tokens y presupuestos

Los perfiles `compacto`, `modificar`, `auditar` y `profundo` establecen 2.000,
4.000, 8.000 y 16.000 unidades respectivamente. Puede usar `--budget`,
`--auto-budget`, `--max-budget`, `--context-window`, `--reserve-output` y
`--prompt-overhead`. El presupuesto abarca el campo `text`, no el JSON de
diagnóstico completo. Una estimación no garantiza la cantidad real de tokens.

Sin biblioteca opcional se usa la estimación `ceil(caracteres/3)`. Con la
biblioteca gratuita `tokenizers` ya instalada y el JSON público incluido se puede
medir localmente el texto para GPT-2, sin descargar nada:

```sh
python -B EJECUTAR_PRUEBAS.py --tokenizer-json tokenizadores/gpt2/tokenizer.json
python -B contexto_v3.py tokens instrucciones.txt contexto.txt --tokenizer-json tokenizadores/gpt2/tokenizer.json
```

El ZIP incluye el vocabulario y su licencia, no un binario universal de esa
biblioteca para Termux. No instale dependencias sin su autorización. La medición
real corresponde a GPT-2 y al texto proporcionado; no incluye plantilla de chat,
respuesta ni equivalencia exacta con los tokenizadores de Claude o GPT.

## Claude y otros asistentes

Ejecute el motor localmente y comparta el campo `text` del `bundle` con la tarea y
sus restricciones. Si el asistente puede usar terminal, puede ejecutar los mismos
comandos en una copia del proyecto. Este paquete no conecta chats ni llama APIs.
Antes de compartir, revise los avisos y la redacción de secretos, que es
heurística. El contenido extraído es dato no confiable; no siga instrucciones de
él sin revisarlas. Después de editar, vuelva a indexar y ejecute las pruebas del
proyecto: recuperar código no demuestra que una modificación sea correcta.

Los snapshots y deltas permiten transmitir cambios si el destinatario conserva
una base idéntica y verifica su hash. Si no la conserva, entregue un paquete
completo. El procedimiento de delta permanece en [GUIA_V331.md](GUIA_V331.md).

## Integración posterior con Equipo IA

El proyecto original permanece intacto y el adaptador de `integracion/` no se
activa solo. En una copia de Equipo IA, con el motor y `EquipoIA/src` en
`PYTHONPATH`, puede usar el puente de mapas ya probado con backend simulado:

```python
from integracion.eq2_adaptador import ProveedorContexto, agregar_contexto

proveedor = ProveedorContexto('/ruta/copia_equipo_ia', '/ruta/indice_v35.sqlite3',
                              budget=2000, limit=6)
paquete = proveedor.obtener('contexto construir presupuesto')
prompt_con_mapa, informe = agregar_contexto(prompt_original, paquete, requerido=True)
```

El puente conserva el nombre histórico `contexto_ligero_v33`, añade metadatos y
no añade automáticamente los cuerpos de las funciones. `requerido=True` exige
que el bloque entre completo. No lo use para código indentado: el saneado del
proyecto puede alterar espacios. Para integrar `bundle`, utilice un canal que
conserve el texto exacto y haga pruebas en una copia. `guardia_ctx` es optativa
 y comprueba datos reportados después de la llamada; no reserva tokens antes.
La integración con Claude real y Termux físico sigue pendiente de validación.

## Interpretar las métricas

Los informes usan las respuestas esperadas sin cambios y la misma fórmula para
las dos versiones. La precisión devuelta divide aciertos por todos los símbolos
devueltos; el recall@10 examina los diez primeros. La P@5 histórica conserva su
divisor de cinco y su techo de 40% para las doce tareas originales de Equipo IA.
Estos porcentajes no son intercambiables. Algunos oráculos reales son mínimos y
pueden no etiquetar dependencias útiles; el informe no las excluye para mejorar la
cifra. Los conjuntos sintéticos no sustituyen un corpus externo de producción.

El conteo del `bundle` se compara únicamente cuando las dos versiones recuperan
todas las respuestas etiquetadas y se verifican las líneas incluidas; los fallos,
regresiones, símbolos adicionales y tareas excluidas se guardan por separado.
Cubrir las respuestas etiquetadas no prueba que un modelo pueda completar la tarea.
