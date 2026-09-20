"""Local web UI. A thin wrapper over synth.core and the generated output folder.

Everything model-specific (licence, prompt style, duration cap and available knobs) is
read from the backend registry. Track history is rebuilt from the WAV files and JSON
sidecars already written by ``core.generate``; the UI owns no second copy of that data.
"""
from __future__ import annotations

import html
import json
import math
import random
import statistics
import tempfile
import threading
from functools import lru_cache
from pathlib import Path

import gradio as gr
import soundfile as sf

from synth import backends, core, jobs, prompting

UI_CSS = """
#generate-button:disabled {
    background: var(--button-secondary-background-fill);
    color: transparent;
    isolation: isolate;
    background-color: var(--button-secondary-background-fill);
    opacity: 1;
    overflow: hidden;
    position: relative;
}

#generate-button:disabled::before {
    animation: generation-progress 1.4s ease-in-out infinite;
    background: var(--button-primary-background-fill);
    content: "";
    inset: 0;
    position: absolute;
    transform: translateX(-105%);
    width: 55%;
    z-index: 0;
}

#generate-button:disabled::after {
    background: var(--button-secondary-background-fill);
    border-radius: var(--button-large-radius);
    color: var(--button-secondary-text-color);
    content: "Generating...";
    left: 50%;
    padding: 0.2rem 0.75rem;
    position: absolute;
    top: 50%;
    transform: translate(-50%, -50%);
    z-index: 1;
}

/* Every column and card must be allowed to shrink, or one long string inside
   makes the whole page scroll sideways on a phone. */
#history-panel,
#controls-panel,
.history-audio,
.history-card,
.queue-job {
    min-width: 0;
}

.history-card,
.queue-job {
    overflow-wrap: anywhere;
}

/* Gradio's own toast is wider than a small phone and would scroll the page. */
.toast-wrap {
    max-width: calc(100vw - 1rem);
}

.history-waveform {
    background: var(--block-background-fill);
    border: 1px solid var(--border-color-primary);
    border-radius: var(--block-radius);
    color: var(--neutral-400);
    cursor: pointer;
    height: 4.25rem;
    overflow: hidden;
    position: relative;
    width: 100%;
}

.history-waveform:focus-visible {
    outline: 2px solid var(--color-accent);
    outline-offset: 2px;
}

.history-waveform svg {
    display: block;
    height: 100%;
    width: 100%;
}

.history-waveform-cursor {
    background: var(--button-primary-background-fill);
    bottom: 0;
    left: var(--waveform-position, 0%);
    pointer-events: none;
    position: absolute;
    top: 0;
    width: 2px;
}

.history-audio {
    display: block;
    margin-top: 0.4rem;
    width: 100%;
}

.queue-job {
    background: var(--block-background-fill);
    border: 1px solid var(--border-color-primary);
    border-radius: var(--block-radius);
    padding: 0.75rem;
}

.queue-job-header {
    align-items: baseline;
    display: flex;
    /* A flex child defaults to min-width:auto and refuses to shrink below its
       content, which is what pushed this header 16px past its own box on a
       phone. Wrapping plus min-width:0 below is the fix, not a narrower font. */
    flex-wrap: wrap;
    gap: 0.35rem 0.75rem;
    justify-content: space-between;
}

.queue-job-title {
    font-weight: 600;
    min-width: 0;
    overflow-wrap: anywhere;
}

.queue-job-status {
    color: var(--body-text-color-subdued);
    font-size: 0.85em;
    white-space: nowrap;
}

.queue-job-summary {
    color: var(--body-text-color-subdued);
    font-size: 0.9em;
    margin-top: 0.35rem;
    /* Prompts and generated filenames carry long unbroken runs. */
    overflow-wrap: anywhere;
}

.queue-job-track {
    background: var(--button-secondary-background-fill);
    border-radius: var(--button-large-radius);
    height: 3.25rem;
    margin-top: 0.65rem;
    overflow: hidden;
    position: relative;
}

.queue-job-fill {
    background: var(--button-primary-background-fill);
    bottom: 0;
    left: 0;
    position: absolute;
    top: 0;
    transition: width 0.5s linear;
    width: var(--job-progress, 0%);
}

.queue-job.queued .queue-job-fill {
    animation: queued-job-wipe 1.4s ease-in-out infinite;
    transform: translateX(-105%);
    width: 55%;
}

.queue-job.failed {
    border-color: var(--error-background-fill);
}

/* Clicked by the polling loop in UI_JS; never shown, but must stay clickable. */
#poll-button {
    height: 0;
    margin: 0;
    min-height: 0;
    opacity: 0;
    overflow: hidden;
    padding: 0;
    pointer-events: none;
    position: absolute;
}

@keyframes queued-job-wipe {
    from { transform: translateX(-105%); }
    to { transform: translateX(190%); }
}

@keyframes generation-progress {
    from { transform: translateX(-105%); }
    to { transform: translateX(190%); }
}

@media (prefers-reduced-motion: reduce) {
    #generate-button:disabled::before,
    .queue-job.queued .queue-job-fill {
        animation: none;
        transform: translateX(40%);
    }
}
"""

