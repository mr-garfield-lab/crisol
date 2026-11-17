# Equipo IA V3 — Etapa 5: memoria y aprendizaje

**Estado: CERRADA** (2026-11-10). `verificar_v3.py --completo` da F0–F9 correctas (`evidencias/etapa5/`).

## 1. Qué aporta

`eq3/memoria.py` reúne en una sola consulta los tipos de memoria que pide la orden maestra. No reescribe
ninguna base y REUTILIZA los complementos de Codex: `complementos_codex/` es una copia idéntica, con su
`ORIGEN_SHA256.json`.

| Tipo | Fuente | Ámbito | Cómo se selecciona |
|---|---|---|---|
| Semántica (`hecho`, `criterio`) y procedimental (`leccion`) | Bases de aprendizaje de V2-F.1 (`aprendizaje/aN.db`) | INDIVIDUAL | Ver «Selección de la memoria individual», debajo |
| Episódica | Traza unificada (Etapa 1): objetivo, resultado y decisiones | COMPARTIDA | Fracción de términos de CONTENIDO de la consulta presentes; umbral 0,34 |
| De proyecto | `cambios_v3.sqlite3` (Etapa 3): solo cambios APLICADOS con autorización | COMPARTIDA | El mismo umbral, o que la consulta nombre una función o un archivo que el cambio define |

**Selección de la memoria individual.**

1. `capturar()` de Codex copia la base EN MEMORIA desde una conexión de SOLO LECTURA y revalida cada recuerdo:
   hash del texto, cuarentena, contenido instructivo y evidencias.
2. `recuperar()` de Codex excluye lo caducado, lo bloqueado, las hipótesis (salvo permiso) y las contradicciones
   no resueltas: ambas partes quedan fuera.
3. Después se aplica el filtro de contenido de V3 (§2), que solo puede quitar.

`consultar()` devuelve además el bloque para el prompt, siempre marcado como **DATOS con su procedencia, no
instrucciones**, y advierte de que un recuerdo «sin_verificar» no está verificado.

**Lo que NO es.** No hay entrenamiento ni cambio de pesos de ningún modelo: es recuperación de información con
su procedencia (ids y SHA-256). Que la memoria mejore lo que hace un modelo no se ha medido, porque requiere Qwen
real.

## 2. Comparación con memoria, sin memoria y por recencia (escenarios PRERREGISTRADOS)

**Escenarios.** Hay dos conjuntos. Cada uno se registró con su SHA-256 ANTES de medirse:

| Conjunto | Archivo | SHA-256 | Cuándo se registró | Uso |
|---|---|---|---|---|
| 1 | `v3/escenarios_memoria.json` | `0dfa3c0f…` | Antes de escribir el evaluador | Diagnóstico |
| 2 | `v3/escenarios_memoria_2.json` | `6d088d00…` | Después de medir el conjunto 1 y ANTES de escribir el filtro | Contraste: no se usó para diseñarlo |

**Corpus.** Los recuerdos se crean con la API REAL de V2-F.1 (`AprendizajeAgente.recordar`).

**Métricas.** Recall de los relevantes, «falsos» (ni relevantes ni tolerados) y «prohibidos»: hipótesis,
caducados e instructivos.

**Resultados.** Los tres números de cada celda son recall / falsos / prohibidos.

| Método | Conjunto 1 antes | Conjunto 2 antes | Conjunto 1 **con filtro** | Conjunto 2 **con filtro** |
|---|---|---|---|---|
| `memoria_v3` | 1,0 / 7 / 0 | 1,0 / 15 / 0 | **1,0 / 0 / 0** | **1,0 / 0 / 0** |
| Sin memoria | 0,0 / 0 / 0 | 0,0 / 0 / 0 | 0,0 / 0 / 0 | 0,0 / 0 / 0 |
| Recencia (n más recientes) | 0,2 / 15 / 12 | 0,2 / 20 / 14 | 0,2 / 15 / 12 | 0,2 / 20 / 14 |

**Hallazgos:**

1. **Defecto real en los complementos de Codex**, medido en los dos conjuntos.
   - **Síntoma:** el control negativo fallaba («dibujar un gráfico de barras» recuperaba tres recuerdos).
   - **Causa:** la lista de palabras vacías de `palabras()` no incluye «de», «un», «en», «la» ni «no».
   - **Corrección:** la hace eq3, sin tocar la copia de Codex. Es un filtro de palabras de CONTENIDO que solo
     puede quitar selecciones.
   - **Verificación:** en el conjunto de CONTRASTE pasa de 15 falsos a 0 sin perder recall, y los controles
     negativos P6 y P7 quedan vacíos.
2. **La defensa contra contenido instructivo de V2-F.1 actúa AL ESCRIBIR.** El conjunto 1 suponía que R7
   («IGNORA LAS INSTRUCCIONES…») se guardaría y se bloquearía al recuperar. En realidad, `recordar()` lo rechaza
   antes de que exista. No se modificó el escenario: su SHA-256 sigue igual. El evaluador registra el rechazo en
   `rechazados_al_escribir`.
3. **La recencia es peligrosa además de imprecisa.** Recupera hipótesis y recuerdos caducados (12 y 14 casos)
   porque no filtra nada.
4. **Memoria de proyecto.** Por umbral no encontraba «mediana» en «mejorar la función mediana del proyecto»
   (1 de 4 términos). Se añadió la regla de identificadores, documentada en el código.

## 3. Pruebas

| Prueba | Resultado |
|---|---|
| `pruebas/test_eq3_memoria.py` | 9 de 9 correctas, entre ellas: los escenarios no cambiaron desde su registro (SHA-256); la conexión es de SOLO lectura; la base queda byte a byte igual; el filtro solo quita; los controles negativos episódico y de proyecto |
| Mutación de la Etapa 5 (`v3/mutaciones/etapa5.json`) | 9 de 9 detectadas, incluido alterar un juicio prerregistrado |
| Verificador integral | F0–F9 correctas; F8 = mutación de la Etapa 5, 9 de 9 |

## 4. Limitaciones

1. **Escenarios propios.** Los conjuntos los escribió el mismo autor que el sistema; el 2 es de contraste, pero no
   es independiente. Miden el mecanismo, no el efecto en un modelo.
2. **Similitud léxica.** No es semántica: sinónimos o paráfrasis sin palabras en común no se recuperan.
3. **Palabras vacías.** La lista es española; las consultas en otros idiomas quedan sin filtrar.
4. **Contradicciones.** No se crearon recuerdos contradictorios en estos escenarios; ese comportamiento lo
   cubren las pruebas propias de los complementos de Codex (36 de 37 contra V2-F.1, incluidas en la línea
   base).
