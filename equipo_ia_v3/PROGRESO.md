# Equipo IA V3 — PROGRESO

**Autorización vigente (usuario, 2026-11-10).** Desarrollo autónomo por etapas, en el orden de la orden
maestra. Se avanza sin esperar confirmación solo si la etapa cumple sus criterios de aceptación.

- **Git:** SOLO commits locales con archivos de Equipo IA. No se publica en GitHub ni se hacen operaciones
  remotas nuevas.
- **Fuera de alcance:** GameAgentEngine, AURORA, ATLAS y AI Lab Coordinator.

| Etapa | Estado | Documento | Commit local |
|---|---|---|---|
| 0. Auditoría y línea base | **Cerrada** | [`docs/ETAPA0_AUDITORIA.md`](docs/ETAPA0_AUDITORIA.md) | `c29134d` |
| 1. Núcleo, trazabilidad y calidad | **Cerrada** (F0–F5 correctas) | [`docs/ETAPA1_TRAZA.md`](docs/ETAPA1_TRAZA.md) | ver `git log` |
| 2. Grafo y contexto | **Cerrada** (F0–F7 correctas) | [`docs/ETAPA2_GRAFO.md`](docs/ETAPA2_GRAFO.md) | commit conjunto 2+3 |
| 3. Programación controlada | **Cerrada** (F0–F7 correctas) | [`docs/ETAPA3_PROGRAMACION.md`](docs/ETAPA3_PROGRAMACION.md) | commit conjunto 2+3 |
| 4. Debate, planificación y coordinación | **Cerrada** (F0–F8 correctas) | [`docs/ETAPA4_COORDINACION.md`](docs/ETAPA4_COORDINACION.md) | commit de la E4 |
| 5. Memoria y aprendizaje | **Cerrada** (F0–F9 correctas) | [`docs/ETAPA5_MEMORIA.md`](docs/ETAPA5_MEMORIA.md) | commit de la E5 |
| 6. Optimización PC | **Cerrada** (ESTIMACIONES; F0–F11 correctas) | [`docs/ETAPA6_PC.md`](docs/ETAPA6_PC.md) | commit E6+E7 |
| 7. Auditoría integral | **Cerrada** (AUD-01 a AUD-04 corregidos) | [`docs/ETAPA7_AUDITORIA.md`](docs/ETAPA7_AUDITORIA.md) | commit E6+E7 |
| 8. Paquete | **Cerrada**: el ZIP extraído en limpio pasa F0–F11 | [`docs/ETAPA8_PAQUETE.md`](docs/ETAPA8_PAQUETE.md) | commit de cierre |

### V3.1 — F0.5 portabilidad a Windows (2026-11-10)

| Fase V3.1 | Estado | Documento |
|---|---|---|
| F0.5 portabilidad (Windows nativo principal) | **Cerrada en Windows (2026-11-11)**: `verificar_v3.py --completo` 14/14; F11 503 IGUAL, 0 bloqueantes; V-SRV-12/V-UNI-23 corregidos con adaptador autorizado (§10 del informe) | [`docs/V31_F05_INFORME_FINAL.md`](docs/V31_F05_INFORME_FINAL.md) |
| Mantenimiento previo a F1 (2026-11-11) | **Cerrado**: `--reanudar`, rutas personales en el empaquetado, Git local, propuesta de `majflt`. `--completo` final 15/15 de una vez (un intento anterior falló por V-CON-11, prueba inestable: defecto ABIERTO) | [`docs/V31_MANTENIMIENTO.md`](docs/V31_MANTENIMIENTO.md) |
| F1–F6 (modelo local, contexto, aislamiento, ciclos, experiencias, evaluación) | **Pendientes de aprobación** (decisiones D1–D4) | [`docs/V31_PLAN_ACTIVACION_F1.md`](docs/V31_PLAN_ACTIVACION_F1.md), [`docs/V3_1_PLAN.md`](docs/V3_1_PLAN.md) |
| V3.2 (multicerebro, grafo reactivo…) | **Solo estudio**, sin implementar | [`docs/V32_ESTUDIO_DEBATE.md`](docs/V32_ESTUDIO_DEBATE.md) |

