---
status: active
author: stephen+claude
created: 2026-08-15
updated: 2026-09-24
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

### Gradio: a panel that silently stops updating

**Symptom:** the queue card freezes at `0s elapsed` while the render completes
normally, and stays on screen after the queue has emptied. Looks exactly like a
crashed render. Cost hours on 2026-09-19.

**Causes, both real and independent:**

- **`gr.Timer` never fires** in this Gradio build. A Blocks app containing nothing
  but a Timer does not tick either, queued or not. Do not rely on it; drive polling
  from this app's own JS, which does run (see `startPolling` in `UI_JS`).
- **`@gr.render` does not re-run for an event dispatched with `queue=False`.** The
  state updates and the render never fires. Every handler writing to a component
  that feeds a render block must go through the queue. A test in `synth/tests.py`
  now fails if one does not.

**How to tell them apart:** add a plain `gr.HTML` to the handler's outputs and print
a timestamp into it. If that element updates while the render block does not, the
poll is fine and the render is the problem. Reading the code will not show this.

### Gradio copies every file you hand `gr.Audio`

**Symptom:** the server stalls as track history grows; audio URLs point at
`/T/gradio/<hash>/...` rather than at `output/`.

**Cause:** `gr.Audio(value=path)` postprocesses by copying the file into Gradio's
temp cache, and the whole history re-renders whenever a render finishes. A dozen
67 MB tracks copied about a gigabyte per update.

**Fix:** render a plain `<audio>` element pointing at `/gradio_api/file=<abs path>`.
`launch(allowed_paths=[output])` already lets the browser fetch the real file, with
range requests intact, so nothing needs copying.

### The React UI only serves a library filename

**Symptom:** a player is silent, or a request for audio returns 400.

**Cause:** `synth/ui_server.py` serves `GET /audio/<filename>` only when that name
is a WAV directly in `output/`. A path, a symlink out of the folder, or a file
Gradio used to copy into its temp cache is refused.

**Fix:** keep the player `src` on `/audio/<filename>`. Verify with a range request:
it should return 206 and `audio/wav`.

### Gradio serves no file you have not allowed

**Symptom:** every player in the UI is silent. The WAV on disk is valid, and the
server logs nothing.

**Cause:** Gradio serves only declared paths. Without `allowed_paths`, a request for
a generated track returns 403 with `File not allowed`, which the audio element shows
as silence.

**Fix:** `launch(allowed_paths=[str(core.OUTPUT_DIR)])`. Verify with a range request:
it should return 206 and `audio/x-wav`, not 403.

### A render estimate must be fitted, not assumed

**Symptom:** a job that finishes in 26 seconds crawls at 5% and reads as hung.

**Cause:** render cost is a fixed overhead plus a small per-second rate, not a
multiple of track length. A 380s Stable Audio render takes less wall time than a
180s one did. Separately, a backend's first render also pays for a multi-gigabyte
weight download, and averaging that in as render time poisons every later estimate.

**Fix:** fit `overhead + rate * duration` from the most recent renders only, and keep
measured per-backend fallbacks. Elapsed seconds are shown next to the percentage so a
wrong estimate reads as wrong rather than as hung. Once elapsed passes the estimate the
card says `past Ns estimate` instead of sitting on `estimated 95%`. Whole-track remixes
also take a `max(fit, 0.5 * duration, 60s)` floor, because init-audio of a long track is
far slower than text-to-audio of the same length (a 347s remix took 221s here).

### Hugging Face Xet backend hangs silently

**Symptom:** download creates 0-byte `.incomplete` files and stops. No error, no timeout,
no progress. Process stays alive looking busy.

**Fix:** force plain HTTPS. Set **before anything imports `huggingface_hub`**:

```python
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
```

Already set in `synth/core.py`, `runners/minimax_mlx_runner.py`,
`runners/musicgen_runner.py` and `runners/stable_audio_runner.py`. Every new runner
that downloads weights needs it too. **Do not remove it.**

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

### Regenerate keeps saying Rhodes, plate reverb, or a polished finish

**Symptom:** prompts from different genres, or repeated presses of Regenerate, use
the same instruments and the same studio phrases.

**Cause:** each genre had only a few lines, and every description prompt also
pulled from one shared list of rooms, effects and eras. Liquid drum and bass
always tagged electric piano.

