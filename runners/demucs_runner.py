"""HTDemucs on MLX. Executes inside .venv-demucs - see synth/backends.py.

A mix comes back as vocals, drums, bass and other. A stem with nothing in it
is a real result, so silence is written rather than failed.
"""
import json
import os
import sys
import time

os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

STEMS = ("vocals", "drums", "bass", "other")


def request_from_job(job: dict) -> dict:
    """The fields this separation actually uses."""
    options = job.get("options") or {}
    model = options.get("model")
    outputs = job.get("outputs")
    source = job.get("init_audio")
    if not model:
        raise ValueError("Demucs needs 'model' in runtime.runner_options")
    if not source:
        raise ValueError("Demucs needs the mix as init_audio")
    if not isinstance(outputs, dict) or set(outputs) != set(STEMS):
        raise ValueError(f"Demucs needs outputs for {', '.join(STEMS)}")
    if any(not isinstance(path, str) or not path for path in outputs.values()):
        raise ValueError("Demucs stem paths must be non-empty strings")
    if job.get("seed") is None:
        raise ValueError("Demucs needs a seed")
    return {
        "model": str(model),
        "source": str(source),
        "seed": int(job["seed"]),
        "outputs": {name: str(outputs[name]) for name in STEMS},
    }


def as_frames(audio):
    """(channels, samples) or (samples,) becomes (samples, channels) for the WAV."""
    import numpy as np

    array = np.asarray(audio, dtype=np.float32)
    if array.ndim == 1:
        array = array[:, None]
    elif array.ndim == 2 and array.shape[0] <= 8 and array.shape[0] < array.shape[1]:
        array = array.T
    elif array.ndim != 2:
        raise ValueError(f"Demucs stem has shape {array.shape}")
    return np.ascontiguousarray(array)


def main() -> int:
    job = json.load(sys.stdin)
    try:
        request = request_from_job(job)
    except (KeyError, TypeError, ValueError) as exc:
        sys.stderr.write(str(exc))
        return 2

    import soundfile as sf
    from demucs_mlx import Separator

    started = time.time()
    separator = Separator(model=request["model"], shifts=1, seed=request["seed"])
    _origin, stems = separator.separate_audio_file(request["source"])
    missing = [name for name in STEMS if name not in stems]
    if missing:
        sys.stderr.write(f"Demucs did not return {', '.join(missing)}")
        return 1
    rate = int(separator.samplerate)
    for name in STEMS:
        sf.write(request["outputs"][name], as_frames(stems[name]), rate, subtype="PCM_16")
    json.dump(
        {
            "path": request["outputs"]["vocals"],
            "paths": request["outputs"],
            "elapsed_seconds": round(time.time() - started, 1),
        },
        sys.stdout,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
