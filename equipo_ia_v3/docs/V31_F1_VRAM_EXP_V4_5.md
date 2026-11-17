# V3.1 F1-VRAM-EXP-V4.5 — convivencia con un PC compartido

**Estado:** laboratorio experimental, prerregistrado antes de las puertas y de F1.

## 1. Diagnóstico de V4.4 (F1 del 2026-11-12, 14:52–)

Evidencia: `evidencias/v31_f1_vram_exp_v4_4/f1_comparacion1/`, conservada sin cambios.

- **Con su propia carga, el protocolo térmico funcionó:**
  - máxima de 81 °C;
  - 0 frenos térmicos;
  - ventilador ≤ 70 %;
  - enfriamiento a 60 °C antes de cada petición.
- **Tras 44 filas, alguien empezó a jugar a Roblox,** que usa unos 820 MiB de VRAM. F1 detectó la actividad, cortó y
  cerró Qwen, restauró Wallpaper Engine y se quedó esperando.
- **A las 15:15:43, con Qwen cerrado,** `nvidia-smi` marcó un freno térmico de hardware durante 1 s, a 74 °C (código
  `0x48`). Con las reglas de V4.4 eso es crítico, así que esa F1 no puede completarse válidamente.
- **Después, solo con el juego,** la GPU llegó a 85 °C con el ventilador al 88 %.
- **Conclusión:** no todo el calor viene de Equipo IA. V4.4 no distinguía el origen de un evento térmico y su espera
  máxima de 1 h no cubría una sesión de juego.

## 2. Cambios de V4.5 (solo en el laboratorio)

V4.5 son dos archivos nuevos:
- `eq3/evaluar_f1_vram_exp_v4_5.py`, copia de V4.4;
- `eq3/termica_v4_5.py`, copia de `termica_v4_4.py`.

V4.4 y todo lo anterior siguen sin cambios.

### 2.1 Origen de los eventos térmicos (cambio 2)

`propio_activo()` devuelve:
- **True** si Equipo IA tiene una tarea en curso (contador `_EN_TAREA`) o si hay **cualquier** proceso llama vivo. Uno
  ajeno no se puede distinguir, así que no se atribuye a terceros;
- **False** solo si se listaron los procesos y no hay ninguno;
- **None** si no se puede saber.

| Origen | Freno de hardware, ≥ 88 °C o freno de software ≥ 20 s | Fallo de supervisión |
|---|---|---|
| **Propio** | Crítico, como en V4.4 | Crítico |
| **Incierto** | **Crítico** (`…_origen_incierto`) | Crítico |
| **Externo verificado** | Se anota como **interferencia externa**: no es crítico y la evaluación espera **5 min sin eventos externos** antes de seguir. **Salvo ≥ 92 °C** (máximo de operación), que se trata como inseguro y aborta | Crítico |

Las interferencias quedan en `termica.interferencias_externas`, con hora, motivo y temperatura.

### 2.2 Esperas largas (cambio 3)

`esperar_v45` es la espera de V4.4 (persona, VRAM ajena, GPU y fondo animado) con estos cambios:
- **Espera máxima de 4 h**, frente a 1 h en V4.4. Durante la espera:
  - Qwen está cerrado; los recursos de Equipo IA se liberan al cortar la tarea, y entre tareas no hay servidor;
  - no se genera nada;
  - Wallpaper Engine se devuelve a la persona.
- **Persona:** las mismas señales de V4.4, que no se fían solo del teclado y el ratón (sesiones, pantalla completa,
  ventana en primer plano). A eso se suma la carga ajena de GPU y VRAM: un juego, con la GPU por encima del 40 %, no
  deja reanudar.
- **Reanudar** solo si todo está en verde y no ha habido interferencia térmica externa en los últimos 5 min.
- **Térmica crítica o STOP:** la espera vuelve **en el acto** y la evaluación se aborta.
- **Registro:** cada pausa se anota en `comparacion.json → pausas` con inicio, duración, motivos y resultado.

### 2.3 STOP global

Crear el archivo `SALIDA/STOP` detiene la evaluación de forma ordenada:
- **durante una generación**, el vigía la corta, igual que la VRAM o la térmica;
- **durante una espera**, la espera vuelve en el acto.

En los dos casos la evaluación se aborta, se anota, Wallpaper Engine se restaura y no queda ningún llama.

