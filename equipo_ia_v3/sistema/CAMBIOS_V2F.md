# Cambios de V2-F frente a V2-E.7-r3

**Base:** copia de V2-E.7-r3 recibida dentro de `CONTEXTO_LIGERO_V3_4_DESCARGA.zip`, en `referencia_original/equipo_ia_referencia/`.
- 216 archivos coinciden byte a byte con su `MANIFIESTO_SHA256.txt`, que se copió en `herramientas/manifiesto_v2e7r3.txt`.
- Faltaban 5 archivos (ver `LEEME_V2F.md` §7).

El detalle está en `LEEME_V2F.md`.

| Cambio | Archivos |
|---|---|
| Casos literales ejecutables (sin inyección), ejemplos del enunciado, oráculo del usuario, propiedades | `src/eq2/casos.py` (nuevo) |
| Registro tipado e inmutable de herramientas y despachador con permisos por agente y flujo, errores clasificados y sustitución explícita | `src/eq2/herramientas.py` (nuevo) |
| Plan estructurado: subtareas, dependencias, prioridad, orden, información que falta, revisión del plan y detector de pruebas debilitadas | `src/eq2/planificacion.py` (nuevo) |
| Autocorrección: precomprobación estática, historial de intentos, contraejemplos, impugnaciones, afirmaciones sin evidencia | `src/eq2/autocorreccion.py` (nuevo) |
| Memoria de experiencias por agente sobre `aprendizaje.py` (hechos frente a hipótesis, calibración) | `src/eq2/experiencias.py` (nuevo) |
| Motor V2-F: subclase de `motor.Motor` (estado REPLANIFICAR, puerta de información, contraejemplos de A3, disputas A1↔A3 y A1↔A2, reservas, experiencias) | `src/eq2/motor_v2f.py` (nuevo) |
| Debate por evidencias (propuestas independientes, ejecución cruzada, adjudicación determinista, reparación) | `src/eq2/debate.py` (nuevo) |
| Banco comparativo de un agente frente al equipo (4 modos, oráculos ocultos, simulado y real) | `src/eq2/banco_capacidades.py` (nuevo), `banco.py` (nuevo), `bancos/capacidades_v1/*.json` (nuevos) |
| Tablas del motor como atributos de clase y gancho `_alternativa_sin_progreso`. Mismo comportamiento en V2-E: sus pruebas pasan sin cambios | `src/eq2/motor.py` |
| Tareas `debate_codigo` y claves `motor`, `casos`, `propiedades` y `politica_falta`. El motor V2-F es el predeterminado de las tareas nuevas (`"motor": "v2e"` mantiene el anterior). Conclusión `verificado_con_reservas` | `src/eq2/tareas.py`, `equipo.py` (agentes según el tipo, `--ctx`, 2048 por defecto) |
| Versión `f2-v2f` y carpeta `lab_v2f`; `lab_v2e7r3` protegida | `src/eq2/__init__.py`, `src/eq2/config.py` |
| Verificador: fases CAP y BAN, banco simulado reproducible (V-BAN-01), V-QWEN-04, estructura y diferencias frente a r3 | `verificar.py` |
| Validador estático: incluye `banco.py` | `validar_estatico.py` |
| Invariante del hallazgo C (V2-E.6-r3): se añade `experiencias.py` como lector de la memoria con una comprobación ESTÁTICA nueva. Su texto solo llega a prompts y ningún módulo de permisos importa la memoria. Además, una prueba de conducta: misma decisión con y sin memoria maliciosa. **Requiere revisión de GPT-6** | `tests/test_v2e6r3_indirecta.py`, `tests/test_v2f_motor.py` |
| Pruebas nuevas | `tests/test_v2f_componentes.py`, `tests/test_v2f_motor.py`, `tests/test_v2f_debate.py`, `tests/test_v2f_tareas.py`, `tests/test_v2f_banco.py` |
| Ejemplos | `ejemplos/tarea_v2f_codigo.json`, `ejemplos/tarea_v2f_debate.json` |
| Paquetes de ejemplo compatibles con `f2-v2f`, regenerados (en la copia recibida faltaban los ZIP) | `auditoria_ejemplo/fuente/manifiesto.json`, `auditoria_ejemplo/auditoria_ejemplo.zip`, `retos/zomboid_v1/paquete_desafio/fuente/manifiesto.json`, `retos/zomboid_v1/paquete_desafio/desafio_zomboid_v1.zip` |
| Tabla de cumplimiento: requisitos R-V2F-* | `cumplimiento.json` |
| Solo el nombre de la carpeta de datos (`lab_v2e7r3` → `lab_v2f`) en textos de ayuda y en pruebas heredadas (marcadas `# CAMBIO V2-F`) | `aprender.py`, `auditar.py`, `ejecutar_v2.py`, `perfiles.py`, `retos.py`, `supervisar.py`, `herramientas/tabla_cumplimiento.py`, `tests/test_v2b.py`, `tests/test_v2d.py`, `tests/test_v2e.py`, `tests/test_v2e2.py`, `tests/test_v2e3.py`, `tests/test_v2e4.py`, `tests/test_v2e4r2.py`, `tests/test_v2e5.py`, `tests/test_v2e5r2.py`, `tests/test_v2e6_aprendizaje.py`, `tests/test_v2e6_retos.py`, `tests/test_verificador.py` |
| Documentos | `LEEME_V2F.md` (nuevo), `CAMBIOS_V2F.md` (nuevo), `LEEME.md` (aviso de versión), `VERIFICADOR.md` (fases CAP y BAN); listas de archivos regeneradas en `CAMBIOS_V2E6.md`, `CAMBIOS_V2E6R2.md`, `CAMBIOS_V2E6R3.md`, `CAMBIOS_V2E7.md`, `CAMBIOS_V2E7R2.md` y `CAMBIOS_V2E7R3.md` (sin otro cambio) |
| Archivos ausentes en la copia recibida (no se pueden reconstruir) | `modlab_pz/fixtures/mod_ejemplo_propio.lua` (quitado) |

