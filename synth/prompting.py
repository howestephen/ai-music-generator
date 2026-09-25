"""Genre-aware prompt construction for description-style backends.

Stable Audio 3 was trained on Freesound and AudioSparx audio together with their
metadata, so prompts that look like that metadata do better than free invention.
Stability's own guide (docs/guides/prompting.md in their repo) gives the shape:
a `Key: Value` tag preamble followed by prose naming genre, instruments, mood and
BPM. This module builds that shape, using each genre's own vocabulary, so the UI
can offer a genre rather than asking for a paragraph.

What this module deliberately does NOT do is invent controls the model lacks.
Stable Audio 3 has no key or scale conditioning and no section tokens: structure
reaches it only as prose. Bar-accurate section work is a separate mechanism,
inpainting, which lives in `core.generate`'s job contract rather than here.
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass, field

# Tags Stability names explicitly as raising quality and coherence for music.
MUSIC_PREAMBLE = "TrackType: Music, VocalType: Instrumental"

# Optional character pins for the UI. They are not applied on their own: doing that
# dressed every genre in the same room, the same tape and the same era.
SPACE = (
    "recorded in a dead, close-mic'd room",
    "with a wide, cavernous reverb",
    "in a tight, dry studio space",
    "with the natural ambience of a large hall",
    "close-mic'd with almost no room sound",
    "drenched in a long plate reverb",
    "with a short, boxy room character",
)
EFFECTS = (
    "tape saturation warming the highs",
    "a slow filter sweep opening across the track",
    "heavy sidechain pumping against the kick",
    "subtle chorus widening the stereo image",
    "bitcrushed detail in the background",
    "analogue distortion on the low end",
    "long delay throws trailing the main line",
    "a gentle high-pass on the intro",
)
ERA = (
    "with a nineties analogue character",
    "with a modern, polished finish",
    "with an early-2000s digital sheen",
    "with a dusty, sampled-from-vinyl feel",
    "with a raw, unmastered edge",
    "",
    "",
)



@dataclass(frozen=True)
class Genre:
    """One genre's vocabulary. Every list is a pool a variation draws from."""

    tags: tuple[str, ...]
    bpm: tuple[int, int]
    drums: tuple[str, ...]
    bass: tuple[str, ...]
    lead: tuple[str, ...]
    texture: tuple[str, ...]
    mood: tuple[str, ...]
    production: tuple[str, ...]
    structure: tuple[str, ...] = ()
    instruments: tuple[str, ...] = field(default=())
    # How the genre reads inside a sentence. The dropdown label is for people and
    # may carry a slash or an ampersand, neither of which belongs in prose.
    prose: str = ""
    # Short forms for tag-style backends, which want a comma list rather than prose.
    keywords: tuple[str, ...] = ()

    def default_bpm(self) -> int:
        return (self.bpm[0] + self.bpm[1]) // 2


# 4:20. Long enough for a drum and bass arrangement, short of the Stable Audio cap.
DRUM_AND_BASS_DURATION = 260


def suggested_duration(genre_name: str | None) -> int | None:
    """Seconds the duration control should offer when this genre is chosen."""
    if genre_name and genre_name.startswith("Drum & Bass"):
        return DRUM_AND_BASS_DURATION
    return None


# Spelling alone gets these wrong: "UK" reads "you-kay", so it takes "a".
_CONSONANT_SOUNDING = ("uk", "uni", "euro", "eu", "one", "use")


def _upper_first(text: str) -> str:
    """Capitalise the first letter only. `str.capitalize` lowercases the rest,
    which turns an Amen break into an amen break and a Rhodes into a rhodes."""
    return text[:1].upper() + text[1:]


def _article(word: str) -> str:
    lowered = word.lower()
    if lowered.startswith(_CONSONANT_SOUNDING):
        return "a"
    return "an" if lowered[:1] in "aeiou" else "a"


