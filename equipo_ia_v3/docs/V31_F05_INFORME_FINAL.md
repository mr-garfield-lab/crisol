# Equipo IA V3.1 — F0.5 (portabilidad a Windows): informe final

**Fecha:** 2026-11-10 · **Plataforma probada:** Windows 11 Pro 10.0.26200, Python 3.12.10 (Ryzen 5 5600GT, 31 GB, RTX 3050 8 GB)
· **Autor del trabajo:** Claude Code · **Base:** paquete V3 Etapa 8 (`EquipoIA_V3_1.zip`, SHA-256 `d0b8d37e…4f76`).

> **Resumen (cierre, 2026-11-11).** F0.5 está **CERRADA en Windows nativo**. `verificar_v3.py --completo`:
> **14 de 14 fases correctas**; F11 **503 de 503 pruebas iguales** a la línea base de Windows, con **0 bloqueantes**.
> V2-F.1 (`sistema/`, sin modificar) pasa **193 de 264** comprobaciones de su verificador (al empezar, **145**), y
> **cada una** de las diferencias que quedan con Linux tiene una causa de plataforma demostrada. El fallo funcional
> de etiqueta (V-SRV-12, V-UNI-23) se corrigió con un adaptador autorizado (§10). Linux/WSL2 y Termux siguen sin
> probar con V3.1.
>
> Las secciones 2–9 describen el estado del 2026-11-10 (antes del cierre); los cambios están en §10.

## 1. Qué se pidió y qué restricciones se respetaron

Objetivo: que Equipo IA V3.1 funcione en **Windows nativo** (plataforma principal) y en Linux/WSL2 (segunda plataforma),
con un solo motor, sin reconstruir el proyecto, y preparar después el laboratorio de aprendizaje (F1–F6).

| Restricción | Cumplimiento |
|---|---|
| No modificar `sistema/` (V2-F.1) | **Cumplida.** F0 lo comprueba: 233 archivos, 0 distintos, 0 ajenos |
| No instalar ni descargar software, modelos, Docker ni WSL2; no usar APIs de pago | **Cumplida** |
| No ejecutar código generado por agentes | **Cumplida.** Solo las suites del proyecto con agentes SIMULADOS. El ejecutor restringido solo se probó con un espacio VACÍO |
| No debilitar protecciones ni ocultar fallos | **Cumplida.** Ver §6; las 3 diferencias no aceptadas siguen bloqueando |
| No simular memoria | **Cumplida.** Solo mediciones reales de Windows; lo que Windows no mide queda ausente (§4.3) |
| No iniciar F1 sin aprobación | **Cumplida** |

## 2. Resultado por fases (verificador integral `verificar_v3.py` en Windows)

| Fase | Resultado |
|---|---|
| F0 integridad de `sistema/` | OK |
| F1 pruebas de la herramienta de línea base (`v3/tests`) | OK (ver ejecución final, §8) |
| F2 pruebas de eq3 (`pruebas/`) | OK, con 4 pruebas OMITIDAS por falta del privilegio de symlinks de archivo |
| F3–F10 mutaciones por etapa | Todas detectadas; 1 OMITIDA (etapa 6 M8, necesita symlinks de archivo) |
| F12 mutaciones de los adaptadores de plataforma | **18/18** detectadas |
| F13 mutaciones de uniones de directorio | **3/3**: demuestra que el `is_symlink()` original de V3 dejaba pasar las uniones de Windows |
| F11 línea base (503 pruebas, V2-F.1 + codex + Contexto Ligero) | Con la línea base de Windows: **500 IGUAL, 3 bloqueantes** (§5) |

## 3. Evolución de F11 en Windows (comprobaciones OK del verificador de V2-F.1, de 264)

| Ejecución | Cambio introducido | OK | Diferencias con Linux (todas las suites) |
|---|---|---|---|
| 1 | Adaptadores básicos (entorno, enlaces, LF en el primer proceso) | 145 | 216 |
| 2 | UTF-8 y LF en **toda** la cadena de procesos hijo | 177 | 183 |
| 3 | `~` desde `HOME` (como en Linux) y ruta temporal corta | 181 | 179 |
| 4 | **Memoria real de Windows** para la vigilancia de V2-F.1 | **192** | 168 → **3 sin aceptar** tras clasificar |

