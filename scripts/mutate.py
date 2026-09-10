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
]


def suite_passes() -> bool:
    shutil.rmtree(ROOT / "synth" / "__pycache__", ignore_errors=True)
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
