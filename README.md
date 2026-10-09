---
status: active
author: stephen+claude
created: 2026-08-15
updated: 2026-10-09
---

# AI Music Generator

A local workbench for **verbal music synthesis**: describing music in words and rendering
it locally as audio.

Runs on Apple Silicon (M3 Max, 128 GB), with ACE-Step optionally using your own 4090.
No hosted inference or per-track charges.
Deliberately open-ended: soundtrack and underscore, vocal parts or textures for production,
a larger studio engine, and other experiments.

| Document | Purpose |
|---|---|
| [docs/decisions.md](docs/decisions.md) | Why the stack looks the way it does |
| [docs/gotchas.md](docs/gotchas.md) | Setup traps, symptoms, and fixes |
| [docs/prompting.md](docs/prompting.md) | How each backend wants to be asked |
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

The same installation runs `stable-audio-sfx`, the sound-effects checkpoint.
Pre-download its files rather than making the first queued job wait:

```bash
HF_HUB_DISABLE_XET=1 .venv-sa3/bin/python -c \
  "import weights; [weights.ensure_local(path) for path, _ in weights.SHARED + weights.DIT_BUNDLES['sm-sfx']]"
```

Select **Stable Audio (Sound effects) 3** in Generate and describe a sound directly.
Music presets are hidden for this model; duration, guidance and seed still apply.
It uses the Mac's native MLX runtime. A Windows/CUDA fallback is not connected yet.

ACE-Step 1.5 cannot share that environment. Upstream pins `transformers>=4.51,<4.58`
and ships its own MLX path. The pin is the macOS launcher's default: 2B turbo and
the 0.6B planner.

```bash
ACE=~/.cache/ai-music-generator/ACE-Step-1.5
git clone https://github.com/ace-step/ACE-Step-1.5.git "$ACE"
git -C "$ACE" checkout ca1e85fe9430179831e6bc6be790c332190a3866
UV_PROJECT_ENVIRONMENT="$PWD/.venv-ace" uv sync --directory "$ACE" --python 3.12
HF_HUB_DISABLE_XET=1 .venv-ace/bin/python -m acestep.model_downloader \
  --model acestep-5Hz-lm-0.6B --skip-main --force --dir "$ACE/checkpoints"
```

Separation is HTDemucs, not a prompt model. It has its own environment:

```bash
uv venv --python 3.12 .venv-demucs
uv pip install --python .venv-demucs/bin/python 'demucs-mlx[convert]' soundfile
```

A sung line is SoulX, not a prompt model. Do not install the bridge
`requirements.txt`: those pins are CUDA packages. The short list below is the
one that imports here. `librosa==0.11.0` is required.

```bash
SOULX=~/.cache/ai-music-generator/SoulX-Singer-MLX
git clone https://github.com/ailuntx/SoulX-Singer-MLX.git "$SOULX"
git -C "$SOULX" checkout cc5b3054188e8f0d1cab13c07a3e7b6f339bd871
uv venv --python 3.12 .venv-soulx
uv pip install --python .venv-soulx/bin/python \
  torch==2.2.0 torchaudio==2.2.0 "transformers==4.41.2" "numpy==1.26.4" \
  omegaconf einops accelerate soundfile tqdm huggingface_hub mlx safetensors \
  g2p_en nltk "scipy==1.16.2" "librosa==0.11.0"
printf '%s\n' "$SOULX" > .venv-soulx/lib/python3.12/site-packages/soulx.pth
./.venv-soulx/bin/python -m nltk.downloader -d .venv-soulx/nltk_data \
  cmudict averaged_perceptron_tagger averaged_perceptron_tagger_eng
./.venv-soulx/bin/python -c 'import nltk, sys; nltk.data.path = [sys.prefix + "/nltk_data"]; from g2p_en import G2p; assert G2p()("Hello")'
```

The pronunciation check uses the installed language data, without loading singing
weights. An import-only model probe does not check this dependency.
The score runner enables CPU fallback for PyTorch operations unsupported on MPS,
including reference-audio FFT. Its final vocoder head and input run explicitly
on CPU because complex MPS arithmetic crashes even with fallback enabled;
the backbone and diffusion stay on MPS.

Weights download on first use to `~/.cache/`: MiniMax MLX about 13 GB, MusicGen 19 GB,
and both Stable Audio sizes together about 6.1 GB, since they share one repository.
ACE-Step 1.5 downloads its base bundle (about 10 GB, including the upstream default
planner) on first generate, before MLX conversion. Install the selected 0.6B
planner explicitly with the command above. An import probe does not verify weights. SoulX
downloads into `$SOULX/models` on the first sing. A conversion also downloads
the official RMVPE pitch file into that same models folder, and
`openai/whisper-base`, which the conversion model loads itself.

## Models

Six prompt models behind one CLI, each in whatever environment it needs, plus
Demucs for separation and SoulX for a sung line. `./.venv/bin/python -m synth.cli models` probes every one.

| Backend | Model | Max | Prompt style | Licence |
|---|---|---|---|---|
| `stable-audio-medium` | Stable Audio 3 medium (1.4B DiT, default) | 380s | description | Stability Community |
| `stable-audio-sm` | Stable Audio 3 small (50M DiT) | 120s | description | Stability Community |
| `stable-audio-sfx` | Stable Audio 3 sound effects | 120s | direct sound description | Stability Community |
| `minimax-mlx` | MiniMax Music 3 (MLX 8-bit) | 300s | caption | MiniMax Community |
| `acestep` | ACE-Step 1.5 turbo (4090, else MLX) | 600s | tags | MIT |
| `musicgen` | MusicGen stereo-large | 30s | tags | **CC-BY-NC, non-commercial** |