Ninguna ejecución introdujo una regresión nueva.

## 4. Problemas encontrados, causa raíz y solución

### 4.1 Corregidos con adaptadores (sin tocar `sistema/`)

Todo está en `eq3/plataforma.py` y `eq3/lanzador_eq2.py`; en Linux y Termux nada cambia.

| Problema en Windows | Causa raíz | Adaptador | Prueba / mutación |
|---|---|---|---|
| El verificador y las pruebas se caían (`UnicodeDecodeError`) | Hijos en cp1252, padre en UTF-8 | `entorno_hijo` + `-X utf8` en toda la cadena | `test_eq3_plataforma`; M3, M12 |
| Los hashes declarados por V2-F.1 no coincidían con sus archivos | Escribe en modo texto sin `newline` → CRLF en Windows | Lanzador: escritura de texto con «\n» | M7 |
| `~` era el perfil REAL del usuario en los procesos hijo | Windows usa `USERPROFILE`, no `HOME` | `USERPROFILE`/`TEMP`… = carpeta temporal | M2 |
| El modelo falso de V2-F.1 no se encontraba (comprobaciones del servidor) | Python 3.8+ ignora `HOME` en Windows | `~` desde `HOME` si está definida | M15 |
| **Uniones de directorio atravesaban las defensas de eq3** (seguridad) | `is_symlink()` no ve las uniones; `os.walk` entra en ellas | `es_enlace` (symlinks + puntos de reanálisis) | F13 (3/3), M1 |
| El grafo no indexaba nada | Contexto Ligero exige `dir_fd`/`O_NOFOLLOW` | `leer_acotado` (mismas reglas + flujos NTFS + inodo) | M4–M6, M10 |
| **El monitor de V2-F.1 abortaba TODA sesión** («sin_medicion_MemAvailable») | Lee `/proc/meminfo`, que no existe en Windows | Mediciones REALES de Windows en ese formato (§4.3) | M16–M18 |
| Pruebas y espejos de mutación fallaban (WinError 1314) | Symlinks sin privilegio | Uniones o copias; si no se puede, OMITIDA con motivo | — |
| Otros | SQLite abierto en una prueba, rutas POSIX en firmas, `/tmp`, ruta larga | Cierre explícito, normalización, `gettempdir`, ajuste de la prueba | — |

### 4.2 Causas demostradas de las diferencias que quedan (aceptadas en la línea base de Windows)

`v3/linea_base_plataforma.py` (modo estricto) acepta una diferencia solo si **cada fallo individual** de sus
subpruebas tiene una regla de `v3/causas_windows.json`, con su firma en la evidencia de ese fallo. La evidencia viene
de la traza del verificador o de mediciones por prueba (`*_MEDIDO`, obtenidas con instrumentos que solo registran).

| Causa | Tipo | Diferencias | Cómo se demostró |
|---|---|---|---|
| `WIN_CL_LECTURA_POSIX` (Contexto Ligero original) | Inevitable en el módulo original | 117 | **Contrafactual**: con la lectura de eq3, cada prueba vuelve al estado de Linux |
| `WIN_EJECUTOR_SIN_RESOURCE` | Inevitable; **fallo cerrado correcto** | 13 | **Medido por prueba**: cada invocación del ejecutor restringido termina con `No module named 'resource'` antes de ejecutar nada |
| `WIN_ENLACE_SIN_PRIVILEGIO` | Inevitable (sin modo de desarrollador) | 11 | WinError 1314 en cada fallo |
| `WIN_ARCHIVO_ABIERTO` (+ `WIN_TEMPORALES_ABIERTOS`) | Inevitable | 7 + 1 | WinError 32; las carpetas sin borrar contienen solo `server.log` |
| `WIN_SIGINT_PROPIO` | Inevitable (semántica de señales) | 5 | `os.kill(getpid(), SIGINT/SIGTERM)` termina el proceso: rc=2 / rc=15, medido aislando las pruebas |
| `WIN_SIN_SIGKILL` | Inevitable | 3 | No existe SIGKILL; `terminate()` es `TerminateProcess` (cierre en ~0,01 s, el manejador lento nunca se ejecuta) |
| `WIN_SIN_MAJFLT` | Inevitable; comportamiento honesto | 3 | Con memoria real, V2-F.1 marca «no concluyente» porque Windows no da fallos de página mayores (medido por petición) |
| `WIN_PLATAFORMA_DETECTADA` | Aserción de Linux | 2 | V2-F.1 detecta Windows correctamente |
| `WIN_CANDADO_SIN_PID_VIVO` | Fallo cerrado correcto | 1 | Experimento directo: `AdaptadorWindows.pid_vivo` → `NoSoportado`; nunca da un candado por obsoleto |
| `WIN_RUTA_LARGA` | Inevitable | 1 | WinError 267 |
| `OMITIDO_V2F1` (+ `WIN_ZIP_BARRA`) | Material omitido (igual que en Linux) + diferencia de `zipfile` | 1 | Experimento directo: en Windows `zipfile` convierte «\» en «/»; los nombres peligrosos siguen rechazados |

