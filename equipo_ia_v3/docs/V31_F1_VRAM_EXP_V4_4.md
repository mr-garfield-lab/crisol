# V3.1 F1-VRAM-EXP-V4.4 — protocolo térmico

**Estado:** laboratorio experimental, prerregistrado. La evaluación F1 completa **no** se ha ejecutado con V4.4.

## 1. Por qué

- La F1 con V4.3 (2026-11-12, 13:00–13:11) se detuvo con 31/90 filas por un freno térmico a 84 °C.
  Evidencia: `evidencias/v31_f1_vram_exp_v4_3/f1_comparacion1_*`.
- **Causa:** E3 encadena generaciones largas al 96–97 % de uso de GPU casi sin pausa.
  - El chip sube unos 20 °C en 5–6 s y baja igual de rápido.
  - El disipador acumula calor: tras 10 s de reposo, la siguiente tarea partió de 59 °C y llegó a 84 °C en 26 s.
- **Decisión del usuario:** repetir las 90 ejecuciones desde cero con un protocolo térmico uniforme. Reanudar solo
  ahorraba 8–10 min y comprometía la validez.

## 2. Qué cambia (solo en el laboratorio)

V4.4 es un archivo nuevo, `eq3/evaluar_f1_vram_exp_v4_4.py` (copia de V4.3), más `eq3/termica_v4_4.py`. Siguen sin
cambios:
- V4.3 y V4.2;
- la estable y V2-F.1;
- los prerregistros V1–V4.3;
- las evidencias de las F1 detenidas: las 39 filas de V4.2 y las 31 de V4.3.

### 2.1 Sensores (solo lectura)

- Se leen con `nvidia-smi`, cada 1 s, durante toda la evaluación. Nunca se tocan potencia, frecuencias, ventiladores ni
  límites.
- **Datos que se registran** en `termica.jsonl`:
  - temperatura;
  - frenos por separado: térmico de hardware, térmico de software, de hardware y de potencia de hardware;
  - código de motivos activos;
  - relojes SM y de memoria, ventilador, pstate, uso y VRAM;
  - potencia.
- **Lo que el sensor no da queda como `null`**, por ejemplo `power.draw` = [N/A] en esta RTX 3050. Nunca se inventa.

### 2.2 Enfriar antes de CADA petición (igual en S1, S1×3 y E3)

`proteger_backend_v44` envuelve el protector de V4.3. Antes de cada `completar`:
- espera a que la GPU esté a **≤ 60 °C y sin freno de software**;
- la espera máxima es de **180 s**; si no se alcanza, es crítico y se aborta de forma ordenada, sin enviar nada.

Como todas las peticiones de los tres métodos pasan por `EV.ejecutar_tarea`, la pausa es idéntica para todos. G10 lo
comprueba: una espera por cada petición.

### 2.3 Vigilancia durante la generación

`VigiaTermica` extiende el vigía de V4.3 (VRAM y terceros):
- **En S1 y S1×3:** consulta la térmica en cada `parar()`, que el backend llama sin parar mientras dura la petición.
- **En E3:** además, al muestrear (cada 2 s) crea el archivo STOP de la tarea.

Si la térmica es crítica:
- se corta la petición en curso, por la misma vía que el tope de VRAM (G8);
- la tarea se guarda en `fila_termica.json`;
- **se aborta toda la evaluación**: `Abortada`, anotada en `comparacion.json`, con Wallpaper Engine restaurado.

Así una generación larga no puede eludir la vigilancia: pruebas simuladas en S1 y E3, y G12 con Qwen real.

### 2.4 Tiempos por separado

Cada petición anota `enfriamiento_s`, `generacion_s`, `temp_inicio_C` y `pico_C`. Cada fila guarda `termica`, con:
- `enfriamiento_s`;
- `generacion_s`;
- `trabajo_s` = total − enfriamiento;
- `total_s`;
- `pico_C` y `esperas`.

`comparacion.json` reúne todo en `tiempos` y `termica`. **Las pausas no se ocultan:** el informe dará la eficiencia con
y sin enfriamiento.

## 3. Umbrales y su justificación

Datos de la tarjeta, de `nvidia-smi -q`:
- RTX 3050 de 8192 MiB (dispositivo 0x2582);
- 115 W fijos;
- objetivo 83 °C, máximo de operación 92 °C, freno de hardware 94 °C y apagado 97 °C.

Datos medidos el 2026-11-12:
- en reposo, entre 39 y 52 °C;
- en reposo baja de 79 °C a 59 °C en ≤ 5 s;
- con carga sostenida sube unos 25 °C en 26 s.

