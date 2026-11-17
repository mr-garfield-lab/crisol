# F1-VRAM-EXP-V4.5.1 — informe de las 14 puertas

**Resultado: 14 de 14 puertas en verde** (`evidencias/v31_f1_vram_exp_v4_5_1/puertas1/puertas.json`, 2026-11-13 06:01–07:07,
PC libre: 10 168 s sin teclado ni ratón en G6). Los procesos del laboratorio quedaron liberados (`llama_al_final = []`), y
Wallpaper Engine se pausó a las 07:04:49 y se restauró a las 07:07:02. F1 empezó sola a las 07:07, según lo autorizado.

| Puerta | Qué comprueba | Resultado | Dato clave |
|---|---|---|---|
| G1 | integridad de V1–V4.5.1 y de la estable | **OK** | 0 diferencias; compatibilidad con V2-F.1: 14 pruebas OK |
| G2 | externos y VRAM de otras aplicaciones | **OK** | 1056 MiB (tope 1992); `externos_ok`: archivos externos verificados |
| G3 | STOP durante una generación con Qwen real | **OK** | corte en 0,06 s; VRAM liberada en 1,73 s |
| G4 | límite de memoria con Qwen real | **OK** | corte en 5,64 s por presión de memoria; VRAM liberada en 1,72 s |
| G5 | baterías de mutaciones F15–F26 y V-SRV | **OK** | F21 22/22, F22 6/6, F23 36/36, F24 59/59, F25 80/80, **F26 86/86** |
| G6 | persona y recursos | **OK** | sin persona, VRAM ajena 1056 MiB, GPU 1–7 % |
| G7 | Wallpaper Engine: pausa y restauración | **OK** | pausa 07:04:49, restauración 07:07:02; mismos procesos |
| G8 | tope de VRAM total con Qwen real | **OK** | corte en 0,09 s al superar el tope; VRAM liberada en 1,17 s |
| G9 | fallo de arranque del servidor | **OK** | aborto durante la carga, sin llama ni puerto ocupado |
| G10 | equivalencia S1 / S1×3 / E3 | **OK** | estable 11, procedencia 23, térmica 23, compartido 19 y **atribución de G12: 16 pruebas OK** |
| G11 | sensores térmicos reales | **OK** | todos los campos presentes salvo `potencia_W` (no disponible en esta tarjeta) |
| G12 | corte térmico real con Qwen | **OK** | freno simulado a mitad de una generación; corte en **0,56 s**, motivo exacto `freno_termico_hardware`, VRAM 1056 → 1056 MiB |
| G13 | interferencia externa en reposo real | **OK** | origen «externo» con Equipo IA en reposo; ≥ 92 °C → inseguro; **origen incierto se conserva** |
| G14 | STOP global real | **OK** | corte en 0,09 s; VRAM liberada en 1,16 s |

**Lo que corrige V4.5.1:** G12 de V4.5 dio «origen incierto» porque su sensor no sabía de quién era el servidor (ver
`V31_F1_VRAM_EXP_V4_5_1.md` y `verificacion_causa_g12.json`). No cambió la lógica de protección.

**Nota:** G12 guarda además `origen_atribuido`, que se lee tras cerrar el servidor y por eso pone «externo»; no interviene en el criterio de G12.
Las lecturas con el servidor vivo (`G12/termica.jsonl`) están anotadas como «propio».