GENRES: dict[str, Genre] = {
    "Drum & Bass - Liquid": Genre(
        tags=("Genre: Drum and Bass",),
        bpm=(172, 176),
        drums=(
            "a smooth, tightly swung break with brushed ghost notes",
            "a rolling breakbeat with soft-edged snares",
            "crisp two-step drums with a warm, round kick",
            "a lightly shuffled break, hats ticking in double time",
            "brushed snare figures over a quiet, bouncing kick",
            "a jazzy break with soft rim clicks between the snares",
        ),
        bass=(
            "a deep rolling sub bass that slides between notes",
            "a warm, filtered bassline that breathes with the pads",
            "a round sub that sits under everything without crowding it",
            "a mellow bass guitar line walking under the break",
            "a soft sine bass holding long notes through the groove",
            "a muted sub pulse that swells only on the drop",
        ),
        lead=(
            "lush Rhodes chords floating over the break",
            "a soulful piano motif answering the drums",
            "a soft saxophone line weaving through the mix",
            "a breathy flute phrase answering the snare",
            "muted trumpet notes hanging in the space above the bass",
            "nylon-string harmonics picked between the drum fills",
            "a vibraphone figure chiming softly over the groove",
            "a sung hum, wordless and close, never a lyric",
        ),
        texture=(
            "filtered atmospherics and distant rain sit under the groove",
            "warm pad swells fill the space between phrases",
            "reversed cymbals and soft vinyl noise stitch the sections",
            "a quiet chorus on the chords, never wide enough to wash the drums out",
            "room tone from a small club under the break",
        ),
        mood=(
            "warm, liquid and euphoric", "reflective and spacious",
            "late-night and smooth", "sunlit and unforced",
        ),
        production=(
            "the mix is clean and deep with a wide, warm low end",
            "the production is polished and unhurried",
            "the drums stay dry while the chords sit further back",
            "the low end is round and never gritty",
        ),
        structure=(
            "a beatless intro opens into a rolling first drop, a softer breakdown "
            "lands halfway, and the last drop is the fullest",
            "the break rides throughout, with the lead entering late and leaving space",
            "a long rolling groove, one quiet middle eight, then the same groove fuller",
        ),
        instruments=(
            "Instruments: Bass, Drums, Electric Piano, Synthesizer",
            "Instruments: Bass, Drums, Flute, Synthesizer",
            "Instruments: Bass, Drums, Saxophone, Synthesizer",
            "Instruments: Bass, Drums, Trumpet, Acoustic Guitar",
            "Instruments: Bass, Drums, Vibraphone, Synthesizer",
            "Instruments: Bass, Drums, Piano, Synthesizer",
        ),
        prose="liquid drum and bass",
        keywords=(
            "liquid dnb", "rolling sub bass", "smooth breakbeat", "flute phrase",
            "sax line", "vibraphone", "muted trumpet", "jazzy break",
        ),
    ),
    "Drum & Bass - Neurofunk": Genre(
        tags=("Genre: Drum and Bass",),
        bpm=(172, 176),
        drums=(
            "surgical, heavily processed drums with a cracking snare",
            "tight technical breaks with metallic percussion fills",
            "a clipped, machine-precise beat with rattling ghost hits",
            "a resampled break, every hit gated and retuned",
            "machine-gun edits on the snare with almost no sustain",
            "a dry, close break with fizzing hat rolls in the gaps",
        ),
        bass=(
            "a neurofunk bass full of metallic formant sweeps",
            "a snarling Reese detuned into a wide, moving growl",
            "a modulating bass that morphs between notes like machinery",
            "a distorted, talking bass that bends through a resonant filter",
            "a bass that speaks in vowels, then snaps back to a pure sub",
            "two detuned oscillators beating against each other in the low mid",
        ),
        lead=(
            "sparse, dissonant stabs cutting between the bass",
            "a cold synth motif buried under the low end",
            "sci-fi sweeps and alarms punctuating the drop",
            "a single atonal blip repeating, then pitch-shifting down",
            "short FM pings answering the snare, never a melody",
            "a warning-tone sequence, three notes and silence",
        ),
        texture=(
            "industrial metallic noise and mechanical clanks",
            "granular glitches scattered across the stereo field",
            "dark drones underneath the drums",
            "radio static and clipped breath noises between phrases",
            "a tight spring of noise that ducks under every bass note",
        ),
        mood=(
            "dark and technical", "aggressive and precise",
            "menacing and clinical", "cold and machined",
        ),
        production=(
            "the mix is surgical, loud and heavily compressed",
            "the production is cold, sharp and sub-heavy",
            "the mids are carved out so the bass can move",
            "every transient is clipped on purpose",
        ),
        structure=(
            "a tense sound-design intro, a sharp first drop, a brief mechanical "
            "breakdown, then a heavier second drop",
            "drums alone, then the bass enters as the only event, then both lock",
            "a long technical roll, one bar of silence, then the bass restarts lower",
        ),
        instruments=(
            "Instruments: Bass, Drums, Synthesizer",
            "Instruments: Bass, Drums, Synthesizer, Sampler",
            "Instruments: Drums, Synthesizer, Sub Bass",
        ),
        prose="neurofunk drum and bass",
        keywords=(
            "neurofunk", "reese bass", "formant sweeps", "technical drums",
            "dark sci-fi", "talking bass", "gated break", "fm pings",
        ),
    ),
    "Drum & Bass - Dancefloor": Genre(
        tags=("Genre: Drum and Bass",),
        bpm=(172, 176),
        drums=(
            "a punchy, wide-open beat built for a festival system",
            "a driving break with a huge, bright snare",
            "simple, powerful drums with big crash accents",
            "a straight, loud break with a clap layered on the snare",
            "open hats rushing into each drop, then cutting out",
            "a four-bar drum fill of toms before the hook returns",
        ),
        bass=(
            "a clean, enormous sub that hits like a wall",
            "a bright, bouncing bass hook you can hum",
            "a punchy mid-range bass riff carrying the drop",
            "a saw bass playing the same notes as the hook, an octave down",
            "a short, percussive bass stab on the offbeat under the melody",
            "one held sub note through the chorus, then a run into the next drop",
        ),
        lead=(
            "a soaring supersaw hook that opens the drop",
            "an anthemic synth melody built for a crowd",
            "a big euphoric chord progression rising into the drop",
            "a bright plucked topline with a memorable hook",
            "a long, singing lead line over a fast break",
            "a vocal-chop hook with no words, pitched to the chords",
            "a brass-like synth fanfare marking the start of the drop",
        ),
        texture=(
            "huge white-noise risers and impacts at every transition",
            "stadium reverb and crowd-sized delays",
            "shimmering high pads lifting the chorus",
            "a noise sweep that opens only in the last bar of the build",
            "wide unison detune on the hook and nowhere else",
        ),
        mood=(
            "euphoric and enormous", "bright and anthemic",
            "uplifting and driving", "celebratory and loud",
        ),
        production=(
            "the mix is glossy, loud and festival-ready",
            "the production is polished and radio-bright",
            "the hook is the loudest thing in the track",
            "the drums punch through a wide, bright top end",
        ),
        structure=(
            "an intro hook, a long build with a filter sweep, an anthemic first "
            "drop, a melodic breakdown, then the biggest drop last",
            "the hook is stated quietly, then the break drops out, then the full chorus",
            "two drops, the second with the lead an octave higher",
        ),
        instruments=(
            "Instruments: Bass, Drums, Synthesizer, Piano",
            "Instruments: Bass, Drums, Synthesizer",
            "Instruments: Drums, Synthesizer, Sub Bass, Sampler",
        ),
        prose="dancefloor drum and bass",
        keywords=(
            "dancefloor dnb", "supersaw hook", "anthemic", "festival",
            "big sub bass", "euphoric drop", "vocal chop hook", "bright snare",
        ),
    ),
    "Drum & Bass - Jungle": Genre(
        tags=("Genre: Drum and Bass", "Genre: Jungle"),
        bpm=(160, 174),
        drums=(
            "a chopped Amen break, edited hard and fast",
            "layered breakbeats cut into stuttering fills",
            "a raw, time-stretched break with vinyl grit",
            "the Think break, chopped so the snare lands early",
            "two breaks stacked, one pitched up and one left low",
            "a break that speeds into a roll, then drops back to the original chop",
        ),
        bass=(
            "a deep dub sub bass rolling underneath",
            "a heavy, warm sub with a long decay",
            "an 808-style bass sliding between low notes",
            "a reggae-style bass note held, then dropped an octave",
            "a simple two-note bass, nothing but weight under the chop",
            "a dub bass hit with a spring tail, once every two bars",
        ),
        lead=(
            "ragga vocal chops stabbing through the break",
            "a dub siren wailing over the drums",
            "a minor key stab pattern echoing off the beat",
            "a dancehall toast chopped to single syllables",
            "an off-key music-box phrase against the break",
            "a short horn sample, one stab, then silence",
        ),
        texture=(
            "tape hiss, vinyl crackle and dub delay throws",
            "distant rave sirens and reversed noise",
            "a sampler choking as the chops overlap",
            "pirate-radio static between the phrases",
            "a tape stop into the next break",
        ),
        mood=(
            "raw and rolling", "dark and hypnotic",
            "energetic and rugged", "rave-worn and frantic",
        ),
        production=(
            "the production is raw, sampled and unpolished, straight off vinyl",
            "the breaks are louder than everything else",
            "it sounds dubbed from a cassette, tops rolled off",
            "the bass is mono and the breaks are wide",
        ),
        structure=(
            "a dub intro, an extended break-driven roll, a stripped bass-only "
            "section, then the full break returns",
            "the chop runs unbroken, the bass entering and leaving",
            "a siren intro, a long roller, a rewind, then the same break harder",
        ),
        instruments=(
            "Instruments: Bass, Drums, Sampler",
            "Instruments: Drums, Sub Bass, Sampler",
            "Instruments: Bass, Drums, Synthesizer, Sampler",
        ),
        prose="jungle",
        keywords=(
            "jungle", "Amen break", "ragga chops", "dub sub bass",
            "time-stretched breaks", "Think break", "rewind", "dub siren",
        ),
    ),
    "Drum & Bass - Halftime": Genre(
        tags=("Genre: Drum and Bass",),
        bpm=(168, 174),
        drums=(
            "sparse halftime drums with a heavy, delayed snare",
            "a slow, weighty beat under fast hi-hat detail",
            "a broken, off-grid pattern with lots of space",
            "one kick and one snare per bar, nothing else for long stretches",
            "a halftime backbeat with tiny foley clicks in the gaps",
            "brushed metal hits instead of a conventional hat",
        ),
        bass=(
            "a slow, enormous sub that swells and decays",
            "a textured bass drone shifting under the beat",
            "a granular bass that rumbles rather than plays notes",
            "a sub that only speaks on the first beat of every four bars",
            "a downward pitch dive instead of a bassline",
            "a low bowed tone, almost a note, under the snare",
        ),
        lead=(
            "a distant, detuned melodic fragment",
            "cold bell tones scattered over the beat",
            "a processed vocal shard repeating in the space",
            "a music-box phrase slowed until the pitches sag",
            "a single piano note, struck and left",
            "a choir vowel with no words, far behind the snare",
        ),
        texture=(
            "wide pads and field recordings",
            "granular clouds and reversed reverb tails",
            "wind and a low room tone, no beat for several bars",
            "contact-mic scrapes panned hard left and right",
            "a fog of filtered noise that never becomes a melody",
        ),
        mood=(
            "dark and cavernous", "brooding and spacious",
            "cinematic and heavy", "still and ominous",
        ),
        production=(
            "the mix is deep and wide with enormous low-end weight",
            "most of the track is near-silence around one heavy snare",
            "the top end is dull on purpose, all the energy below",
            "reverb tails are longer than the notes that made them",
        ),
        structure=(
            "a quiet opening, the halftime beat entering low, a long textural "
            "middle, then a heavier final section",
            "the snare arrives late, leaves, and returns heavier",
            "no drop in the dance sense: weight accumulates and then thins out",
        ),
        instruments=(
            "Instruments: Bass, Drums, Synthesizer",
            "Instruments: Sub Bass, Drums, Piano, Sampler",
            "Instruments: Drums, Synthesizer, Strings",
        ),
        prose="halftime drum and bass",
        keywords=(
            "halftime dnb", "sparse drums", "sub weight", "granular textures",
            "broken beat", "delayed snare", "bowed sub", "foley clicks",
        ),
    ),
    "Techno - Hypnotic": Genre(
        tags=("Genre: Techno", "Genre: Minimal"),
        bpm=(128, 134),
        drums=(
            "a relentless four-to-the-floor kick with tight closed hats",
            "a locked groove with a dry rimshot and shaker",
            "a stripped beat with an offbeat open hat",
            "a kick and a closed hat only, for minutes at a time",
            "a small shuffle on a rim, never a fill",
            "machine hats in straight sixteenths under a dry kick",
        ),
        bass=(
            "a hypnotic rolling bassline locked to the kick",
            "a single low pulse repeating without variation",
            "a filtered sub that opens across several minutes",
            "one bass note per bar, no fill, no run",
            "a bass sequence of three notes cycling for the whole track",
            "a sub that ducks under the kick and is gone between hits",
        ),
        lead=(
            "a hypnotic arpeggio slowly opening its filter",
            "one stabbing chord repeating with tiny variations",
            "a modulating drone that shifts almost imperceptibly",
            "a two-note motif, the second note a semitone flat",
            "a click sequence that becomes a tone as the filter opens",
            "no melody at all, only the changing tone of the hats",
        ),
        texture=(
            "short delay throws and a little tape hiss",
            "a distant metal scrape, once every sixteen bars",
            "a background tone that moves too slowly to notice at first",
            "the room's own hum, left in",
            "a noise floor that rises and falls with the filter",
        ),
        mood=(
            "hypnotic and mechanical", "dark and relentless",
            "meditative and locked", "patient and severe",
        ),
        production=(
            "the mix is dry, tight and built for a dark room",
            "the production is raw and analogue with saturated drums",
            "nothing is wide; the kick is dead centre",
            "the track is a loop that earns its length by subtraction",
        ),
        structure=(
            "a long tool-like intro, a gradual build, a stripped breakdown "
            "and a driving final section",
            "elements enter one at a time and leave the same way",
            "no breakdown spectacle: the kick stops for eight bars and returns",
        ),
        instruments=(
            "Instruments: Drums, Bass, Synthesizer",
            "Instruments: Drum Machine, Synthesizer, Sub Bass",
            "Instruments: Drums, Synthesizer",
        ),
        prose="hypnotic techno",
        keywords=(
            "hypnotic techno", "rolling bassline", "locked groove",
            "one note bass", "closed hats", "warehouse", "filter opening", "tool",
        ),
    ),
    "Techno - Industrial": Genre(
        tags=("Genre: Techno", "Genre: Industrial"),
        bpm=(130, 145),
        drums=(
            "a distorted, overdriven kick hitting hard",
            "harsh metallic percussion and crashing noise hits",
            "a pounding beat with clanging factory rhythms",
            "an anvil hit on the offbeat, ringing into the next kick",
            "kicks so clipped they are almost a click, then a blast of noise",
            "a marching pattern of metal hits over a straight kick",
        ),
        bass=(
            "a distorted bass grinding in fifths under the kick",
            "a saturated low rumble under the kick",
            "a bass made of feedback, tuned just enough to be a note",
            "a downward industrial rumble instead of a riff",
            "octave jumps on a filthy oscillator, no glide",
            "a sub that is felt, with all the audible bass replaced by distortion",
        ),
        lead=(
            "a screaming, detuned synth line",
            "harsh atonal stabs cutting through the noise",
            "a siren-like lead rising over the beat",
            "a sampled power-tool whine, pitched to a tritone",
            "one brutal chord, repeated, no melody",
            "a klaxon pattern, four blasts and a gap",
        ),
        texture=(
            "sheet-metal impacts and chain noise",
            "white noise blasts where a cymbal would be",
            "a distorted room, small and ugly",
            "electrical hum that swells between sections",
            "scrapes of a bow on metal, left untreated",
        ),
        mood=(
            "brutal and relentless", "raw and physical",
            "bleak and pounding", "hostile and mechanical",
        ),
        production=(
            "the mix is loud, distorted and deliberately harsh",
            "the kick clips the converter and is left that way",
            "there is no polish on the top end",
            "the noise is part of the arrangement, not a bed under it",
        ),
        structure=(
            "a noise intro, a punishing main section, a brief drop to "
            "percussion, then heavier again",
            "the distortion increases each section until the last is almost a tone",
            "percussion alone, then the full assault, then percussion again",
        ),
        instruments=(
            "Instruments: Drums, Synthesizer, Bass",
            "Instruments: Drum Machine, Synthesizer, Metal Percussion",
            "Instruments: Drums, Synthesizer, Noise",
        ),
        prose="industrial techno",
        keywords=(
            "industrial techno", "distorted kick", "factory rhythms",
            "metallic percussion", "harsh", "anvil", "feedback bass", "klaxon",
        ),
    ),
    "Techno - Melodic": Genre(
        tags=("Genre: Techno", "Genre: Electronic"),
        bpm=(120, 126),
        drums=(
            "a clean four-to-the-floor kick with crisp hats",
            "a driving beat with a soft clap on the offbeat",
            "a steady kick with a shaker and no snare",
            "open hats only in the peak, closed hats everywhere else",
            "a light ride pattern over a soft kick",
            "percussion drops out and leaves the kick alone for the breakdown",
        ),
        bass=(
            "a warm rolling bassline with a gentle glide",
            "a deep, melodic sub following the chord changes",
            "a bass that outlines the chords in long notes",
            "a rounded synth bass, one note per chord, no riff",
            "the bass enters with the melody and leaves with it",
            "a quiet sub through the breakdown, fuller when the kick returns",
        ),
        lead=(
            "a wistful arpeggio climbing over the groove",
            "a wide, emotive pad chord progression",
            "a plucked melodic hook with long delay",
            "a minor-key piano figure, simple and repeating",
            "a string line that only appears at the peak",
            "a soft vocal pad with no words, following the chords",
        ),
        texture=(
            "high shimmer behind the arpeggio, not a riser",
            "a little analogue drift on the pad, never on the kick",
            "long delays on the pluck, dry drums",
            "air and a distant wash only in the breakdown",
            "the chords widen in the peak and narrow again after",
        ),
        mood=(
            "emotive and widescreen", "hopeful and driving",
            "bittersweet and warm", "yearning and steady",
        ),
        production=(
            "the mix is wide, clean and lush",
            "the kick stays dry while the chords are far away",
            "the melody is clear, never buried in the bass",
            "loudness comes from the arrangement, not from clipping",
        ),
        structure=(
            "a sparse intro, a melodic build, a full emotional peak, "
            "then a long outro",
            "the theme is stated on piano, then by the synth, then by both",
            "one breakdown with no drums, then the theme returns intact",
        ),
        instruments=(
            "Instruments: Synthesizer, Drums, Bass",
            "Instruments: Piano, Synthesizer, Drums, Bass",
            "Instruments: Strings, Synthesizer, Drums",
        ),
        prose="melodic techno",
        keywords=(
            "melodic techno", "emotive pads", "arpeggio", "piano figure",
            "driving groove", "bittersweet", "string peak", "dry kick",
        ),
    ),
    "House - Deep": Genre(
        tags=("Genre: House", "Genre: Deep House"),
        bpm=(118, 124),
        drums=(
            "a soft four-to-the-floor kick with brushed hats",
            "a warm, swung groove with light percussion",
            "a muffled kick and a shaker, no clap",
            "congas answering the kick in a quiet pattern",
            "hats that drag a little behind the beat",
            "a rimshot so soft it is almost a click",
        ),
        bass=(
            "a deep, round bassline with a soft attack",
            "a warm sub that rolls gently under the chords",
            "a bass guitar thumbing long notes, never slapped",
            "a synth bass that only moves when the chord changes",
            "a low hum through the breakdown, then the bassline returns",
            "root notes only, lots of space between them",
        ),
        lead=(
            "a muted jazz guitar figure",
            "a soft pad chord progression drifting over the groove",
            "a breathy tenor sax phrase, four bars and out",
            "electric piano stabs, two chords, widely voiced",
            "a sung ooh, wordless, answering the bass",
            "a marimba pattern, quiet, in the upper register",
        ),
        texture=(
            "a small-room wash on the chords only",
            "shaker layers that widen the groove without brightening it",
            "a faint hiss under the kick, like an old desk",
            "the chords filtered down in the breakdown",
            "a little chorus on the guitar, none on the drums",
        ),
        mood=(
            "warm and soulful", "late-night and groovy",
            "deep and unhurried", "close and low-lit",
        ),
        production=(
            "the production is warm and unhurried, nothing bright on top",
            "the kick is round and the hats are dull",
            "the vocal texture sits inside the chords, not in front",
            "space is left under the bass on purpose",
        ),
        structure=(
            "a drum intro, a long deep groove, a stripped break, then the "
            "full arrangement returns",
            "the same two chords for the whole track, the lead changing over them",
            "a DJ-friendly intro of kick and hat, the song arriving late",
        ),
        instruments=(
            "Instruments: Electric Piano, Bass, Drums, Synthesizer",
            "Instruments: Guitar, Bass, Drums, Saxophone",
            "Instruments: Marimba, Bass, Drums, Synthesizer",
            "Instruments: Bass Guitar, Drums, Synthesizer",
        ),
        prose="deep house",
        keywords=(
            "deep house", "warm sub bass", "shuffled hats", "jazz guitar",
            "late night", "congas", "tenor sax", "two chords",
        ),
    ),
    "House - Classic": Genre(
        tags=("Genre: House",),
        bpm=(122, 128),
        drums=(
            "a punchy four-to-the-floor kick with a crisp clap",
            "a swinging drum groove with live-feeling percussion",
            "a drum-machine kick and a real handclap",
            "open hats on the offbeat, Chicago style",
            "a tambourine locked to the clap",
            "a live kick over a machine hat pattern",
        ),
        bass=(
            "a bouncing filtered bassline",
            "a round, syncopated bass hitting the offbeats",
            "an organ bass, left hand only, pumping with the kick",
            "a simple root-fifth bass, no fills",
            "a bassline that drops out for the piano break",
            "one-note bass stabs, short and dry",
        ),
        lead=(
            "a gospel-flavoured piano riff",
            "a plucked organ stab pattern",
            "a bright disco string line",
            "a diva vocal sample, one word, pitched and repeated",
            "a brass stab on the first beat of the chorus",
            "a sparkling high piano run into the drop",
        ),
        texture=(
            "a little vinyl noise under the piano, not the whole mix",
            "tambourine and shaker lifting the chorus",
            "a short room on the clap only",
            "the strings wide, the kick narrow",
            "a filter opening across the last eight bars of the build",
        ),
        mood=(
            "uplifting and euphoric", "joyful and warm",
            "classic and bouncy", "sunny and communal",
        ),
        production=(
            "the mix is bright, punchy and club-ready",
            "the piano is up front and the kick is just behind it",
            "it sounds like a 1988 drum machine and a real piano",
            "the top end is crisp without being harsh",
        ),
        structure=(
            "a DJ-friendly drum intro, a building sixteen bars, a euphoric "
            "drop and a stripped outro",
            "piano first, then drums, then the full band, then piano alone",
            "the vocal sample is saved for the second chorus",
        ),
        instruments=(
            "Instruments: Piano, Bass, Drums, Organ",
            "Instruments: Piano, Strings, Drums, Bass",
            "Instruments: Organ, Drums, Sampler, Bass",
        ),
        prose="classic house",
        keywords=(
            "classic house", "gospel piano", "disco strings",
            "four on the floor", "handclaps", "organ stabs", "tambourine", "diva sample",
        ),
    ),
    "House - Tech": Genre(
        tags=("Genre: House", "Genre: Techno"),
        bpm=(124, 130),
        drums=(
            "a tight, dry kick with clipped closed hats",
            "a stripped groove with a sharp rimshot",
            "a kick, a clap and a shaker, nothing else",
            "offbeat hats, very short, no reverb",
            "a cowbell pattern that enters only in the main groove",
            "percussion loops swapped every sixteen bars, kick unchanged",
        ),
        bass=(
            "a syncopated, punchy bass hook",
            "a rubbery filtered bassline driving the groove",
            "a bass riff of five notes, funky and short",
            "the bass ducks hard against the kick and snaps back",
            "a percussive bass, more slap than sustain",
            "root and octave only, placed on the offbeat",
        ),
        lead=(
            "a chopped vocal stab repeating on the offbeat",
            "a minimal plucked riff, sidechained to the kick",
            "a one-word shout, used as percussion",
            "a tiny synth blip, two pitches, no phrase longer than a bar",
            "a rim-like synth tick doubling the percussion",
            "no topline at all through the intro, only bass and drums",
        ),
        texture=(
            "dry percussion loops and very short delays",
            "a small noise rise only at the end of a phrase",
            "the groove filtered down, then snapped back",
            "almost no reverb anywhere",
            "a little saturation on the bass, the drums left clean",
        ),
        mood=(
            "driving and stripped", "hypnotic and funky",
            "dark and rolling", "tight and physical",
        ),
        production=(
            "the mix is tight, dry and built for a big room",
            "the kick and bass are the song",
            "nothing lush is allowed in the midrange",
            "it is arranged for a DJ, with a long usable intro",
        ),
        structure=(
            "a long percussive intro, a rolling main groove, a filtered "
            "break, then back to the groove",
            "the vocal stab is withheld until the bass has been established",
            "three grooves, each a small change of percussion, same bass",
        ),
        instruments=(
            "Instruments: Drums, Bass, Synthesizer",
            "Instruments: Drum Machine, Bass, Sampler",
            "Instruments: Drums, Synthesizer, Percussion",
        ),
        prose="tech house",
        keywords=(
            "tech house", "vocal stabs", "rubbery bass", "dry percussion",
            "sidechain", "rolling groove", "cowbell", "offbeat hats",
        ),
    ),
    "Dubstep - Deep": Genre(
        tags=("Genre: Dubstep", "Genre: Dub", "Genre: Bass"),
        bpm=(138, 142),
        drums=(
            "a sparse half-time beat with a dry rimshot on the third beat",
            "a skeletal two-step pattern with shuffled hats and long gaps",
            "a restrained beat with a soft kick and a cracking wooden snare",
            "swung percussion with a single tambourine hit marking the bar",
            "a kick on beat one and a snare on beat three, hats almost absent",
            "woodblock and a soft shaker, the beat more implied than played",
        ),
        bass=(
            "an enormous sine sub moving in slow, whole notes",
            "a deep dub bassline that swells and decays under everything",
            "a warm sub felt in the chest rather than heard, drifting slowly in pitch",
            "a heavy sub pressure that holds one note for bars at a time",
            "a bass note that enters late in the bar and rings through the next",
            "root movement only, each note held for four bars",
        ),
        lead=(
            "a minor key dub chord stab drenched in tape delay",
            "a distant melodica line echoing into the space",
            "a sparse bell melody left to ring out",
            "a lonely, detuned string pad drifting across the bars",
            "a single organ chord, struck and sent through a spring",
            "a far-off flute note, one pitch, repeating slowly",
        ),
        texture=(
            "cavernous reverb and long dub delay throws",
            "vinyl crackle, rain and distant room noise",
            "a low drone humming underneath the whole track",
            "spring reverb splashes on the offbeats",
            "the space between hits is louder than the hits",
        ),
        mood=(
            "meditative and heavy", "dark and spacious",
            "dread-laden and warm", "hypnotic and patient",
        ),
        production=(
            "the production is deep and murky, built for a sound system",
            "the mix prizes weight and space over loudness, with enormous low end",
            "the drums are small and the bass is the room",
            "nothing in the midrange competes with the sub",
        ),
        structure=(
            "a long atmospheric intro, the sub entering as the drop rather than "
            "any gimmick, sixteen-bar sections, and a stripped dub outro",
            "it rolls patiently, dropping to bass and percussion in the middle "
            "before the full weight returns",
            "the chord stab is introduced alone, then the beat, then the sub",
        ),
        instruments=(
            "Instruments: Bass, Drums, Synthesizer",
            "Instruments: Sub Bass, Drums, Melodica, Organ",
            "Instruments: Bass, Percussion, Strings",
        ),
        prose="deep dubstep",
        keywords=("deep dubstep", "sub bass pressure", "half-time", "two-step",
                  "dub chords", "tape delay", "meditative", "sound system"),
    ),
    "Dubstep - Brostep": Genre(
        tags=("Genre: Dubstep", "Genre: Bass"),
        bpm=(140, 145),
        drums=(
            "a half-time drum pattern with a huge snare on the third beat",
            "sparse, heavy drums with rattling trap-style hats",
            "a snare so wide it fills the bar, kick only on the one",
            "machine-gun hat rolls into the drop, then silence",
            "a clap stacked on the snare, both clipped",
            "tom fills that exist only to announce the drop",
        ),
        bass=(
            "a growling wobble bass modulated by an LFO",
            "a screaming talking bass full of vowel movement",
            "a violently distorted mid-range bass",
            "a bass that yoyos between two notes, then holds a roar",
            "a mid-range growl with a separate pure sub underneath",
            "a bass drop that pitches down a full octave in one beat",
        ),
        lead=(
            "a detuned supersaw lead cutting through the drop",
            "an ominous minor pad motif before the drop",
            "a screamed synth octave on the downbeat of the drop",
            "a chiptune-like arpeggio, tiny against the bass",
            "a choir stab, one chord, used as an impact",
            "a lead that only plays in the build, gone once the bass starts",
        ),
        texture=(
            "impacts, risers and downlifters mark every transition",
            "granular noise and sub drops thicken the low end",
            "a reverse crash filling the bar before the drop",
            "the mix ducks everything but the bass at the hit",
            "distorted noise bursts instead of cymbals",
        ),
        mood=(
            "aggressive and heavy", "dark and menacing",
            "explosive and blunt", "loud and theatrical",
        ),
        production=(
            "the mix is huge, distorted and sub-heavy",
            "the snare is the second loudest thing after the bass",
            "the build is clean so the drop feels filthy",
            "mid-range bass is pushed until it almost breaks",
        ),
        structure=(
            "a tense build, a hard drop at the halfway point, then a second, "
            "heavier drop",
            "half the track is the build; the drop is short and repeated",
            "drop, breakdown to a single pad, then a different bass for the second drop",
        ),
        instruments=(
            "Instruments: Bass, Drums, Synthesizer",
            "Instruments: Synthesizer, Drums, Sub Bass",
            "Instruments: Bass, Drum Machine, Sampler",
        ),
        prose="brostep",
        keywords=(
            "brostep", "wobble bass", "half-time drums", "huge snare",
            "supersaw lead", "sub drop", "vowel roar", "impact",
        ),
    ),
    "Glitch Hop": Genre(
        tags=("Genre: Glitch Hop", "Genre: Hip Hop", "Genre: Electronic"),
        bpm=(100, 112),
        drums=(
            "a chopped breakbeat cut into stuttering micro-edits",
            "heavy hip-hop drums with glitched retriggers and gated stutters",
            "a swung beat interrupted by rapid triplet fills and tape stops",
            "thick, compressed drums with a snare that stutters into the next bar",
            "a boom-bap shell with the snare retriggered into a glitch",
            "kick and snare steady, hats cut into uneven bursts",
        ),
        bass=(
            "a heavily processed synth bass that talks and morphs",
            "a fat, distorted bass riff with a funky swagger",
            "a bit-crushed sub that grinds under the groove",
            "a rubbery modulated bass locked to the drum edits",
            "a bass note held, then sliced into the same rhythm as the stutter",
            "an octave bass, clean for a bar, then crushed",
        ),
        lead=(
            "a filtered funk guitar sample chopped into a riff",
            "a warped, pitch-bent synth melody",
            "a chopped vocal shard stuttering on the offbeat",
            "a warm, melodic synth line cutting through the grit",
            "a horn sample, one hit, then the same hit an octave down and glitched",
            "a square-wave hook that stays in tune while the drums fall apart",
        ),
        texture=(
            "granular glitches, digital debris and reversed hits",
            "bit-crushed artefacts and tape-stop sweeps between sections",
            "surface noise under heavily processed sound design",
            "buffer repeats that freeze a syllable and then release it",
            "a digital click trail following the snare edits",
        ),
        mood=(
            "funky and mechanical", "gritty and cinematic",
            "playful and heavy", "swaggering and warped",
        ),
        production=(
            "the production is dense and heavily sound-designed, punchy and mid-tempo",
            "the mix is thick and gritty with every element processed hard",
            "the drums are crushed and the lead is left relatively clean",
            "edits are obvious; nothing is smoothed over",
        ),
        structure=(
            "an atmospheric intro, a heavy swung groove, a glitched breakdown "
            "where everything stutters, then a fuller final groove",
            "the riff plays straight, then the same riff is sliced apart",
            "a groove, a full stop, the groove again with a new bass",
        ),
        instruments=(
            "Instruments: Drums, Bass, Synthesizer, Guitar",
            "Instruments: Drums, Synthesizer, Sampler",
            "Instruments: Bass, Drums, Turntables",
        ),
        prose="glitch hop",
        keywords=("glitch hop", "stutter edits", "chopped breaks", "processed bass",
                  "hip-hop swing", "bitcrush", "tape stop", "sound design"),
    ),
    "Ambient": Genre(
        tags=("Genre: Ambient",),
        bpm=(60, 80),
        drums=(
            "no drums at all",
            "only the faintest pulse of soft percussion",
            "a single soft hit every few bars, barely a beat",
            "distant wind chimes instead of any kit",
            "a heartbeat-slow thump, felt more than counted",
            "silence where a rhythm would be",
        ),
        bass=(
            "a slow sub drone underpinning everything",
            "no bass beyond a low hum",
            "a bowed low note that never changes pitch",
            "the fundamental of a pad, no separate bass part",
            "a tone so low it is only a pressure",
            "bass absent until the final third, then one held note",
        ),
        lead=(
            "sparse piano notes left to ring out",
            "a slow evolving pad that never quite resolves",
            "a distant bowed string sustaining across the piece",
            "a glass harmonica tone, one pitch at a time",
            "a clarinet note held until it disappears",
            "high sine tones, far apart, no phrase",
        ),
        texture=(
            "tape hiss, field recordings and long reverb tails",
            "granular clouds drifting slowly across the stereo image",
            "shoreline and air, no musical event for long stretches",
            "the sound of a large empty room, mics far away",
            "a soft chorusing that moves the pad without adding notes",
        ),
        mood=(
            "gentle and unobtrusive", "melancholic and spacious",
            "calm and weightless", "still and pale",
        ),
        production=(
            "the recording is soft, wide and deeply reverberant",
            "nothing is close-mic'd; every source is far",
            "dynamics stay small from start to end",
            "there is no beat to mix around, only depth",
        ),
        structure=(
            "it evolves slowly and continuously with no clear sections",
            "one idea enters, another leaves, they never stack into a chorus",
            "the piece is one long fade, louder only in the middle by a little",
        ),
        instruments=(
            "Instruments: Synthesizer, Piano, Strings",
            "Instruments: Piano, Field Recording",
            "Instruments: Strings, Synthesizer",
        ),
        prose="ambient",
        keywords=(
            "evolving pads", "sparse piano", "long reverb", "no drums",
            "drone", "glass tones", "field recording", "weightless",
        ),
    ),
    "Cinematic / Trailer": Genre(
        tags=("Genre: Soundtrack", "Genre: Orchestral"),
        bpm=(80, 110),
        drums=(
            "a frame drum on a slow four-bar cycle",
            "taiko hits and braams punctuating the build",
            "toms in a rising pattern, cymbals held back until the peak",
            "a war-drum pulse, single hits, getting closer together",
            "orchestral percussion only on the downbeats",
            "no kit, only impacts and a low drum every bar",
        ),
        bass=(
            "a low cello ostinato carrying the pulse",
            "a sub-heavy orchestral drone",
            "basses and cellos in octaves, long notes",
            "a brass pedal tone under the strings",
            "the low end is the braam, not a bass guitar",
            "pizzicato basses ticking, then switching to bowed",
        ),
        lead=(
            "distant horn swells rising over the strings",
            "a solo violin line above a bed of tremolo strings",
            "a french horn call, five notes, then the orchestra answers",
            "a choir singing vowels, no language",
            "a piano motif stated once, then taken by the strings",
            "trumpet in unison with the horns at the peak only",
        ),
        texture=(
            "choral pads and metallic risers",
            "granular string textures and air",
            "a reverse cymbal into each new section",
            "the sound of a scoring stage, chairs and air",
            "cluster chords in the strings under the melody",
        ),
        mood=(
            "serious and restrained, building subtly", "epic and triumphant",
            "ominous and vast", "solemn and gathering",
        ),
        production=(
            "recorded in a large scoring stage with deep natural reverb",
            "the orchestra is a single image, not a stack of samples",
            "impacts are big but the melody stays intelligible",
            "the peak is loud because more players enter, not because of limiting",
        ),
        structure=(
            "it begins sparse and restrained, builds steadily through the middle "
            "and resolves into a full, powerful final section",
            "a motif, a development, a silence, then the full statement",
            "percussion withholds until the last third",
        ),
        instruments=(
            "Instruments: Strings, Brass, Percussion, Choir",
            "Instruments: Cello, French Horn, Timpani, Piano",
            "Instruments: Violin, Strings, Brass, Percussion",
        ),
        prose="cinematic trailer",
        keywords=(
            "orchestral", "taiko drums", "cello ostinato", "horn swells",
            "choir", "epic build", "braam", "french horn",
        ),
    ),
    "Lo-fi Hip Hop": Genre(
        tags=("Genre: Hip Hop", "Genre: Chillout"),
        bpm=(80, 92),
        drums=(
            "loose, dusty drums swung slightly off the grid",
            "mellow drums with a soft rimshot",
            "a brushed snare and a quiet kick, hats almost gone",
            "a drum loop that wobbles in pitch, as if the tape is tired",
            "finger snaps and a soft kick, no snare",
            "the same two-bar loop, the snare a little late every time",
        ),
        bass=(
            "a round upright bass walking gently",
            "a soft sine sub bass",
            "a muted bass guitar, roots only",
            "a bass note sampled with the drum hit, not played separately",
            "upright bass in half notes, never busy",
            "a low hum that follows the chord and does not funk",
        ),
        lead=(
            "a muted jazz guitar motif",
            "a worn piano loop, two chords, tape-warbled",
            "a vibraphone lick, slow, slightly out of tune",
            "a flute sample, four notes, repeating",
            "a hummed melody, close and quiet, no words",
            "a soft horn pad, one chord held under the loop",
        ),
        texture=(
            "vinyl crackle, tape wow and distant street noise",
            "rain on a window and a muffled room",
            "the loop filtered so the top end is gone",
            "a radio voice, unintelligible, far in the background",
            "wow and flutter on the whole mix, not just the sample",
        ),
        mood=(
            "relaxed and nostalgic", "sleepy and warm",
            "hazy and private", "gentle and worn",
        ),
        production=(
            "the whole thing is filtered, saturated and slightly degraded",
            "it sounds like a cassette of a beat, not a finished master",
            "the drums and the chord are one loop, not a multitrack",
            "nothing transient is sharp",
        ),
        structure=(
            "it loops gently with small variations rather than big sections",
            "the same loop, a bar of rain, the loop again with the hum",
            "no drop and no chorus, only a loop that thins and returns",
        ),
        instruments=(
            "Instruments: Piano, Bass, Drums, Guitar",
            "Instruments: Vibraphone, Upright Bass, Drums",
            "Instruments: Flute, Sampler, Drums",
        ),
        prose="lo-fi hip hop",
        keywords=(
            "dusty drums", "vinyl crackle", "tape wow", "soft sine bass",
            "muted guitar", "worn piano", "sleepy", "cassette",
        ),
    ),
    "Synthwave": Genre(
        tags=("Genre: Synthwave", "Genre: Electronic"),
        bpm=(100, 118),
        drums=(
            "gated reverb snares and a punchy electronic kick",
            "a drum machine with a loud clap and straight hats",
            "electronic toms filling into the chorus",
            "a kick on every beat and a snare with a long gated tail",
            "the hats are sixteenth notes, the snare is enormous",
            "a Linn-style pattern, simple and loud",
        ),
        bass=(
            "a driving arpeggiated synth bass",
            "a fat analogue bass pulse",
            "a sequenced bass, eight notes to the bar, no swing",
            "octave jumps on a saw bass under the lead",
            "a pulsing bass that only plays in the verse",
            "one held bass note through the chorus pad",
        ),
        lead=(
            "a soaring analogue lead with heavy chorus",
            "bright neon arpeggios",
            "a square-wave melody, portamento between the notes",
            "a brass-patch fanfare for the chorus",
            "a delayed pluck playing a minor hook",
            "a vocal-ish synth lead with no lyrics, wide and chorused",
        ),
        texture=(
            "shimmering pads and tape delay throws",
            "a chorus so wide the lead is almost two instruments",
            "gated snare tails filling the gaps in the melody",
            "a little tape hiss under an otherwise glossy mix",
            "the pad enters an octave up for the final chorus",
        ),
        mood=(
            "nostalgic and neon-lit", "moody and nocturnal",
            "driving and retro", "glossy and lonely",
        ),
        production=(
            "the production is glossy eighties with heavy chorus and reverb",
            "the snare is gated and everything else is wet",
            "it sounds like a hardware sequencer, not a plugin stack",
            "the chorus is wider and louder than the verse, nothing else changes",
        ),
        structure=(
            "a synth intro, a driving main section and a soaring final chorus",
            "arpeggio intro, verse with bass, chorus with the lead, instrumental break",
            "the hook is the arpeggio, stated three times, bigger each time",
        ),
        instruments=(
            "Instruments: Synthesizer, Drums, Bass",
            "Instruments: Synthesizer, Drum Machine",
            "Instruments: Synthesizer, Electric Guitar, Drums",
        ),
        prose="synthwave",
        keywords=(
            "analogue synths", "gated reverb snare", "arpeggiated bass",
            "neon pads", "chorus lead", "square wave", "portamento", "drum machine",
        ),
    ),
    "Trance": Genre(
        tags=("Genre: Trance",),
        bpm=(136, 142),
        drums=(
            "a punchy four-to-the-floor kick with rolling offbeat hats",
            "kick and offbeat hat only, the snare saved for the peak",
            "a rolling hat pattern that speeds through the build",
            "the kick absent for the whole breakdown, then back on the one",
            "a clap on the two and four once the drop lands",
            "sixteenth hats, completely straight, no swing",
        ),
        bass=(
            "an offbeat rolling bassline locked under the kick",
            "a bass that pumps on every offbeat and rests on the kick",
            "root notes only, a new root each eight bars with the chord",
            "the bass disappears in the breakdown and returns with the kick",
            "a saw bass an octave under the lead, same rhythm as the offbeat",
            "one bass note held, sidechained so it breathes with the kick",
        ),
        lead=(
            "a euphoric supersaw lead",
            "a rapid plucked arpeggio climbing in octaves",
            "a long supersaw note that bends up into the drop",
            "a gated pluck playing sixteenths through the breakdown",
            "a melody of long notes, few of them, very high",
            "the arpeggio and the supersaw together only at the final peak",
        ),
        texture=(
            "huge white-noise risers and long reverb sweeps",
            "a noise wash that is the entire breakdown bed",
            "delays on the pluck bouncing in triplets",
            "the lead widened with unison detune, the kick mono",
            "an impact only at the moment the kick returns",
        ),
        mood=(
            "euphoric and uplifting", "emotional and widescreen",
            "yearning and bright", "vast and climbing",
        ),
        production=(
            "the mix is wide, bright and enormous",
            "the breakdown is almost only reverb and the pluck",
            "the kick is the loudest element once it returns",
            "nothing funky, nothing swung, everything lifted",
        ),
        structure=(
            "a long build, a full beatless breakdown in the middle, then the main "
            "euphoric drop",
            "kick for two minutes, kick gone, the melody alone, kick back harder",
            "the arpeggio starts the track and is still there at the end",
        ),
        instruments=(
            "Instruments: Synthesizer, Drums, Bass",
            "Instruments: Synthesizer, Drum Machine",
            "Instruments: Synthesizer, Sub Bass, Drums",
        ),
        prose="trance",
        keywords=(
            "supersaw melody", "offbeat bassline", "white noise riser",
            "euphoric breakdown", "plucked arpeggio", "straight kick",
            "beatless middle", "unison detune",
        ),
    ),
    "UK Garage": Genre(
        tags=("Genre: Garage", "Genre: Electronic"),
        bpm=(130, 136),
        drums=(
            "a shuffled two-step beat with skippy hats and a sharp snare",
            "kick on the one, snare skipping, hats rushing ahead",
            "a 2-step pattern with a shaker filling the gaps",
            "the snare lands late, the kick stays strict",
            "open hats only on the skip, otherwise closed and short",
            "a clap with the snare, both very dry",
        ),
        bass=(
            "a bouncing organ bass",
            "a deep sub bass with a quick glide",
            "a bass that hits with the kick and slides off",
            "short bass stabs, never a long note",
            "a sub that only plays in the second half of the bar",
            "organ left-hand bass, percussive and swung",
        ),
        lead=(
            "chopped vocal-textured stabs",
            "warm organ chords",
            "a two-chord organ riff, staccato",
            "a vocal chop used as a snare answer, no sentence",
            "a bright synth pluck on the offbeat",
            "a brief sax lick, four notes, then the organ returns",
        ),
        texture=(
            "crisp shakers and very short delays",
            "a little vinyl noise under an otherwise clean mix",
            "the organ slightly chorused, the drums bone dry",
            "a skip in the percussion that the bass copies",
            "almost no reverb, the swing is the space",
        ),
        mood=(
            "bouncy and playful", "smooth and late-night",
            "skippy and bright", "slick and swung",
        ),
        production=(
            "the mix is snappy and swung with a tight low end",
            "the drums are louder than the organ",
            "it is arranged to be mixed by a DJ, short phrases",
            "the vocal chop is a rhythm, not a singer",
        ),
        structure=(
            "a drum intro, a bouncing main groove and a stripped-back break",
            "organ chord, then drums, then the vocal chop, then all three",
            "the break is drums and sub only, the organ saved for the return",
        ),
        instruments=(
            "Instruments: Bass, Drums, Organ, Synthesizer",
            "Instruments: Organ, Drums, Sampler, Sub Bass",
            "Instruments: Drums, Bass, Saxophone, Organ",
        ),
        prose="UK garage",
        keywords=(
            "two-step beat", "skippy hats", "organ bass", "chopped vocal stabs",
            "swing", "shaker", "late snare", "staccato organ",
        ),
    ),
    "Future Garage": Genre(
        tags=("Genre: Garage", "Genre: Electronic", "Genre: Chillout"),
        bpm=(128, 138),
        drums=(
            "a soft two-step shuffle with brushed, distant snares",
            "a muted skippy beat mixed low under the pads",
            "gentle clicks and shakers with a light, padded kick",
            "a kick that misses the occasional beat on purpose",
            "hats reduced to a soft tick, snare far away",
            "the beat enters late and stays quiet",
        ),
        bass=(
            "a warm, restrained sub that never dominates",
            "a soft filtered bassline sitting deep in the mix",
            "a muted sub pulse felt more than heard",
            "a bass note only on the first beat of the phrase",
            "a rounded sub that swells with the pad and recedes",
            "no riff, just a low warmth under the shuffle",
        ),
        lead=(
            "a pitched, wordless vocal fragment drifting in and out",
            "a muted piano figure buried in reverb",
            "a soft bell melody half-hidden behind the pads",
            "a guitar harmonic, one note, repeating slowly",
            "a choir-like pad with no consonants",
            "a music-box phrase, very quiet, behind the vocal fragment",
        ),
        texture=(
            "rain, room noise and tape hiss under everything",
            "wide reverb tails and a soft haze",
            "distant city ambience and soft granular haze",
            "the beat low-passed so it sits inside the pad",
            "a fog that thickens in the middle and clears at the edges",
        ),
        mood=(
            "wistful and hazy", "calm and introspective",
            "melancholic and warm", "soft and nocturnal",
        ),
        production=(
            "the mix is soft-edged, low-passed and unhurried",
            "the production is muted and diffuse, nothing sharp",
            "the vocal fragment is a texture, not a hook",
            "reverb is longer than the notes",
        ),
        structure=(
            "it drifts in on atmosphere, settles into a gentle shuffle, thins out "
            "in the middle and fades rather than ending",
            "pad first, shuffle second, a thinner middle, the same shuffle returning quieter",
            "no drop: the track simply becomes a little fuller, then less",
        ),
        instruments=(
            "Instruments: Synthesizer, Piano, Drums, Bass",
            "Instruments: Piano, Sampler, Drums, Sub Bass",
            "Instruments: Synthesizer, Guitar, Drums",
        ),
        prose="future garage",
        keywords=(
            "future garage", "soft shuffle", "muted sub", "wordless fragment",
            "rainy atmosphere", "reverb-soaked", "study beats", "half-hidden bell",
        ),
    ),
    "Post-Dubstep": Genre(
        tags=("Genre: Garage", "Genre: Downtempo", "Genre: Electronic"),
        bpm=(128, 138),
        drums=(
            "a clattering, unquantised two-step pattern that never sits on the grid",
            "sparse garage drums made of vinyl clicks, lighter flicks and rimshots",
            "a loose shuffle with a dry snare and long silences between hits",
            "hand-placed percussion that drags and rushes like a worn tape",
            "a kick that arrives late and a snare that arrives later",
            "clicks and a dry snare, the pattern different every four bars",
        ),
        bass=(
            "a deep, warm sub that appears for a few bars and vanishes",
            "a soft low pulse buried far beneath the surface noise",
            "a muted sub weight that never resolves anywhere",
            "one bass note, then a long absence",
            "a sub that slides down and does not come back up",
            "low end only as a pressure, no pitch you could sing",
        ),
        lead=(
            "a pitched-up wordless vocal fragment, anonymous and yearning",
            "a slowed, time-stretched R&B vocal shard repeating out of context",
            "a single detuned synth chord holding across the whole section",
            "a faint, ghostly melody half-buried in the hiss",
            "a piano note, detuned, struck once a phrase",
            "a sample of a voice breathing, pitched, not speaking",
        ),
        texture=(
            "heavy vinyl crackle used as percussion in its own right",
            "rain, distant traffic and late-night city ambience",
            "tape hiss, room noise and the sound of a worn recording",
            "reversed reverb tails bleeding between sections",
        ),
        mood=(
            "melancholy and isolated", "nocturnal and yearning",
            "haunted and weightless", "lonely and unresolved",
        ),
        production=(
            "the production is lo-fi and murky, everything distant and off-grid",
            "the mix is hazy and degraded, as if recorded off a worn tape",
            "the vocal shard is quieter than the crackle",
            "nothing is quantised and nothing is bright",
        ),
        structure=(
            "it fades in on crackle and rain, drifts through loose sections that "
            "never quite repeat, and dissolves rather than ending",
            "a long quiet opening, a broken shuffle that comes and goes, and a "
            "final section stripped back to vocal and noise",
            "the beat leaves for a long time and is not promised back",
        ),
        instruments=(
            "Instruments: Drums, Bass, Synthesizer",
            "Instruments: Sampler, Drums, Sub Bass",
            "Instruments: Piano, Drums, Field Recording",
        ),
        prose="post-dubstep",
        keywords=(
            "post-dubstep", "unquantised shuffle", "crackle as percussion",
            "pitched vocal shard", "night bus", "off-grid", "yearning", "worn tape",
        ),
    ),
    "Psydub": Genre(
        tags=("Genre: Dub", "Genre: Chillout", "Genre: Electronic"),
        bpm=(85, 110),
        drums=(
            "a slow dub beat with a heavy, delayed rimshot",
            "loose organic percussion with hand drums and shakers",
            "a laid-back halftime groove with tape-delayed snares",
            "congas and a rim, the kick only every other bar",
            "a shaker pattern that phase-shifts against the rimshot",
            "frame drum and a soft electronic kick, both delayed",
        ),
        bass=(
            "a deep, round dub bassline walking slowly",
            "a warm analogue sub with a long, soft decay",
            "a rolling bass figure that repeats hypnotically",
            "a bass guitar sliding into each root from below",
            "one bass note sent through a delay until it becomes the rhythm",
            "a sub that bubbles, short notes, lots of space",
        ),
        lead=(
            "a psychedelic synth line bending through a filter",
            "a sitar-like melody echoing into the distance",
            "sparse marimba and kalimba figures drifting over the beat",
            "a melodica line soaked in spring reverb",
            "a flute line that bends the same way the synth does",
            "a didgeridoo drone under the percussion, not a melody",
        ),
        texture=(
            "long dub delay throws trailing off into space",
            "field recordings of forest and water under the groove",
            "swirling phased pads and backwards textures",
            "a spring reverb splash on the rim only",
            "insects and leaves, quiet, under the bass",
        ),
        mood=(
            "hypnotic and warm", "psychedelic and unhurried",
            "earthy and spacious", "ritual and slow",
        ),
        production=(
            "the production is warm and analogue with heavy tape delay",
            "the mix is deep, dubby and wide, everything drenched in space",
            "the delay is a musical part, not an effect on top",
            "the percussion is organic and the bass is electronic, and both stay",
        ),
        structure=(
            "it builds slowly from percussion and bass, layers textures through "
            "the middle, and strips back to the dub groove at the end",
            "a long percussion intro, the bass enters, the melodica last",
            "the groove never drops; layers come and go over it",
        ),
        instruments=(
            "Instruments: Bass, Drums, Synthesizer, Percussion",
            "Instruments: Melodica, Bass, Hand Drums, Synthesizer",
            "Instruments: Kalimba, Flute, Bass, Percussion",
        ),
        prose="psydub",
        keywords=(
            "psydub", "spring reverb", "hand drums", "melodica",
            "psychedelic", "forest recordings", "delay throws", "kalimba",
        ),
    ),
    "Trip Hop": Genre(
        tags=("Genre: Trip Hop",),
        bpm=(75, 95),
        drums=(
            "a heavy, sluggish break dragging behind the beat",
            "sampled drums with a thick, compressed snare",
            "a slow groove with tambourine on the offbeat",
            "a break chopped so the snare lands late",
            "kick and snare only, hats removed from the sample",
            "a drum loop run through a filter that opens and closes",
        ),
        bass=(
            "a thick upright bass line walking under the beat",
            "a fuzzy analogue sub with a slow attack",
            "a bass guitar doubling a minor riff, picked slowly",
            "one low note held under the string loop",
            "the bass drops out and the break is suddenly thin",
            "a sub hit with the kick, then silence in the bar",
        ),
        lead=(
            "a minor key string sample looping mournfully",
            "a detuned electric piano, two chords, no flourish",
            "a muted trumpet line drifting over the groove",
            "a haunting theremin-like lead",
            "a sung phrase with the words buried past recognition",
            "a cello line, slow, over the break",
        ),
        texture=(
            "surface noise and tape wow on the drum sample",
            "low choir pads under the strings",
            "a film-score scrape of violin, used once",
            "the sample's own room, dull and close",
            "a little distortion on the bass, the trumpet left clean",
        ),
        mood=(
            "brooding and shadowy", "smoky and melancholic",
            "paranoid and cool", "heavy and slow",
        ),
        production=(
            "the production is dark, sampled and heavily filtered",
            "the mix is thick and mid-heavy, like an old record",
            "the break is the loudest element",
            "it feels looped even when a new layer enters",
        ),
        structure=(
            "a looped intro, a long central groove with layers added and removed, "
            "and a stripped outro",
            "drums and bass, then strings, then trumpet, then drums alone",
            "the same loop three times, each pass with one element removed",
        ),
        instruments=(
            "Instruments: Drums, Bass, Electric Piano, Strings",
            "Instruments: Drums, Upright Bass, Trumpet, Sampler",
            "Instruments: Cello, Drums, Bass, Synthesizer",
        ),
        prose="trip hop",
        keywords=(
            "trip hop", "sluggish break", "minor strings", "trumpet drift",
            "theremin", "sampled drums", "shadowy", "cello line",
        ),
    ),
    "Dub Techno": Genre(
        tags=("Genre: Techno", "Genre: Dub", "Genre: Minimal"),
        bpm=(118, 128),
        drums=(
            "a soft, muffled four-to-the-floor kick with brushed hats",
            "a restrained beat with a clicking rimshot and little else",
            "a kick buried in the chord's decay",
            "hats so quiet they are only a texture",
            "the kick drops out and the delay of the chord keeps time",
            "a dry tick beside a very soft kick",
        ),
        bass=(
            "a deep, warm sub pulse locked to the kick",
            "a slow analogue bass that breathes with the chords",
            "a sub that is the same note for minutes",
            "bass and kick fused into one muffled thump",
            "a low tone that swells when the chord filter opens",
            "no separate bassline, only the chord's low partial",
        ),
        lead=(
            "a filtered chord stab drenched in delay, repeating for minutes",
            "a soft, detuned pad chord decaying into the reverb",
            "one minor chord, the filter the only change",
            "a chord hit, then only its delay for several bars",
            "two chords alternating so slowly the change is easy to miss",
            "a stab with no attack left, only the tail",
        ),
        texture=(
            "cavernous dub delay and endless reverb tails",
            "tape hiss, static and faint crackle throughout",
            "slowly evolving background drones",
            "the delay feedback riding just below a howl",
            "a muffled room, as if the track is next door",
        ),
        mood=(
            "hypnotic and submerged", "cold and meditative",
            "warm and endless", "grey and patient",
        ),
        production=(
            "the production is deep, murky and heavily processed",
            "the mix is soft-edged with everything far back in the room",
            "the chord and its delay are the arrangement",
            "the kick never cuts through; it presses",
        ),
        structure=(
            "it evolves almost imperceptibly, adding and removing a single "
            "element at a time across the whole track",
            "the same chord for the duration, the beat entering and leaving",
            "no peak: the loudest moment is only slightly louder",
        ),
        instruments=(
            "Instruments: Synthesizer, Drums, Bass",
            "Instruments: Synthesizer, Drum Machine",
            "Instruments: Chord Synth, Sub Bass, Kick",
        ),
        prose="dub techno",
        keywords=(
            "dub techno", "chord stab", "delay feedback", "muffled kick",
            "one chord", "submerged", "soft hats", "long tail",
        ),
    ),
    "Downtempo": Genre(
        tags=("Genre: Downtempo", "Genre: Chillout"),
        bpm=(85, 105),
        drums=(
            "a relaxed, padded beat with soft brushed percussion",
            "an easy mid-tempo groove with shakers and light congas",
            "a loose, unhurried drum pattern low in the mix",
            "a soft kick and a shaker, no snare",
            "hand percussion only, the pulse implied",
            "a gentle rim and a conga, both quiet",
        ),
        bass=(
            "a warm, simple bassline with plenty of room",
            "a soft analogue sub holding the harmony",
            "a bass guitar playing whole notes in the sun",
            "root and fifth, nothing faster",
            "the bass enters after the guitar has set the chord",
            "a round bass that never syncopates",
        ),
        lead=(
            "a nylon guitar figure picked gently",
            "a warm electric piano progression",
            "a soft flute melody drifting over the top",
            "a whistled tune, simple, untrained",
            "a soft organ pad, two chords, very slow",
            "a Spanish-flavoured guitar phrase, not a solo",
        ),
        texture=(
            "ocean and evening air under the groove",
            "warm pads, soft at the edges",
            "cicadas or distant water, very quiet",
            "a little chorus on the guitar only",
            "the mix feels outdoor, not a club",
        ),
        mood=(
            "sunlit and unhurried", "calm and golden",
            "relaxed and open", "balearic and easy",
        ),
        production=(
            "the production is warm and soft at every edge",
            "nothing competes with the guitar",
            "the percussion is a cushion, not a beat to dance to",
            "it could play under conversation",
        ),
        structure=(
            "it opens on atmosphere, settles into an easy groove, and drifts out",
            "guitar, then percussion, then flute, then guitar alone",
            "one tempo, one mood, a slightly fuller middle",
        ),
        instruments=(
            "Instruments: Guitar, Electric Piano, Bass, Percussion",
            "Instruments: Nylon Guitar, Flute, Shaker, Bass",
            "Instruments: Organ, Congas, Bass, Guitar",
        ),
        prose="downtempo",
        keywords=(
            "balearic", "picked nylon", "warm pads", "soft percussion",
            "sunset", "flute", "evening air", "easy groove",
        ),
    ),
    "Chillwave": Genre(
        tags=("Genre: Chillwave", "Genre: Electronic", "Genre: Chillout"),
        bpm=(95, 115),
        drums=(
            "a soft gated drum machine pattern, slightly washed out",
            "a hazy beat with a padded kick and dull snare",
            "a drum machine buried under the synth wash",
            "straight hats, but the whole kit is blurred",
            "the beat fades in with the pad and never gets loud",
            "a clap with a long reverb instead of a snare",
        ),
        bass=(
            "a warm analogue bass pulse, gently detuned",
            "a soft synth bass sitting under the wash",
            "a bass arpeggio so slow it is almost a pad",
            "root notes, chorused, out of focus",
            "the bass detuned a few cents flat of the lead",
            "a pulsing bass that breathes with the guitar figure",
        ),
        lead=(
            "a nostalgic, detuned synth melody",
            "a chorus-drenched guitar figure repeating",
            "a pitched vocal sample stretched into a pad",
            "a Juno-style pad playing the chords, no separate hook",
            "a soft lead that slides between notes",
            "a guitar chord stabbed and left to wash",
        ),
        texture=(
            "heavy tape wobble and sun-bleached saturation",
            "wide chorus and long, hazy reverb on everything",
            "the whole mix slightly underwater",
            "a faded-photo high end, nothing crisp",
            "wow on the tape across the entire song",
        ),
        mood=(
            "nostalgic and dreamlike", "hazy and warm",
            "wistful and faded", "sun-bleached and slow",
        ),
        production=(
            "the production is washed out, like a faded tape",
            "every element has the same chorus and the same reverb",
            "transients are rounded off",
            "it sounds remembered rather than performed",
        ),
        structure=(
            "a slow synth fade-in, a steady dreamlike middle, a long fade out",
            "the guitar figure is the whole song, the beat arriving underneath",
            "no chorus lift, only a slightly wider middle",
        ),
        instruments=(
            "Instruments: Synthesizer, Drums, Guitar, Bass",
            "Instruments: Synthesizer, Drum Machine, Electric Guitar",
            "Instruments: Guitar, Synthesizer, Bass",
        ),
        prose="chillwave",
        keywords=(
            "chillwave", "tape wobble", "detuned synths", "dreamy",
            "sun-bleached", "chorus guitar", "washed drums", "faded tape",
        ),
    ),
    "IDM": Genre(
        tags=("Genre: Electronic", "Genre: IDM"),
        bpm=(90, 140),
        drums=(
            "intricate glitched percussion, cut and stuttered",
            "a broken, constantly shifting beat that never quite repeats",
            "crisp programmed drums with micro-edits and rolls",
            "a grid that slips, hits landing a few milliseconds off",
            "rolls of tiny clicks that become a snare and fall apart",
            "a beat in 7, then a bar of 4, then something else",
        ),
        bass=(
            "a warm analogue bass wandering under the glitches",
            "a low sine pulse anchoring the chaos",
            "a bass note retuned per hit, never a riff you can tap",
            "sub pulses in a different meter from the drums",
            "a soft bass melody, simple, against busy percussion",
            "the low end cuts out whenever the edits get densest",
        ),
        lead=(
            "a fragile, detuned melody played on a soft synth",
            "bell tones arranged in shifting, generative patterns",
            "a melancholy pad progression underneath the edits",
            "a music-box phrase in a scale that does not match the bass",
            "FM tones, short, arranged like a mobile",
            "a piano figure, quiet, ignoring the rhythm's complexity",
        ),
        texture=(
            "granular artefacts, clicks and digital debris",
            "soft, wide pads offsetting the sharp percussion",
            "a little noise floor, otherwise very clean",
            "reverses of the percussion used as decoration",
            "space around the melody even when the drums are busy",
        ),
        mood=(
            "melancholy and intricate", "playful and strange",
            "cold and beautiful", "precise and tender",
        ),
        production=(
            "the production is precise and detailed, clinical but warm underneath",
            "the edits are intentional, not a glitch plugin on a loop",
            "the melody is easy to hear through the rhythm",
            "dry close percussion, wet only on the bells",
        ),
        structure=(
            "a quiet melodic opening, increasingly complex rhythmic edits through "
            "the middle, resolving back to the melody",
            "the beat keeps changing; the melody is the only stable thing",
            "a complex middle, then almost nothing, then the melody alone",
        ),
        instruments=(
            "Instruments: Synthesizer, Drums",
            "Instruments: Piano, Synthesizer, Percussion",
            "Instruments: Bell, Bass, Drum Machine",
        ),
        prose="IDM",
        keywords=(
            "idm", "glitch percussion", "braindance", "detuned melody",
            "generative", "microedits", "odd meter", "bell tones",
        ),
    ),
    "Funk": Genre(
        tags=("Genre: Funk",),
        bpm=(96, 112),
        drums=(
            "tight drums full of swing, ghost notes on the snare",
            "a dry kit, kick and snare locked, hats swinging hard",
            "rim clicks and a tambourine, the backbeat slightly late",
            "a breakbeat feel without leaving the pocket",
            "four-on-the-floor kick with a wildly swung hat",
            "the drummer plays the one and leaves holes for the bass",
        ),
        bass=(
            "a slapped electric bass locking hard with the kick",
            "a fingerstyle bass riff, syncopated, never straight",
            "octave pops on the bass, then a long muted note",
            "the bass plays the hook and the guitar answers",
            "a muted bass line, all rhythm, few pitches",
            "slap on the chorus, fingers on the verse",
        ),
        lead=(
            "a clipped rhythm guitar with wah",
            "a close-mic'd clavinet riff",
            "horn stabs, three notes, on the offbeat",
            "a chicken-scratch guitar, sixteenths, no chords",
            "a short synth squawk doubling the clavinet",
            "a shouted count-in used once, then the riff",
        ),
        texture=(
            "tambourine on the chorus only",
            "a little amp grit on the guitar, the bass DI-clean",
            "handclaps with the snare in the hook",
            "the horns dry and close, the kit in a small room",
            "wah swept open for one bar and closed again",
        ),
        mood=(
            "playful and confident", "gritty and energetic",
            "sweaty and tight", "swaggering and precise",
        ),
        production=(
            "warm and textured, the sound of a live rhythm section",
            "the bass is the loudest melodic instrument",
            "it sounds like a band in one room, not a grid",
            "the pocket is loose by a few milliseconds and left that way",
        ),
        structure=(
            "a tight groove with a breakdown and a punchy return",
            "bass alone for two bars, then the full band",
            "verse riff, horn hook, drum break, verse riff again",
        ),
        instruments=(
            "Instruments: Guitar, Bass, Drums, Brass, Clavinet",
            "Instruments: Electric Bass, Drums, Electric Guitar",
            "Instruments: Clavinet, Bass, Drums, Horns",
        ),
        prose="funk",
        keywords=(
            "slap bass", "wah guitar", "clavinet", "horn stabs",
            "tight drums", "chicken scratch", "ghost notes", "pocket",
        ),
    ),
    "Jazz": Genre(
        tags=("Genre: Jazz",),
        bpm=(90, 130),
        drums=(
            "brushed drums riding gently on the snare",
            "sticks on a ride cymbal, feathered kick, no backbeat",
            "brushes in a ballad, the snare a whisper",
            "a light swing on the ride, comps with the piano",
            "trading fours, drums answering the horn",
            "a light rim pattern under a swing feel",
        ),
        bass=(
            "a walking upright bass",
            "half notes on the upright, ballad tempo",
            "a bass that outlines the changes, four to the bar",
            "the upright drops to two feel in the bridge",
            "a pedal point under a modal section, then back to walking",
            "the bass solos in the middle, arco for eight bars",
        ),
        lead=(
            "a warm trumpet melody",
            "a relaxed piano solo over comping chords",
            "a tenor saxophone stating the head",
            "a guitar comping in small voicings, then a short solo",
            "a flute taking the melody, light and unforced",
            "vibraphone chords behind the horn",
        ),
        texture=(
            "the natural room sound of a small club",
            "a little spill between the mics, left in",
            "the piano lid open, the horn close",
            "audience room tone, no applause",
            "brushes louder than the sticks would be",
        ),
        mood=(
            "smoky and late-night", "bright and swinging",
            "cool and unhurried", "lyrical and blue",
        ),
        production=(
            "live-recorded and close-mic'd with natural room tone",
            "no grid, the time is the drummer's",
            "the horn is in front, the piano comps behind",
            "it sounds like one take in a small room",
        ),
        structure=(
            "a head, solos over the changes, and a return to the head",
            "melody, piano solo, horn solo, melody out",
            "a rubato intro, then the time starts with the bass walk",
        ),
        instruments=(
            "Instruments: Piano, Double Bass, Drums, Trumpet, Saxophone",
            "Instruments: Guitar, Upright Bass, Drums, Flute",
            "Instruments: Vibraphone, Piano, Double Bass, Drums",
        ),
        prose="jazz",
        keywords=(
            "brushed drums", "walking bass", "trumpet melody", "piano comping",
            "tenor head", "ride cymbal", "small club", "head and solos",
        ),
    ),
    "Minimal Electronic": Genre(
        tags=("Genre: Electronic",),
        bpm=(95, 115),
        drums=(
            "light, precise percussion with a soft kick",
            "a click, a soft kick, and nothing on the backbeat",
            "woodblock and a muted hat, very quiet",
            "the pulse is a tick, not a drum kit",
            "percussion enters halfway and stays sparse",
            "one percussive sound, repeated, panned slowly",
        ),
        bass=(
            "a clean, restrained sub bass",
            "a sine bass, one note, no movement",
            "the bass is a pulse aligned with the tick",
            "a sub that fades in and never plays a riff",
            "root only, an octave below the pluck",
            "bass absent; the pluck's low note is enough",
        ),
        lead=(
            "a clean plucky synth arpeggio",
            "a simple bell-like motif",
            "three notes on a mallet patch, long gaps",
            "a sine melody, no vibrato, no chorus",
            "a pattern of delays that is the melody",
            "one chord, a new note added every eight bars",
        ),
        texture=(
            "a soft noise that never becomes a sweep",
            "tiny granular speckles, very quiet",
            "almost dry, a short room on the bell only",
            "silence used as an instrument between the notes",
            "a slow pan, nothing else moving",
        ),
        mood=(
            "curious and modern", "calm and focused",
            "optimistic and spare", "clear and small",
        ),
        production=(
            "the mix is clean, dry and uncluttered",
            "every sound has its own space and no effects bed",
            "it is quiet on purpose",
            "nothing is doubled",
        ),
        structure=(
            "it builds gradually by adding one element at a time",
            "the pluck alone, then the tick, then the sine, then one leaves",
            "no section change, only a slow addition",
        ),
        instruments=(
            "Instruments: Synthesizer, Drums",
            "Instruments: Synthesizer, Mallet, Percussion",
            "Instruments: Bell, Sub Bass, Click",
        ),
        prose="minimal electronic",
        keywords=(
            "plucky arpeggio", "clean sub bass", "light percussion", "bell motif",
            "sine melody", "sparse", "dry mix", "one note",
        ),
    ),
    "Corporate / Uplifting": Genre(
        tags=("Genre: Corporate", "Genre: Pop"),
        bpm=(105, 120),
        drums=(
            "a steady four-on-the-floor beat with handclaps",
            "a light kick, a clap, and a soft shaker",
            "drums that enter after the piano has stated the theme",
            "no snare, only claps and a muted kick",
            "a simple pop groove, straight, not swung",
            "percussion builds by adding a shaker, then a clap, then a kick",
        ),
        bass=(
            "a simple, supportive electric bass",
            "root notes on the piano chords, nothing syncopated",
            "a soft synth bass, long notes",
            "the bass follows the left hand of the piano",
            "bass enters with the drums, not before",
            "a warm bass guitar, whole notes",
        ),
        lead=(
            "bright piano chords",
            "a plucked synth motif with subtle strings",
            "a muted acoustic guitar strumming the changes",
            "a bell motif, four notes, repeating",
            "a wordless ah, soft, with the strings",
            "a marimba doubling the piano hook",
        ),
        texture=(
            "light bell accents and airy pads",
            "strings that swell only in the last section",
            "a little sparkle on the piano, no distortion anywhere",
            "the mix opens up when the claps enter",
            "pads very quiet under the piano",
        ),
        mood=(
            "uplifting and optimistic", "confident and forward-moving",
            "bright and tidy", "warm and encouraging",
        ),
        production=(
            "the mix is bright, clean and polished",
            "the piano is the focus, everything else supports it",
            "no grit, no darkness, no drop",
            "it resolves upward and stays there",
        ),
        structure=(
            "it builds steadily and resolves on a confident final section",
            "piano theme, fuller arrangement, a quiet reminder of the theme, full end",
            "each section adds one instrument and does not take any away",
        ),
        instruments=(
            "Instruments: Piano, Strings, Bass, Drums",
            "Instruments: Piano, Acoustic Guitar, Claps, Bass",
            "Instruments: Marimba, Piano, Strings, Shaker",
        ),
        prose="uplifting corporate",
        keywords=(
            "bright piano", "subtle strings", "soft claps", "steady beat",
            "optimistic", "bright bells", "strummed guitar", "clean mix",
        ),
    ),
    "Metal": Genre(
        tags=("Genre: Metal", "Genre: Rock"),
        bpm=(140, 180),
        drums=(
            "double-kick drums with crashing cymbals",
            "a blast of kicks under a half-time snare",
            "toms announcing the breakdown, then a slow heavy beat",
            "the snare on the three, kicks in sixteenths",
            "a d-beat, fast and unadorned",
            "cymbals choked, the kit dry and close, then a crash at the riff change",
        ),
        bass=(
            "a distorted bass doubling the guitar riff",
            "the bass follows the kick, not the guitar, in the breakdown",
            "a picked bass, gritty, locked to the riff",
            "low open strings ringing under a palm-muted guitar",
            "the bass drops an octave for the chorus riff",
            "a fuzz bass line that is the riff when the guitars stop",
        ),
        lead=(
            "a heavy palm-muted guitar riff",
            "a shredding lead guitar line",
            "two guitars in harmony, thirds, only in the lead break",
            "a pinch harmonic accent at the end of the riff",
            "a clean guitar phrase in the intro, then the distortion hits",
            "a tremolo-picked riff, minor, no solo",
        ),
        texture=(
            "feedback and room ambience between phrases",
            "amp hiss in the silence before the riff",
            "a pick scrape into the chorus",
            "the guitars panned hard left and right, bass and kick centre",
            "a cymbal wash only at the end of the phrase",
        ),
        mood=(
            "aggressive and relentless", "dark and heavy",
            "tense and furious", "bleak and physical",
        ),
        production=(
            "the guitars are tight and heavily distorted, the mix aggressive",
            "the kicks are clicky enough to read through the guitars",
            "it sounds like a band, guitars doubled, one drummer",
            "the riff is louder than the solo",
        ),
        structure=(
            "a riff-driven verse, a heavier chorus and a breakdown",
            "intro riff, verse, chorus, solo over the verse riff, chorus",
            "the breakdown is half time, then the original riff returns double time",
        ),
        instruments=(
            "Instruments: Electric Guitar, Bass, Drums",
            "Instruments: Electric Guitar, Distorted Bass, Drum Kit",
            "Instruments: Guitar, Bass, Drums, Cymbals",
        ),
        prose="metal",
        keywords=(
            "palm muted guitar", "double kick", "distorted bass", "shredding lead",
            "breakdown", "tremolo riff", "blast beat", "amp feedback",
        ),
    ),
    "Folk / Acoustic": Genre(
        tags=("Genre: Folk", "Genre: Acoustic"),
        bpm=(85, 115),
        drums=(
            "light brushed percussion and a stomping foot",
            "a shaker and a soft cajon, nothing else",
            "no drums, only the guitar's own rhythm",
            "a bodhran, slow, under the fiddle",
            "hand claps on the chorus, verses bare",
            "brushes on a cardboard box, very quiet",
        ),
        bass=(
            "a gentle upright bass",
            "the guitar's bass strings are the bass part",
            "a soft bowed bass, long notes under the air",
            "upright bass in roots and fifths, sparse",
            "no bass instrument at all",
            "a hummed low note doubling the guitar's lowest string",
        ),
        lead=(
            "delicately finger-picked acoustic guitar",
            "a fiddle playing a simple air",
            "a voice humming the tune, no lyrics",
            "a mandolin tremolo on the chorus",
            "a tin whistle stating the melody once",
            "two guitars, one picking, one strumming quietly",
        ),
        texture=(
            "the natural creak and air of a close-mic'd wooden room",
            "fingers on strings, squeaks left in",
            "a little room, no reverb unit",
            "the chair and the breath between phrases",
            "open air, as if recorded on a porch",
        ),
        mood=(
            "warm and intimate", "wistful and pastoral",
            "plain and tender", "quiet and storytelling",
        ),
        production=(
            "live-recorded and close-mic'd with a natural, unprocessed sound",
            "one microphone would have been enough",
            "no click track, the tempo drifts a little",
            "the voice, if any, is a hum beside the guitar, not a lead vocal",
        ),
        structure=(
            "a simple verse and chorus shape with a quiet middle section",
            "guitar alone, fiddle joins, both, guitar alone again",
            "the melody twice, a quieter third time, and a stop",
        ),
        instruments=(
            "Instruments: Acoustic Guitar, Violin, Double Bass",
            "Instruments: Acoustic Guitar, Mandolin, Bodhran",
            "Instruments: Tin Whistle, Acoustic Guitar",
        ),
        prose="acoustic folk",
        keywords=(
            "finger picked acoustic guitar", "fiddle", "gentle upright",
            "brushed percussion", "mandolin", "tin whistle", "wooden room", "bodhran",
        ),
    ),
    "Drum & Bass - Jump-up": Genre(
        tags=("Genre: Drum and Bass",),
        bpm=(172, 176),
        drums=(
            "a simple, loud break with a clownish offbeat snare",
            "straight drums, big kick, almost no ghost notes",
            "a crash on every drop and nowhere else",
            "hats ticking evenly, the snare huge and late",
            "a fill of kicks into a silent beat, then the bass",
            "the break is basic on purpose so the bass can talk",
        ),
        bass=(
            "a bouncy bass riff that yoyos between two notes",
            "a mid-range bass hook you could chant",
            "a simple saw bass, three notes, endlessly repeated",
            "the bass drops out for a bar and restarts an octave up",
            "a percussive bass stab on the offbeat, then a long note",
            "one silly, memorable bass phrase and nothing underneath it",
        ),
        lead=(
            "a dancehall vocal chop, one syllable, used as a hit",
            "a cartoonish synth horn, two notes",
            "an off-key music-box stab before the bass returns",
            "a crowd shout with no words, on the one",
            "a short ragga phrase, chopped to the rhythm of the bass",
            "no melody, the bass riff is the tune",
        ),
        texture=(
            "a rewind sound into the drop",
            "the mix ducks for the bass phrase and comes back",
            "a silly sample, one hit, then gone",
            "almost no reverb, the riff is dry and upfront",
            "a noise blast instead of a transition",
        ),
        mood=(
            "bouncy and ridiculous", "rowdy and simple",
            "playful and loud", "cheeky and direct",
        ),
        production=(
            "the bass riff is the entire point of the mix",
            "drums are loud and plain",
            "nothing atmospheric is allowed to get in the way",
            "it is arranged to hit immediately",
        ),
        structure=(
            "a short build, the bass riff, a bar of silence, the riff again",
            "the hook is the first thing you hear and the last",
            "two drops, the second with the riff pitched up",
        ),
        instruments=(
            "Instruments: Bass, Drums, Sampler",
            "Instruments: Synthesizer, Drums, Sub Bass",
            "Instruments: Drums, Bass, Vocal Sample",
        ),
        prose="jump-up drum and bass",
        keywords=(
            "jump-up", "bouncy bass", "simple break", "dancehall chop",
            "yoyo riff", "bass rewind", "upfront riff", "chantable hook",
        ),
    ),
    "House - Acid": Genre(
        tags=("Genre: House", "Genre: Acid"),
        bpm=(122, 128),
        drums=(
            "a dry 909 kick and a sharp clap",
            "closed hats in sixteenths, no swing",
            "a rimshot pattern beside the clap",
            "the kick alone for sixteen bars before the hats",
            "open hat on the offbeat only in the peak",
            "machine drums, completely straight",
        ),
        bass=(
            "a 303 bassline squelching through a resonant filter",
            "the same 303 pattern, accent and slide changing slowly",
            "a squelch that opens until it almost screams, then closes",
            "slides between notes, the rhythm more important than the pitch",
            "the 303 is the bass and the lead at once",
            "a simpler sub under the 303 so the low end stays solid",
        ),
        lead=(
            "no separate lead; the 303 is the hook",
            "a single stab chord, minor, far behind the squelch",
            "a short vocal sample, one word, repeating",
            "a high resonant ping answering the 303's accent",
            "silence in the midrange so the filter can move",
            "a second 303 line, higher, only in the last section",
        ),
        texture=(
            "filter resonance pushed until it whistles",
            "delay on the 303 taps, not on the drums",
            "a little drive on the squelch, the kick clean",
            "the hats dry and short",
            "automation is the arrangement",
        ),
        mood=(
            "hypnotic and acidic", "tense and rolling",
            "warehouse and raw", "squelchy and locked",
        ),
        production=(
            "the 303 is louder than the drums feel",
            "it sounds like a drum machine and one silver box",
            "no chords competing with the filter",
            "the track is a pattern evolving, not a song with sections",
        ),
        structure=(
            "drums, then the 303 enters filtered down, then the resonance opens",
            "one pattern for the whole track, the filter the only story",
            "a breakdown that is only the 303, then the kick returns",
        ),
        instruments=(
            "Instruments: Drum Machine, Synthesizer, TB-303",
            "Instruments: Synthesizer, Drums, Sampler",
            "Instruments: Bass Synthesizer, Drum Machine",
        ),
        prose="acid house",
        keywords=(
            "acid house", "303", "squelch", "resonant filter",
            "909 kick", "slides", "silver box", "one pattern",
        ),
    ),
    "Breakbeat": Genre(
        tags=("Genre: Breakbeat", "Genre: Electronic"),
        bpm=(118, 132),
        drums=(
            "a big, distorted break, funky and obvious",
            "a chopped funk break with a huge snare",
            "layered breaks, one clean and one crushed",
            "a break that stops dead and restarts on the one",
            "fills every four bars, the groove never subtle",
            "live-sounding drums pushed until they crunch",
        ),
        bass=(
            "a funky bass guitar riff under the break",
            "a distorted synth bass answering the snare",
            "octave pops, then a held low note",
            "the bass riff is sampled from the same record as the break",
            "a simple root-note bass, the break does the talking",
            "wah on the bass for the chorus only",
        ),
        lead=(
            "a shouted hook with no full sentence",
            "a funky guitar chop, two beats long",
            "a brass sample, one stab, panned wide",
            "a siren used as a joke, once",
            "an organ riff, short and bright",
            "a vocal ad-lib chopped to the snare",
        ),
        texture=(
            "the break is compressed until it pumps",
            "a little vinyl on the sample, the rest of the mix clean",
            "a crash and a stop, then the riff",
            "distortion on the snare bus only",
            "party noise, distant, under the intro",
        ),
        mood=(
            "funky and brash", "rowdy and sample-heavy",
            "big and grinning", "energetic and blocky",
        ),
        production=(
            "the break is the loudest thing in the track",
            "it sounds like a party record, not a sound-design piece",
            "samples are obvious and meant to be",
            "the low end is fat and the snare is huge",
        ),
        structure=(
            "a break intro, the bass riff, a stop, the full groove",
            "the same break three ways: filtered, full, then with the vocal",
            "a fake ending, then the break one more time",
        ),
        instruments=(
            "Instruments: Drums, Bass Guitar, Sampler",
            "Instruments: Breaks, Synthesizer, Brass",
            "Instruments: Drums, Electric Guitar, Bass",
        ),
        prose="big beat",
        keywords=(
            "big beat", "funky break", "distorted snare", "bass guitar riff",
            "sample chop", "party", "brass stab", "stop and restart",
        ),
    ),
    "Reggae": Genre(
        tags=("Genre: Reggae", "Genre: Dub"),
        bpm=(72, 90),
        drums=(
            "a one-drop beat, kick and snare together on the three",
            "cross-stick reggae drums, light and patient",
            "a steppers kick on every beat, snare still on the three",
            "rimshot and a quiet kick, lots of air",
            "hi-hats playing the offbeats with the guitar",
            "the drums drop out and leave the bass and skank",
        ),
        bass=(
            "a deep reggae bassline, notes blooming and dying",
            "the bass plays the melody, slow and heavy",
            "a drop-out: silence, then the bass alone",
            "root, fifth, and a slide into the next bar",
            "the bass sits in front of the drums",
            "one bar of bass, one bar of rest",
        ),
        lead=(
            "a guitar skank on the offbeat, short and dry",
            "an organ bubble, repeating a two-note pattern",
            "a melodica taking the tune, spring reverb behind it",
            "horns in unison, a short line, then out",
            "a sung melody with the words left as hums",
            "a lead guitar double-stop, restrained",
        ),
        texture=(
            "spring reverb on the snare and the horns",
            "a delay throw on the last word of a phrase",
            "the mix opens into space when the drums drop",
            "tape echo on the organ, the skank dry",
            "a little hiss, like a dub plate",
        ),
        mood=(
            "heavy and sunlit", "patient and deep",
            "rooted and warm", "dubwise and spare",
        ),
        production=(
            "the bass and the skank are the song",
            "space is part of the rhythm",
            "it sounds like a band, not a loop",
            "echo is used as a musical decision, once, not always",
        ),
        structure=(
            "a bass intro, the one-drop, a horn line, a dub section with drums out",
            "the full band, then bass and skank only, then the horns return",
            "verse feel, a dub break, the same groove",
        ),
        instruments=(
            "Instruments: Bass, Drums, Electric Guitar, Organ",
            "Instruments: Bass, Drums, Melodica, Horns",
            "Instruments: Electric Guitar, Bass, Drums, Organ",
        ),
        prose="roots reggae",
        keywords=(
            "roots reggae", "one drop", "guitar skank", "organ bubble",
            "bass melody", "dub plate", "dub spring", "offbeat chop",
        ),
    ),
    "Soul": Genre(
        tags=("Genre: Soul", "Genre: R&B"),
        bpm=(80, 104),
        drums=(
            "a live kit, snare on two and four, hats swinging",
            "a tight soul groove with ghost notes",
            "brushes for the verse, sticks for the chorus",
            "a simple backbeat, the band playing around it",
            "tambourine with the snare in the hook",
            "the drummer leaves space for the horn hits",
        ),
        bass=(
            "a fingerstyle electric bass, melodic and syncopated",
            "the bass walks between the chord tones",
            "a muted bass line, pockets of silence",
            "octave jumps into the chorus",
            "the bass answers the vocal hum",
            "a warm bass guitar, no slap",
        ),
        lead=(
            "a Wurlitzer riff, bright and percussive",
            "a horn section punch, three notes",
            "a Hammond organ pad under the chords",
            "a hummed lead, close, no lyric",
            "a rhythm guitar chuck on the offbeat",
            "a short sax answer at the end of the phrase",
        ),
        texture=(
            "the horns dry, the organ with a little Leslie",
            "a small room around the kit",
            "handclaps with the chorus snare",
            "the vocal hum doubled softly",
            "tape warmth on the whole band, not a filter effect",
        ),
        mood=(
            "warm and devoted", "joyful and grounded",
            "aching and steady", "sweet and live",
        ),
        production=(
            "it sounds like a rhythm section and a horn section in one room",
            "the pocket is human",
            "the hum is a lead, not a texture buried in reverb",
            "nothing electronic announces itself",
        ),
        structure=(
            "a groove intro, a verse, a horn chorus, a quieter bridge, the chorus",
            "bass and drums, then chords, then horns",
            "the hook is the horn line, repeated, then varied",
        ),
        instruments=(
            "Instruments: Electric Bass, Drums, Wurlitzer, Horns",
            "Instruments: Hammond Organ, Bass, Drums, Saxophone",
            "Instruments: Electric Guitar, Bass, Drums, Horns",
        ),
        prose="classic soul",
        keywords=(
            "classic soul", "Wurlitzer", "horn section", "Hammond",
            "live drums", "fingerstyle bass", "backbeat", "hummed lead",
        ),
    ),
    "Bossa Nova": Genre(
        tags=("Genre: Bossa Nova", "Genre: Jazz"),
        bpm=(116, 136),
        drums=(
            "brushes and a soft rim, the bossa pattern quiet",
            "a clave suggested by the rim, never pounded",
            "shaker and brushes, no backbeat",
            "the percussion is a whisper under the guitar",
            "a light surdo pulse, felt, not hit hard",
            "almost no cymbals",
        ),
        bass=(
            "an upright bass in roots and fifths, syncopated gently",
            "the bass lands with the guitar's thumb, not the beat",
            "half notes, rounded, never slapped",
            "a bass line that moves only when the chord does",
            "the upright drops out for a guitar break",
            "soft, close, no amp grit",
        ),
        lead=(
            "a nylon guitar playing the melody and the rhythm together",
            "a soft flute answering the guitar",
            "piano comping in small, close voicings",
            "a hummed tune, intimate, no words",
            "a single-note guitar line, spare",
            "vibraphone, very quiet, behind the nylon strings",
        ),
        texture=(
            "fingers on nylon strings, audible",
            "a small room, almost dry",
            "the brushes closer than the guitar",
            "no reverb wash; the space is the room",
            "a little air between the notes",
        ),
        mood=(
            "intimate and swaying", "gentle and sunlit",
            "wistful and close", "unhurried and warm",
        ),
        production=(
            "it sounds like three people in a quiet room",
            "the guitar is the rhythm section and the melody",
            "nothing is loud",
            "the time is flexible by a hair and left alone",
        ),
        structure=(
            "guitar states the tune, flute answers, guitar returns",
            "one chorus, a quieter middle, the tune again",
            "no build, only a change of who plays the melody",
        ),
        instruments=(
            "Instruments: Nylon Guitar, Upright Bass, Brushes",
            "Instruments: Nylon Guitar, Flute, Upright Bass",
            "Instruments: Piano, Nylon Guitar, Shaker",
        ),
        prose="bossa nova",
        keywords=(
            "bossa nova", "nylon strings", "clave", "brushes",
            "flute answer", "quiet upright", "intimate", "soft rim",
        ),
    ),
    "Blues": Genre(
        tags=("Genre: Blues",),
        bpm=(70, 110),
        drums=(
            "a slow blues shuffle on the snare",
            "a backbeat with a riding hat, unhurried",
            "brushes in a slow twelve-eight",
            "the kick sparse, the shuffle in the hat",
            "a stop-time hit with the guitar riff",
            "no drums at all, just the guitar's thumb",
        ),
        bass=(
            "an upright bass walking a twelve-bar pattern",
            "electric bass locking to the shuffle",
            "root and flat-seventh, nothing fancy",
            "the bass stops when the guitar does, then comes back",
            "a simple boogie line on the low strings",
            "half-time bass under a vocal hum",
        ),
        lead=(
            "an electric guitar bending into the blue notes",
            "a harmonica riff answering the guitar",
            "a piano playing boogie in the left hand",
            "a sung hum following the twelve-bar changes",
            "a slide guitar phrase, open tuning",
            "a short guitar solo, then back to the riff",
        ),
        texture=(
            "amp grit on the guitar, the rest of the band clean",
            "a small bar room around the kit",
            "the harmonica close and a little distorted",
            "string squeaks on the bends, left in",
            "a little slapback on the vocal hum",
        ),
        mood=(
            "aching and grounded", "gritty and slow",
            "late and unfussy", "blue and physical",
        ),
        production=(
            "it sounds like a bar band, not a production",
            "the guitar tone is the record",
            "the shuffle is human, not a loop",
            "solos are short and give the riff back",
        ),
        structure=(
            "a twelve-bar form, a turnaround, the form again",
            "riff, verse hum, guitar answer, riff",
            "the band stops, the guitar plays alone, the band returns",
        ),
        instruments=(
            "Instruments: Electric Guitar, Harmonica, Bass, Drums",
            "Instruments: Slide Guitar, Upright Bass, Drums",
            "Instruments: Piano, Electric Guitar, Bass, Drums",
        ),
        prose="electric blues",
        keywords=(
            "electric blues", "shuffle", "harmonica", "twelve-bar",
            "blue notes", "slide guitar", "turnaround", "bar band",
        ),
    ),
    "Hip Hop": Genre(
        tags=("Genre: Hip Hop",),
        bpm=(86, 98),
        drums=(
            "a punchy boom-bap kit, snare cracking on the two and four",
            "an MPC pattern, kick and snare, hats swung",
            "a break chopped into a new pocket, not left as the original",
            "the snare is dry and loud, the kick round",
            "a drum fill of kicks into the next loop",
            "hats open for one bar, then closed again",
        ),
        bass=(
            "a sampled bass hit programmed into a riff",
            "an 808 with a short decay, not a trap sustain",
            "the bass follows the kick, then walks for two beats",
            "a bass guitar loop, filtered, under the drums",
            "one bass note stabbing with the kick",
            "the low end drops out for the scratch and returns",
        ),
        lead=(
            "a chopped soul sample, instrumental, no lyric left intact",
            "a scratch phrase used as a hook",
            "a horn stab from a record, two hits",
            "a piano chop, one bar, looped",
            "a vocal ad-lib with the words sliced out",
            "a guitar flick from a sample, rhythmic",
        ),
        texture=(
            "a little dust on the sample, the drums clean and punchy",
            "the scratch in the foreground for one bar",
            "sample chops with audible edit points",
            "the loop filtered for four bars, then opened",
            "no modern sheen; it sounds like a sampler and a mixer",
        ),
        mood=(
            "confident and direct", "gritty and head-nodding",
            "focused and rhythmic", "bold and spare",
        ),
        production=(
            "the drums punch and the sample sits behind them",
            "it is a beat for an MC, even with no MC on it",
            "the pocket is swung, not drunken",
            "edits are part of the style, not hidden",
        ),
        structure=(
            "an intro loop, the drums drop, a scratch break, the loop returns",
            "eight bars, a drum stop, eight bars with the bass",
            "the hook is the sample chop, repeated, then flipped",
        ),
        instruments=(
            "Instruments: Drums, Sampler, Bass",
            "Instruments: Turntables, Drums, Sampler",
            "Instruments: MPC, Bass, Horn Sample",
        ),
        prose="boom bap",
        keywords=(
            "boom bap", "MPC", "soul chop", "scratch",
            "punchy snare", "head nod", "sampler", "drum stop",
        ),
    ),
    "Rock": Genre(
        tags=("Genre: Rock",),
        bpm=(108, 140),
        drums=(
            "a live rock kit, snare on the two and four",
            "a ride cymbal through the verse, crashes in the chorus",
            "the drummer pushes the chorus and lays back in the verse",
            "toms into the chorus, then the backbeat",
            "a simple kick-snare groove, no double kick",
            "sticks, not programmed hats",
        ),
        bass=(
            "an electric bass following the guitar riff",
            "root notes in the verse, a busier line in the chorus",
            "the bass locks to the kick",
            "a picked bass, clean, under distorted guitars",
            "the bass plays the melody of the riff an octave down",
            "whole notes under a held guitar chord",
        ),
        lead=(
            "a jangly electric guitar riff",
            "two guitars, one strumming, one picking a hook",
            "a short guitar solo that states a melody, not a shred",
            "a sung hum doubling the guitar hook",
            "power chords in the chorus, open chords in the verse",
            "a clean guitar intro, distortion arriving with the drums",
        ),
        texture=(
            "a little room on the kit, guitars close",
            "amp crunch, not a wall of gain",
            "the chorus wider than the verse",
            "feedback only as the song ends",
            "a tambourine on the chorus backbeat",
        ),
        mood=(
            "direct and melodic", "driving and plainspoken",
            "bright and band-like", "urgent and tuneful",
        ),
        production=(
            "it sounds like a guitar band in a room",
            "the riff is the hook",
            "vocals, if present, are a hum with the guitars, not a pop topline",
            "the chorus is the same song, louder and wider",
        ),
        structure=(
            "intro riff, verse, chorus, verse, chorus, a short solo, chorus",
            "the riff alone, then the band, then the riff alone again",
            "a bridge that thins to guitar and voice-hum, then the full chorus",
        ),
        instruments=(
            "Instruments: Electric Guitar, Bass, Drums",
            "Instruments: Electric Guitar, Acoustic Guitar, Bass, Drums",
            "Instruments: Guitar, Bass, Drums, Tambourine",
        ),
        prose="indie rock",
        keywords=(
            "indie rock", "guitar riff", "rock kit", "power chords",
            "two and four", "guitar band", "jangly", "chorus lift",
        ),
    ),
    "Classical": Genre(
        tags=("Genre: Classical", "Genre: Chamber"),
        bpm=(60, 96),
        drums=(
            "no percussion, the pulse is the bow",
            "the ensemble keeps time without a drum",
            "silence where a backbeat would be",
            "unmeasured, the phrases breathing instead of a click",
            "a rest is the only rhythm between entries",
            "no kit, no hits, no impacts",
        ),
        bass=(
            "a cello playing the bass line in long bows",
            "the viola's low string as the only bass",
            "a cello pedal, one note, under the violin",
            "pizzicato cello, quiet, marking the harmony",
            "no separate bass, the ensemble's lowest voice",
            "a double bass entering only for the final phrase",
        ),
        lead=(
            "a violin melody, lyrical and unhurried",
            "a piano alone, a short classical phrase",
            "an oboe stating the theme",
            "a string quartet voicing, violin on top",
            "a flute and violin in octaves",
            "the piano accompanying, the cello taking the tune",
        ),
        texture=(
            "a concert-hall distance, not a close mic",
            "bow noise, very quiet, left in",
            "the ensemble breathes together",
            "natural room, no added reverb tail",
            "dynamics from piano to mezzo-forte, never a hit",
        ),
        mood=(
            "lyrical and restrained", "tender and formal",
            "clear and serious", "quiet and composed",
        ),
        production=(
            "it sounds like a small ensemble in a hall",
            "no impacts, no risers, no kit",
            "the melody is sung by an instrument",
            "balance is acoustic, not mixed for loudness",
        ),
        structure=(
            "a phrase, an answer, a short development, the phrase again",
            "piano alone, then the quartet, then piano alone",
            "one movement's worth of an idea, and a cadence",
        ),
        instruments=(
            "Instruments: Violin, Viola, Cello, Piano",
            "Instruments: Oboe, Strings",
            "Instruments: Piano, Cello",
        ),
        prose="chamber music",
        keywords=(
            "chamber music", "string quartet", "violin melody", "cello",
            "oboe", "unmeasured", "concert hall", "lyrical",
        ),
    ),
}


