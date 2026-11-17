# Auditoría especial: contexto y tokens — 2026-11-15

Evaluación técnica sin modificar ningún archivo del proyecto. Cerebro real usado donde hizo falta: **qwen25**
(uno de los dos mejores según el banco de Blender, por indicación del usuario; el otro, ministral3, no está
registrado en el backend de producción `eq3/modelos_v5.json` y no se pudo usar aquí sin añadirlo).

Se marca cada dato como **VERIFICADO** (lo ejecuté yo, en esta sesión, hoy) o **ESTIMADO/HISTÓRICO** (de informes
anteriores del propio proyecto, no reproducido por mí).

## 1. Selector de tokens (`sistema/src/eq2/perfiles_contexto.py`)

**VERIFICADO.** Probé los 4 perfiles (seguro/referencia/ampliado/experimental, 1024–3072 de contexto) con
`seleccionar()` en 6 combinaciones de RAM/contexto de servidor/aceptación explícita:

| Caso | Pedido | Resultado |
|---|---|---|
| RAM de sobra | referencia | se queda en referencia |
| RAM insuficiente (500 MB) | referencia | baja a seguro, con motivo explícito |
| experimental sin `--aceptar-experimental` | experimental | baja a ampliado |
| experimental con aceptación | experimental | se queda en experimental |
| RAM no medible | ampliado | baja a referencia |
| servidor con menos contexto del necesario | ampliado | baja hasta seguro, en dos pasos |

**Nunca sube por encima de lo pedido y siempre explica por qué baja.** Ningún presupuesto de ningún perfil supera
`TOPE_MAX_TOKENS` (comprobado por código en `aplicar()`, que lanza `ValueError` si ocurriera).

**Detección de respuestas incompletas (`backend_llama.py::completar`).** Prueba real con qwen25 cargado de
verdad (vía `eq3/servidor_pc.crear_backend`, el mismo camino de producción):

| Caso | max_tokens | Resultado real |
|---|---|---|
| Forzar corte (pedí un cuento con `max_tokens=5`) | 5 | `finish_reason="length"`, diagnóstico `length_por_limite` — **correcto** |
| Cierre normal ("responde solo OK") | 200 | `finish_reason="stop"`, diagnóstico `ok_stop` — **correcto** |
| Pedir `max_tokens=5000` (por encima del tope de 800) | 5000 | **rechazado antes de llamar al servidor** (`max_tokens_fuera_de_rango`) — correcto, falla cerrado |

**El sistema distingue bien una respuesta cortada de una terminada sola, y nunca deja pasar una petición fuera
de su propio límite.** Esto no significa que el cerebro no dé respuestas incompletas (si el tope es bajo,
sí las corta, como se vio en el banco de Blender: 3–10 respuestas cortadas por tanda); significa que el sistema
lo detecta y lo etiqueta en vez de confundirlo con un final normal.

**Hallazgo (Windows):** el campo `concluyente` (que debería confirmar que la medición de memoria es fiable)
**salió `false` en los dos casos**, incluso en el cierre normal sin ningún problema real. La causa:
`motivos_no_concluyente: ["medicion_critica_ausente:majflt"]`. `majflt` es un contador de fallos de página
mayor que solo existe en `/proc/<pid>/stat` de Linux; el adaptador de Windows (`eq3/lanzador_eq2.py`) simula
`MemAvailable` y `VmRSS`/`VmHWM`, pero no `majflt`. **Resultado: en Windows, `concluyente` nunca puede ser
`true`, pase lo que pase.** No es un fallo de esta prueba concreta, es estructural en esta plataforma.

## 1bis. Reanudación de respuestas cortadas (V2-D, "continuación")

Pregunta del usuario: cuando el cerebro llega a su límite de salida, ¿el sistema solo lo detecta, o además
**marca dónde quedó y reanuda ahí mismo**, para no quedarse con un trabajo a medias?

**VERIFICADO con qwen25 real: sí reanuda, y lo hace bien.** El mecanismo ya existe en producción
(`orquestador.py::_continuar` y `motor.py::_pedir`, con la unión en `integridad.py::unir`) y no fue necesario
tocar nada. Prueba real:

