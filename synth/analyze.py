"""Measure tempo, optional pitch-collection coverage, hit points and edge loudness."""
from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

PITCH_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
KEY_PITCH_CLASS = {
    "C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3,
    "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8,
    "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11,
}
SCALE_INTERVALS = {
    "major": (0, 2, 4, 5, 7, 9, 11),
    "minor": (0, 2, 3, 5, 7, 8, 10),
    "dorian": (0, 2, 3, 5, 7, 9, 10),
    "phrygian": (0, 1, 3, 5, 7, 8, 10),
    "lydian": (0, 2, 4, 6, 7, 9, 11),
    "mixolydian": (0, 2, 4, 5, 7, 9, 10),
    "locrian": (0, 1, 3, 5, 6, 8, 10),
    "harmonic-minor": (0, 2, 3, 5, 7, 8, 11),
}


@dataclass
class Analysis:
    name: str
    duration: float
    tempo: float | None
    target_collection: str | None
    pitch_coverage: float | None
    peak_pitch: str
    hit_alignment: float | None
    quiet_start: bool
    quiet_end: bool

    def line(self) -> str:
        tempo = "--" if self.tempo is None else f"{self.tempo:.1f}bpm"
        target = self.target_collection or "--"
        coverage = "--" if self.pitch_coverage is None else f"{self.pitch_coverage:.0%}"
        hits = "--" if self.hit_alignment is None else f"{self.hit_alignment:.0%}"
        edges = f"{'quiet' if self.quiet_start else '--'}/{'quiet' if self.quiet_end else '--'}"
        return (
            f"{self.name[:40]:<42} {self.duration:5.1f}s "
            f"{tempo:>9}  {target[:14]:<14} {coverage:>5}  peak {self.peak_pitch:<2}  "
            f"hits {hits:>3}  edges {edges}"
        )


def _target_pitch_classes(key: str | None, scale: str | None) -> tuple[set[int] | None, str | None]:
    if (key is None) != (scale is None):
        raise ValueError("--key and --scale must be supplied together")
    if key is None:
        return None, None
    key = key.strip().replace("♭", "b").replace("♯", "#")
    key = key[:1].upper() + key[1:].lower()
    scale = scale.strip().lower().replace("_", "-").replace(" ", "-")
    if key not in KEY_PITCH_CLASS:
        raise ValueError(f"unknown key {key!r}; choose one of {', '.join(KEY_PITCH_CLASS)}")
    if scale not in SCALE_INTERVALS:
        raise ValueError(
            f"unknown scale {scale!r}; choose one of {', '.join(SCALE_INTERVALS)}"
        )
    root = KEY_PITCH_CLASS[key]
    return {(root + interval) % 12 for interval in SCALE_INTERVALS[scale]}, f"{key} {scale}"


def _finite_mean(values: np.ndarray) -> float | None:
    finite = values[np.isfinite(values)]
    return float(finite.mean()) if finite.size else None


