"""Check generated audio against a brief: tempo, hit points, modality, sweeps.

The model can't be *told* a tempo or a mode, so the only honest way to know whether
a track matches the brief is to measure the audio it actually produced.
"""
from __future__ import annotations

import argparse
import warnings
from dataclasses import dataclass
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")

PITCH_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# D Mixolydian: D E F# G A B C. The flat 7 (C natural) is what separates it from
# D major, so comparing C against C# is the sharpest single test for the mode.
D_MIXOLYDIAN = {2, 4, 6, 7, 9, 11, 0}


@dataclass
class Analysis:
    name: str
    duration: float
    tempo: float
    scale_fit: float
    flat7_ratio: float
    tonic: str
    hit_alignment: float
    intro_swell: bool
    outro_fade: bool

    def line(self) -> str:
        sweeps = f"{'in' if self.intro_swell else '--'}/{'out' if self.outro_fade else '--'}"
        return (
            f"{self.name[:40]:<42} {self.duration:5.1f}s "
            f"{self.tempo:6.1f}bpm  scale {self.scale_fit:4.0%}  "
            f"b7 {self.flat7_ratio:4.1f}x  tonic {self.tonic:<2}  "
            f"hits {self.hit_alignment:4.0%}  sweep {sweeps}"
        )


def analyse(path: Path, hit_interval: float = 8.0) -> Analysis:
    import librosa

    y, sr = librosa.load(str(path), mono=True)
    duration = len(y) / sr

    tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
    tempo = float(np.atleast_1d(tempo)[0])

    # --- modality -------------------------------------------------------
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr).mean(axis=1)
    chroma = chroma / (chroma.sum() + 1e-9)
    scale_fit = float(sum(chroma[i] for i in D_MIXOLYDIAN))
    # >1 means the flat 7 (C) beats the major 7 (C#) — the Mixolydian tell.
    flat7_ratio = float(chroma[0] / (chroma[1] + 1e-9))
    tonic = PITCH_NAMES[int(np.argmax(chroma))]

    # --- hit points -----------------------------------------------------
    # Does something transient actually land near each N-second boundary?
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    times = librosa.times_like(onset_env, sr=sr)
    threshold = float(np.percentile(onset_env, 75))
    targets = np.arange(hit_interval, duration - 1, hit_interval)
    hits = 0
    for t in targets:
        window = (times > t - 0.6) & (times < t + 0.6)
        if window.any() and onset_env[window].max() > threshold:
            hits += 1
    hit_alignment = hits / len(targets) if len(targets) else 0.0

    # --- sweeps ---------------------------------------------------------
    rms = librosa.feature.rms(y=y)[0]
    n = len(rms)
    head, tail, mid = rms[: n // 10], rms[-n // 10:], float(np.median(rms))
    intro_swell = float(head.mean()) < mid * 0.85
    outro_fade = float(tail.mean()) < mid * 0.85

    return Analysis(
        name=path.stem,
        duration=duration,
        tempo=tempo,
        scale_fit=scale_fit,
        flat7_ratio=flat7_ratio,
        tonic=tonic,
        hit_alignment=hit_alignment,
        intro_swell=intro_swell,
        outro_fade=outro_fade,
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Measure tracks against a brief.")
    ap.add_argument("paths", nargs="+", help="wav files to analyse")
    ap.add_argument("--hit-interval", type=float, default=8.0,
                    help="expected hit point spacing in seconds (default: 8)")
    args = ap.parse_args(argv)

    print(
        f"{'track':<42} {'len':>6} {'tempo':>9}  {'scale':>9}  "
        f"{'flat7':>7}  {'tonic':>7}  {'hits':>8}  sweeps"
    )
    print("-" * 118)
    for p in args.paths:
        print(analyse(Path(p), args.hit_interval).line())
    print(
        "\nscale = share of energy in D-Mixolydian pitch classes (higher is better)"
        "\nflat7 = C vs C# energy; >1.0 means Mixolydian rather than major"
        "\nhits  = share of 8s boundaries with a transient within +/-0.6s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
