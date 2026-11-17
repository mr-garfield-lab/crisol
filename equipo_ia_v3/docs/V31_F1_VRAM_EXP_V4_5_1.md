# F1-VRAM-EXP-V4.5.1 — corrección de la puerta G12

**Estado:** preregistrada antes de las puertas. Autorización del usuario (2026-11-13): crear V4.5.1 y, **solo si las 14
puertas pasan**, iniciar automáticamente las 90 ejecuciones de F1. Ante un fallo crítico o pérdida de integridad, la
evaluación se detiene y se conserva la evidencia. No se instala software ni se usan APIs de pago.

## Por qué existe

Las puertas de V4.5 (2026-11-13, `evidencias/v31_f1_vram_exp_v4_5/puertas2/`) dieron **13 de 14**. Falló **G12**
(corte térmico real). F1 no se lanzó, porque el orquestador no lanza F1 ante un fallo que no sea por una persona.

| Dato de G12 en V4.5 | Valor |
|---|---|
| Interrupción de la petición | 0,56 s (límite 3 s) |
| Cierre del servidor | limpio, 1,0 s |
| VRAM tras el corte | 1057 MiB = la de antes (liberada) |
| Temperatura máxima real | 66 °C; ningún freno real antes de la simulación |
| Motivo registrado | `freno_termico_hardware_origen_incierto` |
| Motivo esperado por la puerta | `freno_termico_hardware` |

**Causa (verificada, no supuesta):** `evidencias/v31_f1_vram_exp_v4_5_1/verificacion_causa_g12.json`.
- En la evidencia real, las tres lecturas con el freno simulado quedaron anotadas con origen `incierto`.
- G12 de V4.5 creaba su `Termica` **sin `propio_activo`**, y el valor por defecto es «no se puede saber».
- Reproduciendo la MISMA lectura, solo cambia quién conoce la propiedad del servidor:

| `propio_activo` | Origen | Resultado |
|---|---|---|
| ninguno (como G12 de V4.5) | incierto | crítico `…_origen_incierto` |
| función real, servidor llama vivo (lo que hay en G12) | propio | crítico `freno_termico_hardware` |
| función real, ningún llama | externo | no crítico, interferencia anotada |
| función real, lista de procesos ilegible | incierto | crítico `…_origen_incierto` |

**Conclusión:** la lógica de atribución de V4.5 funciona como se diseñó. El defecto estaba en el escenario simulado de G12:
no le decía a la térmica que el servidor llama era de Equipo IA. En una tarea real de F1 sí lo sabe (`nueva_termica` pasa
`propio_activo`, y G13 lo comprobó).

## Qué cambia

1. **`termica_g12`** (nueva): crea la `Termica` de G12 con la función real `propio_activo`. G12 la usa.
   No se fuerza «propio»: si el servidor no estuviera vivo, saldría externo o incierto, como en F1.
2. **Criterio de G12 sin relajar:** crítico exactamente `freno_termico_hardware`, corte ≤ 3 s, cierre limpio, VRAM liberada,
   configuración efectiva de llama y enfriamiento real previo. Se anota además `origen_atribuido`.
3. **G10** añade `test_eq3_g12_v4_5_1.py` (16 pruebas): propio, externo, **origen realmente incierto (se conserva
   `_origen_incierto`)**, error al consultar procesos, externo ≥ 92 °C sigue siendo inseguro, causa de V4.5 reproducida, y
   que todo el código de V4.5.1 es idéntico al de V4.5 salvo `corte_termico_real`, `g10_equivalencia` y `g5`.
4. **G5** añade la batería **F26** (86 mutaciones: las 80 de V4.5 retargeteadas + 6 de G12) y repite F15–F25.
5. Nombres de versión y archivos protegidos (V4.5, su prerregistro y la evidencia de sus puertas quedan fijados por SHA-256).

## Qué NO cambia (comprobado por pruebas y por diff)

- `eq3/termica_v4_5.py`, **el mismo archivo**: lógica de atribución, límites térmicos (enfriar a 60 °C, máx. 180 s,
  crítico ≥ 88 °C, freno de software ≥ 20 s, 3 lecturas fallidas, externo ≥ 92 °C, reposo externo 300 s).
- STOP global, pausas de hasta 4 h, Wallpaper Engine en pausa, aislamiento y propiedad de procesos, persona, VRAM
  (6912 / 1992 MiB), E2, RAM.
- Tareas, oráculos, prompts, semillas, temperaturas, orden y regla de decisión de F1; control de fugas con procedencia.
- Cada función y clase de V4.5.1 es textualmente idéntica a la de V4.5 (tras normalizar el nombre de versión), salvo las
  tres permitidas y la nueva `termica_g12`.

## Cómo se ejecuta

Orquestador (espera a que el PC esté libre; pasa las 14 puertas; si todas pasan, lanza las 90 ejecuciones; no reintenta
una F1 abortada):

    py -B -X utf8 lab_vram\orquestar_f1_v4_5_1.py EXTERNOS evidencias\v31_f1_vram_exp_v4_5_1

Parada ordenada: crear `evidencias\v31_f1_vram_exp_v4_5_1\STOP_ORQUESTADOR` (y, durante F1, el archivo `STOP` de la carpeta
de F1). El orquestador no forma parte del método y no está en la lista de archivos protegidos.