### 4.3 La lectura de memoria real: por qué no es una simulación y qué garantías conserva

- **Qué hace.** Solo en Windows, y solo al LEER «/proc/meminfo» o «/proc/<pid>/status» (rutas que no existen en
  Windows), devuelve `MemAvailable` (GlobalMemoryStatusEx) y `VmRSS`/`VmHWM` (GetProcessMemoryInfo).
- **Valores reales.** Una prueba comprueba, en un proceso real, que el valor coincide con la API de Windows.
- **Nada inventado.** `majflt`, `minflt`, `RssAnon`, `RssFile` y `SwapFree` siguen ausentes (prueba + M18), y por eso
  V2-F.1 marca esas peticiones como «no concluyentes».
- **Falla cerrado.** Si la API falla, se abre la ruta real, que no existe: V2-F.1 se queda sin medición y aborta,
  exactamente como sin adaptador (prueba + M17).
- **STOP intacto.** El mecanismo de STOP no se tocó. Con memoria real, las pruebas de STOP de V2-F.1 pasan, igual que
  las de memoria baja (`test_memoria_baja_*`) y la de aborto sin medición (`test_sin_medicion_de_memoria_aborta`).

## 5. Lo que NO se acepta (visible y bloqueante)

> **Resuelto en el cierre (§10):** V-SRV-12 pasa; V-UNI-23 queda solo con `WIN_SIN_SIGKILL`; V-CUM-03 se acepta
> porque ya no queda nada pendiente. La tabla siguiente es el estado anterior.

| Comprobación | Causa demostrada | Por qué no se acepta |
|---|---|---|
| V-SRV-12, V-UNI-23 | `WIN_FUNCIONAL_CONEXION_RESET`: si el servidor muere a mitad de petición, Windows entrega `ConnectionResetError` (Linux, fin de datos), y V2-F.1 informa «conexion_perdida» en lugar de «servidor_muerto» | Es un **fallo funcional** de V2-F.1 en Windows: la sesión se detiene igual, pero la etiqueta del informe es incorrecta. Corregirlo exige cambiar V2-F.1 o un adaptador que reclasifique (decisión pendiente) |
| V-CUM-03 | Resumen de cumplimiento (agregado de las demás) | Solo se aceptaría si no quedara nada pendiente; quedan las dos anteriores |

Se comprobó que la puerta de regresión de Windows marca **exactamente** estas 3 (`_experimentos/comprobar_puerta.py`).

## 6. Seguridad: comprobaciones de que los adaptadores no debilitan nada

| Protección | Evidencia |
|---|---|
| SEG-01 / ejecutor restringido | El lanzador NO se interpone en órdenes `-S` (M13). En Windows el ejecutor falla cerrado. No se habilitó ninguna ejecución de código generado |
| Integridad SHA-256 | Ninguna comprobación se relajó. Con LF, los archivos coinciden byte a byte con lo declarado; eq3 sigue comparando hashes reales (F4 12/12) |
| Enlaces y uniones | `es_enlace` en `ingesta`, `cambios`, `perfiles_pc` y `empaquetar` (F13 3/3, M1). El empaquetado rechaza enlaces (F10) |
| Carpeta personal | Hijos con `~` temporal (M2); `HOME` solo cuando V2-F.1 la fija (prueba dedicada) |
| Órdenes ajenas | `llama-server` y cualquier otro ejecutable pasan sin cambios (M14) |
| Memoria | Solo datos reales, nada inventado y fallo cerrado si no hay medición (M16–M18) |
| Línea base | La de Linux no se modificó. La de Windows solo contiene diferencias con causa y evidencia; lo no explicado y lo funcional siguen bloqueando |

