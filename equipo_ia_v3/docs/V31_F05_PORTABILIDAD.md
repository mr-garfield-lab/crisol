# Equipo IA V3.1 — F0.5: portabilidad Windows / Linux con un solo motor

**Estado:** ver §5 (resultados) y §6 (qué queda sin validar). Fecha: 2026-11-10. Base: paquete V3 (Etapa 8),
`originales/EquipoIA_V3_1.zip`, SHA-256 `d0b8d37e…4f76`.

**Principios que se mantienen:** `sistema/` (V2-F.1) no se modifica (F0 lo comprueba); Contexto Ligero y los
complementos de Codex siguen siendo copias idénticas; ninguna lógica de A1/A2/A3 cambia; todo lo que depende del
sistema operativo está en UN módulo, `eq3/plataforma.py`. No se instaló nada ni se cambió ninguna configuración de
Windows, y no se ejecutó código generado por agentes.

## 1. Problemas encontrados en Windows 11 y su causa raíz

| # | Síntoma | Causa raíz | Gravedad |
|---|---|---|---|
| P1 | `verificar_v3.py` se cae en F1 (`UnicodeDecodeError` y `TypeError`) | Los procesos hijo recibían un entorno mínimo de Linux: sin `SYSTEMROOT` ni UTF-8, el hijo escribía en cp1252 y el padre leía UTF-8 | Bloqueante |
| P2 | 10 `setUpClass` de `pruebas/` fallan | La misma causa en `pruebas/comun.demo()` | Bloqueante |
| P3 | (latente) `~` de un proceso hijo era la carpeta REAL del usuario | En Windows `Path.home()` usa `USERPROFILE`, no `HOME`; el entorno mínimo solo cambiaba `HOME` | **Seguridad**: una prueba podía escribir en el perfil del usuario |
| P4 | Pruebas de seguridad y espejos de mutación fallan con WinError 1314 | Crear symlinks exige un privilegio (modo de desarrollador o administrador) | Bloqueante para F3–F10 |
| P5 | (latente) Una **unión de directorio** (junction) atravesaba todas las defensas de eq3 | `Path.is_symlink()` no ve las uniones, y `os.walk(followlinks=False)` entra en ellas (comprobado con Python 3.12) | **Seguridad**: escape del laboratorio/proyecto en `ingesta`, `cambios`, `perfiles_pc` y `empaquetar` |
| P6 | El grafo no indexa nada (recall 0,0; 0 de 68 archivos) | Contexto Ligero exige `dir_fd`/`O_NOFOLLOW` (POSIX) y falla cerrado | Funcional |
| P7 | Toda importación de trazas de V2-F.1 falla por `ErrorIntegridad` | V2-F.1 escribe en modo texto sin `newline`: en Windows los archivos llevan «\r\n», pero declara el SHA-256 del texto con «\n» | Funcional (defecto de V2-F.1 en Windows) |
| P8 | `PermissionError` (WinError 32) al limpiar | Una prueba dejaba abierta una conexión SQLite, y Windows no deja borrar un archivo abierto | Pruebas |
| P9 | Firmas de la línea base distintas | La normalización solo conocía rutas POSIX (no `C:\…` ni `C:\\…` escapadas) | Pruebas |
| P10 | Carpeta temporal por defecto `/tmp` → `C:\tmp` | `os.environ.get("TMPDIR", "/tmp")` | Menor: escribía fuera de la carpeta de trabajo |

## 2. Solución: adaptadores, no un segundo motor

| Adaptador (`eq3/plataforma.py`) | Resuelve | Linux / Termux |
|---|---|---|
| `entorno_hijo`, `ejecutar` | P1, P2, P3: en Windows añade las variables de sistema imprescindibles, fuerza UTF-8 y redirige `USERPROFILE`/`TEMP`/`TMP`/`APPDATA`/`LOCALAPPDATA` a la carpeta temporal; la salida siempre se lee como UTF-8 | Entorno EXACTAMENTE igual que en V3 (lo comprueba una prueba) |
| `es_enlace` | P5: symlink en cualquier sistema y, en Windows, también uniones y cualquier punto de reanálisis (falla cerrado) | Idéntico a `is_symlink()` |
| `crear_enlace`, `replicar_solo_lectura` | P4: pruebas con unión de directorio si no hay privilegio; espejos de mutación con COPIA en vez de symlink (nunca con unión) | symlink, como antes |
| `leer_acotado`, `adaptar_contexto_ligero` | P6: misma regla que `read_bounded` (sin enlaces en ningún componente, solo archivos normales, tope de bytes) más rechazo de «:» (flujos alternativos) y nombres acabados en punto o espacio, y comprobación de que el archivo abierto es el validado (inodo). Se instala SOLO donde falta la lectura POSIX, sin tocar Contexto Ligero | No se instala |
| `orden_eq2` + `eq3/lanzador_eq2.py` | P7: en Windows, V2-F.1 se ejecuta con escritura de texto en «\n» (como en Linux), sin modificar sus archivos | V2-F.1 se ejecuta directamente, como antes |
| `variantes_ruta`, `barras_tras_marca` | P9 | Sin cambios en las firmas |

