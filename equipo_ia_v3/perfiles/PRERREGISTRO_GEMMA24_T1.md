# Preregistro: gemma24 (Gemma 4 26B-A4B), primer modelo «grande» en una tarjeta de 8 GB

Escrito ANTES de cargar el modelo. Fecha: 2026-11-17. El usuario autorizó la descarga y pidió «las pruebas que
consideres idóneas».

## Modelo
- `unsloth/gemma-4-26B-A4B-it-GGUF`, revisión `c099eb48e663fd284577b04978a94ffccb261841`,
  `gemma-4-26B-A4B-it-UD-Q4_K_M.gguf`, 16 947 541 728 bytes, SHA-256
  `f2c28b3dc4776931ac6f879e11f203dec637ea0f14267a86ec8f6165f63f293f`. Licencia Apache-2.0.
- 25,2B parámetros por expertos (~4B activos por token), arquitectura `gemma4`, la misma que gemma12.
- Registrado como modelo DEL USUARIO (`añadir_modelo`, alias `gemma24`): los laboratorios le aplican siempre el perfil
  por hardware. Es la primera prueba real de ese camino con un modelo que no cabe en la GPU.
- Equipo: RTX 3050 8 GB, Ryzen 5 5600GT, 32 GB, llama.cpp b12110, contexto 4096.

## Pruebas (en este orden; si una falla por algo de infraestructura, se para y se anota)
1. **Velocidad** (corta, 2 respuestas de 200 tokens), con las capas que proponga el perfil.
2. **Revisión de código** (`lab_revision`, `herramienta3`, 32 casos): que la infraestructura funciona con él.
3. **Diagnóstico de Project Zomboid** (los mismos 22 casos de la tanda 1b, condición `hechos`): donde más margen hay.

## Predicciones (no son reglas; se comparan al final)
- **Perfil:** capas en GPU, 30–45 % de las del modelo. VRAM prevista por debajo del tope (7168 MiB).
- **Velocidad:** 8–15 tokens/s; menos de 5 sería un mal resultado para un modelo por expertos.
- **Revisión:** 22–24 de 24, al nivel de gemma12 (24/24).
- **Diagnóstico de Project Zomboid:** 11–14 de 18, frente a 11 de gemma12, y al menos 2 de 4 nuevos.

## Reglas de decisión
1. **Crisol funciona con un modelo grande:** las 3 pruebas terminan sin corte por VRAM ni por temperatura, con cierre
   limpio y la VRAM máxima por debajo del tope.
2. **Al nivel del equipo en código:** al menos 22 de 24 en la revisión.
3. **Mejora el diagnóstico:** al menos 13 de 18 en Project Zomboid (2 más que gemma12), sin más falsas alarmas (≤ 2) ni
   más inseguros (≤ 1) que gemma12.
4. Se informa: tokens por segundo reales, capas en GPU, VRAM máxima, RAM usada, segundos por respuesta y respuestas
   cortadas. La velocidad no decide nada.

Evidencia: `evidencias/v31_gemma24/`.

## Resultado (2026-11-17; revisión 14:19–14:24, diagnóstico 14:24–14:45)
| prueba | gemma24 | gemma12 (referencia) | predicción |
|---|---|---|---|
| Perfil: capas en GPU | 9 de 30 (30 %); 10 tras cerrar apps | 37–39 de 48 | 30–45 % |
| Velocidad real | **10,6–11,2 tokens/s** | 13–15 | 8–15 |
| Revisión de código | **24/24**, 0 rotos, 0 falsas alarmas | 24/24 | 22–24 |
| Diagnóstico de Project Zomboid (hechos) | **15/18** (conocidos 13/14, nuevos 2/4) | 11/18 | 11–14 |
| Controles sin falsa alarma | **4/4** | 2/4 | — |
| Arreglos inseguros | **0** | 1 | — |
| Respuestas cortadas | 0 | — | — |
| VRAM máxima | 6607 MiB (tope 7168) | — | < tope |

Reglas:
1. **Crisol funciona con un modelo grande: SÍ, CON MATIZ.** No hubo cortes por VRAM ni por temperatura, y todo cerró limpio. Pero el
   diagnóstico se cortó DOS veces por el freno de memoria del núcleo (`presion_memoria_258916kB` y `…248768kB`:
   «MemAvailable» por debajo de su umbral). El armazón rearrancó solo y terminó sin perder ni repetir casos. Hay que
   investigar qué mide ese freno en Windows: al terminar quedaban 21,9 GB de RAM libre, y el modelo (17 GB) se lee
   desde disco. Sin tocar el núcleo (V2-F.1, protegido).
2. **Al nivel del equipo en código: SÍ** (24/24).
3. **Mejora el diagnóstico: SÍ** (15 ≥ 13, 0 falsas alarmas ≤ 2, 0 inseguros ≤ 1).

Sigue sin acertar el guardado lento (0/2, nuevo) ni una de las dos opciones mal escritas (C13). En `bruto` sigue
acertando 1/18, igual que los demás: sin el traductor no hay diagnóstico.
Lectura: el primer modelo «grande» medido en una tarjeta de 8 GB es el mejor cerebro de diagnóstico hasta ahora, a
unos 11 tokens/s. El perfil por hardware acertó la carga parcial sin superar el tope. El freno de memoria es lo
siguiente que hay que entender.
