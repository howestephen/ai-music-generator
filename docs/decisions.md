---
status: active
author: stephen+claude
created: 2026-08-15
updated: 2026-09-19
---

# Decisions

Why the stack looks the way it does. Newest first. Each entry records the decision,
rationale and reason to revisit it.

---

## 2026-09-19 - The UI polls from its own JS, through the queue

**Decided:** the queue and history panels refresh by a hidden button that this app's
JavaScript clicks once a second, and every handler feeding a `@gr.render` block runs
through Gradio's queue rather than with `queue=False`.

**Why:** `gr.Timer` does not fire at all in this Gradio build, proved with a Blocks app
containing nothing but a Timer. Separately, `@gr.render` does not re-run for an event
dispatched with `queue=False`, so the panels updated their state and never redrew. Together
these made a completed render look like a crashed one.

**Would revisit if:** a Gradio upgrade makes `gr.Timer` fire, or `@gr.render` gains
re-execution for unqueued events. Both are worth retesting with the throwaway probe rather
than assumed.

---

## 2026-09-19 - Prompting guidance lives in docs/, not the README

**Decided:** per-backend prompt shapes, tags and worked examples moved to
[prompting.md](prompting.md); the README keeps a three-line summary and a link.

**Why:** the README is a visitor-facing overview with a word budget, and it now carries five
backends, three prompt styles and three install procedures. The prompting detail is
reference material consulted while writing a prompt, which is what `docs/` is for.

**Would revisit if:** the backend set shrinks enough that the detail fits back in the README.

## 2026-09-19 - Stable Audio 3 runs on Stability's own MLX runtime

**Decided:** the `stable-audio-sm` and `stable-audio-medium` backends drive Stability's
pure-MLX CLI as a subprocess rather than importing its sampler. The runtime is pinned as a
clone under `~/.cache` and added to `.venv-sa3` on the import path, because it ships as a
source tree rather than a package.

**Why:** the supported entry point is the CLI, and it owns the step that matters to this
project: trimming the delivered WAV to exactly the requested seconds. Reimplementing the
orchestration around its low-level pipeline would duplicate several hundred lines and break
on every upstream change. Both model sizes share one runner and differ only by manifest
`runner_options`.

**Would revisit if:** Stability publishes the MLX runtime as a package, or the CLI stops
exposing seed, steps and CFG as flags.

---

## 2026-09-19 - Prompt style is a third axis, not a binary

**Decided:** `prompt_style` accepts `description` alongside `tags` and `caption`, and every
UI preset carries text for all three.

**Why:** Stable Audio wants a plain natural-language sentence. Feeding it comma-separated
tags or MiniMax's structured caption degrades output, which is the same class of mistake
this project already records for ACE-Step. A test now fails if any preset lacks text for a
style some backend declares, because the UI would otherwise raise on model selection.

**Would revisit if:** a backend appears whose prompting does not fit any of the three.

## 2026-09-17 - MiniMax duration is enforced during autoregressive generation

**Decided:** the MiniMax runner passes the selected duration as both its maximum and its
minimum. A project-owned wrapper masks the model's audio-end token until that minimum frame
count exists, then delegates the rest of generation to the exact pinned MLX package. The
post-generation WAV audit remains the independent acceptance check.

**Why:** a 300-second request reached the pinned runtime correctly but it sampled its end
token after 16.7 seconds. Retrying and rejecting short output made the failure visible but
did not make the requested music. The maintained `appautomaton/mlx-minimax-music3`
implementation independently uses the same stop-token constraint for `min_audio_duration`.

**Would revisit if:** the pinned runtime gains a native minimum-duration option, or
long-duration listening tests show that forcing one pass harms musical quality enough to
justify a separately designed continuation workflow.

---

## 2026-09-17 - MiniMax is the default backend

**Decided:** `minimax-mlx` is the manifest default, so the UI opens with MiniMax selected
and CLI generation uses it when `--model` is omitted.

**Why:** Stephen selected MiniMax as the default for the current generation workflow.

**Would revisit if:** the preferred everyday model changes.

---

## 2026-09-16 - Generated audio must pass a measured output contract

