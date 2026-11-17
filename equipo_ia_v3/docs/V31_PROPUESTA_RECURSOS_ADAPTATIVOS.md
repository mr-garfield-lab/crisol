# Propuesta: gestión adaptativa de recursos para Equipo IA (POSTERIOR a F1)

**Estado:** propuesta. **No está implementada.** No cambia F1-VRAM-EXP-V4.4 ni sus límites.

## 1. Objetivo

Que Equipo IA trabaje en segundo plano sin perjudicar a quien use el PC:
- cede recursos en cuanto otra persona o aplicación los necesita;
- protege la GPU del calor y limita el ruido;
- nunca toca aplicaciones ajenas ni la configuración del hardware.

## 2. Tres estados

| Estado | Cuándo | Qué hace Equipo IA |
|---|---|---|
| **ACTIVO** | No hay persona ni carga ajena relevante, hay VRAM y RAM con reserva, la GPU está fría (≤ temperatura de reanudación) y la supervisión funciona | Genera, con pausas de enfriamiento entre peticiones |
| **ESPERA** | Hay una persona o puede haberla, crece la carga ajena (VRAM, uso de GPU o una aplicación a pantalla completa), la GPU está caliente o faltan recursos | Termina o corta la petición en curso sin perder el estado. **No genera.** Si la espera es larga o falta VRAM, **descarga Qwen** (libera ≈ 4,4 GB). Vuelve a ACTIVO solo tras un periodo estable sin persona |
| **DETENIDO** | STOP, fallo de seguridad, temperatura crítica o freno de hardware, pérdida de supervisión (sensores o hilos), fuga del oráculo, o imposibilidad de continuar con seguridad | Cierra **solo** su propio servidor y restaura lo que tocó (p. ej. Wallpaper Engine). **No se reanuda sola:** hace falta una persona |

Transiciones:
- ACTIVO pasa a ESPERA con la primera señal.
- ESPERA vuelve a ACTIVO con todas las señales en verde durante un periodo de histéresis, por ejemplo 2–10 min, para
  no oscilar.
- Desde cualquier estado se pasa a DETENIDO por una causa crítica.

## 3. Detectar a una persona (sin confiar solo en teclado y ratón)

Se reutilizan las señales de V4.x (`persona()`), que fallan cerradas:
- entrada reciente;
- otra sesión activa;
- aplicación a pantalla completa (D3D o presentación);
- ventana «ocupada» que no es el escritorio.

Hay que añadir:
- **Carga ajena de GPU y VRAM:** procesos ajenos con VRAM creciente o uso de GPU sostenido. Un juego o un render son
  una persona aunque no se toque el ratón. Ya está medido por proceso (`GPU Process Memory`).
- **Audio o vídeo en reproducción** y la ventana en primer plano: una película no genera entrada.
- **Ante la duda, ESPERA:** nunca suponer que no hay nadie.

## 4. VRAM: convivir, no ampliar

- **La RTX 3050 tiene 8192 MiB físicos.** Los 6144 y 6912 MiB son límites del proyecto y **no se elevan
  automáticamente.**
- **Medición dinámica:** se mide la VRAM disponible y se reserva una parte para aplicaciones ajenas, por ejemplo
  ≥ 1,5–2 GB, más el crecimiento observado. Si no cabe Qwen con esa reserva, no se carga.
- **Ceder:** si una aplicación ajena crece, ESPERA; si la espera se alarga, se descarga el servidor propio.
- **Reducir la huella propia** solo con evidencias del laboratorio de VRAM:
  - E2 ya ahorra unos 106 MiB sin perder velocidad;
  - KV en q8_0 ahorra 154 MiB y pierde un 3,5 %;
  - capas en CPU ahorran 350–886 MiB y pierden un 21–43 %.

  Cualquier cambio necesita sus propias pruebas y tu autorización.
- **Las reservas de seguridad no se reducen** sin pruebas y autorización.

## 5. Calor y ruido (no es lo mismo que la VRAM)

- **El ruido depende de la carga sostenida de la GPU, no de la VRAM.** Los ventiladores responden a la temperatura; la
  temperatura, a cuánto tiempo seguido se genera.
- **Palancas permitidas:**
  - pausas de enfriamiento entre peticiones (V4.4);
  - un ciclo de trabajo máximo, por ejemplo ≤ X % de cada ventana de 5 min;
  - límites de tokens por petición;
  - no encadenar tareas largas.
- **Palancas prohibidas:** frecuencias, potencia, curvas de ventiladores o límites del hardware.
- **Métrica de ruido indirecta:** porcentaje del ventilador (`fan.speed`, que esta tarjeta sí reporta), tiempo por
  encima de 75–80 °C y número de frenos de software. No hay micrófono ni se propone usarlo.

## 6. Reglas que no cambian

- No cerrar ni alterar aplicaciones ajenas.
- No ejecutar trabajo oculto mientras otra persona usa el PC.
- No elevar los límites de VRAM.
- No reducir reservas sin pruebas.
- No cambiar frecuencias, potencia ni ventiladores.
- Cada transición queda registrada con su causa y lo que se midió.

## 7. Cómo se probaría (después de F1)

1. **Máquina de estados pura, con sensores simulados.** Pruebas y mutaciones, como en V4.4.
2. **Pruebas reales cortas:**
   - aparece carga ajena mientras se genera: la petición se corta en segundos;
   - una espera larga descarga Qwen y libera la VRAM;
   - la vuelta a ACTIVO respeta la histéresis.
3. **Medida de convivencia:** una sesión con uso normal del PC (vídeo, navegador) donde el usuario anota si notó algo,
   comparada con los registros.
4. **Medida de ruido:** % de ventilador y temperatura con y sin ciclo de trabajo, con la misma tarea.