Otros cambios: P8 (cerrar la conexión en la prueba), P10 (`tempfile.gettempdir()` cuando no hay `TMPDIR`), y las
pruebas que crean enlaces usan `comun.enlazar_o_omitir`: si la plataforma no permite el enlace, la prueba queda
**OMITIDA con su motivo**, nunca aprobada.

## 3. Pruebas y mutaciones nuevas

- `pruebas/test_eq3_plataforma.py` (18 pruebas): entorno de los hijos (incluido un hijo REAL que comprueba `~`,
  la carpeta temporal y un texto no ASCII), lanzador (bytes exactos, `sys.argv`, `sys.path[0]`), enlaces y uniones,
  lectura acotada (rutas maliciosas, límites, raíz o componente enlazado, archivo sustituido tras validarlo) y
  normalización de rutas.
- `pruebas/test_eq3_cambios.py`: carpeta enlazada dentro del proyecto (proponer, leer y listar) y unión como
  proyecto.
- `v3/mutaciones/v31_plataforma.json` (F12, 11 mutaciones) y `v3/mutaciones/v31_uniones.json` (F13, 3 mutaciones:
  vuelven al `is_symlink()` original y deben DETECTARSE en Windows: prueban que el código de V3 era vulnerable a
  las uniones).
- `v3/mutacion.py`: campo opcional `requiere` (`enlaces_a_archivos`, `windows`). Si la plataforma no lo cumple, la
  mutación queda OMITIDA y se informa; no cuenta como detectada.
- Especificaciones de mutación existentes: solo se actualizó el texto «antes» de 3 mutaciones (etapa1 M3, etapa6
  M8, etapa8 M5) porque su línea pasó de `is_symlink()` a `es_enlace()`; el defecto que inyectan es el mismo.

## 4. Verificador

`verificar_v3.py` usa el mismo entorno de hijos, añade F12 y F13, registra la plataforma en `informe.json` y deja
de suponer `/tmp`. `v3/linea_base.py` elige por defecto `v3/linea_base_esperada_windows.json` en Windows si
existe; **todavía no se ha generado** (ver §5). La herramienta para generarla es `v3/linea_base_plataforma.py`.

## 5. Resultados en Windows 11 (REAL, Python 3.12.10, 2026-11-10)

| Fase | Resultado |
|---|---|
| F0 integridad de `sistema/` | OK (233 presentes, 0 distintos, 0 ajenos, 71 ausentes conocidos) |
| F1 `v3/tests` | OK: 31 pruebas (antes de F0.5: 5 fallos y 1 error de 22) |
| F2 `pruebas/` | OK: 94 pruebas, 4 OMITIDAS por symlinks de archivo sin privilegio (antes: 2 fallos y 14 errores de 42) |
| F12 mutación `v31_plataforma.json` | 11/11 detectadas, sobre el código final |
| F3–F10, F13 | NO EJECUTADAS todavía en Windows |
| F11 línea base | Ejecutada: codex IGUAL; verificador de V2-F.1 88 REGRESION + 3 CAMBIO; Contexto Ligero 125 REGRESION. Causas en `INFORME_V3_1_F05_ANALISIS.md` §5. Sin línea base de Windows generada |

## 6. Qué NO queda validado

- **Linux, WSL2 y Android/Termux no se han ejecutado con V3.1**: aquí no hay ninguno de los tres. Por diseño, en
  esas plataformas el comportamiento es el de V3 (entorno de hijos, firmas, enlaces y orden de V2-F.1 idénticos),
  pero **no se declara compatible** hasta ejecutar `verificar_v3.py --completo` en cada una.
- **Symlinks de archivo en Windows:** sin el modo de desarrollador, 3 pruebas y 1 mutación (etapa6 M8) quedan
  OMITIDAS. Con el modo de desarrollador se ejecutarían; activarlo es un cambio de configuración de Windows que
  corresponde al usuario.
- **V2-F.1 en Windows** sigue teniendo partes de Linux (`/proc` en `vigilancia`/`servidor`, `ProveedorWindows`
  pendiente). No afectan a las demos simuladas ni a las pruebas, pero sí a su servidor de Qwen: por eso F1 usará un
  adaptador en eq3 que se conecta a un llama-server lanzado por el usuario.
