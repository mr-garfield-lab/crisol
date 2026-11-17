# Equipo IA V3 — Etapa 7: auditoría integral

**Estado: CERRADA** (2026-11-10). Verificador: F0–F11 correctas (`evidencias/etapa6_7/`).

## 1. Alcance y método

**Alcance.**
- Todo el código V3: `eq3/` (11 módulos), `equipo3.py`, `verificar_v3.py` y las herramientas de `v3/`; 2.838
  líneas, más 1.366 de pruebas.
- Los componentes reutilizados (`contexto_ligero/`, `complementos_codex/`) se comprueban como copias IDÉNTICAS.
- `sistema/` (V2-F.1) se verifica sin cambios (F0) y con su línea base (F10).

**Método.**
1. **Análisis estático:** búsqueda de procesos, código dinámico, red, borrados y escrituras (§2).
2. **Revisión de las fronteras de confianza:** datos no confiables frente a controles (§3).
3. **Pruebas de mutación:** de cada etapa (67 mutaciones en total) y de la propia herramienta de mutación (§4).
4. **Verificador integral:** con la línea base completa.

## 2. Análisis estático del código V3

| Búsqueda | Resultado |
|---|---|
| `subprocess` | Solo en las herramientas de calidad (`v3/linea_base.py`, `v3/mutacion.py`, `verificar_v3.py`), que ejecutan las pruebas de ESTE proyecto: listas de argumentos fijas, sin shell y con `HOME`/`TMPDIR` aislados. Ninguno en `eq3/` |
| `eval`, `exec`, `pickle`, `marshal`, `shell=True` | Ninguno |
| Red (`socket`, `urllib`, `http`) | Ninguna en V3. El servidor que propone la Etapa 6 escucha solo en `127.0.0.1` y no se lanza |
| Borrados | Solo el temporal propio de una escritura atómica fallida (`cambios.py`) |
| Escrituras | Registro de solo añadir; bases de solo añadir del laboratorio; archivos de proyecto solo por propuesta → autorización → aplicación; resultados de las herramientas de calidad en carpetas NUEVAS bajo `$TMPDIR` |
| `except` amplios | 2 `except BaseException`, ambos para deshacer (transacción y temporal) y volver a lanzar la excepción |
| Referencias a otros proyectos | Solo la constante del presupuesto de 6144 MiB del AI Lab Coordinator, que se lee y no se modifica. Ninguna a GameAgentEngine, AURORA ni ATLAS |

## 3. Fronteras de confianza

| Dato no confiable | Dónde entra | Control |
|---|---|---|
| Archivos del laboratorio de V2-F.1 (respuestas de agentes, JSON, versiones) | `ingesta` | Confinamiento de rutas, enlaces rechazados en cada tramo, límites de tamaño y anidamiento, SHA-256 declarados comprobados, una transacción y STOP |
| Textos de agentes con apariencia de orden o de SQL | `ingesta`, `citas`, `memoria` | Solo se guardan por hash o se tratan como texto. Las citas se contrastan; nada se interpreta. V2-F.1 rechaza al escribir los recuerdos instructivos |
| Solicitudes de herramientas de los agentes | `cambios.solicitar` | Registro congelado. Ninguna herramienta escribe, autoriza ni ejecuta, y los argumentos son tipados |
| Contenido de código propuesto | `cambios.proponer` | Solo `ast.parse`, nunca se ejecuta. La autorización es del usuario con hash tecleado, de un solo uso y con caducidad; se comprueba el TOCTOU y la escritura es atómica |
| Especificaciones de mutación | `v3/mutacion.py` | AUD-01 y AUD-02 (§4.1) |
| Ruta de un GGUF y argumentos del PC | `perfiles_pc` | Solo `stat`; se rechazan los enlaces y los caracteres de control; el servidor queda solo en `127.0.0.1` |

## 4. Hallazgos

### 4.1 Hallazgos de esta auditoría (corregidos)

| Id | Gravedad | Hallazgo | Corrección y prueba |
|---|---|---|---|
| AUD-01 | Media | `v3/mutacion.py` ejecutaba la `orden` de su especificación JSON: un archivo de datos decidía qué proceso lanzar | Solo admite `{python} -B -m unittest discover` con `-s`, `-t` y `-p` y rutas simples. Cubierto por `test_mutacion.py` y la mutación M7 |
| AUD-02 | **Alta** | El destino de una mutación no se validaba: `../../x` escribía fuera del espejo, y `sistema/src/...` escribía A TRAVÉS DEL ENLACE en el `sistema/` real, justo lo que el espejo debía proteger | Solo se mutan archivos COPIADOS, nunca enlazados. Se rechazan `..` y las rutas absolutas, y el destino debe resolverse dentro del espejo sin pasar por enlaces. Son dos capas, cada una probada por separado (`test_mutacion.py`, mutaciones M8 y M9); la prueba comprueba que el `config.py` real no cambia |

