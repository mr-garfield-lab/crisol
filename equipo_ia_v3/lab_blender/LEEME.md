# lab_blender: ejecutar en Blender scripts escritos por cerebros (laboratorio)

Autorizado por el usuario el 2026-11-13 («sí, con filtro»): los cerebros pueden escribir scripts de Blender y este laboratorio
los ejecuta **solo** con las barreras de abajo, **solo** en Blender, y **solo** sobre escenas nuevas o copias. La regla general
de Equipo IA («no ejecutar código de los agentes») sigue vigente fuera de esta carpeta.

Estado (2026-11-14): filtro, ejecutor, verificador, 12 tareas y banco hechos y probados. Tanda 1 REAL con dos cerebros
(46 intentos, sin abortos): Qwen2.5-Coder 9 de 12 y Yi-Coder 8 de 12; ninguno hizo el robot completo ni la caminata.
Informe: `evidencias/v31_lab_blender/tanda1/INFORME.md`. Faltan Gemma 4, Qwen3, Granite y Ministral 3.
Paquete para compartir (Docker, sin datos personales): `lab_blender/docker/` y `entregas/banco_blender_docker_v1.zip`
(la imagen Docker NO se ha construido ni probado aquí).

## Piezas
| archivo | qué hace |
|---|---|
| `filtro.py` | Lee el script (no lo ejecuta) y lo rechaza si usa algo fuera de la lista de permitidos. Da el motivo y la línea. |
| `ejecutor.py` | Filtra, lanza Blender sin ventana, vigila tiempo y memoria, y escribe `resultado.json`. |
| `dentro_blender.py` | Corre dentro de Blender: repite el filtro, ejecuta el script con funciones cerradas, mide la escena, guarda y renderiza. |

## Barreras (en este orden)
1. **Filtro por lista de permitidos.** Módulos: `bpy`, `bmesh`, `mathutils`, `math`, `random`. Funciones integradas: una lista
   corta (sin `open`, `eval`, `exec`, `getattr`, `type`…). Operadores: solo `bpy.ops.` mesh, object, transform, material, curve,
   surface, armature, pose, anim, collection, uv, geometry y constraint, llamados directamente (sin guardar `bpy.ops` en una
   variable). Rechaza clases, decoradores, atributos que empiezan por `_`, marcos de ejecución (`gi_frame`, `f_back`…),
   rutas de archivo (escribir en `.filepath`, argumentos `filepath=`/`directory=`), `bpy.app`, `bpy.utils`, `bpy.types`,
   textos, bibliotecas, drivers, preferencias y modificar los módulos importados.
2. **El filtro se repite dentro de Blender**, con la huella SHA-256 del script que revisó el ejecutor.
3. **Funciones cerradas al ejecutar**: dentro solo existen las funciones de la lista y un `import` que solo admite los cinco módulos.
4. **Blender de fábrica**: `-b --factory-startup -Y --offline-mode` (sin ventana, sin complementos del usuario, sin scripts
   automáticos, sin red). No se heredan variables `PYTHON*` ni `BLENDER_*`.
5. **Límites**: tiempo (120 s por defecto), memoria (6000 MB), número de objetos y de vértices. Si se pasa, el ejecutor
   termina el proceso que lanzó él y lo anota (`TIEMPO`, `MEMORIA`, `LIMITE`). Un archivo `STOP` en la carpeta de salida lo para.
6. **Solo copias**: cada ejecución va en una carpeta nueva; un `.blend` de partida se copia y se comprueba que el original
   no cambia (tamaño, fecha y SHA-256).
7. **El render lo hace el ejecutor**, nunca el script: `bpy.ops.render` está fuera de la lista.

## Lo que NO garantiza
- No es un aislamiento del sistema operativo: Blender corre con los permisos del usuario. El filtro es una lista de permitidos
  hecha a mano y puede tener huecos; por eso hay varias barreras y límites. No ejecutar scripts de origen desconocido.
- Un script puede gastar CPU y memoria hasta el límite, y dejar la escena rota o vacía (eso es un fallo del script, no un riesgo).
- Una simulación que escribe cachés (fluidos, océano…) se detecta después de ejecutar el script y antes de medir la animación.
- El informe da hechos, no dice si el resultado es bueno: eso será trabajo del verificador (pendiente).

## Uso
    py -B -X utf8 lab_blender/filtro.py SCRIPT.py
    py -B -X utf8 lab_blender/ejecutor.py SCRIPT.py CARPETA_NUEVA [--base X.blend] [--fotogramas 1 24] [--video]
                                          [--motor BLENDER_EEVEE] [--resolucion 1280 720] [--tiempo 120]

Estados: `OK`, `RECHAZADO` (no pasó el filtro; Blender no se lanza), `ERROR_SCRIPT` (con la línea), `LIMITE`, `TIEMPO`,
`MEMORIA`, `PARADO`, `FALLO_BLENDER`. En la carpeta quedan `script_cerebro.py`, `resultado.json`, `informe.json`,
`resultado.blend`, la salida de Blender y los fotogramas o el vídeo.

`informe.json` → `escena`: por objeto, nombre, tipo, posición, rotación, dimensiones, caja envolvente, padre, materiales, los
dos colores (nodos y vista 3D), modificadores, y sus posiciones en 5 fotogramas de muestra (`se_mueve`).
Ojo: en Blender 5 los materiales siempre usan nodos; `diffuse_color` solo cambia el color de la vista 3D, no el del render.

## Pruebas
    py -B -X utf8 -m unittest discover -s pruebas -t pruebas -p "test_lab_blender_*.py"

23 pruebas: 6 del filtro (unos 80 scripts peligrosos y los que sí deben pasar), 4 sin Blender, 5 SIMULADAS de las funciones
cerradas (con módulos bpy vacíos) y 8 REALES que lanzan el Blender instalado sin render (unos 30 s): hechos de la escena,
error con su línea, corte por tiempo, corte por memoria, filtro repetido dentro, copia del `.blend`, límites. Sin Blender, las
reales se OMITEN. El render con Eevee (vídeo 1280×720, 48 fotogramas, unos 20 s) se probó a mano: `evidencias/v31_lab_blender/`.

## Más piezas (2026-11-14)
| archivo | qué hace |
|---|---|
| `verificador.py` | Comprobaciones medibles sobre los hechos de la escena, sin IA. Su texto de fallos es lo que recibe el cerebro. |
| `tareas.py` | 12 tareas (T01–T10, B01–B02) con comprobaciones y soluciones de referencia (no entran en ningún prompt). |
| `banco.py` | `validar` (referencias), `ejecutar` (cerebros con la seguridad de V5, sin render), `estado`, `informe`, `videos`. |
| `portable.py` | El mismo bucle contra cualquier servidor local compatible con OpenAI (sin la vigilancia de V5). |
| `docker/` | Dockerfile, LEEME y `empaquetar.py` (revisa que no salgan datos personales antes de crear el ZIP). |

El backend de V2-F.1 limita cada respuesta a 800 tokens: un script largo puede quedar cortado (Yi-Coder: 5 veces en la tanda 1).