## 7. Limitaciones y lo que queda

1. **Linux/WSL2 y Android/Termux no se han ejecutado con V3.1** (aquí no hay WSL2 y no estaba autorizado
   instalarlo). Por diseño se comportan como V3 (entorno, órdenes y firmas idénticos fuera de Windows), pero no se
   declaran compatibles hasta ejecutar `verificar_v3.py --completo` en cada uno.
2. **Fallo funcional `WIN_FUNCIONAL_CONEXION_RESET`** (§5): requiere una decisión.
3. **Sin privilegio de symlinks de archivo:** 4 pruebas y 1 mutación OMITIDAS. Con el modo de desarrollador se
   ejecutarían.
4. **Ejecutor restringido de V2-F.1:** no funciona en Windows (`resource`). Es deliberado no adaptarlo: la ejecución
   real de código debe llegar con aislamiento real (F3), no relajando este ejecutor.
5. **Contadores de memoria:** Windows no ofrece `majflt`; las peticiones salen «no concluyentes» en Windows. Si se
   quiere otro criterio para Windows, debe decidirse explícitamente en V2-F.1 o en eq3 (no se ha hecho).
6. **Ejecución con Qwen real:** no realizada (F1 pendiente de aprobación).

## 8. Recomendaciones para continuar

1. **Decidir sobre `WIN_FUNCIONAL_CONEXION_RESET`:**
   - (a) un adaptador que, en Windows, trate `ConnectionResetError` con el hijo muerto como «servidor_muerto»;
   - (b) corregirlo en V2-F.1 con una línea base nueva;
   - (c) aceptarlo documentado. Recomendación: (a), con prueba y mutación.
2. **Validar en Linux/WSL2** cuando se autorice instalar WSL2: `python3 -B verificar_v3.py --completo` debe dar la
   línea base de Linux intacta.
3. **F1 (modelo local):** seguir `docs/V31_PLAN_ACTIVACION_F1.md`. La recomendación es Qwen2.5-Coder-7B-Instruct
   Q4_K_M entero en la GPU, con un solo `llama-server` en `127.0.0.1` lanzado por el usuario.
4. **F3 (aislamiento):** Windows Sandbox (activarlo lo hace el usuario) o WSL2 + bubblewrap/Docker, con pruebas canario
   antes de cada sesión.
5. **Mejoras posibles, no realizadas:**
   - un criterio explícito para `majflt` en Windows;
   - pruebas de `es_enlace` en `perfiles_pc` con uniones;
   - integrar las herramientas de diagnóstico (`evidencias/v31_f05/diagnostico/`) como orden del proyecto.

## 9. Dónde está cada cosa

| Elemento | Ruta (en el paquete) |
|---|---|
| Adaptadores | `eq3/plataforma.py`, `eq3/lanzador_eq2.py` |
| Pruebas nuevas | `pruebas/test_eq3_plataforma.py`, `v3/tests/test_linea_base_plataforma.py` (más cambios en las pruebas existentes) |
| Mutaciones nuevas | `v3/mutaciones/v31_plataforma.json` (18), `v3/mutaciones/v31_uniones.json` (3) |
| Línea base de Windows | `v3/linea_base_esperada_windows.json`, `v3/causas_windows.json`, generadas con `v3/linea_base_plataforma.py` |
| Evidencias y diagnóstico | `evidencias/v31_f05/` (registros, contrafactuales, evidencia medida y scripts de diagnóstico) |
| Informes anteriores de F0.5 | `docs/V31_F05_PORTABILIDAD.md`, `docs/V31_PLAN_ACTIVACION_F1.md`, `docs/V3_1_PLAN.md` |
| Registro de cambios frente al ZIP original | `evidencias/v31_f05/registro_cambios.md` |

## 10. Cierre de F0.5 (2026-11-11): corrección de V-SRV-12 / V-UNI-23 y estabilidad de la puerta

Autorizado por el usuario: un adaptador **exclusivo de Windows** que reclasifica «conexion_perdida» como
«servidor_muerto» **solo con evidencia de que el proceso del servidor terminó**.

### 10.1 El adaptador