# Menu order. Definitions above can grow in place; this is the order a person sees.
_GENRE_ORDER = (
    "Drum & Bass - Liquid",
    "Drum & Bass - Neurofunk",
    "Drum & Bass - Dancefloor",
    "Drum & Bass - Jungle",
    "Drum & Bass - Halftime",
    "Drum & Bass - Jump-up",
    "Techno - Hypnotic",
    "Techno - Industrial",
    "Techno - Melodic",
    "House - Deep",
    "House - Classic",
    "House - Tech",
    "House - Acid",
    "Dubstep - Deep",
    "Dubstep - Brostep",
    "Glitch Hop",
    "Breakbeat",
    "Ambient",
    "Cinematic / Trailer",
    "Lo-fi Hip Hop",
    "Hip Hop",
    "Synthwave",
    "Trance",
    "UK Garage",
    "Future Garage",
    "Post-Dubstep",
    "Psydub",
    "Reggae",
    "Trip Hop",
    "Dub Techno",
    "Downtempo",
    "Chillwave",
    "IDM",
    "Funk",
    "Soul",
    "Jazz",
    "Bossa Nova",
    "Blues",
    "Rock",
    "Metal",
    "Folk / Acoustic",
    "Classical",
    "Minimal Electronic",
    "Corporate / Uplifting",
)


