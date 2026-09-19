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
- Goal: a request is complete only when the resulting file satisfies its declared contract

| # | Title | Status | Why it matters | Spec | Deps |
|---|---|---|---|---|---|
| 1.1 | Duration and basic audio audit | `done` | MiniMax delivered 16.76 to 33.59 seconds against 240-second requests while the sidecars and UI showed the target as if measured. Every WAV is now audited, requested and delivered are separate facts, and a short asset stays visible but fails acceptance. Re-audited 2026-09-16 | none | 0.4 |
| 1.2 | Enforce MiniMax target duration | `done` | The pinned runtime's duration flag only capped frames and accepted an end token at 16.7 seconds for a 300-second request. Its project-owned wrapper now suppresses that token until the target frame count, while the separate WAV audit still verifies the delivered file. A real render with the known early-stop seed delivered 20.016 seconds for a 20-second target. Completed and independently audited 2026-09-17; 104 unit tests and all 76 mutations pass | none | 1.1 |

## Phase 2: Any model, any length

- Status: `in_progress`
- Goal: adding or upgrading a model is a manifest entry plus a runner, and a model that
  delivers an exact length is not policed as though it might stop early

| # | Title | Status | Why it matters | Spec | Deps |
|---|---|---|---|---|---|
| 2.1 | Per-backend duration contract | `done` | Acceptance assumed every model may stop early, so a fixed-length model was judged by a ratio it cannot miss and an overshoot passed silently. A backend now declares `best_effort` or `exact`. The sample-stream audit still runs everywhere; only the duration policy varies. An exact contract gains an upper bound, and the manifest refuses to pair it with a short-render tolerance or a retry. Landed 2026-09-19 | none | 1.2 |
| 2.2 | Per-backend runner options | `done` | A second variant of one runtime (Stable Audio's small and medium DiTs) differs only in which checkpoint loads, so without this each variant would need its own runner script. `runtime.runner_options` is a string map passed straight to the runner job, refused on a backend that has no runner. Landed 2026-09-19 | none | 2.1 |
| 2.3 | Serve generated audio to the browser | `done` | Gradio serves only declared paths, so every history player received 403 and rendered silence while the server logged nothing and the files on disk were valid. `launch` now allows `output/`. Reported by owner 2026-09-19, fixed the same day | none | - |
| 2.4 | Stable Audio 3 backend (small and medium) | `done` | First model with an exact duration contract, and the first where a second variant costs only a manifest entry. Stability's own pure-MLX runtime, 44.1kHz stereo, licensed training data, commercial use below the revenue threshold. Adds a third prompt style, `description`, because tag and caption prompting both degrade it. Landed 2026-09-19 | none | 2.2 |
| 2.5 | Genre dropdown and model-aware prompts | `done` | 16 genres, each with its own vocabulary and tempo range, replacing five fixed presets. A genre writes a prompt in the selected backend's own style, and Regenerate draws a fresh variation. Stable Audio 3 medium becomes the default. Landed 2026-09-19 | none | 2.4 |
| 2.6 | Honest render estimate and exclusive playback | `done` | Progress read as hung twice: a cold-start weight download was counted as render time, and cost was modelled as a multiple of track length when it is really a fixed overhead plus a small rate, so a 26s render crawled against a 95s estimate. The estimate is now fitted from recent renders of differing lengths, a running card shows elapsed seconds, and starting one history track stops any other. Reported by owner 2026-09-19 | none | 2.5 |
| 2.7 | Mobile layout does not scroll sideways | `done` | Flex children default to `min-width: auto` and refuse to shrink below their content, so a queue card held 301px of header in a 285px box and pushed the page sideways on a phone. Panels and cards may now shrink, the header wraps, and long unbroken prompts and filenames break. Measured at 320, 360, 375 and 390 with a full history: zero overflow. Reported by owner 2026-09-19 | none | 2.6 |

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
