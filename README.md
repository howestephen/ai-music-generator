---
status: active
author: stephen+claude
created: 2026-08-15
updated: 2026-09-16
---

# AI Music Generator

A local workbench for **verbal music synthesis** - describing music in words and rendering
it locally as audio.

Runs on Apple Silicon (M3 Max, 128 GB). No cloud, no per-track licensing, no upload of
anything you're working on.

## What this is for

Deliberately open-ended. Current and possible uses:

- Generating soundtrack and underscore for video work
- Producing interesting vocal parts, textures or fragments to pull into music production
- Acting as the engine underneath a larger studio tool or system
- Whatever artistic or technical concept the experimentation suggests

Because the destination isn't fixed, the project prioritises **organisation and recorded
reasoning**. Decisions retain their rationale and traps are recorded once.

| Document | Purpose |
|---|---|
| [docs/decisions.md](docs/decisions.md) | Why the stack looks the way it does |
| [docs/gotchas.md](docs/gotchas.md) | Setup traps, symptoms, and fixes |
| [CLAUDE.md](CLAUDE.md) | Working rules for AI assistance in this repo |

## Models

Three backends behind one CLI. Each runs in whatever environment it needs.

```bash
./.venv/bin/python -m synth.cli models
```

| Backend | Model | Max | Prompt style | Licence |
|---|---|---|---|---|
| `minimax-mlx` | MiniMax Music 3 (MLX 8-bit) | 300s | caption | MiniMax Community |
| `acestep` | ACE-Step v1 3.5B | 240s | tags | Apache-2.0 |
| `musicgen` | MusicGen stereo-large | 30s | tags | **CC-BY-NC - non-commercial** |

`minimax-mlx` is the newest and the only one with explicit **BPM, key and scale** control.
It runs natively on Metal via MLX rather than PyTorch/MPS.

`acestep` is fast (roughly realtime) but is a song-form model - it is demonstrably weak at
orchestral and cinematic material, where it drifts toward rock band instrumentation.

`musicgen` is capable but slow on Metal (~15× realtime) and capped at 30 seconds.
Non-commercial weights.

### Prompting reference

