# Plataformas: estado real y fases (V2-E.5)

## Estado de verificación (no se declara compatibilidad sin pruebas)
| Plataforma | Estado | Constancia |
|---|---|---|
| Android / Termux | **probado por el usuario** hasta V2-E.1 | V2-E.2 … V2-E.5 están pendientes de validar en el dispositivo (comandos en `LEEME_V2E5.md`). |
| Linux | **probado solo en la sandbox Linux de desarrollo** | Sin probar en un escritorio Linux real (Ubuntu, Fedora…). |
| Windows 10/11 | **solo diseño** | Nunca se ha ejecutado. `AdaptadorWindows` lanza `NoSoportado` en lugar de devolver datos inventados. |

`python3 -B auditar.py plataforma` muestra el adaptador elegido, las capacidades detectadas y la auditoría de dependencias. Es de solo lectura: no crea el laboratorio ni escribe nada.

## Auditoría de dependencias específicas (`plataforma.auditar_dependencias()`)
Búsqueda estática y determinista por expresiones regulares en `src/eq2/*.py`, `ejecutar_v2.py` y `supervisar.py`. `plataforma.py` queda excluido. Número de líneas por archivo:

| Categoría | Archivos (líneas) | Qué es |
|---|---|---|
| rutas | `rutas.py` (10), `ejecutar_v2.py` (2), `orquestador.py` (1), `__init__.py` (1) | `TMPDIR`, `O_NOFOLLOW`, `os.link`, `/data/data`, `PREFIX` |
| procesos | `orquestador.py` (4), `servidor.py` (4), `ciclo.py` (2), `motor.py` (2), `memoria.py` (1), `rutas.py` (1) | `/proc/<pid>`, `os.getpid()`, `.terminate()`, `.kill()`, `SIGKILL` |
| recursos | `monitor.py` (6), `servidor.py` (3), `vigilancia.py` (2) | `/proc/meminfo`, `/proc/self`, `/sys/class/power_supply`, `proc_dir` |
| servidor | `ejecutar_v2.py` (6), `servidor.py` (4), `__init__.py` (2), `orquestador.py` (2), `backend_llama.py`, `cliente_http.py`, `config.py`, `inferencia.py` (1 cada uno) | `llama-server`, `termux-wake-lock`/`unlock`, `127.0.0.1` |
| señales | `motor.py` (3), `orquestador.py` (3) | `signal.SIGINT`/`SIGTERM`, `signal.signal(` |

La auditoría es **heurística**:
- una coincidencia no implica que el código falle en otra plataforma;
- la ausencia de coincidencias no garantiza que sea portable.

Los módulos nuevos de V2-E.5 (`criticas.py`) no tienen ninguna coincidencia.

## Adaptadores (`plataforma.py`)
`AdaptadorPlataforma` reúne en un único punto lo que depende del sistema:
- `raiz_temporal(env)`;
- `pid_vivo(pid)`;
- `proceso_llama_activo()`;
- `mem_disponible_kb()`;
- `bateria()`;
- `comando_servidor()`;
- `wake_lock_disponible()`;
- `entorno()` (solo lectura);
- `informe()`.

| Adaptador | Implementación |
|---|---|
| `AdaptadorLinux` | Las **mismas** funciones que ya usaba el código: `/proc`, `servidor.llama_activo`, `vigilancia.leer_mem_available`. |
| `AdaptadorTermux` | Hereda de Linux; añade la detección de `termux-wake-lock`. |
| `AdaptadorWindows` | Diseño: todo lo que no puede comprobar lanza `NoSoportado`; el comando es `llama-server.exe`. |

**El núcleo no se duplica.** Cada adaptador solo envuelve las llamadas al sistema.

`test_v2e5.TestAdaptadores.test_termux_y_linux_dan_lo_mismo_que_el_codigo_anterior` comprueba, con un `/proc` falso, que Linux y Termux devuelven exactamente lo mismo que el código anterior.

## Fases
- **Fase 1 (V2-E.5, hecha).**
  - Auditoría, adaptadores y el subcomando `auditar.py plataforma`.
  - Un único punto del núcleo pasa por el adaptador: la comprobación del candado de sesión (`pid_vivo`). En Linux y Termux el comportamiento es idéntico al anterior. Si la plataforma no puede comprobarlo, el candado **no** se considera obsoleto (actitud conservadora) y el mensaje lo dice.
- **Fase 2 (siguiente: escritorio Linux).**
  - Pasar por el adaptador `servidor.llama_activo`, `wake_lock`, el comando del servidor, la raíz temporal y la vigilancia de memoria y batería.
  - Ejecutar la suite y una deliberación real en un escritorio Linux (Python 3.11 o superior, `llama-server` compilado) y anotar los resultados aquí.
- **Fase 3 (Windows 10/11).**
  - Implementar `AdaptadorWindows`:
    - `%TEMP%` y `%LOCALAPPDATA%`;
    - procesos con `tasklist /FO CSV` sin shell, o `ctypes` con una excepción explícita del validador;
    - memoria con `GlobalMemoryStatusEx`;
    - `SIGBREAK`;
    - enlaces y *junctions* mediante `st_file_attributes`.
  - Sustituir la dependencia de `os.link` y `O_NOFOLLOW` por comprobaciones equivalentes.
  - La validación en Windows 10 y en Windows 11 la hace el usuario. Hasta entonces, Windows sigue siendo «solo diseño».

`MIGRACION_WINDOWS.md` (V2-E) contiene la tabla detallada de equivalencias.

## V2-E.6: restricciones reales por plataforma
- **Ejecutado:** solo Linux (sandbox), con Python 3.13. Termux (Android) y Windows **no se han ejecutado** en esta entrega.
- **Android / Termux:**
  - Python de Termux **sin `os.link`**. La ruta sin enlaces duros se prueba simulando su ausencia, con `--sin-link` en desarrollo.
  - `/proc/meminfo` suele ser legible, así que la RAM se puede medir para elegir el perfil de contexto.
  - Si no se puede medir, V2-E.6 no sube de 2048 (perfil de referencia).
  - `resource.getrusage` existe.
  - Hay que usar `python3 -m zipfile -e` en lugar de `unzip`, que puede no estar instalado.
  - `~/storage/downloads` exige `termux-setup-storage`.
- **Windows:**
  - No hay `resource` ni `/proc`: las métricas de CPU y RAM del verificador quedan como `medido: false`.
  - Las comprobaciones de procesos quedan NO VERIFICADA.
  - El adaptador es solo de diseño (ver `MIGRACION_WINDOWS.md`).
- **Linux de escritorio:** igual que la sandbox. `llama-server` no está incluido.