| Aspecto | Cómo se cumple |
|---|---|
| Dónde | `eq3/lanzador_eq2.py`: `con_servidor_muerto`, `servidor_terminado`, `BuscadorBackend`. Se aplica al importar `eq2.backend_llama` (el archivo de `sistema/` se carga con su cargador real, sin cambios) |
| Cuándo reclasifica | Solo si el motivo empieza por `conexion_perdida:` **y** el proceso del servidor tiene código de salida (espera de 0,5 s, la misma que usa V2-F.1 en `servidor.murio_pronto`) |
| Cuándo NO | Servidor vivo, sin proceso, estado indeterminado (cualquier error al consultarlo) o cualquier otro motivo: STOP, señal, plazo agotado, presión de memoria, `respuesta_truncada`, `http_500`, `envio_fallido`… Ni siquiera se consulta el proceso |
| STOP, memoria, aislamiento | Sin cambios. El error era fatal y sigue siéndolo: la sesión se detiene igual. Una prueba comprueba que `iniciar`, `detener`, `supervisar`, `_deberia_parar` y `cliente_http.peticion` no se tocan |
| Linux y Termux | Sin cambios: el adaptador solo se instala con `os.name == "nt"` (comprobado por prueba) |
| Línea base de Linux | Sin cambios (`v3/linea_base_esperada.json`) |

**Pruebas** (`pruebas/test_eq3_plataforma.py`, clase `TestServidorMuerto`, procesos REALES):

- *Positivas:* proceso terminado → `servidor_muerto`, fatal, registro de la petición actualizado y error original
  en la traza; proceso que termina dentro de la espera.
- *Negativas:* servidor vivo → `conexion_perdida` (y el proceso sigue vivo, sin tocar); sin proceso, consulta que
  falla, sin código de salida, objeto que no es un proceso, sin servidor → `conexion_perdida`; nueve motivos ajenos
  (incluidos `stop_usuario` y `senal`) con el servidor muerto → sin cambios y sin consultar el proceso.
- *De punta a punta:* la prueba de V2-F.1 que fallaba (`test_v2_backend…test_servidor_muere_durante_la_peticion`)
  ejecutada a través del lanzador pasa.

**Mutaciones** (`v3/mutaciones/v31_plataforma.json`): M19 adaptador sin conectar · M20 reclasificar sin comprobar el
proceso · M21 dar por muerto un servidor vivo · M22 reclasificar cualquier motivo (STOP incluido) · M23 que deje de ser
fatal. **23/23 detectadas** (las 18 anteriores + estas 5).

### 10.2 Resultado en F11 (ejecución 5)

| Comprobación | Antes | Ahora |
|---|---|---|
| V-SRV-12 | FALLO (`conexion_perdida`) — bloqueante | **OK** |
| V-UNI-23 | FALLO (2 subpruebas: etiqueta + SIGKILL) — bloqueante | FALLO solo por `WIN_SIN_SIGKILL` (causa de plataforma ya catalogada) — **no bloquea** |
| V-CUM-03 | Bloqueado por las dos anteriores | Aceptado por la regla de agregado **solo porque no queda nada sin explicar** (no se tocó la regla) |

El verificador de V2-F.1 pasa **193 de 264** (antes 192). La regla `WIN_FUNCIONAL_CONEXION_RESET` se conserva como
centinela con `bloquea: true`: si el adaptador dejara de funcionar, la diferencia volvería a bloquear.

Línea base de Windows regenerada **sin `--parcial`** (modo estricto: sin una sola diferencia sin explicar, no se
escribe): **0 bloqueantes**. La anterior se conserva en
`evidencias/v31_f05/linea_base_esperada_windows_anterior_3_bloqueantes.json`.

### 10.3 Problemas de estabilidad descubiertos al repetir F11, y su corrección

Comparar la ejecución 5 con la 4 (`diagnostico/comparar_ejecuciones.py`) mostró diferencias que **no** venían del
adaptador. Ninguna cambia un estado (OK/FALLO/ERROR); todas son de la firma con que la puerta identifica un fallo:

