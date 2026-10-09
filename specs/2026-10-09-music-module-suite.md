---
status: active
author: stephen+codex
created: 2026-10-09
updated: 2026-10-09
---

# Local music-module suite

## Intent and scope

One local UI for suitable music tools, with Apple Silicon and NVIDIA routes,
preferences and explicit fallbacks. Immediate work is installing and integrating
tools. A downloadable app with optional tool installation is a later milestone.
No paid service calls, gated-licence acceptance or unsupported quality claims.

## Candidate register

Initial routes below reflect documented runtime support, not a local speed test.
An entry is not installed or supported here until its real job passes.

| Module | Purpose | First route to assess | Other route / constraint |
|---|---|---|---|
| Stable Audio 3 SFX | Described sounds | M3 MLX, existing runtime | NVIDIA adapter not integrated; Stability/Gemma terms |
| YuE2 | Lyrics/style to songs and score plans | M3, efficient community MLX | Official CUDA on 4090; weight licence differs from conversion code |
| HeartMuLa 3B | Lyrics/tags to songs | M3 community MLX | Official CUDA lazy loading on 4090; codec weights required |
| DiffSinger | Notes/lyrics with expressive controls | 4090 official PyTorch | Mac ONNX deployment needs inference validation and licensed voicebank |
| Basic Pitch | Audio to MIDI and pitch bends | Mac Core ML | Windows ONNX; Python compatibility or browser runtime needs checking |
| GAME | Singing to MIDI | 4090 official PyTorch | ONNX export alone is not an inference adapter; weight terms need review |
| HeartTranscriptor | Sung lyric transcription | 4090 official runtime | Mac path unverified; not a replacement for song generation |
| SAM Audio | Prompt-directed sound isolation | 4090 official runtime | Gated weights and custom licence; no proven Mac fallback here |
| ACE-Step cover/repaint | Existing-song transformations | Existing MLX/CUDA installations | Wire supported controls; extract is generative, not stem separation |
| Stable Audio LoRA/negative prompts | Adapter-based style and prompt control | Existing M3 MLX runtime | Adapter must match checkpoint; no arbitrary pickle loading |
| MusicFlamingo | Music descriptions and questions | Official CUDA | Non-commercial research weights; not a generator or quality judge |
| Seed-VC | Reference-voice singing conversion | Official Mac/CUDA paths | Archived repository; overlaps installed SoulX SVC; lower priority |
| SongGeneration / LeVo2 | Additional song generation | Pending evidence | Resolve official source, weights and licence before installation |

## Architecture and routing acceptance

- Registry identifies tool capabilities separately from runtime variants. Keep
  existing stable backend IDs so saved tracks and jobs remain readable.
- Each route has OS, accelerator, memory, interpreter, pinned source/weights,
  licence and health state. Local settings hold host addresses and disk paths.
- Auto selects the first healthy supported route; users can see and override it.
  Before submission, check reachability, required model files and valid controls.
- Fall back only before dispatch and only to the same model capability. A failed
  dispatched job is not blindly retried. Record preferred route, actual route and
  reason for fallback with the job and resulting artefact.
- Preserve serial execution initially. Remote operation must not duplicate jobs
  after an uncertain response or lose cancellation and input-file ownership.
- Extend artefacts for audio, MIDI, score and text with typed previews/downloads
  and the same explicit Delete/Undo lifecycle, not hidden permanent copies.
- A module passes an installed end-to-end job, output validation, UI dispatch,
  adversarial tests and independent audit before being labelled ready.

## Licences and sources

- [Stable Audio's official MLX documentation](https://github.com/Stability-AI/stable-audio-3/blob/main/optimized/mlx/README.md): SFX checkpoint, codec pairing and direct text prompts.
- [Official YuE2](https://github.com/multimodal-art-projection/YuE) and [model licence](https://github.com/multimodal-art-projection/YuE/blob/main/MODEL_LICENSE): non-commercial weights with additional individual-creator output permission. Company use needs separate consideration. A conversion's Apache badge does not replace these terms.
- [YuE2 MLX port](https://github.com/vanch007/mlx-Yue) and [alternative converted weights](https://huggingface.co/ahmadw/YuE2-3B-MLX): inspect full codec and quantised paths before selecting a pinned build.
- [HeartMuLa official runtime](https://github.com/HeartMuLa/heartlib), [3B weights](https://huggingface.co/HeartMuLa/HeartMuLa-oss-3B), [codec](https://huggingface.co/HeartMuLa/HeartCodec-oss-20260123) and [MLX port](https://github.com/Acelogic/heartlib-mlx): Apache-2.0 entries; community Mac inference still needs local verification.
- [DiffSinger](https://github.com/openvpi/DiffSinger), [Basic Pitch](https://github.com/spotify/basic-pitch), [GAME](https://github.com/openvpi/GAME): code licences do not clear independently selected voicebanks or model weights.
- [SAM Audio](https://github.com/facebookresearch/sam-audio): checkpoint access and custom terms must be resolved by the user.
- [ACE-Step inference](https://github.com/ace-step/ACE-Step-1.5/blob/main/docs/en/INFERENCE.md): cover/repaint controls require their own adapter mapping.
- [MusicFlamingo model](https://huggingface.co/nvidia/music-flamingo-hf) and [Seed-VC](https://github.com/Plachtaa/seed-vc): restricted model use and archived maintenance respectively prevent treating them as default additions.

## First checkpoint

SFX integration and a recorded suite plan. Shared routing, additional singers,
MIDI/text artefacts and the installer screen remain subsequent work, not delivered
by this first checkpoint. Packaging must not delay useful local tools.
