# Equipo IA — V2-E.4 revisión r2 — corrección tras la auditoría estática de GPT-6

Revisión independiente construida sobre V2-E.4 r1. **r1 y las versiones anteriores no se han modificado.** Sus huellas SHA-256 coinciden.
No añade capacidades ni ModLab. El modo real (Modo B) sigue **deshabilitado**.
**No se ha ejecutado nada en Termux ni con el modelo real.** Todos los resultados proceden de la sandbox Linux.

## 1. Problema
GPT-6 encontró que `Laboratorio.confirmar_causa_con()` confirmaba una causa con **una sola reproducción**, mientras que el investigador automático exige reproducción y control. Al revisarlo aparecieron **dos caminos más** con el mismo efecto:

| # | Camino | Qué permitía |
|---|---|---|
| 1 | `Laboratorio.confirmar_causa_con(eid)` | Confirmar la causa con un experimento aislado que «reproduce» el fallo. Una regla «si contiene X, falla» solo comprueba lo que ella misma supone. |
| 2 | `RegistroIncidencias.confirmar_causa(..., respaldo="simulacion")` | A cualquier actor que no fuera un agente (laboratorio, motor o usuario), marcar la causa como respaldada con **una** evidencia simulada. |
| 3 | `Laboratorio.planificar(..., rol="control", hipotesis_id=...)` | Fabricar un experimento de «control» con un texto o una regla inventados, que nunca se observaron en una versión real. |

## 2. Corrección (mínima suficiente)
**Las reglas las impone la base de datos (esquema 4).** Así valen para cualquier camino, manual o automático:
1. **Causa confirmada.** Solo puede quedar `confirmada` en uno de estos dos casos:
   - con respaldo `simulacion` y `causa_hipotesis` apuntando a una hipótesis **respaldada** de esa misma incidencia;
   - con respaldo `prueba_real` y una prueba real registrada, lo que es imposible con el Modo B deshabilitado.

   Una sola actualización fija los tres campos y la base comprueba el conjunto. Ninguna incidencia nace confirmada.
2. **Hipótesis respaldada.** Solo puede pasar a `respaldada` si la **reproducción** coincide con una **observación del motor** con la incidencia **presente**, y el **control** con una observación con la incidencia **ausente**. Las dos deben coincidir en ejecución, versión, archivo y SHA-256 del texto.
3. **Observaciones.** La tabla nueva `observaciones`, de solo anexar, guarda en cada versión qué incidencias se observaron y el SHA-256 del texto de cada archivo. Solo el actor `motor` la escribe, desde `Investigador.observar` en el ciclo del motor.
4. **Reversión automática.** Si una hipótesis deja de estar respaldada, un disparador devuelve su causa a hipótesis y lo anota en el historial.

**En el código:**
- `Laboratorio.planificar()` ya **no acepta** `rol` ni `hipotesis_id`. La reproducción y el control solo se crean con `planificar_prueba_de_hipotesis(hid, rol, run_id, version, texto)`, que **construye la regla desde la hipótesis** (archivo y patrón) y guarda la procedencia.
- `confirmar_causa_con(eid)` solo confirma si la hipótesis del experimento ya está respaldada. Si no, devuelve `False` y anota una sola vez el motivo: «un experimento aislado no basta».
- `crear_regresion(eid)` solo parte de la **reproducción de la hipótesis que respalda la causa**.
- Si la base rechaza la procedencia, la hipótesis se queda en «consistente» y el motivo aparece en los límites, sin desactivar la investigación. Un control sobre una versión en la que ya no existe el archivo no cuenta.
- `auditar.py demo-laboratorio` muestra ahora que un experimento aislado **no** confirma. El ciclo completo está en `demo-ciclo`.

**Consecuencia:** el respaldo «análisis estático» ya no se puede alcanzar. Todo respaldo procede de la reproducción y el control simulados sobre versiones observadas.

