"""Model registry.

Each backend declares which Python interpreter runs it. Backends whose dependencies
conflict (MiniMax needs transformers>=5, ACE-Step pins 4.50) live in separate venvs and
are invoked as subprocesses; in-process backends use the current interpreter.

Backends also declare which knobs they actually have. A `None` default means the backend
has no such control, and `core.generate` refuses a value for it rather than dropping it
silently and recording it in the sidecar as if it had applied.
"""
from __future__ import annotations

import json
import subprocess
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
    dtype: str                  # what the weights really run as; recorded in the sidecar
    default_steps: int | None = 60          # None = the backend has no step count
    default_guidance: float | None = 15.0   # None = the backend exposes no guidance control
    max_duration: float = 240.0
    prompt_style: str = "tags"  # "tags" or "caption"
    instrumental_tag: str = "[inst]"
    supports_lyrics: bool = True

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
        notes="Song-form model. Weak at orchestral/cinematic: tends toward band instrumentation.",
        # ACE-Step defaults to bfloat16, which errors on Apple Silicon. Upstream says
        # pass `--bf16 false` on macOS; float32 is the equivalent here.
        dtype="float32",
        default_steps=60,
        default_guidance=15.0,
        prompt_style="tags",
    ),
    # The fp32 PyTorch build (MiniMaxAI/MiniMax-Music3, 53GB) was removed: the MLX
    # build below supersedes it on Apple Silicon. Don't re-add it without reason.
    "minimax-mlx": Backend(
        name="minimax-mlx",
        model_id="vanch007/MiniMax-Music3-MLX-8bit",
        venv=".venv-mlx",
        runner="minimax_mlx_runner.py",
        licence="MiniMax Community (commercial OK w/ attribution; >$20M revenue needs authorisation)",
        notes="Native Apple MLX/Metal, 8-bit. 13GB vs 54GB fp32. Preferred build on Apple Silicon.",
        dtype="8-bit (MLX)",
        default_steps=30,
        # The mlx-minimax-music3 CLI exposes --steps but no guidance flag; its cfg
        # scales are fixed inside its GenerationConfig. Nothing to plumb through.
        default_guidance=None,
        max_duration=300.0,
        prompt_style="caption",
        instrumental_tag="[Instrumental]",
    ),
    "musicgen": Backend(
        name="musicgen",
        model_id="facebook/musicgen-stereo-large",
        venv=".venv",
        runner="musicgen_runner.py",
        licence="CC-BY-NC-4.0, NON-COMMERCIAL ONLY",
        notes="Strong instrumental model, but 30s per generation.",
        dtype="float32",
        default_steps=None,     # autoregressive: token count follows duration, no step knob
        default_guidance=3.0,   # MusicGen's own documented default; 15 drives it far too hard
        max_duration=30.0,
        prompt_style="tags",
        instrumental_tag="",
        supports_lyrics=False,  # no lyrics channel at all
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
