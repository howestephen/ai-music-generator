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

# Stability names technique, recording environment and effects as descriptors that
# are in the training data, so these apply across genres and multiply the number of
# distinct prompts far faster than adding genre-specific lines would.
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
        ),
        bass=(
            "a deep rolling sub bass that slides between notes",
            "a warm, filtered bassline that breathes with the pads",
            "a round sub that sits under everything without crowding it",
        ),
        lead=(
            "lush Rhodes chords floating over the break",
            "a soulful piano motif answering the drums",
            "a wordless vocal texture drifting above the groove",
            "a soft saxophone line weaving through the mix",
        ),
        texture=(
            "filtered atmospherics and distant rain sit under the groove",
            "warm pad swells fill the space between phrases",
            "reversed cymbals and soft vinyl noise stitch the sections",
        ),
        mood=("warm, liquid and euphoric", "reflective and spacious", "late-night and smooth"),
        production=(
            "the mix is clean and deep with a wide, warm low end",
            "the production is polished and unhurried",
        ),
        structure=(
            "a beatless intro opens into a rolling first drop, a softer breakdown "
            "lands halfway, and the last drop is the fullest",
        ),
        instruments=("Instruments: Bass, Drums, Electric Piano, Synthesizer",),
        prose="liquid drum and bass",
        keywords=("liquid dnb", "rolling sub bass", "rhodes chords", "soulful",
                  "atmospheric pads", "smooth breakbeat"),
    ),
    "Drum & Bass - Neurofunk": Genre(
        tags=("Genre: Drum and Bass",),
        bpm=(172, 176),
        drums=(
            "surgical, heavily processed drums with a cracking snare",
            "tight technical breaks with metallic percussion fills",
            "a clipped, machine-precise beat with rattling ghost hits",
        ),
        bass=(
            "a neurofunk bass full of metallic formant sweeps",
            "a snarling Reese detuned into a wide, moving growl",
            "a modulating bass that morphs between notes like machinery",
            "a distorted, talking bass that bends through a resonant filter",
        ),
        lead=(
            "sparse, dissonant stabs cutting between the bass",
            "a cold synth motif buried under the low end",
            "sci-fi sweeps and alarms punctuating the drop",
        ),
        texture=(
            "industrial metallic noise and mechanical clanks",
            "granular glitches scattered across the stereo field",
            "dark ambient drones underneath the drums",
        ),
        mood=("dark and technical", "aggressive and precise", "menacing and clinical"),
        production=(
            "the mix is surgical, loud and heavily compressed",
            "the production is cold, sharp and sub-heavy",
        ),
        structure=(
            "a tense sound-design intro, a sharp first drop, a brief mechanical "
            "breakdown, then a heavier second drop",
        ),
        instruments=("Instruments: Bass, Drums, Synthesizer",),
        prose="neurofunk drum and bass",
        keywords=("neurofunk", "reese bass", "formant sweeps", "technical drums",
                  "dark sci-fi", "distorted bass"),
    ),
    "Drum & Bass - Dancefloor": Genre(
        tags=("Genre: Drum and Bass",),
        bpm=(172, 176),
        drums=(
            "a punchy, wide-open beat built for a festival system",
            "a driving break with a huge, bright snare",
            "simple, powerful drums with big crash accents",
        ),
        bass=(
            "a clean, enormous sub that hits like a wall",
            "a bright, bouncing bass hook you can hum",
            "a punchy mid-range bass riff carrying the drop",
        ),
        lead=(
            "a soaring supersaw hook that opens the drop",
            "an anthemic synth melody built for a crowd",
            "a big euphoric chord progression rising into the drop",
            "a bright plucked topline with a memorable hook",
        ),
        texture=(
            "huge white-noise risers and impacts at every transition",
            "stadium reverb and crowd-sized delays",
            "shimmering high pads lifting the chorus",
        ),
        mood=("euphoric and enormous", "bright and anthemic", "uplifting and driving"),
        production=(
            "the mix is glossy, loud and festival-ready",
            "the production is polished and radio-bright",
        ),
        structure=(
            "an intro hook, a long build with a filter sweep, an anthemic first "
            "drop, a melodic breakdown, then the biggest drop last",
        ),
        instruments=("Instruments: Bass, Drums, Synthesizer, Piano",),
        prose="dancefloor drum and bass",
        keywords=("dancefloor dnb", "supersaw hook", "anthemic", "festival",
                  "big sub bass", "euphoric drop"),
    ),
    "Drum & Bass - Jungle": Genre(
        tags=("Genre: Drum and Bass", "Genre: Jungle"),
        bpm=(160, 174),
        drums=(
            "a chopped Amen break, edited hard and fast",
            "layered breakbeats cut into stuttering fills",
            "a raw, time-stretched break with vinyl grit",
        ),
        bass=(
            "a deep dub sub bass rolling underneath",
            "a heavy, warm sub with a long decay",
            "an 808-style bass sliding between low notes",
        ),
        lead=(
            "ragga vocal chops stabbing through the break",
            "a dub siren wailing over the drums",
            "a minor key stab pattern echoing off the beat",
        ),
        texture=(
            "tape hiss, vinyl crackle and dub delay throws",
            "distant rave sirens and reversed noise",
        ),
        mood=("raw and rolling", "dark and hypnotic", "energetic and rugged"),
        production=(
            "the production is raw, sampled and unpolished, straight off vinyl",
        ),
        structure=(
            "a dub intro, an extended break-driven roll, a stripped bass-only "
            "section, then the full break returns",
        ),
        instruments=("Instruments: Bass, Drums, Synthesizer",),
        prose="jungle",
        keywords=("jungle", "amen break", "ragga chops", "dub sub bass",
                  "time-stretched breaks", "vinyl grit"),
    ),
    "Drum & Bass - Halftime": Genre(
        tags=("Genre: Drum and Bass",),
        bpm=(168, 174),
        drums=(
            "sparse halftime drums with a heavy, delayed snare",
            "a slow, weighty beat under fast hi-hat detail",
            "a broken, off-grid pattern with lots of space",
        ),
        bass=(
            "a slow, enormous sub that swells and decays",
            "a textured bass drone shifting under the beat",
            "a granular bass that rumbles rather than plays notes",
        ),
        lead=(
            "a distant, detuned melodic fragment",
            "cold bell tones scattered over the beat",
            "a processed vocal shard repeating in the space",
        ),
        texture=(
            "wide ambient pads and field recordings",
            "granular clouds and reversed reverb tails",
        ),
        mood=("dark and cavernous", "brooding and spacious", "cinematic and heavy"),
        production=(
            "the mix is deep and wide with enormous low-end weight",
        ),
        structure=(
            "an ambient opening, the halftime beat entering low, a long textural "
            "middle, then a heavier final section",
        ),
        instruments=("Instruments: Bass, Drums, Synthesizer",),
        prose="halftime drum and bass",
        keywords=("halftime dnb", "sparse drums", "sub weight", "granular textures",
                  "cinematic", "broken beat"),
    ),
    "Techno - Hypnotic": Genre(
        tags=("Genre: Techno", "Genre: Minimal"),
        bpm=(128, 134),
        drums=("a relentless four-to-the-floor kick with tight closed hats",
               "a locked groove with a dry rimshot and shaker",
               "a stripped beat with an offbeat open hat"),
        bass=("a hypnotic rolling bassline locked to the kick",
              "a single low pulse repeating without variation",
              "a filtered sub that opens across several minutes"),
        lead=("a hypnotic arpeggio slowly opening its filter",
              "one stabbing chord repeating with tiny variations",
              "a modulating drone that shifts almost imperceptibly"),
        texture=("dubby delay throws and tape hiss add depth",
                 "long reverb tails and distant metallic noise",
                 "a slowly evolving background drone"),
        mood=("hypnotic and mechanical", "dark and relentless", "meditative and locked"),
        production=("the mix is dry, tight and built for a dark room",
                    "the production is raw and analogue with saturated drums"),
        structure=("a long tool-like intro, a gradual build, a stripped breakdown "
                   "and a driving final section",),
        instruments=("Instruments: Drums, Bass, Synthesizer",),
        prose="hypnotic techno",
        keywords=("hypnotic techno", "rolling bassline", "locked groove",
                  "dub delay", "minimal", "warehouse"),
    ),
    "Techno - Industrial": Genre(
        tags=("Genre: Techno", "Genre: Industrial"),
        bpm=(130, 145),
        drums=("a distorted, overdriven kick hitting hard",
               "harsh metallic percussion and crashing noise hits",
               "a pounding beat with clanging factory rhythms"),
        bass=("a distorted acid bass squelching through a resonant filter",
              "a saturated low rumble under the kick"),
        lead=("a screaming, detuned synth line",
              "harsh atonal stabs cutting through the noise",
              "a siren-like lead rising over the beat"),
        texture=("industrial metallic noise and mechanical clanks",
                 "white noise sweeps and distorted room reverb"),
        mood=("brutal and relentless", "raw and physical", "bleak and pounding"),
        production=("the mix is loud, distorted and deliberately harsh",),
        structure=("a noise intro, a punishing main section, a brief drop to "
                   "percussion, then heavier again",),
        instruments=("Instruments: Drums, Synthesizer, Bass",),
        prose="industrial techno",
        keywords=("industrial techno", "distorted kick", "acid bass",
                  "metallic percussion", "harsh", "warehouse"),
    ),
    "Techno - Melodic": Genre(
        tags=("Genre: Techno", "Genre: Electronic"),
        bpm=(120, 126),
        drums=("a clean four-to-the-floor kick with crisp hats",
               "a driving beat with a soft clap on the offbeat"),
        bass=("a warm rolling bassline with a gentle glide",
              "a deep, melodic sub following the chord changes"),
        lead=("a wistful arpeggio climbing over the groove",
              "a wide, emotive pad chord progression",
              "a plucked melodic hook with long delay"),
        texture=("shimmering high pads and airy noise sweeps",
                 "warm analogue drift and soft tape saturation"),
        mood=("emotive and widescreen", "hopeful and driving", "bittersweet and warm"),
        production=("the mix is wide, clean and lush",),
        structure=("an atmospheric intro, a melodic build, a full emotional peak, "
                   "then a long outro",),
        instruments=("Instruments: Synthesizer, Drums, Bass",),
        prose="melodic techno",
        keywords=("melodic techno", "emotive pads", "arpeggio", "wide reverb",
                  "driving groove", "bittersweet"),
    ),
    "House - Deep": Genre(
        tags=("Genre: House", "Genre: Deep House"),
        bpm=(118, 124),
        drums=("a soft four-to-the-floor kick with brushed hats",
               "a warm, swung groove with light percussion"),
        bass=("a deep, round bassline with a soft attack",
              "a warm sub that rolls gently under the chords"),
        lead=("warm Rhodes chords with a soulful lift",
              "a muted jazz guitar figure",
              "a soft pad chord progression drifting over the groove"),
        texture=("vinyl crackle and soft room reverb warm the whole track",
                 "airy pads and shaker layers widen the groove"),
        mood=("warm and soulful", "late-night and groovy", "deep and unhurried"),
        production=("the production is warm and analogue with gentle tape saturation",),
        structure=("a drum intro, a long deep groove, a stripped break, then the "
                   "full arrangement returns",),
        instruments=("Instruments: Electric Piano, Bass, Drums, Synthesizer",),
        prose="deep house",
        keywords=("deep house", "rhodes chords", "warm sub bass", "shuffled hats",
                  "soulful", "late night"),
    ),
    "House - Classic": Genre(
        tags=("Genre: House",),
        bpm=(122, 128),
        drums=("a punchy four-to-the-floor kick with a crisp clap",
               "a swinging drum groove with live-feeling percussion"),
        bass=("a bouncing filtered bassline",
              "a round, syncopated 808-style bass"),
        lead=("a gospel-flavoured piano riff",
              "a plucked organ stab pattern",
              "a bright disco string line"),
        texture=("vinyl crackle and warm room reverb",
                 "tambourine and shaker lifting the chorus"),
        mood=("uplifting and euphoric", "joyful and warm", "classic and bouncy"),
        production=("the mix is bright, punchy and club-ready",),
        structure=("a DJ-friendly drum intro, a building sixteen bars, a euphoric "
                   "drop and a stripped outro",),
        instruments=("Instruments: Piano, Bass, Drums, Organ",),
        prose="classic house",
        keywords=("classic house", "gospel piano", "disco strings",
                  "four on the floor", "handclaps", "euphoric"),
    ),
    "House - Tech": Genre(
        tags=("Genre: House", "Genre: Techno"),
        bpm=(124, 130),
        drums=("a tight, dry kick with clipped closed hats",
               "a stripped groove with a sharp rimshot"),
        bass=("a syncopated, punchy bass hook",
              "a rubbery filtered bassline driving the groove"),
        lead=("a chopped vocal stab repeating on the offbeat",
              "a minimal plucked riff with heavy sidechain"),
        texture=("dry percussion loops and short delay throws",
                 "subtle white noise rises into each section"),
        mood=("driving and stripped", "hypnotic and funky", "dark and rolling"),
        production=("the mix is tight, dry and built for a big room",),
        structure=("a long percussive intro, a rolling main groove, a filtered "
                   "break, then back to the groove",),
        instruments=("Instruments: Drums, Bass, Synthesizer",),
        prose="tech house",
        keywords=("tech house", "vocal stabs", "rubbery bass", "dry percussion",
                  "sidechain", "rolling groove"),
    ),
    "Dubstep - Deep": Genre(
        tags=("Genre: Dubstep", "Genre: Dub", "Genre: Bass"),
        bpm=(138, 142),
        drums=(
            "a sparse half-time beat with a dry rimshot on the third beat",
            "a skeletal two-step pattern with shuffled hats and long gaps",
            "a restrained beat with a soft kick and a cracking wooden snare",
            "swung percussion with a single tambourine hit marking the bar",
        ),
        bass=(
            "an enormous sine sub moving in slow, whole notes",
            "a deep dub bassline that swells and decays under everything",
            "a warm sub felt in the chest rather than heard, drifting slowly in pitch",
            "a heavy sub pressure that holds one note for bars at a time",
        ),
        lead=(
            "a minor key dub chord stab drenched in tape delay",
            "a distant melodica line echoing into the space",
            "a sparse bell melody left to ring out",
            "a lonely, detuned string pad drifting across the bars",
        ),
        texture=(
            "cavernous reverb and long dub delay throws",
            "vinyl crackle, rain and distant room noise",
            "a low drone humming underneath the whole track",
        ),
        mood=(
            "meditative and heavy", "dark and spacious",
            "dread-laden and warm", "hypnotic and patient",
        ),
        production=(
            "the production is deep and murky, built for a sound system",
            "the mix prizes weight and space over loudness, with enormous low end",
        ),
        structure=(
            "a long atmospheric intro, the sub entering as the drop rather than "
            "any gimmick, sixteen-bar sections, and a stripped dub outro",
            "it rolls patiently, dropping to bass and percussion in the middle "
            "before the full weight returns",
        ),
        instruments=("Instruments: Bass, Drums, Synthesizer",),
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
        ),
        bass=(
            "a growling wobble bass modulated by an LFO",
            "a screaming talking bass full of formant movement",
            "a violently distorted mid-range bass",
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
        prose="brostep",
        keywords=("brostep", "wobble bass", "half-time drums", "huge snare",
                  "supersaw lead", "sub drop"),
    ),
    "Glitch Hop": Genre(
        tags=("Genre: Glitch Hop", "Genre: Hip Hop", "Genre: Electronic"),
        bpm=(100, 112),
        drums=(
            "a chopped breakbeat cut into stuttering micro-edits",
            "heavy hip-hop drums with glitched retriggers and gated stutters",
            "a swung beat interrupted by rapid triplet fills and tape stops",
            "thick, compressed drums with a snare that stutters into the next bar",
        ),
        bass=(
            "a heavily processed synth bass that talks and morphs",
            "a fat, distorted bass riff with a funky swagger",
            "a bit-crushed sub that grinds under the groove",
            "a rubbery modulated bass locked to the drum edits",
        ),
        lead=(
            "a filtered funk guitar sample chopped into a riff",
            "a warped, pitch-bent synth melody",
            "a chopped vocal shard stuttering on the offbeat",
            "a warm, melodic synth line cutting through the grit",
        ),
        texture=(
            "granular glitches, digital debris and reversed hits",
            "bit-crushed artefacts and tape-stop sweeps between sections",
            "vinyl crackle under heavily processed sound design",
        ),
        mood=(
            "funky and mechanical", "gritty and cinematic",
            "playful and heavy", "swaggering and warped",
        ),
        production=(
            "the production is dense and heavily sound-designed, punchy and mid-tempo",
            "the mix is thick and gritty with every element processed hard",
        ),
        structure=(
            "an atmospheric intro, a heavy swung groove, a glitched breakdown "
            "where everything stutters, then a fuller final groove",
        ),
        instruments=("Instruments: Drums, Bass, Synthesizer, Guitar",),
        prose="glitch hop",
        keywords=("glitch hop", "stutter edits", "chopped breaks", "processed bass",
                  "hip-hop swing", "bitcrush", "tape stop", "sound design"),
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
    "Future Garage": Genre(
        tags=("Genre: Garage", "Genre: Electronic", "Genre: Chillout"),
        bpm=(128, 138),
        drums=(
            "a soft two-step shuffle with brushed, distant snares",
            "a muted skippy beat mixed low under the pads",
            "gentle clicks and shakers with a light, padded kick",
        ),
        bass=(
            "a warm, restrained sub that never dominates",
            "a soft filtered bassline sitting deep in the mix",
            "a muted sub pulse felt more than heard",
        ),
        lead=(
            "a pitched, wordless vocal fragment drifting in and out",
            "a muted piano figure buried in reverb",
            "a soft bell melody half-hidden behind the pads",
        ),
        texture=(
            "rain, room noise and tape hiss under everything",
            "wide reverb tails and gentle vinyl crackle",
            "distant city ambience and soft granular haze",
        ),
        mood=("wistful and hazy", "calm and introspective", "melancholic and warm"),
        production=(
            "the mix is soft-edged, low-passed and unhurried",
            "the production is muted and diffuse, nothing sharp",
        ),
        structure=(
            "it drifts in on atmosphere, settles into a gentle shuffle, thins out "
            "in the middle and fades rather than ending",
        ),
        instruments=("Instruments: Synthesizer, Piano, Drums, Bass",),
        prose="future garage",
        keywords=("future garage", "two-step shuffle", "muted sub", "vocal chops",
                  "rainy atmosphere", "reverb-soaked", "study beats"),
    ),
    "Post-Dubstep": Genre(
        tags=("Genre: Garage", "Genre: Downtempo", "Genre: Electronic"),
        bpm=(128, 138),
        drums=(
            "a clattering, unquantised two-step pattern that never sits on the grid",
            "sparse garage drums made of vinyl clicks, lighter flicks and rimshots",
            "a loose shuffle with a dry snare and long silences between hits",
            "hand-placed percussion that drags and rushes like a worn tape",
        ),
        bass=(
            "a deep, warm sub that appears for a few bars and vanishes",
            "a soft low pulse buried far beneath the surface noise",
            "a muted sub weight that never resolves anywhere",
        ),
        lead=(
            "a pitched-up wordless vocal fragment, anonymous and yearning",
            "a slowed, time-stretched R&B vocal shard repeating out of context",
            "a single detuned synth chord holding across the whole section",
            "a faint, ghostly melody half-buried in the hiss",
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
        ),
        structure=(
            "it fades in on crackle and rain, drifts through loose sections that "
            "never quite repeat, and dissolves rather than ending",
            "a long ambient opening, a broken shuffle that comes and goes, and a "
            "final section stripped back to vocal and noise",
        ),
        instruments=("Instruments: Drums, Bass, Synthesizer",),
        prose="post-dubstep",
        keywords=("post-dubstep", "two-step", "vinyl crackle", "pitched vocal chops",
                  "rain", "melancholy", "off-grid", "night bus", "lo-fi"),
    ),
    "Psydub": Genre(
        tags=("Genre: Dub", "Genre: Chillout", "Genre: Electronic"),
        bpm=(85, 110),
        drums=(
            "a slow dub beat with a heavy, delayed rimshot",
            "loose organic percussion with hand drums and shakers",
            "a laid-back halftime groove with tape-delayed snares",
        ),
        bass=(
            "a deep, round dub bassline walking slowly",
            "a warm analogue sub with a long, soft decay",
            "a rolling bass figure that repeats hypnotically",
        ),
        lead=(
            "a psychedelic synth line bending through a filter",
            "a sitar-like melody echoing into the distance",
            "sparse marimba and kalimba figures drifting over the beat",
            "a melodica line soaked in spring reverb",
        ),
        texture=(
            "long dub delay throws trailing off into space",
            "field recordings of forest and water under the groove",
            "swirling phased pads and backwards textures",
        ),
        mood=("hypnotic and warm", "psychedelic and unhurried", "earthy and spacious"),
        production=(
            "the production is warm and analogue with heavy tape delay",
            "the mix is deep, dubby and wide, everything drenched in space",
        ),
        structure=(
            "it builds slowly from percussion and bass, layers textures through "
            "the middle, and strips back to the dub groove at the end",
        ),
        instruments=("Instruments: Bass, Drums, Synthesizer, Percussion",),
        prose="psydub",
        keywords=("psydub", "dub delay", "hand percussion", "analogue bass",
                  "psychedelic", "forest field recordings", "downtempo"),
    ),
    "Trip Hop": Genre(
        tags=("Genre: Trip Hop", "Genre: Downtempo"),
        bpm=(75, 95),
        drums=(
            "a heavy, sluggish break dragging behind the beat",
            "dusty sampled drums with a thick, compressed snare",
            "a slow boom-bap groove with tambourine on the offbeat",
        ),
        bass=(
            "a thick upright bass line walking under the beat",
            "a fuzzy analogue sub with a slow attack",
        ),
        lead=(
            "a minor key string sample looping mournfully",
            "a detuned Rhodes chord progression",
            "a muted trumpet line drifting over the groove",
            "a haunting theremin-like lead",
        ),
        texture=(
            "vinyl crackle, tape wow and distant record noise",
            "cinematic string swells and low choir pads",
        ),
        mood=("brooding and cinematic", "smoky and melancholic", "paranoid and cool"),
        production=(
            "the production is dark, sampled and heavily filtered",
            "the mix is thick and mid-heavy, like an old record",
        ),
        structure=(
            "a looped intro, a long central groove with layers added and removed, "
            "and a stripped outro",
        ),
        instruments=("Instruments: Drums, Bass, Electric Piano, Strings",),
        prose="trip hop",
        keywords=("trip hop", "dusty drums", "vinyl crackle", "minor strings",
                  "rhodes", "downtempo", "cinematic"),
    ),
    "Dub Techno": Genre(
        tags=("Genre: Techno", "Genre: Dub", "Genre: Minimal"),
        bpm=(118, 128),
        drums=(
            "a soft, muffled four-to-the-floor kick with brushed hats",
            "a restrained beat with a clicking rimshot and little else",
        ),
        bass=(
            "a deep, warm sub pulse locked to the kick",
            "a slow analogue bass that breathes with the chords",
        ),
        lead=(
            "a filtered chord stab drenched in delay, repeating for minutes",
            "a soft, detuned pad chord decaying into the reverb",
        ),
        texture=(
            "cavernous dub delay and endless reverb tails",
            "tape hiss, static and faint crackle throughout",
            "slowly evolving background drones",
        ),
        mood=("hypnotic and submerged", "cold and meditative", "warm and endless"),
        production=(
            "the production is deep, murky and heavily processed",
            "the mix is soft-edged with everything far back in the room",
        ),
        structure=(
            "it evolves almost imperceptibly, adding and removing a single "
            "element at a time across the whole track",
        ),
        instruments=("Instruments: Synthesizer, Drums, Bass",),
        prose="dub techno",
        keywords=("dub techno", "chord stabs", "tape delay", "hypnotic",
                  "muffled kick", "deep reverb", "minimal"),
    ),
    "Downtempo": Genre(
        tags=("Genre: Downtempo", "Genre: Chillout"),
        bpm=(85, 105),
        drums=(
            "a relaxed, padded beat with soft brushed percussion",
            "an easy mid-tempo groove with shakers and light congas",
            "a loose, unhurried drum pattern low in the mix",
        ),
        bass=(
            "a warm, simple bassline with plenty of room",
            "a soft analogue sub holding the harmony",
        ),
        lead=(
            "a nylon guitar figure picked gently",
            "a warm electric piano progression",
            "a soft flute or whistle melody drifting over the top",
        ),
        texture=(
            "ocean and evening ambience under the groove",
            "warm analogue pads and gentle tape saturation",
        ),
        mood=("sunlit and unhurried", "calm and golden", "relaxed and open"),
        production=(
            "the production is warm and analogue, soft at every edge",
        ),
        structure=(
            "it opens on atmosphere, settles into an easy groove, and drifts out",
        ),
        instruments=("Instruments: Guitar, Electric Piano, Bass, Percussion",),
        prose="downtempo",
        keywords=("downtempo", "balearic", "nylon guitar", "warm pads",
                  "soft percussion", "sunset", "chillout"),
    ),
    "Chillwave": Genre(
        tags=("Genre: Chillwave", "Genre: Electronic", "Genre: Chillout"),
        bpm=(95, 115),
        drums=(
            "a soft gated drum machine pattern, slightly washed out",
            "a hazy beat with a padded kick and lo-fi snare",
        ),
        bass=(
            "a warm analogue bass pulse, gently detuned",
            "a soft synth bass sitting under the wash",
        ),
        lead=(
            "a nostalgic, detuned synth melody",
            "a chorus-drenched guitar figure repeating",
            "a pitched vocal sample stretched into a pad",
        ),
        texture=(
            "heavy tape wobble and sun-bleached saturation",
            "wide chorus and long, hazy reverb on everything",
        ),
        mood=("nostalgic and dreamlike", "hazy and warm", "wistful and faded"),
        production=(
            "the production is washed out and lo-fi, like a faded tape",
        ),
        structure=(
            "a slow synth fade-in, a steady dreamlike middle, a long fade out",
        ),
        instruments=("Instruments: Synthesizer, Drums, Guitar, Bass",),
        prose="chillwave",
        keywords=("chillwave", "tape wobble", "detuned synths", "dreamy",
                  "sun-bleached", "lo-fi", "nostalgic"),
    ),
    "IDM": Genre(
        tags=("Genre: Electronic", "Genre: IDM"),
        bpm=(90, 140),
        drums=(
            "intricate glitched percussion, cut and stuttered",
            "a broken, constantly shifting beat that never quite repeats",
            "crisp programmed drums with micro-edits and rolls",
        ),
        bass=(
            "a warm analogue bass wandering under the glitches",
            "a low sine pulse anchoring the chaos",
        ),
        lead=(
            "a fragile, detuned melody played on a soft synth",
            "bell tones arranged in shifting, generative patterns",
            "a melancholy pad progression underneath the edits",
        ),
        texture=(
            "granular artefacts, clicks and digital debris",
            "soft, wide pads offsetting the sharp percussion",
        ),
        mood=("melancholy and intricate", "playful and strange", "cold and beautiful"),
        production=(
            "the production is precise and detailed, clinical but warm underneath",
        ),
        structure=(
            "a quiet melodic opening, increasingly complex rhythmic edits through "
            "the middle, resolving back to the melody",
        ),
        instruments=("Instruments: Synthesizer, Drums",),
        prose="IDM",
        keywords=("idm", "glitch percussion", "braindance", "detuned melody",
                  "generative", "microedits"),
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
    tags.append(chosen_instruments or (genre.instruments[0] if genre.instruments else ""))
    tags = [tag for tag in tags if tag]
    core_phrases = [drums, bass, lead]
    rng.shuffle(core_phrases)

    if character:
        colour = [rng.choice(genre.texture), *character]
    else:
        colour = [rng.choice(genre.texture)]
        for pool in (SPACE, EFFECTS, ERA):
            pick = rng.choice(pool)
            if pick and rng.random() < 0.6:
                colour.append(pick)
        rng.shuffle(colour)
        colour = colour[: rng.randint(1, min(3, len(colour)))]
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

    sentences = [f"{opening}."]
    sentences.append(
        f"{_upper_first(core_phrases[0])} sits under {core_phrases[1]}"
        f", with {core_phrases[2]}."
    )
    sentences.append(_upper_first(colour[0]) + (
        f", {', '.join(colour[1:])}." if len(colour) > 1 else "."
    ))
    if structure:
        sentences.append(f"Structurally, {structure}.")
    elif genre.structure and rng.random() < 0.7:
        sentences.append(f"Structurally, {rng.choice(genre.structure)}.")
    if rng.random() < 0.6:
        sentences.append(_upper_first(rng.choice(genre.production)) + ".")
    if extra.strip():
        sentences.append(extra.strip().rstrip(".") + ".")
    return ", ".join(tags) + ". " + " ".join(sentences)
