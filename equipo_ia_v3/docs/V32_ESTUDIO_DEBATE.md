# Equipo IA V3.2 — Estudio y debate técnico: multicerebro, grafo reactivo, conocimiento, rendimiento y seguridad

**Autor:** Claude Code (programador principal) · **Fecha:** 2026-11-11 · **Para:** el usuario, GPT-6 y Ricardo
**Estado:** análisis independiente, **sin implementación**. No se ha modificado código, instalado nada ni descargado
ningún modelo para este estudio. Base: Equipo IA V3.1 (F0.5 cerrada en Windows y etapa de mantenimiento).

**Cómo leer las afirmaciones.** Cada una lleva una de estas marcas:
- **[IMPL]**: implementado y con pruebas en el repositorio (se cita el archivo).
- **[MEDIDO]**: medido en este PC durante V3.1.
- **[ESTIM]**: estimación razonada (cálculo o regla general), no medida.
- **[HIPÓT]**: hipótesis por comprobar.
- **[NO VERIF]**: no he podido comprobarlo con lo disponible.

---

## 0. Resumen

1. **Buena parte de lo propuesto ya existe** en V2-F.1, Contexto Ligero o la capa V3:
   - la revisión ciega;
   - la cuarentena de conocimiento no verificado;
   - la distinción entre hecho e hipótesis;
   - el índice incremental con invalidación por SHA-256;
   - el contexto incremental con hashes;
   - los presupuestos dinámicos de tokens;
   - la lista blanca de herramientas;
   - la reanudación del verificador.

   Antes de construir nada hay que **conectar y medir** lo que ya hay. Reconstruirlo duplicaría código y riesgos.
2. **Nada de la arquitectura multicerebro se puede decidir sin F1.** Ningún agente ha resuelto todavía una tarea
   con un modelo real, así que cualquier comparación «uno o dos modelos» sería hoy especulación.
3. **Lo que más tiempo puede ahorrar no es de IA:** es la **reutilización determinista de resultados de pruebas por
   dependencias declaradas** (§6). La batería tarda unos 41 minutos [MEDIDO], y un 40–45 % es el verificador de
   V2-F.1, que está congelado y cuyo resultado solo puede cambiar si cambian sus entradas.
4. **El segundo modelo crítico es la única propuesta de IA con una justificación técnica sólida**: con temperatura 0
   y un solo modelo, la diversidad solo viene de los prompts (lo dice el propio `debate.py`). Pero en 8 GB de VRAM
   tiene costes reales, y debe ganarse su sitio en un experimento con errores sembrados (§10, X3).
5. **El «cerebro auxiliar de conocimiento» no necesita ser un modelo.** Lo que se le pide es recuperación,
   dependencias, caducidad y selección de pruebas, y eso ya lo hacen, o lo harían mejor, Python, SQLite y el grafo:
   de forma determinista, auditable y miles de veces más rápida.
6. **Fragmentación, compresión LZ4/Zstd y caché compartida entre agentes no tienen nada que optimizar aquí.** Los
   agentes no se transfieren datos por una red: están en el mismo proceso. El coste real es de **tokens de prompt**.
   Para eso existe la caché de prefijos de llama.cpp, que V2-F.1 ya activa (`cache_prompt: true`) pero que el
   cambio de agente probablemente invalida (§5).
7. **Recomendación:** Alternativa 1 (conservadora) ampliada con tres mejoras deterministas, y la Alternativa 2
   **condicionada** al experimento X3. La Alternativa 3 se descarta para este hardware y esta fase.

---

## 1. Estado real del proyecto (punto de partida)

