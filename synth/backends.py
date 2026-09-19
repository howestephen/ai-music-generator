"""Versioned model-manifest loader and runtime registry.

Each backend declares which Python interpreter runs it. Backends whose dependencies
conflict (MiniMax needs transformers>=5, ACE-Step pins 4.50) live in separate venvs and
are invoked as subprocesses; in-process backends use the current interpreter.

Backends also declare which knobs they actually have. A `None` default means the backend
has no such control, and `core.generate` refuses a value for it rather than dropping it
silently and recording it in the sidecar as if it had applied.
"""
from __future__ import annotations

import json
import math
import os
import signal
import subprocess
import time
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = Path(__file__).with_name("backends.json")
TERMINATE_GRACE_SECONDS = 5
# How a backend answers a duration request. "best_effort" models may stop early,
# so a ratio decides acceptance and a fresh seed may be worth trying. "exact"
# models are fixed-length by construction, so any deviation is an integration
# fault rather than a creative miss, and retrying would change nothing.
DURATION_CONTRACTS = frozenset({"best_effort", "exact"})
# How a backend wants to be asked. Using the wrong one degrades output badly, so
# the UI and its presets are keyed off this rather than off the backend name.
# "tags": comma-separated style tags. "caption": MiniMax's structured prose
# caption. "description": a plain natural-language sentence.
PROMPT_STYLES = frozenset({"tags", "caption", "description"})


def _expect_keys(data: dict, required: set[str], location: str) -> None:
    missing = required - data.keys()
    unknown = data.keys() - required
    if missing:
        raise ValueError(f"{location} is missing: {', '.join(sorted(missing))}")
    if unknown:
        raise ValueError(f"{location} has unknown fields: {', '.join(sorted(unknown))}")


@dataclass(frozen=True)
class NumericControl:
    """One backend-owned numeric setting shared by core, CLI and UI callers."""

    default: float
    minimum: float
    maximum: float | None
    step: float
    label: str
    info: str
    integer: bool = False

    @classmethod
    def from_manifest(cls, data, location: str) -> "NumericControl | None":
        if data is None:
            return None
        if not isinstance(data, dict):
            raise ValueError(f"{location} must be an object or null")
        _expect_keys(
            data,
            {"default", "minimum", "maximum", "step", "label", "info", "integer"},
            location,
        )
        for field in ("default", "minimum", "step"):
            value = data[field]
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
            ):
                raise ValueError(f"{location}.{field} must be a finite number")
        maximum = data["maximum"]
        if maximum is not None and (
            isinstance(maximum, bool)
            or not isinstance(maximum, (int, float))
            or not math.isfinite(maximum)
        ):
            raise ValueError(f"{location}.maximum must be a finite number or null")
        if not isinstance(data["integer"], bool):
            raise ValueError(f"{location}.integer must be true or false")
        if not isinstance(data["label"], str) or not isinstance(data["info"], str):
            raise ValueError(f"{location} label and info must be strings")
        control = cls(**data)
        if control.step <= 0:
            raise ValueError(f"{location}.step must be positive")
        if control.maximum is not None and control.maximum < control.minimum:
            raise ValueError(f"{location}.maximum must not be below its minimum")
        control.validate(control.default, f"{location}.default")
        if not control.label or not control.info:
            raise ValueError(f"{location} must declare non-empty label and info text")
        return control

    def validate(self, value, name: str):
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"{name} must be a number (got {value!r})") from exc
        if not math.isfinite(number):
            raise ValueError(f"{name} must be finite (got {value!r})")
        if number < self.minimum:
            raise ValueError(f"{name} must be at least {self.minimum:g} (got {number:g})")
        if self.maximum is not None and number > self.maximum:
            raise ValueError(f"{name} caps at {self.maximum:g} (got {number:g})")
        if self.integer:
            if not number.is_integer():
                raise ValueError(f"{name} must be a whole number (got {number:g})")
            return int(number)
        return number


