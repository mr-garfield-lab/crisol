# Preregistro: banco de revisión de código, tanda 2 (imports colocados sin IA y aviso de arreglo repetido)

Escrito ANTES de preguntar a ningún cerebro. Fecha: 2026-11-15.

## Pregunta
En la tanda 1, con la herramienta delante, quedaron sin arreglar 5 casos de qwen25 y 3 de ministral3, por dos causas:
los `import` de Java puestos DENTRO de la clase (4 de 6 fallos de Java) y un mismo arreglo equivocado repetido tres
veces. ¿Las dos mejoras sin IA los resuelven sin estropear nada?

## Qué cambia (condición `herramienta2`; el resto, idéntico a `herramienta` de la tanda 1)
1. **Imports colocados por el sistema**: cualquier `import` que proponga el cerebro (con ARREGLO o INSERTAR) se quita
   de donde lo puso y se coloca arriba, tras los demás import (o tras `package` / el docstring). Si un ARREGLO ponía
   el import ENCIMA de una línea que no era un import, esa línea se conserva.
2. **Aviso de arreglo repetido**: si, tras aplicar el arreglo, el compilador sigue fallando en una línea que el cerebro
   acaba de cambiar, el siguiente intento lleva «AVISO: tu arreglo anterior en la línea N no resolvió el error; ahora
   esa línea dice «…». Propón un arreglo DISTINTO». Si la respuesta no traía ningún arreglo aplicable, se le avisa.
- Mismos 32 casos (mismo corpus, oráculo revalidado con las herramientas), mismos cerebros (qwen25, ministral3),
  contexto 4096, `max_tokens` 500, temperatura 0, hasta 3 intentos, el código del cerebro nunca se ejecuta.

## Comprobado antes (cerebros falsos que imitan los fallos reales; `comprobar_sin_gpu.py`, 14/14)
- Import encima del campo (como qwen25): `herramienta` → no compila en 3 llamadas; `herramienta2` → arreglado en 1 y
  el campo se conserva.
- Arreglo repetido (`total = totl`) que solo cambia con un aviso: `herramienta` → no compila en 3; `herramienta2` →
  arreglado en 2.

## Reglas de decisión (fijadas antes de ver resultados; base: `herramienta` de la tanda 1)
1. **Las mejoras aportan** si `herramienta2` arregla al menos 2 casos más que la tanda 1 en los DOS cerebros
   (tanda 1: qwen25 19/24, ministral3 21/24).
2. **Imports de Java**: los 2 casos de import que falta en Java (JV_INV_E4, JV_RUT_E4) arreglados en los dos cerebros
   (tanda 1: 0 de 2 en los dos).
3. **Sin retroceso**: 0 archivos rotos, como mucho 3 arreglos que tocan de más, y ningún caso que la tanda 1 arreglaba
   y la tanda 2 no (se permite 1 por cerebro como ruido).

## Resultado (2026-11-15; 5 minutos, sin paradas)

| | qwen25 T1 → **T2** | ministral3 T1 → **T2** |
|---|---|---|
| Arreglados (de 24) | 19 → **21** | 21 → **23** |
| Imports de Java (de 2) | 0 → 1 | 0 → **2** |
| Gana / pierde | gana PY_INV_E2, PY_INV_F2, JV_INV_E4 · pierde PY_RUT_E3 | gana JV_INV_E4, JV_RUT_E4 · pierde ninguno |
| Rotos / tocando de más | 0 / 0 | 0 / 0 |
| Llamadas | 38 → 36 | 36 → 32 |
| Avisos dados / imports recolocados | 8 / 5 | 2 / 4 |

Veredictos según las reglas fijadas:
1. **Las mejoras aportan: SÍ** (+2 en los dos).
2. **Imports de Java: NO en qwen25** (1 de 2; ministral3 2 de 2). La causa del que falla no es la colocación: qwen25
   escribió una orden dentro de otra («ARREGLO 18: INSERTAR 18: import java.util.Arrays;») y el lector la tomó
   literal.
3. **Sin retroceso: SÍ** (0 rotos, 0 tocando de más; qwen25 pierde 1 caso, dentro del margen de ruido).

El caso perdido (qwen25, PY_RUT_E3), explicado: propuso `from math import ceil` para un código que usa `math.ceil`;
el sistema colocó bien el import, pero `math` sigue sin existir. El aviso no saltó porque la línea que falla no la
había tocado el cerebro (su cambio se recolocó). Pendiente (tanda 3): desenvolver órdenes anidadas y avisar cuando un
import recolocado no resuelve el error.
