# Preregistro: banco de revisión de código, tanda 3 (órdenes anidadas y aviso de import recolocado)

Escrito ANTES de preguntar a ningún cerebro. Fecha: 2026-11-15.

## Pregunta
En la tanda 2 quedaron 3 casos sin arreglar en qwen25 y 1 en ministral3. Dos de los de qwen25 tenían causa clara y
corregible sin IA: (a) una orden dentro de otra («ARREGLO 18: INSERTAR 18: import …»), tomada literal por el lector;
(b) un `from math import ceil` para un código que usa `math.ceil`: el import se colocó bien, pero el error siguió y no
saltó ningún aviso porque la línea que falla no la había tocado el cerebro. ¿Se resuelven sin estropear nada?

## Qué cambia (condición `herramienta3` = `herramienta2` más:)
1. **Órdenes anidadas**: el lector desenvuelve «ARREGLO N: INSERTAR N: …» y similares. (Este cambio está en el lector
   común; no afecta a las tandas ya puntuadas.)
2. **Aviso de import recolocado**: si el sistema colocó arriba un import del cerebro y el compilador sigue fallando
   por un nombre en otra línea, el siguiente intento dice qué import se colocó, en qué línea sigue el error y que
   compruebe que el import corresponde a cómo se usa el nombre.
- Mismo corpus (32 casos, oráculo revalidado), mismos cerebros, mismos parámetros que las tandas 1 y 2.

## Comprobado antes (falsos que repiten lo que hizo qwen25; `comprobar_sin_gpu.py`, 17/17)
Orden anidada → arreglado en 1 llamada. `from math import ceil` → con `herramienta2`, no compila en 3; con
`herramienta3`, arreglado en 2 (tras el aviso pone `import math`).

## Reglas de decisión (base: `herramienta2` de la tanda 2: qwen25 21/24, ministral3 23/24)
1. **Aporta** si qwen25 arregla 22 o más y ministral3 no baja de 23.
2. **Imports de Java**: los 2 casos de import que falta en Java, arreglados en los dos cerebros.
3. **Sin retroceso**: 0 archivos rotos, 0 arreglos que tocan de más, y como mucho 1 caso perdido frente a la tanda 2
   por cerebro.

## Resultado (2026-11-15; 5 minutos, sin paradas)

| | qwen25 T2 → **T3** | ministral3 T2 → **T3** |
|---|---|---|
| Arreglados (de 24) | 21 → **23** | 23 → **23** |
| Imports de Java (de 2) | 1 → **2** | 2 → **2** |
| Gana / pierde | gana PY_RUT_E3, JV_RUT_E4 · pierde ninguno | ninguno / ninguno |
| Rotos / tocando de más / falsas alarmas | 0 / 0 / 0 | 0 / 0 / 0 |

Veredictos: **1. Aporta: SÍ** (qwen25 23 ≥ 22; ministral3 se mantiene en 23). **2. Imports de Java: SÍ** (2 de 2 en
los dos). **3. Sin retroceso: SÍ** (0 rotos, 0 tocando de más, 0 casos perdidos).

Queda 1 caso por cerebro, los dos en Java y de estructura: qwen25 (JV_INV_E2) borra el `return` al arreglar el nombre
(«missing return statement»); ministral3 (JV_INV_F2) toca la llave del `main` al arreglar la sintaxis.

## Recorrido del banco de revisión (24 casos con error, 8 correctos)
| | solo | herramienta (T1) | + imports y aviso (T2) | + anidadas y aviso de import (T3) |
|---|---|---|---|---|
| qwen25 | 10 | 19 | 21 | **23** |
| ministral3 | 10 | 21 | 23 | **23** |
En todas las condiciones con herramienta: 0 archivos correctos rotos, 0 falsas alarmas y 0 arreglos que tocan de más.
