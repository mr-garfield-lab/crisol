# Equipo IA — Fase 2, V2-E — ENTREGA PARA AUDITORÍA

**Estado: NO se ha ejecutado el modelo real, ni llama-server, ni nada en Termux con este código.**
Todo lo «ejecutado» fue en una sandbox Linux x86 con agentes y ejecutores SIMULADOS y un llama-server FALSO.
**El sistema NO puede ejecutar código generado de forma segura**: no se ha demostrado ningún aislamiento y el Modo B está deshabilitado.

Arquitectura detallada: `ARQUITECTURA_V2E.md`. Plan para Windows 11: `MIGRACION_WINDOWS.md`.

## 1. Análisis de V2-D e incompatibilidades (resumen)
1. **Votación:** el reintento de A3 por `razon_demasiado_larga` recibía el recordatorio genérico; ahora recibe uno con el límite exacto. Además, los 3 votos empezaban con mensajes de sistema distintos y llama-server no podía reutilizar la caché del prompt.
2. **Contexto 2048 principal:** es el valor por defecto **del ejecutable**; la biblioteca mantiene 1024 para que las 399 pruebas heredadas sigan valiendo. Hay pruebas específicas con 2048.
3. **Pruebas aisladas en Termux:** no es posible con garantías (sin root no hay namespaces, cgroups ni seccomp configurables; proot no es una barrera). Modo B deshabilitado; en su lugar, **análisis estático** sin ejecución.
4. **Escritura atómica del estado para la supervisión:** requirió permitir `os.replace`/`os.link` **solo en `rutas.py`** (antes estaban prohibidos en todo el código).
5. **Esquema 4 compartido con V2-D:** se sube a **5** (mismas tablas) para que la biblioteca también rechace `datos_v2d`.
6. **Asesoría externa:** no hay integración automática; solo exportación e importación manual.

## 2. Qué hay nuevo
| Prioridad | Componente | Archivos |
|---|---|---|
| 1 | Votación: `RAZON: máximo 150 caracteres` (aviso a 200 y rechazo a 300 sin cambios); recordatorio `razon_larga`; los 3 votos comparten mensaje de sistema y prefijo (instrucción, tarea, propuesta final y revisión), y la identidad del votante y el recordatorio van al final | `prompts.py`, `contexto.py` (`sufijo`), `orquestador.py` |
| 2 | Motor autónomo PLANIFICAR → … → FINALIZAR con presupuestos acotados, criterios de A2, bloqueo de A3, alcance, sin progreso, memoria | `motor.py` |
| 3 | Proyectos multiarchivo seguros: rutas, versiones conservadas, SHA-256, atómico, límites | `proyecto.py`, `archivos.py`, `rutas.py` |
| 4 | Observabilidad y control | `supervisar.py`, `estado_actual.json`, `eventos.jsonl`, `informe.json` |
| 5 | Pruebas de regresión, seguridad, límites y mutaciones | `tests/test_v2e.py` (63 pruebas) |
| 6 | Preparación de Windows 11 | `aislamiento.py` (Modo B), `plataforma.py` (proveedores), `MIGRACION_WINDOWS.md` |
| — | Análisis estático sin ejecutar (`ast.parse`) | `analisis_estatico.py` |
| — | Asesoría GPT-6/Claude manual | `asesoria.py`, `supervisar.py exportar-asesoria` |
| — | Métricas por agente y de votación (llamadas, reintentos, tiempo de reintentos, `cache_n`); el comparador muestra el tiempo de votación ahorrado | `metricas.py`, `comparar_metricas.py` |

**Ahorro de la votación: hipótesis, no medida.** Con `cache_prompt` y una sola ranura, llama-server reutiliza el prefijo común con la petición anterior; la parte compartida (unos 750 de 820 caracteres en una prueba) debería evaluarse una sola vez en vez de tres. El campo `cache_n` de las métricas lo confirmará en el teléfono. El reintento dirigido también debería evitar un segundo fallo de longitud. `comparar_metricas.py` muestra el tiempo de votación de V2-D frente a V2-E con la misma tarea.

## 3. Cómo se distingue lo verificado de lo que no
`resultado` solo puede ser `verificado` con pruebas **reales** que verifiquen **todos** los criterios. En V2-E no hay pruebas reales, así que **siempre es `no_verificado`**. Una simulación aparece como `criterios_superados_en_simulacion`; el análisis estático, como `prueba_presente_sin_ejecutar`. `Resultado(simulado=True, tipo="real")` lanza una excepción.

## 4. Modos del ejecutable
| Modo | Modelo | Ejecutor | Qué demuestra |
|---|---|---|---|
| `--modo tarea_simulada` | no (agentes simulados) | simulado | Tarea completa de programación: 3 archivos, una prueba falla, A3 objeta, A2 diagnostica, A1 corrige, v2 supera en simulación |
| `--modo tarea --iniciar-servidor-real` | **sí** (un llama-server) | **estático** (no ejecuta) | Que A1, A2 y A3 generen, revisen y corrijan archivos de verdad; detecta errores de sintaxis, nombres no definidos y pruebas ausentes |
| `--modo deliberacion --iniciar-servidor-real` | sí | — | Deliberación y votación (como V2-D, con la votación optimizada) |
| `--modo comprobar`, `una_llamada`, `ciclo_simulado` | — | — | Como en V2-D |

`--ctx 2048` (por defecto) o `--ctx 1024`. Datos siempre en `datos_v2e`.

