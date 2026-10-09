---
status: active
author: stephen+claude
created: 2026-09-10
updated: 2026-10-09
---

# ROADMAP

Living execution map. High-signal only: the full envelope for a milestone lives in
its spec under `specs/` once one exists. Owner decisions are listed at the bottom so
they are never buried in a chat.

## Status legend

`planned` · `in_progress` · `blocked` · `done` · `deferred`

## Project summary

- Goal: a local home UI for music generation, singing, sound design, transcription
  and production tools, with device-aware execution on Apple Silicon and NVIDIA
- Current phase: Phase 5, music-module suite expansion
- Biggest known risk: the owner is not happy with the output yet
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

- Status: `done`, merged to main on 2026-09-23. Spec:
  [specs/2026-09-20-track-library.md](specs/2026-09-20-track-library.md)
- Handoff: [handoffs/2026-09-20-track-library.md](handoffs/2026-09-20-track-library.md)
- Goal: a generation can be named, kept, found and removed. `output/` is flat and
  unbounded, the card buries the genre in a block of text, and Regenerate has drifted
  too far from the prompt to use

| # | Title | Status | Why it matters |
|---|---|---|---|
| 3.1 | Sidecar gains title, rating and genre | `done` | Nothing identifies a track but its filename. Old sidecars must keep parsing |
| 3.2 | History card leads with title and genre | `done` | The detail goes behind a disclosure; waveform, seek and playback stay as they are |
| 3.3 | Delete and keep/discard per track | `done` | Delete hides the track immediately, offers Undo for one hour, then permanently removes the WAV and sidecar. No archive copy |
| 3.4 | Filter by genre, rating and text | `done` | 31 tracks was already unmanageable. A view concern that must not touch files |
| 3.5 | Regenerate sits next to the prompt | `done` | You cannot see what you are regenerating. The only visual design question here |
| 3.6 | Dropdowns are clickable across their whole area | `done` | Only the small arrow responds, so every menu takes several attempts. Gradio's own hit area, so it needs CSS over the component |
| 3.7 | Instruments, character and keywords collapse | `done` | They are open by default and dominate the panel. They belong behind an Advanced disclosure, closed |
| 3.8 | Decide whether Stable Audio keeps a vocals control | `done` | Relabelled to Vocal texture on backends without a lyrics channel; kept as With vocals where lyrics exist |


## Phase 4: React and Tailwind UI

- Status: `done` 2026-09-24, for review. `python app.py` serves `web/dist`
- Goal: replace the Gradio page with React and Tailwind. Do not skin Gradio

| # | Title | Status | Why it matters |
|---|---|---|---|
| 4.1 | Product design pass on the whole surface | `done` | Generate, queue, history and remix. Phone layout is one column. Menus are native selects |
| 4.2 | Build that design in React and Tailwind | `done` | Queue, history and audio serving stay. Audio is read from `output/` by filename. The old Gradio builder is still in `app.py` and is not launched |

## Phase 5: Music-module suite

- Status: `in_progress`. Spec: [specs/2026-10-09-music-module-suite.md](specs/2026-10-09-music-module-suite.md)
- Priority: install and integrate suitable tools, not packaging. A source or import
  probe is not a completed integration; each tool needs an installed end-to-end job.

| # | Work | Status | Acceptance |
|---|---|---|---|
| 5.1 | Stable Audio sound effects | `in_progress` | Separate checkpoint, direct prompt UI, audited WAV and existing library actions |
| 5.2 | Shared device preferences and fallbacks | `planned` | Per-tool supported routes, health checks, visible actual device; fallback only before dispatch |
| 5.3 | YuE2 and HeartMuLa song generation | `planned` | Efficient MLX variants first; licences recorded; full lyric-to-audio jobs |
| 5.4 | Audio-to-MIDI and lyric transcription | `planned` | Basic Pitch, GAME and HeartTranscriptor assessed; playable source and downloadable MIDI/text artefacts |
| 5.5 | More score singing and voice tools | `planned` | DiffSinger with a separately cleared voicebank; SAM Audio subject to model access |
| 5.6 | Expose existing runtime capabilities | `planned` | ACE-Step cover/repaint; Stable Audio negative prompts and compatible LoRA controls |
| 5.7 | Remaining candidate decisions | `planned` | SongGeneration/LeVo2 licence evidence, MusicFlamingo restrictions, Seed-VC maintenance assessment |

