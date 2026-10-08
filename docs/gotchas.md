---
status: active
author: stephen+claude
created: 2026-08-15
updated: 2026-10-08
---

# Gotchas

Traps hit while building this, with symptoms and fixes. **Read before installing a new
model or debugging a failure** - several of these cost hours and every one of them is
already paid for.

The nastiest share a shape: **the thing appears to work and produces plausible output**, so
nothing raises an alarm. Prefer failures that are loud.

---

## Same-name tracks can block Delete

The earlier Undo storage used the original filename. A new render could reuse a
deleted name, and deleting it failed while the earlier version remained in Trash.
The React callback also discarded that error. Pending pairs now get separate
storage identities while retaining the original restore basename; both Delete and
Restore report failures. New output reservations include Trash names and sidecars.

Vocal texture changes the menu selection only. Its wordless-vocal request is added
when a genre is selected or Regenerate is pressed; Generate submits the visible
prompt unchanged. This UI connection remains unresolved, not an audio-quality finding.

## Seneca

### ComfyUI is on port 8000, and the LAN address does not answer

**Symptom:** port 8188 times out, and `http://192.168.4.46` is "No route to host",
while `seneca.local` still pings.

**Cause:** the desktop app was started with `--listen 0.0.0.0 --port 8000`.
HTTP from this Mac reaches it on Tailscale (`seneca.tail37ad60.ts.net`), not
on the LAN address. Port 1234 on that same Tailscale address is LM Link, an
OpenAI-compatible text server, not a music model.

**Fix:** ACE-Step jobs use `http://seneca.tail37ad60.ts.net:8000`. Set
`AI_MUSIC_COMFY=0` to keep ACE-Step on this Mac. Set `AI_MUSIC_COMFY_URL` if
the port moves. A failed graph is an error. A box that does not answer falls
back to MLX. Do not call ComfyUI's global interrupt: that cancels whatever
else is running on the 4090.

---

## Installation

### `numba` resolves to a 2021 version and refuses to install

**Symptom:** `RuntimeError: Cannot install on Python version 3.12.9; only versions
>=3.6,<3.10 are supported` while installing ACE-Step v1.

**Cause:** ACE-Step v1 pins `librosa==0.11.0`; the resolver backtracks to `numba` 0.53.1,
which predates Python 3.10.

**Fix:** that install is retired. ACE-Step 1.5 is the `uv sync` block in the README.
If a v1 checkout is forced anyway, pin numba forward:

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

### A suffix byte range is the end of the WAV, not its beginning

**Symptom:** an audio request for `bytes=-4` returns five bytes from the WAV
header; a valid range ending past the file returns 416.

**Cause:** the HTTP handler treated a missing start as zero and rejected an end
beyond the file instead of clipping it.

**Fix:** suffix ranges return the last requested bytes, oversized ends clip to
EOF, and invalid or unsatisfiable single ranges return an empty 416 with the
file size. Served-HTTP tests assert exact bytes and headers, including empty files.
Decimal numerals are clamped before integer conversion, including long leading-zero values.
Multiple ranges are not supported.

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

Already set in `synth/core.py`, `runners/acestep_runner.py`,
`runners/demucs_runner.py`, `runners/minimax_mlx_runner.py`,
`runners/musicgen_runner.py`, `runners/soulx_runner.py`,
`runners/soulx_svc_runner.py` and
`runners/stable_audio_runner.py`. Every new runner
that downloads weights needs it too. **Do not remove it.**

### SoulX upstream requirements are a CUDA pin

**Symptom:** installing the bridge `requirements.txt` fails on sageattention,
nemo or torchcodec.

**Cause:** the official Soul-AILab pins are CUDA packages. This Mac does not
use them. `soulxsinger` also imports librosa, which that file's pins do not
make obvious until the import fails.

**Fix:** use the short install in the README, including `librosa==0.11.0`,
and the `.pth` that points at the clone. Do not install that requirements
file. The first sing downloads `mlx-community/SoulX-Singer` into the clone.

### SoulX on Python 3.10 cannot load its pitch extractor

**Symptom:** importing `soulxsinger` dies in `scipy.sparse.linalg` with
`__DATA/__thread_bss` has a zero-fill section type.

