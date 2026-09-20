---
status: active
author: stephen+claude
created: 2026-09-20
updated: 2026-09-20
generated_by: claude-opus-5
generated_at: 2026-09-20T14:08Z
generated_from: conversation
---

# Track library and generate panel

Milestone 3. Written to be executed without the conversation that produced it.

## Why

`output/` is a flat, unbounded folder and the UI only lists it. A track cannot be
deleted, kept, named or found. On 2026-09-20 all 31 tracks were deleted by hand
because most were the wrong length and there was no way to sort the good from the
bad. The history card prints its metadata as one block of text, so the genre, which
is the thing you actually look for, is buried in it.

The generate panel has the same problem from growth: **Regenerate** now sits far
enough from the prompt that you cannot see what you are regenerating.

## What exists now

- `output/NAME.wav` plus `NAME.json`, written by `core.Track.write_sidecar`
- `app._load_history` rebuilds the list from disk on every change, newest first
- `app._history_copy` renders the metadata line, `_history_waveform` the SVG
- Tracks are served straight from `output/`, not copied (`launch(allowed_paths=...)`)
- There is no rating, name, tag or delete anywhere in the codebase

## Scope

### 3.1 Sidecar gains a name, a rating and a genre

`core.Track` gains three fields, written by every new render:

| Field | Type | Meaning |
|---|---|---|
| `title` | `str` | A short generated name, two to four words |
| `rating` | `str \| None` | `None`, `"keep"` or `"discard"` |
| `genre` | `str \| None` | The genre selected in the UI, if one was |

Constraints:

- **Old sidecars must keep parsing.** Sidecars written before milestone 1.1 already
  lack fields and are handled by reading the WAV directly; do the same here. A
  missing `title` falls back to the prompt's first few words, a missing `rating` to
  `None`, a missing `genre` to `None`. No migration script, no rewriting old files.
- `title` is generated from the prompt and genre, not asked for. It is a label, not
  a creative act: a deterministic function of prompt, genre and seed so the same
  render always gets the same name. Put it in `synth/prompting.py` beside the other
  language, with its own tests.
- `genre` must come from the UI selection rather than being parsed back out of the
  prompt, which would be guesswork.

### 3.2 History card is readable

Each card shows, in this order:

1. The generated **title**, prominent
2. The **genre** and duration, secondary
3. The waveform and player, as now
4. Everything else (prompt, seed, model, audit status, sample rate, timings) behind
   a closed disclosure

Keep the existing waveform, seek behaviour and exclusive playback untouched.

### 3.3 Manage a track

Per card: **Delete**, and a keep/discard toggle.

- Delete removes the track from the library immediately and moves its WAV and sidecar
  together into an app-owned pending-deletion area. Do not copy or archive either file.
- Show **Undo delete** for one hour. Undo restores the same pair to the library. Once
  the hour expires, permanently remove both files. Expired pending deletions are also
  purged when the app next starts, so closing the app does not preserve them forever.
- Keep/discard is a label only. It never deletes anything on its own.

### 3.4 Find a track

Above the history: filter by genre, filter by rating, and a text search across title
and prompt. Filtering is a view concern only and must not touch files.

With no tracks matching, say so rather than rendering an empty list.

### 3.5 Generate panel reorganised

**Regenerate** sits next to the prompt it regenerates. Group the controls so the
prompt and the things that write it are together, and the render settings
(duration, steps, guidance, seed) are separate from them.

This is the only part of this milestone with a visual design question in it. The
rest is mechanical.

### 3.6 Dropdowns are clickable across their whole area

Every dropdown currently only responds when the small arrow itself is hit, so choosing
a model, genre or mood takes several attempts. This is Gradio's own hit area, so the
fix is CSS over its component, in `UI_CSS` in `app.py`, not a change to the component.

Verify by clicking the label text and the middle of the control, not just the arrow.

### 3.7 Advanced controls collapse by default

**Instruments**, **Character** and **Extra keywords** are open by default and dominate
the generate panel. Move them inside a closed `gr.Accordion` labelled Advanced. Genre,
tempo, mood and voice stay visible.

The **Structure (bars)** accordion already behaves this way; match it.

### 3.8 Decide whether Stable Audio keeps a vocals control

The owner reports that selecting **With vocals** appears to do nothing on Stable Audio.
Stability's own guide states their models never produce intelligible vocals, only
unintelligible vocal textures, so this may be a control that cannot be honoured.

Do not rephrase the prompt and hope. Test first: render the same seed and prompt with
the control on and off and compare. Then either relabel it so it promises only what the
model does, or remove it for backends with no lyrics channel. A control that cannot
change the output is the fault milestone 0.2 already had to fix once.

MiniMax and ACE-Step do have a lyrics channel and are unaffected.

## Traps that will bite

Read [docs/gotchas.md](../docs/gotchas.md) first. The three that specifically apply:

- **`gr.Timer` never fires in this Gradio build.** Polling is driven by this app's
  own JS clicking a hidden button. Do not replace it with a Timer.
- **`@gr.render` does not re-run for an event dispatched with `queue=False`.** Every
  handler writing to a component that feeds a render block must go through the
  queue. A test already fails if one does not; do not weaken it.
- **`gr.Audio` copies its file into Gradio's temp cache on every render.** History
  audio is a plain `<audio>` element served from `output/`. Keep it that way.

## Done when

- A new render writes `title`, `rating` and `genre`; an old sidecar still loads
- The card leads with title and genre, with the detail collapsed
- Keep/discard persists across a restart
- Filtering by genre, rating and text works and touches no files
- Regenerate is adjacent to the prompt
- Delete disappears immediately, Undo restores it for one hour, and expiry permanently
  removes the WAV and sidecar without leaving an archive copy
- Dropdowns respond anywhere on the control, not only on the arrow
- Instruments, character and keywords sit behind a closed Advanced disclosure
- The Stable Audio vocals control is tested, then relabelled, removed or kept on the
  evidence
- Unit tests cover the sidecar fallback, the title generator and the filters, and
  `scripts/mutate.py` gains a mutation for each new rule

## Not in scope

Stem separation, vocal synthesis, and the wider visual design pass. Those are
separate roadmap entries.
