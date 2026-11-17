# Cambios de V2-E.6-r2 frente a V2-E.6

Base: la entrega V2-E.6.
- ZIP con SHA-256 `4de6dfebcfe6c86be2ab3044301ca6972805c5459a5bef0a663923fb8ddeb230`.
- Su manifiesto está copiado en `herramientas/manifiesto_v2e6.txt`.

Son solo correcciones de la auditoría adversarial. El detalle está en `LEEME_V2E6R2.md`.

| Corrección | Archivos |
|---|---|
| **Caso A.** Una prueba estática debe estar vinculada a una ejecución registrada: tabla `ejecuciones`, `probar()`, verificadores registrados en código, re-ejecución antes de cambiar el estado y en la auditoría. `observado` y `dato_externo` dejan de cambiar el estado. Esquema de aprendizaje 2. | `src/eq2/aprendizaje.py`, `src/eq2/evaluacion_aprendizaje.py`, `src/eq2/orquestador.py` |
| **Caso B.** Análisis de contenido instructivo con plegado de ofuscaciones, análisis por cláusulas multilingüe, cargas codificadas y cuarentena. | `src/eq2/contaminacion.py` (nuevo), `src/eq2/aprendizaje.py` |
| **Recomendación 2.** Aviso explícito en el bloque de recuerdos del prompt. | `src/eq2/prompts.py` |
| **Versión y carpeta propias:** `f2-v2e6-r2` y `lab_v2e6r2`. `lab_v2e6` pasa a carpeta anterior protegida. | `src/eq2/config.py`, `src/eq2/__init__.py`, y las órdenes y documentos que nombran la carpeta |
| Los paquetes de ejemplo se reconstruyen con `compatible_con` + `f2-v2e6-r2`. | `auditoria_ejemplo/…`, `retos/zomboid_v1/paquete_desafio/…` |
| **Verificador:** área del módulo de pruebas nuevo y comprobación de cambios también frente a V2-E.6. | `verificar.py`, `herramientas/lista_cambios.py`, `cumplimiento.json` |
| **Pruebas nuevas:** `tests/test_v2e6r2_adversarial.py`. Las heredadas modificadas llevan `# CAMBIO V2-E.6-r2`. | `tests/…` |

## Archivos
<!-- LISTA_DE_ARCHIVOS: generada por herramientas/lista_cambios.py -->

Nuevos (75):

- `CAMBIOS_V2E6R2.md`
- `CAMBIOS_V2E6R3.md`
- `CAMBIOS_V2E7.md`
- `CAMBIOS_V2E7R2.md`
- `CAMBIOS_V2E7R3.md`
- `CAMBIOS_V2F.md`
- `CAMBIOS_V2F1.md`
- `INTEGRACION_MODLAB_PZ.md`
- `INTERFACES_CODEX.md`
- `LEEME_V2E6R2.md`
- `LEEME_V2E6R3.md`
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
- `herramientas/manifiesto_v2e6.txt`
- `herramientas/manifiesto_v2e6r2.txt`
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
- `src/eq2/contaminacion.py`
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
- `tests/corpus_indirecto.py`
- `tests/test_v2e6r2_adversarial.py`
- `tests/test_v2e6r3_indirecta.py`
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

Cambiados (46):

- `CAMBIOS_V2E6.md`
- `CUMPLIMIENTO_V2E6.md`
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
- `herramientas/lista_cambios.py`
- `herramientas/tabla_cumplimiento.py`
- `perfiles.py`
- `retos.py`
- `retos/zomboid_v1/paquete_desafio/desafio_zomboid_v1.zip`
- `retos/zomboid_v1/paquete_desafio/fuente/manifiesto.json`
- `src/eq2/__init__.py`
- `src/eq2/aprendizaje.py`
- `src/eq2/config.py`
- `src/eq2/contexto.py`
- `src/eq2/evaluacion_aprendizaje.py`
- `src/eq2/motor.py`
- `src/eq2/orquestador.py`
- `src/eq2/prompts.py`
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
- `tests/test_verificador.py`
- `validar_estatico.py`
- `verificar.py`

Quitados (0):

- ninguno

Sin cambios: 122.