**Cause:** the SciPy 1.15 wheel does not load on this OS. SciPy 1.16 does,
and 1.16 no longer publishes a Python 3.10 build. The official pitch
extractor also caps a contour at 300 seconds unless told otherwise, which
would clip a recording the backend accepts up to 600.

**Fix:** the SoulX environment is Python 3.12 with `scipy==1.16.2`, as in
the README. The conversion runner passes a 600 second cap into that
extractor. Do not put the environment back on Python 3.10.

### SoulX imports successfully but fails when processing lyrics

**Symptom:** the first Sing downloads weights, then fails with missing
`taggers/averaged_perceptron_tagger_eng/`.

**Cause:** installed `g2p_en` requests the older tagger at import time, but
installed NLTK's English `pos_tag` uses the `_eng` resource. The import probe
therefore passed without proving that pronunciation worked.

**Fix:** install the language data into `.venv-soulx/nltk_data` using the
README command, then call the real `G2p` rather than only importing it.
On 2026-10-07 the failed lyric's six words passed pronunciation and every
returned phoneme matched SoulX's installed phone set. This does not prove
that inference or audio publication succeeds; those still need a render.

### SoulX reference-audio FFT is unsupported on MPS

**Symptom:** score singing reaches the mel encoder, then fails with
`aten::_fft_r2c` not implemented for MPS.

**Cause:** the installed PyTorch 2.2 runtime cannot run this FFT on Metal.

**Fix:** the score runner enables `PYTORCH_ENABLE_MPS_FALLBACK=1` before
importing PyTorch. Unsupported operations use CPU; the model stays on MPS.
The actual installed `MelSpectrogramEncoder` passed with finite output on
MPS after this change. This operation check does not verify full inference
or publication of the failed song. Voice conversion was not tested here.

### SoulX vocoder complex arithmetic crashes even with MPS fallback

**Symptom:** singing reaches `ISTFTHead`, then complex multiplication raises
an internal MPS assertion.

**Cause:** enabling fallback did not prevent this complex-arithmetic MPS
assertion in PyTorch 2.2. The earlier mel-only check did not reach it.

**Fix:** after the final model move to MPS, the score runner moves only
`model.vocoder.model.head` to CPU and transfers its input with a pre-forward hook.
The backbone and diffusion remain on MPS. The head returns CPU waveform
samples, which the upstream inference path already converts to NumPy for saving.
The installed `Vocoder` wraps `Vocos` under `.model`; `.vocoder.head` does not
exist. The first diagnostic exposed that incorrect path, which was corrected
before requeueing. The upstream clone is not modified. The one-second diagnostic
then completed through the live API, passed the non-silent finite-audio audit,
appeared in library state and served a 1,024-byte player range with HTTP 206.
Import and mel-encoder checks alone had missed the waveform failure.

### HTDemucs will not load without the convert extra

**Symptom:** Separate fails at once with `Model conversion requires the [convert] extras` from `demucs_mlx.mlx_convert`.

**Cause:** `demucs-mlx` is the MLX runtime, and the first load builds its cache from the official PyTorch checkpoint. A plain `demucs-mlx` install does not include `demucs` or `torch`, which that conversion imports. `~/.cache/demucs-mlx` was empty, so every split tried to convert and stopped.

**Fix:** install `demucs-mlx[convert]` in `.venv-demucs`, as the README says. That extra is `demucs>=4.0` and `torch>=2.6`. The first successful load writes `~/.cache/demucs-mlx/htdemucs.safetensors`. Later splits read that file.

### Model dependency conflicts are unresolvable - use separate venvs

ACE-Step 1.5 pins `transformers>=4.51.0,<4.58.0` (v1 pinned `==4.50.0`); MiniMax Music 3
needs `>=5`. There is no shared resolution. Backends declare their own venv in
`synth/backends.py` and run as subprocesses. Don't try to unify them.

---

## Apple Silicon

### Check for an MLX build before downloading anything

**MLX is Apple-native and dramatically more efficient than PyTorch/MPS.** Community MLX
conversions often appear within days of a model release.

