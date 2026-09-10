---
status: active
author: stephen+claude
created: 2026-08-15
updated: 2026-09-10
---

# AI Music Generator

A local workbench for **verbal music synthesis** - describing music in words and having it
rendered as audio, entirely on this machine.

Runs on Apple Silicon (M3 Max, 128 GB). No cloud, no per-track licensing, no upload of
anything you're working on.

## What this is for

Deliberately open-ended. Current and possible uses:

- Generating soundtrack and underscore for video work
- Producing interesting vocal parts, textures or fragments to pull into music production
- Acting as the engine underneath a larger studio tool or system
- Whatever artistic or technical concept the experimentation suggests

Because the destination isn't fixed, the project prioritises **organisation and recorded
reasoning** over any one feature. Decisions get written down with their rationale so future
work doesn't relitigate them, and traps get recorded so they're only paid for once.

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
| `--seed` | Reproduce a specific track |
| `--steps` | Inference steps - lower is faster, rougher |
| `--lyrics` | Defaults to the backend's instrumental sentinel |
| `--json` | Machine-readable output |

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

Every WAV gets a matching `.json` sidecar recording prompt, seed, model and settings. This
is what makes the tool usable rather than a slot machine: when something lands, you can
change one parameter instead of rerolling and losing it.

```bash
./.venv/bin/python -m synth.cli gen "<prompt from json>" --seed <seed from json> -m <model>
```

## Layout

```
synth/core.py      generate() - single entry point, dispatches to a backend
synth/backends.py  model registry: venv, runner, caps, licence, prompt style
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
runner script plus a registry entry.

## Environments

| venv | Contains |
|---|---|
| `.venv` | ACE-Step, MusicGen, analysis tooling |
| `.venv-mlx` | MLX runtime for MiniMax Music 3 |

Model weights cache to `~/.cache/` (MiniMax MLX 13 GB, MusicGen 19 GB, ACE-Step 7.7 GB),
outside the repo.
