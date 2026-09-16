#!/usr/bin/env python3
"""Prove the unit tests are sensitive to the code they guard.

Applies each mutation below to the INSTALLED source, runs the suite, restores the
file from a byte copy (never git checkout: that would wipe uncommitted work), and
reports. Every mutation must make the suite FAIL; a mutation that passes means the
tests do not cover that rule. Bytecode is cleared before every run because a
same-length edit restored within the same second would otherwise reuse a stale .pyc.

    ./.venv/bin/python scripts/mutate.py

Stdlib only. Exit 0 = every mutation caught, 1 = at least one survived.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = ROOT / ".venv" / "bin" / "python"

MUTATIONS = [
    ("drop steps from job dict", "synth/core.py", '            "steps": steps,', "            "),
    ("musicgen guidance back to 15", "synth/backends.py", "default_guidance=3.0,", "default_guidance=15.0,"),
    ("stamp float32 for everyone", "synth/core.py", "dtype=backend.dtype,", 'dtype="float32",'),
    ("sidecar backend = model_id", "synth/core.py", "backend=backend.name,", "backend=backend.model_id,"),
    ("silently drop unsupported knob", "synth/core.py",
     '            raise ValueError(f"{backend.name} has no {knob} control (got {value!r})")', "            pass"),
    ("musicgen accepts lyrics", "synth/backends.py", "supports_lyrics=False,", "supports_lyrics=True,"),
    ("minimax default steps = 60", "synth/backends.py", "default_steps=30,", "default_steps=60,"),
    ("runner drops steps=0", "runners/minimax_mlx_runner.py",
     '    if job.get("steps") is not None:', '    if job.get("steps"):'),
    ("runner uses stale console script", "runners/minimax_mlx_runner.py",
     '        sys.executable, "-m", "mlx_minimax_music3.cli", "generate",',
     '        "mlx-minimax-music3", "generate",'),
    ("UI history oldest first", "app.py",
     'reverse=True)', 'reverse=False)'),
    ("UI ignores selected model", "app.py",
     "            model=backend.name,", "            model=core.DEFAULT_MODEL,"),
    ("queued UI job ignores selected model", "app.py",
     '        "guidance_scale": guidance if backend.default_guidance is not None else None,\n'
     '        "model": backend.name,\n'
     '    }',
     '        "guidance_scale": guidance if backend.default_guidance is not None else None,\n'
     '        "model": core.DEFAULT_MODEL,\n'
     '    }'),
    ("UI exposes unsupported step control", "app.py",
     "gr.update(value=backend.default_steps or 60, visible=backend.default_steps is not None),",
     "gr.update(value=backend.default_steps or 60, visible=True),"),
    ("MiniMax preset stays as tags", "app.py",
     '    return prompts[backends.get(model).prompt_style]',
     '    return prompts["tags"]'),
    ("Generate button stays clickable", "app.py",
     'return gr.update(value="Generating...", interactive=False, variant="secondary")',
     'return gr.update(value="Generating...", interactive=True, variant="secondary")'),
    ("Generate progress returns to a thin strip", "app.py",
     "    inset: 0;",
     "    bottom: 0;\n    height: 0.35rem;\n    left: 0;"),
    ("History column is wider than controls", "app.py",
     'with gr.Column(scale=1, elem_id="history-panel"):',
     'with gr.Column(scale=2, elem_id="history-panel"):'),
    ("Scrollable built-in waveform is shown", "app.py",
     ".history-audio .waveform-container,\n.history-audio .timestamps,\n"
     ".history-audio .subtitle-display {\n    display: none;\n}",
     ".history-audio .waveform-container,\n.history-audio .timestamps,\n"
     ".history-audio .subtitle-display {\n    display: block;\n}"),
    ("Full waveform cannot seek", "app.py",
     "audio.currentTime = Math.max(0, Math.min(1, position)) * audio.duration;",
     "audio.currentTime = 0;"),
    ("running queue job can be removed", "synth/jobs.py",
     "                if job.id != job_id or job.status == \"running\"",
     "                if job.id != job_id"),
    ("estimated queue progress claims completion", "synth/jobs.py",
     "progress = min(95.0, 90.0 * elapsed / job.expected_seconds)",
     "progress = min(100.0, 90.0 * elapsed / job.expected_seconds)"),
    ("queued job loses its acceptance wipe", "app.py",
     "animation: queued-job-wipe 1.4s ease-in-out infinite;",
     "animation: none;"),
    ("queue trusts a missing output file", "synth/jobs.py",
     '                if not output_path.is_file():',
     '                if False:'),
    ("runtime estimate trusts infinite history metadata", "app.py",
     "            math.isfinite(track_duration)\n"
     "            and math.isfinite(elapsed)",
     "            True\n"
     "            and True"),
    ("UI accepts infinite duration", "app.py",
     "    if not math.isfinite(duration) or duration <= 0:",
     "    if duration <= 0:"),
    ("new browser trusts stale session queue", "app.py",
     "    return _queue_snapshot()\n\n\ndef _history_items_for_render",
     "    return _session_value\n\n\ndef _history_items_for_render"),
    ("new browser trusts stale session history", "app.py",
     "    return _load_history()\n\n\ndef _poll_ui",
     "    return _session_value\n\n\ndef _poll_ui"),
]


def suite_passes() -> bool:
    shutil.rmtree(ROOT / "synth" / "__pycache__", ignore_errors=True)
    shutil.rmtree(ROOT / "__pycache__", ignore_errors=True)
    r = subprocess.run([str(PY), "-B", "-m", "unittest", "discover", "-s", "synth", "-t", "."],
                       cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    return r.returncode == 0


def main() -> int:
    if not suite_passes():
        print("baseline suite FAILS; fix that before mutating", file=sys.stderr)
        return 1
    print("baseline: OK")
    backup = Path(tempfile.mkdtemp())
    survived = 0
    for label, rel, old, new in MUTATIONS:
        target = ROOT / rel
        copy = backup / rel.replace("/", "__")
        shutil.copy2(target, copy)
        src = target.read_text(encoding="utf-8")
        if src.count(old) != 1:
            print(f"mutation [{label}]: target text not unique, skipped", file=sys.stderr)
            survived += 1
            continue
        target.write_text(src.replace(old, new), encoding="utf-8")
        try:
            caught = not suite_passes()
        finally:
            shutil.copy2(copy, target)
        print(f"mutation [{label}]: {'caught' if caught else 'SURVIVED'}")
        survived += 0 if caught else 1
    shutil.rmtree(backup, ignore_errors=True)
    ok = suite_passes()
    print(f"restored: {'OK' if ok else 'FAIL'}; {len(MUTATIONS) - survived}/{len(MUTATIONS)} caught")
    return 0 if ok and survived == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
