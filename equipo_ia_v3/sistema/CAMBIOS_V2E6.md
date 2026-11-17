# Cambios de V2-E.6 frente a V2-E.5-r3

Base: la copia auténtica de V2-E.5-r3.
- Su `MANIFIESTO_SHA256.txt` coincide con el árbol r3. Se copió a `herramientas/manifiesto_r3.txt`.
- El ZIP r3 tiene el SHA-256 `419626b6efd9eb15af21b65653e88c468d245273ca21c5f4b7ae34a5ac6c7eb3`.

La comprobación V-CUM-02 del verificador recalcula las diferencias y FALLA si algún archivo nuevo, cambiado o quitado no figura en la lista final de este documento.

## Resumen por área
1. **Contexto y tokens.**
   - `perfiles_contexto.py` (nuevo) define cuatro perfiles:

     | Perfil | Contexto | Presupuestos de salida |
     |---|---|---|
     | seguro | 1024 | los de r3 |
     | referencia | 2048 | idénticos a r3 |
     | ampliado | 2560 | +25 % en las fases largas |
     | experimental | 3072 | +50 %; exige aceptación explícita |

   - En todos los perfiles el voto se queda en 120 tokens.
   - Reservas de sistema y memoria.
   - Límites ESTRICTOS por tarea y por sesión: `limite_tokens_tarea` y `limite_tokens_sesion`.
   - Retroceso automático, con motivos, si la RAM no alcanza o no se puede medir, o si el servidor tiene menos contexto.
   - `TOPE_MAX_TOKENS` pasa de 700 a 800.
   - CLI: `--perfil-contexto` y `--aceptar-experimental`.
   - El resumen incluye `tokens_pedidos_sesion` y el perfil.
2. **Laboratorios (esquema de cuaderno 3).**
   - Artefactos con SHA-256, versiones, procedencia y espacio (A1, A2, A3 o común).
   - Evidencia con fuente y líneas, comprobada contra el artefacto. Se rechaza la evidencia insuficiente.
   - Hipótesis y falsaciones exigen una condición de falsación.
   - Rechazo y abstención deben ser razonados.
   - Las comprobaciones declarativas (`contiene`, `no_contiene`, `cuenta_regex`, `lineas_existen`, `cita_literal`) las evalúa el laboratorio.
   - Pendientes del coordinador con 7 estados y transiciones impuestas por la base.
   - «verificado» exige una comprobación positiva del sistema sobre ESA propuesta.
   - `aprobada_con_cambios` → `cambios_solicitados`, nunca «verificado».
   - Tipos nuevos para A1, A2 y A3.
   - El código conserva la indentación (`sanea.limpiar_codigo`).
3. **Agentes.**
   - `roles.py`: tarjetas de rol persistidas en `roles/` con su huella.
   - `independencia.py`: señales deterministas de dependencia. Se integran en el resultado y en las advertencias, sin cambiar el recuento.
4. **Aprendizaje.**
   - `aprendizaje.py`:
     - una base por agente, con estados y tipos de evidencia;
     - disparadores que impiden que un voto, una opinión o una simulación verifiquen o refuten;
     - historia inmutable;
     - deduplicación, caducidad, contradicciones y filtro de contaminación;
     - recuperación con metadatos;
     - feedback humano autorizado y revocación.
   - `evaluacion_aprendizaje.py`: evaluación pre/post SIMULADA.
   - `aprender.py`: CLI.
   - El orquestador guarda tras cada tarea un hecho observado, verificado por el registro, y el voto como hipótesis. Los prompts reciben las memorias con metadatos; `memoria.buscar` devuelve además fecha y turno.
5. **Pruebas variables.**
   - `pruebas_variables.py` combina semillas fijas (11, 42, 2026) y una opcional con niveles 1–3.
   - Conjunto Zomboid: orden barajado, recorte, formato e inyección.
   - Conjunto de deliberación: comportamientos sorteados, con un oráculo oculto de lo que el sistema debe detectar.
   - Comprueba el determinismo.