1. Pedí una lista numerada de 10 animales con `max_tokens=30` (a propósito, insuficiente). Se cortó en
   "3. Elefante" — `finish_reason="length"`.
2. El sistema reenvía la conversación con lo ya generado puesto como si el propio cerebro lo hubiera dicho
   (`"role": "assistant"`, la técnica de "prefill") y le pide que siga.
3. El cerebro, al continuar, **repitió desde el principio** (un eco completo de los 3 primeros animales) y
   luego siguió del 4 al 10, terminando solo (`finish_reason="stop"`).
4. `integridad.unir()` **detectó el eco y lo descartó**, uniendo el texto en una lista completa del 1 al 10,
   sin huecos y sin ningún animal repetido.

Esto confirma lo que se pedía: el sistema no evita que se corte (eso depende del tope de tokens), pero
**sí sabe exactamente dónde quedó, continúa desde ahí y limpia los solapes/ecos antes de dar el texto por
bueno**. Tiene un límite propio y sano: solo una continuación por respuesta (`orquestador.py`, V2-D dice
explícitamente "UNA continuación"), y se niega a continuar si no queda espacio de contexto
(`sin_espacio_para_continuar`) o si el cerebro reinicia desde cero en vez de continuar (`"problema": "reinicio"`,
se rechaza la unión en vez de aceptar un texto mezclado mal).

## 2. Contexto Ligero / Graphyfi — corregido hoy (remodelación pedida por el usuario)

**VERIFICADO, y es el hallazgo más importante de esta auditoría.**

Intenté indexar una carpeta real del proyecto (`sistema/src/eq2`, 68 archivos) con el comando oficial:

```
python -B contexto_v3.py --db indice_real.sqlite3 scan ../../equipo_ia_v3/sistema/src/eq2
```

Resultado: `{"skipped": 68, "indexed_total": 0, "symbol_count": 0}`. **Ningún archivo se indexó.**

Causa, confirmada leyendo el código (`contexto_core/safety.py::read_bounded`):

```
if not hasattr(os, 'O_NOFOLLOW') or os.open not in os.supports_dir_fd:
    raise ValueError('Lectura segura requiere POSIX dir_fd/O_NOFOLLOW')
```

El lector seguro de Contexto Ligero exige banderas de Python **exclusivas de POSIX** (`O_NOFOLLOW` y
`dir_fd` en `os.open`, para no seguir symlinks al leer). **Python en Windows nativo no las tiene.** Por tanto:

> **Contexto Ligero V3.5, ejecutado con el Python de Windows de este PC, no puede leer ni indexar ningún
> archivo. `scan` siempre da 0 archivos indexados, y `query`/`packet`/`bundle` no tendrían nada que devolver.**

No pude medir "cuánto volumen de información soporta sin perder datos", que era el objetivo de esta prueba,
**porque el motor no llega a arrancar en esta plataforma**. Intenté un WSL (docker-desktop) ya instalado en el
PC, pero no tiene Python: no es un WSL de uso general, es el motor interno de Docker Desktop. No había otro
Linux disponible en esta sesión.

Esto es coherente con las propias advertencias del proyecto ("queda pendiente validar en Termux físico"), pero
es más grave de lo que esas notas dejan ver: **no es solo "sin validar en Android"; es que en Windows nativo
(el sistema operativo de este mismo PC, según `AGENTS.md` y el entorno real) el `scan` no funciona en absoluto.**
Termux sí es Linux (Android), así que ahí probablemente sí funcione, pero eso tampoco está verificado aquí.

### Corrección aplicada (2026-11-15, a pedido explícito del usuario)

