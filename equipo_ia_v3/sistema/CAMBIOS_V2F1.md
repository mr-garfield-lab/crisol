# Cambios de V2-F.1 frente a V2-F

**Base:** el ZIP de V2-F que adjuntó el usuario (SHA-256 `ee73af5702e1d627707c8d289da0ca5e0126eba6bf34500f697f77676ee1e146`).
- Sus 271 archivos coinciden con su manifiesto, copiado en `herramientas/manifiesto_v2f.txt`.
- El detalle está en `LEEME_V2F1.md`.

| Cambio | Archivos |
|---|---|
| Tipo de tarea `funcion_supervisada`. A1 escribe, el controlador analiza sin ejecutar (EV1–EV7), A2 revisa, A3 propone casos y evalúa, la decisión es por evidencia (`decidir_ronda`), se corrige con límites, hay pruebas pendientes NO ejecutadas e informe verificable. Ejecución dinámica bloqueada | `src/eq2/funcion_supervisada.py` (nuevo) |
| Interfaces para los módulos de Codex (memoria, selector, diagnóstico): contratos, adaptadores por defecto, validación y conformidad | `src/eq2/interfaces_codex.py` (nuevo), `INTERFACES_CODEX.md` (nuevo) |
| Demostración SIMULADA (backend de guion que recibe los prompts reales) con tres escenarios | `src/eq2/demo_funcion.py` (nuevo) |
| Tareas: tipo `funcion_supervisada` y clave `funcion` (solo en ese tipo; las demás tareas no cambian), `_ejecutar_funcion`, `componentes_codex` y agentes según el tipo | `src/eq2/tareas.py` |
| CLI: `equipo.py demo funcion [--escenario …]`; código de salida y aviso de las tareas `funcion_supervisada` | `equipo.py` |
| Bloques de código que **conservan la indentación**, opcionales y compatibles hacia atrás. `contexto.Bloque(..., codigo=True)` y `sanea.envolver_codigo`; un bloque del motor admite un 4.º elemento. `AgentesMotorLLM.ultimo_prompt` registra los bloques omitidos y recortados. Los flujos de V2-F no cambian | `src/eq2/contexto.py`, `src/eq2/sanea.py`, `src/eq2/motor.py` |
| Límite de tiempo del flujo nuevo (`FS_SEG_TOTAL`), versión `f2-v2f1` y carpeta `lab_v2f1`; `lab_v2f` protegida | `src/eq2/config.py`, `src/eq2/__init__.py` |
| Docstring: nombre de la carpeta de datos | `src/eq2/experiencias.py` |
| Ejemplos de la demostración | `ejemplos/tarea_funcion_demo.json` (nuevo), `ejemplos/tarea_funcion_falta_info.json` (nuevo) |
| Verificador: fase FUN, V-FUN-01 (demostración simulada reproducible), V-QWEN-05 (demostración con Qwen real), tres demostraciones nuevas, estructura y diferencias frente a V2-F | `verificar.py`, `VERIFICADOR.md` |
| Pruebas nuevas | `tests/test_v2f1_funcion.py` (nuevo), `tests/test_v2f1_codex.py` (nuevo) |
| Invariante del hallazgo C (V2-E.6-r3; ampliado en V2-F). Lectores nuevos de la memoria: `interfaces_codex` (recupera) y `funcion_supervisada` (usa el texto). Una comprobación ESTÁTICA nueva (`_v2f1_solo_prompt`) exige que lo recuperado solo se devuelva como texto y llegue únicamente como `experiencias=` a una llamada a un agente, que lo pone en un bloque del prompt. Ningún módulo de permisos importa `interfaces_codex` ni `funcion_supervisada`. Prueba de mutación hecha a mano: si el texto recuperado decide la autorización, la prueba falla. Además, una prueba de conducta: mismas decisiones con y sin una memoria engañosa que sí llega al prompt. **Requiere revisión de GPT-6** | `tests/test_v2e6r3_indirecta.py`, `tests/test_v2f1_funcion.py` |
| Pruebas de interrupción deterministas, portadas de V2-E.9-r2: disparo por el ESTADO del registro del servidor falso, no por temporizador; pruebas separadas de arranque y de petición; SIGKILL. Solo cambian las pruebas | `tests/_v2.py`, `tests/test_v2_backend.py`, `tests/test_v2b.py` |
| La reproducibilidad del paquete de ejemplo dependía de la zlib de cada Python. Ahora: mismo SHA al construir dos veces en el mismo entorno, y mismo contenido que el incluido | `tests/test_v2e5r3.py` |
| Paquetes de ejemplo compatibles con `f2-v2f1`, regenerados | `auditoria_ejemplo/fuente/manifiesto.json`, `auditoria_ejemplo/auditoria_ejemplo.zip`, `retos/zomboid_v1/paquete_desafio/fuente/manifiesto.json`, `retos/zomboid_v1/paquete_desafio/desafio_zomboid_v1.zip` |
| Tabla de cumplimiento: requisitos R-V2F1-* | `cumplimiento.json` |
| Solo el nombre de la carpeta de datos (`lab_v2f` → `lab_v2f1`) en textos de ayuda y en pruebas heredadas (marcadas `# CAMBIO V2-F.1`) | `aprender.py`, `auditar.py`, `banco.py`, `ejecutar_v2.py`, `perfiles.py`, `retos.py`, `supervisar.py`, `herramientas/tabla_cumplimiento.py`, `tests/test_v2d.py`, `tests/test_v2e.py`, `tests/test_v2e2.py`, `tests/test_v2e3.py`, `tests/test_v2e4.py`, `tests/test_v2e4r2.py`, `tests/test_v2e5.py`, `tests/test_v2e5r2.py`, `tests/test_v2e6_aprendizaje.py`, `tests/test_v2e6_retos.py`, `tests/test_v2f_banco.py`, `tests/test_v2f_debate.py`, `tests/test_v2f_motor.py`, `tests/test_verificador.py` |
| Documentos | `LEEME_V2F1.md` (nuevo), `CAMBIOS_V2F1.md` (nuevo), `LEEME.md` (aviso de versión); listas de archivos regeneradas en `CAMBIOS_V2E6.md`, `CAMBIOS_V2E6R2.md`, `CAMBIOS_V2E6R3.md`, `CAMBIOS_V2E7.md`, `CAMBIOS_V2E7R2.md`, `CAMBIOS_V2E7R3.md` y `CAMBIOS_V2F.md` (sin otro cambio) |
| Evidencias: las de V2-F se conservan, sin cambios, en `evidencias_claude/v2f/`; las de V2-F.1 son nuevas | `evidencias_claude/` |

