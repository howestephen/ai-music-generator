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
import re
import shutil
import statistics
import tempfile
import threading
import time
from functools import lru_cache
from pathlib import Path

import gradio as gr
import soundfile as sf

from synth import backends, core, jobs, prompting

# Deleted tracks sit here for one hour, then the WAV and sidecar are removed for good.
PENDING_DELETE_DIR = ".pending-delete"
UNDO_WINDOW_SECONDS = 3600
PENDING_META_SUFFIX = ".pending.json"

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

.history-title {
    font-size: 1.15rem;
    font-weight: 650;
    margin: 0.15rem 0 0.1rem;
    overflow-wrap: anywhere;
}

.history-meta {
    color: var(--body-text-color-subdued);
    font-size: 0.9em;
    margin: 0 0 0.45rem;
    overflow-wrap: anywhere;
}

.history-details {
    color: var(--body-text-color-subdued);
    font-size: 0.9em;
    margin-top: 0.55rem;
    overflow-wrap: anywhere;
}

.history-details summary {
    cursor: pointer;
    font-weight: 600;
    margin-bottom: 0.35rem;
}

.history-pending {
    background: var(--block-background-fill);
    border: 1px solid var(--border-color-primary);
    border-radius: var(--block-radius);
    margin-bottom: 0.65rem;
    padding: 0.55rem 0.75rem;
}

/* Gradio only opens a dropdown when the small arrow is hit. Make the whole
   control the hit target so the label text and field body also open it. */
#controls-panel .dropdown-arrow,
#history-panel .dropdown-arrow {
    pointer-events: none;
}

#controls-panel [data-testid="dropdown"] .wrap,
#history-panel [data-testid="dropdown"] .wrap,
#controls-panel .wrap.svelte-1hfxr4,
#history-panel .wrap.svelte-1hfxr4 {
    cursor: pointer;
}

#controls-panel [data-testid="dropdown"] input,
#history-panel [data-testid="dropdown"] input {
    caret-color: transparent;
    cursor: pointer;
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


def _compose_prompt(genre, model, bpm, mood, vocals, instruments, character, keywords):
    """Build the prompt from the menu selections, in the backend's own style."""
    if not genre:
        return gr.skip()
    backend = backends.get(model)
    wants_vocals = vocals in ("With vocals", "Vocal texture")
    return prompting.build_prompt(
        genre,
        style=backend.prompt_style,
        bpm=int(bpm) if bpm else None,
        mood=None if not mood or mood == prompting.RANDOM_CHOICE else mood,
        instruments=tuple(instruments or ()),
        character=tuple(character or ()),
        vocals=wants_vocals,
        extra=keywords or "",
    )


def _voice_choice_labels(model: str) -> tuple[list[str], str]:
    """Honest labels: lyrics backends can sing; Stable Audio only textures."""
    backend = backends.get(model)
    if backend.supports_lyrics:
        return (
            ["Instrumental", "With vocals"],
            "Models with a lyrics channel can sing words when lyrics are provided.",
        )
    return (
        ["Instrumental", "Vocal texture"],
        "Stable Audio never sings words; this only asks for a wordless vocal texture "
        "in the prompt.",
    )


def _voice_updates(model: str, vocals: str):
    """Keep the voice control honest for the selected backend, and show lyrics only
    where a lyrics channel exists."""
    backend = backends.get(model)
    choices, info = _voice_choice_labels(model)
    wants_vocals = vocals in ("With vocals", "Vocal texture")
    return (
        gr.update(choices=choices, value=choices[1] if wants_vocals else choices[0], info=info),
        gr.update(visible=backend.supports_lyrics and wants_vocals),
    )


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


def _pending_root(output_dir: Path | None = None) -> Path:
    root = Path(output_dir) if output_dir else core.OUTPUT_DIR
    pending = root / PENDING_DELETE_DIR
    pending.mkdir(parents=True, exist_ok=True)
    return pending


def _display_title(track: dict) -> str:
    title = track.get("title")
    if isinstance(title, str) and title.strip():
        return title.strip()
    prompt = str(track.get("prompt") or "")
    if prompt and prompt != "Prompt unavailable":
        words = [
            word for word in re.findall(r"[A-Za-z][A-Za-z'-]*", prompt) if len(word) > 2
        ][:4]
        if words:
            return " ".join(words)
    return str(track.get("name") or "Untitled")