def genre_names() -> list[str]:
    missing = set(GENRES) - set(_GENRE_ORDER)
    extra = set(_GENRE_ORDER) - set(GENRES)
    if missing or extra or len(_GENRE_ORDER) != len(set(_GENRE_ORDER)):
        raise RuntimeError(
            f"genre menu is out of date (missing {sorted(missing)}, extra {sorted(extra)})"
        )
    return list(_GENRE_ORDER)


# Words that never earn a place in a generated track title. Prompt tags and
# production jargon are noise; the label should read like a short name.
_TITLE_STOP = frozenset({
    "a", "an", "the", "and", "or", "of", "to", "in", "with", "for", "on", "at",
    "by", "from", "as", "is", "are", "be", "this", "that", "its", "into", "over",
    "under", "only", "no", "not", "bpm", "track", "tracks", "instrumental",
    "music", "genre", "mood", "arrangement", "structure", "instruments",
    "production", "tracktype", "vocaltype", "global", "metadata", "seconds",
    "bars", "then", "sits", "under", "wordless", "vocal", "texture", "vocals",
})


def track_title(prompt: str, genre: str | None = None, seed: int = 0) -> str:
    """A short two-to-four word label. Deterministic for the same inputs.

    The title is a filing name, not a creative act: the same prompt, genre and
    seed always produce the same string so a re-render does not rename the track.
    """
    rng = random.Random(f"{int(seed)}\0{genre or ''}\0{prompt}")
    candidates: list[str] = []
    seen: set[str] = set()

    def _consider(raw: str) -> None:
        lower = raw.lower()
        if lower in _TITLE_STOP or len(lower) < 3 or lower in seen:
            return
        seen.add(lower)
        candidates.append(raw)

    if genre:
        for part in re.findall(r"[A-Za-z][A-Za-z'-]*", genre):
            _consider(part)
    for part in re.findall(r"[A-Za-z][A-Za-z'-]*", prompt or ""):
        _consider(part)

    if not candidates:
        return "Untitled Track"

    count = rng.randint(2, min(4, max(2, len(candidates))))
    count = min(count, len(candidates))
    picked = rng.sample(candidates, count)
    order = {word.lower(): index for index, word in enumerate(candidates)}
    picked.sort(key=lambda word: order[word.lower()])
    return " ".join(_upper_first(word) for word in picked)


