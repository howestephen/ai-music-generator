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

Deliberately open-ended: soundtrack and underscore, vocal parts or textures for music
production, a larger studio engine, and other artistic experiments.

The project prioritises **organisation and recorded reasoning**. Decisions retain their
rationale and traps are recorded once.

| Document | Purpose |
|---|---|
| [docs/decisions.md](docs/decisions.md) | Why the stack looks the way it does |
| [docs/gotchas.md](docs/gotchas.md) | Setup traps, symptoms, and fixes |
| [CLAUDE.md](CLAUDE.md) | Working rules for AI assistance in this repo |

## Installation

This project needs Apple Silicon with Metal, Python 3.12 and
[`uv`](https://docs.astral.sh/uv/). Create the main environment from its full lock:

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
```

MiniMax has an incompatible dependency stack, so install its adapter at the exact tested
source commit in a second environment:

```bash
uv venv --python 3.12 .venv-mlx
uv pip install --python .venv-mlx/bin/python \
  "mlx-minimax-music3 @ git+https://github.com/vanch007/mlx-minimax-music3.git@b42e07bd2c0ffd14cc6b75ca19d9a96e5397eaf9"
uv pip check --python .venv/bin/python
uv pip check --python .venv-mlx/bin/python
./.venv/bin/python -m synth.cli models
```

Both environments are tested with Python 3.12.9. Model weights download on first use to
`~/.cache/`: MiniMax MLX is about 13 GB, MusicGen 19 GB and ACE-Step 7.7 GB.

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

`minimax-mlx` alone has explicit **BPM, key and scale** control and runs through MLX/Metal.

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
The app therefore treats it as a target and measures the delivered WAV before accepting
the result. MiniMax must deliver at least 90% of the target.

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

The model dropdown exposes every registered backend. Switching it updates duration,
controls, licence, guidance and prompt-style-specific presets from the same versioned JSON
manifest used by the API.
Generated tracks remain in a newest-first playable history beside the controls. Each
waveform fits the available width and remains seekable. History rebuilds from `output/`, so
closing the browser does not lose earlier tracks. Use **Refresh history** to include files
generated elsewhere while the UI is already open.

The UI queues multiple requests serially. Generate shows an acceptance wipe and becomes
available once queued. Pending jobs can be reordered or removed; the active card shows a
labelled progress estimate before becoming a waveform. Serial rendering avoids competing
Metal jobs. Queue and history live on the local server, so browsers share the same state.
Every completed WAV is checked for a readable, finite, non-silent sample stream and its
measured duration. A short render remains in history as `SHORT`, with delivered and target
lengths shown separately. When the user has not locked a seed, the UI retries one short
render with a new seed; a repeated shortfall becomes a visible failed queue job. A fixed
seed is not retried because it would reproduce the same result. An active render cannot
yet be cancelled safely.

**Analyse measurable properties** - tempo, strongest pitch, transient placement and
relative start/end loudness:

```bash
./.venv/bin/python -m synth.analyze output/*.wav
./.venv/bin/python -m synth.analyze output/*.wav --key D --scale mixolydian
```

Pitch-class collection coverage is opt-in through `--key` and `--scale`. It cannot
distinguish relative keys or modes that contain the same notes. Start/end results only say
that an edge is quiet relative to the track median; they do not detect a fade or sweep. One
unreadable file does not abort the batch, but produces a non-zero exit. Measurements do not
judge musical quality.

### Flags

| Flag | Effect |
|---|---|
| `--model` / `-m` | Backend to use |
| `--duration` / `-d` | Target seconds (each backend enforces its own cap and output acceptance policy) |
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

Every WAV gets a matching `.json` sidecar recording the prompt, seed, model, applied
settings, requested duration, measured duration, duration ratio, audit status, frame count,
sample rate, channel count, file size and peak amplitude. Unsupported controls are `null`.
The UI measures legacy WAVs directly, because sidecars written before 1.1 stored the target
under `duration`. It uses the files as its persistent history rather than keeping a separate
database.

```bash
./.venv/bin/python -m synth.cli gen "<prompt from json>" \
  --duration <requested_duration from json> --seed <seed from json> \
  -m <backend from json>
```

## Layout

```
synth/core.py      generate() - single entry point, dispatches to a backend
synth/backends.json versioned model manifest: runtime, controls, licence, prompt style
synth/backends.py  strict manifest loader and runtime registry
synth/cli.py       gen / batch / models / ui
synth/analyze.py   measure requested audio properties
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
