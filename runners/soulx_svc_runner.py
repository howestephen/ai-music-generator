"""SoulX-Singer voice conversion, MLX weights through the official PyTorch module.

Executes inside .venv-soulx. A conversion follows a sung recording. The voice
is an uploaded reference, or the English example when none is given. Pitch
comes from the official RMVPE checkpoint, not from a typed melody.
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

CLONE = Path.home() / ".cache" / "ai-music-generator" / "SoulX-Singer-MLX"
PROMPT_WAV = CLONE / "example" / "audio" / "en_prompt.mp3"
MODEL_ID = "mlx-community/SoulX-Singer"
RMVPE_REPO = "Soul-AILab/SoulX-Singer-Preprocess"
RMVPE_FILE = "rmvpe/rmvpe.pt"
# soulxsinger.yaml: 24 kHz audio, hop 480. The extractor's own default cap is
# 300s, which would clip a recording this backend accepts up to 600s.
F0_RATE = 24000
F0_HOP = 480
F0_MAX_SECONDS = 600.0
N_STEPS = 32
CFG = 3.0


def request_from_job(job: dict) -> dict:
    """A conversion is a recording plus an optional voice. A melody is refused."""
    options = job.get("options") or {}
    if options.get("component") != "svc":
        raise ValueError("SoulX-SVC needs the svc component")
    if job.get("notes"):
        raise ValueError("SoulX-SVC does not take a melody")
    if str(job.get("lyrics") or "").strip():
        raise ValueError("SoulX-SVC does not take lyrics")
    target = str(job.get("target_audio") or "").strip()
    if not target:
        raise ValueError("SoulX-SVC needs a sung recording")
    prompt = job.get("prompt_audio")
    if prompt is not None:
        prompt = str(prompt).strip() or None
    if job.get("seed") is None:
        raise ValueError("SoulX-SVC needs a seed")
    if not job.get("output_path"):
        raise ValueError("SoulX-SVC needs an output path")
    return {
        "target_audio": target,
        "prompt_audio": prompt,
        "seed": int(job["seed"]),
        "output_path": job["output_path"],
    }


def rmvpe_path() -> Path:
    return CLONE / "models" / "SoulX-Singer-Preprocess" / RMVPE_FILE


def main() -> int:
    job = json.load(sys.stdin)
    try:
        request = request_from_job(job)
    except (KeyError, TypeError, ValueError) as exc:
        sys.stderr.write(str(exc))
        return 2
    if not CLONE.is_dir() or not PROMPT_WAV.is_file():
        sys.stderr.write(f"SoulX bridge is not at {CLONE}")
        return 1
    target = Path(request["target_audio"])
    prompt = Path(request["prompt_audio"]) if request["prompt_audio"] else PROMPT_WAV
    if not target.is_file():
        sys.stderr.write(f"recording is not a file: {target}")
        return 2
    if not prompt.is_file():
        sys.stderr.write(f"voice is not a file: {prompt}")
        return 2

    sys.path.insert(0, str(CLONE))
    from huggingface_hub import hf_hub_download, snapshot_download

    model_dir = CLONE / "models" / "SoulX-Singer"
    if not (model_dir / "svc").is_dir():
        snapshot_download(MODEL_ID, local_dir=str(model_dir))
    weights = rmvpe_path()
    if not weights.is_file():
        hf_hub_download(RMVPE_REPO, RMVPE_FILE, local_dir=str(weights.parent.parent))
    if not weights.is_file():
        sys.stderr.write(f"RMVPE checkpoint is not at {weights}")
        return 1

    import numpy as np
    import torch
    from preprocess.tools.f0_extraction import F0Extractor
    from scripts.mlx_bridge import load_component_state
    from soulxsinger.models.soulxsinger_svc import SoulXSingerSVC
    from soulxsinger.utils.file_utils import load_config
    from cli.inference_svc import process as process_svc

    started = time.time()
    save_dir = Path(tempfile.mkdtemp(prefix="soulx-svc-"))
    try:
        extractor = F0Extractor(
            str(weights),
            device="mps",
            is_half=False,
            target_sr=F0_RATE,
            hop_size=F0_HOP,
            max_duration=F0_MAX_SECONDS,
            verbose=False,
        )
        prompt_f0 = save_dir / "prompt_f0.npy"
        target_f0 = save_dir / "target_f0.npy"
        extractor.process(str(prompt), f0_path=str(prompt_f0))
        extractor.process(str(target), f0_path=str(target_f0))

        torch.manual_seed(request["seed"])
        np.random.seed(request["seed"] % (2**32))
        config = load_config(str(CLONE / "soulxsinger/config/soulxsinger.yaml"))
        model = SoulXSingerSVC(config).to("mps")
        model.load_state_dict(load_component_state(model_dir, "svc"), strict=True)
        model.eval().to("mps")

        class Args:
            pass

        args = Args()
        args.device = "mps"
        args.prompt_wav_path = str(prompt)
        args.target_wav_path = str(target)
        args.prompt_f0_path = str(prompt_f0)
        args.target_f0_path = str(target_f0)
        args.save_dir = str(save_dir)
        args.auto_shift = True
        args.pitch_shift = 0
        args.n_steps = N_STEPS
        args.cfg = CFG
        args.use_fp16 = False
        process_svc(args, config, model)
        produced = save_dir / "generated.wav"
        if not produced.is_file():
            sys.stderr.write("SoulX-SVC did not write generated.wav")
            return 1
        os.replace(produced, request["output_path"])
    finally:
        for child in save_dir.iterdir():
            child.unlink(missing_ok=True)
        save_dir.rmdir()
    json.dump(
        {
            "path": request["output_path"],
            "elapsed_seconds": round(time.time() - started, 1),
            "backend": "mlx",
        },
        sys.stdout,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
