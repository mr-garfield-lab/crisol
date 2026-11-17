# V3.1 — Laboratorio de VRAM: investigación CPU/GPU/Vega (2026-11-12)

Investigación de la orden técnica «optimización de VRAM y evaluación experimental CPU/GPU».
- **Qué se ha cambiado:**
  - no se ha integrado nada;
  - V2-F.1, la configuración estable, F1-VRAM-EXP y los prerregistros V1, V2 y V3 están intactos;
  - los límites de seguridad no se han cambiado: tope de 6912 MiB y 1832 MiB de VRAM ajena.
- **Dónde está:**
  - código: `lab_vram/`;
  - pruebas: `pruebas/test_lab_vram.py`, 7 OK;
  - evidencias: `evidencias/lab_vram/` (registros de llama.cpp, `banco.json` de cada batería y manifiesto).

## 1. Hardware y entorno detectados (MEDIDO)

| Elemento | Detectado |
|---|---|
| CPU | AMD Ryzen 5 5600GT, 6 núcleos / 12 hilos |
| RAM | 32 GB (2 × 16 GB DDR4-3200, doble canal); 31,3 GB visibles; archivo de paginación de 6,5 GB, casi sin uso |
| GPU discreta | NVIDIA RTX 3050 de 8192 MiB, controlador 610.88 (WDDM); tiene conectado el monitor (1440×900) |
| GPU integrada | AMD Radeon Graphics (Vega 7), habilitada, controlador 31.0.12042.4 (Adrenalin 22.20, de 2022), 512 MiB de UMA; Vulkan 1.3.217; **sin monitor conectado** |
| llama.cpp | b12110 (commit cd959bae9), compilación CUDA 12.4 verificada; solo dispositivo CUDA0 |
| Modelo | Qwen2.5-Coder-7B-Instruct Q4_K_M (4,68 GB), verificado por SHA-256 |

**Descarga autorizada en el chat:**
- `llama-b12110-bin-win-vulkan-x64.zip`, de la misma versión y de ggml-org;
- su SHA-256 coincide con el que publica GitHub y lo subió github-actions[bot];
- comparada con la compilación CUDA, solo añade `ggml-vulkan.dll`, y todo lo demás es idéntico byte a byte;
- se usó en una carpeta de laboratorio aparte, CUDA + `ggml-vulkan.dll`, verificada con su manifiesto (57 archivos);
- no se instaló ningún controlador ni se tocó ninguna configuración de Windows.

## 2. Método

- **Servidor:** `llama-server` propio, igual que lo lanza V2-F.1: `-c 2048 -t 6 -np 1 --no-ui`.
- **Prompt:** fijo de 1223 tokens, del tamaño de un primer paso de E3.
- **Generación:**
  - 256 tokens con temperatura 0, semilla 1 e `ignore_eos`, después de una petición de calentamiento;
  - **3 repeticiones** por configuración, más una prueba de STOP: corte a los 3 s y cierre del servidor.
- **Medidas:**
  - VRAM, con nvidia-smi y con los búferes que declara llama.cpp;
  - RAM del proceso y del sistema;
  - fallos duros de página (HardFaultCount);
  - uso de CPU y GPU;
  - tiempo hasta el primer token.
- **Huella del texto:** se guarda el SHA-256 del texto generado. El texto nunca se ejecuta.
- **Protecciones:**
  - antes de cada configuración se exigía que nadie usara el PC (≥ 10 min sin entrada, sin otra sesión y sin pantalla completa) y que la VRAM ajena no pasara de 1832 MiB;
  - un vigía cada 0,5 s terminaría **solo el servidor propio** si la VRAM total pasara de 6912 MiB, si apareciera entrada de teclado o ratón, o si la RAM disponible bajara de 2048 MiB;
  - **ninguna se disparó**, y la VRAM total máxima fue de unos 5530 MiB.
- **Criterio del laboratorio frente al de F1:** Wallpaper Engine (alrededor del 30 % de la GPU) activa la señal «aplicación ocupada» de Windows. El laboratorio la registra pero no la trata como una persona.
- **Entorno:** madrugada, con el PC sin uso y 950–1007 MiB de VRAM ajena. Unos 20 minutos de carga en total.

## 3. Resultados con Qwen 7B (MEDIDOS; tokens/s = media de 3 repeticiones)

Referencia A0 (como hoy):
- 4516 MiB de Qwen cargado y 4528 MiB de pico;
- 39,6 t/s de generación (39,74 y 39,44 en dos cargas independientes);
- unos 1530 t/s de prompt.

