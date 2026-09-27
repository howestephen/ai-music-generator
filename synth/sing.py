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
