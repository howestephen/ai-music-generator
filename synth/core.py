"""Core generation. Prompt models go through `generate`. A mix is split by `separate`."""
from __future__ import annotations

import json
import math
import os
import random
import re
import time
import warnings

from . import backends, prompting
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path

VALID_RATINGS = (None, "keep", "discard")

# Hugging Face's Xet transfer backend hangs on the first model download here:
# four 0-byte .incomplete files and no progress. Forcing plain HTTPS transfer fixes it.
# Must be set before anything imports huggingface_hub.
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

# torchaudio routes saves through TorchCodec and warns about `format`/`backend` args
# that ACE-Step passes anyway. Harmless, and it drowns out real output.
warnings.filterwarnings("ignore", message=".*not used by TorchCodec.*")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
PROMPTS_DIR = PROJECT_ROOT / "prompts"

DEFAULT_MODEL = backends.DEFAULT_BACKEND


@dataclass
class Track:
    """A generated track and everything needed to reproduce it.

    `backend` is the registry key (what `--model` takes); `model` is the weights id.
    `infer_step` and `guidance_scale` are None when the backend has no such control,
    so the sidecar never claims a setting that did not apply.
    `title`, `rating` and `genre` are library fields: a short generated name, an
    optional keep/discard label, and the UI genre when one was selected. Old
    sidecars omit them; loaders must tolerate that.
    """

    path: Path
    prompt: str
    duration: float
    requested_duration: float
    duration_ratio: float
    audit_status: str
    audio_frames: int
    sample_rate: int
    channels: int
    file_bytes: int
    peak_amplitude: float
    seed: int
    infer_step: int | None
    guidance_scale: float | None
    lyrics: str
    backend: str
    model: str
    dtype: str
    generated_at: str
    elapsed_seconds: float
    title: str
    rating: str | None = None
    genre: str | None = None

    def sidecar_path(self) -> Path:
        return self.path.with_suffix(".json")

    def write_sidecar(self) -> Path:
        data = asdict(self)
        data["path"] = self.path.name  # relative: the folder may get moved
        target = self.sidecar_path()
        target.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return target


class OutputAuditError(RuntimeError):
    """A creative asset was retained, but it did not satisfy its output contract."""

    def __init__(
        self,
        track: Track,
        minimum_duration: float,
        maximum_duration: float = math.inf,
    ):
        self.track = track
        self.minimum_duration = minimum_duration
        self.maximum_duration = maximum_duration
        # Decided from the bounds, not the track's status field, so the message is
        # right for any caller that constructs this directly.
        if track.duration > maximum_duration:
            bound = f"maximum accepted is {maximum_duration:.2f}s"
            kept = "Overlong output retained"
        else:
            bound = f"minimum accepted is {minimum_duration:.2f}s"
            kept = "Short output retained"
        super().__init__(
            f"{track.backend} returned {track.duration:.2f}s for a "
            f"{track.requested_duration:g}s target; {bound}. {kept} at {track.path}"
        )


def _slug(text: str, max_len: int = 48) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len].rstrip("-") or "track"


