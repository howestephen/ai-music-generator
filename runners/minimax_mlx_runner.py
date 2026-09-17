"""MiniMax Music 3, MLX 8-bit. Executes inside .venv-mlx - see synth/backends.py.

Native Apple Metal via MLX rather than PyTorch/MPS. The project wrapper adds the one
constraint missing from the pinned runtime: do not accept its end token before the target.
"""
import json
import argparse
import math
import os
import subprocess
import sys
import time
from collections.abc import Sequence

# Xet transfer hangs silently on first download. Set before anything touches
# huggingface_hub, and set here too so the runner is safe when run on its own.
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

MODEL_ID = "vanch007/MiniMax-Music3-MLX-8bit"
MIN_DURATION_WRAPPER = os.path.abspath(__file__)
# The outer adapter has a 7,200-second ceiling. Leave enough time for this layer
# to kill and reap the model process, serialise the result and exit first.
COMMAND_TIMEOUT_SECONDS = 7100


def _parse_wrapper_args(argv: Sequence[str] | None) -> tuple[float, list[str]]:
    """Remove the wrapper-only flag and leave the upstream CLI arguments intact."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--min-duration", type=float, required=True)
    known, forwarded = parser.parse_known_args(argv)
    if not math.isfinite(known.min_duration) or known.min_duration <= 0:
        parser.error("--min-duration must be a finite positive number")
    return known.min_duration, forwarded


def _install_minimum_duration(min_duration: float) -> int:
    """Mask the audio-end token until the requested number of frames exists."""
    import mlx.core as mx
    from mlx_minimax_music3 import pipeline
    from mlx_minimax_music3.config import GenerationConfig, ModelConfig

    model = ModelConfig()
    minimum_frames = GenerationConfig(audio_duration=min_duration).max_frames(model)
    original_semantic_guided_logits = pipeline.semantic_guided_logits
    semantic_call_index = 0

    def semantic_guided_logits_with_minimum(
        logits,
        allowed_vocab,
        cfg_scale=1.5,
        conditional_top_k=50,
    ):
        nonlocal semantic_call_index
        completed_frames = max(0, semantic_call_index - 1)
        if completed_frames < minimum_frames:
            stop_token = mx.arange(allowed_vocab.shape[-1]) == model.audio_end_token_id
            allowed_vocab = allowed_vocab & ~stop_token
        semantic_call_index += 1
        return original_semantic_guided_logits(
            logits,
            allowed_vocab,
            cfg_scale=cfg_scale,
            conditional_top_k=conditional_top_k,
        )

    pipeline.semantic_guided_logits = semantic_guided_logits_with_minimum
    return minimum_frames


def _generate_main(argv: Sequence[str] | None = None) -> int:
    """Apply the constraint, then delegate parsing and generation to the pinned CLI."""
    min_duration, forwarded = _parse_wrapper_args(argv)
    _install_minimum_duration(min_duration)

    from mlx_minimax_music3 import cli

    return cli.main(forwarded)


def main() -> int:
    job = json.load(sys.stdin)
    started = time.time()

    cmd = [
        sys.executable, MIN_DURATION_WRAPPER, "_generate", "generate",
        "--model", MODEL_ID,
        "--prompt", job["prompt"],
        "--duration", str(float(job["duration"])),
        "--min-duration", str(float(job["duration"])),
        "--seed", str(int(job["seed"])),
        "--output", job["output_path"],
    ]
    if job.get("lyrics"):
        cmd += ["--lyrics", job["lyrics"]]
    if job.get("steps") is not None:  # 0 is a value, not an absence
        cmd += ["--steps", str(int(job["steps"]))]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            timeout=COMMAND_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        sys.stderr.write(
            f"MiniMax generation timed out after {COMMAND_TIMEOUT_SECONDS} seconds"
        )
        return 124
    if proc.returncode != 0:
        sys.stderr.write("\n".join(proc.stderr.strip().splitlines()[-15:]))
        return proc.returncode

    json.dump(
        {
            "path": job["output_path"],
            "elapsed_seconds": round(time.time() - started, 1),
            "backend": "mlx",
        },
        sys.stdout,
    )
    return 0


if __name__ == "__main__":
    if sys.argv[1:2] == ["_generate"]:
        raise SystemExit(_generate_main(sys.argv[2:]))
    raise SystemExit(main())