**Alcance de la garantía:** protege frente a los caminos del sistema y frente al texto de los agentes. **No** protege frente a alguien con acceso local que edite a mano el archivo SQLite o que llame a la API interna inventando observaciones del motor desde su propio código Python.

## 3. Tipos especializados: solo declaraciones, no aislamiento
- `TipoExperimento.validar` y `.correr` se consideran **código no confiable de terceros** y **no se invocan nunca**: ni al registrar, ni al planificar, ni al ejecutar.
- Planificar un tipo especializado lanza `TipoNoEjecutable`. `_correr` y `ejecutar` tienen la misma defensa.
- Los campos `ejecuta_codigo` y `usa_red` son lo que el tipo **declara** de sí mismo. El registro rechaza las declaraciones prohibidas, pero **no es un aislamiento de seguridad**. La documentación del módulo y de la clase lo dice expresamente.
- Ejecutarlos en el futuro exigirá aislamiento real y una autorización explícita del usuario. No hay nada de eso en esta versión.

## 4. Archivos
- **Nuevos:**
  - `tests/test_v2e4r2.py` (25 pruebas);
  - `LEEME_V2E4R2.md`;
  - en `tests/_comun.py`, `respaldar_causa()`, que prepara una causa confirmada por el único camino válido.
- **Modificados:**
  - `incidencias.py`: esquema 4, `observaciones`, cuatro disparadores nuevos, `confirmar_causa` (una sola actualización), `registrar_observacion` y `observaciones`;
  - `laboratorio.py`: `planificar_prueba_de_hipotesis`, `planificar` sin `rol` ni `hipotesis_id`, `confirmar_causa_con`, `crear_regresion`, tipos solo declarativos (`TipoNoEjecutable`) y la deduplicación de evidencia limitada a la estática o simulada;
  - `investigacion.py`: registra las observaciones, usa el método canónico, exige que el control tenga el archivo y tolera el rechazo de procedencia;
  - `motor_incidencias.py`: la observación pasa por el aislamiento de fallos de la investigación;
  - `auditar.py`: `demo-laboratorio`;
  - `config.py` y `__init__.py`: `datos_v2e4r2` y `VERSION = "f2-v2e4-r2"`;
  - `ejecutar_v2.py` y `supervisar.py`: la carpeta;
  - `LEEME_V2E4.md`: nota y marcas **[sustituido en r2]**.
- **Carpeta de datos nueva** (`datos_v2e4r2`) **y esquema 4:** los datos creados con las reglas de r1 no se mezclan. Una base de r1 (esquema 3) se rechaza.

## 5. Pruebas heredadas modificadas (CAMBIO V2-E.4-r2)
**Por la corrección** (antes daban por buena la confirmación débil):
- `test_v2e2.BaseReg.confirmar`, el ayudante de preparación de las pruebas de planificación: ahora usa `_comun.respaldar_causa`. Las aserciones de esas pruebas **no** cambian.
- `test_v2e2.TestLaboratorio.test_simulacion_reproduce_confirma_y_crea_regresion`: una reproducción aislada ya **no** confirma ni permite crear una regresión; la regresión se crea por el camino completo.
- `test_v2e2.TestLaboratorio.test_regresion_exige_que_el_experimento_reproduzca_el_fallo`: idem, y además comprueba que un experimento libre no sirve de origen.
- `test_v2e2.TestCLI.test_recorrido_completo`: `regresiones` ya no muestra `REG-000001` tras `demo-laboratorio`.
- `test_v2e3.TestAgenteCorrecto.test_seleccion_por_estado`: la preparación por el camino completo.
- `test_v2e3.TestRespaldoYDeclaraciones.test_niveles_de_respaldo`: un experimento aislado no da respaldo, y el respaldo estático no se alcanza.
- `test_v2e3.TestRespaldoYDeclaraciones.test_la_base_impide_presentar_simulacion_como_prueba_real`: confirmar con una evidencia ahora **falla**.
- `test_v2e3.TestRespaldoYDeclaraciones.test_cabecera_dice_el_respaldo`: la preparación por el camino completo.
- `test_v2e4.TestRegistroV2E4.test_solo_el_laboratorio_cambia_hipotesis_y_respaldada_exige_dos_experimentos`: el método canónico.
- `test_v2e4.TestTiposEspecializados`: el tipo **ya no se ejecuta**; se comprueba que ni `validar` ni `correr` se invocan.
- `test_v2e4.TestRecuperacion.test_fallo_de_la_investigacion_no_detiene_la_tarea_ni_el_registro`: simula el fallo en el método canónico.

