# V3.1 · Criterio de medición de `majflt` en Windows (propuesta, NO implementada)

**Estado:** investigación terminada y propuesta para decidir antes de activar Qwen (F1, decisión D3 de
`V31_PLAN_ACTIVACION_F1.md`). No se ha cambiado ningún código.

## 1. Qué hace V2-F.1 con `majflt`

- `monitor.leer_fallos` lee `minflt` y `majflt` de `/proc/<pid>/stat` del proceso `llama-server`.
- `config.CRITICAS = ("MemAvailable", "VmRSS", "majflt")`: si falta una, la respuesta sale
  `completo_no_concluyente` («medicion_critica_ausente:majflt»).
- `backend_llama` guarda, por petición, `delta_fallos = {minflt, majflt}` (después − antes).
- **Para qué sirve:** un fallo de página MAYOR es una página que hubo que traer del disco. Con el modelo GGUF mapeado
  en memoria, `majflt > 0` durante una petición indica que parte del modelo (o de la memoria) no estaba en RAM: la
  medición de velocidad queda contaminada por la E/S de disco, y hay sospecha de falta de memoria o de paginación.
- **No** interviene en STOP ni en el aborto por memoria (esos usan `MemAvailable`): solo decide si una medición es
  concluyente.

## 2. Qué ofrece Windows (medido en esta máquina, 2026-11-11)

Experimento (`evidencias/v31_mantenimiento/exp_majflt.py`; solo lee contadores, y escribe y borra un archivo propio en
la carpeta temporal): se escribe un archivo SIN pasar por la caché del sistema (`FILE_FLAG_NO_BUFFERING |
WRITE_THROUGH`) y luego se lee con `mmap` dos veces. La primera lectura obliga a traer cada página del disco
(«fría»); la segunda ya está en memoria («caliente»).

| Contador | API | 128 MiB fría | 128 MiB caliente | 256 MiB fría | 256 MiB caliente | 256 MiB, medido DESDE OTRO proceso: fría / caliente |
|---|---|---|---|---|---|---|
| A. `PageFaultCount` | `GetProcessMemoryInfo` (documentada) | 33 093 | 33 089 | 65 928 | 65 924 | 65 674 / 65 665 |
| B. `HardFaultCount` | `NtQuerySystemInformation` (clase 5, `SYSTEM_PROCESS_INFORMATION`) | **132** | **0** | **260** | **0** | **260 / 0** |

Resultados en `evidencias/v31_mantenimiento/majflt_*.json`.

Conclusiones:

- **A no sirve como `majflt`.** Cuenta todos los fallos (blandos y duros) y no distingue una lectura de disco de una
  de memoria (33 093 frente a 33 089). Llamarlo `majflt` sería inventar el dato.
- **B sí distingue** disco de memoria, escala con lo leído (132 → 260 al duplicar) y **se puede medir desde fuera**,
  que es como se mediría `llama-server`. Windows agrupa la lectura (cada fallo duro trae ~1 MiB, unas 250 páginas),
  igual que Linux agrupa con *readahead*; los valores no son comparables uno a uno con Linux, pero **0 frente a > 0**
  significa lo mismo.
- **Riesgo de B:** el campo existe desde Windows 7 y lo usan herramientas como Process Explorer y System Informer,
  pero Microsoft lo documenta como «reservado». Si una versión de Windows lo cambiara, leeríamos un valor incorrecto
  en silencio. Por eso la propuesta exige una autocomprobación.

## 3. Opciones

| Opción | Qué haría | A favor | En contra |
|---|---|---|---|
| **1. Dejarlo como está** | `majflt` ausente en Windows; toda respuesta con Qwen sale «no concluyente» | Ningún riesgo de dato falso | Ninguna medición de F1 en Windows sería concluyente |
| **2. `HardFaultCount` como `majflt`, con autocomprobación** (recomendada) | El lanzador sirve `/proc/<pid>/stat` con `majflt` = `HardFaultCount` y `minflt` = `PageFaultCount − HardFaultCount`, solo si al arrancar pasa la sonda de §2 (fría > 0 y caliente = 0) | Dato real y medido; si la sonda falla, vuelve a la opción 1 (fallo cerrado) | Campo no documentado oficialmente; semántica agrupada (se etiqueta como «fallos duros de Windows») |
| 3. Quitar `majflt` de las críticas solo en Windows | Cambiar `config.CRITICAS` | Simple | Exige modificar `sistema/` y pierde la detección de E/S de disco |
| 4. Contador del sistema (`\Memory\Pages Input/sec`) | Fallos duros de TODO el sistema | Documentado | No es por proceso: cualquier otro programa contamina la medición |

## 4. Propuesta: opción 2, con estas garantías

Todas comprobables con pruebas y mutaciones, como el adaptador de memoria real de F0.5:

1. **Sonda al iniciar** (en el lanzador, una vez por proceso, ~0,3 s con 128 MiB en la carpeta temporal): solo si da
   fría > 0 y caliente = 0 se activa; si no, `majflt` sigue ausente.
2. **Nada inventado:** si la consulta falla para ese pid, el campo falta (como ahora).
3. **Etiquetado:** el informe de cada sesión en Windows dice «majflt = HardFaultCount de Windows (agrupado ~1 MiB)».
4. **Interpretación en F1:** con el modelo entero en VRAM y RAM sobrada, se espera `delta majflt = 0` por petición.
   Un valor > 0 marca la petición para revisión (posible paginación del modelo); no la aborta.
5. **`sistema/` sin cambios.**

**Decisión pendiente del usuario** antes de F1: opción 2 (recomendada) u opción 1.