| Umbral | Valor | Por qué |
|---|---|---|
| Reanudar | **≤ 60 °C** | Se evaluó entre 60 y 65 °C. Partiendo de 59 °C se llegó a 84 °C y partiendo de 52 °C, a 79 °C, así que con 65 °C una petición larga superaría el objetivo con facilidad. Se elige 60 °C: es el extremo bajo del rango y el enfriamiento esperado es de 5–15 s por petición. **No garantiza** quedarse por debajo de 83 °C en las peticiones más largas de E3, de unos 20 s; por eso está la regla del freno de software |
| Espera máxima | **180 s** | En reposo la GPU baja a ≤ 60 °C en segundos. Si no lo consigue en 3 min, algo anómalo ocurre (ventilación, otra carga) y se aborta |
| Freno de software continuo | **≥ 20 s → parada** | Que el controlador regule al llegar a 83 °C es normal y breve. Que regule durante casi una generación entera significa que la refrigeración no da abasto incluso con pausas |
| Temperatura crítica | **≥ 88 °C → parada inmediata** | 5 °C por encima del objetivo, donde la regulación del controlador ya no contuvo la temperatura, y 4 °C por debajo del máximo de operación (92 °C). **No está demostrado que sea el umbral óptimo**: es una protección conservadora |
| Freno de hardware (térmico, de potencia o cualquiera) | **parada inmediata** | A estas temperaturas no debería aparecer: indicaría un problema |
| Fallo de supervisión | **3 lecturas seguidas sin temperatura, o el hilo muerto → parada** | Sin supervisión no se sigue |
| Aviso | 80 °C | Solo se anota: el pico de cada petición queda en `pico_C` |

## 4. Pruebas

| Grupo | Qué prueba | Archivo |
|---|---|---|
| Regresión de V4.3 | Las 40 pruebas de V4.3, adaptadas: activan una térmica simulada y el formato del aborto es `Tipo: mensaje` | `test_eq3_evaluar_f1_vram_exp_v4_4.py`, `test_eq3_procedencia_v4_4.py` |
| Lectura | Lectura real de ejemplo; `[N/A]` queda como `null`; formato incorrecto o sensor ausente da error, no valores inventados | `test_eq3_termica_v4_4.py` |
| Fallos térmicos simulados | Freno de hardware (térmico, general y de potencia), 88 °C, freno de software de 19 s frente a 20 s e intermitente, 3 lecturas sin sensor, excepción en el hilo, hilo muerto, registro jsonl | ídem |
| Enfriar | Espera a 60 °C; no reanuda con freno de software; aborta si se agota la espera; aborta si se vuelve crítico mientras espera | ídem |
| Vigía | Corta y crea el STOP una sola vez; sin térmica falla cerrado; la VRAM sigue mandando | ídem |
| Protector | Una espera antes de cada petición, con los tiempos por separado; si no se enfría, no se envía nada; sin térmica, no se envía | ídem |
| Integración (flujo real de V2-F.1) | Mismo protocolo en S1, S1×3 y E3: una espera por petición y trabajo = total − enfriamiento. **Una generación larga, de 10 s, se corta en < 5 s en S1 y en E3** y aborta toda la evaluación. Sin térmica no se ejecuta nada | ídem |
| `comparar` | Un aborto térmico queda anotado; el fondo se restaura; la térmica se inicia y se detiene | ídem |
| G10 | Exige las pruebas térmicas | ídem |
| Mutaciones F24 | 59 mutaciones: las 36 de V4.3, reaplicadas, y 23 térmicas | `v3/mutaciones/v31_f1_vram_exp_v4_4.json` |
| Puertas nuevas | **G11:** sensores reales (temperatura y los cuatro frenos son obligatorios; lo demás se anota). **G12:** corte térmico real con Qwen, con la señal simulada a mitad de una generación larga: se corta en ≤ 3 s y se cierra limpio | `puertas` |

## 5. Riesgos residuales

- **Los umbrales son conservadores, no óptimos demostrados.** 88 °C y 20 s salen de las especificaciones de la tarjeta
  y de una sola sesión de medida.
- **Las peticiones más largas de E3 pueden llegar a 83–84 °C** aun partiendo de 60 °C, con un freno de software breve
  que se registra. Si dura ≥ 20 s, la evaluación se detiene.
- **El límite de 45 min por tarea de E3 incluye el enfriamiento.** Con pausas normales (5–15 s por petición, hasta 9
  peticiones por tarea) el margen sobra.
- **Sin medida de potencia**, porque el sensor no la da. **No se miden** la temperatura ambiente, el flujo de aire de
  la caja ni el polvo: conviene revisarlos físicamente.
- **El freno que detuvo V4.3 no se puede atribuir** a hardware o software: el supervisor de V4.3 los registraba juntos
  y los contadores acumulados de `nvidia-smi` marcan 0 µs. V4.4 los registra por separado.
