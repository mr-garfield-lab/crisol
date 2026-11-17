# Preregistro: banco de Blender, tanda 13 (relacional v2: formas, articulaciones y fases)

Escrito ANTES de preguntar a ningún cerebro. Fecha: 2026-11-15.

## Pregunta
La tanda 12 mostró que, si el cerebro solo describe piezas y relaciones y un programa hace las cuentas, los dos
cerebros construyen el robot T05. ¿Llega esa arquitectura a piezas más complicadas (cilindros, esferas, conos),
articulaciones y una caminata? ¿Ayuda construir por fases y que los avisos propongan el arreglo?

## Cambios respecto a la tanda 12 (`relacional2.py`)
- **Piezas con forma**: `caja`, `cilindro`, `esfera`, `cono`, orientadas en x, y o z. El programa las construye con
  primitivas fijas (el verificador reconoce la forma por su número de vértices).
- **Articulaciones**: `{"pieza", "punto": arriba|abajo|centro}`; el programa pone ahí el origen de la pieza.
- **Animación** con desplazamiento del conjunto y giros por fotogramas clave en cada articulación.
- **Relaciones nuevas**: `delante`, `detras`, `espejo_x` (simetría), `mover` (ajuste relativo), `centro`.
- **Avisos que proponen el arreglo**: el resolvedor sugiere qué quitar en un conflicto y corrige erratas
  («¿querías decir…?»); lo medido en Blender se traduce a relaciones («usa ["encima", "Cabeza", "Torso"]»).
- **Dos condiciones**: `una_vez` (todo el JSON en un turno) y `fases` (1 piezas → 2 relaciones → 3 articulaciones →
  4 animación; cada fase se comprueba en Blender con lo que ya se puede medir; hasta 3 intentos por fase).
- La condición `funciones` de la tanda 12 se deja: ganó la relacional.

## Tareas (las dos nuevas viven en `relacional2.py`, no en `tareas.py`)
- T05 (robot, 28 comprobaciones) y T08 (robot que avanza, 35), con el verificador estricto.
- **T13, robot articulado que camina (50)**: el robot de T05 con caderas y hombros; avanza 4 m; piernas ±30° en
  contrafase, brazos ±20° al revés que su pierna, rectas en 1, 24 y 48. Comprueba la postura de reposo, que cada
  extremidad gire desde el centro de su cara de arriba y no se separe del torso, la amplitud y la contrafase.
- **T14, robot detallado (82)**: 14 piezas, con cilindros (brazos, piernas, antena), esferas (ojos, manos, punta) y
  cajas (torso, cabeza, pies); ojos en la cara delantera, pies desplazados hacia delante, jerarquía de varios
  niveles (mano → brazo → torso). El JSON compacto de referencia ocupa unos 610 tokens: con el tope de 800, escrito
  con sangría puede no caber de una vez.

## Comprobado antes (sin cerebro real, Blender real; `comprobar_relacional2.py`, 16/16)
Resolvedor: posiciones de T14, conflicto que propone quitar, erratas en relación y forma, pieza sin colocar, JSON
cortado, orden indiferente y fases por tarea. JSON de referencia: T05 28/28, T08 35/35, T13 50/50, T14 82/82.
Cerebros falsos que fallan adrede (cabeza debajo, centro de más, piernas sin x, brazos sin articulación) y solo se
arreglan si el aviso propone el arreglo: aprueban las 8 combinaciones.

## Reglas de decisión (fijadas antes de ver resultados)
1. **Llega a lo complicado** si cada cerebro aprueba al menos una de las dos tareas nuevas (T13 o T14) en alguna
   condición.
2. **Las fases ayudan** si, sumando las comprobaciones finales de las 8 combinaciones de cada condición, `fases`
   supera a `una_vez`.
3. **Sin retroceso** respecto a la tanda 12: cada cerebro vuelve a aprobar T05 en alguna condición.
4. **Resultado fuerte**: algún cerebro aprueba las cuatro tareas en una condición.
5. Se informa cuántas respuestas se cortan por el tope de tokens y qué avisos llevaron a un arreglo.