def _quiet_edge_flags(rms: np.ndarray) -> tuple[bool, bool]:
    rms = np.asarray(rms, dtype=float).reshape(-1)
    finite = rms[np.isfinite(rms)]
    if not finite.size:
        return False, False
    mid = float(np.median(finite))
    if not math.isfinite(mid) or mid <= 1e-12:
        return False, False
    window = max(1, len(rms) // 10)
    head = _finite_mean(rms[:window])
    tail = _finite_mean(rms[-window:])
    return (
        head is not None and head < mid * 0.85,
        tail is not None and tail < mid * 0.85,
    )


def analyse(
    path: Path,
    hit_interval: float = 8.0,
    key: str | None = None,
    scale: str | None = None,
) -> Analysis:
    import librosa

    if not math.isfinite(hit_interval) or hit_interval <= 0:
        raise ValueError("hit interval must be a positive finite number")
    target_pitches, target_label = _target_pitch_classes(key, scale)
    y, sr = librosa.load(str(path), mono=True)
    if len(y) == 0 or sr <= 0:
        raise ValueError("audio contains no samples")
    duration = len(y) / sr

    tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
    tempo = float(np.atleast_1d(tempo)[0])
    if not math.isfinite(tempo) or tempo <= 0:
        tempo = None

    # Pitch measurements are descriptive unless the caller explicitly supplies a target.
    chroma = np.asarray(librosa.feature.chroma_cqt(y=y, sr=sr), dtype=float).mean(axis=1)
    chroma = np.nan_to_num(chroma, nan=0.0, posinf=0.0, neginf=0.0)
    chroma_total = float(chroma.sum())
    if chroma_total > 1e-12:
        chroma = chroma / chroma_total
        peak_pitch = PITCH_NAMES[int(np.argmax(chroma))]
        pitch_coverage = (
            float(sum(chroma[pitch] for pitch in target_pitches))
            if target_pitches is not None else None
        )
    else:
        peak_pitch = "--"
        pitch_coverage = None

    # --- hit points -----------------------------------------------------
    # Does something transient actually land near each N-second boundary?
    onset_env = np.asarray(librosa.onset.onset_strength(y=y, sr=sr), dtype=float)
    targets = np.arange(hit_interval, duration - 1, hit_interval)
    hit_alignment = None
    if len(targets) and onset_env.size and np.isfinite(onset_env).all():
        times = librosa.times_like(onset_env, sr=sr)
        threshold = float(np.percentile(onset_env, 75))
        hits = 0
        for t in targets:
            window = (times > t - 0.6) & (times < t + 0.6)
            if window.any() and onset_env[window].max() > threshold:
                hits += 1
        hit_alignment = hits / len(targets)

    # --- relative edge loudness -----------------------------------------
    quiet_start, quiet_end = _quiet_edge_flags(librosa.feature.rms(y=y)[0])

    return Analysis(
        name=path.stem,
        duration=duration,
        tempo=tempo,
        target_collection=target_label,
        pitch_coverage=pitch_coverage,
        peak_pitch=peak_pitch,
        hit_alignment=hit_alignment,
        quiet_start=quiet_start,
        quiet_end=quiet_end,
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Measure generated tracks without judging quality.")
    ap.add_argument("paths", nargs="+", help="wav files to analyse")
    ap.add_argument("--hit-interval", type=float, default=8.0,
                    help="expected hit point spacing in seconds (default: 8)")
    ap.add_argument(
        "--key",
        help="key root for optional pitch-collection coverage, e.g. D",
    )
    ap.add_argument(
        "--scale",
        help=f"scale for optional pitch-collection coverage: {', '.join(SCALE_INTERVALS)}",
    )
    args = ap.parse_args(argv)
    try:
        _target_pitch_classes(args.key, args.scale)
    except ValueError as exc:
        ap.error(str(exc))

    print(
        f"{'track':<42} {'len':>6} {'tempo':>9}  {'collection':<14} {'cover':>5}  "
        f"{'peak':>7}  {'hits':>8}  edges(start/end)"
    )
    print("-" * 106)
    failures = 0
    for p in args.paths:
        try:
            result = analyse(Path(p), args.hit_interval, args.key, args.scale)
        except Exception as exc:
            failures += 1
            print(f"{p}: failed: {exc}", file=sys.stderr)
            continue
        print(result.line())
    if args.key is None:
        print("\ncover = not measured; pass --key and --scale to test a pitch collection")
    else:
        print(
            "\ncover = share of normalised chroma activation in the requested pitch "
            "collection; relative modes using the same notes are indistinguishable"
        )
    print(
        f"hits = share of {args.hit_interval:g}s boundaries with a transient within +/-0.6s; "
        "-- means no boundary was eligible or onset data was unavailable\n"
        "edges = quiet means the first or last 10% mean is below the track median; "
        "this does not detect a sweep or fade"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
