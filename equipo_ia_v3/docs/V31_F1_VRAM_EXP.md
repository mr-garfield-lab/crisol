# V3.1 F1 — Variante experimental F1-VRAM-EXP (tope de VRAM 6912 MiB)

Autorizada por el usuario el 2026-11-11 tras el intento 1 de la comparación estable, que se abortó con fallo cerrado
(S1/T10 llegó a 6231 MiB con el tope de 6144; las demás aplicaciones del PC usaban entre 1449 y 1625 MiB).

## Qué es y qué no es

- **Separada y reversible.** Vive en `eq3/evaluar_f1_vram_exp.py`. La configuración **estable** (`eq3/evaluar_f1.py`,
  tope 6144 MiB, VRAM ajena ≤ 1500 MiB, prerregistro V2) **no se ha modificado**: sus SHA-256 siguen siendo los del V2.
  Para volver a la estable basta con no usar este módulo.
- **Mismo método.** Reutiliza de la estable las tareas, los oráculos, los prompts, `ejecutar_tarea`, las tres
  configuraciones, el orden contrabalanceado, las temperaturas, las semillas, el análisis y la regla de decisión.
- **Resultados aparte.** `puertas` y `comparar` solo escriben en carpetas con «vram_exp» en el nombre (evidencias en
  `evidencias/v31_f1_vram_exp/`). Sus resultados no se mezclan ni se comparan como si fueran de la estable.

## Cambios respecto de la estable (prerregistro V3)

| Elemento | Estable (V2) | F1-VRAM-EXP (V3) |
|---|---|---|
| Tope de VRAM total | 6144 MiB | **6912 MiB** (de 8192) |
| Al superar el tope | se corta la tarea y el resto del bloque | se corta la tarea y se **aborta toda la evaluación** |
| VRAM de otras aplicaciones antes de empezar | ≤ 1500 MiB | ≤ **1832 MiB** = 6912 − 4780 (pico medido de Qwen) − 300 de margen |
| Estabilidad de la GPU ajena | — | variación ≤ 200 MiB y uso ≤ 40 % en la ventana (60 s al inicio, 10 s antes de cada tarea) |
| Uso del PC por terceros | — | no se lanza Qwen si hay otra sesión de Windows activa, la consola está en otra sesión, una aplicación a pantalla completa, en presentación u «ocupada», o entrada de teclado/ratón en los últimos 10 min |
| Terceros a mitad de tarea | — | se detiene la tarea (STOP / corte de la petición), se cierra **solo** el servidor de Equipo IA, se espera a que el PC quede libre y se repite la tarea desde cero; máximo 2 interrupciones por tarea; los intentos interrumpidos se guardan y no se puntúan |
| PC ocupado más de 1 h | — | se aborta la evaluación (no válida, se conserva como evidencia) |
| Puertas | G1–G5 | G1 (V2 **y** V3 intactos), G2 (≤ 1832), **G6** (PC libre), G3/G4 solo si G1, G2 y G6 pasan, G5 (F15–F20 + V-SRV) |

Todo lo que no se puede medir (sesiones, estado de pantalla completa, inactividad, VRAM, uso de la GPU) cuenta como
**ocupado** (fallo cerrado).

## Qué se mantiene

STOP de V2-F.1, monitor de memoria (MemAvailable), propiedad del proceso (el servidor es hijo del ejecutor), detector
de procesos llama con fallo cerrado, externos verificados por SHA-256, control de fugas del oráculo en cada petición,
majflt de Windows con sonda, y la regla «no se ejecuta código generado». El módulo no contiene ninguna orden para cerrar
procesos ajenos (lo comprueba `test_no_cierra_procesos_ajenos`): la detección de terceros **solo mira**; nunca cierra,
minimiza ni interfiere con otras aplicaciones.

## Cómo se ha validado (sin Qwen real)

- `pruebas/test_eq3_evaluar_f1_vram_exp.py`, con 19 pruebas:
  - unitarias, con VRAM, uso de la GPU y actividad simulados;
  - un bucle completo con un ejecutor falso: orden, reintento, aborto total y PC ocupado;
  - integración con el ciclo de vida REAL de V2-F.1 y su servidor falso: 6900 MiB no corta; 6913 MiB corta S1 y E3 y
    cierra el servidor; la entrada de un tercero corta S1 y E3 y cierra el servidor.
- `v3/mutaciones/v31_f1_vram_exp.json` (fase F20 de `verificar_v3.py`): 17 mutaciones de las protecciones nuevas.

## Antes de una evaluación larga con Qwen real

`python -B -X utf8 eq3/evaluar_f1_vram_exp.py sondear 60` solo consulta el estado del PC. Las puertas y la comparación
lo repiten por su cuenta y no empiezan si el PC está en uso. Primer sondeo (2026-11-11 19:07):
- PC **en uso**: entrada de teclado o ratón hace 0 s y una aplicación «ocupada» (pantalla completa);
- 2290 MiB de VRAM ajena y la GPU al 45 %.

Por tanto, **no** se lanzó Qwen.

## Riesgos

- 6912 MiB deja unos 1280 MiB libres en la tarjeta de 8192. Una aplicación ajena que reserve VRAM de golpe podría
  degradarse antes de que el vigía (cada 2 s) corte la tarea. El margen de 300 MiB y la exigencia de estabilidad lo
  reducen, pero no lo eliminan.
- La detección de terceros solo ve la sesión propia (inactividad) y el estado de las demás sesiones. Un uso remoto
  ajeno (escritorio remoto en otra sesión) cuenta como «otra sesión activa».
- Reintentar las tareas cortadas por terceros es un cambio de protocolo respecto de la estable. Cada intento usa un
  servidor y un laboratorio nuevos, y el intento interrumpido no se puntúa.
