# Installing and trying Crisol

> Crisol is **experimental**. This guide is tested on **Windows 11 with an NVIDIA RTX 3050 8 GB**. On other systems,
> steps 1–3 should work; the rest is not measured yet. *(Versión en español: [INSTALL.es.md](INSTALL.es.md).)*

## 0. Folder layout

External programs are **not** in the repository. Crisol expects them in an `externos` folder next to it:

```
my_folder/
├── crisol/                 ← this repository
└── externos/
    ├── llama_b12110/       ← llama.cpp (step 4)
    ├── modelos/            ← your .gguf models (step 5)
    └── jdk_temurin_21/     ← optional: JDK for the Java lab (step 7)
```

Run commands **from `crisol/equipo_ia_v3/`** unless stated otherwise.

## 1. Python

Install **Python 3.12** (python.org). Crisol uses only the standard library, so there is nothing else to install.
(`tokenizers` is optional; it only improves token counts in Contexto Ligero.)

## 2. Check that everything works (no GPU, no models)

From `crisol/`:

```sh
py -B -X utf8 comprobar_todo.py
```

Expected: no `FALLA`. Anything that needs a missing tool shows as `OMITIDO` (skipped), which is not an error.

## 3. See your hardware and the proposed profile

```sh
py -B -X utf8 perfiles/equipo_perfil.py detectar
py -B -X utf8 perfiles/equipo_perfil.py informe
```

`informe` contains no personal data. You can paste it into any AI assistant or attach it to an issue.

## 4. llama.cpp (the engine that runs the models)

The labs check the SHA-256 of **every** llama.cpp file before starting anything, so you need **exactly** this build:

1. Download from <https://github.com/ggml-org/llama.cpp/releases/tag/b12110>:
   - `llama-b12110-bin-win-cuda-12.4-x64.zip` (SHA-256 `1ce755bc3a061889234048f88e33328e17971eaad73c4666cfeb26026b317fee`)
   - `cudart-llama-bin-win-cuda-12.4-x64.zip` (SHA-256 `8c79a9b226de4b3cacfd1f83d24f962d0773be79f1e7b75c6af4ded7e32ae1d6`)
2. Extract **both** into `externos/llama_b12110/`.

The expected file list is in `eq3/externos_f1.json`. If a file is missing, extra or different, Crisol starts nothing
and tells you which one.

## 5. A model

You choose the model. To repeat the published results, use the same files (download them from their origin; the
hashes are in the registries):

| Alias | File (in `externos/modelos/`) | Origin | Registry with its SHA-256 |
|---|---|---|---|
| `qwen25` | `qwen2.5-coder-7b-instruct-q4_k_m.gguf` | huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct-GGUF | `eq3/externos_f1.json` |
| `ministral3` | `Ministral-3-8B-Instruct-2512-Q4_K_M.gguf` | huggingface.co/mistralai/Ministral-3-8B-Instruct-2512-GGUF | `lab_vram/banco_modelos_extra.json` |
| `gemma12` | `gemma-4-12B-it-qat-UD-Q4_K_XL.gguf` | huggingface.co/unsloth/gemma-4-12B-it-qat-GGUF | `lab_blender/cerebros_extra.json` |

Respect each model's license. Then register it for the profile and see how it fits your hardware:

```sh
py -B -X utf8 perfiles/equipo_perfil.py añadir_modelo ../../externos/modelos/qwen2.5-coder-7b-instruct-q4_k_m.gguf --alias qwen25
py -B -X utf8 perfiles/equipo_perfil.py recomendar --modelo qwen25
```

**Any other model:** register any GGUF with `añadir_modelo` and pass its alias to `--modelos`. The labs check its
SHA-256 and size before starting it, and **always** apply your hardware profile (VRAM cap and GPU layers), because its
limits are not measured. The model must be on the same disk drive as the `externos` folder (simplest: in
`externos/modelos/`). The project's own names (`qwen25`, `ministral3`, `gemma12`) take priority over yours, so use a
different alias.

## 6. First real run: code review (~5–10 minutes)

```sh
py -B -X utf8 lab_revision/banco_revision.py preparar evidencias/my_review --condiciones herramienta3
py -B -X utf8 eq3/lanzador_eq2.py lab_revision/banco_revision.py ejecutar ../../externos evidencias/my_review --modelos qwen25 --perfil_auto
py -B -X utf8 lab_revision/banco_revision.py informe evidencias/my_review
```

- `--perfil_auto` computes the VRAM cap, the GPU layers and the VRAM other programs may use, for **your** card.
- **Waiting for a free PC:** by default Crisol waits until nobody is using the PC. If you are using it, add
  `--permitir_uso`. The VRAM and temperature caps still apply.
- **Stopping:** create a file named `STOP` in the evidence folder. The run stops between two requests, and
  `--reanudar` resumes it.

The Java cases need the JDK (step 7). Without it, that part cannot be checked.

## 7. Optional

- **JDK (Java code-review lab):** a portable JDK 21 (for example, Eclipse Temurin) extracted in
  `externos/jdk_temurin_21/`, or the `EQUIPO_JAVAC` variable pointing to `javac`.
- **Blender (3D lab):** Blender installed in its default location, or the `BLENDER_EXE` variable pointing to
  `blender.exe`. Code written by brains runs only inside Blender, behind a safety filter.

## Common problems

| Symptom | Likely cause |
|---|---|
| Waits for a "free PC" | You are using the PC, or a program holds VRAM (for example, the NVIDIA overlay). Use `--permitir_uso` or close it |
| "externos no verificados" | A llama.cpp file is missing, or the build is not exactly b12110 |
| Stops because of VRAM | Another program (a game, a render) uses the GPU while a model is loaded |
| `OMITIDO … falta jdk` | Normal without the JDK (step 7) |

Something not working? Open an issue with the exact command, the full error and the output of
`py -B -X utf8 comprobar_todo.py --json` (run it from `crisol/`).
