---
status: active
author: stephen+claude
created: 2026-09-19
updated: 2026-09-30
generated_by: claude-opus-5
generated_at: 2026-09-19T14:34Z
generated_from: conversation
---

# Prompting

Each backend wants a different shape of prompt, and the wrong shape degrades output
badly. The UI's **Genre** dropdown writes the right shape automatically, using the
vocabulary in `synth/prompting.py`. That same catalogue feeds the React menus:
genre, mood, tempo, instruments, character and extra keywords. Regenerate samples
the longer phrase pools (drums, bass, lead, texture, production) and writes them
in the selected model's style. Those pools are not their own menus.

Which tool uses which model:

| Tool | Model | What you give it |
|---|---|---|
| Generate, Stable Audio | `stable-audio-medium` or `stable-audio-sm` | A description. Vocal texture is wordless. No lyrics channel |
| Generate, ACE-Step 1.5 | `acestep` | Comma-separated tags. A lyrics box when With vocals is on |
| Generate, MiniMax | `minimax-mlx` | A structured caption, including a lyrics channel |
| Generate, MusicGen | `musicgen` | Tags. No lyrics channel. Non-commercial |
| Remix | Stable Audio only | The same description, plus an existing track |
| Separate | `demucs` | A mix. No prompt |
| Sing | `soulx` | English words. A scale or pattern writes the notes. Not the generate model |

MiniMax and MusicGen stay installed. The models used for new tracks are Stable
Audio and ACE-Step 1.5.

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

This is the UI's **Remix** tab, and only Stable Audio can run it. It takes a track
from the history or a file you upload, converting an odd sample rate or an MP3
on the way in, and remixes the whole track with an amount-of-change control.
Continuation past the end of a track is not wired up.

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

## `tags`: ACE-Step 1.5

Comma-separated style tags, not sentences. The genre menu writes this shape
from the same catalogue as Stable Audio, then you can edit it.

```
lo-fi hip hop, warm rhodes piano, vinyl crackle, 85bpm, instrumental
```

With vocals off, the runner sends `[Instrumental]` on the lyrics channel.
With vocals on, the lyrics box is the words and the tags stay the style.
On this Mac the planner may fill BPM, key and time signature. It does not
replace the caption. When Seneca's ComfyUI answers, the same tags go to the
4090. BPM is read from a `174bpm` tag, and a named key such as `E minor` is
sent when the tags contain one. Otherwise the 4090 node gets C major. Cover,
repaint and vocal-to-BGM exist in ACE-Step's own musician guide and are not
connected here. Compare seeds rather than treating one result as representative.

## `tags`: MusicGen

The same comma-separated tags. MusicGen has no lyrics channel, so With vocals
is not offered. It is capped at 30 seconds and the licence is non-commercial.
It stays installed. It is not one of the two models used for new tracks.

## Sung line

Sing is not a prompt, and SoulX does not invent a tune from the words. The
downloaded model notes describe two controls only: an F0 contour, or a MIDI
score. The score is what this app sends. One pitched note still has to exist
for each word. The Sing tab writes that score from a named scale or contour
(major, minor, pentatonic, blues, and a few short shapes). Random picks one
of those. You can still edit the notes.

```
C4 0.5
rest 0.25
D4 0.5
```

`C4` is MIDI 60. A MIDI number works too. `rest`, `r` or `0` is a silence and
does not take a word. Each other note takes the next word. A note is longer
than 0 seconds and at most 30. The whole line is 0.2 to 600 seconds. A long
line is shortened so it stays inside that. The voice is the English example.
Mandarin, and a reference recording of your own, are not wired. SoulX-Singer-SVC
can follow a recording you have already sung, and that model is not connected.

## Applies to every backend

Keep prompts focused. Stacking competing directives averages into mush rather than
blending them, see [gotchas.md](gotchas.md).
