---
status: active
author: stephen+claude
created: 2026-08-15
updated: 2026-09-15
---

# Gotchas

Traps hit while building this, with symptoms and fixes. **Read before installing a new
model or debugging a failure** - several of these cost hours and every one of them is
already paid for.

The nastiest share a shape: **the thing appears to work and produces plausible output**, so
nothing raises an alarm. Prefer failures that are loud.

---

## Installation

### `numba` resolves to a 2021 version and refuses to install

**Symptom:** `RuntimeError: Cannot install on Python version 3.12.9; only versions
>=3.6,<3.10 are supported` while installing ACE-Step.

**Cause:** ACE-Step pins `librosa==0.11.0`; the resolver backtracks to `numba` 0.53.1, which
predates Python 3.10.

**Fix:** pin it forward explicitly.

```bash
uv pip install "numba>=0.61" "llvmlite>=0.44" "git+https://github.com/ace-step/ACE-Step.git"
```

### `torchcodec` missing - generation completes, then the save fails

**Symptom:** `ImportError: TorchCodec is required for save_with_torchcodec`. Full diffusion
runs, then dies writing the file - the most annoying possible place.

**Cause:** current torchaudio delegates `save()` to TorchCodec.

**Fix:** `uv pip install torchcodec`.

### Hugging Face Xet backend hangs silently

**Symptom:** download creates 0-byte `.incomplete` files and stops. No error, no timeout,
no progress. Process stays alive looking busy.

**Fix:** force plain HTTPS. Set **before anything imports `huggingface_hub`**:

```python
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
```

Already set in `synth/core.py` and every runner. **Do not remove it.**

### Model dependency conflicts are unresolvable - use separate venvs

ACE-Step pins `transformers==4.50.0`; MiniMax Music 3 needs `>=5`. There is no shared
resolution. Backends declare their own venv in `synth/backends.py` and run as subprocesses.
Don't try to unify them.

---

## Apple Silicon

### Check for an MLX build before downloading anything

**MLX is Apple-native and dramatically more efficient than PyTorch/MPS.** Community MLX
conversions often appear within days of a model release.

We downloaded MiniMax's 54 GB fp32 PyTorch build and ran it at ~13× realtime, when a
**13 GB MLX 8-bit build existed the whole time**. Four times the disk, far slower, and the
efficient build had already been found in the first search.

**Search HuggingFace for `<model> MLX` before downloading. Every time.**

### ACE-Step needs float32, not bfloat16

bfloat16 errors on macOS. Upstream says pass `--bf16 false`; the equivalent here is
`dtype="float32"`. Already set.

---

## Runtime

### A moved virtual environment can keep stale absolute paths in console scripts

**Symptom:** the MiniMax runner fails immediately because `.venv-mlx/bin/mlx-minimax-music3`
tries to execute Python from the repository's previous location.

**Cause:** the generated console script embeds the virtual environment's absolute path.
Moving the repository does not rewrite it, even though `.venv-mlx/bin/python` still works.

**Fix:** the runner invokes `sys.executable -m mlx_minimax_music3.cli` instead of the
generated console script. This uses the interpreter that launched the runner and survives a
repository move.

### MiniMax returns numpy where its own docs assume a torch tensor

**Symptom:** `AttributeError: 'numpy.ndarray' object has no attribute 'float'` - after a
full successful generation.

**Cause:** the official example calls `audio.T.float().cpu().numpy()`. This build returns
numpy already.

**Fix:** accept either, and transpose channel-first to frames-first for `soundfile`. See
`runners/minimax_mlx_runner.py`.

### The instrumental sentinel differs per model - and fails silently

| Backend | "no vocals" |
|---|---|
| `acestep` | `[inst]` |
| `minimax-mlx` | `[Instrumental]` |
| `musicgen` | *(no lyrics channel)* |

Passing the wrong one doesn't error - **you just get unwanted vocals**. Now a backend
property (`instrumental_tag`), resolved in `core.generate`. Never hardcode it. Passing
`--lyrics` to `musicgen` raises rather than being silently ignored.

### A flag the backend cannot honour used to vanish, and the sidecar still recorded it

**Symptom:** `--steps 80 -m minimax-mlx` produced the same audio as no flag, and the
sidecar said `infer_step: 80`. MusicGen ran at guidance 15 (its own default is 3) because
one CLI default was applied to every backend.

**Cause:** `core.generate` built the subprocess job without `steps`, and the
`mlx-minimax-music3` CLI has no guidance flag at all, but nothing said so.

**Fix:** each `Backend` declares `default_steps` and `default_guidance` (`None` = no such
control) and `supports_lyrics`; `core.generate` applies the backend's default and raises
for a value it cannot honour. The sidecar records `null` for a knob that did not apply.
When adding a backend, read its runtime's CLI source for the flags it really takes.

### Duration caps are per-model

MusicGen is architecturally capped at 30s. Asking for more used to return 30s silently.
Backends now declare `max_duration` and raise. Respect the cap rather than working around it.

### Concurrent generations distort timings

Two jobs on the GPU at once made per-track times balloon 2–4×, which looks like a
performance regression and isn't. **Benchmark one at a time.**

Rough figures, single job, M3 Max:

| Backend | Speed |
|---|---|
| ACE-Step | ~1× realtime (60s audio ≈ 69s) |
| MiniMax fp32 (removed) | ~13× realtime |
| MusicGen | ~15× realtime |

---

## Prompting and evaluation

### Overloaded prompts produce mush

Stacking many competing directives - "orchestral **and** electronic, medieval **and**
corporate", four instruments, two moods - tends to get averaged rather than blended. Fewer,
stronger tags work better.

### Match the prompt style to the backend

Tag soup into MiniMax wastes its structured-caption controls; prose into ACE-Step confuses
it. Check `backends.get(model).prompt_style`.

### Song-form models are weak at orchestral

ACE-Step, MiniMax and most current open music models are trained overwhelmingly on
**song-form pop material**. Asked for cinematic orchestral, ACE-Step fell back to its prior
and produced **rock guitars** - while still scoring perfectly on tempo and pitch-class
analysis.

**Before adopting a model for a genre, check that genre appears in its demos.** MiniMax's
published examples are bossa nova, EDM, pop rock, ballad, funk, lo-fi jazz - no orchestral.

### Audio analysis cannot judge quality

`synth/analyze.py` measures tempo, chroma, onsets and RMS. **All of it can pass while the
audio is unusable** - the guitar tracks above scored 100% on hit-point alignment.

Analysis is for verifying *specific measurable claims* (did the requested key land?), never
for deciding whether something sounds good. That requires a human listening. Generate a
small number of options, send them, and ask.