def _normalise_rating(value) -> str | None:
    if value in (None, "", "none"):
        return None
    if value in ("keep", "discard"):
        return value
    return None


def _read_sidecar(path: Path) -> dict:
    try:
        metadata = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError, UnicodeError):
        return {}
    return metadata if isinstance(metadata, dict) else {}


def _write_sidecar_update(wav_path: Path, updates: dict) -> dict:
    metadata = _read_sidecar(wav_path)
    metadata.update(updates)
    if "path" not in metadata:
        metadata["path"] = wav_path.name
    target = wav_path.with_suffix(".json")
    target.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def filter_history(
    tracks: list[dict],
    *,
    genre: str | None = None,
    rating: str | None = None,
    query: str | None = None,
) -> list[dict]:
    """View-only filter. Never touches files."""
    genre_filter = (genre or "").strip()
    rating_raw = (rating or "any").strip().lower() if isinstance(rating, str) else "any"
    if rating_raw in ("", "any", "none"):
        rating_filter = "any"
    elif rating_raw == "unrated":
        rating_filter = "unrated"
    elif rating_raw in ("keep", "discard"):
        rating_filter = rating_raw
    else:
        rating_filter = "any"
    needle = (query or "").strip().lower()
    results = []
    for track in tracks:
        if genre_filter and genre_filter not in ("", "any"):
            if str(track.get("genre") or "") != genre_filter:
                continue
        track_rating = _normalise_rating(track.get("rating"))
        if rating_filter == "unrated":
            if track_rating is not None:
                continue
        elif rating_filter != "any" and track_rating != rating_filter:
            continue
        if needle:
            haystack = " ".join(
                str(part or "")
                for part in (track.get("title"), track.get("prompt"), track.get("name"))
            ).lower()
            if needle not in haystack:
                continue
        results.append(track)
    return results


def _pending_entries(output_dir: Path | None = None) -> list[dict]:
    pending = _pending_root(output_dir)
    entries = []
    for meta_path in pending.glob(f"*{PENDING_META_SUFFIX}"):
        try:
            payload = json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, UnicodeError):
            continue
        if not isinstance(payload, dict):
            continue
        try:
            deleted_at = float(payload.get("deleted_at"))
        except (TypeError, ValueError, OverflowError):
            continue
        stem = meta_path.name[: -len(PENDING_META_SUFFIX)]
        wav = pending / f"{stem}.wav"
        sidecar = pending / f"{stem}.json"
        if not wav.is_file():
            continue
        entries.append({
            "stem": stem,
            "deleted_at": deleted_at,
            "expires_at": deleted_at + UNDO_WINDOW_SECONDS,
            "wav": wav,
            "sidecar": sidecar,
            "meta": meta_path,
            "title": payload.get("title") or stem,
            "name": f"{stem}.wav",
        })
    return sorted(entries, key=lambda item: item["deleted_at"], reverse=True)


def purge_expired_deletions(
    output_dir: Path | None = None,
    *,
    now: float | None = None,
) -> int:
    """Permanently remove pending deletions whose undo window has elapsed."""
    clock = time.time() if now is None else now
    removed = 0
    for entry in _pending_entries(output_dir):
        if entry["expires_at"] > clock:
            continue
        for path in (entry["wav"], entry["sidecar"], entry["meta"]):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        removed += 1
    return removed


def delete_track(path_string: str, output_dir: Path | None = None) -> list[dict]:
    """Move a track out of the library into the one-hour undo area."""
    output_dir = Path(output_dir) if output_dir else core.OUTPUT_DIR
    wav = Path(path_string)
    if wav.parent.resolve() != output_dir.resolve():
        raise ValueError("can only delete tracks from the library folder")
    if not wav.is_file() or wav.suffix.lower() != ".wav":
        raise FileNotFoundError(f"track not found: {wav}")
    sidecar = wav.with_suffix(".json")
    pending = _pending_root(output_dir)
    metadata = _read_sidecar(wav)
    destination_wav = pending / wav.name
    destination_sidecar = pending / sidecar.name
    destination_meta = pending / f"{wav.stem}{PENDING_META_SUFFIX}"
    if destination_wav.exists() or destination_meta.exists():
        raise FileExistsError(f"a pending deletion already uses {wav.name}")
    shutil.move(str(wav), str(destination_wav))
    if sidecar.is_file():
        shutil.move(str(sidecar), str(destination_sidecar))
    destination_meta.write_text(
        json.dumps({
            "deleted_at": time.time(),
            "title": metadata.get("title") or _display_title({
                "title": metadata.get("title"),
                "prompt": metadata.get("prompt"),
                "name": wav.name,
            }),
            "name": wav.name,
        }),
        encoding="utf-8",
    )
    return _load_history(output_dir)


