"""Ordered installed routes. Only a pre-dispatch Offline permits fallback."""
from __future__ import annotations

from . import backends, comfy_ace

LABELS = {"local": "Local device", "cuda": "RTX 4090 (ComfyUI)"}


def validate_preference(backend: backends.Backend, preference: str) -> str:
    if preference != "auto" and preference not in backend.devices:
        raise ValueError(f"{backend.name} does not support device {preference!r}")
    return preference


def public_execution(value) -> dict | None:
    """Old or malformed sidecars must not turn route details into a UI crash."""
    if not isinstance(value, dict):
        return None
    if any(not isinstance(value.get(key), str) for key in ("actual", "preferred", "requested")):
        return None
    if (value.get("actual") not in LABELS or value.get("preferred") not in LABELS
            or value.get("requested") not in {"auto", "local", "cuda"}
            or (value.get("fallback_reason") is not None
                and not isinstance(value.get("fallback_reason"), str))):
        return None
    return {key: value.get(key) for key in ("requested", "preferred", "actual", "fallback_reason")} | {"label": LABELS[value["actual"]]}


def render(backend: backends.Backend, job: dict, preference: str = "auto") -> dict:
    validate_preference(backend, preference)
    candidates = backend.devices if preference == "auto" else (preference,)
    unavailable = []
    for device in candidates:
        if device == "cuda":
            try:
                result = comfy_ace.render(backend.name, job)
            except comfy_ace.Offline:
                unavailable.append("RTX 4090 route disabled, unreachable or missing required weights")
                continue
        else:
            if not backend.available:
                unavailable.append(f"Local backend not set up: {backend.availability_error}")
                continue
            result = backends.run_subprocess(backend, job)
        result["_execution"] = {
            "requested": preference,
            "preferred": candidates[0],
            "actual": device,
            "label": LABELS[device],
            "fallback_reason": "; ".join(unavailable) or None,
        }
        return result
    raise RuntimeError(f"No available device for {backend.name}: {'; '.join(unavailable)}")
