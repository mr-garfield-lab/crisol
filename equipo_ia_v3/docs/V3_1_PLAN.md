# Equipo IA V3.1 — Diagnóstico, inventario de capacidades y plan de activación real en el PC

**Estado: PROPUESTA pendiente de aprobación** (2026-11-10). Hasta que se apruebe, no se hace ninguna modificación
importante. Lo único añadido es el diagnóstico de solo lectura del PC (§3.1), con sus pruebas.

**Punto de partida:** las Etapas 0–8 de V3 están cerradas. El verificador F0–F11 pasa 12 de 12 desde una
extracción limpia del ZIP (`evidencias/etapa8/`), y la línea base de V2-F.1 da IGUAL en 503 de 503 pruebas.

> **Honestidad sobre el alcance.**
> - Este documento se escribió en un contenedor Linux sin GPU, sin llama.cpp y sin modelos.
> - **No he podido inspeccionar el PC:** la sesión no tiene ninguna carpeta del equipo compartida
>   (`list_computer_folders` devolvió una lista vacía). Por eso NADA de lo que sigue afirma qué hay instalado en el
>   PC.
> - Las cifras de rendimiento son COTAS teóricas calculadas, no mediciones.

---

## 1. Diagnóstico

### 1.1 ¿Por qué A1, A2 y A3 siguen usando respuestas simuladas?

1. **En este entorno no hay con qué hacerlo real.** No hay GPU, llama-server ni ningún GGUF, y no tengo
   autorización para descargar modelos. Todas las ejecuciones usan backends de guion: `BackendGuionFuncion`
   (`sistema/src/eq2/demo_funcion.py:105`), `BackendSimulado` (`inferencia.py:73`) y `BackendGuion`
   (`banco_capacidades.py:90`).
2. **La vía real de V2-F.1 está pensada para el teléfono y nunca se ha validado.** `BackendLlama` +
   `servidor.Servidor` lanzan `llama-server` con unas condiciones fijas:
   - sin `-ngl`, es decir, solo CPU (`servidor.py:151-155`);
   - contexto de 1024 a 3072 (`config.CTX_PERMITIDOS`);
   - modelo fijo en `~/equipo-ia/modelos/qwen-coder-3b.gguf` (`config.ruta_modelo`).

   Las comprobaciones con Qwen real (V-QWEN) siguen pendientes de hacerse en el dispositivo.
3. **En Windows nativo, esa vía no arrancaría tal como está.** Lo he comprobado leyendo el código, no
   ejecutándolo:
   - `Servidor.comprobaciones()` lee `/proc/meminfo` (`vigilancia.leer_mem_available`). En Windows obtiene `None`
     y lo registra como un problema que bloquea el arranque.
   - `llama_activo()` recorre `/proc` para buscar procesos.
4. **No hay ejecución de código.** Aunque las respuestas fueran reales, el flujo termina siempre en «aceptada
   sin ejecución»: la ejecución dinámica está fijada a `bloqueada` (`funcion_supervisada.py:76`, SEG-01).

### 1.2 ¿Qué capacidades reales faltan para programar de forma autónoma?

| Falta | Por qué importa |
|---|---|
| Inferencia real en el PC (GPU, contexto de 4096 a 8192) | Sin ella no hay ninguna respuesta real de los agentes |
| Ejecución de pruebas en un aislamiento del sistema operativo | Es la única forma de saber si el código funciona. Hoy está bloqueada (SEG-01) |
| Bucle de corrección: fallo real → A1 corrige → se vuelve a ejecutar | Es la palanca principal de calidad sin tocar los pesos. No existe porque no hay ejecución |
| Contexto del código en los prompts (grafo) | Los agentes solo ven los archivos de la tarea, no el resto del proyecto |
| Experiencias VERIFICADAS reutilizables | Hoy la memoria solo contiene experiencias de ejecuciones simuladas |
| Tareas de más de una función o archivo, con división dinámica | El flujo cubre UNA función (como máximo 3 archivos y 24 KB) con un plan fijo (`PLAN_BASE`) |

### 1.3 Componentes de V3 implementados pero no conectados al flujo de los agentes