UI_JS = """
(() => {
    const wiredPlayers = new WeakSet();

    // A plain <audio> rendered by _history_player, no longer a Gradio component
    // hiding one inside a shadow root.
    const playerFor = (waveform) => waveform.closest(".history-card")
        ?.querySelector("audio.history-audio");

    const showPosition = (waveform, audio) => {
        if (!Number.isFinite(audio.duration) || audio.duration === 0) return;
        const percent = Math.max(0, Math.min(100, audio.currentTime / audio.duration * 100));
        waveform.style.setProperty("--waveform-position", `${percent}%`);
        waveform.setAttribute("aria-valuenow", `${Math.round(percent)}`);
    };

    // Each history card owns its own <audio>, so without this every track you start
    // layers on top of whatever is already playing.
    const everyPlayer = () => [...document.querySelectorAll(".history-waveform")]
        .map(playerFor)
        .filter(Boolean);

    const pauseEveryOtherPlayer = (playing) => {
        everyPlayer().forEach((other) => {
            if (other !== playing && !other.paused) other.pause();
        });
    };

    const wirePlayers = () => {
        document.querySelectorAll(".history-waveform").forEach((waveform) => {
            const audio = playerFor(waveform);
            if (!audio || wiredPlayers.has(audio)) return;
            wiredPlayers.add(audio);
            ["loadedmetadata", "seeking", "timeupdate"]
                .forEach((eventName) => audio.addEventListener(
                    eventName,
                    () => showPosition(waveform, audio),
                ));
            audio.addEventListener("play", () => pauseEveryOtherPlayer(audio));
            showPosition(waveform, audio);
        });
    };

    // Drives the queue and history refresh. gr.Timer is inert in this Gradio
    // build, so the poll is a hidden button clicked from here.
    let pollTimer = null;
    const startPolling = () => {
        if (pollTimer) return;
        pollTimer = setInterval(() => {
            document.querySelector("#poll-button")?.click();
        }, 1000);
    };

    const seek = (waveform, position) => {
        const audio = playerFor(waveform);
        if (!audio || !Number.isFinite(audio.duration)) return;
        audio.currentTime = Math.max(0, Math.min(1, position)) * audio.duration;
        showPosition(waveform, audio);
    };

    document.addEventListener("click", (event) => {
        const waveform = event.target.closest(".history-waveform");
        if (!waveform) return;
        const bounds = waveform.getBoundingClientRect();
        seek(waveform, (event.clientX - bounds.left) / bounds.width);
    });

    document.addEventListener("keydown", (event) => {
        const waveform = event.target.closest(".history-waveform");
        if (!waveform || !["ArrowLeft", "ArrowRight"].includes(event.key)) return;
        const audio = playerFor(waveform);
        if (!audio || !Number.isFinite(audio.duration)) return;
        event.preventDefault();
        const seconds = event.key === "ArrowLeft" ? -5 : 5;
        seek(waveform, (audio.currentTime + seconds) / audio.duration);
    });

    new MutationObserver(() => requestAnimationFrame(wirePlayers))
        .observe(document.body, {childList: true, subtree: true});
    requestAnimationFrame(wirePlayers);
    startPolling();
})();
"""


def _prompt_hint(backend: backends.Backend) -> str:
    if backend.prompt_style == "tags":
        return "Style tags beat sentences: `warm rhodes, 85bpm, mellow`."
    if backend.prompt_style == "description":
        return "Describe the music in a sentence: `a slow cinematic build, low strings`."
    return "Use a structured caption in prose: genre, BPM, key, scale and arrangement."


def _structure_plan(bpm, *bar_counts):
    """Build the section timeline from the bar boxes, or nothing if all are empty."""
    try:
        bars = dict(zip(prompting.SECTION_NAMES, (float(c or 0) for c in bar_counts)))
        return prompting.plan_sections(float(bpm or 120), bars)
    except (TypeError, ValueError):
        return []


def _structure_preview(bpm, *bar_counts):
    plan = _structure_plan(bpm, *bar_counts)
    if not plan:
        return "No structure set: the genre's own arrangement is described instead."
    total = prompting.structure_total(plan)
    rows = " · ".join(
        f"**{section['name']}** {section['start']:.0f}-{section['end']:.0f}s"
        for section in plan
    )
    total_bars = sum(section["bars"] for section in plan)
    return (
        f"{rows}\n\n{total_bars:g} bars, **{total:.0f}s** total at {float(bpm or 120):g} "
        "BPM. The track length follows this. Stable Audio has no structural input, so "
        "this is described to it, not enforced; use **Rework a section** to force one."
    )


def _structure_duration(model, bpm, *bar_counts):
    """Track length follows the arrangement, clamped to what the backend allows."""
    plan = _structure_plan(bpm, *bar_counts)
    if not plan:
        return gr.skip()
    total = prompting.structure_total(plan)
    control = backends.get(model).duration
    if control.maximum is not None:
        total = min(total, control.maximum)
    return gr.update(value=max(control.minimum, round(total)))


def _compose_prompt(genre, model, bpm, mood, vocals, instruments, character, keywords,
                    *bar_counts):
    """Build the prompt from the menu selections, in the backend's own style."""
    if not genre:
        return gr.skip()
    backend = backends.get(model)
    wants_vocals = vocals == "With vocals"
    return prompting.build_prompt(
        genre,
        style=backend.prompt_style,
        bpm=int(bpm) if bpm else None,
        mood=None if not mood or mood == prompting.RANDOM_CHOICE else mood,
        instruments=tuple(instruments or ()),
        character=tuple(character or ()),
        vocals=wants_vocals,
        extra=keywords or "",
        structure=prompting.describe_structure(_structure_plan(bpm, *bar_counts)),
    )


def _voice_updates(model: str, vocals: str):
    """Lyrics only exist where the model has a channel for them."""
    backend = backends.get(model)
    wants_vocals = vocals == "With vocals"
    return gr.update(visible=backend.supports_lyrics and wants_vocals)


def _mood_choices(genre: str | None):
    options = [prompting.RANDOM_CHOICE, *prompting.mood_options(genre)]
    return gr.update(choices=options, value=prompting.RANDOM_CHOICE)


def _genre_prompt(genre: str | None, model: str, bpm: float | None = None) -> str:
    """Build a fresh prompt in the selected backend's own prompt style.

    Called on every genre change and on every press of Regenerate, so each press
    is a new variation rather than the same text.
    """
    if not genre:
        return ""
    tempo = int(bpm) if bpm else None
    return prompting.build_prompt(
        genre, style=backends.get(model).prompt_style, bpm=tempo,
    )


def _genre_bpm(genre: str | None) -> float | int:
    """The genre's typical tempo, so the BPM control follows the dropdown."""
    if not genre or genre not in prompting.GENRES:
        return gr.update()
    return prompting.GENRES[genre].default_bpm()


def _backend_summary(model: str) -> str:
    backend = backends.get(model)
    availability = "Configured" if backend.available else "Setup missing"
    return (
        f"**{backend.model_id}**  \n"
        f"{availability} · {backend.licence} · maximum {backend.max_duration:.0f}s  \n"
        f"{backend.notes}"
    )


def _control_value(control: backends.NumericControl, current=None) -> int | float:
    """Keep a valid current value, otherwise clamp it into the selected model's range."""
    try:
        value = float(current)
    except (TypeError, ValueError, OverflowError):
        value = control.default
    if not math.isfinite(value):
        value = control.default
    value = max(control.minimum, value)
    if control.maximum is not None:
        value = min(control.maximum, value)
    return int(value) if control.integer else value


