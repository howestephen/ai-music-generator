"""ACE-Step 1.5 turbo, MLX. Executes inside .venv-ace - see synth/backends.py.

Upstream's macOS launcher is the contract: the 2B turbo DiT, the 0.6B planner,
and MLX for both. A PyTorch fallback is a failed run, not a quieter success.
The planner may fill BPM, key and time signature. It does not replace the caption.
"""
import json
import os
import shutil
import sys
import tempfile
import time

os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("ACESTEP_LM_BACKEND", "mlx")

INSTRUMENTAL = "[Instrumental]"


def request_from_job(job: dict) -> dict:
    """Turn one project job into the fields the 1.5 call actually honours."""
    options = job.get("options") or {}
    dit = options.get("dit")
    lm = options.get("lm")
    shift = options.get("shift")
    if not dit or not lm or shift in (None, ""):
        raise ValueError(
            "ACE-Step 1.5 needs 'dit', 'lm' and 'shift' in runtime.runner_options; "
            f"got {options!r}"
        )
    if job.get("init_audio") or job.get("inpaint_range"):
        raise ValueError(
            "ACE-Step 1.5 cover and repaint are not connected to the remix control"
        )
    if job.get("guidance") is not None:
        raise ValueError("ACE-Step 1.5 turbo has no guidance control")
    if job.get("steps") is None:
        raise ValueError("ACE-Step 1.5 needs a step count")
    lyrics = job.get("lyrics") or INSTRUMENTAL
    return {
        "dit": str(dit),
        "lm": str(lm),
        "caption": job["prompt"],
        "lyrics": lyrics,
        "instrumental": lyrics.strip() == INSTRUMENTAL,
        "duration": float(job["duration"]),
        "steps": int(job["steps"]),
        "seed": int(job["seed"]),
        "shift": float(shift),
    }


def main() -> int:
    job = json.load(sys.stdin)
    try:
        request = request_from_job(job)
    except (KeyError, TypeError, ValueError) as exc:
        sys.stderr.write(str(exc))
        return 2

    from acestep.handler import AceStepHandler
    from acestep.inference import GenerationConfig, GenerationParams, generate_music
    from acestep.llm_inference import LLMHandler
    import acestep

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(acestep.__file__)))
    started = time.time()
    dit = AceStepHandler()
    status, ok = dit.initialize_service(
        project_root=project_root,
        config_path=request["dit"],
        device="auto",
        use_mlx_dit=True,
    )
    if (
        not ok
        or not getattr(dit, "use_mlx_dit", False)
        or getattr(dit, "mlx_decoder", None) is None
    ):
        sys.stderr.write(status or "ACE-Step DiT is not on MLX")
        return 1

    checkpoint_dir = os.path.join(project_root, "checkpoints")
    lm = LLMHandler()
    lm_status, lm_ok = lm.initialize(
        checkpoint_dir=checkpoint_dir,
        lm_model_path=request["lm"],
        backend="mlx",
        device="mps",
    )
    if not lm_ok or getattr(lm, "llm_backend", None) != "mlx":
        sys.stderr.write(lm_status or "ACE-Step planner is not on MLX")
        return 1

    params = GenerationParams(
        task_type="text2music",
        caption=request["caption"],
        lyrics=request["lyrics"],
        instrumental=request["instrumental"],
        duration=request["duration"],
        inference_steps=request["steps"],
        seed=request["seed"],
        shift=request["shift"],
        thinking=True,
        use_cot_caption=False,
        use_cot_lyrics=False,
    )
    config = GenerationConfig(
        batch_size=1,
        use_random_seed=False,
        seeds=[request["seed"]],
        audio_format="wav",
    )
    save_dir = tempfile.mkdtemp(prefix="acestep-")
    try:
        result = generate_music(dit, lm, params, config, save_dir=save_dir)
        if not result.success or not result.audios:
            sys.stderr.write(result.error or result.status_message or "ACE-Step returned no audio")
            return 1
        produced = result.audios[0].get("path")
        if not produced or not os.path.isfile(produced):
            sys.stderr.write(f"ACE-Step did not write audio ({produced!r})")
            return 1
        shutil.move(produced, job["output_path"])
    finally:
        shutil.rmtree(save_dir, ignore_errors=True)

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