@dataclass(frozen=True)
class OutputAuditPolicy:
    """Backend-owned acceptance and automatic retry policy for delivered audio."""

    minimum_duration_ratio: float
    duration_tolerance_seconds: float
    random_seed_retries: int
    duration_contract: str

    @classmethod
    def from_manifest(cls, data, location: str) -> "OutputAuditPolicy":
        if not isinstance(data, dict):
            raise ValueError(f"{location} must be an object")
        _expect_keys(
            data,
            {
                "minimum_duration_ratio",
                "duration_tolerance_seconds",
                "random_seed_retries",
                "duration_contract",
            },
            location,
        )
        ratio = data["minimum_duration_ratio"]
        tolerance = data["duration_tolerance_seconds"]
        retries = data["random_seed_retries"]
        contract = data["duration_contract"]
        if (
            isinstance(ratio, bool)
            or not isinstance(ratio, (int, float))
            or not math.isfinite(ratio)
            or not 0 < ratio <= 1
        ):
            raise ValueError(f"{location}.minimum_duration_ratio must be within (0, 1]")
        if (
            isinstance(tolerance, bool)
            or not isinstance(tolerance, (int, float))
            or not math.isfinite(tolerance)
            or tolerance < 0
        ):
            raise ValueError(
                f"{location}.duration_tolerance_seconds must be a non-negative number"
            )
        if isinstance(retries, bool) or not isinstance(retries, int) or retries < 0:
            raise ValueError(f"{location}.random_seed_retries must be a non-negative integer")
        if contract not in DURATION_CONTRACTS:
            raise ValueError(
                f"{location}.duration_contract must be one of "
                f"{', '.join(sorted(DURATION_CONTRACTS))}"
            )
        # An exact contract is a claim that the runtime delivers the requested length,
        # so the manifest must not also describe a short result as acceptable or
        # ask for a retry that could only ever reproduce the same length.
        if contract == "exact":
            if ratio != 1:
                raise ValueError(
                    f"{location}.minimum_duration_ratio must be 1 under an exact contract"
                )
            if retries != 0:
                raise ValueError(
                    f"{location}.random_seed_retries must be 0 under an exact contract"
                )
            if tolerance <= 0:
                raise ValueError(
                    f"{location}.duration_tolerance_seconds must be positive under an "
                    "exact contract, to absorb sample-rate rounding"
                )
        return cls(float(ratio), float(tolerance), retries, contract)

    def minimum_duration(self, requested_duration: float) -> float:
        return max(
            0.0,
            requested_duration * self.minimum_duration_ratio
            - self.duration_tolerance_seconds,
        )

    def maximum_duration(self, requested_duration: float) -> float:
        """Upper bound on an acceptable delivery. Only an exact contract has one."""
        if self.duration_contract != "exact":
            return math.inf
        return requested_duration + self.duration_tolerance_seconds


@dataclass(frozen=True)
class AudioAudit:
    """Facts measured from the delivered audio container and sample stream."""

    duration_seconds: float
    frames: int
    sample_rate: int
    channels: int
    file_bytes: int
    peak_amplitude: float


