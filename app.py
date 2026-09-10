"""Local web UI. A thin wrapper over synth.core: no logic lives here.

Everything model-specific (title, licence line, duration cap, which knobs exist) is read
from the registry entry for core.DEFAULT_MODEL, so switching the default cannot leave the
UI advertising the wrong model or licence.
"""
from __future__ import annotations

import gradio as gr

from synth import backends, core

BACKEND = backends.get(core.DEFAULT_MODEL)

# Starting points for work-video backing tracks. Edit freely: they're just prompt text.
PRESETS = {
    "Corporate / uplifting": "uplifting corporate, bright piano, subtle strings, steady four-on-the-floor, optimistic, 110bpm, instrumental",
    "Lo-fi / relaxed": "lo-fi hip hop, warm rhodes piano, soft vinyl crackle, mellow drums, relaxed, 85bpm, instrumental",
    "Ambient / underscore": "ambient underscore, soft evolving pads, sparse piano notes, gentle, unobtrusive, no drums, instrumental",
    "Tech / explainer": "minimal electronic, clean plucky synth arpeggio, light percussion, curious and modern, 100bpm, instrumental",
    "Tension / build": "cinematic tension, low pulsing strings, rising drone, building anticipation, sparse percussion, instrumental",
}


def _generate(prompt, duration, steps, guidance, seed, use_seed):
    if not prompt or not prompt.strip():
        raise gr.Error("Enter a prompt first. Style tags work better than sentences.")
    track = core.generate(
        prompt=prompt.strip(),
        duration=duration,
        seed=int(seed) if use_seed else None,
        # Only hand over the knobs this backend actually has; None means "its default".
        infer_step=int(steps) if BACKEND.default_steps is not None else None,
        guidance_scale=guidance if BACKEND.default_guidance is not None else None,
        model=BACKEND.name,
    )
    status = (
        f"**{track.path.name}**\n\n"
        f"Seed `{track.seed}` · {track.elapsed_seconds}s to generate · {track.duration:.0f}s long\n\n"
        f"Saved to `output/` with a matching `.json` so you can reproduce it."
    )
    return str(track.path), status, track.seed


def build_ui() -> gr.Blocks:
    prompt_hint = (
        "Style tags beat sentences: *`warm rhodes, 85bpm, mellow`* rather than *`something chill`*."
        if BACKEND.prompt_style == "tags"
        else "This model wants a structured caption in prose: genre, BPM, key, scale, arrangement."
    )
    with gr.Blocks(title="Background Music Generator") as demo:
        gr.Markdown(
            "# Background Music Generator\n"
            f"Local instrumental music via `{BACKEND.model_id}` ({BACKEND.licence}). "
            f"{prompt_hint}"
        )

        with gr.Row():
            with gr.Column(scale=3):
                preset = gr.Radio(
                    choices=list(PRESETS), label="Presets", value=None,
                    info="Loads a starting prompt below. Then edit it.",
                )
                prompt = gr.Textbox(
                    label="Prompt", lines=3,
                    placeholder="lo-fi hip hop, warm rhodes piano, soft vinyl crackle, 85bpm, instrumental",
                )
                with gr.Row():
                    duration = gr.Slider(10, int(BACKEND.max_duration), value=min(60, int(BACKEND.max_duration)),
                                         step=5, label="Duration (s)")
                    steps = gr.Slider(20, 120, value=BACKEND.default_steps or 60, step=1, label="Steps",
                                      info="Lower = faster, rougher",
                                      visible=BACKEND.default_steps is not None)
                with gr.Row():
                    guidance = gr.Slider(1, 30, value=BACKEND.default_guidance or 15, step=0.5,
                                         label="Prompt adherence",
                                         visible=BACKEND.default_guidance is not None)
                    seed = gr.Number(value=42, precision=0, label="Seed")
                use_seed = gr.Checkbox(
                    value=False, label="Lock seed",
                    info="Off = new random seed each time. On = reproduce an exact track.",
                )
                go = gr.Button("Generate", variant="primary")

            with gr.Column(scale=2):
                audio = gr.Audio(label="Result", type="filepath")
                status = gr.Markdown()

        preset.change(lambda name: PRESETS.get(name, ""), preset, prompt)
        go.click(
            _generate,
            [prompt, duration, steps, guidance, seed, use_seed],
            [audio, status, seed],
        )
    return demo


def main(share: bool = False, port: int = 7860) -> None:
    build_ui().launch(share=share, server_port=port, inbrowser=True)


if __name__ == "__main__":
    main()
