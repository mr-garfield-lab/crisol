# Equipo IA V3.1 — Plan de activación del modelo local (F1)

**Estado: PROPUESTA, pendiente de aprobación** (2026-11-10; actualizada el 2026-11-11 tras el cierre de F0.5 y la
etapa de mantenimiento: §5, §7–§9). No se ha descargado ningún modelo ni llama.cpp. Las cifras de VRAM y de velocidad
son ESTIMACIONES (`eq3/perfiles_pc.py`, Etapa 6) hasta medirlas en este PC.

## 1. Recursos medidos en el PC (solo lectura)

| Recurso | Medido | Consecuencia |
|---|---|---|
| GPU | RTX 3050, 8192 MiB, capacidad 8.6, controlador 610.88, PCIe 3.0 x8 | CUDA disponible; el controlador admite los binarios CUDA 12 de llama.cpp |
| VRAM en uso por otras aplicaciones | ≈2,0 GiB; la GPU estaba al 96 % de uso durante la medición | Para F1 hay que cerrar las aplicaciones que usan la GPU (juegos, fondos animados) |
| RAM | 31,3 GB, ≈16 GB libres | Suficiente para un 7B entero en la GPU; el 14B obligaría a repartir capas en RAM |
| CPU | Ryzen 5 5600GT, 6 núcleos / 12 hilos | `-t 6` para la parte que quede en la CPU |
| Disco C: | ≈79 GB libres | El GGUF del 7B ocupa ≈4,5 GB |
| llama.cpp / GGUF | No hay ninguno | Hay que obtenerlos (§3), con tu autorización |

## 2. Modelo recomendado: Qwen2.5-Coder-7B-Instruct, Q4_K_M, entero en la GPU

| Opción | VRAM estimada (ctx 8192) | Cota de generación* | Valoración |
|---|---|---|---|
| 3B Q4_K_M | ≈2,5 GiB | ≤ ~115 tok/s | Solo como comparación rápida |
| **7B Q4_K_M** | **≈5,3 GiB** (5431 MiB) | **≤ ~47 tok/s** | **Recomendado**: cabe entero bajo el tope de 6144 MiB del AI Lab Coordinator |
| 7B Q4_K_M con caché KV q8_0 y flash attention | ≈5,1 GiB | similar | Más margen si las otras aplicaciones no se cierran |
| 14B Q4_K_M | 25 de 48 capas en la GPU | ≤ ~9 tok/s | Unas 5 veces más lento: solo un experimento posterior con las mismas tareas |

\* Techo teórico (ancho de banda / bytes por token), no una medición.

**Un solo servidor** compartido por A1, A2 y A3 por turnos (`--parallel 1`): cada agente conserva su tarjeta de rol,
su prompt, su memoria individual y sus responsabilidades; lo único compartido son los pesos del modelo.

## 3. Lo que tendrías que obtener tú (o autorizarme a descargar)

1. **llama.cpp para Windows con CUDA 12** (versión publicada del repositorio oficial `ggml-org/llama.cpp`): el ZIP
   de binarios `win-cuda-12.x-x64` y el ZIP de `cudart` correspondiente. Se descomprime en una carpeta propia
   (por ejemplo `C:\IA\herramientas\llama.cpp`); no requiere instalación ni permisos de administrador.
2. **El GGUF** `qwen2.5-coder-7b-instruct-q4_k_m.gguf` del repositorio oficial de Qwen en Hugging Face, comprobando
   su SHA-256 publicado. Carpeta sugerida: `C:\IA\modelos\`.
3. Nada más: ni Python adicional, ni CUDA Toolkit, ni cambios de configuración de Windows.

## 4. Orden del servidor (la lanzas TÚ; Equipo IA no lanza ni cierra procesos tuyos)

```powershell
llama-server.exe -m C:\IA\modelos\qwen2.5-coder-7b-instruct-q4_k_m.gguf `
  --host 127.0.0.1 --port 8080 -c 8192 -ngl 99 -t 6 --parallel 1
```

- `--host 127.0.0.1`: nunca expuesto a la red (una mutación de la Etapa 6 lo vigila).
- Medir con `nvidia-smi` la VRAM real con el modelo cargado; si se acerca a 8 GiB, usar `-c 4096` o la caché q8_0.

## 5. Qué construiré en F1 (solo tras tu aprobación)

| Pieza | Qué hace | Prueba |
|---|---|---|
| `eq3/servidor_pc.py` | Se conecta a un llama-server YA lanzado en `127.0.0.1`: comprueba `/health` y `/props`, identifica el modelo (nombre, contexto, SHA-256 del GGUF si se indica su ruta) y no lanza ni cierra procesos. Las lecturas de memoria de V2-F.1 en Windows YA están resueltas en F0.5 (`eq3/lanzador_eq2.py`, memoria real); `majflt` depende de la decisión de §7 | Servidor HTTP falso en `127.0.0.1` (respuestas correctas, caídas, modelo equivocado, puerto ajeno) |
| Conexión con `FuncionSupervisada` | Inyecta el backend real por el punto de inyección existente; A1/A2/A3 conservan roles, prompts y memorias | 3 tareas prerregistradas con respuestas REALES, traza verificada, `backend.simulado = False` |
| Límites y STOP | Tope de tokens por paso (los de V2-F.1), tiempo máximo por tarea, número de rondas, STOP por archivo | Pruebas con el servidor falso (lento, colgado, STOP a mitad) |

