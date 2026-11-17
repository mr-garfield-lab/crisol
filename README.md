# Crisol

**A local lab to put AI "brains" to the test on your own PC — and to use them safely.**

> **Status: experimental and still evolving.** Crisol is a research project in active development. Interfaces, results and
> folder layout will change. Everything below says whether it was **measured** or is only **estimated**.

Crisol (Spanish for *crucible*: where metal is melted and tested) runs small open models locally with
[llama.cpp](https://github.com/ggml-org/llama.cpp) and measures what they can really do. A deterministic verifier with no
AI in it decides pass/fail, and decision rules are written down **before** any brain is asked (pre-registration).

## What it does today

| Area | What it measures | Status |
|---|---|---|
| Team core (roles A1/A2/A3) | Propose, cross-check and vote, with memory and controlled tools | Working; one model can play all three roles |
| Code review lab | Brains fix Python/Java compile errors, checked by real compilers | Measured: best brain fixed 24/24, broke 0 correct files |
| Large-project lab | Find and use facts in a codebase much larger than the context | Measured: 21–22/24 on real code |
| Blender lab | Brains design 3D scenes; a verifier measures them in Blender | Measured: the largest robot task passed 82/82 with one brain |
| Hardware profiles | Detects your hardware and proposes layers, context and safety caps | Working; checked against real llama.cpp logs |
| Game diagnostics lab | Reads game logs (Project Zomboid, RimWorld, HOI4) to find mod and performance problems | **Experimental, in testing — not included in the first release** |

## How many brains?

Your choice: **1, 2 or 3**. The core has three roles (A1, A2, A3) and was designed so **one model can play all three**
(it warns when they start agreeing with themselves). The labs accept any list of models. Assigning a different model
to each core role is planned for a future version. More roles may come later.

## You choose the models

Crisol **does not ship or impose any model.** You download the GGUF models you want (respecting their licenses) and
register them:

```sh
py perfiles/equipo_perfil.py añadir_modelo path/to/model.gguf --alias mymodel
py perfiles/equipo_perfil.py recomendar --modelo mymodel
```

The profile tells you how many layers fit on your GPU, which context you can use and which caps apply. Results are
marked **measured** or **ESTIMATED**. You can override them; the VRAM cap is never exceeded.

## Hardware

**Measured on:** AMD Ryzen 5 5600GT, 32 GB RAM, NVIDIA RTX 3050 8 GB, Windows 11, context 4096.

| Brain (Q4) | Fits in 8 GB? | Speed measured |
|---|---|---|
| Qwen2.5-Coder 7B | fully | ~40 tokens/s |
| Ministral 3 8B | fully | ~35 tokens/s |
| Gemma 4 12B QAT | partly (39 of 48 layers) | ~15 tokens/s |

**Other hardware (ESTIMATED, not measured):**

| Your hardware | What to expect |
|---|---|
| No GPU / < 4 GB VRAM | Small models on the CPU, short context, slow |
| 6–8 GB | Like the measured PC |
| 12 GB | 12B models fully on the GPU, roughly twice as fast |
| 16 GB+ | Higher-quality quantizations, longer context, or two brains loaded |

Safety limits **adapt to your hardware**. The VRAM cap is derived from your card's memory, and the thermal brakes come
from the limits your GPU driver reports. Nothing is copied from the PC where Crisol was developed. Only NVIDIA GPUs are
detected today; AMD, Intel and Apple are not measured yet.

If you run Crisol on other hardware, please share your profile (`py perfiles/equipo_perfil.py informe` prints it with
no personal data). That is how "estimated" becomes "measured".

## Works with your own AI assistant

Every tool can print JSON (`--json`), and `informe` produces a hardware report **without paths, user name or computer
name**. You can paste it into any assistant (Claude, Gemini, ChatGPT…) and ask for help. Assistants working on the code
should read [`AGENTS.md`](AGENTS.md).

## Safety principles

- Code written by brains runs **only inside a closed sandbox** (today: the Blender lab), never on your system.
- Nothing is deleted. Changes happen on copies, and every action is logged.
- Hard VRAM and temperature caps; a `STOP` file halts any run.
- No paid APIs and no telemetry: everything stays on your PC.

## Install and quick check

Step-by-step guide: **[INSTALL.md](INSTALL.md)**. The quick check needs no GPU and no models (run it from the
repository folder):

```sh
py -B -X utf8 comprobar_todo.py
```

## Roadmap (no dates promised)

- Assign a different model to each core role; teams larger than three.
- Game diagnostics lab out of testing.
- AMD/Intel GPUs, multi-GPU and Android/Termux measured for real.
- One-command install.

## Contributing

Opinions, bug reports and hardware measurements are very welcome. Open an issue or a discussion. The project's own
documentation is mostly in Spanish; English issues are fine.

## License

[MIT](LICENSE) © 2026 MR. Garfield. Models, llama.cpp, Blender and the JDK are **not** included and keep their own
licenses.
