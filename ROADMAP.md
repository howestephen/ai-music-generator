---
status: active
author: stephen+claude
created: 2026-09-10
updated: 2026-09-16
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
- Current phase: 0, retrofit and audit remediation
- Biggest known risk: installed environments are not yet reproducible from the README
- Default backend: `acestep`, pending a listening test against `minimax-mlx`
  (owner decision, open since 2026-08-14)

## Phase 0: Retrofit and remediation

- Status: `in_progress`
- Goals: the house standard in place and enforced; the 2026-09-09 audit findings
  closed (19 verified: 4 high, 8 medium, 7 low)
- Risks: fixing the parameter seam changes the sidecar format. Kept additive: a
  `backend` key is added and `model` (the weights id) is kept, so old sidecars parse

| # | Title | Status | Why it matters | Spec | Deps |
|---|---|---|---|---|---|
| 0.1 | Retrofit to `ai-product-base` | `done` | Rules, commit gates, frontmatter and the structure lock. Nothing else is enforced until this lands | none | - |
| 0.2 | Per-backend parameter plumbing | `done` | `--steps` and `--guidance` never reach `minimax-mlx`; MusicGen always gets guidance 15 instead of its own 3; `--lyrics` is a silent no-op on MusicGen; sidecar `dtype` is wrong for MLX and its `model` field cannot be fed back to `-m`, so the README reproduction command fails. Landed 2026-09-10 on `fix/backend-parameter-plumbing`: tests in `synth/tests.py`; `./.venv/bin/python scripts/mutate.py` reruns every listed mutation; each must fail the suite | none | 0.1 |
| 0.3 | Model selector and persistent UI history | `done` | The UI was locked to ACE-Step and replaced the visible result after every generation. It now selects any registered backend, adapts controls and presets to that backend, and rebuilds a newest-first playable history from the existing WAV files and sidecars. Landed 2026-09-15 on `codex/ui-model-history`. Button-level generation progress followed on `codex/ui-generate-progress`; the balanced history and fitted waveforms followed on `codex/ui-balanced-history-progress`. UI helpers are covered in `synth/tests.py` | none | 0.2 |
| 0.3.1 | Serial UI render queue | `done` | Submissions now become reorderable and removable pending cards immediately, while one background worker renders at a time. The button is released as soon as the queue accepts a job; the active card shows a clearly labelled estimate because current runners expose start and finish but no trustworthy step callbacks. Queue and history rendering now read their authoritative state from the local server, so separate browsers stay aligned. Implemented on `codex/ui-generation-queue` | none | 0.3 |
| 0.3.2 | Manifest-driven UI controls | `done` | `synth/backends.json` is the versioned source of truth for model runtime, controls, licence and prompting metadata. Gradio's static schema accepts the union of its contracts; model selection narrows visible controls; the API handler and core enforce the selected backend. MiniMax reaches 300 seconds, ACE-Step remains at 240 and MusicGen at 30. Unsupported controls are hidden. A new subprocess model needs one manifest entry and its JSON runner adapter, then appears automatically in the CLI and UI. Completed 2026-09-16 on `codex/ui-generation-queue`; 58 unit tests, 33 mutations and a manual fake-queue endpoint smoke test cover the original 270-second failure | none | 0.3.1 |
| 0.4 | Harden the runner seam | `done` | Manifest probes import the modules each backend actually invokes. Subprocesses use explicit UTF-8 and finite nested timeouts; process-group cleanup prevents an orphaned GPU child. Malformed final JSON, an unexpected path, invalid timing, an existing path and unreadable or empty audio all fail loudly. Collision-safe names prevent same-second overwrites. Duration minimums come from each model contract. Completed 2026-09-16 on `codex/ui-generation-queue` | none | 0.2 |
| 0.5 | Make `analyze.py` honest | `done` | Optional pitch-class collection coverage replaces the hardcoded D Mixolydian score and cannot distinguish modes sharing notes. Strongest chroma is a peak, not a tonic. Quiet edge flags do not claim a sweep or fade, and short edge windows never become empty. Silent or non-finite tonal and onset measurements stay unscored; no eligible hit boundary displays `--`; warnings remain visible; one bad file does not abort the batch but returns failure. Completed 2026-09-16 on `codex/ui-generation-queue` | none | 0.1 |
| 0.6 | Docs match the code | `planned` | README has no install section though `core.py` sends users there; gotchas cite numpy handling the mlx runner does not contain and claim the XET flag is set in every runner; `.venv-mlx` has no manifest anywhere | none | 0.2 |

## Deferred ideas

- Runner diagnostics (`device`, `sampling_rate`, `load_seconds`) into the sidecar.
  Why deferred: a second sidecar format change; do it with 0.2 or not at all.
  Trigger: a track whose device is in doubt
- Runtime notice when generating with the CC-BY-NC MusicGen backend. Why deferred:
  the licence is already stated in the registry, README and decisions. Trigger: any
  output leaving personal use
## Owner decisions open

1. Default backend: `acestep` stays until Stephen has listened to `minimax-mlx` on
   the same brief. Nothing in the code can settle this
2. Resolved 2026-09-10: the finished client brief`briefs/` was deleted on
   Stephen's instruction; `briefs/` stays declared for future prompt sets
3. Resolved 2026-09-10: no new top-level file at this level; the pinned `.venv-mlx`
   install command goes in the README (milestone 0.5)

## Current next step

- Current milestone: 0.6, reconcile installation and documentation
- Then: close Phase 0 and record the next research phase
- Expected validation: `scripts/validate.py --index` clean, retrofit checker clean,
  unit tests pass, independent audit clean