6. **Reto Zomboid.**
   - `retos/zomboid_v1/material_original/` es la copia byte a byte del material del usuario, con su manifiesto.
   - `retos/zomboid_v1/eq2/`: casos, oráculos ocultos y referencias.
   - `retos.py` (biblioteca):
     - generador seguro;
     - prompt sin oráculos, con recorte visible por líneas;
     - análisis del formato HECHO/HIPOTESIS/FALTA/RIESGO/ACCION/VERIFICACION/NOTA;
     - puntuador 0–12 con penalizaciones;
     - tubería A2→A1→A3 sobre los laboratorios;
     - ejecución con cualquier backend.
   - `retos.py` (CLI): órdenes de reto y de pruebas variables.
   - `ejecutar_v2.py`: modos `reto_simulado` y `reto` (real, con `--iniciar-servidor-real`).
7. **Paquetes de desafío.**
   - Formato `eq2/desafio` v1, con las mismas reglas de contenedor.
   - Operaciones `puntuar_reto` y `generar_reto`.
   - Parámetro `reto` validado.
   - Ejemplo en `retos/zomboid_v1/paquete_desafio/`.
8. **Calidad.**
   - Pruebas de STOP durante la continuación y la limpieza.
   - Fallo del modelo a mitad sin pérdida de evidencia.
   - Reanudación EXPLÍCITA: `Orquestador.pendientes_de`, `run_reanudacion` y `ejecutar_v2.py --reanudar RUN_ID`.
   - Cada ejecución registra `runs/<id>/tareas.json`.
9. **Verificador.**
   - 21 fases con INICIO y FIN.
   - Naturaleza de cada comprobación: REAL, SIMULADA, OMITIDA o NO VERIFICADA.
   - `terminal.log` y `eventos.jsonl` con CPU y RAM.
   - Semillas y demostraciones por función: `--demo` y `--lista-demos`.
   - Comprobaciones de cumplimiento, de diferencias con r3 y del material Zomboid.
   - La evidencia de fábrica entra en el manifiesto.
   - Rutas bajo `lab_v2e6/`.
   - Tercera prueba con Qwen real: el reto.

## Pruebas heredadas modificadas
Todas llevan la marca `# CAMBIO V2-E.6 (V2-E.5-r3: …)` con el valor anterior:
- carpeta `datos_v2e5r3` → `lab_v2e6`;
- versión;
- esquema de cuaderno `"2"` → `"3"`;
- el código conserva la indentación;
- rutas del verificador y de la auditoría bajo `lab_v2e6/`.

Para localizarlas:
```
grep -rn "CAMBIO V2-E.6" tests/
```

## Archivos
<!-- LISTA_DE_ARCHIVOS: generada por herramientas/lista_cambios.py -->

Nuevos (121):

