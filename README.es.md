# Crisol

**Un laboratorio local para poner a prueba «cerebros» de IA en tu propio PC, y usarlos con seguridad.**

> **Estado: experimental y en evolución.** Crisol es un proyecto de investigación en pleno desarrollo. Cambiarán las
> interfaces, los resultados y la estructura de carpetas. Todo lo que sigue dice si está **medido** o solo **estimado**.

Crisol ejecuta modelos abiertos pequeños en local con [llama.cpp](https://github.com/ggml-org/llama.cpp) y mide lo que
de verdad saben hacer. Un verificador determinista, sin IA, decide si aprueban, y las reglas de decisión se escriben
**antes** de preguntar a ningún cerebro (preregistro).

## Qué hace hoy

| Área | Qué mide | Estado |
|---|---|---|
| Núcleo del equipo (papeles A1/A2/A3) | Proponer, contrastar y votar, con memoria y herramientas controladas | Funciona; un solo modelo puede hacer los tres papeles |
| Laboratorio de revisión de código | Los cerebros arreglan errores de compilación de Python y Java, comprobados con compiladores reales | Medido: el mejor cerebro arregló 24/24 y no rompió ningún archivo correcto |
| Laboratorio de proyectos grandes | Encontrar y usar datos en un código mucho mayor que su contexto | Medido: 21–22/24 en código real |
| Laboratorio de Blender | Los cerebros diseñan escenas 3D; un verificador las mide en Blender | Medido: la tarea más grande (robot) aprobada 82/82 por un cerebro |
| Perfiles de hardware | Detecta tu equipo y propone capas, contexto y topes de seguridad | Funciona; contrastado con registros reales de llama.cpp |
| Laboratorio de diagnóstico de juegos | Lee registros de juegos (Project Zomboid, RimWorld, HOI4) para encontrar problemas de mods y de rendimiento | **Experimental, en pruebas; no se incluye en la primera publicación** |

## ¿Cuántos cerebros?

Tú eliges: **1, 2 o 3**. El núcleo tiene tres papeles (A1, A2 y A3) y se diseñó para que **un mismo modelo pueda hacer
los tres** (avisa cuando empieza a darse la razón a sí mismo). Los laboratorios aceptan la lista de modelos que quieras.
Asignar un modelo distinto a cada papel está previsto para una versión futura, y más adelante podría haber más papeles.

## Los modelos los eliges tú

Crisol **no incluye ni impone ningún modelo.** Descargas los modelos GGUF que quieras (respetando sus licencias) y los
registras:

```sh
py perfiles/equipo_perfil.py añadir_modelo ruta/al/modelo.gguf --alias mimodelo
py perfiles/equipo_perfil.py recomendar --modelo mimodelo
```

El perfil te dice cuántas capas caben en tu GPU, qué contexto puedes usar y qué topes se aplican. Cada dato se marca
como **medido** o **ESTIMADO**. Puedes cambiarlos tú, pero el tope de VRAM nunca se supera.

## Hardware

**Medido en:** AMD Ryzen 5 5600GT, 32 GB de RAM, NVIDIA RTX 3050 de 8 GB, Windows 11, contexto 4096.

| Cerebro (Q4) | ¿Cabe en 8 GB? | Velocidad medida |
|---|---|---|
| Qwen2.5-Coder 7B | entero | ~40 tokens/s |
| Ministral 3 8B | entero | ~35 tokens/s |
| Gemma 4 12B QAT | en parte (39 de 48 capas) | ~15 tokens/s |

**Otros equipos (ESTIMADO, sin medir):**

| Tu equipo | Qué esperar |
|---|---|
| Sin GPU / < 4 GB de VRAM | Modelos pequeños en el procesador, contexto corto, lento |
| 6–8 GB | Como el PC medido |
| 12 GB | Modelos de 12B enteros en la GPU, más o menos el doble de rápido |
| 16 GB o más | Cuantizaciones de más calidad, más contexto o dos cerebros cargados |

Los límites de seguridad **se adaptan a tu hardware**. El tope de VRAM sale de la memoria de tu tarjeta y los frenos de
temperatura, de los límites que declara su driver. No se copian del PC donde se desarrolló Crisol. Hoy solo se detectan
GPUs NVIDIA; AMD, Intel y Apple están sin medir.

Si lo pruebas en otro hardware, comparte tu perfil (`py perfiles/equipo_perfil.py informe` lo saca sin datos
personales). Así «estimado» pasa a «medido».

## Funciona con tu propio asistente de IA

Todas las herramientas pueden sacar JSON (`--json`), y `informe` genera un informe del hardware **sin rutas, sin
usuario y sin nombre del equipo**. Puedes pegarlo en cualquier asistente (Claude, Gemini, ChatGPT…) y pedirle ayuda.
Los asistentes que trabajen con el código deben leer [`AGENTS.md`](AGENTS.md).

## Principios de seguridad

- El código que escriben los cerebros se ejecuta **solo dentro de una caja aislada** (hoy, el laboratorio de Blender),
  nunca en tu sistema.
- No se borra nada. Se trabaja sobre copias y cada acción queda registrada.
- Topes estrictos de VRAM y de temperatura; un archivo `STOP` para cualquier ejecución.
- Sin APIs de pago y sin telemetría: todo se queda en tu PC.

## Instalación y comprobación rápida

Guía paso a paso: **[INSTALL.es.md](INSTALL.es.md)**. La comprobación rápida no necesita GPU ni modelos (ejecútala
desde la carpeta del repositorio):

```sh
py -B -X utf8 comprobar_todo.py
```

## Hoja de ruta (sin fechas prometidas)

- Un modelo distinto para cada papel del núcleo; equipos de más de tres.
- Sacar el laboratorio de diagnóstico de juegos de la fase de pruebas.
- Medir de verdad GPUs AMD e Intel, varias GPUs y Android/Termux.
- Instalación con un solo comando.

## Participar

Las opiniones, los avisos de fallos y las mediciones de otros equipos son muy bienvenidos. Abre una incidencia
(*issue*) o una conversación (*discussion*).

## Licencia

[MIT](LICENSE) © 2026 MR. Garfield. Los modelos, llama.cpp, Blender y el JDK **no** se incluyen y conservan sus propias
licencias.
