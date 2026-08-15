# Decisions

Why the stack looks the way it does. Newest first. Each entry records what was decided,
why, and what would change it — so a future decision can be revisited on evidence rather
than re-argued from scratch.

---

## 2026-08-15 — Project scope is open-ended verbal music synthesis

**Decided:** the repo is a workbench for describing music in words and rendering it
locally. Not a single-purpose tool.

**Why:** it began as background music for one video. That brief is finished. The useful
thing that remains is the local synthesis capability, which could serve soundtrack work,
vocal parts and textures for music production, a larger studio system, or artistic
experiments not yet defined.

**Consequence:** because the destination is unfixed, organisation and recorded reasoning
matter more than any feature. Decisions and gotchas get written down. Architecture stays
easy to add models to rather than optimised for one workflow.

---

## 2026-08-15 — MLX build preferred over PyTorch on Apple Silicon

**Decided:** `vanch007/MiniMax-Music3-MLX-8bit` (13 GB) is the MiniMax backend. The 54 GB
fp32 PyTorch build was deleted.

**Why:** MLX targets Metal natively. The fp32 build ran at ~13× realtime and consumed four
times the disk for no benefit on this hardware.

**Cost of getting this wrong:** the MLX build was found in the *first* search and treated as
a future optimisation while the inefficient build was downloaded, run and benchmarked.
Roughly two hours and 54 GB wasted. Now a standing rule in
[gotchas.md](gotchas.md#check-for-an-mlx-build-before-downloading-anything).

**Would revisit if:** 8-bit quantisation proves audibly worse than fp32, or a model ships
without an MLX conversion.

---

## 2026-08-14 — MiniMax Music 3 added

**Decided:** adopt MiniMax Music 3 as the most capable backend.

**Why:** ~11B parameters, and uniquely it exposes **explicit BPM, key and scale** control
through its Structured Caption format. Earlier requests for a specific mode (D Mixolydian)
were impossible on ACE-Step, which has no key conditioning. First measurements are
encouraging — flat-7 energy ratio 2.7× versus ACE-Step's 0.7–1.0× — but this is **not yet
confirmed by listening**.

**Licence:** MiniMax Community. Commercial use permitted, with two conditions that matter
only if this becomes commercial: display "MiniMax-Music3" on a commercial product's UI, and
obtain written authorisation above $20M revenue from products using it. Not a constraint
for personal or experimental work.

**Open:** whether it handles orchestral material any better than ACE-Step. Its published
demos are all song-form genres.

---

## 2026-08-14 — Multi-backend architecture with isolated environments

**Decided:** models are registered in `synth/backends.py`; those with conflicting
dependencies run as subprocesses in their own venv, behind one `core.generate`.

**Why:** ACE-Step pins `transformers==4.50` and MiniMax needs `>=5`. Unifying them is
impossible, and picking one model per repo defeats the purpose of a workbench.

**Consequence:** adding a model is a runner script plus a registry entry. Backends declare
their own duration caps, prompt style, instrumental sentinel and licence, so the CLI can
enforce and display them rather than each caller remembering.

---

## 2026-08-14 — MusicGen usable again (non-commercial only)

**Decided:** keep MusicGen available, flagged **CC-BY-NC**.

**Why:** it was originally excluded because its non-commercial weights were unusable for a
commercial video. With the project now personal and experimental, that constraint doesn't
apply. It's slow on Metal (~15× realtime) and capped at 30s, but it's a strong instrumental
model.

**Revisit if:** output is ever destined for commercial use — the licence blocks it.

---

## 2026-08-11 — ACE-Step chosen, and why that was partly wrong

**Decided:** ACE-Step v1 3.5B as the original backend.

**Why at the time:** Apache-2.0 (commercially safe), multi-minute output where Stable Audio
Open caps near 47s, and MusicGen's CC-BY-NC ruled it out for commercial work.

**What was wrong:** the choice weighed licence and track length but **never checked genre
competence**, and the brief's central requirement was orchestral. ACE-Step is a song-form
model; asked for cinematic orchestral it produced rock guitars. Two days of output were
unusable.

**Lesson, now standing:** verify a model handles the *target genre* — check its published
demos — before adopting it on licence and specs.

**Still useful for:** its actual strengths, near-realtime generation of song-form and
loop-based material.

---

## 2026-08-11 — Custom Python rather than ComfyUI

**Decided:** a thin Python project calling models directly, no ComfyUI.

**Why:** ComfyUI's value is composing many models in a node graph, which is an image-gen
problem. Music generation is mostly single-shot — prompt in, audio out — so the graph buys
little, while adding a large dependency surface on the least-tested Apple Silicon path.

**Held up well.** The subprocess-per-backend design later proved essential for dependency
isolation, which would have been harder inside ComfyUI.

**Would revisit if:** work needs genuine multi-model chaining (stem separation → transform →
recombine), where a graph earns its complexity.

---

## 2026-08-11 — JSON sidecar per generated track

**Decided:** every WAV gets a `.json` recording prompt, seed, model and settings.

**Why:** without it the tool is a slot machine. With it, a track you like can be reproduced
and adjusted one parameter at a time.

**Held up well.** Cheap, and the thing that makes iteration possible.
