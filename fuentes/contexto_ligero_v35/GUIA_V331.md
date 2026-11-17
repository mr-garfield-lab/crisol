# V3.3.1: presupuestos, evidencia y contexto incremental

La ventana del modelo y el presupuesto de este motor son cosas diferentes. Este
motor controla cuánto texto entrega; no aumenta la ventana de Claude/Codex ni
modifica las reservas de Equipo IA.

## Presupuestos operativos

| Perfil | Presupuesto | Uso |
|---|---:|---|
| `compacto` | 2.000 | Navegación por metadatos; predeterminado de `packet`. |
| `modificar` | 4.000 | Código de la función, dependencias y pruebas candidatas; predeterminado de `bundle`. |
| `auditar` | 8.000 | Más evidencia para auditoría. |
| `profundo` | 16.000 | Revisión amplia solicitada explícitamente. |

Son tokens estimados salvo que se indique `--tokenizer-json`. El código anterior
ya aceptaba presupuestos manuales grandes; la mejora es ofrecer perfiles útiles
y ampliación controlada, no elevar arbitrariamente ese máximo técnico.

`--auto-budget` es opt-in. Duplica el presupuesto cuando falta espacio hasta
`--max-budget` (16.000 por defecto), sin superar el espacio de `--context-window`
tras restar `--reserve-output` y `--prompt-overhead`. Estas cifras usan la misma
unidad del contador seleccionado y las reservas las aporta quien llama al motor.
Una estimación de caracteres no garantiza caber en la ventana real de un modelo.

```sh
python -B contexto_v3.py --db indice_v331_nuevo.sqlite3 scan referencia_original/equipo_ia_referencia
python -B contexto_v3.py --db indice_v331_nuevo.sqlite3 packet referencia_original/equipo_ia_referencia 'contexto construir presupuesto' --profile compacto
python -B contexto_v3.py --db indice_v331_nuevo.sqlite3 bundle referencia_original/equipo_ia_referencia 'contexto construir presupuesto' --profile auditar --require 'src/eq2/contexto.py::construir' --auto-budget --max-budget 16000
```

`--budget N` sobrescribe el perfil. `--json` muestra los presupuestos intentados,
el efectivo y las omisiones. Compartir solo `text` si se quiere respetar el
presupuesto informado; el JSON diagnóstico añade metadatos fuera del contexto.
No hay ampliación implícita ni autorización de gasto/API.

## Evidencia que conserva los requisitos

`packet` entrega un mapa. `bundle` entrega código verificado por SHA256, con
líneas, funciones completas y redacción heurística. En `bundle`, cada `--require`
obliga a incluir **el código completo** del símbolo; si no cabe, falla. Para
contratos esenciales, repetir `--require` con sus funciones concretas.

Se mantienen 200 líneas máximas por símbolo: el presupuesto mayor no elimina esa
protección. Para símbolos más largos, usar `excerpt` por rangos explícitos. Las
pruebas incluidas por `bundle` son candidatas por referencias/nombres AST; no se
afirma que cubran todo ni que hayan sido ejecutadas. `--no-tests` desactiva esta
búsqueda y `--max-evidence` limita el número de fragmentos. Revisar omisiones.

La redacción de credenciales no es infalible. Revisar manualmente antes de
compartir. El motor no importa ni ejecuta el proyecto indexado.

## Conteo de todo el texto

`tokens` concatena los archivos en el orden indicado, con dos saltos de línea
entre ellos por defecto. Permite contar instrucciones, mapa y fragmentos juntos:

```sh
python -B contexto_v3.py tokens instrucciones.txt mapa.txt fragmento.txt --tokenizer-json tokenizadores/gpt2/tokenizer.json
```

El tokenizador es opcional; requiere la biblioteca descrita en `tokenizadores/`.
Se desactivan truncamiento y padding para contar el texto entero. No hay descarga
implícita, plantilla de chat oculta ni equivalencia prometida con Claude/Codex.
Incluya explícitamente la plantilla real si dispone de ella y necesita contarla.
Los perfiles de 8.000/16.000 no son la ventana soportada por el modelo GPT-2:
su vocabulario se utiliza como unidad reproducible de medición, sin ejecutar GPT-2.

## Contexto incremental con una base conocida

Primero guardar una base y entregarla completa al asistente:

```sh
python -B contexto_v3.py --db indice_v331_nuevo.sqlite3 packet referencia_original/equipo_ia_referencia 'contexto construir presupuesto' --snapshot-out base.json --json
```

Conservar `snapshot_sha256` mostrado por el comando. Después de cambiar SU COPIA
del proyecto, reindexar y crear `actual.json` con la misma consulta. No modificar
`referencia_original` para practicar: use un proyecto o copia de trabajo aparte.

```sh
python -B contexto_v3.py delta base.json actual.json --expected-base HASH_DE_BASE --output cambio.json --stats
python -B contexto_v3.py apply-delta base.json cambio.json --expected-base HASH_DE_BASE --output reconstruido.json
```

Los archivos de salida deben ser nuevos: no se sobrescriben. El delta exige una
base con el hash correcto; su reconstrucción debe coincidir con el hash objetivo.
Si no ahorra o cambia el origen, se envía un sobre completo. `--stats` informa el
coste real del JSON de transporte, incluido overhead, y lo compara también con
el texto plano. El delta puede ahorrar frente al sobre completo y no frente a
pegar solo texto: ambas cifras se muestran.

No asumir que otro chat recuerda la base. Si no la conserva o no puede verificar
la reconstrucción, entregar el contexto completo. Esto no conecta chats entre sí.

## Integración y validación

La base de datos nueva es esquema 3.3.1. No migra ni sobrescribe bases V3.2/V3.3;
cree un nombre nuevo y conserve las anteriores. El adaptador de Equipo IA sigue
usando su constructor y sus reservas; elevar el perfil no evita sus comprobaciones.

```sh
python -B EJECUTAR_PRUEBAS.py
```

El comando compara V3.2, V3.3 validada y esta edición en 12 tareas de Equipo IA y
8 tareas sintéticas congeladas. Añadir `--tokenizer-json` y la biblioteca local
habilita la medición real del vocabulario elegido. Termux físico y modelos reales
siguen requiriendo validación en esos entornos.
