---
status: active
author: stephen+claude
created: 2026-08-15
updated: 2026-09-10
---

# CLAUDE.md - working rules for this repo

## 0. One rules file

`CLAUDE.md` (this file) is the only rules file for every agent: Claude, Codex or
anything else. `AGENTS.md` is a pointer here and never carries rules of its own.
House rules apply underneath; where they differ, this file wins. Retrofitted to
`ai-product-base` on 2026-09-10 (kit commit `55b8711`).

## What this project is

A workbench for **verbal music synthesis** - describing music in words, rendering it
locally on Apple Silicon. Used for both work and personal music-making.

The destination is deliberately open: soundtrack work, vocal parts and textures for music
production, the engine under a larger studio tool, or artistic concepts not yet defined.
Stephen makes music, so output may feed a real production workflow rather than being an end
in itself.

**Because the outcome is unfixed, organisation matters more than any single feature.**
Keep the architecture easy to add models to. Write decisions down. Record traps.

## Autonomy

House defaults, with this project's tightening:

- Default branch is `main`, never `master`
- Commit without asking: yes
- Push without asking: yes on a branch, never on main. There is no remote yet; the
  moment one exists, feature branches push immediately as backup
- Create new top-level folders: no. The structure is declared below and locked by
  `scripts/validate.config.json`
- Delete files: never without listing what changes and what references it.
  Generated audio is a creative asset: archive it, never delete it
- One subagent at a time, never at your own tier or above; for the independent
  audit, or when Stephen asks for delegation

## Read in this order

1. This file, in full
2. [ROADMAP.md](ROADMAP.md): the current milestone and the next step
3. [docs/gotchas.md](docs/gotchas.md): before installing a model or debugging a failure
4. [docs/decisions.md](docs/decisions.md): why the stack looks the way it does
5. [README.md](README.md): usage, prompting, environments
6. The current milestone's spec in `specs/`, if one exists
7. The latest work item in `handoffs/`, if resuming someone else's work

## Structure

Every top-level directory is declared here and in `top_dirs` of
`scripts/validate.config.json`; a commit adding an undeclared one is refused.

| Path | Holds |
|---|---|
| `synth/` | the package: `core.py` (generate), `backends.py` (registry), `cli.py`, `analyze.py` |
| `runners/` | per-backend subprocess entry points, one per isolated venv |
| `briefs/` | prompt sets per project |
| `prompts/` | default batch prompts |
| `output/` | generated audio and sidecars, gitignored |
| `docs/` | `decisions.md` and `gotchas.md`; a new doc here uses a lowercase-dash name |
| `specs/` | milestone specs, named `YYYY-MM-DD-topic.md` |
| `handoffs/` | cross-tool work items, `YYYY-MM-DD-topic.md`, from `handoffs/TEMPLATE.md` |
| `scripts/` | `validate.py` (gate shim), `bootstrap.sh`, `validate.config.json` |
| `_archive/` | superseded material, moved not deleted, with references updated |

Markdown files carry `status` and `author` frontmatter. A new top-level markdown
file goes in the config allowlist in the same commit. Wanting a new file is nearly
always a routing failure.

## Do what was asked. Nothing else.

This is a hard rule, not a preference.

When Stephen asks for something specific, do **that**. Do not widen it, do not add adjacent
work you think would help, and do not substitute your judgement for the instruction. If you
think the request is wrong or incomplete, **say so in a sentence and ask** - do not quietly
do something different.

## Do not invent requirements

Never add creative or technical direction that was not asked for.

Real examples from this project, all of which wasted hours:

- Asked for a **Hans Zimmer style, medieval, orchestral** track. Added "hybrid orchestral
  electronic", "pulsing synth bass" and "corporate" on the theory that a blockchain product
  "wanted a modern edge" - then recommended that invented direction as the top pick. None of
  it was requested. Both additions were actively wrong.
- Asked to **install a model**. Instead downloaded a 54 GB fp32 build, ran unrequested GPU
  benchmarks and control experiments, and generated test audio nobody asked for - while the
  efficient 13 GB MLX build had already been found and was described as a "future
  optimisation".

If a brief says X, the deliverable is X. Additions are not initiative, they are noise.

## Do not run unrequested work

No benchmarks, control experiments, comparison batches or "while I'm here" tests unless
asked. They cost GPU time and Stephen's attention. Do what was asked, confirm it works,
and stop.

## Record decisions and gotchas

This is part of the job, not overhead.

- **[docs/decisions.md](docs/decisions.md)** - when a meaningful choice is made (model,
  architecture, dependency), add an entry: what was decided, why, and what would change it.
  Newest first. Include decisions that turned out badly and why.
- **[docs/gotchas.md](docs/gotchas.md)** - when something costs real time to diagnose,
  record the symptom, the cause and the fix. **Read this before installing a model or
  debugging a failure.**

Nothing gets paid for twice. A trap not written down will be hit again.

## Check for the right build before installing

Before downloading any model, check what variants exist and pick the one that fits this
machine (Apple Silicon, M3 Max). **Search HuggingFace for `<model> MLX` first** - MLX is
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
measures everything except whether something sounds good - a model producing rock guitars
over a drum loop scores perfectly on all of it.

**Never present measurements as quality judgements.** Use `synth/analyze.py` to verify
specific measurable claims ("did the requested key land?"), never to decide whether
something is good. Generate a small number of options, send them, and ask. One clip and a
question beats eight clips and a confident table.

## Ask instead of guessing

When something is ambiguous, ask a short question. A blocked minute is cheaper than an hour
of confidently wrong work.

## Working loop

inspect, plan, implement, adversarial tests, validate, fix, independent adversarial
audit by a separate agent (findings fixed and re-audited), docs updated in existing
files, roadmap updated, commit, report. Atomic commits: two pieces of work is two
commits. Stop at the milestone for Stephen's review.

Validation for this project:

- `./.venv/bin/python -m synth.cli models` lists every backend as `ok`
- `./.venv/bin/python -m unittest discover -s synth -t .` runs the unit tests in
  `synth/tests.py`; the runner seam is stubbed there, so no model loads. Exit 5 (no
  tests discovered) is not a pass
- `./.venv/bin/python scripts/mutate.py` proves the tests bite: every listed
  mutation must fail the suite
- `python3.13 scripts/validate.py` on the working tree, then `--index` on what is
  staged, before every commit. The commit hook enforces frontmatter, the allowlist,
  the structure lock, word budgets, no em-dashes and no secrets. An agent never
  bypasses it
- Never generate audio as a test unless the task is about generation

Report: what changed, what ran, what did not run and why, docs updated, risks.

## Handoffs and archiving

Work passing between tools or sessions goes in `handoffs/YYYY-MM-DD-topic.md`, copied
from [handoffs/TEMPLATE.md](handoffs/TEMPLATE.md): `owner` is whose turn it is; the
receiver acts on the file alone, writes back, flips `owner`, bumps `round`; round 3
escalates to Stephen. Superseded documents move to `_archive/`, references updated;
a live document never links into the archive.
