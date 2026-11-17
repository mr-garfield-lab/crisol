# V3.1 F1-VRAM-EXP — Puertas de seguridad de V4.3 (2026-11-12, 12:24–12:52)

**Resultado: G1–G10 de V4.3 PASAN** (`evidencias/v31_f1_vram_exp_v4_3/puertas1/puertas.json`).
- Las puertas valen para el código y el prerregistro actuales (`huella_codigo` coincide).
- La evaluación F1 completa **no** se ha ejecutado.
- El diseño de la corrección está en `docs/V31_F1_VRAM_EXP_V4_3.md`.

| Puerta | Resultado |
|---|---|
| G1: integridad | **OK**. Cadena V1 → V4.3 por SHA-256 sin diferencias (incluye V4.2 conservada y las evidencias de la F1 abortada). Enunciados sin fugas. Compatibilidad con V2-F.1: 14 OK |
| G2: VRAM ajena | **OK**. 854 ≤ 1992 MiB con el fondo detenido; externos verificados |
| G3: STOP real con E2 | **OK**. Corte en 0,11 s, cierre limpio en 0,94 s, VRAM liberada en 1,59 s (de vuelta a 854 MiB) |
| G4: límite de RAM | **OK**. Corte en 5,75 s, cierre en 0,92 s, VRAM en 1,58 s |
| G5: mutaciones | **OK**. F15 16/16, F16 9/9, F17 8/8, F18 18/18, F19 10/10, F20 17/17, F21 22/22, F22 6/6 y **F23 36/36**: 142/142 |
| G6: persona y recursos | **OK**. Nadie, VRAM ajena constante en 854 MiB y GPU ≤ 8 % |
| G7: Wallpaper Engine | **OK**. Detenido y restaurado (12:51:59), mismo proceso (PID 22112), 158 MiB después, marca retirada |
| G8: tope de VRAM real | **OK**. Corte en 0,59 s, cierre en 0,92 s, VRAM en 1,05 s |
| G9: fallo de arranque | **OK**. `servidor_muerto` al cargar, puerto libre y ningún llama vivo |
| G10: equivalencia | **OK**. Lo estático, como en V4.2. Pruebas de la estable con el servidor falso: 11 OK. **Nuevo:** `test_eq3_procedencia_v4_3`, 23 OK (las mismas garantías de fuga en S1, S1×3 y E3) |
| — procesos liberados | **OK**. Ningún llama ni ningún guardián al terminar |

En G3, G4 y G8, llama.cpp cargó 29/29 capas en GPU, con n_ubatch 128, flash_attn activo y sin ajustes de `--fit`.

## Otras comprobaciones

| Comprobación | Resultado |
|---|---|
| Pruebas de V4.3 (las 17 heredadas de V4.2 y 23 nuevas) | 40 OK |
| Regresión de V4.2 | 17 OK |
| Regresión de la estable F1 | `test_eq3_evaluar_f1` 11 OK, `test_eq3_evaluacion_f1` 16 OK |
| Regresión de V3 | 19 OK |
| Regresión del control de Wallpaper Engine | 6 OK |
| V4.2 intacta | `comprobar_v4` de V4.2: 0 diferencias |
| Repetición sin modelo de los 45 prompts reales de E3 | Mismos resultados con la estable y con V4.3 |
| T10 con la salida real de A1 | La estable aborta tras 1 prompt; V4.3 envía 3 y acaba en CORRECTO, con el relevo ligado al SHA-256 de A1 (`209f07e7…`) |

## Defectos encontrados durante la preparación

- **F23, primera ronda: 34/36 detectadas.**
  - **P13** era una mutación equivalente: una respuesta vacía inventada no puede verificar nada. La sustituí por
    «contar el propio prompt como procedencia», que sí se detecta.
  - **P14** (G10 sin las pruebas de procedencia) sobrevivía porque faltaba una prueba. Añadí
    `test_g10_exige_las_pruebas_de_procedencia`.
- **Segunda ronda: 36/36 detectadas.** Se repitió dentro de G5.

## F1 completa con V4.3 (2026-11-12, 13:00–13:11): DETENIDA por temperatura, no válida

- **Lanzamiento:** con el supervisor `lab_vram/f1_v4_3_supervisado.py`. Las comprobaciones previas pasaron:
  - prerregistros intactos y puertas del mismo código;
  - 16,5 GB de RAM libres;
  - nadie usando el PC;
  - GPU a 41 °C.
- **Avance:** 31 de 90 filas (S1 r1, S1×3 r1 y E3 r1 T01).
- **Por qué se detuvo:** al empezar E3, la GPU estuvo al 96–97 % de forma continua y pasó de 59 °C a 84 °C en 26 s.
  `nvidia-smi` marcó un freno térmico y el supervisor detuvo la evaluación de forma ordenada.
  - El objetivo de la GPU es 83 °C y su máximo de operación, 92 °C.
  - El criterio del supervisor (cualquier freno térmico cuenta como anomalía) es más estricto a propósito. No se
    relajó ni se relanzó.
- **Estado al detenerse:** ningún llama vivo; Wallpaper Engine restaurado (mismo PID, 158 MiB); marca retirada.
- **Evidencia:** en `evidencias/v31_f1_vram_exp_v4_3/`:
  - `f1_comparacion1_aborto.json` y `f1_comparacion1_supervision.json`;
  - `f1_comparacion1_termica.jsonl`;
  - `f1_comparacion1/comparacion.json`.

## Riesgos residuales

- La exención nueva es estrecha: solo E3, solo bloques de relevo, contexto copiado literalmente y sin exposición
  previa. Cualquier caso dudoso sigue abortando (fallo cerrado).
- La F1 completa sigue sin probarse de principio a fin con Qwen real: es la propia evaluación, no autorizada.
- Siguen los riesgos de V4.2: la VRAM ajena de día puede superar el presupuesto, la evaluación dura varias horas con
  la GPU cargada, y el guardián no cubre un corte de luz o un reinicio.