| Componente | Qué hace hoy | Qué falta para conectarlo |
|---|---|---|
| `eq3/traza` | Importa una ejecución DESPUÉS de que termine y la verifica | Registrar en vivo o importar al final de cada iteración del bucle |
| `eq3/grafo` (contexto) | Indexa y recupera mediante la CLI; se mide contra oráculos | Inyectar el paquete de contexto en los prompts de A1/A2 |
| `eq3/memoria` (individual con filtro, episódica y de proyecto) | Consultas por CLI y evaluación prerregistrada | Inyectarla en los prompts. V2-F.1 ya inyecta hasta 2 recuerdos por agente (`interfaces_codex.Componentes.memoria`) desde su propia base |
| `eq3/citas` | Contrasta las citas de A2/A3 DESPUÉS de la ejecución | Devolver las citas rechazadas como nota en la ronda siguiente |
| `eq3/cambios` | Propuesta → autorización → aplicación, a mano por CLI | Usarlo para pasar al proyecto real la solución ya verificada en el aislamiento |
| `eq3/perfiles_pc` | Calcula la orden de llama-server; no lanza nada | Usarlo para proponer al usuario la orden exacta |

**Punto de conexión sin tocar `sistema/`.** `FuncionSupervisada(...)` (`funcion_supervisada.py:458`) acepta
inyectados el backend, la memoria y los componentes.

- `interfaces_codex.Componentes(recuperador=, selector=, diagnostico=)` es el punto ÚNICO, y ya validado, por el
  que entran componentes externos.
- Así, V3.1 puede conectar el contexto y la memoria de eq3 sin modificar V2-F.1, con lo que F0 y la línea base
  siguen siendo válidas.

### 1.4 ¿Qué impide ejecutar tareas reales en aislamiento?

1. **SEG-01.** El ejecutor restringido de V2-F.1 (lista blanca de AST más un proceso hijo con límites) **se
   puede saltar**: no es un aislamiento del sistema operativo.
2. **Bloqueo deliberado en V2-F.1.** `config.MODO_B_HABILITADO = False`, y `EjecutorReal._ejecutar` no implementa
   la ejecución a propósito (`aislamiento.py:43-59`). Es correcto y no debe cambiarse.
3. **No hay aislamiento verificado en el PC.** No sé si hay Docker, WSL2 o Windows Sandbox; el diagnóstico del
   §3.1 lo dirá. Instalar o activar cualquiera de ellos requiere tu autorización.
4. **Sin comprobación empírica del aislamiento.** No basta con que exista Docker: hay que DEMOSTRAR, antes de cada
   sesión, que sin red, sin acceso a tus archivos y con límites de CPU, memoria y tiempo el código no puede
   escapar (§4).

### 1.5 Mejoras de inteligencia operativa SIN cambiar pesos

«Aprender de la experiencia» significa aquí GUARDAR y RECUPERAR información verificada para dársela al modelo
como contexto. **Los pesos del modelo no cambian en ningún caso**; no hay entrenamiento ni ajuste fino.

| Mejora | Efecto esperado (hay que medirlo) | Coste |
|---|---|---|
| Modelo de 7B y contexto de 8192 en la GPU (frente a 3B y 1024–3072 en la CPU del teléfono) | Mejor código y mejor revisión | Ninguno de código: solo la orden del servidor |
| Retroalimentación con las pruebas reales (salida del fallo saneada y truncada, como DATOS) | Corrección dirigida en lugar de a ciegas | Requiere el aislamiento |
| Contexto recuperado del grafo (firmas y dependencias relevantes) | Menos nombres inventados y menos módulos inexistentes | Bajo: el grafo ya existe |
| Experiencias verificadas (fallo → corrección → pruebas superadas) recuperadas en tareas parecidas | Menos iteraciones en errores repetidos | Bajo: la memoria y la traza ya existen |
| Citas rechazadas devueltas a A2/A3 | Menos afirmaciones sin respaldo | Bajo: `citas` ya existe |
| Varios candidatos de A1, elegidos por las pruebas (opcional) | Más tareas resueltas a la primera | Multiplica el tiempo de inferencia |
| Controlador determinista como único árbitro (ya existe) | Ningún agente se autoaprueba | — |

---

## 2. Inventario de capacidades

Estados:
- **IMPLEMENTADO:** código real, probado aquí.
- **SIMULADO:** solo funciona con agentes de guion.
- **EXPERIMENTAL:** implementado pero sin validar en el mundo real, o basado en estimaciones.
- **PENDIENTE:** no existe.

