"""MiniMax Music 3, MLX 8-bit. Executes inside .venv-mlx - see synth/backends.py.

Native Apple Metal via MLX rather than PyTorch/MPS. Shells out to the runtime's own
documented CLI rather than reaching into its internals, so upstream changes stay contained.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

MODEL_ID = "vanch007/MiniMax-Music3-MLX-8bit"
CLI = Path(sys.executable).parent / "mlx-minimax-music3"


def main() -> int:
    job = json.load(sys.stdin)
    started = time.time()

    cmd = [
        str(CLI), "generate",
        "--model", MODEL_ID,
        "--prompt", job["prompt"],
        "--duration", str(int(float(job["duration"]))),
        "--seed", str(int(job["seed"])),
        "--output", job["output_path"],
    ]
    if job.get("lyrics"):
        cmd += ["--lyrics", job["lyrics"]]
    if job.get("steps"):
        cmd += ["--steps", str(int(job["steps"]))]

    proc = subprocess.run(cmd, capture_output=True, text=True)
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