**Fix:** the draw stays inside that genre's own lists, including which instrument
tag is used. The shared list is only added when it is chosen as a character pin.
Lines are not copied from one genre into another.

### The genre filter shows one dancefloor track when the library is full of them

**Symptom:** Drum & Bass - Dancefloor lists a single track. The other drum and bass
files say "dancefloor drum and bass" in the prompt.

**Cause:** the filter matched only the `genre` field on the sidecar. Tracks written
before that field existed have no genre, so they matched nothing.

**Fix:** when the field is missing, the view reads the style phrase out of the prompt.
A saved genre still wins. The sidecar is not rewritten. `metal` does not match
`metallic`.


### The pinned MiniMax duration flag is only a ceiling without the project wrapper

**Symptom:** a request says 240 or 300 seconds, but the WAV is only 17 to 42 seconds long.
Sidecars written before phase 1.1 also showed the requested number as `duration`, so the UI
made the short result look compliant.

**Cause:** the pinned MLX package converts `audio_duration` into `max_frames`, then stops
as soon as the language model samples `audio_end_token_id`. The public duration flag does
not impose a minimum or guarantee the requested length.

**Fix:** the internal generation mode in `runners/minimax_mlx_runner.py` masks the audio-end token until the selected
target frame count exists, using the same mechanism as the maintained MLX runtime's
`min_audio_duration`. The outer runner passes the selected duration as both minimum and
maximum. Do not remove `--min-duration` or call the pinned package CLI directly.

Still never infer delivered length from the request. Audit the WAV after generation, record
requested and measured duration separately, and compare it with the backend's manifest
policy. The boundary also rejects unreadable, empty, silent and non-finite audio. Retain a
failed creative asset and its sidecar for investigation rather than deleting it.

### Exit code zero does not prove that a runner produced audio

**Symptom:** a CLI call appeared successful, or a UI job reached the end of its estimate,
but no playable file existed. Malformed runner JSON could also escape as a decode error.

**Cause:** the subprocess boundary trusted the exit code and the first JSON-looking stdout
line. It did not validate the result fields or the output file.

**Fix:** the manifest now declares import probes and a finite runner timeout. The caller
decodes UTF-8 explicitly and requires valid result JSON, the requested fresh output path,
a finite elapsed time and a readable audio container before writing a sidecar. A timeout
terminates the adapter's process group so its model child cannot continue using the GPU.

### A moved virtual environment can keep stale absolute paths in console scripts

**Symptom:** the MiniMax runner fails immediately because `.venv-mlx/bin/mlx-minimax-music3`
tries to execute Python from the repository's previous location.

**Cause:** the generated console script embeds the virtual environment's absolute path.
Moving the repository does not rewrite it, even though `.venv-mlx/bin/python` still works.

**Fix:** the runner starts its own `_generate` mode with `sys.executable`, then that mode
imports the pinned `mlx_minimax_music3.cli`. Both processes therefore use the interpreter
that launched the runner rather than the generated console script, so a repository move
does not leave either invocation pointing at the old path.

### MiniMax audio conversion belongs to the installed MLX package

**Symptom:** changing the adapter to copy PyTorch-oriented save examples causes an error
after the expensive generation has completed.

**Cause:** The runner returns JSON from `mlx_minimax_music3.cli`; it never receives an
audio tensor or array. The pinned package's `audio.py` already converts its MLX array to a
finite NumPy frames-by-channels array, clips it and writes 16-bit PCM through `soundfile`.

**Fix:** leave conversion in the pinned package and validate the resulting container at
the project boundary. Do not add NumPy or PyTorch conversion to
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
Backends now declare their full numeric control contracts and raise outside them. Respect
the selected backend's cap rather than working around it.

Gradio component schemas are static even when `gr.update()` changes a slider in the browser.
If the component is initially built from a shorter default model, the API can reject a valid
request for a longer model before the handler runs. Build the static component from the
union of backend contracts, then narrow it visually and validate the selected backend in
the handler. This is why MiniMax's 300-second requests must not inherit ACE-Step's
240-second component schema.

### Concurrent generations distort timings

Two jobs on the GPU at once made per-track times balloon 2-4x, which looks like a
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

Analysis verifies *specific measurable claims*, never whether music sounds good. Optional
pitch-class coverage cannot distinguish modes containing the same notes. The strongest
chroma pitch is a peak, not a tonic. Quiet edges are not detected fades or sweeps. Quality
requires human listening.
