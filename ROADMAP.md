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

- Status: `done`, all 19 verified audit findings of 2026-09-09 closed (4 high, 8
  medium, 7 low). Detail is in git history and [docs/decisions.md](docs/decisions.md)
- The sidecar change was kept additive: `backend` was added and `model` kept, so
  sidecars written before it still parse

| # | Title | Status | Landed |
|---|---|---|---|
| 0.1 | Retrofit to `ai-product-base`: rules, commit gates, frontmatter, structure lock | `done` | 2026-09-10 |
| 0.2 | Per-backend parameter plumbing, so a control that cannot apply is refused not dropped | `done` | 2026-09-10 |
| 0.3 | Model selector and persistent UI history rebuilt from the files on disk | `done` | 2026-09-15 |
| 0.3.1 | Serial render queue, server-owned across browsers | `done` | 2026-09-16 |
| 0.3.2 | Manifest-driven UI controls: `synth/backends.json` is the source of truth | `done` | 2026-09-16 |
| 0.4 | Harden the runner seam: UTF-8, nested timeouts, process-group cleanup, loud failures | `done` | 2026-09-16 |
| 0.5 | Make `analyze.py` honest: no invented key score, no claimed fades | `done` | 2026-09-16 |
| 0.6 | Docs match the code: locked environments and pinned MiniMax source commit | `done` | 2026-09-16 |

## Phase 1: Output acceptance

- Status: `done`
- Goal: a request is complete only when the resulting file satisfies its declared
  contract. Detail in git history and [docs/decisions.md](docs/decisions.md)

| # | Title | Status | Landed |
|---|---|---|---|
| 1.1 | Audit every delivered WAV; requested and delivered are separate facts | `done` | 2026-09-16 |
| 1.2 | Enforce the MiniMax target during generation, not just after it | `done` | 2026-09-17 |

## Phase 2: Any model, any length

- Status: `in_progress`
- Goal: adding or upgrading a model is a manifest entry plus a runner, a model that
  delivers an exact length is not policed as though it might stop early, and the UI
  tells the truth about what is happening. Detail in git and
  [docs/decisions.md](docs/decisions.md), traps in [docs/gotchas.md](docs/gotchas.md)

| # | Title | Status | Landed |
|---|---|---|---|
| 2.1 | Per-backend duration contract: `best_effort` or `exact` | `done` | 2026-09-19 |
| 2.2 | Per-backend runner options, so a variant costs only a manifest entry | `done` | 2026-09-19 |
| 2.3 | Serve generated audio to the browser (`allowed_paths`) | `done` | 2026-09-19 |
| 2.4 | Stable Audio 3 small and medium, the first exact-length backends | `done` | 2026-09-19 |
| 2.5 | Genre dropdown writing prompts in each backend's own style | `done` | 2026-09-19 |
| 2.6 | Render estimate fitted from measurements; one track plays at a time | `done` | 2026-09-19 |
| 2.7 | Mobile layout no longer scrolls sideways | `done` | 2026-09-19 |
| 2.8 | Queue panel reflects reality (`gr.Timer` inert, `queue=False` blocks renders) | `done` | 2026-09-19 |
| 2.10 | Prompts vary in shape and vocabulary, not just adjectives | `done` | 2026-09-19 |

| 2.9 | Section editing through inpainting | `in_progress` | Stable Audio has no section tokens, so prose is the only pre-generation structure control; regenerating a span of a finished track is the real mechanism, and bars convert to seconds once BPM is known. Core, manifest and runner carry init audio and an inpaint range, refused loudly where unsupported; proven on a real render. A **Rework a section** panel picks a track, tempo, start bar and length. Still to do: one mode visible at a time, uploading an outside track, and exposing the noise level for whole-track remixing | none | 2.8 |

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