| Capacidad | Estado | Dónde |
|---|---|---|
| Debate A1/A2/A3 con propuestas **independientes a ciegas**, ejecución cruzada y **adjudicación determinista** (la mayoría no sustituye a las pruebas) | [IMPL] con agentes SIMULADOS; nunca con un modelo real | `sistema/src/eq2/debate.py` |
| Recuento de votos determinista («el código cuenta; el modelo no decide») | [IMPL] | `sistema/src/eq2/protocolo.py` |
| Registro inmutable de herramientas, validación previa y errores clasificados | [IMPL] | `sistema/src/eq2/herramientas.py` |
| Control de contaminación de la memoria: plegado Unicode y homoglifos, análisis por cláusulas, cargas codificadas, instrucciones indirectas → rechazo o cuarentena | [IMPL] | `sistema/src/eq2/contaminacion.py` |
| Hecho (observado por el sistema) frente a lección u opinión (hipótesis de confianza baja); nada nace verificado | [IMPL] | `sistema/src/eq2/experiencias.py` |
| Recuperación de memoria que excluye lo caducado, bloqueado o en cuarentena, las hipótesis (salvo permiso) y las contradicciones no resueltas | [IMPL] | `eq3/memoria.py` |
| Índice de código SQLite **incremental**: solo reprocesa archivos cuyo SHA-256 cambió y elimina los desaparecidos | [IMPL] | `contexto_ligero/contexto_core/index.py` (`scan`), `eq3/grafo.py` |
| Contexto incremental (instantáneas y deltas con hash; «los hashes detectan cambios, no autentican») | [IMPL] | `contexto_core/delta.py` |
| Paquetes de contexto por intención con clausura estática «sin pérdida silenciosa» | [IMPL] | `contexto_core/packets.py` |
| Presupuestos de tokens por perfil (2000/4000/8000/16000) con crecimiento automático acotado por la ventana | [IMPL] | `contexto_core/budget.py` |
| Verificador de citas determinista (líneas, símbolos, casos y hechos contrastados con el archivo real) | [IMPL] | `eq3/citas.py` |
| Recall@k del grafo frente a oráculos prerregistrados | [IMPL] | `eq3/grafo.py` (`medir`) |
| Reanudación del verificador con huella exacta de código y entorno | [IMPL] (mantenimiento) | `verificar_v3.py --reanudar` |
| Ejecución de código generado | **Bloqueada** en Windows (el ejecutor restringido falla de forma cerrada). En Linux es una lista blanca AST con límites, **no un sandbox** | SEG-01 pendiente (F3) |
| Modelo real (Qwen + llama-server) | **Nunca ejecutado** | F1 pendiente |

**Consecuencia:** las propuestas deben formularse como «conectar, medir y, si hace falta, ampliar», no como
«crear».

---

## 2. Propuesta A — Arquitectura multicerebro

### 2.1 Cerebro principal (Qwen)

De acuerdo. Es el plan de F1: Qwen2.5-Coder-7B-Instruct Q4_K_M entero en la GPU, con un único `llama-server` en
`127.0.0.1` compartido por turnos (`docs/V31_PLAN_ACTIVACION_F1.md`).

### 2.2 Cerebro crítico de otra familia

**A favor (fundado):**
- Varios agentes del mismo modelo comparten sesgos y puntos ciegos. `debate.py` lo reconoce: con temperatura 0 y un
  solo modelo, la diversidad solo puede venir de prompts distintos.
- Un modelo de otra familia (otro preentrenamiento y otros datos) tiene, en principio, errores menos correlacionados
  [HIPÓT]. Es la única forma de independencia que no se consigue con prompts.

**En contra o con riesgo:**
- **Capacidad.** Lo que cabe junto al 7B es un modelo de unos 2–4 B parámetros. Un crítico más débil que el autor
  puede aportar más ruido que señal: objeciones falsas que A1 tiene que rebatir, rondas extra y tiempo [HIPÓT].
- **VRAM** [ESTIM]: el 7B Q4_K_M ocupa unos 4,7 GiB de pesos más la caché KV. Un 3–4 B en Q4 ocupa unos 2–2,5 GiB.
  Con los dos residentes, a unos 7–7,5 GiB, **no queda margen** en 8 GiB, sobre todo porque se midieron unos
  2 GiB ya usados por otras aplicaciones [MEDIDO, F0.5]. Las opciones serían:
  - (a) crítico en la CPU (Ryzen 5 5600GT): mucho más lento [ESTIM: un orden de magnitud por debajo de la GPU];
  - (b) alternar modelos cargando y descargando: unos segundos por cambio si el GGUF está en la caché de disco, más
    en frío [ESTIM, NO VERIF];
  - (c) dos modelos más pequeños, con el riesgo de perder calidad en el principal.
