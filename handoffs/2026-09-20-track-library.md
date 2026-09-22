---
status: active
author: stephen+claude
type: handoff
task: Build Phase 3, the track library and generate panel, against its spec
owner: stephen
state: needs-review
round: 2
created: 2026-09-20
updated: 2026-09-22
generated_by: cursor-composer
generated_at: 2026-09-22T16:40Z
generated_from: conversation
---

# Track library and generate panel

Cross-tool work item. The two tools never talk directly: they read and write THIS
file. Whoever is `owner` acts, writes back, flips `owner`, and increments `round`.
At round 3, escalate to Stephen with both positions rather than looping.

## Context

A local workbench for describing music in words and rendering it on Apple Silicon.
Five backends behind one CLI and one Gradio UI. Stephen owns it. Phase 3 work is on
branch `phase-3-track-library`.

Read in this order before touching anything: `CLAUDE.md`, `ROADMAP.md`,
`docs/gotchas.md`, `docs/decisions.md`, then the spec at
[specs/2026-09-20-track-library.md](../specs/2026-09-20-track-library.md). The spec is
the work. This file is only the state around it.

## Done

- Spec written and agreed, covering 3.1 to 3.8
- Roadmap restructured: Phase 3 is this work, Phase 4 is the visual design pass
- Documentation audited by a separate agent on 2026-09-20 and the findings fixed
- 3.1 Sidecar writes `title`, `rating`, `genre`; old sidecars still load
- 3.2 History card leads with title and genre; detail behind a closed disclosure
- 3.3 Delete moves WAV+sidecar to `output/.pending-delete/` for one-hour Undo, then
  purges; keep/discard persists on the sidecar
- 3.4 Genre, rating and text filters are view-only
- 3.5 Regenerate sits beside the prompt; render settings are grouped below
- 3.6 Dropdown hit-area CSS covers the whole control
- 3.7 Instruments, character and keywords sit in a closed Advanced accordion
- 3.8 Stable Audio voice choice relabelled to **Vocal texture**; lyrics backends keep
  **With vocals**. Decision recorded in `docs/decisions.md` (Stability guide + prompt
  delta test; no listening A/B this session)
- Unit tests and mutate anchors for the new rules added

## Outstanding

- Independent adversarial audit
- Stephen review / listening A/B of Stable Audio instrumental vs texture if he wants
  sound evidence beyond Stability's docs
- Merge or push of `phase-3-track-library` (ask before main push)

## Acceptance

The spec's own "Done when" list, plus the project's standing gates:

- `./.venv/bin/python -m synth.cli models` lists every backend as `ok` (Metal required;
  sandbox probes may show MISSING)
- `./.venv/bin/python -m unittest discover -s synth -t .` passes (189 tests)
- `./.venv/bin/python scripts/mutate.py` catches every mutation (92/92 on 2026-09-22)
- `python3.13 scripts/validate.py` reports 0 errors
- A real render is verified by artifact, not by assertion (not run this session)
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
- 2026-09-22 cursor: Picked up the handoff on Stephen's request. Implemented 3.1-3.8 on
  branch `phase-3-track-library`. Voice control is model-aware (Vocal texture vs With
  vocals). Pending deletions live under `output/.pending-delete/`. Unit tests 189 OK;
  mutate 92/92 caught; validate 0 errors. Handing back for review. No listening A/B
  and no real render this session.
