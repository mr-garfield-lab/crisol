# Plan de mejoras para flujos grandes de información (código, Blender y análisis)

Fecha: 2026-11-15. Ordenado por impacto y por lo que ya está medido. «Medido» = hay evidencia en
`evidencias/v31_lab_flujos`; «propuesta» = sin probar todavía.

## Ya hecho
1. **Banco de flujos grandes** (`lab_flujos/`): proyecto sintético 65 veces mayor que el contexto, respuestas exactas
   conocidas, verificador sin IA, prerregistro. Medido en la tanda 1.
2. **Contexto Ligero funcionando en Windows** (`fuentes/contexto_ligero_v35/contexto_core/safety.py`, con copia de
   seguridad). Medido: 68/68 archivos indexados, pruebas propias rotas de 137 a 13 (las 13 por permisos de symlinks).
3. **Flujo híbrido con troceado y puntos de guardado** (condición `hibrida` del banco): enrutador, filtro léxico,
   trozos que no parten funciones, guardado por trozo, verificación de nombres. Comprobado con un cerebro falso;
   medido en la tanda 2: +7 aciertos en los dos cerebros (21 y 23 de 24), 0 inventadas, 0 trozos repetidos.

## Siguiente (en este orden)
0. **Medido en la tanda 2 (pendiente de prerregistrar en la tanda 3):** verificación estricta en los recuentos (el
   cuerpo de la función debe contener lo que nombra la pregunta; con eso, 6/6 recuentos exactos sobre los mismos
   datos) y repetir la instrucción de formato en cada turno (qwen25 la pierde en la segunda ronda).
4. **Contexto Ligero: indexar constantes de módulo** (`LIMITE = 7`, `TOPE_MAX_TOKENS = 800`) como símbolos. Hoy
   solo indexa funciones y clases, y por eso no encuentra esas respuestas (medido: D y R1–R2 a 0 en `ligero`). El
   troceado lo compensa, pero gastando más llamadas. Toca `fuentes/contexto_ligero_v35`: con tu aprobación.
5. **Avisar del error de la carpeta de indexado:** si se indexa la carpeta del propio paquete, se pierden todas las
   llamadas entre módulos (medido: 0 frente a 28 en el corpus; 473 frente a 880 relaciones en `sistema/src/eq2`).
   Propuesta: que `scan` avise si la raíz contiene `__init__.py` y no hay ninguna relación entre módulos.
6. **Dos saltos en el troceado:** si Contexto Ligero no encuentra una respuesta que está en OTRA función (tipo B), el
   troceado de hoy no sigue el `import`. Propuesta: seguir los imports de forma determinista (sin IA) y añadir esos
   archivos al filtro.
7. **Llevarlo al sistema real** (`sistema/src/eq2`): un modo «lector de proyectos grandes» en el orquestador con el
   mismo enrutador y puntos de guardado, cuando el banco lo confirme. Toca el núcleo: prerregistro y aprobación.

## Propuesta del usuario (2026-11-15): revisión de código
- **Detectar código que no funciona o es malicioso**, con la regla de este banco: el cerebro propone y las
  herramientas comprueban. Compilación y línea exacta del error sin IA (`ast`, `py_compile`); el cerebro explica y
  propone el arreglo; el sistema verifica que la línea citada existe, que el error se reproduce y que el arreglo
  compila. Para lo malicioso se parte del filtro de seguridad del banco de Blender (módulos, llamadas y accesos
  prohibidos) y de la redacción de secretos de Contexto Ligero; el cerebro aporta sospechas más sutiles (ofuscación,
  descargas escondidas), siempre citando una línea real que se comprueba.
- **Comprobar el código que escribe el propio agente antes de entregarlo** (también propuesta del usuario):
  compilar, filtro de seguridad y pruebas si las hay; si falla, el error vuelve al cerebro con la línea exacta
  (estilo editor) para que corrija, con un tope de intentos; si no lo consigue, se entrega marcado como «no
  funciona, por esto», nunca como bueno. Ya medido en el banco de Blender (3 intentos con lo medido: 3–4 tareas
  aprobadas más por cerebro gracias a corregir); falta generalizarlo a todo el código y localizar mejor el error.
- Medirlo con un **banco de revisión**: proyecto con fallos y trampas maliciosas plantadas, oráculo exacto; medir
  aciertos, falsas alarmas y si la línea citada es la correcta.

## Fallo encontrado en el empaquetador (2026-11-15)
- `v3/empaquetar.py` no revisa ni anonimiza los archivos que no son texto UTF-8: un `server.log` con un byte no UTF-8,
  las imágenes PNG (Blender escribe la ruta en sus metadatos) y los vídeos entraban tal cual, con la carpeta de
  trabajo de la máquina de origen dentro. Mitigado en `lab_flujos/paquete_amigo.py` (excluye esos tipos y rechaza el
  paquete si entra cualquier archivo no UTF-8). Pendiente: corregirlo en el propio empaquetador.

## Después
8. **Varias continuaciones con tope**, en vez de una sola por respuesta (hoy ~1.000 tokens máximos de salida por
   respuesta). Útil para respuestas largas (informes, scripts grandes de Blender). Toca el núcleo.
9. **Medir contexto de 8192** con qwen25: calculo ~0,5 GB más de VRAM; hay que medir VRAM, velocidad y si el cerebro
   pierde precisión con prompts largos (el banco de flujos sirve para eso tal cual).
10. **Banco de flujos con proyectos reales más grandes** (por ejemplo, el propio `equipo_ia_v3` entero o una
    biblioteca conocida), con preguntas cuyo oráculo se saque con `ast`.
11. **`concluyente` en Windows:** documentar que siempre sale `false` por la falta de `majflt`, o medir otra cosa
    equivalente, para que no se use como alarma.
12. **Validar en Termux** (Android), que es el objetivo original del proyecto.
