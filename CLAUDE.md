# Working rules for this repo

## What this project is

A workbench for **verbal music synthesis** — describing music in words, rendering it
locally on Apple Silicon. Used for both work and personal music-making.

The destination is deliberately open: soundtrack work, vocal parts and textures for music
production, the engine under a larger studio tool, or artistic concepts not yet defined.
Stephen makes music, so output may feed a real production workflow rather than being an end
in itself.

**Because the outcome is unfixed, organisation matters more than any single feature.**
Keep the architecture easy to add models to. Write decisions down. Record traps.

## Do what was asked. Nothing else.

This is a hard rule, not a preference.

When Stephen asks for something specific, do **that**. Do not widen it, do not add adjacent
work you think would help, and do not substitute your judgement for the instruction. If you
think the request is wrong or incomplete, **say so in a sentence and ask** — do not quietly
do something different.

## Do not invent requirements

Never add creative or technical direction that was not asked for.

Real examples from this project, all of which wasted hours:

- Asked for a **Hans Zimmer style, medieval, orchestral** track. Added "hybrid orchestral
  electronic", "pulsing synth bass" and "corporate" on the theory that a blockchain product
  "wanted a modern edge" — then recommended that invented direction as the top pick. None of
  it was requested. Both additions were actively wrong.
- Asked to **install a model**. Instead downloaded a 54 GB fp32 build, ran unrequested GPU
  benchmarks and control experiments, and generated test audio nobody asked for — while the
  efficient 13 GB MLX build had already been found and was described as a "future
  optimisation".

If a brief says X, the deliverable is X. Additions are not initiative, they are noise.

## Do not run unrequested work

No benchmarks, control experiments, comparison batches or "while I'm here" tests unless
asked. They cost GPU time and Stephen's attention. Do what was asked, confirm it works,
and stop.

## Record decisions and gotchas

This is part of the job, not overhead.

- **[docs/decisions.md](docs/decisions.md)** — when a meaningful choice is made (model,
  architecture, dependency), add an entry: what was decided, why, and what would change it.
  Newest first. Include decisions that turned out badly and why.
- **[docs/gotchas.md](docs/gotchas.md)** — when something costs real time to diagnose,
  record the symptom, the cause and the fix. **Read this before installing a model or
  debugging a failure.**

The point is that nothing gets paid for twice. A trap not written down will be hit again.

## Check for the right build before installing

Before downloading any model, check what variants exist and pick the one that fits this
machine (Apple Silicon, M3 Max). **Search HuggingFace for `<model> MLX` first** — MLX is
Metal-native and far faster than PyTorch/MPS, and community conversions often appear within
days of release.

Never download a large inefficient build and describe the efficient one as a possible later
optimisation. That is the wrong order and has already happened once.

## Verify genre competence before adopting a model

Most open music models are trained on song-form pop material and are weak elsewhere. Check
that the target genre appears in a model's published demos before adopting it on licence
and specifications. ACE-Step was chosen for its licence and track length and produced rock
guitars for an orchestral brief.

## Claude cannot hear audio

Claude has no way to perceive generated audio. Numerical analysis (tempo, chroma, onsets)
measures everything except whether something sounds good — a model producing rock guitars
over a drum loop scores perfectly on all of it.

**Never present measurements as quality judgements.** Use `synth/analyze.py` to verify
specific measurable claims ("did the requested key land?"), never to decide whether
something is good. Generate a small number of options, send them, and ask. One clip and a
question beats eight clips and a confident table.

## Ask instead of guessing

When something is ambiguous, ask a short question. A blocked minute is cheaper than an hour
of confidently wrong work.
