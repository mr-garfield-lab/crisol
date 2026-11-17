# Diagnóstico del STOP intermitente (`test_stop_durante_la_tarea`), V2-E.5-r3

Todo lo que aparece aquí se ejecutó en la sandbox Linux, con el servidor **falso** de las pruebas. **No se ha reproducido en Termux.** La explicación es compatible con lo que se observó allí (equipo más lento), pero no se ha comprobado en ese dispositivo.

## 1. Síntoma
La prueba heredada escribe `STOP` con un temporizador de 1 s mientras el motor trabaja contra un servidor falso. Cada respuesta tarda 0,4 s y la carga del servidor 0,3 s.
- Unas veces termina en `detenido`/`stop_usuario`.
- Otras termina en `error_critico`.

## 2. Método: instrumentación temporal (no se entrega)
Un guion de investigación, fuera del paquete, envolvió con marcas `time.monotonic()`, número de orden e hilo estas funciones:
- `BackendLlama.iniciar`, `.completar` y `.detener`;
- `ServidorLlama.esperar_listo`;
- `cliente_http.peticion`;
- `Motor._fin`;
- la primera detección de `Motor._motivo_parada`.

Después se barrió el instante del STOP entre 0,0 y 3,9 s.

**Antes de la corrección** (motor de V2-E.5-r2):

| Instante del STOP | Resultado |
|---|---|
| 0,1–0,3 s (servidor cargando) | `error_critico` — `inferencia:abortado_durante_carga:stop_usuario` |
| 0,4–1,6 s (entre pasos) | `detenido` — `stop_usuario` |
| ≥ 1,7 s (la tarea ya había terminado) | `sin_verificar` |

**Con una petición larga** (pausa de 2 s), un STOP a 1,0, 1,5 o 2,5 s, con la petición HTTP en curso, termina **siempre** en `error_critico` — `inferencia:stop_usuario`. Traza real (extracto; el instante está en segundos desde el inicio):
```
(21, 0.368, MainThread, ENTRA http.peticion)
(22, 1.001, Thread-1,   STOP_ESCRITO)
(23, 1.370, MainThread, PARADA_DETECTADA stop_usuario)
(24, 1.370, MainThread, EXCEPCION http.peticion ErrorHTTP stop_usuario)
(25, 1.370, MainThread, EXCEPCION backend.completar ErrorInferencia stop_usuario)
(26, 1.370, MainThread, MOTOR._fin error_critico inferencia:stop_usuario)
(27, 1.370, MainThread, ENTRA backend.detener)
```

## 3. Causa raíz (demostrada)
Una parada **pedida** que interrumpe una operación del backend no llega al motor como «parada». Hay dos formas:
- `cliente_http.peticion` comprueba `deberia_parar` cada 0,5 s y, si hay STOP, lanza `ErrorHTTP("stop_usuario")`.
- `esperar_listo` lanza `abortado_durante_carga:stop_usuario`.

En los dos casos el backend lo convierte en `ErrorInferencia`. `Motor._ejecutar_con_backend` traducía **todo** `ErrorInferencia` en `error_critico`.

Que un STOP termine en `detenido` o en `error_critico` dependía solo de **dónde caía** respecto a las operaciones:
- entre dos pasos lo detecta `_limites` y termina en `detenido`;
- durante la carga o durante una petición termina en `error_critico`.

En un equipo rápido el STOP de 1 s suele caer entre dos pasos. En uno lento o cargado (Termux) cae más a menudo durante una carga o una petición.

**Reproducción de la intermitencia.** Prueba heredada con el código antiguo, con 2 núcleos ocupados por 6 procesos `yes`:

| Ejecuciones | Fallos | Motivo |
|---|---|---|
| 25 | 2 | — |
| 40 | 3 | `('inferencia:stop_usuario', ['GENERAR'], 2)`, es decir, el STOP cayó en la 2.ª petición |

**Con el código corregido y la misma carga:** 25 de 25 correctas.

## 4. Defectos relacionados encontrados y corregidos
1. **STOP antes de lanzar el servidor** (archivo STOP previo): terminaba en `error_critico` (`parada_antes_de_lanzar:stop_usuario`).
2. **Carrera de STOP borrado.** Si el usuario borraba STOP justo después de que el backend lo detectara, el motor ya no lo veía y el resultado era `error_critico`. Ahora la primera parada detectada **se retiene**.
3. **Orquestador.** «La parada pedida manda sobre el fallo» convertía **cualquier** fallo de arranque en `interrumpida/stop_usuario` si existía STOP. Así se **ocultaba** un fallo real, por ejemplo `servidor_murio_al_arrancar_rc_1`.

