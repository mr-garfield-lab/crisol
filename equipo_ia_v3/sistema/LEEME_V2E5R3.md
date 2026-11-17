# Equipo IA — V2-E.5-r3: STOP corregido, verificador integral, paquetes de auditoría y avances funcionales

Copia independiente construida sobre V2-E.5-r2. **Las versiones anteriores no se han modificado**: sus huellas coinciden.
- `MODO_B_HABILITADO = False`.
- No se ejecuta código generado ni código de paquetes.
- Sin dependencias nuevas: solo la biblioteca estándar.
- **No se ha ejecutado nada en Termux, en Windows ni con Qwen.** Toda la evidencia procede de la sandbox Linux con servidores y backends falsos.

## 1. Funcionalidades nuevas (qué funciona y qué no)
| Parte | Estado |
|---|---|
| STOP: causa raíz demostrada y corregida (motor y orquestador), informe `parada` con traza | **Hecho y probado** (`DIAGNOSTICO_STOP.md`) |
| Verificador integral `verificar.py` (14 áreas, marcas de grabación, informes, código de salida, repeticiones) | **Hecho y probado**; incluye pruebas del propio verificador |
| Paquetes de auditoría declarativos (formato `eq2/auditoria` v1, autorización del usuario, registro, ejemplo) | **Hecho y probado**. El código Python de un paquete queda **NO_DISPONIBLE** (no hay aislamiento real) |
| Laboratorios: tipos comunes (hipótesis, decisiones, aprendizajes sustentados) y `Coordinador.comparar` con desacuerdos | **Hecho y probado** (API; el motor aún no escribe en los cuadernos de forma automática) |
| Críticas: categorías `error_demostrado`, `contradiccion`, `sospecha_razonable`, `sin_evidencia` | **Hecho y probado**. «Error demostrado» solo cuando el análisis estático marca la línea citada; en una deliberación sin ejecución nunca lo hay |
| Contrato JSON versionado de personalidad (`contratos/`) | **Solo validación** (`perfiles.py validar-contrato`); no se guarda ni se activa nada |
| Pruebas con Qwen real en el verificador | **Implementadas, sin ejecutar** (`--qwen-real --iniciar-servidor-real`) |
| Windows 10/11 y escritorio Linux | Sin cambios: diseño o sandbox |

## 2. STOP (prioridad crítica)
La causa raíz, el método, las trazas, el cambio y las pruebas están en `DIAGNOSTICO_STOP.md`. En resumen:
- **Causa.** Una parada pedida que interrumpía la **carga del servidor** o una **petición HTTP** llegaba como `ErrorInferencia` y el motor la convertía en `error_critico`. El resultado dependía del instante del STOP.
- **Reproducción.** Con el código antiguo y CPU cargada, la prueba heredada falló 2/25 y 3/40 veces, siempre con `inferencia:stop_usuario`. Con el corregido y la misma carga: 25/25 correctas.
- **Defectos relacionados, también corregidos:**
  - el STOP previo al arranque;
  - el STOP borrado justo después de detectarlo (la parada ahora se retiene);
  - el orquestador, que **ocultaba** fallos reales de arranque si había un STOP.
- **Ahora:**
  - una parada válida termina en `detenido` (motor) o `interrumpida` (orquestador), con su motivo;
  - un fallo independiente sigue siendo un fallo y se clasifica como `fallo_independiente_durante_parada`;
  - una limpieza fallida se informa como `parada_con_fallo_de_limpieza`.
- **Pruebas.** Hay 15 pruebas deterministas permanentes (`tests/test_v2e5r3_stop.py`). Contra el código anterior dan 7 fallos y 7 errores. Comprueban que no quedan procesos, puertos, candados ni temporales.

## 3. Verificador y paquetes
- **Uso:** `python3 -B verificar.py`. Ver `VERIFICADOR.md`.
- **Paquetes:** el formato, las operaciones admitidas, las reglas de seguridad y el flujo de autorización están en `PAQUETES_AUDITORIA.md`.
- **Herramienta para autores:** `herramientas/construir_paquete.py`.

## 4. Archivos (respecto a V2-E.5-r2)
- **Nuevos:**
  - en la raíz: `verificar.py`, `herramientas/construir_paquete.py`;
  - en `src/eq2/`: `paquetes_auditoria.py`;
  - pruebas: `tests/test_v2e5r3_stop.py` (15), `tests/test_v2e5r3.py` (18), `tests/test_verificador.py` (10);
  - `contratos/` (descripción, LEEME y 7 ejemplos);
  - `auditoria_ejemplo/` (fuente y ZIP);
  - documentación: `DIAGNOSTICO_STOP.md`, `VERIFICADOR.md`, `PAQUETES_AUDITORIA.md`, `LEEME_V2E5R3.md`;
  - `MANIFIESTO_SHA256.txt` (huellas de la entrega).
- **Modificados:**
  - `motor.py`: parada correcta, retención de la parada y `parada` en el informe; categorías y errores demostrados por versión;
  - `orquestador.py`: el arranque con STOP ya no oculta fallos; `parada` en el resumen;
  - `inferencia.py`: `parada_de`;
  - `criticas.py`: categorías y demostraciones estáticas;
  - `laboratorios.py`: esquema del cuaderno 2, tipos comunes, aprendizajes y `comparar`;
  - `personalidad.py`: `validar_contrato`;
  - `config.py` y `__init__.py`: `datos_v2e5r3` y `f2-v2e5-r3`;
  - `perfiles.py`: `validar-contrato`;
  - `auditar.py`, `ejecutar_v2.py`, `supervisar.py`: la carpeta;
  - `LABORATORIOS.md`.
