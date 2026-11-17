# Equipo IA V3.1 — guía para repetir los bancos en otro PC

Gracias por ayudar. La idea es repetir en tu equipo las mismas pruebas que se hicieron en el PC de origen y comparar.
Todo es local: no se usa ninguna API ni servicio de pago, y nada sale de tu PC salvo lo que tú decidas enviar.

## Qué hay en el paquete

- **Equipo IA** (`equipo_ia_v3/sistema/`): el sistema de tres agentes (A1, A2, A3) sobre modelos locales con llama.cpp.
- **Banco de flujos grandes** (`equipo_ia_v3/lab_flujos/`): mide cuánta información de un proyecto mucho más grande
  que el contexto del cerebro consigue encontrar y usar bien, si se inventa datos y si una tarea cortada a medias se
  reanuda sin perder ni repetir trabajo. Empieza por `lab_flujos/PLAN_MEJORAS.md` y los `PRERREGISTRO_FLUJOS_T*.md`.
- **Banco de Blender** (`equipo_ia_v3/lab_blender/`, opcional): el cerebro escribe scripts de Blender y un verificador
  sin IA mide la escena.
- **Contexto Ligero V3.5** (`fuentes/contexto_ligero_v35/`): el buscador de código que alimenta a los cerebros.
- Resultados del PC de origen, para comparar: `equipo_ia_v3/evidencias/v31_lab_flujos/` y `.../v31_lab_blender/`
  (las rutas de aquella máquina están sustituidas por `<TRABAJO>` y `<CASA>`).

**No incluye**: los modelos (≈5 GB cada uno), llama.cpp, Blender, bases de datos, contraseñas ni datos personales.

Hay dos formas de probar:

| | Qué comprueba | Qué necesitas |
|---|---|---|
| **A. Docker** | Que todo funciona igual en tu equipo, con cerebros FALSOS: Contexto Ligero, reproducibilidad, parar y reanudar, verificación y flujo de identidad | Docker. CPU, sin GPU ni modelos. Unos minutos |
| **B. Windows con cerebros reales** | Las tandas de verdad con qwen25 y ministral3 | Windows 10/11, GPU NVIDIA (se calibró con una RTX 3050 de 8 GB), Python 3.12, ~11 GB de descargas |

## A. Verificación con Docker (empieza por aquí)

Desde la carpeta raíz del ZIP (la que contiene `equipo_ia_v3/` y `fuentes/`):

```sh
docker build -f equipo_ia_v3/lab_flujos/docker/Dockerfile -t equipo-ia-flujos .
docker run --rm --network none equipo-ia-flujos
```

**Esperado**: `10/10 comprobaciones pasan`, `51/51 comprobaciones de Java pasan` y `RESULTADO: OK`. Las pruebas propias de Contexto Ligero se muestran solo a
título informativo: algunas necesitan archivos que no van en el paquete. Sin Docker, en cualquier Python 3.12, desde
`equipo_ia_v3/`:

```sh
python -B -X utf8 lab_flujos/humo/comprobar_sin_gpu.py
```

> **Por qué los cerebros reales no van en Docker:** las protecciones del banco (esperar a que el PC esté libre,
> parar por temperatura, leer la memoria) usan funciones de Windows, y llama.cpp está registrado en su versión para
> Windows. Adaptarlo a Docker con GPU es trabajo pendiente.

## B. Tandas con cerebros reales (Windows)

### 1. Archivos externos

Crea una carpeta (por ejemplo `C:\EquipoIA\externos`) con esta estructura:

```
externos\
  llama_b12110\     ← el contenido de los DOS zip de llama.cpp, juntos en la misma carpeta
  modelos\qwen2.5-coder-7b-instruct-q4_k_m.gguf
  modelos\Ministral-3-8B-Instruct-2512-Q4_K_M.gguf
```

| Archivo | De dónde | SHA-256 |
|---|---|---|
| `llama-b12110-bin-win-cuda-12.4-x64.zip` | https://github.com/ggml-org/llama.cpp/releases/tag/b12110 | `1ce755bc3a061889234048f88e33328e17971eaad73c4666cfeb26026b317fee` |
| `cudart-llama-bin-win-cuda-12.4-x64.zip` | la misma página | `8c79a9b226de4b3cacfd1f83d24f962d0773be79f1e7b75c6af4ded7e32ae1d6` |
| `qwen2.5-coder-7b-instruct-q4_k_m.gguf` (4 683 073 536 bytes) | https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct-GGUF | `509287f78cb4d4cf6b3843734733b914b2c158e43e22a7f4bf5e963800894d3c` |
| `Ministral-3-8B-Instruct-2512-Q4_K_M.gguf` (5 198 911 904 bytes) | https://huggingface.co/mistralai/Ministral-3-8B-Instruct-2512-GGUF | `33e7a72cf5e6e2cfc2f2847075acc013d68bba023e35310cef86b5cf8fdca761` |