- **Cadena de suministro.** Cada modelo nuevo es otro GGUF que verificar, otra licencia y otra superficie de
  análisis para llama.cpp (§8).

**Revisión ciega antes de ver a A1:** ya existe (`debate.py`, paso 1). Lo que falta es **medir** si reduce el
anclaje, y eso entra en el experimento X3.

**Conclusión:** la pregunta de investigación es correcta. Debe responderse con el experimento X3 (errores sembrados,
§10), no por diseño. Si un Qwen con instrucciones de crítica detecta los errores sembrados casi igual que un modelo
de otra familia, el segundo modelo sobra.

### 2.3 Cerebro auxiliar de conocimiento

| Función pedida | ¿Necesita IA? | Qué ya existe o qué haría |
|---|---|---|
| Buscar información relevante | No | `retrieval` de Contexto Ligero, medido con recall@k frente a oráculos |
| Preparar paquetes de contexto | No | `packets.build_packet` + `budget` |
| Dependencias entre archivos | No; la IA sería peor | `dependencies.dependency_plan` (AST) |
| Recuperar experiencias verificadas | No | `eq3/memoria.py`, `experiencias.py` |
| Detectar información obsoleta | No | Hash del origen frente al hash al registrar: si el archivo cambió, el recuerdo caduca (determinista) |
| Detectar contradicciones | En parte | Ya se excluyen las contradicciones registradas; detectar contradicciones semánticas nuevas sí necesitaría un modelo, y su salida sería solo una hipótesis |
| Proponer relaciones semánticas | Sí | Salida tipo «inferida» en cuarentena (§3); valor dudoso frente a su riesgo |
| Seleccionar pruebas de regresión | **No debe** | Selección determinista por dependencias (§6); ninguna IA decide qué pruebas se omiten |

**Conclusión:** un tercer modelo añadiría VRAM, latencia y una vía de contaminación para dos funciones marginales.
Se descarta. Las funciones deterministas se mejoran en la capa V3.

---

## 3. Propuesta B — Grafo reactivo incremental

**¿Se puede evolucionar Contexto Ligero sin reconstruirlo?** Sí, y es lo que ya hace V3. `eq3/grafo.py` lo usa sin
modificarlo (copia idéntica comprobada por prueba) y lo amplía por fuera. Así se mantiene la compatibilidad de sus
interfaces.

| Punto pedido | Estado | Propuesta |
|---|---|---|
| 1. Detección de cambios | [IMPL] por SHA-256 en `scan` | Suficiente para archivos; para funciones, comparar el hash de cada símbolo (rango de líneas del AST) |
| 2. Índice incremental | [IMPL] | — |
| 3. Invalidación de cachés | [IMPL] para el índice | Extenderla a paquetes y recuerdos: cada uno guarda los hashes de lo que usó; si alguno cambia, deja de ser válido |
| 4. Notificación selectiva a agentes | No existe | **Sin vigilantes de archivos** (watchers), que se comportan distinto en Windows, Linux y Termux y añaden concurrencia. Basta con un `scan` al inicio de cada paso (barato porque es incremental) y un «qué cambió desde tu última versión» como lista de rutas y símbolos |
| 5. Versionado de nodos y relaciones | Parcial (versiones de la traza) | Cada relación guarda el hash de origen y destino con los que se estableció |
| 6. Recuperación tras interrupciones | Índice en SQLite con transacciones | Confirmar el `commit` por archivo y añadir pruebas de corte a mitad de `scan` (§9-E) |
| 7. Historial de experiencias verificadas | [IMPL] en V2-F.1 | — |