# Offered in the UI as menus. Empty means "let the genre decide", so a selection
# pins one axis while Regenerate keeps varying the rest.
RANDOM_CHOICE = "(let the genre decide)"

# A structure is laid out in bars, because that is how music is counted, and reaches
# the model in seconds, because that is all it understands. Nothing here makes the
# model obey the plan: Stable Audio has no structural input, so this is a described
# arrangement, not a guarantee. The only hard guarantee is reworking a span after the
# fact, which is what the Rework tab does.
SECTION_NAMES = ("Intro", "Build", "Drop", "Breakdown", "Second drop", "Outro")
BEATS_PER_BAR = 4


def plan_sections(bpm: float, bars: dict[str, float]) -> list[dict]:
    """Turn a bar count per section into a timeline in seconds.

    Sections with no bars are dropped, so an arrangement is built by filling in only
    the parts you want.
    """
    if not bpm or bpm <= 0:
        raise ValueError(f"tempo must be positive (got {bpm!r})")
    bar_seconds = BEATS_PER_BAR * 60.0 / float(bpm)
    plan, cursor = [], 0.0
    for name in SECTION_NAMES:
        count = float(bars.get(name) or 0)
        if count <= 0:
            continue
        length = count * bar_seconds
        plan.append({
            "name": name,
            "bars": count,
            "start": round(cursor, 2),
            "end": round(cursor + length, 2),
        })
        cursor += length
    return plan


