# Preregistro: banco de Blender, tanda 12 (arquitecturas: el cerebro dice QUÉ, un programa calcula el CUÁNTO)

Escrito ANTES de preguntar a ningún cerebro. Fecha: 2026-11-15. Base: `ESTUDIO_ARQUITECTURAS.md`.

## Pregunta
En las tandas 9–11 los cerebros entienden la estructura del robot pero fallan al combinar medidas. Si la geometría
la calcula un programa, ¿construyen el robot bien y de una vez?

## Verificador más estricto (corrección previa a esta tanda)
Revisando el vídeo de la tanda 11 se vio que «toca» aceptaba brazos metidos en el torso o colgando debajo de él. Se
añaden a T05 y T08 `a_un_lado` (cada brazo, por fuera del lado del torso y a su altura) y `sin_solapes` (ninguna
pieza dentro de otra): 28 y 35 comprobaciones. Las referencias aprueban; **con este verificador ningún robot de las
tandas anteriores queda aprobado** (lo mejor: ministral3, 25/28 en T05 y 32/35 en T08, tanda 11 por pasos).

## Condiciones (`arquitecturas.py`; robot entero en un turno, hasta 3 intentos con lo medido)
- **funciones (A)**: Python con una biblioteca ya cargada (`caja`, `encima`, `debajo`, `a_la_izquierda`,
  `a_la_derecha`, `en_el_suelo`, `poner`, `mover`, `hijo`, `avanzar`) que hace las cuentas. Sin el manual v6 (enseña
  bpy suelto); su lugar lo ocupa la descripción de la biblioteca con un ejemplo que no es la tarea (una mesa).
- **relacional (B)**: solo un JSON de piezas, medidas, padres y relaciones (`encima`, `debajo`, `izquierda`,
  `derecha`, `en_el_suelo`, `x/y/z`) y la animación. Un resolvedor sin IA, fuera de Blender, coloca las piezas, avisa
  de conflictos y genera el script. Un error del resolvedor gasta intento y se le devuelve tal cual.
Cerebros qwen25 y ministral3, 800 tokens, temperatura 0, mismo armazón y filtro de seguridad.

## Comprobado antes (sin cerebro real; `comprobar_arquitecturas.py`, 11/11)
Resolvedor: posiciones exactas, conflicto, relación desconocida, pieza inexistente, referencia sin posición, JSON roto
y orden indiferente. En Blender real, cerebros falsos que fallan adrede el 1.er intento (brazos bajo el torso en A;
conflicto en B) aprueban T05 28/28 y T08 35/35 al 2.º.

## Reglas de decisión (fijadas antes de ver resultados)
1. **La arquitectura funciona** si, en alguna condición, cada cerebro aprueba al menos uno de los dos robots.
2. **Resultado fuerte**: alguna condición en la que los dos cerebros aprueban los dos robots.
3. **Mejor que pasos**: una condición supera, en suma de comprobaciones de los 4 robots, a la tanda 11 por pasos
   revisada con el verificador estricto (2 + 2 + 25 + 32 = 61 de 126).
4. Se informa qué falla en cada condición (relaciones mal elegidas, medidas, JSON, padres, animación) y cuántos
   intentos hacen falta.

## Resultado (2026-11-15; ~20 minutos, sin paradas)

| | funciones T05 | funciones T08 | relacional T05 | relacional T08 |
|---|---|---|---|---|
| qwen25 | 26/28 | 33/35 | **28/28 APROBADO (3.er)** | 0/35 (3 conflictos) |
| ministral3 | 25/28 | 32/35 | **28/28 APROBADO (3.er)** | 33/35 |

**Primeros robots aprobados con el verificador estricto**, y por los dos cerebros (qwen25 nunca había pasado de la
cabeza). Imagen del de ministral3: `externos/blender_lab/videos_tanda12/ministral3_rel_T05/fotograma_0001.png`.

Veredictos según las reglas fijadas:
1. **La arquitectura funciona: SÍ** (relacional: cada cerebro aprueba T05).
2. **Resultado fuerte: NO** (nadie aprueba T08).
3. **Mejor que pasos: SÍ** en las dos (mejor intento por robot): funciones 116/126, relacional 89/126, frente a 61/126
   de la tanda 11 por pasos.

Qué falla ahora (ya no son cuentas: la geometría sale exacta siempre; son ELECCIONES de una sola palabra):
- qwen25 funciones: escribe `debajo("Cabeza", "Torso")` en vez de `encima` y lo repite 3 veces aunque se le dice que la
  base de la cabeza está a 0,90 y lo alto del torso a 2,60.
- ministral3 funciones: coloca las piernas con `a_la_izquierda`/`a_la_derecha`, que también fijan la altura del torso y
  deshacen el `en_el_suelo` anterior (trampa de la biblioteca: el nombre no dice que cambia z); además inventa un
  tercer argumento (`a_la_izquierda(…, 0.25)`) y el script falla.
- relacional: sin una relación de x, las dos piernas quedan en x = 0; ministral3 lo «arregla» en T08 con `y` en vez de
  `x`. qwen25 en T08 da a la vez un `centro` (mal calculado) y la relación `encima`; el resolvedor avisa del conflicto,
  pero qwen25 cambia el número del centro en vez de quitarlo, y la escena no llega a construirse (todo o nada).

## Para la siguiente tanda (propuestas)
- Avisos del resolvedor que propongan el arreglo: «sobra el "centro" de «Cabeza»: la relación ya la coloca».
- Relación de simetría (`["simetricos_x", "Pierna_I", "Pierna_D", separación]`) para piernas y brazos.
- En funciones: que cada función cambie solo lo que dice su nombre (o avisar si deshace algo ya fijado).
- Traducir lo medido por el verificador al vocabulario de relaciones («la cabeza quedó DEBAJO del torso: usa encima»).
