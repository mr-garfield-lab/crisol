# Instalar y probar Crisol

> Crisol es **experimental**. Esta guía está probada en **Windows 11 con una NVIDIA RTX 3050 de 8 GB**. En otros
> sistemas, los pasos 1–3 deberían funcionar; los demás no están medidos todavía.

## 0. Estructura de carpetas

Crisol espera los programas externos (que **no** van en el repositorio) en una carpeta `externos` junto a él:

```
mi_carpeta/
├── crisol/                 ← este repositorio
└── externos/
    ├── llama_b12110/       ← llama.cpp (paso 4)
    ├── modelos/            ← tus modelos .gguf (paso 5)
    └── jdk_temurin_21/     ← opcional: JDK para el laboratorio de Java (paso 7)
```

Todos los comandos se ejecutan **desde `crisol/equipo_ia_v3/`**, salvo que se diga otra cosa.

## 1. Python

Instala **Python 3.12** (python.org). Crisol solo usa la biblioteca estándar: no hay que instalar paquetes.
(`tokenizers` es opcional: solo mejora el recuento de tokens de Contexto Ligero.)

## 2. Comprobar que todo está bien (sin GPU ni modelos)

Desde `crisol/`:

```sh
py -B -X utf8 comprobar_todo.py
```

Esperado: ninguna `FALLA`. Lo que necesite algo que no tengas sale como `OMITIDO`: no es un error.

## 3. Ver tu hardware y el perfil que te propone Crisol

```sh
py -B -X utf8 perfiles/equipo_perfil.py detectar
py -B -X utf8 perfiles/equipo_perfil.py informe
```

`informe` no lleva datos personales: puedes pegarlo en cualquier asistente de IA o compartirlo en una incidencia.

## 4. llama.cpp (el motor que ejecuta los modelos)

Los laboratorios comprueban la huella SHA-256 de **cada archivo** de llama.cpp antes de lanzar nada, así que hace falta
**exactamente** esta versión:

1. Descarga de <https://github.com/ggml-org/llama.cpp/releases/tag/b12110>:
   - `llama-b12110-bin-win-cuda-12.4-x64.zip` (SHA-256 `1ce755bc3a061889234048f88e33328e17971eaad73c4666cfeb26026b317fee`)
   - `cudart-llama-bin-win-cuda-12.4-x64.zip` (SHA-256 `8c79a9b226de4b3cacfd1f83d24f962d0773be79f1e7b75c6af4ded7e32ae1d6`)
2. Descomprime **los dos** en `externos/llama_b12110/`.

La lista de archivos esperados está en `eq3/externos_f1.json`. Si falta uno, sobra o no coincide, Crisol no arranca
nada y te dice cuál.

## 5. Un modelo

Tú eliges el modelo. Para repetir las pruebas publicadas, usa los mismos archivos (descárgalos de su origen; las
huellas están en los registros):

| Alias | Archivo (en `externos/modelos/`) | Origen | Registro con su SHA-256 |
|---|---|---|---|
| `qwen25` | `qwen2.5-coder-7b-instruct-q4_k_m.gguf` | huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct-GGUF | `eq3/externos_f1.json` |
| `ministral3` | `Ministral-3-8B-Instruct-2512-Q4_K_M.gguf` | huggingface.co/mistralai/Ministral-3-8B-Instruct-2512-GGUF | `lab_vram/banco_modelos_extra.json` |
| `gemma12` | `gemma-4-12B-it-qat-UD-Q4_K_XL.gguf` | huggingface.co/unsloth/gemma-4-12B-it-qat-GGUF | `lab_blender/cerebros_extra.json` |

Respeta la licencia de cada modelo. Después, regístralo para el perfil y mira cómo cabe en tu equipo:

```sh
py -B -X utf8 perfiles/equipo_perfil.py añadir_modelo ../../externos/modelos/qwen2.5-coder-7b-instruct-q4_k_m.gguf --alias qwen25
py -B -X utf8 perfiles/equipo_perfil.py recomendar --modelo qwen25
```

**Otro modelo distinto (limitación actual):** el perfil acepta cualquier GGUF. Los laboratorios, en cambio, todavía
solo lanzan modelos de sus registros con huella. Para usar uno nuevo en ellos, añade su entrada (archivo, sha256,
bytes y origen) a `lab_blender/cerebros_extra.json` siguiendo el ejemplo de `gemma12`. En una versión próxima los
laboratorios leerán directamente los modelos registrados con `añadir_modelo`.

## 6. Primera prueba real: revisión de código (~5–10 minutos)

```sh
py -B -X utf8 lab_revision/banco_revision.py preparar evidencias/mi_revision --condiciones herramienta3
py -B -X utf8 eq3/lanzador_eq2.py lab_revision/banco_revision.py ejecutar ../../externos evidencias/mi_revision --modelos qwen25 --perfil_auto
py -B -X utf8 lab_revision/banco_revision.py informe evidencias/mi_revision
```

- `--perfil_auto` calcula para **tu** tarjeta el tope de VRAM, las capas en GPU y la VRAM que pueden usar otros
  programas.
- **Esperar a que el PC esté libre:** sin más opciones, Crisol espera a que nadie use el PC. Si lo estás usando, añade
  `--permitir_uso`; sigue respetando los topes de VRAM y temperatura.
- **Parar:** crea un archivo `STOP` dentro de la carpeta de evidencia. Se para entre dos peticiones y se puede reanudar
  con `--reanudar`.

El caso Java necesita el JDK (paso 7); sin él, esa parte no se puede comprobar.

## 7. Opcionales

- **JDK (laboratorio de revisión en Java):** un JDK 21 portátil (por ejemplo, Eclipse Temurin) descomprimido en
  `externos/jdk_temurin_21/`, o la variable `EQUIPO_JAVAC` con la ruta a `javac`.
- **Blender (laboratorio 3D):** Blender instalado en la ruta por defecto, o la variable `BLENDER_EXE` con la ruta a
  `blender.exe`. El código que escriben los cerebros se ejecuta solo dentro de Blender, con un filtro de seguridad.

## Problemas frecuentes

| Síntoma | Causa probable |
|---|---|
| Se queda esperando «PC libre» | Estás usando el PC, o un programa ocupa VRAM (por ejemplo, la superposición de NVIDIA). Usa `--permitir_uso` o ciérralo |
| «externos no verificados» | Falta un archivo de llama.cpp o no es la versión b12110 exacta |
| Se para por VRAM | Otro programa (un juego, un render) usa la tarjeta mientras hay un modelo cargado |
| `OMITIDO … falta jdk` | Normal sin JDK (paso 7) |

¿Algo no funciona? Abre una incidencia con el comando exacto, el error completo y la salida de
`py -B -X utf8 comprobar_todo.py --json` (ejecútalo desde `crisol/`).