The `stable-audio` backends are fixed-length latent diffusion at 44.1 kHz stereo, trained
on licensed data, and the only ones whose delivered length is exact by construction rather
than audited against a tolerance. They have no key or scale control: the model conditions
on text and duration alone. `minimax-mlx` alone has explicit BPM, key and scale, through
its caption.
`acestep` is the 1.5 turbo. A generate goes to Seneca's 4090 when ComfyUI on
port 8000 answers with the turbo DiT and the 0.6B and 4B text encoders, and
stays on MLX here when it does not. It takes the same tag prompts, has no
guidance control, and can run from 10 seconds to 10 minutes. Cover and repaint
exist in the upstream runtime and are not connected to Remix. Stable Audio,
MiniMax, MusicGen, Demucs and SoulX stay on this Mac. `musicgen` is
capable but slow on Metal and capped at 30 seconds.
Separate, in the header, splits a library track or an upload into vocals, drums,
bass and other. Each stem is its own track. A quiet stem is kept.
Sing has two models. SoulX-Singer takes English words and a melody of `C4 0.5`
lines, one pitched note per word, in the English example voice. SoulX-Singer
SVC follows a recording you have already sung, in that same example voice or
in a voice you upload. A full mix should be separated first.

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
| `--device` | `auto`, `local` or `cuda`; pinning forbids fallback. Only ACE-Step currently has a CUDA adapter |
| `--duration` / `-d` | Target seconds (each backend enforces its own cap and acceptance policy) |
| `--count` / `-n` | Variations per prompt |
| `--guidance` / `-g` | Prompt adherence. Backend default; `minimax-mlx` has none and refuses it |
| `--seed` | Reproduce a specific track (`gen` only) |
| `--steps` | Inference steps, lower is faster and rougher; `musicgen` refuses it |
| `--lyrics` | Defaults to the backend's instrumental sentinel; refused where there is no lyrics channel |
| `--json` | Machine-readable output, one JSON object per line (`gen` only) |

The UI dropdown exposes every backend and redraws its controls, cap and licence from the
manifest. A **Genre** dropdown writes the prompt for you in the selected backend's own
style, drawing on that genre's vocabulary and typical tempo; **Regenerate** gives another
variation, and the tempo control is written into the prompt. Requests queue serially to avoid competing Metal jobs; pending jobs can
be reordered or removed, an active one shows a labelled percentage estimate and cannot yet
be cancelled. Finished tracks sit in a newest-first history, each waveform playable and
seekable. Queue and history live on the server, so browsers share one state and history
rebuilds from `output/`. **Refresh history** picks up files generated elsewhere.
Queued jobs and existing tracks share one scroll area, so a long queue cannot hide the library.
Audio serving supports single byte ranges, including suffix and open-ended requests.
Download sits beside Remix, Separate and Delete on each track's action row.
Advanced shows the last returned seed; Lock reuses it. Each track's Prompt and seed
disclosure shows its own saved values, not the current form.
Advanced also selects the generation device. Auto follows the manifest's ordered
installed routes: ACE-Step prefers the 4090, then local; other modules are local-only.
Track details record actual route and fallback reason. "Local device" identifies
the execution host, not a promise that every operation used its GPU. A submission
timeout is a failure, never permission to generate a duplicate locally.
Delete offers one hour of Undo, then the server purges the WAV and sidecar even
without an open browser. Uploaded and converted working inputs are removed when
their queued job finishes, fails or is removed; user originals are preserved.
Same-name deletions have separate Undo identities. Delete and Restore errors are visible.
New renders use three random words, with a visible numeric suffix on collision;
names in the library and the Undo area are reserved. Existing tracks are not renamed.

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

Prompt style differs by backend, and the wrong one degrades output badly. The UI's
**Genre** dropdown writes the right style for you; **[docs/prompting.md](docs/prompting.md)**
is the full reference for writing them by hand.

In short: `stable-audio-*` wants AudioSparx tags and a plain sentence, `minimax-mlx` wants a
Structured Caption (its only route to BPM, key and scale), and `acestep` and `musicgen` want
comma-separated tags.

The pinned MLX runtime treats duration as an upper bound, so this project suppresses its
early-stop token until the target is reached, then measures the delivered WAV. MiniMax must
deliver at least 90% of the target to pass. Stable Audio needs none of this: it is
fixed-length, so its contract is exact and it is never retried.

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
runners/            subprocess entry points for backends in their own venv
app.py              local web UI (React and Tailwind, served from web/dist)
web/                the browser UI
output/             generated audio + sidecars (gitignored)
```

The full directory map is in [CLAUDE.md](CLAUDE.md).

Backends whose dependencies conflict run as subprocesses in their own venv: ACE-Step 1.5
pins `transformers>=4.51,<4.58` while MiniMax needs `>=5`. Adding a model is a manifest entry plus a
runner implementing the JSON job contract, after which it appears automatically in the CLI,
dropdown, validation and UI controls. A second variant of a model already present needs
only the manifest entry, through `runner_options`. A runner succeeds only once both its
JSON result and a readable audio file at a fresh path have been checked.