**Tres clases de relaciones:** muy de acuerdo, y con una regla más dura. Una relación solo cambia de clase por un
evento determinista:
- **estructural**: la crea el análisis AST;
- **verificada**: la crea una prueba registrada, con la ruta y el SHA-256 de su resultado;
- **inferida**: la propone un modelo.

Ningún modelo puede crear relaciones estructurales ni verificadas. Al recuperar, una inferida nunca se presenta como
hecho: va etiquetada y solo si se pide expresamente, igual que las hipótesis en `memoria.py`. Esta regla tiene que
llevar mutaciones que la protejan.

**Riesgo nuevo:** las relaciones inferidas a partir de comentarios o cadenas del código son una vía de **inyección**,
porque un comentario malicioso puede «sugerir» relaciones o textos. Deben pasar por `contaminacion.py` como los
recuerdos.

---

## 4. Propuesta C — Fragmentación, caché e intercambio

**Objeción de fondo.** La propuesta parece pensada para agentes distribuidos que se transfieren datos. En Equipo IA,
A1, A2 y A3 son **turnos de un mismo coordinador** en un solo proceso: no hay transferencia que fragmentar ni
comprimir. El coste no está en los bytes (los contextos son de unos pocos KB a unos cientos de KB de texto), sino en
**cuántos tokens procesa el modelo**.
- **LZ4/Zstd:** no hay nada que optimizar. Comprimir texto que después hay que descomprimir para meterlo en un prompt
  no reduce tokens. **Se descarta** salvo que algún día haya transporte entre máquinas.
- **Fragmentos con identificador, versión, hash, procedencia, relaciones y permisos:** útiles como **modelo de datos**
  del conocimiento (`delta.py` y `packets.py` ya tienen buena parte), no como protocolo de intercambio.
  - Los permisos por agente tienen sentido. Ejemplo: A3 no debe ver la propuesta de A1 durante la revisión ciega,
    y eso es un control de acceso.
  - La procedencia necesita **autenticación**, no solo hash (§8).
- **Fuente autoritativa centralizada:** de acuerdo; ya lo es (SQLite del laboratorio).
- **Cachés locales por agente:** desaconsejadas. Cada caché es otra copia que puede quedar obsoleta. Mejor una única
  fuente con consultas baratas: el índice ya es local y rápido.

### 4.1 Lo que sí importa: la caché de prefijos y la caché KV de llama.cpp

- V2-F.1 envía `cache_prompt: true` [IMPL, `backend_llama.py`] y registra `cache_n` y `prompt_ms` por petición
  [IMPL]. **El instrumento de medida ya existe.**
- Con `--parallel 1` y agentes que alternan, el prefijo común se rompe en cuanto empieza el texto propio de cada
  agente (su rol). Lo probable [HIPÓT] es que cada cambio de agente reprocese casi todo el prompt.
- Dos palancas, ambas medibles con `cache_n` y `prompt_ms`:
  1. **Ordenar el prompt** para que lo compartido (tarea, paquete de contexto, hechos) vaya antes de lo específico
     del rol. Así se reutiliza entre agentes. Cambia el comportamiento de los modelos, así que hay que comparar la
     calidad.
  2. **Una ranura (slot) por agente** (`--parallel 3`, asignando la ranura en cada petición): cada agente conserva
     su propia caché. Coste [ESTIM, a partir de la configuración publicada de Qwen2.5-7B: 28 capas, 4 cabezas KV,
     dimensión 128]: unos 56 KiB por token en f16, unos 448 MiB por ranura de 8 192 tokens, alrededor de 1,3 GiB
     para tres ranuras (la mitad con KV q8_0). **Cabe con el 7B solo** y no con dos modelos residentes, lo que
     enfrenta las Propuestas A y E.

---

## 5. Propuesta D — Batería de pruebas adaptativa