| Capacidad | Estado | Dónde | Nota |
|---|---|---|---|
| Flujo A1 → controlador → A2 → A3 → decisión determinista | IMPLEMENTADO (código) / SIMULADO (agentes) | `sistema/.../funcion_supervisada.py` | El resultado nunca es «verificado» sin ejecución |
| Respuestas de A1/A2/A3 con Qwen | EXPERIMENTAL | `backend_llama.py`, `servidor.py` | Código existente, nunca validado; pensado para Termux |
| Identidad y responsabilidades de cada agente | IMPLEMENTADO | `roles.py`, `funcion_supervisada.INSTR_FS` / `AGENTE_FS` | A1 genera y corrige, A2 revisa, A3 propone casos de prueba y critica |
| Análisis estático (`ast`, nombres, módulos, lista blanca) | IMPLEMENTADO | `analisis_estatico.py`, `analisis_controlador` | Real; no ejecuta nada |
| Debate y crítica (mejoras, problemas, «REBATIDA», decisión por ronda) | IMPLEMENTADO / SIMULADO | `decidir_ronda`, `leer_a2`, `leer_a3` | Lógica real; contenido de guion |
| Planificación y división de tareas | IMPLEMENTADO (plan fijo) | `PLAN_BASE` | La división dinámica está PENDIENTE |
| Ejecución de pruebas del código generado | PENDIENTE (bloqueada) | `EJECUCION_DINAMICA` | SEG-01 |
| Ejecutor restringido (lista blanca de AST) | EXPERIMENTAL, **no seguro** | `ejecutor_restringido.py` | SEG-01: se puede saltar. Es opcional en otros modos de V2-F.1 (`tareas.py` con autorización, `banco_capacidades.py`). No se usa en `funcion_supervisada`, y V3 no lo activa |
| Bucle de corrección con pruebas reales | PENDIENTE | — | V3.1 F4 |
| Memoria por agente de V2-F.1 (2 recuerdos en el prompt) | IMPLEMENTADO / SIMULADO | `experiencias.py`, `interfaces_codex.py` | Se alimenta de ejecuciones simuladas |
| Memoria de V3 (individual con filtro, episódica y de proyecto) | IMPLEMENTADO, no conectado | `eq3/memoria.py` | Léxica; con evaluación prerregistrada |
| Traza unificada con cadena de hashes | IMPLEMENTADO | `eq3/traza.py`, `almacen.py` | Importación posterior, no en vivo |
| Reconstrucción y verificación de una ejecución | IMPLEMENTADO | `eq3/reconstruccion.py` | Reglas R1–R6 |
| Índice de código y recuperación de contexto | IMPLEMENTADO, no conectado | `eq3/grafo.py` + Contexto Ligero | Medido contra oráculos y una referencia ingenua |
| Cambios controlados (propuesta → autorización → aplicación) | IMPLEMENTADO | `eq3/cambios.py` | Hash tecleado, caducidad, un solo uso, TOCTOU, escritura atómica |
| Verificación de citas | IMPLEMENTADO, posterior | `eq3/citas.py` | — |
| STOP | IMPLEMENTADO | `parar` en V2-F.1; `ingesta.comprobar_stop` | — |
| Planificador de recursos del PC | EXPERIMENTAL (estimaciones) | `eq3/perfiles_pc.py` | Recomienda el 7B entero en la GPU |
| Diagnóstico de solo lectura del PC | IMPLEMENTADO (aquí) / sin ejecutar en el PC | `diagnostico_pc.py` | Probado con GGUF SINTÉTICOS |
| Aislamiento del sistema operativo | PENDIENTE | — | V3.1 F3 |
| Experiencias verificadas y su transferencia | PENDIENTE | — | La tabla `experiencias` de la traza existe |
| Línea base, mutación y empaquetado | IMPLEMENTADO | `v3/` | 503 pruebas IGUAL; 74 + 12 mutaciones detectadas |
| Validación en Windows 11 | PENDIENTE | — | Requiere el PC |
| Validación en Android/Termux | PENDIENTE | — | Requiere el teléfono |

---

## 3. Preparación de las pruebas reales en Windows

### 3.1 Qué hay realmente en el PC: diagnóstico de solo lectura

No he podido comprobarlo. Para no suponer nada, `diagnostico_pc.py` (biblioteca estándar, Python 3.11 o
posterior) informa de:

- la edición de Windows;
- la CPU, los núcleos y la RAM;
- la GPU (`nvidia-smi --query-gpu`);
- Python;
- los ejecutables de llama.cpp;
- los GGUF (tamaño, y de la **cabecera**: arquitectura, capas, contexto y cabezas KV);
- WSL, Docker y Windows Sandbox (si la edición lo admite y si está activado).