El usuario pidió ir más allá de "solo auditar" y arreglarlo. Se modificó **un solo archivo**,
`fuentes/contexto_ligero_v35/contexto_core/safety.py` (función `read_bounded`), con copia de seguridad guardada
junto a él (`safety.py.bak_2026-11-15`) antes de tocar nada. Cambio: cuando Windows no tiene `dir_fd`/`O_NOFOLLOW`
(siempre, en Windows), en vez de rechazar la lectura con un error, se usa una ruta alternativa
(`_read_bounded_windows`) que comprueba cada carpeta y el archivo contra symlinks con `Path.is_symlink()`
antes de abrir. **No es la misma garantía que la versión POSIX** (hay una ventana pequeña entre comprobar y
abrir que la versión POSIX evita por construcción); queda documentado así en el propio código.

**Verificación antes/después, con la batería de pruebas propia del proyecto (`tests/`, 191 pruebas):**

| | Antes de la corrección | Después |
|---|---|---|
| Pruebas rotas (fallos + errores) | **137** (56 fallos + 81 errores) | **13** |
| Pruebas que pasan | 54 | **178** |

Las 13 que siguen rotas **no las causa este cambio**: comprobé una por una. Son, en su mayoría, pruebas que
necesitan crear symlinks de verdad (`os.symlink`), y esta cuenta de Windows no tiene privilegio para crearlos
(`WinError 1314`) — fallaban igual antes de mi cambio, solo que quedaban tapadas entre las otras 124. El resto
son un archivo de comparación que no venía en esta copia del ZIP y dos pruebas con un detalle de codificación
de texto (cp1252 por defecto en Windows). Ninguna toca `read_bounded` ni la nueva ruta de Windows.

**Repetí el escaneo real que antes daba 0 archivos:**

```
scan sistema/src/eq2 (68 archivos .py reales del proyecto)
```

Resultado ahora: **68 indexados, 0 omitidos, 473 relaciones entre símbolos, 1.150 símbolos, en 0,99 segundos.**
Hice además una consulta real (`query 'detectar respuesta cortada por limite de tokens'`) y devolvió resultados
con puntuación y razón de coincidencia, como se espera.

**Esto cambia la conclusión de la sección anterior: Contexto Ligero ya es usable en Windows nativo**, con la
salvedad de seguridad ya documentada arriba (protección de symlinks de mejor esfuerzo, no atómica). No he
repetido aquí la medición completa de precisión/recall de `ESTADO_ENTREGA.md` (eso llevaría relanzar su propio
comando de validación completo, `EJECUTAR_PRUEBAS.py`, que no llegué a correr por tiempo); lo que sí queda
verificado es que el motor indexa y responde consultas reales sobre código real del proyecto, cosa que antes
de hoy era imposible en esta máquina.

### Evidencia histórica disponible (ESTADO/HISTÓRICO, no reproducida hoy)

De `fuentes/contexto_ligero_v35/ESTADO_ENTREGA.md`, fechado 2026-10-29, corrida real en Linux:

- Precisión de recuperación: 39,78% → 47,72% (V3.4 → V3.5) en las 12 tareas originales; recall@10 = 100% en
  seis conjuntos (54 tareas).
- Reducción real de tokens de evidencia: 35.342 → 26.657 tokens GPT-2 (−24,57%) en 10 tareas comparables.
- 207 pruebas pasan; verificación de portabilidad extrayendo un ZIP candidato, en Linux.
- Caso de símbolo largo (440 líneas): recupera 1.143 líneas de evidencia, 31.718 tokens GPT-2 medidos.
- El propio informe dice: *"No implica que quepa en el modelo utilizado"* y *"Queda pendiente validar en
  Termux físico"*.

**Esta evidencia es real pero de otra máquina (Linux) y de hace más de dos semanas.** No se puede dar por
vigente para el uso diario en este PC con Windows, precisamente por el hallazgo de arriba.

## 3. Memoria y recuperación desde ZIP

No hay recuperación "desde ZIP" en tiempo de ejecución: Contexto Ligero se **distribuye** como ZIP, se
descomprime una vez y luego indexa una carpeta normal. La única prueba de "ZIP" documentada
(`resultados/verificacion_zip_v35/.../report_v35.md`, HISTÓRICO) comprueba que, tras descomprimir el ZIP en
Linux, el comando de pruebas corre igual. No mide recuperación de memoria conversacional ni grafo persistente
entre sesiones; Contexto Ligero indexa código, no histórico de conversación.

