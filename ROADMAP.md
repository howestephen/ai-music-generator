---
status: active
author: stephen+claude
created: 2026-09-10
updated: 2026-09-20
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
- Current phase: Phase 3, the track library
- Biggest known risk: no listening assessment has been done on any output
- Default backend: `stable-audio-medium` (2026-09-19, superseding `minimax-mlx`)

## Phase 0: Retrofit and remediation

- Status: `done` 2026-09-16. All 19 verified audit findings of 2026-09-09 closed (4
  high, 8 medium, 7 low). The retrofit put the house standard, commit gates and
  structure lock in place; per-backend parameter plumbing stopped controls being
  silently dropped; the UI gained a model selector and a persistent, serial,
  manifest-driven render queue; the runner seam was hardened with UTF-8, nested
  timeouts and process-group cleanup; `analyze.py` stopped inventing a key score; and
  the docs were made to match the code. Detail in git and
  [docs/decisions.md](docs/decisions.md)

## Phase 1: Output acceptance

- Status: `done`. A request is complete only when the delivered file satisfies its
  contract: every WAV audited (1.1, 2026-09-16), and MiniMax's target enforced during
  generation rather than only after it (1.2, 2026-09-17)

## Phase 2: Any model, any length

- Status: `done`, signed off 2026-09-20. Adding a model is a manifest entry plus a
  runner; an exact-length model is not policed as though it might stop early; the UI
  tells the truth. Detail in [docs/decisions.md](docs/decisions.md), traps in
  [docs/gotchas.md](docs/gotchas.md)
- Delivered: duration contracts and runner options per backend; audio actually served
  to the browser; Stable Audio 3 as the first exact-length backend and now the default;
  prompts composed from menus across 34 genres with distinct sub-style vocabulary;
  honest render estimates; a mobile layout that does not scroll sideways; a queue panel
  that reflects reality; arrangements laid out in bars; and section editing or
  whole-track remixing of any audio, including uploads

## Phase 3: Track library and generate panel

- Status: `planned`. Spec: [specs/2026-09-20-track-library.md](specs/2026-09-20-track-library.md)
- Owner instruction 2026-09-20: Codex executes this, not Fable or Opus. Handoff:
  [handoffs/2026-09-20-track-library.md](handoffs/2026-09-20-track-library.md)
- Goal: a generation can be named, kept, found and removed. `output/` is flat and
  unbounded, the card buries the genre in a block of text, and Regenerate has drifted
  too far from the prompt to use

| # | Title | Status | Why it matters |
|---|---|---|---|
| 3.1 | Sidecar gains title, rating and genre | `planned` | Nothing identifies a track but its filename. Old sidecars must keep parsing |
| 3.2 | History card leads with title and genre | `planned` | The detail goes behind a disclosure; waveform, seek and playback stay as they are |
| 3.3 | Delete and keep/discard per track | `planned` | Delete hides the track immediately, offers Undo for one hour, then permanently removes the WAV and sidecar. No archive copy |
| 3.4 | Filter by genre, rating and text | `planned` | 31 tracks was already unmanageable. A view concern that must not touch files |
| 3.5 | Regenerate sits next to the prompt | `planned` | You cannot see what you are regenerating. The only visual design question here |
| 3.6 | Dropdowns are clickable across their whole area | `planned` | Only the small arrow responds, so every menu takes several attempts. Gradio's own hit area, so it needs CSS over the component |
| 3.7 | Instruments, character and keywords collapse | `planned` | They are open by default and dominate the panel. They belong behind an Advanced disclosure, closed |
| 3.8 | Decide whether Stable Audio keeps a vocals control | `planned` | Owner reports it appears ignored. Stability document that their models never produce intelligible vocals, only textures, so it may be a control that cannot be honoured. Test before changing it |


## Phase 4: Visual design pass

- Status: `planned`, after Phase 3
- Goal: the UI is functional and plain, and keeps growing. Design it rather than
  letting it accrete

| # | Title | Status | Why it matters |
|---|---|---|---|
| 4.1 | Product design pass on the whole surface | `planned` | Hierarchy, grouping and naming across generate, queue, history and rework. Phone layout is in the brief, not an afterthought |
| 4.2 | Rebuild against that design | `planned` | Gradio constrains layout, so this is custom CSS and JS over its components. Read [docs/gotchas.md](docs/gotchas.md) first: `gr.Timer` never fires here and `@gr.render` will not re-run for a `queue=False` event; a redesign can silently reintroduce both |

## Deferred ideas

- ACE-Step 1.5 as a backend, replacing v1. MIT code and weights, licensed training data,
  10s to 600s, explicit BPM, key, scale and time signature, repaint, cover and
  vocal-to-BGM, with an MLX path. Recommended on 2026-09-19 when the owner asked for
  every good model, then not built. Needs its own venv: `transformers>=4.51,<4.58`
- Route heavy renders to Seneca, the 4090 box. Its ComfyUI already has nodes for
  ACE-Step, ACE-Step 1.5, MiniMax Music 3 and Stable Audio, but no audio checkpoints
  yet. Raised 2026-09-19 after a Mac render fought another agent for the GPU. A
  departure from the local-only premise, so it needs an owner decision

- Runner diagnostics (`device`, `sampling_rate`, `load_seconds`) into the sidecar. Do it
  with the Phase 3 sidecar change or not at all
- Runtime notice on the CC-BY-NC MusicGen backend. Trigger: any output leaving personal
  use
- Research further local music models. Compare Apple Silicon support, licence, duration,
  controllability, genre evidence, runtime and integration cost before proposing any
- Deliver vocals and instruments as separate audio files. Compare the routes rather than
  assuming one: ACE-Step 1.5 lists Track Separation and Vocal2BGM natively (MIT); Demucs
  runs locally on any audio, including tracks already in `output/`; LALAL.AI is installed
  with paid credit, so it costs no install. Whichever wins, a stem is a generated asset
  and needs its own sidecar and audit. Trigger: the first track that needs one
- Vocal-specific synthesis, so a written topline can be sung. SoulX-Singer takes a
  melody as F0 or MIDI plus lyrics rather than a text prompt, so it needs an input
  surface no backend here has. Open: no Apple Silicon build found, and its training-data
  provenance is less clearly stated than Stability's

## Owner decisions open

1. **Whether renders may leave this Mac.** Routing heavy work to Seneca's 4090 departs
   from the project's local-only premise

Resolved: a library Delete removes at once, is restorable for an hour, then is
permanent, with no archived copy (2026-09-20); `stable-audio-medium` is the default
backend (2026-09-19, superseding
`minimax-mlx` of 2026-09-17); `briefs/` stays declared for future prompt sets though
its contents were deleted (2026-09-10); the pinned `.venv-mlx` install command lives
in the README rather than a new top-level file (2026-09-10); UI deletion removes a
track immediately, retains it for one hour for Undo, then permanently removes it with
no archive copy (2026-09-20).

## Current next step

- Current milestone: Phase 2 complete and signed off 2026-09-20. Five backends, 34
  genres, prompts composed from menus, arrangements laid out in bars, and any span of
  any track regeneratable
- Then: Phase 3, the track library, executed by Codex against its spec and handoff
- The honest gap: nobody has listened to any output yet, so no claim in this file is a
  judgement of how anything sounds
- Exit gates for any milestone: unit tests, mutations and validators pass; installed
  model probes pass; a real render is verified by artifact; independent audit is clean
