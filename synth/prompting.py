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
from dataclasses import dataclass, field

# Tags Stability names explicitly as raising quality and coherence for music.
MUSIC_PREAMBLE = "TrackType: Music, VocalType: Instrumental"


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


# Spelling alone gets these wrong: "UK" reads "you-kay", so it takes "a".
_CONSONANT_SOUNDING = ("uk", "uni", "euro", "eu", "one", "use")


def _article(word: str) -> str:
    lowered = word.lower()
    if lowered.startswith(_CONSONANT_SOUNDING):
        return "a"
    return "an" if lowered[:1] in "aeiou" else "a"


GENRES: dict[str, Genre] = {
    "Drum & Bass": Genre(
        tags=("Genre: Drum and Bass",),
        bpm=(172, 176),
        drums=(
            "a chopped Amen break with a snappy, tightly tuned snare",
            "crisp two-step drums with ghost notes between the kick and snare",
            "a rolling breakbeat with shuffled hats and a cracking rimshot",
        ),
        bass=(
            "a snarling Reese bass detuned into a wide, moving growl",
            "a deep rolling sub bass that slides between notes",
            "a neurofunk bass full of metallic formant sweeps",
        ),
        lead=(
            "lush Rhodes chords floating over the break",
            "a soaring detuned pad lead that opens across the drop",
            "clipped vocal-textured stabs answering the drums",
        ),
        texture=(
            "reversed cymbal risers and vinyl noise stitch the sections together",
            "filtered atmospherics and distant rain sit under the groove",
            "granular pad smears drift across the stereo field",
        ),
        mood=("rolling and hypnotic", "dark and driving", "warm, liquid and euphoric"),
        production=(
            "the mix is punchy and club-ready with a tight low end",
            "the production is clean and modern with heavy sub weight",
        ),
        structure=(
            "a filtered intro rolls for thirty-two bars before the first drop, a "
            "stripped breakdown lands halfway, and the second drop is the heaviest",
            "a DJ-friendly beatless intro leads into a sixteen-bar build, a long "
            "rolling drop, then a breakdown and a final drop",
        ),
        instruments=("Instruments: Bass, Drums, Synthesizer, Electric Piano",),
        prose="drum and bass",
        keywords=("amen break", "reese bass", "rolling sub bass", "breakbeat", "jungle drums", "rhodes chords"),
    ),
    "Techno": Genre(
        tags=("Genre: Techno",),
        bpm=(128, 138),
        drums=(
            "a relentless four-to-the-floor kick with tight closed hats",
            "a driving kick under syncopated rides and a clapping offbeat",
        ),
        bass=(
            "a hypnotic rolling bassline locked to the kick",
            "a distorted acid bass that squelches through a resonant filter",
        ),
        lead=(
            "a hypnotic arpeggio slowly opening its filter",
            "stabbing detuned chords repeating with small variations",
        ),
        texture=(
            "industrial metallic noise and long reverb tails fill the space",
            "dubby delay throws and tape hiss add depth",
        ),
        mood=("dark and relentless", "hypnotic and mechanical", "raw and physical"),
        production=(
            "the mix is loud, compressed and built for a big room",
            "the production is raw and analogue with saturated drums",
        ),
        structure=(
            "a long tool-like intro, a gradual sixteen-bar build, a stripped "
            "breakdown and a driving final section",
        ),
        instruments=("Instruments: Drums, Bass, Synthesizer",),
        prose="techno",
        keywords=("four to the floor", "acid bass", "hypnotic arpeggio", "industrial noise", "warehouse reverb"),
    ),
    "House": Genre(
        tags=("Genre: House",),
        bpm=(120, 126),
        drums=(
            "a warm four-to-the-floor kick with shuffled hats and a crisp clap",
            "a swinging drum groove with live-feeling percussion",
        ),
        bass=(
            "a bouncing filtered bassline",
            "a round, syncopated 808-style bass",
        ),
        lead=(
            "a gospel-flavoured piano riff",
            "warm Rhodes chords with a soulful lift",
            "a plucked synth motif answering the groove",
        ),
        texture=(
            "vinyl crackle and soft room reverb warm the whole track",
            "airy pads and shaker layers widen the groove",
        ),
        mood=("uplifting and euphoric", "warm and soulful", "late-night and groovy"),
        production=(
            "the production is warm and analogue with gentle tape saturation",
            "the mix is bright, punchy and club-ready",
        ),
        structure=(
            "a DJ-friendly drum intro, a building sixteen bars, a euphoric drop "
            "and a stripped outro",
        ),
        instruments=("Instruments: Piano, Bass, Drums, Synthesizer",),
        prose="house",
        keywords=("four on the floor", "gospel piano", "filtered bassline", "shuffled hats", "soulful chords"),
    ),
    "Dubstep": Genre(
        tags=("Genre: Dubstep",),
        bpm=(140, 145),
        drums=(
            "a half-time drum pattern with a huge snare on the third beat",
            "sparse, heavy drums with rattling trap-style hats",
        ),
        bass=(
            "a growling wobble bass modulated by an LFO",
            "a screaming talking bass full of formant movement",
        ),
        lead=(
            "a detuned supersaw lead cutting through the drop",
            "an ominous minor pad motif before the drop",
        ),
        texture=(
            "impacts, risers and downlifters mark every transition",
            "granular noise and sub drops thicken the low end",
        ),
        mood=("aggressive and heavy", "dark and menacing", "explosive"),
        production=("the mix is huge, distorted and sub-heavy",),
        structure=(
            "a tense build, a hard drop at the halfway point, then a second, "
            "heavier drop",
        ),
        instruments=("Instruments: Bass, Drums, Synthesizer",),
        prose="dubstep",
        keywords=("wobble bass", "half-time drums", "huge snare", "supersaw lead", "sub drop"),
    ),
    "Ambient": Genre(
        tags=("Genre: Ambient",),
        bpm=(60, 80),
        drums=("no drums at all", "only the faintest pulse of soft percussion"),
        bass=("a slow sub drone underpinning everything", "no bass beyond a low hum"),
        lead=(
            "sparse piano notes left to ring out",
            "a slow evolving pad that never quite resolves",
            "a distant bowed string sustaining across the piece",
        ),
        texture=(
            "tape hiss, field recordings and long reverb tails",
            "granular clouds drifting slowly across the stereo image",
        ),
        mood=("gentle and unobtrusive", "melancholic and spacious", "calm and weightless"),
        production=("the recording is soft, wide and deeply reverberant",),
        structure=("it evolves slowly and continuously with no clear sections",),
        instruments=("Instruments: Synthesizer, Piano, Strings",),
        prose="ambient",
        keywords=("evolving pads", "sparse piano", "long reverb", "no drums", "tape hiss", "drone"),
    ),
    "Cinematic / Trailer": Genre(
        tags=("Genre: Soundtrack", "Genre: Orchestral"),
        bpm=(80, 110),
        drums=(
            "a frame drum on a slow four-bar cycle",
            "taiko hits and braams punctuating the build",
        ),
        bass=("a low cello ostinato carrying the pulse", "a sub-heavy orchestral drone"),
        lead=(
            "distant horn swells rising over the strings",
            "a solo violin line above a bed of tremolo strings",
        ),
        texture=("choral pads and metallic risers", "granular string textures and air"),
        mood=("serious and restrained, building subtly", "epic and triumphant", "ominous"),
        production=("recorded in a large scoring stage with deep natural reverb",),
        structure=(
            "it begins sparse and restrained, builds steadily through the middle "
            "and resolves into a full, powerful final section",
        ),
        instruments=("Instruments: Strings, Brass, Percussion, Choir",),
        prose="cinematic trailer",
        keywords=("orchestral", "taiko drums", "cello ostinato", "horn swells", "choir", "epic build"),
    ),
    "Lo-fi Hip Hop": Genre(
        tags=("Genre: Hip Hop", "Genre: Chillout"),
        bpm=(80, 92),
        drums=(
            "loose, dusty drums swung slightly off the grid",
            "mellow boom-bap drums with a soft rimshot",
        ),
        bass=("a round upright bass walking gently", "a soft sine sub bass"),
        lead=("a warm Rhodes piano chord progression", "a muted jazz guitar motif"),
        texture=("vinyl crackle, tape wow and distant street noise",),
        mood=("relaxed and nostalgic", "sleepy and warm"),
        production=("the whole thing is filtered, saturated and slightly lo-fi",),
        structure=("it loops gently with small variations rather than big sections",),
        instruments=("Instruments: Electric Piano, Bass, Drums, Guitar",),
        prose="lo-fi hip hop",
        keywords=("warm rhodes piano", "vinyl crackle", "boom bap drums", "upright bass", "dusty swing"),
    ),
    "Synthwave": Genre(
        tags=("Genre: Synthwave", "Genre: Electronic"),
        bpm=(100, 118),
        drums=("gated reverb snares and a punchy electronic kick",),
        bass=("a driving arpeggiated synth bass", "a fat analogue bass pulse"),
        lead=("a soaring analogue lead with heavy chorus", "bright neon arpeggios"),
        texture=("shimmering pads and tape delay throws",),
        mood=("nostalgic and neon-lit", "moody and cinematic", "driving and retro"),
        production=("the production is glossy eighties with heavy chorus and reverb",),
        structure=("a synth intro, a driving main section and a soaring final chorus",),
        instruments=("Instruments: Synthesizer, Drums, Bass",),
        prose="synthwave",
        keywords=("analogue synths", "gated reverb snare", "arpeggiated bass", "neon pads", "chorus lead"),
    ),
    "Trance": Genre(
        tags=("Genre: Trance",),
        bpm=(136, 142),
        drums=("a punchy four-to-the-floor kick with rolling offbeat hats",),
        bass=("an offbeat rolling bassline locked under the kick",),
        lead=("a euphoric supersaw lead", "a rapid plucked arpeggio climbing in octaves"),
        texture=("huge white-noise risers and long reverb sweeps",),
        mood=("euphoric and uplifting", "emotional and widescreen"),
        production=("the mix is wide, bright and enormous",),
        structure=(
            "a long build, a full beatless breakdown in the middle, then the main "
            "euphoric drop",
        ),
        instruments=("Instruments: Synthesizer, Drums, Bass",),
        prose="trance",
        keywords=("supersaw lead", "offbeat bassline", "white noise riser", "euphoric breakdown"),
    ),
    "UK Garage": Genre(
        tags=("Genre: Garage", "Genre: Electronic"),
        bpm=(130, 136),
        drums=("a shuffled two-step beat with skippy hats and a sharp snare",),
        bass=("a bouncing organ bass", "a deep sub bass with a quick glide"),
        lead=("chopped vocal-textured stabs", "warm organ chords"),
        texture=("crisp shakers, vinyl noise and short delay throws",),
        mood=("bouncy and playful", "smooth and late-night"),
        production=("the mix is snappy and swung with a tight low end",),
        structure=("a drum intro, a bouncing main groove and a stripped-back break",),
        instruments=("Instruments: Bass, Drums, Organ, Synthesizer",),
        prose="UK garage",
        keywords=("two-step beat", "skippy hats", "organ bass", "chopped vocal stabs", "swing"),
    ),
    "Funk": Genre(
        tags=("Genre: Funk",),
        bpm=(96, 112),
        drums=("tight drums full of swing and old-school flavour",),
        bass=("a slapped electric bass locking hard with the kick",),
        lead=("a clipped rhythm guitar with wah", "a close-mic'd clavinet riff"),
        texture=("horn stabs and tambourine lift the chorus",),
        mood=("playful and confident", "gritty and energetic"),
        production=("warm and textured, the sound of analogue gear and tape",),
        structure=("a tight groove with a breakdown and a punchy return",),
        instruments=("Instruments: Guitar, Bass, Drums, Brass, Clavinet",),
        prose="funk",
        keywords=("slap bass", "wah guitar", "clavinet", "horn stabs", "tight drums"),
    ),
    "Jazz": Genre(
        tags=("Genre: Jazz",),
        bpm=(90, 130),
        drums=("brushed drums riding gently on the snare",),
        bass=("a walking upright bass",),
        lead=("a warm trumpet melody", "a relaxed piano solo over comping chords"),
        texture=("the natural room sound of a small club",),
        mood=("smoky and late-night", "bright and swinging"),
        production=("live-recorded and close-mic'd with natural room tone",),
        structure=("a head, solos over the changes, and a return to the head",),
        instruments=("Instruments: Piano, Double Bass, Drums, Trumpet, Saxophone",),
        prose="jazz",
        keywords=("brushed drums", "walking upright bass", "trumpet melody", "piano comping", "club ambience"),
    ),
    "Minimal Electronic": Genre(
        tags=("Genre: Electronic",),
        bpm=(95, 115),
        drums=("light, precise percussion with a soft kick",),
        bass=("a clean, restrained sub bass",),
        lead=("a clean plucky synth arpeggio", "a simple bell-like motif"),
        texture=("subtle noise sweeps and soft granular detail",),
        mood=("curious and modern", "calm and focused", "optimistic"),
        production=("the mix is clean, dry and uncluttered",),
        structure=("it builds gradually by adding one element at a time",),
        instruments=("Instruments: Synthesizer, Drums",),
        prose="minimal electronic",
        keywords=("plucky arpeggio", "clean sub bass", "light percussion", "bell motif"),
    ),
    "Corporate / Uplifting": Genre(
        tags=("Genre: Corporate", "Genre: Pop"),
        bpm=(105, 120),
        drums=("a steady four-on-the-floor beat with handclaps",),
        bass=("a simple, supportive electric bass",),
        lead=("bright piano chords", "a plucked synth motif with subtle strings"),
        texture=("light bell accents and airy pads",),
        mood=("uplifting and optimistic", "confident and forward-moving"),
        production=("the mix is bright, clean and polished",),
        structure=("it builds steadily and resolves on a confident final section",),
        instruments=("Instruments: Piano, Strings, Bass, Drums",),
        prose="uplifting corporate",
        keywords=("bright piano", "subtle strings", "handclaps", "steady beat", "optimistic"),
    ),
    "Metal": Genre(
        tags=("Genre: Metal", "Genre: Rock"),
        bpm=(140, 180),
        drums=("double-kick drums with crashing cymbals",),
        bass=("a distorted bass doubling the guitar riff",),
        lead=("a heavy palm-muted guitar riff", "a shredding lead guitar line"),
        texture=("feedback and room ambience between phrases",),
        mood=("aggressive and relentless", "dark and heavy"),
        production=("the guitars are tight and heavily distorted, the mix aggressive",),
        structure=("a riff-driven verse, a heavier chorus and a breakdown",),
        instruments=("Instruments: Electric Guitar, Bass, Drums",),
        prose="metal",
        keywords=("palm muted guitar", "double kick", "distorted bass", "shredding lead"),
    ),
    "Folk / Acoustic": Genre(
        tags=("Genre: Folk", "Genre: Acoustic"),
        bpm=(85, 115),
        drums=("light brushed percussion and a stomping foot",),
        bass=("a gentle upright bass",),
        lead=("delicately finger-picked acoustic guitar", "a fiddle playing a simple air"),
        texture=("the natural creak and air of a close-mic'd wooden room",),
        mood=("warm and intimate", "wistful and pastoral"),
        production=("live-recorded and close-mic'd with a natural, unprocessed sound",),
        structure=("a simple verse and chorus shape with a quiet middle section",),
        instruments=("Instruments: Acoustic Guitar, Violin, Double Bass",),
        prose="acoustic folk",
        keywords=("finger picked acoustic guitar", "fiddle", "upright bass", "brushed percussion"),
    ),
}