| Problema | Causa | Corrección (`v3/linea_base.py`, `normalizar`) | Prueba |
|---|---|---|---|
| 2 firmas de Contexto Ligero cambiaban en cada ejecución | Nombre temporal aleatorio `ctx33_integracion_XXXXXXXX` | Se sustituye por `<X>`, como los demás temporales | `test_normalizar_firmas_que_cambian_entre_ejecuciones` |
| 5 firmas citaban un elemento distinto de un conjunto en cada ejecución | Orden de iteración de conjuntos (los corredores usan `-I`, que ignora `PYTHONHASHSEED`) | Se quita solo el elemento citado; tipo de fallo y sentido de la diferencia se conservan | ídem |
| 1 firma dependía de la carpeta del proyecto | unittest abrevia (`[N chars]`) y parte la ruta real | Se quita el resumen abreviado; se conserva la última línea del diff | `test_normalizar_firma_que_no_depende_de_la_carpeta_del_proyecto` |
| `--completo` fallaba en F11 en Windows | Su carpeta de salida es larga y el verificador de V2-F.1 anida ~170 caracteres más (WinError 267) | `linea_base.py` rechaza en Windows una salida de más de 48 caracteres; `verificar_v3.py` le da una corta | `test_windows_rechaza_una_salida_demasiado_larga_para_el_verificador` |
| F7 de `--completo` falló una vez con `WinError 5` | Acceso denegado esporádico al crear un enlace del espejo de mutación | `replicar_solo_lectura` copia también ante WinError 5 (si no quedó nada a medias); cualquier otro error sigue fallando | `test_replicar_con_acceso_denegado_copia_y_otros_errores_no_se_ocultan` |

Además, `linea_base_plataforma.py` ahora **sustituye las rutas de la máquina** (`<SALIDA>`, `<CASA>`, `<TRABAJO>`) en
la línea base y su revisión, y **rechaza** escribirla si alguna FIRMA dependiera de ellas (2 pruebas nuevas).

**Atajo declarado.** Tras corregir las firmas no se repitió F11 entera (20 min), sino solo «contexto» (12 s), y se
combinó con la ejecución 5 (`diagnostico/componer_ejecucion.py`, que exige los mismos estados prueba a prueba y que
la normalización no cambie firmas de las otras suites). La comprobación independiente de las 503 pruebas es la F11
de `--completo` (§10.4). Una repetición extra de codex + contexto dio 239/239 IGUAL.

### 10.4 Verificador integral `--completo`

Ejecución `20261111T065837_086389Z` (Windows 11, Python 3.12.10, prioridad baja, sin nada más en paralelo):

| Fase | Resultado |
|---|---|
| F0 integridad de `sistema/` | OK — 233 presentes, 0 distintos, 0 ajenos |
| F1 herramienta de línea base | OK |
| F2 pruebas de eq3 | OK (4 OMITIDAS: symlinks de archivo) |
| F3–F10 mutaciones por etapa | 9/9 · 12/12 · 6/6 · 12/12 · 10/10 · 9/9 · 8/8 (1 OMITIDA) · 7/7 |
| F12 adaptadores de plataforma | **23/23** |
| F13 uniones de directorio | 3/3 |
| F11 línea base completa | **503 IGUAL**, 0 regresiones, 0 cambios (1105 s) |
| **Total** | **14 de 14 fases correctas, ESTADO GENERAL: CORRECTO** (2406 s) |

Además, esta F11 completa e independiente coincide **prueba a prueba** (estado y firma) con la ejecución compuesta
de §10.3 (`comparar_ejecuciones.py`: 0 diferencias): la corrección de firmas es estable entre ejecuciones.

Un intento anterior (`20261111T004800_651882Z`) se interrumpió: F7 falló por el `WinError 5` descrito en §10.3 (se
conserva el registro en `evidencias/v31_f05/cierre_intento1_F7_WinError5.log`) y la sesión terminó antes de acabar.

Evidencias del cierre: `evidencias/v31_f05/cierre_*` (registro del verificador, `informe.json`, F11, estados,
revisión de la línea base, evidencia medida, contrafactual de Contexto Ligero, mutaciones).

### 10.5 Lo que sigue pendiente (sin cambios respecto a §7)

- Linux/WSL2 y Android/Termux no se han ejecutado con V3.1.
- Ejecutor restringido de V2-F.1 en Windows: falla cerrado (`resource`); la ejecución de código generado sigue
  bloqueada hasta F3.
- Sin privilegio de symlinks de archivo: 4 pruebas y 1 mutación OMITIDAS.
- Nada probado con un modelo real; F1 no iniciada.
