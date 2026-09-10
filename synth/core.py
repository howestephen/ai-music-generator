"""Core generation. Everything else in this project is a thin wrapper over `generate`."""
from __future__ import annotations

import json
import os
import random
import re
import time
import warnings

from . import backends
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path

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

DEFAULT_MODEL = "acestep"  # switch to "minimax-mlx" once its output is judged better

_pipeline = None


def _load_pipeline():
    """Load the model once per process. Costs ~30-60s and several GB of RAM."""
    global _pipeline
    if _pipeline is None:
        from acestep.pipeline_ace_step import ACEStepPipeline

        _pipeline = ACEStepPipeline(dtype=backends.get("acestep").dtype, torch_compile=False)
    return _pipeline


@dataclass
class Track:
    """A generated track and everything needed to reproduce it.

    `backend` is the registry key (what `--model` takes); `model` is the weights id.
    `infer_step` and `guidance_scale` are None when the backend has no such control,
    so the sidecar never claims a setting that did not apply.
    """

    path: Path
    prompt: str
    duration: float
    seed: int
    infer_step: int | None
    guidance_scale: float | None
    lyrics: str
    backend: str
    model: str
    dtype: str
    generated_at: str
    elapsed_seconds: float

    def sidecar_path(self) -> Path:
        return self.path.with_suffix(".json")

    def write_sidecar(self) -> Path:
        data = asdict(self)
        data["path"] = self.path.name  # relative: the folder may get moved
        target = self.sidecar_path()
        target.write_text(json.dumps(data, indent=2))
        return target


def _slug(text: str, max_len: int = 48) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len].rstrip("-") or "track"


def _resolve(backend: backends.Backend, knob: str, value, default):
    """Apply the backend's own default, or refuse a value it cannot honour."""
    if default is None:
        if value is not None:
            raise ValueError(f"{backend.name} has no {knob} control (got {value!r})")
        return None
    return value if value is not None else default


def generate(
    prompt: str,
    duration: float = 60.0,
    seed: int | None = None,
    infer_step: int | None = None,
    guidance_scale: float | None = None,
    lyrics: str | None = None,
    output_dir: Path | None = None,
    model: str = DEFAULT_MODEL,
) -> Track:
    """Generate one track.

    Prompt style depends on the backend. ACE-Step and MusicGen want comma-separated
    style tags ("lo-fi hip hop, warm rhodes, 85bpm"). MiniMax wants a Structured
    Caption in prose, which is where its BPM/key/scale control lives:
    "Genre: cinematic orchestral. BPM: 120. Key: D. Scale: Mixolydian. Arrangement: ..."
    Check `backends.get(model).prompt_style`.

    `infer_step` and `guidance_scale` default to the backend's own values. Passing one
    to a backend that has no such control raises rather than being dropped.

    `seed` is recorded in the sidecar so a track you like can be reproduced or
    nudged one parameter at a time. Omit it for a random one.
    """
    if not prompt.strip():
        raise ValueError("prompt is empty")

    backend = backends.get(model)
    if not backend.available:
        raise RuntimeError(
            f"Backend {backend.name!r} is not set up: expected interpreter at "
            f"{backend.python}. See README for install steps."
        )
    if duration > backend.max_duration:
        raise ValueError(
            f"{backend.name} caps at {backend.max_duration:.0f}s (asked for {duration:.0f}s)"
        )

    steps = _resolve(backend, "step count", infer_step, backend.default_steps)
    if steps is not None and int(steps) < 1:
        raise ValueError(f"step count must be at least 1 (got {steps!r})")
    guidance = _resolve(backend, "guidance", guidance_scale, backend.default_guidance)

    # Each backend spells 'no vocals' differently, and one has no lyrics channel at all.
    if lyrics is not None and not backend.supports_lyrics:
        raise ValueError(f"{backend.name} has no lyrics channel (got {lyrics!r})")
    if lyrics is None:
        lyrics = backend.instrumental_tag

    output_dir = Path(output_dir) if output_dir else OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    if seed is None:
        seed = random.randint(0, 2**31 - 1)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = output_dir / f"{stamp}_{backend.name}_{_slug(prompt)}_seed{seed}.wav"

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
        })
        elapsed = result.get("elapsed_seconds", time.time() - started)
    else:
        if steps is None or guidance is None:
            raise RuntimeError(
                f"{backend.name} runs in-process and needs both default_steps and "
                "default_guidance declared in synth/backends.py"
            )
        pipe = _load_pipeline()
        pipe(
            prompt=prompt,
            lyrics=lyrics,
            audio_duration=float(duration),
            infer_step=int(steps),
            guidance_scale=float(guidance),
            manual_seeds=[int(seed)],
            save_path=str(path),
            format="wav",
        )
        elapsed = time.time() - started

    track = Track(
        path=path,
        prompt=prompt,
        duration=float(duration),
        seed=int(seed),
        infer_step=steps,
        guidance_scale=guidance,
        lyrics=lyrics,
        backend=backend.name,
        model=backend.model_id,
        dtype=backend.dtype,
        generated_at=stamp,
        elapsed_seconds=round(elapsed, 1),
    )
    track.write_sidecar()
    return track