def structure_total(plan: list[dict]) -> float:
    return round(plan[-1]["end"], 2) if plan else 0.0


def describe_structure(plan: list[dict]) -> str:
    """One sentence naming each section and when it lands, for the prompt."""
    if not plan:
        return ""
    parts = []
    for section in plan:
        parts.append(
            f"{section['name'].lower()} for {section['bars']:g} bars "
            f"({section['start']:.0f}s to {section['end']:.0f}s)"
        )
    return "arranged as " + ", then ".join(parts)


def character_options() -> list[str]:
    """Everything selectable on the character axis, for a UI multiselect."""
    return [option for option in (*SPACE, *EFFECTS, *ERA) if option]


def mood_options(genre_name: str | None = None) -> list[str]:
    if genre_name and genre_name in GENRES:
        return list(GENRES[genre_name].mood)
    moods: list[str] = []
    for genre in GENRES.values():
        moods.extend(genre.mood)
    return sorted(set(moods))


def instrument_options(genre_name: str | None = None) -> list[str]:
    """Instrument names, split out of the AudioSparx `Instruments:` tag."""
    names: set[str] = set()
    pool = (
        [GENRES[genre_name]] if genre_name and genre_name in GENRES
        else list(GENRES.values())
    )
    for genre in pool:
        for tag in genre.instruments:
            names.update(
                part.strip() for part in tag.removeprefix("Instruments:").split(",")
            )
    return sorted(name for name in names if name)


