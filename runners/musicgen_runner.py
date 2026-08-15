"""MusicGen runner. Runs in the main .venv.

NOTE: MusicGen weights are CC-BY-NC-4.0 — non-commercial use only.
Fine for experimentation; do not ship its output commercially.
"""
import json
import os
import sys
import time
import warnings

os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
warnings.filterwarnings("ignore")

import soundfile as sf
import torch
from transformers import AutoProcessor, MusicgenForConditionalGeneration

MODEL_ID = "facebook/musicgen-stereo-large"
TOKENS_PER_SECOND = 50  # MusicGen emits ~50 audio tokens per second


def main() -> int:
    job = json.load(sys.stdin)
    started = time.time()

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    processor = AutoProcessor.from_pretrained(MODEL_ID)
    model = MusicgenForConditionalGeneration.from_pretrained(
        MODEL_ID, torch_dtype=torch.float32
    ).to(device).eval()
    loaded = time.time()

    duration = min(float(job["duration"]), 30.0)  # hard architectural cap
    torch.manual_seed(int(job["seed"]))

    inputs = processor(text=[job["prompt"]], padding=True, return_tensors="pt").to(device)
    with torch.no_grad():
        audio = model.generate(
            **inputs,
            do_sample=True,
            guidance_scale=float(job.get("guidance", 3.0)),
            max_new_tokens=int(TOKENS_PER_SECOND * duration),
        )

    sr = model.config.audio_encoder.sampling_rate
    sf.write(job["output_path"], audio[0].cpu().float().numpy().T, sr)

    json.dump(
        {
            "path": job["output_path"],
            "elapsed_seconds": round(time.time() - started, 1),
            "load_seconds": round(loaded - started, 1),
            "sampling_rate": int(sr),
            "device": device,
            "truncated_to": duration,
        },
        sys.stdout,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
