"""Command line interface. This is the entry point Claude drives."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import backends, core


def _print_track(track: core.Track, as_json: bool) -> None:
    if as_json:
        # One object per line (JSON Lines), so --count N stays machine-parseable.
        print(json.dumps({**json.loads(track.sidecar_path().read_text(encoding="utf-8")),
                          "path": str(track.path)}))
    else:
        print(f"  -> {track.path.name}  ({track.elapsed_seconds}s, seed {track.seed})")


def cmd_gen(args: argparse.Namespace) -> int:
    for i in range(args.count):
        # Only the first generation reuses an explicit seed; the rest vary,
        # otherwise --count would produce N identical files.
        seed = args.seed if (args.seed is not None and i == 0) else None
        if args.count > 1 and not args.json:
            print(f"[{i + 1}/{args.count}] {args.prompt}")
        track = core.generate(
            prompt=args.prompt,
            duration=args.duration,
            seed=seed,
            infer_step=args.steps,
            guidance_scale=args.guidance,
            lyrics=args.lyrics,
            model=args.model,
        )
        _print_track(track, args.json)
    return 0


def cmd_batch(args: argparse.Namespace) -> int:
    prompt_dir = Path(args.dir) if args.dir else core.PROMPTS_DIR
    prompt_dir.mkdir(parents=True, exist_ok=True)

    jobs: list[tuple[str, str]] = []
    for file in sorted(prompt_dir.glob("*.txt")):
        for line in file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                jobs.append((file.name, line))

    if not jobs:
        print(f"No prompts found in {prompt_dir}/. Add a .txt file with one prompt per line.")
        return 1

    print(f"{len(jobs)} prompt(s) from {prompt_dir}/\n")
    failures = 0
    for i, (source, prompt) in enumerate(jobs, 1):
        print(f"[{i}/{len(jobs)}] ({source}) {prompt}")
        for n in range(args.count):
            try:
                track = core.generate(
                    prompt=prompt,
                    duration=args.duration,
                    seed=None,
                    infer_step=args.steps,
                    guidance_scale=args.guidance,
                    lyrics=args.lyrics,
                    model=args.model,
                )
                _print_track(track, as_json=False)
            except Exception as exc:  # one bad prompt shouldn't kill an overnight run
                failures += 1
                print(f"  !! failed: {exc}", file=sys.stderr)

    print(f"\nDone. Output in {core.OUTPUT_DIR}/")
    if failures:
        print(f"{failures} generation(s) failed.", file=sys.stderr)
    return 1 if failures else 0


def _knob(value) -> str:
    return "n/a" if value is None else f"{value:g}"


def cmd_models(args: argparse.Namespace) -> int:
    for name, b in sorted(backends.BACKENDS.items()):
        mark = "ok " if b.available else "MISSING"
        star = " *" if name == core.DEFAULT_MODEL else "  "
        print(f"{star}{name:12} [{mark}] {b.model_id}")
        print(f"              max {b.max_duration:.0f}s | steps {_knob(b.default_steps)} | "
              f"guidance {_knob(b.default_guidance)} | prompt: {b.prompt_style} | {b.dtype}")
        print(f"              {b.licence}")
        print(f"              {b.notes}\n")
    print("* = default. Override with --model/-m. 'n/a' = the backend has no such control.")
    return 0


def cmd_ui(args: argparse.Namespace) -> int:
    # app.py sits at the project root, which isn't importable when the CLI is
    # invoked from another directory.
    sys.path.insert(0, str(core.PROJECT_ROOT))
    from app import main as ui_main

    ui_main(share=False, port=args.port)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="synth",
        description="Describe music in words, render it locally.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--duration", "-d", type=float, default=60.0,
                       help="length in seconds (default: 60)")
        p.add_argument("--steps", type=int, default=None,
                       help="inference steps; lower is faster, rougher "
                            "(default: the backend's own, see `models`)")
        p.add_argument("--guidance", "-g", type=float, default=None,
                       help="prompt adherence; higher follows the prompt harder "
                            "(default: the backend's own, see `models`)")
        p.add_argument("--lyrics", default=None,
                       help="lyrics; default is the backend's instrumental sentinel")
        p.add_argument("--count", "-n", type=int, default=1,
                       help="variations to generate per prompt (default: 1)")
        p.add_argument("--model", "-m", default=core.DEFAULT_MODEL,
                       choices=sorted(backends.BACKENDS),
                       help=f"backend to use (default: {core.DEFAULT_MODEL})")

    gen = sub.add_parser("gen", help="generate from a single prompt")
    gen.add_argument("prompt", help="style tags for acestep/musicgen, e.g. 'lo-fi hip hop, "
                                    "warm rhodes, 85bpm'; a structured caption for minimax-mlx")
    gen.add_argument("--seed", type=int, default=None, help="reproduce a previous track")
    gen.add_argument("--json", action="store_true", help="machine-readable output, one JSON object per line")
    add_common(gen)
    gen.set_defaults(func=cmd_gen)

    batch = sub.add_parser("batch", help="generate from every prompt in prompts/")
    batch.add_argument("--dir", default=None, help="prompt directory (default: prompts/)")
    add_common(batch)
    batch.set_defaults(func=cmd_batch)

    models = sub.add_parser("models", help="list available backends")
    models.set_defaults(func=cmd_models)

    ui = sub.add_parser("ui", help="launch the local web UI")
    ui.add_argument("--port", type=int, default=7860)
    ui.set_defaults(func=cmd_ui)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