def _control_update(
    control: backends.NumericControl | None,
    current=None,
    preserve_current: bool = False,
):
    if control is None:
        return gr.update(visible=False)
    value = _control_value(control, current) if preserve_current else control.default
    return gr.update(
        minimum=control.minimum,
        maximum=control.maximum,
        step=control.step,
        value=value,
        label=control.label,
        info=control.info,
        visible=True,
    )


def _control_envelope(attribute: str) -> tuple[float, float | None, float]:
    controls = [
        control
        for backend in backends.BACKENDS.values()
        if (control := getattr(backend, attribute)) is not None
    ]
    minimum = min(control.minimum for control in controls)
    maximum = (
        None
        if any(control.maximum is None for control in controls)
        else max(control.maximum for control in controls)
    )
    return minimum, maximum, min(control.step for control in controls)


def _model_updates(model, duration, genre, bpm):
    backend = backends.get(model)
    prompt = _genre_prompt(genre, model, bpm) if genre else gr.update()
    return (
        _backend_summary(model),
        _control_update(backend.duration, duration, preserve_current=True),
        _control_update(backend.steps),
        _control_update(backend.guidance),
        _prompt_hint(backend),
        prompt,
    )


@lru_cache(maxsize=512)
def _history_audio_audit(
    path_string: str,
    modified_ns: int,
) -> tuple[backends.AudioAudit | None, str | None]:
    """Fully audit a WAV once per file revision, including its sample stream."""
    del modified_ns  # Cache key: a replaced file is audited again.
    try:
        return backends.audit_audio_file(Path(path_string), "history"), None
    except RuntimeError as exc:
        return None, str(exc)


def _load_history(output_dir: Path | None = None) -> list[dict]:
    output_dir = Path(output_dir) if output_dir else core.OUTPUT_DIR
    if not output_dir.exists():
        return []

    tracks = []
    for path in output_dir.glob("*.wav"):
        metadata = {}
        try:
            metadata = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError, UnicodeError):
            pass
        if not isinstance(metadata, dict):
            metadata = {}
        try:
            modified_ns = path.stat().st_mtime_ns
        except OSError:
            continue
        requested_duration = metadata.get("requested_duration", metadata.get("duration"))
        audio_audit, audit_error = _history_audio_audit(str(path), modified_ns)
        measured_duration = audio_audit.duration_seconds if audio_audit else None
        audio_frames = audio_audit.frames if audio_audit else None
        sample_rate = audio_audit.sample_rate if audio_audit else None
        channels = audio_audit.channels if audio_audit else None
        file_bytes = audio_audit.file_bytes if audio_audit else None

        duration_ratio = None
        audit_status = "invalid" if measured_duration is None else "unverified"
        try:
            target = float(requested_duration)
            if not math.isfinite(target) or target <= 0:
                raise ValueError
            if measured_duration is not None:
                duration_ratio = measured_duration / target
                backend = backends.BACKENDS.get(str(metadata.get("backend")))
                if backend is not None:
                    minimum = backend.output_audit.minimum_duration(target)
                    maximum = backend.output_audit.maximum_duration(target)
                    if measured_duration < minimum:
                        audit_status = "short"
                    elif measured_duration > maximum:
                        audit_status = "long"
                    else:
                        audit_status = "passed"
        except (TypeError, ValueError, OverflowError):
            requested_duration = None
        tracks.append({
            "path": str(path),
            "name": path.name,
            "modified_ns": modified_ns,
            "backend": metadata.get("backend", "unknown model"),
            "duration": measured_duration,
            "requested_duration": requested_duration,
            "duration_ratio": duration_ratio,
            "audit_status": audit_status,
            "audit_error": audit_error,
            "audio_frames": audio_frames,
            "sample_rate": sample_rate,
            "channels": channels,
            "file_bytes": file_bytes,
            "elapsed_seconds": metadata.get("elapsed_seconds"),
            "seed": metadata.get("seed"),
            "prompt": metadata.get("prompt", "Prompt unavailable"),
            "generated_at": metadata.get("generated_at", "Time unavailable"),
        })
    return sorted(tracks, key=lambda item: (item["modified_ns"], item["name"]), reverse=True)


def _history_copy(track: dict) -> str:
    details = [html.escape(str(track["backend"]))]
    if track["duration"] is not None:
        try:
            delivered = float(track["duration"])
            if math.isfinite(delivered):
                details.append(f"{delivered:.1f}s delivered")
        except (TypeError, ValueError, OverflowError):
            pass
    if track.get("requested_duration") is not None:
        try:
            target = float(track["requested_duration"])
            if math.isfinite(target):
                details.append(f"{target:g}s target")
        except (TypeError, ValueError, OverflowError):
            pass
    audit_status = track.get("audit_status")
    if audit_status in {"short", "long", "invalid"}:
        details.append(str(audit_status).upper())
    if track["seed"] is not None:
        details.append(f"seed {html.escape(str(track['seed']))}")
    return (
        f"**{html.escape(track['name'])}**  \n"
        f"{' · '.join(details)} · {html.escape(str(track['generated_at']))}  \n"
        f"{html.escape(str(track['prompt']))}"
    )


@lru_cache(maxsize=256)
def _waveform_peaks(path_string: str, modified_ns: int, bars: int = 120) -> tuple[float, ...]:
    del modified_ns  # Part of the cache key, so a replaced WAV is read again.
    try:
        with sf.SoundFile(path_string) as audio:
            if len(audio) == 0:
                return ()
            peaks = []
            for index in range(bars):
                start = round(index * len(audio) / bars)
                end = round((index + 1) * len(audio) / bars)
                audio.seek(start)
                samples = audio.read(end - start, dtype="float32", always_2d=True)
                peaks.append(float(abs(samples).max()) if samples.size else 0.0)
    except (OSError, RuntimeError, ValueError):
        return ()
    return tuple(peaks)


def _history_player(track: dict) -> str:
    """A plain audio element served straight from `output/`.

    `gr.Audio` postprocesses its value by copying the file into Gradio's temp
    cache, and the whole history is re-rendered whenever a render finishes. With
    a dozen 67 MB tracks that copied about a gigabyte per update, which blocked
    the server long enough for the queue timer to stop and the card to freeze at
    "0s elapsed". `launch(allowed_paths=...)` already lets the browser fetch the
    real file, with range requests, so nothing needs copying.
    """
    src = html.escape(f"/gradio_api/file={Path(track['path']).resolve()}", quote=True)
    return (
        f'<audio class="history-audio" controls preload="none" src="{src}"></audio>'
    )


