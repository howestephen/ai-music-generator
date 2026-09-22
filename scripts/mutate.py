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
    ("default backend reverts to ACE-Step", "synth/backends.json",
     '  "default_backend": "stable-audio-medium",',
     '  "default_backend": "acestep",'),
    ("drop steps from job dict", "synth/core.py", '            "steps": steps,', "            "),
    ("musicgen guidance back to 15", "synth/backends.json",
     '          "default": 3,\n'
     '          "minimum": 0,\n'
     '          "maximum": 30,\n'
     '          "step": 0.1,\n'
     '          "label": "Prompt adherence",\n'
     '          "info": "MusicGen guidance scale. Default: 3.",',
     '          "default": 15,\n'
     '          "minimum": 0,\n'
     '          "maximum": 30,\n'
     '          "step": 0.1,\n'
     '          "label": "Prompt adherence",\n'
     '          "info": "MusicGen guidance scale. Default: 15.",'),
    ("stamp float32 for everyone", "synth/core.py", "dtype=backend.dtype,", 'dtype="float32",'),
    ("sidecar backend = model_id", "synth/core.py", "backend=backend.name,", "backend=backend.model_id,"),
    ("silently drop unsupported knob", "synth/core.py",
     '            raise ValueError(f"{backend.name} has no {knob} control (got {value!r})")', "            pass"),
    ("musicgen accepts lyrics", "synth/backends.json",
     '      "notes": "Strong instrumental model, but 30s per generation.",\n'
     '      "dtype": "float32",\n'
     '      "prompt_style": "tags",\n'
     '      "instrumental_tag": "",\n'
     '      "supports_lyrics": false,',
     '      "notes": "Strong instrumental model, but 30s per generation.",\n'
     '      "dtype": "float32",\n'
     '      "prompt_style": "tags",\n'
     '      "instrumental_tag": "",\n'
     '      "supports_lyrics": true,'),
    ("minimax default steps = 60", "synth/backends.json",
     '          "default": 30,\n'
     '          "minimum": 1,\n'
     '          "maximum": null,',
     '          "default": 60,\n'
     '          "minimum": 1,\n'
     '          "maximum": null,'),
    ("runner drops steps=0", "runners/minimax_mlx_runner.py",
     '    if job.get("steps") is not None:', '    if job.get("steps"):'),
    ("runner uses stale console script", "runners/minimax_mlx_runner.py",
     '        sys.executable, MIN_DURATION_WRAPPER, "_generate", "generate",',
     '        "mlx-minimax-music3", "generate",'),
    ("runner stops enforcing MiniMax minimum duration", "runners/minimax_mlx_runner.py",
     '        "--min-duration", str(float(job["duration"])),',
     '        "--min-duration", "1.0",'),
    ("MiniMax wrapper allows an early stop token", "runners/minimax_mlx_runner.py",
     "        if completed_frames < minimum_frames:",
     "        if False:"),
    ("runner truncates fractional duration", "runners/minimax_mlx_runner.py",
     '        "--duration", str(float(job["duration"])),',
     '        "--duration", str(int(float(job["duration"]))),'),
    ("UI history oldest first", "app.py",
     'return sorted(tracks, key=lambda item: (item["modified_ns"], item["name"]), reverse=True)',
     'return sorted(tracks, key=lambda item: (item["modified_ns"], item["name"]), reverse=False)'),
    ("queued UI job ignores selected model", "app.py",
     '        "guidance_scale": guidance,\n'
     '        "model": backend.name,\n'
     '        "genre": chosen_genre or None,\n'
     '        "_duration_retries": backend.output_audit.random_seed_retries if not use_seed else 0,\n'
     '        "_retry_seed": not use_seed,\n'
     '    }',
     '        "guidance_scale": guidance,\n'
     '        "model": core.DEFAULT_MODEL,\n'
     '        "genre": chosen_genre or None,\n'
     '        "_duration_retries": backend.output_audit.random_seed_retries if not use_seed else 0,\n'
     '        "_retry_seed": not use_seed,\n'
     '    }'),
    ("UI exposes unsupported step control", "app.py",
     "        _control_update(backend.steps),",
     "        gr.update(visible=True),"),
    ("UI API schema is capped below MiniMax", "app.py",
     "                        duration_minimum, duration_maximum,",
     "                        duration_minimum, 240,"),
    ("MiniMax duration is capped like ACE", "synth/backends.json",
     '          "maximum": 300,\n'
     '          "step": 1,\n'
     '          "label": "Target duration (s)",\n'
     '          "info": "MiniMax supports up to 300 seconds. Its stop token is suppressed until the target, then the delivered WAV is measured independently.",',
     '          "maximum": 240,\n'
     '          "step": 1,\n'
     '          "label": "Target duration (s)",\n'
     '          "info": "MiniMax supports up to 240 seconds. Its stop token is suppressed until the target, then the delivered WAV is measured independently.",'),
    ("genre prompt ignores the backend's own style", "app.py",
     "        style=backend.prompt_style,",
     '        style="tags",'),
    ("Generate button stays clickable", "app.py",
     'return gr.update(value="Generating...", interactive=False, variant="secondary")',
     'return gr.update(value="Generating...", interactive=True, variant="secondary")'),
    ("Generate progress returns to a thin strip", "app.py",
     "    inset: 0;",
     "    bottom: 0;\n    height: 0.35rem;\n    left: 0;"),
    ("History column is wider than controls", "app.py",
     'with gr.Column(scale=1, elem_id="history-panel"):',
     'with gr.Column(scale=2, elem_id="history-panel"):'),
    ("history audio goes back through Gradio's file copy", "app.py",
     '    src = html.escape(f"/gradio_api/file={Path(track[\'path\']).resolve()}", quote=True)',
     '    src = html.escape(str(track["path"]), quote=True)'),
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
    ("numeric controls accept infinite values", "synth/backends.py",
     "        if not math.isfinite(number):",
     "        if False:"),
    ("manifest accepts non-finite numeric fields", "synth/backends.py",
     "                or not math.isfinite(value)",
     "                or False"),
    ("manifest accepts booleans as numeric fields", "synth/backends.py",
     "                isinstance(value, bool)\n"
     "                or not isinstance(value, (int, float))",
     "                False\n"
     "                or not isinstance(value, (int, float))"),
    ("core truncates fractional duration", "synth/core.py",
     '    duration = backend.duration.validate(duration, f"{backend.name} duration")',
     '    duration = int(backend.duration.validate(duration, f"{backend.name} duration"))'),
    ("new browser trusts stale session queue", "app.py",
     "    return _queue_snapshot()\n\n\ndef _history_items_for_render",
     "    return _session_value\n\n\ndef _history_items_for_render"),
    ("new browser trusts stale session history", "app.py",
     "    return _load_history()\n\n\ndef _poll_ui",
     "    return _session_value\n\n\ndef _poll_ui"),
    ("queue singleton initialisation loses its lock", "app.py",
     "        with _JOB_QUEUE_LOCK:\n"
     "            if _JOB_QUEUE is None:\n"
     "                _JOB_QUEUE = jobs.GenerationQueue(_run_queued_job)",
     "        if _JOB_QUEUE is None:\n"
     "            _JOB_QUEUE = jobs.GenerationQueue(_run_queued_job)"),
    ("runner subprocess has no timeout", "synth/backends.py",
     "        stdout, stderr = proc.communicate(input_text, timeout=timeout_seconds)",
     "        stdout, stderr = proc.communicate(input_text, timeout=None)"),
    ("runner timeout leaves descendants in the parent process group", "synth/backends.py",
     '        start_new_session=os.name == "posix",',
     "        start_new_session=False,"),
    ("timeout never escalates an uncooperative process group", "synth/backends.py",
     "        if group_alive:\n"
     "            try:\n"
     "                os.killpg(proc.pid, signal.SIGKILL)",
     "        if False:\n"
     "            try:\n"
     "                os.killpg(proc.pid, signal.SIGKILL)"),
    ("process-group probe leaks macOS permission errors", "synth/backends.py",
     "            except PermissionError:\n"
     "                # macOS can return EPERM while a terminated process group is",
     "            except RuntimeError:\n"
     "                # macOS can return EPERM while a terminated process group is"),
    ("runtime probe imports nothing", "synth/backends.py",
     '        imports = "; ".join(f"import {module}" for module in self.probe_modules)',
     '        imports = ""'),
    ("runner accepts a missing or empty output", "synth/backends.py",
     "    if not path.is_file() or path.stat().st_size == 0:",
     "    if False:"),
    ("core accepts generation without audio audit", "synth/core.py",
     "        if not isinstance(audio_audit, backends.AudioAudit):",
     "        if False:"),
    ("runner falls back past malformed final JSON", "synth/backends.py",
     "                raise RuntimeError(\n"
     '                    f"{backend.name} runner produced malformed JSON"\n'
     "                ) from exc",
     "                continue"),
    ("runner accepts a different reported path", "synth/backends.py",
     "    if not isinstance(returned_path, str) or Path(returned_path).resolve() != expected.resolve():",
     "    if False:"),
    ("runner accepts non-finite elapsed time", "synth/backends.py",
     "        or not math.isfinite(elapsed)",
     "        or False"),
    ("runner replaces invalid UTF-8", "synth/backends.py",
     '        errors="strict",\n        start_new_session=os.name == "posix",',
     '        errors="replace",\n        start_new_session=os.name == "posix",'),
    ("runner accepts an existing stale output", "synth/backends.py",
     "    if expected.exists():",
     "    if False:"),
    ("runner skips audio stream audit", "synth/backends.py",
     '    result["_audio_audit"] = audit_audio_file(expected, backend.name)',
     '    result["_audio_audit"] = None'),
    ("runner accepts silent audio", "synth/backends.py",
     "    if peak <= 1e-7:",
     "    if False:"),
    ("core accepts a short output", "synth/core.py",
     '        if audit_status != "passed":',
     "        if False:"),
    ("core records the target as delivered duration", "synth/core.py",
     "            duration=round(delivered_duration, 3),",
     "            duration=float(duration),"),
    ("history trusts the old sidecar duration", "app.py",
     "        measured_duration = audio_audit.duration_seconds if audio_audit else None",
     '        measured_duration = metadata.get("duration")'),
    ("UI disables the short-output retry", "app.py",
     '        "_duration_retries": backend.output_audit.random_seed_retries if not use_seed else 0,',
     '        "_duration_retries": 0,'),
    ("queue poll bypasses the queue and stops the render block", "app.py",
     "            outputs=[queue_state, history, history_signature],\n"
     '            show_progress="hidden",',
     "            outputs=[queue_state, history, history_signature],\n"
     "            queue=False,\n"
     '            show_progress="hidden",'),
    ("UI stops serving the output folder", "app.py",
     "        allowed_paths=[str(core.OUTPUT_DIR)],",
     "        "),
    ("runner options never reach the runner", "synth/core.py",
     '                "options": dict(backend.runner_options),',
     "                "),
    ("runner options skip their type check", "synth/backends.py",
     "        if not isinstance(runner_options, dict) or any(",
     "        if False or any("),
    ("runner options are allowed without a runner", "synth/backends.py",
     '        if data["runner"] is None and runner_options:',
     "        if False:"),
    ("exact contract loses its upper bound on delivered duration", "synth/backends.py",
     '        if self.duration_contract != "exact":\n'
     "            return math.inf",
     '        if self.duration_contract != "never":\n'
     "            return math.inf"),
    ("core stops rejecting an overlong render", "synth/core.py",
     "        elif delivered_duration > maximum_duration:\n"
     '            audit_status = "long"',
     "        elif False:\n"
     '            audit_status = "long"'),
    ("exact contract may also tolerate a short render", "synth/backends.py",
     "            if ratio != 1:",
     "            if False:"),
    ("exact contract may also ask for a retry", "synth/backends.py",
     "            if retries != 0:",
     "            if False:"),
    ("manifest accepts any duration contract string", "synth/backends.py",
     "        if contract not in DURATION_CONTRACTS:",
     "        if False:"),
    ("duration policy permits a zero-second floor", "synth/backends.py",
     "        return max(\n"
     "            0.0,\n"
     "            requested_duration * self.minimum_duration_ratio\n"
     "            - self.duration_tolerance_seconds,\n"
     "        )",
     "        return 0.0"),
    ("failed retry keeps its original summary seed", "synth/jobs.py",
     "                    if isinstance(exc, GenerationFailure):",
     "                    if False:"),
    ("concurrent output reservations are not exclusive", "synth/core.py",
     "os.O_CREAT | os.O_EXCL | os.O_WRONLY",
     "os.O_CREAT | os.O_WRONLY"),
    ("MiniMax inner timeout can outlive its adapter", "runners/minimax_mlx_runner.py",
     "COMMAND_TIMEOUT_SECONDS = 7100",
     "COMMAND_TIMEOUT_SECONDS = 7200"),
    ("MiniMax probes only its shallow package root", "synth/backends.json",
     '"probe_modules": ["mlx_minimax_music3.cli"]',
     '"probe_modules": ["mlx_minimax_music3"]'),
    ("analysis silently defaults to D Mixolydian", "synth/analyze.py",
     "    if key is None:\n        return None, None",
     "    if key is None:\n"
     "        return {0, 2, 4, 6, 7, 9, 11}, \"D mixolydian\""),
    ("short analysis uses an empty RMS window", "synth/analyze.py",
     "    window = max(1, len(rms) // 10)",
     "    window = len(rms) // 10"),
    ("one unreadable track aborts analysis batch", "synth/analyze.py",
     "        except Exception as exc:",
     "        except RuntimeError as exc:"),
    ("analysis drops the requested key and scale", "synth/analyze.py",
     "            result = analyse(Path(p), args.hit_interval, args.key, args.scale)",
     "            result = analyse(Path(p), args.hit_interval, None, None)"),
    ("analysis calls strongest pitch the tonic", "synth/analyze.py",
     'f"{\'peak\':>7}  {\'hits\':>8}  edges(start/end)"',
     'f"{\'tonic\':>7}  {\'hits\':>8}  edges(start/end)"'),
    ("analysis calls quiet edges sweeps", "synth/analyze.py",
     'f"{\'peak\':>7}  {\'hits\':>8}  edges(start/end)"',
     'f"{\'peak\':>7}  {\'hits\':>8}  sweeps"'),
    ("analysis reports zero when no hit boundary was tested", "synth/analyze.py",
     "    hit_alignment = None\n"
     "    if len(targets) and onset_env.size and np.isfinite(onset_env).all():",
     "    hit_alignment = 0.0\n"
     "    if len(targets) and onset_env.size and np.isfinite(onset_env).all():"),
    ("analysis scores non-finite onset data as zero hits", "synth/analyze.py",
     "    if len(targets) and onset_env.size and np.isfinite(onset_env).all():",
     "    if len(targets) and onset_env.size:"),
    ("analysis retains an invalid tempo estimate", "synth/analyze.py",
     "    if not math.isfinite(tempo) or tempo <= 0:",
     "    if False:"),
    ("analysis accepts audio with no samples", "synth/analyze.py",
     "    if len(y) == 0 or sr <= 0:",
     "    if False:"),
    ("analysis globally hides runtime warnings", "synth/analyze.py",
     "import sys\nfrom dataclasses import dataclass",
     'import sys\nimport warnings\nwarnings.filterwarnings("ignore")\nfrom dataclasses import dataclass'),
    ("analysis key parsing remains case-sensitive", "synth/analyze.py",
     '    key = key[:1].upper() + key[1:].lower()',
     "    key = key"),
    ("MiniMax install floats off its tested source commit", "README.md",
     "mlx-minimax-music3.git@b42e07bd2c0ffd14cc6b75ca19d9a96e5397eaf9",
     "mlx-minimax-music3.git@v0.1.0"),
    ("gotcha puts MiniMax conversion back in the runner", "docs/gotchas.md",
     "The runner returns JSON from `mlx_minimax_music3.cli`",
     "The runner converts audio from `mlx_minimax_music3.cli`"),
    ("README skips the main environment compatibility check", "README.md",
     "uv pip check --python .venv/bin/python",
     "uv pip check --python .venv-mlx/bin/python"),
    ("README skips the installed backend probe", "README.md",
     "uv pip check --python .venv-mlx/bin/python\n"
     "./.venv/bin/python -m synth.cli models",
     "uv pip check --python .venv-mlx/bin/python\n"
     "./.venv/bin/python -m synth.cli --help"),
    ("MiniMax runner loses the documented XET workaround", "runners/minimax_mlx_runner.py",
     'os.environ.setdefault("HF_HUB_DISABLE_XET", "1")',
     'os.environ.setdefault("HF_HUB_DISABLE_XET", "0")'),
    ("track title ignores seed and genre", "synth/prompting.py",
     'rng = random.Random(f"{int(seed)}\\0{genre or \'\'}\\0{prompt}")',
     "rng = random.Random()"),
    ("new renders drop the selected genre", "synth/core.py",
     "            genre=genre,",
     "            genre=None,"),
    ("text filter matches every track", "app.py",
     "            if needle not in haystack:\n                continue",
     "            if False:\n                continue"),
    ("purge never removes expired deletions", "app.py",
     '        if entry["expires_at"] > clock:\n            continue',
     "        if True:\n            continue"),
    ("keep discard never reaches the sidecar", "app.py",
     '    _write_sidecar_update(wav, {"rating": normalised})',
     "    normalised = normalised"),
    ("delete copies into pending instead of moving", "app.py",
     "    shutil.move(str(wav), str(destination_wav))",
     "    shutil.copy2(str(wav), str(destination_wav))"),
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