def genre_names() -> list[str]:
    return list(GENRES)


def build_prompt(
    genre_name: str,
    *,
    style: str = "description",
    bpm: int | None = None,
    seed: int | None = None,
    extra: str = "",
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
    mood = rng.choice(genre.mood)
    drums, bass, lead = (rng.choice(p) for p in (genre.drums, genre.bass, genre.lead))

    if style == "tags":
        picked = rng.sample(genre.keywords, min(4, len(genre.keywords)))
        parts = [prose, *picked, f"{tempo}bpm", mood, "instrumental"]
        if extra.strip():
            parts.append(extra.strip().rstrip("."))
        return ", ".join(parts)

    if style == "caption":
        arrangement = f"{drums}, {bass}, and {lead}"
        caption = (
            f"Global Metadata: Genre: {prose}. BPM: {tempo}. Mood: {mood}. "
            f"Arrangement: {arrangement}. {rng.choice(genre.texture).capitalize()}."
        )
        if genre.structure:
            caption += f" Structure: {rng.choice(genre.structure)}."
        if extra.strip():
            caption += f" {extra.strip().rstrip('.')}."
        return caption + " Instrumental only, no vocals."

    if style != "description":
        raise ValueError(f"unknown prompt style {style!r}")

    tags = [MUSIC_PREAMBLE, *genre.tags, *genre.instruments]
    sentences = [
        f"{_article(prose).capitalize()} {prose} instrumental at {tempo} BPM, "
        f"{mood}.",
        f"It is built on {drums} and {bass}, with {lead}.",
        f"{rng.choice(genre.texture).capitalize()}.",
    ]
    if genre.structure:
        sentences.append(f"Structurally, {rng.choice(genre.structure)}.")
    sentences.append(f"{rng.choice(genre.production).capitalize()}.")
    if extra.strip():
        sentences.append(extra.strip().rstrip(".") + ".")

    return ", ".join(tags) + ". " + " ".join(sentences)