def _history_waveform(track: dict) -> str:
    peaks = _waveform_peaks(track["path"], track["modified_ns"])
    if not peaks:
        bars = '<text x="50" y="22" text-anchor="middle">Waveform unavailable</text>'
    else:
        peak_max = max(peaks) or 1.0
        rects = []
        for index, peak in enumerate(peaks):
            height = max(1.0, peak / peak_max * 34)
            rects.append(
                f'<rect x="{index + 0.15:g}" y="{20 - height / 2:g}" '
                f'width="0.7" height="{height:g}" rx="0.25" />'
            )
        bars = "".join(rects)
    label = html.escape(f"Seek through {track['name']}", quote=True)
    return (
        f'<div class="history-waveform" role="slider" tabindex="0" '
        f'aria-label="{label}" aria-valuemin="0" aria-valuemax="100" '
        'aria-valuenow="0">'
        '<svg viewBox="0 0 120 40" preserveAspectRatio="none" aria-hidden="true">'
        f'{bars}</svg><span class="history-waveform-cursor"></span></div>'
    )


# Stability's runtime reads init audio as 44.1 kHz 16-bit PCM. Everything this
# project renders with Stable Audio already matches; ACE-Step writes 48 kHz, so a
# track from there cannot be reworked without a conversion step.
EDIT_SAMPLE_RATE = 44100
BEATS_PER_BAR = prompting.BEATS_PER_BAR
BAR_CHOICES = (8, 16, 32, 64, 128)
SECTION_MODE = "Rework one section"
REMIX_MODE = "Remix the whole track"


def _bars_to_seconds(bpm: float, bars: float) -> float:
    """Bars are the musical unit; the model only takes seconds."""
    return bars * BEATS_PER_BAR * 60.0 / float(bpm)


def _prepare_edit_source(path_string: str) -> tuple[Path, str | None]:
    """Return a WAV the runtime will accept, converting the file if it has to.

    Stability's runtime reads 44.1 kHz 16-bit PCM. An Ableton bounce at 48 kHz or a
    320 kbps MP3 is a perfectly reasonable thing to hand it, so convert rather than
    refuse. A conversion is written beside the original as a new file; nothing the
    user supplied is ever overwritten.
    """
    source = Path(path_string)
    with sf.SoundFile(str(source)) as handle:
        rate, subtype, frames = handle.samplerate, handle.subtype, len(handle)
    if rate == EDIT_SAMPLE_RATE and subtype == "PCM_16":
        return source, None

    import numpy as np

    data, _ = sf.read(str(source), dtype="float32", always_2d=True)
    if rate != EDIT_SAMPLE_RATE:
        # Linear resample. Good enough for a model input, and it avoids adding a
        # dependency for something the model's own encoder will re-analyse anyway.
        target_frames = int(round(len(data) * EDIT_SAMPLE_RATE / rate))
        source_index = np.linspace(0, len(data) - 1, target_frames)
        data = np.stack(
            [np.interp(source_index, np.arange(len(data)), data[:, channel])
             for channel in range(data.shape[1])],
            axis=1,
        )
    if data.shape[1] == 1:
        data = np.repeat(data, 2, axis=1)
    # Not output/: a converted input is not a generated asset, and anything left
    # in output/ appears in the track history as a sidecar-less mystery file.
    converted = Path(tempfile.gettempdir()) / f"sa3-input-{source.stem}-44k1.wav"
    sf.write(str(converted), data, EDIT_SAMPLE_RATE, subtype="PCM_16")
    return converted, (
        f"converted {rate} Hz {subtype} to {EDIT_SAMPLE_RATE} Hz 16-bit"
    )


def _editable_track_choices() -> list[tuple[str, str]]:
    choices = []
    for track in _load_history():
        if track["duration"] is None:
            continue
        label = f"{track['backend']} · {track['duration']:.0f}s · {track['name'][:44]}"
        choices.append((label, track["path"]))
    return choices


def _edit_span(track_path: str | None, bpm: float, start_bar: float, bars: float):
    """Describe the span a bar selection covers, or why it cannot be used."""
    if not track_path:
        return "Pick a track to rework."
    try:
        audit, error = _history_audio_audit(
            track_path, Path(track_path).stat().st_mtime_ns
        )
    except OSError:
        return "That track is no longer on disk."
    if audit is None:
        return f"That file is not readable audio: {error}"
    total = audit.duration_seconds
    start = _bars_to_seconds(bpm, max(0.0, start_bar - 1))
    end = start + _bars_to_seconds(bpm, bars)
    bar_seconds = _bars_to_seconds(bpm, 1)
    total_bars = total / bar_seconds if bar_seconds else 0
    if end > total:
        return (
            f"**Out of range.** Bars {start_bar:g} to {start_bar + bars - 1:g} end at "
            f"{end:.1f}s but the track is {total:.1f}s (about {total_bars:.0f} bars "
            f"at {bpm:g} BPM)."
        )
    return (
        f"Regenerating **{start:.1f}s to {end:.1f}s** "
        f"(bars {start_bar:g} to {start_bar + bars - 1:g} of about {total_bars:.0f}, "
        f"one bar = {bar_seconds:.2f}s). Everything outside is kept."
    )


_JOB_QUEUE: jobs.GenerationQueue | None = None
_JOB_QUEUE_LOCK = threading.Lock()


def _run_queued_job(payload: dict) -> core.Track:
    request = dict(payload)
    retries = int(request.pop("_duration_retries", 0))
    retry_seed = bool(request.pop("_retry_seed", False))
    for attempt in range(retries + 1):
        try:
            return core.generate(**request)
        except core.OutputAuditError as exc:
            if not retry_seed or attempt >= retries:
                attempts = attempt + 1
                raise jobs.GenerationFailure(
                    f"Duration audit failed after {attempts} attempt"
                    f"{'s' if attempts != 1 else ''}: {exc}",
                    summary_updates={"seed": request["seed"]},
                ) from exc
            next_seed = random.randint(0, 2**31 - 1)
            if next_seed == request["seed"]:
                next_seed = (next_seed + 1) % (2**31)
            request["seed"] = next_seed
    raise AssertionError("unreachable duration retry state")