## Archivos
<!-- LISTA_DE_ARCHIVOS: generada por herramientas/lista_cambios.py -->

Nuevos (33):

- `CAMBIOS_V2F.md`
- `CAMBIOS_V2F1.md`
- `INTERFACES_CODEX.md`
- `LEEME_V2F.md`
- `LEEME_V2F1.md`
- `banco.py`
- `bancos/capacidades_v1/oraculos.json`
- `bancos/capacidades_v1/simulacion.json`
- `bancos/capacidades_v1/tareas.json`
- `ejemplos/tarea_funcion_demo.json`
- `ejemplos/tarea_funcion_falta_info.json`
- `ejemplos/tarea_v2f_codigo.json`
- `ejemplos/tarea_v2f_debate.json`
- `herramientas/manifiesto_v2e7r3.txt`
- `herramientas/manifiesto_v2f.txt`
- `src/eq2/autocorreccion.py`
- `src/eq2/banco_capacidades.py`
- `src/eq2/casos.py`
- `src/eq2/debate.py`
- `src/eq2/demo_funcion.py`
- `src/eq2/experiencias.py`
- `src/eq2/funcion_supervisada.py`
- `src/eq2/herramientas.py`
- `src/eq2/interfaces_codex.py`
- `src/eq2/motor_v2f.py`
- `src/eq2/planificacion.py`
- `tests/test_v2f1_codex.py`
- `tests/test_v2f1_funcion.py`
- `tests/test_v2f_banco.py`
- `tests/test_v2f_componentes.py`
- `tests/test_v2f_debate.py`
- `tests/test_v2f_motor.py`
- `tests/test_v2f_tareas.py`

Cambiados (45):

- `CAMBIOS_V2E6.md`
- `CAMBIOS_V2E6R2.md`
- `CAMBIOS_V2E6R3.md`
- `CAMBIOS_V2E7.md`
- `CAMBIOS_V2E7R2.md`
- `CAMBIOS_V2E7R3.md`
- `LEEME.md`
- `VERIFICADOR.md`
- `aprender.py`
- `auditar.py`
- `auditoria_ejemplo/auditoria_ejemplo.zip`
- `auditoria_ejemplo/fuente/manifiesto.json`
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
- `tests/test_verificador.py`
- `validar_estatico.py`
- `verificar.py`

Quitados (1):

- `modlab_pz/fixtures/mod_ejemplo_propio.lua`

Sin cambios: 165.