- `sistema/` sigue sin cambios. Los adaptadores de plataforma están en `eq3/plataforma.py` y `eq3/lanzador_eq2.py`.
- Linux/WSL2 y Termux **no se han vuelto a ejecutar con V3.1**.
- **Git local** desde el 2026-11-11 (sin remotos; ver `docs/V31_GIT_LOCAL.md`): `main` = cierre de F0.5; trabajo en
  `mantenimiento-v31`.
- **Defecto abierto:** V-CON-11 es inestable en Windows (compara dos lecturas de memoria real); ver
  `evidencias/v31_mantenimiento/V-CON-11_inestabilidad_30_ejecuciones.md`.

### Estado final de V3 (2026-11-10)

- **Etapas:** las 0–8 están cerradas, con commits locales; no se publicó nada desde `99f27be`, como pidió el
  usuario.
- **Pruebas y mutaciones:** 95 pruebas propias y 74 mutaciones, todas detectadas.
- **Línea base:** la de V2-F.1 da IGUAL 503 de 503.
- **Entrega:** `dist/equipo_ia_v3_<commit>/EquipoIA_V3.zip`, más su `.sha256` (ver `docs/ETAPA8_PAQUETE.md`).
- **Pendiente** (necesita al usuario o su hardware): validar con Qwen real, en Termux y en Windows; los ZIP
  originales para el material omitido; y SEG-01. Ver las recomendaciones en `docs/ETAPA8_PAQUETE.md` §5.

## Estructura

| Ruta | Contenido |
|---|---|
| `sistema/` | Copia íntegra de `fuentes/claude_v2f1` (Equipo IA V2-F.1, `eq2`). No se modifica; faltan 71 archivos de su manifiesto, omitidos en la importación |
| `eq3/` | Capa V3:<br>- `almacen.py`: base SQLite de solo añadir con cadena de hashes<br>- `traza.py`, `ingesta.py`, `reconstruccion.py`, `registro.py` (E1)<br>- `grafo.py` (E2)<br>- `cambios.py` (E3)<br>- `citas.py` (E4) |
| `contexto_ligero/`, `complementos_codex/` | Copias IDÉNTICAS de componentes reutilizados (Contexto Ligero V3.5 y complementos de Codex), con su `ORIGEN_SHA256.json` |
| `equipo3.py` | CLI de V3: `traza …`, `grafo …` y `cambios …` (autorizar es solo para el usuario) |
| `verificar_v3.py` | Verificador integral: F0 integridad, F1–F2 pruebas, F3–F6 mutaciones por etapa; línea base completa con `--completo` |
| `pruebas/` | Pruebas de eq3 (`comun.py` genera las demos de V2-F.1) |
| `v3/` | Línea base y puerta de regresión (`linea_base.py`, `corredor_unittest.py`, `linea_base_esperada.json`), pruebas de mutación (`mutacion.py`, `mutaciones/etapaN.json`) y sus pruebas (`tests/`) |
| `docs/`, `evidencias/` | Informes por etapa y evidencias (cada carpeta tiene su `LEEME.md`) |

## Órdenes (desde `equipo_ia_v3/`)

```sh
python3 -B verificar_v3.py --completo     # TODO: integridad, pruebas, mutaciones y línea base (~12 min en Linux)
python3 -B verificar_v3.py                # sin la línea base completa (~4 min)
python3 -B v3/linea_base.py               # solo la puerta de regresión: 0 = igual que la línea base
python3 -B equipo3.py traza --help        # traza unificada (E1)
python3 -B equipo3.py grafo --help        # índice de código, contexto y grafo de tareas (E2)
python3 -B equipo3.py cambios --help      # propuesta → autorización del usuario → aplicación (E3)
```

## Resultados

### Etapa 0 (detalle en su informe)