def _get_job_queue() -> jobs.GenerationQueue:
    global _JOB_QUEUE
    if _JOB_QUEUE is None:
        with _JOB_QUEUE_LOCK:
            if _JOB_QUEUE is None:
                _JOB_QUEUE = jobs.GenerationQueue(_run_queued_job)
    return _JOB_QUEUE


def _queue_snapshot() -> list[dict]:
    return _get_job_queue().snapshot()


# How long a render takes per second of audio, before this backend has any history.
# Measured on this machine, 2026-09-19.
# Render cost is a fixed overhead plus a per-second rate, NOT a multiple of track
# length: a 380s Stable Audio render takes less wall time than a 180s one did,
# because model load and decode dominate. Treating it as a ratio made a 26-second
# job crawl against a 95-second estimate and read as hung. Measured on this
# machine, 2026-09-19, as (overhead seconds, seconds per second of audio).
FALLBACK_COST = {
    "acestep": (20.0, 2.4),
    "minimax-mlx": (30.0, 3.2),
    "musicgen": (25.0, 14.0),
    "stable-audio-sm": (3.0, 0.03),
    "stable-audio-medium": (12.0, 0.05),
}
# Only the most recent renders count: the first render of any backend also pays for
# a multi-gigabyte weight download, which is not render time.
COST_SAMPLE = 6


def _estimate_runtime(model: str, duration: float) -> float:
    """Expected wall time for one render, fitted from this backend's own history."""
    samples = []
    for track in _load_history():
        if track["backend"] != model:
            continue
        try:
            track_duration = float(track.get("requested_duration", track.get("duration")))
            elapsed = float(track["elapsed_seconds"])
        except (TypeError, ValueError, OverflowError):
            continue
        if (
            math.isfinite(track_duration)
            and math.isfinite(elapsed)
            and track_duration > 0
            and elapsed > 0
        ):
            samples.append((track_duration, elapsed))
        if len(samples) >= COST_SAMPLE:  # _load_history is newest first
            break

    overhead, rate = FALLBACK_COST.get(model, (20.0, 3.0))
    lengths = {length for length, _ in samples}
    if len(samples) >= 3 and len(lengths) >= 2:
        # Enough spread to fit the line rather than trust the measured constants.
        try:
            fit = statistics.linear_regression(
                [length for length, _ in samples], [taken for _, taken in samples]
            )
            if fit.slope > 0 and fit.intercept + fit.slope * duration > 0:
                overhead, rate = fit.intercept, fit.slope
        except (statistics.StatisticsError, ValueError):
            pass
    elif samples:
        # One length only: scale that measurement, keeping the known overhead shape.
        length, taken = samples[0]
        rate = max((taken - overhead) / length, 0.0) if taken > overhead else rate

    return max(5.0, overhead + rate * float(duration))


def _editable_track_choices_update():
    return gr.update(choices=_editable_track_choices())


def _enqueue_edit(model, track_path, upload, prompt, bpm, start_bar, bars, steps,
                  guidance, mode=SECTION_MODE, noise=0.6):
    """Rework one span of a track, or remix the whole thing.

    A section rework masks a range and keeps everything outside it. A whole-track
    remix starts from the audio instead of noise and lets `noise` decide how far it
    travels: low keeps melody and rhythm, high keeps only timbre and tonality.
    """
    backend = backends.get(model)
    if not backend.supports_editing:
        raise gr.Error(f"{backend.name} cannot rework audio. Pick a Stable Audio model.")
    track_path = upload or track_path
    if not track_path:
        raise gr.Error("Pick a track from the history, or upload one.")
    note = None
    try:
        track_path, note = _prepare_edit_source(str(track_path))
    except (OSError, RuntimeError, ValueError) as exc:
        raise gr.Error(f"Could not read that audio: {exc}") from exc
    track_path = str(track_path)
    if not prompt or not prompt.strip():
        raise gr.Error("Describe what the section should become.")
    source = Path(track_path)
    try:
        audit, error = _history_audio_audit(str(source), source.stat().st_mtime_ns)
    except OSError as exc:
        raise gr.Error(f"That track is no longer readable: {exc}") from exc
    if audit is None:
        raise gr.Error(f"That file is not readable audio: {error}")
    if audit.sample_rate != EDIT_SAMPLE_RATE:
        raise gr.Error(
            f"Rework needs {EDIT_SAMPLE_RATE} Hz input and conversion did not produce "
            f"it (got {audit.sample_rate} Hz)."
        )
    if duration_cap := backend.duration.maximum:
        if audit.duration_seconds > duration_cap:
            raise gr.Error(
                f"That track is {audit.duration_seconds:.0f}s; {backend.name} caps at "
                f"{duration_cap:g}s. Rework a shorter track."
            )
    whole_track = mode == REMIX_MODE
    start = _bars_to_seconds(bpm, max(0.0, start_bar - 1))
    end = start + _bars_to_seconds(bpm, bars)
    duration = audit.duration_seconds
    if whole_track:
        start, end = 0.0, duration
    elif end > duration:
        # core.generate would refuse this too, but only on the worker thread, where
        # it becomes a failed card instead of an answer to the button you pressed.
        raise gr.Error(
            f"Bars {start_bar:g}-{start_bar + bars - 1:g} end at {end:.1f}s but the "
            f"track is only {duration:.1f}s. Pick fewer bars or a later tempo."
        )
    try:
        duration = backend.duration.validate(duration, f"{backend.name} duration")
        steps = (
            backend.steps.validate(steps, f"{backend.name} steps")
            if backend.steps is not None else None
        )
        guidance = (
            backend.guidance.validate(guidance, f"{backend.name} guidance")
            if backend.guidance is not None else None
        )
    except ValueError as exc:
        raise gr.Error(str(exc)) from exc

    chosen_seed = random.randint(0, 2**31 - 1)
    payload = {
        "prompt": prompt.strip(),
        "duration": duration,
        "seed": chosen_seed,
        "infer_step": steps,
        "guidance_scale": guidance,
        "model": backend.name,
        "init_audio": str(source),
        "inpaint_range": None if whole_track else (start, end),
        "init_noise_level": float(noise) if whole_track else None,
        # An exact contract already forbids retries, and a rework is deliberate.
        "_duration_retries": 0,
        "_retry_seed": False,
    }
    label = (
        f"remix whole track at {float(noise):g}" if whole_track
        else f"rework {start:.1f}-{end:.1f}s"
    )
    summary = {
        "model": backend.name,
        "model_id": backend.model_id,
        "prompt": f"{label} · {prompt.strip()}",
        "duration": duration,
        "seed": chosen_seed,
    }
    queue = _get_job_queue()
    queue.enqueue(payload, summary, _estimate_runtime(model, duration))
    detail = f" · {note}" if note else ""
    if whole_track:
        headline = (
            f"**Queued a whole-track remix of {source.name[:40]}** · "
            f"change {float(noise):g} · seed `{chosen_seed}`{detail}"
        )
    else:
        headline = (
            f"**Queued a rework of {source.name[:40]}** · bars {start_bar:g}-"
            f"{start_bar + bars - 1:g} ({start:.1f}s to {end:.1f}s) · "
            f"seed `{chosen_seed}`{detail}"
        )
    return headline, queue.snapshot()


