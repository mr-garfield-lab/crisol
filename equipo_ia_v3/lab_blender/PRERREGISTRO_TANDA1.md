# Preregistro de la tanda 1 del banco de Blender

Escrito ANTES de que ningún cerebro vea una tarea. Fecha: 2026-11-14.

## Qué se mide
Si un cerebro local sabe escribir scripts de Blender que cumplen una tarea medible, y si corrige cuando se le devuelve lo
medido. Decide el verificador sin IA (`verificador.py`); ningún cerebro juzga nada.

## Congelado en este commit
- 12 tareas de `tareas.py` (T01–T10 desde escena vacía, B01–B02 sobre la copia de un .blend) con sus comprobaciones.
- Prompt de sistema de `banco.py` (incluye una chuleta de la API igual para todos los cerebros), 3 intentos por tarea,
  800 tokens por respuesta (ver anotación al final), contexto 4096.
- Filtro y ejecutor de `lab_blender/` (límite de 90 s por ejecución). Durante la tanda Blender NO renderiza.
- Validación previa REAL (`evidencias/v31_lab_blender/validacion_tareas.json`): las 12 soluciones de referencia aprueban su
  tarea, un script vacío no aprueba ninguna y la solución de una tarea no aprueba otra, salvo dos casos esperados
  (T08 contiene T05; B01 contiene T05).

## Cerebros
`qwen25` (Qwen2.5-Coder 7B) y `yi` (Yi-Coder 9B): los dos «coder», de dos en dos. Los otros cuatro, después.

## Medidas por cerebro
1. Tareas aprobadas a la primera y tareas aprobadas en total (hasta 3 intentos); cuántas se ganan gracias a corregir.
2. Por tarea, comprobaciones cumplidas en cada intento (¿la corrección mejora o empeora?).
3. Estados: OK, ERROR_SCRIPT, RECHAZADO (filtro), TIEMPO, MEMORIA, LIMITE; respuestas cortadas por longitud.
4. Seguridad: scripts rechazados por el filtro y por qué; que los .blend de partida queden intactos.
5. La velocidad se anota y no decide nada.

## Criterios fijados antes
- «Útil para Blender sencillo»: aprueba al menos 8 de 12 tareas y las 4 primeras (T01–T04).
- «La corrección funciona»: al menos la mitad de las tareas falladas a la primera se aprueban después.
- Fallo de seguridad: que un .blend de partida cambie, o que se ejecute algo que el filtro debía parar. Un script rechazado
  por el filtro NO es un fallo de seguridad (el filtro hizo su trabajo), pero se cuenta.

## Límites conocidos
- 12 tareas y una sola pasada por cerebro: orientativo, sin intervalos fiables.
- Las tareas y la chuleta las escribió el mismo asistente que el verificador; las soluciones de referencia usan justo las
  recetas de la chuleta. Un cerebro que copie la chuleta lo tiene más fácil: es deliberado (se mide seguir instrucciones
  y componer geometría), y hay que decirlo al leer el resultado.
- El verificador mide cajas envolventes: no ve si una pieza está girada de forma rara dentro de su caja.
- No se juzga la estética. Los vídeos son para el usuario.

## Anotación antes de la primera petición (2026-11-14)
El primer lanzamiento abortó SIN hacer ninguna petición: el backend de V2-F.1 (`sistema/`, que no se modifica) admite como
máximo 800 tokens por respuesta y se pedían 1400. Se baja a 800 (ningún cerebro llegó a ver una tarea). Consecuencia: un
script largo puede quedar cortado; se cuenta como «respuestas cortadas por longitud». Evidencia del aborto:
`evidencias/v31_lab_blender/tanda1_abortada_sin_peticiones/`.
