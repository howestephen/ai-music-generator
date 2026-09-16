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
import subprocess
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = Path(__file__).with_name("backends.json")


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
    prompt_style: str = "tags"  # "tags" or "caption"
    instrumental_tag: str = "[inst]"
    supports_lyrics: bool = True

    @classmethod
    def from_manifest(cls, name: str, data) -> "Backend":
        if not isinstance(data, dict):
            raise ValueError(f"backends.{name} must be an object")
        _expect_keys(
            data,
            {
                "model_id", "venv", "runner", "licence", "notes", "dtype",
                "prompt_style", "instrumental_tag", "supports_lyrics", "controls",
            },
            f"backends.{name}",
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
        if data["prompt_style"] not in {"tags", "caption"}:
            raise ValueError(f"backends.{name}.prompt_style must be 'tags' or 'caption'")
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
            prompt_style=data["prompt_style"],
            instrumental_tag=data["instrumental_tag"],
            supports_lyrics=data["supports_lyrics"],
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

    @property
    def available(self) -> bool:
        if not self.python.exists():
            return False
        if self.runner and not (PROJECT_ROOT / "runners" / self.runner).exists():
            return False
        return True


def load_manifest(path: Path = MANIFEST_PATH) -> tuple[str, dict[str, Backend]]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Cannot load backend manifest {path}: {exc}") from exc
    if not isinstance(document, dict):
        raise ValueError("backend manifest must contain one JSON object")
    _expect_keys(document, {"schema_version", "default_backend", "backends"}, "manifest")
    if document["schema_version"] != 1:
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


def run_subprocess(backend: Backend, job: dict) -> dict:
    """Run a job in the backend's own interpreter and return its JSON result."""
    script = PROJECT_ROOT / "runners" / backend.runner
    proc = subprocess.run(
        [str(backend.python), str(script)],
        input=json.dumps(job),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-15:])
        raise RuntimeError(f"{backend.name} runner failed:\n{tail}")
    # Model loading chatter goes to stderr, but be defensive about stray stdout.
    for line in reversed(proc.stdout.strip().splitlines()):
        if line.startswith("{"):
            return json.loads(line)
    raise RuntimeError(f"{backend.name} runner produced no JSON result")
