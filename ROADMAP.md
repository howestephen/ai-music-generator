---
status: active
author: stephen+claude
created: 2026-09-10
updated: 2026-09-10
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
- Biggest known risk: `core.generate` is the one seam that knows about per-backend
  differences and applies them inconsistently, so CLI flags are silently dropped and
  sidecars record settings that never applied
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
| 0.1 | Retrofit to `ai-product-base` | `in_progress` | Rules, commit gates, frontmatter and the structure lock. Nothing else is enforced until this lands | none | - |
| 0.2 | Per-backend parameter plumbing | `planned` | `--steps` and `--guidance` never reach `minimax-mlx`; MusicGen always gets guidance 15 instead of its own 3; `--lyrics` is a silent no-op on MusicGen; sidecar `dtype` is wrong for MLX and its `model` field cannot be fed back to `-m`, so the README reproduction command fails. Rewrite exists in a git stash dated 2026-09-10 with 18 passing tests | none | 0.1 |
| 0.3 | Harden the runner seam | `planned` | Unguarded `json.loads`; no check that the runner wrote the file; no duration lower bound; `available` ignores the `mlx-minimax-music3` binary; no subprocess timeout; subprocess text not decoded as UTF-8 explicitly | none | 0.2 |
| 0.4 | Make `analyze.py` honest | `planned` | Hardcoded to D Mixolydian from a finished brief, so every other track gets a confident, meaningless scale score; one bad file aborts the whole run; NaN `intro_swell` on short clips is swallowed by a blanket warnings filter | none | 0.1 |
| 0.5 | Docs match the code | `planned` | README has no install section though `core.py` sends users there; gotchas cite numpy handling the mlx runner does not contain and claim the XET flag is set in every runner; `.venv-mlx` has no manifest anywhere | none | 0.2 |

## Deferred ideas

- Runner diagnostics (`device`, `sampling_rate`, `load_seconds`) into the sidecar.
  Why deferred: a second sidecar format change; do it with 0.2 or not at all.
  Trigger: a track whose device is in doubt
- Runtime notice when generating with the CC-BY-NC MusicGen backend. Why deferred:
  the licence is already stated in the registry, README and decisions. Trigger: any
  output leaving personal use
- Backend selector in the Gradio UI. Why deferred: the UI now reads its model facts
  from the registry, which closes the licence-mismatch risk. Trigger: the UI is used
  for anything but the default backend

## Owner decisions open

1. Default backend: `acestep` stays until Stephen has listened to `minimax-mlx` on
   the same brief. Nothing in the code can settle this
2. the client brief option D is the invented-scope prompt that
   `CLAUDE.md` cites as a hard lesson, and its rerun directory duplicates the same finished
   brief. Archive or consolidate: Stephen's call
3. Whether `.venv-mlx` gets its own requirements file (a new top-level file) or the
   pinned install command in the README is enough

## Current next step

- Smallest next milestone: 0.1, finish the retrofit and have it audited
- Then: 0.2, apply the stashed parameter-plumbing work, test, audit, commit
- Expected validation: `scripts/validate.py --index` clean, retrofit checker clean,
  unit tests pass, independent audit clean