def _reserve_output_path(output_dir: Path, stem: str) -> tuple[Path, Path]:
    """Atomically reserve a path across concurrent CLI and server processes."""
    suffix = 2
    candidate = output_dir / f"{stem}.wav"
    while True:
        reservation = candidate.with_suffix(".wav.lock")
        try:
            descriptor = os.open(reservation, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            candidate = output_dir / f"{stem}_{suffix}.wav"
            suffix += 1
            continue
        os.close(descriptor)
        if candidate.exists():
            reservation.unlink()
            candidate = output_dir / f"{stem}_{suffix}.wav"
            suffix += 1
            continue
        return candidate, reservation


def _resolve(backend: backends.Backend, knob: str, value, default):
    """Apply the backend's own default, or refuse a value it cannot honour."""
    if default is None:
        if value is not None:
            raise ValueError(f"{backend.name} has no {knob} control (got {value!r})")
        return None
    return value if value is not None else default


def generate(
    prompt: str,
    duration: float | None = None,
    seed: int | None = None,
    infer_step: int | None = None,
    guidance_scale: float | None = None,
    lyrics: str | None = None,
    output_dir: Path | None = None,
    model: str = DEFAULT_MODEL,
    init_audio: Path | str | None = None,
    init_noise_level: float | None = None,
    inpaint_range: tuple[float, float] | None = None,
    genre: str | None = None,
    rating: str | None = None,
) -> Track:
    """Generate one track.

    Prompt style depends on the backend. ACE-Step 1.5 and MusicGen want comma-separated
    style tags ("lo-fi hip hop, warm rhodes, 85bpm"). MiniMax wants a Structured
    Caption in prose, which is where its BPM/key/scale control lives:
    "Genre: cinematic orchestral. BPM: 120. Key: D. Scale: Mixolydian. Arrangement: ..."
    Check `backends.get(model).prompt_style`.

    `infer_step` and `guidance_scale` default to the backend's own values. Passing one
    to a backend that has no such control raises rather than being dropped.

    `seed` is recorded in the sidecar so a track you like can be reproduced or
    nudged one parameter at a time. Omit it for a random one.

    `init_audio` starts from an existing WAV instead of noise. With `inpaint_range`
    (start, end in seconds) only that span is regenerated and the rest is preserved,
    which is the one route to bar-accurate structural edits. `init_noise_level` sets
    how far a plain audio-to-audio pass may travel from the original. A backend that
    cannot edit refuses all three rather than ignoring them.
    """
    if not prompt.strip():
        raise ValueError("prompt is empty")

    backend = backends.get(model)
    if backend.task != "generate":
        raise ValueError(f"{backend.name} is a {backend.task} tool, not a prompt model")
    # None means "whatever this backend considers a track". Hardcoding a number here
    # gave a 60-second clip from a model that makes six-minute ones, on every caller
    # that did not pass one, which was the whole CLI.
    if duration is None:
        duration = backend.duration.default
    if not backend.available:
        raise RuntimeError(
            f"Backend {backend.name!r} is not set up: {backend.availability_error}. "
            "See README for install steps."
        )
    duration = backend.duration.validate(duration, f"{backend.name} duration")

    steps = _resolve(backend, "step count", infer_step, backend.default_steps)
    if steps is not None:
        steps = backend.steps.validate(steps, f"{backend.name} steps")
    guidance = _resolve(backend, "guidance", guidance_scale, backend.default_guidance)
    if guidance is not None:
        guidance = backend.guidance.validate(guidance, f"{backend.name} guidance")

    # Each backend spells 'no vocals' differently, and one has no lyrics channel at all.
    if lyrics is not None and not backend.supports_lyrics:
        raise ValueError(f"{backend.name} has no lyrics channel (got {lyrics!r})")
    if lyrics is None:
        lyrics = backend.instrumental_tag

    edit_request = init_audio is not None or inpaint_range is not None
    if edit_request and not backend.supports_editing:
        raise ValueError(
            f"{backend.name} cannot edit existing audio; it has no init-audio or "
            "inpaint support"
        )
    if init_audio is not None:
        init_audio = Path(init_audio)
        if not init_audio.is_file():
            raise ValueError(f"init audio is not a file: {init_audio}")
    elif inpaint_range is not None:
        raise ValueError("inpaint_range needs init_audio to inpaint into")
    if init_noise_level is not None:
        if init_audio is None:
            raise ValueError("init_noise_level needs init_audio")
        if not math.isfinite(init_noise_level) or init_noise_level < 0:
            raise ValueError(
                f"init_noise_level must be a non-negative number (got {init_noise_level!r})"
            )
    if inpaint_range is not None:
        try:
            span_start, span_end = (float(value) for value in inpaint_range)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"inpaint_range must be two numbers (got {inpaint_range!r})") from exc
        if not (math.isfinite(span_start) and math.isfinite(span_end)):
            raise ValueError("inpaint_range must be finite")
        if span_start < 0 or span_end <= span_start:
            raise ValueError(
                f"inpaint_range must be an increasing span inside the track "
                f"(got {span_start:g} to {span_end:g})"
            )
        if span_end > float(duration):
            raise ValueError(
                f"inpaint_range ends at {span_end:g}s, past the {duration:g}s target"
            )
        inpaint_range = (span_start, span_end)

    output_dir = Path(output_dir) if output_dir else OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    if seed is None:
        seed = random.randint(0, 2**31 - 1)

    if rating not in VALID_RATINGS:
        raise ValueError(f"rating must be one of {VALID_RATINGS!r} (got {rating!r})")
    if genre is not None:
        genre = str(genre).strip() or None

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    title = prompting.track_title(prompt, genre, int(seed))
    stem = _slug(title, max_len=80)
    path, reservation = _reserve_output_path(output_dir, stem)

    try:
        started = time.time()
        if backend.runner:
            result = backends.run_subprocess(backend, {
                "prompt": prompt,
                "lyrics": lyrics,
                "duration": float(duration),
                "seed": int(seed),
                "steps": steps,
                "guidance": guidance,
                "output_path": str(path),
                "options": dict(backend.runner_options),
                "init_audio": str(init_audio) if init_audio else None,
                "init_noise_level": init_noise_level,
                "inpaint_range": list(inpaint_range) if inpaint_range else None,
            })
            elapsed = result.get("elapsed_seconds", time.time() - started)
            audio_audit = result.get("_audio_audit")
        else:
            raise RuntimeError(f"{backend.name} has no runner")

        if not isinstance(audio_audit, backends.AudioAudit):
            audio_audit = backends.audit_audio_file(path, backend.name)

        delivered_duration = audio_audit.duration_seconds
        duration_ratio = delivered_duration / float(duration)
        minimum_duration = backend.output_audit.minimum_duration(float(duration))
        maximum_duration = backend.output_audit.maximum_duration(float(duration))
        if delivered_duration < minimum_duration:
            audit_status = "short"
        elif delivered_duration > maximum_duration:
            audit_status = "long"
        else:
            audit_status = "passed"

        track = Track(
            path=path,
            prompt=prompt,
            duration=round(delivered_duration, 3),
            requested_duration=float(duration),
            duration_ratio=round(duration_ratio, 4),
            audit_status=audit_status,
            audio_frames=audio_audit.frames,
            sample_rate=audio_audit.sample_rate,
            channels=audio_audit.channels,
            file_bytes=audio_audit.file_bytes,
            peak_amplitude=round(audio_audit.peak_amplitude, 8),
            seed=int(seed),
            infer_step=steps,
            guidance_scale=guidance,
            lyrics=lyrics,
            backend=backend.name,
            model=backend.model_id,
            dtype=backend.dtype,
            generated_at=stamp,
            elapsed_seconds=round(elapsed, 1),
            title=title,
            rating=rating,
            genre=genre,
        )
        track.write_sidecar()
        if audit_status != "passed":
            raise OutputAuditError(track, minimum_duration, maximum_duration)
        return track
    finally:
        reservation.unlink(missing_ok=True)


