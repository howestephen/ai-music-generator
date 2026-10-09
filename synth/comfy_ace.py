"""ACE-Step 1.5 on Seneca's 4090, through the ComfyUI that is already open there.

The graph is the official split workflow that matches the weights on that machine:
turbo DiT, the 0.6B and 4B text encoders, and the 1.5 VAE. The 1.7B encoder from
the other template is not installed. Stable Audio weights are not on that box, so
this module refuses every backend except acestep. If Seneca does not answer, the
caller keeps the MLX runner.
"""
from __future__ import annotations

import io
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

UNET = "acestep_v1.5_turbo.safetensors"
CLIP_SMALL = "qwen_0.6b_ace15.safetensors"
CLIP_LARGE = "qwen_4b_ace15.safetensors"
VAE = "ace_1.5_vae.safetensors"
DEFAULT_URL = "http://seneca.tail37ad60.ts.net:8000"
KEYSCALES = (
    "C major", "C# major", "Db major", "D major", "D# major", "Eb major",
    "E major", "F major", "F# major", "Gb major", "G major", "G# major",
    "Ab major", "A major", "A# major", "Bb major", "B major",
    "C minor", "C# minor", "Db minor", "D minor", "D# minor", "Eb minor",
    "E minor", "F minor", "F# minor", "Gb minor", "G minor", "G# minor",
    "Ab minor", "A minor", "A# minor", "Bb minor", "B minor",
)
_BPM = re.compile(r"(?<!\d)(\d{2,3})\s*bpm\b", re.IGNORECASE)
_probe_cache = {"url": "", "ok": False, "until": 0.0}


class Offline(Exception):
    """Seneca did not take the job. The Mac runner may still run it."""


def base_url() -> str:
    return os.environ.get("AI_MUSIC_COMFY_URL", DEFAULT_URL).rstrip("/")


def clear_probe_cache() -> None:
    _probe_cache.update(url="", ok=False, until=0.0)


def bpm_from_caption(text: str) -> int:
    match = _BPM.search(text or "")
    if match is None:
        return 120
    return min(300, max(10, int(match.group(1))))


def key_from_caption(text: str) -> str:
    lowered = (text or "").lower()
    for name in sorted(KEYSCALES, key=len, reverse=True):
        if name.lower() in lowered:
            return name
    return "C major"


def build_graph(job: dict) -> dict:
    """API-format graph. Node choices follow audio_ace_step_1_5_split_4b."""
    if job.get("init_audio") or job.get("inpaint_range"):
        raise ValueError(
            "ACE-Step 1.5 cover and repaint are not connected to the remix control"
        )
    if job.get("guidance") is not None:
        raise ValueError("ACE-Step 1.5 turbo has no guidance control")
    if job.get("steps") is None:
        raise ValueError("ACE-Step 1.5 needs a step count")
    options = job.get("options") or {}
    shift = options.get("shift")
    if shift in (None, ""):
        raise ValueError("ACE-Step 1.5 needs 'shift' in runtime.runner_options")
    caption = str(job["prompt"])
    duration = float(job["duration"])
    seed = int(job["seed"])
    steps = int(job["steps"])
    lyrics = str(job.get("lyrics") or "[Instrumental]")
    return {
        "104": {
            "class_type": "UNETLoader",
            "inputs": {"unet_name": UNET, "weight_dtype": "default"},
        },
        "105": {
            "class_type": "DualCLIPLoader",
            "inputs": {
                "clip_name1": CLIP_SMALL,
                "clip_name2": CLIP_LARGE,
                "type": "ace",
            },
        },
        "106": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": VAE},
        },
        "78": {
            "class_type": "ModelSamplingAuraFlow",
            "inputs": {"model": ["104", 0], "shift": float(shift)},
        },
        "94": {
            "class_type": "TextEncodeAceStepAudio1.5",
            "inputs": {
                "clip": ["105", 0],
                "tags": caption,
                "lyrics": lyrics,
                "seed": seed,
                "bpm": bpm_from_caption(caption),
                "duration": duration,
                "timesignature": "4",
                "language": "en",
                "keyscale": key_from_caption(caption),
                "generate_audio_codes": True,
                "cfg_scale": 2.0,
                "temperature": 0.85,
                "top_p": 0.9,
                "top_k": 0,
                "min_p": 0.0,
            },
        },
        "47": {
            "class_type": "ConditioningZeroOut",
            "inputs": {"conditioning": ["94", 0]},
        },
        "98": {
            "class_type": "EmptyAceStep1.5LatentAudio",
            "inputs": {"seconds": duration, "batch_size": 1},
        },
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["78", 0],
                "seed": seed,
                "steps": steps,
                "cfg": 1.0,
                "sampler_name": "euler",
                "scheduler": "simple",
                "positive": ["94", 0],
                "negative": ["47", 0],
                "latent_image": ["98", 0],
                "denoise": 1.0,
            },
        },
        "18": {
            "class_type": "VAEDecodeAudio",
            "inputs": {"samples": ["3", 0], "vae": ["106", 0]},
        },
        "107": {
            "class_type": "SaveAudio",
            "inputs": {
                "audio": ["18", 0],
                "filename_prefix": "ai-music-generator/ace",
            },
        },
    }