def undo_delete(stem: str, output_dir: Path | None = None) -> list[dict]:
    """Restore a pending deletion back into the library."""
    output_dir = Path(output_dir) if output_dir else core.OUTPUT_DIR
    pending = _pending_root(output_dir)
    entry = next((item for item in _pending_entries(output_dir) if item["stem"] == stem), None)
    if entry is None:
        raise FileNotFoundError(f"no pending deletion for {stem!r}")
    if entry["expires_at"] <= time.time():
        purge_expired_deletions(output_dir)
        raise FileNotFoundError(f"undo window expired for {stem!r}")
    destination_wav = output_dir / entry["wav"].name
    destination_sidecar = output_dir / entry["sidecar"].name
    if destination_wav.exists():
        raise FileExistsError(f"library already has {destination_wav.name}")
    shutil.move(str(entry["wav"]), str(destination_wav))
    if entry["sidecar"].is_file():
        shutil.move(str(entry["sidecar"]), str(destination_sidecar))
    entry["meta"].unlink(missing_ok=True)
    return _load_history(output_dir)


def set_track_rating(
    path_string: str,
    rating: str | None,
    output_dir: Path | None = None,
) -> list[dict]:
    """Persist keep/discard on the sidecar. Never deletes the track."""
    output_dir = Path(output_dir) if output_dir else core.OUTPUT_DIR
    wav = Path(path_string)
    if wav.parent.resolve() != output_dir.resolve():
        raise ValueError("can only rate tracks in the library folder")
    if not wav.is_file():
        raise FileNotFoundError(f"track not found: {wav}")
    normalised = _normalise_rating(rating)
    if rating not in (None, "", "none", "keep", "discard") and normalised is None:
        raise ValueError(f"rating must be keep, discard or none (got {rating!r})")
    _write_sidecar_update(wav, {"rating": normalised})
    return _load_history(output_dir)


def _load_history(output_dir: Path | None = None) -> list[dict]:
    output_dir = Path(output_dir) if output_dir else core.OUTPUT_DIR
    if not output_dir.exists():
        return []

    tracks = []
    for path in output_dir.glob("*.wav"):
        metadata = _read_sidecar(path)
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

        title = metadata.get("title")
        if not isinstance(title, str) or not title.strip():
            title = None
        genre = metadata.get("genre")
        if not isinstance(genre, str) or not genre.strip():
            genre = None
        track = {
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
            "title": title,
            "rating": _normalise_rating(metadata.get("rating")),
            "genre": genre,
        }
        track["display_title"] = _display_title(track)
        tracks.append(track)
    return sorted(tracks, key=lambda item: (item["modified_ns"], item["name"]), reverse=True)


