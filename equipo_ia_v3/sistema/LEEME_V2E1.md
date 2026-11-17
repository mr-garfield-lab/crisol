# Equipo IA — V2-E.1 (corrección de compatibilidad con Android/Termux) — ENTREGA PARA AUDITORÍA

Versión correctiva independiente de V2-E. **La V2-E original no se ha modificado** (las huellas SHA-256 de sus 61 archivos y su ZIP coinciden con las de la entrega).
**No se ha ejecutado el modelo real ni nada en Termux con este código.** La ejecución real de código generado sigue **deshabilitada** (Modo B).

## 1. Problema
En el Python de Termux, `os` **no tiene `link`**. `rutas.escribir_atomico()` llamaba a `os.link(...)` y capturaba `OSError`, pero la llamada lanzaba `AttributeError`, que no es un `OSError`. Resultado en el dispositivo: 462 pruebas con 18 fallos y 5 errores.

## 2. Reproducción y clasificación de los 23 resultados
Se reprodujo en la sandbox retirando `os.link` del intérprete, también en los subprocesos de las pruebas, mediante un `sitecustomize` **solo de la sandbox; no va en el paquete**. **Resultado: exactamente 18 fallos y 5 errores, los mismos números que en Termux.**

| Prueba (V2-E) | Tipo | Causa |
|---|---|---|
| `TestProyecto.test_versiones_conservadas_y_manifiesto` | error | `AttributeError: os.link` directo |
| `TestProyecto.test_nunca_sobrescribe` | error | `AttributeError: os.link` directo |
| `TestAsesoria.test_exportar_e_importar` | error | `AttributeError: os.link` directo (exportar usa `escribir_atomico`) |
| `TestProyecto.test_escritura_no_atomica_se_informa` | error | **Defecto de la prueba**: `mock.patch("eq2.rutas.os.link")` exige que el atributo exista |
| `TestMotorServidorFalso.test_error_de_sintaxis_se_corrige_automaticamente` | error | `IndexError` consecuencia: el motor terminó en `error_critico` (por `os.link`) antes del análisis estático |
| 13 de `TestMaquinaDeEstados`, `TestAnalisisEstatico` y `TestSupervisionCLI`, y 4 de `TestMotorServidorFalso` | fallo | El motor capturó el `AttributeError` al guardar la versión 1, terminó en `error_critico` y la aserción posterior falló (`'error_critico' != ...`) |

**Conclusión:** los 23 son consecuencia de la ausencia de `os.link`. Prueba diferencial:
- con `os.link` presente, V2-E pasa las 462;
- sin `os.link`, falla en esos 23;
- con la corrección, pasa en los dos modos.

No hay resultados independientes **en lo que la sandbox puede reproducir**. Si en el teléfono la lista de nombres no coincide con esta tabla, la diferencia se debería a otra cosa de Termux y conviene enviármela.

Defectos **adicionales** encontrados al escribir las pruebas nuevas (no aparecían en Termux, pero eran reales):
1. **Un fallo de E/S a mitad de `guardar_version` bloqueaba el proyecto para siempre:** la carpeta `v1` quedaba creada y la siguiente versión fallaba con `FileExistsError`. Ahora el número de versión se consume al crear la carpeta; la versión fallida queda sin `manifiesto.json` (marcada como incompleta) y se informa en `versiones_incompletas`.
2. **Un fallo de escritura dejaba el archivo temporal o un parcial;** si `os.fdopen` fallaba, el descriptor quedaba abierto. Ahora se borra el temporal y el parcial creado por la propia llamada, y se cierra el descriptor.

## 3. Corrección (`src/eq2/rutas.py`)
- `hay_enlaces_duros()`: detección **explícita** con `callable(getattr(os, "link", None))`, evaluada en cada llamada. No hay ningún `except Exception`.
- **Con `os.link`:** temporal `O_EXCL` + `fsync` + `os.link(temporal, destino)`, que falla si el destino existe. Publicación **atómica**.
  - `FileExistsError` se propaga.
  - Solo los `errno` que significan «sin enlaces duros» (`EPERM`, `EACCES`, `EXDEV`, `EMLINK`, `ENOSYS`, `ENOTSUP`/`EOPNOTSUPP`) pasan a la alternativa.
  - **Cualquier otro error se propaga** (`EIO`, `ENOSPC`, `OSError` sin `errno`...). El temporal se borra siempre.
- **Sin `os.link` (Termux) o sin soporte de enlaces:** creación **exclusiva** del destino con `O_CREAT|O_EXCL|O_NOFOLLOW` + escritura + `fsync`. **Nunca sobrescribe.** `os.replace` y `os.rename` **no** se usan; hay una prueba que lo verifica.
- **Limitación documentada: la alternativa NO es atómica.** Mientras se escribe, otro lector podría ver el archivo incompleto. Si la escritura falla, el parcial se borra. El manifiesto con SHA-256 permite detectar contenido incompleto, y cada versión del proyecto declara `atomico: false` en el informe. En Termux, por tanto, **todas** las escrituras de proyecto serán `atomico: false`.
- Se mantienen la creación exclusiva, `O_NOFOLLOW` y el rechazo de enlaces en cualquier componente de la ruta (`rutas.Laboratorio`).
- **Validador estático:** prohíbe `except:` desnudo, `except Exception` y `except BaseException` en `rutas.py`.