### 2.4 Tiempos por separado

Cada fila guarda `termica`, con:
- `generacion_s` (inferencia);
- `enfriamiento_s`;
- **`espera_humana_s`** (la espera antes de la tarea);
- `trabajo_s` (total − enfriamiento) y `total_s`;
- `pico_C`;
- **`intentos_interrumpidos`**.

### 2.5 Wallpaper Engine en pausa (decisión del usuario)

V4.5 **pausa** Wallpaper Engine (`-control pause`) en vez de detenerlo, como hacía V4.4:
- el fondo queda visible como imagen fija;
- según la medida de V4, la GPU baja del 31 % al 6 %;
- no libera VRAM, pero sus ≈ 158 MiB caben de sobra: VRAM ajena ≈ 1019 MiB con el fondo activo, frente a un
  presupuesto de 1992.

La restauración (`-control play`), el guardián independiente y la devolución del fondo a la persona no cambian.

### 2.6 Sin cambios

- límites térmicos y enfriamiento a 60 °C antes de cada petición (los 55 °C **no** se implementan);
- E2 y límites de VRAM y RAM;
- STOP de V2-F.1, propiedad de procesos y Wallpaper Engine;
- tareas, oráculos, prompts, semillas, orden y regla de decisión;
- repetición de una tarea cortada por terceros (máximo 2, desde cero).

## 3. Integridad metodológica (pruebas reproducibles)

| Requisito | Cómo se comprueba |
|---|---|
| Las pausas no alteran prompts, semillas, parámetros ni oráculos | Misma tarea en S1, S1×3 y E3 con 0 s y con 120 s de enfriamiento por petición: SHA-256 de cada prompt, temperatura, semilla, `max_tokens`, evaluación y prompt del primer paso **idénticos** |
| No se pierden, duplican ni omiten tareas | Bucle real (`ejecutar_bucle`) con pausas por persona y una interrupción por terceros: **90 filas**, en el orden prerregistrado y sin duplicados |
| Las respuestas interrumpidas se identifican | La tarea cortada se repite desde cero; el intento cortado queda en `intentos_interrumpidos` y no se puntúa |
| No se mezclan ejecuciones | Un laboratorio nuevo por tarea y por intento (`r{rep}/{C}/{T}/intento{n}`); `comparar` exige una carpeta nueva |
| Trazabilidad | `fila.json` por tarea con el SHA-256 de cada petición; prerregistro con el SHA-256 de todo el código y de las evidencias previas |
| Sin ventaja para ningún método | La misma espera, el mismo enfriamiento y el mismo vigía para los tres (G10 y las pruebas de integración) |
| Tiempos por separado | Inferencia, enfriamiento, espera humana y total (`tiempos_termicos`) |
| Ejecución parcial | **Política prerregistrada:** una F1 abortada (STOP, crítico, o más de 4 h de espera) **no es válida**, se conserva como evidencia y **no se reinicia sola** |

## 4. Puertas de V4.5

G1–G12, como en V4.4, más:
- **G13: interferencia externa con Equipo IA en reposo real,** comprobado: no hay ningún llama.
  - un freno simulado sobre una lectura real se atribuye a terceros y obliga a esperar;
  - 93 °C se trata como inseguro;
  - un origen incierto es crítico.
- **G14: STOP global real.**
  - a mitad de una generación larga de Qwen, corta en ≤ 3 s, cierra limpio y libera la VRAM;
  - durante una espera, vuelve en menos de 2 s.

G5 añade F25: las 59 mutaciones de V4.4, reaplicadas a V4.5, y 20 nuevas.

## 5. Riesgos residuales

- **La atribución externa es conservadora.** Cualquier llama vivo cuenta como propio; uno ajeno, por ejemplo de los
  hermanos, haría crítico cualquier evento. Esto evita culpar a terceros por error, pero puede abortar de más.
- **Interferencias muy frecuentes** podrían alargar F1 hasta el límite de 4 h y abortarla.
- **El freno de hardware a 74 °C con Roblox sigue sin explicación.** V4.5 lo trata como interferencia, pero conviene
  revisar la tarjeta, la ventilación y el polvo.
- **El límite de 45 min por tarea de E3** incluye el enfriamiento, pero no la espera humana, que ocurre entre tareas.