## 5. Cambio realizado (mínimo)
- **`inferencia.parada_de(motivo)`.** Reconoce **solo** las formas exactas `stop_usuario` y `senal`, y `abortado_durante_carga:<parada>` y `parada_antes_de_lanzar:<parada>`. Nunca usa subcadenas: `servidor_muerto`, `plazo_agotado`, `http_500` y `x:stop_usuario` no son paradas.
- **Motor.** Un `ErrorInferencia` se trata como parada **solo si** su motivo es una de esas formas **y** el motor detectó una parada. Si se cumple, termina en `detenido` con su motivo. Cualquier otro error sigue siendo `error_critico`.
- **Informe del motor.** Cada informe incluye `parada` con estos campos:
  - `solicitada`, `motivo`;
  - `punto`: `antes_de_lanzar`, `carga_servidor`, `peticion_http` o `entre_pasos:<estado>`;
  - `error_que_la_materializo`, `fallos_independientes`;
  - `clasificacion`: `parada_limpia`, `parada_con_fallo_de_limpieza`, `fallo_independiente_durante_parada` o `sin_parada`;
  - `traza`, con orden y marcas monotónicas de solicitud, detección, error, inicio y fin de `detener` y estado final.
- **Orquestador.** La parada solo «manda» si es lo que interrumpió el arranque. Si no, informa `backend_no_inicia:<fallo>` y `parada.clasificacion = fallo_independiente_durante_parada`. El resumen de la sesión incluye siempre `parada`.
- **Lo que no se ha hecho:** convertir indiscriminadamente los errores en `detenido`. Una limpieza fallida no cambia el estado `detenido`, pero se informa como fallo independiente.

## 6. Pruebas de regresión permanentes (`tests/test_v2e5r3_stop.py`, 15 pruebas)
Son deterministas: el STOP se coloca con ganchos en el punto exacto, sin temporizadores.

| Prueba | Comprueba |
|---|---|
| clasificación de motivos | formas exactas y rechazo de subcadenas |
| antes de empezar | no se lanza ningún proceso |
| durante la carga | la parada se materializa como `abortado_durante_carga` |
| durante una petición HTTP en curso | el servidor falso tarda 30 s; la parada no espera la respuesta |
| señal durante una petición | la parada llega por `senal` |
| entre dos pasos | detección por `_limites` |
| STOP borrado justo después de detectarlo | la parada retenida sigue valiendo |
| parada repetida | STOP + señal + señal + STOP; después, otra ejecución con STOP previo |
| STOP después de terminar | no cambia el resultado |
| fallo de limpieza | se informa sin cambiar la parada |
| fallo independiente durante la parada | `servidor_muerto` con STOP presente: `error_critico` y clasificación `fallo_independiente_durante_parada` |
| motivo «stop_usuario» sin parada detectada | sigue siendo `error_critico` |
| orquestador | durante una petición, durante la carga, y fallo de arranque con STOP presente |

**Restos.** Cada prueba comprueba que no quedan:
- el proceso hijo;
- el puerto;
- el candado `lock/`;
- temporales `.tmp_*`.

**Prueba de que habrían detectado el defecto.** Se ejecutaron contra el motor y el orquestador de V2-E.5-r2:
- **7 fallos.** Entre ellos:
  - `('error_critico', 'inferencia:abortado_durante_carga:stop_usuario') != ('detenido', 'stop_usuario')`;
  - `('error_critico', 'inferencia:stop_usuario') != ...`;
  - `('error_critico', 'inferencia:parada_antes_de_lanzar:stop_usuario') != ...`;
  - `'stop_usuario' != 'backend_no_inicia:servidor_murio_al_arrancar_rc_1'`.
- **7 errores**, por la falta del campo `parada`.

## 7. Repeticiones
El verificador (`verificar.py`, área 13) repite la batería de STOP y la prueba heredada en cada ejecución (`--repeticiones N`).

**Diez o cien ejecuciones correctas no demuestran la ausencia de errores.** Las pruebas deterministas son la evidencia principal; las repeticiones solo sirven para buscar intermitencias que no estén previstas.

## 8. Qué sigue pendiente
- **Termux.** Falta la confirmación en el dispositivo; el verificador lo ejecutará allí.
- **Estado del backend.** El orquestador, al detener, no registra la traza fina de la parada como hace el motor: solo la clasificación. Se puede ampliar si GPT-6 lo considera necesario.