| Config | Qué cambia | VRAM Qwen (MiB) | Ahorro | Generación t/s | vs A0 | vs 41 | Prompt t/s | Texto = A0 |
|---|---|---|---|---|---|---|---|---|
| A0_estable | nada (`--fit` on, `-ngl` auto, FA auto) | 4516 | — | 39,6 | — | −3 % | ~1530 | sí |
| A1_todo_gpu | `--fit off -ngl all -fa on` | 4516 | 0 | 39,7 | 0 % | −3 % | 1538 | sí |
| **E2_ub128** | A1 + `-ub 128 -b 512` | **4410** | **−106** | **39,6 / 39,7** | **0 %** | −3 % | ~1437 (−6 %) | sí |
| E3_ub128_kvq8 | E2 + caché KV q8_0 | 4362 | −154 | 38,25 / 38,25 | −3,5 % | −7 % | ~1402 (−8 %) | sí* |
| E4_kv_ram | E2 + KV en RAM (`-nkvo`) | 4297 | −219 | 21,7 | −45 % | −47 % | 1213 | sí |
| B2_cpu2 | E2 + bloques 0–1 en CPU | 4166 | −350 | 31,2 | −21 % | −24 % | 924 | sí |
| F2_ffn_cpu4 | E2 + FFN de 4 bloques en CPU | 3955 | −561 | 27,8 | −30 % | −32 % | 735 | sí |
| C4_cpu4 | E2 + bloques 0–3 en CPU | 3898 | −618 | 26,2 | −34 % | −36 % | 689 | sí |
| F1_salida_cpu | E2 + capa de salida en CPU | 3788 | −728 | 24,3 (23,2–25,0) | −39 % | −41 % | 1016 | **no** |
| C6_cpu6 | E2 + bloques 0–5 en CPU | 3630 | −886 | 22,6 | −43 % | −45 % | 545 | **no** |
| V0_vulkan_rtx | Vulkan en lugar de CUDA en la RTX | 4395 | −121 | 38,6 | −3 % | −6 % | 1002 (−35 %) | sí |
| V2_vega2 | bloques 0–1 en la Vega | 4127 | −389 | 28,1 | −29 % | −31 % | 470 | sí |
| V4_vega4 | bloques 0–3 en la Vega | 3859 | −657 | 22,0 | −44 % | −46 % | 278 | sí |
| VS_salida_vega | capa de salida en la Vega | 3792 | −724 | 18,6 | −53 % | −55 % | 378 | sí |
| V6_vega6 | bloques 0–5 en la Vega | 3591 | −925 | 18,1 | −54 % | −56 % | 193 | sí |

\* La igualdad de texto se comprobó solo con 256 tokens de un prompt. **No** demuestra que la calidad sea la misma.

**Variabilidad:**
- entre repeticiones fue < 0,7 % (salvo F1, con un 7 %);
- entre dos cargas independientes, < 1 % (A0: 39,74 y 39,44; E2: 39,66 y 39,60; E3: 38,25 y 38,25).

**Lo que no cambió en ninguna configuración:**
- 0 fallos duros de página;
- STOP: corte a los 3,0 s y cierre en 0,2–0,5 s;
- VRAM liberada en ≤ 0,6 s;
- ningún proceso llama quedó vivo;
- 12,9–16,8 GB de RAM disponible.

**Desglose de la VRAM de A0 (MEDIDO, búferes de llama.cpp):**
- pesos 4168 MiB;
- caché KV 112 MiB;
- cómputo 141 MiB (Flash Attention ya está activa por defecto);
- contexto CUDA ≈ 95 MiB.

Ajustar la caché y los búferes solo puede ahorrar 100–250 MiB. **Para ahorrar 500–1024 MiB hay que sacar pesos de la RTX**, y cada bloque fuera cuesta ≈ 3,5–4 ms por token en la CPU, que es la penalización del ancho de banda de la DDR4.

## 4. Viabilidad

- **CPU/RAM:**
  - Funciona sin paginación ni fallos.
  - Ninguna configuración llega a ≥ 500 MiB de ahorro con ≥ 35 t/s: el ahorro mínimo útil (C4, −618 MiB) cuesta un −34 %.
  - Mover la capa de salida o 6 bloques **cambia el texto generado**, porque la aritmética de la CPU es distinta.
- **Vega 7:**
  - Funciona con CUDA + Vulkan en el mismo proceso.
  - **Es peor que la CPU en todas las comparaciones** (2 bloques: 28,1 frente a 31,2 t/s; procesando el prompt, la mitad), porque comparte la misma DDR4 que la CPU y añade transferencias entre dispositivos.
  - No vale la pena como acelerador del modelo.
- **Laboratorio 6B:** no hay ningún modelo de unos 6B en local; los `qwen-coder-3b.gguf` de `t/` son modelos falsos de las pruebas. Las pruebas cortas con el 7B fueron seguras y baratas (~1 min por configuración), así que un 6B no aportaba nada. **Etapa omitida** sin descargar nada.
- **Elegir la configuración al empezar cada tarea:**
  - Técnicamente es viable: cada configuración carga en ~3 s y libera en < 1 s.
  - Llama.cpp **ya lo hace sin avisar**: con `--fit on` (valor por defecto, que hereda A0) mueve capas a la CPU si quedan < 1024 MiB libres.
  - Eso hace que F1 dependa de la VRAM ajena del momento y no sea reproducible: si la VRAM ajena sube, la velocidad podría caer un 20–45 % sin que nada lo registre. **Es un hallazgo de riesgo.**

