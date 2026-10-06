"""SoulX-Singer score control, MLX weights through the official PyTorch module.

Executes inside .venv-soulx. The timbre is the English example prompt shipped
with the bridge. A written line is one pitched note per word.
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

CLONE = Path.home() / ".cache" / "ai-music-generator" / "SoulX-Singer-MLX"
PROMPT_WAV = CLONE / "example" / "audio" / "en_prompt.mp3"
PROMPT_META = CLONE / "example" / "audio" / "en_prompt.json"
MODEL_ID = "mlx-community/SoulX-Singer"


def seed_inference(seed: int) -> None:
    import torch
    torch.manual_seed(seed)


def build_target(lyrics: str, notes: list[dict], word_phones: list[list[str]], allowed: set[str] | None = None) -> dict:
    """Metadata SoulX reads. Pitched notes and words must be the same length."""
    words = lyrics.split()
    if not words:
        raise ValueError("lyrics are empty")
    pitched = [note for note in notes if int(note["pitch"]) > 0]
    if len(words) != len(pitched):
        word_word = "word" if len(words) == 1 else "words"
        note_word = "note" if len(pitched) == 1 else "notes"
        raise ValueError(f"{len(words)} {word_word} and {len(pitched)} pitched {note_word}")
    if len(word_phones) != len(words):
        raise ValueError("each word needs a pronunciation")
    phonemes: list[str] = []
    pitches: list[str] = []
    types: list[str] = []
    durations: list[str] = []
    texts: list[str] = []
    word_index = 0
    for note in notes:
        pitch = int(note["pitch"])
        seconds = float(note["seconds"])
        if seconds <= 0:
            raise ValueError("a note duration must be positive")
        durations.append(f"{seconds:.4f}")
        if pitch <= 0:
            phonemes.append("<SP>")
            pitches.append("0")
            types.append("1")
            texts.append("<SP>")
            continue
        phones = word_phones[word_index]
        if not phones:
            raise ValueError(f"no pronunciation for {words[word_index]!r}")
        for phone in phones:
            name = f"en_{phone}"
            if allowed is not None and name not in allowed:
                raise ValueError(f"{words[word_index]!r} uses {name}, which SoulX does not have")
        phonemes.append("en_" + "-".join(phones))
        pitches.append(str(pitch))
        types.append("2")
        texts.append(words[word_index])
        word_index += 1
    total_ms = int(round(sum(float(note["seconds"]) for note in notes) * 1000))
    return {
        "index": f"vocal_0_{total_ms}",
        "language": "English",
        "time": [0, total_ms],
        "duration": " ".join(durations),
        "text": " ".join(texts),
        "phoneme": " ".join(phonemes),
        "note_pitch": " ".join(pitches),
        "note_type": " ".join(types),
        "f0": "",
    }


def phones_for(word: str, pronounce) -> list[str]:
    """ARPAbet phones from a g2p callable, punctuation ignored."""
    phones = []
    for token in pronounce(word):
        text = str(token).strip()
        if text[:1].isalpha() and all(char.isalpha() or char in "012" for char in text):
            phones.append(text)
    if not phones:
        raise ValueError(f"no pronunciation for {word!r}")
    return phones


def request_from_job(job: dict) -> dict:
    lyrics = str(job.get("lyrics") or "").strip()
    notes = job.get("notes")
    if not lyrics:
        raise ValueError("SoulX needs lyrics")
    if not isinstance(notes, list) or not notes:
        raise ValueError("SoulX needs a melody")
    for note in notes:
        if not isinstance(note, dict) or "pitch" not in note or "seconds" not in note:
            raise ValueError("each note needs a pitch and seconds")
    if job.get("seed") is None:
        raise ValueError("SoulX needs a seed")
    return {"lyrics": lyrics, "notes": notes, "seed": int(job["seed"]), "output_path": job["output_path"]}


def main() -> int:
    job = json.load(sys.stdin)
    try:
        request = request_from_job(job)
    except (KeyError, TypeError, ValueError) as exc:
        sys.stderr.write(str(exc))
        return 2
    if not CLONE.is_dir() or not PROMPT_WAV.is_file() or not PROMPT_META.is_file():
        sys.stderr.write(f"SoulX bridge is not at {CLONE}")
        return 1

    sys.path.insert(0, str(CLONE))
    from g2p_en import G2p
    from huggingface_hub import snapshot_download

    model_dir = CLONE / "models" / "SoulX-Singer"
    if not (model_dir / "svs").is_dir():
        snapshot_download(MODEL_ID, local_dir=str(model_dir))

    phone_set = set(json.loads((CLONE / "soulxsinger/utils/phoneme/phone_set.json").read_text(encoding="utf-8")))
    pronounce = G2p()
    try:
        word_phones = [phones_for(word, pronounce) for word in request["lyrics"].split()]
        target = build_target(request["lyrics"], request["notes"], word_phones, phone_set)
    except (TypeError, ValueError) as exc:
        sys.stderr.write(str(exc))
        return 2

    from cli.inference import process as process_svs
    from scripts.mlx_bridge import load_component_state
    from soulxsinger.models.soulxsinger import SoulXSinger
    from soulxsinger.utils.file_utils import load_config
    seed_inference(request["seed"])
    started = time.time()
    config = load_config(str(CLONE / "soulxsinger/config/soulxsinger.yaml"))
    model = SoulXSinger(config).to("mps")
    model.load_state_dict(load_component_state(model_dir, "svs"), strict=True)
    model.eval().to("mps")
    save_dir = Path(tempfile.mkdtemp(prefix="soulx-"))
    meta_path = save_dir / "target.json"
    meta_path.write_text(json.dumps([target]), encoding="utf-8")

    class Args:
        pass

    args = Args()
    args.device = "mps"
    args.prompt_wav_path = str(PROMPT_WAV)
    args.prompt_metadata_path = str(PROMPT_META)
    args.target_metadata_path = str(meta_path)
    args.phoneset_path = str(CLONE / "soulxsinger/utils/phoneme/phone_set.json")
    args.save_dir = str(save_dir)
    args.auto_shift = True
    args.pitch_shift = 0
    args.control = "score"
    args.use_fp16 = False
    try:
        process_svs(args, config, model)
        produced = save_dir / "generated.wav"
        if not produced.is_file():
            sys.stderr.write("SoulX did not write generated.wav")
            return 1
        os.replace(produced, request["output_path"])
    finally:
        for child in save_dir.iterdir():
            child.unlink(missing_ok=True)
        save_dir.rmdir()
    json.dump(
        {
            "path": request["output_path"],
            "elapsed_seconds": round(time.time() - started, 1),
            "backend": "mlx",
        },
        sys.stdout,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
