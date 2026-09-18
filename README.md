---
status: active
author: stephen+claude
created: 2026-08-15
updated: 2026-09-18
---

# AI Music Generator

A local workbench for **verbal music synthesis**: describing music in words and rendering
it locally as audio.

Runs on Apple Silicon (M3 Max, 128 GB). No cloud, no per-track licensing, no upload of
anything you're working on. Deliberately open-ended: soundtrack and underscore, vocal parts
or textures for music production, a larger studio engine, and other artistic experiments.

| Document | Purpose |
|---|---|
| [docs/decisions.md](docs/decisions.md) | Why the stack looks the way it does |
| [docs/gotchas.md](docs/gotchas.md) | Setup traps, symptoms, and fixes |
| [CLAUDE.md](CLAUDE.md) | Working rules for AI assistance in this repo |

## Installation

Needs Apple Silicon with Metal, Python 3.12 and [`uv`](https://docs.astral.sh/uv/). Both
environments are tested on 3.12.9.

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
```

MiniMax has an incompatible dependency stack, so its adapter installs into a second
environment at the exact tested source commit:

```bash
uv venv --python 3.12 .venv-mlx
uv pip install --python .venv-mlx/bin/python \
  "mlx-minimax-music3 @ git+https://github.com/vanch007/mlx-minimax-music3.git@b42e07bd2c0ffd14cc6b75ca19d9a96e5397eaf9"
uv pip check --python .venv/bin/python
uv pip check --python .venv-mlx/bin/python
./.venv/bin/python -m synth.cli models
```

Weights download on first use to `~/.cache/`: MiniMax MLX about 13 GB, MusicGen 19 GB,
ACE-Step 7.7 GB.

## Models

Three backends behind one CLI, each in whatever environment it needs.
`./.venv/bin/python -m synth.cli models` probes all three.

| Backend | Model | Max | Prompt style | Licence |
|---|---|---|---|---|
| `minimax-mlx` | MiniMax Music 3 (MLX 8-bit, default) | 300s | caption | MiniMax Community |
| `acestep` | ACE-Step v1 3.5B | 240s | tags | Apache-2.0 |
| `musicgen` | MusicGen stereo-large | 30s | tags | **CC-BY-NC, non-commercial** |

`minimax-mlx` alone has explicit BPM, key and scale control, and runs through MLX/Metal.
`acestep` is roughly realtime but song-form, and demonstrably weak at orchestral and
cinematic material, where it drifts toward rock band instrumentation. `musicgen` is capable
but slow on Metal (about 15x realtime) and capped at 30 seconds.

## Usage

```bash
# one track
./.venv/bin/python -m synth.cli gen "<prompt>" --model minimax-mlx --duration 70

# batch: a directory of prompt files, one prompt per line, # for comments
./.venv/bin/python -m synth.cli batch --dir briefs/my-brief --model minimax-mlx --duration 60

# web UI
./.venv/bin/python app.py
```

| Flag | Effect |
|---|---|
| `--model` / `-m` | Backend to use |
| `--duration` / `-d` | Target seconds (each backend enforces its own cap and acceptance policy) |
| `--count` / `-n` | Variations per prompt |
| `--guidance` / `-g` | Prompt adherence. Backend default (`acestep` 15, `musicgen` 3); `minimax-mlx` exposes none and refuses the flag |
| `--seed` | Reproduce a specific track |
| `--steps` | Inference steps, lower is faster and rougher. Backend default; `musicgen` has none and refuses the flag |
| `--lyrics` | Defaults to the backend's instrumental sentinel; `musicgen` has no lyrics channel and refuses the flag |
| `--json` | Machine-readable output, one JSON object per line |

The UI dropdown exposes every registered backend and redraws its controls, duration cap,
licence and presets from the same manifest the API uses. Requests queue serially to avoid
competing Metal jobs, and pending jobs can be reordered or removed. Queue and history live
on the local server, so browsers share one state and history rebuilds from `output/`.
**Refresh history** picks up files generated elsewhere while the UI is open.

Every completed WAV is checked for a readable, finite, non-silent sample stream and its
measured duration. A short render stays in history marked `SHORT`, with delivered and target
lengths shown separately. An unlocked seed is retried once; a fixed seed is not, because it
would reproduce the same result. An active render cannot yet be cancelled.

### Analysis

```bash
./.venv/bin/python -m synth.analyze output/*.wav
./.venv/bin/python -m synth.analyze output/*.wav --key D --scale mixolydian
```

Measures tempo, strongest pitch, transient placement and relative start/end loudness.
Pitch-class coverage is opt-in through `--key` and `--scale` and cannot distinguish relative
keys or modes sharing the same notes. Edge results say only that an edge is quiet against
the track median, not that a fade or sweep exists. One unreadable file does not abort the
batch but produces a non-zero exit. **Measurements do not judge musical quality.**

## Prompting

Prompt style differs by backend, and using the wrong one degrades output badly.

`acestep` and `musicgen` want comma-separated tags. The pipeline supplies ACE-Step's
`[inst]` sentinel automatically, and ACE-Step is seed-sensitive, so compare seeds rather
than treating one result as representative.

```
lo-fi hip hop, warm rhodes piano, vinyl crackle, 85bpm, instrumental
```

`minimax-mlx` wants a **Structured Caption** in prose. This is the only route to its BPM,
key and scale control:

```
Genre: cinematic orchestral, medieval. BPM: 120. Key: D. Scale: Mixolydian.
Mood: serious, restrained, building subtly. Listening scenario: background score
under voiceover. Arrangement: low cello ostinato carries the pulse; frame drum on a
four-bar cycle; distant horn swells; soft sweep leading in and out.
Instrumental only, no vocals.
```

Its caption sections are **Global Metadata** (genre, BPM, key, scale, emotional progression,
listening scenario, production profile), **Vocal Details** and **Arrangement** (primary and
secondary instruments, section-level evolution, groove, bass, percussion, textures, spatial
effects). State instrumental intent and the lead texture explicitly, anchor only two or
three instruments, and describe a coherent section-by-section evolution. The source
references are the
[model guide](https://github.com/MiniMax-AI/MiniMax-Music3/blob/main/README.md),
[caption rewriter](https://github.com/MiniMax-AI/MiniMax-Music3/blob/main/skills/music-caption-rewriter/SKILL.md)
and [prompt guide](https://github.com/MiniMax-AI/skills/blob/main/skills/minimax-music-gen/references/prompt_guide.md).

The pinned MLX runtime treats duration as an upper bound, so this project suppresses its
early-stop token until the selected target is reached, then measures the delivered WAV
independently. MiniMax must deliver at least 90% of the target to pass that audit.

Keep prompts focused. Stacking competing directives averages into mush rather than blending,
see [docs/gotchas.md](docs/gotchas.md).

## Reproducibility

Every WAV gets a matching `.json` sidecar: prompt, seed, model, applied settings, requested
and measured duration, duration ratio, audit status, frame count, sample rate, channel
count, file size and peak amplitude. Unsupported controls are `null`. Sidecars written
before milestone 1.1 stored the target under `duration`, so the UI measures those WAVs
directly.

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

Backends whose dependencies conflict run as subprocesses in their own venv: ACE-Step pins
`transformers==4.50` while MiniMax needs `>=5`. Adding a model is a manifest entry plus a
runner implementing the existing JSON job contract, after which it appears automatically in
the CLI, dropdown, validation and UI controls. A runner succeeds only once both its JSON
result and a readable audio file at a fresh path have been checked, and a timed-out runner
is terminated together with its model child.
