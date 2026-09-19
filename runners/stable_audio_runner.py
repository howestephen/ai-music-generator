"""Stable Audio 3, pure MLX. Executes inside .venv-sa3 - see synth/backends.py.

Stability ships its own Apple Silicon runtime with no PyTorch at inference time. That
runtime is a source tree rather than a package, so the install puts it on this venv's
import path (see README) and this runner locates its CLI from the imported pipeline
module rather than from a path written down here.

Which checkpoint to load comes from the manifest, not from this file: both the small
and medium models run through this one runner, distinguished only by `runner_options`.

Unlike the autoregressive backends, the sampler works to a fixed latent length and the
runtime trims the WAV to exactly the requested seconds, which is why these backends
declare an `exact` duration contract.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

# Xet transfer hangs silently on first download, as it does for MiniMax.
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

# The manifest's own timeout is the authority and kills the whole process group. This
# inner limit only exists so this layer can reap the child and report first, so it sits
# below the smallest timeout any Stable Audio backend declares.
COMMAND_TIMEOUT_SECONDS = 3500


def _cli_script() -> Path:
    """Find the installed runtime's own entry point, or say how to install it."""
    try:
        import models.defs.sa3_pipeline as pipeline
    except ImportError as exc:
        raise SystemExit(
            f"Stable Audio 3 runtime is not on this venv's import path ({exc}). "
            "See README: the clone is pinned under ~/.cache and added to .venv-sa3 "
            "with a .pth file."
        ) from exc
    script = Path(pipeline.__file__).resolve().parents[2] / "scripts" / "sa3_mlx.py"
    if not script.is_file():
        raise SystemExit(f"Stable Audio 3 CLI is missing at {script}")
    return script


def main() -> int:
    job = json.load(sys.stdin)
    options = job.get("options") or {}
    dit = options.get("dit")
    decoder = options.get("decoder")
    if not dit or not decoder:
        sys.stderr.write(
            "Stable Audio 3 needs 'dit' and 'decoder' in this backend's "
            "runtime.runner_options; got %r" % (options,)
        )
        return 2

    started = time.time()
    cmd = [
        sys.executable, str(_cli_script()),
        "--prompt", job["prompt"],
        "--seconds", str(float(job["duration"])),
        "--seed", str(int(job["seed"])),
        "--dit", dit,
        "--decoder", decoder,
        "--out", job["output_path"],
    ]
    if job.get("steps") is not None:  # 0 is a value, not an absence
        cmd += ["--steps", str(int(job["steps"]))]
    if job.get("guidance") is not None:
        cmd += ["--cfg", str(float(job["guidance"]))]

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
            f"Stable Audio generation timed out after {COMMAND_TIMEOUT_SECONDS} seconds"
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