**Decided:** a runner is successful only when the delivered WAV is readable, finite,
non-silent and long enough for that backend's manifest policy. Sidecars store requested and
delivered duration separately with basic audio facts. Short creative assets are retained and
shown as failed rather than deleted or silently accepted.

The UI retries one short result with a fresh seed when the user did not lock the seed. A
fixed seed is never retried automatically because the retry would be deterministic. Backend
thresholds and retry counts live in `synth/backends.json`, alongside the controls they
qualify.

**Why:** MiniMax uses requested duration as a maximum frame budget and may emit its end
token much earlier. Twenty recent MiniMax renders delivered roughly 6% to 36% of their target,
while their old sidecars and UI presented the target as though it were measured output.

**Revisited 2026-09-17:** the runner now enforces the selected minimum during generation;
the output contract remains because enforcement and delivered-file verification are
different boundaries.

---

## 2026-09-16 - Installation follows the real environment split

**Decided:** `.venv` is recreated from the complete `requirements.txt` lock. The separate
`.venv-mlx` uses the exact tested `mlx-minimax-music3` Git commit documented in README,
followed by compatibility checks for both environments.

**Why:** MiniMax cannot share ACE-Step's Transformers version, and a console script from a
moved virtual environment embeds a stale absolute interpreter path. The source pin belongs
beside the two-environment setup rather than in a new top-level manifest.

**Would revisit if:** `uv` gains a single lock that cleanly represents isolated backend
environments without merging their dependency graphs.

---

## 2026-09-16 - Pitch-collection coverage requires an explicit target

**Decided:** `synth.analyze` measures pitch-class collection coverage only when key and
scale are supplied. It cannot distinguish modes sharing the same notes. Otherwise it
reports only the strongest chroma pitch, labelled as a peak rather than a tonic.

**Why:** the previous D Mixolydian target belonged to one finished brief but was presented
as truth for every track. Chroma energy also cannot infer a tonic confidently.

Quiet start/end flags compare edge means with the track median; they do not claim a fade or
sweep. **Would revisit if:** validated tonal or envelope estimation replaces these proxies.

---

## 2026-09-16 - A runner result is a verified contract, not an exit code

**Decided:** every subprocess backend declares import probes and a finite timeout in the
model manifest. A successful call must return valid UTF-8 JSON with the expected path and
a finite elapsed time, and must leave a readable audio file at a fresh path. Timed-out
adapters terminate their whole process group so the model cannot remain on the GPU.

**Why:** exit code zero did not prove that a runner returned usable metadata or wrote any
audio. A stalled subprocess could also hold the serial UI queue forever.

**Would revisit if:** persistent workers add heartbeats and cancellation.

---

## 2026-09-16 - UI controls are backend-owned contracts

**Decided:** model configuration lives in the versioned `synth/backends.json` manifest.
It declares runtime, prompting metadata and numeric controls. The strict loader rejects
unknown fields; core, browser and API use the loaded contract.

**Why:** Gradio inherited ACE-Step's 240-second schema and rejected valid longer MiniMax
requests before the handler ran. The static schema now holds the union; selection narrows
the UI and core enforces the chosen model.

**Would revisit if:** a backend needs another control type or runner contract.

---

## 2026-09-16 - UI generations use one serial worker

**Decided:** the UI accepts reorderable, removable pending jobs but renders serially. The
button is released on acceptance because concurrent Metal jobs ran two to four times slower.

Runners expose no trustworthy callbacks, so active progress is labelled estimated and stays
below 100% until output exists. Queue state is process-wide; history comes from `output/`.
Active cancellation still needs subprocess ownership.

**Would revisit if:** backends expose stable step callbacks, or isolated hardware makes
parallel jobs genuinely faster rather than merely concurrent.

---

## 2026-09-15 - UI history uses generated files as its source of truth

**Decided:** track history is the newest-first view of `output/*.wav` and sidecars, with no
database or browser-only copy.

**Why:** those files already persist results and reproducibility settings. Reusing them also
shows older and CLI-generated tracks without a store that can drift.

**Would revisit if:** the output collection becomes large enough to need pagination,
search or indexed metadata.

---

## 2026-09-10 - Backends declare their knobs; core refuses what it cannot honour