def _enqueue_generation(model, prompt, duration, steps, guidance, seed,
                        use_seed, lyrics=None):
    if not prompt or not prompt.strip():
        raise gr.Error("Enter a prompt first.")
    backend = backends.get(model)
    try:
        duration = backend.duration.validate(duration, f"{backend.name} duration")
        steps = (
            backend.steps.validate(steps, f"{backend.name} steps")
            if backend.steps is not None else None
        )
        guidance = (
            backend.guidance.validate(guidance, f"{backend.name} guidance")
            if backend.guidance is not None else None
        )
    except ValueError as exc:
        raise gr.Error(str(exc)) from exc
    words = (lyrics or "").strip()
    if words and not backend.supports_lyrics:
        raise gr.Error(
            f"{backend.name} has no lyrics channel, so it cannot sing words. "
            "MiniMax and ACE-Step can."
        )
    chosen_seed = int(seed) if use_seed else random.randint(0, 2**31 - 1)
    payload = {
        "prompt": prompt.strip(),
        "lyrics": words or None,
        "duration": duration,
        "seed": chosen_seed,
        "infer_step": steps,
        "guidance_scale": guidance,
        "model": backend.name,
        "_duration_retries": backend.output_audit.random_seed_retries if not use_seed else 0,
        "_retry_seed": not use_seed,
    }
    summary = {
        "model": backend.name,
        "model_id": backend.model_id,
        "prompt": prompt.strip(),
        "duration": duration,
        "seed": chosen_seed,
    }
    queue = _get_job_queue()
    queue.enqueue(payload, summary, _estimate_runtime(model, duration))
    status = (
        f"**Queued {backend.name}** · {duration:g}s target · seed `{chosen_seed}`  \n"
        "The Generate button is ready for another job. The delivered WAV will be audited"
        + (" and retried once with a new seed if it is short." if not use_seed else ".")
    )
    return status, chosen_seed, queue.snapshot()


def _history_signature(output_dir: Path | None = None) -> tuple[tuple[str, int], ...]:
    output_dir = Path(output_dir) if output_dir else core.OUTPUT_DIR
    if not output_dir.exists():
        return ()
    signature = []
    for pattern in ("*.wav", "*.json"):
        for path in output_dir.glob(pattern):
            try:
                signature.append((path.name, path.stat().st_mtime_ns))
            except OSError:
                continue
    return tuple(sorted(signature))


def _refresh_history():
    return _load_history(), _history_signature()


def _queue_items_for_render(_session_value=None):
    """Use browser state only as a refresh signal; the server queue is authoritative."""
    return _queue_snapshot()


def _history_items_for_render(_session_value=None):
    """Rebuild each browser's view from the shared output folder."""
    return _load_history()


def _poll_ui(previous_signature):
    current_signature = _history_signature()
    history = _load_history() if current_signature != previous_signature else gr.skip()
    return _get_job_queue().snapshot(), history, current_signature


def _move_job(job_id: str, direction: int):
    return _get_job_queue().move(job_id, direction)


def _remove_job(job_id: str):
    return _get_job_queue().remove(job_id)


def _queue_job_html(job: dict) -> str:
    status_labels = {
        "queued": f"Queued #{job.get('queue_position', 1)}",
        "running": (
            f"Rendering · {job.get('elapsed_seconds') or 0:.0f}s elapsed · "
            f"estimated {job['progress']:g}%"
        ),
        "complete": "Finishing",
        "failed": "Failed",
    }
    prompt = html.escape(str(job["prompt"]))
    if len(prompt) > 180:
        prompt = f"{prompt[:177]}..."
    details = (
        f"{html.escape(str(job['model']))} · {float(job['duration']):g}s target · "
        f"seed {html.escape(str(job['seed']))}"
    )
    error = ""
    if job.get("error"):
        error = f'<div class="queue-job-summary">{html.escape(str(job["error"]))}</div>'
    return (
        f'<div class="queue-job {html.escape(job["status"])}" '
        f'style="--job-progress: {float(job["progress"]):g}%">'
        '<div class="queue-job-header">'
        f'<span class="queue-job-title">{details}</span>'
        f'<span class="queue-job-status">{status_labels[job["status"]]}</span>'
        '</div>'
        f'<div class="queue-job-summary">{prompt}</div>{error}'
        '<div class="queue-job-track"><span class="queue-job-fill"></span></div>'
        '</div>'
    )


def _generation_started():
    return gr.update(value="Generating...", interactive=False, variant="secondary")


def _generation_finished():
    return gr.update(value="Generate", interactive=True, variant="primary")