## 5. Pruebas (ejecutadas en sandbox)
- **Validador estático:** 0 problemas (incluye `supervisar.py`).
- **Suite completa:** 462 pruebas OK con `-W error::ResourceWarning -X dev` (399 heredadas y 63 nuevas), también desde el ZIP extraído.
- **Pruebas heredadas que cambiaron (justificadas):**
  1. `test_orquestador.test_voto_sin_formato_dos_veces_es_abstencion`: la identidad del votante se busca al final del mensaje de usuario (cambio de prompt de la votación).
  2. Detectores de agente en `tests/test_v2c.py` (BackendGuion), `tests/test_v2d.py` (BackendCont) y `tests/fake_llama_server.py`: también buscan la identidad en el mensaje de usuario. Es el mismo motivo.
  3. `test_v2c.test_esquema_es_el_vigente` y `test_v2d.TestEsquema4.test_esquema`: esquema 5.
  4. `test_v2d.test_ciclo_simulado`, `test_v2d.test_deliberacion_sin_modelo_usa_datos_v2d...` y `test_v2b.test_sin_modelo...`: carpeta `datos_v2e`.
- **Mutaciones:** ver §6.

## 6. Mutaciones (ejecutadas)
Se desactivaron, una a una, 29 protecciones y se ejecutaron `test_v2d.py` + `test_v2e.py`.
- **Primera ronda:** 22 de 28 detectadas. Las 6 restantes revelaron 4 huecos en las pruebas (versión repetida, tope de llamadas antes de llamar, criterio C0 con análisis estático, éxito simulado con objeción de A3) y **una debilidad del código**: el motor creía a cualquier ejecutor que declarara `tipo="real"`. Se corrigió (solo se acepta de `EjecutorReal` con el Modo B habilitado; si no, `resultado_real_no_autorizado` y error crítico) y se añadieron las pruebas.
- **Segunda ronda:** detectadas todas salvo **2 mutaciones equivalentes**, que son defensas redundantes:
  - E5: quitar `reales and` del cálculo de `resultado`. Un criterio solo puede estar `verificado` con un resultado real autorizado, así que la condición ya está implícita.
  - E16: quitar la comprobación de enlace en `reemplazar_atomico`. `rutas.ruta()` ya rechaza un destino que sea enlace.
- Detectadas (entre otras): límite de 150 en el prompt, reintento dirigido, prefijo común, transiciones sin validar, simulado declarado como real, presupuesto sin acotar, mismo fallo repetido, bloqueo de A3, STOP, tiempo, rutas, sobrescritura, tamaño total, interruptor y autoverificación del Modo B, sintaxis en el análisis estático, nombre de la asesoría, detección de permisos, memoria baja, parada del servidor, esquema 5, plazo por prueba y resultados reales no autorizados.

## 7. Instalación (carpeta nueva)
```
mkdir -p "$TMPDIR/equipo_f2/codigo_v2e"
cd "$TMPDIR/equipo_f2/codigo_v2e"
unzip /ruta/a/equipo_f2_v2e.zip       # crea equipo_f2_v2e/
cd equipo_f2_v2e
```
Datos: `$TMPDIR/equipo_f2/datos_v2e/` (esquema 5). `datos_v2`, `datos_v2b`, `datos_v2c` y `datos_v2d` se rechazan y no se tocan.

## 8. Instrucciones para pruebas reales (cada paso con autorización)
1. `python3 -B -I validar_estatico.py` → 0 problemas.
2. `python3 -B -W error::ResourceWarning -X dev -m unittest discover -s tests -p "test_*.py"` → 462 OK.
3. `python3 -B ejecutar_v2.py --modo tarea_simulada` (sin modelo). En otra sesión de Termux: `python3 -B supervisar.py estado` / `informe`.
4. `python3 -B ejecutar_v2.py --modo comprobar` (anotar el soporte de continuación).
5. **Deliberación con la votación optimizada** (misma tarea que V2-D): `python3 -B ejecutar_v2.py --modo deliberacion --iniciar-servidor-real`. Comparar con `comparar_metricas.py <summary V2-D> <summary V2-E>` (tiempo de votación, reintentos, `cache_n`). Repetir con `--ctx 1024` para separar el efecto del contexto.
6. **Tarea con el motor y el modelo real** (análisis estático; no ejecuta código): `python3 -B ejecutar_v2.py --modo tarea --iniciar-servidor-real`. Supervisar con `supervisar.py estado | eventos | recursos`; parar con `supervisar.py detener`. Revisar `runs/<run>/proyecto/v*/` y `informe.json`.
7. Comprobación posterior: puerto 8089 libre, ningún proceso `llama*`, y los datos de V2-B/C/D sin cambios.

## 9. Riesgos pendientes
- **No hay ejecución real de pruebas:** el motor con el modelo real solo llega a `sin_verificar`. No se debe afirmar que el código funciona.
- El análisis estático detecta errores de forma, no de lógica. Sus avisos de riesgo (imports, `open`, `eval`) son informativos.
- Un modelo de 3B puede no seguir los formatos `CRITERIO:`, `ARCHIVO:` o `BLOQUEO:`. Sin criterios se usa C0 y se registra; sin archivos, cuenta como iteración fallida.
- La detección de «intentos de ampliar permisos» es por patrones: puede haber falsos positivos y negativos. En cualquier caso, los permisos no dependen de ella (son inmutables).
- **2048 de contexto:** prompts más largos, más evaluación del prompt. El +30 % respecto a V2-D no está garantizado; la caché KV estimada (unos 72 MB) no está medida.
- El prefijo común de la votación depende de cómo reutilice la caché la versión de llama-server: sin `cache_n` > 0 no hay ahorro.
- `escribir_atomico` usa enlaces duros; si el sistema de archivos los rechaza, escribe con `O_EXCL` (nunca sobrescribe, pero no es atómico) y lo registra (`atomico: false`).
- Heredados: SIGKILL del supervisor; estimación de tokens provisional; TOCTOU; un único modelo para los tres papeles; prefill sin verificar en el dispositivo.
