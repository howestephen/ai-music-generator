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
- Biggest known risk: the runner seam is still soft (0.4): a runner can exit 0 having
  written nothing, hang forever, or emit malformed JSON, and the caller cannot tell
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
| 0.3.1 | Serial UI render queue | `done` | Submissions now become reorderable and removable pending cards immediately, while one background worker renders at a time. The button is released as soon as the queue accepts a job; the active card shows a clearly labelled estimate because current runners expose start and finish but no trustworthy step callbacks. Implemented on `codex/ui-generation-queue` | none | 0.3 |
| 0.4 | Harden the runner seam | `in_progress` | Unguarded `json.loads`; no check that the runner wrote the file; no duration lower bound; `available` does not verify that the MiniMax module imports; no subprocess timeout; subprocess text not decoded as UTF-8 explicitly. First slice landed 2026-09-15: the MiniMax runner invokes its module with the current environment's Python, avoiding stale absolute paths in console scripts after a repository move | none | 0.2 |
| 0.5 | Make `analyze.py` honest | `planned` | Hardcoded to D Mixolydian from a finished brief, so every other track gets a confident, meaningless scale score; one bad file aborts the whole run; NaN `intro_swell` on short clips is swallowed by a blanket warnings filter | none | 0.1 |
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

- Current milestone: finish 0.4, harden the runner seam
- Then: 0.5 and 0.6 in either order; 0.6 depends on 0.2, which has landed
- Expected validation: `scripts/validate.py --index` clean, retrofit checker clean,
  unit tests pass, independent audit clean