def build_ui() -> gr.Blocks:
    initial_backend = backends.get(core.DEFAULT_MODEL)
    duration_minimum, duration_maximum, duration_step = _control_envelope("duration")
    steps_minimum, steps_maximum, steps_step = _control_envelope("steps")
    guidance_minimum, guidance_maximum, guidance_step = _control_envelope("guidance")
    initial_steps = initial_backend.steps or next(
        backend.steps for backend in backends.BACKENDS.values() if backend.steps is not None
    )
    initial_guidance = initial_backend.guidance or next(
        backend.guidance
        for backend in backends.BACKENDS.values()
        if backend.guidance is not None
    )
    model_choices = [
        (f"{name} · {backend.model_id}", name)
        for name, backend in backends.BACKENDS.items()
    ]
    with gr.Blocks(title="Background Music Generator") as demo:
        gr.Markdown("# Background Music Generator\nLocal instrumental music, generated on this machine.")

        with gr.Row(equal_height=False):
            with gr.Column(scale=1, elem_id="controls-panel"):
                model = gr.Dropdown(
                    choices=model_choices,
                    value=core.DEFAULT_MODEL,
                    label="Model",
                )
                model_summary = gr.Markdown(_backend_summary(core.DEFAULT_MODEL))
                with gr.Tabs():
                    with gr.Tab("New track"):
                        with gr.Row():
                            genre = gr.Dropdown(
                                choices=prompting.genre_names(), label="Genre", value=None,
                                scale=3,
                                info="Writes a prompt in this model's own style. Then edit it.",
                            )
                            regenerate = gr.Button("Regenerate", scale=1)
                        bpm = gr.Slider(
                            50, 200, value=120, step=1, label="Tempo (BPM)",
                            info="Written into the prompt. No model takes a tempo directly.",
                        )
                        with gr.Row():
                            mood = gr.Dropdown(
                                choices=[prompting.RANDOM_CHOICE],
                                value=prompting.RANDOM_CHOICE, label="Mood",
                            )
                            vocals = gr.Radio(
                                choices=["Instrumental", "With vocals"],
                                value="Instrumental", label="Voice",
                            )
                        instruments = gr.Dropdown(
                            choices=prompting.instrument_options(), multiselect=True,
                            label="Instruments", value=[],
                            info="Empty uses the genre's own instrumentation.",
                        )
                        character = gr.Dropdown(
                            choices=prompting.character_options(), multiselect=True,
                            label="Character", value=[],
                            info="Recording space, effects and era. Empty varies it.",
                        )
                        with gr.Accordion("Structure (bars)", open=False):
                            gr.Markdown(
                                "Lay the arrangement out in bars. Leave all at 0 to let "
                                "the genre decide."
                            )
                            with gr.Row():
                                section_bars = [
                                    gr.Number(
                                        value=0, precision=0, minimum=0, maximum=512,
                                        label=name,
                                    )
                                    for name in prompting.SECTION_NAMES
                                ]
                            structure_preview = gr.Markdown(
                                "No structure set: the genre's own arrangement is "
                                "described instead."
                            )
                        keywords = gr.Textbox(
                            label="Extra keywords", lines=1,
                            placeholder="amen break, jungle, ragga chops",
                            info="Folded into the prompt below.",
                        )
                        lyrics = gr.Textbox(
                            label="Lyrics", lines=3, visible=False,
                            placeholder="[verse]\nfirst line here",
                            info="Only models with a lyrics channel can sing words.",
                        )
                        prompt = gr.Textbox(
                            label="Prompt (composed from the menus above)", lines=4,
                            placeholder="Pick a genre, or type your own prompt here.",
                        )
                        prompt_help = gr.Markdown(_prompt_hint(initial_backend))
                        with gr.Row():
                            # Components use the union of every backend's schema so Gradio's
                            # static API preprocessor never rejects a value that is valid for
                            # another model. The selected backend narrows these in the browser,
                            # and the submission handler enforces the same backend contract.
                            duration = gr.Slider(
                                duration_minimum, duration_maximum,
                                value=initial_backend.duration.default,
                                step=duration_step,
                                label=initial_backend.duration.label,
                                info=initial_backend.duration.info,
                            )
                            steps = gr.Number(
                                value=initial_steps.default,
                                minimum=steps_minimum,
                                maximum=steps_maximum,
                                step=steps_step,
                                precision=0,
                                label=initial_steps.label,
                                info=initial_steps.info,
                                visible=initial_backend.steps is not None,
                            )
                        with gr.Row():
                            guidance = gr.Slider(
                                guidance_minimum, guidance_maximum,
                                value=initial_guidance.default,
                                step=guidance_step,
                                label=initial_guidance.label,
                                info=initial_guidance.info,
                                visible=initial_backend.guidance is not None,
                            )
                            seed = gr.Number(value=42, precision=0, label="Seed")
                        use_seed = gr.Checkbox(
                            value=False, label="Lock seed",
                            info="Off = new random seed each time. On = reproduce an exact track.",
                        )
                        go = gr.Button("Generate", variant="primary", elem_id="generate-button")
                        status = gr.Markdown("Ready to queue a generation.")

                        # The only bar-accurate structural control this model family has.
                        # Before generation, structure is prose; afterwards, a span can be
                        # regenerated in place, and bars convert to seconds from the tempo.
                    with gr.Tab("Rework a section"):
                        gr.Markdown(
                            "Regenerate part of a finished track and keep the rest. "
                            "Stable Audio only."
                        )
                        edit_track = gr.Dropdown(
                            choices=_editable_track_choices(),
                            label="Track from history", value=None,
                        )
                        edit_upload = gr.Audio(
                            label="Or upload a track",
                            type="filepath",
                            sources=["upload"],
                        )
                        edit_mode = gr.Radio(
                            choices=[SECTION_MODE, REMIX_MODE], value=SECTION_MODE,
                            label="What to change",
                        )
                        edit_noise = gr.Slider(
                            0.1, 1.2, value=0.6, step=0.05, visible=False,
                            label="Amount of change",
                            info="Low keeps the melody and rhythm and swaps the sounds; "
                                 "high keeps only the timbre and tonality.",
                        )
                        with gr.Row() as edit_bars_row:
                            edit_bpm = gr.Number(
                                value=120, label="Tempo (BPM)", precision=0,
                                minimum=20, maximum=300,
                            )
                            edit_start_bar = gr.Number(
                                value=33, label="From bar", precision=0, minimum=1,
                            )
                            edit_bars = gr.Dropdown(
                                choices=[str(count) for count in BAR_CHOICES],
                                value="32", label="Length (bars)",
                            )
                        edit_span = gr.Markdown("Pick a track to rework.")
                        edit_prompt = gr.Textbox(
                            label="This section becomes", lines=2,
                            placeholder="a stripped breakdown, no drums, just pads and a "
                                        "filtered vocal texture",
                        )
                        edit_go = gr.Button("Rework section", variant="secondary")
                        edit_status = gr.Markdown("")

            with gr.Column(scale=1, elem_id="history-panel"):
                gr.Markdown("## Render queue")
                queue_state = gr.State([])

                @gr.render(inputs=queue_state)
                def render_queue(session_queue_items):
                    queue_items = _queue_items_for_render(session_queue_items)
                    if not queue_items:
                        gr.Markdown("No queued renders.")
                    for job in queue_items:
                        with gr.Group(key=f"job-{job['id']}"):
                            gr.HTML(_queue_job_html(job))
                            if job["status"] == "queued":
                                with gr.Row():
                                    up = gr.Button("Move up", size="sm")
                                    down = gr.Button("Move down", size="sm")
                                    remove = gr.Button("Remove", size="sm")
                                up.click(
                                    lambda job_id=job["id"]: _move_job(job_id, -1),
                                    outputs=queue_state,
                                )
                                down.click(
                                    lambda job_id=job["id"]: _move_job(job_id, 1),
                                    outputs=queue_state,
                                )
                                remove.click(
                                    lambda job_id=job["id"]: _remove_job(job_id),
                                    outputs=queue_state,
                                )
                            elif job["status"] == "failed":
                                remove = gr.Button("Dismiss", size="sm")
                                remove.click(
                                    lambda job_id=job["id"]: _remove_job(job_id),
                                    outputs=queue_state,
                                )

                with gr.Row():
                    gr.Markdown("## Track history")
                    refresh = gr.Button("Refresh history", size="sm")
                history = gr.State([])
                history_signature = gr.State(_history_signature())

                @gr.render(inputs=history)
                def render_history(session_tracks):
                    tracks = _history_items_for_render(session_tracks)
                    if not tracks:
                        gr.Markdown("No generated tracks yet.")
                        return
                    for track in tracks:
                        with gr.Group(elem_classes="history-card"):
                            gr.HTML(
                                _history_waveform(track),
                                key=f"waveform-{track['path']}",
                            )
                            gr.HTML(
                                _history_player(track),
                                key=f"audio-{track['path']}",
                            )
                            gr.Markdown(
                                _history_copy(track),
                                key=f"details-{track['path']}",
                            )

        model.change(
            _model_updates,
            [model, duration, genre, bpm],
            [model_summary, duration, steps, guidance, prompt_help, prompt],
        )
        demo.load(
            _model_updates,
            [model, duration, genre, bpm],
            [model_summary, duration, steps, guidance, prompt_help, prompt],
            queue=False,
        )
        compose_inputs = [genre, model, bpm, mood, vocals, instruments, character,
                          keywords, *section_bars]
        # Any menu change recomposes the prompt, so the text always reflects the
        # selections rather than drifting away from them.
        genre.change(_mood_choices, genre, mood).then(
            _genre_bpm, genre, bpm
        ).then(_compose_prompt, compose_inputs, prompt)
        genre.select(_mood_choices, genre, mood).then(
            _genre_bpm, genre, bpm
        ).then(_compose_prompt, compose_inputs, prompt)
        for control in (bpm, mood, vocals, instruments, character, keywords):
            control.change(_compose_prompt, compose_inputs, prompt)
        # Changing the arrangement redraws its timeline, sets the track length from
        # the total, and rewrites the prompt to describe it.
        for control in (bpm, *section_bars):
            control.change(
                _structure_preview, [bpm, *section_bars], structure_preview
            ).then(
                _structure_duration, [model, bpm, *section_bars], duration
            ).then(_compose_prompt, compose_inputs, prompt)
        for control in (mood, instruments, character):
            control.select(_compose_prompt, compose_inputs, prompt)
        regenerate.click(_compose_prompt, compose_inputs, prompt)
        for control in (model, vocals):
            control.change(_voice_updates, [model, vocals], lyrics)

        refresh.click(
            _refresh_history,
            outputs=[history, history_signature],
        )
        def _span_update(path, bpm, start, bars):
            return _edit_span(
                path, float(bpm or 120), float(start or 1), float(bars or 32)
            )

        span_inputs = [edit_track, edit_bpm, edit_start_bar, edit_bars]
        for control in span_inputs:
            control.change(_span_update, span_inputs, edit_span)
        # A dropdown reports a user's pick as `select`, not `change`, so without this
        # the span never updates when you choose a track.
        for control in (edit_track, edit_bars):
            control.select(_span_update, span_inputs, edit_span)
        refresh.click(_editable_track_choices_update, outputs=edit_track)
        # Bars belong to a section rework; the change amount belongs to a whole-track
        # remix. Showing both at once invites setting one that is ignored.
        edit_mode.change(
            lambda mode: (
                gr.update(visible=mode == SECTION_MODE),
                gr.update(visible=mode == SECTION_MODE),
                gr.update(visible=mode == REMIX_MODE),
            ),
            edit_mode,
            [edit_bars_row, edit_span, edit_noise],
        )
        edit_go.click(
            lambda model, path, upload, prompt, bpm, start, bars, steps, guidance, mode, noise: (
                _enqueue_edit(
                    model, path, upload, prompt, float(bpm or 120), float(start or 1),
                    float(bars or 32), steps, guidance, mode, noise,
                )
            ),
            [model, edit_track, edit_upload, edit_prompt, edit_bpm, edit_start_bar,
             edit_bars, steps, guidance, edit_mode, edit_noise],
            [edit_status, queue_state],
        )
        request = go.click(
            _generation_started,
            outputs=go,
            queue=False,
            show_progress="hidden",
        )
        submission = request.then(
            _enqueue_generation,
            [model, prompt, duration, steps, guidance, seed, use_seed, lyrics],
            [status, seed, queue_state],
            show_progress="hidden",
        )
        submission.success(
            _generation_finished,
            outputs=go,
            queue=False,
            show_progress="hidden",
        )
        submission.failure(
            _generation_finished,
            outputs=go,
            queue=False,
            show_progress="hidden",
        )
        # gr.Timer does not fire in Gradio 6.17.3 here: a Blocks app containing
        # nothing but a Timer never ticks either, queued or not. The queue card
        # therefore froze at "0s elapsed" while the render finished normally.
        # This app's own JS does run, so it drives the poll instead.
        poll = gr.Button("Refresh queue", elem_id="poll-button", visible=True)
        poll.click(
            _poll_ui,
            inputs=history_signature,
            outputs=[queue_state, history, history_signature],
            show_progress="hidden",
        )
    return demo


def main(share: bool = False, port: int = 7860) -> None:
    # Gradio serves only from paths it has been told about. Tracks are read back from
    # `output/` by absolute path, so without this every player 403s and renders silent.
    build_ui().launch(
        share=share,
        server_port=port,
        inbrowser=True,
        css=UI_CSS,
        js=UI_JS,
        allowed_paths=[str(core.OUTPUT_DIR)],
    )


if __name__ == "__main__":
    main()