## Archivos

<!-- LISTA_DE_ARCHIVOS: generada por herramientas/lista_cambios.py -->

Nuevos (11):

- `CAMBIOS_V2F1.md`
- `INTERFACES_CODEX.md`
- `LEEME_V2F1.md`
- `ejemplos/tarea_funcion_demo.json`
- `ejemplos/tarea_funcion_falta_info.json`
- `herramientas/manifiesto_v2f.txt`
- `src/eq2/demo_funcion.py`
- `src/eq2/funcion_supervisada.py`
- `src/eq2/interfaces_codex.py`
- `tests/test_v2f1_codex.py`
- `tests/test_v2f1_funcion.py`

Cambiados (50):

- `CAMBIOS_V2E6.md`
- `CAMBIOS_V2E6R2.md`
- `CAMBIOS_V2E6R3.md`
- `CAMBIOS_V2E7.md`
- `CAMBIOS_V2E7R2.md`
- `CAMBIOS_V2E7R3.md`
- `CAMBIOS_V2F.md`
- `LEEME.md`
- `VERIFICADOR.md`
- `aprender.py`
- `auditar.py`
- `auditoria_ejemplo/auditoria_ejemplo.zip`
- `auditoria_ejemplo/fuente/manifiesto.json`
- `banco.py`
- `cumplimiento.json`
- `ejecutar_v2.py`
- `equipo.py`
- `herramientas/tabla_cumplimiento.py`
- `perfiles.py`
- `retos.py`
- `retos/zomboid_v1/paquete_desafio/desafio_zomboid_v1.zip`
- `retos/zomboid_v1/paquete_desafio/fuente/manifiesto.json`
- `src/eq2/__init__.py`
- `src/eq2/config.py`
- `src/eq2/contexto.py`
- `src/eq2/experiencias.py`
- `src/eq2/motor.py`
- `src/eq2/sanea.py`
- `src/eq2/tareas.py`
- `supervisar.py`
- `tests/_v2.py`
- `tests/test_v2_backend.py`
- `tests/test_v2b.py`
- `tests/test_v2d.py`
- `tests/test_v2e.py`
- `tests/test_v2e2.py`
- `tests/test_v2e3.py`
- `tests/test_v2e4.py`
- `tests/test_v2e4r2.py`
- `tests/test_v2e5.py`
- `tests/test_v2e5r2.py`
- `tests/test_v2e5r3.py`
- `tests/test_v2e6_aprendizaje.py`
- `tests/test_v2e6_retos.py`
- `tests/test_v2e6r3_indirecta.py`
- `tests/test_v2f_banco.py`
- `tests/test_v2f_debate.py`
- `tests/test_v2f_motor.py`
- `tests/test_verificador.py`
- `verificar.py`

Quitados (0):

- ninguno

Sin cambios: 182.