**Decided:** backends declare steps, guidance, lyrics support and dtype. Core applies each
backend's defaults and refuses unsupported values. Sidecars add the CLI's `backend` key,
while retaining the weights ID in `model`.

**Why:** the audit found controls never reached MiniMax, MusicGen used guidance 15, and
sidecars could not reproduce their backend. Loud refusal is safer than recording a setting
that did not apply.

**Kept additive:** old sidecars still parse; new ones carry one extra key.

**Would revisit if:** a backend gains another control or sidecars need schema versioning.

---

## 2026-08-15 - Project scope is open-ended verbal music synthesis

**Decided:** the repo is a workbench for describing music in words and rendering it
locally. Not a single-purpose tool.

**Why:** it began as background music for one video. That brief is finished. The useful
thing that remains is the local synthesis capability, which could serve soundtrack work,
vocal parts and textures for music production, a larger studio system, or artistic
experiments not yet defined.

**Consequence:** keep reasoning recorded and the architecture easy to extend.

---

## 2026-08-15 - MLX build preferred over PyTorch on Apple Silicon

**Decided:** `vanch007/MiniMax-Music3-MLX-8bit` (13 GB) is the MiniMax backend. The 54 GB
fp32 PyTorch build was deleted.

**Why:** MLX targets Metal natively. The fp32 build ran at ~13× realtime, consumed four
times the disk and cost roughly two hours to download and benchmark. Now a standing rule in
[gotchas.md](gotchas.md#check-for-an-mlx-build-before-downloading-anything).

**Would revisit if:** 8-bit quantisation proves audibly worse than fp32, or a model ships
without an MLX conversion.

---

## 2026-08-14 - MiniMax Music 3 added

**Decided:** adopt MiniMax Music 3 as the most capable backend.

**Why:** it uniquely exposes **explicit BPM, key and scale** through Structured Captions.
ACE-Step has no key conditioning. Early pitch measurements are encouraging but are **not
confirmed by listening**.

**Licence:** MiniMax Community. Commercial products must display "MiniMax-Music3" and need
written authorisation above $20M annual revenue from products using it.

**Open:** whether it handles orchestral material any better than ACE-Step. Its published
demos are all song-form genres.

---

## 2026-08-14 - Multi-backend architecture with isolated environments

**Decided:** models are registered in `synth/backends.py`; those with conflicting
dependencies run as subprocesses in their own venv, behind one `core.generate`.

**Why:** ACE-Step pins `transformers==4.50` and MiniMax needs `>=5`; they cannot share an
environment.

**Consequence:** adding a model is a runner script plus a registry entry. Backends declare
their own duration caps, prompt style, instrumental sentinel and licence, so the CLI can
enforce and display them rather than each caller remembering.

---

## 2026-08-14 - MusicGen usable again (non-commercial only)

**Decided:** keep MusicGen available, flagged **CC-BY-NC**.

**Why:** personal experiments can use this capable but slow, 30-second model.

**Revisit if:** output is ever destined for commercial use - the licence blocks it.

---

## 2026-08-11 - ACE-Step chosen, and why that was partly wrong

**Decided:** ACE-Step v1 3.5B as the original backend.

**Why at the time:** Apache-2.0, multi-minute output and commercial safety.

**What was wrong:** the choice weighed licence and track length but **never checked genre
competence**, and the brief's central requirement was orchestral. ACE-Step is a song-form
model; asked for cinematic orchestral it produced rock guitars. Two days of output were
unusable.

**Lesson:** verify the target genre in published demos before adopting on specs and licence.

**Still useful for:** its actual strengths, near-realtime generation of song-form and
loop-based material.

---

## 2026-08-11 - Custom Python rather than ComfyUI

**Decided:** a thin Python project calling models directly, no ComfyUI.

**Why:** music generation here is mostly prompt in, audio out. A node graph adds a large
dependency surface on the least-tested Apple Silicon path.

**Would revisit if:** work needs genuine multi-model chaining (stem separation → transform →
recombine), where a graph earns its complexity.

---

## 2026-08-11 - JSON sidecar per generated track

**Decided:** every WAV gets a `.json` recording prompt, seed, model and settings.

**Why:** it makes a useful track reproducible and adjustable.

**Held up well.** Cheap, and the thing that makes iteration possible.