```
python diagnostico_pc.py --buscar C:\ruta\a\modelos --buscar C:\ruta\a\llama.cpp --salida diagnostico.json
```

**Garantías, comprobadas por 9 pruebas y 12 mutaciones** (`pruebas/test_eq3_diagnostico.py`,
`v3/mutaciones/v31_diagnostico.json`):

- No instala, no descarga, no usa la red y no carga modelos.
- Solo mira las carpetas de `--buscar`, sin seguir enlaces ni uniones de directorio de Windows, y con un tope de
  entradas.
- **No ejecuta los programas que encuentra**, salvo que se pida con `--consultar-versiones`.
- No sobrescribe archivos.
- Oculta la carpeta personal (`~`) en las rutas.

### 3.2 Evaluación de modelos de 7B y 14B cuantizados

Tope de VRAM: `min(8192 − 1024 de reserva para Windows, 6144 del AI Lab Coordinator) = 6144 MiB`. El presupuesto
del coordinador se respeta y no se modifica.

| Modelo (GGUF Q4_K_M) | Capas en la GPU | VRAM / RAM estimadas | Cota teórica de generación* | Valoración |
|---|---|---|---|---|
| Qwen2.5-Coder-3B-Instruct (≈1,8 GiB) | 36 de 36 | 2520 / 1024 MiB | ≤ ~115 tokens/s | Rápido, pero calidad limitada; útil solo para comparar con el teléfono |
| **Qwen2.5-Coder-7B-Instruct (≈4,4 GiB)** | **28 de 28** | **5431 / 1024 MiB** | **≤ ~47 tokens/s** | **Recomendado.** Cabe entero en la GPU bajo el tope. Es el mejor equilibrio para un bucle de 3 agentes con varias rondas |
| Qwen2.5-Coder-14B-Instruct (≈8,4 GiB) | 25 de 48 (parcial) | 5992 / 5866 MiB | ≤ ~9 tokens/s | Mejor calidad esperada, pero unas 5 veces más lento según la cota, y el procesado del prompt en la CPU es lento. Solo como comparación medida |
| 7B en Q5_K_M (≈5,1 GiB) | 28 de 28 con contexto 4096 | ~5,9 GiB | ≤ ~41 tokens/s | Posible, pero al límite del tope: solo si las mediciones lo permiten |
| MoE de unos 30B (p. ej. Qwen3-Coder-30B-A3B) | Parcial | ≈18 GB de RAM (aproximado) | — | Descartado por ahora: ocuparía la mayor parte de los 32 GB y competiría con tus aplicaciones |

\* **Cómo se calcula la cota.** La generación de cada token lee todos los pesos.

- La RTX 3050 de 8 GB tiene unos 224 GB/s de ancho de banda.
- La DDR4 en doble canal da unos 51 GB/s si es DDR4-3200, lo que hay que confirmar.

La cota es `ancho de banda / bytes leídos por token`. Es un **techo, no una medición**: lo real será menor. Las
cifras de VRAM salen de `equipo3.py pc recomendar` (Etapa 6) y también son estimaciones.

**Recomendación.**
- UN solo servidor con el **7B Q4_K_M**, compartido por A1, A2 y A3 por turnos (`--parallel 1`, `127.0.0.1`).
- Nunca tres modelos a la vez.
- El 14B solo en un experimento posterior con las MISMAS tareas, de modo que se decida por medición y no por
  suposición.

**Qué podría hacer falta instalar.** Lo confirmará el diagnóstico, y nada se instala sin tu autorización:
- llama.cpp compilado con CUDA para Windows o para WSL2;
- el GGUF elegido;
- el aislamiento del §4.

### 3.3 Windows nativo frente a WSL2

| | Windows nativo | WSL2 (Ubuntu) |
|---|---|---|
| llama-server con CUDA | Sí (compilación de Windows) | Sí (CUDA sobre WSL) |
| V2-F.1 tal cual | No: lee `/proc` | Sí: es Linux |
| Aislamiento para SEG-01 | Docker Desktop (que usa WSL2) o Windows Sandbox (solo en Pro) | bubblewrap o Docker dentro de WSL2 |
| Adaptaciones necesarias | Lector de memoria de Windows y adaptador de servidor | Ninguna para V2-F.1 |

Propuesta: **elegir después de ver el diagnóstico**. Si WSL2 ya está instalado, es el camino con menos código
nuevo. En cualquiera de los dos casos, el servidor puede lanzarlo TÚ con la orden que propone `perfiles_pc`, y
Equipo IA se conecta a él (F1). Así, Equipo IA nunca lanza ni cierra procesos tuyos.

