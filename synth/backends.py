"""Model registry.

Each backend declares which Python interpreter runs it. Backends whose dependencies
conflict (MiniMax needs transformers>=5, ACE-Step pins 4.50) live in separate venvs and
are invoked as subprocesses; in-process backends use the current interpreter.
"""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Backend:
    name: str
    model_id: str
    venv: str | None            # None = run in-process
    runner: str | None          # script under runners/, for subprocess backends
    licence: str
    notes: str
    default_steps: int = 60
    max_duration: float = 240.0
    prompt_style: str = "tags"  # "tags" or "caption"
    instrumental_tag: str = "[inst]"

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


BACKENDS: dict[str, Backend] = {
    "acestep": Backend(
        name="acestep",
        model_id="ACE-Step/ACE-Step-v1-3.5B",
        venv=".venv",
        runner=None,
        licence="Apache-2.0 (commercial OK)",
        notes="Song-form model. Weak at orchestral/cinematic - tends toward band instrumentation.",
        default_steps=60,
        prompt_style="tags",
    ),
    # The fp32 PyTorch build (MiniMaxAI/MiniMax-Music3, 53GB) was removed - the MLX
    # build below supersedes it on Apple Silicon. Don't re-add it without reason.
    "minimax-mlx": Backend(
        name="minimax-mlx",
        model_id="vanch007/MiniMax-Music3-MLX-8bit",
        venv=".venv-mlx",
        runner="minimax_mlx_runner.py",
        licence="MiniMax Community (commercial OK w/ attribution; >$20M revenue needs authorisation)",
        notes="Native Apple MLX/Metal, 8-bit. 13GB vs 54GB fp32. Preferred build on Apple Silicon.",
        default_steps=30,
        max_duration=300.0,
        prompt_style="caption",
        instrumental_tag="[Instrumental]",
    ),
    "musicgen": Backend(
        name="musicgen",
        model_id="facebook/musicgen-stereo-large",
        venv=".venv",
        runner="musicgen_runner.py",
        licence="CC-BY-NC-4.0 - NON-COMMERCIAL ONLY",
        notes="Strong instrumental model, but 30s per generation.",
        default_steps=0,
        max_duration=30.0,
        prompt_style="tags",
        instrumental_tag="",
    ),
}


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
