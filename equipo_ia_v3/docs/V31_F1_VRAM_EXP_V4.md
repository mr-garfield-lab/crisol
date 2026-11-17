# V3.1 F1 — Variante experimental F1-VRAM-EXP-V4 (E2 + presupuesto verificado + Wallpaper Engine reversible)

Preparada el 2026-11-12 por orden del usuario. **La evaluación F1 completa NO se ha ejecutado ni está autorizada.**

**Qué no se ha tocado:**
- V2-F.1 (`sistema/`), la configuración estable (`eq3/evaluar_f1.py`, 6144 MiB) y F1-VRAM-EXP (V3) no se han
  modificado;
- los prerregistros V1, V2 y V3 siguen intactos: V4 los comprueba por su SHA-256.

**Dónde está:**
- código: `eq3/evaluar_f1_vram_exp_v4.py` y `lab_vram/wallpaper.py`;
- evidencias: `evidencias/v31_f1_vram_exp_v4/` y `evidencias/lab_vram/v4_wallpaper1/`.

## Cambios respecto de V3 y su justificación

| Elemento | V3 | V4 | Justificación (medida) |
|---|---|---|---|
| llama-server | por defecto (`--fit on`, `-ngl auto`) | **E2**: `--fit off -ngl all -fa on -ub 128 -b 512` (+ `-lv 4`, solo registro) | laboratorio: −106 MiB, misma velocidad; `--fit off` evita que llama.cpp pase capas a la CPU sin avisar |
| Cómo se pasa | — | prefijo de `comando` de `ServidorLlama` | `construir_argv` = `comando + [-m, --host, --port, -c, -t, -np, --no-ui]`: V2-F.1 sin cambios |
| Configuración efectiva | no se comprobaba | se lee `server.log` tras cada tarea: 29/29 capas, n_ubatch 128, sin ajuste de `--fit`; si no, infraestructura | requisito de reproducibilidad |
| Pico de Qwen | 4780 (**estimado**) | **4420 (medido)** | ver la sección siguiente |
| Margen | 300 | **500** ≈ 2 × 251 MiB | 251 = mayor crecimiento de la VRAM ajena compatible con el intento 1 |
| VRAM ajena máxima | 1832 | **1992** = 6912 − 4420 − 500 | ninguna cifra sin verificar |
| Tope total | 6912 | **6912** (sin cambios) | — |
| Persona | incluía «aplicación ocupada» siempre | entrada < 10 min, otra sesión, consola ajena, D3D a pantalla completa, presentación o «ocupada» **con una ventana que no sea el escritorio** | Windows marca «ocupada» porque el escritorio (`Progman`) ocupa toda la pantalla, también con el fondo detenido (medido). Un vídeo a pantalla completa sí cuenta como persona |
| Uso de la GPU | bloqueaba como si fuera actividad | **recurso aparte** (≤ 40 %, medido con el fondo ya detenido) | el fondo animado usaba un 26–54 % sin que hubiera nadie |
| Wallpaper Engine | — | `-control stop` con el PC libre; `-control play` al acabar, abortar, fallar o si aparece una persona | autorización expresa del usuario, solo para esta aplicación |

## 4780 frente a 4528 (y 4420)

- **4780 era una resta, no una medida de Qwen:** el pico total del intento 1 (6231 MiB, vigía en S1/T10) menos la
  VRAM ajena medida al **empezar** el bloque (1452 MiB) da 4779.
- **Medidas directas de Qwen (A0):**
  - humo de F1: 1421 → 5926 MiB = 4505 MiB cargado;
  - laboratorio: 4516 MiB cargado y 4528 MiB de pico, en dos cargas independientes.
- **Medida con E2:** 4420 MiB de pico, en dos cargas con un prompt de 1223 tokens y en una con 1735 tokens. Con un
  contexto fijo de 2048, la reserva no crece con el prompt.
- **Inferencia: por qué el intento 1 daba más.** Los ~251 MiB de diferencia (6231 − 4528 − 1452) eran, como mucho,
  VRAM ajena que creció durante el bloque. La VRAM ajena medida al empezar los bloques siguientes fue de 1588–1625 MiB
  (+136–173). No se puede atribuir con exactitud, porque el vigía solo guardaba el total. Por eso V4 usa 251 como cota
  superior del crecimiento y un margen del doble.