---

## 4. Seguridad: SEG-01 antes de cualquier ejecución autónoma

**Regla.** El código generado solo se ejecuta si se cumplen las tres condiciones siguientes. Si falta cualquiera,
la ejecución sigue DESHABILITADA y el resultado sigue siendo «aceptada sin ejecución».

1. **Aislamiento del sistema operativo** con estas propiedades:
   - sin red;
   - sin acceso a tus archivos: solo una COPIA del espacio de la tarea;
   - usuario sin privilegios;
   - límites de CPU, memoria, número de procesos y tiempo;
   - sistema de archivos de solo lectura, salvo el espacio de trabajo.
2. **Comprobación empírica antes de cada sesión.** Una batería de pruebas canario dentro del aislamiento debe dar
   todo bloqueado:
   - abrir una conexión de red;
   - leer un archivo canario del anfitrión;
   - escribir fuera del espacio;
   - superar el límite de memoria y el de procesos;
   - superar el tiempo.

   Si una sola no se bloquea, no se ejecuta nada y la sesión queda como FALLIDA en la traza.
3. **Autorización por tarea.** Autorizas una tarea con sus límites (iteraciones, tiempo y CPU), ligada a su
   hash. Hay STOP en todo momento, y cada ejecución queda en la traza con su salida.

**Autonomía acotada.** Dentro del aislamiento, los agentes iteran solos sobre una COPIA. Pasar la solución a un
proyecto real sigue exigiendo `cambios`: propuesta, tu autorización con el hash tecleado y aplicación. Se
mantiene la separación entre propuesta, autorización y ejecución.

**Opciones de aislamiento, por orden de preferencia.** Cualquiera exige tu autorización para instalarla o
activarla.

| Opción | Cómo | Valoración |
|---|---|---|
| (a) Docker | `--network none --read-only --cap-drop ALL --security-opt no-new-privileges --user 65534 --memory --cpus --pids-limit`, con el espacio de trabajo montado y una imagen de Python ya descargada | La más sólida |
| (b) bubblewrap dentro de WSL2 | `--unshare-all` y montajes mínimos | Ligera |
| (c) Windows Sandbox | Solo en Windows Pro | Pesada: arranca una máquina virtual y no trae Python |
| (d) Mantener la ejecución deshabilitada | — | — |

---

## 5. Plan de V3.1

**Principios.**
- `sistema/` (V2-F.1) NO se modifica: se conecta mediante sus puntos de inyección. F0 y la línea base siguen
  siendo la prueba de que no hay regresiones.
- Un solo modelo compartido; cada agente conserva su tarjeta de rol, su prompt, su memoria individual y sus
  responsabilidades.
- Se reutiliza lo que ya existe (eq2, traza, grafo, memoria, citas, cambios, perfiles_pc). Solo se añaden
  módulos donde no hay nada que reutilizar.

Cada fase se cierra con:
- pruebas y mutaciones;
- una fase en el verificador;
- `PROGRESO.md` y un commit local.

**Tú apruebas cada fase antes de empezarla.**

