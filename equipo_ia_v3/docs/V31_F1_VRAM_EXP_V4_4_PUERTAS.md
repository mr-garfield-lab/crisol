# V3.1 F1-VRAM-EXP — Puertas de seguridad de V4.4 (2026-11-12, 14:15–14:50)

**Resultado: G1–G12 de V4.4 PASAN** (`evidencias/v31_f1_vram_exp_v4_4/puertas1/puertas.json`).
- Las puertas valen para el código y el prerregistro actuales (`huella_codigo` coincide).
- El diseño está en `docs/V31_F1_VRAM_EXP_V4_4.md`.

| Puerta | Resultado |
|---|---|
| G1: integridad | **OK**. Cadena V1 → V4.4 por SHA-256 sin diferencias: incluye V4.2 y V4.3 conservadas, y las evidencias de las F1 detenidas (39 y 31 filas). Compatibilidad con V2-F.1: 14 OK |
| G2: VRAM ajena | **OK**. 861 ≤ 1992 MiB; externos verificados |
| G3: STOP | **OK**. Corte en 0,12 s; VRAM liberada en 1,61 s; cierre limpio |
| G4: RAM | **OK**. Corte en 5,74 s; VRAM en 1,62 s |
| G5: mutaciones | **OK**. F15 16/16, F16 9/9, F17 8/8, F18 18/18, F19 10/10, F20 17/17, F21 22/22, F22 6/6, F23 36/36 y **F24 59/59**: 201/201 |
| G6: persona y recursos | **OK**. Nadie, 861 MiB de VRAM ajena estables y GPU ≤ 8 % |
| G7: Wallpaper Engine | **OK**. Detenido y restaurado (14:49:46): mismo PID 22112, 158 MiB y marca retirada |
| G8: tope de VRAM | **OK**. Corte en 0,64 s; VRAM en 1,08 s |
| G9: fallo de arranque | **OK**. `servidor_muerto`; puerto libre |
| G10: equivalencia | **OK**. Estable con el servidor falso: 11 OK. Procedencia: 23 OK. **Térmica: 23 OK** (mismo protocolo en S1, S1×3 y E3) |
| **G11: sensores reales** | **OK**. Temperatura y los cuatro frenos, leídos en todas las lecturas. Además: ventilador (37 %), relojes y pstate. **Sin potencia**: `power.draw` = [N/A], que queda como `null` |
| **G12: corte térmico real** | **OK**. Enfrió antes de la petición (54 °C, 0,08 s). Con la señal de freno térmico de hardware simulada a mitad de una generación larga, la cortó en **0,59 s**, cerró limpio y liberó la VRAM en 1,11 s. Pico de 71 °C |
| — procesos liberados | **OK**. Ningún llama ni ningún guardián |

En G3, G4, G8 y G12, llama.cpp cargó 29/29 capas en GPU, con n_ubatch 128, flash_attn activo y sin ajustes de `--fit`.

**Regresiones sin GPU, todas OK:**
- V4.4: 63 pruebas.
- V4.3: 40.
- V4.2: 17.
- La estable F1: 11 y 16.
- V3: 19.
- Wallpaper Engine: 6.
- Supervisor de V4.3: 4.
- `servidor_pc`: 14.
- V4.2 y V4.3 siguen sin diferencias.
