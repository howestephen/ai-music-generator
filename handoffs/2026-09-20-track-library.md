---
status: active
author: stephen+claude
type: handoff
task: Build Phase 3, the track library and generate panel, against its spec
owner: codex
state: needs-work
round: 1
created: 2026-09-20
updated: 2026-09-20
generated_by: claude-opus-5
generated_at: 2026-09-20T15:40Z
generated_from: conversation
---

# Track library and generate panel

Cross-tool work item. The two tools never talk directly: they read and write THIS
file. Whoever is `owner` acts, writes back, flips `owner`, and increments `round`.
At round 3, escalate to Stephen with both positions rather than looping.

## Context

A local workbench for describing music in words and rendering it on Apple Silicon.
Five backends behind one CLI and one Gradio UI. Stephen owns it. Layer zero, so work
goes straight to `main`, no feature branches for small changes.

Read in this order before touching anything: `CLAUDE.md`, `ROADMAP.md`,
`docs/gotchas.md`, `docs/decisions.md`, then the spec at
[specs/2026-09-20-track-library.md](../specs/2026-09-20-track-library.md). The spec is
the work. This file is only the state around it.

Where things stand: Phases 0 to 2 are done and signed off. The app generates, queues,
audits, and can rework any span of any track. What it cannot do is help you live with
the results: a generation cannot be named, kept, rated, found or removed.

## Done

- Spec written and agreed, covering 3.1 to 3.8
- Roadmap restructured: Phase 3 is this work, Phase 4 is the visual design pass
- Documentation audited by a separate agent on 2026-09-20 and the findings fixed
- 177 unit tests pass; `scripts/mutate.py` catches every listed mutation

## Outstanding

All of the spec. Nothing in Phase 3 has been started.

Two things shape it:

1. **Delete is settled.** Remove the track from the library immediately, retain its WAV
   and sidecar together for a one-hour Undo, then permanently delete both. Do not make
   or keep an archive copy. Purge expired pending deletions on app startup as well.
2. **3.8 is a question, not a task.** Test whether the Stable Audio vocals control
   changes the output at all before changing any wording. It may be a control the
   model cannot honour.

## Acceptance

The spec's own "Done when" list, plus the project's standing gates:

- `./.venv/bin/python -m synth.cli models` lists every backend as `ok`
- `./.venv/bin/python -m unittest discover -s synth -t .` passes
- `./.venv/bin/python scripts/mutate.py` catches every mutation, with a new one added
  for each new rule
- `python3.13 scripts/validate.py` reports 0 errors, and no file this work touches is
  pushed over its word budget
- A real render is verified by artifact, not by assertion
- `ROADMAP.md` and `docs/decisions.md` updated in the same change as the code

## Traps

`docs/gotchas.md` has the full list. The three that will bite this work specifically:

- `gr.Timer` never fires in this Gradio build. Polling is driven by the app's own JS
  clicking a hidden button. Do not replace it with a Timer.
- `@gr.render` does not re-run for an event dispatched with `queue=False`. Every
  handler writing to a component feeding a render block must go through the queue. A
  test already fails if one does not.
- `gr.Audio` copies its file into Gradio's temp cache on every render. History audio is
  a plain `<audio>` element served from `output/`. Keep it that way.

Rebuilding the history cards is exactly the change that reintroduces all three.

## Log

- 2026-09-20 claude: Phase 2 closed. Spec written for Phase 3 and handed to Codex on
  Stephen's instruction. Documentation audited and corrected. One code fix went with
  the audit: `core.generate` and the CLI both hardcoded a 60-second duration, so the
  per-backend defaults added earlier only ever applied to the UI slider; both now defer
  to the manifest. Owner decision on delete-versus-archive still outstanding.
- 2026-09-20 codex: Owner settled deletion. A deleted track leaves the library
  immediately, remains recoverable through Undo for one hour, then its WAV and sidecar
  are permanently removed. No archive copy is kept.