Device preference means an initial supported route, not a speed claim. Compare
real timings only if needed and authorised. Never silently substitute another model,
drop a control, or retry a dispatched failed generation on another machine.

## Phase 6: Downloadable studio

- Status: `planned`, owner direction 2026-10-09. Other people should be able to
  download and use the app. This follows the immediate suite work.
- Tool-selection/download screen: capability, licence and consent, hardware support,
  disk requirements, install progress, version/pin, repair and uninstall actions.
- Portable setup: hardware detection, isolated runtimes, optional remote worker,
  resumable downloads, clear unsupported-device errors and no bundled private paths.
- Distribution gates: clean-machine installation, licence/redistribution review,
  model-specific notices, signed releases and update/rollback design.

## Deferred ideas

- ACE-Step 1.5 replaced v1 on 2026-09-27: MLX turbo plus the 0.6B planner, 10s to
  600s, in `.venv-ace`. Cover, repaint and vocal-to-BGM stay in the upstream runtime
  and are not connected here. XL is a manifest change if a render needs it
- ACE-Step 1.5 generate routes to Seneca's 4090 when ComfyUI answers on
  port 8000 over Tailscale. The installed weights are the turbo DiT, the 0.6B
  and 4B text encoders, and the 1.5 VAE. Stable Audio nodes are present and
  the weights are not, so Stable Audio stays on this Mac. MiniMax Music 3
  weights are on the box and are not routed. SoulX and Demucs stay on this Mac

- Runner diagnostics (`device`, `sampling_rate`, `load_seconds`) into the sidecar. Do it
  with the Phase 3 sidecar change or not at all
- Runtime notice on the CC-BY-NC MusicGen backend. Trigger: any output leaving personal
  use
- Prompt shapes per model are in [docs/prompting.md](docs/prompting.md), updated
  2026-09-30. Stable Audio's full upstream guide is already copied. ACE-Step's
  musician guide describes modes this app does not connect, so it is not copied
  as the working guide
- Research further local music models. Compare Apple Silicon support, licence, duration,
  controllability, genre evidence, runtime and integration cost before proposing any
- Stem separation shipped 2026-09-28 as HTDemucs on MLX (`demucs`). A mix becomes
  vocals, drums, bass and other, each with its own sidecar. ACE-Step extract is
  base-model only and generative, so it was not the separator. LALAL.AI was left unused
- A sung line shipped 2026-09-28 as SoulX-Singer (`soulx`). English words, one
  pitched note per word, in the English example voice. The Sing tab writes
  that score from a scale or a short pattern. SoulX does not invent a tune
  from the lyric. SoulX-Singer SVC (`soulx-svc`, 2026.03) is the other Sing
  model: it follows a recording, in the example voice or a voice you upload

## Owner decisions open

None.

Resolved: a broader local suite and later downloadable app are the destination
(2026-10-09). Device-aware preferences and fallbacks will supersede the current
ACE-Step-only remote routing once verified. Currently ACE-Step generate uses
Seneca's 4090 when ComfyUI answers, and every other model stays on this Mac
(2026-09-30), superseding the 2026-09-24 choice
to keep all renders here; the next UI is React and Tailwind, not a Gradio skin (2026-09-24);
Stable Audio's voice control is a texture and the owner has heard it add occasional
vague voice noises (2026-09-24); a library Delete removes at once, is restorable for
an hour, then is permanent, with no archived copy (2026-09-20); `stable-audio-medium` is the default
backend (2026-09-19, superseding
`minimax-mlx` of 2026-09-17); `briefs/` stays declared for future prompt sets though
its contents were deleted (2026-09-10); the pinned `.venv-mlx` install command lives
in the README rather than a new top-level file (2026-09-10); UI deletion removes a
track immediately, retains it for one hour for Undo, then permanently removes it with
no archive copy (2026-09-20).

## Current next step

