---
status: active
author: stephen+claude
created: 2026-08-15
updated: 2026-09-19
---

# AI Music Generator

A local workbench for **verbal music synthesis**: describing music in words and rendering
it locally as audio.

Runs on Apple Silicon (M3 Max, 128 GB). No cloud, no per-track licensing, nothing uploaded.
Deliberately open-ended: soundtrack and underscore, vocal parts or textures for production,
a larger studio engine, and other experiments.

| Document | Purpose |
|---|---|
| [docs/decisions.md](docs/decisions.md) | Why the stack looks the way it does |
| [docs/gotchas.md](docs/gotchas.md) | Setup traps, symptoms, and fixes |
| [CLAUDE.md](CLAUDE.md) | Working rules for AI assistance in this repo |

## Installation

Needs Apple Silicon with Metal, Python 3.12 and [`uv`](https://docs.astral.sh/uv/). Both
environments are tested on 3.12.9. `requirements.txt` is a full lock: every dependency is
pinned to a version or a commit.

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
```

MiniMax has an incompatible dependency stack, so its adapter installs into its own
environment at the tested source commit:

```bash
uv venv --python 3.12 .venv-mlx
uv pip install --python .venv-mlx/bin/python \
  "mlx-minimax-music3 @ git+https://github.com/vanch007/mlx-minimax-music3.git@b42e07bd2c0ffd14cc6b75ca19d9a96e5397eaf9"
uv pip check --python .venv/bin/python
uv pip check --python .venv-mlx/bin/python
./.venv/bin/python -m synth.cli models
```

Stable Audio 3 ships as a source tree rather than a package, so it is pinned as a clone
and placed on its own environment's import path:

```bash
SA3=~/.cache/ai-music-generator/stable-audio-3
git clone https://github.com/Stability-AI/stable-audio-3.git "$SA3"
git -C "$SA3" checkout 779434a908193105335fd8d833418603625b2859
uv venv --python 3.12 .venv-sa3
uv pip install --python .venv-sa3/bin/python -r "$SA3/optimized/mlx/requirements.txt"
printf '%s\n%s\n' "$SA3/optimized/mlx" "$SA3/optimized/mlx/scripts" \
  > .venv-sa3/lib/python3.12/site-packages/stable_audio_3.pth
```

Weights download on first use to `~/.cache/`: MiniMax MLX about 13 GB, MusicGen 19 GB,
ACE-Step 7.7 GB, Stable Audio small about 1.9 GB and medium about 6.5 GB.

## Models

Three backends behind one CLI, each in whatever environment it needs.
`./.venv/bin/python -m synth.cli models` probes all three.

| Backend | Model | Max | Prompt style | Licence |
|---|---|---|---|---|
| `minimax-mlx` | MiniMax Music 3 (MLX 8-bit, default) | 300s | caption | MiniMax Community |
| `stable-audio-sm` | Stable Audio 3 small (50M DiT) | 120s | description | Stability Community |
| `stable-audio-medium` | Stable Audio 3 medium (1.4B DiT) | 380s | description | Stability Community |
| `acestep` | ACE-Step v1 3.5B | 240s | tags | Apache-2.0 |
| `musicgen` | MusicGen stereo-large | 30s | tags | **CC-BY-NC, non-commercial** |

The two `stable-audio` backends are fixed-length latent diffusion at 44.1 kHz stereo,
trained on licensed data, and are the only ones whose delivered length is exact by
construction rather than audited against a tolerance. `minimax-mlx` alone has explicit
BPM, key and scale control, and runs through MLX/Metal.
`acestep` is roughly realtime but song-form and weak at orchestral and cinematic material,
where it drifts toward rock instrumentation. `musicgen` is capable but slow on Metal (about
15x realtime) and capped at 30 seconds.

## Usage

```bash
# one track
./.venv/bin/python -m synth.cli gen "<prompt>" --model minimax-mlx --duration 70

# batch: every prompt in prompts/, one prompt per line, # for comments
./.venv/bin/python -m synth.cli batch --model minimax-mlx --duration 60
./.venv/bin/python -m synth.cli batch --dir path/to/other-prompts --model acestep

# web UI
./.venv/bin/python app.py
```

| Flag | Effect |
|---|---|
| `--model` / `-m` | Backend to use |
| `--duration` / `-d` | Target seconds (each backend enforces its own cap and acceptance policy) |
| `--count` / `-n` | Variations per prompt |
| `--guidance` / `-g` | Prompt adherence. Backend default; `minimax-mlx` has none and refuses it |
| `--seed` | Reproduce a specific track (`gen` only) |
| `--steps` | Inference steps, lower is faster and rougher; `musicgen` refuses it |
| `--lyrics` | Defaults to the backend's instrumental sentinel; refused where there is no lyrics channel |
| `--json` | Machine-readable output, one JSON object per line (`gen` only) |

The UI dropdown exposes every backend and redraws its controls, cap, licence and presets
from the manifest. Requests queue serially to avoid competing Metal jobs; pending jobs can
be reordered or removed, an active one shows a labelled percentage estimate and cannot yet
be cancelled. Finished tracks sit in a newest-first history, each waveform playable and
seekable. Queue and history live on the server, so browsers share one state and history
rebuilds from `output/`. **Refresh history** picks up files generated elsewhere.

Every completed WAV is checked for a readable, finite, non-silent sample stream and its
measured duration, on the CLI and in the UI alike. A short render stays in the history
marked `SHORT`, delivered and target shown separately. **Only the UI retries**, and only on
an unlocked seed, since a fixed seed would reproduce the same result. `gen` and `batch`
never retry. Backends declaring an exact contract are never retried at all.

### Analysis

```bash
./.venv/bin/python -m synth.analyze output/*.wav --key D --scale mixolydian
```

Measures tempo, strongest pitch, transient placement and relative edge loudness.
Pitch-class coverage is opt-in through `--key` and `--scale` and cannot separate modes
sharing notes. A quiet edge means only that, not that a fade exists.
**Measurements do not judge quality.**

## Prompting

Prompt style differs by backend, and using the wrong one degrades output badly.

`acestep` and `musicgen` want comma-separated tags. The pipeline supplies ACE-Step's
`[inst]` sentinel, and ACE-Step is seed-sensitive, so compare seeds rather than treating
one result as representative.

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

Its sections are **Global Metadata** (genre, BPM, key, scale, emotional progression,
listening scenario, production profile), **Vocal Details** and **Arrangement**. State
instrumental intent explicitly, anchor two or three instruments, and describe a
section-by-section evolution. Sources: the
[model guide](https://github.com/MiniMax-AI/MiniMax-Music3/blob/main/README.md),
[caption rewriter](https://github.com/MiniMax-AI/MiniMax-Music3/blob/main/skills/music-caption-rewriter/SKILL.md)
and [prompt guide](https://github.com/MiniMax-AI/skills/blob/main/skills/minimax-music-gen/references/prompt_guide.md).

`stable-audio-*` wants one plain sentence, not tags and not a caption:
`a slow cinematic build, low strings and a rising drone, no drums`.

The pinned MLX runtime treats duration as an upper bound, so this project suppresses its
early-stop token until the target is reached, then measures the delivered WAV. MiniMax must
deliver at least 90% of the target to pass. Stable Audio needs none of this: it is
fixed-length, so its contract is exact and it is never retried.

Keep prompts focused. Stacking competing directives averages into mush rather than blending,
see [docs/gotchas.md](docs/gotchas.md).

## Reproducibility

Every WAV gets a matching `.json` sidecar: prompt, seed, model, applied settings, requested
and measured duration, duration ratio, audit status and basic audio facts. Unsupported
controls are `null`. Sidecars written before milestone 1.1 stored the target under
`duration`, so the UI measures those directly.

```bash
./.venv/bin/python -m synth.cli gen "<prompt from json>" \
  --duration <requested_duration from json> --seed <seed from json> \
  -m <backend from json>
```

## Layout

```
synth/core.py       generate() - the single entry point, dispatches to a backend
synth/backends.json versioned model manifest: runtime, controls, licence, prompt style
runners/            per-backend subprocess entry points, one per isolated environment
app.py              Gradio web UI
output/             generated audio + sidecars (gitignored)
```

The full directory map is in [CLAUDE.md](CLAUDE.md).

Backends whose dependencies conflict run as subprocesses in their own venv: ACE-Step pins
`transformers==4.50` while MiniMax needs `>=5`. Adding a model is a manifest entry plus a
runner implementing the JSON job contract, after which it appears automatically in the CLI,
dropdown, validation and UI controls. A second variant of a model already present needs
only the manifest entry, through `runner_options`. A runner succeeds only once both its
JSON result and a readable audio file at a fresh path have been checked.