- **Pruebas heredadas modificadas:** 24 líneas, **solo** por la carpeta y la versión, marcadas `CAMBIO V2-E.5-r3`. No ha cambiado ninguna aserción de comportamiento, y la prueba intermitente original se conserva **sin cambios**.

## 5. Resultados ejecutados (sandbox Linux, Python 3.13)
| Comprobación | Resultado |
|---|---|
| Validador estático | 0 problemas |
| Suite completa (`unittest`) **con** `os.link` | **828/828 OK**: 785 de r2 + 15 de STOP + 18 de r3 + 10 del verificador |
| `verificar.py` completo en el árbol de trabajo | **157 comprobaciones: 153 OK, 0 FALLO, 1 OMITIDA y 3 NO_VERIFICADAS**, en 241 s |
| `verificar.py` y la suite desde el ZIP extraído, con y sin `os.link` | ver la respuesta de entrega |
| Mutaciones de las protecciones nuevas, contra `test_v2e5r3_stop`, `test_v2e5r3` y `test_verificador` | **38/38 detectadas** en la pasada final |
| Prueba heredada de STOP, 25 veces con la CPU saturada | código anterior: 2 fallos; corregido: 0 fallos |

**Detalle de la ejecución del verificador:**
- **OMITIDA:** no había paquetes externos.
- **NO_VERIFICADAS:**
  - el manifiesto (el árbol de trabajo no lo tiene; el ZIP sí);
  - las 2 pruebas de Qwen real.

**Sobre las mutaciones:**
- **Primera ronda.** Sobrevivieron 3 y una estaba mal definida:
  - un requisito «demostrado» por análisis estático;
  - un desacuerdo con versiones sustituidas;
  - `huella_archivo` con una ruta absoluta y el SHA-256 correcto.

  Se añadieron sus pruebas y la mutación mal definida se corrigió.
- **Pasada final.** Se repitieron las 38: 38/38 detectadas.
- **Qué cubren:**
  - la clasificación de la parada y su retención;
  - el criterio del orquestador;
  - la limpieza y los fallos independientes;
  - las categorías y las demostraciones;
  - el disparador de aprendizajes y cada tipo de desacuerdo;
  - cada regla del contenedor y del manifiesto;
  - la disponibilidad de las operaciones;
  - la autorización por SHA-256;
  - el código de salida y el fallo controlado;
  - la comprobación de huellas;
  - el informe sin núcleo.

## 6. Instalación y validación en un laboratorio Termux (cuando GPT-6 y el usuario lo autoricen)
```
mkdir -p "$TMPDIR/equipo_f2/codigo_v2e5r3" && cd "$TMPDIR/equipo_f2/codigo_v2e5r3"
unzip /ruta/a/equipo_f2_v2e5r3.zip && cd equipo_f2_v2e5r3
python3 -B verificar.py                       # ÚNICO comando: batería completa (≈ 4–10 min)
#   salida 0 = sin fallos; 1 = hay fallos (traza en .../verificacion/<id>/trazas/); 2 = no se pudo preparar
python3 -B verificar.py --repeticiones 10 --solo V-REP      # buscar intermitencias (opcional)
# Solo con autorización explícita (modelo real, un llama-server):
python3 -B verificar.py --solo V-QWEN --qwen-real --iniciar-servidor-real
```
- Los informes quedan en `$TMPDIR/equipo_f2/verificacion/<id>/informe.json` e `informe.md`.
- Para compartir los resultados con GPT-6, basta con el `informe.json` y la carpeta `trazas/`.
- **Importante:** usa siempre `python3 -B`. Si aparece `V-INT-02 FALLO` por `__pycache__`, lo creó una ejecución sin `-B`. Se puede borrar esa carpeta `__pycache__` del paquete (no contiene datos) y volver a verificar.

## 7. Errores corregidos y pendientes
- **Corregidos:**
  - STOP intermitente: causa raíz demostrada;
  - STOP antes del arranque;
  - carrera de STOP borrado;
  - ocultación de fallos de arranque con STOP;
  - nombre de disparador repetido (en r2).
- **Pendientes:**
  - validación en Termux;
  - Qwen real;
  - Windows;
  - aislamiento real para pruebas con código de paquetes;
  - firma de paquetes;
  - escritura automática del motor en los cuadernos;
  - uso del perfil en los prompts (decisión aparte);
  - traza fina de parada en el orquestador.

## 8. Recomendaciones para V2-E.6
1. **Ejecutar `verificar.py` en Termux** y enviar `informe.json` a GPT-6. Si GPT-6 necesita más comprobaciones, que prepare un paquete declarativo.
2. **Calibrar el clasificador de críticas** con revisiones reales etiquetadas, a través de un paquete `clasificar_criticas`.
3. **Integración mínima de los cuadernos en el motor:** solo registro de objeciones clasificadas y resultados simulados.
4. **Diseñar el aislamiento real** necesario para paquetes con código, antes de habilitarlos. Hasta entonces, solo paquetes declarativos.