- **Línea base:** 503 pruebas (verificador 264, codex 37, contexto 202). Las 41 que no están OK tienen causa
  explícita: material omitido (31), Qwen real (5), tokenizers (4) y sin entrada externa (1).
- **Reproducibilidad:** A = B en 503 de 503.
- **La puerta no oculta fallos:** mutaciones 5 de 5 y ejecución C sobre `sistema/` mutado (17 REGRESION y
  7 CAMBIO).
- **Seguridad:** SEG-01, la lista blanca AST se puede saltar; la ejecución de código generado sigue
  DESHABILITADA.

### Etapa 1 (detalle en su informe)

- **Traza:** traza unificada con reconstrucción verificable de ejecuciones reales de V2-F.1 (agentes
  SIMULADOS).
- **Pruebas y mutación:** 23 de 23 pruebas; 12 de 12 mutaciones detectadas.
- **Verificador integral:** F0–F5 correctas. La propia puerta encontró y permitió corregir un defecto de la herramienta de la Etapa 0, con la línea base intacta.

### Naturaleza de lo verificado

- **Con Qwen real:** NADA. No hay GGUF ni llama-server en este entorno, ni autorización para descargarlos.
- **Agentes:** todas las ejecuciones de A1/A2/A3 usan el backend SIMULADO de V2-F.1 (guion o servidor falso).
- **Código:** el de V2-F.1 y el de V3 se ejecutan de verdad (REAL), en Linux. No se ha probado en Android/Termux
  ni en Windows.

## Bloqueos y limitaciones abiertos

1. **Material omitido:** 25 comprobaciones del verificador, 1 prueba de codex y 5 de Contexto Ligero dependen
   de él. Solo se recuperan con los ZIP originales (p. ej. `equipo_f2_v2f1.zip`, SHA-256 `11fc0837…`).
2. **Plataformas:** Qwen real, Android/Termux y Windows 11 requieren validación del usuario en cada plataforma.
3. **Dependencia opcional:** `tokenizers` no está instalada, y instalar software no está autorizado.
4. **Limitaciones de la Etapa 1:** ver su §7 (ingesta posterior, solo `funcion_supervisada`, autorización
   completa en la Etapa 3).

## Cómo continuar si se pierde el contexto

### Restricciones vigentes

- **Solo Equipo IA (A1/A2/A3).** GameAgentEngine es un proyecto aparte y no se toca:
  - no se modifica, mueve, borra ni publica;
  - no se incluye en commits ni se altera su configuración;
  - no se reutiliza su código.

  Si el hook de parada señala `GameAgentEngine/` o pide «push», se informa del aviso y no se hace nada más.
- **Otros proyectos:** tampoco se tocan AURORA, ATLAS ni AI Lab Coordinator; no se modifica el presupuesto de
  6144 MiB ni se integran proyectos.
- **Git:** no publicar, no ejecutar operaciones remotas, no modificar `main` ni fusionar, y no abrir pull
  requests. Solo commits LOCALES con `git add -- equipo_ia_v3/...` explícito.
- **Prohibido:** usar APIs de pago, instalar o descargar software o modelos, acceder a archivos personales,
  ejecutar código generado sin aislamiento (SEG-01), interferir con otras aplicaciones y agotar los recursos de
  la máquina.
- **Honestidad:** distinguir REAL, SIMULADO, OMITIDO y FALLIDO; no afirmar entrenamiento ni cambios de pesos;
  no ocultar fallos ni rebajar criterios.

### Al cerrar cada etapa

1. Ejecutar `python3 -B verificar_v3.py --completo`, que debe dar CORRECTO.
2. Añadir sus mutaciones en `v3/mutaciones/etapaN.json` y su fase en `verificar_v3.py`.
3. Revisar duplicación y deuda técnica.
4. Escribir `docs/ETAPAN_*.md`.
5. Actualizar este archivo.
6. Hacer un commit local.

### Estado de Git

Rama `experimental/equipo-ia-v3`, creada desde `main` @ `1241ff9`.

