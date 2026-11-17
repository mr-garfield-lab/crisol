# Preregistro: banco de Blender, tanda 13c (calculadora con posiciones)

Escrito ANTES de preguntar a ningún cerebro. Fecha: 2026-11-15.

## Pregunta
En la 13b ministral3 usó la calculadora en todas sus respuestas, pero mal: calculaba distancias («alto(Torso)/2 +
mitad(Cabeza)») y las ponía como posiciones absolutas en un `centro`, a la vez que una relación colocaba la misma pieza
(7 conflictos), y perdió T05 y T08. ¿Se arregla si la calculadora también da posiciones y el sistema dice cuándo usarla?

## Cambios respecto a la 13b (solo `relacional2.py`; la 13b queda congelada en `relacional2_tanda13b.py`)
1. **Funciones de posición** de una pieza ya colocada: x(P), y(P), z(P), arriba(P), abajo(P), borde_izq(P),
   borde_der(P), borde_delante(P), borde_detras(P). Una fórmula que usa la posición de una pieza aún sin colocar
   espera a que se coloque; si nunca se coloca (o es circular), se avisa.
2. **El sistema** dice: la calculadora solo para una coordenada que ninguna relación fija; las medidas son
   distancias, no posiciones; ejemplo con `borde_izq`.
3. **Aviso de conflicto** con una fórmula: añade que alto(), mitad()… son distancias y cuáles dan posiciones.
Todo lo demás igual que la 13b: T05, T08, T13, T14, condición `fases`, qwen25 y ministral3, 800 tokens, 3 intentos
por fase, verificador estricto, `--permitir_uso`.

## Comprobado antes (sin cerebro real)
`comprobar_relacional2.py` 18/18 (2 pruebas nuevas: fórmula con posición diferida, aviso de distancias) y
`comprobar_componentes.py` 6/6; aparte: dependencia circular avisada y `__import__` rechazado.

## Reglas de decisión (fijadas antes de ver resultados)
1. **Sin retroceso**: los dos cerebros aprueban T05 (como en la tanda 13).
2. **Los cambios ayudan** si los conflictos provocados por fórmulas bajan de 7 (13b) y la suma de comprobaciones
   finales de T05 + T08 + T13 de ministral3 sube respecto a la 13b (17 + 17 + 21 = 55). Se compara sin T14 porque en la
   13b su cifra dependió de si la fase de piezas se cortaba, no de la calculadora.
3. Se informa: suma total frente a 238 (13b), respuestas con fórmulas, cuántas usan funciones de posición,
   conflictos y cuántas parejas en el mismo sitio se detectan y arreglan.

## Resultados (`tanda13c`, 2026-11-15, 18:35–18:44, sin cortes)

| | T05 | T08 | T13 | T14 | suma |
|---|---|---|---|---|---|
| qwen25 (13b → 13c) | 28 ✓ → 28 ✓ | 28 → 35 ✓ | 21 → 21 | 53 → 53 | 130 → 137 |
| ministral3 (13b → 13c) | 17 → 28 ✓ | 17 → 35 ✓ | 21 → **50 ✓** | 53 → 0 | 108 → 113 |

1. **Sin retroceso: sí.** Los dos aprueban T05 (y T08).
2. **Los cambios ayudan: sí.** Conflictos por fórmulas: 1 (antes 7). ministral3 en T05 + T08 + T13: 113 (antes 55).
3. Recuentos: total 250 (13b: 238). Fórmulas: ministral3 en 7 respuestas, 6 con funciones de posición; qwen25 en 1.
   Pareja en el mismo sitio: 2 detecciones (ministral3 T05, arreglada al intento siguiente; qwen25 T14 con los ojos).
   Usos inválidos nuevos, avisados y corregidos: una posición dentro de `mover` y una fórmula en `desplazamiento`.
**Hito:** ministral3 aprueba T13 (andador articulado, 50/50): es la primera vez que un cerebro aprueba T13.
**Lo que queda:** T14 se pierde por el límite de 800 tokens: ministral3 corta la fase de piezas 3 veces y qwen25 corta
relaciones 2 veces (su primer intento llegó a 65/82, su mejor marca). Siguiente: trocear las fases largas.
