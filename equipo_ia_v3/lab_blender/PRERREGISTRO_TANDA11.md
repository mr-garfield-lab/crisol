# Preregistro: banco de Blender, tanda 11 (pasos + cuentas con lo medido + reescritura detectada)

Escrito ANTES de preguntar a ningún cerebro. Fecha: 2026-11-15.

## Pregunta
En la tanda 10 los cerebros leen la pista geométrica pero no hacen la cuenta, y ministral3 perdió T05 al reescribir
el script aprobado (torso duplicado). Si se les da la cuenta hecha con lo que midió Blender en SU intento y se frena
la reescritura, ¿terminan los robots?

## Cambio respecto a la tanda 10 (`pasos.py --cuentas`, que incluye `--mejoras`)
- **Cuentas con lo medido** (sin IA, de las cajas de la escena de Blender del intento fallido): para `encima`, `toca`,
  `apoyado`, `centro` y `dimensiones`, cuánto mover la pieza y en qué eje, o por cuánto multiplicar su scale.
  Ejemplo: «la base de «Cabeza» está a z = 2.35 y lo alto de «Torso» a z = 2.60: mueve «Cabeza» +0.25 m en z».
- **Reescritura detectada antes de Blender**: si el código nuevo vuelve a poner nombre a una pieza ya aprobada
  (`ob.name = "Torso"` o `caja("Torso", …)`), no se ejecuta ni gasta intento; se le pide una vez más solo lo nuevo.
  Queda en la evidencia como fila `reescritura`.
Todo lo demás igual que las tandas 9 y 10.

## Comprobado antes (cerebro falso, Blender real; `comprobar_pasos.py`, 4/4)
Las tandas 9 y 10 se reproducen igual sin el nuevo interruptor. Con `--cuentas`: una cabeza baja (el fallo real de la
tanda 10) se arregla al 2.º intento con la cuenta «+0.25 m en z»; una reescritura del torso en las piernas se detecta,
se pide otra vez y las piernas pasan al 1.er intento. Aprobado 25/25.

## Reglas de decisión (fijadas antes de ver resultados)
1. **Las cuentas desatascan** si al menos 3 de los 4 robots superan el paso de la cabeza.
2. **Los pasos aportan**: cada cerebro aprueba al menos uno de los dos robots completos.
3. **Resultado fuerte**: los dos cerebros aprueban los dos robots.
4. Se informa cuántas reescrituras se detectan y si la segunda petición las corrige.

## Resultado (2026-11-15; sin paradas)

| | T05 (t9 → t10 → **t11**) | T08 (t9 → t10 → **t11**) |
|---|---|---|
| qwen25 | 2/25 → 2/25 → 2/25 | 2/32 → 2/32 → 2/32 |
| ministral3 | 25/25 → 2/25 → **25/25 APROBADO** | 2/32 → 16/32 → **32/32 APROBADO** |

**Primera vez que un cerebro aprueba el robot animado T08**, y ministral3 aprueba los dos robots con solo 6 llamadas
cada uno.

Veredictos según las reglas fijadas:
1. **Las cuentas desatascan: NO** (2 de 4 superan la cabeza; hacían falta 3).
2. **Los pasos aportan: NO** (qwen25 no aprueba ninguno).
3. **Resultado fuerte: NO.**
4. **Reescrituras detectadas: 0.** Esta vez ningún cerebro reescribió lo aprobado; el detector no se puso a prueba.

Cómo lo consigue ministral3: la cuenta del torso («mueve +0.80 m en z») le hace escribir un torso limpio con
`location=(0, 0, 2.0)` en vez del apaño de las tandas 9 y 10 (crearlo en 0,6 y luego `location.z = 2.0`). Con ese
script delante, en la cabeza escribe la cuenta él solo, `2.0 + 1.2 / 2 + 0.5 / 2`, y acierta al primer intento. Las
piernas las arregla al 2.º intento con «mueve −0.70 m en z». **Un paso anterior limpio hace fáciles los siguientes.**

Cómo falla qwen25: oscila entre dos restricciones. Crea la cabeza con `size=0.5` y además `scale=0.5` (mide 0,25).
Cuando arregla la altura (+0,12, cuenta hecha para la cabeza pequeña) sigue mal el tamaño; cuando arregla el tamaño
(`size=1`) conserva el +0,12 y la base vuelve a quedar baja. No sostiene dos datos a la vez.

Lectura: cuando el cerebro tiene que combinar varias medidas, falla; si el número le llega hecho o puede escribir la
cuenta con datos limpios delante, acierta. Apunta a una arquitectura en la que el cerebro diga **qué** va dónde y un
programa calcule el **cuánto** (estudio pendiente, antes de la tanda 12).

## CORRECCIÓN (2026-11-15, revisando el vídeo del robot animado)
El verificador tenía un hueco: «toca» daba por buena cualquier caja pegada o METIDA en el torso, y nada comprobaba
que los brazos estuvieran a los lados. Los robots «aprobados» tenían los brazos mal:
- tanda 9, ministral3 T05: brazos metidos 0,10 m en el torso y colgando casi enteros por debajo (z 0,5–1,5).
- tanda 11, ministral3 T05: brazos metidos 0,12 m en el torso.
- tanda 11, ministral3 T08: brazos DEBAJO del torso, metidos 0,23 m dentro de las piernas.
Se añaden a T05 y T08 tres comprobaciones (`a_un_lado` para cada brazo y `sin_solapes` entre todas las piezas); las
referencias siguen aprobando (28/28 y 35/35). Revisados con ellas, **ningún robot de ninguna tanda queda aprobado**:
los tres pasan a 25/28, 25/28 y 32/35. Las lecturas sobre la cabeza y las cuentas siguen valiendo; lo de «primer
robot aprobado» no.