| AUD-03 | Media | Dos especificaciones de mutación quedaron incompletas al crecer las pruebas: la de la Etapa 6 no copiaba `equipo3.py`, y la de la Etapa 0 enlazaba `sistema/` mientras `v3/tests` ya incluía el empaquetado, que rechaza los enlaces. Lo detectó el CONTROL obligatorio: las fases F9 y F3 dieron FALLO y no un resultado vacío | Se completó la de la E6; la E0 y la E8 usan un espejo por COPIA, con `copiar_raiz` validado (solo archivos de la raíz, nunca GameAgentEngine). Regla: cada especificación debe copiar lo que usan sus pruebas |
| AUD-04 | Baja | El empaquetado rechazó una fixture de Contexto Ligero: una cabecera PEM con cuerpo «VALOR_PRIVADO» para comprobar la REDACCIÓN de secretos | Se comprobó que es sintética: 13 caracteres, no es una clave. La excepción queda ligada al SHA-256 exacto del archivo, y el escáner no se debilita. Las pruebas propias construyen sus fixtures en tiempo de ejecución |

### 4.2 Hallazgos de las etapas anteriores (resumen)

| Etapa | Hallazgo | Estado |
|---|---|---|
| 0 | SEG-01: la lista blanca AST del ejecutor de V2-F.1 se puede saltar | Abierto, mitigado: la ejecución de código generado sigue DESHABILITADA |
| 1 | La firma de la línea base dependía de la longitud de la carpeta de salida (lo encontró la propia puerta) | Corregido; la línea base no cambió |
| 1 | Pruebas de rutas y enlaces débiles: las mutaciones M2 y M3 sobrevivían | Corregido |
| 1 | `RecursionError` y `sqlite3.Error` sin capturar | Corregido |
| 4 | Cortar frases en cada punto rompía `x.py`; las citas de escape se ignoraban; se informaba una versión calculada en lugar de la usada | Corregido |
| 5 | Palabras vacías incompletas en Codex, con falsos positivos y controles negativos fallidos | Corregido en eq3 y verificado en un conjunto de contraste |
| 5 | V2-F.1 rechaza el contenido instructivo al escribir | Comportamiento correcto; documentado |

## 5. Calidad y deuda técnica

- **Duplicación:** `almacen.py` es común a la traza y a los cambios. `traza.py` bajó de 219 a 90 líneas. Los
  componentes de terceros se reutilizan como copias idénticas, sin reimplementarlos.
- **Funciones de más de 60 líneas:** `ingesta.leer_ejecucion` (153), `equipo3.main` (92), `linea_base.main` (80) y
  `reconstruccion.verificar` (67).
  - **Deuda:** conviene dividir `leer_ejecucion` en una función por tipo de registro antes de admitir otros tipos
    de tarea.
  - **Por qué no ahora:** no se refactorizó durante la auditoría, para no cambiar código ya verificado. Las 23
    pruebas y las 12 mutaciones de la Etapa 1 protegen esa división.
- **Mutación:** 67 mutaciones en siete especificaciones, todas detectadas. Las que sobrevivieron en algún momento
  revelaron pruebas débiles y se corrigieron (M2/M3 de E1, M6 de E4, M5 de E0).

## 6. Riesgos que siguen abiertos

1. **SEG-01:** no hay aislamiento del sistema operativo para ejecutar código generado. Toda solución queda
   «aceptada sin ejecución».
2. **Qwen real sin validar:** todas las ejecuciones de agentes de esta versión son SIMULADAS.
3. **Plataformas sin validar:** Android/Termux y Windows 11 no se han validado. Las cifras del PC son estimaciones.
4. **Alcance limitado:** la memoria es léxica, la ingesta solo cubre `funcion_supervisada` y la autorización es
   local, sin autenticación de usuarios.

## 7. Criterios de aceptación de la Etapa 7

| Criterio | Evidencia | Cumple |
|---|---|---|
| Revisión de seguridad de todo V3 | §2–§4 | Sí |
| Hallazgos corregidos con prueba y mutación | AUD-01 y AUD-02 | Sí |
| Verificador integral completo | F0–F10 (rápida) y F11 (completa), con el mismo código | Sí |
| Riesgos abiertos documentados | §6 | Sí |