## Resultado PARCIAL (2026-11-15; 3 arranques)
Arranque 1 (12:24): qwen25 completo; ministral3 cortado a las 12:39 por actividad en el PC. Se añadió `--permitir_uso`
(el usuario usa el PC: no se mira teclado/ratón; VRAM, GPU y térmica siguen; G2 con 1992 MiB de VRAM ajena). Arranque
3 (14:29) cortado a las 14:36 por la térmica: **freno térmico por software 20 s a ~80 °C** (con Roblox abierto a la vez).
Falta ministral3 · fases · T14.

| | una_vez T05 | T08 | T13 | T14 | fases T05 | T08 | T13 | T14 |
|---|---|---|---|---|---|---|---|---|
| qwen25 | 25/28 | 32/35 | 47/50 | 0/82 | **28/28** | 17/35 | 21/50 | 53/82 |
| ministral3 | 0/28 | 32/35 | 47/50 | 0/82 | **28/28** | **35/35** | 21/50 | (falta) |

**Primer robot animado aprobado con el verificador estricto: ministral3 por fases (T08, 35/35).**

Veredictos (provisionales; falta una combinación):
1. **Llega a lo complicado: NO.** Nadie aprueba T13 ni T14; los dos se atascan en la fase de relaciones.
2. **Las fases ayudan: SÍ** ya con lo medido: qwen25 104 → 119; ministral3 79 → 84 sin contar su T14 (que solo puede sumar).
3. **Sin retroceso: SÍ** (los dos aprueban T05 por fases).
4. **Resultado fuerte: NO.**
5. **8 de 51 respuestas cortadas por el tope de 800 tokens**: T14 de una vez se cortó en los 6 intentos (lo previsto);
   por fases, la fase de piezas de T14 cabe (qwen25 42/42).

Qué falla (ya no es geometría; es la forma de describir):
- **Las piernas sin x** (las dos en x = 0, una dentro de otra): el fallo más repetido; el aviso propone `espejo_x` y fijar
  la x de una, y los cerebros repiten la misma respuesta.
- **Colocar dos veces la misma pieza** (`centro` o `x`/`z` sueltos + una relación): el resolvedor avisa del conflicto y
  dice «quita una de las dos», pero en el reintento cambian el número en vez de quitarlo (qwen25 T14: 3 veces igual).
- Inventan argumentos (`["izquierda", "Brazo_I", "Torso", -0.55]`) y nombran como objeto de la animación algo que no es
  una pieza.

## Para la siguiente tanda (propuestas)
- El aviso de conflicto debe decir EXACTAMENTE qué borrar («borra ["centro", "Pierna_I", -0.5, 0, 0]»), no «una de las dos».
- Detectar ANTES de Blender dos piezas en el mismo sitio y decir qué coordenada falta («Pierna_I y Pierna_D están las dos
  en x = 0: fija la x de Pierna_I y usa espejo_x para Pierna_D»).
- Relaciones con desplazamiento lateral explícito para piezas pareadas (p. ej. `["debajo", A, B, {"x": -0.3}]`).

## Resultado FINAL (2026-11-15, 14:59)
Tras otros dos cortes térmicos con Roblox abierto (14:42 freno por software; 14:50 **freno térmico de hardware a solo
67 °C con la GPU al 99 %**), la última combinación se corrió con Roblox cerrado, con el resolvedor original de esta
tanda (`relacional2_tanda13.py`, copia previa a los cambios de la 13b) y pausas de enfriamiento entre llamadas.

ministral3 · fases · T14: **0/82**. La fase de piezas se cortó por el tope de 800 tokens en los 3 intentos, con la
misma respuesta: el aviso «escribe el JSON más compacto» no le hizo cambiar.

Sumas finales (8 combinaciones por condición): qwen25 una_vez 104 → fases 119; ministral3 una_vez 79 → fases 84.
Veredictos definitivos: 1 **NO** · 2 **SÍ, las fases ayudan** · 3 **SÍ** · 4 **NO**. 8 de 54 respuestas cortadas.

Propuesta añadida: partir la fase de piezas en tandas (p. ej. 7 piezas por llamada) cuando la tarea tenga muchas.

**Nota (revisión posterior):** un intento (qwen25 · fases · T08 · relaciones · 3) fue rechazado por un fallo del
resolvedor (falso conflicto entre una x puesta por defecto y un `espejo_x`); ver PRERREGISTRO_TANDA13B.md. No cambia
los veredictos.