**Dato de partida** [MEDIDO, 2026-11-11]: `verificar_v3.py --completo` tarda unos 2 400–2 500 s, unos 41 minutos.
F11 (la línea base de 503 pruebas) se lleva unos 16–19 minutos, y casi todo es el verificador de V2-F.1.

**Propuesta (mejor que la planteada): reutilización determinista por dependencias declaradas, no por IA.**
- Cada fase declara sus **entradas**, por ejemplo:
  - F11: `sistema/`, `fuentes/`, `eq3/lanzador_eq2.py`, `eq3/plataforma.py`, `v3/linea_base*.py`, las líneas base y
    el entorno;
  - F12: `eq3/` y sus pruebas.
- `--reanudar` (ya implementado con huella de TODO el árbol) pasaría a huella **por fase**: una fase se reutiliza si
  la huella de **sus** entradas es idéntica.
- **Estimación** [ESTIM]: un cambio solo de documentación no repetiría nada salvo el empaquetado; un cambio en `eq3/`
  sin tocar el lanzador repetiría F2, F12 y poco más. En las iteraciones de desarrollo, entre un 50 % y un 90 % menos
  de tiempo.
- **Riesgo principal: una dependencia no declarada.** Un resultado obsoleto pasaría por bueno. Medidas:
  1. las entradas declaradas son un superconjunto conservador (directorios enteros, no archivos sueltos);
  2. una prueba que compruebe que cada fase solo lee archivos dentro de sus entradas declaradas (con un registro de
     aperturas, como el diagnóstico de F0.5);
  3. una mutación que cambie un archivo de una dependencia y exija que la fase se repita;
  4. **la batería completa sin reutilización sigue siendo obligatoria para toda entrega** (vuestra restricción, que
     comparto).
- **Selección por cobertura (pytest-testmon):** el proyecto usa `unittest` y no tiene `coverage` instalado. La
  selección por dependencias declaradas da casi todo el beneficio sin instalar nada y es más fácil de auditar.
  testmon sería una alternativa futura [NO VERIF en este proyecto].
- **Detección de pruebas inestables: prioritaria, y ya tenemos un caso real.** Hoy F11 falló por **V-CON-11**: una
  subprueba de V2-F.1 compara dos lecturas seguidas de la memoria disponible, y con memoria real de Windows a veces
  difieren unos kB [MEDIDO: 1 fallo en 30 ejecuciones aisladas]. Propuesta: la línea base se genera a partir de N
  ejecuciones; lo que varía se declara **inestable con su causa**, y la puerta lo trata aparte, nunca como OK ni como
  regresión silenciosa.
- **El cerebro crítico proponiendo casos adversariales:** útil, pero sus casos son **hipótesis** hasta que un humano o
  un oráculo los acepte. Es exactamente lo que hace `debate.py` con los casos de agente, que pueden ser impugnados y
  no deciden contra el oráculo.

---

## 6. Propuesta E — Rendimiento y tokens

**No invento cifras de velocidad:** ninguna está medida, porque F1 no se ha ejecutado. Lo que sí se puede razonar:

| Componente | Qué domina | Palanca |
|---|---|---|
| Procesado del prompt | Tokens de contexto × agentes × rondas | Grafo + presupuesto; caché de prefijos y ranuras (§4.1) |
| Generación | Tokens generados; la velocidad la fija el ancho de banda de la GPU | Límites de tokens por paso (ya existen); respuestas estructuradas cortas |
| Cambio de modelo | Carga del GGUF | Evitarlo: un modelo residente, o el crítico en la CPU |
| Recuperación de contexto | SQLite local | Ya es del orden de milisegundos [ESTIM]; no es el cuello de botella |
| Pruebas | Batería integral, unos 41 min [MEDIDO] | §5 |

**Ventanas de contexto** [ESTIM]: en el 7B, 4 096 y 8 192 tokens caben con holgura. Con 16 384, la caché KV sube a
unos 0,9 GiB en f16 por ranura; con otras aplicaciones usando la GPU, el margen se vuelve escaso. **Mi postura:**
empezar con 8 192 y el perfil `compacto` o `modificar`, y medir si la calidad mejora al crecer. El objetivo del grafo
es **reducir** contexto. Vuestra frase al respecto es exactamente la correcta.