- **Publicados** (antes de la instrucción de no publicar): `c438cda`, `3e135b3` y `99f27be`.
- **Solo locales:** `c29134d` (cierre de la Etapa 0) y los posteriores.

### Diseño previsto de las etapas 3–8 (cada una con pruebas, mutaciones y una fase del verificador)

**Etapa 3, programación controlada.** Herramientas tipadas para proyectos Python del laboratorio, con un
registro congelado del mismo diseño que `eq2.herramientas` (`MappingProxyType`, `huella_registro`):

- **Herramientas:** `leer`, `listar`, `buscar` (grafo) y `proponer_parche`. La propuesta guarda el SHA-256 de antes
  y de después, el diff y el análisis estático de `eq2.analisis_estatico`.
- **Autorización:** la concede SOLO el usuario por la CLI. Es de un solo uso, caduca y se limita al hash de la
  propuesta y al archivo.
- **Aplicación:** la hace el controlador, no el agente. Exige una autorización válida y que el archivo siga con
  su SHA de antes (contra el TOCTOU); escribe de forma atómica y deja todo en la traza.
- **Ejecución de pruebas:** sigue «no_disponible» (SEG-01).
- **Demostración:** llevar la versión recomendada de una ejecución a un proyecto del laboratorio pasando por
  propuesta, autorización y aplicación, con toda la cadena verificable.

**Etapa 4, coordinación.** Un verificador de CITAS: las afirmaciones de A1/A2/A3 sobre el código
(archivo:línea, símbolo) se contrastan con el índice y con el archivo real, y las inventadas se rechazan. A1 y
A2 reciben paquetes de contexto del grafo, con presupuesto de tokens.

**Etapa 5, memoria.** Recuperación de experiencias pasadas (traza y aprendizaje) para una tarea nueva. Se mide
la precisión de lo recuperado frente a etiquetas, con y sin memoria; es una medida del MECANISMO, no del
modelo, y no se afirma ningún cambio de pesos.

**Etapa 6, PC.** Perfiles de llama-server como datos (contexto, capas en GPU, hilos) para el Ryzen 5 5600,
32 GB y RTX 3050 8 GB, con un validador de límites (VRAM, RAM, un solo modelo compartido por turnos). Sin
modificar el presupuesto de 6144 MiB del AI Lab Coordinator. NO VALIDADO en el PC real.

**Etapa 7, auditoría integral.** Revisión de seguridad de todo V3; verificador completo y todas las mutaciones.

**Etapa 8, paquete.** ZIP con manifiesto y SHA-256; guías para Windows y Android/Termux; inventario de
funciones con su naturaleza (REAL o SIMULADA); limitaciones.

### Siguiente paso

**Etapa 2, grafo y contexto:** reutilizar Contexto Ligero (`fuentes/contexto_ligero_v35`: índice, dependencias y
paquetes de contexto) mediante un adaptador de solo lectura. Hay que:

- indexar `sistema/src`;
- construir el grafo de dependencias y el de tareas y decisiones a partir de la traza;
- hacer recuperación contextual con actualización incremental e invalidación;
- medir la recuperación en tareas reales.

API real comprobada en `contexto_core/`:

| Módulo | Funciones |
|---|---|
| `index` | `connect`, `scan(root, db)`, `search` y `edge`; tablas `tasks`, `edges`, `decisions` y `code_edges` |
| `dependencies` | `dependency_plan(db, seeds)` |
| `retrieval` | `retrieve_detailed(db, query)` |
| `context` | `packet(root, db, q, budget)` |
| `delta` | `create_snapshot`, `make_delta` y `apply_delta(..., expected_base_sha256)` |

Para medir sin oráculos propios: `benchmarks/tasks_v35_reales.json` (y los demás `tasks_*.json`) contiene
consultas sobre `src/eq2` con los archivos y símbolos relevantes declarados ANTES del benchmark
(`declared_before_benchmark`). Se aplican a `sistema/src` (V2-F.1), conservando solo los símbolos que existen.