- `CAMBIOS_V2E6.md`
- `CAMBIOS_V2E6R2.md`
- `CAMBIOS_V2E6R3.md`
- `CAMBIOS_V2E7.md`
- `CAMBIOS_V2E7R2.md`
- `CAMBIOS_V2E7R3.md`
- `CAMBIOS_V2F.md`
- `CAMBIOS_V2F1.md`
- `CUMPLIMIENTO_V2E6.md`
- `INTEGRACION_MODLAB_PZ.md`
- `INTERFACES_CODEX.md`
- `LEEME_V2E6.md`
- `LEEME_V2E6R2.md`
- `LEEME_V2E6R3.md`
- `LEEME_V2E7.md`
- `LEEME_V2E7R2.md`
- `LEEME_V2E7R3.md`
- `LEEME_V2F.md`
- `LEEME_V2F1.md`
- `LIMITES_Y_RIESGOS_V2E6.md`
- `ROLLBACK_V2E6.md`
- `aprender.py`
- `banco.py`
- `bancos/capacidades_v1/oraculos.json`
- `bancos/capacidades_v1/simulacion.json`
- `bancos/capacidades_v1/tareas.json`
- `cumplimiento.json`
- `ejemplos/tarea_demo.json`
- `ejemplos/tarea_funcion_demo.json`
- `ejemplos/tarea_funcion_falta_info.json`
- `ejemplos/tarea_pz_fallo_intencional.json`
- `ejemplos/tarea_v2f_codigo.json`
- `ejemplos/tarea_v2f_debate.json`
- `equipo.py`
- `herramientas/lista_cambios.py`
- `herramientas/manifiesto_r3.txt`
- `herramientas/manifiesto_v2e6.txt`
- `herramientas/manifiesto_v2e6r2.txt`
- `herramientas/manifiesto_v2e6r3.txt`
- `herramientas/manifiesto_v2e7.txt`
- `herramientas/manifiesto_v2e7r2.txt`
- `herramientas/manifiesto_v2e7r3.txt`
- `herramientas/manifiesto_v2f.txt`
- `herramientas/tabla_cumplimiento.py`
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
- `retos.py`
- `retos/zomboid_v1/NO_EJECUTAR.md`
- `retos/zomboid_v1/eq2/casos.json`
- `retos/zomboid_v1/eq2/oraculos.json`
- `retos/zomboid_v1/eq2/referencias.json`
- `retos/zomboid_v1/material_original/CRITERIOS_EVALUACION.md`
- `retos/zomboid_v1/material_original/MANIFIESTO.json`
- `retos/zomboid_v1/material_original/README.md`
- `retos/zomboid_v1/material_original/evidencias/01_fuentes.txt`
- `retos/zomboid_v1/material_original/evidencias/02_plantillas.txt`
- `retos/zomboid_v1/material_original/evidencias/03_viewpoint.txt`
- `retos/zomboid_v1/material_original/evidencias/04_inicio.txt`
- `retos/zomboid_v1/material_original/generar_reto.py`
- `retos/zomboid_v1/paquete_desafio/desafio_zomboid_v1.zip`
- `retos/zomboid_v1/paquete_desafio/fuente/LEEME.md`
- `retos/zomboid_v1/paquete_desafio/fuente/datos/respuestas.json`
- `retos/zomboid_v1/paquete_desafio/fuente/manifiesto.json`
- `retos/zomboid_v1/paquete_desafio/fuente/reto/casos.json`
- `retos/zomboid_v1/paquete_desafio/fuente/reto/evidencias/01_fuentes.txt`
- `retos/zomboid_v1/paquete_desafio/fuente/reto/evidencias/02_plantillas.txt`
- `retos/zomboid_v1/paquete_desafio/fuente/reto/evidencias/03_viewpoint.txt`
- `retos/zomboid_v1/paquete_desafio/fuente/reto/evidencias/04_inicio.txt`
- `retos/zomboid_v1/paquete_desafio/fuente/reto/oraculos.json`
- `src/eq2/aprendizaje.py`
- `src/eq2/autocorreccion.py`
- `src/eq2/banco_capacidades.py`
- `src/eq2/casos.py`
- `src/eq2/contaminacion.py`
- `src/eq2/corredor_pruebas.py`
- `src/eq2/debate.py`
- `src/eq2/demo_funcion.py`
- `src/eq2/ejecutor_restringido.py`
- `src/eq2/evaluacion_aprendizaje.py`
- `src/eq2/evidencia_pz.py`
- `src/eq2/experiencias.py`
- `src/eq2/funcion_supervisada.py`
- `src/eq2/herramientas.py`
- `src/eq2/independencia.py`
- `src/eq2/interfaces_codex.py`
- `src/eq2/modlab_pz_adaptador.py`
- `src/eq2/motor_v2f.py`
- `src/eq2/perfiles_contexto.py`
- `src/eq2/planificacion.py`
- `src/eq2/pruebas_variables.py`
- `src/eq2/retos.py`
- `src/eq2/roles.py`
- `src/eq2/tareas.py`
- `tests/corpus_indirecto.py`
- `tests/test_v2e6_agentes.py`
- `tests/test_v2e6_aprendizaje.py`
- `tests/test_v2e6_calidad.py`
- `tests/test_v2e6_contexto.py`
- `tests/test_v2e6_laboratorios.py`
- `tests/test_v2e6_retos.py`
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

Cambiados (36):

- `LABORATORIOS.md`
- `LEEME.md`
- `PAQUETES_AUDITORIA.md`
- `PLATAFORMAS.md`
- `VERIFICADOR.md`
- `auditar.py`
- `auditoria_ejemplo/auditoria_ejemplo.zip`
- `auditoria_ejemplo/fuente/manifiesto.json`
- `ejecutar_v2.py`
- `perfiles.py`
- `src/eq2/__init__.py`
- `src/eq2/config.py`
- `src/eq2/contexto.py`
- `src/eq2/laboratorios.py`
- `src/eq2/memoria.py`
- `src/eq2/motor.py`
- `src/eq2/orquestador.py`
- `src/eq2/paquetes_auditoria.py`
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
- `tests/test_verificador.py`
- `validar_estatico.py`
- `verificar.py`

Quitados (0):

- ninguno

Sin cambios: 86.