**Presupuestos dinámicos:** ya existen (`budget.py`): el presupuesto solo crece si el contenido obligatorio no cabe,
y nunca por encima de la ventana. Falta decidir **quién** pide más. Debe ser una regla determinista: tipo de tarea y
omisiones informadas por el paquete, no el modelo.

**Métrica central:** de acuerdo con «tiempo total por tarea correctamente resuelta y verificada». La definiría así:

> tiempo de pared desde el enunciado hasta una solución que pasa el oráculo prerregistrado, dividido por las tareas
> resueltas, contando también el tiempo gastado en tareas fallidas.

Junto a ella, registraría:
- tokens de prompt y generados;
- VRAM máxima;
- intervenciones humanas;
- regresiones introducidas;
- respuestas «no concluyentes».

---

## 7. Propuesta F — Seguridad

Los 12 requisitos me parecen correctos. Los números 1–3, 6 y 10 ya están [IMPL] en V2-F.1:
- herramientas en lista blanca;
- validación previa;
- `contaminacion.py`;
- «nada nace verificado».

El 5 (aislamiento real) **no** está resuelto, y lo repito: el ejecutor restringido de V2-F.1 no es un sandbox y en
Windows ni siquiera funciona.

### 7.1 Amenazas NUEVAS que introduce la arquitectura propuesta

| Amenaza | Dónde | Medida |
|---|---|---|
| **GGUF malicioso o corrupto** (cadena de suministro; los analizadores de GGUF han tenido vulnerabilidades) | Cada modelo nuevo | Solo de fuentes oficiales, SHA-256 publicado y comprobado antes de cargarlo, llama.cpp actualizado; un modelo nuevo exige aprobación del usuario |
| **Inyección a través del grafo**: comentarios o cadenas del código que se convierten en etiquetas o relaciones inferidas y acaban en prompts | B, C | Todo texto que llega al grafo desde el contenido pasa por `contaminacion.py`; las inferidas, en cuarentena |
| **Fuga entre agentes por la caché** | Ranuras KV | La caché de prefijos solo reutiliza un prefijo **idéntico**: no inyecta contenido de otro prompt [ESTIM, por cómo funciona]. El riesgo real es de **diseño**: un paquete común que incluya la propuesta de A1 rompería la revisión ciega. Control de acceso por agente sobre los paquetes, con pruebas |
| **Procedencia falsificada**: un registro que dice «verificado por prueba X» sin serlo | Relaciones verificadas, experiencias | El SHA-256 no autentica (de acuerdo con vosotros). Firma **HMAC con una clave del anfitrión** que ningún agente ni contenedor conoce, sobre cada evento verificado; verificación al recuperar |
| **TOCTOU** (se comprueba un hash y se usa otra versión) | Fragmentos y paquetes | Leer una vez y usar los mismos bytes cuyo hash se comprobó; `leer_acotado` ya comprueba el inodo |
| **Envenenamiento de la selección de pruebas** | D | Ninguna IA selecciona ni omite pruebas: la selección es por dependencias declaradas y la batería integral es obligatoria en las entregas |
| **Escalada por el crítico**: un segundo modelo con más permisos «para revisar» | A | Mismo registro de herramientas: el crítico **solo lee** lo que se le entrega y no tiene herramientas que ejecuten |
| **STOP durante un cambio de modelo** | A | El STOP debe cubrir la carga y descarga (V2-F.1 ya aborta durante la carga del servidor); prueba específica con servidor falso lento |
| **Concurrencia en SQLite** si aparecen procesos auxiliares | B, D | Un único escritor (el coordinador), transacciones cortas, WAL; pruebas de corte |

---

## 8. Ideas adicionales (§9 de la propuesta)

