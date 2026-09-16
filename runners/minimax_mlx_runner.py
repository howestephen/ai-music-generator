"""MiniMax Music 3, MLX 8-bit. Executes inside .venv-mlx - see synth/backends.py.

Native Apple Metal via MLX rather than PyTorch/MPS. Shells out to the runtime's own
documented CLI rather than reaching into its internals, so upstream changes stay contained.
"""
import json
import os
import subprocess
import sys
import time

# Xet transfer hangs silently on first download. Set before anything touches
# huggingface_hub, and set here too so the runner is safe when run on its own.
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

MODEL_ID = "vanch007/MiniMax-Music3-MLX-8bit"
# The outer adapter has a 7,200-second ceiling. Leave enough time for this layer
# to kill and reap the model process, serialise the result and exit first.
COMMAND_TIMEOUT_SECONDS = 7100


def main() -> int:
    job = json.load(sys.stdin)
    started = time.time()

    cmd = [
        sys.executable, "-m", "mlx_minimax_music3.cli", "generate",
        "--model", MODEL_ID,
        "--prompt", job["prompt"],
        "--duration", str(float(job["duration"])),
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
    raise SystemExit(main())
