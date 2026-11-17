# Equipo IA V3 — Etapa 2: grafo y contexto

**Estado: CERRADA** (2026-11-10). `verificar_v3.py --completo` da F0–F7 correctas (`evidencias/etapa2_3/`).

## 1. Qué aporta y cómo

Se REUTILIZA Contexto Ligero V3.5 sin reimplementarlo ni modificarlo:

- **Copia en el laboratorio:** `contexto_ligero/` es una copia idéntica de
  `fuentes/contexto_ligero_v35/{contexto_core, contexto_v3.py}` y de sus tareas de benchmark.
- **Procedencia:** se registra en `contexto_ligero/ORIGEN_SHA256.json`, con 20 archivos; una prueba exige que no
  se añada, quite ni altere ninguno.
- **Adaptador:** `eq3/grafo.py` es una capa fina que no duplica la lógica de Contexto Ligero.

| Capacidad de la orden maestra | Implementación | Evidencia |
|---|---|---|
| Indexación del repositorio | `Grafo.indexar()` → `index.scan`: archivos, símbolos y aristas de llamada | `sistema/src`: 68 archivos, 1.150 símbolos y 880 aristas en 0,75 s |
| Grafo de dependencias | `Grafo.dependencias()` → `dependency_plan`, que declara `runtime_complete: False` (no ve el despacho dinámico) | `TestIndiceIncremental` |
| Grafo de tareas y decisiones | `Grafo.importar_traza()`: objetivos, ejecuciones, 23 decisiones, versiones v1→v2→v3 (`depends_on`, acíclico) y experiencias (`relates_to`), todo desde la traza de la Etapa 1 | `TestGrafoDeTrazas` |
| Recuperación contextual | `recuperar()` devuelve archivos y símbolos con su SHA-256 ACTUAL; `paquete()` arma un contexto con presupuesto de tokens ESTIMADOS («no es cota de tokens reales») | `test_paquete_en_presupuesto_y_honesto_con_los_tokens` |
| Actualización incremental | Sin cambios no se reprocesa nada (0 de 68); con un archivo cambiado, solo ese (1 de 68) | `test_incremental_cambio_y_borrado_invalidan` |
| Invalidación | Un archivo borrado se elimina del índice (`stale_removed: 1`) y no vuelve a ofrecerse | ídem |
| Integración con la memoria | Las experiencias de A1/A2/A3 quedan enlazadas en el grafo con la ejecución que las produjo | `TestGrafoDeTrazas`. La recuperación de recuerdos por consulta y la comparación con y sin memoria corresponden a la Etapa 5 |

## 2. Medición de la recuperación (tareas reales)

**Oráculos.** No son míos. Son las tareas de Contexto Ligero declaradas antes de su benchmark
(`declared_before_benchmark`) sobre el código de Equipo IA: `tasks_v35_reales.json`, `tasks_v34_reales.json` y
`tasks_independientes.json`.

**Aplicación a esta versión.** Se traducen `src/eq2/…` → `eq2/…`, y solo se conservan los pares (archivo,
símbolo) cuyo símbolo existe en V2-F.1. Quedan **20 tareas**. Se descartan **15 pares**, todos de
`tasks_independientes.json`, que se refiere a otro corpus (`src/commerce/…`) que no está aquí.

**Comparación.** Línea ingenua: archivos ordenados por la frecuencia de los términos de la consulta.

| Recall de archivos relevantes (media de 20 tareas) | @1 | @3 | @5 |
|---|---|---|---|
| Contexto Ligero (`recuperar`) | **0,95** | **1,00** | **1,00** |
| Línea ingenua | 0,25 | 0,55 | 0,65 |

**Precauciones** (no se ocultan):

- Las consultas contienen nombres de símbolos y las escribió el autor de Contexto Ligero para su herramienta, lo
  que puede favorecerla.
- Los oráculos son «mínimos relevantes, no exhaustivos».
- 20 tareas es una muestra pequeña, y solo se mide el recall por archivo.
- La medición es reproducible: dos ejecuciones dan exactamente lo mismo (prueba).

## 3. Pruebas

| Prueba | Resultado |
|---|---|
| `pruebas/test_eq3_grafo.py` | 8 de 8 correctas |
| Mutación de la Etapa 2 (`v3/mutaciones/etapa2.json`) | 6 de 6 detectadas |
| Verificador integral | F0–F7 correctas; F5 = mutación de la Etapa 2, 6 de 6 |

Mutaciones detectadas:

- versiones sin enlazar;
- ejecución sin objetivo;
- experiencias sin enlazar;
- reimportación no idempotente;
- oráculos sin traducir, que se descartarían en silencio;
- copia de Contexto Ligero alterada.

## 4. Limitaciones

1. **Alcance del análisis:** el índice extrae símbolos de Python por análisis estático; las dependencias
   dinámicas, las reexportaciones y los datos quedan fuera (Contexto Ligero lo declara).
2. **Tokens:** se estiman (caracteres/3). La medición real requiere el tokenizador de cada modelo, que no está
   instalado.
3. **Grafo posterior:** el grafo de tareas se construye después de las ejecuciones, desde la traza. A1, A2 y A3
   todavía no lo consultan durante una tarea; esa integración corresponde a la Etapa 4 (coordinación).
4. **Plataformas:** no validado en Android/Termux ni en Windows. Contexto Ligero declara compatibilidad con Termux
   (POSIX, SQLite y FTS5 opcional); aquí FTS5 está disponible.
