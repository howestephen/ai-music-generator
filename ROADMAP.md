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

- Goal: describe music in words, render it locally on Apple Silicon, and keep adding
  models cheap
- Current phase: Phase 1.2 complete; next direction pending owner review
- Biggest known risk: no listening assessment has been done on any output
- Default backend: `minimax-mlx` (owner decision, resolved 2026-09-17)

## Phase 0: Retrofit and remediation

- Status: `done`. All 19 verified audit findings of 2026-09-09 closed (4 high, 8
  medium, 7 low); detail in git and [docs/decisions.md](docs/decisions.md). The
  sidecar change was additive, so older sidecars still parse

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

- Status: `done`. A request is complete only when the delivered file satisfies its
  contract: every WAV audited (1.1, 2026-09-16), and MiniMax's target enforced during
  generation rather than only after it (1.2, 2026-09-17)

## Phase 2: Any model, any length

- Status: `done`
- Goal: adding a model is a manifest entry plus a runner, an exact-length model is not
  policed as though it might stop early, and the UI tells the truth. Detail in
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
| 2.11 | Menus compose the prompt; lyrics only where a backend can sing | `done` | 2026-09-19 |
| 2.12 | Structure builder: bars per section, described to the model | `done` | 2026-09-20 |
| 2.13 | Genres split into sub-styles; 34 genres with distinct vocabulary | `done` | 2026-09-20 |
| 2.9 | Section editing and whole-track remixing through inpainting | `done` | 2026-09-20 |


## Phase 3: Track library and generate panel

- Status: `planned`. Spec: [specs/2026-09-20-track-library.md](specs/2026-09-20-track-library.md)
- Owner instruction 2026-09-20: Codex executes this, not Fable or Opus
- Goal: a generation can be named, kept, found and removed. `output/` is flat and
  unbounded, the card buries the genre in a block of text, and Regenerate has drifted
  too far from the prompt to use

| # | Title | Status | Why it matters |
|---|---|---|---|
| 3.1 | Sidecar gains title, rating and genre | `planned` | Nothing identifies a track but its filename. Old sidecars must keep parsing |
| 3.2 | History card leads with title and genre | `planned` | The detail goes behind a disclosure; waveform, seek and playback stay as they are |
| 3.3 | Delete and keep/discard per track | `planned` | **Blocked on an owner decision:** `CLAUDE.md` says generated audio is never deleted, but a generation is treated as disposable in practice |
| 3.4 | Filter by genre, rating and text | `planned` | 31 tracks was already unmanageable. A view concern that must not touch files |
| 3.5 | Regenerate sits next to the prompt | `planned` | You cannot see what you are regenerating. The only visual design question here |

## Phase 4: Visual design pass

- Status: `planned`, after Phase 3
- Goal: the UI is functional and plain, and keeps growing. Design it rather than
  letting it accrete

| # | Title | Status | Why it matters |
|---|---|---|---|
| 4.1 | Product design pass on the whole surface | `planned` | Hierarchy, grouping and naming across generate, queue, history and rework. Phone layout is in the brief, not an afterthought |
| 4.2 | Rebuild against that design | `planned` | Gradio constrains layout, so this is custom CSS and JS over its components. Read [docs/gotchas.md](docs/gotchas.md) first: `gr.Timer` never fires here and `@gr.render` will not re-run for a `queue=False` event; a redesign can silently reintroduce both |

## Deferred ideas

- Runner diagnostics (`device`, `sampling_rate`, `load_seconds`) into the sidecar.
  Why deferred: a second sidecar format change. Trigger: a track whose device is in doubt
- Runtime notice on the CC-BY-NC MusicGen backend. Why deferred: the licence is already
  stated in the registry, README and decisions. Trigger: any output leaving personal use
- Research further local music models. Compare Apple Silicon support, licence, duration,
  controllability, genre evidence, runtime and integration cost before proposing any
- Deliver vocals and instruments as separate audio files. Compare the routes rather than
  assuming one: ACE-Step 1.5 lists Track Separation and Vocal2BGM natively (MIT); Demucs
  runs locally on any audio, including tracks already in `output/`; LALAL.AI is installed
  with paid credit, so it costs no install. Whichever wins, a stem is a generated asset
  and needs its own sidecar and audit. Trigger: the first track that needs one
- Vocal-specific synthesis, so a written topline can be sung. SoulX-Singer (Feb 2026,
  zero-shot) takes a melody as F0 or MIDI plus lyrics rather than a text prompt, so it
  needs an input surface no backend here has. Open questions: no Apple Silicon build was
  found, and its training-data provenance is less clearly stated than Stability's.
  Trigger: wanting to sing a melody written in Ableton

## Owner decisions open

1. Resolved 2026-09-17: `minimax-mlx` is the default backend on Stephen's instruction
2. Resolved 2026-09-10: the finished client brief`briefs/` was deleted on
   Stephen's instruction; `briefs/` stays declared for future prompt sets
3. Resolved 2026-09-10: no new top-level file at this level; the pinned `.venv-mlx`
   install command goes in the README (milestone 0.6)

## Current next step

- Current milestone: Phase 2 complete and signed off 2026-09-20. Five backends, 34
  genres, prompts composed from menus, arrangements laid out in bars, and any span of
  any track regeneratable
- Then: Phase 3, the track library, executed by Codex against its spec
- Not started, and the honest gap: nobody has listened to any output yet
- Phase 1.2 exit gates: the runner passes one target as both minimum and maximum; a real
  render reaches its requested duration; unit tests, mutations and validators pass;
  installed model probes pass; independent audit is clean