def _history_heading(track: dict) -> str:
    title = html.escape(_display_title(track))
    bits = []
    if track.get("genre"):
        bits.append(html.escape(str(track["genre"])))
    if track["duration"] is not None:
        try:
            delivered = float(track["duration"])
            if math.isfinite(delivered):
                bits.append(f"{delivered:.1f}s")
        except (TypeError, ValueError, OverflowError):
            pass
    rating = _normalise_rating(track.get("rating"))
    if rating:
        bits.append(rating)
    meta = " · ".join(bits) if bits else "No genre recorded"
    return (
        f'<div class="history-title">{title}</div>'
        f'<div class="history-meta">{meta}</div>'
    )


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
    sample_rate = track.get("sample_rate")
    if sample_rate is not None:
        details.append(f"{html.escape(str(sample_rate))} Hz")
    if track.get("elapsed_seconds") is not None:
        details.append(f"{html.escape(str(track['elapsed_seconds']))}s render")
    body = (
        f"<div>{' · '.join(details)} · {html.escape(str(track['generated_at']))}</div>"
        f"<div>{html.escape(str(track['prompt']))}</div>"
    )
    return (
        f'<details class="history-details">'
        f"<summary>Details</summary>"
        f"{body}"
        f"</details>"
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
        label = (
            f"{_display_title(track)} · {track['backend']} · "
            f"{track['duration']:.0f}s"
        )
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
    # Init-audio remixes of long tracks are much slower than text-to-audio of the
    # same length. A 347s remix took 221s here while the txt2audio fit predicted ~29s.
    estimate = max(_estimate_runtime(model, duration), float(duration) * 0.5, 60.0)
    queue.enqueue(payload, summary, estimate)
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
                        use_seed, lyrics=None, genre=None):
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
    chosen_genre = str(genre).strip() if genre else None
    payload = {
        "prompt": prompt.strip(),
        "lyrics": words or None,
        "duration": duration,
        "seed": chosen_seed,
        "infer_step": steps,
        "guidance_scale": guidance,
        "model": backend.name,
        "genre": chosen_genre or None,
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
    pending = output_dir / PENDING_DELETE_DIR
    if pending.exists():
        for path in pending.iterdir():
            try:
                signature.append((f"{PENDING_DELETE_DIR}/{path.name}", path.stat().st_mtime_ns))
            except OSError:
                continue
    return tuple(sorted(signature))


def _refresh_history():
    purge_expired_deletions()
    return _load_history(), _history_signature()


def _genre_filter_choices(tracks: list[dict] | None = None) -> list[str]:
    known = ["any", *prompting.genre_names()]
    present = sorted({
        str(track.get("genre"))
        for track in (tracks or [])
        if track.get("genre")
    })
    for genre in present:
        if genre not in known:
            known.append(genre)
    return known


def _rate_track_ui(path, rating):
    return set_track_rating(path, rating), _history_signature()


def _delete_track_ui(path):
    return delete_track(path), _history_signature()


def _undo_delete_ui(stem):
    return undo_delete(stem), _history_signature()


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


def _queue_status_text(job: dict) -> str:
    elapsed = float(job.get("elapsed_seconds") or 0)
    expected = float(job.get("expected_seconds") or 0)
    if job["status"] == "queued":
        return f"Queued #{job.get('queue_position', 1)}"
    if job["status"] == "running":
        # Estimated progress caps at 95% until the worker finishes. A long remix of a
        # 347s track sat there for minutes after the estimate and read as hung.
        if expected > 0 and elapsed > expected:
            return (
                f"Rendering · {elapsed:.0f}s elapsed · past {expected:.0f}s estimate"
            )
        return (
            f"Rendering · {elapsed:.0f}s elapsed · "
            f"estimated {job['progress']:g}%"
        )
    if job["status"] == "complete":
        return "Finishing"
    return "Failed"


def _queue_job_html(job: dict) -> str:
    status_text = _queue_status_text(job)
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
        f'<span class="queue-job-status">{status_text}</span>'
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
                        genre = gr.Dropdown(
                            choices=prompting.genre_names(), label="Genre", value=None,
                            info="Writes a prompt in this model's own style. Then edit it.",
                        )
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
                                choices=_voice_choice_labels(core.DEFAULT_MODEL)[0],
                                value="Instrumental", label="Voice",
                                info=_voice_choice_labels(core.DEFAULT_MODEL)[1],
                            )
                        with gr.Accordion("Advanced", open=False):
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
                        with gr.Row():
                            prompt = gr.Textbox(
                                label="Prompt (composed from the menus above)", lines=4,
                                placeholder="Pick a genre, or type your own prompt here.",
                                scale=4,
                            )
                            regenerate = gr.Button("Regenerate", scale=1)
                        prompt_help = gr.Markdown(_prompt_hint(initial_backend))
                        gr.Markdown("#### Render settings")
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

                    with gr.Tab("Remix a track"):
                        gr.Markdown(
                            "Start from a finished track and push it toward a new prompt. "
                            "Stable Audio only. The whole track is re-rendered, so a long "
                            "source takes as long as generating one of the same length."
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
                        edit_noise = gr.Slider(
                            0.1, 1.2, value=0.6, step=0.05,
                            label="Amount of change",
                            info="Low keeps the melody and rhythm and swaps the sounds; "
                                 "high keeps only the timbre and tonality.",
                        )
                        edit_prompt = gr.Textbox(
                            label="Become", lines=2,
                            placeholder="a VIP remix, tighter drums, brighter lead",
                        )
                        edit_go = gr.Button("Remix track", variant="secondary")
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
                with gr.Row():
                    filter_genre = gr.Dropdown(
                        choices=_genre_filter_choices(),
                        value="any",
                        label="Genre filter",
                    )
                    filter_rating = gr.Dropdown(
                        choices=["any", "keep", "discard", "unrated"],
                        value="any",
                        label="Rating filter",
                    )
                filter_query = gr.Textbox(
                    label="Search title or prompt",
                    lines=1,
                    placeholder="liquid amen",
                )
                history = gr.State([])
                history_signature = gr.State(_history_signature())
                history_filters = [history, filter_genre, filter_rating, filter_query]

                @gr.render(inputs=history_filters)
                def render_history(session_tracks, genre_value, rating_value, query_value):
                    pending = [
                        entry for entry in _pending_entries()
                        if entry["expires_at"] > time.time()
                    ]
                    for entry in pending:
                        remaining = max(0, int(entry["expires_at"] - time.time()))
                        minutes = remaining // 60
                        with gr.Group(elem_classes="history-pending", key=f"pending-{entry['stem']}"):
                            gr.HTML(
                                f'<div>Deleted <strong>{html.escape(str(entry["title"]))}</strong>'
                                f' · Undo for {minutes}m</div>'
                            )
                            undo = gr.Button("Undo delete", size="sm")
                            undo.click(
                                lambda stem=entry["stem"]: _undo_delete_ui(stem),
                                outputs=[history, history_signature],
                            )
                    tracks = filter_history(
                        _history_items_for_render(session_tracks),
                        genre=genre_value,
                        rating=rating_value,
                        query=query_value,
                    )
                    if not tracks:
                        if _history_items_for_render(session_tracks):
                            gr.Markdown("No tracks match these filters.")
                        else:
                            gr.Markdown("No generated tracks yet.")
                        return
                    for track in tracks:
                        with gr.Group(elem_classes="history-card"):
                            gr.HTML(
                                _history_heading(track),
                                key=f"heading-{track['path']}",
                            )
                            gr.HTML(
                                _history_waveform(track),
                                key=f"waveform-{track['path']}",
                            )
                            gr.HTML(
                                _history_player(track),
                                key=f"audio-{track['path']}",
                            )
                            gr.HTML(
                                _history_copy(track),
                                key=f"details-{track['path']}",
                            )
                            with gr.Row():
                                keep = gr.Button("Keep", size="sm")
                                discard = gr.Button("Discard", size="sm")
                                clear = gr.Button("Clear rating", size="sm")
                                delete = gr.Button("Delete", size="sm")
                            keep.click(
                                lambda path=track["path"]: _rate_track_ui(path, "keep"),
                                outputs=[history, history_signature],
                            )
                            discard.click(
                                lambda path=track["path"]: _rate_track_ui(path, "discard"),
                                outputs=[history, history_signature],
                            )
                            clear.click(
                                lambda path=track["path"]: _rate_track_ui(path, None),
                                outputs=[history, history_signature],
                            )
                            delete.click(
                                lambda path=track["path"]: _delete_track_ui(path),
                                outputs=[history, history_signature],
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
                          keywords]
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
        for control in (mood, instruments, character):
            control.select(_compose_prompt, compose_inputs, prompt)
        regenerate.click(_compose_prompt, compose_inputs, prompt)
        for control in (model, vocals):
            control.change(_voice_updates, [model, vocals], [vocals, lyrics])

        refresh.click(
            _refresh_history,
            outputs=[history, history_signature],
        )
        refresh.click(_editable_track_choices_update, outputs=edit_track)
        edit_go.click(
            lambda model, path, upload, prompt, steps, guidance, noise: (
                _enqueue_edit(
                    model, path, upload, prompt, 120, 1, 32, steps, guidance,
                    REMIX_MODE, noise,
                )
            ),
            [model, edit_track, edit_upload, edit_prompt, steps, guidance, edit_noise],
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
            [model, prompt, duration, steps, guidance, seed, use_seed, lyrics, genre],
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
    """Serve the React UI. `share` is ignored: the page stays on this machine."""
    del share
    purge_expired_deletions()
    from synth.ui_server import serve

    serve(port)


if __name__ == "__main__":
    main()