El sistema comprueba el SHA-256 de cada archivo antes de lanzar nada (también los 56 archivos de `llama_b12110`). Si
algo no coincide, no arranca. Para comprobarlo tú: `Get-FileHash .\archivo -Algorithm SHA256`.

### 2. Antes de lanzar

- **Cierra juegos y programas que usen la GPU**: el banco espera si otra cosa ocupa más de 1,1 GB de VRAM.
- **No toques el PC**: el banco solo arranca cuando lleva unos 10 minutos sin teclado ni ratón, y se pausa si lo usas.
- **Temperatura**: si la GPU llega a ~87 °C, se para sola sin perder nada; espera a que baje y relanza con
  `--reanudar` (misma orden). Nunca repite lo ya hecho.
- Los umbrales se calibraron en una RTX 3050 de 8 GB. Con otra GPU puede que el banco espere más de la cuenta o no
  arranque: anota lo que diga y avisa, también es un resultado útil.

### 3. Comprobación rápida (sin GPU, ~1 min)

Desde `equipo_ia_v3\`:

```powershell
py -B -X utf8 lab_flujos\humo\comprobar_sin_gpu.py
```

### 4. Las dos tandas a repetir

Desde `equipo_ia_v3\`, cambiando `C:\EquipoIA\externos` por tu carpeta. Cada tanda: primero `preparar` (sin GPU, segundos)
y luego `ejecutar` (con GPU, ~15–25 minutos con el PC libre). Usa SIEMPRE `eq3\lanzador_eq2.py` delante: sin él,
Windows no da la lectura de memoria y el banco se niega a arrancar.

**Tanda 3** (nombres exactos, trampas, contar en todo el proyecto, troceado con puntos de guardado):

```powershell
py -B -X utf8 lab_flujos\banco_flujos.py preparar evidencias\amigo_t3 --condiciones ligero hibrida --tipos A B C D E T R
py -B -X utf8 eq3\lanzador_eq2.py lab_flujos\banco_flujos.py ejecutar C:\EquipoIA\externos evidencias\amigo_t3
```

**Tanda 5** (preguntas parafraseadas y flujo de identidad):

```powershell
py -B -X utf8 lab_flujos\banco_flujos.py preparar evidencias\amigo_t5 --condiciones ligero identidad --tipos P A B D R T
py -B -X utf8 eq3\lanzador_eq2.py lab_flujos\banco_flujos.py ejecutar C:\EquipoIA\externos evidencias\amigo_t5
```

**Tanda 6** (código REAL de Equipo IA, preguntas como las haría una persona; ver
`lab_flujos/PRERREGISTRO_FLUJOS_T6.md`):

```powershell
py -B -X utf8 lab_flujos\banco_flujos.py preparar evidencias\amigo_t6 --condiciones ligero identidad --tipos N X U
py -B -X utf8 eq3\lanzador_eq2.py lab_flujos\banco_flujos.py ejecutar C:\EquipoIA\externos evidencias\amigo_t6
```

**Tanda 7** (la mejor combinación medida: Contexto Ligero y, si no encuentra, flujo de identidad; las 69 preguntas de
las tandas 5 y 6; ver `lab_flujos/PRERREGISTRO_FLUJOS_T7.md`):

```powershell
py -B -X utf8 lab_flujos\banco_flujos.py preparar evidencias\amigo_t7 --condiciones ligero combinada --tipos A B D R T P N X U
py -B -X utf8 eq3\lanzador_eq2.py lab_flujos\banco_flujos.py ejecutar C:\EquipoIA\externos evidencias\amigo_t7
```

Al terminar, el informe:

```powershell
py -B -X utf8 lab_flujos\banco_flujos.py informe evidencias\amigo_t5
```

Para comparar: `evidencias\v31_lab_flujos\tanda3\INFORME.md` y `...\tanda5\INFORME.md` del PC de origen.

### 5. Qué enviar de vuelta

De cada carpeta `evidencias\amigo_t*`: **`INFORME.md`, `peticiones.jsonl` y `trozos.jsonl`**, y dinos el modelo de tu
GPU. Esos tres archivos no contienen rutas ni datos de tu PC. **No envíes** `preparacion.json`, `banco.json` ni las
carpetas `qwen25\` y `ministral3\`: llevan rutas de tu máquina.

## Banco de revisión de código (Python y Java)

¿Encuentra el cerebro los errores que impiden compilar y los arregla sin tocar lo que estaba bien? 32 archivos con
errores plantados (sintaxis, nombres, imports, tipos, argumentos), 8 de ellos correctos para medir falsas alarmas.
El compilador encuentra el error, el cerebro lo explica y arregla, se recompila y, si sigue fallando, se le avisa
(hasta 3 intentos). **El código del cerebro nunca se ejecuta, solo se compila.** Lo malicioso no está incluido todavía.

Necesita un **JDK** para la parte de Java (con solo un JRE no hay compilador). En el PC de origen se usó Eclipse Temurin
21.0.13 portátil, comprobado por su SHA-256: detalles y enlace en `lab_flujos/JDK_EXTERNO.md`. Descomprímelo donde
quieras e indica el compilador con la variable `EQUIPO_JAVAC`:

```powershell
$env:EQUIPO_JAVAC = "C:\EquipoIA\jdk-21.0.13+9\bin\javac.exe"
py -B -X utf8 lab_revision\comprobar_sin_gpu.py            # sin GPU: 17/17 esperado
py -B -X utf8 lab_revision\banco_revision.py preparar evidencias\amigo_revision --condiciones solo herramienta3
py -B -X utf8 eq3\lanzador_eq2.py lab_revision\banco_revision.py ejecutar C:\EquipoIA\externos evidencias\amigo_revision
py -B -X utf8 lab_revision\banco_revision.py informe evidencias\amigo_revision
```

Resultados del PC de origen en `evidencias\v31_lab_revision\tanda1` a `tanda3` y en `lab_revision\PRERREGISTRO_*`.
Para enviar de vuelta: `INFORME.md` y `peticiones.jsonl` (sin rutas de tu PC).

## Leer código Java (mods de Minecraft y similares)

Contexto Ligero lee también **Java**: clases, interfaces, enums (con sus valores), `record`, métodos, constructores,
sobrecargas (`Clase.metodo#2`), campos y constantes, con sus **anotaciones** (`@SubscribeEvent`, `@Inject`, `@Mixin`…)
y las **llamadas entre clases** resueltas por `package` e `import` (también `import static`). Al pedir el código de un
método, entrega además la cabecera de su clase, los campos y constantes que usa y los métodos a los que llama (hasta
varios saltos). Comprobación con un mod de ejemplo, sin GPU:

