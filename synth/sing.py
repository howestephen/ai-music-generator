"""A written melody for SoulX-Singer. One pitched note per word, rests optional."""
from __future__ import annotations

import math
import re

_SEMITONE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_PITCH = re.compile(r"([A-Ga-g])([#b]?)(-?\d)$")


def parse_pitch(token: str) -> int:
    """MIDI note, or 0 for a rest. C4 is 60."""
    text = token.strip()
    if text.lower() in {"rest", "r"}:
        return 0
    if text.isdigit():
        value = int(text)
        if 0 <= value <= 127:
            return value
        raise ValueError(f"{token!r} is outside MIDI 0-127")
    match = _PITCH.fullmatch(text)
    if match is None:
        raise ValueError(f"{token!r} is not a pitch")
    degree = _SEMITONE[match.group(1).upper()]
    accidental = match.group(2)
    if accidental == "#":
        degree += 1
    elif accidental == "b":
        degree -= 1
    octave = int(match.group(3))
    midi = (octave + 1) * 12 + degree
    if not 0 <= midi <= 127:
        raise ValueError(f"{token!r} is outside MIDI 0-127")
    return midi


def parse_score(text: str) -> list[dict]:
    """Lines of `C4 0.5`. A rest does not take a word."""
    notes = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) != 2:
            raise ValueError(f"a melody line is a pitch and seconds (got {raw!r})")
        pitch = parse_pitch(parts[0])
        try:
            seconds = float(parts[1])
        except ValueError as exc:
            raise ValueError(f"seconds must be a number (got {parts[1]!r})") from exc
        if not math.isfinite(seconds) or seconds <= 0 or seconds > 30:
            raise ValueError(f"each note must be between 0 and 30 seconds (got {seconds:g})")
        notes.append({"pitch": pitch, "seconds": seconds})
    if not notes:
        raise ValueError("the melody is empty")
    if not any(note["pitch"] > 0 for note in notes):
        raise ValueError("the melody has no pitched notes")
    return notes


def pitched_count(notes: list[dict]) -> int:
    return sum(1 for note in notes if int(note["pitch"]) > 0)


def count_mismatch(word_count: int, pitched: int) -> str:
    words = "word" if word_count == 1 else "words"
    notes = "note" if pitched == 1 else "notes"
    return f"{word_count} {words} and {pitched} pitched {notes}"


_NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
# A step is a MIDI pitch, or None for a rest. Rests do not take a word.
# SoulX will not invent a melody: these only write the score it already requires.
_PATTERNS: dict[str, tuple[tuple[int | None, float], ...]] = {
    "C major up": ((60, 0.5), (62, 0.5), (64, 0.5), (65, 0.5), (67, 0.5), (69, 0.5), (71, 0.5), (72, 0.5)),
    "C major down": ((72, 0.5), (71, 0.5), (69, 0.5), (67, 0.5), (65, 0.5), (64, 0.5), (62, 0.5), (60, 0.5)),
    "A minor up": ((57, 0.5), (59, 0.5), (60, 0.5), (62, 0.5), (64, 0.5), (65, 0.5), (67, 0.5), (69, 0.5)),
    "A minor down": ((69, 0.5), (67, 0.5), (65, 0.5), (64, 0.5), (62, 0.5), (60, 0.5), (59, 0.5), (57, 0.5)),
    "C major triad": ((60, 0.5), (64, 0.5), (67, 0.5), (64, 0.5)),
    "A minor triad": ((57, 0.5), (60, 0.5), (64, 0.5), (60, 0.5)),
    "C major pentatonic": ((60, 0.5), (62, 0.5), (64, 0.5), (67, 0.5), (69, 0.5)),
    "A minor pentatonic": ((57, 0.5), (60, 0.5), (62, 0.5), (64, 0.5), (67, 0.5)),
    "A blues": ((57, 0.55), (60, 0.4), (62, 0.4), (63, 0.35), (64, 0.5), (67, 0.45)),
    "Arch": ((60, 0.45), (62, 0.45), (64, 0.45), (65, 0.5), (64, 0.45), (62, 0.45)),
    "Neighbour": ((60, 0.4), (62, 0.35), (60, 0.4), (59, 0.35), (60, 0.5)),
    "Pedal": ((60, 0.35), (64, 0.45), (60, 0.35), (67, 0.45), (60, 0.4)),
    "Step and hold": ((60, 0.7), (60, 0.35), (62, 0.7), (62, 0.35), (64, 0.7), (64, 0.35)),
    "Scale with breaths": (
        (60, 0.45), (62, 0.45), (64, 0.45), (65, 0.5), (None, 0.25),
        (67, 0.45), (69, 0.45), (71, 0.45), (72, 0.55),
    ),
}
DEFAULT_PATTERN = "C major up"
_MAX_LINE_SECONDS = 600.0
_MIN_NOTE_SECONDS = 0.05


def pattern_names() -> tuple[str, ...]:
    return tuple(_PATTERNS)


def midi_name(midi: int) -> str:
    if not 0 <= midi <= 127:
        raise ValueError(f"{midi} is outside MIDI 0-127")
    return f"{_NOTE_NAMES[midi % 12]}{midi // 12 - 1}"


def score_for(name: str, word_count: int) -> str:
    """One pitched note per word, tiled from a named scale or contour."""
    try:
        steps = _PATTERNS[name]
    except KeyError:
        raise ValueError(f"unknown melody {name!r}") from None
    if isinstance(word_count, bool) or not isinstance(word_count, int) or word_count < 1:
        raise ValueError(f"a melody needs at least one word (got {word_count!r})")
    if not any(pitch is not None for pitch, _seconds in steps):
        raise ValueError(f"{name} has no pitched notes")
    lines: list[tuple[int | None, float]] = []
    remaining = word_count
    index = 0
    while remaining > 0:
        pitch, seconds = steps[index % len(steps)]
        index += 1
        if index > word_count * (len(steps) + 1):
            raise ValueError(f"{name} never lands on a pitch")
        lines.append((pitch, seconds))
        if pitch is not None:
            remaining -= 1
    total = sum(seconds for _pitch, seconds in lines)
    scale = 1.0
    if total > _MAX_LINE_SECONDS:
        scale = _MAX_LINE_SECONDS / total
    rendered = []
    for pitch, seconds in lines:
        length = seconds * scale
        if length < _MIN_NOTE_SECONDS:
            raise ValueError(
                f"{word_count} words do not fit in {_MAX_LINE_SECONDS:g} seconds"
            )
        token = "rest" if pitch is None else midi_name(pitch)
        rendered.append(f"{token} {length:.4g}")
    text = "\n".join(rendered)
    notes = parse_score(text)
    if pitched_count(notes) != word_count:
        raise ValueError(count_mismatch(word_count, pitched_count(notes)))
    if sum(note["seconds"] for note in notes) > _MAX_LINE_SECONDS + 1e-6:
        raise ValueError("the melody is longer than 600 seconds")
    return text