## 4. Otros cambios
- `VERSION = "f2-v2e1-r1"`. **Datos propios:** `datos_v2e1`. `datos_v2e` pasa a «carpeta anterior» y nunca se escribe. El esquema sigue siendo el 5 (sin cambios de tablas).
- **Pruebas heredadas modificadas (justificadas):**
  1. `test_v2e.test_escritura_no_atomica_se_informa`: `create=True` y un `PermissionError` con `errno EPERM`, como el real. Sin `errno` reconocido ya no se acepta como «sin enlaces».
  2. `test_v2e.test_error_de_sintaxis_se_corrige_automaticamente`: comprueba primero el estado final, para que un fallo sea legible y no un `IndexError`.
  3. `test_v2e.test_tarea_simulada_y_supervision`, `test_v2d.test_ciclo_simulado`, `test_v2d.test_deliberacion_sin_modelo_...` y `test_v2b.test_sin_modelo_...`: carpeta `datos_v2e1`.

## 5. Pruebas nuevas (`tests/test_v2e1.py`, 25)
- **Regresión sin `os.link`:** detección, escritura no atómica declarada, prohibición de `os.replace`/`os.rename`, motor completo, proyecto con manifiesto SHA-256 y asesoría.
- **Errores de `os.link`:** cada `errno` aceptado usa la alternativa; `EIO`, `ENOSPC` y sin `errno` se propagan y limpian; carrera en la que otro escritor crea el destino justo antes del enlace; errores no previstos sin disfrazar.
- **Sobrescritura y enlaces, en ambos modos:** archivo existente intacto; enlace a un archivo ajeno; enlace colgante (no se crea el destino ajeno); carpeta existente; `..`; carpeta enlazada; flags `O_EXCL`, `O_CREAT` y `O_NOFOLLOW`, sin `O_TRUNC`.
- **Concurrencia, en ambos modos:**
  - 16 hilos sobre el mismo destino: exactamente 1 gana, 15 reciben `FileExistsError` y el contenido es íntegro, del ganador, sin mezclas.
  - 16 hilos sobre destinos distintos: todos escriben.
  - **6 procesos reales** sobre el mismo destino: 1 gana y 5 son rechazados, con un único autor en el contenido.
- **Limpieza ante errores, en ambos modos:** fallo de codificación, de `fsync`, de `os.fdopen` (descriptor cerrado) y de `os.replace` (original intacto); nunca se borra un archivo ajeno; versión fallida sin temporales y sin bloquear las siguientes.
- **Garantías estáticas:** `rutas.py` sin capturas indiscriminadas, el validador lo impone, Modo B deshabilitado y carpetas correctas.

## 6. Resultados (ejecutados en la sandbox Linux; NO en Termux)
| Comprobación | Resultado |
|---|---|
| Validador estático | 0 problemas |
| Suite completa **con** `os.link` | **487/487 OK** |
| Suite completa **sin** `os.link` (simulación de Termux, incluidos subprocesos) | **487/487 OK** |
| V2-E original sin `os.link` (reproducción) | 462: 18 fallos + 5 errores (como en Termux) |
| Mutaciones (11, en ambos modos) | 10 detectadas; 1 equivalente (F11: convertir la carrera `FileExistsError` en alternativa; `O_EXCL` la vuelve a rechazar) |
| Suite y validador desde el ZIP extraído | ver la respuesta de entrega |

Mutaciones detectadas: no detectar la ausencia de `os.link`; aceptar cualquier `OSError`; alternativa con `os.replace`; sin `O_EXCL`; sin `O_NOFOLLOW`; no borrar el temporal; no borrar el parcial; no cerrar el descriptor; volver a la numeración que bloqueaba versiones; quitar la regla del validador.

## 7. Instalación y pasos en Termux
```
mkdir -p "$TMPDIR/equipo_f2/codigo_v2e1"
cd "$TMPDIR/equipo_f2/codigo_v2e1"
unzip /ruta/a/equipo_f2_v2e1.zip      # crea equipo_f2_v2e1/
cd equipo_f2_v2e1
python3 -B -I validar_estatico.py                                              # 0 problemas
python3 -B -W error::ResourceWarning -X dev -m unittest discover -s tests -p "test_*.py"   # 487
python3 -c "import os; print('os.link:', hasattr(os, 'link'))"              # esperado en Termux: False
```
En Termux, las pruebas «con os.link» de `test_v2e1` ejecutan igualmente el modo sin enlace, porque ahí el atributo no existe. Las pruebas que simulan errores de `os.link` lo crean temporalmente con `create=True`.

## 8. Limitaciones conocidas
- **En Termux la escritura de proyectos no es atómica** (no hay `os.link`): exclusiva y sin sobrescritura, pero un lector concurrente podría ver un archivo a medio escribir. El único lector concurrente previsto es `supervisar.py`, y solo lee `estado_actual.json` (que usa `os.replace`, atómico) y archivos JSONL o informes. El código generado no lo lee nadie mientras se escribe.
- **TOCTOU:** entre `lexists` y la creación hay una ventana; `O_EXCL` la cierra para la creación. El borrado de un parcial tras un fallo supone que nadie ha sustituido ese archivo entretanto (solo posible para un proceso con permisos sobre el laboratorio).
- Las carpetas de versiones incompletas permanecen en disco (no se borran árboles); se identifican por la ausencia de `manifiesto.json`.
- La simulación de Termux en la sandbox solo retira `os.link`. Otras diferencias del dispositivo (rendimiento, señales, `/proc`, SELinux) no se reproducen.
- Sin cambios respecto a V2-E: Modo B deshabilitado, ningún resultado aparece como verificado sin pruebas reales, y siguen los riesgos documentados en `LEEME_V2E.md`.