## Wallpaper Engine (medido, sin Qwen, PC libre)

| Estado | VRAM total | VRAM de Wallpaper Engine | Uso de la GPU | Restauración |
|---|---|---|---|---|
| Normal | 1006 MiB | 160 MiB | 31 % | — |
| Pausado (`-control pause`) | 1006 MiB (**0 liberados**) | 160 | 6 % | `play`: OK |
| Detenido (`-control stop`) | 847 MiB (**−159**) | 0 | 4 % | `play`: OK (158 MiB, 27 %) |
| Cierre ordenado (WM_CLOSE, `taskkill` sin `/F`) | **no se cierra**: lo ignora | 158 | 30 % | no fue necesaria |

- **Comprobaciones:** ninguna instancia duplicada; el mismo proceso de principio a fin; ninguna configuración
  modificada.
- **Cierre:** la documentación oficial no tiene ninguna orden para salir. Como el cierre ordenado no funciona, **no se
  automatiza** (forzarlo exigiría otra autorización). Además, no aportaría más que `stop`: 160 MiB son toda su VRAM.
- **Prueba real de V4:**
  - `stop` a las 04:37:57;
  - pico de E2, STOP (G3) y memoria (G4) con Qwen real;
  - `play` a las 04:38:52, y quedó en 1005 MiB y 34 % de GPU, igual que al principio.

## Pruebas de seguridad

| # | Comprobación | Cómo | Resultado |
|---|---|---|---|
| 1 | Detección de persona | simulada (13 pruebas de V4 + 6 del control) | OK |
| 2 | Persona ≠ fondo animado | simulada + real (escritorio «ocupado», sin nadie, no bloquea; un vídeo sí) | OK |
| 3 | Tope total de 6912 | vigía `VigiaExp` (V3), simulado; real: pico de 5267 | OK |
| 4 | Fluctuaciones | margen de 500, estabilidad ≤ 200 MiB, condiciones antes de cada tarea | OK (simulado) |
| 5 | STOP y liberación | **real con E2**: G3 corta en 0,11 s, cierre en 0,92 s, VRAM en 1,55 s; G4 en 5,7 s | OK |
| 6 | Restauración del fondo | real (2 veces) + simulada (error, persona, fondo que no se detiene) | OK |
| 7 | Fallos de arranque y cierre | E2 en el arranque, en el cierre y ante errores (`finally`); configuración no E2 = infraestructura | OK (simulado) |
| 8 | Estable sin cambios | SHA-256 de V1, V2 y V3 = 0 diferencias; pruebas de la estable y de V3 OK | OK |
| 9 | Configuración efectiva | `server.log`: 29/29 capas, n_ubatch 128, `flash_attn` activo, sin `--fit` | OK (real) |
| 10 | Evidencias previas | sin borrar ni sobrescribir nada | OK |

**Mutaciones:**
- F21 (V4): 15/15 detectadas;
- F22 (control de Wallpaper Engine): 6/6 detectadas.

## Riesgos que quedan

- **De día**, la VRAM ajena llegó a 2390 MiB. Aun restando los 159 de Wallpaper Engine, ~2231 supera los 1992: F1 no
  empezaría, o se pararía a esperar. Es viable de noche o con poco uso, como los ~850 MiB de esta madrugada.
- Si alguien abre de golpe una aplicación con mucha VRAM a mitad de una tarea, el vigía corta en ≤ 2 s. Entre medias
  podría haber contención breve, sin superar 8192.
- La detección de persona no ve a quien mira una pantalla que no está a pantalla completa sin tocar nada durante
  10 minutos.
- Detener Wallpaper Engine deja el fondo estático durante F1. Se restaura al terminar, pero si el proceso de Equipo IA
  muriera de golpe (corte de luz, cierre forzado), el fondo quedaría detenido hasta que alguien lo reanude o se
  reinicie.
- La puerta G5 completa (F15–F22 + V-SRV) **no** se ha vuelto a ejecutar en esta sesión, para no cargar el PC. Es
  obligatoria antes de F1.
- No hay una función `puertas` propia de V4: `comparar` exige un `puertas.json` de V4 que todavía no existe. Escribirla
  y ejecutarla (con G5) es el paso previo a F1.