We downloaded MiniMax's 54 GB fp32 PyTorch build and ran it at ~13× realtime, when a
**13 GB MLX 8-bit build existed the whole time**. Four times the disk, far slower, and the
efficient build had already been found in the first search.

**Search HuggingFace for `<model> MLX` before downloading. Every time.**

### ACE-Step 1.5 will quietly leave MLX

**Symptom:** a generate works, then takes far longer than the turbo model should,
and the log says PyTorch fallback.

**Cause:** `initialize_service` still returns success when the MLX DiT fails to
load, and continues on PyTorch. The same is true of the planner if `mlx` is
unavailable.

**Fix:** `runners/acestep_runner.py` refuses a DiT that did not set `use_mlx_dit`
and a planner whose backend is not `mlx`. Do not delete those checks.

v1's float32 requirement was the same class of trap: bfloat16 errors on macOS.
1.5's MLX path is the one this machine uses.

### ACE-Step needs float32, not bfloat16

bfloat16 errors on macOS for the v1 pipeline. That pipeline is no longer called.
The note stays because a PyTorch fallback would hit it.

---

## Runtime

### A long render queue hides the library instead of scrolling

**Symptom:** queued cards fill the drawer and existing tracks cannot be reached;
scrolling works again when the queue clears.

**Cause:** only the track list scrolled, while the non-shrinking queue and filters
sat above it, outside that scroll area.

**Fix:** the drawer body scrolls the queue, filters, tracks and library links
together. Its handle stays fixed. The track list no longer has a nested scroller.

### SoulX first-use downloads look like an almost-finished render

**Symptom:** Sing sits at its capped estimated progress, past its time estimate.

**Observed 2026-10-07:** the active runner was downloading incomplete `svs` and
`svc` weight shards over HTTPS. It had not reached generation or UI publication.
The initial SoulX estimate is an unmeasured fallback, not a download estimate.
The runner's unrestricted first snapshot includes both components. No active job
was cancelled or restarted during this diagnosis.

### Working audio and deletion must survive failure paths

**Symptom:** same-named inputs change a queued job's source, deleted audio survives
unseen, or silent separation stems show as invalid.

**Cause:** converted paths reused the source stem; purge discarded metadata even
after unlink errors; history used the non-silent generation audit for Demucs.

**Fix:** unique owned inputs, cleanup on queue completion/failure/removal, retained
purge metadata and server-driven expiry, plus separation-aware history audit.
Cleanup never includes user originals.

Restoring vocal settings must restore both the words and vocal mode. Otherwise
Generate submits no lyrics even though the restored words appear on screen.
SoulX must seed PyTorch before model construction; recording a seed in its
sidecar alone does not control the sampler's noise.

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
| `acestep` | `[Instrumental]` |
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

### Stable Audio below prompt adherence 1 stops following the preset

**Symptom:** a drum and bass preset still writes "drum and bass" into the prompt,
and the track does not come out as drum and bass. The sidecar says
`guidance_scale: 0.0`.

**Cause:** the runner passes that number through as `--cfg`. Stability's CLI
says `1` is the distilled default, so the prompt is followed and the guidance
pass is skipped. A value from `0` up to but not including `1` pulls toward the
unconditional branch. The control allows `0`, and a fresh page starts at `1`.
The four Stable Audio tracks from 01:22 on 2026-09-25 were submitted at `0`.
Every Stable Audio sidecar before that was `1`, including ones built by the
expanded vocabulary.

**Fix:** set Prompt adherence back to `1`. For this model, `1` is the setting
that follows the prompt. `0` is not a milder version of that.

### Welded description lines stop a preset sounding like itself

**Symptom:** jump-up at prompt adherence `1` still came out like liquid. The
sidecar was a real jump-up brief, genre tag included, but the lines read
"a music-box stab sits under the bass drops out for a bar, with the break is
basic".

**Cause:** half of the description prompts glued the drum, bass and lead
clauses with "sits under" and "with". Those clauses are already phrases, so
the join is not English. Jump-up and liquid also share the only genre tag,
`Genre: Drum and Bass`, which this model often renders as the smoother style.

**Fix:** each chosen line is its own sentence. The comma-fragment form, the
one closer to Stability's examples, is unchanged.

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