- 2026-10-08: Advanced seed and each card's saved prompt/seed restored. Same-name
  deletion collisions fixed, with visible Delete/Restore errors and crash-safe Undo.
  New titles use random words; collision suffixes are visible and Trash names reserved.
  All 258 tests, nine targeted mutations, frontend build and eight backend probes pass.
  Desktop fixture checks cover Separate dispatch, colliding Delete, Undo and conflict
  errors. Full mutation run and audio rendering were not performed. Vocal texture's
  menu-to-prompt connection remains unresolved; Regenerate includes it.

- 2026-10-08: track Download moved into the shared action row with Remix,
  Separate and Delete. The native player download option is hidden where supported.
  All 249 tests, the targeted Download mutation, frontend build and validators
  pass. The live app serves the rebuilt assets. No browser viewport measurement,
  real download click, full mutation run or audio generation was performed here.

- Current milestone: audit repairs merged and pushed to main at `609532c`.
  Repairs cover working-input ownership, deletion retries and unattended expiry,
  restored lyrics, silent stems, SoulX seed application and remote runtime metadata.
  The removed rating controls remain a design decision; no new controls are added.
- Verified for that merge: 244 unit tests, 104/104 mutations, eight installed backend probes,
  frontend build, validators and clean independent re-audit.
- Continuing audit: single audio byte-range repair on `fix/audio-byte-ranges`.
  Suffix requests now read from EOF and oversized ends clip to the file length.
  Large decimal numerals are bounded before conversion. Four new playback mutations
  caught by the served-HTTP suite; all 246 tests pass after restoration and re-audit is
  clean. Eight installed backend probes, frontend build and validators pass.
  The previous 104 mutations were not rerun here; a full-suite mutation attempt
  stalled in the unrelated legacy Gradio configuration probe and was stopped.
- Drawer repair on `fix/queued-library-scroll`: queue and library share the scrolling
  body so long queues cannot consume the track viewport. All 246 tests, the new
  targeted scrolling mutation, eight import probes, frontend build and validators
  pass. Browser scrolling measurements await a per-action hook approval; source
  and built CSS were checked, but no mobile or desktop browser measurement is claimed.
  Sing's apparent end-of-render stall was first-use weight downloading,
  not UI publication. After downloading, that job failed on missing NLTK English
  tagger data. Installed the missing resource into the singing environment and
  verified the failed lyric's six words against the real G2p and SoulX phone set.
  README now installs all pronunciation resources and checks a real G2p call.
  Full singing retry remains unverified: the public failed-job summary does not
  retain the melody needed to repeat the original request exactly.
- Subsequent score-singing retry reached the reference-audio mel encoder and
  failed on PyTorch's unsupported MPS FFT. The score runner now enables CPU
  fallback before PyTorch imports. The installed FFT and SoulX mel encoder
  passed on MPS with finite output; that operation check left singing output unverified.
  All 247 unit tests pass outside the sandbox, the new targeted fallback
  mutation is caught, validators pass and independent audit found no blocker.
  The full mutation suite was not rerun for this repair.
- Complete-render follow-up: MPS fallback did not catch the vocoder's complex
  arithmetic assertion. Move only the nested final waveform head and its input
  to CPU after the final model MPS move; leave backbone and diffusion on MPS.
  Live API diagnostics at 1s and 5.25s completed, published in library state,
  passed finite/non-silent/duration audits and served 1,024-byte HTTP 206 audio
  ranges. All 248 tests pass, three new targeted mutations are caught, and the
  installed bridge wiring has an independent clean audit. The full mutation
  suite, browser playback/listening and voice conversion were not checked.
  These were diagnostic lyrics and notes, not an exact retry of the owner's melody.
- Next: browser verification of the drawer repair, then owner review of both
  unmerged repair branches. No additional render, listening test or live remote
  graph is planned for this checkpoint.
- The honest gap: the owner has heard Stable Audio's vocal texture (occasional vague
  voice noises) and is not happy with the output. Nothing else in this file is a
  judgement of how a track sounds
- Exit gates for any milestone: unit tests, mutations and validators pass; installed
  model probes pass; a real render is verified by artifact; independent audit is clean