**Solo por el nombre de la carpeta, la versión o el esquema:** las de CLI y versión de `test_v2b`, `test_v2d`, `test_v2e`, `test_v2e2`, `test_v2e3` y `test_v2e4`, marcadas en el código.

## 6. Resultados ejecutados (sandbox Linux; NO en Termux)
| Comprobación | Resultado |
|---|---|
| Validador estático | 0 problemas |
| Suite completa **con** `os.link` | **674/674 OK** en 2 de 2 pasadas (649 de r1 + 25 nuevas) |
| Suite completa **sin** `os.link` (simulación de Termux) | **674/674 OK** |
| Mutaciones de las protecciones de r2 (contra `test_v2e4r2` + `test_v2e4` + `test_v2e3` + `test_v2e2`) | **19/19 detectadas** (dos sobrevivieron en la primera ronda; se añadieron sus pruebas y se repitieron) |
| r1 y V2-B … V2-E.3 sin cambios (`sha256sum -c`) | OK |
| Suite y validador desde el ZIP extraído | ver la respuesta de entrega |

**Qué detectan las mutaciones:**
- el disparador de causa confirmada;
- la procedencia de la reproducción y la del control;
- la reversión automática;
- «no nacer confirmada»;
- el actor de las observaciones, que sean de solo anexar y su idempotencia;
- la procedencia obligatoria de los experimentos con rol;
- que el respaldo sea siempre de simulación;
- la comprobación de `confirmar_causa_con`;
- el origen de la regresión;
- el rechazo de los tipos especializados en `_validar` y en `_correr`;
- el SHA-256 canónico;
- la anotación única del rechazo;
- que se registren las observaciones;
- que el control tenga el archivo;
- la tolerancia ante el rechazo de procedencia.

## 7. Validación en Termux
```
mkdir -p "$TMPDIR/equipo_f2/codigo_v2e4r2" && cd "$TMPDIR/equipo_f2/codigo_v2e4r2"
unzip /ruta/a/equipo_f2_v2e4r2.zip && cd equipo_f2_v2e4r2
python3 -B -I validar_estatico.py
python3 -B -W error::ResourceWarning -X dev -m unittest discover -s tests -p "test_*.py"
python3 -B -W error::ResourceWarning -X dev -m unittest discover -s tests -p "test_v2e4r2.py"
python3 -B auditar.py demo-laboratorio     # «causa confirmada: False» con un experimento aislado
python3 -B auditar.py demo-ciclo           # camino completo: reproducción + control observados
ls "$TMPDIR/equipo_f2"                     # datos_v2e4r2 (datos_v2e4 de r1 intacta si existía)
```

## 8. Limitaciones y riesgos que siguen abiertos
- **El límite de la garantía** es el indicado en la sección 2: acceso local al archivo SQLite o código Python propio que invente observaciones.
- **«Respaldada por simulación» sigue siendo una correlación textual entre versiones.** No es causalidad ni funcionamiento real.
- **Un control necesita que el archivo exista** en la versión que pasa. Si A1 lo borra, la hipótesis queda «consistente».
- **El resto de las limitaciones de V2-E.4 sigue vigente** (`LEEME_V2E4.md`, secciones 10 y 11), incluido el fallo intermitente sin explicar de `test_stop_durante_la_tarea`, heredado y dependiente del reloj.