@dataclass(frozen=True)
class Backend:
    name: str
    model_id: str
    venv: str | None            # None = run in-process
    runner: str | None          # script under runners/, for subprocess backends
    licence: str
    notes: str
    dtype: str                  # what the weights really run as; recorded in the sidecar
    duration: NumericControl
    steps: NumericControl | None
    guidance: NumericControl | None
    output_audit: OutputAuditPolicy
    prompt_style: str = "tags"  # see PROMPT_STYLES
    # Can regenerate part of an existing track (init audio, inpaint range). Asking a
    # backend without it would be a silent no-op, which milestone 0.2 already fixed.
    supports_editing: bool = False
    instrumental_tag: str = "[inst]"
    supports_lyrics: bool = True
    probe_modules: tuple[str, ...] = ()
    # Pairs, not a dict: a dict field would make this frozen value unhashable.
    runner_options: tuple[tuple[str, str], ...] = ()
    timeout_seconds: int | None = None

    @classmethod
    def from_manifest(cls, name: str, data) -> "Backend":
        if not isinstance(data, dict):
            raise ValueError(f"backends.{name} must be an object")
        _expect_keys(
            data,
            {
                "model_id", "venv", "runner", "licence", "notes", "dtype",
                "prompt_style", "instrumental_tag", "supports_lyrics", "runtime",
                "controls", "output_audit", "supports_editing",
            },
            f"backends.{name}",
        )
        runtime = data["runtime"]
        if not isinstance(runtime, dict):
            raise ValueError(f"backends.{name}.runtime must be an object")
        _expect_keys(
            runtime,
            {"probe_modules", "timeout_seconds", "runner_options"},
            f"backends.{name}.runtime",
        )
        probe_modules = runtime["probe_modules"]
        if (
            not isinstance(probe_modules, list)
            or not probe_modules
            or any(not isinstance(module, str) or not module for module in probe_modules)
        ):
            raise ValueError(
                f"backends.{name}.runtime.probe_modules must be a non-empty string list"
            )
        # Per-backend switches the runner needs but core has no opinion about, such as
        # which checkpoint of a multi-model runtime to load. Keeping them here is what
        # lets a second variant of an existing model be a manifest entry alone.
        runner_options = runtime["runner_options"]
        if not isinstance(runner_options, dict) or any(
            not isinstance(key, str)
            or not key
            or not isinstance(value, str)
            or not value
            for key, value in runner_options.items()
        ):
            raise ValueError(
                f"backends.{name}.runtime.runner_options must map non-empty strings "
                "to non-empty strings"
            )
        if data["runner"] is None and runner_options:
            raise ValueError(
                f"backends.{name}.runtime.runner_options needs a runner to receive them"
            )
        timeout_seconds = runtime["timeout_seconds"]
        if timeout_seconds is not None and (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, int)
            or timeout_seconds <= 0
        ):
            raise ValueError(
                f"backends.{name}.runtime.timeout_seconds must be a positive integer or null"
            )
        if data["runner"] is None and timeout_seconds is not None:
            raise ValueError(
                f"backends.{name}.runtime.timeout_seconds must be null without a runner"
            )
        if data["runner"] is not None and timeout_seconds is None:
            raise ValueError(
                f"backends.{name}.runtime.timeout_seconds is required for a runner"
            )
        controls = data["controls"]
        if not isinstance(controls, dict):
            raise ValueError(f"backends.{name}.controls must be an object")
        _expect_keys(controls, {"duration", "steps", "guidance"}, f"backends.{name}.controls")
        duration = NumericControl.from_manifest(
            controls["duration"], f"backends.{name}.controls.duration",
        )
        if duration is None or duration.maximum is None:
            raise ValueError(f"backends.{name}.controls.duration requires a maximum")
        if not isinstance(data["supports_editing"], bool):
            raise ValueError(f"backends.{name}.supports_editing must be true or false")
        if data["prompt_style"] not in PROMPT_STYLES:
            raise ValueError(
                f"backends.{name}.prompt_style must be one of "
                f"{', '.join(sorted(PROMPT_STYLES))}"
            )
        return cls(
            name=name,
            model_id=data["model_id"],
            venv=data["venv"],
            runner=data["runner"],
            licence=data["licence"],
            notes=data["notes"],
            dtype=data["dtype"],
            duration=duration,
            steps=NumericControl.from_manifest(
                controls["steps"], f"backends.{name}.controls.steps",
            ),
            guidance=NumericControl.from_manifest(
                controls["guidance"], f"backends.{name}.controls.guidance",
            ),
            output_audit=OutputAuditPolicy.from_manifest(
                data["output_audit"], f"backends.{name}.output_audit",
            ),
            prompt_style=data["prompt_style"],
            supports_editing=data["supports_editing"],
            instrumental_tag=data["instrumental_tag"],
            supports_lyrics=data["supports_lyrics"],
            probe_modules=tuple(probe_modules),
            runner_options=tuple(sorted(runner_options.items())),
            timeout_seconds=timeout_seconds,
        )

    @property
    def max_duration(self) -> float:
        if self.duration.maximum is None:
            raise ValueError(f"{self.name} duration must declare a maximum")
        return self.duration.maximum

    @property
    def default_steps(self) -> int | None:
        return int(self.steps.default) if self.steps is not None else None

    @property
    def default_guidance(self) -> float | None:
        return float(self.guidance.default) if self.guidance is not None else None

    @property
    def python(self) -> Path:
        return PROJECT_ROOT / (self.venv or ".venv") / "bin" / "python"

    @cached_property
    def availability_error(self) -> str | None:
        if not self.python.exists():
            return f"missing interpreter at {self.python}"
        if self.runner and not (PROJECT_ROOT / "runners" / self.runner).exists():
            return f"missing runner runners/{self.runner}"
        imports = "; ".join(f"import {module}" for module in self.probe_modules)
        try:
            proc = subprocess.run(
                [str(self.python), "-c", imports],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="strict",
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired, UnicodeError) as exc:
            return f"runtime probe failed: {exc}"
        if proc.returncode != 0:
            detail = proc.stderr.strip().splitlines()
            return detail[-1] if detail else "runtime import probe failed"
        return None

    @property
    def available(self) -> bool:
        return self.availability_error is None


def load_manifest(path: Path = MANIFEST_PATH) -> tuple[str, dict[str, Backend]]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Cannot load backend manifest {path}: {exc}") from exc
    if not isinstance(document, dict):
        raise ValueError("backend manifest must contain one JSON object")
    _expect_keys(document, {"schema_version", "default_backend", "backends"}, "manifest")
    if document["schema_version"] != 6:
        raise ValueError(f"unsupported backend manifest schema {document['schema_version']!r}")
    raw_backends = document["backends"]
    if not isinstance(raw_backends, dict) or not raw_backends:
        raise ValueError("manifest.backends must be a non-empty object")
    loaded = {
        name: Backend.from_manifest(name, data)
        for name, data in raw_backends.items()
    }
    default = document["default_backend"]
    if default not in loaded:
        raise ValueError(f"default backend {default!r} is not declared in manifest.backends")
    return default, loaded


DEFAULT_BACKEND, BACKENDS = load_manifest()


def get(name: str) -> Backend:
    try:
        return BACKENDS[name]
    except KeyError:
        raise SystemExit(
            f"Unknown model {name!r}. Available: {', '.join(sorted(BACKENDS))}"
        )


