# V3.1 F1-VRAM-EXP — Puertas de seguridad de V4 (noche del 2026-11-12)

**Resultado: las puertas G1–G10 de la variante V4.2 PASAN** (`evidencias/v31_f1_vram_exp_v4/puertas2_v4_2/puertas.json`,
05:29–05:53).
- **Sin cambios:**
  - V2-F.1, la configuración estable, F1-VRAM-EXP (V3) y los prerregistros V1, V2, V3, V4 y V4.1 no se modificaron;
  - la cadena de hashes se comprueba entera: 0 diferencias.
- **No ejecutada:** la evaluación F1 completa.

## Defectos encontrados y corregidos (solo en el laboratorio V4)

| # | Defecto | Dónde apareció | Corrección | Versión |
|---|---|---|---|---|
| A | `comparar` aceptaba cualquier `puertas.json` de V4, sin comprobar el código ni el prerregistro | revisión antes de las puertas | `puertas.json` guarda `huella_codigo()` y `comparar` exige que coincida | V4.1 |
| B | si Equipo IA moría de golpe, Wallpaper Engine quedaba detenido | revisión (riesgo ya documentado en V4) | guardián independiente (`lab_vram/guardian_fondo.py`); sin guardián no se detiene el fondo | V4.1 |
| C | una tarea que no corría con E2 solo se marcaba y la evaluación seguía | revisión | aborta TODA la evaluación y guarda `fila_no_e2.json` | V4.1 |
| D | el guardián no actuaba: la marca tenía una ruta relativa y él arranca en otra carpeta | 1.ª prueba real del guardián | ruta absoluta; el guardián rechaza las rutas relativas; registro tolerante a fallos | V4.1 |
| E | 2 mutaciones sobrevivían (F1V4_11, F1V4_22) | verificación previa de F21 | dos comprobaciones nuevas en las pruebas | V4.1 |
| F | **una prueba mutada de F21 llegaba a usar el Wallpaper Engine REAL**: sin la comprobación de las puertas, `comparar` seguía adelante | 1.as puertas (V4.1), `pythonw` inesperado a las 05:22 | la prueba sustituye `FondoAnimado` por uno que falla: ninguna prueba toca la aplicación real | V4.2 |

- **Efecto de F:** el fondo se detuvo y se restauró solo (lo comprobé: 158 MiB y 29 % de GPU después). No se lanzó
  Qwen, porque los externos falsos del test no pasan la verificación.
- **Primeras puertas (V4.1):** en `puertas1/` también pasaron todas, pero se conservan **solo como evidencia**. Se
  ejecutaron con la prueba defectuosa y no sirven para `comparar`, porque el código cambió.

## Resultado de cada puerta (V4.2)

| Puerta | Qué comprueba | Resultado |
|---|---|---|
| G1 | prerregistros V1→V4.2 por SHA-256 (0 diferencias), enunciados sin fugas, compatibilidad con V2-F.1 (`test_eq3_servidor_pc`, 14 OK) | **OK** |
| G2 | externos verificados; VRAM ajena 847 ≤ 1992 MiB (con el fondo detenido) | **OK** |
| G3 | STOP real con E2 | **OK**: corte en 0,09 s, cierre limpio en 0,94 s, VRAM liberada en 1,58 s (847 → 5257 → 847); servidor hijo del ejecutor |
| G4 | límite de RAM real (monitor de V2-F.1 más estricto) | **OK**: corte en 5,72 s, cierre en 0,92 s, VRAM en 1,56 s |
| G5 | mutaciones completas | **OK**: F15 16/16, F16 9/9, F17 8/8, F18 18/18, F19 10/10, F20 17/17, F21 22/22, F22 6/6 (106/106); V-SRV con las mismas firmas |
| G6 | sin persona (el escritorio «ocupado» no cuenta) y recursos estables 60 s | **OK**: 847 MiB constantes, GPU ≤ 8 % |
| G7 | Wallpaper Engine: guardián → stop → restauración | **OK**: guardián a las 05:51:28, stop a las 05:51:30, play a las 05:53:22 (~2 min detenido); mismo proceso, 158 MiB al final, marca retirada |
| G8 | tope de VRAM real: a mitad de la generación el tope del vigía pasa a 5057 (más estricto que los 5257 en uso) | **OK**: corte en 0,62 s, cierre en 0,94 s, VRAM en 1,06 s |
| G9 | fallo de arranque real (opción inexistente) | **OK**: `servidor_muerto` al cargar, puerto libre, ningún llama vivo, VRAM igual |
| G10 | S1, S1×3 y E3 equivalentes | **OK**: orden contrabalanceado; `comparar` usa E2, el mismo ejecutor y el mismo vigía para las tres; T 0,7 y semillas 11/42/2026; máx. 2 iteraciones; ctx 2048; las pruebas de la estable con el servidor falso confirman el mismo prompt (11 OK) |
| — | procesos liberados | **OK**: ningún llama ni ningún guardián al terminar |

