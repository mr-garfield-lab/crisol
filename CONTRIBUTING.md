# Contributing to Crisol / Cómo participar

Crisol is experimental and evolving. Opinions are as welcome as code.
*Crisol es experimental y está en evolución. Las opiniones valen tanto como el código.*

## Ways to help / Formas de ayudar

1. **Share a hardware measurement / Comparte una medición de tu equipo.** Run
   `py perfiles/equipo_perfil.py informe` (it prints no personal data) and open an issue with the output and the
   speed you got. That turns "ESTIMATED" into "measured". / *Así «ESTIMADO» pasa a «medido».*
2. **Report a bug / Avisa de un fallo:** the exact command, the full error text and the output of
   `py -B -X utf8 comprobar_todo.py --json`.
3. **Propose an idea / Propón una idea** in Discussions.
4. **Send code / Envía código** (see the rules below).

## Rules for code / Reglas para el código

These keep the project honest and safe. *Mantienen el proyecto honesto y seguro.*

- **Measure before you claim / Mide antes de afirmar.** A change that affects a result needs a pre-registration
  (`PRERREGISTRO_*.md`) written **before** running the brains, with its decision rules. Never edit a pre-registration
  after seeing results: if you find a mistake, note it and run a new batch.
- **The verifier has no AI / El verificador no lleva IA.** Pass/fail is decided by deterministic code, never by a model.
- **Safety caps are not optional / Los topes de seguridad no son opcionales.** Do not raise or bypass VRAM, thermal or
  STOP limits. Code written by a brain never runs outside the sandbox.
- **No deletions, work on copies / Nada se borra, se trabaja sobre copias.** Keep a pinned copy of any file whose
  results are already published (`*_t1.py`, …).
- **No personal data / Sin datos personales:** no real logs, paths, user names or saves in commits.
- **No models in the repo / Sin modelos en el repositorio:** users choose and download their own.
- `py -B -X utf8 comprobar_todo.py` must not get worse: no new FALLA.
- Label every result **REAL**, **SIMULATED/SIMULADO**, **SKIPPED/OMITIDO** or **FAILED/FALLIDO**.

## AI assistants / Asistentes de IA

Contributions made with an AI assistant are welcome. The assistant must follow [`AGENTS.md`](AGENTS.md) and you are
responsible for what you submit. *Puedes usar un asistente de IA; tú respondes de lo que envías.*
