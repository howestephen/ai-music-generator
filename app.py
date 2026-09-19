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

.history-audio .waveform-container,
.history-audio .timestamps,
.history-audio .subtitle-display {
    display: none;
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

    const playerFor = (waveform) => {
        const host = waveform.closest(".history-card")
            ?.querySelector(".history-audio #waveform > div");
        return host?.shadowRoot?.querySelector("audio");
    };

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
})();
"""


def _prompt_hint(backend: backends.Backend) -> str:
    if backend.prompt_style == "tags":
        return "Style tags beat sentences: `warm rhodes, 85bpm, mellow`."
    if backend.prompt_style == "description":
        return "Describe the music in a sentence: `a slow cinematic build, low strings`."
    return "Use a structured caption in prose: genre, BPM, key, scale and arrangement."


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


def _enqueue_generation(model, prompt, duration, steps, guidance, seed, use_seed):
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
    chosen_seed = int(seed) if use_seed else random.randint(0, 2**31 - 1)
    payload = {
        "prompt": prompt.strip(),
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
                prompt = gr.Textbox(
                    label="Prompt", lines=3,
                    placeholder="lo-fi hip hop, warm rhodes piano, soft vinyl crackle, 85bpm, instrumental",
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
                                    queue=False,
                                )
                                down.click(
                                    lambda job_id=job["id"]: _move_job(job_id, 1),
                                    outputs=queue_state,
                                    queue=False,
                                )
                                remove.click(
                                    lambda job_id=job["id"]: _remove_job(job_id),
                                    outputs=queue_state,
                                    queue=False,
                                )
                            elif job["status"] == "failed":
                                remove = gr.Button("Dismiss", size="sm")
                                remove.click(
                                    lambda job_id=job["id"]: _remove_job(job_id),
                                    outputs=queue_state,
                                    queue=False,
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
                            gr.Audio(
                                value=track["path"],
                                show_label=False,
                                interactive=False,
                                editable=False,
                                elem_classes="history-audio",
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
        genre.change(_genre_bpm, genre, bpm).then(
            _genre_prompt, [genre, model, bpm], prompt
        )
        regenerate.click(_genre_prompt, [genre, model, bpm], prompt)

        refresh.click(
            _refresh_history,
            outputs=[history, history_signature],
            queue=False,
        )
        request = go.click(
            _generation_started,
            outputs=go,
            queue=False,
            show_progress="hidden",
        )
        submission = request.then(
            _enqueue_generation,
            [model, prompt, duration, steps, guidance, seed, use_seed],
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
        timer = gr.Timer(0.5)
        timer.tick(
            _poll_ui,
            inputs=history_signature,
            outputs=[queue_state, history, history_signature],
            queue=False,
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