For `minimax-mlx`, write vivid English sentences under `Global Metadata`, `Vocal Details`
and `Arrangement`. State instrumental intent and the lead texture explicitly, anchor only
two or three instruments, and describe a coherent section-by-section evolution. The
[official model guide](https://github.com/MiniMax-AI/MiniMax-Music3/blob/main/README.md),
[caption rewriter](https://github.com/MiniMax-AI/MiniMax-Music3/blob/main/skills/music-caption-rewriter/SKILL.md)
and [prompt guide](https://github.com/MiniMax-AI/skills/blob/main/skills/minimax-music-gen/references/prompt_guide.md)
are the source references. The requested duration is an upper bound, not a guarantee.

For `acestep`, use concise comma-separated genre, instrumentation, mood and tempo tags. The
generation pipeline supplies its `[inst]` sentinel automatically. ACE-Step is seed-sensitive and its
own [model card](https://huggingface.co/ACE-Step/ACE-Step-v1-3.5B) warns that long output
can lose structure, so compare seeds rather than treating one result as representative.

## Usage

**One track:**

```bash
./.venv/bin/python -m synth.cli gen "<prompt>" --model minimax-mlx --duration 70
```

**Batch** - put prompts in a directory, one per line, `#` for comments:

```bash
./.venv/bin/python -m synth.cli batch --dir briefs/my-brief --model minimax-mlx --duration 60
```

**Web UI:**

```bash
./.venv/bin/python app.py
```

The model dropdown exposes every registered backend. Switching model updates the duration
cap, supported controls, licence information and prompt guidance; presets are converted to
the selected backend's prompt style using separate tag and structured-caption versions.
The browser and API read those settings from the same versioned JSON manifest, so neither
can impose another model's limits.
Generated tracks remain in a playable history to the right of the controls, newest first,
in a balanced 50/50 layout. Each complete waveform is fitted to the available width and
remains clickable for seeking. The history is rebuilt from `output/` when the UI starts, so
closing the browser does not lose earlier tracks. Use **Refresh history** to include files
generated elsewhere while the UI is already open.

The UI accepts multiple render requests into a serial queue. The Generate button shows an
acceptance wipe, then becomes available again as soon as the job is queued. Pending jobs can
be reordered or removed in the right column. One job renders at a time; its card shows an
explicitly labelled progress estimate, then gives way to the finished waveform. Serial
rendering avoids the severe slowdown and unpredictable timings caused by competing Metal
jobs. Queue cards and track history are read from the shared local server, so opening the
UI in another browser shows the same active and pending jobs and completed tracks. An active
render cannot yet be cancelled safely.

**Analyse what came out** - tempo, modality, transient placement:

```bash
./.venv/bin/python -m synth.analyze output/*.wav
```

### Flags

| Flag | Effect |
|---|---|
| `--model` / `-m` | Backend to use |
| `--duration` / `-d` | Seconds (each backend enforces its own cap) |
| `--count` / `-n` | Variations per prompt |
| `--guidance` / `-g` | Prompt adherence. Default is the backend's own (`acestep` 15, `musicgen` 3); `minimax-mlx` exposes none and refuses the flag |
| `--seed` | Reproduce a specific track |
| `--steps` | Inference steps, lower is faster and rougher. Default is the backend's own; `musicgen` has none and refuses the flag |
| `--lyrics` | Defaults to the backend's instrumental sentinel; `musicgen` has no lyrics channel and refuses the flag |
| `--json` | Machine-readable output, one JSON object per line |

## Prompting

**Prompt style differs by backend** and using the wrong one degrades output badly.

`acestep` and `musicgen` want comma-separated style tags:

```
lo-fi hip hop, warm rhodes piano, vinyl crackle, 85bpm, instrumental
```

`minimax-mlx` wants a **Structured Caption** in prose. This is where its BPM/key/scale
control lives, and it is the only way to reach those controls:

```
Genre: cinematic orchestral, medieval. BPM: 120. Key: D. Scale: Mixolydian.
Mood: serious, restrained, building subtly. Listening scenario: background score
under voiceover. Arrangement: low cello ostinato carries the pulse; frame drum on a
four-bar cycle; distant horn swells; soft sweep leading in and out.
Instrumental only, no vocals.
```

Documented caption sections are **Global Metadata** (genre, BPM, key, scale, emotional
progression, listening scenario, production profile), **Vocal Details**, and
**Arrangement** (primary/secondary instruments, section-level evolution, groove, bass,
percussion, textures, spatial effects).

Keep prompts focused. Stacking many competing directives tends to average into mush rather
than blending - see [docs/gotchas.md](docs/gotchas.md).

## Reproducibility

Every WAV gets a matching `.json` sidecar recording prompt, seed, backend, model and the
settings that actually applied (a knob the backend does not have is recorded as `null`). This
is what makes the tool usable rather than a slot machine: when something lands, you can
change one parameter instead of rerolling and losing it. The UI reads these same files for
its persistent history; it does not keep a separate database.

```bash
./.venv/bin/python -m synth.cli gen "<prompt from json>" --seed <seed from json> -m <backend from json>
```

## Layout

```
synth/core.py      generate() - single entry point, dispatches to a backend
synth/backends.json versioned model manifest: runtime, controls, licence, prompt style
synth/backends.py  strict manifest loader and runtime registry
synth/cli.py       gen / batch / models / ui
synth/analyze.py   measure output against a brief
runners/           per-backend subprocess entry points (isolated environments)
app.py             Gradio web UI
briefs/            prompt sets per project
output/            generated audio + sidecars (gitignored)
docs/              decisions and gotchas
```

Backends whose dependencies conflict run as subprocesses in their own venv - ACE-Step pins
`transformers==4.50` while MiniMax needs `>=5`, so they can't share one. Adding a model is a
manifest entry plus a runner implementing the existing JSON job contract. The model then
appears automatically in the CLI, dropdown, validation and model-specific UI controls.
The manifest also declares modules used to verify the environment and a finite timeout for
each subprocess runner. A runner is successful only after its JSON result and readable
audio file at a fresh path have both been checked. A timed-out runner and its model child
are terminated together.

## Environments

| venv | Contains |
|---|---|
| `.venv` | ACE-Step, MusicGen, analysis tooling |
| `.venv-mlx` | MLX runtime for MiniMax Music 3 |

Model weights cache to `~/.cache/` (MiniMax MLX 13 GB, MusicGen 19 GB, ACE-Step 7.7 GB),
outside the repo.
