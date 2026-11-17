# Cambios de V2-E.7 frente a V2-E.6-r3

Base: la entrega V2-E.6-r3.
- ZIP con SHA-256 `aeb4f6b52b5b9e2e35211058024266645b64a85c94b20951d960b0687c111ee0`.
- Su manifiesto está copiado en `herramientas/manifiesto_v2e6r3.txt`.

El detalle está en `LEEME_V2E7.md`.

| Cambio | Archivos |
|---|---|
| Órdenes `tarea importar / ejecutar / estado / exportar / lista` | `equipo.py` (nuevo) |
| Tareas LAB-NNN con guardado persistente, auditoría determinista y de A3, manifiestos y exportación ZIP | `src/eq2/tareas.py` (nuevo), `ejemplos/tarea_demo.json` (nuevo) |
| Ejecución REAL y restringida de las pruebas: lista blanca AST, proceso hijo con límites, gancho de auditoría y nonce | `src/eq2/ejecutor_restringido.py`, `src/eq2/corredor_pruebas.py` (nuevos); `validar_estatico.py` (excepción documentada de `subprocess` y `equipo.py` en el alcance) |
| Motor: A2 escribe las pruebas (estado PRUEBAS), éxito `criterios_verificados` solo con pruebas reales, auditoría de A3 antes de cerrar el backend | `src/eq2/motor.py` |
| Versión y carpeta propias (`f2-v2e7-r1`, `lab_v2e7`; `lab_v2e6r3` protegida), paquetes de ejemplo reconstruidos | `src/eq2/config.py`, `src/eq2/__init__.py`, órdenes y documentos que nombran la carpeta, `auditoria_ejemplo/…`, `retos/…/paquete_desafio/…` |
| Verificador, cumplimiento y pruebas | `verificar.py`, `cumplimiento.json`, `tests/test_v2e7_equipo.py` (nuevo); las pruebas heredadas modificadas llevan `# CAMBIO V2-E.7` |

## Archivos
<!-- LISTA_DE_ARCHIVOS: generada por herramientas/lista_cambios.py -->

Nuevos (65):

- `CAMBIOS_V2E7.md`
- `CAMBIOS_V2E7R2.md`
- `CAMBIOS_V2E7R3.md`
- `CAMBIOS_V2F.md`
- `CAMBIOS_V2F1.md`
- `INTEGRACION_MODLAB_PZ.md`
- `INTERFACES_CODEX.md`
- `LEEME_V2E7.md`
- `LEEME_V2E7R2.md`
- `LEEME_V2E7R3.md`
- `LEEME_V2F.md`
- `LEEME_V2F1.md`
- `banco.py`
- `bancos/capacidades_v1/oraculos.json`
- `bancos/capacidades_v1/simulacion.json`
- `bancos/capacidades_v1/tareas.json`
- `ejemplos/tarea_demo.json`
- `ejemplos/tarea_funcion_demo.json`
- `ejemplos/tarea_funcion_falta_info.json`
- `ejemplos/tarea_pz_fallo_intencional.json`
- `ejemplos/tarea_v2f_codigo.json`
- `ejemplos/tarea_v2f_debate.json`
- `equipo.py`
- `herramientas/manifiesto_v2e6r3.txt`
- `herramientas/manifiesto_v2e7.txt`
- `herramientas/manifiesto_v2e7r2.txt`
- `herramientas/manifiesto_v2e7r3.txt`
- `herramientas/manifiesto_v2f.txt`
- `modlab_pz/EJECUTAR_PRUEBAS.py`
- `modlab_pz/INTEGRACION_CLAUDE.md`
- `modlab_pz/LEEME.md`
- `modlab_pz/__init__.py`
- `modlab_pz/contrato_agentes.json`
- `modlab_pz/escenarios/inventario_demo.json`
- `modlab_pz/escenarios/inventario_error_intencional.json`
- `modlab_pz/laboratorio.py`
- `modlab_pz/lua_analisis.py`
- `modlab_pz/test_laboratorio.py`
- `modlab_pz/test_lua_analisis.py`
- `src/eq2/autocorreccion.py`
- `src/eq2/banco_capacidades.py`
- `src/eq2/casos.py`
- `src/eq2/corredor_pruebas.py`
- `src/eq2/debate.py`
- `src/eq2/demo_funcion.py`
- `src/eq2/ejecutor_restringido.py`
- `src/eq2/evidencia_pz.py`
- `src/eq2/experiencias.py`
- `src/eq2/funcion_supervisada.py`
- `src/eq2/herramientas.py`
- `src/eq2/interfaces_codex.py`
- `src/eq2/modlab_pz_adaptador.py`
- `src/eq2/motor_v2f.py`
- `src/eq2/planificacion.py`
- `src/eq2/tareas.py`
- `tests/test_v2e7_equipo.py`
- `tests/test_v2e7r2_modlab.py`
- `tests/test_v2e7r3_auditoria_pz.py`
- `tests/test_v2f1_codex.py`
- `tests/test_v2f1_funcion.py`
- `tests/test_v2f_banco.py`
- `tests/test_v2f_componentes.py`
- `tests/test_v2f_debate.py`
- `tests/test_v2f_motor.py`
- `tests/test_v2f_tareas.py`

Cambiados (43):

- `CAMBIOS_V2E6.md`
- `CAMBIOS_V2E6R2.md`
- `CAMBIOS_V2E6R3.md`
- `LEEME.md`
- `LEEME_V2E6.md`
- `LIMITES_Y_RIESGOS_V2E6.md`
- `PAQUETES_AUDITORIA.md`
- `VERIFICADOR.md`
- `aprender.py`
- `auditar.py`
- `auditoria_ejemplo/auditoria_ejemplo.zip`
- `auditoria_ejemplo/fuente/manifiesto.json`
- `cumplimiento.json`
- `ejecutar_v2.py`
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

Quitados (0):

- ninguno

Sin cambios: 135.
