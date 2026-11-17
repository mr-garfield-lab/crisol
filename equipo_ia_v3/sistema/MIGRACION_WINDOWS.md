# Plan de migración a Windows 11 (actualizado en V2-E)

Ni V2-D ni V2-E se han ejecutado en Windows. Este plan describe qué hay que cambiar y en qué orden. La sincronización entre el equipo Android y el equipo Windows no forma parte de V2-D.

## 1. Qué ya es portable
- Lógica pura (sin E/S): `votos.py`, `protocolo.py`, `integridad.py`, `compresion.py`, `contexto.py`, `prompts.py`, `sanea.py`, `metricas.py`, `archivos.py`.
- `archivos.py` ya rechaza nombres reservados de Windows (`CON`, `NUL`, `AUX`...).
- `ciclo.py` y `ejecutor.py` (interfaces): solo usan `pathlib` y `rutas.Laboratorio`.
- `cliente_http.py`: sockets estándar contra `127.0.0.1`.
- SQLite (`memoria.py`): portable; los archivos `.db` de Android no se copian a Windows sin revisión (esquema 4).

## 2. Qué depende de Linux/Android (`plataforma.py` lo detecta)
| Componente | Dependencia actual | Equivalente previsto en Windows |
|---|---|---|
| `monitor.py`, `vigilancia.py` | `/proc/meminfo`, `/proc/<pid>/status` | `psutil` (dependencia nueva, a aprobar) o `GlobalMemoryStatusEx` vía `ctypes` (el validador lo prohíbe hoy: requeriría una excepción explícita). |
| `servidor.llama_activo` | recorrido de `/proc` | lista de procesos con `psutil` o `tasklist /FO CSV` (sin shell). |
| `servidor.wake_lock` | `termux-wake-lock` | no aplica; desactivar con `--sin-wake-lock`. |
| `servidor.detener` | `SIGTERM` → `SIGKILL` | `Popen.terminate()` = `TerminateProcess` (no hay parada «suave»): ajustar la lógica de gracia y documentarlo. |
| `rutas.py` | `O_NOFOLLOW`, `TMPDIR` | `%TEMP%`; los enlaces de Windows (symlinks y *junctions*/reparse points) requieren comprobación con `os.lstat(...).st_file_attributes`. |
| Señales del orquestador | `SIGINT`/`SIGTERM` | `SIGINT` (Ctrl+C) y `SIGBREAK`; el archivo STOP sigue funcionando igual. |

## 3. Pasos propuestos (cada uno con su propia revisión)
1. **Capa de plataforma:** crear `plataforma_windows.py` con `mem_disponible_kb()`, `muestra_proceso(pid)`, `proceso_llama_activo()`, y hacer que `monitor`, `vigilancia` y `servidor` llamen a `plataforma` en vez de leer `/proc` directamente. Pruebas con lectores inyectados (ya existen en el diseño).
2. **Rutas:** `raiz_laboratorio()` con `%TEMP%` cuando `TMPDIR` no exista; detección de reparse points; pruebas de escape con *junctions*.
3. **Servidor:** `llama-server.exe` (CUDA/Vulkan/CPU según el PC). Mantener argv explícito, `127.0.0.1`, un único proceso, `-np 1`. Revisar `--help` de esa versión (incluido `--no-prefill-assistant`).
4. **Modelo mayor:** subir `CTX` y `MAX_TOKENS` solo tras medir RAM/VRAM; `config.CTX_PERMITIDOS` y los caps por bloque escalan con `CTX/1024`.
5. **Ejecutor REAL (por primera vez):** solo con aislamiento real: **Windows Sandbox** (Windows 11 Pro/Enterprise), una VM, o un contenedor (Docker/WSL2 con red desactivada). Requisitos: carpeta compartida de solo lectura para el código y otra de escritura para resultados, sin red, límites de CPU/RAM/tiempo, sin credenciales, destrucción del entorno tras cada ejecución. Implementarlo como subclase de `ejecutor.EjecutorBase` con `aislamiento` distinto de `"ninguno"`; `Politica.aislamiento_requerido` sigue siendo obligatorio. El validador estático tendrá que permitir `subprocess` SOLO en ese módulo, con revisión explícita.
6. **Comunicación entre equipos (posterior):** intercambio de archivos firmados (hash) en una carpeta o protocolo local; nunca ejecución remota de órdenes.

## 4. Lo que NO debe migrarse tal cual
- Las suposiciones de rendimiento del S23 (≈9 tok/s, carga ≈3 s).
- Los límites de tiempo: recalibrar con `comparar_metricas.py`.
- Un directorio como «sandbox»: en Windows tampoco lo es.

## 5. Novedades de V2-E que facilitan la migración
- `plataforma.ProveedorPlataforma` con `ProveedorLinux` (implementado) y `ProveedorWindows` (pendiente: hoy lanza `NoSoportado`). El motor ya pide la memoria disponible a través del proveedor; falta migrar `monitor.py`, `vigilancia.py` y `servidor.llama_activo` a esa capa.
- `aislamiento.MaquinaVirtualWindows`: es el punto donde implementar el Modo B. Antes de habilitarlo (`config.MODO_B_HABILITADO`), su `autoverificar()` debe DEMOSTRAR con pruebas cada requisito de `aislamiento.REQUISITOS`: sistema de archivos (solo carpeta de trabajo), sin red, sin procesos fuera del entorno, límites de CPU y memoria, duración, sin acceso a archivos personales e instalaciones solo con permiso explícito y dentro del entorno. Propuesta: Windows Sandbox o una VM de Hyper-V sin adaptador de red, con carpeta de entrada de solo lectura (`MappedFolder ReadOnly`), carpeta de salida, `LogonCommand` que ejecute solo `python -m pytest` con tiempo límite, y destrucción del entorno al terminar.
- Panel local: puede leer `estado_actual.json`, `eventos.jsonl` e `informe.json` sin cambiar el motor; la orden de parada sigue siendo el archivo `STOP`.
- Comunicación con el teléfono (opcional, futura): intercambio de archivos `informe.json` y de solicitudes de asesoría con huella SHA-256; nunca órdenes remotas.
- Prohibido en cualquier plataforma: reinicios, cambios globales del sistema, borrar archivos ajenos al laboratorio, persistencia oculta, ocultar procesos.