| Idea | Valoración |
|---|---|
| A. Revisión ciega | **Ya implementada** (`debate.py`, paso 1). Falta medir su efecto (X3) |
| B. Grafo de evidencias (problema → hipótesis → solución → cambio → prueba → resultado) | **Buena, y barata**: la traza unificada (Etapa 1) y `importar_traza` ya llevan objetivos, decisiones, versiones y experiencias al grafo. Faltan los nodos de hipótesis y de prueba con su resultado firmado. Es la base para saber *por qué* se aceptó algo |
| C. Contaminación del conocimiento | **Ya implementado** (cuarentena, caducidad, contradicciones). Se extendería a las relaciones inferidas |
| D. Presupuesto de razonamiento | Bien, siempre que **decida el código con reglas** (riesgo y tamaño de la tarea, historial) y nunca un modelo. Los controles obligatorios no dependen de esa decisión |
| E. Fallos controlados | **Muy recomendable.** El proyecto ya tiene la infraestructura (mutaciones, servidor falso con modos de fallo, pruebas de STOP). Añadir: corte a mitad de `scan`, caché corrupta, fragmento con hash erróneo, respuestas contradictorias entre modelos |
| F. Métrica de productividad verificable | De acuerdo; definición en §6 |

---

## 9. Comparación de alternativas

| | **1. Conservadora** (un Qwen; grafo, caché y pruebas) | **2. Intermedia** (+ crítico de otra familia; auxiliar determinista) | **3. Avanzada** (2 modelos + auxiliar IA + grafo reactivo distribuido) |
|---|---|---|---|
| Beneficio esperado | Menos tokens y tiempo de prueba; base medible | + errores menos correlacionados en la crítica [HIPÓT] | + algo de recuperación semántica [HIPÓT] |
| Riesgo | Bajo | Medio: VRAM, latencia, otro GGUF | Alto: contaminación, coherencia de cachés, superficie de ataque |
| Complejidad | Baja: casi todo existe | Media | Alta |
| Compatibilidad V3.1 | Total | Alta (backend por agente; V2-F.1 ya inyecta el backend) | Baja: reescribe el flujo de conocimiento |
| Recursos (8 GiB VRAM) | Cabe con holgura, incluso con 3 ranuras KV [ESTIM] | Justo: un modelo en la CPU o alternar modelos | No cabe sin degradar el principal |
| Mantenimiento | Bajo | Medio | Alto, para una sola persona |
| Regresiones posibles | Pocas, y cubiertas por la batería | Rondas extra con objeciones falsas | Difíciles de detectar (no determinista) |
| **Veredicto** | **Adoptar** | **Solo si X3 lo justifica** | **Descartar ahora** |

---

## 10. Experimentos pequeños y reversibles (en orden)

Todos con criterios fijados **antes** de ejecutarlos, sin tocar `sistema/` y reversibles (capa V3 o ramas de Git
local).

| # | Experimento | Requiere | Aceptar si… | Rechazar si… |
|---|---|---|---|---|
| **X0** | **F1** tal como está planificada: S1 / S1×3 / E3 sobre las mismas tareas | Aprobación de F1 | — (es la medida base) | — |
| **X1** | Detección de pruebas inestables: línea base a partir de 3 ejecuciones | Nada nuevo | Identifica V-CON-11 y no marca nada que sea determinista (comprobado repitiendo) | Marca como inestable una regresión real sembrada (mutación) |
| **X2** | Huella **por fase** en `--reanudar` | Nada nuevo | Tras un cambio solo en documentación o solo en `eq3/`, el tiempo baja ≥ 50 %, **y** una mutación con una dependencia oculta obliga a repetir la fase | Cualquier caso de reutilización con una entrada cambiada |
| **X3** | **Crítico con errores sembrados**: ≥ 30 errores conocidos (generados con la infraestructura de mutaciones sobre código del proyecto); A3 con Qwen frente a A3 con un modelo de otra familia de 2–4 B | F1 hecha; aprobación para descargar el segundo modelo | El segundo modelo detecta ≥ 15 puntos porcentuales más de errores sembrados, con ≤ 50 % más de tiempo por tarea, estable en 2 ejecuciones | Diferencia < 15 puntos o más objeciones falsas que aciertos nuevos |
| **X4** | Caché de prefijos: orden del prompt (compartido primero) y ranura por agente | F1 hecha | `prompt_ms` total por tarea −30 % o más, **sin** pérdida de aciertos en X0 | Pérdida de aciertos o VRAM por encima del tope |
| **X5** | Clases de relaciones (estructural / verificada / inferida) en la capa V3 | Nada nuevo | Ninguna mutación logra que una inferida llegue a «verificada» sin un evento de prueba firmado | Cualquier promoción automática |
| **X6** | Paquete del grafo frente a contexto ingenuo en las tareas de F1 | F1 hecha | Mismos aciertos con ≥ 30 % menos de tokens de prompt | Pérdida de aciertos |