En G3, G4 y G8 se confirmó la configuración efectiva de llama.cpp en cada arranque: 29/29 capas en GPU, n_ubatch 128,
`flash_attn` activo y `--fit` sin ajustes.

## Recuperación independiente de Wallpaper Engine (investigada y probada)

- **Cómo funciona:**
  - se lanza por WMI (`Win32_Process.Create`) con `pythonw`: fuera del árbol de procesos de Equipo IA y sin ventana;
  - espera al proceso de Equipo IA por su handle, así que no le afecta que se reutilice el pid;
  - si Equipo IA termina sin retirar la marca, ejecuta `-control play` y se retira; vive como mucho 24 h.
- **Lo que no hace:** no es un servicio, no toca el inicio de Windows ni ningún otro proceso.
- **Prueba real** (`guardian2/`):
  - con una terminación inesperada simulada, reanudó el fondo en ~4 s;
  - con una terminación normal, se retiró sin actuar.
- **Lo que no cubre:**
  - un corte de luz o un reinicio (no comprobé si Wallpaper Engine arranca reproduciendo tras un reinicio, aunque es lo
    habitual);
  - que alguien mate el propio guardián.

## Pendiente y riesgos

- **De día**, la VRAM ajena (hasta ~2230 MiB con el fondo detenido) supera el presupuesto de 1992: F1 no empezaría o se
  quedaría esperando. V4.2 es para la noche o para momentos de poco uso.
- F1 completa son 90 ejecuciones (15 tareas × 3 configuraciones × 2 repeticiones) y durará **varias horas con la GPU
  cargada** (ruido del ventilador). El fondo animado estaría detenido todo ese tiempo, salvo cuando aparezca alguien.
- G4 prueba el monitor de RAM con un umbral más estricto que la memoria real, sin agotar la RAM de verdad, como la
  estable.
- No se ha probado `comparar` de principio a fin con Qwen real: es la propia evaluación F1, no autorizada.

## Primera evaluación F1 completa (2026-11-12, 11:29–11:45): ABORTADA, no válida

- **Autorización:** el usuario la autorizó de día con el PC libre.
- **Condiciones de inicio:** sin persona (7,6 h sin entrada), VRAM ajena de 854 MiB con el fondo detenido y GPU ≤ 38 %.
- **Avance:** 39 de 90 ejecuciones (S1 r1 completo, S1×3 r1 completo, E3 r1 T01–T09).
- **Cómo se detuvo:** abortó en E3/T10 con `FugaDeOraculo ['T10.esperado']`. La salida fue el código 3, todo de forma
  ordenada.
- **Estado al detenerse:**
  - Wallpaper Engine restaurado, con el mismo PID;
  - ningún llama ni guardián vivo;
  - todas las ejecuciones con E2 efectivo (29/29 capas, ubatch 128, sin ajustes de `--fit`).
- **Causa: falso positivo del detector de fugas en los pasos 2 y siguientes.**
  - A1 escribió por sí mismo la respuesta correcta, `['a', 'b', 'c']`.
  - E3 pasa ese código a A2.
  - `fugas_de_oraculo` busca el literal esperado en todo el prompt sin distinguir su origen.
  - Las puertas no lo vieron: G10 usa un servidor falso que nunca acierta.
- **Evidencia:** `evidencias/v31_f1_vram_exp_v4/f1_comparacion1/aborto.json`, `comparacion.json` y `r1/`.
- **Pendiente (requiere decisión):** corregir el detector en el laboratorio V4 para que ignore el texto producido por
  el modelo en la misma tarea. Haría falta un prerregistro V4.3, repetir las puertas afectadas (G5, G10 y una
  prueba nueva de E3 con un modelo falso que acierta) y repetir F1 desde cero.