## 5. Lo que realmente determina el margen (MEDIDO + HIPÓTESIS)

- **VRAM de las otras aplicaciones (MEDIDO):**
  - de noche, 950–1007 MiB;
  - el día del intento 1, 1449–2390 MiB (variación de ~1,4 GB).
- **Quién la ocupa de noche (MEDIDO):** composición del escritorio en la RTX (dwm 369 MiB, Wallpaper Engine 160 MiB, explorer 137 MiB) y overlays y aplicaciones web (~30–70 MiB cada una).
- **La variación ajena supera el ahorro alcanzable:** la variación de la VRAM ajena es **mayor** que cualquier ahorro razonable en Qwen (≤ 154 MiB sin pérdida apreciable).
- **Diferencia con el pico del intento 1:**
  - el pico de Qwen medido aquí es de 4528 MiB (A0), frente a los ~4780 que se estimaron en el intento 1;
  - **hipótesis**: los ~250 MiB de diferencia eran VRAM ajena que creció durante la tarea (la ajena solo se midió al empezar);
  - no está verificado.
- **Alternativa con más impacto (HIPÓTESIS, no probada, requiere tu decisión):**
  - conectar el monitor a la salida de vídeo de la placa base, para que el escritorio, Wallpaper Engine y los navegadores se dibujen en la Vega;
  - podría liberar de la RTX la mayor parte de los 0,7–2,4 GB ajenos;
  - es un cambio físico y global del equipo (y puede afectar a quien juegue en ese PC), así que no lo he hecho.
  - La preferencia de GPU por aplicación de Windows (Configuración → Gráficos) es otra vía, también global; no la he tocado.

## 6. Respuestas

1. **¿Qué configuración da más estabilidad con el menor sacrificio de velocidad?**
   - **E2:** `--fit off -ngl all -fa on -ub 128 -b 512`.
   - Ahorra **106 MiB**, con la misma velocidad de generación (39,6 t/s), −6 % de velocidad de prompt y el mismo texto.
   - Además, `--fit off` hace que la colocación sea fija y reproducible.
   - E3 (KV q8_0) ahorra 48 MiB más a cambio de un −3,5 % de velocidad y de un posible efecto en la calidad. No lo recomiendo para F1.
2. **¿Vega, RAM, ambas o ninguna?**
   - Para el modelo, **ninguna**: la RAM cuesta ≥ 21 % por cada 350 MiB y la Vega rinde peor que la CPU.
   - La Vega solo tendría sentido para **dibujar el escritorio** (alternativa del §5), no para el modelo.
3. **¿Basta para retomar F1-VRAM-EXP?**
   - **No por sí solo.** E2 deja a Qwen en ~4420 MiB de pico, unos 360 MiB menos que el pico supuesto de 4780 con el que se calcularon los 1832 MiB de VRAM ajena permitida. Pero la VRAM ajena de día (hasta 2,4 GB) sigue sin caber.
   - Además, el prerregistro V3 exige ≤ 40 % de uso de la GPU y ninguna aplicación «ocupada». Wallpaper Engine incumple las dos cosas **siempre** (30–54 % y «ocupada» incluso con el PC sin uso), así que F1-VRAM-EXP no podría empezar nunca mientras siga abierto.
   - Retomarla requiere decidir los criterios de inicio (prerregistro V4) o hacerla con el escritorio en la Vega o en un horario sin carga.

## 7. Plan reversible de integración (NO aplicado; requiere tu aprobación y un prerregistro V4)

1. Variante «F1-VRAM-EXP-E2», separada como F1-VRAM-EXP. Pasaría `--fit off -ngl all -fa on -ub 128 -b 512` sin tocar V2-F.1. Falta comprobar si `ServidorLlama` admite opciones extra a través de `comando=`, que hoy solo usan las pruebas. Si no las admite, no se integra.
2. Recalcular la VRAM ajena permitida con el pico medido de E2: 6912 − 4420 − 300 = 2192 MiB, frente a los 1832 actuales.
3. Revisar el criterio de uso de la GPU y de «aplicación ocupada» de F1-VRAM-EXP para que distinga Wallpaper Engine de una persona (como hace el laboratorio), o exigir que se cierre por quien lo usa.
4. Volver al estado anterior = no usar la variante.

## 8. Riesgos y límites de este estudio

- Una sola tarjeta, un prompt fijo, 256 tokens y contexto de 2048. No se midieron prompts de ~2000 tokens ni la calidad de las respuestas.
- Todas las mediciones son de madrugada, con Wallpaper Engine usando la GPU: los t/s absolutos podrían variar con otra carga. Las diferencias relativas son consistentes entre cargas.
- La Vega se probó con un controlador de 2022; uno más reciente podría rendir algo más, pero su ancho de banda (DDR4 compartida) es un límite físico.
- La carpeta CUDA + Vulkan es solo de laboratorio, fuera del registro de externos de F1.
