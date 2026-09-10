#!/usr/bin/env python3
"""Manual structure and anti-drift check for this project.

**A shim, deliberately.** The rules have ONE implementation, in the hook kit,
which is installed once per machine. This file only says which source to judge:
the working tree by default, the index with --index (what the commit hook sees).

Exit codes: 0 = clean (warnings allowed), 1 = violations, 2 = no kit installed.

    <python> scripts/validate.py            # check the files on disk
    <python> scripts/validate.py --index    # check what is staged, as the hook does

Stdlib only.
"""
import subprocess
import sys
from pathlib import Path


def kit_dir() -> Path:
    r = subprocess.run(["git", "config", "--global", "--get", "core.hooksPath"],
                       capture_output=True, text=True)
    p = Path(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else None
    if p and (p / "structure_gate.py").is_file():
        return p
    print("validate: no hook kit installed on this machine, so nothing is "
          "gating this project.\n"
          "  Fix: python3 <repos>/_projects-admin/scripts/install_global_hooks.py --apply",
          file=sys.stderr)
    raise SystemExit(2)


sys.path.insert(0, str(kit_dir()))
import structure_gate  # noqa: E402


if __name__ == "__main__":
    argv = sys.argv[1:]
    if "--index" not in argv and "--worktree" not in argv:
        argv.append("--worktree")
    argv = [a for a in argv if a != "--index"]
    sys.exit(structure_gate.main(argv, label="validate"))