def build_prompt(
    genre_name: str,
    *,
    style: str = "description",
    bpm: int | None = None,
    seed: int | None = None,
    extra: str = "",
    mood: str | None = None,
    instruments: tuple[str, ...] = (),
    character: tuple[str, ...] = (),
    vocals: bool = False,
    structure: str = "",
) -> str:
    """Compose one prompt variation for `genre_name` in the backend's own style.

    Passing a different `seed` (or none) gives a different variation, which is what
    the UI's Regenerate button does. `bpm` overrides the genre's typical tempo.
    `style` is a backend's `prompt_style`: tags, caption or description. Asking the
    wrong style of a model degrades its output, so the UI passes the selected
    backend's own value rather than assuming one.
    """
    try:
        genre = GENRES[genre_name]
    except KeyError:
        raise ValueError(f"unknown genre {genre_name!r}") from None

    rng = random.Random(seed)
    tempo = bpm if bpm is not None else rng.randint(*genre.bpm)
    prose = genre.prose or genre_name.lower()
    if not mood or mood == RANDOM_CHOICE:
        mood = rng.choice(genre.mood)
    chosen_instruments = (
        f"Instruments: {', '.join(instruments)}" if instruments else None
    )
    voice_tag = "VocalType: Instrumental" if not vocals else None
    voice_words = "" if not vocals else "with a wordless vocal texture over the top"
    drums, bass, lead = (rng.choice(p) for p in (genre.drums, genre.bass, genre.lead))

    if style == "tags":
        picked = rng.sample(genre.keywords, min(4, len(genre.keywords)))
        parts = [prose, *picked, f"{tempo}bpm", mood]
        parts.extend(instrument.lower() for instrument in instruments)
        parts.extend(character)
        parts.append("with vocals" if vocals else "instrumental")
        if extra.strip():
            parts.append(extra.strip().rstrip("."))
        return ", ".join(parts)

    if style == "caption":
        arrangement = f"{drums}, {bass}, and {lead}"
        caption = (
            f"Global Metadata: Genre: {prose}. BPM: {tempo}. Mood: {mood}. "
            f"Arrangement: {arrangement}. {_upper_first(rng.choice(genre.texture))}."
        )
        if instruments:
            caption += f" Instruments: {', '.join(instruments)}."
        if character:
            caption += f" Production: {', '.join(character)}."
        chosen_structure = structure or (
            rng.choice(genre.structure) if genre.structure else ""
        )
        if chosen_structure:
            caption += f" Structure: {chosen_structure}."
        if extra.strip():
            caption += f" {extra.strip().rstrip('.')}."
        return caption + (
            " Vocals: wordless vocal texture." if vocals
            else " Instrumental only, no vocals."
        )

    if style != "description":
        raise ValueError(f"unknown prompt style {style!r}")

    # Stability's own examples are tags plus comma-separated fragments, not
    # grammatical sentences ("TrackType: Instrument, a sombre solo acoustic guitar
    # track with cavernous reverb"). Varying the shape, which elements appear and
    # their order is what stops every prompt reading the same.
    tags = ["TrackType: Music"]
    if voice_tag:
        tags.append(voice_tag)
    tags.extend(genre.tags)
    if not chosen_instruments and genre.instruments:
        chosen_instruments = rng.choice(genre.instruments)
    tags.append(chosen_instruments or "")
    tags = [tag for tag in tags if tag]
    core_phrases = [drums, bass, lead]
    rng.shuffle(core_phrases)

    if character:
        colour = [rng.choice(genre.texture), *character]
    else:
        pool = list(dict.fromkeys(genre.texture))
        rng.shuffle(pool)
        colour = pool[: rng.randint(1, min(2, len(pool)))]
    if voice_words:
        colour.append(voice_words)

    kind = "track" if vocals else "instrumental"
    # The article must agree with whatever word actually follows it, which is the
    # mood, not the genre.
    opening = f"{_upper_first(_article(mood))} {mood} {prose} {kind} at {tempo} BPM"

    if rng.random() < 0.5:
        # Fragment form, closest to Stability's own examples.
        parts = [opening, *core_phrases, *colour]
        if structure:
            parts.append(structure)
        elif genre.structure and rng.random() < 0.7:
            parts.append(rng.choice(genre.structure))
        if rng.random() < 0.6:
            parts.append(rng.choice(genre.production))
        if extra.strip():
            parts.append(extra.strip().rstrip("."))
        return ", ".join(tags) + ". " + ", ".join(parts) + "."

    # Each line is already a clause. Joining them with "sits under" / "with"
    # produced lines like "a stab sits under the bass drops out, with the break
    # is basic", which the model cannot use.
    sentences = [f"{opening}."]
    sentences.extend(
        f"{_upper_first(phrase).rstrip('.')}." for phrase in core_phrases
    )
    colour_line = _upper_first(colour[0]).rstrip(".")
    if len(colour) > 1:
        colour_line += ", " + ", ".join(part.rstrip(".") for part in colour[1:])
    sentences.append(colour_line + ".")
    if structure:
        sentences.append(f"Structurally, {structure}.")
    elif genre.structure and rng.random() < 0.7:
        sentences.append(f"Structurally, {rng.choice(genre.structure)}.")
    if rng.random() < 0.6:
        sentences.append(_upper_first(rng.choice(genre.production)) + ".")
    if extra.strip():
        sentences.append(extra.strip().rstrip(".") + ".")
    return ", ".join(tags) + ". " + " ".join(sentences)