def _terminate_process_tree(proc: subprocess.Popen) -> None:
    """Terminate a runner and its descendants, then ensure the adapter is reaped."""
    if os.name == "posix":
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except PermissionError:
            proc.terminate()
        deadline = time.monotonic() + TERMINATE_GRACE_SECONDS
        group_alive = True
        while group_alive and time.monotonic() < deadline:
            try:
                os.killpg(proc.pid, 0)
            except ProcessLookupError:
                group_alive = False
            except PermissionError:
                # macOS can return EPERM while a terminated process group is
                # disappearing. Escalate once, but never let the probe replace
                # the original timeout error or bypass adapter reaping.
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
                group_alive = False
            else:
                time.sleep(0.05)
        if group_alive:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except PermissionError:
                proc.kill()
    else:
        proc.kill()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def _run_process(command: list[str], input_text: str, timeout_seconds: int):
    """Run one isolated adapter process with strict UTF-8 and tree cleanup."""
    proc = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="strict",
        start_new_session=os.name == "posix",
    )
    try:
        stdout, stderr = proc.communicate(input_text, timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        _terminate_process_tree(proc)
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            if stream is not None:
                stream.close()
        raise
    return subprocess.CompletedProcess(command, proc.returncode, stdout, stderr)


def audit_audio_file(path: Path, backend_name: str) -> AudioAudit:
    """Measure basic output facts and refuse empty, silent or non-finite audio."""
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError(f"{backend_name} runner wrote no audio file: {path}")
    try:
        import numpy as np
        import soundfile as sf

        with sf.SoundFile(str(path)) as audio:
            frames = len(audio)
            sample_rate = int(audio.samplerate)
            channels = int(audio.channels)
            peak = 0.0
            for block in audio.blocks(blocksize=65_536, dtype="float32", always_2d=True):
                if not np.isfinite(block).all():
                    raise RuntimeError(
                        f"{backend_name} runner wrote non-finite audio samples: {path}"
                    )
                if block.size:
                    peak = max(peak, float(np.max(np.abs(block))))
    except Exception as exc:
        if isinstance(exc, RuntimeError) and "non-finite audio samples" in str(exc):
            raise
        raise RuntimeError(f"{backend_name} runner wrote invalid audio: {path}") from exc
    if frames <= 0 or sample_rate <= 0 or channels <= 0:
        raise RuntimeError(f"{backend_name} runner wrote empty audio: {path}")
    if peak <= 1e-7:
        raise RuntimeError(f"{backend_name} runner wrote silent audio: {path}")
    return AudioAudit(
        duration_seconds=frames / sample_rate,
        frames=frames,
        sample_rate=sample_rate,
        channels=channels,
        file_bytes=path.stat().st_size,
        peak_amplitude=peak,
    )


def run_subprocess(backend: Backend, job: dict) -> dict:
    """Run a job in the backend's own interpreter and return its JSON result."""
    if not backend.runner or backend.timeout_seconds is None:
        raise RuntimeError(f"{backend.name} has no subprocess runtime configured")
    script = PROJECT_ROOT / "runners" / backend.runner
    expected = Path(job["output_path"])
    if expected.exists():
        raise RuntimeError(f"refusing to overwrite an existing output: {expected}")
    try:
        proc = _run_process(
            [str(backend.python), str(script)],
            json.dumps(job),
            backend.timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"{backend.name} runner timed out after {backend.timeout_seconds} seconds"
        ) from exc
    except UnicodeError as exc:
        raise RuntimeError(f"{backend.name} runner emitted invalid UTF-8") from exc
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-15:])
        raise RuntimeError(f"{backend.name} runner failed:\n{tail}")
    # Model loading chatter goes to stderr, but be defensive about stray stdout.
    result = None
    for line in reversed(proc.stdout.strip().splitlines()):
        if line.lstrip().startswith("{"):
            try:
                result = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"{backend.name} runner produced malformed JSON"
                ) from exc
            break
    if result is None:
        raise RuntimeError(f"{backend.name} runner produced no JSON result")
    if not isinstance(result, dict):
        raise RuntimeError(f"{backend.name} runner JSON result must be an object")

    returned_path = result.get("path")
    if not isinstance(returned_path, str) or Path(returned_path).resolve() != expected.resolve():
        raise RuntimeError(
            f"{backend.name} runner reported an unexpected output path: {returned_path!r}"
        )
    elapsed = result.get("elapsed_seconds")
    if (
        isinstance(elapsed, bool)
        or not isinstance(elapsed, (int, float))
        or not math.isfinite(elapsed)
        or elapsed < 0
    ):
        raise RuntimeError(
            f"{backend.name} runner reported invalid elapsed_seconds: {elapsed!r}"
        )
    result["_audio_audit"] = audit_audio_file(expected, backend.name)
    return result
