---
status: active
author: stephen+claude
created: 2026-09-19
updated: 2026-09-28
generated_by: claude-opus-5
generated_at: 2026-09-19T14:34Z
generated_from: conversation
---

# Prompting

Each backend wants a different shape of prompt, and the wrong shape degrades output
badly. The UI's **Genre** dropdown writes the right shape automatically, using the
vocabulary in `synth/prompting.py`; this file is the reference behind it and the
place to look when hand-writing a prompt.

`synth.cli models` prints each backend's `prompt_style`.

## `description`: Stable Audio 3

Source: Stability's own prompt guide, copied into
[docs/stable-audio-prompting.md](stable-audio-prompting.md) from their
repository at `docs/guides/prompting.md`.

Prompt adherence is `--cfg` on their CLI. `1` is the distilled default: the
prompt is followed, and the extra guidance pass is skipped. Above `1` pushes
harder toward the prompt. From `0` up to but not including `1` pulls toward the
unconditional branch, so the text counts for less. Below `0` pushes away from
the prompt. The control in this app starts at `1`.

The model was trained on Freesound and AudioSparx audio together with their
metadata, so prompts that resemble that metadata do best: a short `Key: Value` tag
preamble, then prose.

```
TrackType: Music, VocalType: Instrumental, Genre: Drum and Bass,
Instruments: Bass, Drums, Synthesizer. A drum and bass instrumental at 174 BPM,
rolling and hypnotic. It is built on a chopped Amen break and a snarling Reese
bass, with lush Rhodes chords over the top. The mix is punchy and club-ready.
```

Tags worth using:

| Tag | Effect |
|---|---|
| `TrackType: Music` | Full instrumental track. `Instrument` isolates one part, `SFX` is for sound effects |
| `VocalType: Instrumental` | Raises coherence; Stability names this pair as improving quality |
| `Genre: X` | Repeatable, and unrelated genres can be combined |
| `Instruments: A, B, C` | Names what plays |
| `Format: Duo` | For a specific small ensemble |

Then cover genre, instruments, mood and BPM in prose. State the tempo as text
(`174 BPM`): there is no numeric tempo input. Extra lines are either comma
fragments, as in the example above, or each their own sentence. Drum and bass
genres open the duration control at 4:20.

**What it does not have.** No key or scale conditioning, and no section or bar
control. Structure reaches it only as description (*"a stripped breakdown halfway,
then a heavier second drop"*). Vocals are never intelligible, though vocal textures
appear. Choose a duration that suits the material rather than always maximising it.

**Editing an existing track** is where real structural control lives: the runtime
accepts an init audio file with a mask range in seconds, regenerating only that span
and keeping the rest. Stability's guidance: mask a large region first and reduce it,
and keep the prompt plausible against the surrounding audio.

This is the UI's **Rework a section** tab. It takes a track from the history or a file
you upload, converting an odd sample rate or an MP3 on the way in, and offers two
modes: rework one span selected in bars, or remix the whole track with an
amount-of-change control. Continuation past the end of a track is not wired up.

## `caption`: MiniMax Music 3

A Structured Caption in prose, and the only route to explicit BPM, key and scale.

```
Global Metadata: Genre: cinematic orchestral, medieval. BPM: 120. Key: D.
Scale: Mixolydian. Mood: serious, restrained, building subtly.
Arrangement: low cello ostinato carries the pulse; frame drum on a four-bar
cycle; distant horn swells. Instrumental only, no vocals.
```

Sections are **Global Metadata** (genre, BPM, key, scale, emotional progression,
listening scenario, production profile), **Vocal Details** and **Arrangement**.
Anchor two or three instruments and describe a section-by-section evolution. State
instrumental intent explicitly.

Sources: the
[model guide](https://github.com/MiniMax-AI/MiniMax-Music3/blob/main/README.md),
[caption rewriter](https://github.com/MiniMax-AI/MiniMax-Music3/blob/main/skills/music-caption-rewriter/SKILL.md)
and [prompt guide](https://github.com/MiniMax-AI/skills/blob/main/skills/minimax-music-gen/references/prompt_guide.md).

## `tags`: ACE-Step and MusicGen

Comma-separated style tags, not sentences.

```
lo-fi hip hop, warm rhodes piano, vinyl crackle, 85bpm, instrumental
```

The pipeline supplies ACE-Step's `[Instrumental]` sentinel. 1.5 still wants these
tags. Its planner may fill BPM, key and time signature, and it does not replace
the caption. Compare seeds rather than treating one result as representative.
v1 was weak at orchestral material. 1.5's own examples include an orchestral
cover, which is not a judgement of a render from this machine.

## Sung line

Sing is not a prompt. The words are the lyric. The melody is one line per note:

```
C4 0.5
rest 0.25
D4 0.5
```

`C4` is MIDI 60. A MIDI number works too. `rest`, `r` or `0` is a silence and
does not take a word. Each other note takes the next word. A note is longer
than 0 seconds and at most 30. The whole line is 0.2 to 600 seconds. The
voice is the English example. Mandarin, and a reference recording of your
own, are not wired.

## Applies to every backend

Keep prompts focused. Stacking competing directives averages into mush rather than
blending them, see [gotchas.md](gotchas.md).