La ejecución del código generado SIGUE BLOQUEADA en F1 (SEG-01): el resultado máximo es «aceptada sin ejecución».

## 6. Después de F1 (cada fase con su aprobación)

- **F2:** contexto del grafo y memoria en los prompts, comparando con y sin ellos sobre las mismas tareas.
- **F3 (SEG-01):** aislamiento real. En este PC la opción sin instalar nada es **Windows Sandbox** (Windows 11 Pro):
  máquina virtual desechable sin red, con una carpeta de entrada de solo lectura y otra de salida. Activarla es un
  cambio de configuración de Windows que tendrías que hacer tú. Alternativa: WSL2 con Docker o bubblewrap (requiere
  instalarlos). Antes de cada sesión, las pruebas canario del plan (red, archivo del anfitrión, escritura fuera,
  memoria, procesos, tiempo) deben dar TODO bloqueado; si una no, no se ejecuta nada.
- **F4–F6:** bucle de corrección con pruebas ocultas, experiencias verificadas y evaluación con tareas nuevas, según
  `V3_1_PLAN.md`.

## 7. Decisiones que necesito antes de empezar F1

| # | Decisión | Opciones | Recomendación |
|---|---|---|---|
| D1 | Aprobar F1 | Sí / todavía no | — |
| D2 | Obtener llama.cpp (CUDA 12) y el GGUF del 7B (§3) | Los descargas tú, o me autorizas a descargarlos de las fuentes oficiales | Como prefieras; en ambos casos se comprueba su SHA-256 antes de usarlos |
| D3 | Criterio de `majflt` en Windows (`docs/V31_MAJFLT_WINDOWS.md`) | (1) sigue ausente: toda respuesta en Windows es «no concluyente»; (2) `HardFaultCount` medido, con autocomprobación y fallo cerrado | **(2)**: sin ella, ninguna medición de F1 en Windows sería concluyente |
| D4 | Lanzar el servidor | Lo lanzas tú con la orden de §4, o una orden de eq3 que lo lance y lo cierre | Tú: Equipo IA no lanza ni cierra procesos tuyos |

## 8. Cómo se evaluará F1 (prerregistrado ANTES de ver resultados)

La pregunta de F1 no es solo «¿funciona con un modelo real?», sino **«¿aporta el equipo A1/A2/A3 algo frente a un
solo agente?»**. Con un 7B, varios agentes del MISMO modelo comparten puntos ciegos, y los estudios muestran que el
debate a menudo no supera a un agente con votación a igual presupuesto. Por eso F1 mide tres configuraciones sobre
las MISMAS tareas y con el MISMO tope de tokens por tarea:

| Configuración | Qué es |
|---|---|
| **S1** | Un solo agente (rol de A1, sin revisión) |
| **S1×3** | El mismo agente, 3 respuestas independientes; gana la que pase los oráculos o, si ninguna, la mayoritaria |
| **E3** | El equipo A1/A2/A3 de V2-F.1 tal como está |

- **Tareas:** las 3 prerregistradas de §5, más un reto nuevo de diagnóstico estático con material REAL (propuesta:
  `zomboid_v2`, con problemas de mods de Project Zomboid que el usuario autorice leer; solo lectura, fragmentos
  copiados, sin redistribuir mods ajenos en ZIP compartidos). Cada tarea con su respuesta esperada y su oráculo
  ANTES de ejecutar nada.
- **Métricas por tarea:** acierto según el oráculo; citas válidas y rechazadas (verificador de citas); tokens y
  tiempo de pared; número de rondas; respuestas «no concluyentes» y su motivo.
- **Criterio de decisión** (fijado de antemano): si E3 no supera a S1×3 en acierto con el mismo presupuesto, la
  recomendación será simplificar el equipo (menos agentes, o roles con herramientas distintas), no ampliarlo.
- **Repetición:** temperatura 0 y semilla fija (las de V2-F.1); cada configuración se ejecuta 2 veces para comprobar
  que el resultado es estable.
- La ejecución de código generado SIGUE BLOQUEADA: el máximo es «aceptada sin ejecución» (SEG-01).

## 9. Orden de trabajo propuesto para F1

1. Con D1–D4 resueltas: comprobar el SHA-256 del GGUF y de llama.cpp; lanzar el servidor (tú) y medir la VRAM real.
2. `eq3/servidor_pc.py`, con pruebas contra un servidor falso y mutaciones; si D3 = (2), el adaptador de `majflt`
   con su sonda, pruebas y mutaciones (mismo patrón que la memoria real de F0.5).
3. Prerregistrar tareas, oráculos y el criterio de §8 en un archivo con su SHA-256, ANTES de la primera ejecución.
4. Ejecutar S1, S1×3 y E3 (2 veces cada una); informe con todas las respuestas, trazas y métricas.
5. `verificar_v3.py --completo` al final (con `--reanudar` si se corta), entrega versionada sin rutas personales y
   commit local.
