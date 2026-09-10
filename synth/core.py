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

# Hugging Face's Xet transfer backend hangs on the first model download here -
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

# ACE-Step defaults to bfloat16, which errors on Apple Silicon.
# The upstream README says to pass `--bf16 false` on macOS; float32 is the equivalent here.
DTYPE = "float32"

# ACE-Step treats this lyrics sentinel as "no vocals".
INSTRUMENTAL = "[inst]"

_pipeline = None


def _load_pipeline():
    """Load the model once per process. Costs ~30-60s and several GB of RAM."""
    global _pipeline
    if _pipeline is None:
        from acestep.pipeline_ace_step import ACEStepPipeline

        _pipeline = ACEStepPipeline(dtype=DTYPE, torch_compile=False)
    return _pipeline


@dataclass
class Track:
    """A generated track and everything needed to reproduce it."""

    path: Path
    prompt: str
    duration: float
    seed: int
    infer_step: int
    guidance_scale: float
    lyrics: str
    model: str
    dtype: str
    generated_at: str
    elapsed_seconds: float

    def sidecar_path(self) -> Path:
        return self.path.with_suffix(".json")

    def write_sidecar(self) -> Path:
        data = asdict(self)
        data["path"] = self.path.name  # relative - the folder may get moved
        target = self.sidecar_path()
        target.write_text(json.dumps(data, indent=2))
        return target


def _slug(text: str, max_len: int = 48) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len].rstrip("-") or "track"


def generate(
    prompt: str,
    duration: float = 60.0,
    seed: int | None = None,
    infer_step: int = 60,
    guidance_scale: float = 15.0,
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

    `seed` is recorded in the sidecar so a track you like can be reproduced or
    nudged one parameter at a time. Omit it for a random one.
    """
    if not prompt.strip():
        raise ValueError("prompt is empty")

    backend = backends.get(model)
    if not backend.available:
        raise RuntimeError(
            f"Backend {backend.name!r} is not set up - expected interpreter at "
            f"{backend.python}. See README for install steps."
        )
    if duration > backend.max_duration:
        raise ValueError(
            f"{backend.name} caps at {backend.max_duration:.0f}s (asked for {duration:.0f}s)"
        )

    # Each backend spells 'no vocals' differently.
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
            "guidance": float(guidance_scale),
            "output_path": str(path),
        })
        elapsed = result.get("elapsed_seconds", time.time() - started)
    else:
        pipe = _load_pipeline()
        pipe(
            prompt=prompt,
            lyrics=lyrics,
            audio_duration=float(duration),
            infer_step=int(infer_step),
            guidance_scale=float(guidance_scale),
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
        infer_step=int(infer_step),
        guidance_scale=float(guidance_scale),
        lyrics=lyrics,
        model=backend.model_id,
        dtype=DTYPE,
        generated_at=stamp,
        elapsed_seconds=round(elapsed, 1),
    )
    track.write_sidecar()
    return track