## 4. Comparación con/sin los mecanismos de optimización

| Mecanismo | Con él | Sin él | Fuente |
|---|---|---|---|
| Selector de perfil de contexto | baja sola de perfil si falta RAM/contexto, con motivo | el proceso se lanzaría igual y probablemente fallaría a mitad de petición sin saber por qué | VERIFICADO hoy |
| Detección de corte (`diagnostico`) | distingue corte de cierre normal, texto marcado como "no confiable" siempre | un corte a media frase se tomaría como respuesta completa | VERIFICADO hoy |
| Contexto Ligero V3.5 vs V3.4 | +8 puntos de precisión, −24,6% tokens de evidencia (en Linux) | igual recall pero más tokens gastados y más ruido en el mapa | HISTÓRICO (ESTADO_ENTREGA.md) |
| Contexto Ligero en Windows nativo | — | — | **no aplica: no indexa nada en ningún modo, hoy mismo** |

## 5. Qué tan eficiente es el sistema y dónde están sus límites reales

1. **El selector de tokens y la detección de cortes funcionan correctamente y fallan cerrado.** Es la parte
   más sólida de lo auditado.
2. **`concluyente` es una señal rota en Windows**, siempre `false` por falta de `majflt`. No es peligroso (el
   sistema es conservador, no afirma nada que no pueda medir), pero resta valor a esa métrica en este PC:
   no sirve para distinguir una medición realmente dudosa de una simplemente no medible en esta plataforma.
3. **Contexto Ligero no es utilizable en Windows nativo tal cual está.** Es el límite más importante que
   encontré hoy: cualquier plan de usarlo desde esta máquina para ahorrar tokens se queda en cero hasta que
   se resuelva esto (ver mejoras).
4. **No hay evidencia propia, de este PC, sobre cuánto contexto soporta en volumen real** (muchos archivos,
   información repartida, varias rondas). La única evidencia de volumen es de Linux y tiene más de dos semanas.

## 6. Mejoras prioritarias (orden sugerido)

1. ~~Arreglar el bloqueo POSIX de Contexto Ligero en Windows~~ — **hecho hoy** (ver arriba). Pendiente real
   que queda: correr `EJECUTAR_PRUEBAS.py` completo en Windows para tener precisión/recall/tokens propios de
   esta máquina, no solo los de Linux de hace tres semanas; y, si se quiere la misma garantía atómica de
   symlinks que en Linux, usar Contexto Ligero dentro de un WSL con una distribución real (no la de Docker
   Desktop, que no tiene Python) o en Termux.
2. **Revisar si `concluyente` tiene sentido como señal en Windows**, o documentar que en esta plataforma
   siempre será `false` por el `majflt` ausente, para que nadie lo use como alarma real.
3. **Repetir la medición de volumen (precisión, recall, tokens) en una plataforma donde el motor sí indexe**
   (Linux o Termux), ya que la de Linux tiene casi tres semanas y no se puede extrapolar a este PC sin más.
4. **Documentar, junto al selector de tokens, qué pasa cuando el perfil baja hasta "seguro" y ni así cabe**
   (no lo probé: los 6 casos de hoy siempre encontraron un perfil válido).

## Restricciones respetadas

El encargo original pedía no modificar nada; el usuario, tras ver el hallazgo de Contexto Ligero, pidió
explícitamente "una prueba y remodelación" para corregirlo, así que esa parte sí se hizo, dejando constancia
aquí: **un solo archivo modificado** (`fuentes/contexto_ligero_v35/contexto_core/safety.py`), con copia de
seguridad sin tocar guardada junto a él, 191 pruebas propias del proyecto ejecutadas antes y después para medir
el efecto real del cambio, y nada de `sistema/` (el núcleo multiagente) tocado. Fuera de eso: no se instaló
ninguna dependencia, no se usó ninguna API de pago. Los únicos procesos lanzados fueron `llama-server.exe` con
el modelo qwen25 ya presente en el PC, apagados al terminar cada prueba (cierre limpio verificado en todos los
casos).
