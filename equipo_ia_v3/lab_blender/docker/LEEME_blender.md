# Banco de Blender para modelos de IA locales

Mide si un modelo de lenguaje **local** sabe escribir scripts de Blender que cumplan una tarea, y si corrige cuando se le
devuelve lo que salió mal. El ciclo es:

    modelo escribe un script → filtro de seguridad → Blender lo ejecuta sin ventana → un verificador SIN IA mide la escena
    → si falla, el modelo recibe lo medido y corrige (hasta 3 intentos)

Quien decide si una tarea está aprobada es el verificador (medidas: nombres, tamaños, posiciones, piezas unidas, movimiento),
nunca un modelo. Hay 12 tareas, de un cubo a un robot de cajas que camina.

## Qué necesitas
- Docker.
- Un servidor de modelos en tu máquina con API compatible con OpenAI: `llama-server` de llama.cpp, Ollama, LM Studio…
  **La imagen no trae ningún modelo** y no usa servicios de pago ni claves.

## 1. Construir
    docker build -t banco-blender .

Descarga Blender 5.2.3 para Linux de blender.org (unos 400 MB). Si esa versión ya no está, pasa otra con
`--build-arg BLENDER_URL=…` (las tareas se validaron con Blender 5.2.3).

## 2. Comprobar que funciona (sin modelo)
    docker run --rm banco-blender -m unittest discover -s pruebas -t pruebas -p "test_lab_blender_*.py"
    docker run --rm -v "$PWD/datos:/datos" banco-blender lab_blender/banco.py validar /datos/blender

La segunda orden ejecuta las 12 soluciones de referencia y debe terminar con `"ok": true`.

## 3. Evaluar un modelo
Arranca tu servidor de modelos en el puerto que quieras (ejemplo: 8080) y lanza:

    docker run --rm -v "$PWD/datos:/datos" --add-host=host.docker.internal:host-gateway --memory 8g banco-blender \
        lab_blender/portable.py /datos/evidencia_MIMODELO /datos/blender \
        --url http://host.docker.internal:8080/v1 --modelo MIMODELO

- Con Ollama la URL suele ser `http://host.docker.internal:11434/v1` y `--modelo` el nombre del modelo en Ollama.
- El resultado queda en `datos/evidencia_MIMODELO/INFORME.md` (tabla por tarea) y `peticiones.jsonl` (cada intento: lo que
  escribió el modelo, el estado y lo que midió el verificador).
- Para parar: crea un archivo `STOP` en `datos/evidencia_MIMODELO`. Para seguir después: la misma orden con `--reanudar`.
- Solo algunas tareas: `--tareas T01 T02 T03`.
- El modelo necesita un contexto de al menos 4096 tokens; cada respuesta se limita a 800.

## Seguridad: léelo antes de usarlo
El banco **ejecuta código escrito por un modelo**. Las barreras son:
1. Filtro por lista de permitidos (`lab_blender/filtro.py`): solo `bpy`, `bmesh`, `mathutils`, `math` y `random`; sin
   archivos, red, clases, `eval`/`exec`, ni operadores de guardar, exportar o renderizar. Un script que no pasa no se ejecuta.
2. El filtro se repite dentro de Blender, y dentro solo existen las funciones de una lista cerrada.
3. Blender arranca de fábrica, sin complementos, sin scripts automáticos y sin red (`--offline-mode`).
4. Límites de tiempo (90 s) y de memoria por ejecución; cada intento va en una carpeta nueva y los `.blend` de partida se copian.
5. En esta imagen, además, todo corre como un usuario sin privilegios dentro del contenedor.

**El filtro no es un aislamiento perfecto**: es una lista hecha a mano. Por eso conviene usarlo como aquí, dentro de un
contenedor, montando solo la carpeta `datos` y con `--memory`. No montes carpetas personales en el contenedor.

## Privacidad
- El paquete solo contiene código, las tareas y sus pruebas. No lleva modelos, resultados, rutas ni datos de nadie.
- El banco solo se conecta a la URL que tú le das. No envía telemetría ni usa claves.
- Lo que escriba tu modelo se guarda en tu carpeta `datos`, en tu máquina.

## Límites que conviene conocer
- **No probado en Linux ni dentro de Docker por quien lo escribió**: se desarrolló y probó en Windows con Blender 5.2.3
  (115 pruebas). El Dockerfile está escrito con cuidado pero sin construir; si falta alguna biblioteca del sistema, Blender
  lo dirá al arrancar. La validación del paso 2 es justo para comprobarlo.
- Los vídeos (`--videos`) necesitan una GPU que Blender pueda usar dentro del contenedor; sin ella, omite esa opción.
  Medir las tareas no necesita GPU.
- Son 12 tareas y una pasada por modelo: orienta, no es una medida estadística.
- El prompt incluye una «chuleta» con las recetas básicas de Blender, igual para todos los modelos. Las tareas y el
  enunciado están en español.
- El verificador mide cajas envolventes: no juzga la estética ni ve una pieza girada dentro de su caja.

## Resultado de ejemplo (dos modelos de 7–9 mil millones de parámetros, cuantizados a 4 bits)
| modelo | aprobadas | a la primera | gracias a corregir |
|---|---|---|---|
| Qwen2.5-Coder 7B | 9 de 12 | 5 | 4 |
| Yi-Coder 9B | 8 de 12 | 6 | 2 |

Ninguno consiguió el robot completo desde cero ni la caminata. Los dos añadieron bien una pieza a un robot ya hecho.

## Archivos
| archivo | qué hace |
|---|---|
| `lab_blender/filtro.py` | filtro de seguridad (no ejecuta nada) |
| `lab_blender/ejecutor.py` | lanza Blender con límites y recoge el resultado |
| `lab_blender/dentro_blender.py` | corre dentro de Blender: ejecuta el script y mide la escena |
| `lab_blender/verificador.py` | comprobaciones medibles, sin IA |
| `lab_blender/tareas.py` | las 12 tareas y sus soluciones de referencia |
| `lab_blender/banco.py` | bucle de intentos, análisis e informe (su orden `ejecutar` es de otro sistema: usa `portable.py`) |
| `lab_blender/portable.py` | el banco contra cualquier servidor local compatible con OpenAI |
| `MANIFIESTO.json` | SHA-256 de cada archivo |