def render(backend_name: str, job: dict) -> dict:
    if os.environ.get("AI_MUSIC_COMFY", "1") == "0" or backend_name != "acestep":
        raise Offline("ACE-Step stays on this Mac")
    url = base_url()
    if not probe(url):
        raise Offline(url)
    graph = build_graph(job)
    started = time.time()
    prompt_id = _submit(url, graph)
    described = _wait(url, prompt_id, timeout=7200)
    audio = _download(url, described)
    _write_wav(audio, job["output_path"])
    return {
        "path": job["output_path"],
        "elapsed_seconds": round(time.time() - started, 1),
        "dtype": "ComfyUI (runtime dtype not reported)",
    }


def probe(url: str | None = None) -> bool:
    target = (url or base_url()).rstrip("/")
    now = time.time()
    if _probe_cache["url"] == target and now < _probe_cache["until"]:
        return bool(_probe_cache["ok"])
    ok = _probe_now(target)
    _probe_cache.update(url=target, ok=ok, until=now + (60 if ok else 20))
    return ok


def _probe_now(url: str) -> bool:
    try:
        stats = _request(f"{url}/system_stats", timeout=2, soft=True)
        folders = {
            "diffusion_models": _request(f"{url}/models/diffusion_models", timeout=3, soft=True),
            "text_encoders": _request(f"{url}/models/text_encoders", timeout=3, soft=True),
            "vae": _request(f"{url}/models/vae", timeout=3, soft=True),
        }
    except (Offline, RuntimeError, json.JSONDecodeError, ValueError, TypeError):
        return False
    devices = stats.get("devices") if isinstance(stats, dict) else None
    if not isinstance(devices, list) or not any(
        isinstance(device, dict) and "4090" in str(device.get("name", ""))
        for device in devices
    ):
        return False
    needed = {
        "diffusion_models": UNET,
        "text_encoders": CLIP_SMALL,
        "vae": VAE,
    }
    for folder, filename in needed.items():
        names = folders[folder]
        if not isinstance(names, list) or filename not in names:
            return False
    encoders = folders["text_encoders"]
    return isinstance(encoders, list) and CLIP_LARGE in encoders


def _submit(url: str, graph: dict) -> str:
    body = _request(
        f"{url}/prompt",
        {"prompt": graph, "client_id": uuid.uuid4().hex},
        timeout=30,
        soft=False,
    )
    if not isinstance(body, dict) or body.get("node_errors") or "prompt_id" not in body:
        raise RuntimeError(f"ComfyUI rejected the ACE-Step graph ({body!r})"[:500])
    return str(body["prompt_id"])


def _wait(url: str, prompt_id: str, timeout: float) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        history = _request(f"{url}/history/{prompt_id}", timeout=20, soft=False)
        entry = history.get(prompt_id) if isinstance(history, dict) else None
        if isinstance(entry, dict):
            status = entry.get("status") or {}
            if status.get("status_str") == "error":
                raise RuntimeError(f"ComfyUI ACE-Step failed ({_status_text(entry)})")
            if status.get("completed"):
                return _audio_ref(entry)
        time.sleep(1.5)
    raise RuntimeError("ComfyUI did not finish the ACE-Step job")


def _audio_ref(entry: dict) -> dict:
    outputs = entry.get("outputs") or {}
    if isinstance(outputs, dict):
        for node in outputs.values():
            if not isinstance(node, dict):
                continue
            for value in node.values():
                if isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict) and item.get("filename"):
                            return item
    raise RuntimeError("ComfyUI finished without an audio file")


def _download(url: str, described: dict) -> bytes:
    query = urllib.parse.urlencode({
        "filename": described["filename"],
        "subfolder": described.get("subfolder") or "",
        "type": described.get("type") or "output",
    })
    return _read(f"{url}/view?{query}", timeout=120, soft=False)


def _write_wav(data: bytes, dest: str) -> None:
    if data[:4] == b"RIFF":
        with open(dest, "wb") as handle:
            handle.write(data)
        return
    import soundfile as sf
    audio, rate = sf.read(io.BytesIO(data))
    sf.write(dest, audio, rate)


def _status_text(entry: dict) -> str:
    messages = (entry.get("status") or {}).get("messages") or []
    text = json.dumps(messages, default=str)
    return text[:400]


def _request(url: str, payload: dict | None = None, timeout: float = 20, *, soft: bool):
    raw = _read(url, payload, timeout, soft)
    if not raw:
        return {}
    return json.loads(raw)


def _read(url: str, payload: dict | None = None, timeout: float = 20, soft: bool = False) -> bytes:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        raise RuntimeError(f"ComfyUI {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        if soft:
            raise Offline(str(exc)) from exc
        raise RuntimeError(f"ComfyUI connection failed: {exc}") from exc