| Fase | Qué | Reutiliza / añade | Criterio de aceptación | Naturaleza de la prueba |
|---|---|---|---|---|
| **F0** (hecha) | Diagnóstico de solo lectura del PC | Añade `diagnostico_pc.py` | 9 pruebas y 12 de 12 mutaciones | REAL aquí con GGUF sintéticos; falta ejecutarlo en el PC |
| **F1** | Inferencia real: conectar `BackendLlama` a un llama-server que lanzas tú (`127.0.0.1`, comprobando `/health` y `/props`), sin lanzar ni cerrar procesos. Ejecutar `FuncionSupervisada` con agentes REALES; la ejecución sigue bloqueada | Reutiliza BackendLlama, FuncionSupervisada, traza y perfiles_pc. Añade el adaptador `eq3/servidor_pc.py` | Aquí, pruebas con un servidor HTTP falso en `127.0.0.1`. **En el PC**: 3 tareas prerregistradas con respuestas reales, una traza verificada, `backend.simulado = False` y el modelo identificado por SHA-256 y `/props` | SIMULADO aquí / **REAL en el PC** |
| **F2** | Contexto y memoria en los prompts mediante `Componentes(recuperador=…)`: paquete del grafo más la memoria individual y de proyecto, dentro del presupuesto de bytes | Reutiliza grafo, memoria e interfaces_codex. Añade `eq3/componentes_v31.py` | Pruebas deterministas y mutaciones. **En el PC**: comparación con y sin contexto sobre las mismas tareas | REAL en el PC |
| **F3** | Aislamiento (SEG-01): proveedor de aislamiento con las pruebas canario del §4; si alguna falla, la ejecución queda bloqueada | Añade `eq3/aislamiento_pc.py` | Aquí, la lógica con proveedores falsos (incluido uno que «deja escapar» y debe bloquearse). **En el PC**: todas las canario bloqueadas | SIMULADO aquí / **REAL en el PC** |
| **F4** | Bucle de corrección: pruebas OCULTAS más los casos que ya propone A3 (`fs_casos`), en el aislamiento → fallo saneado como DATOS → nueva ronda (A1 corrige; A2/A3 revisan; el controlador decide), hasta N iteraciones con STOP. «Verificada» solo si pasan las pruebas ocultas | Reutiliza FuncionSupervisada por iteración y citas como retroalimentación. Añade `eq3/ciclo.py` | **En el PC**: al menos un ciclo trazado completo (fallo → corrección → aprobado) | **REAL en el PC** |
| **F5** | Experiencias verificadas: guardar (tarea, fallo, corrección, prueba superada) como lección VERIFICADA; los intentos fallidos quedan como hipótesis y no se recuperan por defecto. Transferencia: individual por agente y compartida por proyecto | Reutiliza la tabla `experiencias` de la traza y `memoria` | **En el PC**: pares de tareas parecidas, con experiencias y sin ellas, más un control negativo con experiencias irrelevantes | **REAL en el PC** |
| **F6** | Orden de evidencias para Windows: ejecuta el banco de tareas y recoge el paquete de evidencias en un ZIP | Reutiliza empaquetar y verificar_v3. Añade `pc_evidencia.py` | Paquete reproducible y verificable | REAL en el PC |

**Banco de tareas prerregistrado** (se fija con su SHA-256 ANTES de la primera ejecución real):

- unas 12 tareas pequeñas de Python con **pruebas ocultas** que los agentes no ven;
- 4 de ellas con casos límite pensados para provocar un fallo y su corrección;
- 4 pares de tareas parecidas para medir la reutilización.

**Qué se informará:**
- tareas resueltas a la primera y tras N iteraciones;
- iteraciones, tokens y tiempo;
- todo con recuentos en bruto: con tan pocas tareas no se afirmará significación estadística.

**Evidencia «real» mínima por capacidad.** Una capacidad se considera DEMOSTRADA solo con al menos un caso
trazado y reproducible en el PC, que conste de:

- identidad del modelo (SHA-256 del GGUF, `/props` y versión de llama-server);
- traza con la cadena verificada;
- resultado de las pruebas canario;
- salida de las pruebas ocultas;
- diferencias entre versiones.

Lo que falle se informará como FALLIDO, sin cambiar los criterios.

**Qué NO incluye V3.1:**
- entrenamiento o ajuste de pesos;
- varios modelos simultáneos;
- integración con AI Lab Coordinator;
- cambios en `sistema/`;
- ejecución sin aislamiento demostrado;
- ningún cambio en GameAgentEngine, AURORA ni ATLAS.

---

## 6. Decisiones que necesito de ti

1. **Aprobación del plan** (todo, o fase por fase).
2. **Acceso al PC, eligiendo una de estas formas:**
   - ejecutas tú `diagnostico_pc.py` y me pasas `diagnostico.json`, revisado antes por ti;
   - compartes una carpeta de Equipo IA desde la app de escritorio de Claude (Configuración → Claude Code →
     Remote Control). Esta función puede no estar disponible en todas las cuentas.
3. **Modelo:** 7B Q4_K_M (recomendado), o la comparación de 7B con 14B en la F5.
4. **Aislamiento:** Docker, bubblewrap en WSL2, Windows Sandbox, o mantener la ejecución deshabilitada. Si hay
   que instalar algo, necesito tu autorización explícita.
5. **Contexto inicial:** 3072 (lo admite V2-F.1 sin cambios) u 8192 (requiere una sustitución explícita y trazada
   en eq3).
   - Nota: con cualquiera de los dos, V2-F.1 limita la RESPUESTA de cada paso a unos 560 tokens como máximo
     (`TOKENS_FS`, `config.TOPE_MAX_TOKENS`).
   - Un contexto mayor da más espacio de ENTRADA (código, contexto y memoria), no respuestas más largas.