Primero X1, X2 y X5: no necesitan modelo ni descargas y atacan los problemas medidos (inestabilidad y 41 minutos por
validación). Después X0 (F1) y, sobre sus resultados, X4, X6 y X3.

---

## 11. Preguntas abiertas

**Para el usuario:**
1. ¿Autorizas F1 (decisiones D1–D4 del plan)? Todo lo demás depende de ella.
2. Para X3, ¿autorizarías más adelante descargar un segundo modelo de 2–4 B de otra familia? Lo elegiría por
   licencia, por soporte en llama.cpp y por su SHA-256 publicado.
3. ¿Qué te importa más en una tarea: el tiempo total o la probabilidad de acierto? Determina el criterio cuando se
   enfrentan (por ejemplo, el crítico en la CPU).

**Para GPT-6:**
1. ¿Hay evidencia publicada y reproducible de que un crítico de otra familia, **más pequeño** que el autor, mejore la
   detección de errores frente a una autocrítica con instrucciones distintas? (No lo he comprobado con fuentes en
   este estudio [NO VERIF].)
2. ¿Ves alguna forma de que la caché de prefijos o las ranuras de llama.cpp filtren contenido entre peticiones con
   prompts distintos, más allá del diseño del propio prompt?
3. Para las relaciones «verificadas», ¿basta un HMAC con clave del anfitrión, o propones firmas asimétricas para
   poder verificar en otra máquina sin compartir la clave?
4. ¿Qué criterio propones para declarar una prueba «inestable» sin que se convierta en una forma de esconder
   regresiones?

---

## 12. Recomendación final

**No transformar todavía la arquitectura.** El sistema ya tiene, sin estrenar, buena parte de lo que se propone. El
mayor riesgo del proyecto hoy no es la falta de componentes, sino que **nada se ha medido con un modelo real**.

1. **Ahora, sin modelo:** X1 (inestables), X2 (huella por fase) y X5 (clases de relaciones con firma del anfitrión).
   Son deterministas y baratos, atacan problemas medidos y no aumentan la superficie de ataque.
2. **Después, F1 (X0)**, con la evaluación prerregistrada S1 / S1×3 / E3.
3. **Con los datos de F1:** X4 y X6 (tokens y caché) y, solo si E3 muestra valor, X3 para decidir el segundo modelo.
4. **Descartado:** el tercer modelo «de conocimiento», la fragmentación y compresión del intercambio, los vigilantes
   de archivos y las cachés por agente.
5. **Sin cambios:** la ejecución de código generado sigue bloqueada hasta F3 (aislamiento real con pruebas canario,
   medición del resultado desde el anfitrión y firma de las evidencias), y la batería integral sigue siendo
   obligatoria para cada entrega.

> Respuesta a la pregunta central: más rápido, **reutilizando de forma determinista** lo que no ha cambiado (pruebas,
> índice, caché KV); más independiente, **solo si un experimento lo demuestra**; más colaborativo, **midiendo** si el
> debate aporta frente a un agente con votación; y más seguro, **sin dejar que ningún modelo decida qué es verdad,
> qué se ejecuta ni qué se deja de probar**.
