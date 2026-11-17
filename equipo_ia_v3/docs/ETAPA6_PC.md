# Equipo IA V3 — Etapa 6: optimización para el PC (Windows 11, Ryzen 5 5600, 32 GB, RTX 3050 8 GB)

**Estado: CERRADA** (2026-11-10). Verificador: F0–F11 correctas (`evidencias/etapa6_7/`).

> **Todo lo de esta etapa son ESTIMACIONES, NO validadas en el PC real.**
> - Este contenedor es Linux, sin GPU, sin llama-server y sin modelos.
> - No se ha descargado ningún modelo.
> - Las cifras deben confirmarse en el PC con `nvidia-smi` y con el registro de llama-server.

## 1. Qué aporta

`eq3/perfiles_pc.py` es un planificador de recursos que NO lanza nada. Recibe el modelo, el contexto y el equipo
declarado, y devuelve:

- **Capas en la GPU:** el máximo que cabe.
- **Memoria estimada:** VRAM (pesos proporcionales a las capas descargadas, caché KV en f16 y un margen de cálculo)
  y RAM.
- **Avisos:** por ejemplo, descarga parcial o RAM insuficiente.
- **Orden propuesta para llama-server:** como lista de argumentos, sin shell.

Decisiones de diseño, cumpliendo las restricciones de la orden maestra:

| Restricción | Cómo se respeta |
|---|---|
| Tres agentes no implican tres modelos | UN servidor compartido por A1/A2/A3 por turnos (`--parallel 1`), como en V2-F.1 |
| Presupuesto de 6144 MiB del AI Lab Coordinator | Se usa como TOPE de VRAM, igual que la reserva de Windows (1 GiB, estimación): se toma el menor de los dos. El valor está en una dataclass congelada y no se modifica ni se integra con ese proyecto |
| No descargar modelos | Catálogo APROXIMADO (Qwen2.5-Coder 3B/7B/14B en Q4_K_M). Con la ruta de un GGUF existente se usa su tamaño real por `stat`, sin leerlo |
| Seguridad del servidor | Solo `--host 127.0.0.1`. Se rechazan las rutas con caracteres de control y los enlaces simbólicos |
| Contexto | Admitidos 2048, 4096, 8192 y 16384 (en el teléfono, V2-F.1 usa 1024–3072) |

## 2. Plan estimado para el PC del usuario (contexto 8192)

| Modelo (Q4_K_M, tamaño de catálogo) | Capas en GPU | VRAM estimada | RAM estimada | Caché KV |
|---|---|---|---|---|
| Qwen2.5-Coder 3B (≈1,8 GiB) | 36 de 36 | 2520 MiB | 1024 MiB | 288 MiB |
| **Qwen2.5-Coder 7B (≈4,4 GiB): recomendado** | **28 de 28** | **5431 MiB** | 1024 MiB | 448 MiB |
| Qwen2.5-Coder 14B (≈8,4 GiB) | 25 de 48 (parcial) | 5992 MiB | 5866 MiB | 1536 MiB |

El tope de VRAM es el menor entre 8192 − 1024 y 6144, es decir, 6144 MiB. La recomendación es el mayor modelo
que cabe ENTERO en la GPU. El 14B cabe con descarga parcial, pero será notablemente más lento.

Orden propuesta para el 7B:

```
llama-server -m <ruta al GGUF> --host 127.0.0.1 --port 8080 -c 8192 -ngl 28 -t 6 --parallel 1
```

V2-F.1 lanza llama-server SIN `-ngl` (pensado para la CPU del teléfono). Usar la GPU en el PC exige lanzar el
servidor con esta orden y conectar Equipo IA a él (`--port`), o adaptar `servidor.py` con su propia línea base.
No se ha hecho, para no modificar `sistema/`.

## 3. Pruebas

| Prueba | Resultado |
|---|---|
| `pruebas/test_eq3_perfiles.py` | 12 de 12 correctas, incluida la CLI `equipo3.py pc` (aritmética comprobada a mano, tope del coordinador, reserva de Windows, monotonía con el contexto, orden local de un solo servidor, entradas inválidas, tamaño real por `stat`, rechazo de enlaces) |
| Mutación de la Etapa 6 (`v3/mutaciones/etapa6.json`) | 9 de 9 detectadas |
| Verificador integral | F0–F11 correctas; F9 = mutación de la Etapa 6, 9 de 9 |

## 4. Limitaciones

1. **Cifras.** Las del catálogo y las sobrecargas (300 MiB más un 5 %) son aproximadas, y la reserva de Windows
   es una estimación.
2. **Modelo de memoria.** No modela la caché KV cuantizada, `--flash-attn`, la división del contexto entre
   ranuras ni la memoria que usen otras aplicaciones de la GPU.
3. **Sin medición de rendimiento.** No se ha medido el rendimiento (tokens/s) ni la latencia: requiere el PC
   real.
4. **Detección.** El equipo se declara; detectarlo automáticamente en Windows queda pendiente de validar allí.
