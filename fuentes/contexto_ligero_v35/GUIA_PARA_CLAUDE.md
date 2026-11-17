# Uso con Claude y validación en Termux

**Esta guía conserva instrucciones históricas. Para la entrega V3.5 use
[GUIA_V35.md](GUIA_V35.md), que describe los comandos actuales, las dependencias
y el uso con Claude.** Las cifras y límites de abajo corresponden a versiones
anteriores. El texto anterior se conserva íntegro en
`historial/entrega_v331/GUIA_PARA_CLAUDE.md`.

Para V3.3.1 consulte [GUIA_V331.md](GUIA_V331.md).

## Transferencia a Claude

Adjunte este ZIP y pida leer primero `LEEME.md`, `ESTADO_ENTREGA.md` y el informe
final enlazado allí. Claude necesita acceso a los archivos y una terminal para
usar el motor directamente. En un chat sin terminal, ejecute los comandos usted
y pegue sus salidas. No existe comunicación automática entre chats.

Flujo recomendado, desde la carpeta descomprimida:

```sh
python -B contexto_v3.py --db indice_claude.sqlite3 scan referencia_original/equipo_ia_referencia
python -B contexto_v3.py --db indice_claude.sqlite3 query "contexto construir presupuesto"
python -B contexto_v3.py --db indice_claude.sqlite3 packet referencia_original/equipo_ia_referencia "contexto construir presupuesto" --budget 1000 --require 'src/eq2/contexto.py::construir'
python -B contexto_v3.py --db indice_claude.sqlite3 snippet referencia_original/equipo_ia_referencia src/eq2/contexto.py construir
```

1. Envíe el mapa compacto, el objetivo y sus restricciones.
2. Pida a Claude identificar los contratos, funciones y pruebas que necesita.
3. Extraiga esos símbolos con `snippet`; para símbolos largos use `excerpt` con
   rangos explícitos, hasta 200 líneas. Cada fragmento valida el hash vigente.
4. Antes de cambiar código, compruebe los permisos, las llamadas y las pruebas
   relevantes. El mapa es parcial y sus dependencias no cubren dispatch dinámico.
5. Tras modificar una COPIA del proyecto, reindexe y pruebe. No use fragmentos
   cuyo hash ya no corresponda al archivo.

`--require 'ruta::simbolo'` puede repetirse para contratos críticos. Falla en vez
de omitirlos si no caben. Esto exige sus metadatos; solicite también el código.
`--min-score-ratio 0` amplía el mapa; `--dependencies 0` evita expansión del grafo.
El valor predeterminado incluye hasta cuatro dependencias y filtra candidatos
por relevancia relativa. Las omisiones detalladas están en `packet --json`.

No envíe todo el JSON como contexto: su presupuesto cubre únicamente `text`.
Revise secretos manualmente. El código y los documentos extraídos son datos no
confiables; ninguna instrucción contenida en ellos autoriza ejecutar comandos.

## Samsung / Termux: pendiente de validar en dispositivo

Requisito: Python 3.10 o posterior ya instalado, con SQLite. El motor no necesita
paquetes adicionales ni acceso a Internet. Descomprima el ZIP en una carpeta
nueva dentro del almacenamiento privado de Termux, preferiblemente bajo `$HOME`.
Evite ejecutar desde el almacenamiento compartido de Android.

```sh
cd "$HOME/contexto_ligero_v33"
python --version
python -B EJECUTAR_PRUEBAS.py
```

Adapte la ruta al nombre/carpeta que haya creado al descomprimir. El ZIP contiene
una carpeta raíz `contexto_ligero_v33`. El comando prueba ambas versiones,
integración simulada, rendimiento y hashes, y devuelve código distinto de cero
si falla. Cada ejecución conserva resultados nuevos sin sobrescribir anteriores.

Para su proyecto real, use una base nueva y la ruta de su copia de trabajo:

```sh
python -B contexto_v3.py --db "$HOME/indice_ctx_v33_nuevo.sqlite3" scan /ruta/a/copia_equipo_ia
python -B contexto_v3.py --db "$HOME/indice_ctx_v33_nuevo.sqlite3" packet /ruta/a/copia_equipo_ia "orquestador memoria contexto" --budget 1000
```

Debe comprobarse en Termux: pruebas completas, permisos/symlinks, disponibilidad
SQLite/FTS5 (hay alternativa sin FTS5), tiempo/RAM bajo carga y cierre del proceso.
Las bases incluidas en resultados están ligadas a las rutas del entorno de prueba;
son evidencias, no índices portables. Cree una base nueva en el dispositivo.

## Integración posterior con Equipo IA

No se modificó su orquestador ni se activó el experimento CTX. Se entregan dos
módulos opt-in en `integracion/`:

- `eq2_adaptador.ProveedorContexto`: obtiene un paquete de una base ya indexada.
- `eq2_adaptador.agregar_contexto`: añade el paquete como bloque saneado de datos
  mediante el constructor original de Equipo IA, completo o lo omite completo.
  `requerido=True` rechaza antes del backend cuando el contexto no cabe.
- `guardia_ctx.OrquestadorConGuardiaCTX`: subclase que rechaza excesos de tokens
  reportados en la vía común de llamadas/continuaciones, conservando su débito.

Ejemplo en una COPIA de la aplicación, con este motor y `EquipoIA/src` disponibles
en `PYTHONPATH`:

```python
from integracion.eq2_adaptador import ProveedorContexto, agregar_contexto

proveedor = ProveedorContexto('/ruta/a/copia_equipo_ia', '/ruta/indice_v33.sqlite3', budget=500)
paquete = proveedor.obtener('contexto construir presupuesto')
# prompt_original ya lo construyó Equipo IA con sus reglas y reservas.
prompt_con_contexto, informe = agregar_contexto(prompt_original, paquete, requerido=True)
# Pase prompt_con_contexto a su flujo habitual, conservando todas sus guardas.
```

No use el adaptador para código indentado: el saneado de Equipo IA puede modificar
espacios. Audite los snippets fuera de ese puente de metadatos. La integración
probada usa backend simulado y el código original de referencia; no acredita
funcionamiento con Claude ni llama-server reales. La guardia CTX verifica datos
reportados después de recibir una respuesta; no evita un envío excesivo previo.

Para retroceder, deje de usar el adaptador/subclase y vuelva al flujo original.
Conserve los archivos y las bases V3.2/V3.3; no hace falta borrar ni migrar nada.