```powershell
py -B -X utf8 lab_flujos\humo\comprobar_java.py
```

Para usarlo con tu propio mod (con tu código, no con código descompilado del juego, que no se debe compartir):

```powershell
cd ..\fuentes\contexto_ligero_v35
py -B -X utf8 contexto_v3.py --db C:\EquipoIA\mimod.sqlite3 scan C:\ruta\a\tu\mod
py -B -X utf8 contexto_v3.py --db C:\EquipoIA\mimod.sqlite3 query "qué pasa al romper un bloque"
py -B -X utf8 contexto_v3.py --db C:\EquipoIA\mimod.sqlite3 bundle C:\ruta\a\tu\mod "romper bloque" --budget 3000 --allow-partial
```

**Límites (sin compilador):** no resuelve tipos, herencia ni sobrecargas por sus argumentos; una llamada sobre un objeto
(`jugador.quemar()`) no sabe de qué clase es; los métodos de interfaz sin cuerpo se indexan, pero sin código que
mostrar. El banco de flujos con cerebros sigue siendo de Python.

## Banco de Blender (opcional)

Necesita Blender 5.2 instalado (o la variable `BLENDER_EXE`). Desde `equipo_ia_v3\`:

```powershell
py -B -X utf8 lab_blender\banco.py validar C:\EquipoIA\blender_lab
py -B -X utf8 eq3\lanzador_eq2.py lab_blender\banco.py ejecutar C:\EquipoIA\externos evidencias\amigo_blender C:\EquipoIA\blender_lab --modelos qwen25 ministral3 --manual lab_blender\MANUAL_BLENDER_V6.md
```

## Aviso sincero

- Lo verificado en el PC de origen: todo lo de este paquete en Windows 11 con Python 3.12 y una RTX 3050 de 8 GB.
  La imagen Docker se construyó y ejecutó en ese mismo PC (ver el final de este documento si no fuera así).
- Contexto Ligero lleva tres cambios del 2026-11-15 sobre la V3.5 original: lectura en Windows (`safety.py`), índice
  de constantes de módulo y lectura de Java (`index.py`, `support.py`, `data_support.py`). Detalles en
  `equipo_ia_v3/AUDITORIA_CONTEXTO_TOKENS_2026-11-15.md` y `lab_flujos/PRERREGISTRO_FLUJOS_T5.md`.
- Equipo IA es un sistema experimental: no está listo para producción.
