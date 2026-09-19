---
status: active
author: stephen+claude
created: 2026-09-10
updated: 2026-09-19
---

# ROADMAP

Living execution map. High-signal only: the full envelope for a milestone lives in
its spec under `specs/` once one exists. Owner decisions are listed at the bottom so
they are never buried in a chat.

## Status legend

`planned` · `in_progress` · `blocked` · `done` · `deferred`

## Project summary

- Goal: describe music in words, render it locally on Apple Silicon, and keep the
  architecture easy to add models to
- Current phase: Phase 1.2 complete; next direction pending owner review
- Biggest known risk: forced long MiniMax renders still need listening assessment for
  musical structure and quality across the full duration
- Default backend: `minimax-mlx` (owner decision, resolved 2026-09-17)

## Phase 0: Retrofit and remediation

- Status: `done`
- Goals: the house standard in place and enforced; the 2026-09-09 audit findings
  closed (19 verified: 4 high, 8 medium, 7 low)
- Risks: fixing the parameter seam changes the sidecar format. Kept additive: a
  `backend` key is added and `model` (the weights id) is kept, so old sidecars parse

| # | Title | Status | Why it matters | Spec | Deps |
|---|---|---|---|---|---|
| 0.1 | Retrofit to `ai-product-base` | `done` | Rules, commit gates, frontmatter and the structure lock. Nothing else is enforced until this lands | none | - |
| 0.2 | Per-backend parameter plumbing | `done` | `--steps` and `--guidance` never reached `minimax-mlx`, MusicGen always got guidance 15 instead of its own 3, `--lyrics` was a silent no-op there, and the sidecar's `dtype` and `model` were wrong for MLX, so the README reproduction command failed. Landed 2026-09-10 | none | 0.1 |
| 0.3 | Model selector and persistent UI history | `done` | The UI was locked to ACE-Step and replaced the visible result after every generation. It now selects any registered backend, adapts controls and presets to that backend, and rebuilds a newest-first playable history from the existing WAV files and sidecars. Landed 2026-09-15. Button-level generation progress followed, then the balanced history and fitted waveforms. UI helpers are covered in `synth/tests.py` | none | 0.2 |
| 0.3.1 | Serial UI render queue | `done` | Submissions become reorderable and removable pending cards immediately while one worker renders at a time. The button is released once queued; the active card shows a labelled estimate because runners expose only start and finish. Queue and history state is server-owned across browsers. A process-wide lock guarantees concurrent first access creates one worker. Independently re-audited 2026-09-16 | none | 0.3 |
| 0.3.2 | Manifest-driven UI controls | `done` | `synth/backends.json` became the versioned source of truth for runtime, controls, licence and prompting metadata. Gradio's static schema accepts the union of the contracts; selecting a model narrows the visible controls, and core enforces that backend. A new subprocess model is one manifest entry plus a JSON runner adapter. Completed 2026-09-16; covers the original 270-second failure | none | 0.3.1 |
| 0.4 | Harden the runner seam | `done` | Probes import the modules each backend really invokes. Subprocesses use explicit UTF-8, finite nested timeouts and process-group cleanup, so no orphaned GPU child survives. Malformed JSON, an unexpected or existing path, invalid timing and unreadable audio all fail loudly. Completed 2026-09-16 | none | 0.2 |
| 0.5 | Make `analyze.py` honest | `done` | Optional pitch-class coverage replaces the hardcoded D Mixolydian score and cannot separate modes sharing notes. Strongest chroma is a peak, not a tonic. Quiet edges no longer claim a fade. Silent or non-finite measurements stay unscored, warnings stay visible, and one bad file fails the run without aborting it. Completed 2026-09-16 | none | 0.1 |
| 0.6 | Docs match the code | `done` | README now recreates the locked main environment and pins the isolated MiniMax package to the tested source commit. Environment checks and model probes are documented. Gotchas now describe the actual MLX package conversion boundary and name each XET setting. Completed and independently re-audited 2026-09-16 | none | 0.2 |

## Phase 1: Output acceptance

- Status: `done`
- Goal: a request is complete only when the resulting file satisfies its declared contract

| # | Title | Status | Why it matters | Spec | Deps |
|---|---|---|---|---|---|
| 1.1 | Duration and basic audio audit | `done` | MiniMax accepted 16.76–33.59 second files for 240-second requests and 41.56 seconds for a 300-second request, while sidecars and the UI displayed the target as measured. Every WAV is now audited; requested and delivered facts are separate; short assets remain visible but fail acceptance; an unlocked UI seed retries once. Completed and independently re-audited 2026-09-16 | none | 0.4 |
| 1.2 | Enforce MiniMax target duration | `done` | The pinned runtime's duration flag only capped frames and accepted an end token at 16.7 seconds for a 300-second request. Its project-owned wrapper now suppresses that token until the target frame count, while the separate WAV audit still verifies the delivered file. A real render with the known early-stop seed delivered 20.016 seconds for a 20-second target. Completed and independently audited 2026-09-17; 104 unit tests and all 76 mutations pass | none | 1.1 |

## Phase 2: Any model, any length

- Status: `in_progress`
- Goal: adding or upgrading a model is a manifest entry plus a runner, and a model that
  delivers an exact length is not policed as though it might stop early

| # | Title | Status | Why it matters | Spec | Deps |
|---|---|---|---|---|---|
| 2.1 | Per-backend duration contract | `done` | Acceptance assumed every model may stop early, so a fixed-length model was judged by a ratio it cannot miss and an overshoot passed silently. A backend now declares `best_effort` or `exact`. The sample-stream audit still runs everywhere; only the duration policy varies. An exact contract gains an upper bound, and the manifest refuses to pair it with a short-render tolerance or a retry. Landed 2026-09-19 | none | 1.2 |
| 2.2 | Per-backend runner options | `done` | A second variant of one runtime (Stable Audio's small and medium DiTs) differs only in which checkpoint loads, so without this each variant would need its own runner script. `runtime.runner_options` is a string map passed straight to the runner job, refused on a backend that has no runner. Landed 2026-09-19 | none | 2.1 |

## Deferred ideas

- Runner diagnostics (`device`, `sampling_rate`, `load_seconds`) into the sidecar.
  Why deferred: a second sidecar format change; do it with 0.2 or not at all.
  Trigger: a track whose device is in doubt
- Runtime notice when generating with the CC-BY-NC MusicGen backend. Why deferred:
  the licence is already stated in the registry, README and decisions. Trigger: any
  output leaving personal use
- Research current local music models and alternative generation architectures. Compare
  Apple Silicon support, licence, duration, controllability, genre evidence, runtime and
  integration cost before proposing additions. Trigger: after Phase 0 owner review

## Owner decisions open

1. Resolved 2026-09-17: `minimax-mlx` is the default backend on Stephen's instruction
2. Resolved 2026-09-10: the finished client brief`briefs/` was deleted on
   Stephen's instruction; `briefs/` stays declared for future prompt sets
3. Resolved 2026-09-10: no new top-level file at this level; the pinned `.venv-mlx`
   install command goes in the README (milestone 0.6)

## Current next step

- Current milestone: Phase 2, expanding the model set on owner instruction (2026-09-19):
  update models that have newer versions and add good ones the project lacks
- Then: Stable Audio 3 and ACE-Step 1.5 as backends
- Phase 1.2 exit gates: the runner passes one target as both minimum and maximum; a real
  render reaches its requested duration; unit tests, mutations and validators pass;
  installed model probes pass; independent audit is clean