SEPARATION_STEMS = ("vocals", "drums", "bass", "other")


def _source_label(path: Path) -> tuple[str, str | None]:
    """Title and genre from a library sidecar, or the file name."""
    sidecar = path.with_suffix(".json")
    title = path.stem.replace("_", " ").replace("-", " ")
    genre = None
    if sidecar.is_file():
        try:
            data = json.loads(sidecar.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = None
        if isinstance(data, dict):
            recorded = data.get("title")
            if isinstance(recorded, str) and recorded.strip():
                title = recorded.strip()
            recorded_genre = data.get("genre")
            if isinstance(recorded_genre, str) and recorded_genre.strip():
                genre = recorded_genre.strip()
    return title, genre


def separate(
    source: Path | str,
    seed: int | None = None,
    output_dir: Path | None = None,
) -> list[Track]:
    """Split one mix into vocals, drums, bass and other.

    Each stem is its own library track. A stem that is silent stays, because a
    mix with no vocal still separated.
    """
    backend = backends.get("demucs")
    if backend.task != "separate":
        raise RuntimeError("the demucs backend is not registered as separation")
    if not backend.available:
        raise RuntimeError(
            f"Backend {backend.name!r} is not set up: {backend.availability_error}. "
            "See README for install steps."
        )
    source = Path(source)
    if not source.is_file():
        raise ValueError(f"mix is not a file: {source}")
    source_audit = backends.audit_audio_file(source, "mix")
    duration = backend.duration.validate(
        source_audit.duration_seconds, f"{backend.name} duration",
    )
    if seed is None:
        seed = random.randint(0, 2**31 - 1)
    output_dir = Path(output_dir) if output_dir else OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    base_title, source_genre = _source_label(source)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    reserved: list[tuple[str, Path, Path]] = []
    try:
        outputs: dict[str, Path] = {}
        for label in SEPARATION_STEMS:
            path, reservation = _reserve_output_path(
                output_dir, _slug(f"{base_title} {label}", max_len=80),
            )
            reserved.append((label, path, reservation))
            outputs[label] = path
        result = backends.run_subprocess(backend, {
            "prompt": f"separate {source.name}",
            "lyrics": "",
            "duration": float(duration),
            "seed": int(seed),
            "steps": None,
            "guidance": None,
            "output_path": str(outputs["vocals"]),
            "outputs": {label: str(path) for label, path in outputs.items()},
            "options": dict(backend.runner_options),
            "init_audio": str(source),
            "init_noise_level": None,
            "inpaint_range": None,
        })
        audits = result.get("_audio_audits")
        if not isinstance(audits, dict):
            audits = {
                label: backends.audit_audio_file(path, backend.name, allow_silence=True)
                for label, path in outputs.items()
            }
        if set(audits) != set(SEPARATION_STEMS):
            raise RuntimeError("separation did not audit every stem")
        elapsed = result.get("elapsed_seconds", 0.0)
        tracks: list[Track] = []
        failure: OutputAuditError | None = None
        separation_name = backend.name
        separation_dtype = backend.dtype
        for label in SEPARATION_STEMS:
            stem_audit = audits[label]
            if not isinstance(stem_audit, backends.AudioAudit):
                raise RuntimeError(f"{label} was not audited")
            audio_audit = stem_audit
            delivered = audio_audit.duration_seconds
            ratio = delivered / float(duration)
            minimum = backend.output_audit.minimum_duration(float(duration))
            maximum = backend.output_audit.maximum_duration(float(duration))
            if delivered < minimum:
                status = "short"
            elif delivered > maximum:
                status = "long"
            else:
                status = "passed"
            track = Track(
                path=outputs[label],
                prompt=f"separated {label} from {source.name}",
                duration=round(delivered, 3),
                requested_duration=float(duration),
                duration_ratio=round(ratio, 4),
                audit_status=status,
                audio_frames=audio_audit.frames,
                sample_rate=audio_audit.sample_rate,
                channels=audio_audit.channels,
                file_bytes=audio_audit.file_bytes,
                peak_amplitude=round(audio_audit.peak_amplitude, 8),
                seed=int(seed),
                infer_step=None,
                guidance_scale=None,
                lyrics="",
                backend=separation_name,
                model=backend.model_id,
                dtype=separation_dtype,
                generated_at=stamp,
                elapsed_seconds=round(float(elapsed), 1),
                title=f"{base_title} {label}",
                rating=None,
                genre=source_genre,
            )
            track.write_sidecar()
            tracks.append(track)
            if status != "passed" and failure is None:
                failure = OutputAuditError(track, minimum, maximum)
        if failure is not None:
            raise failure
        return tracks
    finally:
        for _label, path, reservation in reserved:
            reservation.unlink(missing_ok=True)
            if not path.with_suffix(".json").is_file():
                path.unlink(missing_ok=True)
