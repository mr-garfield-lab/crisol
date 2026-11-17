# Preregistro: banco de Blender, tanda 10 (robots por pasos con avisos y pistas)

Escrito ANTES de preguntar a ningún cerebro. Fecha: 2026-11-15.

## Pregunta
En la tanda 9 (pasos, 3 intentos por paso), 3 de 4 robots se atascaron en la cabeza: qwen25 repitió el mismo código
en los 3 intentos y ministral3 no dio con la cuenta de «apoyar encima». ¿Se desatascan con un aviso de código
repetido y una pista geométrica genérica (sin los números de la tarea)?

## Cambio respecto a la tanda 9 (solo esto; `pasos.py --mejoras`)
En cada reintento, además de lo medido por el verificador:
- «tu código anterior falló; no lo repitas».
- Si el código es idéntico al del intento anterior: «tu último código es IDÉNTICO… escribe uno DISTINTO».
- Según la comprobación que falla (nunca con números de la tarea):
  - `encima` / `apoyado` / `toca` → cómo apoyar una caja encima de otra (centro = alto del otro + media altura);
  - `toca` → además, cómo tocarse por un lado (distancia entre centros = suma de medias anchuras);
  - `dimensiones` → medida final = size × scale (`primitive_cube_add` por defecto size = 2).
Todo lo demás igual: T05 y T08, mismos pasos, 3 intentos por paso, qwen25 y ministral3, manual v6, 800 tokens,
temperatura 0, mismo armazón y filtro de seguridad. Cada fila guarda qué comprobaciones fallaron.

## Comprobado antes (sin cerebro real, Blender real; `comprobar_pasos.py`)
Sin `--mejoras`, igual que la tanda 9 (T05 25/25, T08 32/32). Con `--mejoras`: un cerebro falso que repite la cabeza
mal solo la arregla cuando ve el aviso de IDÉNTICO y la pista de apoyo → aprobado 25/25 al tercer intento. Las pistas
no contienen números de la tarea.

## Reglas de decisión (fijadas antes de ver resultados)
1. **Las ayudas desatascan** si al menos 2 de los 3 robots atascados en la cabeza en la tanda 9 (qwen25 T05 y T08,
   ministral3 T08) superan ahora el paso de la cabeza.
2. **Los pasos aportan** (misma regla que la tanda 9): cada cerebro aprueba al menos uno de los dos robots completos.
3. **Sin retroceso**: ministral3 vuelve a aprobar T05; ningún robot termina con menos comprobaciones que en la tanda 9.
4. Se informa si qwen25 deja de repetir código idéntico y en qué paso se atasca cada uno.

## Resultado (2026-11-15; 8 minutos, sin paradas)

| | T05 tanda 9 → 10 | T08 tanda 9 → 10 |
|---|---|---|
| qwen25 | 1/4 pasos (2/25) → 1/4 pasos (2/25) | 1/5 pasos (2/32) → 1/5 pasos (2/32) |
| ministral3 | **4/4 APROBADO (25/25)** → 1/4 pasos (2/25) | 1/5 pasos (2/32) → **3/5 pasos (16/32)** |

Veredictos según las reglas fijadas:
1. **Las ayudas desatascan: NO.** Solo 1 de los 3 atascos en la cabeza se supera (ministral3 T08, al 2.º intento;
   luego pasa las piernas al 3.º y se atasca en los brazos: «toca» falla 3 veces).
2. **Los pasos aportan: NO.** Ningún robot aprobado.
3. **Sin retroceso: NO.** ministral3 pierde T05 (de 25/25 a 2/25).
4. qwen25 **deja de repetir código idéntico** (en T05 los 3 intentos son distintos; en T08 corrige el tamaño, de 5/7
   a 6/7), pero sigue poniendo el centro de la cabeza en lo alto del torso (z = 2,6): lee la pista y no aplica la cuenta.

Por qué pierde ministral3 T05: con el aviso cambia de camino. En el 2.º intento hace la cuenta casi bien (+0,35 en vez
de +0,25) pero usa `primitive_cube_add(...)[0]` y el script falla; en el 3.º **reescribe todo el script aprobado**
además del paso nuevo y deja un «Torso.001» duplicado.

Lectura: el aviso de repetido funciona (los cerebros cambian el código), pero la pista geométrica no basta para que
hagan la cuenta. Con temperatura 0 y una sola pasada por robot, cambiar el texto del aviso cambia toda la trayectoria:
ganar T08 y perder T05 puede ser en parte azar; harían falta varias pasadas por variante para separarlo.

## Para la siguiente tanda (propuestas)
- **Detectar la reescritura del script aprobado** antes de Blender (el código nuevo vuelve a crear objetos ya hechos)
  y pedir solo lo nuevo, sin gastar intento.
- Pista con la cuenta hecha sobre los datos MEDIDOS (no los de la tarea): «la base está a 2,35 y lo alto del otro a
  2,60: súbela 0,25». Es lo que el verificador ya sabe; no revela la solución de la tarea, solo traduce lo medido.
- Repetir cada variante varias veces (p. ej. con semillas o temperatura baja distinta de 0) para medir el ruido.
