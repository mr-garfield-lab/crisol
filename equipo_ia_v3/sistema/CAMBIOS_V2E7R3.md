# Cambios de V2-E.7-r3 frente a V2-E.7-r2

Base: la entrega V2-E.7-r2.
- ZIP con SHA-256 `e2f24c04c327a43c83ca35486bb348e546086577bec721bfc29fb395e8869459`.
- Su manifiesto está copiado en `herramientas/manifiesto_v2e7r2.txt`.

El detalle está en `LEEME_V2E7R3.md`.

| Cambio | Archivos |
|---|---|
| Evidencia verificada para A3 (4 categorías, SHA-256, pasos, inventario) | `src/eq2/evidencia_pz.py` (nuevo) |
| A3 audita con el paso `pz_auditar` y la evidencia nueva; se guarda el texto recibido y `cita_pasos` | `src/eq2/tareas.py` (solo `_ejecutar_pz`), `src/eq2/motor.py` (`INSTR`/`AGENTE_PASO`/`TOKENS_PASO["pz_auditar"]`, límite 1200 en `paso_libre`) |
| Pruebas de regresión | `tests/test_v2e7r3_auditoria_pz.py` (nuevo); `tests/test_v2e7r2_modlab.py` (clave del guion `pz_auditar`) |
| Versión y carpeta (`f2-v2e7-r3`, `lab_v2e7r3`; `lab_v2e7r2` protegida), paquetes de ejemplo, verificador, cumplimiento y documentos | `src/eq2/config.py`, `src/eq2/__init__.py`, `verificar.py`, `cumplimiento.json`, `LEEME_V2E7.md`, `LEEME_V2E7R2.md`, `VERIFICADOR.md`, `PAQUETES_AUDITORIA.md`; las pruebas heredadas modificadas llevan `# CAMBIO V2-E.7-r3` |
| Solo el nombre de la carpeta de datos (`lab_v2e7r2` → `lab_v2e7r3`) en textos de ayuda | `aprender.py`, `auditar.py`, `ejecutar_v2.py`, `equipo.py`, `perfiles.py`, `retos.py`, `supervisar.py`, `herramientas/tabla_cumplimiento.py` |
| Lista de archivos regenerada (sin otro cambio) | `CAMBIOS_V2E6.md`, `CAMBIOS_V2E6R2.md`, `CAMBIOS_V2E6R3.md`, `CAMBIOS_V2E7.md`, `CAMBIOS_V2E7R2.md` |

## Archivos
<!-- LISTA_DE_ARCHIVOS: generada por herramientas/lista_cambios.py -->

Nuevos (38):

- `CAMBIOS_V2E7R3.md`
- `CAMBIOS_V2F.md`
- `CAMBIOS_V2F1.md`
- `INTERFACES_CODEX.md`
- `LEEME_V2E7R3.md`
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
- `herramientas/manifiesto_v2e7r2.txt`
- `herramientas/manifiesto_v2e7r3.txt`
- `herramientas/manifiesto_v2f.txt`
- `src/eq2/autocorreccion.py`
- `src/eq2/banco_capacidades.py`
- `src/eq2/casos.py`
- `src/eq2/debate.py`
- `src/eq2/demo_funcion.py`
- `src/eq2/evidencia_pz.py`
- `src/eq2/experiencias.py`
- `src/eq2/funcion_supervisada.py`
- `src/eq2/herramientas.py`
- `src/eq2/interfaces_codex.py`
- `src/eq2/motor_v2f.py`
- `src/eq2/planificacion.py`
- `tests/test_v2e7r3_auditoria_pz.py`
- `tests/test_v2f1_codex.py`
- `tests/test_v2f1_funcion.py`
- `tests/test_v2f_banco.py`
- `tests/test_v2f_componentes.py`
- `tests/test_v2f_debate.py`
- `tests/test_v2f_motor.py`
- `tests/test_v2f_tareas.py`

Cambiados (48):

- `CAMBIOS_V2E6.md`
- `CAMBIOS_V2E6R2.md`
- `CAMBIOS_V2E6R3.md`
- `CAMBIOS_V2E7.md`
- `CAMBIOS_V2E7R2.md`
- `LEEME.md`
- `LEEME_V2E7.md`
- `LEEME_V2E7R2.md`
- `PAQUETES_AUDITORIA.md`
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
- `tests/test_v2e7r2_modlab.py`
- `tests/test_verificador.py`
- `validar_estatico.py`
- `verificar.py`

Quitados (1):

- `modlab_pz/fixtures/mod_ejemplo_propio.lua`

Sin cambios: 157.
